"""Heading-scoped content blocks: the passages an AI answer could quote.

    result = extract_blocks(html_text, "https://linear.app/pricing", page_key="pricing")

A block is the visible text under one heading (h1-h4), collected from leaf
text (p, li, td, dd, summary, leaf divs and spans) with a space at every
element boundary, so words are never glued. Long sections are split at
element boundaries. Navigation, footers, cookie banners, dialogs and hidden
nodes are removed first. Blocks under 8 words are dropped.

Each block records facts only: heading_path, text, words, numbers, years,
named-entity hints, outbound source links, the opening word when it is a
pronoun, and position. There is no score: the model scores the most
important blocks with references/citability-guide.md. Fewer than 3 blocks
gives status "insufficient_content" (never a score of 0).

extract_claims() pulls numeric claims ("100M users", "50 million people")
from any text so the collector can line them up across sources.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

from _growthkit import html as gk_html
from bs4 import NavigableString, Tag

from . import discovery

MIN_WORDS = 8
MAX_BLOCK_WORDS = 220
MAX_TEXT_CHARS = 1200
MIN_BLOCKS = 3

_HEADING_RE = re.compile(r"^h([1-6])$")
_LEAF_TAGS = {"p", "li", "td", "th", "dd", "dt", "blockquote", "figcaption", "summary", "caption", "pre", "address"}
_BLOCK_DESCENDANTS = ["p", "li", "div", "section", "article", "ul", "ol", "table", "h1", "h2", "h3", "h4",
                      "h5", "h6", "blockquote", "dl", "form", "header", "footer", "aside", "main", "figure", "details"]
_PRONOUNS = {
    "it", "its", "it's", "this", "that", "these", "those", "they", "them", "their", "theirs", "he", "she",
    "his", "her", "here", "there", "such", "which", "we", "our", "us", "ours", "you", "your",
}
_STOP_ENTITY = {
    "The", "A", "An", "This", "That", "These", "Those", "It", "We", "Our", "You", "Your", "I", "In", "On",
    "For", "With", "To", "Of", "And", "Or", "But", "If", "When", "What", "How", "Why", "Who", "Where",
    "Get", "Start", "Try", "Sign", "Learn", "Book", "See", "Read", "Free", "New", "All", "More", "Our",
    "Every", "Each", "Use", "Build", "Make", "Find", "Join", "Contact", "Explore", "Discover", "Yes", "No",
}
_COOKIE_RE = re.compile(r"onetrust|cookiebot|cookieyes|cookie|consent|gdpr|osano|didomi|usercentrics|truste", re.I)
_SECTIONING = {"article", "section", "aside", "blockquote", "figure", "li"}
_ZERO_WIDTH_RE = re.compile("[\u200b\u200c\u200d\u2060\ufeff\u00ad]")

NUMBER_RE = re.compile(
    r"(?<![\w.])(?:[$€£¥₹₺]\s?)?\d{1,3}(?:[,.]\d{3})*(?:\.\d+)?\+?"
    r"(?:\s?(?:%|percent|x\b|k\b|m\b|bn\b|b\b|million\b|billion\b|thousand\b))?"
    r"|(?<![\w.])(?:[$€£¥₹₺]\s?)?\d+(?:\.\d+)?\+?(?:\s?(?:%|x\b|k\b|m\b|bn\b|b\b))",
    re.I,
)
YEAR_RE = re.compile(r"\b(?:19[89]\d|20[0-4]\d)\b")
_ENTITY_RE = re.compile(r"\b[A-Z][A-Za-z0-9&.+-]*[A-Za-z0-9+](?:\s+[A-Z][A-Za-z0-9&.+-]*[A-Za-z0-9+]){0,3}")


# ---------------------------------------------------------------------------
# Chrome removal
# ---------------------------------------------------------------------------


def _in_sectioning(tag: Tag) -> bool:
    parent = tag.parent
    while isinstance(parent, Tag):
        if parent.name in _SECTIONING:
            return True
        parent = parent.parent
    return False


def _is_chrome(tag: Tag) -> bool:
    role = str(tag.get("role") or "").lower()
    name = tag.name
    if name == "nav" or role in ("navigation", "contentinfo", "dialog", "alertdialog", "search"):
        return True
    if name == "dialog" or str(tag.get("aria-modal") or "").lower() == "true":
        return True
    if name == "footer" and not _in_sectioning(tag):
        return True
    if (name == "header" and not _in_sectioning(tag)) or role == "banner":
        h1 = tag.find("h1")
        return not (h1 is not None and gk_html.word_count(gk_html.clean_text(h1)) >= 3)
    ident = " ".join([str(tag.get("id") or "")] + [str(c) for c in (tag.get("class") or [])])
    if ident and _COOKIE_RE.search(ident) and gk_html.word_count(tag.get_text(" ", strip=True)) <= 250:
        return True
    return False


def _remove_chrome(root: Tag) -> int:
    targets = [t for t in root.find_all(True) if _is_chrome(t)]
    removed = 0
    for tag in targets:
        if tag.parent is not None:
            tag.extract()
            removed += 1
    return removed


# ---------------------------------------------------------------------------
# Walking
# ---------------------------------------------------------------------------


def _is_leaf_container(tag: Tag) -> bool:
    """A div/span-like element whose text is not split into block children."""
    return tag.find(_BLOCK_DESCENDANTS) is None


def _links_in(tag: Tag, base_url: Optional[str]) -> List[str]:
    out = []
    for a in tag.find_all("a", href=True) if isinstance(tag, Tag) else []:
        href = str(a.get("href") or "").strip()
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        try:
            out.append(urljoin(base_url or "", href))
        except ValueError:
            continue
    if isinstance(tag, Tag) and tag.name == "a" and tag.get("href"):
        try:
            out.append(urljoin(base_url or "", str(tag.get("href"))))
        except ValueError:
            pass
    return out


def _clean(node) -> str:
    """clean_text() without zero-width characters (U+2060 and friends in headings)."""
    text = gk_html.clean_text(node, collapse=True) if not isinstance(node, str) else gk_html.clean_text(node)
    return " ".join(_ZERO_WIDTH_RE.sub("", text).split())


class _Walker:
    def __init__(self, base_url: Optional[str]) -> None:
        self.base_url = base_url
        self.stack: List[Tuple[int, str]] = []
        self.sections: List[Dict[str, Any]] = []
        self.current: Optional[Dict[str, Any]] = None
        self._start_section()

    def _start_section(self) -> None:
        self.current = {"heading_path": [t for _, t in self.stack],
                        "heading_level": self.stack[-1][0] if self.stack else None,
                        "segments": [], "links": [], "list_items": 0, "table_cells": 0}
        self.sections.append(self.current)

    def heading(self, level: int, text: str) -> None:
        if level > 4:
            # h5/h6 are usually card titles: keep them as text, not as scope.
            self.segment(text, "h%d" % level, [])
            return
        while self.stack and self.stack[-1][0] >= level:
            self.stack.pop()
        self.stack.append((level, text))
        self._start_section()

    def segment(self, text: str, tag_name: str, links: List[str]) -> None:
        if not text:
            return
        assert self.current is not None
        self.current["segments"].append(text)
        self.current["links"].extend(links)
        if tag_name == "li":
            self.current["list_items"] += 1
        elif tag_name in ("td", "th"):
            self.current["table_cells"] += 1

    def walk(self, node: Tag) -> None:
        for child in list(node.children):
            if isinstance(child, NavigableString):
                text = _clean(str(child))
                if text and gk_html.word_count(text) >= 1 and node.name not in ("html", "head"):
                    self.segment(text, node.name or "", [])
                continue
            if not isinstance(child, Tag):
                continue
            match = _HEADING_RE.match(child.name or "")
            if match:
                text = _clean(child)
                if text:
                    self.heading(int(match.group(1)), text)
                continue
            if child.name in _LEAF_TAGS or _is_leaf_container(child):
                inner_heading = child.find(_HEADING_RE)
                if inner_heading is not None and child.name != "summary":
                    self.walk(child)
                    continue
                text = _clean(child)
                self.segment(text, child.name or "", _links_in(child, self.base_url))
                continue
            self.walk(child)


# ---------------------------------------------------------------------------
# Facts per block
# ---------------------------------------------------------------------------


def find_numbers(text: str) -> List[str]:
    out: List[str] = []
    for match in NUMBER_RE.finditer(text or ""):
        token = match.group(0).strip()
        if YEAR_RE.fullmatch(token.rstrip("+")):
            continue
        if token and token not in out:
            out.append(token)
    return out[:12]


def find_years(text: str) -> List[str]:
    out: List[str] = []
    for match in YEAR_RE.finditer(text or ""):
        if match.group(0) not in out:
            out.append(match.group(0))
    return out[:6]


def find_entities(text: str) -> List[str]:
    """Capitalized phrases that are not sentence openers (hints, not judgments)."""
    out: List[str] = []
    for sentence in re.split(r"(?<=[.!?:;])\s+|\s+\|\s+", text or ""):
        words = sentence.split()
        if not words:
            continue
        for match in _ENTITY_RE.finditer(sentence):
            phrase = match.group(0).strip(".")
            if match.start() == 0 and " " not in phrase:
                continue  # a lone sentence-initial capital is not evidence of a name
            first = phrase.split()[0]
            if first in _STOP_ENTITY and " " not in phrase:
                continue
            if phrase.isupper() and len(phrase) > 6:
                continue
            if phrase not in out:
                out.append(phrase)
    return out[:8]


def opening_word(text: str) -> Optional[str]:
    first = (text or "").strip().split(" ", 1)[0].strip("\"'([{").lower().replace("’", "'")
    first = first.rstrip(",.:;!?")
    return first if first in _PRONOUNS else None


def _source_links(links: List[str], site_domain: str) -> List[str]:
    out = []
    for url in links:
        host = (urlparse(url).hostname or "").lower()
        if not host or discovery.registrable_domain(host) == site_domain:
            continue
        if url not in out:
            out.append(url)
    return out[:5]


def _chunk(segments: List[str], max_words: int) -> List[List[str]]:
    chunks: List[List[str]] = [[]]
    words = 0
    for seg in segments:
        count = gk_html.word_count(seg)
        if chunks[-1] and words + count > max_words:
            chunks.append([])
            words = 0
        chunks[-1].append(seg)
        words += count
    return [c for c in chunks if c]


def extract_blocks(
    markup: Optional[str],
    url: Optional[str] = None,
    page_key: str = "page",
    page_type: Optional[str] = None,
    max_blocks: int = 60,
    min_words: int = MIN_WORDS,
    max_block_words: int = MAX_BLOCK_WORDS,
) -> Dict[str, Any]:
    """Blocks plus counts. status is 'ok' or 'insufficient_content'."""
    soup = gk_html.parse(markup or "")
    gk_html.strip_invisible(soup)
    body = soup.body or soup
    raw_words = gk_html.word_count(gk_html.clean_text(body))
    _remove_chrome(body)
    root = body.find("main") or body.find(attrs={"role": "main"}) or body
    walker = _Walker(url)
    if root is not body:
        # A hero outside <main> (header with the h1) still counts.
        for h1 in body.find_all("h1"):
            if not _contains(root, h1):
                walker.heading(1, _clean(h1))
                break
    walker.walk(root)

    site_domain = discovery.registrable_domain(urlparse(url or "").hostname or "") if url else ""
    blocks: List[Dict[str, Any]] = []
    seen = set()
    for section in walker.sections:
        segments = gk_html.dedupe_texts(section["segments"], containment=True)
        for chunk in _chunk(segments, max_block_words):
            text = " ".join(chunk).strip()
            words = gk_html.word_count(text)
            if words < min_words:
                continue
            key = re.sub(r"\W+", " ", text.lower()).strip()
            if key in seen:
                continue
            seen.add(key)
            blocks.append({
                "id": "%s-b%d" % (page_key, len(blocks) + 1),
                "page": page_key,
                "page_type": page_type,
                "url": url,
                "heading_path": section["heading_path"][-3:],
                "heading_is_question": bool(section["heading_path"]) and section["heading_path"][-1].rstrip().endswith("?"),
                "text": text[:MAX_TEXT_CHARS],
                "truncated": len(text) > MAX_TEXT_CHARS,
                "words": words,
                "numbers": find_numbers(text),
                "years": find_years(text),
                "entities": find_entities(text),
                "source_links": _source_links(section["links"], site_domain) if site_domain else [],
                "opening_pronoun": opening_word(text),
                "list_items": section["list_items"],
                "table_cells": section["table_cells"],
                "position": len(blocks),
            })
    total = len(blocks)
    for block in blocks:
        block["position_pct"] = round(100.0 * block["position"] / max(total - 1, 1)) if total > 1 else 0
    truncated = total > max_blocks
    blocks = blocks[:max_blocks]
    status = "ok" if total >= MIN_BLOCKS else "insufficient_content"
    return {
        "status": status,
        "reason": None if status == "ok" else (
            "Only %d block(s) of %d+ words found under headings; %d visible words in total. "
            "Do not score citability from this page (render it in a browser or pick another page)."
            % (total, min_words, raw_words)),
        "raw_text_words": raw_words,
        "count": total,
        "returned": len(blocks),
        "truncated": truncated,
        "with_numbers": sum(1 for b in blocks if b["numbers"]),
        "with_source_links": sum(1 for b in blocks if b["source_links"]),
        "question_headings": sum(1 for b in blocks if b["heading_is_question"]),
        "pronoun_openings": sum(1 for b in blocks if b["opening_pronoun"]),
        "blocks": blocks,
    }


def _contains(ancestor: Tag, node: Tag) -> bool:
    current = node
    while current is not None:
        if current is ancestor:
            return True
        current = current.parent
    return False


# ---------------------------------------------------------------------------
# Numeric claims for the consistency check
# ---------------------------------------------------------------------------

UNIT_FAMILIES = {
    "people": ("users", "user", "people", "members", "individuals", "learners", "creators", "developers",
               "professionals", "subscribers", "marketers", "designers", "engineers"),
    "organizations": ("teams", "companies", "businesses", "organizations", "organisations", "customers",
                      "brands", "enterprises", "startups", "agencies", "clients", "workspaces"),
    "countries": ("countries", "markets", "regions"),
    "languages": ("languages",),
    "integrations": ("integrations", "apps", "connectors", "plugins", "extensions", "tools"),
    "templates": ("templates",),
    "reviews": ("reviews", "ratings", "stars"),
    "employees": ("employees", "staff", "people on our team"),
    "uptime": ("uptime",),
}
_UNIT_TO_FAMILY = {word: family for family, words in UNIT_FAMILIES.items() for word in words}
_CLAIM_RE = re.compile(
    r"(?P<num>\d{1,3}(?:[,.]\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)\s*(?P<mult>k|m|mm|bn|b|thousand|million|billion)?\b\+?"
    r"\s*(?:\+\s*)?(?:(?:of|active|paying|monthly|happy|global|million|thousand|more|than|over|in|across|from|"
    r"the|world'?s|top|leading|fortune|500|best)\s+){0,4}(?P<unit>[a-z]+)",
    re.I,
)
_MULT = {"k": 1e3, "thousand": 1e3, "m": 1e6, "mm": 1e6, "million": 1e6, "b": 1e9, "bn": 1e9, "billion": 1e9}


def _number_value(num: str, mult: Optional[str]) -> Optional[float]:
    text = num.replace(",", "")
    if num.count(".") > 1 or re.match(r"^\d{1,3}\.\d{3}$", num):
        text = num.replace(".", "")  # 1.000 written with a dot separator
    try:
        value = float(text)
    except ValueError:
        return None
    return value * _MULT.get((mult or "").lower(), 1.0)


def extract_claims(text: Optional[str], source: str, limit: int = 12) -> List[Dict[str, Any]]:
    """Numeric claims with a unit family: [{source, family, unit, value, raw, text}]."""
    out: List[Dict[str, Any]] = []
    if not text:
        return out
    sentences = re.split(r"(?<=[.!?])\s+|\n+", text)
    for sentence in sentences:
        for match in _CLAIM_RE.finditer(sentence):
            unit = match.group("unit").lower()
            family = _UNIT_TO_FAMILY.get(unit)
            if not family:
                continue
            value = _number_value(match.group("num"), match.group("mult"))
            if value is None or YEAR_RE.fullmatch(match.group("num")) and not match.group("mult"):
                continue
            out.append({
                "source": source,
                "family": family,
                "unit": unit,
                "value": value,
                "raw": " ".join(match.group(0).split())[:60],
                "text": " ".join(sentence.split())[:240],
            })
            if len(out) >= limit:
                return out
    return out


def find_conflicts(claims: List[Dict[str, Any]], tolerance: float = 0.05) -> List[Dict[str, Any]]:
    """Unit families stated with different values in different sources."""
    families: Dict[str, List[Dict[str, Any]]] = {}
    for claim in claims:
        families.setdefault(claim["family"], []).append(claim)
    conflicts = []
    for family, items in families.items():
        sources = {c["source"] for c in items}
        if len(sources) < 2:
            continue
        values = [c["value"] for c in items if c["value"] > 0]
        if not values:
            continue
        if max(values) / min(values) <= 1 + tolerance:
            continue
        conflicts.append({
            "family": family,
            "values": [{"source": c["source"], "raw": c["raw"], "value": c["value"], "text": c["text"]}
                       for c in items][:8],
        })
    return conflicts


__all__ = [
    "MIN_WORDS", "MIN_BLOCKS", "extract_blocks", "find_numbers", "find_years", "find_entities",
    "opening_word", "extract_claims", "find_conflicts", "UNIT_FAMILIES",
]
