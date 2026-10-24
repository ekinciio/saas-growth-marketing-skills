"""Network side of the collector: polite fetching of site-level files.

Every request goes through Fetcher, which reuses one session, waits
POLITE_DELAY seconds between requests to the same host, and records what was
requested so the report can list its sources. Fetch results come from
_growthkit.http.fetch(), which never raises and sniffs HTML served in place
of text files (SPA catch-alls).
"""

from __future__ import annotations

import json
import time
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import quote, urlparse

from _growthkit import http

from . import POLITE_DELAY, discovery, llms, robots

FetchFn = Callable[..., Dict[str, Any]]


class Fetcher:
    """http.fetch with one session, per-host politeness and a request log."""

    def __init__(self, timeout: float = 15.0, delay: float = POLITE_DELAY, fetch_fn: Optional[FetchFn] = None,
                 sleep_fn: Optional[Callable[[float], None]] = None) -> None:
        self.timeout = timeout
        self.delay = delay
        self._fetch = fetch_fn or http.fetch
        self._sleep = sleep_fn or time.sleep
        self._last: Dict[str, float] = {}
        self.session = http.new_session() if fetch_fn is None else None
        self.log: List[Dict[str, Any]] = []

    def get(self, url: str, kind: str = "html", **kwargs: Any) -> Dict[str, Any]:
        host = (urlparse(url if "://" in url else "https://" + url).hostname or "").lower()
        last = self._last.get(host)
        if last is not None and self.delay:
            wait = self.delay - (time.monotonic() - last)
            if wait > 0:
                self._sleep(wait)
        kwargs.setdefault("timeout", self.timeout)
        if self.session is not None:
            kwargs.setdefault("session", self.session)
        result = self._fetch(url, kind=kind, **kwargs)
        self._last[host] = time.monotonic()
        self.log.append({"url": result.get("url") or url, "kind": kind, "status": result.get("status"),
                         "http_status": result.get("http_status")})
        return result

    def close(self) -> None:
        if self.session is not None:
            try:
                self.session.close()
            except Exception:  # noqa: BLE001
                pass


def _root(url: str) -> str:
    return http.site_root(url)


# ---------------------------------------------------------------------------
# robots.txt
# ---------------------------------------------------------------------------


def fetch_robots(fetcher: Fetcher, site_url: str, keep_text: int = 20000) -> Dict[str, Any]:
    """robots.txt for one host: status per RFC 9309, parse, sitemaps, signals."""
    url = http.site_url(site_url, "/robots.txt")
    result = fetcher.get(url, kind="text")
    status = robots.robots_status(result)
    parsed = robots.parse(result.get("text")) if status in ("ok", "too_large") else None
    final_host = (urlparse(result.get("final_url") or url).hostname or "").lower()
    requested_host = (urlparse(url).hostname or "").lower()
    out: Dict[str, Any] = {
        "url": url,
        "final_url": result.get("final_url"),
        "cross_host_redirect": bool(result.get("final_url")) and final_host != requested_host,
        "status": status,
        "http_status": result.get("http_status"),
        "meaning": robots.STATUS_MEANING.get(status),
        "error": result.get("error"),
        "bot_protection": (result.get("bot_protection") or {}).get("vendor"),
        "parsed": parsed,
        "text": (result.get("text") or "")[:keep_text] if parsed is not None else None,
    }
    if parsed is not None:
        out.update({
            "groups": len(parsed["groups"]),
            "sitemaps_declared": parsed["sitemaps"][:10],
            "content_signals": parsed["content_signals"][:6],
            "cloudflare_policy_text": parsed["cloudflare_policy_text"],
            "warnings": parsed["warnings"][:8],
            "agents": robots.agents_in_file(parsed),
            "bytes": parsed["bytes"],
        })
    return out


def public_robots(info: Dict[str, Any]) -> Dict[str, Any]:
    """robots info without the parse tree (for JSON output)."""
    return {k: v for k, v in info.items() if k not in ("parsed",)}


# ---------------------------------------------------------------------------
# Sitemaps
# ---------------------------------------------------------------------------


def discover_sitemaps(fetcher: Fetcher, site_url: str, declared: List[str], max_fetches: int = 5) -> Dict[str, Any]:
    """Read declared sitemaps (or /sitemap.xml); follow an index into up to 3 children."""
    queue = list(declared[:3]) or [http.site_url(site_url, "/sitemap.xml")]
    source = "robots.txt" if declared else "default location /sitemap.xml"
    fetched: List[Dict[str, Any]] = []
    entries: List[Dict[str, Any]] = []
    newest: Optional[str] = None
    total = 0
    index_children = 0
    seen = set()
    while queue and len(fetched) < max_fetches:
        url = queue.pop(0)
        if url in seen:
            continue
        seen.add(url)
        result = fetcher.get(url, kind="xml")
        record: Dict[str, Any] = {"url": url, "status": result.get("status"), "http_status": result.get("http_status"),
                                  "soft_404": bool(result.get("soft_404"))}
        if result.get("status") in ("ok", "too_large") and result.get("text"):
            parsed = discovery.parse_sitemap(result["text"])
            record.update({"kind": parsed["kind"], "count": parsed["count"], "with_lastmod": parsed["with_lastmod"],
                           "newest_lastmod": parsed["newest_lastmod"], "truncated": result.get("status") == "too_large"})
            if parsed["kind"] == "sitemapindex":
                index_children += parsed["count"]
                for child in discovery.pick_child_sitemaps(parsed["urls"]):
                    if child not in seen:
                        queue.append(child)
            else:
                total += parsed["count"]
                entries.extend(parsed["urls"][:5000])
            if parsed["newest_lastmod"] and (newest is None or parsed["newest_lastmod"] > newest):
                newest = parsed["newest_lastmod"]
        fetched.append(record)
    ok = [f for f in fetched if f.get("kind") in ("urlset", "sitemapindex", "text")]
    return {
        "source": source,
        "found": bool(ok),
        "fetched": fetched,
        "url_count_read": total,
        "index_children": index_children,
        "complete": not queue and index_children <= 3,
        "newest_lastmod": newest,
        "with_lastmod": sum(f.get("with_lastmod") or 0 for f in ok),
        "entries": entries,
    }


def public_sitemap(info: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in info.items() if k != "entries"}


# ---------------------------------------------------------------------------
# llms.txt, llms-full.txt, Markdown versions
# ---------------------------------------------------------------------------


def fetch_llms(fetcher: Fetcher, site_url: str) -> Dict[str, Any]:
    """/llms.txt status and validation (the text is kept for drafts and diffs)."""
    url = http.site_url(site_url, "/llms.txt")
    result = fetcher.get(url, kind="text")
    code = result.get("http_status")
    if result.get("status") in ("ok", "too_large") and (result.get("text") or "").strip():
        status = "found"
    elif result.get("soft_404"):
        status = "html_not_llms"
    elif result.get("status") == "blocked":
        status = "blocked"
    elif code is None:
        status = "unreachable"
    elif code >= 500:
        status = "server_error"
    elif code >= 400:
        status = "not_found"
    else:
        status = "empty"
    out: Dict[str, Any] = {"url": url, "status": status, "http_status": code,
                           "content_type": result.get("content_type"), "text": None, "validation": None}
    if status == "found":
        text = result.get("text") or ""
        out["text"] = text
        out["bytes"] = len(text.encode("utf-8"))
        out["validation"] = llms.validate(text, site_url)
    return out


def public_llms(info: Dict[str, Any]) -> Dict[str, Any]:
    out = {k: v for k, v in info.items() if k != "text"}
    if out.get("validation"):
        out["validation"] = {k: v for k, v in out["validation"].items() if k != "parsed"}
    return out


def fetch_llms_full(fetcher: Fetcher, site_url: str) -> Dict[str, Any]:
    url = http.site_url(site_url, "/llms-full.txt")
    result = fetcher.get(url, kind="text", max_bytes=65536)
    exists = result.get("status") in ("ok", "too_large") and bool((result.get("text") or "").strip())
    return {"url": url, "exists": exists, "http_status": result.get("http_status"),
            "larger_than_64kb": result.get("status") == "too_large",
            "soft_404": bool(result.get("soft_404"))}


def check_links(fetcher: Fetcher, urls: List[str], limit: int = 20) -> Dict[str, Any]:
    """GET the first `limit` unique URLs (4 KB read) and report dead ones."""
    checked: List[Dict[str, Any]] = []
    unique: List[str] = []
    for url in urls:
        if url.startswith(("http://", "https://")) and url not in unique:
            unique.append(url)
    for url in unique[:limit]:
        result = fetcher.get(url, kind="text", max_bytes=4096)
        code = result.get("http_status")
        state = "ok" if code is not None and code < 400 else ("blocked" if result.get("status") == "blocked" else "dead")
        checked.append({"url": url, "http_status": code, "state": state})
    return {
        "checked": len(checked),
        "of": len(unique),
        "dead": [c for c in checked if c["state"] == "dead"],
        "blocked": len([c for c in checked if c["state"] == "blocked"]),
    }


def _looks_markdown(text: str) -> bool:
    head = (text or "").lstrip()[:2000]
    return bool(head) and not http.looks_like_html(head) and (
        head.startswith("#") or "](" in head or "\n## " in head or "\n- " in head)


def markdown_checks(fetcher: Fetcher, page_url: str) -> Dict[str, Any]:
    """Is a Markdown version of this page available (.md mirror or Accept negotiation)?"""
    parsed = urlparse(page_url)
    path = parsed.path or "/"
    candidate = path + "index.md" if path.endswith("/") else path + ".md"
    mirror_url = "%s://%s%s" % (parsed.scheme, parsed.netloc, candidate)
    mirror = fetcher.get(mirror_url, kind="text", max_bytes=65536)
    mirror_ok = mirror.get("status") in ("ok", "too_large") and _looks_markdown(mirror.get("text") or "")
    negotiated = fetcher.get(page_url, kind="text", max_bytes=65536, headers={"Accept": "text/markdown, text/html;q=0.5"})
    ctype = negotiated.get("content_type") or ""
    negotiation_ok = ctype.startswith("text/markdown") and not negotiated.get("soft_404")
    headers = negotiated.get("headers") or {}
    return {
        "page": page_url,
        "mirror_url": mirror_url,
        "mirror": mirror_ok,
        "mirror_http_status": mirror.get("http_status"),
        "negotiation": negotiation_ok,
        "negotiated_content_type": ctype or None,
        "markdown_tokens_header": headers.get("x-markdown-tokens"),
        "content_signal_header": headers.get("content-signal"),
    }


# ---------------------------------------------------------------------------
# Wikidata entity check (free API, honest tool user agent)
# ---------------------------------------------------------------------------

WIKIDATA_API = "https://www.wikidata.org/w/api.php"


def _json(result: Dict[str, Any]) -> Optional[Any]:
    if result.get("status") not in ("ok", "too_large"):
        return None
    try:
        return json.loads(result.get("text") or "")
    except ValueError:
        return None


def wikidata(fetcher: Fetcher, name: Optional[str], site_domain: str) -> Dict[str, Any]:
    """Wikidata items for the brand; match = the item whose official website (P856) is this domain."""
    out: Dict[str, Any] = {"status": "skipped", "query": name, "candidates": [], "match": None,
                           "source": WIKIDATA_API}
    if not name:
        out["status"] = "no_name"
        return out
    search_url = "%s?action=wbsearchentities&search=%s&language=en&uselang=en&type=item&limit=7&format=json" % (
        WIKIDATA_API, quote(name))
    data = _json(fetcher.get(search_url, kind="text", headers={"Accept": "application/json"}))
    if data is None:
        out["status"] = "lookup_failed"
        return out
    hits = [h for h in data.get("search") or [] if h.get("id")]
    if not hits:
        out["status"] = "no_candidates"
        return out
    ids = "|".join(h["id"] for h in hits)
    entity_url = "%s?action=wbgetentities&ids=%s&props=claims%%7Csitelinks&sitefilter=enwiki&format=json" % (
        WIKIDATA_API, quote(ids, safe="|"))
    entities = (_json(fetcher.get(entity_url, kind="text", headers={"Accept": "application/json"})) or {}).get("entities") or {}
    for hit in hits:
        entity = entities.get(hit["id"]) or {}
        websites = []
        for claim in (entity.get("claims") or {}).get("P856") or []:
            value = (((claim.get("mainsnak") or {}).get("datavalue") or {}).get("value"))
            if isinstance(value, str):
                websites.append(value)
        matches = any(discovery.registrable_domain(urlparse(w).hostname or "") == site_domain for w in websites)
        enwiki = ((entity.get("sitelinks") or {}).get("enwiki") or {}).get("title")
        out["candidates"].append({"id": hit["id"], "label": hit.get("label"),
                                  "description": (hit.get("description") or "")[:90] or None,
                                  "official_website": websites[:2], "matches_domain": matches,
                                  "enwiki": enwiki})
        if matches and out["match"] is None:
            out["match"] = hit["id"]
    # Matching item first, then the first two search hits.
    out["candidates"].sort(key=lambda c: not c["matches_domain"])
    out["candidates"] = out["candidates"][:3]
    out["status"] = "matched" if out["match"] else "no_domain_match"
    return out


__all__ = [
    "Fetcher", "fetch_robots", "public_robots", "discover_sitemaps", "public_sitemap", "fetch_llms",
    "public_llms", "fetch_llms_full", "check_links", "markdown_checks", "wikidata",
]
