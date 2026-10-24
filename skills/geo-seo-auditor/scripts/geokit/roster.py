"""The AI crawler roster: one data file read by the scripts and the reference.

references/ai-crawlers.json is the single roster for this skill. It mirrors
section 1 of references/_shared/volatile-facts.md (tests check that every
token matches). references/ai-crawlers.md carries tables generated from it
by markdown_tables(); crawler_checker.py --roster-md rewrites them.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from . import ROSTER_PATH

TYPES = ("search", "user-fetch", "training", "control", "other")
PRIORITIES = ("critical", "high", "medium", "policy", "info")
RESPECT_TEXT = {
    "yes": "Yes",
    "may_not": "May not (user-triggered)",
    "not_stated": "Not stated",
    "disputed": "Disputed",
}

MD_BEGIN = "<!-- roster:begin (generated from ai-crawlers.json; do not edit by hand) -->"
MD_END = "<!-- roster:end -->"

_CACHE: Dict[str, Any] = {}


def load(path: Optional[str] = None) -> Dict[str, Any]:
    """The parsed roster file (cached per path)."""
    key = str(path or ROSTER_PATH)
    if key not in _CACHE:
        with open(key, encoding="utf-8") as handle:
            _CACHE[key] = json.load(handle)
    return _CACHE[key]


def crawlers(path: Optional[str] = None) -> List[Dict[str, Any]]:
    return list(load(path)["crawlers"])


def by_token(path: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
    """{lower-case token: entry}."""
    return {c["token"].lower(): c for c in crawlers(path)}


def legacy_tokens(path: Optional[str] = None) -> Dict[str, str]:
    """{lower-case legacy token: note}."""
    return {item["token"].lower(): item["note"] for item in load(path).get("legacy_tokens", [])}


def platforms(path: Optional[str] = None) -> List[Dict[str, Any]]:
    return list(load(path).get("platforms", []))


def last_verified(path: Optional[str] = None) -> str:
    return str(load(path).get("last_verified"))


def _cell(value: Any) -> str:
    text = "-" if value in (None, "") else str(value)
    return text.replace("|", "/")


def markdown_tables(path: Optional[str] = None) -> str:
    """The generated block for references/ai-crawlers.md (markers included)."""
    data = load(path)
    lines = [MD_BEGIN, ""]
    lines.append("Roster last verified: %s. %d tokens." % (data.get("last_verified"), len(data["crawlers"])))
    lines.append("")
    titles = {
        "search": "Search crawlers (allow these to be cited)",
        "user-fetch": "User-triggered fetchers (robots.txt may not apply)",
        "training": "Training crawlers (a policy choice)",
        "control": "Control tokens (do not crawl)",
        "other": "Other crawlers",
    }
    for kind in TYPES:
        rows = [c for c in data["crawlers"] if c["type"] == kind]
        if not rows:
            continue
        lines.append("### %s" % titles[kind])
        lines.append("")
        lines.append("| Token | Operator | Priority | What it controls | Honors robots.txt | IP list | Source | Status |")
        lines.append("|---|---|---|---|---|---|---|---|")
        for c in rows:
            lines.append("| `%s` | %s | %s | %s | %s | %s | %s | %s (%s) |" % (
                c["token"], _cell(c["operator"]), c["priority"], _cell(c["controls"]),
                RESPECT_TEXT.get(c["robots_respected"], c["robots_respected"]),
                _cell(c.get("ip_list")), _cell(c.get("source_url")), c["status"], c["last_verified"],
            ))
        lines.append("")
    lines.append("### Tokens to stop recommending")
    lines.append("")
    lines.append("| Token | Why |")
    lines.append("|---|---|")
    for item in data.get("legacy_tokens", []):
        lines.append("| `%s` | %s |" % (item["token"], _cell(item["note"])))
    lines.append("")
    lines.append("### Platforms and the tokens that decide access")
    lines.append("")
    lines.append("| Platform | Search token | User fetch | Training or control | Page controls | Owner setting |")
    lines.append("|---|---|---|---|---|---|")
    for p in data.get("platforms", []):
        lines.append("| %s | %s | %s | %s | %s | %s |" % (
            p["name"], ", ".join(p["search_tokens"]) or "-", ", ".join(p["user_fetch_tokens"]) or "-",
            ", ".join(p["training_tokens"]) or "-",
            {"google": "noindex, nosnippet, max-snippet", "bing": "noindex, NOARCHIVE, NOCACHE"}.get(
                p.get("page_controls") or "", "-"),
            _cell(p.get("owner_setting")),
        ))
    lines.append("")
    lines.append(MD_END)
    return "\n".join(lines)


def replace_generated(markdown: str, generated: str) -> str:
    """Swap the text between the roster markers for `generated`."""
    start = markdown.find(MD_BEGIN)
    end = markdown.find(MD_END)
    if start < 0 or end < 0 or end < start:
        raise ValueError("roster markers not found in the markdown file")
    return markdown[:start] + generated + markdown[end + len(MD_END):]


def generated_block(markdown: str) -> Optional[str]:
    """The current generated block in a markdown file, or None."""
    start = markdown.find(MD_BEGIN)
    end = markdown.find(MD_END)
    if start < 0 or end < 0:
        return None
    return markdown[start:end + len(MD_END)]


__all__ = [
    "TYPES", "PRIORITIES", "MD_BEGIN", "MD_END", "load", "crawlers", "by_token",
    "legacy_tokens", "platforms", "last_verified", "markdown_tables",
    "replace_generated", "generated_block",
]
