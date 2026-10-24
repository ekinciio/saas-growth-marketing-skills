#!/usr/bin/env python3
"""Ordered outline of a SaaS page's main-content blocks (saas-landing-builder).

A fact extractor for the review (rebuild plan) and pre-fill steps. It fetches
a URL or reads a saved HTML file, drops hidden nodes and page chrome (nav,
footer, cookie banners), and returns the main-content blocks in page order:
heading, a 300-character excerpt, CTAs with href and intent, image counts
(inline SVG included), list items, quote / accordion / form / table markers
and claim candidates that need a source. It also reports the nav and footer
facts the page-type checks need.

There is no score and no order verdict: the model labels every block with
references/section-labels.md, and blueprint_tools.py completeness counts the
labels against the section set for the page type.

Usage:
    python3 page_structure_analyzer.py https://example.com --json
    python3 page_structure_analyzer.py saved.html --url https://example.com --json
    python3 page_structure_analyzer.py example.com --json --out growth-reports/.cache/example-outline.json

Exit codes (shared contract, _growthkit/cli.py):
    0 ok   2 usage error   3 unreachable or blocked   4 partial (page cut at
    the size limit)   5 nothing to analyze (JavaScript shell, empty page)
"""

from __future__ import annotations

import os
import re
import sys
from html import escape
from typing import Any, Dict, List, Optional, Set

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _growthkit import cli  # noqa: E402
import builder_common  # noqa: E402

TOOL = "page_structure_analyzer"

EXCERPT_CHARS = 300
MAX_BLOCK_CTAS = 6
MAX_CLAIMS = 40
MAX_QUOTES = 12
# Blocks whose word sets overlap this much are flagged as likely responsive
# twins (the same section rendered once for desktop and once for mobile).
SIMILARITY_THRESHOLD = 0.6
# Below these the static HTML probably misses content a browser would show.
THIN_MAIN_WORDS = 150
FEW_BLOCKS = 3

_SVG_RE = re.compile(r"<svg\b([^>]*)>(.*?)</svg\s*>", re.IGNORECASE | re.DOTALL)
_ATTR_RE = re.compile(r"""([a-zA-Z_:][-a-zA-Z0-9_:.]*)\s*=\s*("[^"]*"|'[^']*'|[^\s"'>]+)""")
_TITLE_RE = re.compile(r"<title\b[^>]*>(.*?)</title\s*>", re.IGNORECASE | re.DOTALL)
_KEEP_SVG_ATTRS = ("aria-hidden", "hidden", "class", "style", "role", "id")
_HEADING_TAG_RE = re.compile(r"^h[1-6]$")
_WORD_RE = re.compile(r"[^\W_]+", re.UNICODE)
LEGAL_RE = re.compile(
    r"privacy|terms|legal|imprint|impressum|datenschutz|cookie|gdpr|kvkk|gizlilik|"
    r"aviso[- ]legal|mentions[- ]l.gales|dpa\b|security|trust",
    re.IGNORECASE,
)


def svg_to_img(markup: str) -> str:
    """Replace each inline <svg> with an <img> placeholder.

    page_facts() drops <svg> as non-rendered, so SVG logo bars vanish from
    the outline. As <img data-svg> they count as images, keep their hidden
    attributes (aria-hidden icons are still removed) and give link text from
    aria-label or <title> ("GitHub" instead of an empty icon link).
    """
    def replace(match: "re.Match[str]") -> str:
        attrs_text, inner = match.group(1), match.group(2)
        if "<script" in inner.lower() or "</script" in inner.lower():
            return match.group(0)
        attrs = {}
        for name, value in _ATTR_RE.findall(attrs_text):
            attrs[name.lower()] = value.strip("\"'")
        label = attrs.get("aria-label") or ""
        if not label:
            title = _TITLE_RE.search(inner)
            if title:
                label = re.sub(r"<[^>]+>", " ", title.group(1))
        label = " ".join(label.split())[:80]
        kept = "".join(
            ' %s="%s"' % (name, escape(attrs[name], quote=True))
            for name in _KEEP_SVG_ATTRS if name in attrs
        )
        return '<img data-svg="1" alt="%s"%s>' % (escape(label, quote=True), kept)

    return _SVG_RE.sub(replace, markup or "")


def _words(text: str) -> Set[str]:
    return {w.lower() for w in _WORD_RE.findall(text or "") if len(w) > 2}


def _similarity(a: Set[str], b: Set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / float(len(a | b))


def _block_heading(block: Dict[str, Any]) -> Optional[str]:
    """page_facts reports no heading when the block itself is an <h2>."""
    if block.get("heading"):
        return block["heading"]
    if _HEADING_TAG_RE.match(block.get("tag") or "") and block.get("text"):
        return block["text"][:160]
    return None


def _hero_index(outline: List[Dict[str, Any]], ctas: List[Dict[str, Any]]) -> Optional[int]:
    for block in outline:
        if block.get("heading_level") == 1 or block.get("tag") == "h1":
            return block["index"]
    for cta in ctas:
        if cta.get("zone") == "hero" and cta.get("block") is not None:
            return cta["block"]
    return outline[0]["index"] if outline else None


def build_blocks(facts: Dict[str, Any], claims_mod: Any) -> List[Dict[str, Any]]:
    """Turn page_facts()['outline'] into the blocks the model labels."""
    outline = facts.get("outline") or []
    ctas = facts.get("ctas") or []
    hero = _hero_index(outline, ctas)
    blocks: List[Dict[str, Any]] = []
    seen: List[Any] = []
    for position, raw in enumerate(outline):
        index = raw["index"]
        block_ctas = [
            {"text": c.get("text"), "href": c.get("href"), "intent": c.get("intent"), "style": c.get("style")}
            for c in ctas if c.get("block") == index
        ][:MAX_BLOCK_CTAS]
        excerpt = (raw.get("text") or "")[:EXCERPT_CHARS]
        words = _words(raw.get("text") or "")
        similar_to = None
        for other_index, other_words in seen:
            if _similarity(words, other_words) >= SIMILARITY_THRESHOLD and len(words) >= 8:
                similar_to = other_index
                break
        seen.append((index, words))
        headings = raw.get("headings") or []
        blocks.append({
            "index": index,
            "position": position,
            "zone": "hero" if index == hero else "body",
            "tag": raw.get("tag"),
            "id": raw.get("id"),
            "class": raw.get("class"),
            "heading": _block_heading(raw),
            "heading_level": raw.get("heading_level"),
            "subheadings": headings[1:6],
            "words": raw.get("words"),
            "excerpt": excerpt,
            "ctas": block_ctas,
            "images": raw.get("images"),
            "list_items": raw.get("list_items"),
            "has_blockquote": raw.get("has_blockquote"),
            "has_accordion": raw.get("has_details"),
            "has_form": raw.get("has_form"),
            "has_table": raw.get("has_table"),
            "claims": [
                {"type": c["type"], "text": c["text"]}
                for c in claims_mod.find_claims(excerpt)
            ][:8],
            "similar_to": similar_to,
        })
    return blocks


def chrome_facts(markup: str, page_url: Optional[str], ctas: List[Dict[str, Any]], html_mod: Any) -> Dict[str, Any]:
    """Nav and footer facts: link counts, CTAs with intent, legal links."""
    soup = html_mod.parse(markup)
    html_mod.strip_invisible(soup)
    body = soup.body or soup

    def outside_sections(tag: Any) -> bool:
        return tag.find_parent(["article", "section", "aside", "main"]) is None

    nav_nodes = [t for t in body.find_all(["nav", "header"]) if outside_sections(t) or t.name == "nav"]
    nav_nodes += [t for t in body.find_all(attrs={"role": "navigation"}) if t not in nav_nodes]
    footer_nodes = [t for t in body.find_all("footer") if outside_sections(t)]
    footer_nodes += [t for t in body.find_all(attrs={"role": "contentinfo"}) if t not in footer_nodes]

    def links(nodes: List[Any]) -> List[Dict[str, str]]:
        out: List[Dict[str, str]] = []
        seen: Set[str] = set()
        for node in nodes:
            for anchor in node.find_all("a", href=True):
                href = str(anchor.get("href")).strip()
                if not href or href.startswith(("#", "javascript:")):
                    continue
                text = html_mod.clean_text(anchor, collapse=True) or str(anchor.get("aria-label") or "")
                key = href.rstrip("/").lower()
                if key in seen:
                    continue
                seen.add(key)
                out.append({"text": text[:80], "href": href})
        return out

    nav_links = links(nav_nodes)
    footer_links = links(footer_nodes)
    legal = [
        link["text"] or link["href"] for link in footer_links
        if LEGAL_RE.search(link["text"] or "") or LEGAL_RE.search(link["href"] or "")
    ]

    def zone_ctas(zone: str) -> List[Dict[str, Any]]:
        return [
            {"text": c.get("text"), "href": c.get("href"), "intent": c.get("intent")}
            for c in ctas if c.get("zone") == zone
        ][:12]

    return {
        "nav": {
            "present": bool(nav_nodes),
            "link_count": len(nav_links),
            "ctas": zone_ctas("nav"),
        },
        "footer": {
            "present": bool(footer_nodes),
            "link_count": len(footer_links),
            "legal_links": legal[:12],
            "ctas": zone_ctas("footer"),
        },
    }


def summarize_ctas(ctas: List[Dict[str, Any]]) -> Dict[str, Any]:
    """CTA counts by zone and intent, plus the hero CTAs in order."""
    by_zone: Dict[str, Dict[str, int]] = {}
    for cta in ctas:
        zone = cta.get("zone") or "body"
        intent = cta.get("intent") or "none"
        by_zone.setdefault(zone, {})
        by_zone[zone][intent] = by_zone[zone].get(intent, 0) + int(cta.get("count") or 1)
    hero = [
        {"text": c.get("text"), "href": c.get("href"), "intent": c.get("intent"), "style": c.get("style")}
        for c in ctas if c.get("zone") == "hero"
    ][:6]
    return {"by_zone": by_zone, "hero": hero}


def render_hint(facts: Dict[str, Any], blocks: List[Dict[str, Any]], fetch: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Whether a browser render would probably show more of the page."""
    reasons: List[str] = []
    main_words = int(facts.get("main_word_count") or 0)
    if main_words < THIN_MAIN_WORDS:
        reasons.append("only %d words of main content in the static HTML" % main_words)
    if len(blocks) < FEW_BLOCKS:
        reasons.append("only %d main-content block(s) in the static HTML" % len(blocks))
    signals = facts.get("js_shell_signals") or {}
    if signals.get("empty_root"):
        reasons.append("empty app root #%s" % signals["empty_root"])
    if fetch and fetch.get("truncated"):
        reasons.append("the page was cut at the size limit")
    return {"render_recommended": bool(reasons), "reasons": reasons}


def analyze(markup: str, page_url: Optional[str], fetch: Optional[Dict[str, Any]] = None,
            max_blocks: int = 40) -> Dict[str, Any]:
    """All facts for one page. Raises nothing for odd HTML; returns plain JSON types."""
    from _growthkit import html as html_mod
    import proof_patterns as claims_mod

    prepared = svg_to_img(markup)
    facts = html_mod.page_facts(prepared, page_url, text_chars=20000, max_blocks=max_blocks)
    blocks = build_blocks(facts, claims_mod)
    main_text = facts.get("main_text") or ""
    page_claims: List[Dict[str, Any]] = []
    seen_claims: Set[Any] = set()
    for claim in claims_mod.find_claims(main_text):
        key = (claim["type"], claim["text"].lower())
        if key in seen_claims:
            continue
        seen_claims.add(key)
        page_claims.append({"type": claim["type"], "text": claim["text"], "context": claim["context"]})
    quotes = [
        {"text": q["text"], "attribution": q["attribution"]}
        for q in claims_mod.find_quotes(main_text)
    ][:MAX_QUOTES]
    ctas = facts.get("ctas") or []
    meta = facts.get("meta") or {}
    headings = facts.get("headings") or {}
    forms = [
        {
            "kind": f.get("kind"), "zone": f.get("zone"), "block": f.get("block"),
            "questions": f.get("questions"), "required": f.get("required_count"),
            "submit_text": f.get("submit_text"), "primary_candidate": f.get("primary_candidate"),
        }
        for f in (facts.get("forms") or []) if not f.get("hidden")
    ][:8]
    return {
        "page": {
            "url": page_url,
            "title": facts.get("title"),
            "lang": facts.get("lang"),
            "meta_description": meta.get("description"),
            "canonical": meta.get("canonical"),
            "robots": meta.get("robots") or {},
            "viewport": meta.get("viewport"),
            "h1": (headings.get("h1") or [])[:3],
            "h2_count": len(headings.get("h2") or []),
            "word_count": facts.get("word_count"),
            "main_word_count": facts.get("main_word_count"),
            "json_ld_types": (facts.get("json_ld") or {}).get("types") or [],
        },
        "blocks": blocks,
        "block_count": len(blocks),
        "ctas": summarize_ctas(ctas),
        "chrome": chrome_facts(prepared, page_url, ctas, html_mod),
        "forms": forms,
        "embedded_forms": facts.get("embedded_forms") or [],
        "media": facts.get("media") or {},
        "claims": page_claims[:MAX_CLAIMS],
        "claims_total": len(page_claims),
        "quotes": quotes,
        "render": render_hint(facts, blocks, fetch),
        "is_js_shell": bool(facts.get("is_js_shell")),
        "js_shell_signals": facts.get("js_shell_signals") or {},
        "hidden_removed": facts.get("hidden_removed") or {},
        "extractor_notes": facts.get("notes") or [],
        "_facts_for_status": {
            "word_count": facts.get("word_count"),
            "headings": {"h1": headings.get("h1") or []},
            "is_js_shell": facts.get("is_js_shell"),
        },
    }


def format_human(envelope: Dict[str, Any]) -> str:
    """Short text view for a person at a terminal (the model uses --json)."""
    lines = []
    if envelope.get("status") != cli.STATUS_OK:
        lines.append("STATUS: %s" % envelope.get("status"))
        for error in envelope.get("errors") or []:
            lines.append("ERROR: %s" % error)
    page = envelope.get("page") or {}
    if page:
        lines.append("URL: %s" % (page.get("url") or "(file)"))
        lines.append("Title: %s" % (page.get("title") or "-"))
        lines.append("Main-content words: %s in %s blocks" % (page.get("main_word_count"), envelope.get("block_count")))
    for block in envelope.get("blocks") or []:
        lines.append("  [%s] %-5s %-60s ctas=%d img=%s" % (
            block["index"], block["zone"], (block.get("heading") or block.get("excerpt") or "")[:60],
            len(block.get("ctas") or []), block.get("images")))
    render = envelope.get("render") or {}
    if render.get("render_recommended"):
        lines.append("Render recommended: " + "; ".join(render.get("reasons") or []))
    for note in envelope.get("notes") or []:
        lines.append("NOTE: %s" % note)
    lines.append("No score: label the blocks with references/section-labels.md.")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    parser = cli.build_parser(
        "Ordered outline of a SaaS page's main-content blocks, as facts for the model to label.",
        input_help="URL, saved HTML file, or '-' to read HTML from stdin",
        prog="page_structure_analyzer.py",
        demo=False,
    )
    parser.add_argument("--url", help="original URL of a saved HTML file (resolves links; shown in the output)")
    parser.add_argument("--max-blocks", type=int, default=40, help="most blocks to return (default: 40)")
    args = parser.parse_args(argv)
    run = cli.Run(TOOL, args)
    builder_common.ensure_private_reports_dir(args.out, run.log)
    try:
        source = cli.resolve_input(args.input)
    except cli.UsageError as exc:
        return run.fail(cli.STATUS_USAGE, str(exc))
    if args.max_blocks < 1:
        return run.fail(cli.STATUS_USAGE, "--max-blocks must be at least 1")

    from _growthkit import http

    fetch_summary = None
    status = cli.STATUS_OK
    source_info: Dict[str, Any] = {"kind": source["kind"], "input": source["value"]}
    if source["kind"] == "url":
        try:
            page_url = http.normalize_url(source["value"])
        except ValueError as exc:
            return run.fail(cli.STATUS_USAGE, str(exc), data={"source": source_info})
        run.log("fetching %s" % page_url)
        result = http.fetch(page_url, timeout=args.timeout)
        fetch_summary = http.summarize(result)
        source_info["fetch"] = fetch_summary
        outcome, message = cli.fetch_outcome(result)
        if outcome in (cli.STATUS_BLOCKED, cli.STATUS_UNREACHABLE):
            kind = "blocked" if outcome == cli.STATUS_BLOCKED else (
                "http_error" if result.get("http_status") else "unreachable")
            source_info["failure"] = kind
            run.note("blocked: follow references/_shared/browser-fallback.md" if kind == "blocked"
                     else "unreachable: check the URL with the user; a browser will not help")
            return run.fail(outcome, message, data={"source": source_info})
        if outcome == cli.STATUS_NOTHING:
            run.note("follow references/_shared/browser-fallback.md (render the page, then pass the saved file)")
            return run.fail(outcome, message, data={"source": source_info})
        if outcome == cli.STATUS_PARTIAL:
            run.error(message)
            status = cli.STATUS_PARTIAL
        markup = result.get("html") or ""
        page_url = result.get("final_url") or page_url
    else:
        markup = source["text"] or ""
        page_url = None
        if args.url:
            try:
                page_url = http.normalize_url(args.url)
            except ValueError as exc:
                return run.fail(cli.STATUS_USAGE, "--url: %s" % exc)

    facts = analyze(markup, page_url, fetch_summary, args.max_blocks)
    gate = facts.pop("_facts_for_status")
    verdict, message = cli.facts_outcome(gate)
    data = dict(source=source_info, **facts)
    if verdict == cli.STATUS_NOTHING or not facts["blocks"]:
        run.note("follow references/_shared/browser-fallback.md (render the page, then pass the saved file)")
        data["blocks"] = []
        data["block_count"] = 0
        return run.fail(cli.STATUS_NOTHING, message or "No main-content blocks found in the HTML.", data=data)
    if message:
        run.note(message)
    if facts["render"]["render_recommended"]:
        run.note("render recommended before labelling: " + "; ".join(facts["render"]["reasons"]))
    return run.emit(data, status=status, human=format_human)


if __name__ == "__main__":
    sys.exit(main())
