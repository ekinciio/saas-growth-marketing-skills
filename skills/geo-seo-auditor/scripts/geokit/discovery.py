"""Which URLs to look at: page types, sitemaps and a deterministic sample.

AI answers about a SaaS product cite its pricing, docs, comparison and blog
pages far more often than a homepage hero, so the audit samples one page of
each type it can find. Classification is by URL path only (no judgment):

    classify_url("https://linear.app/docs/projects")  -> "docs"
    classify_url("https://x.app/blog/launch-week")     -> "blog"
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urljoin, urlparse, urlunparse

_LOCALE_RE = re.compile(r"^/([a-z]{2})(?:[-_][a-zA-Z]{2,4})?(?=/|$)", re.I)
# Language codes seen as locale prefixes on SaaS sites. Two-letter paths that
# are not languages here ("/ai/", "/lp/", "/go/", "/vs/") stay part of the path.
_LANGS = {
    "en", "de", "fr", "es", "it", "pt", "nl", "sv", "da", "nb", "fi", "pl", "cs", "tr", "ru",
    "ja", "ko", "zh", "ar", "he", "iw", "hu", "ro", "el", "bg", "sk", "sl", "ms", "hi", "th", "vi",
    "uk", "id", "et", "lv", "lt", "ca",
}

# Order matters: the first matching type wins.
_TYPE_RULES: List[Tuple[str, "re.Pattern[str]"]] = [
    ("pricing", re.compile(r"^/(?:pricing|plans|prices|price|plans-and-pricing)(?:/|$|\.)", re.I)),
    ("comparison", re.compile(
        r"(?:^|/)(?:compare|comparison|comparisons|vs|versus|alternatives?)(?:/|$)"
        r"|[a-z0-9]-vs-[a-z0-9]|[a-z0-9]_vs_[a-z0-9]|-versus-|-alternatives?(?:/|$)", re.I)),
    ("changelog", re.compile(r"^/(?:changelog|change-log|release-notes|releases|whats-new|what-s-new|updates)(?:/|$)", re.I)),
    ("docs", re.compile(
        r"^/(?:docs|documentation|help|help-center|helpcenter|guides?|kb|knowledge-base|knowledgebase|"
        r"support/articles|support/solutions|developers?|api|api-reference|reference|manual|learn|academy|"
        r"tutorials?|handbook|faq)(?:/|$)", re.I)),
    ("blog", re.compile(r"^/(?:blog|posts?|articles?|news|insights|stories|resources/blog|magazine)/[^/]+", re.I)),
    ("blog_index", re.compile(r"^/(?:blog|posts|articles|news|insights)/?$", re.I)),
    ("customers", re.compile(r"^/(?:customers|case-studies|case-study|customer-stories|success-stories)(?:/|$)", re.I)),
    ("integrations", re.compile(r"^/(?:integrations?|apps|marketplace|connectors)(?:/|$)", re.I)),
    ("security", re.compile(r"^/(?:security|trust|trust-center|compliance)(?:/|$)", re.I)),
    ("about", re.compile(r"^/(?:about|about-us|company)(?:/|$)", re.I)),
    ("features", re.compile(r"^/(?:features?|product|products|platform|solutions?|use-cases?)(?:/|$)", re.I)),
]
_DOCS_HOST_RE = re.compile(r"^(?:docs|help|support|developers?|developer|learn|kb|academy|api)\.", re.I)
_BLOG_HOST_RE = re.compile(r"^(?:blog|news)\.", re.I)

# Never sampled: accounts, legal, jobs, assets, search and tracking URLs.
_EXCLUDE_RE = re.compile(
    r"(?:^|/)(?:login|log-in|signin|sign-in|signup|sign-up|register|join|logout|account|accounts|"
    r"dashboard|app|cart|checkout|auth|oauth|sso|invite|invites|password|reset|"
    r"privacy|privacy-policy|terms|tos|legal|cookies?|cookie-policy|gdpr|dpa|imprint|impressum|"
    r"careers|jobs|job|status|press|media-kit|brand|cdn-cgi|wp-admin|wp-json|feed|rss|tag|tags|category|"
    r"categories|author|authors|search|unsubscribe|_next|static|assets)(?:/|$|\?)",
    re.I,
)
_ASSET_RE = re.compile(r"\.(?:png|jpe?g|gif|webp|svg|ico|pdf|zip|gz|mp4|mov|webm|mp3|css|js|json|xml|txt|woff2?)$", re.I)
_APP_HOST_RE = re.compile(r"^(?:app|dashboard|console|my|portal|studio|login|auth|accounts?|status)\.", re.I)

# Sampling plan: page types in order of value for AI answers about a SaaS product.
DEFAULT_PLAN = ["pricing", "docs", "docs", "comparison", "blog", "changelog", "customers",
                "integrations", "security", "features", "about"]


def registrable_domain(host: str) -> str:
    """'docs.linear.app' -> 'linear.app' (approximate; two-level suffixes handled)."""
    host = (host or "").lower().strip(".")
    if host.startswith("www."):
        host = host[4:]
    labels = host.split(".")
    two_level = {"co.uk", "org.uk", "ac.uk", "com.au", "net.au", "com.br", "co.jp", "co.in",
                 "co.nz", "com.tr", "com.mx", "co.za", "com.sg", "co.kr", "com.ar", "com.hk",
                 "com.tw", "co.il", "com.my", "co.id"}
    if len(labels) >= 3 and ".".join(labels[-2:]) in two_level:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:]) if len(labels) >= 2 else host


def strip_locale(path: str) -> str:
    """'/de-de/pricing' -> '/pricing'; '/docs/x' unchanged."""
    match = _LOCALE_RE.match(path or "/")
    if match and match.group(1).lower() in _LANGS:
        return path[match.end():] or "/"
    return path or "/"


def has_locale_prefix(path: str) -> bool:
    return strip_locale(path) != (path or "/")


def classify_url(url: str) -> Optional[str]:
    """Page type from the URL alone, or None. The homepage is 'home'."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return None
    host = (parsed.hostname or "").lower()
    path = strip_locale(parsed.path or "/")
    if path in ("", "/") and not _DOCS_HOST_RE.match(host) and not _BLOG_HOST_RE.match(host):
        return "home"
    for kind, pattern in _TYPE_RULES:
        if pattern.search(path):
            return kind
    if _DOCS_HOST_RE.match(host):
        return "docs"
    if _BLOG_HOST_RE.match(host):
        return "blog" if path.strip("/") else "blog_index"
    return None


def is_candidate(url: str, site_domain: str) -> bool:
    """A public content URL on the same registrable domain that may be sampled."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    host = (parsed.hostname or "").lower()
    if not host or registrable_domain(host) != site_domain:
        return False
    if _APP_HOST_RE.match(host):
        return False
    path = parsed.path or "/"
    if parsed.query or _EXCLUDE_RE.search(path) or _ASSET_RE.search(path):
        return False
    return True


def canonical_url(url: str) -> str:
    """Drop fragments; keep scheme, host, path and query."""
    parsed = urlparse(url)
    return urlunparse((parsed.scheme.lower(), (parsed.netloc or "").lower(), parsed.path or "/",
                       "", parsed.query, ""))


def links_from_html(html_text: Optional[str], base_url: str) -> List[Dict[str, str]]:
    """[{url, text}] for every <a href> in document order (regex, no parsing cost)."""
    out: List[Dict[str, str]] = []
    if not html_text:
        return out
    for match in re.finditer(r"<a\b[^>]*?\bhref\s*=\s*([\"'])(.*?)\1[^>]*>(.*?)</a\s*>", html_text, re.I | re.S):
        href = match.group(2).strip()
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:", "data:")):
            continue
        try:
            absolute = urljoin(base_url, href)
        except ValueError:
            continue
        text = re.sub(r"<[^>]+>", " ", match.group(3))
        text = " ".join(text.split())[:120]
        out.append({"url": canonical_url(absolute), "text": text})
    return out


# ---------------------------------------------------------------------------
# Sitemaps
# ---------------------------------------------------------------------------

_LOC_RE = re.compile(r"<(?:\w+:)?loc>\s*(?:<!\[CDATA\[)?\s*(.*?)\s*(?:\]\]>)?\s*</(?:\w+:)?loc>", re.I | re.S)
_ENTRY_RE = re.compile(r"<(?:\w+:)?(url|sitemap)\b[^>]*>(.*?)</(?:\w+:)?\1>", re.I | re.S)
_LASTMOD_RE = re.compile(r"<(?:\w+:)?lastmod>\s*(.*?)\s*</(?:\w+:)?lastmod>", re.I | re.S)


def parse_sitemap(text: Optional[str]) -> Dict[str, Any]:
    """{kind, urls: [{loc, lastmod}], count, with_lastmod, newest_lastmod}."""
    text = text or ""
    head = text[:4096].lower()
    kind = "sitemapindex" if "<sitemapindex" in head else ("urlset" if "<urlset" in head else "unknown")
    entries: List[Dict[str, Optional[str]]] = []
    for match in _ENTRY_RE.finditer(text):
        body = match.group(2)
        loc = _LOC_RE.search(body)
        if not loc:
            continue
        lastmod = _LASTMOD_RE.search(body)
        entries.append({"loc": loc.group(1).strip().replace("&amp;", "&"),
                        "lastmod": lastmod.group(1).strip() if lastmod else None})
    if not entries and kind == "unknown":
        # Plain-text sitemap: one URL per line.
        for line in text.splitlines():
            line = line.strip()
            if line.startswith(("http://", "https://")):
                entries.append({"loc": line, "lastmod": None})
        if entries:
            kind = "text"
    dated = [e["lastmod"] for e in entries if e["lastmod"]]
    return {
        "kind": kind,
        "urls": entries,
        "count": len(entries),
        "with_lastmod": len(dated),
        "newest_lastmod": max((d[:10] for d in dated), default=None),
    }


def pick_child_sitemaps(children: List[Dict[str, Any]], limit: int = 3) -> List[str]:
    """Child sitemaps worth reading first (pages, blog, docs), then the rest in order."""
    preferred = re.compile(r"page|main|core|marketing|blog|post|docs|help|product|guide|compare|root", re.I)
    locs = [c["loc"] for c in children]
    first = [u for u in locs if preferred.search(u.rsplit("/", 1)[-1])]
    rest = [u for u in locs if u not in first]
    return (first + rest)[:limit]


# ---------------------------------------------------------------------------
# Sampling
# ---------------------------------------------------------------------------


def _depth(url: str) -> int:
    return len([p for p in strip_locale(urlparse(url).path).split("/") if p])


def _sort_key(entry: Dict[str, Any]) -> Tuple[int, int, int, int]:
    url = entry["url"]
    parsed = urlparse(url)
    return (
        1 if has_locale_prefix(parsed.path) else 0,   # prefer the default language
        0 if entry.get("from_nav") else 1,            # linked from the homepage
        _depth(url),
        entry.get("order", 0),
    )


def build_candidates(
    nav_links: Iterable[Dict[str, str]],
    sitemap_entries: Iterable[Dict[str, Any]],
    llms_links: Iterable[str],
    site_domain: str,
) -> Dict[str, List[Dict[str, Any]]]:
    """Candidate URLs grouped by page type, deduplicated, in preference order."""
    seen: Dict[str, Dict[str, Any]] = {}
    order = 0
    for link in nav_links:
        url = link["url"]
        if is_candidate(url, site_domain) and url not in seen:
            order += 1
            seen[url] = {"url": url, "from_nav": True, "lastmod": None, "order": order, "source": "homepage link"}
    for entry in sitemap_entries:
        url = canonical_url(entry["loc"])
        if not is_candidate(url, site_domain):
            continue
        order += 1
        if url in seen:
            seen[url]["lastmod"] = entry.get("lastmod")
            continue
        seen[url] = {"url": url, "from_nav": False, "lastmod": entry.get("lastmod"), "order": order,
                     "source": "sitemap"}
    for url in llms_links:
        url = canonical_url(url)
        if is_candidate(url, site_domain) and url not in seen:
            order += 1
            seen[url] = {"url": url, "from_nav": False, "lastmod": None, "order": order, "source": "llms.txt"}
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for entry in seen.values():
        kind = classify_url(entry["url"])
        if kind and kind != "home":
            grouped.setdefault(kind, []).append(entry)
    for kind, entries in grouped.items():
        if kind == "blog":
            # Newest post first when the sitemap has dates.
            entries.sort(key=lambda e: (e.get("lastmod") or "", -e["order"]), reverse=True)
            dated = [e for e in entries if e.get("lastmod")]
            undated = [e for e in entries if not e.get("lastmod")]
            undated.sort(key=_sort_key)
            grouped[kind] = dated + undated
        elif kind == "docs":
            # Real articles (depth >= 2) before section indexes.
            entries.sort(key=lambda e: (0 if _depth(e["url"]) >= 2 else 1,) + _sort_key(e))
        else:
            entries.sort(key=_sort_key)
    return grouped


def sample_pages(
    home_url: str,
    grouped: Dict[str, List[Dict[str, Any]]],
    max_pages: int,
    overrides: Optional[Dict[str, str]] = None,
    plan: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Pick up to max_pages URLs: home first, then the plan's page types."""
    picks: List[Dict[str, Any]] = [{"type": "home", "url": home_url, "source": "input"}]
    used = {canonical_url(home_url)}
    for kind, url in (overrides or {}).items():
        if len(picks) >= max_pages:
            break
        url = canonical_url(url)
        if url not in used:
            picks.append({"type": kind, "url": url, "source": "user"})
            used.add(url)
    docs_sections: List[str] = []
    for kind in plan or DEFAULT_PLAN:
        if len(picks) >= max_pages:
            break
        if overrides and kind in overrides:
            continue
        for entry in grouped.get(kind, []):
            if entry["url"] in used:
                continue
            if kind == "docs":
                parts = [p for p in strip_locale(urlparse(entry["url"]).path).split("/") if p]
                section = "/".join(parts[:2])
                if section in docs_sections and len(grouped.get("docs", [])) > 2:
                    continue
                docs_sections.append(section)
            picks.append({"type": kind, "url": entry["url"], "source": entry["source"],
                          "lastmod": entry.get("lastmod")})
            used.add(entry["url"])
            break
    return picks[:max_pages]


def robots_samples(home_url: str, grouped: Dict[str, List[Dict[str, Any]]], picks: List[Dict[str, Any]],
                   limit: int = 10) -> List[str]:
    """URLs to test robots rules against: sampled pages plus one per other type."""
    urls: List[str] = []
    for item in picks:
        if item["url"] not in urls:
            urls.append(item["url"])
    for kind in ("pricing", "docs", "comparison", "blog", "changelog", "customers", "integrations",
                 "features", "security", "about"):
        if len(urls) >= limit:
            break
        for entry in grouped.get(kind, [])[:1]:
            if entry["url"] not in urls:
                urls.append(entry["url"])
    if canonical_url(home_url) not in [canonical_url(u) for u in urls]:
        urls.insert(0, home_url)
    return urls[:limit]


__all__ = [
    "DEFAULT_PLAN", "registrable_domain", "strip_locale", "has_locale_prefix", "classify_url",
    "is_candidate", "canonical_url", "links_from_html", "parse_sitemap", "pick_child_sitemaps",
    "build_candidates", "sample_pages", "robots_samples",
]
