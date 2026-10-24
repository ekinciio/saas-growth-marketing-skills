#!/usr/bin/env python3
"""PLG funnel facts, revenue impact model, rubric scoring, export import and test sizing.

The script collects facts and does deterministic math. It never judges: the
model scores the funnel against references/rubric.md and writes the advice.

Subcommands (each prints one JSON document with --json; exit codes follow
_growthkit/cli.py: 0 ok, 2 usage or input error, 3 unreachable or blocked,
4 partial, 5 nothing to analyze):

  facts <input.json | ->   Benchmark each funnel number against the matching
                           row of references/_shared/saas-benchmarks.json
                           (keyed by motion, ARR or ACV band, pricing model,
                           AI-native and B2B/B2C), derive monthly and annual
                           equivalents, model the 12-month MRR gain of moving
                           each metric to its benchmark, rank the leaks by that
                           gain, add a sensitivity table and size A/B tests.
                           The first argument may be left out: "facts" is the
                           default ("funnel_analyzer.py input.json").
  score <dimensions.json>  Weighted 0-100 total and letter grade from the
                           model's rubric scores; "na" and "not_measured"
                           dimensions are left out and the weights renormalized.
  import <export.csv>      Activation rate, time-to-value distribution, week
                           1/4/12 retention and a flattening check from a
                           PostHog, Amplitude, Mixpanel or GA4 export (event
                           log, retention table or funnel table); volumes from
                           a billing export. Aggregates only; no user ids.
  size                     A/B test sizing for one conversion rate (two
                           proportions, alpha 0.05 two-sided, power 0.8).
  benchmarks               The benchmark rows that match a segment.
  pricing <url | file>     Quotes from a pricing page that show the motion
                           (free plan, trial length, card requirement, seat or
                           usage pricing, contact sales).

Input for facts (every block and key is optional except at least one metric):

  {
    "product": "Acme",
    "context": {"motion": "freemium_self_serve", "gtm_motion": "plg",
                "arr_band": "100k-1m", "pricing_model": "per-seat", "b2b": true,
                "ai_native": false, "activation_definition": "created a project",
                "activation_window_days": 7, "conversion_window_days": 180},
    "metrics": {"visitor_to_signup": 4.2, "activation_rate": "18%",
                "free_to_paid": 2.1, "monthly_logo_churn": 3.5, "nrr": 88,
                "grr": 80, "time_to_value": "3 days", "cac_payback_months": 15,
                "month_1_retention": 40, "week_1_retention": 35},
    "volumes": {"monthly_visitors": 48000, "monthly_signups": 2016,
                "paying_customers": 1250, "mrr": 56000, "arpa": 44.8},
    "funnel_counts": {"visitors": 52000, "signups": 2100, "activated": 640,
                      "paid": 95}
  }

Percent metrics are in percent (25 or "25%" means 25%). Words such as
"skip", "n/a" or null mean "not provided". NRR or GRR typed as a ratio (1.12)
is read as 112% with a warning. Durations take units ("36 hours", "3 days").
The old flat keys (signup_to_active, monthly_churn, time_to_value_days,
payback_months) are still read.

Requirements: Python 3.9+, standard library only (pricing also needs requests
and beautifulsoup4, through _growthkit).
"""

from __future__ import annotations

import copy
import json
import math
import os
import re
import sys
from collections import OrderedDict
from datetime import date, datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from _growthkit import __version__, cli, stats  # noqa: E402

TOOL = "funnel_analyzer"
SKILL = "plg-funnel-analyzer"
RUBRIC_VERSION = "plg-rubric-v1"
BENCHMARK_FILE = os.path.join(os.path.dirname(_SCRIPTS_DIR), "references", "_shared", "saas-benchmarks.json")

WEEKS_PER_MONTH = 4.33          # report-contract.md section 6
MODEL_MONTHS = 12
DEFAULT_MDE = 20.0              # percent, relative (report-contract.md section 6)
MAX_TEST_WEEKS = 4.0
STALE_AFTER_DAYS = 183          # benchmark README freshness rule (6 months)
CONF_RANK = {"low": 0, "medium": 1, "high": 2}
CONF_NAME = {value: key for key, value in CONF_RANK.items()}


class FunnelInputError(ValueError):
    """One or more input values are unusable. ``problems`` lists every one."""

    def __init__(self, problems: Sequence[str]) -> None:
        self.problems = list(problems)
        super().__init__("; ".join(self.problems))


# ---------------------------------------------------------------------------
# Metric catalogue
# ---------------------------------------------------------------------------

# kind: rate (percent of a base), retention (annual percent that may be typed
# as a ratio), hours, months. benchmark: (metric key in saas-benchmarks.json,
# required period or None). motion: "conversion" rows are keyed by the free
# offer (freemium, trial with or without card); "gtm" rows by plg, sales-led
# or hybrid. dimension: the rubric dimension the metric feeds.
METRICS: "OrderedDict[str, Dict[str, Any]]" = OrderedDict([
    ("visitor_to_signup", {
        "label": "Visitor-to-signup", "kind": "rate", "range": (0.0, 100.0),
        "benchmark": [("visitor_to_signup", None)], "motion": "conversion",
        "dimension": "acquisition", "direction": "higher_is_better"}),
    ("activation_rate", {
        "label": "Activation rate", "kind": "rate", "range": (0.0, 100.0),
        "benchmark": [("activation_rate", None)], "motion": "gtm",
        "dimension": "activation", "direction": "higher_is_better"}),
    ("time_to_value_hours", {
        "label": "Time to value", "kind": "hours", "range": (0.0, 24.0 * 365),
        "benchmark": [("time_to_value", None)], "motion": "gtm",
        "dimension": "time_to_value", "direction": "lower_is_better"}),
    ("free_to_paid", {
        "label": "Free-to-paid or trial-to-paid", "kind": "rate", "range": (0.0, 100.0),
        "benchmark": [("free_to_paid", None), ("trial_to_paid", None)], "motion": "conversion",
        "dimension": "monetization", "direction": "higher_is_better"}),
    ("monthly_logo_churn", {
        "label": "Monthly logo churn", "kind": "rate", "range": (0.0, 100.0),
        "benchmark": [("logo_churn", "monthly")], "motion": "gtm",
        "dimension": "retention", "direction": "lower_is_better"}),
    ("grr", {
        "label": "Gross revenue retention (12 months)", "kind": "retention", "range": (10.0, 100.0),
        "benchmark": [("grr", "annual")], "motion": "gtm",
        "dimension": "retention", "direction": "higher_is_better"}),
    ("month_1_retention", {
        "label": "Month-1 user retention", "kind": "rate", "range": (0.0, 100.0),
        "benchmark": [("month_1_retention", None)], "motion": "gtm",
        "dimension": "retention", "direction": "higher_is_better"}),
    ("week_1_retention", {
        "label": "Week-1 user retention", "kind": "rate", "range": (0.0, 100.0),
        "benchmark": [], "motion": "gtm", "dimension": "retention", "direction": "higher_is_better"}),
    ("week_4_retention", {
        "label": "Week-4 user retention", "kind": "rate", "range": (0.0, 100.0),
        "benchmark": [], "motion": "gtm", "dimension": "retention", "direction": "higher_is_better"}),
    ("week_12_retention", {
        "label": "Week-12 user retention", "kind": "rate", "range": (0.0, 100.0),
        "benchmark": [], "motion": "gtm", "dimension": "retention", "direction": "higher_is_better"}),
    ("nrr", {
        "label": "Net revenue retention (12 months)", "kind": "retention", "range": (10.0, 300.0),
        "benchmark": [("nrr", "annual")], "motion": "gtm",
        "dimension": "expansion", "direction": "higher_is_better"}),
    ("cac_payback_months", {
        "label": "CAC payback", "kind": "months", "range": (0.0, 240.0),
        "benchmark": [("cac_payback", None)], "motion": "gtm",
        "dimension": "efficiency", "direction": "lower_is_better"}),
])

# Other spellings people and models use. Values are (canonical key, unit
# multiplier for bare numbers): time_to_value_days 3 -> 72 hours.
ALIASES: Dict[str, Tuple[str, Optional[float]]] = {
    "signup_to_active": ("activation_rate", None),
    "signup_to_activation": ("activation_rate", None),
    "activation": ("activation_rate", None),
    "website_to_signup": ("visitor_to_signup", None),
    "visit_to_signup": ("visitor_to_signup", None),
    "visitor_to_trial": ("visitor_to_signup", None),
    "trial_to_paid": ("free_to_paid", None),
    "free_to_paid_conversion": ("free_to_paid", None),
    "monthly_churn": ("monthly_logo_churn", None),
    "logo_churn": ("monthly_logo_churn", None),
    "customer_churn": ("monthly_logo_churn", None),
    "net_revenue_retention": ("nrr", None),
    "gross_revenue_retention": ("grr", None),
    "payback_months": ("cac_payback_months", None),
    "payback": ("cac_payback_months", None),
    "cac_payback": ("cac_payback_months", None),
    "time_to_value": ("time_to_value_hours", None),
    "ttv": ("time_to_value_hours", None),
    "ttv_hours": ("time_to_value_hours", 1.0),
    "time_to_value_days": ("time_to_value_hours", 24.0),
    "ttv_days": ("time_to_value_hours", 24.0),
    "m1_retention": ("month_1_retention", None),
    "w1_retention": ("week_1_retention", None),
    "w4_retention": ("week_4_retention", None),
    "w12_retention": ("week_12_retention", None),
}

TOP_LEVEL_KEYS = {"product", "subject", "context", "metrics", "volumes", "funnel_counts",
                  "data_source", "sources", "notes"}

HOUR_UNITS = {
    "minute": 1 / 60.0, "minutes": 1 / 60.0, "min": 1 / 60.0, "mins": 1 / 60.0,
    "hour": 1.0, "hours": 1.0, "h": 1.0, "hr": 1.0, "hrs": 1.0,
    "day": 24.0, "days": 24.0, "d": 24.0,
    "week": 168.0, "weeks": 168.0, "w": 168.0, "wk": 168.0, "wks": 168.0,
}
MONTH_UNITS = {
    "month": 1.0, "months": 1.0, "mo": 1.0, "mos": 1.0, "mth": 1.0, "mths": 1.0,
    "year": 12.0, "years": 12.0, "yr": 12.0, "yrs": 12.0, "y": 12.0,
}
DAY_UNITS = {
    "day": 1.0, "days": 1.0, "d": 1.0, "week": 7.0, "weeks": 7.0, "w": 7.0, "wk": 7.0,
    "month": 30.44, "months": 30.44, "mo": 30.44, "year": 365.25, "years": 365.25,
}
_DURATION_RE = re.compile(r"^\s*([+-]?\d+(?:[.,]\d+)?)\s*([a-z]+)?\s*$", re.I)
_EXPLICIT_PERCENT_RE = re.compile(r"%|\bpercent\b|\bpct\b", re.I)

# Rubric dimensions. Weights must match references/rubric.md (a test checks).
DIMENSIONS: "OrderedDict[str, Dict[str, Any]]" = OrderedDict([
    ("acquisition", {"label": "Acquisition (visitor-to-signup)", "weight": 10.0}),
    ("activation", {"label": "Activation", "weight": 20.0}),
    ("time_to_value", {"label": "Time to value", "weight": 10.0}),
    ("monetization", {"label": "Monetization (free-to-paid or trial-to-paid)", "weight": 20.0}),
    ("retention", {"label": "Retention (logo, revenue and usage)", "weight": 25.0}),
    ("expansion", {"label": "Expansion (NRR)", "weight": 10.0}),
    ("efficiency", {"label": "Acquisition efficiency (CAC payback)", "weight": 5.0}),
])
GRADE_BANDS = ((70.0, "A"), (57.0, "B"), (43.0, "C"), (30.0, "D"), (0.0, "F"))
MIN_MEASURED_SHARE = 0.6        # report-contract.md section 4


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _round(value: Optional[float], digits: int = 2) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return round(float(value), digits)


def _today() -> date:
    return date.today()


def _key(text: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(text).strip().lower()).strip("_")


def _fmt_number(value: Optional[float]) -> str:
    if value is None:
        return "-"
    if abs(value) >= 1000:
        return "{:,.0f}".format(value)
    text = ("%.2f" % value).rstrip("0").rstrip(".")
    return text or "0"


def _fmt_value(key: str, value: Optional[float]) -> str:
    if value is None:
        return "-"
    kind = METRICS[key]["kind"] if key in METRICS else "rate"
    if kind == "hours":
        if value >= 48:
            return "%.1f hours (%.1f days)" % (value, value / 24.0)
        return "%.1f hours" % value
    if kind == "months":
        return "%.1f months" % value
    return "%.1f%%" % value


def _type_name(value: Any) -> str:
    return {"list": "list", "dict": "object"}.get(type(value).__name__, type(value).__name__)


# ---------------------------------------------------------------------------
# Input normalization
# ---------------------------------------------------------------------------


def _parse_duration(value: Any, units: Dict[str, float], field: str, default: Optional[float],
                    what: str) -> float:
    """Read '36 hours', '3 days', '1.5 years'. Bare numbers use ``default`` (or fail)."""
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError("%s: expected a number or a duration such as '3 days', got %s"
                         % (field, _type_name(value)))
    if isinstance(value, (int, float)):
        number, unit = float(value), None
    else:
        match = _DURATION_RE.match(value)
        if not match:
            raise ValueError("%s: %r is not a duration; write it like '36 hours' or '3 days'" % (field, value))
        number = float(match.group(1).replace(",", "."))
        unit = (match.group(2) or "").lower() or None
    if not math.isfinite(number):
        raise ValueError("%s: %s is not a finite number" % (field, value))
    if unit is None:
        if default is None:
            raise ValueError("%s: %r has no unit; write it like '36 hours' or '3 days'" % (field, value))
        return number * default
    if unit not in units:
        if unit == "m":
            raise ValueError("%s: unit 'm' is ambiguous (minutes or months); spell it out" % field)
        raise ValueError("%s: unit %r is not accepted for %s; use %s"
                         % (field, unit, what, ", ".join(sorted({u for u in units if len(u) > 2})[:6])))
    return number * units[unit]


def _parse_percent(value: Any, field: str) -> Tuple[float, bool]:
    """Return (number in percent, explicit percent sign)."""
    if isinstance(value, bool):
        raise ValueError("%s: %r is not a number" % (field, value))
    if isinstance(value, (int, float)):
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("%s: %s is not a finite number" % (field, _fmt_raw(value)))
        return number, False
    if isinstance(value, str):
        explicit = bool(_EXPLICIT_PERCENT_RE.search(value))
        cleaned = re.sub(r"\bpct\b", "%", value, flags=re.I)
        try:
            number = cli.to_percent(cleaned, field=field)
        except cli.CoercionError as exc:
            raise ValueError(str(exc))
        if number is None:
            raise ValueError("%s: no number in %r" % (field, value))
        return number, explicit
    raise ValueError("%s: expected a number, got %s" % (field, _type_name(value)))


def _fmt_raw(value: Any) -> str:
    if isinstance(value, float) and math.isnan(value):
        return "nan"
    return str(value)


def normalize_metrics(payload: Any) -> Tuple[Dict[str, float], List[str]]:
    """Clean the metrics block. Returns (metrics, warnings); raises FunnelInputError.

    Keys may be canonical (METRICS) or aliases (ALIASES). Missing words
    ("skip", "n/a", "", null) drop the metric. Every problem is collected
    before raising, so the user can fix them in one go.
    """
    if not isinstance(payload, dict):
        raise FunnelInputError(["The metrics must be an object of named values, got %s." % _type_name(payload)])
    metrics: Dict[str, float] = {}
    origin: Dict[str, str] = {}
    problems: List[str] = []
    warnings: List[str] = []
    small: List[Tuple[str, str, float]] = []
    for raw_key, value in payload.items():
        key = _key(raw_key)
        multiplier: Optional[float] = None
        if key in METRICS:
            canonical = key
            if METRICS[key]["kind"] == "hours":
                multiplier = 1.0
        elif key in ALIASES:
            canonical, multiplier = ALIASES[key]
        else:
            warnings.append("Ignored unknown metric %r. Known metrics: %s." % (raw_key, ", ".join(METRICS)))
            continue
        if isinstance(value, float) and math.isnan(value):
            problems.append("%s: nan is not a finite number" % raw_key)
            continue
        if cli.is_missing(value):
            continue
        spec = METRICS[canonical]
        low, high = spec["range"]
        try:
            if spec["kind"] == "hours":
                number = _parse_duration(value, HOUR_UNITS, raw_key, multiplier, "time to value")
                explicit = True
            elif spec["kind"] == "months":
                number = _parse_duration(value, MONTH_UNITS, raw_key, 1.0, "CAC payback")
                explicit = True
            else:
                number, explicit = _parse_percent(value, raw_key)
        except ValueError as exc:
            problems.append(str(exc))
            continue
        if number < 0:
            problems.append("%s: %s is negative" % (raw_key, _fmt_raw(value)))
            continue
        if spec["kind"] == "retention" and not explicit and 0 < number < 10:
            warnings.append("%s = %s read as a ratio, so %s%%." % (raw_key, _fmt_raw(value), _fmt_number(number * 100)))
            number *= 100.0
        if not (low <= number <= high):
            unit = "%" if spec["kind"] in ("rate", "retention") else ""
            problems.append("%s: %s%s is outside the possible range %s-%s%s"
                            % (raw_key, _fmt_number(number), unit, _fmt_number(low), _fmt_number(high), unit))
            continue
        if canonical in metrics:
            problems.append("%s: %s is given twice (also as %r)" % (raw_key, canonical, origin[canonical]))
            continue
        if spec["kind"] == "rate" and not explicit and 0 < number <= 1:
            small.append((raw_key, canonical, number))
        metrics[canonical] = number
        origin[canonical] = raw_key
    if len(small) >= 2:
        problems.append(
            "These values look like fractions, but rates are read in percent: %s. Multiply by 100 "
            "(or add a %% sign if they really are below 1%%)."
            % ", ".join("%s = %s (did you mean %s?)" % (raw, _fmt_number(num), _fmt_number(num * 100))
                        for raw, _c, num in small))
    elif len(small) == 1:
        raw, _canonical, num = small[0]
        warnings.append("%s = %s is read as %s%%. If it is a fraction, the value is %s%%."
                        % (raw, _fmt_number(num), _fmt_number(num), _fmt_number(num * 100)))
    if problems:
        raise FunnelInputError(problems)
    return metrics, warnings


MOTION_ALIASES = {
    "freemium_self_serve": "freemium_self_serve", "self_serve_freemium": "freemium_self_serve",
    "freemium_selfserve": "freemium_self_serve",
    "freemium_sales_assist": "freemium_sales_assist", "sales_assisted_freemium": "freemium_sales_assist",
    "freemium_sales_assisted": "freemium_sales_assist", "freemium_with_sales": "freemium_sales_assist",
    "freemium": "freemium", "free_plan": "freemium", "free_tier": "freemium",
    "trial_no_card": "trial_no_card", "trial_opt_in": "trial_no_card", "opt_in_trial": "trial_no_card",
    "no_card_trial": "trial_no_card", "free_trial_no_card": "trial_no_card", "trial_without_card": "trial_no_card",
    "trial_card_required": "trial_card_required", "trial_opt_out": "trial_card_required",
    "opt_out_trial": "trial_card_required", "card_required_trial": "trial_card_required",
    "free_trial_card_required": "trial_card_required", "trial_with_card": "trial_card_required",
    "trial": "trial", "free_trial": "trial",
    "reverse_trial": "reverse_trial",
    "none": "no_free_offer", "no_free_offer": "no_free_offer", "demo_only": "no_free_offer",
    "demo": "no_free_offer", "paid_only": "no_free_offer",
    "unknown": None, "not_sure": None,
}
GTM_ALIASES = {
    "plg": "plg", "product_led": "plg", "self_serve": "plg", "product_led_growth": "plg",
    "sales_led": "sales_led", "sales": "sales_led", "slg": "sales_led",
    "hybrid": "hybrid", "plg_plus_sales": "hybrid", "product_led_sales": "hybrid",
}
PRICING_ALIASES = {
    "per_seat": "seat", "seat": "seat", "seats": "seat", "per_user": "seat", "seat_based": "seat",
    "usage": "usage", "usage_based": "usage", "consumption": "usage", "metered": "usage",
    "hybrid": "hybrid", "flat": "non_seat_subscription", "tiered": "non_seat_subscription",
    "flat_rate": "non_seat_subscription", "free": None,
}
ARR_BANDS = {
    "none": (0.0, 0.0), "0": (0.0, 0.0), "lt100k": (0.0, 100e3), "100k_1m": (100e3, 1e6),
    "1m_10m": (1e6, 10e6), "10m": (10e6, float("inf")), "10m_plus": (10e6, float("inf")),
}


def _arr_band_range(text: str) -> Optional[Tuple[float, float]]:
    """growth-context.md arr_band ('<100k', '100k-1m', '1m-10m', '10m+') or '$1M-$3M' style."""
    token = str(text).strip().lower().replace(" ", "")
    simple = {"<100k": "lt100k", "100k-1m": "100k_1m", "1m-10m": "1m_10m", "10m+": "10m_plus"}
    if token in simple:
        return ARR_BANDS[simple[token]]
    if _key(token) in ARR_BANDS:
        return ARR_BANDS[_key(token)]
    return parse_band(text)


_AMOUNT_RE = r"\$?\s*(\d+(?:\.\d+)?)\s*([kmb]?)"


def _amount(number: str, suffix: str) -> float:
    return float(number) * {"": 1.0, "k": 1e3, "m": 1e6, "b": 1e9}[suffix.lower()]


def parse_band(text: Any) -> Optional[Tuple[float, float]]:
    """'<$5M' -> (0, 5e6); '>=$250K' -> (250e3, inf); '$1M-$3M' -> (1e6, 3e6); '<$25/month'."""
    if text is None:
        return None
    token = str(text).strip().lower().replace(",", "")
    token = re.sub(r"/\s*(?:month|mo)\b", "", token).strip()
    if token in ("all", ""):
        return None
    match = re.match(r"^(<=|>=|<|>)\s*" + _AMOUNT_RE + r"$", token)
    if match:
        op, number, suffix = match.groups()
        value = _amount(number, suffix)
        return (0.0, value) if op.startswith("<") else (value, float("inf"))
    match = re.match(r"^" + _AMOUNT_RE + r"\s*-\s*" + _AMOUNT_RE + r"$", token)
    if match:
        low = _amount(match.group(1), match.group(2))
        high = _amount(match.group(3), match.group(4) or match.group(2))
        return (low, high)
    return None


def _days(value: Any, field: str) -> float:
    days = _parse_duration(value, DAY_UNITS, field, 1.0, "a window in days")
    if days <= 0:
        raise ValueError("%s: must be more than 0 days" % field)
    return days


def normalize_context(raw: Any) -> Tuple[Dict[str, Any], List[str], List[str]]:
    """Clean the context block. Returns (context, warnings, problems)."""
    ctx: Dict[str, Any] = {}
    warnings: List[str] = []
    problems: List[str] = []
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        return ctx, warnings, ["context must be an object, got %s." % _type_name(raw)]

    def text(name: str) -> Optional[str]:
        value = raw.get(name)
        return None if cli.is_missing(value) else str(value).strip()

    gtm = text("gtm_motion")
    if gtm:
        ctx["gtm_motion"] = GTM_ALIASES.get(_key(gtm))
        if ctx["gtm_motion"] is None:
            warnings.append("gtm_motion %r not recognized (use plg, sales-led or hybrid)." % gtm)
    motion = text("motion")
    if motion:
        token = _key(motion)
        if token not in MOTION_ALIASES:
            warnings.append("motion %r not recognized; use freemium_self_serve, freemium_sales_assist, "
                            "trial_no_card, trial_card_required or reverse_trial." % motion)
        else:
            ctx["motion"] = MOTION_ALIASES[token]
            ctx["motion_basis"] = "given"
    if not ctx.get("motion"):
        offer = _key(text("free_offer") or "")
        card = raw.get("card_required")
        try:
            card_flag = cli.to_bool(card, "card_required")
        except cli.CoercionError as exc:
            problems.append(str(exc))
            card_flag = None
        derived = None
        if offer == "freemium":
            derived = {"plg": "freemium_self_serve", "sales_led": "freemium_sales_assist",
                       "hybrid": "freemium_sales_assist"}.get(ctx.get("gtm_motion"), "freemium")
        elif offer in ("free_trial", "trial"):
            derived = {True: "trial_card_required", False: "trial_no_card"}.get(card_flag, "trial")
        elif offer in ("demo_only", "none"):
            derived = "no_free_offer"
        elif offer == "reverse_trial":
            derived = "reverse_trial"
        if derived:
            ctx["motion"] = derived
            ctx["motion_basis"] = "derived from free_offer%s" % (" and card_required" if card_flag is not None else "")
    for name in ("arr", "acv", "arpa"):
        value = raw.get(name)
        if cli.is_missing(value):
            continue
        try:
            ctx[name] = cli.to_number(value, field=name, minimum=0)
        except cli.CoercionError as exc:
            problems.append(str(exc))
    band = text("arr_band")
    if band and "arr" not in ctx:
        span = _arr_band_range(band)
        if span is None:
            warnings.append("arr_band %r not recognized (use <100k, 100k-1m, 1m-10m or 10m+)." % band)
        else:
            ctx["arr_range"] = span
            ctx["arr_band"] = band
    pricing = text("pricing_model")
    if pricing:
        token = _key(pricing)
        if token in PRICING_ALIASES:
            ctx["pricing_model"] = PRICING_ALIASES[token]
        else:
            warnings.append("pricing_model %r not recognized (use per-seat, usage, hybrid, flat or tiered)."
                            % pricing)
    for name in ("ai_native", "b2b"):
        try:
            flag = cli.to_bool(raw.get(name), name)
        except cli.CoercionError as exc:
            problems.append(str(exc))
            continue
        if flag is not None:
            ctx[name] = flag
    company = _key(text("company_type") or "")
    if "b2b" not in ctx and company in ("b2b", "b2b_saas"):
        ctx["b2b"] = True
    elif "b2b" not in ctx and company in ("b2c", "b2c_saas", "consumer", "prosumer"):
        ctx["b2b"] = False
    source = _key(text("traffic_source") or "")
    if source in ("organic", "paid"):
        ctx["traffic_source"] = source
    for name in ("funding", "contract_term", "vertical"):
        value = text(name)
        if value:
            ctx[name] = _key(value)
    definition = text("activation_definition") or text("activation_event")
    if definition:
        ctx["activation_definition"] = definition
    for name in ("activation_window_days", "conversion_window_days"):
        value = raw.get(name)
        if cli.is_missing(value):
            continue
        try:
            ctx[name] = _days(value, name)
        except ValueError as exc:
            problems.append(str(exc))
    data_source = _key(text("data_source") or "typed")
    ctx["data_source"] = data_source if data_source in ("typed", "export", "mixed") else "typed"
    return ctx, warnings, problems


VOLUME_KEYS = ("monthly_visitors", "monthly_signups", "paying_customers", "mrr", "arpa")


def normalize_volumes(raw: Any) -> Tuple[Dict[str, float], List[str]]:
    volumes: Dict[str, float] = {}
    problems: List[str] = []
    if raw is None:
        return volumes, problems
    if not isinstance(raw, dict):
        return volumes, ["volumes must be an object, got %s." % _type_name(raw)]
    for name, value in raw.items():
        key = _key(name)
        key = {"visitors": "monthly_visitors", "signups": "monthly_signups", "customers": "paying_customers",
               "paying": "paying_customers", "arpu": "arpa"}.get(key, key)
        if key not in VOLUME_KEYS:
            problems.append("volumes: unknown key %r (use %s)" % (name, ", ".join(VOLUME_KEYS)))
            continue
        if isinstance(value, float) and math.isnan(value):
            problems.append("%s: nan is not a finite number" % name)
            continue
        try:
            number = cli.to_number(value, field=name, minimum=0)
        except cli.CoercionError as exc:
            problems.append(str(exc))
            continue
        if number is not None:
            volumes[key] = number
    return volumes, problems


def funnel_count_facts(raw: Any) -> Tuple[Dict[str, Any], List[str]]:
    """Rates (with 95% Wilson intervals) from one period of funnel counts."""
    if raw is None:
        return {}, []
    if not isinstance(raw, dict):
        return {}, ["funnel_counts must be an object, got %s." % _type_name(raw)]
    counts: Dict[str, int] = {}
    problems: List[str] = []
    for name in ("visitors", "signups", "activated", "paid"):
        value = raw.get(name)
        if cli.is_missing(value):
            continue
        try:
            number = cli.to_int(value, field="funnel_counts." + name, minimum=0)
        except cli.CoercionError as exc:
            problems.append(str(exc))
            continue
        if number is not None:
            counts[name] = number
    steps = [("visitor_to_signup", "visitors", "signups"), ("activation_rate", "signups", "activated"),
             ("free_to_paid", "signups", "paid")]
    rates: Dict[str, Any] = {}
    for metric, base, part in steps:
        if base in counts and part in counts:
            if counts[base] == 0:
                continue
            if counts[part] > counts[base]:
                problems.append("funnel_counts: %s (%d) is larger than %s (%d)" % (part, counts[part], base, counts[base]))
                continue
            low, high = stats.wilson_interval(counts[part], counts[base])
            rates[metric] = {"value": counts[part] * 100.0 / counts[base], "numerator": counts[part],
                             "denominator": counts[base], "ci95": [_round(low * 100, 2), _round(high * 100, 2)]}
    if "activated" in counts and "paid" in counts and counts["activated"]:
        low, high = stats.wilson_interval(min(counts["paid"], counts["activated"]), counts["activated"])
        rates["activated_to_paid"] = {"value": counts["paid"] * 100.0 / counts["activated"],
                                      "numerator": counts["paid"], "denominator": counts["activated"],
                                      "ci95": [_round(low * 100, 2), _round(high * 100, 2)]}
    return {"counts": counts, "rates": rates, "period": raw.get("period")}, problems


# ---------------------------------------------------------------------------
# Benchmarks: loading, segment matching, position
# ---------------------------------------------------------------------------

_BENCH_CACHE: Dict[str, Dict[str, Any]] = {}


def load_benchmarks(path: Optional[str] = None) -> Dict[str, Any]:
    path = path or BENCHMARK_FILE
    if path not in _BENCH_CACHE:
        try:
            with open(path, encoding="utf-8") as handle:
                _BENCH_CACHE[path] = json.load(handle)
        except (OSError, ValueError) as exc:
            raise cli.UsageError("Cannot read the benchmark file %s (%s). Reinstall the skill or run "
                                 "tools/sync_shared.py." % (path, exc))
    return _BENCH_CACHE[path]


CONVERSION_MOTIONS = {
    "free_to_paid": {
        "freemium_self_serve": ["freemium_self_serve", "freemium"],
        "freemium_sales_assist": ["freemium_sales_assist", "freemium"],
        "freemium": ["freemium", "freemium_self_serve", "freemium_sales_assist"],
        "trial_no_card": ["trial_opt_in", "free_trial"],
        "trial_card_required": ["trial_opt_out"],
    },
    "visitor_to_signup": {
        "freemium_self_serve": ["freemium"],
        "freemium_sales_assist": ["freemium"],
        "freemium": ["freemium"],
        "trial_no_card": ["trial_opt_in", "free_trial"],
        "trial_card_required": ["trial_opt_out"],
    },
}
NO_MOTION_REASON = {
    None: "Monetization motion unknown. Free-to-paid and visitor-to-signup differ several-fold between "
          "freemium, a no-card trial and a card-required trial, so the rate is shown without a benchmark. "
          "Set context.motion.",
    "trial": "Trial card requirement unknown. Card-required trials convert at several times the rate of "
             "no-card trials, so the rate is shown without a benchmark. Set context.motion to "
             "trial_no_card or trial_card_required.",
    "reverse_trial": "No verified reverse-trial benchmark exists in saas-benchmarks.json; the rate is shown "
                     "without one.",
    "no_free_offer": "No free plan or trial (demo-only), so free-to-paid and self-serve signup benchmarks "
                     "do not apply.",
}
# Panel floors: a source that only covers companies above this ARR. When the
# user's ARR is unknown the row still applies (most companies with real
# revenue are above it); when it is known and below, it does not.
PANEL_FLOOR_MAX = 1e6


def _range_relation(user: Tuple[float, float], row: Tuple[float, float]) -> str:
    low, high = user
    row_low, row_high = row
    if low == high:  # a point (exact ARR)
        return "inside" if row_low <= low < row_high or (low == 0 and row_low == 0) else "outside"
    if low >= row_low and high <= row_high:
        return "inside"
    if high <= row_low or low >= row_high:
        return "outside"
    return "overlap"


def _user_arr(ctx: Dict[str, Any]) -> Optional[Tuple[float, float]]:
    if ctx.get("arr") is not None:
        return (float(ctx["arr"]), float(ctx["arr"]))
    return ctx.get("arr_range")


def _match_row(row: Dict[str, Any], metric: str, ctx: Dict[str, Any]) -> Optional[Tuple[Tuple, List[str]]]:
    """Segment fit of one benchmark row: (sort key, matched dimensions) or None when it does not apply.

    Order of importance follows shared/benchmarks/README.md "Choosing a row":
    ARR or ACV band, pricing model, motion, AI-native, then other cuts.
    """
    segment = row.get("segment") or {}
    matched: List[str] = []
    band_score = pricing_score = motion_score = ai_score = extra_score = 0

    # Motion.
    motion = segment.get("motion") or "all"
    if METRICS[metric]["motion"] == "conversion":
        allowed = CONVERSION_MOTIONS.get(metric, {}).get(ctx.get("motion"), [])
        if motion not in allowed:
            return None
        motion_score = len(allowed) - allowed.index(motion)
        matched.append("motion=%s" % motion)
    elif motion != "all":
        if ctx.get("gtm_motion") != motion:
            return None
        motion_score = 1
        matched.append("motion=%s" % motion)

    # ARR band.
    arr_band = segment.get("arr_band") or "all"
    if arr_band != "all":
        span = parse_band(arr_band)
        user = _user_arr(ctx)
        if span is None:
            return None
        if user is None:
            if not (span[1] == float("inf") and span[0] <= PANEL_FLOOR_MAX):
                return None
        else:
            relation = _range_relation(user, span)
            if relation == "outside":
                return None
            if not (span[1] == float("inf") and span[0] <= PANEL_FLOOR_MAX):
                band_score += 2 if relation == "inside" else 1
                matched.append("arr_band=%s%s" % (arr_band, "" if relation == "inside" else " (partly)"))

    # ACV band.
    acv_band = segment.get("acv_band") or "all"
    if acv_band != "all":
        span = parse_band(acv_band)
        if span is None or ctx.get("acv") is None:
            return None
        if _range_relation((ctx["acv"], ctx["acv"]), span) != "inside":
            return None
        band_score += 2
        matched.append("acv_band=%s" % acv_band)

    # Pricing model.
    pricing = segment.get("pricing_model") or "all"
    if pricing != "all":
        if ctx.get("pricing_model") != pricing:
            return None
        pricing_score = 1
        matched.append("pricing_model=%s" % pricing)

    # AI-native.
    ai = segment.get("ai_native")
    if ai is True:
        if ctx.get("ai_native") is not True:
            return None
        ai_score = 1
        matched.append("ai_native")
    elif ai is False:
        if ctx.get("ai_native") is True:
            return None
        if ctx.get("ai_native") is False:
            ai_score = 1

    # Other cuts.
    for name, value in (segment.get("extra") or {}).items():
        if name == "company_type":
            want = {"b2b_saas": True, "b2c_saas": False}.get(value)
            have = ctx.get("b2b")
            if have is None:
                if want is False:
                    return None
                continue
            if have != want:
                return None
            extra_score += 1
            matched.append("company_type=%s" % value)
        elif name == "industry":
            if value == "b2b_saas":
                if ctx.get("b2b") is False:
                    return None
                if ctx.get("b2b") is True:
                    extra_score += 1
                    matched.append("industry=b2b_saas")
        elif name == "traffic_source":
            have = ctx.get("traffic_source")
            if have is None:
                continue
            if have != value:
                return None
            extra_score += 1
            matched.append("traffic_source=%s" % value)
        elif name in ("arpa_band", "price_point"):
            span = parse_band(value)
            if span is None or ctx.get("arpa") is None:
                return None
            if _range_relation((ctx["arpa"], ctx["arpa"]), span) != "inside":
                return None
            band_score += 2
            matched.append("%s=%s" % (name, value))
        else:
            if ctx.get(name) != _key(value):
                return None
            extra_score += 1
            matched.append("%s=%s" % (name, value))

    sort_key = (band_score, pricing_score, motion_score, ai_score, extra_score,
                int(row.get("year") or 0), CONF_RANK.get(row.get("confidence"), 0),
                1 if any(row.get(k) is not None for k in ("p25", "median", "p75")) else 0)
    return sort_key, matched


def _candidate_rows(bench: Dict[str, Any], metric: str) -> List[Dict[str, Any]]:
    rows = []
    for source_metric, period in METRICS[metric]["benchmark"]:
        for row in bench.get("rows", []):
            if row.get("metric") != source_metric or not row.get("verified"):
                continue
            if period and row.get("period") != period:
                continue
            rows.append(row)
    return rows


def row_brief(row: Dict[str, Any], full: bool = False) -> Dict[str, Any]:
    """A benchmark row for the JSON output. ``full`` adds url, definition and caveats."""
    segment = row.get("segment") or {}
    seg = OrderedDict((k, v) for k, v in segment.items() if k != "extra" and v not in ("all", None))
    seg.update(segment.get("extra") or {})
    out: Dict[str, Any] = OrderedDict([
        ("id", row.get("id")), ("source", row.get("source_name")), ("year", row.get("year")),
        ("segment", dict(seg) if seg else "all"),
    ])
    if full:
        out["url"] = row.get("source_url")
        out["unit"] = row.get("unit")
        out["period"] = row.get("period")
    if row.get("window"):
        out["window"] = row["window"]
    for key in ("p25", "median", "p75", "p90", "mean", "value"):
        if row.get(key) is not None:
            out[key] = row[key]
    if row.get("thresholds"):
        out["thresholds"] = [{k: band.get(k) for k in ("label", "min", "max") if band.get(k) is not None}
                             for band in row["thresholds"]]
    out["confidence"] = row.get("confidence")
    if full:
        out["direction"] = row.get("direction")
        out["verified_on"] = row.get("verified_on")
    try:
        checked = datetime.strptime(str(row.get("verified_on")), "%Y-%m-%d").date()
        if (_today() - checked).days > STALE_AFTER_DAYS:
            out["stale"] = True
    except ValueError:
        pass
    if full:
        out["definition"] = row.get("definition")
        if row.get("value_note"):
            out["note"] = row["value_note"]
        if row.get("sample_size"):
            out["sample_size"] = row["sample_size"]
        if row.get("data_period"):
            out["data_period"] = row["data_period"]
    return out


def select_rows(metric: str, ctx: Dict[str, Any], bench: Dict[str, Any], alternatives: int = 3) -> Dict[str, Any]:
    """Primary benchmark row for the user's segment, alternatives, or the reason there is none."""
    spec = METRICS[metric]
    if not spec["benchmark"]:
        return {"primary": None, "alternatives": [], "nearest": [],
                "reason": "No verified benchmark for %s in saas-benchmarks.json. Judge it from the "
                          "curve shape (flattening check) and the trend, not from a number." % spec["label"]}
    rows = _candidate_rows(bench, metric)
    if spec["motion"] == "conversion" and not CONVERSION_MOTIONS.get(metric, {}).get(ctx.get("motion")):
        reason = NO_MOTION_REASON.get(ctx.get("motion"), NO_MOTION_REASON[None])
        context_rows = sorted(rows, key=lambda r: (str(r.get("segment", {}).get("motion")), r["id"]))
        return {"primary": None, "alternatives": [], "reason": reason,
                "nearest": [row_brief(r) for r in context_rows[:6]]}
    scored = []
    for row in rows:
        fit = _match_row(row, metric, ctx)
        if fit is not None:
            scored.append((fit[0], row, fit[1]))
    if not scored:
        nearest = sorted(rows, key=lambda r: (-int(r.get("year") or 0), r["id"]))[:4]
        return {"primary": None, "alternatives": [], "nearest": [row_brief(r) for r in nearest],
                "reason": "No benchmark row matches this segment%s. The nearest rows are listed for "
                          "context only." % _missing_segment_hint(metric, ctx)}
    # Best segment fit first; equal fits in id order, so the choice is deterministic.
    scored.sort(key=lambda item: item[1]["id"])
    scored.sort(key=lambda item: item[0], reverse=True)
    _primary_key, primary, matched = scored[0]
    rest = scored[1:]
    others: List[Tuple[Tuple, Dict[str, Any], List[str]]] = []
    seen_sources = {primary.get("source_id")}
    for item in rest:  # one row per other source first ("when two sources disagree, show both")
        if item[1].get("source_id") not in seen_sources:
            others.append(item)
            seen_sources.add(item[1].get("source_id"))
    for item in rest:
        if item not in others:
            others.append(item)
    brief = row_brief(primary, full=True)
    return {
        "primary": brief,
        "primary_row": primary,
        "matched_on": matched or ["all (no narrower segment applies)"],
        "alternatives": [dict(row_brief(item[1]), matched_on=item[2] or ["all"]) for item in others[:alternatives]],
        "alternative_rows": [item[1] for item in others[:alternatives]],
        "nearest": [],
        "reason": None,
    }


def _missing_segment_hint(metric: str, ctx: Dict[str, Any]) -> str:
    if metric == "monthly_logo_churn":
        missing = [name for name in ("arpa", "arr") if ctx.get(name) is None and not (name == "arr" and ctx.get("arr_range"))]
        if missing:
            return " (logo-churn rows are cut by ARPA or ARR band; %s not given)" % " and ".join(missing)
        return " (logo-churn rows exist only for ARPA under $25 or over $500 a month and ARR under $300K or $1M-$3M)"
    return ""


def _reference(row: Dict[str, Any]) -> Optional[Tuple[str, float]]:
    """The value a metric is compared with: median, else the 'good' threshold, mean or value."""
    if row.get("median") is not None:
        return "median", float(row["median"])
    if row.get("thresholds"):
        bands = sorted(row["thresholds"], key=lambda b: (b.get("min") is None, b.get("min") or 0))
        if bands and bands[0].get("min") is not None:
            return "%s threshold (lower bound)" % bands[0].get("label", "first"), float(bands[0]["min"])
    if row.get("mean") is not None:
        return "mean", float(row["mean"])
    if row.get("value") is not None:
        return "value", float(row["value"])
    for key in ("p75", "p25"):
        if row.get(key) is not None:
            return key, float(row[key])
    return None


def position(value: float, row: Dict[str, Any]) -> Dict[str, Any]:
    """Where a value sits against one benchmark row. Pure arithmetic, no judgment."""
    lower_better = row.get("direction") == "lower_is_better"
    out: Dict[str, Any] = {"direction": row.get("direction")}
    points = [(name, float(row[name])) for name in ("p25", "median", "p75", "p90") if row.get(name) is not None]
    if points:
        points.sort(key=lambda p: p[1])
        if value < points[0][1]:
            band = "below_" + points[0][0]
        else:
            band = "at_or_above_" + points[-1][0]
            for (n1, v1), (n2, v2) in zip(points, points[1:]):
                if v1 <= value < v2:
                    band = "%s_to_%s" % (n1, n2)
                    break
        out["basis"] = "percentiles"
        out["band"] = band
        names = [p[0] for p in points]
        if {"p25", "median", "p75"} <= set(names):
            quartile = {"below_p25": 4, "p25_to_median": 3, "median_to_p75": 2}.get(band, 1)
            if lower_better:
                quartile = 5 - quartile
            out["performance_quartile"] = {1: "top", 2: "second", 3: "third", 4: "bottom"}[quartile]
    elif row.get("thresholds"):
        bands = sorted(row["thresholds"], key=lambda b: (b.get("min") is None, b.get("min") or 0))
        label = None
        if bands[0].get("min") is not None and value < bands[0]["min"]:
            label = "below_" + bands[0]["label"]
        for index, band in enumerate(bands):
            low = band.get("min")
            high = band.get("max")
            if (low is None or value >= low) and (high is None or value < high):
                label = band["label"]
            elif high is not None and value >= high:
                nxt = bands[index + 1] if index + 1 < len(bands) else None
                if nxt is None:
                    label = "above_" + band["label"]
                elif nxt.get("min") is not None and value < nxt["min"]:
                    label = "between_%s_and_%s" % (band["label"], nxt["label"])
        out["basis"] = "thresholds (rule of thumb, not a distribution)"
        out["band"] = label or "unclassified"
    else:
        out["basis"] = "mean" if row.get("mean") is not None else "value (statistic not named by the source)"
    reference = _reference(row)
    if reference:
        ref_name, ref_value = reference
        out["reference"] = {"statistic": ref_name, "value": ref_value}
        out["difference"] = _round(value - ref_value, 3)
        if ref_value:
            out["ratio_to_reference"] = _round(value / ref_value, 3)
            gap = (value - ref_value) / ref_value if lower_better else (ref_value - value) / ref_value
            out["shortfall_relative"] = _round(gap, 3)
        if abs(value - ref_value) < 1e-9:
            out["performance"] = "at_reference"
        else:
            better = value < ref_value if lower_better else value > ref_value
            out["performance"] = "better_than_reference" if better else "worse_than_reference"
        if "band" not in out:
            out["band"] = {"better_than_reference": "above_" if not lower_better else "below_",
                           "worse_than_reference": "below_" if not lower_better else "above_",
                           "at_reference": "at_"}[out["performance"]] + ref_name.split()[0]
    return out


def _benchmark_confidence(selection: Dict[str, Any]) -> Tuple[str, List[str]]:
    row = selection["primary_row"]
    reasons: List[str] = []
    level = CONF_RANK.get(row.get("confidence"), 0)
    level = min(level, CONF_RANK["medium"])  # a benchmark comparison is at most medium (report contract)
    if row.get("confidence") == "low":
        reasons.append("the benchmark row itself is low confidence")
    if selection["primary"].get("stale"):
        level = min(level, CONF_RANK["low"])
        reasons.append("benchmark verified more than 6 months ago; re-check before quoting")
    if int(row.get("year") or 0) and _today().year - int(row["year"]) >= 4:
        level = min(level, CONF_RANK["low"])
        reasons.append("benchmark data is from %s" % row["year"])
    return CONF_NAME[level], reasons


def compare_metric(metric: str, value: float, ctx: Dict[str, Any], bench: Dict[str, Any],
                   value_confidence: str = "medium") -> Dict[str, Any]:
    spec = METRICS[metric]
    out: Dict[str, Any] = OrderedDict([("label", spec["label"]), ("value", _round(value, 4)),
                                       ("unit", {"rate": "percent", "retention": "percent"}.get(spec["kind"], spec["kind"])),
                                       ("dimension", spec["dimension"])])
    selection = select_rows(metric, ctx, bench)
    caveats: List[str] = []
    if selection["primary"] is None:
        out["comparable"] = False
        out["not_compared_reason"] = selection["reason"]
        if selection["nearest"]:
            out["nearest_rows"] = selection["nearest"]
        out["confidence"] = value_confidence
        return out
    out["comparable"] = True
    out["benchmark"] = selection["primary"]
    out["matched_on"] = selection["matched_on"]
    out["position"] = position(value, selection["primary_row"])
    alternatives = []
    for brief, row in zip(selection["alternatives"], selection["alternative_rows"]):
        alt = dict(brief)
        alt["position"] = {k: v for k, v in position(value, row).items()
                           if k in ("band", "performance", "reference", "ratio_to_reference")}
        alternatives.append(alt)
    out["alternatives"] = alternatives
    level_name, reasons = _benchmark_confidence(selection)
    caveats.extend(reasons)
    level = min(CONF_RANK[level_name], CONF_RANK.get(value_confidence, 1))
    if metric in ("activation_rate", "time_to_value_hours"):
        if not ctx.get("activation_definition"):
            level = min(level, CONF_RANK["low"])
            caveats.append("activation definition not given; benchmark rows use each product's own definition")
        else:
            caveats.append("benchmark products define activation their own way; compare like-for-like only")
    if metric == "free_to_paid":
        window = selection["primary"].get("window") or ""
        months = re.search(r"(\d+)\s*months?", window)
        user_window = ctx.get("conversion_window_days")
        if months:
            bench_days = float(months.group(1)) * 30.44
            if user_window is None:
                caveats.append("conversion window not given; the benchmark counts conversions %s" % window)
                level = min(level, CONF_RANK["medium"])
            elif abs(user_window - bench_days) > 45:
                level = min(level, CONF_RANK["low"])
                caveats.append("your conversion window (%d days) differs from the benchmark's (%s)"
                               % (round(user_window), window))
        else:
            caveats.append("the benchmark source does not state its conversion window")
        if ctx.get("motion") == "trial_no_card" and selection["primary_row"].get("segment", {}).get("motion") == "free_trial":
            caveats.append("this trial benchmark does not split card-required and no-card trials")
    if metric == "monthly_logo_churn":
        caveats.append("logo churn rows describe Nov 2021 - Jan 2022 data")
    if metric == "visitor_to_signup":
        level = min(level, CONF_RANK["low"])
        caveats.append("visitor-to-signup depends on which visitors are counted (all pages or landing pages, "
                       "returning visitors, bots) and on the traffic mix; the rows are an agency client average "
                       "and an unnamed statistic, so treat the gap as directional")
    out["confidence"] = CONF_NAME[level]
    if caveats:
        out["caveats"] = caveats
    target = _target(value, selection["primary_row"])
    if target is not None:
        out["target"] = target
        conservative = target
        for row in selection["alternative_rows"]:
            alt = _target(value, row)
            if alt is not None and alt["improves"] and target["improves"]:
                if abs(alt["value"] - value) < abs(conservative["value"] - value):
                    conservative = alt
        out["conservative_target"] = conservative
    return out


def _target(value: float, row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    reference = _reference(row)
    if reference is None:
        return None
    lower_better = row.get("direction") == "lower_is_better"
    ref_name, ref_value = reference
    improves = ref_value < value if lower_better else ref_value > value
    return {"value": ref_value, "statistic": ref_name, "row": row["id"], "improves": improves}


# ---------------------------------------------------------------------------
# Derived facts
# ---------------------------------------------------------------------------


def derived_facts(metrics: Dict[str, float], volumes: Dict[str, float], ctx: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    out: Dict[str, Any] = OrderedDict()
    notes: List[str] = []
    churn = metrics.get("monthly_logo_churn")
    if churn is not None:
        annual = (1 - (1 - churn / 100.0) ** 12) * 100.0
        out["annual_logo_churn_equivalent"] = _round(annual, 1)
        out["annual_logo_retention_equivalent"] = _round(100.0 - annual, 1)
        if churn > 0:
            out["expected_customer_lifetime_months"] = _round(100.0 / churn, 1)
    for key in ("nrr", "grr"):
        if metrics.get(key) is not None:
            out["%s_monthly_equivalent" % key] = _round((metrics[key] / 100.0) ** (1 / 12.0) * 100.0, 2)
    if churn is not None and metrics.get("nrr") is not None:
        implied = metrics["nrr"] - (100.0 - out["annual_logo_churn_equivalent"])
        out["nrr_minus_annual_logo_retention_points"] = _round(implied, 1)
        if implied > 30:
            notes.append("NRR %s%% is %s points above the logo retention that %s%% monthly churn implies "
                         "(%s%% a year). That needs strong expansion; confirm that churn is monthly and "
                         "NRR is a 12-month figure." % (_fmt_number(metrics["nrr"]), _fmt_number(implied),
                                                        _fmt_number(churn), _fmt_number(100.0 - out["annual_logo_churn_equivalent"])))
    if metrics.get("grr") is not None and metrics.get("nrr") is not None and metrics["nrr"] < metrics["grr"]:
        notes.append("NRR is below GRR, which cannot happen for the same cohort and period (NRR adds expansion "
                     "to GRR). Check the two figures.")
    mrr = volumes.get("mrr")
    paying = volumes.get("paying_customers")
    arpa = volumes.get("arpa") or ctx.get("arpa")
    if arpa is None and mrr and paying:
        arpa = mrr / paying
        out["arpa_derived"] = _round(arpa, 2)
    if mrr is None and arpa is not None and paying:
        out["mrr_derived"] = _round(arpa * paying, 2)
    if mrr is not None:
        out["arr_from_mrr"] = _round(mrr * 12, 0)
    signups = volumes.get("monthly_signups")
    visitors = volumes.get("monthly_visitors")
    v2s = metrics.get("visitor_to_signup")
    if signups and visitors and v2s:
        implied = signups * 100.0 / visitors
        out["visitor_to_signup_from_volumes"] = _round(implied, 2)
        if abs(implied - v2s) / v2s > 0.2:
            notes.append("visitor_to_signup is %s%% but monthly volumes imply %s%% (%s signups / %s visitors); "
                         "check which pages and period the rate covers."
                         % (_fmt_number(v2s), _fmt_number(implied), _fmt_number(signups), _fmt_number(visitors)))
    if signups:
        out["weekly_signups"] = _round(signups / WEEKS_PER_MONTH, 1)
    if visitors:
        out["weekly_visitors"] = _round(visitors / WEEKS_PER_MONTH, 1)
    return out, notes


# ---------------------------------------------------------------------------
# Impact model
# ---------------------------------------------------------------------------


def _simulate(mrr0: float, retention: float, new_mrr: float, months: int = MODEL_MONTHS) -> Tuple[float, float]:
    """Month-end MRR after ``months`` and revenue booked over those months.

    Each month: MRR = previous MRR x monthly net retention + new MRR.
    """
    mrr = mrr0
    revenue = 0.0
    for _ in range(months):
        mrr = mrr * retention + new_mrr
        revenue += mrr
    return mrr, revenue


LEVER_ORDER = ("visitor_to_signup", "activation_rate", "free_to_paid", "monthly_logo_churn", "nrr", "grr")


def impact_model(metrics: Dict[str, float], volumes: Dict[str, float], ctx: Dict[str, Any],
                 comparisons: Dict[str, Dict[str, Any]], derived: Dict[str, Any]) -> Dict[str, Any]:
    """12-month MRR effect of moving one metric at a time to its benchmark (deterministic)."""
    out: Dict[str, Any] = OrderedDict()
    missing: List[str] = []
    mrr0 = volumes.get("mrr")
    paying = volumes.get("paying_customers")
    arpa = volumes.get("arpa") or ctx.get("arpa") or derived.get("arpa_derived")
    if arpa is None and ctx.get("acv"):
        arpa = ctx["acv"] / 12.0
    if mrr0 is None and arpa is not None and paying:
        mrr0 = arpa * paying
    if mrr0 is None:
        missing.append("mrr (or paying_customers and arpa)")
    if arpa is None:
        missing.append("arpa (or mrr and paying_customers)")

    # Monthly net revenue retention multiplier.
    basis = None
    retention = None
    if metrics.get("nrr") is not None:
        basis, retention = "nrr", (metrics["nrr"] / 100.0) ** (1 / 12.0)
    elif metrics.get("monthly_logo_churn") is not None:
        basis, retention = "monthly_logo_churn", 1 - metrics["monthly_logo_churn"] / 100.0
    elif metrics.get("grr") is not None:
        basis, retention = "grr", (metrics["grr"] / 100.0) ** (1 / 12.0)
    else:
        missing.append("a retention figure (nrr, monthly_logo_churn or grr)")

    signups = volumes.get("monthly_signups")
    visitors = volumes.get("monthly_visitors")
    v2s = metrics.get("visitor_to_signup")
    if signups is None and visitors and v2s:
        signups = visitors * v2s / 100.0
    if visitors is None and signups and v2s:
        visitors = signups * 100.0 / v2s
    f2p = metrics.get("free_to_paid")
    new_side = True
    for name, value in (("monthly_signups", signups), ("free_to_paid", f2p)):
        if value is None:
            new_side = False
            missing.append(name)

    if mrr0 is None or retention is None or arpa is None:
        out["status"] = "not_modeled"
        out["missing_inputs"] = missing
        out["why"] = "The 12-month model needs current MRR, ARPA and one retention figure."
        return out

    new_customers = signups * f2p / 100.0 if new_side else 0.0
    base_new_mrr = new_customers * arpa
    base_mrr12, base_rev = _simulate(mrr0, retention, base_new_mrr)
    out["status"] = "modeled" if new_side else "partial"
    if not new_side:
        out["missing_inputs"] = missing
        out["why"] = ("New customers are not modeled (missing %s); only retention levers on the current base "
                      "are computed." % ", ".join(m for m in missing if m in ("monthly_signups", "free_to_paid")))
    out["inputs"] = OrderedDict([
        ("mrr_now", _round(mrr0, 2)), ("arpa", _round(arpa, 2)),
        ("monthly_signups", _round(signups, 1) if signups is not None else None),
        ("monthly_visitors", _round(visitors, 1) if visitors is not None else None),
        ("new_paying_customers_per_month", _round(new_customers, 2) if new_side else None),
        ("retention_basis", basis), ("monthly_net_retention", _round(retention * 100, 3)),
    ])
    out["baseline"] = {"mrr_month_12": _round(base_mrr12, 0), "revenue_12_months": _round(base_rev, 0),
                       "mrr_change_12_months": _round(base_mrr12 - mrr0, 0)}
    assumptions = [
        "Steady state: the same signups every month, conversions booked in the month of signup (the "
        "conversion window is ignored), new customers pay the current ARPA.",
        "All MRR follows one monthly net retention rate taken from %s." % {
            "nrr": "NRR (12-month NRR to the power 1/12)",
            "monthly_logo_churn": "monthly logo churn (revenue churn assumed equal to logo churn, no expansion)",
            "grr": "GRR (no expansion)"}[basis],
        "One lever moves at a time; gains are not additive. Churn and NRR overlap because NRR already "
        "includes churn.",
    ]

    def run(new_mrr: float, ret: float) -> Tuple[float, float]:
        return _simulate(mrr0, ret, new_mrr)

    def lever_effect(key: str, target: float) -> Optional[Tuple[float, float, str]]:
        """(new_mrr, retention, description) with the lever at ``target``."""
        if key == "visitor_to_signup":
            if not new_side or not v2s or visitors is None:
                return None
            return (visitors * target / 100.0) * f2p / 100.0 * arpa, retention, "signups scale with visitor-to-signup"
        if key == "activation_rate":
            act = metrics.get("activation_rate")
            if not new_side or not act:
                return None
            new_f2p = min(100.0, f2p * target / act)
            return signups * new_f2p / 100.0 * arpa, retention, "free-to-paid scales with activation"
        if key == "free_to_paid":
            if not new_side:
                return None
            return signups * target / 100.0 * arpa, retention, "new paying customers = signups x free-to-paid"
        if key == "monthly_logo_churn":
            churn = metrics.get("monthly_logo_churn")
            if churn is None:
                return None
            if basis == "monthly_logo_churn":
                return base_new_mrr, 1 - target / 100.0, "monthly retention = 1 - churn"
            return base_new_mrr, retention + (churn - target) / 100.0, \
                "monthly net retention rises by the churn points saved"
        if key in ("nrr", "grr"):
            if basis != key:
                return None
            return base_new_mrr, (target / 100.0) ** (1 / 12.0), "monthly net retention = %s^(1/12)" % key.upper()
        return None

    if any(k == "activation_rate" for k in metrics) and new_side:
        assumptions.append("Activation lever: paid conversions come from activated users, so free-to-paid "
                           "moves in proportion to activation.")
    if basis != "monthly_logo_churn" and metrics.get("monthly_logo_churn") is not None:
        assumptions.append("Churn lever with %s as the basis: each point of monthly logo churn saved adds one "
                           "point of monthly net retention (churned customers assumed to pay average ARPA)."
                           % basis.upper())
    out["assumptions"] = assumptions

    levers = []
    for key in LEVER_ORDER:
        if key not in metrics:
            continue
        current = metrics[key]
        entry: Dict[str, Any] = OrderedDict([("metric", key), ("current", _round(current, 3))])
        comparison = comparisons.get(key) or {}
        probe = lever_effect(key, current)
        if probe is None:
            entry["status"] = "not_modeled"
            entry["why"] = ("needs monthly_signups and free_to_paid" if key in ("visitor_to_signup", "activation_rate", "free_to_paid")
                            else "only the retention basis (%s) is modeled" % basis)
            levers.append(entry)
            continue
        entry["mechanism"] = probe[2]
        for label, target_key in (("to_benchmark", "target"), ("to_conservative_benchmark", "conservative_target")):
            target = comparison.get(target_key)
            if not target:
                continue
            block: Dict[str, Any] = {"target": target["value"], "statistic": target["statistic"], "row": target["row"]}
            if not target["improves"]:
                block["status"] = "already_at_or_better"
                block["mrr_gain_month_12"] = 0.0
                block["revenue_gain_12_months"] = 0.0
            else:
                effect = lever_effect(key, target["value"])
                mrr12, rev = run(effect[0], effect[1])
                block["status"] = "modeled"
                block["mrr_month_12"] = _round(mrr12, 0)
                block["mrr_gain_month_12"] = _round(mrr12 - base_mrr12, 0)
                block["revenue_gain_12_months"] = _round(rev - base_rev, 0)
            entry[label] = block
        if "to_benchmark" not in entry:
            entry["status"] = "no_benchmark_target"
            entry["why"] = comparison.get("not_compared_reason") or "no comparable benchmark row"
        else:
            entry["status"] = "modeled"
            entry["confidence"] = comparison.get("confidence")
        levers.append(entry)
    out["levers"] = levers

    ranked = [lv for lv in levers if lv.get("status") == "modeled"
              and (lv.get("to_conservative_benchmark") or lv.get("to_benchmark", {})).get("mrr_gain_month_12", 0) > 0]
    ranked.sort(key=lambda lv: (-(lv.get("to_conservative_benchmark") or lv["to_benchmark"])["mrr_gain_month_12"],
                                LEVER_ORDER.index(lv["metric"])))
    out["leaks_ranked"] = [{
        "rank": index + 1, "metric": lv["metric"],
        "mrr_gain_month_12_conservative": (lv.get("to_conservative_benchmark") or lv["to_benchmark"])["mrr_gain_month_12"],
        "mrr_gain_month_12_to_benchmark": lv["to_benchmark"]["mrr_gain_month_12"],
        "revenue_gain_12_months_conservative": (lv.get("to_conservative_benchmark") or lv["to_benchmark"])["revenue_gain_12_months"],
        "confidence": lv.get("confidence"),
    } for index, lv in enumerate(ranked)]
    out["biggest_leak"] = out["leaks_ranked"][0]["metric"] if out["leaks_ranked"] else None
    out["ranking_rule"] = ("Levers ranked by month-12 MRR gain when moved to the closest benchmark reference "
                           "that is better than today (conservative target); ties keep funnel order.")

    sensitivity = []
    steps = {"visitor_to_signup": ("+10% relative", lambda v: min(100.0, v * 1.1)),
             "activation_rate": ("+10% relative", lambda v: min(100.0, v * 1.1)),
             "free_to_paid": ("+10% relative", lambda v: min(100.0, v * 1.1)),
             "monthly_logo_churn": ("-10% relative", lambda v: v * 0.9),
             "nrr": ("+2 points", lambda v: v + 2.0),
             "grr": ("+2 points", lambda v: min(100.0, v + 2.0))}
    for key in LEVER_ORDER:
        if key not in metrics:
            continue
        step_label, step = steps[key]
        new_value = step(metrics[key])
        effect = lever_effect(key, new_value)
        if effect is None:
            continue
        mrr12, rev = run(effect[0], effect[1])
        sensitivity.append({"metric": key, "step": step_label, "from": _round(metrics[key], 3),
                            "to": _round(new_value, 3), "mrr_gain_month_12": _round(mrr12 - base_mrr12, 0),
                            "revenue_gain_12_months": _round(rev - base_rev, 0)})
    sensitivity.sort(key=lambda s: -s["mrr_gain_month_12"])
    out["sensitivity"] = sensitivity
    out["not_in_model"] = [k for k in metrics if k not in LEVER_ORDER]
    return out


# ---------------------------------------------------------------------------
# Test sizing
# ---------------------------------------------------------------------------


def size_test(baseline_percent: float, weekly: float, mde_percent: float = DEFAULT_MDE,
              max_weeks: float = MAX_TEST_WEEKS, direction: str = "up") -> Dict[str, Any]:
    """stats.plan_test() in percent units, rounded for reports."""
    baseline = baseline_percent / 100.0
    mde = mde_percent / 100.0 * (-1 if direction == "down" else 1)
    plan = stats.plan_test(baseline, weekly, mde, relative=True, max_weeks=max_weeks)
    at_max = plan.get("mde_at_max_weeks")
    return OrderedDict([
        ("baseline_percent", _round(baseline_percent, 3)),
        ("target_percent", _round(plan["target_rate"] * 100, 3)),
        ("mde_relative_percent", _round(mde_percent, 2)),
        ("weekly_entering_test", _round(weekly, 1)),
        ("n_per_arm", plan["n_per_arm"]),
        ("total_needed", plan["total_visitors"]),
        ("weeks", _round(plan["weeks"], 1)),
        ("weeks_rounded", max(2, plan["weeks_rounded"])),
        ("feasible_within_weeks", max_weeks),
        ("feasible", plan["feasible"]),
        ("detectable_relative_change_in_max_weeks_percent",
         _round(abs(at_max["relative"]) * 100, 1) if at_max else None),
        ("verdict", plan["verdict"]),
        ("method", "two-proportion z-test, alpha 0.05 two-sided, power 0.8, 2 arms (growthkit stats.plan_test)"),
    ])


def test_sizing(metrics: Dict[str, float], volumes: Dict[str, float], ctx: Dict[str, Any],
                mde_percent: float) -> Dict[str, Any]:
    out: Dict[str, Any] = OrderedDict()
    signups = volumes.get("monthly_signups")
    visitors = volumes.get("monthly_visitors")
    v2s = metrics.get("visitor_to_signup")
    if signups is None and visitors and v2s:
        signups = visitors * v2s / 100.0
    if visitors is None and signups and v2s:
        visitors = signups * 100.0 / v2s
    plans = (("visitor_to_signup", visitors, None),
             ("activation_rate", signups, ctx.get("activation_window_days")),
             ("free_to_paid", signups, ctx.get("conversion_window_days")))
    for key, monthly, delay in plans:
        value = metrics.get(key)
        if value is None:
            continue
        if not monthly:
            out[key] = {"status": "traffic_unknown",
                        "why": "monthly %s not given, so the weekly traffic of a test is unknown"
                               % ("visitors" if key == "visitor_to_signup" else "signups")}
            continue
        if not 0 < value < 100:
            out[key] = {"status": "not_sizable", "why": "baseline must be between 0% and 100%"}
            continue
        try:
            plan = size_test(value, monthly / WEEKS_PER_MONTH, mde_percent)
        except ValueError as exc:
            out[key] = {"status": "not_sizable", "why": str(exc)}
            continue
        plan["status"] = "sized"
        if delay:
            plan["readout_delay_days"] = _round(delay, 0)
            plan["note"] = ("The last users enrolled need %d more days before their outcome is known; add that "
                            "to the test length." % round(delay))
        out[key] = plan
    return out


# ---------------------------------------------------------------------------
# facts
# ---------------------------------------------------------------------------

DEMO_INPUT = {
    "product": "DemoApp (sample data)",
    "context": {
        "motion": "freemium_self_serve", "gtm_motion": "plg", "b2b": True, "pricing_model": "per-seat",
        "activation_definition": "created a first project and invited one teammate",
        "activation_window_days": 7, "conversion_window_days": 180,
    },
    "metrics": {
        "visitor_to_signup": 4.2, "activation_rate": 18, "free_to_paid": 2.1, "monthly_logo_churn": 3.5,
        "nrr": 88, "time_to_value": "3 days", "cac_payback_months": 15,
    },
    "volumes": {"monthly_visitors": 48000, "monthly_signups": 2016, "paying_customers": 1250, "mrr": 56000},
}

LEGACY_KEYS = {"signup_to_active", "free_to_paid", "monthly_churn", "nrr", "time_to_value_days", "payback_months"}


def build_facts(payload: Any, bench: Dict[str, Any], mde_percent: float = DEFAULT_MDE) -> Dict[str, Any]:
    """Everything the model needs to score and advise, as plain JSON types."""
    if not isinstance(payload, dict):
        raise FunnelInputError(["The input must be a JSON object, got %s." % _type_name(payload)])
    warnings: List[str] = []
    problems: List[str] = []
    if "metrics" in payload:
        raw_metrics = payload.get("metrics")
        if raw_metrics is None:
            raw_metrics = {}
        unknown_top = [k for k in payload if k not in TOP_LEVEL_KEYS]
        if unknown_top:
            warnings.append("Ignored unknown top-level key(s): %s." % ", ".join(unknown_top))
    else:
        raw_metrics = {k: v for k, v in payload.items() if k not in TOP_LEVEL_KEYS}
        if raw_metrics:
            warnings.append("Read top-level keys as metrics (no \"metrics\" block).")
    try:
        metrics, metric_warnings = normalize_metrics(raw_metrics)
        warnings.extend(metric_warnings)
    except FunnelInputError as exc:
        problems.extend(exc.problems)
        metrics = {}
    ctx, ctx_warnings, ctx_problems = normalize_context(payload.get("context"))
    warnings.extend(ctx_warnings)
    problems.extend(ctx_problems)
    volumes, volume_problems = normalize_volumes(payload.get("volumes"))
    problems.extend(volume_problems)
    counts, count_problems = funnel_count_facts(payload.get("funnel_counts"))
    problems.extend(count_problems)
    if problems:
        raise FunnelInputError(problems)

    value_sources: Dict[str, str] = {k: ctx["data_source"] for k in metrics}
    for name, source in (payload.get("sources") or {}).items() if isinstance(payload.get("sources"), dict) else []:
        canonical = name if name in METRICS else ALIASES.get(_key(name), (None,))[0]
        if canonical in value_sources and _key(source) in ("typed", "export", "counts"):
            value_sources[canonical] = _key(source)
    if counts:
        for key, rate in counts["rates"].items():
            if key in METRICS and key not in metrics:
                metrics[key] = rate["value"]
                value_sources[key] = "counts"
        if "visitors" in counts["counts"] and "monthly_visitors" not in volumes:
            volumes["monthly_visitors"] = float(counts["counts"]["visitors"])
            warnings.append("monthly_visitors taken from funnel_counts (assumed to be one month).")
        if "signups" in counts["counts"] and "monthly_signups" not in volumes:
            volumes["monthly_signups"] = float(counts["counts"]["signups"])
            warnings.append("monthly_signups taken from funnel_counts (assumed to be one month).")
        if "paid" in counts["counts"] and "free_to_paid" in counts["rates"]:
            warnings.append("free_to_paid from funnel_counts is paid / signups in the same period, not a "
                            "cohort conversion; read it as approximate.")
    if not metrics:
        return {"metrics": {}, "warnings": warnings, "context": _ctx_out(ctx)}

    if ctx.get("arr") is None and volumes.get("mrr") is not None:
        ctx["arr"] = volumes["mrr"] * 12
        ctx["arr_basis"] = "mrr x 12"
    if ctx.get("arpa") is None:
        if volumes.get("arpa") is not None:
            ctx["arpa"] = volumes["arpa"]
        elif volumes.get("mrr") and volumes.get("paying_customers"):
            ctx["arpa"] = volumes["mrr"] / volumes["paying_customers"]
    if ctx.get("acv") is None and ctx.get("arpa") is not None:
        ctx["acv"] = ctx["arpa"] * 12
        ctx["acv_basis"] = "arpa x 12"

    value_conf = {"export": "high", "counts": "medium", "typed": "medium", "mixed": "medium"}
    comparisons: Dict[str, Dict[str, Any]] = OrderedDict()
    for key in METRICS:
        if key in metrics:
            comparison = compare_metric(key, metrics[key], ctx, bench, value_conf.get(value_sources.get(key), "medium"))
            comparison["value_source"] = value_sources.get(key, "typed")
            if value_sources.get(key) == "counts":
                comparison["ci95"] = counts["rates"][key]["ci95"]
            comparisons[key] = comparison
    derived, derived_notes = derived_facts(metrics, volumes, ctx)
    warnings.extend(derived_notes)
    model = impact_model(metrics, volumes, ctx, comparisons, derived)
    sizing = test_sizing(metrics, volumes, ctx, mde_percent)

    by_dimension: Dict[str, Any] = OrderedDict()
    for dim in DIMENSIONS:
        keys = [k for k in comparisons if METRICS[k]["dimension"] == dim]
        by_dimension[dim] = {"weight": DIMENSIONS[dim]["weight"], "metrics": keys,
                             "status": "has_data" if keys else "not_measured"}
    gap_ranking = sorted(
        ({"metric": k, "shortfall_relative": c["position"]["shortfall_relative"], "confidence": c["confidence"]}
         for k, c in comparisons.items()
         if c.get("comparable") and c["position"].get("shortfall_relative") is not None
         and c["position"]["shortfall_relative"] > 0),
        key=lambda item: -item["shortfall_relative"])

    result: Dict[str, Any] = OrderedDict()
    result["product"] = payload.get("product") or payload.get("subject")
    result["context"] = _ctx_out(ctx)
    result["metrics"] = comparisons
    result["derived"] = derived
    if counts:
        result["funnel_counts"] = counts
    result["impact_model"] = model
    result["gap_ranking"] = gap_ranking
    result["test_sizing"] = sizing
    result["dimensions"] = by_dimension
    result["rubric"] = {"version": RUBRIC_VERSION, "file": "references/rubric.md"}
    result["benchmark_file"] = {"last_verified": bench.get("last_verified"), "schema_version": bench.get("schema_version")}
    result["warnings"] = warnings
    return result


def _ctx_out(ctx: Dict[str, Any]) -> Dict[str, Any]:
    out = OrderedDict()
    for key in ("motion", "motion_basis", "gtm_motion", "arr", "arr_basis", "arr_band", "acv", "acv_basis",
                "arpa", "pricing_model", "ai_native", "b2b", "traffic_source", "funding", "contract_term",
                "activation_definition", "activation_window_days", "conversion_window_days", "data_source"):
        if key in ctx and ctx[key] is not None:
            value = ctx[key]
            out[key] = _round(value, 2) if isinstance(value, float) else value
    if "motion" not in out:
        out["motion"] = None
    return out


def format_facts(envelope: Dict[str, Any], compare: bool = False) -> str:
    lines: List[str] = []
    if envelope.get("status") != "ok":
        lines.append("Status: %s" % envelope.get("status"))
        for item in envelope.get("errors", []):
            lines.append("  error: %s" % item)
        if not envelope.get("metrics"):
            return "\n".join(lines)
    ctx = envelope.get("context") or {}
    lines.append("PLG FUNNEL FACTS%s" % (" - %s" % envelope["product"] if envelope.get("product") else ""))
    lines.append("Segment: " + ", ".join("%s=%s" % (k, ctx[k]) for k in ("motion", "gtm_motion", "arr", "arr_band",
                                                                           "arpa", "pricing_model", "b2b", "ai_native")
                                          if ctx.get(k) is not None))
    lines.append("")
    lines.append("%-34s %-20s %-44s %s" % ("Metric", "Value", "Reference (source, year)", "Position"))
    for key, item in (envelope.get("metrics") or {}).items():
        value = _fmt_value(key, item["value"])
        if item.get("comparable"):
            pos = item["position"]
            ref = pos.get("reference") or {}
            bench = item["benchmark"]
            ref_text = "%s %s (%s %s)" % (ref.get("statistic", "").split()[0], _fmt_value(key, ref.get("value")),
                                          (bench.get("source") or "").split(",")[0][:22], bench.get("year"))
            pos_text = "%s; %s" % (pos.get("band"), (pos.get("performance") or "").replace("_", " "))
        else:
            ref_text = "no comparable benchmark"
            pos_text = "not compared"
        lines.append("%-34s %-20s %-44s %s [%s]" % (item["label"][:34], value, ref_text[:44], pos_text, item.get("confidence")))
        if compare:
            for alt in item.get("alternatives", []):
                apos = alt.get("position", {})
                lines.append("%-34s %-20s %-44s %s" % ("", "  also:", ("%s %s" % (alt.get("source", "")[:28], alt.get("year")))[:44],
                                                      apos.get("band")))
    model = envelope.get("impact_model") or {}
    lines.append("")
    if model.get("status") in ("modeled", "partial"):
        lines.append("12-month model: MRR %s now -> %s at month 12 (baseline)"
                     % (_fmt_number(model["inputs"]["mrr_now"]), _fmt_number(model["baseline"]["mrr_month_12"])))
        for leak in model.get("leaks_ranked", []):
            lines.append("  %d. %-22s +%s MRR at month 12 (conservative target; +%s to the primary benchmark)"
                         % (leak["rank"], leak["metric"], _fmt_number(leak["mrr_gain_month_12_conservative"]),
                            _fmt_number(leak["mrr_gain_month_12_to_benchmark"])))
        if model.get("sensitivity"):
            lines.append("Sensitivity (one lever at a time):")
            for row in model["sensitivity"]:
                lines.append("  %-22s %-14s +%s MRR at month 12" % (row["metric"], row["step"], _fmt_number(row["mrr_gain_month_12"])))
    else:
        lines.append("12-month model not computed: missing %s" % ", ".join(model.get("missing_inputs", [])))
    sizing = envelope.get("test_sizing") or {}
    if sizing:
        lines.append("A/B test sizing (MDE relative, 4-week limit):")
        for key, plan in sizing.items():
            if plan.get("status") == "sized":
                lines.append("  %-22s %s per arm, %.1f weeks -> %s" % (key, _fmt_number(plan["n_per_arm"]), plan["weeks"], plan["verdict"]))
            else:
                lines.append("  %-22s %s" % (key, plan.get("why")))
    if envelope.get("notes"):
        lines.append("")
        lines.append("Notes:")
        for note in envelope["notes"]:
            lines.append("  - " + note)
    return "\n".join(lines)


def cmd_facts(args: Any) -> int:
    run = cli.Run(TOOL, args)
    try:
        if args.demo:
            payload = copy.deepcopy(DEMO_INPUT)
        else:
            payload, _source = cli.load_json_input(args.input, expect=None)
        bench = load_benchmarks()
        if not (0 < args.mde < 1000):
            raise cli.UsageError("--mde must be a relative change in percent between 0 and 1000, got %s" % args.mde)
        result = build_facts(payload, bench, args.mde)
    except FunnelInputError as exc:
        for problem in exc.problems:
            run.error(problem)
        run.note("Fix the listed values and run again. Rates are in percent (25 means 25%).")
        return run.emit({"problems": exc.problems}, status=cli.STATUS_USAGE,
                        human="Input error:\n" + "\n".join("  - " + p for p in exc.problems))
    except cli.UsageError as exc:
        return run.fail(cli.STATUS_USAGE, str(exc))
    for warning in result.pop("warnings", []):
        run.note(warning)
    if not result.get("metrics"):
        return run.fail(cli.STATUS_NOTHING, "No funnel numbers in the input. Give at least one metric "
                                            "(activation_rate, free_to_paid, ...) or funnel_counts.", result)
    return run.emit(result, human=lambda env: format_facts(env, compare=args.compare))


# ---------------------------------------------------------------------------
# score
# ---------------------------------------------------------------------------


def score_dimensions(payload: Any) -> Dict[str, Any]:
    """Weighted rubric total. Raises FunnelInputError for invalid entries."""
    if isinstance(payload, dict) and "dimensions" in payload:
        entries = payload["dimensions"]
    else:
        entries = payload
    if isinstance(entries, dict):
        entries = [dict(value, id=key) if isinstance(value, dict) else {"id": key, "score": value}
                   for key, value in entries.items()]
    if not isinstance(entries, list):
        raise FunnelInputError(["Expected {\"dimensions\": [...]} with one entry per rubric dimension."])
    problems: List[str] = []
    notes: List[str] = []
    seen: Dict[str, Dict[str, Any]] = {}
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            problems.append("dimensions[%d]: expected an object" % index)
            continue
        dim = _key(entry.get("id") or entry.get("dimension") or "")
        if dim not in DIMENSIONS:
            problems.append("dimensions[%d]: unknown id %r (use %s)" % (index, entry.get("id"), ", ".join(DIMENSIONS)))
            continue
        if dim in seen:
            problems.append("%s: scored twice" % dim)
            continue
        status = _key(entry.get("status") or "scored")
        if status not in ("scored", "na", "not_measured"):
            problems.append("%s: status must be scored, na or not_measured, got %r" % (dim, entry.get("status")))
            continue
        score = None
        if status == "scored":
            raw = entry.get("score")
            if isinstance(raw, bool) or not isinstance(raw, (int, float)) or not math.isfinite(raw):
                problems.append("%s: score must be a number from 0 to 10, got %r" % (dim, raw))
                continue
            if not 0 <= raw <= 10:
                problems.append("%s: score must be from 0 to 10, got %s" % (dim, raw))
                continue
            score = float(raw)
        confidence = _key(entry.get("confidence") or "")
        if status == "scored" and confidence not in CONF_RANK:
            notes.append("%s: confidence missing or not high/medium/low; counted as low." % dim)
            confidence = "low"
        seen[dim] = {"score": score, "status": status, "confidence": confidence if status == "scored" else None,
                     "evidence": entry.get("evidence") or [], "justification": entry.get("justification")}
        if status == "scored" and not seen[dim]["evidence"]:
            notes.append("%s: no evidence IDs given; every score must cite evidence." % dim)
    if problems:
        raise FunnelInputError(problems)
    rows = []
    applicable = measured = points = 0.0
    weight_by_conf = {"high": 0.0, "medium": 0.0, "low": 0.0}
    for dim, spec in DIMENSIONS.items():
        entry = seen.get(dim)
        if entry is None:
            entry = {"score": None, "status": "not_measured", "confidence": None, "evidence": [], "justification": None}
            notes.append("%s: not in the input; counted as not measured." % dim)
        weight = spec["weight"]
        row = OrderedDict([("id", dim), ("label", spec["label"]), ("weight", weight), ("score", entry["score"]),
                           ("max", 10), ("status", entry["status"]), ("confidence", entry["confidence"]),
                           ("evidence", entry["evidence"]), ("justification", entry["justification"])])
        if entry["status"] != "na":
            applicable += weight
        if entry["status"] == "scored":
            measured += weight
            points += entry["score"] / 10.0 * weight
            weight_by_conf[entry["confidence"]] += weight
            row["weighted_points"] = _round(entry["score"] / 10.0 * weight, 2)
        rows.append(row)
    scoring: Dict[str, Any] = OrderedDict([("mode", "rubric"), ("version", RUBRIC_VERSION)])
    if measured == 0:
        scoring.update({"value": None, "max": 100, "grade": None, "confidence": None, "measured_weight": 0.0,
                        "composite_shown": False, "reason": "no dimension was scored"})
        return {"scoring": scoring, "dimensions": rows, "notes": notes}
    share = measured / applicable if applicable else 0.0
    composite = points / measured * 100.0
    high_share = weight_by_conf["high"] / measured
    low_share = weight_by_conf["low"] / measured
    confidence = "high" if high_share >= 0.8 else "low" if low_share > 0.5 else "medium"
    shown = share >= MIN_MEASURED_SHARE - 1e-9
    scoring.update(OrderedDict([
        ("value", _round(composite, 1) if shown else None),
        ("max", 100),
        ("grade", _grade(composite) if shown else None),
        ("confidence", confidence),
        ("measured_weight", _round(share, 3)),
        ("applicable_weight", _round(applicable, 1)),
        ("composite_shown", shown),
        ("reason", None if shown else "measured weight %.0f%% is below the %.0f%% needed for a total; show "
                                      "per-dimension scores only" % (share * 100, MIN_MEASURED_SHARE * 100)),
        ("composite_if_shown", _round(composite, 1)),
        ("range_if_not_measured_scored_0_to_10", [
            _round(points / applicable * 100.0, 1) if applicable else None,
            _round((points + (applicable - measured)) / applicable * 100.0, 1) if applicable else None]),
        ("grade_bands", "A >= 70, B >= 57, C >= 43, D >= 30, F < 30 (the segment median on every dimension scores 50)"),
    ]))
    return {"scoring": scoring, "dimensions": rows, "notes": notes}


def _grade(value: float) -> str:
    for floor, letter in GRADE_BANDS:
        if value >= floor - 1e-9:
            return letter
    return "F"


def format_score(envelope: Dict[str, Any]) -> str:
    if envelope.get("status") not in ("ok", "partial") or "scoring" not in envelope:
        return "Error: " + "; ".join(envelope.get("errors") or ["no score"])
    scoring = envelope["scoring"]
    lines = []
    if scoring.get("composite_shown"):
        lines.append("Funnel score: %s/100, grade %s (rubric %s; confidence %s; %.0f%% of weight measured)"
                     % (_fmt_number(scoring["value"]), scoring["grade"], scoring["version"], scoring["confidence"],
                        scoring["measured_weight"] * 100))
    else:
        lines.append("No total: %s" % scoring.get("reason"))
    for row in envelope["dimensions"]:
        lines.append("  %-46s %-6s weight %-5s %s" % (row["label"], _fmt_number(row["score"]) if row["score"] is not None else "-",
                                                     _fmt_number(row["weight"]), row["status"]))
    return "\n".join(lines)


def cmd_score(args: Any) -> int:
    run = cli.Run(TOOL, args)
    try:
        payload, _source = cli.load_json_input(args.input, expect=(dict, list))
        result = score_dimensions(payload)
    except FunnelInputError as exc:
        for problem in exc.problems:
            run.error(problem)
        return run.emit({"problems": exc.problems}, status=cli.STATUS_USAGE,
                        human="Input error:\n" + "\n".join("  - " + p for p in exc.problems))
    except cli.UsageError as exc:
        return run.fail(cli.STATUS_USAGE, str(exc))
    for note in result.pop("notes", []):
        run.note(note)
    if result["scoring"]["measured_weight"] == 0:
        return run.fail(cli.STATUS_NOTHING, "No dimension was scored, so there is no total.", result)
    return run.emit(result, human=format_score)


# ---------------------------------------------------------------------------
# import
# ---------------------------------------------------------------------------


def _quantile(sorted_values: List[float], q: float) -> Optional[float]:
    """Linear interpolation between closest ranks (the common 'type 7' definition)."""
    if not sorted_values:
        return None
    if len(sorted_values) == 1:
        return sorted_values[0]
    pos = (len(sorted_values) - 1) * q
    low = int(math.floor(pos))
    high = min(low + 1, len(sorted_values) - 1)
    return sorted_values[low] + (sorted_values[high] - sorted_values[low]) * (pos - low)


def flattening_check(average: List[Dict[str, Any]], tail_span: int = 4, min_points: int = 5,
                     flat_loss: float = 0.10) -> Dict[str, Any]:
    """Does the average retention curve level off?

    Tool convention (not a benchmark): compare the last observed period with
    the one ``tail_span`` periods earlier. 'flattening' when the curve lost
    at most ``flat_loss`` (10%) of the users still active at the earlier
    point; 'still_declining' when it lost more; 'falls_to_zero' at 0.
    """
    points = [(p["period"], p["rate"], p.get("cohorts")) for p in average
              if p.get("period") is not None and p["period"] >= 1 and p.get("rate") is not None]
    out: Dict[str, Any] = OrderedDict([("rule", "last observed period vs %d periods earlier; flattening when the "
                                                "relative loss is %d%% or less (tool convention, not a benchmark)"
                                        % (tail_span, round(flat_loss * 100)))])
    if len(points) < min_points or len(points) <= tail_span:
        out["verdict"] = "too_short"
        out["why"] = "needs at least %d periods after period 0; the data has %d" % (max(min_points, tail_span + 1), len(points))
        return out
    last_period, last_rate, last_cohorts = points[-1]
    ref_period, ref_rate, _ref_cohorts = points[-1 - tail_span]
    first_period, first_rate, _ = points[0]
    early_period, early_rate, _ = points[min(tail_span, len(points) - 1)]
    out["first_period"] = {"period": first_period, "rate_percent": _round(first_rate * 100, 2)}
    out["tail_start"] = {"period": ref_period, "rate_percent": _round(ref_rate * 100, 2)}
    out["tail_end"] = {"period": last_period, "rate_percent": _round(last_rate * 100, 2), "cohorts": last_cohorts}
    tail_loss = 1 - last_rate / ref_rate if ref_rate > 0 else None
    early_loss = 1 - early_rate / first_rate if first_rate > 0 else None
    out["tail_relative_loss_percent"] = _round(tail_loss * 100, 1) if tail_loss is not None else None
    out["early_relative_loss_percent"] = _round(early_loss * 100, 1) if early_loss is not None else None
    out["tail_loss_points_per_period"] = _round((ref_rate - last_rate) * 100 / tail_span, 2)
    if last_rate <= 0:
        out["verdict"] = "falls_to_zero"
    elif tail_loss is not None and tail_loss <= flat_loss:
        out["verdict"] = "flattening"
    else:
        out["verdict"] = "still_declining"
    if last_cohorts is not None and last_cohorts < 3:
        out["caution"] = ("only %d cohort(s) reach the last period, so the tail rests on few users and on the "
                          "oldest cohorts" % last_cohorts)
    return out


def _checkpoints(unit: str) -> List[int]:
    return {"week": [1, 4, 12], "day": [1, 7, 30], "month": [1, 3, 6]}.get(unit, [1, 4, 12])


def retention_facts(retention: Dict[str, Any]) -> Dict[str, Any]:
    unit = retention.get("period_unit") or "period"
    average = retention.get("average") or []
    by_period = {p["period"]: p for p in average}
    checkpoints = []
    for period in _checkpoints(unit):
        point = by_period.get(period)
        checkpoints.append({"period": period, "unit": unit,
                            "rate_percent": _round(point["rate"] * 100, 2) if point and point.get("rate") is not None else None,
                            "cohorts": point.get("cohorts") if point else 0})
    curve = [{"period": p["period"], "rate_percent": _round(p["rate"] * 100, 2) if p.get("rate") is not None else None,
              "cohorts": p.get("cohorts")} for p in average]
    return OrderedDict([("period_unit", unit), ("cohort_count", retention.get("cohort_count")),
                        ("checkpoints", checkpoints), ("average_curve", curve[:27]),
                        ("flattening", flattening_check(average)),
                        ("definitions", retention.get("definitions"))])


def _suggest_from_retention(facts: Dict[str, Any], suggested: Dict[str, Any]) -> None:
    unit = facts.get("period_unit")
    for point in facts.get("checkpoints", []):
        if point["rate_percent"] is None:
            continue
        if unit == "week" and point["period"] in (1, 4, 12):
            suggested["metrics"]["week_%d_retention" % point["period"]] = point["rate_percent"]
        if unit == "month" and point["period"] == 1:
            suggested["metrics"]["month_1_retention"] = point["rate_percent"]


def event_facts(normalized: Dict[str, Any], signup_event: Optional[str], activation_event: Optional[str],
                window_days: float, active_event: Optional[str], period: str) -> Dict[str, Any]:
    from _growthkit import importers  # noqa: WPS433 - stdlib-only module, imported on demand

    events = normalized["events"]
    if not events:
        raise importers.NothingToImport("No readable event rows.")
    names: Dict[str, int] = {}
    for _user, name, _when in events:
        names[name] = names.get(name, 0) + 1
    top = sorted(names.items(), key=lambda item: (-item[1], item[0]))[:25]
    for option, wanted in (("--signup-event", signup_event), ("--activation-event", activation_event),
                           ("--active-event", active_event)):
        if wanted and wanted not in names:
            raise importers.ImportOptionError("%s %r is not an event in the file." % (option, wanted),
                                              {"most_frequent_events": [n for n, _c in top]})
    per_user: Dict[str, List[Tuple[datetime, str]]] = {}
    for user, name, when in events:
        per_user.setdefault(user, []).append((when, name))
    for items in per_user.values():
        items.sort()
    first_seen = min(when for _u, _n, when in events)
    last_seen = max(when for _u, _n, when in events)
    window = timedelta(days=window_days)
    out: Dict[str, Any] = OrderedDict()
    out["events"] = {"event_count": len(events), "user_count": len(per_user), "first_event": first_seen.isoformat(),
                     "last_event": last_seen.isoformat(),
                     "top_events": [{"event": n, "count": c} for n, c in top]}
    signup_times: Dict[str, datetime] = {}
    for user, items in per_user.items():
        start = next((when for when, name in items if signup_event is None or name == signup_event), None)
        if start is not None:
            signup_times[user] = start
    out["signup_definition"] = ("first %r event" % signup_event) if signup_event else "first event of each user"

    # Monthly signups over complete calendar months.
    months: Dict[str, int] = {}
    for when in signup_times.values():
        months[when.strftime("%Y-%m")] = months.get(when.strftime("%Y-%m"), 0) + 1
    first_month, last_month = first_seen.strftime("%Y-%m"), last_seen.strftime("%Y-%m")
    complete = sorted(m for m in months if first_month < m < last_month)
    out["monthly_signups"] = OrderedDict([
        ("complete_months", len(complete)),
        ("average", _round(sum(months[m] for m in complete) / len(complete), 1) if complete else None),
        ("by_month", [{"month": m, "signups": months[m]} for m in sorted(months)][-13:]),
        ("note", "first and last calendar months of the file are partial and excluded from the average"),
    ])

    if activation_event:
        eligible = [u for u, start in signup_times.items() if start + window <= last_seen]
        hours: List[float] = []
        for user in eligible:
            start = signup_times[user]
            hit = next((when for when, name in per_user[user]
                        if name == activation_event and start <= when <= start + window), None)
            if hit is not None:
                hours.append((hit - start).total_seconds() / 3600.0)
        hours.sort()
        activation: Dict[str, Any] = OrderedDict([
            ("definition", "users whose %r follows their signup within %s days" % (activation_event, _fmt_number(window_days))),
            ("eligible_signups", len(eligible)),
            ("excluded_too_recent", len(signup_times) - len(eligible)),
            ("activated", len(hours)),
        ])
        if eligible:
            low, high = stats.wilson_interval(len(hours), len(eligible))
            activation["rate_percent"] = _round(len(hours) * 100.0 / len(eligible), 2)
            activation["ci95_percent"] = [_round(low * 100, 2), _round(high * 100, 2)]
        else:
            activation["rate_percent"] = None
            activation["why"] = "no signup is older than the %s-day window" % _fmt_number(window_days)
        out["activation"] = activation
        if hours:
            within = lambda limit: _round(sum(1 for h in hours if h <= limit) * 100.0 / len(hours), 1)  # noqa: E731
            out["time_to_value_hours"] = OrderedDict([
                ("activated_users", len(hours)),
                ("p25", _round(_quantile(hours, 0.25), 2)), ("median", _round(_quantile(hours, 0.5), 2)),
                ("p75", _round(_quantile(hours, 0.75), 2)), ("p90", _round(_quantile(hours, 0.9), 2)),
                ("share_within_1_hour_percent", within(1)), ("share_within_1_day_percent", within(24)),
                ("share_within_7_days_percent", within(168)),
                ("definition", "hours from signup to the first %r within the window, activated users only"
                               % activation_event),
            ])
    try:
        summary = importers.summarize_events(normalized, steps=None, cohort_event=signup_event,
                                             active_event=active_event, period=period)
    except importers.NothingToImport:
        summary = {}
    if summary.get("retention"):
        out["retention"] = retention_facts(summary["retention"])
    else:
        out["retention"] = {"status": "not_measured",
                            "why": "the events cover less than one full %s after the first cohort" % period}
    out["notes"] = [n for n in (summary.get("events") or {}).get("notes", []) if "--step" not in n]
    return out


def funnel_facts(funnel: Dict[str, Any], signup_step: Optional[str], activation_step: Optional[str]) -> Dict[str, Any]:
    segments = funnel.get("segments") or []
    segment = next((s for s in segments if str(s.get("segment")).lower() in ("all", "total", "all users")), segments[0])
    steps = segment["steps"]

    def find(token: Optional[str], default: Optional[int]) -> Optional[int]:
        if token is None:
            return default
        text = str(token).strip()
        if text.isdigit() and 1 <= int(text) <= len(steps):
            return int(text) - 1
        for index, step in enumerate(steps):
            if str(step["name"]).strip().lower() == text.lower():
                return index
        raise ValueError("step %r not found; steps are: %s" % (token, ", ".join(s["name"] for s in steps)))

    out: Dict[str, Any] = OrderedDict([("segment", segment.get("segment")), ("segment_count", funnel.get("segment_count")),
                                       ("steps", steps), ("biggest_drop", segment.get("biggest_drop"))])
    start = find(signup_step, 0)
    act = find(activation_step, None)
    if act is not None:
        if act <= start:
            raise ValueError("the activation step must come after the signup step")
        base = steps[start]["count"]
        hit = steps[act]["count"]
        out["activation"] = OrderedDict([
            ("definition", "%r / %r in this funnel export" % (steps[act]["name"], steps[start]["name"])),
            ("signups", base), ("activated", hit),
            ("rate_percent", _round(hit * 100.0 / base, 2) if base else None),
        ])
        if base and float(base).is_integer() and float(hit).is_integer() and hit <= base:
            low, high = stats.wilson_interval(int(hit), int(base))
            out["activation"]["ci95_percent"] = [_round(low * 100, 2), _round(high * 100, 2)]
        seconds = steps[act].get("time_to_convert_seconds")
        if seconds is not None:
            out["activation"]["median_time_from_previous_step_hours"] = _round(seconds / 3600.0, 2)
    return out


def billing_volumes(billing: Dict[str, Any]) -> Dict[str, Any]:
    currency = billing.get("primary_currency")
    block = (billing.get("by_currency") or {}).get(currency) or {}
    current = block.get("current") or {}
    out: Dict[str, Any] = OrderedDict([("as_of", billing.get("as_of")), ("currency", currency),
                                       ("mrr", current.get("mrr")), ("paying_customers", current.get("paying_customers")),
                                       ("arpa", current.get("arpa"))])
    averages = block.get("window_averages") or {}
    if billing.get("churn_observable") and averages.get("avg_monthly_logo_churn_rate") is not None:
        out["monthly_logo_churn_percent"] = _round(averages["avg_monthly_logo_churn_rate"] * 100, 2)
        out["churn_window_months"] = averages.get("months")
    ttm = block.get("ttm_retention") or {}
    if billing.get("churn_observable") and ttm.get("nrr") is not None:
        out["nrr_ttm_percent"] = _round(ttm["nrr"] * 100, 1)
        out["grr_ttm_percent"] = _round(ttm["grr"] * 100, 1) if ttm.get("grr") is not None else None
    elif ttm.get("reason"):
        out["nrr_ttm_why_missing"] = ttm["reason"]
    out["note"] = ("Volumes for the funnel impact model. For the full MRR, churn and NRR report run "
                   "subscription-metrics on the same export.")
    return out


def cmd_import(args: Any) -> int:
    from _growthkit import importers

    run = cli.Run(TOOL, args)
    path = args.input
    if not path:
        return run.fail(cli.STATUS_USAGE, "No input file. Pass the downloaded export (.csv, .tsv or .zip).")
    if not os.path.isfile(path):
        return run.fail(cli.STATUS_USAGE, "File not found: %s" % path)
    if args.window_days <= 0:
        return run.fail(cli.STATUS_USAGE, "--window-days must be more than 0")
    try:
        loaded = importers.load(path, kind=args.kind, source=args.source, member=args.member, values=args.values)
        kind = loaded["format"]["kind"]
        result: Dict[str, Any] = OrderedDict()
        result["file"] = loaded["file"]
        result["format"] = loaded["format"]
        result["rows"] = loaded["rows"]
        suggested: Dict[str, Any] = {"metrics": OrderedDict(), "volumes": OrderedDict(),
                                     "context": OrderedDict([("data_source", "export")])}
        notes = list(loaded["normalized"].get("notes", []))
        if kind == "events":
            facts = event_facts(loaded["normalized"], args.signup_event, args.activation_event,
                                args.window_days, args.active_event, args.period)
            notes.extend(facts.pop("notes", []))
            result.update(facts)
            if facts.get("activation", {}).get("rate_percent") is not None:
                suggested["metrics"]["activation_rate"] = facts["activation"]["rate_percent"]
                suggested["context"]["activation_window_days"] = args.window_days
                suggested["context"]["activation_definition"] = facts["activation"]["definition"]
            if facts.get("time_to_value_hours", {}).get("median") is not None:
                suggested["metrics"]["time_to_value_hours"] = facts["time_to_value_hours"]["median"]
            if facts.get("monthly_signups", {}).get("average") is not None:
                suggested["volumes"]["monthly_signups"] = facts["monthly_signups"]["average"]
            if isinstance(facts.get("retention"), dict) and facts["retention"].get("checkpoints"):
                _suggest_from_retention(facts["retention"], suggested)
            if not args.activation_event:
                notes.append("Pass --signup-event and --activation-event (names from events.top_events) for the "
                             "activation rate and the time-to-value distribution.")
        elif kind == "retention":
            facts = retention_facts(importers.summarize_retention(loaded["normalized"]))
            result["retention"] = facts
            _suggest_from_retention(facts, suggested)
        elif kind == "funnel":
            summary = importers.summarize_funnel(loaded["normalized"])
            notes.extend(summary.get("notes", []))
            try:
                facts = funnel_facts(summary, args.signup_step, args.activation_step)
            except ValueError as exc:
                return run.fail(cli.STATUS_USAGE, str(exc), {"steps": [s["name"] for s in summary["segments"][0]["steps"]]})
            result["funnel"] = facts
            if facts.get("activation", {}).get("rate_percent") is not None:
                suggested["metrics"]["activation_rate"] = facts["activation"]["rate_percent"]
            else:
                notes.append("Pass --activation-step <name or number> (and --signup-step when step 1 is not the "
                             "signup) for the activation rate.")
        elif kind == "billing":
            billing = importers.summarize_billing(loaded["normalized"], args.as_of)
            notes.extend(billing.get("notes", []))
            volumes = billing_volumes(billing)
            result["billing"] = volumes
            for source_key, target_key in (("mrr", "mrr"), ("paying_customers", "paying_customers"), ("arpa", "arpa")):
                if volumes.get(source_key) is not None:
                    suggested["volumes"][target_key] = volumes[source_key]
            if volumes.get("monthly_logo_churn_percent") is not None:
                suggested["metrics"]["monthly_logo_churn"] = volumes["monthly_logo_churn_percent"]
            if volumes.get("nrr_ttm_percent") is not None:
                suggested["metrics"]["nrr"] = volumes["nrr_ttm_percent"]
                if volumes.get("grr_ttm_percent") is not None:
                    suggested["metrics"]["grr"] = volumes["grr_ttm_percent"]
        else:
            return run.fail(cli.STATUS_USAGE, "This is a %s export (%s), not funnel, retention, event or billing "
                                              "data." % (kind, loaded["format"]["label"]))
        result["suggested_input"] = suggested
        result = importers.scrub(result)
    except importers.NothingToImport as exc:
        return run.fail(cli.STATUS_NOTHING, importers.scrub(str(exc)), importers.scrub(exc.details))
    except importers.ImportOptionError as exc:
        return run.fail(cli.STATUS_USAGE, importers.scrub(str(exc)), importers.scrub(exc.details))
    except importers.ImportFormatError as exc:
        data = dict(exc.details)
        data.setdefault("supported_formats", sorted(importers.FORMATS_BY_SOURCE))
        return run.fail(cli.STATUS_USAGE, importers.scrub(str(exc)), importers.scrub(data))
    for note in notes:
        run.note(importers.scrub(note))
    rows = result["rows"]
    status = cli.STATUS_OK
    if rows["data_rows"] and rows["unreadable"] / float(rows["data_rows"]) > importers.UNREADABLE_PARTIAL_SHARE:
        run.error("%d of %d rows could not be read." % (rows["unreadable"], rows["data_rows"]))
        status = cli.STATUS_PARTIAL
    return run.emit(result, status=status)


# ---------------------------------------------------------------------------
# size
# ---------------------------------------------------------------------------


def cmd_size(args: Any) -> int:
    run = cli.Run(TOOL, args)
    try:
        baseline = cli.to_percent(args.baseline, field="--baseline", minimum=0, maximum=100)
        weekly = cli.to_number(args.weekly, field="--weekly", minimum=0)
        mde = cli.to_percent(args.mde, field="--mde", minimum=0)
    except cli.CoercionError as exc:
        return run.fail(cli.STATUS_USAGE, str(exc))
    if baseline is None or weekly is None or not weekly or mde is None or not mde:
        return run.fail(cli.STATUS_USAGE, "--baseline, --weekly and --mde need numbers above 0.")
    if not 0 < baseline < 100:
        return run.fail(cli.STATUS_USAGE, "--baseline must be between 0 and 100 percent.")
    try:
        plan = size_test(baseline, weekly, mde, args.max_weeks, "down" if args.decrease else "up")
    except ValueError as exc:
        return run.fail(cli.STATUS_USAGE, str(exc))
    plan["test_plan"] = "ab_test" if plan["feasible"] else "ship_and_measure"
    return run.emit({"plan": plan}, human=lambda env: "%s: %s per arm, %.1f weeks. %s" % (
        "A/B test" if env["plan"]["feasible"] else "Ship and measure", _fmt_number(env["plan"]["n_per_arm"]),
        env["plan"]["weeks"], env["plan"]["verdict"]))


# ---------------------------------------------------------------------------
# benchmarks
# ---------------------------------------------------------------------------

CATEGORY_METRICS = {
    "acquisition": ["visitor_to_signup"],
    "activation": ["activation_rate", "time_to_value_hours", "month_1_retention"],
    "conversion": ["visitor_to_signup", "free_to_paid"],
    "retention": ["monthly_logo_churn", "grr", "month_1_retention", "week_1_retention"],
    "revenue": ["nrr", "grr", "cac_payback_months"],
    "referral": [],
    "all": [k for k in METRICS],
}
NOT_BENCHMARKED = {
    "week_1_retention": "No verified week-1/4/12 user retention benchmark; use the flattening check on your own curve.",
    "referral": "No verified viral coefficient, invite acceptance or referral benchmark in saas-benchmarks.json; "
                "measure your own loop (references/growth-loops.md).",
    "reverse_trial": "No verified reverse-trial conversion benchmark.",
}


def cmd_benchmarks(args: Any) -> int:
    run = cli.Run(TOOL, args)
    raw_ctx = {"motion": args.motion, "gtm_motion": args.gtm_motion, "arr_band": args.arr_band, "arr": args.arr,
               "acv": args.acv, "arpa": args.arpa, "pricing_model": args.pricing_model, "ai_native": args.ai_native,
               "b2b": args.b2b, "traffic_source": args.traffic_source}
    ctx, warnings, problems = normalize_context({k: v for k, v in raw_ctx.items() if v is not None})
    if problems:
        return run.fail(cli.STATUS_USAGE, "; ".join(problems))
    for warning in warnings:
        run.note(warning)
    try:
        bench = load_benchmarks()
    except cli.UsageError as exc:
        return run.fail(cli.STATUS_USAGE, str(exc))
    out: Dict[str, Any] = OrderedDict()
    for key in CATEGORY_METRICS[args.category]:
        selection = select_rows(key, ctx, bench)
        entry: Dict[str, Any] = OrderedDict([("label", METRICS[key]["label"])])
        if selection["primary"] is None:
            entry["comparable"] = False
            entry["reason"] = selection["reason"]
            if selection["nearest"]:
                entry["nearest_rows"] = selection["nearest"]
        else:
            entry["comparable"] = True
            entry["primary"] = selection["primary"]
            entry["matched_on"] = selection["matched_on"]
            entry["alternatives"] = selection["alternatives"]
        out[key] = entry
    result = {"category": args.category, "context": _ctx_out(ctx), "benchmarks": out,
              "not_benchmarked": NOT_BENCHMARKED, "benchmark_file_last_verified": bench.get("last_verified")}
    return run.emit(result)


# ---------------------------------------------------------------------------
# pricing
# ---------------------------------------------------------------------------

PRICING_SIGNALS = OrderedDict([
    ("free_plan", r"\bfree (?:plan|tier|forever)\b|\bfree for (?:individuals|personal|small teams|up to)\b"
                  r"|(?<![\d.,])[$\u20ac\u00a3]\s?0(?![\d.,])(?:\s*/\s*(?:mo|month|user|seat))?"
                  r"|\b(?:forever|always) free\b"),
    ("free_trial", r"\bfree trial\b|\b\d{1,2}[- ]day (?:free )?trial\b|\bstart (?:your |a )?(?:free )?trial\b"
                   r"|\btrial period\b"),
    ("try_free_cta", r"\btry (?:it )?(?:\w+ )?(?:for )?free\b|\b(?:get started|sign up|start) (?:for )?free\b"),
    ("no_card", r"no credit card(?: required| needed)?|no card required|without a credit card|no payment details"),
    ("card_required", r"(?<!no )(?<!credit )(?:credit )?card (?:is )?required|requires a (?:credit )?card"),
    ("per_seat", r"\bper (?:user|seat|member|editor|agent)\b|/\s*(?:user|seat|member|editor)\b"),
    ("usage_based", r"\bper (?:request|call|credit|token|event|gb|minute|run|task|message)\b"
                    r"|\bpay[- ]as[- ]you[- ]go\b|\busage[- ]based\b|\bcredits? (?:per|included|a month)\b"),
    ("contact_sales", r"\bcontact (?:sales|us)\b|\btalk to (?:sales|an expert)\b|\b(?:book|request|get) a demo\b"),
    ("reverse_trial", r"\breverse trial\b|\btrial of (?:our |the )?(?:pro|premium|business|plus)\b"),
    ("annual_billing", r"\bbilled (?:annually|yearly)\b|\bsave (?:up to )?\d{1,2}\s?%|\bannual(?:ly)? billing\b"),
])
_PRICE_RE = re.compile(r"(?:[$€£])\s?\d[\d,]*(?:\.\d{1,2})?")
_TRIAL_DAYS_RE = re.compile(r"\b(\d{1,2})[- ]day (?:free )?trial\b", re.I)


def pricing_signals(text: str, max_snippets: int = 3) -> Dict[str, Any]:
    flat = " ".join(text.split())
    signals: Dict[str, Any] = OrderedDict()
    for name, pattern in PRICING_SIGNALS.items():
        snippets: List[str] = []
        count = 0
        for match in re.finditer(pattern, flat, re.I):
            count += 1
            if len(snippets) < max_snippets:
                start = max(0, match.start() - 70)
                end = min(len(flat), match.end() + 70)
                snippet = ("..." if start else "") + flat[start:end].strip() + ("..." if end < len(flat) else "")
                if snippet not in snippets:
                    snippets.append(snippet)
        signals[name] = {"count": count, "quotes": snippets}
    prices: List[str] = []
    for match in _PRICE_RE.finditer(flat):
        token = match.group(0).replace(" ", "")
        if token not in prices:
            prices.append(token)
    trial_days = sorted({int(m.group(1)) for m in _TRIAL_DAYS_RE.finditer(flat)})
    return {"signals": signals, "prices": prices[:20], "trial_days": trial_days}


def cmd_pricing(args: Any) -> int:
    run = cli.Run(TOOL, args)
    try:
        source = cli.resolve_input(args.input, allow_url=True, allow_file=True, allow_stdin=False)
    except cli.UsageError as exc:
        return run.fail(cli.STATUS_USAGE, str(exc))
    from _growthkit import html as gk_html

    page: Dict[str, Any] = OrderedDict()
    if source["kind"] == "url":
        from _growthkit import http as gk_http

        fetched = gk_http.fetch(source["value"], timeout=args.timeout)
        status, message = cli.fetch_outcome(fetched)
        page.update({"url": fetched.get("url"), "final_url": fetched.get("final_url"),
                     "http_status": fetched.get("http_status"), "fetched": "static fetch, %s" % date.today().isoformat()})
        if status not in (cli.STATUS_OK, cli.STATUS_PARTIAL):
            return run.fail(status, message, {"page": page, "fetch": gk_http.summarize(fetched)})
        if message:
            run.note(message)
        markup = fetched.get("html") or ""
    else:
        markup = source["text"] or ""
        page.update({"file": os.path.basename(source["value"]), "fetched": "saved HTML file"})
    facts = gk_html.page_facts(markup, page.get("final_url") or page.get("url"), text_chars=0)
    status, message = cli.facts_outcome(facts)
    page.update({"title": facts.get("title"), "word_count": facts.get("word_count"), "lang": facts.get("lang")})
    if status == cli.STATUS_NOTHING:
        return run.fail(status, message, {"page": page})
    if message:
        run.note(message)
    found = pricing_signals(gk_html.visible_text(markup))
    if not found["prices"] and not any(v["count"] for v in found["signals"].values()):
        run.note("No prices or plan wording in the static HTML. Prices may load with JavaScript; follow the "
                 "browser fallback and pass the saved HTML file.")
    run.note("Quotes are evidence for the model to read; the script does not decide the motion.")
    return run.emit({"page": page, "pricing": found})


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------

COMMANDS = ("facts", "score", "import", "size", "benchmarks", "pricing")


def _common(parser: Any, demo: bool = False) -> None:
    parser.add_argument("--json", action="store_true", help="print only JSON to stdout (logs go to stderr)")
    parser.add_argument("--out", metavar="PATH", help="also save the JSON result to PATH")
    if demo:
        parser.add_argument("--demo", action="store_true", help="run on built-in sample data (labelled DEMO DATA)")


def build_parser() -> Any:
    parser = cli.ArgumentParser(
        prog="funnel_analyzer.py",
        description="PLG funnel facts, 12-month impact model, rubric scoring, export import and test sizing.",
        epilog="Run '<subcommand> --help' for the options of each subcommand. 'facts' is the default.",
        formatter_class=__import__("argparse").RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version="%(prog)s " + __version__)
    sub = parser.add_subparsers(dest="command", parser_class=cli.ArgumentParser)

    facts = sub.add_parser("facts", help="benchmark funnel numbers and model the 12-month impact")
    facts.add_argument("input", nargs="?", help="JSON file with context, metrics and volumes, or '-' for stdin")
    _common(facts, demo=True)
    facts.add_argument("--mde", type=float, default=DEFAULT_MDE,
                       help="relative effect (percent) for test sizing, default 20")
    facts.add_argument("--compare", action="store_true", help="human output: also list the alternative benchmark rows")

    score = sub.add_parser("score", help="weighted rubric total from the model's dimension scores")
    score.add_argument("input", nargs="?", help="JSON file {\"dimensions\": [...]}, or '-' for stdin")
    _common(score)

    imp = sub.add_parser("import", help="activation, time to value and retention from an analytics export")
    imp.add_argument("input", nargs="?", help="the downloaded export (.csv, .tsv or .zip)")
    _common(imp)
    imp.add_argument("--signup-event", help="event log: the event that marks signup (default: a user's first event)")
    imp.add_argument("--activation-event", help="event log: the activation event")
    imp.add_argument("--active-event", help="event log: an event that counts a user as retained (default: any event)")
    imp.add_argument("--window-days", type=float, default=7.0,
                     help="days after signup in which activation counts (default 7; use your own definition)")
    imp.add_argument("--period", choices=("week", "day"), default="week", help="event log retention period")
    imp.add_argument("--signup-step", help="funnel table: signup step name or number (default step 1)")
    imp.add_argument("--activation-step", help="funnel table: activation step name or number")
    imp.add_argument("--kind", choices=("billing", "funnel", "retention", "events"), help="only try this kind")
    imp.add_argument("--source", metavar="FORMAT", help="force a format id (see _growthkit importers --list-formats)")
    imp.add_argument("--member", metavar="NAME", help="CSV file to read inside a .zip")
    imp.add_argument("--values", choices=("auto", "percent", "count", "fraction"), default="auto",
                     help="what retention cells hold (default auto)")
    imp.add_argument("--as-of", metavar="YYYY-MM", help="billing: month to report on")

    size = sub.add_parser("size", help="A/B test sizing for one conversion rate")
    _common(size)
    size.add_argument("--baseline", required=True, help="current rate in percent, e.g. 18 or 18%%")
    size.add_argument("--weekly", required=True, help="users entering the test per week")
    size.add_argument("--mde", default=str(DEFAULT_MDE), help="relative change to detect, percent (default 20)")
    size.add_argument("--max-weeks", type=float, default=MAX_TEST_WEEKS, help="longest acceptable test (default 4)")
    size.add_argument("--decrease", action="store_true", help="the goal is a lower rate (for example churn)")

    bench = sub.add_parser("benchmarks", help="benchmark rows for a segment")
    _common(bench)
    bench.add_argument("--category", choices=sorted(CATEGORY_METRICS), default="all")
    bench.add_argument("--motion", help="freemium_self_serve, freemium_sales_assist, trial_no_card, "
                                        "trial_card_required or reverse_trial")
    bench.add_argument("--gtm-motion", help="plg, sales-led or hybrid")
    bench.add_argument("--arr-band", help="<100k, 100k-1m, 1m-10m or 10m+")
    bench.add_argument("--arr", help="annual recurring revenue")
    bench.add_argument("--acv", help="average annual contract value")
    bench.add_argument("--arpa", help="average monthly revenue per account")
    bench.add_argument("--pricing-model", help="per-seat, usage, hybrid, flat or tiered")
    bench.add_argument("--ai-native", help="true or false")
    bench.add_argument("--b2b", help="true or false")
    bench.add_argument("--traffic-source", help="organic or paid")

    pricing = sub.add_parser("pricing", help="motion evidence from a pricing page")
    pricing.add_argument("input", nargs="?", help="pricing page URL or a saved HTML file")
    _common(pricing)
    pricing.add_argument("--timeout", type=float, default=15.0, help="network timeout in seconds (default 15)")
    return parser


HANDLERS: Dict[str, Callable[[Any], int]] = {
    "facts": cmd_facts, "score": cmd_score, "import": cmd_import, "size": cmd_size,
    "benchmarks": cmd_benchmarks, "pricing": cmd_pricing,
}


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or (argv[0] not in COMMANDS and argv[0] not in ("-h", "--help", "--version")):
        argv = ["facts"] + argv
    parser = build_parser()
    args = parser.parse_args(argv)
    return HANDLERS[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
