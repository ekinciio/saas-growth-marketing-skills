"""HTTP fetching that never raises and says honestly what came back.

    from _growthkit import http
    result = http.fetch("linear.app")              # an HTML page
    robots = http.fetch_site_file(result["final_url"] or result["url"], "/robots.txt")

fetch() returns a dict (always the same keys, JSON-serializable):

    status          ok | http_error | blocked | unreachable | js_shell |
                    too_large | not_html
    http_status     final HTTP status code, or None when nothing came back
    url             the normalized URL that was requested
    final_url       URL after redirects
    redirect_chain  [{"url", "status"}] for every hop before the final one
    content_type    MIME type without parameters ("text/html")
    encoding        how the body was decoded
    html            decoded body for kind="html", else None
    text            decoded body for kind="text"/"xml", else None
    bytes           bytes read (after gzip decoding)
    truncated       True when the body hit max_bytes
    elapsed_ms      total time
    error           human-readable reason when status is not ok
    bot_protection  None, or {"vendor", "vendors", "challenge", "signals"}
                    (also set on ok pages: "behind Cloudflare" matters for
                    AI crawler access)
    is_js_shell     True when the HTML is a client-rendered shell
    js_shell_signals  the numbers behind is_js_shell (HTML only)
    soft_404        True when a text file URL answered with an HTML page
    headers         response headers, lower-cased (set-cookie left out)
    cookie_names    names of cookies the response set (bot-wall evidence)

Status rules, in order:
    1. no response (DNS, refused, timeout, TLS, redirect loop) -> unreachable
    2. a bot-protection challenge, or 403/429 behind a known bot wall, or
       any 429 -> blocked
    3. HTTP 4xx/5xx -> http_error
    4. kind="html": not HTML -> not_html; over max_bytes -> too_large;
       client-rendered shell -> js_shell; else ok
       kind="text"/"xml": an HTML body (SPA catch-all, soft 404) ->
       http_error with soft_404=True; over max_bytes -> too_large; else ok

User-Agent policy: HTML pages are fetched with one current desktop browser
UA (BROWSER_UA) because many marketing sites serve bots a different page.
robots.txt, llms.txt and sitemaps are fetched with an honest tool UA
(TOOL_UA), because those files are meant for crawlers. There is no
challenge solving and no UA rotation: a bot wall is reported, not bypassed.
"""

from __future__ import annotations

import gzip
import re
import socket
import time
import zlib
from html import unescape
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse, urlunparse

from . import REPO_URL, __version__
from .cli import import_or_exit
from . import html as _html

requests = import_or_exit("requests")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Refresh when Chrome stable moves on (it ships every two weeks since Sep
# 2026). CI warns when BROWSER_UA_UPDATED is more than 8 weeks old.
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36"
)
BROWSER_UA_UPDATED = "2026-10-24"

TOOL_UA = "SaaSGrowthSkills/%s (+%s)" % (__version__, REPO_URL)

DEFAULT_TIMEOUT = 15.0
# Body size caps per kind. A 5 MB HTML page is already huge (the largest
# marketing page seen in the audit was 2.2 MB); sitemaps may be up to 50 MB
# by spec, but 10 MB of URLs is plenty for an audit.
MAX_BYTES = {"html": 5_000_000, "text": 2_000_000, "xml": 10_000_000}

ACCEPT = {
    "html": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "text": "text/plain,text/markdown;q=0.9,*/*;q=0.5",
    "xml": "application/xml,text/xml;q=0.9,*/*;q=0.5",
}

STATUS_OK = "ok"
STATUS_HTTP_ERROR = "http_error"
STATUS_BLOCKED = "blocked"
STATUS_UNREACHABLE = "unreachable"
STATUS_JS_SHELL = "js_shell"
STATUS_TOO_LARGE = "too_large"
STATUS_NOT_HTML = "not_html"
STATUSES = (
    STATUS_OK, STATUS_HTTP_ERROR, STATUS_BLOCKED, STATUS_UNREACHABLE,
    STATUS_JS_SHELL, STATUS_TOO_LARGE, STATUS_NOT_HTML,
)

_HTML_MIMES = {"text/html", "application/xhtml+xml"}

# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------


def normalize_url(raw: str) -> str:
    """Return an absolute http(s) URL or raise ValueError.

    'linear.app' -> 'https://linear.app/', '//x.com/a' -> 'https://x.com/a'.
    Scheme and host are lower-cased, the fragment is dropped, and anything
    that is not http(s) or has no plausible host is rejected.
    """
    value = (raw or "").strip().strip("<>\"'")
    if not value:
        raise ValueError("Empty URL")
    if value.startswith("//"):
        value = "https:" + value
    elif not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", value):
        if re.match(r"^(?:mailto|javascript|data|file|tel):", value, re.IGNORECASE):
            raise ValueError("Not a web URL: %s" % raw)
        value = "https://" + value
    try:
        parsed = urlparse(value)
        host = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Invalid URL %r: %s" % (raw, exc))
    if parsed.scheme.lower() not in ("http", "https"):
        raise ValueError("Only http and https URLs can be fetched, got %r" % raw)
    netloc = parsed.netloc
    if not host or any(ch.isspace() for ch in netloc) or netloc.startswith("-"):
        raise ValueError("Invalid URL: %r" % raw)
    is_ip = bool(re.match(r"^\d{1,3}(?:\.\d{1,3}){3}$", host)) or ":" in host
    if "." not in host and host != "localhost" and not is_ip:
        raise ValueError("Invalid URL (no domain): %r" % raw)
    if not re.match(r"^[a-z0-9.\-_:\[\]\u00a1-\uffff]+$", host):
        raise ValueError("Invalid host in URL: %r" % raw)
    netloc = host if ":" not in host else "[%s]" % host
    if port:
        netloc = "%s:%d" % (netloc, port)
    if "@" in parsed.netloc:
        netloc = "%s@%s" % (parsed.netloc.rsplit("@", 1)[0], netloc)
    path = parsed.path or "/"
    return urlunparse((parsed.scheme.lower(), netloc, path, parsed.params, parsed.query, ""))


def site_root(url: str) -> str:
    """'https://www.notion.com/pricing?x=1' -> 'https://www.notion.com'."""
    parsed = urlparse(normalize_url(url))
    return "%s://%s" % (parsed.scheme, parsed.netloc)


def site_url(url: str, path: str) -> str:
    """URL of a site-level file: site_url('linear.app/x', '/llms.txt')."""
    return urljoin(site_root(url) + "/", path.lstrip("/"))


# ---------------------------------------------------------------------------
# Body helpers
# ---------------------------------------------------------------------------


def looks_like_html(body: Optional[str]) -> bool:
    """True when a body is an HTML document (used to spot soft 404s).

    robots.txt and llms.txt never start with '<', and sitemaps start with
    '<?xml' or '<urlset'. An SPA catch-all that serves index.html for every
    path starts with '<!doctype html' or '<html'.
    """
    if not body:
        return False
    head = body.lstrip("\ufeff \t\r\n")[:2048].lower()
    if not head.startswith("<"):
        return False
    if head.startswith(("<?xml", "<urlset", "<sitemapindex", "<rss", "<feed")):
        return bool(re.search(r"<html\b", head))
    return bool(re.search(r"<!doctype html|<html\b|<head\b|<body\b|<meta\b|<title\b|<div\b|<script\b", head))


def _content_type(headers: Any) -> Tuple[Optional[str], Optional[str]]:
    """(mime, charset) from a Content-Type header."""
    value = headers.get("content-type") if headers is not None else None
    if not value:
        return None, None
    parts = [p.strip() for p in str(value).split(";")]
    mime = parts[0].lower() or None
    charset = None
    for part in parts[1:]:
        if part.lower().startswith("charset="):
            charset = part.split("=", 1)[1].strip().strip("\"'") or None
    return mime, charset


def _maybe_gunzip(body: bytes, url: str, max_bytes: int) -> Tuple[bytes, bool]:
    """Decompress a .gz file body (sitemap.xml.gz). Returns (body, truncated)."""
    if not body.startswith(b"\x1f\x8b"):
        return body, False
    try:
        decompressor = zlib.decompressobj(16 + zlib.MAX_WBITS)
        data = decompressor.decompress(body, max_bytes)
        return data, bool(decompressor.unconsumed_tail)
    except zlib.error:
        try:
            return gzip.decompress(body)[:max_bytes], False
        except (OSError, EOFError):
            return body, False


class _BodyTimeout(Exception):
    pass


def _read_capped(response: Any, max_bytes: int, deadline: Optional[float]) -> Tuple[bytes, bool]:
    """Read at most max_bytes from a streamed response. Returns (body, truncated)."""
    chunks: List[bytes] = []
    total = 0
    truncated = False
    for chunk in response.iter_content(chunk_size=65536):
        if not chunk:
            continue
        remaining = max_bytes - total
        if len(chunk) > remaining:
            if remaining > 0:
                chunks.append(chunk[:remaining])
                total += remaining
            truncated = True
            break
        chunks.append(chunk)
        total += len(chunk)
        if deadline is not None and time.monotonic() > deadline:
            raise _BodyTimeout()
    return b"".join(chunks), truncated


def _cookie_names(response: Any) -> List[str]:
    names: List[str] = []
    for resp in list(getattr(response, "history", None) or []) + [response]:
        jar = getattr(resp, "cookies", None)
        try:
            keys = list(jar.keys()) if jar is not None else []
        except Exception:  # noqa: BLE001 - a broken cookie jar must not break fetch
            keys = []
        for name in keys:
            if name not in names:
                names.append(name)
        header = None
        headers = getattr(resp, "headers", None)
        if headers is not None:
            header = headers.get("set-cookie")
        if header:
            for match in re.finditer(r"(?:^|,)\s*([A-Za-z0-9_.$\-]+)=", str(header)):
                if match.group(1) not in names:
                    names.append(match.group(1))
    return names


def _describe_exception(exc: BaseException) -> str:
    """Short, readable reason for a failed request."""
    text = str(exc)
    if isinstance(exc, requests.exceptions.SSLError):
        return "TLS/SSL error: %s" % text[:200]
    if isinstance(exc, requests.exceptions.ConnectTimeout):
        return "Connection timed out"
    if isinstance(exc, requests.exceptions.ReadTimeout):
        return "Server stopped responding (read timeout)"
    if isinstance(exc, requests.exceptions.TooManyRedirects):
        return "Too many redirects (redirect loop)"
    if isinstance(exc, requests.exceptions.ConnectionError):
        lowered = text.lower()
        if any(s in lowered for s in ("name or service not known", "nodename nor servname",
                                       "getaddrinfo failed", "failed to resolve", "no address associated")):
            return "DNS lookup failed: the domain does not resolve"
        if "refused" in lowered:
            return "Connection refused"
        return "Connection failed: %s" % text[:200]
    return "%s: %s" % (type(exc).__name__, text[:200])


# ---------------------------------------------------------------------------
# Bot-protection detection
# ---------------------------------------------------------------------------

# (vendor, header name, value regex or None). Presence alone is evidence
# that the vendor sits in front of the site, not that we were blocked.
_HEADER_SIGNALS: List[Tuple[str, str, Optional[str]]] = [
    ("cloudflare", "cf-ray", None),
    ("cloudflare", "server", r"cloudflare"),
    ("cloudflare", "cf-cache-status", None),
    ("akamai", "server", r"akamaighost|akamai"),
    ("akamai", "akamai-grn", None),
    ("akamai", "x-akamai-transformed", None),
    ("akamai", "akamai-cache-status", None),
    ("datadome", "x-datadome", None),
    ("datadome", "x-datadome-cid", None),
    ("datadome", "x-dd-b", None),
    ("datadome", "server", r"datadome"),
    ("imperva", "x-iinfo", None),
    ("imperva", "x-cdn", r"incapsula|imperva"),
    ("sucuri", "x-sucuri-id", None),
    ("sucuri", "x-sucuri-cache", None),
    ("sucuri", "server", r"sucuri"),
    ("aws_waf", "x-amzn-waf-action", None),
    ("vercel", "x-vercel-mitigated", None),
    ("kasada", "x-kpsdk-ct", None),
    ("kasada", "x-kpsdk-cd", None),
]

# Headers that by themselves mean "this response is a challenge".
_CHALLENGE_HEADERS: List[Tuple[str, str, str]] = [
    ("cloudflare", "cf-mitigated", r"challenge"),
    ("aws_waf", "x-amzn-waf-action", r"challenge|captcha|block"),
    ("vercel", "x-vercel-mitigated", r"challenge|deny"),
]

_COOKIE_SIGNALS: List[Tuple[str, str]] = [
    ("cloudflare", r"^(?:__cf_bm|cf_clearance|__cflb)$"),
    ("akamai", r"^(?:_abck|bm_sz|ak_bmsc|bm_sv)$"),
    ("datadome", r"^datadome$"),
    ("perimeterx", r"^_px(?:3|2|hd|vid|de)?$"),
    ("imperva", r"^(?:incap_ses_.*|visid_incap_.*|nlbi_.*)$"),
    ("aws_waf", r"^aws-waf-token$"),
    ("kasada", r"^(?:KP_UIDz.*|x-kpsdk-.*)$"),
]

# Body markers of a challenge or block page: (vendor, pattern, strict).
# Strict markers only ever appear on challenge pages, so they are trusted on
# a near-empty 200 page too. Non-strict markers (scripts some vendors also
# inject into normal pages) are trusted only on an error status or 202.
_BODY_CHALLENGE: List[Tuple[str, re.Pattern, bool]] = [
    ("cloudflare", re.compile(
        r"<title>\s*just a moment\.{0,3}\s*</title>|_cf_chl_opt|/cdn-cgi/challenge-platform/h/|"
        r"cf-browser-verification|attention required! \| cloudflare|sorry, you have been blocked|"
        r"checking your browser before accessing|enable javascript and cookies to continue",
        re.I), True),
    ("datadome", re.compile(r"captcha-delivery\.com", re.I), True),
    ("akamai", re.compile(
        r"<title>\s*access denied\s*</title>[\s\S]{0,2000}reference\s*#|errors\.edgesuite\.net|"
        r"/_sec/cp_challenge|sec-if-cpt-container|powered and protected by akamai", re.I), True),
    ("perimeterx", re.compile(r"px-captcha|captcha\.px-cdn\.net|_pxcaptcha|press (?:&amp;|&) hold", re.I), True),
    ("imperva", re.compile(r"incapsula incident id|request unsuccessful\. incapsula", re.I), True),
    ("imperva", re.compile(r"_incapsula_resource", re.I), False),
    ("sucuri", re.compile(r"sucuri website firewall|cloudproxy@sucuri", re.I), True),
    ("aws_waf", re.compile(r"awswafintegration|token\.awswaf\.com|challenge\.awswaf", re.I), False),
    ("kasada", re.compile(r"kpsdk", re.I), False),
    ("vercel", re.compile(r"vercel security checkpoint", re.I), True),
]

# Generic "prove you are human" wording, trusted only on 401/403/429/503.
_GENERIC_CHALLENGE = re.compile(
    r"verify (?:that )?you are (?:a )?human|are you a robot|unusual traffic from your (?:computer|network)|"
    r"please complete the security check|access to this page has been denied|bot detection|"
    r"you have been blocked|request blocked|automated (?:access|requests|queries)",
    re.I,
)

_VENDOR_PRIORITY = [
    "datadome", "perimeterx", "kasada", "imperva", "akamai", "aws_waf",
    "sucuri", "cloudflare", "vercel", "unknown",
]


def detect_bot_protection(
    http_status: Optional[int],
    headers: Optional[Dict[str, str]],
    body: Optional[str],
    cookie_names: Optional[List[str]] = None,
    visible_words: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """Identify a bot-protection vendor and whether this response is a challenge.

    Returns None when nothing is detected, else {"vendor": primary vendor,
    "vendors": all detected, "challenge": bool, "signals": [evidence]}.
    """
    headers = {str(k).lower(): str(v) for k, v in (headers or {}).items()}
    vendors: List[str] = []
    challenge_vendors: List[str] = []
    signals: List[str] = []

    def add(vendor: str, signal: str, challenge: bool = False) -> None:
        if vendor not in vendors:
            vendors.append(vendor)
        if challenge and vendor not in challenge_vendors:
            challenge_vendors.append(vendor)
        if signal not in signals:
            signals.append(signal)

    for vendor, name, pattern in _HEADER_SIGNALS:
        value = headers.get(name)
        if value is not None and (pattern is None or re.search(pattern, value, re.I)):
            add(vendor, "header %s: %s" % (name, value[:60]))
    for vendor, name, pattern in _CHALLENGE_HEADERS:
        value = headers.get(name)
        if value is not None and re.search(pattern, value, re.I):
            add(vendor, "header %s: %s" % (name, value[:60]), challenge=True)
    for name in cookie_names or []:
        for vendor, pattern in _COOKIE_SIGNALS:
            if re.match(pattern, name):
                add(vendor, "cookie %s" % name)
    status = http_status or 0
    error_status = status >= 400 or status == 202
    sparse = visible_words is not None and visible_words < 150
    if body and (error_status or sparse):
        # Block pages often entity-encode their text ("Reference&#32;&#35;18").
        sample = unescape(body[:200000])
        for vendor, pattern, strict in _BODY_CHALLENGE:
            if not (strict or error_status):
                continue
            match = pattern.search(sample)
            if match:
                add(vendor, "body: %s" % match.group(0)[:60].strip(), challenge=True)
        if status in (401, 403, 429, 503):
            match = _GENERIC_CHALLENGE.search(sample)
            if match:
                add("unknown" if not vendors else vendors[0],
                    "body: %s" % match.group(0)[:60], challenge=True)
    if not vendors:
        return None
    ordered = sorted(vendors, key=lambda v: (v not in challenge_vendors, _VENDOR_PRIORITY.index(v)
                                             if v in _VENDOR_PRIORITY else 99))
    return {
        "vendor": ordered[0],
        "vendors": vendors,
        "challenge": bool(challenge_vendors),
        "signals": signals[:12],
    }


def _is_blocked(http_status: Optional[int], bot: Optional[Dict[str, Any]]) -> bool:
    """A challenge page, any 429, or a 403 from behind a known bot wall.

    A 401 (login required) or a 503 without challenge markers (origin down
    behind a CDN) stays an http_error: blaming a bot wall would mislead.
    """
    if http_status == 429:
        return True
    if not bot:
        return False
    if bot["challenge"]:
        return True
    return http_status == 403


# ---------------------------------------------------------------------------
# fetch
# ---------------------------------------------------------------------------


def _empty_result(url: str, kind: str) -> Dict[str, Any]:
    return {
        "status": STATUS_UNREACHABLE,
        "kind": kind,
        "url": url,
        "http_status": None,
        "final_url": None,
        "redirect_chain": [],
        "content_type": None,
        "encoding": None,
        "html": None,
        "text": None,
        "bytes": 0,
        "truncated": False,
        "elapsed_ms": 0,
        "error": None,
        "bot_protection": None,
        "is_js_shell": False,
        "js_shell_signals": None,
        "soft_404": False,
        "headers": {},
        "cookie_names": [],
    }


def default_headers(kind: str = "html", user_agent: Optional[str] = None) -> Dict[str, str]:
    """Request headers for a kind: browser UA for pages, tool UA for files."""
    return {
        "User-Agent": user_agent or (BROWSER_UA if kind == "html" else TOOL_UA),
        "Accept": ACCEPT.get(kind, ACCEPT["html"]),
        "Accept-Language": "en-US,en;q=0.9",
    }


def new_session() -> Any:
    """A requests.Session. Reuse one per run for keep-alive between requests."""
    return requests.Session()


def fetch(
    url: str,
    kind: str = "html",
    timeout: float = DEFAULT_TIMEOUT,
    max_bytes: Optional[int] = None,
    user_agent: Optional[str] = None,
    headers: Optional[Dict[str, str]] = None,
    session: Any = None,
    retries: int = 1,
    retry_backoff: float = 1.0,
) -> Dict[str, Any]:
    """Fetch a URL and classify the outcome. Never raises for network or HTTP errors.

    kind: "html" for pages, "text" for robots.txt / llms.txt, "xml" for
    sitemaps. retries applies only to connection errors and timeouts (not
    to HTTP errors, and never to a bot wall).
    """
    if kind not in MAX_BYTES:
        raise ValueError("kind must be one of %s" % ", ".join(sorted(MAX_BYTES)))
    started = time.monotonic()
    result = _empty_result(url, kind)
    try:
        url = normalize_url(url)
    except ValueError as exc:
        result["error"] = str(exc)
        return result
    result["url"] = url
    limit = int(max_bytes or MAX_BYTES[kind])
    request_headers = default_headers(kind, user_agent)
    request_headers.update(headers or {})
    own_session = session is None
    client = session if session is not None else new_session()
    try:
        response = None
        attempt = 0
        while response is None:
            try:
                response = client.get(
                    url, headers=request_headers, timeout=timeout,
                    allow_redirects=True, stream=True,
                )
            except requests.exceptions.SSLError as exc:
                result["error"] = _describe_exception(exc)
                return result
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
                if attempt >= retries:
                    result["error"] = _describe_exception(exc)
                    return result
                attempt += 1
                if retry_backoff:
                    time.sleep(retry_backoff * attempt)
            except requests.exceptions.RequestException as exc:
                result["error"] = _describe_exception(exc)
                return result
        try:
            deadline = started + max(float(timeout or DEFAULT_TIMEOUT), 1.0) * 3
            raw, truncated = _read_capped(response, limit, deadline)
        except _BodyTimeout:
            result["error"] = "Timed out while reading the response body"
            result["http_status"] = response.status_code
            return result
        except (requests.exceptions.RequestException, OSError, socket.timeout) as exc:
            result["error"] = "Failed while reading the response body: %s" % _describe_exception(exc)
            result["http_status"] = response.status_code
            return result
        finally:
            try:
                response.close()
            except Exception:  # noqa: BLE001 - closing must never mask the result
                pass
        _classify(result, response, raw, truncated, limit)
        return result
    finally:
        if own_session:
            try:
                client.close()
            except Exception:  # noqa: BLE001
                pass
        result["elapsed_ms"] = int((time.monotonic() - started) * 1000)


def _classify(result: Dict[str, Any], response: Any, raw: bytes, truncated: bool, limit: int) -> None:
    """Fill the result from a response whose body has been read."""
    kind = result["kind"]
    status_code = int(response.status_code)
    result["http_status"] = status_code
    result["final_url"] = str(getattr(response, "url", "") or result["url"])
    result["redirect_chain"] = [
        {"url": str(hop.url), "status": int(hop.status_code)}
        for hop in (getattr(response, "history", None) or [])
    ]
    headers = {str(k).lower(): str(v) for k, v in (response.headers or {}).items()}
    cookie_names = _cookie_names(response)
    result["cookie_names"] = cookie_names
    result["headers"] = {k: v for k, v in headers.items() if k != "set-cookie"}
    mime, charset = _content_type(headers)
    result["content_type"] = mime

    gunzipped = False
    if kind != "html" and (result["final_url"].lower().endswith(".gz") or raw.startswith(b"\x1f\x8b")):
        unpacked, gz_truncated = _maybe_gunzip(raw, result["final_url"], limit)
        gunzipped = unpacked is not raw
        raw, truncated = unpacked, truncated or gz_truncated
    result["bytes"] = len(raw)
    result["truncated"] = truncated

    binary = b"\x00" in raw[:1024]
    textual_mime = gunzipped or mime is None or mime.startswith("text/") or mime in _HTML_MIMES or \
        mime.endswith(("+xml", "/xml", "/json", "+json", "/javascript")) or mime == "application/octet-stream"
    sniffed_markup = looks_like_html(raw[:2048].decode("utf-8", "ignore"))
    body = ""
    # Decode only text: a PDF or image page is never turned into a garbage
    # string. A mislabelled HTML page is still decoded, and so is any
    # non-binary text file (robots.txt is sometimes served with odd types;
    # dropping it would read as an empty, allow-all robots.txt).
    if raw and not binary and (textual_mime or sniffed_markup or kind != "html"):
        body, encoding = _html.decode_bytes(raw, charset, is_html=kind == "html" or sniffed_markup)
        result["encoding"] = encoding

    # For pages the Content-Type is enough; for text files only the body
    # counts (servers often label robots.txt as text/html).
    body_is_html = bool(body) and (looks_like_html(body) or (kind == "html" and mime in _HTML_MIMES))
    shell = _html.js_shell_signals(body) if body_is_html else None
    visible_words = shell["visible_words"] if shell else None

    bot = detect_bot_protection(status_code, headers, body if body_is_html or status_code >= 400 else "",
                                cookie_names, visible_words)
    result["bot_protection"] = bot

    if _is_blocked(status_code, bot):
        result["status"] = STATUS_BLOCKED
        vendor = bot["vendor"] if bot else "rate limit"
        result["error"] = "Blocked by bot protection (%s), HTTP %d" % (vendor, status_code) if bot \
            else "Rate limited (HTTP 429 Too Many Requests)"
        _attach_body(result, kind, body, body_is_html)
        return
    if status_code >= 400 or status_code < 200 or 300 <= status_code < 400:
        result["status"] = STATUS_HTTP_ERROR
        reason = getattr(response, "reason", None) or ""
        result["error"] = ("HTTP %d %s" % (status_code, reason)).strip()
        _attach_body(result, kind, body, body_is_html)
        return

    if kind == "html":
        if binary or not body_is_html:
            result["status"] = STATUS_NOT_HTML
            result["error"] = "Expected an HTML page, got %s" % (mime or "an unknown content type")
            if body:
                result["text"] = body
            return
        result["html"] = body
        result["js_shell_signals"] = shell
        result["is_js_shell"] = bool(shell and shell["is_js_shell"])
        if truncated:
            result["status"] = STATUS_TOO_LARGE
            result["error"] = "Page is larger than %d bytes; only the first %d bytes were read" % (limit, limit)
        elif result["is_js_shell"]:
            result["status"] = STATUS_JS_SHELL
            result["error"] = (
                "Static HTML is a JavaScript shell (%d visible words); render the page in a browser"
                % shell["visible_words"]
            )
        else:
            result["status"] = STATUS_OK
        return

    # Text resources: robots.txt, llms.txt, sitemaps.
    if body_is_html:
        result["status"] = STATUS_HTTP_ERROR
        result["soft_404"] = True
        result["error"] = (
            "Expected a %s file but the server returned an HTML page (soft 404 or SPA catch-all)"
            % ("text" if kind == "text" else "XML")
        )
        return
    if binary:
        result["status"] = STATUS_HTTP_ERROR
        result["error"] = "Expected a %s file but got binary content" % kind
        return
    result["text"] = body
    if truncated:
        result["status"] = STATUS_TOO_LARGE
        result["error"] = "File is larger than %d bytes; only the first %d bytes were read" % (limit, limit)
    else:
        result["status"] = STATUS_OK


def _attach_body(result: Dict[str, Any], kind: str, body: str, body_is_html: bool) -> None:
    """Keep an error page's body (useful evidence) in the matching field."""
    if not body:
        return
    if kind == "html" and body_is_html:
        result["html"] = body
    else:
        result["text"] = body


def fetch_page(url: str, **kwargs: Any) -> Dict[str, Any]:
    """fetch(url, kind="html")."""
    return fetch(url, kind="html", **kwargs)


def fetch_site_file(page_url: str, path: str, kind: Optional[str] = None, **kwargs: Any) -> Dict[str, Any]:
    """Fetch a site-level file such as /robots.txt, /llms.txt or /sitemap.xml.

    kind defaults to "xml" for .xml / .xml.gz paths and "text" otherwise.
    """
    if kind is None:
        kind = "xml" if re.search(r"\.xml(?:\.gz)?$", path, re.I) else "text"
    try:
        target = site_url(page_url, path)
    except ValueError as exc:
        result = _empty_result(page_url, kind)
        result["error"] = str(exc)
        return result
    return fetch(target, kind=kind, **kwargs)


def summarize(result: Dict[str, Any]) -> Dict[str, Any]:
    """A fetch result without the bodies and headers, for JSON output."""
    keep = (
        "status", "kind", "url", "http_status", "final_url", "redirect_chain",
        "content_type", "bytes", "truncated", "elapsed_ms", "error",
        "bot_protection", "is_js_shell", "soft_404",
    )
    summary = {key: result.get(key) for key in keep}
    if result.get("js_shell_signals"):
        summary["js_shell_signals"] = result["js_shell_signals"]
    return summary


__all__ = [
    "BROWSER_UA", "BROWSER_UA_UPDATED", "TOOL_UA", "DEFAULT_TIMEOUT", "MAX_BYTES",
    "STATUS_OK", "STATUS_HTTP_ERROR", "STATUS_BLOCKED", "STATUS_UNREACHABLE",
    "STATUS_JS_SHELL", "STATUS_TOO_LARGE", "STATUS_NOT_HTML", "STATUSES",
    "normalize_url", "site_root", "site_url", "looks_like_html",
    "detect_bot_protection", "default_headers", "new_session",
    "fetch", "fetch_page", "fetch_site_file", "summarize",
]
