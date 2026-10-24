"""Proof placeholders and claim candidates in landing-page copy.

Shared by page_structure_analyzer.py (claims already on a live page) and
blueprint_tools.py lint (claims in a draft). Extraction only: a match is a
string the model must trace to proof the user supplied, or replace with a
bracketed placeholder. Nothing here decides whether a claim is true.

Placeholder syntax (report-contract.md section 7 and references/proof-rules.md):
    [LOGO: 4-6 customer logos]          upper-case kind, optional note
    [testimonial: name, role, company]  known kind in any case
A bracket that is a markdown link ("[text](url)"), an evidence ID ("[E1]",
"[V2]"), a checkbox ("[ ]", "[x]") or a footnote ("[^1]") is not a
placeholder.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

EM_DASH = chr(0x2014)
EN_DASH = chr(0x2013)

# Kinds a placeholder may start with in any letter case. Upper-case first
# words ("[HEADSHOT: ...]") are accepted as placeholders too.
PLACEHOLDER_KINDS = {
    "logo", "logos", "customer", "testimonial", "quote", "review", "reviews",
    "rating", "metric", "stat", "number", "result", "case", "proof", "award",
    "badge", "certification", "press", "screenshot", "image", "video", "demo",
    "price", "pricing", "guarantee", "name", "company", "source", "link", "url",
    "date", "count", "headshot", "photo", "partner", "integration", "integrations",
    "compliance", "security", "brand", "cta", "offer", "legal", "voc", "placeholder",
}

# Upper-case labels that are not proof slots.
NOT_PLACEHOLDERS = {"draft"}

_PLACEHOLDER_RE = re.compile(r"\[([^\[\]\n]{2,400})\](?!\()")
_FIRST_WORD_RE = re.compile(r"^\s*([A-Za-z][A-Za-z_-]*)")
_EVIDENCE_ID_RE = re.compile(r"^[A-Z]{1,2}\d{1,3}(?:\s*,\s*[A-Z]{1,2}\d{1,3})*$")

# Claim candidates. Each is a performance, popularity or ranking claim that
# needs a source (FTC substantiation; 16 CFR 465 for reviews and testimonials).
_NUM = r"\d+(?:[.,]\d+)?"
_UNIT = r"(?:\s?(?:%|x|k|seconds?|minutes?|mins?|hours?|hrs?|days?|weeks?|months?|years?)\b|%)?"
CLAIM_PATTERNS: List[Tuple[str, "re.Pattern[str]"]] = [
    ("before_after", re.compile(
        r"\bfrom\s+[$€£]?" + _NUM + _UNIT + r"\s+(?:down\s+|up\s+)?to\s+[$€£]?" + _NUM + _UNIT,
        re.I)),
    ("percent", re.compile(r"(?<![\w.])" + _NUM + r"\s?(?:%|percent\b)", re.I)),
    ("multiplier", re.compile(r"(?<![\w.])" + _NUM + r"\s?x(?![\w])", re.I)),
    ("count", re.compile(
        r"(?<![\w.$])(?:\d{1,3}(?:[,.]\d{3})+|\d+(?:[.,]\d+)?\s?(?:k|m|mm|b|million|thousand|billion)\b|\d{2,})\+?"
        r"(?:\s+(?:of\s+)?(?:happy\s+|active\s+|paying\s+)?(?:customers|teams|users|companies|businesses|developers|"
        r"people|organi[sz]ations|brands|members|downloads|installs|reviews|countries|agencies|startups|"
        r"creators|stores|clinics|restaurants|schools|hospitals|marketers|engineers|designers))",
        re.I)),
    ("plus_count", re.compile(r"(?<![\w.$])(?:\d{1,3}(?:[,.]\d{3})+|\d+(?:[.,]\d+)?\s?[kmb]?)\+(?![\w])", re.I)),
    ("rating", re.compile(
        r"(?<![\w.])[0-5](?:[.,]\d{1,2})?\s?(?:/\s?5|out of 5|stars?\b)|★", re.I)),
    ("ranking", re.compile(r"#\s?1\b|\bno\.\s?1\b|\bnumber\s+one\b|\btop[- ]rated\b|\baward[- ]winning\b", re.I)),
    ("time_claim", re.compile(
        r"\b(?:in|under|within|less than|in just|in only)\s+" + _NUM
        + r"\s?(?:seconds?|secs?|minutes?|mins?|hours?|hrs?|days?|weeks?)\b", re.I)),
    ("money", re.compile(r"(?:[$€£¥₺₹])\s?\d[\d,.]*(?:\s?[kmb]\b)?", re.I)),
]

# "Quoted words" - Name   (straight or curly quotes, at least 4 words inside)
_QUOTE_RE = re.compile(
    r"[\"“„]([^\"“”„]{20,400})[\"”]\s*(?:[-,]|" + EM_DASH + "|" + EN_DASH
    + r")\s*([A-Z][\w.'-]+(?:\s+[A-Z][\w.'-]+){0,3})"
)


def placeholder_kind(inner: str) -> Optional[str]:
    """The placeholder kind for the text inside [...], or None if it is not one."""
    text = inner.strip()
    if not text or text.startswith("^") or text.lower() in ("x", " "):
        return None
    if _EVIDENCE_ID_RE.match(text):
        return None
    match = _FIRST_WORD_RE.match(text)
    if not match:
        return None
    word = match.group(1)
    lower = word.lower()
    if lower in NOT_PLACEHOLDERS:
        return None
    if lower in PLACEHOLDER_KINDS or lower.rstrip("s") in PLACEHOLDER_KINDS:
        return lower
    if len(word) >= 2 and word.isupper():
        return lower
    return None


def find_placeholders(text: str) -> List[Dict[str, object]]:
    """[{kind, text, start, end}] for every placeholder in text."""
    out: List[Dict[str, object]] = []
    for match in _PLACEHOLDER_RE.finditer(text or ""):
        kind = placeholder_kind(match.group(1))
        if kind is None:
            continue
        out.append({"kind": kind, "text": match.group(0), "start": match.start(), "end": match.end()})
    return out


def _mask(text: str, spans: List[Tuple[int, int]]) -> str:
    """Replace spans with spaces so offsets stay the same."""
    if not spans:
        return text
    chars = list(text)
    for start, end in spans:
        for i in range(start, min(end, len(chars))):
            chars[i] = " "
    return "".join(chars)


_MD_LINK_TARGET_RE = re.compile(r"\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
_URL_RE = re.compile(r"https?://\S+")
_CODE_RE = re.compile(r"`[^`\n]*`")
_EVIDENCE_REF_RE = re.compile(r"\[[A-Z]{1,2}\d{1,3}(?:\s*,\s*[A-Z]{1,2}\d{1,3})*\]")


def _snippet(text: str, start: int, end: int, width: int = 60) -> str:
    left = max(0, start - width)
    right = min(len(text), end + width)
    return " ".join(text[left:right].split())


def find_claims(text: str) -> List[Dict[str, object]]:
    """Claim candidates outside placeholders, links, URLs and inline code.

    Returns [{type, text, start, end, context}] in text order; overlapping
    matches keep the first (by the order of CLAIM_PATTERNS) and drop the rest.
    """
    if not text:
        return []
    spans = [(p["start"], p["end"]) for p in find_placeholders(text)]
    spans += [(m.start(), m.end()) for m in _MD_LINK_TARGET_RE.finditer(text)]
    spans += [(m.start(), m.end()) for m in _URL_RE.finditer(text)]
    spans += [(m.start(), m.end()) for m in _CODE_RE.finditer(text)]
    spans += [(m.start(), m.end()) for m in _EVIDENCE_REF_RE.finditer(text)]
    masked = _mask(text, spans)
    found: List[Dict[str, object]] = []
    taken: List[Tuple[int, int]] = []
    for kind, pattern in CLAIM_PATTERNS:
        for match in pattern.finditer(masked):
            start, end = match.start(), match.end()
            if not match.group(0).strip():
                continue
            if any(start < t_end and end > t_start for t_start, t_end in taken):
                continue
            taken.append((start, end))
            found.append({
                "type": kind,
                "text": text[start:end].strip(),
                "start": start,
                "end": end,
                "context": _snippet(text, start, end),
            })
    found.sort(key=lambda item: item["start"])
    return found


def find_quotes(text: str) -> List[Dict[str, object]]:
    """Attributed quotes ("..." - Name) outside placeholders."""
    if not text:
        return []
    spans = [(p["start"], p["end"]) for p in find_placeholders(text)]
    masked = _mask(text, spans)
    out: List[Dict[str, object]] = []
    for match in _QUOTE_RE.finditer(masked):
        if len(match.group(1).split()) < 4:
            continue
        out.append({
            "text": " ".join(match.group(1).split())[:200],
            "attribution": match.group(2),
            "start": match.start(),
            "end": match.end(),
        })
    return out


__all__ = [
    "PLACEHOLDER_KINDS", "CLAIM_PATTERNS", "placeholder_kind", "find_placeholders",
    "find_claims", "find_quotes",
]
