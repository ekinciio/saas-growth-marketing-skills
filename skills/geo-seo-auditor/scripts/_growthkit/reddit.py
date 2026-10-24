"""Shared Reddit search client for the growth skills.

Used by reddit-opportunity-finder and brand-mention-scanner so both skills
share one tested implementation of access order, rate limiting and parsing.

Access order (per search)
    1. OAuth API, when REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET are set.
       Reddit only issues these to apps approved under its Responsible
       Builder Policy, so most users will not have them. Full data: score,
       comment count, locked / archived / over_18 flags, flair.
    2. Public RSS (Atom) search feed. The default for everyone else: no key,
       but no score or comment counts, and roughly one request per minute.
    3. Public JSON search, as a fallback when RSS fails for a reason other
       than rate limiting (JSON shares the RSS quota, so retrying it after a
       429 only burns another minute). It returns 403 in most environments;
       after the first 403 the client stops trying it.

Rate limiting
    Reddit sends x-ratelimit-used, x-ratelimit-remaining and
    x-ratelimit-reset (seconds until the window resets) on every response.
    It does NOT send Retry-After on a 429. After every response the client
    records those headers; when remaining is below 1, the next request to
    the same host waits until the reset (plus 1 s, capped at 70 s). A 429
    waits for the reset the same way and is retried once.

Status
    Every HTTP call is appended to ``client.requests_log`` with its own
    status (ok, empty, rate_limited, blocked, auth_error, http_error,
    network_error, parse_error), HTTP status, wait time and rate-limit
    headers. ``search()`` returns a dict with an overall status (ok, empty,
    failed), the method that produced the posts, the per-request entries for
    that search, and separate ``notes`` (degraded mode, fallbacks) and
    ``errors`` (nothing worked).

User-Agent
    Read from REDDIT_USER_AGENT. Reddit asks for the format
    '<platform>:<app id>:<version> (by /u/<your username>)'. The default
    names no person.

Usage (keep one client for a whole run so rate-limit state carries over):

    from _growthkit import reddit
    client = reddit.RedditClient()
    result = client.search(reddit.build_or_query(["notion alternative", "obsidian"]),
                           sort="relevance", time_filter="month")
    if result["status"] == "failed": ...
    for post in result["posts"]: ...

Tests inject ``session`` (anything with ``request(method, url, **kwargs)``),
``sleep``, ``clock`` and ``env`` so no network or real waiting is needed.
"""

from __future__ import annotations

import os
import re
import sys
import time
import warnings
import xml.etree.ElementTree as ET
from datetime import datetime
from html import unescape

# requests is a runtime dependency of the toolkit. The import is guarded so
# that the parsers in this module stay usable (and testable) without it, and
# the LibreSSL warning urllib3 prints on macOS system Python is silenced for
# this import only.
with warnings.catch_warnings():
    warnings.filterwarnings("ignore", message=".*OpenSSL.*")
    try:
        import requests
    except ImportError:  # pragma: no cover - only hit when requests is missing
        requests = None

if requests is not None:
    _NETWORK_ERRORS = (requests.RequestException, OSError)
else:  # pragma: no cover
    _NETWORK_ERRORS = (OSError,)


# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

USER_AGENT_ENV = "REDDIT_USER_AGENT"
CLIENT_ID_ENV = "REDDIT_CLIENT_ID"
CLIENT_SECRET_ENV = "REDDIT_CLIENT_SECRET"

# Neutral default: identifies the toolkit, not any person or Reddit account.
DEFAULT_USER_AGENT = "python:saas-growth-skills:2.0"

WWW_BASE = "https://www.reddit.com"
OAUTH_BASE = "https://oauth.reddit.com"
TOKEN_URL = "https://www.reddit.com/api/v1/access_token"

MAX_WAIT_SECONDS = 70.0
# Used only when a 429 arrives without any x-ratelimit-reset header. The
# unauthenticated window observed in testing was about 60 s.
DEFAULT_429_WAIT_SECONDS = 60.0
# Safety margin added to x-ratelimit-reset before the next request.
RESET_MARGIN_SECONDS = 1.0

MAX_LIMIT = 100
MAX_QUERY_LENGTH = 512  # Reddit caps search queries at 512 characters

SORTS = ("relevance", "new", "top", "comments", "hot")
TIME_FILTERS = ("hour", "day", "week", "month", "year", "all")
TIME_FILTER_SECONDS = {
    "hour": 3600,
    "day": 86400,
    "week": 7 * 86400,
    "month": 30 * 86400,
    "year": 365 * 86400,
    "all": None,
}

METHOD_LABELS = {
    "oauth": "Reddit OAuth API",
    "rss": "Reddit RSS feed",
    "json": "Reddit public JSON API",
}

RSS_NOTE = (
    "Reddit RSS feed used: no scores or comment counts (score and "
    "num_comments are None), and about 1 request per minute without OAuth."
)

ATOM = "{http://www.w3.org/2005/Atom}"
ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}

_SUBREDDIT_RE = re.compile(r"^[A-Za-z0-9_+]+$")
_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")
# Reddit's operators are upper case; NOT may also start a term ('NOT spam').
_BOOLEAN_OP_RE = re.compile(r"(^|\s)(OR|AND|NOT)(\s|$)")
# The '[link]' anchor in an RSS entry's footer points at the shared URL for
# link, image and gallery posts (and back at the thread for self posts).
_RSS_LINK_RE = re.compile(r'<a href="([^"]+)">\s*\[link\]\s*</a>')


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------


def resolve_user_agent(env=None) -> str:
    """Return REDDIT_USER_AGENT from the environment, or the neutral default."""
    env = os.environ if env is None else env
    value = (env.get(USER_AGENT_ENV) or "").strip()
    return value or DEFAULT_USER_AGENT


def quote_term(term: str) -> str:
    """Quote a multi-word keyword so Reddit matches the phrase, not any word.

    A term that is exactly one quoted phrase is kept as is. Any other term
    with its own quotes or OR/AND/NOT operators is wrapped in parentheses
    (otherwise left alone), so joining terms with OR cannot change what an
    operator inside a term applies to.
    """
    term = (term or "").strip()
    if not term:
        return ""
    if len(term) > 1 and term.startswith('"') and term.endswith('"') and term.count('"') == 2:
        return term
    if '"' in term or _BOOLEAN_OP_RE.search(term):
        return "(" + term + ")"
    if " " in term:
        return '"' + term + '"'
    return term


def build_or_query(terms) -> str:
    """Combine keywords into one OR query, e.g. '"a b" OR c'.

    One combined query costs one request instead of one per keyword, which
    matters at about 1 request per minute on RSS.

    Raises:
        ValueError: when no non-empty term is given, or the query is longer
            than Reddit's 512-character limit.
    """
    parts = [quote_term(t) for t in terms]
    parts = [p for p in parts if p]
    if not parts:
        raise ValueError("no keywords given")
    query = " OR ".join(parts)
    if len(query) > MAX_QUERY_LENGTH:
        raise ValueError(
            "combined query is %d characters; Reddit allows %d. "
            "Split the keywords into several searches." % (len(query), MAX_QUERY_LENGTH)
        )
    return query


def normalize_subreddit(name):
    """Turn 'r/SaaS', '/r/SaaS/' or 'SaaS' into 'SaaS'. None stays None."""
    if name is None:
        return None
    cleaned = name.strip().strip("/")
    if cleaned.lower().startswith("r/"):
        cleaned = cleaned[2:]
    if not cleaned or not _SUBREDDIT_RE.match(cleaned):
        raise ValueError("invalid subreddit name: %r" % name)
    return cleaned


def iso_to_epoch(timestamp):
    """Convert an ISO 8601 timestamp to a Unix epoch float, or None."""
    if not timestamp:
        return None
    try:
        return datetime.fromisoformat(timestamp.strip().replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def within_time_filter(posts, time_filter, now=None):
    """Keep posts created inside the --time window (posts without a date are kept).

    RSS results are not always limited to the requested window, so callers
    that promise a window should apply this.
    """
    if time_filter not in TIME_FILTER_SECONDS:
        raise ValueError("time_filter must be one of %s" % ", ".join(TIME_FILTERS))
    window = TIME_FILTER_SECONDS[time_filter]
    if window is None:
        return list(posts)
    now = time.time() if now is None else now
    cutoff = now - window
    return [p for p in posts if p.get("created_utc") is None or p["created_utc"] >= cutoff]


def _header(headers, name):
    """Case-insensitive header lookup that works on plain dicts too."""
    if headers is None:
        return None
    value = headers.get(name)
    if value is not None:
        return value
    lowered = name.lower()
    for key, val in headers.items():
        if key.lower() == lowered:
            return val
    return None


def _to_float(value):
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def parse_rate_headers(headers) -> dict:
    """Read Reddit's x-ratelimit-* headers into floats (None when absent)."""
    return {
        "used": _to_float(_header(headers, "x-ratelimit-used")),
        "remaining": _to_float(_header(headers, "x-ratelimit-remaining")),
        "reset": _to_float(_header(headers, "x-ratelimit-reset")),
    }


def _stderr_log(message: str) -> None:
    print("[reddit] " + message, file=sys.stderr)


def _failure_message(method: str, entry: dict) -> str:
    """One readable line for a failed request, e.g. 'Reddit RSS feed failed: rate_limited (HTTP 429)'."""
    if entry["method"] == "oauth_token":
        label = "Reddit OAuth token request"
    else:
        label = METHOD_LABELS.get(method, method)
    message = "%s failed: %s" % (label, entry["status"])
    if entry["http_status"]:
        message += " (HTTP %s)" % entry["http_status"]
    if entry["status"] in ("network_error", "parse_error") and entry["error"]:
        message += " - " + entry["error"]
    if entry["method"] == "oauth_token":
        message += "; check %s and %s" % (CLIENT_ID_ENV, CLIENT_SECRET_ENV)
    elif method == "json" and entry["status"] == "blocked":
        message += "; Reddit blocks the public JSON API for most clients"
    return message


# --------------------------------------------------------------------------
# Parsers
# --------------------------------------------------------------------------


def _empty_post() -> dict:
    """Common post shape for every access method (unknown values are None)."""
    return {
        "id": "",
        "fullname": "",
        "title": "",
        "subreddit": "",
        "is_user_profile": False,
        "author": "",
        "url": "",
        "external_url": None,
        "created_utc": None,
        "body_text": "",
        "score": None,
        "num_comments": None,
        "upvote_ratio": None,
        "locked": None,
        "archived": None,
        "over_18": None,
        "is_self": None,
        "link_flair_text": None,
        "source": "",
    }


def _is_user_profile(subreddit: str) -> bool:
    lowered = (subreddit or "").lower()
    return lowered.startswith("u_") or lowered.startswith("u/")


def _rss_body_text(content_html: str) -> str:
    """Plain text of an entry's HTML content, without Reddit's footer.

    Reddit appends 'submitted by /u/x to r/y [link] [comments]' to every
    entry; that footer is dropped so the body holds only what the poster
    wrote (empty for link posts).
    """
    if not content_html:
        return ""
    text = _TAG_RE.sub(" ", content_html)
    text = _SPACE_RE.sub(" ", unescape(text)).strip()
    idx = text.rfind("submitted by")
    if idx != -1 and "[comments]" in text[idx:]:
        text = text[:idx].rstrip()
    return text


def _rss_external_url(content_html: str, post_url: str, post_id: str):
    """The URL a link post shares, from the footer's '[link]' anchor.

    The footer is removed from body_text, so this keeps the one useful
    thing in it. Returns None for self posts, where '[link]' points back at
    the thread itself. Relative links (crossposts, which point at the
    original thread) are made absolute.
    """
    matches = _RSS_LINK_RE.findall(content_html or "")
    if not matches:
        return None
    href = unescape(matches[-1]).strip()  # the footer comes last
    if not href:
        return None
    if href.startswith("/"):
        href = WWW_BASE + href
    if href.rstrip("/") == (post_url or "").rstrip("/"):
        return None
    if post_id and ("/comments/%s/" % post_id) in href.rstrip("/") + "/":
        return None  # this post's own thread under another slug
    return href


def parse_atom(xml_text: str) -> list:
    """Parse a Reddit search Atom feed into post dicts.

    Only post entries (ids starting with 't3_') are kept. The feed has no
    score or comment counts, so those fields are None.

    Raises:
        ValueError: when the text is not an Atom feed (for example Reddit's
            HTML block page). ET.ParseError is a subclass of SyntaxError, so
            it is converted to ValueError for a single except clause.
    """
    # Reddit's feed never has a DOCTYPE. Refusing one up front avoids entity
    # expansion tricks in untrusted XML, and an HTML block page (which starts
    # with <!DOCTYPE html>) is reported as what it is.
    if re.search(r"<!(DOCTYPE|ENTITY)", (xml_text or "")[:4096], re.IGNORECASE):
        raise ValueError("response is not an Atom feed (it has a DOCTYPE; likely an HTML page)")
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise ValueError("response is not valid XML: %s" % exc)
    if root.tag != ATOM + "feed":
        raise ValueError("response is not an Atom feed (root <%s>)" % root.tag)

    posts = []
    for entry in root.findall("atom:entry", ATOM_NS):
        fullname = (entry.findtext("atom:id", default="", namespaces=ATOM_NS) or "").strip()
        if not fullname.startswith("t3_"):
            continue  # skip subreddit / user entries

        post = _empty_post()
        post["fullname"] = fullname
        post["id"] = fullname[3:]
        post["title"] = (entry.findtext("atom:title", default="", namespaces=ATOM_NS) or "").strip()

        link = entry.find("atom:link", ATOM_NS)
        post["url"] = link.get("href", "") if link is not None else ""

        category = entry.find("atom:category", ATOM_NS)
        subreddit = category.get("term", "") if category is not None else ""
        post["subreddit"] = subreddit
        post["is_user_profile"] = _is_user_profile(subreddit)

        author = (entry.findtext("atom:author/atom:name", default="", namespaces=ATOM_NS) or "").strip()
        if author.startswith("/u/"):
            author = author[3:]
        post["author"] = author or "[unknown]"

        published = (
            entry.findtext("atom:published", default="", namespaces=ATOM_NS)
            or entry.findtext("atom:updated", default="", namespaces=ATOM_NS)
        )
        post["created_utc"] = iso_to_epoch(published)
        content_html = entry.findtext("atom:content", default="", namespaces=ATOM_NS) or ""
        post["body_text"] = _rss_body_text(content_html)
        post["external_url"] = _rss_external_url(content_html, post["url"], post["id"])
        post["source"] = "rss"
        posts.append(post)
    return posts


def parse_listing_json(data, source: str = "json") -> list:
    """Normalize a Reddit search listing (OAuth or public JSON) into post dicts.

    Keeps the moderation flags (locked, archived, over_18) that callers need
    to drop threads nobody can reply to.

    Raises:
        ValueError: when the payload is not a Reddit listing.
    """
    if not isinstance(data, dict) or not isinstance(data.get("data"), dict):
        raise ValueError("response is not a Reddit listing")
    posts = []
    for child in data["data"].get("children") or []:
        if not isinstance(child, dict) or child.get("kind") not in (None, "t3"):
            continue
        raw = child.get("data")
        if not isinstance(raw, dict):
            continue
        post = _empty_post()
        post["id"] = str(raw.get("id") or "")
        post["fullname"] = str(raw.get("name") or ("t3_" + post["id"] if post["id"] else ""))
        post["title"] = str(raw.get("title") or "")
        subreddit = str(raw.get("subreddit") or "")
        post["subreddit"] = subreddit
        post["is_user_profile"] = _is_user_profile(subreddit)
        post["author"] = str(raw.get("author") or "[deleted]")
        permalink = str(raw.get("permalink") or "")
        post["url"] = WWW_BASE + permalink if permalink.startswith("/") else permalink
        is_self = raw.get("is_self")
        post["is_self"] = is_self
        link_url = str(raw.get("url") or "")
        if is_self is False and link_url and link_url != post["url"]:
            post["external_url"] = link_url
        created = raw.get("created_utc")
        post["created_utc"] = (
            float(created) if isinstance(created, (int, float)) and not isinstance(created, bool) else None
        )
        post["body_text"] = str(raw.get("selftext") or "")
        for key in ("score", "num_comments", "upvote_ratio", "locked", "archived",
                    "over_18", "link_flair_text"):
            post[key] = raw.get(key)
        post["source"] = source
        posts.append(post)
    return posts


# --------------------------------------------------------------------------
# Client
# --------------------------------------------------------------------------


def _default_session():
    if requests is None:
        raise RuntimeError(
            "Missing dependency 'requests'. Install it with: pip install requests"
        )
    return requests.Session()


class RedditClient:
    """Reddit search with RSS/OAuth/JSON access order and header-driven pacing.

    Args:
        session: object with ``request(method, url, **kwargs)`` returning a
            response with ``status_code``, ``headers``, ``text`` and
            ``json()``. Defaults to a requests.Session.
        env: mapping used for REDDIT_* variables. Defaults to os.environ.
        user_agent: overrides REDDIT_USER_AGENT.
        sleep: function used to wait (injected in tests).
        clock: monotonic clock in seconds (injected in tests).
        timeout: per-request timeout in seconds.
        max_wait: cap for any single rate-limit wait (default 70 s).
        log: function receiving progress messages (defaults to stderr).
    """

    def __init__(self, session=None, env=None, user_agent=None, sleep=time.sleep,
                 clock=time.monotonic, timeout: float = 20.0,
                 max_wait: float = MAX_WAIT_SECONDS, log=None):
        self.env = os.environ if env is None else env
        self.user_agent = user_agent or resolve_user_agent(self.env)
        self.session = session if session is not None else _default_session()
        self._sleep = sleep
        self._clock = clock
        self.timeout = timeout
        self.max_wait = max_wait
        self._log = log if log is not None else _stderr_log

        self.requests_log = []
        self._ready_at = {}  # rate-limit bucket (host) -> clock time when free
        self._token = None
        self._token_expires_at = 0.0
        self._oauth_disabled = False
        self.json_blocked = False

    # -- credentials -------------------------------------------------------

    @property
    def has_oauth_credentials(self) -> bool:
        return bool((self.env.get(CLIENT_ID_ENV) or "").strip()
                    and (self.env.get(CLIENT_SECRET_ENV) or "").strip())

    @property
    def oauth_enabled(self) -> bool:
        return self.has_oauth_credentials and not self._oauth_disabled

    # -- rate limiting -----------------------------------------------------

    def _wait_for(self, bucket: str) -> float:
        """Sleep until the bucket's rate-limit window has reset. Returns seconds waited."""
        ready_at = self._ready_at.get(bucket)
        if ready_at is None:
            return 0.0
        wait = min(ready_at - self._clock(), self.max_wait)
        if wait <= 0:
            return 0.0
        self._log("waiting %.0fs for the Reddit rate-limit window to reset" % wait)
        self._sleep(wait)
        return wait

    def _schedule(self, bucket: str, seconds: float) -> None:
        """Block the bucket for ``seconds`` (capped) from now."""
        seconds = max(0.0, min(seconds, self.max_wait))
        self._ready_at[bucket] = self._clock() + seconds

    def _record_rate_headers(self, bucket: str, rate: dict) -> None:
        remaining, reset = rate["remaining"], rate["reset"]
        if remaining is not None and remaining < 1 and reset is not None:
            self._schedule(bucket, reset + RESET_MARGIN_SECONDS)

    # -- HTTP --------------------------------------------------------------

    def _send(self, method: str, http_method: str, url: str, bucket: str,
              params=None, headers=None, data=None, auth=None, parse=None):
        """Send one logical request (retrying once on 429) and log each attempt.

        Returns:
            (payload, entry): ``payload`` is the parsed result (or the raw
            response when ``parse`` is None) and None on failure; ``entry``
            is the log entry of the final attempt.
        """
        all_headers = {"User-Agent": self.user_agent}
        all_headers.update(headers or {})
        for attempt in (1, 2):
            waited = self._wait_for(bucket)
            entry = {
                "method": method,
                "url": url,
                "params": dict(params or {}),
                "attempt": attempt,
                "http_status": None,
                "status": None,
                "waited_seconds": round(waited, 1),
                "ratelimit": {"used": None, "remaining": None, "reset": None},
                "error": None,
            }
            self.requests_log.append(entry)
            try:
                response = self.session.request(
                    http_method, url, params=params, headers=all_headers,
                    data=data, auth=auth, timeout=self.timeout,
                )
            except _NETWORK_ERRORS as exc:
                entry["status"] = "network_error"
                entry["error"] = "%s: %s" % (type(exc).__name__, exc)
                return None, entry

            entry["http_status"] = response.status_code
            rate = parse_rate_headers(response.headers)
            entry["ratelimit"] = rate
            self._record_rate_headers(bucket, rate)

            if response.status_code == 429:
                entry["status"] = "rate_limited"
                entry["error"] = "HTTP 429 Too Many Requests"
                # Reddit sends x-ratelimit-reset, not Retry-After; accept either.
                wait = rate["reset"]
                if wait is None:
                    wait = _to_float(_header(response.headers, "Retry-After"))
                if wait is None:
                    wait = DEFAULT_429_WAIT_SECONDS
                    self._schedule(bucket, wait)
                else:
                    self._schedule(bucket, wait + RESET_MARGIN_SECONDS)
                if attempt == 1:
                    continue  # retry once after the wait in _wait_for
                return None, entry

            if response.status_code in (401, 403):
                entry["status"] = "auth_error" if response.status_code == 401 else "blocked"
                entry["error"] = "HTTP %d" % response.status_code
                return None, entry
            if not 200 <= response.status_code < 300:
                entry["status"] = "http_error"
                entry["error"] = "HTTP %d" % response.status_code
                return None, entry

            if parse is None:
                entry["status"] = "ok"
                return response, entry
            try:
                payload = parse(response)
            except (ValueError, TypeError, AttributeError, KeyError) as exc:
                # Malformed or unexpected payloads are a per-request status,
                # never a crash in the calling skill.
                entry["status"] = "parse_error"
                entry["error"] = "%s: %s" % (type(exc).__name__, exc)
                return None, entry
            entry["status"] = "ok" if payload else "empty"
            return payload, entry
        return None, entry  # pragma: no cover - loop always returns

    # -- OAuth -------------------------------------------------------------

    def _get_token(self):
        """Return a cached app-only bearer token, fetching one when needed."""
        if self._token and self._clock() < self._token_expires_at:
            return self._token, None

        def parse(response):
            body = response.json()
            if not isinstance(body, dict) or not body.get("access_token"):
                raise ValueError("no access_token in token response")
            return body

        body, entry = self._send(
            "oauth_token", "POST", TOKEN_URL, bucket="www",
            data={"grant_type": "client_credentials"},
            auth=(self.env.get(CLIENT_ID_ENV, "").strip(),
                  self.env.get(CLIENT_SECRET_ENV, "").strip()),
            parse=parse,
        )
        if body is None:
            if entry["status"] in ("auth_error", "blocked", "parse_error") or entry["http_status"] == 400:
                # Bad or unapproved credentials will not start working mid-run.
                self._oauth_disabled = True
            return None, entry
        self._token = body["access_token"]
        expires_in = _to_float(body.get("expires_in")) or 3600.0
        self._token_expires_at = self._clock() + max(expires_in - 60.0, 60.0)
        return self._token, entry

    # -- search ------------------------------------------------------------

    @staticmethod
    def _search_params(query, sort, time_filter, limit, subreddit, extra=None):
        params = {"q": query, "sort": sort, "t": time_filter, "limit": limit, "type": "link"}
        if subreddit:
            params["restrict_sr"] = 1
        params.update(extra or {})
        return params

    def _search_oauth(self, query, sort, time_filter, limit, subreddit):
        token, token_entry = self._get_token()
        if token is None:
            return None, token_entry
        path = "/r/%s/search" % subreddit if subreddit else "/search"
        params = self._search_params(query, sort, time_filter, limit, subreddit, {"raw_json": 1})
        posts, entry = self._send(
            "oauth", "GET", OAUTH_BASE + path, bucket="oauth", params=params,
            headers={"Authorization": "bearer " + token},
            parse=lambda r: parse_listing_json(r.json(), source="oauth"),
        )
        if entry["status"] == "auth_error":
            self._token = None  # expired or revoked; fetch a new one next time
        return posts, entry

    def _search_rss(self, query, sort, time_filter, limit, subreddit):
        path = "/r/%s/search.rss" % subreddit if subreddit else "/search.rss"
        params = self._search_params(query, sort, time_filter, limit, subreddit)
        return self._send("rss", "GET", WWW_BASE + path, bucket="www", params=params,
                          parse=lambda r: parse_atom(r.text))

    def _search_json(self, query, sort, time_filter, limit, subreddit):
        path = "/r/%s/search.json" % subreddit if subreddit else "/search.json"
        params = self._search_params(query, sort, time_filter, limit, subreddit, {"raw_json": 1})
        posts, entry = self._send(
            "json", "GET", WWW_BASE + path, bucket="www", params=params,
            headers={"Accept": "application/json"},
            parse=lambda r: parse_listing_json(r.json(), source="json"),
        )
        if entry["status"] == "blocked":
            self.json_blocked = True
        return posts, entry

    def search(self, query: str, subreddit=None, sort: str = "relevance",
               time_filter: str = "week", limit: int = MAX_LIMIT) -> dict:
        """Search Reddit posts, trying OAuth (if configured), then RSS, then JSON.

        Args:
            query: Reddit search query (see build_or_query for several keywords).
            subreddit: restrict to one subreddit ('SaaS' or 'r/SaaS'), or None.
            sort: relevance (default), new, top, comments or hot.
            time_filter: hour, day, week (default), month, year or all.
            limit: 1-100 posts (default 100, the maximum Reddit returns).

        Returns:
            dict with keys: query, subreddit, sort, time_filter, limit,
            status ('ok' | 'empty' | 'failed'), failure_reason (status of
            the last failed request when status is 'failed', else None),
            method ('oauth' | 'rss' | 'json' | None), http_status, posts,
            requests (log entries for this search), notes, errors.

        Raises:
            ValueError: on an empty query or an invalid sort, time filter,
                limit or subreddit name.
        """
        query = (query or "").strip()
        if not query:
            raise ValueError("query is empty")
        if sort not in SORTS:
            raise ValueError("sort must be one of %s" % ", ".join(SORTS))
        if time_filter not in TIME_FILTERS:
            raise ValueError("time_filter must be one of %s" % ", ".join(TIME_FILTERS))
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_LIMIT:
            raise ValueError("limit must be an integer from 1 to %d" % MAX_LIMIT)
        subreddit = normalize_subreddit(subreddit)

        result = {
            "query": query,
            "subreddit": subreddit,
            "sort": sort,
            "time_filter": time_filter,
            "limit": limit,
            "status": "failed",
            "failure_reason": None,
            "method": None,
            "http_status": None,
            "posts": [],
            "requests": [],
            "notes": [],
            "errors": [],
        }
        first_log_index = len(self.requests_log)
        failures = []  # (method, entry) for every method that did not work
        last_entry = None

        plan = []
        if self.oauth_enabled:
            plan.append("oauth")
        elif self.has_oauth_credentials:
            result["notes"].append(
                "OAuth skipped: the Reddit credentials were rejected earlier in this run."
            )
        plan.extend(["rss", "json"])

        for method in plan:
            if method == "json":
                if self.json_blocked:
                    continue
                if last_entry is not None and last_entry["status"] == "rate_limited":
                    # Same host and quota as RSS: trying it now only waits again.
                    continue
            runner = {"oauth": self._search_oauth, "rss": self._search_rss,
                      "json": self._search_json}[method]
            posts, entry = runner(query, sort, time_filter, limit, subreddit)
            last_entry = entry
            if posts is not None:
                result["status"] = "ok" if posts else "empty"
                result["method"] = method
                result["http_status"] = entry["http_status"]
                result["posts"] = posts
                break
            failures.append((method, entry))

        for method, entry in failures:
            message = _failure_message(method, entry)
            # A failure that a later method recovered from is degraded mode
            # (a note); only an unrecovered search is an error.
            (result["notes"] if result["method"] else result["errors"]).append(message)

        if result["method"] is None and last_entry is not None:
            result["failure_reason"] = last_entry["status"]
        if result["method"] == "rss":
            result["notes"].append(RSS_NOTE)
        result["requests"] = self.requests_log[first_log_index:]
        return result
