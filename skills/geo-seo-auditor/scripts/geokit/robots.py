"""robots.txt per RFC 9309: parsing, group selection, longest-match rules.

    parsed = parse(text)
    verdict = evaluate_token(parsed, "GPTBot", ["https://x.app/", "https://x.app/pricing"])

Rules implemented (RFC 9309, https://www.rfc-editor.org/rfc/rfc9309.html):
- A group is one or more user-agent lines followed by rules. Other lines
  (sitemap, content-signal, crawl-delay) do not end a group.
- The product token is matched case-insensitively; all groups that name the
  token are merged; with none, the '*' group applies; with no '*' group,
  everything is allowed.
- The most specific (longest) matching rule wins; on a tie Allow wins.
  '*' matches any sequence and a trailing '$' anchors the end.
- /robots.txt itself is always allowed.
- A leading byte-order mark and 'key : value' spacing are accepted.

robots_status() turns a fetch result into what crawlers do with it:
2xx -> parse; 404/410 and other 4xx -> no rules (allowed); 401/403 or a bot
wall -> unverifiable from here; 429/5xx/unreachable -> compliant crawlers
assume complete disallow; an HTML page served at /robots.txt -> no rules
(misconfiguration).
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import unquote, urlparse

from . import roster

_LINE_RE = re.compile(r"^\s*([A-Za-z][A-Za-z _-]*?)\s*:\s*(.*?)\s*$")
_KEYS = {
    "user-agent": "user-agent", "useragent": "user-agent", "user agent": "user-agent",
    "user_agent": "user-agent",
    "allow": "allow",
    "disallow": "disallow", "dissallow": "disallow", "disalow": "disallow",
    "sitemap": "sitemap", "site-map": "sitemap",
    "content-signal": "content-signal", "content-signals": "content-signal",
    "crawl-delay": "crawl-delay",
    "host": "host",
}
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]+")
_CF_POLICY_RE = re.compile(
    r"as a condition of accessing this website, you agree to abide by the following content signals"
    r"|begin cloudflare managed content",
    re.I,
)

# What a robots.txt fetch outcome means for crawlers.
STATUS_MEANING = {
    "ok": "robots.txt was read; rules below apply.",
    "empty": "robots.txt is empty; crawling is allowed.",
    "not_found": "No robots.txt (HTTP 4xx); under RFC 9309 crawlers may access everything.",
    "html_not_robots": "An HTML page is served at /robots.txt (SPA catch-all or soft 404). Crawlers find no valid rules, so everything is allowed; publish a real robots.txt.",
    "forbidden": "robots.txt answered 401/403 to this tool. Crawlers that get the same answer treat it as 'no rules', but a bot wall may answer them differently: unverifiable from here.",
    "blocked": "Bot protection or rate limiting answered instead of robots.txt: unverifiable from here. Check the CDN or WAF rules for AI crawlers.",
    "server_error": "robots.txt returned a server error (5xx or 429). Compliant crawlers MUST assume complete disallow until it recovers: fix urgently.",
    "unreachable": "robots.txt could not be reached (DNS, TLS, timeout). Compliant crawlers assume complete disallow while this lasts.",
    "too_large": "robots.txt is larger than the read limit; only the first part was parsed (RFC 9309 asks crawlers to parse at least 500 KiB).",
}

# Verdicts a crawler can get.
ALLOWED = "allowed"
BLOCKED = "blocked"
PARTIAL = "partial"
UNVERIFIABLE = "unverifiable"
ASSUMED_BLOCKED = "assumed_blocked"


def _normalize_key(raw: str) -> Optional[str]:
    return _KEYS.get(" ".join(raw.strip().lower().split()))


def product_token(value: str) -> str:
    """'GPTBot/1.1 (+https://openai.com)' -> 'gptbot'; '*' -> '*'."""
    value = (value or "").strip()
    if value.startswith("*"):
        return "*"
    match = _TOKEN_RE.match(value)
    return (match.group(0) if match else value).lower()


def parse_content_signal(value: str) -> Dict[str, str]:
    """'search=yes, ai-train=no' -> {'search': 'yes', 'ai-train': 'no'}."""
    signals: Dict[str, str] = {}
    for part in re.split(r"[,;]", value or ""):
        if "=" not in part:
            continue
        key, _, val = part.partition("=")
        key = key.strip().lower()
        val = val.strip().lower()
        if key:
            signals[key] = val
    return signals


def parse(text: Optional[str]) -> Dict[str, Any]:
    """Parse robots.txt text into groups, sitemaps, content signals and warnings."""
    text = (text or "").lstrip("﻿")
    groups: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = None
    last_was_agent = False
    sitemaps: List[str] = []
    content_signals: List[Dict[str, Any]] = []
    warnings: List[str] = []
    orphan_rules = 0
    invalid_lines = 0
    unknown_keys: Dict[str, int] = {}
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.split("#", 1)[0]
        if not line.strip():
            continue
        match = _LINE_RE.match(line)
        if not match:
            invalid_lines += 1
            continue
        key = _normalize_key(match.group(1))
        value = match.group(2).strip()
        if key is None:
            name = match.group(1).strip().lower()
            unknown_keys[name] = unknown_keys.get(name, 0) + 1
            continue
        if key == "user-agent":
            if current is None or not last_was_agent:
                current = {"agents": [], "agent_lines": [], "rules": [], "line": number,
                           "content_signal": None, "crawl_delay": None}
                groups.append(current)
            current["agents"].append(product_token(value))
            current["agent_lines"].append(value)
            last_was_agent = True
            continue
        if key == "sitemap":
            if value:
                sitemaps.append(value)
            continue
        last_was_agent = False
        if key in ("allow", "disallow"):
            if current is None:
                orphan_rules += 1
                continue
            current["rules"].append({"kind": key, "pattern": value, "line": number})
        elif key == "content-signal":
            signals = parse_content_signal(value)
            entry = {"line": number, "value": value, "signals": signals,
                     "agents": list(current["agents"]) if current is not None else []}
            content_signals.append(entry)
            if current is not None:
                current["content_signal"] = signals
        elif key == "crawl-delay" and current is not None:
            current["crawl_delay"] = value
    if orphan_rules:
        warnings.append("%d allow/disallow line(s) appear before any user-agent line and are ignored" % orphan_rules)
    if invalid_lines:
        warnings.append("%d line(s) are not 'key: value' records and are ignored" % invalid_lines)
    for name, count in sorted(unknown_keys.items()):
        warnings.append("unsupported field '%s' (%d line(s)); crawlers ignore it" % (name, count))
    return {
        "groups": groups,
        "sitemaps": sitemaps,
        "content_signals": content_signals,
        "warnings": warnings,
        "cloudflare_policy_text": bool(_CF_POLICY_RE.search(text)),
        "bytes": len(text.encode("utf-8")),
    }


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------

_REGEX_CACHE: Dict[str, "re.Pattern[str]"] = {}


def _normalize_path(path: str) -> str:
    """Percent-decode except '/' so '/a%2Fb' and '/a/b' stay different."""
    return unquote(path.replace("%2F", "\x00").replace("%2f", "\x00")).replace("\x00", "%2F")


def _compile(pattern: str) -> "re.Pattern[str]":
    cached = _REGEX_CACHE.get(pattern)
    if cached is not None:
        return cached
    anchored = pattern.endswith("$")
    body = _normalize_path(pattern[:-1] if anchored else pattern)
    regex = "".join(".*" if ch == "*" else re.escape(ch) for ch in body)
    compiled = re.compile(regex + ("$" if anchored else ""), re.DOTALL)
    _REGEX_CACHE[pattern] = compiled
    return compiled


def path_of(url: str) -> str:
    """The part of a URL that robots rules match: path plus query."""
    if not url.startswith(("http://", "https://")) and url.startswith("/"):
        return url
    parsed = urlparse(url)
    path = parsed.path or "/"
    if parsed.query:
        path += "?" + parsed.query
    return path


def decide(rules: Iterable[Dict[str, Any]], path: str) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """(allowed, deciding rule) for one path under one merged rule list."""
    if path.split("?", 1)[0] == "/robots.txt":
        return True, None
    target = _normalize_path(path)
    best: Optional[Dict[str, Any]] = None
    for rule in rules:
        pattern = rule["pattern"]
        if not pattern:
            continue  # an empty Disallow or Allow matches nothing
        if not _compile(pattern).match(target):
            continue
        if best is None:
            best = rule
            continue
        if len(pattern) > len(best["pattern"]):
            best = rule
        elif len(pattern) == len(best["pattern"]) and rule["kind"] == "allow" and best["kind"] == "disallow":
            best = rule
    if best is None:
        return True, None
    return best["kind"] == "allow", best


def rules_for(parsed: Dict[str, Any], token: str) -> Tuple[List[Dict[str, Any]], str]:
    """(merged rules, group) where group is 'explicit', 'wildcard' or 'none'."""
    wanted = token.lower()
    explicit = [g for g in parsed["groups"] if wanted in g["agents"]]
    if explicit:
        return [r for g in explicit for r in g["rules"]], "explicit"
    wildcard = [g for g in parsed["groups"] if "*" in g["agents"]]
    if wildcard:
        return [r for g in wildcard for r in g["rules"]], "wildcard"
    return [], "none"


def rule_text(rule: Optional[Dict[str, Any]]) -> Optional[str]:
    if not rule:
        return None
    return "%s: %s (line %d)" % (rule["kind"].capitalize(), rule["pattern"], rule["line"])


def evaluate_token(parsed: Dict[str, Any], token: str, sample_urls: List[str]) -> Dict[str, Any]:
    """Verdict for one token over sample URLs: allowed, blocked or partial."""
    rules, group = rules_for(parsed, token)
    blocked: List[Dict[str, Any]] = []
    allowed_count = 0
    first_allow_rule = None
    for url in sample_urls:
        ok, rule = decide(rules, path_of(url))
        if ok:
            allowed_count += 1
            if rule is not None and first_allow_rule is None:
                first_allow_rule = rule
        else:
            blocked.append({"url": url, "rule": rule_text(rule)})
    if not sample_urls:
        verdict = ALLOWED
    elif not blocked:
        verdict = ALLOWED
    elif allowed_count == 0:
        verdict = BLOCKED
    else:
        verdict = PARTIAL
    return {
        "verdict": verdict,
        "group": group,
        "blocked_samples": blocked,
        "allowed_samples": allowed_count,
        "rule": blocked[0]["rule"] if blocked else rule_text(first_allow_rule),
    }


# ---------------------------------------------------------------------------
# Fetch outcome -> robots status
# ---------------------------------------------------------------------------


def robots_status(result: Dict[str, Any]) -> str:
    """Classify an http.fetch() result for /robots.txt."""
    status = result.get("status")
    code = result.get("http_status")
    if status == "ok":
        return "empty" if not (result.get("text") or "").strip() else "ok"
    if status == "too_large":
        return "too_large"
    if result.get("soft_404"):
        return "html_not_robots"
    if status == "blocked":
        return "server_error" if code == 429 and not result.get("bot_protection") else "blocked"
    if code is None:
        return "unreachable"
    if code == 429 or code >= 500:
        return "server_error"
    if code in (401, 403):
        return "forbidden"
    if 400 <= code < 500:
        return "not_found"
    return "unreachable"


def verdict_without_rules(status: str) -> Optional[str]:
    """The verdict every token gets when the file could not be parsed."""
    if status in ("not_found", "empty", "html_not_robots"):
        return ALLOWED
    if status in ("forbidden", "blocked"):
        return UNVERIFIABLE
    if status in ("server_error", "unreachable"):
        return ASSUMED_BLOCKED
    return None  # ok / too_large: evaluate the rules


def evaluate_all(
    parsed: Optional[Dict[str, Any]],
    status: str,
    sample_urls: List[str],
    tokens: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """One row per roster token: verdict, group, blocked samples and rule."""
    rows: List[Dict[str, Any]] = []
    fixed = verdict_without_rules(status)
    for entry in tokens if tokens is not None else roster.crawlers():
        row = {
            "token": entry["token"],
            "operator": entry["operator"],
            "type": entry["type"],
            "priority": entry["priority"],
            "robots_respected": entry["robots_respected"],
            "status": entry["status"],
        }
        if fixed is not None or parsed is None:
            row.update({"verdict": fixed or UNVERIFIABLE, "group": "none", "blocked_samples": [],
                        "allowed_samples": 0, "rule": None})
        else:
            row.update(evaluate_token(parsed, entry["token"], sample_urls))
        rows.append(row)
    return rows


def agents_in_file(parsed: Dict[str, Any]) -> Dict[str, Any]:
    """Explicit user-agents in the file, split into roster, legacy and other."""
    known = roster.by_token()
    legacy = roster.legacy_tokens()
    seen: List[str] = []
    for group in parsed["groups"]:
        for agent in group["agents"]:
            if agent != "*" and agent not in seen:
                seen.append(agent)
    return {
        "roster": [known[a]["token"] for a in seen if a in known],
        "legacy": [{"token": a, "note": legacy[a]} for a in seen if a in legacy],
        "other_count": len([a for a in seen if a not in known and a not in legacy]),
        "other": [a for a in seen if a not in known and a not in legacy][:15],
        "has_wildcard_group": any("*" in g["agents"] for g in parsed["groups"]),
    }


def summarize(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Counts by type and verdict, plus the critical and high-priority problems."""
    by_type: Dict[str, Dict[str, List[str]]] = {}
    for row in rows:
        bucket = by_type.setdefault(row["type"], {})
        bucket.setdefault(row["verdict"], []).append(row["token"])
    critical = [r["token"] for r in rows if r["priority"] == "critical" and r["verdict"] != ALLOWED]
    high = [r["token"] for r in rows if r["priority"] == "high" and r["verdict"] != ALLOWED]
    return {"by_type": by_type, "critical_not_allowed": critical, "search_not_allowed": high}


__all__ = [
    "STATUS_MEANING", "ALLOWED", "BLOCKED", "PARTIAL", "UNVERIFIABLE", "ASSUMED_BLOCKED",
    "product_token", "parse_content_signal", "parse", "path_of", "decide", "rules_for", "rule_text",
    "evaluate_token", "robots_status", "verdict_without_rules", "evaluate_all",
    "agents_in_file", "summarize",
]
