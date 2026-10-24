#!/usr/bin/env python3
"""Pricing facts and math engine for the pricing-analyzer skill.

The script never judges pricing. It normalizes what the user (or a pricing
page) says, does deterministic math, and prints one JSON envelope. The model
judges the facts against references/rubric.md.

Commands (each prints one JSON envelope with --json; see --help):

    facts     own and competitor tiers -> normalized tiers (custom prices,
              flat / per-seat / usage billing, monthly vs annual, seat
              minimums and caps), "Everything in X" expansion and the
              features each tier adds, a cost-at-scenario matrix (monthly
              cost at 1/5/20/100 seats or the user's own segment sizes, own
              pricing vs each competitor), feature gates ("cheapest plan
              with SSO"), and business-metric facts with flags.
    survey    Van Westendorp Price Sensitivity Meter from per-respondent
              rows (JSON or a CSV export), with invalid respondents dropped,
              a sample-size gate, and the optional Newton-Miller-Smith
              purchase-intent extension (revenue-optimal price).
    increase  price-increase break-even churn, what-if outcomes, notice and
              grandfathering timelines per customer segment.
    score     weighted total of the model's rubric scores (na and
              not_measured dimensions are dropped and the weights
              renormalized).
    plan      A/B test sizing for a pricing or packaging test (shared stats).

Usage:
    pricing_analyzer.py facts input.json --json
    pricing_analyzer.py survey responses.csv --json
    pricing_analyzer.py increase increase.json --json
    pricing_analyzer.py score scores.json --json
    pricing_analyzer.py plan --baseline 3% --weekly-visitors 2500 --json
    pricing_analyzer.py input.json --json      (no command: facts, or survey
                                                when the file is a survey)

Exit codes (shared contract): 0 ok, 2 input error (every bad field is
listed in "errors"), 4 partial, 5 nothing to analyze (for example fewer
than 30 valid survey responses), 1 a bug.

Customer data stays local: survey and metrics outputs are aggregates only.
"""

from __future__ import annotations

import csv
import io
import json
import math
import os
import re
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from _growthkit import cli, stats  # noqa: E402

TOOL = "pricing_analyzer"
COMMANDS = ("facts", "survey", "increase", "score", "plan")
BENCHMARKS_PATH = HERE.parent / "references" / "_shared" / "saas-benchmarks.json"

DEFAULT_SEAT_SCENARIOS = (1, 5, 20, 100)
MAX_SCENARIOS = 25

# Van Westendorp sample-size gate. SurveyMonkey: "The PSM needs a minimum of
# 30 completed responses to generate the chart" and "aim for 100 to 200 from
# your target buyer segment" (references/wtp-research.md, verified 2026-10-24).
VW_MIN_VALID = 30
VW_STANDARD_VALID = 100

# Newton-Miller-Smith defaults from the R package pricesensitivitymeter
# (PSM_CONSTANTS.NMS_DEFAULTS): a 5-point purchase-intent scale where 5 is
# "very likely", calibrated to purchase probabilities.
NMS_PI_SCALE = (5, 4, 3, 2, 1)
NMS_PI_CALIBRATED = (0.7, 0.5, 0.3, 0.1, 0.0)

# The rubric in references/rubric.md. Keep ids, weights and the version in
# sync with that file (a unit test checks it).
RUBRIC_VERSION = "pricing-rubric-v1"
RUBRIC_WEIGHTS = {
    "value_metric": 20,
    "packaging_fences": 20,
    "ladder_anchoring": 15,
    "price_level": 10,
    "entry_offer": 10,
    "enterprise_threshold": 10,
    "cost_to_serve": 10,
    "annual_discounting": 5,
}
RUBRIC_MAX = 10
COMPOSITE_MIN_MEASURED = 0.6  # report-contract.md section 4, rule 4


# ---------------------------------------------------------------------------
# Input errors
# ---------------------------------------------------------------------------

class PricingInputError(ValueError):
    """The input cannot be analyzed. ``problems`` holds one message per bad field."""

    def __init__(self, problems: List[str]) -> None:
        self.problems = list(problems)
        super().__init__("; ".join(self.problems))


# ---------------------------------------------------------------------------
# Price parsing
# ---------------------------------------------------------------------------

# Price strings that mean "no published price" (a "Contact sales" tier).
_CUSTOM_PRICE_RE = re.compile(
    r"\b(?:custom|contact|sales|quote|talk|call|demo|request|bespoke|"
    r"negotiable|enterprise|tbd)\b|get\s+in\s+touch|let'?s\s+chat",
    re.IGNORECASE,
)
_FREE_PRICE_RE = re.compile(r"^\s*free\b", re.IGNORECASE)
_YEARLY_PRICE_RE = re.compile(r"\d\s*(?:/|per|a)\s*(?:yr|year)\b|\bper\s+annum\b", re.IGNORECASE)
_NUMBER_TOKEN_RE = re.compile(r"\d[\d.,]*\d|\d")
_PLAIN_NUMBER_RE = re.compile(r"^\d+(?:\.\d+)?$")
_THOUSANDS_RE = re.compile(r"^\d{1,3}(?:,\d{3})+(?:\.\d+)?$")
_DECIMAL_COMMA_RE = re.compile(r"^\d+,\d{1,2}$")
_EU_THOUSANDS_RE = re.compile(r"^\d{1,3}(?:\.\d{3})+,\d{1,2}$")
_MAGNITUDE_SUFFIX_RE = re.compile(r"^\s*[km](?![a-z])", re.IGNORECASE)
_PER_SEAT_HINT_RE = re.compile(
    r"\b(?:per|/|a|each)\s*(?:user|seat|member|editor|agent|license|licence|teammate|person|creator)s?\b",
    re.IGNORECASE,
)

_PRICE_HINT = 'use a number (0 for a free tier), or null / "custom" for a Contact sales tier'


def _parse_number_token(token: str) -> Optional[float]:
    """Read one number token, or None when its separators are ambiguous."""
    if _PLAIN_NUMBER_RE.match(token):
        return float(token)
    if _THOUSANDS_RE.match(token):
        return float(token.replace(",", ""))
    if _DECIMAL_COMMA_RE.match(token):
        return float(token.replace(",", "."))
    if _EU_THOUSANDS_RE.match(token):
        return float(token.replace(".", "").replace(",", "."))
    return None


def _clean_number(value: float) -> float:
    """An int when the value is whole, so $29 does not print as 29.0."""
    return int(value) if float(value).is_integer() else value


def _to_number(raw: Any, where: str) -> float:
    """A JSON number or numeric string as a non-negative number, else ValueError."""
    if isinstance(raw, bool):
        raise ValueError("%s: %r is not a number" % (where, raw))
    if isinstance(raw, (int, float)):
        value = raw
    elif isinstance(raw, str):
        text = raw.strip()
        if text.startswith("-"):
            raise ValueError("%s: %r is negative" % (where, raw))
        match = _NUMBER_TOKEN_RE.search(text)
        if not match:
            raise ValueError("%s: %r is not a number" % (where, raw))
        parsed = _parse_number_token(match.group(0))
        if parsed is None or _MAGNITUDE_SUFFIX_RE.match(text[match.end():]):
            raise ValueError(
                "%s: %r is not a clear number (write it in full, e.g. 1200 or 10.99)" % (where, raw)
            )
        value = _clean_number(parsed)
    else:
        raise ValueError("%s: expected a number, got %s" % (where, type(raw).__name__))
    if math.isnan(value) or math.isinf(value):
        raise ValueError("%s: %r is not a finite number" % (where, raw))
    if value < 0:
        raise ValueError("%s: %r is negative" % (where, raw))
    return value


def _parse_price(raw: Any, where: str) -> Tuple[Optional[float], bool]:
    """Parse a monthly list price. Returns (price, is_custom).

    price is None for custom ("Contact sales") tiers. A yearly figure is an
    error here: put it in annual_price (or annual_price_total).
    """
    if raw is None:
        return None, True
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            raise ValueError("%s: empty price - %s" % (where, _PRICE_HINT))
        if _CUSTOM_PRICE_RE.search(text):
            return None, True
        if _FREE_PRICE_RE.match(text):
            return 0, False
        if _YEARLY_PRICE_RE.search(text):
            raise ValueError(
                "%s: %r looks like a yearly price - enter the monthly price, or put the "
                "yearly figure in annual_price_total" % (where, raw)
            )
    try:
        return _to_number(raw, where), False
    except ValueError as exc:
        raise ValueError("%s - %s" % (exc, _PRICE_HINT)) from None


def _optional_number(raw: Any, where: str, problems: List[str]) -> Optional[float]:
    """A non-negative number, None when missing ('skip', '', null)."""
    if cli.is_missing(raw):
        return None
    try:
        return _to_number(raw, where)
    except ValueError as exc:
        problems.append(str(exc))
        return None


def _optional_int(raw: Any, where: str, problems: List[str]) -> Optional[int]:
    value = _optional_number(raw, where, problems)
    if value is None:
        return None
    if not float(value).is_integer():
        problems.append("%s: %r must be a whole number" % (where, raw))
        return None
    return int(value)


def _optional_percent(raw: Any, where: str, problems: List[str],
                      maximum: float = 100.0) -> Optional[float]:
    """A percentage in percent units ('25%', 25, '1/4' -> 25.0)."""
    try:
        return cli.to_percent(raw, field=where, minimum=0, maximum=maximum)
    except cli.CoercionError as exc:
        problems.append(str(exc))
        return None


def _annual_monthly(tier_raw: Dict[str, Any], where: str, problems: List[str],
                    notes: List[str]) -> Optional[float]:
    """Monthly-equivalent price when billed annually.

    annual_price is the per-month figure most pricing pages show ("$8/mo
    billed annually"); annual_price_total is the yearly amount. A yearly
    string in annual_price ("$96/yr") is divided by 12 and noted.
    """
    if not cli.is_missing(tier_raw.get("annual_price_total")):
        total = _optional_number(tier_raw.get("annual_price_total"), where + ".annual_price_total", problems)
        return None if total is None else round(total / 12.0, 4)
    raw = tier_raw.get("annual_price")
    if cli.is_missing(raw):
        return None
    if isinstance(raw, str) and _CUSTOM_PRICE_RE.search(raw):
        return None
    if isinstance(raw, str) and _YEARLY_PRICE_RE.search(raw):
        total = _optional_number(raw, where + ".annual_price", problems)
        if total is None:
            return None
        notes.append("%s.annual_price %r read as a yearly total and divided by 12." % (where, raw))
        return round(total / 12.0, 4)
    return _optional_number(raw, where + ".annual_price", problems)


# ---------------------------------------------------------------------------
# Features: "Everything in X" expansion, diffs and limit changes
# ---------------------------------------------------------------------------

# "Everything in Plus, plus:", "Includes everything in the Pro plan", "All
# features of Team"; the tier name itself is matched against the real tier
# names (longest first), so "Everything in Pro Plus" finds "Pro Plus", not "Pro".
_INHERIT_PREFIX_RE = re.compile(
    r"^\s*(?:includes\s+|including\s+)?(?:everything|all(?:\s+the)?\s+features?|all)\s+"
    r"(?:in|from|of|on|included\s+in)\s+(?:the\s+)?(?P<rest>.+)$",
    re.IGNORECASE,
)
# "All Free features + 5 teams", "All Pro features, plus:".
_ALL_X_RE = re.compile(r"^\s*all\s+(?:the\s+|of\s+(?:the\s+)?)?(?P<rest>.+)$", re.IGNORECASE)
_AFTER_NAME_RE = re.compile(
    r"^\s*(?:(?:plan|tier|package|edition)\b)?\s*(?P<features>features?\b)?\s*[,:;]?\s*"
    r"(?P<plus>(?:plus|and)\b|\+)?\s*:?\s*(?P<extra>.*?)\s*[:.!]*\s*$",
    re.IGNORECASE,
)

_LIMIT_LEAD_RE = re.compile(
    r"^(?:includes\s+)?(?:up\s+to\s+)?(?P<qty>unlimited|\d[\d,.]*\s*(?:k|m|gb|tb|mb)?\+?)\s+(?P<item>[a-z][^:]*)$",
    re.IGNORECASE,
)
_LIMIT_TRAIL_RE = re.compile(r"^(?P<item>[a-z][^:]*?)\s*:\s*(?P<qty>unlimited|\d[\d,.]*\s*(?:k|m|gb|tb|mb)?\+?)$",
                             re.IGNORECASE)


def _feature_key(text: str) -> str:
    """Comparison key: lower case, single spaces, no trailing punctuation."""
    value = " ".join(str(text).lower().replace("’", "'").split())
    return value.strip(" .;:,!*")


def _name_key(text: str) -> str:
    value = _feature_key(text)
    value = re.sub(r"^(?:the)\s+", "", value)
    value = re.sub(r"\s+(?:plan|tier|package|edition)$", "", value)
    return value


def _limit_parts(feature: str) -> Optional[Tuple[str, str]]:
    """('projects', '3') for '3 projects', 'Up to 3 projects' or 'Projects: 3'."""
    text = _feature_key(feature)
    match = _LIMIT_LEAD_RE.match(text) or _LIMIT_TRAIL_RE.match(text)
    if not match:
        return None
    item = re.sub(r"\s+", " ", match.group("item")).strip()
    item = re.sub(r"(?<=[a-z])s\b", "", item)  # "users" -> "user", "projects" -> "project"
    return item, match.group("qty").strip()


def _normalize_features(raw: Any, where: str, problems: List[str]) -> List[str]:
    """Features as a list of non-empty strings (missing -> [])."""
    if raw is None:
        return []
    if isinstance(raw, str):
        return [part.strip() for part in re.split(r"[,;\n]", raw) if part.strip()]
    if isinstance(raw, (list, tuple)):
        out = []
        for item in raw:
            if item is None:
                continue
            text = str(item).strip()
            if text:
                out.append(text)
        return out
    problems.append("%s: expected a list of feature names, got %s" % (where, type(raw).__name__))
    return []


def _leading_tier_name(text: str, names: Dict[str, str], own_key: str) -> Optional[Tuple[str, str]]:
    """(tier name, text after it) when text starts with a tier name (longest first)."""
    lowered = text.lower().replace("’", "'")
    for key in sorted(names, key=len, reverse=True):
        if key == own_key or not key:
            continue
        if lowered.startswith(key) and (len(lowered) == len(key) or not lowered[len(key)].isalnum()):
            return names[key], text[len(key):]
    return None


def _match_inheritance(feature: str, names: Dict[str, str], own_key: str) -> Optional[Tuple[str, Optional[str]]]:
    """(tier name, extra feature or None) for 'Everything in Plus, plus: X' style markers."""
    text = " ".join(feature.split())
    forms = []
    match = _INHERIT_PREFIX_RE.match(text)
    if match:
        forms.append(("prefix", match.group("rest")))
    match = _ALL_X_RE.match(text)
    if match:
        forms.append(("all", match.group("rest")))
    forms.append(("bare", text))
    for kind, rest in forms:
        hit = _leading_tier_name(rest, names, own_key)
        if hit is None:
            continue
        name, after = hit
        tail = _AFTER_NAME_RE.match(after)
        if tail is None:
            continue
        has_plus = bool(tail.group("plus"))
        extra = (tail.group("extra") or "").strip(" ,;:") or None
        if kind == "all" and not tail.group("features"):
            continue  # "All Pro" without "features" is not an inheritance marker
        if kind == "bare" and not has_plus:
            continue  # a feature that merely starts with a tier name
        if extra and not has_plus:
            if kind == "prefix":
                return name, None  # "Everything in Business for teams": descriptive tail
            continue
        return name, extra
    return None


def expand_features(tiers: List[Dict[str, Any]], notes: List[str], company: str) -> None:
    """Resolve 'Everything in X' and compute what each tier adds over the one below.

    Works in place on normalized tiers in ladder order. Adds features_listed,
    inherits_from, features_all, added, removed and limit_changes.
    """
    names = {_name_key(t["name"]): t["name"] for t in tiers}
    by_name = {t["name"]: t for t in tiers}
    for tier in tiers:
        own_key = _name_key(tier["name"])
        inherits = None
        listed = []
        for feature in tier["features_raw"]:
            hit = _match_inheritance(feature, names, own_key) if inherits is None else None
            if hit is not None:
                inherits = hit[0]
                if hit[1]:
                    listed.append(hit[1])
                continue
            if inherits is None and re.match(r"^\s*(?:everything|all)\s+(?:in|from|of)\b", feature, re.I):
                notes.append("%s %s: %r names a tier that is not in the input; kept as a feature."
                             % (company, tier["name"], feature))
            listed.append(feature)
        tier["features_listed"] = listed
        tier["inherits_from"] = inherits

    resolved: Dict[str, List[str]] = {}

    def resolve(name: str, chain: Tuple[str, ...]) -> List[str]:
        if name in resolved:
            return resolved[name]
        tier = by_name[name]
        features: List[str] = []
        seen = set()
        parent = tier["inherits_from"]
        if parent and parent not in chain:
            for feature in resolve(parent, chain + (name,)):
                key = _feature_key(feature)
                if key not in seen:
                    seen.add(key)
                    features.append(feature)
        elif parent:
            notes.append("%s %s: circular 'Everything in' reference ignored." % (company, name))
        for feature in tier["features_listed"]:
            key = _feature_key(feature)
            if key not in seen:
                seen.add(key)
                features.append(feature)
        resolved[name] = features
        return features

    previous: Optional[Dict[str, Any]] = None
    for tier in tiers:
        tier["features_all"] = resolve(tier["name"], ())
        base = by_name[tier["inherits_from"]] if tier["inherits_from"] else previous
        tier["compared_with"] = base["name"] if base else None
        if base is None:
            tier["added"] = list(tier["features_all"])
            tier["removed"] = []
            tier["limit_changes"] = []
        else:
            base_keys = {_feature_key(f): f for f in resolve(base["name"], ())}
            own_keys = {_feature_key(f): f for f in tier["features_all"]}
            added = [f for k, f in own_keys.items() if k not in base_keys]
            removed = [f for k, f in base_keys.items() if k not in own_keys]
            changes = []
            added_limits = {}
            for feature in added:
                parts = _limit_parts(feature)
                if parts:
                    added_limits.setdefault(parts[0], (parts[1], feature))
            matched_added, matched_removed = set(), set()
            for feature in removed:
                parts = _limit_parts(feature)
                if parts and parts[0] in added_limits:
                    new_qty, new_feature = added_limits[parts[0]]
                    changes.append({"item": parts[0], "from": parts[1], "to": new_qty})
                    matched_added.add(new_feature)
                    matched_removed.add(feature)
            tier["added"] = [f for f in added if f not in matched_added]
            tier["removed"] = [f for f in removed if f not in matched_removed]
            tier["limit_changes"] = changes
        previous = tier


# ---------------------------------------------------------------------------
# Tier normalization
# ---------------------------------------------------------------------------

_BILLING_UNITS = {
    "flat": "flat", "account": "flat", "per_account": "flat", "per account": "flat",
    "workspace": "flat", "per_workspace": "flat", "flat_rate": "flat", "flat rate": "flat",
    "per_seat": "per_seat", "per seat": "per_seat", "seat": "per_seat", "per_user": "per_seat",
    "per user": "per_seat", "user": "per_seat", "per_member": "per_seat", "member": "per_seat",
    "usage": "usage", "usage_based": "usage", "usage-based": "usage", "metered": "usage",
    "credits": "usage", "outcome": "usage", "per_outcome": "usage",
}


def _text_or_none(value: Any) -> Optional[str]:
    """A short text field, or None for missing values and non-text types."""
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return None
    return cli.to_text(value)


def _billing_unit(raw: Any, where: str, problems: List[str]) -> Optional[str]:
    if cli.is_missing(raw):
        return None
    key = str(raw).strip().lower().replace("-", "_") if isinstance(raw, str) else None
    if key is not None:
        key2 = key.replace("_", " ")
        for candidate in (key, key2):
            if candidate in _BILLING_UNITS:
                return _BILLING_UNITS[candidate]
    problems.append("%s: %r is not a billing unit (use flat, per_seat or usage)" % (where, raw))
    return None


def _normalize_tier(raw: Any, where: str, index: int, problems: List[str],
                    notes: List[str], default_unit: Optional[str]) -> Optional[Dict[str, Any]]:
    """One tier as a dict with every pricing field normalized."""
    default_name = "Tier %d" % (index + 1)
    if isinstance(raw, dict):
        tier_raw = raw
    elif raw is None or (isinstance(raw, (int, float, str)) and not isinstance(raw, bool)):
        tier_raw = {"price": raw}
    else:
        problems.append(
            '%s: expected a tier object like {"name": "Pro", "price": 29} or a price, got %s'
            % (where, type(raw).__name__)
        )
        return None

    name = tier_raw.get("name") or tier_raw.get("tier") or tier_raw.get("plan")
    name = str(name).strip() if name is not None else ""
    before = len(problems)

    annual = _annual_monthly(tier_raw, where, problems, notes)
    monthly_billing = True
    if "price" not in tier_raw:
        if annual is not None:
            price, custom, monthly_billing = None, False, False
        else:
            problems.append("%s.price is missing - %s" % (where, _PRICE_HINT))
            return None
    else:
        try:
            price, custom = _parse_price(tier_raw.get("price"), where + ".price")
        except ValueError as exc:
            problems.append(str(exc))
            return None
    if custom:
        annual = None

    unit = _billing_unit(tier_raw.get("billing_unit"), where + ".billing_unit", problems)
    unit_source = "input"
    if unit is None and tier_raw.get("per_seat") is not None:
        try:
            unit = "per_seat" if cli.to_bool(tier_raw.get("per_seat"), where + ".per_seat") else "flat"
        except cli.CoercionError as exc:
            problems.append(str(exc))
    if unit is None and isinstance(tier_raw.get("price"), str) and _PER_SEAT_HINT_RE.search(tier_raw["price"]):
        unit, unit_source = "per_seat", "price_text"
    if unit is None and default_unit:
        unit, unit_source = default_unit, "company_default"
    if unit is None:
        unit, unit_source = "flat", "assumed"

    tier = {
        "name": name or default_name,
        "price_monthly": price,
        "price_annual_monthly": annual,
        "monthly_billing": monthly_billing,
        "custom_price": custom,
        "billing_unit": unit,
        "billing_unit_source": unit_source,
        "seat_min": _optional_int(tier_raw.get("seat_min"), where + ".seat_min", problems),
        "seat_max": _optional_int(tier_raw.get("seat_max"), where + ".seat_max", problems),
        "included_seats": _optional_int(tier_raw.get("included_seats"), where + ".included_seats", problems),
        "extra_seat_price": _optional_number(tier_raw.get("extra_seat_price"), where + ".extra_seat_price", problems),
        "platform_fee": _optional_number(tier_raw.get("platform_fee"), where + ".platform_fee", problems),
        "included_usage": _optional_number(tier_raw.get("included_usage"), where + ".included_usage", problems),
        "usage_per_seat": False,
        "usage_unit": _text_or_none(tier_raw.get("usage_unit")),
        "overage_price": _optional_number(tier_raw.get("overage_price"), where + ".overage_price", problems),
        "overage_unit_size": _optional_number(tier_raw.get("overage_unit_size"), where + ".overage_unit_size", problems),
        "badge": _text_or_none(tier_raw.get("badge")),
        "self_serve": None,
        "features_raw": _normalize_features(tier_raw.get("features"), where + ".features", problems),
        "source": _text_or_none(tier_raw.get("source")),
    }
    if tier_raw.get("usage_per_seat") is not None:
        try:
            tier["usage_per_seat"] = bool(cli.to_bool(tier_raw.get("usage_per_seat"), where + ".usage_per_seat"))
        except cli.CoercionError as exc:
            problems.append(str(exc))
    if tier_raw.get("self_serve") is not None:
        try:
            tier["self_serve"] = cli.to_bool(tier_raw.get("self_serve"), where + ".self_serve")
        except cli.CoercionError as exc:
            problems.append(str(exc))
    if tier["self_serve"] is None:
        tier["self_serve"] = not custom
    if tier["overage_unit_size"] == 0:
        problems.append("%s.overage_unit_size must be greater than 0" % where)
    if (tier["seat_min"] and tier["seat_max"] and tier["seat_min"] > tier["seat_max"]):
        problems.append("%s: seat_min %s is above seat_max %s" % (where, tier["seat_min"], tier["seat_max"]))
    if len(problems) > before:
        return None
    if price is not None and annual is not None and price > 0:
        tier["annual_discount_pct"] = round((1 - annual / price) * 100, 1)
        if annual > price:
            notes.append("%s: annual_price %s is above the monthly price %s; check the input."
                         % (where, annual, price))
    else:
        tier["annual_discount_pct"] = None
    tier["is_free"] = (price == 0 and not custom and not tier["platform_fee"]
                       and not (tier["overage_price"] and tier["billing_unit"] == "usage"))
    return tier


def _ladder_sort_key(tier: Dict[str, Any]) -> Tuple[int, float]:
    if tier["custom_price"]:
        return (1, 0.0)
    price = tier["price_monthly"] if tier["price_monthly"] is not None else tier["price_annual_monthly"]
    return (0, float(price or 0) + float(tier.get("platform_fee") or 0))


def normalize_company(raw: Any, where: str, is_own: bool, problems: List[str],
                      notes: List[str]) -> Optional[Dict[str, Any]]:
    """A company: {company, tiers, ...} (own pricing or a competitor)."""
    if isinstance(raw, list):
        raw = {"tiers": raw}
    if not isinstance(raw, dict):
        problems.append('%s: expected an object like {"company": "Acme", "tiers": [...]}' % where)
        return None
    name = raw.get("company") or raw.get("name") or raw.get("product")
    name = str(name).strip() if name else ("Your product" if is_own else where)
    default_unit = _billing_unit(raw.get("billing_unit"), where + ".billing_unit", problems)
    if raw.get("tiers") is not None:
        tiers_raw, key = raw["tiers"], "tiers"
    else:
        tiers_raw, key = raw.get("prices"), "prices"
    if tiers_raw is None:
        if is_own:
            problems.append('tiers: missing - add a "tiers" list with at least one tier')
        else:
            notes.append("Competitor '%s' has no 'tiers' or 'prices' - skipped." % name)
        return None
    if isinstance(tiers_raw, dict):
        tiers_raw = [dict(v, name=v.get("name") or k) if isinstance(v, dict) else {"name": k, "price": v}
                     for k, v in tiers_raw.items()]
    if not isinstance(tiers_raw, list):
        problems.append("%s.%s: expected a list of tiers, got %s" % (where, key, type(tiers_raw).__name__))
        return None
    before = len(problems)
    tiers = []
    for i, item in enumerate(tiers_raw):
        tier = _normalize_tier(item, "%s.%s[%d]" % (where, key, i), i, problems, notes, default_unit)
        if tier is not None:
            tiers.append(tier)
    if len(problems) > before:
        return None
    if not tiers:
        if is_own:
            problems.append("tiers: the list is empty - add at least one tier")
        else:
            notes.append("Competitor '%s' has no tiers - skipped." % name)
        return None
    names_seen: Dict[str, int] = {}
    for tier in tiers:
        key_name = _name_key(tier["name"])
        names_seen[key_name] = names_seen.get(key_name, 0) + 1
        if names_seen[key_name] > 1:
            tier["name"] = "%s (%d)" % (tier["name"], names_seen[key_name])
    tiers.sort(key=_ladder_sort_key)  # stable: equal prices keep input order
    for position, tier in enumerate(tiers):
        tier["position"] = position + 1
    if not is_own and not any(not t["custom_price"] for t in tiers):
        notes.append("Competitor '%s' has no published price (all tiers custom); it is listed "
                     "but has no costs in the matrix." % name)
    expand_features(tiers, notes, name)
    assumed = [t["name"] for t in tiers if t["billing_unit_source"] == "assumed" and not t["custom_price"]
               and not t["is_free"]]
    if assumed:
        notes.append("%s: billing_unit not given for %s; treated as flat (per account). Set billing_unit "
                     "to per_seat if the price is per user." % (name, ", ".join(assumed)))
    observed = raw.get("observed") or raw.get("observed_on")
    return {
        "company": name,
        "own": is_own,
        "url": raw.get("url") if isinstance(raw.get("url"), str) else None,
        "observed": str(observed) if observed else None,
        "currency": str(raw.get("currency")).upper() if raw.get("currency") else None,
        "tiers": tiers,
    }


# ---------------------------------------------------------------------------
# Cost at scenario
# ---------------------------------------------------------------------------

def _scenarios(raw: Any, extra_seats: Optional[float], problems: List[str]) -> List[Dict[str, Any]]:
    """Scenarios as [{"id", "label", "seats", "usage"}]."""
    out: List[Dict[str, Any]] = []

    def add(seats: Any, usage: Any, label: Any, where: str) -> None:
        seat_value = _optional_number(seats, where + ".seats", problems) if seats is not None else 1
        usage_value = _optional_number(usage, where + ".usage", problems) if usage is not None else None
        if seat_value is None:
            return
        if seat_value < 1 or not float(seat_value).is_integer():
            problems.append("%s.seats must be a whole number of at least 1, got %r" % (where, seats))
            return
        seat_value = int(seat_value)
        text = str(label).strip() if label else (
            "%d seat%s" % (seat_value, "" if seat_value == 1 else "s")
            + ("" if usage_value is None else ", %s usage" % _fmt_num(usage_value)))
        out.append({"label": text, "seats": seat_value, "usage": usage_value})

    if raw is None:
        for seats in DEFAULT_SEAT_SCENARIOS:
            add(seats, None, None, "scenarios")
    elif isinstance(raw, list):
        for i, item in enumerate(raw):
            if isinstance(item, dict):
                add(item.get("seats", 1), item.get("usage"), item.get("label"), "scenarios[%d]" % i)
            else:
                add(item, None, None, "scenarios[%d]" % i)
    elif isinstance(raw, dict):
        seats_list = raw.get("seats") or [1]
        usage_list = raw.get("usage") or [None]
        if not isinstance(seats_list, list):
            seats_list = [seats_list]
        if not isinstance(usage_list, list):
            usage_list = [usage_list]
        for s in seats_list:
            for u in usage_list:
                add(s, u, None, "scenarios")
    else:
        problems.append("scenarios: expected a list of seat counts or scenario objects")
    if extra_seats:
        seats = int(round(extra_seats))
        if seats >= 1 and not any(s["seats"] == seats and s["usage"] is None for s in out):
            out.append({"label": "your average account (%d seats)" % seats, "seats": seats, "usage": None})
    if len(out) > MAX_SCENARIOS:
        problems.append("scenarios: %d scenarios given; at most %d" % (len(out), MAX_SCENARIOS))
    for i, scenario in enumerate(out):
        scenario["id"] = "s%d" % (i + 1)
    return out


def tier_cost(tier: Dict[str, Any], seats: int, usage: Optional[float],
              annual: bool = False) -> Tuple[Optional[float], Optional[str]]:
    """Monthly cost of one tier for a scenario. Returns (cost, status).

    status is None for a priced result, else one of: custom (contact sales),
    no_annual_price, monthly_not_offered, over_seat_cap, usage_over_allowance
    (no overage price), usage_not_given (the cost excludes usage charges).
    """
    if tier["custom_price"]:
        return None, "custom"
    unit_price = tier["price_annual_monthly"] if annual else tier["price_monthly"]
    if unit_price is None:
        return None, "no_annual_price" if annual else "monthly_not_offered"
    if tier["seat_max"] is not None and seats > tier["seat_max"]:
        return None, "over_seat_cap"
    unit = tier["billing_unit"]
    cost = float(tier["platform_fee"] or 0)
    if unit == "per_seat":
        cost += unit_price * max(seats, tier["seat_min"] or 1)
    else:
        cost += unit_price
        if unit == "flat" and tier["included_seats"] is not None and seats > tier["included_seats"]:
            if tier["extra_seat_price"] is None:
                return None, "over_seat_cap"
            cost += (seats - tier["included_seats"]) * tier["extra_seat_price"]
    status = None
    has_usage_pricing = tier["included_usage"] is not None or tier["overage_price"] is not None
    if has_usage_pricing:
        if usage is None:
            status = "usage_not_given"
        else:
            allowance = (tier["included_usage"] or 0) * (seats if tier["usage_per_seat"] else 1)
            over = max(0.0, usage - allowance)
            if over > 0:
                if tier["overage_price"] is None:
                    return None, "usage_over_allowance"
                size = tier["overage_unit_size"] or 1
                cost += math.ceil(over / size - 1e-9) * tier["overage_price"]
    return round(cost, 2), status


def _cheapest(company: Dict[str, Any], scenario: Dict[str, Any], annual: bool,
              paid_only: bool = True, tier_filter: Optional[set] = None) -> Optional[Dict[str, Any]]:
    best = None
    for tier in company["tiers"]:
        if tier_filter is not None and tier["name"] not in tier_filter:
            continue
        if paid_only and tier["is_free"]:
            continue
        cost, status = tier_cost(tier, scenario["seats"], scenario["usage"], annual)
        if cost is None:
            continue
        if paid_only and cost == 0:
            continue
        if best is None or cost < best["cost"]:
            best = {"tier": tier["name"], "cost": cost, "status": status}
    return best


def _pct_diff(own: Optional[float], other: Optional[float]) -> Optional[float]:
    if own is None or other is None or other == 0:
        return None
    return round((own - other) / other * 100, 1)


def cost_matrix(companies: List[Dict[str, Any]], scenarios: List[Dict[str, Any]],
                tier_map: List[Dict[str, Any]], gates: Dict[str, Any]) -> Dict[str, Any]:
    """Monthly cost of every tier at every scenario, plus own-vs-competitor comparisons."""
    rows = []
    for company in companies:
        tiers = []
        for tier in company["tiers"]:
            monthly, annual, status = [], [], []
            for scenario in scenarios:
                m_cost, m_status = tier_cost(tier, scenario["seats"], scenario["usage"], False)
                a_cost, a_status = tier_cost(tier, scenario["seats"], scenario["usage"], True)
                monthly.append(m_cost)
                annual.append(a_cost)
                status.append(m_status or a_status)
            tiers.append({"tier": tier["name"], "monthly_billing": monthly, "annual_billing": annual,
                          "status": status})
        rows.append({"company": company["company"], "own": company["own"], "tiers": tiers})

    own = companies[0]
    competitors = companies[1:]
    by_scenario = []
    for scenario in scenarios:
        entry: Dict[str, Any] = {"scenario": scenario["id"], "label": scenario["label"],
                                 "cheapest_paid": []}
        for company in companies:
            m = _cheapest(company, scenario, annual=False)
            a = _cheapest(company, scenario, annual=True)
            entry["cheapest_paid"].append({
                "company": company["company"],
                "monthly_billing": m,
                "annual_billing": a,
            })
        ranked = sorted((c for c in entry["cheapest_paid"] if c["monthly_billing"]),
                        key=lambda c: c["monthly_billing"]["cost"])
        entry["rank_monthly_billing"] = [c["company"] for c in ranked]
        own_m = entry["cheapest_paid"][0]["monthly_billing"]
        own_a = entry["cheapest_paid"][0]["annual_billing"]
        entry["own_vs"] = []
        for i, company in enumerate(competitors, start=1):
            comp = entry["cheapest_paid"][i]
            entry["own_vs"].append({
                "company": company["company"],
                "monthly_billing_diff_pct": _pct_diff(own_m["cost"] if own_m else None,
                                                      comp["monthly_billing"]["cost"] if comp["monthly_billing"] else None),
                "annual_billing_diff_pct": _pct_diff(own_a["cost"] if own_a else None,
                                                     comp["annual_billing"]["cost"] if comp["annual_billing"] else None),
            })
        by_scenario.append(entry)

    matched = []
    for pair in tier_map:
        label = pair.get("label")
        mapping = pair.get("tiers", {})
        mapping_ci = {str(k).lower(): v for k, v in mapping.items()}
        result = {"label": label, "tiers": mapping, "by_scenario": []}
        for scenario in scenarios:
            costs = {}
            for company in companies:
                tier_name = mapping.get(company["company"]) or mapping_ci.get(company["company"].lower())
                tier = next((t for t in company["tiers"] if tier_name and _name_key(t["name"]) == _name_key(tier_name)), None)
                if tier is None:
                    costs[company["company"]] = {"monthly_billing": None, "annual_billing": None,
                                                 "status": "tier_not_found" if tier_name else "not_mapped"}
                    continue
                m_cost, m_status = tier_cost(tier, scenario["seats"], scenario["usage"], False)
                a_cost, a_status = tier_cost(tier, scenario["seats"], scenario["usage"], True)
                costs[company["company"]] = {"monthly_billing": m_cost, "annual_billing": a_cost,
                                             "status": m_status or a_status}
            own_cost = costs.get(own["company"], {}).get("monthly_billing")
            diffs = {name: _pct_diff(own_cost, value.get("monthly_billing"))
                     for name, value in costs.items() if name != own["company"]}
            result["by_scenario"].append({"scenario": scenario["id"], "costs": costs,
                                          "own_monthly_billing_diff_pct": diffs})
        matched.append(result)

    gate_rows = []
    for keyword_set in gates.get("sets", []):
        row = {"requires": keyword_set, "companies": []}
        for company in companies:
            allowed = set()
            for tier in company["tiers"]:
                if all(gates["first_tier"][company["company"]].get(k) and
                       tier["position"] >= gates["first_tier"][company["company"]][k]["position"]
                       for k in keyword_set):
                    allowed.add(tier["name"])
            costs = []
            for scenario in scenarios:
                m = _cheapest(company, scenario, annual=False, paid_only=False, tier_filter=allowed)
                costs.append(m)
            row["companies"].append({"company": company["company"],
                                     "eligible_tiers": [t["name"] for t in company["tiers"] if t["name"] in allowed],
                                     "cheapest_monthly_billing": costs})
        gate_rows.append(row)

    return {"rows": rows, "by_scenario": by_scenario, "tier_map": matched, "feature_gate_costs": gate_rows}


def feature_gates(companies: List[Dict[str, Any]], keywords: List[str]) -> Dict[str, Any]:
    """First tier (in ladder order) whose features include each keyword."""
    first: Dict[str, Dict[str, Any]] = {}
    table = []
    for company in companies:
        first[company["company"]] = {}
        for keyword in keywords:
            needle = re.compile(r"(?<![a-z0-9])%s(?![a-z0-9])" % re.escape(keyword.lower()), re.IGNORECASE)
            hit = None
            for tier in company["tiers"]:
                for feature in tier["features_all"]:
                    if needle.search(feature):
                        hit = {"tier": tier["name"], "position": tier["position"], "matched": feature,
                               "custom_price": tier["custom_price"]}
                        break
                if hit:
                    break
            first[company["company"]][keyword] = hit
        table.append({"company": company["company"],
                      "first_tier": {k: (v and {kk: v[kk] for kk in ("tier", "matched", "custom_price")})
                                     for k, v in first[company["company"]].items()}})
    return {"keywords": keywords, "by_company": table, "first_tier": first}


# ---------------------------------------------------------------------------
# Benchmarks (read from references/_shared/saas-benchmarks.json)
# ---------------------------------------------------------------------------

def load_benchmarks(path: Path = BENCHMARKS_PATH) -> Optional[Dict[str, Any]]:
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return None
    return {row["id"]: row for row in data.get("rows", []) if isinstance(row, dict) and row.get("id")}


def _bench_ref(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": row["id"], "source": row.get("source_name"), "year": row.get("year"),
        "url": row.get("source_url"), "window": row.get("window"),
        "thresholds": row.get("thresholds"), "mean": row.get("mean"), "median": row.get("median"),
        "verified": row.get("verified"), "verified_on": row.get("verified_on"),
        "value_note": row.get("value_note"),
    }


# ---------------------------------------------------------------------------
# Business metrics -> facts and flags
# ---------------------------------------------------------------------------

def _shares(raw: Any, where: str, problems: List[str]) -> Optional[Dict[str, float]]:
    """{'Pro': 70, 'Team': 30} (counts or percents) -> shares that sum to 1."""
    if raw is None:
        return None
    if not isinstance(raw, dict):
        problems.append("%s: expected an object like {\"Pro\": 70, \"Team\": 30}" % where)
        return None
    values = {}
    for key, value in raw.items():
        number = None
        try:
            number = cli.to_number(value, field="%s.%s" % (where, key), minimum=0)
        except cli.CoercionError as exc:
            problems.append(str(exc))
        if number is not None:
            values[str(key)] = number
    total = sum(values.values())
    if not values or total <= 0:
        problems.append("%s: no positive values" % where)
        return None
    return {k: v / total for k, v in values.items()}


def _find_tier(company: Dict[str, Any], name: str) -> Optional[Dict[str, Any]]:
    key = _name_key(name)
    return next((t for t in company["tiers"] if _name_key(t["name"]) == key), None)


def _flag(flags: List[Dict[str, Any]], flag_id: str, severity: str, fact: str,
          rule: str, basis: str, data: Optional[Dict[str, Any]] = None) -> None:
    flags.append({"id": flag_id, "severity": severity, "fact": fact, "rule": rule, "basis": basis,
                  "data": data or {}})


METRIC_SCHEMA = {
    "paying_customers": "number", "mrr": "number", "arpa_monthly": "number",
    "annual_share_pct": "percent", "avg_discount_pct": "percent", "free_to_paid_pct": "percent",
    "avg_seats_per_account": "number", "gross_margin_pct": "percent",
    "target_gross_margin_pct": "percent", "cost_per_usage_unit": "number",
    "monthly_logo_churn_pct": "percent",
}


def business_facts(own: Dict[str, Any], metrics_raw: Dict[str, Any], context: Dict[str, Any],
                   problems: List[str], notes: List[str],
                   benchmarks: Optional[Dict[str, Any]]) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Facts from the user's business metrics, and flags with severity."""
    flags: List[Dict[str, Any]] = []
    facts: Dict[str, Any] = {}
    metrics: Dict[str, Any] = {}
    for key, kind in METRIC_SCHEMA.items():
        raw = metrics_raw.get(key)
        try:
            if kind == "percent":
                metrics[key] = cli.to_percent(raw, field="metrics." + key, minimum=0, maximum=100)
            else:
                metrics[key] = cli.to_number(raw, field="metrics." + key, minimum=0)
        except cli.CoercionError as exc:
            problems.append(str(exc))
            metrics[key] = None
    tier_mix = _shares(metrics_raw.get("tier_mix"), "metrics.tier_mix", problems)
    mrr_by_tier = _shares(metrics_raw.get("mrr_by_tier"), "metrics.mrr_by_tier", problems)
    expansion = _shares(metrics_raw.get("expansion_source"), "metrics.expansion_source", problems)
    ladder = own["tiers"]
    paid = [t for t in ladder if not t["is_free"] and not t["custom_price"]]
    entry_paid = paid[0] if paid else None
    top_self_serve = paid[-1] if paid else None

    # Unknown tier names in the mix are an input error worth naming.
    for label, mix in (("tier_mix", tier_mix), ("mrr_by_tier", mrr_by_tier)):
        if mix:
            unknown = [name for name in mix if _find_tier(own, name) is None]
            if unknown:
                problems.append("metrics.%s: unknown tier name(s) %s (tiers are: %s)"
                                % (label, ", ".join(unknown), ", ".join(t["name"] for t in ladder)))
    if problems:
        return facts, flags

    arpa = metrics["arpa_monthly"]
    if arpa is None and metrics["mrr"] and metrics["paying_customers"]:
        arpa = metrics["mrr"] / metrics["paying_customers"]
        facts["arpa_monthly_derived"] = True
    facts["arpa_monthly"] = round(arpa, 2) if arpa is not None else None
    for key in ("paying_customers", "mrr", "annual_share_pct", "avg_discount_pct", "free_to_paid_pct",
                "avg_seats_per_account", "gross_margin_pct", "target_gross_margin_pct"):
        facts[key] = metrics[key]
    facts["annual_share_basis"] = metrics_raw.get("annual_share_basis") or ("customers" if metrics["annual_share_pct"] is not None else None)

    if tier_mix:
        paid_mix = {}
        for name, share in tier_mix.items():
            tier = _find_tier(own, name)
            if tier and not tier["is_free"]:
                paid_mix[tier["name"]] = paid_mix.get(tier["name"], 0) + share
        total_paid = sum(paid_mix.values())
        shares = {k: round(v / total_paid, 4) for k, v in paid_mix.items()} if total_paid else {}
        facts["paid_tier_mix"] = shares
        if shares:
            most = max(shares, key=lambda k: shares[k])
            facts["most_popular_paid_tier"] = most
            if entry_paid is not None:
                entry_share = shares.get(entry_paid["name"], 0.0)
                facts["entry_paid_tier"] = entry_paid["name"]
                facts["entry_paid_tier_share"] = entry_share
                if entry_share > 0.5 and len(paid) > 1:
                    _flag(flags, "entry_tier_majority", "medium",
                          "%.0f%% of paying customers are on the cheapest paid tier (%s)."
                          % (entry_share * 100, entry_paid["name"]),
                          "More than half of paying customers on the entry paid tier: check whether the "
                          "fence to the next tier is too low or the entry tier gives away the value "
                          "most customers pay for.",
                          "arithmetic on the user's tier mix (majority rule)",
                          {"tier": entry_paid["name"], "share": entry_share})
            if top_self_serve is not None and top_self_serve is not entry_paid:
                top_share = shares.get(top_self_serve["name"], 0.0)
                facts["top_self_serve_tier"] = top_self_serve["name"]
                facts["top_self_serve_tier_share"] = top_share
                _flag(flags, "top_self_serve_share", "info",
                      "%.0f%% of paying customers are on the most expensive self-serve tier (%s)."
                      % (top_share * 100, top_self_serve["name"]),
                      "Context for anchoring: a small share is normal for an anchor tier; judge it with "
                      "the rubric, not as a problem by itself.",
                      "arithmetic on the user's tier mix", {"tier": top_self_serve["name"], "share": top_share})
            if most == (entry_paid or {}).get("name") and len(paid) > 1:
                _flag(flags, "most_popular_is_entry", "low",
                      "The most common paid tier is the cheapest one (%s)." % most,
                      "Compare with the tier the pricing page highlights as recommended.",
                      "arithmetic on the user's tier mix", {"tier": most})
    if mrr_by_tier:
        facts["mrr_share_by_tier"] = {(_find_tier(own, k) or {"name": k})["name"]: round(v, 4)
                                      for k, v in mrr_by_tier.items()}
    if expansion:
        facts["expansion_source_share"] = {k: round(v, 4) for k, v in expansion.items()}

    # ARPA vs list price: implied seats per account or discount leakage.
    if arpa is not None and tier_mix and paid:
        weights = []
        for name, share in (facts.get("paid_tier_mix") or {}).items():
            tier = _find_tier(own, name)
            if tier is not None and tier["price_monthly"] is not None:
                weights.append((tier, share))
        units = {t["billing_unit"] for t, _ in weights}
        if weights and units == {"per_seat"}:
            per_seat = sum(t["price_monthly"] * s for t, s in weights) / sum(s for _, s in weights)
            per_seat_annual = None
            if all(t["price_annual_monthly"] is not None for t, _ in weights):
                per_seat_annual = sum(t["price_annual_monthly"] * s for t, s in weights) / sum(s for _, s in weights)
            facts["mix_weighted_list_price_per_seat"] = round(per_seat, 2)
            facts["implied_seats_per_account"] = round(arpa / per_seat, 2) if per_seat else None
            if per_seat_annual:
                facts["implied_seats_per_account_if_all_annual"] = round(arpa / per_seat_annual, 2)
            if metrics["avg_seats_per_account"]:
                expected = per_seat * metrics["avg_seats_per_account"]
                facts["implied_discount_vs_list_pct"] = round((1 - arpa / expected) * 100, 1) if expected else None
        elif weights and units == {"flat"}:
            list_avg = sum(t["price_monthly"] * s for t, s in weights) / sum(s for _, s in weights)
            facts["mix_weighted_list_price"] = round(list_avg, 2)
            facts["implied_discount_vs_list_pct"] = round((1 - arpa / list_avg) * 100, 1) if list_avg else None
        elif weights:
            notes.append("ARPA vs list price skipped: the paid tiers mix billing units (%s)." % ", ".join(sorted(units)))
        implied = facts.get("implied_discount_vs_list_pct")
        max_annual = max([t["annual_discount_pct"] for t in ladder if t["annual_discount_pct"] is not None] or [0])
        if implied is not None and implied > max_annual:
            _flag(flags, "discount_beyond_annual", "medium",
                  "ARPA is %.1f%% below the mix-weighted list price, more than the largest annual "
                  "discount offered (%.1f%%)." % (implied, max_annual),
                  "Revenue per account below list by more than the annual discount points to "
                  "discounting, promotions or legacy prices; ask where it comes from.",
                  "arithmetic: ARPA vs the user's own list prices and tier mix",
                  {"implied_discount_pct": implied, "max_annual_discount_pct": max_annual})
        if implied is not None and implied < -5:
            notes.append("ARPA is above the mix-weighted list price: add-ons, usage, extra seats or "
                         "price changes may explain it.")

    # Annual billing.
    annual_tiers = [t for t in ladder if t["annual_discount_pct"] is not None]
    facts["annual_discount_pct_by_tier"] = {t["name"]: t["annual_discount_pct"] for t in annual_tiers}
    if paid and not annual_tiers and not any(not t["monthly_billing"] for t in paid):
        _flag(flags, "no_annual_option", "low",
              "No paid tier in the input has an annual price.",
              "Confirm whether annual billing exists; if not, it is a candidate lever for cash flow "
              "and retention (judge with the annual_discounting dimension).",
              "input completeness")

    # Seat minimums and caps.
    seat_rules = [{"tier": t["name"], "seat_min": t["seat_min"], "seat_max": t["seat_max"]}
                  for t in ladder if (t["seat_min"] or 0) > 1 or t["seat_max"]]
    if seat_rules:
        facts["seat_rules"] = seat_rules

    # Free-to-paid vs the shared benchmark file.
    f2p = metrics["free_to_paid_pct"]
    offer = (context.get("free_offer") or "").replace("-", "_").lower()
    motion = (context.get("gtm_motion") or "").lower()
    if f2p is not None:
        if benchmarks is None:
            notes.append("Benchmark file not found; free-to-paid is reported without a comparison.")
        else:
            row_id = None
            if offer in ("freemium",):
                row_id = ("free_to_paid.lenny2023.freemium_sales_assist" if motion in ("sales-led", "hybrid")
                          else "free_to_paid.lenny2023.freemium_self_serve")
            elif offer in ("free_trial", "reverse_trial"):
                row_id = "free_to_paid.lenny2023.free_trial"
            row = benchmarks.get(row_id) if row_id else None
            if row is None:
                notes.append("free_to_paid_pct given without free_offer (freemium or free-trial); "
                             "no benchmark row chosen.")
            else:
                ref = _bench_ref(row)
                facts["free_to_paid_benchmark"] = ref
                good = next((t for t in (row.get("thresholds") or []) if t.get("label") == "good"), None)
                great = next((t for t in (row.get("thresholds") or []) if t.get("label") == "great"), None)
                window = metrics_raw.get("free_to_paid_window")
                basis = "benchmark:%s (%s %s)" % (row["id"], row.get("source_name"), row.get("year"))
                if good and f2p < good["min"]:
                    _flag(flags, "free_to_paid_below_benchmark", "medium",
                          "Free-to-paid %.1f%% is below the %s-%s%% 'good' band." % (f2p, good["min"], good["max"]),
                          "Rule of thumb, not a percentile. Check the window matches (%s; yours: %s)."
                          % (row.get("window"), window or "not given"), basis, {"value": f2p})
                elif great and f2p >= great["min"]:
                    _flag(flags, "free_to_paid_great", "info",
                          "Free-to-paid %.1f%% is in or above the %s-%s%% 'great' band." % (f2p, great["min"], great["max"]),
                          "Rule of thumb, not a percentile; check the window matches.", basis, {"value": f2p})
                elif good:
                    _flag(flags, "free_to_paid_good", "info",
                          "Free-to-paid %.1f%% is at or above the %s%% 'good' threshold." % (f2p, good["min"]),
                          "Rule of thumb, not a percentile; check the window matches.", basis, {"value": f2p})

    # Cost to serve for usage allowances (AI credits, outcomes, API calls).
    unit_cost = metrics["cost_per_usage_unit"]
    target = metrics["target_gross_margin_pct"]
    margins = []
    if unit_cost is not None:
        for tier in ladder:
            if tier["custom_price"]:
                continue
            row: Dict[str, Any] = {"tier": tier["name"]}
            if tier["included_usage"] is not None and tier["price_monthly"] is not None:
                seats = 1
                allowance = tier["included_usage"] * (seats if tier["usage_per_seat"] else 1)
                revenue = tier["price_monthly"] * (1 if tier["billing_unit"] != "per_seat" else seats) + (tier["platform_fee"] or 0)
                cost = allowance * unit_cost
                row.update({"included_usage": allowance, "cost_at_full_allowance": round(cost, 4),
                            "revenue": revenue,
                            "margin_at_full_allowance_pct": round((revenue - cost) / revenue * 100, 1) if revenue else None,
                            "basis": "1 seat" if tier["usage_per_seat"] else "per account"})
                margin = row["margin_at_full_allowance_pct"]
                if revenue and cost > revenue:
                    _flag(flags, "negative_margin_at_full_allowance", "high",
                          "%s: a customer who uses the full allowance costs %s to serve vs %s revenue."
                          % (tier["name"], _fmt_num(round(cost, 2)), _fmt_num(revenue)),
                          "Included usage worth more than the price loses money on heavy users.",
                          "arithmetic on the user's cost_per_usage_unit", {"tier": tier["name"]})
                elif margin is not None and target is not None and margin < target:
                    _flag(flags, "margin_below_target", "medium",
                          "%s: margin at full allowance is %.1f%%, below the %.1f%% target."
                          % (tier["name"], margin, target),
                          "Heavy users push margin below the user's own target.",
                          "arithmetic vs the user's target_gross_margin_pct", {"tier": tier["name"]})
                elif revenue == 0 and cost > 0:
                    _flag(flags, "free_allowance_cost", "info",
                          "%s: the free allowance costs up to %s per account per month to serve."
                          % (tier["name"], _fmt_num(round(cost, 2))),
                          "Budget free usage as acquisition cost.", "arithmetic", {"tier": tier["name"]})
            if tier["overage_price"] is not None:
                size = tier["overage_unit_size"] or 1
                per_unit = tier["overage_price"] / size
                row["overage_price_per_unit"] = round(per_unit, 6)
                row["overage_margin_pct"] = round((per_unit - unit_cost) / per_unit * 100, 1) if per_unit else None
                if per_unit < unit_cost:
                    _flag(flags, "overage_below_cost", "high",
                          "%s: overage price per unit (%s) is below the cost per unit (%s)."
                          % (tier["name"], _fmt_num(per_unit), _fmt_num(unit_cost)),
                          "Every overage unit loses money.", "arithmetic on the user's cost_per_usage_unit",
                          {"tier": tier["name"]})
            if len(row) > 1:
                margins.append(row)
        facts["cost_to_serve"] = margins
    elif any(t["included_usage"] is not None or t["overage_price"] is not None for t in ladder):
        notes.append("Usage allowances found but metrics.cost_per_usage_unit is missing: cost-to-serve "
                     "and margin floor not measured.")
    return facts, flags


# ---------------------------------------------------------------------------
# facts command
# ---------------------------------------------------------------------------

def _structure_facts(company: Dict[str, Any]) -> Dict[str, Any]:
    tiers = company["tiers"]
    priced = [t for t in tiers if not t["custom_price"]]
    paid = [t for t in priced if not t["is_free"]]
    ratios = []
    for low, high in zip(paid, paid[1:]):
        lp = low["price_monthly"] if low["price_monthly"] is not None else low["price_annual_monthly"]
        hp = high["price_monthly"] if high["price_monthly"] is not None else high["price_annual_monthly"]
        if lp and hp is not None and low["billing_unit"] == high["billing_unit"]:
            ratios.append({"from": low["name"], "to": high["name"], "ratio": round(hp / lp, 2)})
        else:
            ratios.append({"from": low["name"], "to": high["name"], "ratio": None,
                           "why_none": "different billing units" if low["billing_unit"] != high["billing_unit"] else "no price"})
    return {
        "tier_count": len(tiers),
        "paid_self_serve_tiers": len(paid),
        "has_free_tier": any(t["is_free"] for t in tiers),
        "has_custom_tier": any(t["custom_price"] for t in tiers),
        "billing_units": sorted({t["billing_unit"] for t in priced if not t["is_free"]}),
        "price_ratios_between_paid_tiers": ratios,
        "badged_tiers": [{"tier": t["name"], "badge": t["badge"]} for t in tiers if t["badge"]],
        "annual_billing_offered": any(t["price_annual_monthly"] is not None for t in paid),
        "self_serve_seat_ceiling": _seat_ceiling(paid),
    }


def _seat_ceiling(paid: List[Dict[str, Any]]) -> Optional[int]:
    """Largest seat count a self-serve tier allows (None = no cap in the input)."""
    if not paid:
        return None
    caps = []
    for tier in paid:
        if tier["seat_max"] is None and not (tier["billing_unit"] == "flat" and tier["included_seats"] is not None
                                               and tier["extra_seat_price"] is None):
            return None
        caps.append(tier["seat_max"] if tier["seat_max"] is not None else tier["included_seats"])
    return max(caps)


def _public_tier(tier: Dict[str, Any]) -> Dict[str, Any]:
    keys = ("position", "name", "price_monthly", "price_annual_monthly", "annual_discount_pct",
            "monthly_billing", "custom_price", "is_free", "self_serve", "billing_unit",
            "billing_unit_source", "seat_min", "seat_max", "included_seats", "extra_seat_price",
            "platform_fee", "included_usage", "usage_per_seat", "usage_unit", "overage_price",
            "overage_unit_size", "badge", "source", "inherits_from", "compared_with",
            "features_listed", "added", "removed", "limit_changes")
    out = {k: tier.get(k) for k in keys}
    out["feature_count_all"] = len(tier.get("features_all") or [])
    if out.get("features_listed") == out.get("added"):
        out.pop("features_listed")
    if out.get("monthly_billing") is True:
        out.pop("monthly_billing")
    if out.get("self_serve") == (not tier["custom_price"]):
        out.pop("self_serve")
    always = ("price_monthly", "custom_price", "is_free", "billing_unit", "added", "feature_count_all")
    return {k: v for k, v in out.items()
            if k in always or not (v is None or v is False or (isinstance(v, list) and not v))}


def analyze_facts(payload: Dict[str, Any], benchmarks: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """The facts command. Raises PricingInputError listing every bad field."""
    problems: List[str] = []
    notes: List[str] = []
    if not isinstance(payload, dict):
        raise PricingInputError(['the JSON must be an object with a "tiers" list'])
    if "tiers" not in payload and isinstance(payload.get("own"), dict):
        own_raw = payload["own"]
    else:
        own_raw = {k: payload.get(k) for k in ("product", "company", "tiers", "billing_unit", "currency",
                                               "url", "observed") if k in payload}
        if "tiers" not in own_raw:
            own_raw["tiers"] = None
    own = normalize_company(own_raw, "tiers", True, problems, notes)

    competitors: List[Dict[str, Any]] = []
    comps_raw = payload.get("competitors") or payload.get("competitor_pricing")
    if isinstance(comps_raw, dict):
        comps_raw = [{"company": k, "tiers": v} for k, v in comps_raw.items()]
    if comps_raw is not None and not isinstance(comps_raw, list):
        problems.append("competitors: expected a list, got %s" % type(comps_raw).__name__)
        comps_raw = []
    for i, comp in enumerate(comps_raw or []):
        normalized = normalize_company(comp, "competitors[%d]" % i, False, problems, notes)
        if normalized is not None:
            competitors.append(normalized)

    context_raw = payload.get("context") or {}
    if not isinstance(context_raw, dict):
        problems.append("context: expected an object")
        context_raw = {}
    context = dict(context_raw)
    plg = payload.get("plg_motion", context_raw.get("plg_motion"))
    if plg is not None:
        try:
            plg_bool = cli.to_bool(plg, "plg_motion")
        except cli.CoercionError as exc:
            problems.append(str(exc))
            plg_bool = None
        if plg_bool is not None and not context.get("gtm_motion"):
            context["gtm_motion"] = "plg" if plg_bool else "sales-led"
    metrics_raw = payload.get("metrics") or {}
    for legacy, key in (("free_to_paid_pct", "free_to_paid_pct"), ("avg_deal_size", "arpa_monthly")):
        if legacy in payload and key not in metrics_raw:
            metrics_raw = dict(metrics_raw, **{key: payload[legacy]})
            notes.append("Top-level %s read as metrics.%s." % (legacy, key))
    if "most_popular_tier" in payload and "tier_mix" not in metrics_raw:
        notes.append("most_popular_tier is a label, not a tier mix; give metrics.tier_mix "
                     "(customers per tier) for mix facts.")
    if not isinstance(metrics_raw, dict):
        problems.append("metrics: expected an object")
        metrics_raw = {}
    seats_hint = None
    try:
        seats_hint = cli.to_number(metrics_raw.get("avg_seats_per_account"), "metrics.avg_seats_per_account", minimum=0)
    except cli.CoercionError:
        pass  # reported by business_facts
    scenarios = _scenarios(payload.get("scenarios"), seats_hint, problems)

    keywords = payload.get("feature_keywords") or payload.get("match_features") or []
    if isinstance(keywords, str):
        keywords = [keywords]
    if not isinstance(keywords, list) or not all(isinstance(k, str) and k.strip() for k in keywords):
        problems.append("feature_keywords: expected a list of words such as [\"SSO\", \"audit log\"]")
        keywords = []
    keywords = [k.strip() for k in keywords][:12]

    tier_map_raw = payload.get("tier_map") or []
    tier_map: List[Dict[str, Any]] = []
    if not isinstance(tier_map_raw, list):
        problems.append("tier_map: expected a list of {\"label\", \"tiers\": {company: tier}}")
    else:
        for i, item in enumerate(tier_map_raw):
            if not isinstance(item, dict) or not isinstance(item.get("tiers"), dict):
                problems.append("tier_map[%d]: expected {\"label\": ..., \"tiers\": {\"Company\": \"Tier\"}}" % i)
                continue
            tier_map.append({"label": item.get("label") or "map %d" % (i + 1),
                             "tiers": {str(k): str(v) for k, v in item["tiers"].items()}})
    if problems:
        raise PricingInputError(problems)

    companies = [own] + competitors
    for pair in tier_map:
        for company_name in list(pair["tiers"]):
            if company_name not in [c["company"] for c in companies]:
                notes.append("tier_map '%s': company '%s' is not in the input." % (pair["label"], company_name))

    if benchmarks is None:
        benchmarks = load_benchmarks()
    biz, flags = business_facts(own, metrics_raw, context, problems, notes, benchmarks)
    if problems:
        raise PricingInputError(problems)

    gates = feature_gates(companies, keywords) if keywords else {"keywords": [], "by_company": [], "first_tier": {}}
    gate_sets = payload.get("feature_sets") or ([keywords] if len(keywords) > 1 else [[k] for k in keywords])
    gates["sets"] = [s for s in gate_sets if isinstance(s, list) and all(k in keywords for k in s)][:6]
    matrix = cost_matrix(companies, scenarios, tier_map, gates)
    usage_tiers = [c["company"] for c in companies
                   if any(t["included_usage"] is not None or t["overage_price"] is not None for t in c["tiers"])]
    if usage_tiers and all(s["usage"] is None for s in scenarios):
        notes.append("Usage-priced tiers found (%s) but no scenario has a usage value: costs exclude "
                     "usage charges. Add scenarios with usage." % ", ".join(usage_tiers))
    currencies = {c["currency"] for c in companies if c["currency"]}
    if len(currencies) > 1:
        notes.append("Companies use different currencies (%s); the cost matrix does not convert them."
                     % ", ".join(sorted(currencies)))

    for company in companies:
        for tier in company["tiers"]:
            tier.pop("features_raw", None)
    if flags:
        flags.sort(key=lambda f: {"high": 0, "medium": 1, "low": 2, "info": 3}[f["severity"]])
    return {
        "currency": own.get("currency") or payload.get("currency") or context.get("currency"),
        "own": {
            "company": own["company"], "url": own["url"], "observed": own["observed"],
            "structure": _structure_facts(own),
            "tiers": [_public_tier(t) for t in own["tiers"]],
        },
        "competitors": [{
            "company": c["company"], "url": c["url"], "observed": c["observed"],
            "structure": _structure_facts(c),
            "tiers": [_public_tier(t) for t in c["tiers"]],
        } for c in competitors],
        "scenarios": scenarios,
        "cost_matrix": matrix,
        "feature_gates": {"keywords": gates["keywords"], "by_company": gates["by_company"]},
        "business": biz,
        "flags": flags,
        "notes": notes,
    }


# ---------------------------------------------------------------------------
# survey command: Van Westendorp PSM + Newton-Miller-Smith
# ---------------------------------------------------------------------------

SURVEY_FIELDS = ("too_cheap", "cheap", "expensive", "too_expensive")
_SURVEY_ALIASES = {
    "too_cheap": ("too_cheap", "toocheap", "too cheap", "q1", "tc"),
    "cheap": ("cheap", "bargain", "q2", "good_value", "good value"),
    "expensive": ("expensive", "getting_expensive", "getting expensive", "q3"),
    "too_expensive": ("too_expensive", "tooexpensive", "too expensive", "q4", "te"),
    "segment": ("segment", "group", "persona", "plan", "company_size", "company size"),
    "pi_cheap": ("pi_cheap", "purchase_intent_cheap", "likely_at_cheap"),
    "pi_expensive": ("pi_expensive", "purchase_intent_expensive", "likely_at_expensive"),
}
# Question wording from a survey tool export (Typeform, Google Forms, ...).
_SURVEY_QUESTION_RES = (
    ("too_cheap", re.compile(r"too (?:cheap|low)|so (?:cheap|low)|question (?:the |its )?quality|doubt", re.I)),
    ("too_expensive", re.compile(r"too expensive|so expensive|not (?:even )?consider|would not buy|too high", re.I)),
    ("cheap", re.compile(r"bargain|great (?:buy|deal|value)|good value|cheap", re.I)),
    ("expensive", re.compile(r"(?:starting|begin(?:ning)?|start) to (?:seem |feel |get )?expensive|getting expensive|expensive", re.I)),
)


def _norm_header(text: str) -> str:
    return " ".join(str(text).strip().lower().replace("-", " ").replace("_", " ").split())


def map_survey_columns(headers: List[str], overrides: Dict[str, str]) -> Tuple[Dict[str, int], List[str]]:
    """Map CSV headers to survey fields. Returns (field -> column index, notes)."""
    notes: List[str] = []
    mapping: Dict[str, int] = {}
    normalized = [_norm_header(h) for h in headers]
    for field, header in overrides.items():
        key = _norm_header(header)
        if key in normalized:
            mapping[field] = normalized.index(key)
        else:
            raise PricingInputError(["--col %s=%r: no such column (columns: %s)" % (field, header, ", ".join(headers))])
    for field, aliases in _SURVEY_ALIASES.items():
        if field in mapping:
            continue
        for alias in aliases:
            key = _norm_header(alias)
            if key in normalized and normalized.index(key) not in mapping.values():
                mapping[field] = normalized.index(key)
                break
    for field, pattern in _SURVEY_QUESTION_RES:
        if field in mapping:
            continue
        hits = [i for i, h in enumerate(headers) if pattern.search(h) and i not in mapping.values()]
        if len(hits) == 1:
            mapping[field] = hits[0]
            notes.append("Column %r read as %s (matched by question wording)." % (headers[hits[0]], field))
    return mapping, notes


def _rows_from_csv(text: str, overrides: Dict[str, str]) -> Tuple[List[Dict[str, Any]], List[str]]:
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.reader(io.StringIO(text), dialect)
    rows = [r for r in reader if any(cell.strip() for cell in r)]
    if not rows:
        raise PricingInputError(["the CSV file has no rows"])
    headers = rows[0]
    mapping, notes = map_survey_columns(headers, overrides)
    missing = [f for f in SURVEY_FIELDS if f not in mapping]
    if missing:
        raise PricingInputError([
            "could not find the column(s) for %s. Columns found: %s. Pass --col %s=\"<column name>\" "
            "for each." % (", ".join(missing), ", ".join(repr(h) for h in headers), missing[0])
        ])
    out = []
    for raw in rows[1:]:
        row = {}
        for field, index in mapping.items():
            row[field] = raw[index] if index < len(raw) else None
        out.append(row)
    return out, notes


def _survey_rows_from_json(payload: Any) -> Tuple[List[Dict[str, Any]], List[str]]:
    notes: List[str] = []
    if isinstance(payload, list):
        payload = {"responses": payload}
    if not isinstance(payload, dict):
        raise PricingInputError(["the survey JSON must be an object with a \"responses\" list"])
    source = payload.get("survey_data") or payload.get("survey") or payload
    if isinstance(source, dict) and isinstance(source.get("responses"), list):
        rows = []
        for item in source["responses"]:
            if not isinstance(item, dict):
                raise PricingInputError(["responses: every item must be an object with too_cheap, cheap, "
                                         "expensive and too_expensive"])
            row = dict(item)
            if "cheap" not in row and "bargain" in row:
                row["cheap"] = row["bargain"]
            rows.append(row)
        return rows, notes
    legacy_keys = ("too_cheap", "bargain", "expensive", "too_expensive")
    if isinstance(source, dict) and any(k in source for k in legacy_keys + ("cheap",)):
        lists = {}
        missing = []
        for key in ("too_cheap", "cheap", "expensive", "too_expensive"):
            value = source.get(key)
            if value is None and key == "cheap":
                value = source.get("bargain")
            if value is None:
                missing.append(key if key != "cheap" else "cheap (or bargain)")
                continue
            if not isinstance(value, list):
                raise PricingInputError(["%s: expected a list of prices, got %s" % (key, type(value).__name__)])
            lists[key] = value
        if missing:
            raise PricingInputError(["survey: missing key(s) %s" % ", ".join(missing)])
        lengths = {k: len(v) for k, v in lists.items()}
        if len(set(lengths.values())) != 1:
            raise PricingInputError([
                "survey: the four lists have different lengths (%s), so answers cannot be matched to "
                "respondents. Pass one row per respondent in \"responses\"."
                % ", ".join("%s %d" % kv for kv in lengths.items())
            ])
        n = next(iter(lengths.values()))
        rows = [{k: lists[k][i] for k in lists} for i in range(n)]
        notes.append("Legacy four-list input: list position i was read as respondent i. Prefer "
                     "\"responses\" rows so each respondent's answers stay together.")
        return rows, notes
    raise PricingInputError(['survey JSON needs "responses": [{"too_cheap", "cheap", "expensive", '
                             '"too_expensive"}, ...]'])


def _ecdf_le(sorted_values: List[float], price: float) -> float:
    """Share of values <= price (values sorted ascending)."""
    lo, hi = 0, len(sorted_values)
    while lo < hi:
        mid = (lo + hi) // 2
        if sorted_values[mid] <= price:
            lo = mid + 1
        else:
            hi = mid
    return lo / len(sorted_values)


def _bounded_ecdf(values: List[float], price: float) -> float:
    """ecdf with the pricesensitivitymeter boundary rule (>= max -> 1, then <= min -> 0)."""
    if price <= values[0]:
        return 0.0
    if price >= values[-1]:
        return 1.0
    return _ecdf_le(values, price)


def _intersection(prices: List[float], curve_a: List[float], curve_b: List[float]) -> Optional[float]:
    """First crossing of two curves on the price grid (pricesensitivitymeter 'min' method)."""
    diffs = [a - b for a, b in zip(curve_a, curve_b)]
    signs = [(d > 0) - (d < 0) for d in diffs]
    crossings = []
    for i in range(len(diffs) - 1):
        if signs[i + 1] != signs[i]:
            x1, x2, y1, y2 = prices[i], prices[i + 1], diffs[i], diffs[i + 1]
            crossings.append(x1 - y1 * (x2 - x1) / (y2 - y1) if y2 != y1 else (x1 + x2) / 2.0)
    return min(crossings) if crossings else None


def van_westendorp(rows: List[Dict[str, float]], nms: bool) -> Dict[str, Any]:
    """PSM price points on valid rows (same conventions as R pricesensitivitymeter)."""
    tc = sorted(r["too_cheap"] for r in rows)
    ch = sorted(r["cheap"] for r in rows)
    ex = sorted(r["expensive"] for r in rows)
    te = sorted(r["too_expensive"] for r in rows)
    prices = sorted(set(tc) | set(ch) | set(ex) | set(te))
    curves = {"too_cheap": [], "cheap": [], "expensive": [], "too_expensive": []}
    for p in prices:
        curves["too_cheap"].append(1 - _bounded_ecdf(tc, p))
        curves["cheap"].append(1 - _bounded_ecdf(ch, p))
        curves["expensive"].append(_bounded_ecdf(ex, p))
        curves["too_expensive"].append(_bounded_ecdf(te, p))
    not_cheap = [1 - v for v in curves["cheap"]]
    not_expensive = [1 - v for v in curves["expensive"]]
    pmc = _intersection(prices, not_cheap, curves["too_cheap"])
    pme = _intersection(prices, curves["too_expensive"], not_expensive)
    idp = _intersection(prices, curves["expensive"], curves["cheap"])
    opp = _intersection(prices, curves["too_expensive"], curves["too_cheap"])

    def r2(value: Optional[float]) -> Optional[float]:
        return None if value is None else round(value, 2)

    step = max(1, len(prices) // 20)
    table = []
    for i in range(0, len(prices), step):
        table.append({"price": prices[i],
                      "too_cheap_pct": round(curves["too_cheap"][i] * 100, 1),
                      "cheap_pct": round(curves["cheap"][i] * 100, 1),
                      "expensive_pct": round(curves["expensive"][i] * 100, 1),
                      "too_expensive_pct": round(curves["too_expensive"][i] * 100, 1)})
    result: Dict[str, Any] = {
        "n_valid": len(rows),
        "point_of_marginal_cheapness": r2(pmc),
        "optimal_price_point": r2(opp),
        "indifference_price_point": r2(idp),
        "point_of_marginal_expensiveness": r2(pme),
        "acceptable_range": {"low": r2(pmc), "high": r2(pme)},
        "range_ok": pmc is not None and pme is not None and pmc <= pme,
        "medians": {"too_cheap": _median(tc), "cheap": _median(ch), "expensive": _median(ex),
                    "too_expensive": _median(te)},
        "curve_table": table,
    }
    if nms:
        result["nms"] = newton_miller_smith(rows, prices)
    return result


def _median(values: List[float]) -> Optional[float]:
    if not values:
        return None
    n = len(values)
    mid = n // 2
    return values[mid] if n % 2 else round((values[mid - 1] + values[mid]) / 2.0, 4)


def newton_miller_smith(rows: List[Dict[str, Any]], prices: List[float]) -> Dict[str, Any]:
    """Purchase probability and revenue index per price (pricesensitivitymeter method).

    Each respondent: probability 0 at their too-cheap and too-expensive
    prices, the calibrated purchase intent at their cheap and expensive
    prices, linear in between, constant outside.
    """
    usable = [r for r in rows if r.get("pi_cheap_cal") is not None and r.get("pi_expensive_cal") is not None]
    if not usable:
        return {"status": "not_measured", "reason": "no rows with both purchase-intent answers"}
    reach = [0.0] * len(prices)
    for r in usable:
        points = sorted({r["too_cheap"]: 0.0, r["cheap"]: r["pi_cheap_cal"],
                         r["expensive"]: r["pi_expensive_cal"], r["too_expensive"]: 0.0}.items())
        xs = [p for p, _ in points]
        ys = [v for _, v in points]
        for i, price in enumerate(prices):
            if price <= xs[0]:
                value = ys[0]
            elif price >= xs[-1]:
                value = ys[-1]
            else:
                j = 0
                while xs[j + 1] < price:
                    j += 1
                x1, x2, y1, y2 = xs[j], xs[j + 1], ys[j], ys[j + 1]
                value = y1 + (y2 - y1) * (price - x1) / (x2 - x1)
            reach[i] += value
    reach = [v / len(usable) for v in reach]
    revenue = [p * v for p, v in zip(prices, reach)]
    best_reach = max(range(len(prices)), key=lambda i: reach[i])
    best_revenue = max(range(len(prices)), key=lambda i: revenue[i])
    top = sorted(range(len(prices)), key=lambda i: -revenue[i])[:5]
    return {
        "status": "ok",
        "n": len(usable),
        "price_optimal_reach": prices[best_reach],
        "reach_at_optimal_reach_pct": round(reach[best_reach] * 100, 1),
        "price_optimal_revenue": prices[best_revenue],
        "reach_at_optimal_revenue_pct": round(reach[best_revenue] * 100, 1),
        "top_revenue_prices": [{"price": prices[i], "reach_pct": round(reach[i] * 100, 1),
                                "revenue_index": round(revenue[i] / revenue[best_revenue] * 100, 1) if revenue[best_revenue] else None}
                               for i in top],
        "calibration": {"scale": list(NMS_PI_SCALE), "probability": list(NMS_PI_CALIBRATED)},
    }


_EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[a-z]{2,}", re.I)


def _segment_label(value: Any, index: Dict[str, str]) -> Optional[str]:
    text = cli.to_text(value) if not isinstance(value, (list, dict)) else None
    if not text:
        return None
    if _EMAIL_RE.search(text):
        if text not in index:
            index[text] = "segment-%d" % (len(index) + 1)
        return index[text]
    return text[:40]


def analyze_survey(rows_raw: List[Dict[str, Any]], pi_scale: Optional[List[float]] = None,
                   pi_calibrated: Optional[List[float]] = None) -> Tuple[Dict[str, Any], str]:
    """Validate rows and compute PSM (+ NMS) overall and per segment. Returns (result, status)."""
    scale = list(pi_scale or NMS_PI_SCALE)
    calibrated = list(pi_calibrated or NMS_PI_CALIBRATED)
    if len(scale) != len(calibrated):
        raise PricingInputError(["pi_scale and pi_calibrated must have the same length"])
    cal_map = {float(s): float(c) for s, c in zip(scale, calibrated)}
    invalid = {"missing_or_not_a_number": 0, "not_increasing": 0}
    pi_bad = 0
    valid: List[Dict[str, Any]] = []
    segment_index: Dict[str, str] = {}
    for raw in rows_raw:
        row: Dict[str, Any] = {}
        ok = True
        for field in SURVEY_FIELDS:
            try:
                value = cli.to_number(raw.get(field), field=field)
            except cli.CoercionError:
                value = None
            if value is None or value < 0:
                ok = False
                break
            row[field] = value
        if not ok:
            invalid["missing_or_not_a_number"] += 1
            continue
        if not (row["too_cheap"] < row["cheap"] < row["expensive"] < row["too_expensive"]):
            invalid["not_increasing"] += 1
            continue
        row["segment"] = _segment_label(raw.get("segment"), segment_index)
        for key in ("pi_cheap", "pi_expensive"):
            value = raw.get(key)
            if cli.is_missing(value):
                row[key + "_cal"] = None
                continue
            try:
                number = cli.to_number(value, field=key)
            except cli.CoercionError:
                number = None
            if number is None or float(number) not in cal_map:
                pi_bad += 1
                row[key + "_cal"] = None
            else:
                row[key + "_cal"] = cal_map[float(number)]
        valid.append(row)

    total = len(rows_raw)
    n_valid = len(valid)
    invalid_total = total - n_valid
    has_pi = any(r["pi_cheap_cal"] is not None for r in valid)
    result: Dict[str, Any] = {
        "responses_total": total,
        "responses_valid": n_valid,
        "responses_invalid": invalid_total,
        "invalid_reasons": invalid,
        "invalid_share_pct": round(invalid_total / total * 100, 1) if total else None,
        "validation_rule": "too_cheap < cheap < expensive < too_expensive (strict), as in R pricesensitivitymeter",
        "min_valid_required": VW_MIN_VALID,
        "standard_valid_from": VW_STANDARD_VALID,
    }
    if pi_bad:
        result["purchase_intent_values_not_on_scale"] = pi_bad
    if n_valid < VW_MIN_VALID:
        result["reliability"] = "insufficient"
        result["message"] = ("Only %d valid responses; at least %d are needed before price points mean "
                             "anything, and %d+ per segment for a standard read." % (n_valid, VW_MIN_VALID, VW_STANDARD_VALID))
        return result, cli.STATUS_NOTHING
    result["reliability"] = "standard" if n_valid >= VW_STANDARD_VALID else "directional"
    result["overall"] = van_westendorp(valid, nms=has_pi)
    segments: Dict[str, List[Dict[str, Any]]] = {}
    for row in valid:
        if row["segment"]:
            segments.setdefault(row["segment"], []).append(row)
    if segments:
        out = []
        for name in sorted(segments, key=lambda k: -len(segments[k]))[:12]:
            seg_rows = segments[name]
            if len(seg_rows) < VW_MIN_VALID:
                out.append({"segment": name, "n_valid": len(seg_rows), "reliability": "insufficient"})
                continue
            seg = van_westendorp(seg_rows, nms=has_pi)
            seg.pop("curve_table", None)
            seg["segment"] = name
            seg["reliability"] = "standard" if len(seg_rows) >= VW_STANDARD_VALID else "directional"
            out.append(seg)
        result["segments"] = out
        if len(segments) > 12:
            result["segments_truncated"] = len(segments)
    return result, cli.STATUS_OK


# ---------------------------------------------------------------------------
# increase command: price-increase break-even and rollout math
# ---------------------------------------------------------------------------

def _parse_date(raw: Any, where: str, problems: List[str]) -> Optional[date]:
    if cli.is_missing(raw):
        return None
    try:
        return date.fromisoformat(str(raw).strip())
    except ValueError:
        problems.append("%s: %r is not a YYYY-MM-DD date" % (where, raw))
        return None


def analyze_increase(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Break-even churn, what-if outcomes and timing for a price increase."""
    problems: List[str] = []
    notes: List[str] = []
    if not isinstance(payload, dict):
        raise PricingInputError(["the increase JSON must be an object"])
    changes_raw = payload.get("changes")
    if changes_raw is None and ("current_price" in payload or "increase_pct" in payload):
        changes_raw = [{k: payload.get(k) for k in ("tier", "current_price", "new_price", "increase_pct")}]
    if not isinstance(changes_raw, list) or not changes_raw:
        raise PricingInputError(['changes: give at least one {"tier", "current_price", "new_price"} '
                                 '(or "increase_pct")'])
    margin_pct = _optional_percent(payload.get("contribution_margin_pct"), "contribution_margin_pct", problems)
    if margin_pct == 0:
        problems.append("contribution_margin_pct must be greater than 0")
    notice_days = _optional_int(payload.get("notice_days"), "notice_days", problems)
    annual_notice_days = _optional_int(payload.get("annual_notice_days"), "annual_notice_days", problems)
    announce = _parse_date(payload.get("announce_date"), "announce_date", problems)
    baseline_churn = _optional_percent(payload.get("baseline_monthly_churn_pct"), "baseline_monthly_churn_pct", problems)
    grandfather_raw = payload.get("grandfather_months_options", [0, 3, 6, 12])
    if not isinstance(grandfather_raw, list):
        grandfather_raw = [grandfather_raw]
    grandfather = []
    for i, g in enumerate(grandfather_raw):
        value = _optional_int(g, "grandfather_months_options[%d]" % i, problems)
        if value is not None:
            grandfather.append(min(value, 24))
    new_per_month = _optional_number(payload.get("new_customers_per_month"), "new_customers_per_month", problems)

    changes = []
    for i, raw in enumerate(changes_raw):
        where = "changes[%d]" % i
        if not isinstance(raw, dict):
            problems.append("%s: expected an object" % where)
            continue
        current = _optional_number(raw.get("current_price"), where + ".current_price", problems)
        new = _optional_number(raw.get("new_price"), where + ".new_price", problems)
        pct = _optional_percent(raw.get("increase_pct"), where + ".increase_pct", problems, maximum=1000)
        if new is None and current is not None and pct is not None:
            new = round(current * (1 + pct / 100.0), 4)
        if current is None and new is None and pct is None:
            problems.append("%s: give current_price and new_price, or increase_pct" % where)
            continue
        if current is not None and new is not None:
            if current == 0:
                problems.append("%s.current_price is 0: moving a free tier to paid is a packaging change, "
                                "not a price increase" % where)
                continue
            inc = (new - current) / current
        else:
            inc = pct / 100.0
        if inc <= 0:
            problems.append("%s: the new price is not higher than the current price" % where)
            continue
        changes.append({"tier": str(raw.get("tier") or "Tier %d" % (i + 1)), "current_price": current,
                        "new_price": new, "increase": inc})

    segments_raw = payload.get("segments")
    if segments_raw is None and (payload.get("mrr") is not None or payload.get("customers") is not None):
        segments_raw = [{"name": "All affected customers", "tier": changes[0]["tier"] if changes else None,
                         "mrr": payload.get("mrr"), "customers": payload.get("customers"),
                         "billing": payload.get("billing", "monthly")}]
    segments = []
    for i, raw in enumerate(segments_raw or []):
        where = "segments[%d]" % i
        if not isinstance(raw, dict):
            problems.append("%s: expected an object" % where)
            continue
        billing = str(raw.get("billing") or "monthly").lower()
        if billing not in ("monthly", "annual"):
            problems.append("%s.billing: use monthly or annual" % where)
            continue
        seg = {
            "name": str(raw.get("name") or "Segment %d" % (i + 1)),
            "tier": str(raw.get("tier")) if raw.get("tier") is not None else None,
            "customers": _optional_number(raw.get("customers"), where + ".customers", problems),
            "mrr": _optional_number(raw.get("mrr"), where + ".mrr", problems),
            "billing": billing,
            "grandfathered": False,
        }
        if raw.get("grandfathered") is not None:
            try:
                seg["grandfathered"] = bool(cli.to_bool(raw.get("grandfathered"), where + ".grandfathered"))
            except cli.CoercionError as exc:
                problems.append(str(exc))
        segments.append(seg)
    if problems:
        raise PricingInputError(problems)

    margin = (margin_pct / 100.0) if margin_pct is not None else None
    change_rows = []
    for change in changes:
        inc = change["increase"]
        be_revenue = stats.price_increase_breakeven_churn(inc)
        be_profit = stats.price_increase_breakeven_churn(inc, margin) if margin else None
        change_rows.append({
            "tier": change["tier"],
            "current_price": change["current_price"],
            "new_price": change["new_price"],
            "increase_pct": round(inc * 100, 2),
            "breakeven_churn_revenue_pct": round(be_revenue * 100, 2),
            "breakeven_churn_profit_pct": round(be_profit * 100, 2) if be_profit is not None else None,
            "formula": "revenue break-even = increase / (1 + increase); profit break-even = increase / "
                       "(margin + increase) (Nagle, Hogan and Zale)",
        })
    by_tier = {c["tier"].lower(): c for c in change_rows}

    notice = notice_days if notice_days is not None else 30
    annual_notice = annual_notice_days if annual_notice_days is not None else max(notice, 60)
    notice_months = int(math.ceil(notice / 30.0))
    seg_rows = []
    totals = {"mrr": 0.0, "extra_mrr_no_churn": 0.0}
    for seg in segments:
        change = by_tier.get((seg["tier"] or "").lower()) or (change_rows[0] if len(change_rows) == 1 else None)
        if change is None:
            notes.append("Segment '%s' names tier %r, which has no price change; skipped." % (seg["name"], seg["tier"]))
            continue
        inc = change["increase_pct"] / 100.0
        be = change["breakeven_churn_revenue_pct"] / 100.0
        row: Dict[str, Any] = {"segment": seg["name"], "tier": change["tier"], "billing": seg["billing"],
                               "customers": seg["customers"], "mrr": seg["mrr"],
                               "grandfathered": seg["grandfathered"]}
        if seg["customers"] is not None:
            row["customers_you_can_lose_at_breakeven"] = int(math.floor(seg["customers"] * be + 1e-9))
        if seg["mrr"] is not None:
            mrr = seg["mrr"]
            totals["mrr"] += mrr
            totals["extra_mrr_no_churn"] += 0 if seg["grandfathered"] else mrr * inc
            row["extra_mrr_if_no_extra_churn"] = round(mrr * inc, 2)
            levels = sorted({0.0, round(be / 2, 4), round(be, 4), round(be * 1.5, 4)})
            row["what_if"] = [{"extra_churn_pct": round(c * 100, 2),
                               "mrr_after": round(mrr * (1 + inc) * (1 - c), 2),
                               "mrr_change": round(mrr * ((1 + inc) * (1 - c) - 1), 2)} for c in levels]
            annual_notice_months = int(math.ceil(annual_notice / 30.0))

            def first_year_gain(g: int, mrr: float = mrr, inc: float = inc, billing: str = seg["billing"]) -> float:
                """Extra revenue in the 12 months after announcement, with no extra churn."""
                if billing == "monthly":
                    return mrr * inc * max(0, 12 - notice_months - g)
                # Annual: 1/12 of the segment renews each month; a renewal in
                # month m pays the new price for the 13 - m months left.
                first = annual_notice_months + g
                return mrr * inc * sum(13 - m for m in range(1, 13) if m > first) / 12.0

            options = []
            baseline_gain = first_year_gain(0)
            for g in grandfather:
                gain = first_year_gain(g)
                options.append({"grandfather_months": g,
                                "extra_revenue_first_12_months_no_extra_churn": round(gain, 2),
                                "revenue_forgone_vs_no_grandfathering": round(baseline_gain - gain, 2)})
            row["grandfathering_options"] = options
        seg_rows.append(row)

    timeline = None
    if announce is not None:
        timeline = {
            "announce_date": announce.isoformat(),
            "monthly_plans_new_price_from": (announce + timedelta(days=notice)).isoformat(),
            "annual_plans_new_price_at_renewals_after": (announce + timedelta(days=annual_notice)).isoformat(),
        }
    new_customer = None
    if new_per_month is not None and changes:
        uplift = [c for c in changes if c["current_price"] is not None and c["new_price"] is not None]
        if len(uplift) == 1:
            per_customer = uplift[0]["new_price"] - uplift[0]["current_price"]
            months_active = sum(range(1, 13))  # cohorts joining in month 1..12, no churn
            new_customer = {
                "new_customers_per_month": new_per_month,
                "uplift_per_customer_per_month": round(per_customer, 4),
                "extra_revenue_first_12_months_if_conversion_unchanged": round(per_customer * new_per_month * months_active, 2),
                "assumes": "one seat or unit per customer, no churn in new cohorts, conversion unchanged",
            }
    result = {
        "changes": change_rows,
        "segments": seg_rows,
        "totals": {"affected_mrr": round(totals["mrr"], 2),
                   "extra_mrr_if_no_extra_churn": round(totals["extra_mrr_no_churn"], 2)} if seg_rows else None,
        "notice_days_used": notice,
        "annual_notice_days_used": annual_notice,
        "timeline": timeline,
        "new_customers_only": new_customer,
        "baseline_monthly_churn_pct": baseline_churn,
        "assumptions": [
            "Extra churn means customers who leave because of the increase, on top of the baseline.",
            "Monthly plans move to the new price when the notice period ends; annual plans at their next "
            "renewal after the annual notice period, with renewals spread evenly over 12 months.",
            "Grandfathering keeps the old price for the given number of months after the notice period.",
            "No downgrades, seat reductions or expansion are modelled; measure them after launch.",
        ],
        "notes": notes,
    }
    if baseline_churn is not None:
        result["breakeven_vs_baseline"] = [
            {"tier": c["tier"], "breakeven_extra_churn_pct": c["breakeven_churn_revenue_pct"],
             "months_of_baseline_churn": round(c["breakeven_churn_revenue_pct"] / baseline_churn, 1) if baseline_churn else None}
            for c in change_rows]
    return result


# ---------------------------------------------------------------------------
# score command: rubric composite
# ---------------------------------------------------------------------------

def score_rubric(payload: Any) -> Dict[str, Any]:
    """Composite 0-100 from the model's dimension scores (report-contract.md section 4)."""
    problems: List[str] = []
    if isinstance(payload, dict):
        dims = payload.get("dimensions")
    else:
        dims = payload
    if not isinstance(dims, list):
        raise PricingInputError(['expected {"dimensions": [{"id", "score", "status", "confidence"}, ...]}'])
    seen = {}
    for i, item in enumerate(dims):
        where = "dimensions[%d]" % i
        if not isinstance(item, dict):
            problems.append("%s: expected an object" % where)
            continue
        dim_id = item.get("id")
        if dim_id not in RUBRIC_WEIGHTS:
            problems.append("%s.id: %r is not a rubric dimension (%s)" % (where, dim_id, ", ".join(RUBRIC_WEIGHTS)))
            continue
        if dim_id in seen:
            problems.append("%s.id: %r appears twice" % (where, dim_id))
            continue
        status = str(item.get("status") or ("scored" if item.get("score") is not None else "not_measured")).lower()
        if status not in ("scored", "na", "not_measured"):
            problems.append("%s.status: use scored, na or not_measured" % where)
            continue
        score = None
        if status == "scored":
            try:
                score = cli.to_number(item.get("score"), field=where + ".score", minimum=0, maximum=RUBRIC_MAX)
            except cli.CoercionError as exc:
                problems.append(str(exc))
                continue
            if score is None:
                problems.append("%s.score: missing for a scored dimension" % where)
                continue
        confidence = str(item.get("confidence") or "medium").lower()
        if confidence not in ("high", "medium", "low"):
            problems.append("%s.confidence: use high, medium or low" % where)
            continue
        seen[dim_id] = {"id": dim_id, "status": status, "score": score, "confidence": confidence,
                        "weight": RUBRIC_WEIGHTS[dim_id]}
    if problems:
        raise PricingInputError(problems)
    notes = []
    for dim_id in RUBRIC_WEIGHTS:
        if dim_id not in seen:
            seen[dim_id] = {"id": dim_id, "status": "not_measured", "score": None, "confidence": None,
                            "weight": RUBRIC_WEIGHTS[dim_id]}
            notes.append("%s was not in the input; counted as not_measured." % dim_id)
    rows = [seen[d] for d in RUBRIC_WEIGHTS]
    applicable = sum(r["weight"] for r in rows if r["status"] != "na")
    scored = [r for r in rows if r["status"] == "scored"]
    measured = sum(r["weight"] for r in scored)
    measured_share = measured / applicable if applicable else 0.0
    composite = None
    if scored and measured_share >= COMPOSITE_MIN_MEASURED - 1e-9:
        composite = round(sum(r["score"] / RUBRIC_MAX * r["weight"] for r in scored) / measured * 100)
    high = sum(r["weight"] for r in scored if r["confidence"] == "high")
    low = sum(r["weight"] for r in scored if r["confidence"] == "low")
    if not scored:
        confidence = None
    elif high >= 0.8 * measured:
        confidence = "high"
    elif low > 0.5 * measured:
        confidence = "low"
    else:
        confidence = "medium"
    for r in rows:
        r["contribution"] = (round(r["score"] / RUBRIC_MAX * r["weight"] / measured * 100, 1)
                             if r["status"] == "scored" and measured else None)
    return {
        "rubric_version": RUBRIC_VERSION,
        "composite": composite,
        "max": 100,
        "measured_weight_pct": round(measured_share * 100, 1),
        "composite_shown": composite is not None,
        "why_no_composite": None if composite is not None else
        "less than %d%% of the applicable weight was measured" % int(COMPOSITE_MIN_MEASURED * 100),
        "confidence": confidence,
        "dimensions": rows,
        "notes": notes,
    }


# ---------------------------------------------------------------------------
# Output helpers and CLI
# ---------------------------------------------------------------------------

def _fmt_num(value: Optional[float]) -> str:
    if value is None:
        return "-"
    if float(value).is_integer():
        return "{:,}".format(int(value))
    return "{:,.2f}".format(value).rstrip("0").rstrip(".") if abs(value) >= 0.01 else "{:.6f}".format(value).rstrip("0")


def _ensure_reports_gitignore(path: Optional[str]) -> None:
    """When --out writes into growth-reports/, make sure growth-reports/.gitignore exists."""
    if not path:
        return
    absolute = os.path.abspath(path)
    parts = absolute.split(os.sep)
    if "growth-reports" not in parts:
        return
    root = os.sep.join(parts[:parts.index("growth-reports") + 1]) or os.sep
    try:
        os.makedirs(root, exist_ok=True)
        ignore = os.path.join(root, ".gitignore")
        if not os.path.exists(ignore):
            with open(ignore, "w", encoding="utf-8") as handle:
                handle.write("*\n")
    except OSError:
        pass


def _human_facts(env: Dict[str, Any]) -> str:
    lines = []
    own = env.get("own") or {}
    if not own:
        return "\n".join(env.get("errors") or ["No result."])
    lines.append("Pricing facts: %s (%s tiers)" % (own["company"], own["structure"]["tier_count"]))
    for tier in own["tiers"]:
        annual = tier.get("price_annual_monthly")
        if tier.get("custom_price"):
            lines.append("  %s: contact sales" % tier["name"])
        else:
            lines.append("  %s: %s/mo%s [%s]" % (tier["name"], _fmt_num(tier.get("price_monthly")),
                                                  "" if annual is None else " (%s/mo billed annually)" % _fmt_num(annual),
                                                  tier.get("billing_unit")))
        if tier.get("added"):
            lines.append("    adds: %s" % "; ".join(tier["added"][:8]))
    matrix = env.get("cost_matrix") or {}
    if matrix.get("by_scenario"):
        lines.append("Cheapest paid option per scenario (monthly billing):")
        for entry in matrix["by_scenario"]:
            parts = []
            for c in entry["cheapest_paid"]:
                m = c["monthly_billing"]
                parts.append("%s %s" % (c["company"], "-" if not m else "%s (%s)" % (_fmt_num(m["cost"]), m["tier"])))
            lines.append("  %s: %s" % (entry["label"], " | ".join(parts)))
    for flag in env.get("flags") or []:
        lines.append("Flag [%s] %s" % (flag["severity"], flag["fact"]))
    for note in env.get("notes") or []:
        lines.append("Note: %s" % note)
    return "\n".join(lines)


def _human_generic(env: Dict[str, Any]) -> str:
    return cli.to_json(env, compact=False)


DEMO_FACTS = {
    "product": "Demo Tasks",
    "currency": "USD",
    "billing_unit": "per_seat",
    "tiers": [
        {"name": "Free", "price": 0, "seat_max": 3, "features": ["3 projects", "Basic reports"]},
        {"name": "Team", "price": 12, "annual_price": 10, "features": ["Everything in Free, plus:", "Unlimited projects", "Integrations"]},
        {"name": "Business", "price": 24, "annual_price": 20, "badge": "Most popular",
         "features": ["Everything in Team, plus:", "SAML SSO", "Advanced reports", "Admin roles"]},
        {"name": "Enterprise", "price": "Contact sales", "features": ["Everything in Business, plus:", "SCIM", "Audit log", "SLA"]},
    ],
    "metrics": {"paying_customers": 400, "mrr": 30000, "tier_mix": {"Team": 300, "Business": 100}},
    "competitors": [
        {"company": "Rival A", "billing_unit": "per_seat", "tiers": [
            {"name": "Free", "price": 0}, {"name": "Pro", "price": 10, "annual_price": 8},
            {"name": "Business", "price": 20, "annual_price": 16, "features": ["SSO"]}]},
        {"company": "Rival B", "tiers": [
            {"name": "Studio", "price": 99, "billing_unit": "flat", "seat_max": 10},
            {"name": "Unlimited", "price": 299, "billing_unit": "flat", "features": ["SSO", "Unlimited users"]}]},
    ],
    "feature_keywords": ["SSO"],
}


def _demo_survey_rows() -> List[Dict[str, Any]]:
    """Deterministic synthetic survey (not real respondents)."""
    rows = []
    for i in range(120):
        base = 20 + (i * 37 % 41)
        rows.append({"too_cheap": base * 0.5, "cheap": base * 0.8, "expensive": base * 1.4,
                     "too_expensive": base * 2.0, "pi_cheap": 5 - (i % 3), "pi_expensive": 3 - (i % 3),
                     "segment": "SMB" if i % 2 else "Mid-market"})
    return rows


def _build_parser() -> cli.ArgumentParser:
    parser = cli.ArgumentParser(
        prog="pricing_analyzer.py",
        description=__doc__.split("\n\n")[0],
        epilog="Commands: facts, survey, increase, score, plan. Run '<command> --help' for details.",
    )
    parser.add_argument("--version", action="version", version="%(prog)s " + cli.__version__)
    sub = parser.add_subparsers(dest="command")
    helps = {
        "facts": "normalize tiers, feature diffs, cost-at-scenario matrix, business facts and flags",
        "survey": "Van Westendorp (+ Newton-Miller-Smith) from per-respondent rows (JSON or CSV)",
        "increase": "price-increase break-even, what-if and rollout timing",
        "score": "weighted rubric total from the model's dimension scores",
        "plan": "A/B test sizing for a pricing or packaging test",
    }
    for name in COMMANDS:
        p = sub.add_parser(name, help=helps[name], description=helps[name])
        if name != "plan":
            p.add_argument("input", nargs="?", help="JSON file (CSV too for survey), or '-' to read stdin")
        p.add_argument("--json", action="store_true", help="print only JSON to stdout (logs go to stderr)")
        p.add_argument("--out", metavar="PATH", help="also save the JSON result to PATH")
        if name in ("facts", "survey"):
            p.add_argument("--demo", action="store_true", help="run on built-in sample data (labelled DEMO DATA)")
        if name == "survey":
            p.add_argument("--col", action="append", default=[], metavar="FIELD=COLUMN",
                           help="map a CSV column to too_cheap, cheap, expensive, too_expensive, segment, "
                                "pi_cheap or pi_expensive (repeatable)")
        if name == "plan":
            p.add_argument("--baseline", required=True, help="current conversion rate, e.g. 3%% or 0.03")
            p.add_argument("--weekly-visitors", required=True, help="visitors per week who reach the tested page or step")
            p.add_argument("--mde", default="20%", help="relative change to detect (default 20%%)")
            p.add_argument("--arms", type=int, default=2, help="variants including control (default 2)")
            p.add_argument("--max-weeks", type=float, default=4.0, help="longest acceptable test (default 4)")
    return parser


def _load_input(args: Any, allow_csv: bool = False) -> Tuple[Any, str]:
    """(payload, kind) where kind is 'json' or 'csv'."""
    source = cli.resolve_input(args.input, allow_url=False, allow_file=True, allow_stdin=True)
    label = "stdin" if source["kind"] == "stdin" else source["value"]
    text = source["text"] or ""
    if allow_csv and (label.lower().endswith((".csv", ".tsv")) or (source["kind"] == "stdin" and not text.lstrip().startswith(("{", "[")))):
        return text, "csv"
    try:
        return json.loads(text), "json"
    except ValueError as exc:
        raise cli.UsageError("Invalid JSON in %s: %s" % (label, exc))


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] not in COMMANDS and argv[0] not in ("-h", "--help", "--version"):
        # No command: facts, or survey when the file looks like a survey.
        command = "facts"
        first = next((a for a in argv if not a.startswith("-")), None)
        if first and first != "-" and os.path.isfile(first):
            if first.lower().endswith((".csv", ".tsv")):
                command = "survey"
            else:
                try:
                    with open(first, encoding="utf-8-sig") as handle:
                        peek = json.load(handle)
                    if isinstance(peek, dict) and "tiers" not in peek and (
                            "responses" in peek or "too_cheap" in peek):
                        command = "survey"
                except (OSError, ValueError):
                    pass
        argv = [command] + argv
    parser = _build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help(sys.stderr)
        return cli.EXIT_USAGE
    run = cli.Run(TOOL + " " + args.command, args)
    _ensure_reports_gitignore(getattr(args, "out", None))
    try:
        if args.command == "plan":
            return _cmd_plan(run, args)
        if getattr(args, "demo", False):
            payload, kind = (DEMO_FACTS if args.command == "facts" else {"responses": _demo_survey_rows()}), "json"
        else:
            payload, kind = _load_input(args, allow_csv=args.command == "survey")
        if args.command == "facts":
            result = analyze_facts(payload)
            notes = result.pop("notes")
            return run.emit(dict(result, notes=notes), human=_human_facts)
        if args.command == "survey":
            return _cmd_survey(run, args, payload, kind)
        if args.command == "increase":
            result = analyze_increase(payload)
            notes = result.pop("notes")
            return run.emit(dict(result, notes=notes), human=_human_generic)
        if args.command == "score":
            result = score_rubric(payload)
            notes = result.pop("notes")
            return run.emit(dict(result, notes=notes), human=_human_generic)
    except cli.UsageError as exc:
        return run.fail(cli.STATUS_USAGE, str(exc))
    except PricingInputError as exc:
        for problem in exc.problems[:-1]:
            run.error(problem)
        return run.fail(cli.STATUS_USAGE, exc.problems[-1] if exc.problems else "invalid input",
                        data={"hint": "Fix the fields listed in errors and run again. The input format is "
                                      "in references/input-schema.md."})
    return cli.EXIT_USAGE


def _cmd_survey(run: cli.Run, args: Any, payload: Any, kind: str) -> int:
    overrides = {}
    for item in getattr(args, "col", []) or []:
        if "=" not in item:
            raise cli.UsageError("--col expects FIELD=COLUMN, got %r" % item)
        field, column = item.split("=", 1)
        field = field.strip().lower()
        if field not in _SURVEY_ALIASES:
            raise cli.UsageError("--col field %r is not one of %s" % (field, ", ".join(_SURVEY_ALIASES)))
        overrides[field] = column.strip()
    notes: List[str] = []
    pi_scale = pi_cal = None
    if kind == "csv":
        rows, notes = _rows_from_csv(payload, overrides)
    else:
        rows, notes = _survey_rows_from_json(payload)
        if isinstance(payload, dict):
            pi_scale = payload.get("pi_scale")
            pi_cal = payload.get("pi_calibrated")
    if not rows:
        return run.fail(cli.STATUS_NOTHING, "The survey has no response rows.")
    result, status = analyze_survey(rows, pi_scale, pi_cal)
    for note in notes:
        run.note(note)
    if result.get("invalid_share_pct") and result["invalid_share_pct"] >= 20:
        run.note("%.0f%% of responses were inconsistent or incomplete; check the question order and "
                 "wording before trusting the price points." % result["invalid_share_pct"])
    if status != cli.STATUS_OK:
        run.error(result["message"])
    return run.emit(result, status=status, human=_human_generic)


def _cmd_plan(run: cli.Run, args: Any) -> int:
    try:
        baseline = cli.to_percent(args.baseline, field="--baseline", assume_fraction=True, minimum=0, maximum=100)
        weekly = cli.to_number(args.weekly_visitors, field="--weekly-visitors", minimum=0)
        mde = cli.to_percent(args.mde, field="--mde", assume_fraction=True, minimum=0, maximum=1000)
    except cli.CoercionError as exc:
        return run.fail(cli.STATUS_USAGE, str(exc))
    if baseline is None or weekly is None or mde is None:
        return run.fail(cli.STATUS_USAGE, "--baseline, --weekly-visitors and --mde need numbers")
    try:
        plan = stats.plan_test(baseline / 100.0, weekly, mde / 100.0, arms=args.arms, max_weeks=args.max_weeks)
    except ValueError as exc:
        return run.fail(cli.STATUS_USAGE, str(exc))
    plan["test_plan"] = "ab_test" if plan["feasible"] else "ship_and_measure"
    plan["weeks_planned"] = max(2, plan["weeks_rounded"]) if plan["feasible"] else None
    return run.emit({"plan": plan}, human=_human_generic)


if __name__ == "__main__":
    sys.exit(main())
