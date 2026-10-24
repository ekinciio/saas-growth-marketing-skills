"""Facts about one page that decide whether AI search can use it.

    facts = page_record(fetch_result, page_type="pricing")

Builds on _growthkit.html.page_facts() and adds what the GEO audit needs:
- ai_controls: X-Robots-Tag and meta robots parsed per engine (noindex,
  nosnippet, max-snippet, noarchive, nocache, non-standard noai), the
  data-nosnippet count and a Content-Signal response header
- rendering: visible words, JS-shell signals, empty SPA root
- schema: JSON-LD types plus the key fields entity understanding needs
- microdata / RDFa types, lang, hreflang, canonical, viewport, dates

It reports; it does not judge.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from _growthkit import html as gk_html

from . import robots as robots_mod

KNOWN_DIRECTIVES = {
    "all", "none", "index", "noindex", "follow", "nofollow", "nosnippet", "noarchive", "nocache",
    "noimageindex", "notranslate", "indexifembedded", "noodp", "noydir",
}
NONSTANDARD = {"noai", "noimageai"}
GOOGLE_NAMES = ("robots", "googlebot")
BING_NAMES = ("robots", "bingbot", "msnbot")


def parse_directives(content: Optional[str]) -> Dict[str, Any]:
    """'noindex, max-snippet:0' -> {directives: [...], max_snippet: 0, ...}."""
    out: Dict[str, Any] = {"directives": [], "max_snippet": None, "max_image_preview": None,
                           "max_video_preview": None, "unavailable_after": None, "nonstandard": [],
                           "unknown": []}
    for part in re.split(r",", content or ""):
        token = part.strip().lower()
        if not token:
            continue
        if ":" in token:
            key, _, value = token.partition(":")
            key = key.strip()
            value = value.strip()
            if key == "max-snippet":
                try:
                    out["max_snippet"] = int(value)
                except ValueError:
                    out["unknown"].append(token)
                continue
            if key == "max-image-preview":
                out["max_image_preview"] = value
                continue
            if key == "max-video-preview":
                out["max_video_preview"] = value
                continue
            if key == "unavailable_after":
                out["unavailable_after"] = value
                continue
            out["unknown"].append(token)
            continue
        if token in KNOWN_DIRECTIVES:
            out["directives"].append(token)
        elif token in NONSTANDARD:
            out["nonstandard"].append(token)
        else:
            out["unknown"].append(token)
    return out


def parse_x_robots(header: Optional[str]) -> Dict[str, Any]:
    """X-Robots-Tag: 'googlebot: noindex, nofollow' or 'noindex' (several headers joined)."""
    result: Dict[str, Any] = {"raw": header, "all": [], "per_bot": {}}
    if not header:
        return result
    for chunk in re.split(r"\s*,\s*(?=[A-Za-z0-9_-]+\s*:(?!\s*\d))", header):
        chunk = chunk.strip()
        match = re.match(r"^([A-Za-z0-9_-]+)\s*:\s*(.+)$", chunk)
        if match and match.group(1).lower() not in ("max-snippet", "max-image-preview", "max-video-preview",
                                                    "unavailable_after"):
            bot = match.group(1).lower()
            result["per_bot"].setdefault(bot, []).append(match.group(2))
        else:
            result["all"].append(chunk)
    return result


def _flags(parsed_list: List[Dict[str, Any]]) -> Dict[str, Any]:
    directives = set()
    nonstandard = set()
    max_snippet = None
    for parsed in parsed_list:
        directives.update(parsed["directives"])
        nonstandard.update(parsed["nonstandard"])
        if parsed["max_snippet"] is not None:
            max_snippet = parsed["max_snippet"] if max_snippet is None else min(max_snippet, parsed["max_snippet"])
    flags = {
        "noindex": "noindex" in directives or "none" in directives,
        "nosnippet": "nosnippet" in directives,
        "max_snippet": max_snippet,
        "snippet_blocked": "nosnippet" in directives or max_snippet == 0,
        "noarchive": "noarchive" in directives,
        "nocache": "nocache" in directives,
        "nofollow": "nofollow" in directives or "none" in directives,
        "nonstandard": sorted(nonstandard),
    }
    # Only what is set: an empty dict means "no restriction found".
    return {k: v for k, v in flags.items() if v not in (False, None, [])}


def ai_controls(meta_robots: Dict[str, str], headers: Dict[str, str], markup: Optional[str]) -> Dict[str, Any]:
    """Index and snippet controls as Google and Bing read them for this page."""
    x_robots = parse_x_robots((headers or {}).get("x-robots-tag"))
    meta_parsed = {name: parse_directives(value) for name, value in (meta_robots or {}).items()}
    x_all = parse_directives(", ".join(x_robots["all"]))
    x_bot = {bot: parse_directives(", ".join(values)) for bot, values in x_robots["per_bot"].items()}

    def collect(names) -> List[Dict[str, Any]]:
        items = [x_all]
        for name in names:
            if name in meta_parsed:
                items.append(meta_parsed[name])
            if name in x_bot:
                items.append(x_bot[name])
        return items

    data_nosnippet = len(re.findall(r"\bdata-nosnippet\b", markup or "", re.I))
    signal_header = (headers or {}).get("content-signal")
    other_bots = sorted(set(list(meta_parsed) + list(x_bot)) - set(GOOGLE_NAMES) - set(BING_NAMES))
    out = {
        "x_robots_tag": x_robots["raw"],
        "meta_robots": {name: (meta_robots or {}).get(name) for name in meta_parsed},
        "google": _flags(collect(GOOGLE_NAMES)),
        "bing": _flags(collect(BING_NAMES)),
        "other_bot_rules": {bot: (meta_robots or {}).get(bot) or ", ".join(x_robots["per_bot"].get(bot, []))
                            for bot in other_bots},
        "data_nosnippet_count": data_nosnippet,
        "content_signal_header": robots_mod.parse_content_signal(signal_header) if signal_header else None,
        "unknown_directives": sorted({u for p in [x_all] + list(meta_parsed.values()) for u in p["unknown"]}),
    }
    keep = ("google", "bing", "data_nosnippet_count")
    return {k: v for k, v in out.items() if k in keep or v}


# ---------------------------------------------------------------------------
# Schema and other markup
# ---------------------------------------------------------------------------

_ORG_TYPES = {"organization", "corporation", "localbusiness", "onlinebusiness", "ngo", "educationalorganization"}
_SOFTWARE_TYPES = {"softwareapplication", "webapplication", "mobileapplication", "product", "service"}
_ARTICLE_TYPES = {"article", "blogposting", "newsarticle", "techarticle", "report", "webpage", "aboutpage",
                  "faqpage", "qapage", "collectionpage"}


def _types(item: Dict[str, Any]) -> List[str]:
    value = item.get("@type")
    if isinstance(value, list):
        return [str(v) for v in value]
    return [str(value)] if value else []


def _text(value: Any, limit: int = 160) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, dict):
        value = value.get("name") or value.get("@id") or value.get("url")
    if isinstance(value, list):
        value = ", ".join(str(_text(v, limit)) for v in value[:3] if v is not None)
    text = " ".join(str(value).split())
    return text[:limit] if text else None


def _list(value: Any) -> List[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _offers(value: Any) -> List[Dict[str, Any]]:
    offers = []
    for offer in _list(value)[:8]:
        if not isinstance(offer, dict):
            continue
        offers.append({
            "type": _text(offer.get("@type")),
            "name": _text(offer.get("name"), 60),
            "price": _text(offer.get("price") if offer.get("price") is not None else offer.get("lowPrice"), 20),
            "priceCurrency": _text(offer.get("priceCurrency"), 8),
        })
    return offers


def schema_summary(json_ld: Dict[str, Any]) -> Dict[str, Any]:
    """JSON-LD types plus the fields AI systems use to resolve the entity."""
    items = json_ld.get("items") or []
    summary: Dict[str, Any] = {
        "blocks": json_ld.get("blocks", 0),
        "errors": len(json_ld.get("errors") or []),
        "types": json_ld.get("types") or [],
        "organization": None,
        "website": None,
        "software": [],
        "articles": [],
        "faq_pages": 0,
        "howto": 0,
        "breadcrumbs": False,
        "descriptions": [],
    }
    for item in items:
        types = [t.lower() for t in _types(item)]
        if item.get("description"):
            summary["descriptions"].append({"type": _types(item)[0] if _types(item) else None,
                                            "text": _text(item.get("description"), 400)})
        if any(t in _ORG_TYPES for t in types) and summary["organization"] is None:
            same_as = [str(u) for u in _list(item.get("sameAs")) if isinstance(u, str)]
            summary["organization"] = {
                "type": _types(item)[0],
                "name": _text(item.get("name"), 80),
                "url": _text(item.get("url"), 200),
                "logo": bool(item.get("logo")),
                "same_as": same_as[:20],
                "founding_date": _text(item.get("foundingDate"), 20),
            }
        elif "website" in types and summary["website"] is None:
            actions = [a for a in _list(item.get("potentialAction")) if isinstance(a, dict)]
            summary["website"] = {
                "name": _text(item.get("name"), 80),
                "url": _text(item.get("url"), 200),
                "search_action": any("searchaction" in str(a.get("@type", "")).lower() for a in actions),
            }
        if any(t in _SOFTWARE_TYPES for t in types):
            rating = item.get("aggregateRating") if isinstance(item.get("aggregateRating"), dict) else None
            summary["software"].append({
                "type": _types(item)[0],
                "name": _text(item.get("name"), 80),
                "category": _text(item.get("applicationCategory"), 60),
                "operating_system": _text(item.get("operatingSystem"), 60),
                "offers": _offers(item.get("offers")),
                "rating": {
                    "value": _text(rating.get("ratingValue"), 10),
                    "count": _text(rating.get("ratingCount") or rating.get("reviewCount"), 12),
                } if rating else None,
            })
        if any(t in _ARTICLE_TYPES for t in types) and any(k in item for k in ("datePublished", "dateModified", "author", "headline")):
            summary["articles"].append({
                "type": _types(item)[0],
                "headline": _text(item.get("headline") or item.get("name"), 120),
                "date_published": _text(item.get("datePublished"), 30),
                "date_modified": _text(item.get("dateModified"), 30),
                "author": _text(item.get("author"), 80),
            })
        if "faqpage" in types:
            summary["faq_pages"] += 1
        if "howto" in types:
            summary["howto"] += 1
        if "breadcrumblist" in types:
            summary["breadcrumbs"] = True
    summary["software"] = summary["software"][:4]
    summary["articles"] = summary["articles"][:4]
    summary["descriptions"] = summary["descriptions"][:5]
    return summary


def microdata(markup: Optional[str]) -> Dict[str, Any]:
    """itemtype (microdata) and typeof (RDFa) values, by regex."""
    text = markup or ""
    item_types = []
    for match in re.finditer(r"\bitemtype\s*=\s*[\"']([^\"']+)[\"']", text, re.I):
        name = match.group(1).rstrip("/").rsplit("/", 1)[-1]
        if name and name not in item_types:
            item_types.append(name)
    rdfa = []
    for match in re.finditer(r"\btypeof\s*=\s*[\"']([^\"']+)[\"']", text, re.I):
        for name in match.group(1).split():
            name = name.rsplit(":", 1)[-1]
            if name and name not in rdfa:
                rdfa.append(name)
    return {"microdata_types": item_types[:15], "rdfa_types": rdfa[:15]}


def dates(markup: Optional[str], headers: Dict[str, str], schema: Dict[str, Any]) -> Dict[str, Any]:
    """Every machine-readable date signal on the page."""
    text = markup or ""

    def meta(prop: str) -> Optional[str]:
        match = re.search(r"<meta[^>]+(?:property|name)\s*=\s*[\"']%s[\"'][^>]*>" % re.escape(prop), text, re.I)
        if not match:
            return None
        content = re.search(r"content\s*=\s*[\"']([^\"']*)[\"']", match.group(0), re.I)
        return content.group(1).strip()[:30] if content else None

    times = []
    for match in re.finditer(r"<time\b[^>]*\bdatetime\s*=\s*[\"']([^\"']+)[\"']", text, re.I):
        if match.group(1) not in times:
            times.append(match.group(1)[:30])
    article = (schema.get("articles") or [{}])[0] if schema.get("articles") else {}
    return {
        "json_ld_published": article.get("date_published"),
        "json_ld_modified": article.get("date_modified"),
        "meta_published": meta("article:published_time"),
        "meta_modified": meta("article:modified_time") or meta("og:updated_time"),
        "time_elements": times[:3],
        "last_modified_header": (headers or {}).get("last-modified"),
        "any": bool(article.get("date_published") or article.get("date_modified") or meta("article:published_time")
                    or meta("article:modified_time") or meta("og:updated_time") or times),
    }


def _same_page(a: Optional[str], b: Optional[str]) -> Optional[bool]:
    if not a or not b:
        return None
    pa, pb = urlparse(a), urlparse(b)
    host_a = (pa.hostname or "").lower()
    host_b = (pb.hostname or "").lower()
    return host_a == host_b and (pa.path or "/").rstrip("/") == (pb.path or "/").rstrip("/")


def author_signals(markup: Optional[str], schema: Dict[str, Any]) -> Dict[str, Any]:
    text = markup or ""
    meta_author = re.search(r"<meta[^>]+name\s*=\s*[\"']author[\"'][^>]*content\s*=\s*[\"']([^\"']+)[\"']", text, re.I)
    rel_author = bool(re.search(r"<(?:a|link)\b[^>]*\brel\s*=\s*[\"'][^\"']*\bauthor\b", text, re.I))
    schema_author = next((a.get("author") for a in schema.get("articles") or [] if a.get("author")), None)
    return {
        "meta_author": meta_author.group(1).strip()[:80] if meta_author else None,
        "rel_author": rel_author,
        "schema_author": schema_author,
        "any": bool(meta_author or rel_author or schema_author),
    }


def page_record(
    result: Dict[str, Any],
    page_type: str,
    markup: Optional[str] = None,
    url: Optional[str] = None,
) -> Dict[str, Any]:
    """One sampled page: fetch outcome plus the facts above.

    `result` is an http.fetch() result; pass markup (and url) instead for a
    saved HTML file, with result={} or a synthetic dict.
    """
    markup = markup if markup is not None else result.get("html")
    page_url = url or result.get("final_url") or result.get("url")
    record: Dict[str, Any] = {
        "type": page_type,
        "url": result.get("url") or page_url,
        "final_url": result.get("final_url") or page_url,
        "http_status": result.get("http_status"),
        "status": result.get("status", "ok" if markup else None),
        "error": result.get("error"),
        "bot_protection": result.get("bot_protection"),
        "redirect_chain": result.get("redirect_chain") or [],
        "elapsed_ms": result.get("elapsed_ms"),
    }
    if not markup:
        return record
    facts = gk_html.page_facts(markup, page_url, text_chars=0)
    headers = result.get("headers") or {}
    meta = facts["meta"]
    schema = schema_summary(facts["json_ld"])
    shell = facts.get("js_shell_signals") or {}
    record.update({
        "title": facts["title"],
        "meta_description": meta.get("description"),
        "og": {k: v for k, v in (meta.get("og") or {}).items() if k in ("site_name", "title", "description") and v},
        "lang": facts["lang"],
        "hreflang_count": meta.get("hreflang_count", 0),
        "canonical": meta.get("canonical"),
        "canonical_is_self": _same_page(meta.get("canonical"), record["final_url"]) if meta.get("canonical") else None,
        "viewport": bool(meta.get("viewport")),
        "rendering": {
            "visible_words": facts["word_count"],
            "main_words": facts["main_word_count"],
            "is_js_shell": bool(facts["is_js_shell"]),
            "empty_root": shell.get("empty_root"),
            "script_count": shell.get("script_count"),
        },
        "ai_controls": ai_controls(meta.get("robots") or {}, headers, markup),
        "headings": {
            "h1": [h[:120] for h in (facts["headings"].get("h1") or [])[:3]],
            "h2": [h[:80] for h in (facts["headings"].get("h2") or [])[:8]],
            "h1_count": len(facts["headings"].get("h1") or []),
            "h2_count": len(facts["headings"].get("h2") or []),
        },
        "schema": schema,
        "markup": microdata(markup),
        "dates": dates(markup, headers, schema),
        "author": author_signals(markup, schema),
        "social_links": [s["platform"] for s in facts.get("social_links") or []][:12],
    })
    return record


__all__ = [
    "parse_directives", "parse_x_robots", "ai_controls", "schema_summary", "microdata", "dates",
    "author_signals", "page_record",
]
