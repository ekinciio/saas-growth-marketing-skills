"""llms.txt (llmstxt.org): parse, validate, draft, and suggest additions.

The format is Markdown: a required H1 with the site name, an optional
blockquote summary, optional free text, then H2 sections holding link lists
('- [name](url): notes'). An H2 named 'Optional' marks skippable links.

Guardrails (backlog B74):
- A draft is produced only when the site has no valid llms.txt. When a valid
  file exists, only suggested additions are returned, so a richer existing
  file is never replaced by a thinner generated one.
- Drafts use only URLs that were actually seen on the site (homepage links,
  sitemap, sampled pages). Nothing is guessed: no /about, /contact or /blog
  unless the site links to them. With no usable links the draft carries TODO
  text lines, never placeholder links.
- The name comes from og:site_name, then Organization/WebSite schema, then
  the title segment that matches the domain, then the domain label.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from . import discovery

LINK_RE = re.compile(r"^[-*+]\s+\[(?P<title>[^\]]+)\]\((?P<url>[^)\s]+)\)\s*(?::\s*(?P<notes>.*))?$")
MAX_LINES = 500
MAX_LINKS = 200
_TITLE_SPLIT_RE = re.compile(r"\s+[|\-–—:·•]\s+")
_NAV_SKIP_RE = re.compile(
    r"(?:^|/)(?:login|log-in|signin|sign-in|signup|sign-up|register|app|account|cart|checkout|logout|"
    r"auth|oauth|download|careers|jobs|privacy|terms|legal|cookies?|status)(?:/|$|\?)", re.I)
_SECTION_FOR_TYPE = {
    "pricing": "Product", "features": "Product", "integrations": "Product", "comparison": "Product",
    "security": "Product", "docs": "Docs", "changelog": "Docs", "customers": "Company", "about": "Company",
    "blog": "Optional", "blog_index": "Optional",
}
_SECTION_ORDER = ["Product", "Docs", "Company", "Optional"]


def parse(content: Optional[str]) -> Dict[str, Any]:
    """{title, h1_count, summary, details, sections: {name: [links]}, has_optional_section}."""
    result: Dict[str, Any] = {"title": None, "h1_count": 0, "summary": None, "details": [],
                              "sections": {}, "has_optional_section": False, "non_link_lines": 0}
    current: Optional[str] = None
    summary: List[str] = []
    in_code = False
    for line in (content or "").lstrip("﻿").splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        if re.match(r"^#\s+\S", stripped):
            result["h1_count"] += 1
            if result["title"] is None:
                result["title"] = stripped[1:].strip()
            continue
        if re.match(r"^##\s+\S", stripped) and not stripped.startswith("###"):
            current = stripped[2:].strip()
            result["sections"].setdefault(current, [])
            if current.lower() == "optional":
                result["has_optional_section"] = True
            continue
        if not stripped:
            continue
        if stripped.startswith(">") and current is None:
            summary.append(stripped.lstrip(">").strip())
            continue
        if current is not None:
            match = LINK_RE.match(stripped)
            if match:
                result["sections"][current].append({
                    "title": match.group("title").strip(),
                    "url": match.group("url").strip(),
                    "notes": (match.group("notes") or "").strip() or None,
                })
            else:
                result["non_link_lines"] += 1
            continue
        result["details"].append(stripped)
    result["summary"] = " ".join(summary).strip() or None
    return result


def all_links(parsed: Dict[str, Any]) -> List[Dict[str, Any]]:
    links = []
    for section, entries in parsed["sections"].items():
        for entry in entries:
            links.append(dict(entry, section=section))
    return links


def validate(content: Optional[str], site_url: Optional[str] = None) -> Dict[str, Any]:
    """Errors (spec), warnings (recommendations), and link hygiene facts."""
    parsed = parse(content)
    errors: List[str] = []
    warnings: List[str] = []
    if not parsed["title"]:
        errors.append("No H1 title. The file must start with '# <site or product name>' (the only required element).")
    elif parsed["h1_count"] > 1:
        warnings.append("%d H1 headings; the format expects exactly one." % parsed["h1_count"])
    if not parsed["summary"]:
        warnings.append("No blockquote summary ('> ...') after the H1.")
    links = all_links(parsed)
    if not parsed["sections"]:
        warnings.append("No H2 sections with link lists.")
    elif not links:
        warnings.append("H2 sections hold no '- [name](url)' link entries.")
    relative = [l["url"] for l in links if not l["url"].startswith(("http://", "https://"))]
    if relative:
        warnings.append("%d link(s) are not absolute http(s) URLs, e.g. %s" % (len(relative), relative[0]))
    seen: Dict[str, int] = {}
    for link in links:
        key = discovery.canonical_url(link["url"]).rstrip("/") if link["url"].startswith("http") else link["url"]
        seen[key] = seen.get(key, 0) + 1
    duplicates = [{"url": u, "count": n} for u, n in seen.items() if n > 1]
    if duplicates:
        warnings.append("%d URL(s) are listed more than once, e.g. %s (%d times)"
                        % (len(duplicates), duplicates[0]["url"], duplicates[0]["count"]))
    off_domain: List[str] = []
    if site_url:
        domain = discovery.registrable_domain(urlparse(site_url).hostname or "")
        for link in links:
            host = (urlparse(link["url"]).hostname or "").lower()
            if host and discovery.registrable_domain(host) != domain and link["url"] not in off_domain:
                off_domain.append(link["url"])
        if off_domain:
            warnings.append("%d link(s) point to other domains (fine for GitHub or a docs host you own; "
                            "check the rest), e.g. %s" % (len(off_domain), off_domain[0]))
    lines = len((content or "").splitlines())
    if lines > MAX_LINES or len(links) > MAX_LINKS:
        warnings.append("Very long (%d lines, %d links): llms.txt is meant as a curated overview, not a sitemap."
                        % (lines, len(links)))
    md_links = sum(1 for l in links if re.search(r"\.md(?:$|[?#])", l["url"]))
    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "title": parsed["title"],
        "summary": parsed["summary"],
        "sections": {name: len(entries) for name, entries in parsed["sections"].items()},
        "has_optional_section": parsed["has_optional_section"],
        "link_count": len(links),
        "markdown_link_count": md_links,
        "duplicates": duplicates[:10],
        "off_domain": off_domain[:10],
        "lines": lines,
        "parsed": parsed,
    }


# ---------------------------------------------------------------------------
# Brand name
# ---------------------------------------------------------------------------


def brand_name(page: Dict[str, Any], site_url: str) -> Dict[str, Any]:
    """Best brand name from page facts, with the source it came from."""
    domain = discovery.registrable_domain(urlparse(site_url).hostname or "")
    label = domain.split(".")[0] if domain else ""
    og = (page.get("og") or {}).get("site_name")
    if og:
        return {"name": og.strip(), "source": "og:site_name"}
    schema = page.get("schema") or {}
    for key in ("organization", "website"):
        item = schema.get(key) or {}
        if item.get("name"):
            return {"name": item["name"], "source": "JSON-LD %s.name" % key}
    title = page.get("title") or ""
    if title:
        parts = [p.strip() for p in _TITLE_SPLIT_RE.split(title) if p.strip()]
        for part in parts:
            if re.sub(r"[^a-z0-9]", "", part.lower()) == re.sub(r"[^a-z0-9]", "", label.lower()):
                return {"name": part, "source": "title segment matching the domain"}
        if len(parts) > 1 and len(parts[-1].split()) <= 3:
            return {"name": parts[-1], "source": "last title segment (check it)"}
    return {"name": label.capitalize() if label else None, "source": "domain label (check it)"}


# ---------------------------------------------------------------------------
# Drafts and suggestions
# ---------------------------------------------------------------------------


def _usable(url: str, site_domain: str) -> bool:
    return discovery.is_candidate(url, site_domain) and not _NAV_SKIP_RE.search(urlparse(url).path or "/")


def _title_for(link: Dict[str, Any]) -> str:
    text = " ".join((link.get("title") or link.get("text") or "").split())
    text = re.sub(r"[←-⇿➔➡⮕]+", "", text).strip(" -:|")
    if not text:
        path = urlparse(link["url"]).path.strip("/").split("/")[-1] or "Home"
        text = path.replace("-", " ").replace("_", " ").capitalize()
    return text[:80]


def candidate_links(seen_links: List[Dict[str, Any]], site_url: str, limit: int = 30) -> List[Dict[str, Any]]:
    """Real links worth listing: [{url, title, type, section}], typed pages first."""
    domain = discovery.registrable_domain(urlparse(site_url).hostname or "")
    out: List[Dict[str, Any]] = []
    used = set()
    for link in seen_links:
        url = discovery.canonical_url(link["url"])
        if url in used or not _usable(url, domain):
            continue
        kind = link.get("type") or discovery.classify_url(url)
        section = _SECTION_FOR_TYPE.get(kind or "")
        if not section:
            continue
        used.add(url)
        out.append({"url": url, "title": _title_for(link), "type": kind, "section": section})
    out.sort(key=lambda l: _SECTION_ORDER.index(l["section"]))
    return out[:limit]


def draft(name: Optional[str], summary: Optional[str], links: List[Dict[str, Any]]) -> str:
    """A draft llms.txt from real facts only. TODO lines mark what is missing."""
    lines = ["# %s" % (name or "TODO: product name"), ""]
    lines.append("> %s" % (summary or "TODO: one or two sentences on what the product does and for whom."))
    lines.append("")
    lines.append("TODO: add key facts an assistant should know (plans, limits, supported platforms), "
                 "each one also stated on a linked page. Delete this line when done.")
    lines.append("")
    by_section: Dict[str, List[Dict[str, Any]]] = {}
    for link in links:
        by_section.setdefault(link["section"], []).append(link)
    if not by_section:
        lines.append("## Docs")
        lines.append("")
        lines.append("TODO: list 5 to 30 of your most useful pages as '- [Title](https://...): what it answers'. "
                     "No usable links were found on the site, so none are listed here.")
        lines.append("")
    for section in _SECTION_ORDER:
        entries = by_section.get(section) or []
        if not entries:
            continue
        lines.append("## %s" % section)
        lines.append("")
        for link in entries:
            lines.append("- [%s](%s)" % (link["title"], link["url"]))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def suggestions(validation: Dict[str, Any], candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Typed pages seen on the site whose type the existing file does not link at all."""
    listed = {discovery.canonical_url(l["url"]).rstrip("/") for l in all_links(validation["parsed"])
              if l["url"].startswith("http")}
    listed_types = {discovery.classify_url(u) for u in listed}
    out = []
    for link in candidates:
        if link["url"].rstrip("/") in listed:
            continue
        if link["type"] in listed_types:
            continue
        out.append({"url": link["url"], "title": link["title"], "type": link["type"],
                    "why": "the site has a %s page but llms.txt links none" % link["type"]})
        listed_types.add(link["type"])
    return out[:8]


__all__ = [
    "LINK_RE", "parse", "all_links", "validate", "brand_name", "candidate_links", "draft", "suggestions",
]
