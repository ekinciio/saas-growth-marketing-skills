#!/usr/bin/env python3
"""SaaS subscription metrics: the deterministic half of the subscription-metrics skill.

The script computes and compares; it never grades or advises. The model
scores the five rubric dimensions in references/rubric.md from the facts
printed here, and the `score` command turns those scores into the total.

Commands (each prints one JSON document with --json; logs go to stderr):

    calc INPUT        one month of numbers (a JSON file, or '-' for stdin) ->
                      every metric with its formula, period, inputs used,
                      "not measured" reason, and the matching row of the shared
                      benchmark file with the value's position in it.
    import EXPORT     a billing export (Stripe, Paddle, Chargebee, ChartMogul,
                      Baremetrics customer x month, generic CSV) -> MRR bridge,
                      churn, 12-month cohort NRR and GRR, voluntary vs
                      involuntary churn, plan and interval mix, then the same
                      metrics as calc for the last full month. Aggregates only.
    forecast INPUT    24-month MRR projection in three scenarios from new MRR,
                      expansion and churn rates; MRR ceiling; months to
                      milestones; cash runway; lever sensitivity.
    score SCORES      weighted total of the dimension scores the model assigned
                      (na and not-measured dimensions dropped, weights
                      renormalized, no total under 60% measured weight).
    test-plan         A/B test sizing for a bet (wraps the shared stats helper).
    benchmarks        the benchmark rows this skill compares against, as JSON or
                      a Markdown table (--write-guide refreshes the guide table).

Conventions: money is in the input currency (major units); rates are percent
(3.0 means 3%); "monthly" metrics come from one month unless the input says
otherwise. A missing input is "not measured", never 0.

Exit codes (shared contract): 0 ok, 2 usage or input error, 4 partial,
5 nothing to analyze, 1 crash.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import os
import re
import sys
from collections import OrderedDict
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from _growthkit import __version__, cli, importers, stats  # noqa: E402

TOOL = "metrics_calculator"
SKILL_DIR = os.path.dirname(_HERE)
BENCHMARKS_PATH = os.path.join(SKILL_DIR, "references", "_shared", "saas-benchmarks.json")
REPORT_CONTRACT_PATH = os.path.join(SKILL_DIR, "references", "_shared", "report-contract.md")
GUIDE_PATH = os.path.join(SKILL_DIR, "references", "saas-metrics-guide.md")
DEMO_PATH = os.path.join(_HERE, "demo.json")

RUBRIC_VERSION = "rubric-v1"
RUBRIC_FILE = "references/rubric.md"

# Customer lifetime used in LTV is capped: 1 / churn explodes at low churn
# (0.1% a month would mean an 83-year customer). The cap is shown in the output.
LIFETIME_CAP_MONTHS = 60.0
# Used for LTV and CAC payback only when gross margin is not given; always
# listed under assumptions so the report can say so.
DEFAULT_GROSS_MARGIN_PCT = 70.0
DEFAULT_FORECAST_MONTHS = 24
MAX_FORECAST_MONTHS = 60
FORECAST_TRAILING_MONTHS = 3
CHURN_TRAILING_MONTHS = 6
MIN_MEASURED_SHARE = 0.6
# Bessemer's Rule of X weights growth about 2x for private companies
# (rule_of_x.bessemer.index in the benchmark file).
RULE_OF_X_GROWTH_MULTIPLIER = 2.0
# Benchmark ARR, ACV and ARPA bands are in US dollars. Bands are matched only
# for currencies of similar size; others are compared on the general rows.
BAND_CURRENCIES = ("USD", "EUR", "GBP", "CHF")
# Planning factors, not predictions; the output lists them and the input can
# override them under forecast.scenarios.
DEFAULT_SCENARIOS = OrderedDict([
    ("downside", {"new_mrr_factor": 0.8, "churn_factor": 1.25, "expansion_factor": 0.8,
                  "new_mrr_monthly_growth_pct": 0.0}),
    ("base", {"new_mrr_factor": 1.0, "churn_factor": 1.0, "expansion_factor": 1.0,
              "new_mrr_monthly_growth_pct": 0.0}),
    ("upside", {"new_mrr_factor": 1.2, "churn_factor": 0.8, "expansion_factor": 1.2,
                "new_mrr_monthly_growth_pct": 0.0}),
])
SCENARIO_KEYS = ("new_mrr_factor", "churn_factor", "expansion_factor", "new_mrr_monthly_growth_pct")
LEVER_STEP = 0.10
DEFAULT_MILESTONES = ({"label": "1M ARR", "mrr": 1000000.0 / 12.0},
                      {"label": "100K MRR", "mrr": 100000.0},
                      {"label": "5M ARR", "mrr": 5000000.0 / 12.0},
                      {"label": "10M ARR", "mrr": 10000000.0 / 12.0})

# The rubric dimensions and weights. references/rubric.md shows the same
# table; a test keeps the two equal.
DIMENSIONS = (
    ("retention", "Retention", 30),
    ("growth", "Growth", 25),
    ("unit_economics", "Unit economics", 20),
    ("efficiency", "Capital efficiency", 15),
    ("rule_of_40", "Growth and profit balance", 10),
)
GRADE_BANDS = ((85.0, "A"), (70.0, "B"), (55.0, "C"), (40.0, "D"), (0.0, "F"))
DIMENSION_METRICS = OrderedDict([
    ("retention", {"primary": ("grr_ttm", "nrr_ttm", "grr_monthly", "nrr_monthly"),
                   "supporting": ("logo_churn_monthly", "gross_mrr_churn_monthly", "expansion_rate_monthly")}),
    ("growth", {"primary": ("yoy_revenue_growth", "mrr_growth_monthly"),
                "supporting": ("mrr_growth_annualized", "quick_ratio", "net_new_mrr", "mrr_ceiling")}),
    ("unit_economics", {"primary": ("cac_payback_months",),
                        "supporting": ("ltv_to_cac", "ltv", "cac", "arpa_new")}),
    ("efficiency", {"primary": ("burn_multiple", "magic_number"),
                    "supporting": ("runway_months",)}),
    ("rule_of_40", {"primary": ("rule_of_40",), "supporting": ("rule_of_x",)}),
])

# ---------------------------------------------------------------------------
# Input schema
# ---------------------------------------------------------------------------

# kind: text | money (>= 0) | signed | count (whole, >= 0) | rate (0-100 %)
#       | growth (>= -100 %) | margin (<= 100 %) | gm (gross margin) | ttm
FIELDS = OrderedDict([
    ("period_label", ("text", "period (YYYY-MM)")),
    ("currency", ("text", "currency")),
    ("beginning_mrr", ("money", "MRR at the start of the month")),
    ("ending_mrr", ("money", "MRR at the end of the month")),
    ("new_mrr", ("money", "new MRR")),
    ("expansion_mrr", ("money", "expansion MRR")),
    ("contraction_mrr", ("money", "contraction MRR")),
    ("churned_mrr", ("money", "churned MRR")),
    ("reactivation_mrr", ("money", "reactivation MRR")),
    ("customers_start", ("count", "paying customers at the start of the month")),
    ("customers_new", ("count", "new paying customers")),
    ("customers_churned", ("count", "churned customers")),
    ("customers_end", ("count", "paying customers at the end of the month")),
    ("logo_churn_pct", ("rate", "monthly logo churn rate")),
    ("gross_revenue_churn_pct", ("rate", "monthly gross revenue churn rate")),
    ("avg_logo_churn_pct", ("rate", "average monthly logo churn over several months")),
    ("avg_months", ("count", "months in the churn average")),
    ("arpa", ("money", "average MRR per paying customer")),
    ("sales_marketing_spend", ("money", "sales and marketing spend this month")),
    ("gross_margin_pct", ("gm", "gross margin")),
    ("net_burn", ("signed", "net burn this month")),
    ("total_operating_costs", ("money", "total operating costs this month")),
    ("cash_balance", ("money", "cash balance")),
    ("yoy_revenue_growth_pct", ("growth", "year-over-year revenue growth")),
    ("profit_margin_pct", ("margin", "profit margin (EBITDA or free cash flow)")),
    ("margin_basis", ("text", "profit margin basis")),
    ("prev_quarter_sm_spend", ("money", "sales and marketing spend last quarter")),
    ("current_quarter_net_new_arr", ("signed", "net new ARR this quarter")),
    ("ttm_nrr_pct", ("ttm", "12-month cohort NRR")),
    ("ttm_grr_pct", ("ttm", "12-month cohort GRR")),
    ("committed_mrr", ("money", "committed subscription MRR")),
    ("usage_mrr", ("money", "usage-based MRR (last month)")),
])
ALIASES = {
    "total_sales_marketing_spend": "sales_marketing_spend",
    "sm_spend": "sales_marketing_spend",
    "mrr": "ending_mrr",
    "current_mrr": "ending_mrr",
    "starting_mrr": "beginning_mrr",
    "monthly_net_burn": "net_burn",
}
OBJECT_KEYS = ("segment", "forecast", "forecast_basis")
MRR_MOVEMENTS = ("new_mrr", "expansion_mrr", "contraction_mrr", "churned_mrr")

MOTIONS = {"plg": "plg", "product-led": "plg", "product_led": "plg", "self-serve": "plg",
           "sales-led": "sales_led", "sales_led": "sales_led", "hybrid": "hybrid"}
PRICING = {"per-seat": "seat", "per_seat": "seat", "seat": "seat", "seats": "seat",
           "usage": "usage", "usage-based": "usage", "usage_based": "usage", "hybrid": "hybrid",
           "flat": "non_seat_subscription", "tiered": "non_seat_subscription",
           "non_seat_subscription": "non_seat_subscription", "free": None}
FUNDING = {"bootstrapped": "bootstrapped", "equity-backed": "equity_backed",
           "equity_backed": "equity_backed", "vc": "equity_backed", "vc-backed": "equity_backed",
           "venture": "equity_backed"}
CONTRACTS = {"monthly": "month_to_month", "month-to-month": "month_to_month",
             "month_to_month": "month_to_month", "annual": "annual", "yearly": "annual",
             "multi-year": "multi_year", "multi_year": "multi_year"}
VERTICALS = {"vertical": "vertical", "horizontal": "horizontal"}
BUSINESS = {"b2b": "b2b_saas", "b2b_saas": "b2b_saas", "b2c": "b2c_saas", "b2c_saas": "b2c_saas"}
# growth-context.md arr_band values -> [low, high) in currency units.
ARR_BAND_CONTEXT = {"none": (0.0, 0.0), "<100k": (0.0, 1e5), "100k-1m": (1e5, 1e6),
                    "1m-10m": (1e6, 1e7), "10m+": (1e7, math.inf)}
MARGIN_BASES = {"ebitda": "ebitda", "fcf": "fcf", "free cash flow": "fcf", "free_cash_flow": "fcf",
                "operating": "operating", "net": "net"}


class InputError(Exception):
    """Unreadable or impossible input. Holds every problem found, for one fix round."""

    def __init__(self, errors: List[str]) -> None:
        super().__init__("; ".join(errors))
        self.errors = list(errors)


class MissingInputs(Exception):
    """A command cannot run without these inputs (exit 2, listed in missing_inputs)."""

    def __init__(self, missing: List[str], message: str) -> None:
        super().__init__(message)
        self.missing = list(missing)


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _r(value: Optional[float], digits: int = 2) -> Optional[float]:
    if value is None:
        return None
    value = float(value)
    if not math.isfinite(value):
        return None
    result = round(value, digits)
    return 0.0 if result == 0 else result


def _num_text(value: float) -> str:
    """1500.0 -> '1,500'; 0.75 -> '0.75' (for messages)."""
    if float(value).is_integer():
        return "{:,}".format(int(value))
    return "{:,}".format(round(value, 4))


def monthly_equivalent_pct(annual_pct: float) -> float:
    """Annual retention -> constant monthly rate: (annual / 100) ** (1/12) * 100."""
    return 100.0 * (annual_pct / 100.0) ** (1.0 / 12.0)


def annualize_monthly_pct(monthly_pct: float) -> float:
    """Monthly retention -> annual if the month repeated: (monthly / 100) ** 12 * 100."""
    return 100.0 * (monthly_pct / 100.0) ** 12


def annual_churn_from_monthly(monthly_pct: float) -> float:
    """Monthly logo churn -> annual: 1 - (1 - monthly) ** 12."""
    return 100.0 * (1.0 - (1.0 - monthly_pct / 100.0) ** 12)


def _is_month(text: Optional[str]) -> bool:
    return bool(text) and bool(re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", str(text)))


def scoring_mode() -> Tuple[str, Optional[str]]:
    """The report contract's scoring switch, read from the synced copy."""
    try:
        with open(REPORT_CONTRACT_PATH, encoding="utf-8") as handle:
            text = handle.read()
    except OSError:
        return "rubric", "references/_shared/report-contract.md not found; assumed scoring_mode rubric."
    match = re.search(r"^scoring_mode: *(deterministic|rubric|none) *$", text, re.M)
    if not match:
        return "rubric", "No scoring_mode line in report-contract.md; assumed rubric."
    return match.group(1), None


# ---------------------------------------------------------------------------
# Input loading
# ---------------------------------------------------------------------------


def _coerce_field(name: str, kind: str, raw: Any, errors: List[str], warnings: List[str]) -> Any:
    try:
        if kind == "text":
            return cli.to_text(raw, name)
        if cli.is_missing(raw):
            return None
        if kind in ("money", "count"):
            value = cli.to_number(raw, name)
            if value < 0:
                hint = ""
                if name in ("contraction_mrr", "churned_mrr"):
                    hint = " Enter MRR lost as a positive amount (e.g. 2000, not -2000)."
                errors.append("%s: %s cannot be negative.%s" % (name, _num_text(value), hint))
                return None
            if kind == "count":
                if not float(value).is_integer():
                    errors.append("%s: %s is not a whole number of customers." % (name, _num_text(value)))
                    return None
                return int(value)
            return value
        if kind == "signed":
            return cli.to_number(raw, name)
        if kind == "rate":
            value = cli.to_percent(raw, name, minimum=0, maximum=100)
            if value is not None and 0 < value < 0.1 and name != "avg_months":
                warnings.append(
                    "%s is read as %s%% a month. If you meant %s%%, enter %s."
                    % (name, _num_text(value), _num_text(value * 100), _num_text(value * 100)))
            return value
        if kind == "growth":
            value = cli.to_percent(raw, name)
            if value is not None and value < -100:
                errors.append("%s: %s%% is impossible; revenue cannot fall by more than 100%%."
                              % (name, _num_text(value)))
                return None
            return value
        if kind == "margin":
            value = cli.to_percent(raw, name)
            if value is not None and value > 100:
                errors.append("%s: %s%% is impossible; a margin cannot exceed 100%%." % (name, _num_text(value)))
                return None
            return value
        if kind == "gm":
            value = cli.to_percent(raw, name, assume_fraction=True)
            if value is None:
                return None
            if not 0 < value <= 100:
                errors.append(
                    "gross_margin_pct: %s is not a valid gross margin. Use a percent above 0 and up to "
                    "100 (e.g. 75) or a fraction (e.g. 0.75)." % _num_text(value))
                return None
            return value
        if kind == "ttm":
            value = cli.to_number(raw, name)
            if value is None:
                return None
            if 0 < value <= 2:
                if name == "ttm_grr_pct" and value > 1:
                    errors.append(
                        "ttm_grr_pct: %g read as a fraction is %.0f%%, but GRR cannot exceed 100%% because "
                        "it excludes expansion. Enter a percent (e.g. 92)." % (value, value * 100))
                    return None
                warnings.append("%s: read %g as a fraction, i.e. %.1f%%. Enter percents (e.g. 92) to avoid "
                                "this." % (name, value, value * 100))
                value *= 100.0
            if name == "ttm_grr_pct" and not 0 <= value <= 100:
                errors.append("ttm_grr_pct: %s%% is impossible; GRR is between 0%% and 100%% because it "
                              "excludes expansion." % _num_text(value))
                return None
            if name == "ttm_nrr_pct" and value < 0:
                errors.append("ttm_nrr_pct: %s%% cannot be negative." % _num_text(value))
                return None
            return value
    except cli.CoercionError as exc:
        errors.append("%s. Use digits (e.g. 15000), or leave the field out if you do not know it." % exc)
        return None
    raise ValueError("unknown field kind %r" % kind)


def _normalize_segment(raw: Any, errors: List[str], warnings: List[str]) -> Dict[str, Any]:
    """Company segment used to pick benchmark rows (growth-context.md fields)."""
    seg: Dict[str, Any] = {}
    if raw is None:
        return seg
    if not isinstance(raw, dict):
        errors.append("segment: expected an object such as {\"gtm_motion\": \"plg\"}, got %s."
                      % type(raw).__name__)
        return seg

    def pick(keys: Tuple[str, ...], table: Dict[str, Any], label: str) -> None:
        for key in keys:
            value = raw.get(key)
            if cli.is_missing(value):
                continue
            token = str(value).strip().lower()
            if token in table:
                if table[token] is not None:
                    seg[label] = table[token]
            else:
                warnings.append("segment.%s %r is not one of %s; it was ignored for benchmark matching."
                                % (key, value, ", ".join(sorted(table))))
            return

    pick(("gtm_motion", "motion"), MOTIONS, "motion")
    pick(("pricing_model",), PRICING, "pricing_model")
    pick(("funding",), FUNDING, "funding")
    pick(("contract_term",), CONTRACTS, "contract_term")
    pick(("vertical",), VERTICALS, "vertical")
    pick(("business_model",), BUSINESS, "business_model")
    try:
        acv = cli.to_number(raw.get("acv"), "segment.acv", minimum=0)
        if acv is not None:
            seg["acv"] = acv
        ai = cli.to_bool(raw.get("ai_native"), "segment.ai_native")
        if ai is not None:
            seg["ai_native"] = ai
    except cli.CoercionError as exc:
        errors.append(str(exc))
    band = raw.get("arr_band")
    if not cli.is_missing(band):
        token = str(band).strip().lower().replace(" ", "")
        if token in ARR_BAND_CONTEXT:
            seg["arr_band"] = token
        else:
            warnings.append("segment.arr_band %r is not one of %s; it was ignored."
                            % (band, ", ".join(ARR_BAND_CONTEXT)))
    stage = raw.get("stage")
    if not cli.is_missing(stage):
        seg["stage"] = str(stage).strip().lower()
    unknown = sorted(k for k in raw if k not in (
        "gtm_motion", "motion", "pricing_model", "funding", "contract_term", "vertical",
        "business_model", "acv", "ai_native", "arr_band", "stage"))
    if unknown:
        warnings.append("Ignored unknown segment field(s): %s" % ", ".join(unknown))
    return seg


def _normalize_forecast_basis(raw: Any, errors: List[str]) -> Optional[Dict[str, Any]]:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        errors.append("forecast_basis: expected an object.")
        return None
    out: Dict[str, Any] = {}
    try:
        out["avg_new_mrr"] = cli.to_number(raw.get("avg_new_mrr"), "forecast_basis.avg_new_mrr", minimum=0)
        out["avg_expansion_rate_pct"] = cli.to_percent(raw.get("avg_expansion_rate_pct"),
                                                       "forecast_basis.avg_expansion_rate_pct", minimum=0)
        out["avg_gross_churn_rate_pct"] = cli.to_percent(raw.get("avg_gross_churn_rate_pct"),
                                                         "forecast_basis.avg_gross_churn_rate_pct",
                                                         minimum=0, maximum=100)
        out["months"] = cli.to_int(raw.get("months"), "forecast_basis.months", minimum=1)
    except cli.CoercionError as exc:
        errors.append(str(exc))
        return None
    out["source"] = cli.to_text(raw.get("source")) if isinstance(raw.get("source"), str) else None
    return out


def load_inputs(payload: Any) -> Dict[str, Any]:
    """Validate a raw JSON payload. Returns {"values", "meta", "warnings", "notes"}.

    Raises InputError listing every unreadable or impossible value.
    """
    if not isinstance(payload, dict):
        raise InputError(["Input must be a JSON object such as {\"beginning_mrr\": 100000}, got %s."
                          % type(payload).__name__])
    errors: List[str] = []
    warnings: List[str] = []
    notes: List[str] = []

    raw: Dict[str, Any] = {}
    for key, value in payload.items():
        if key in FIELDS:
            raw[key] = value
    for key, value in payload.items():
        name = ALIASES.get(key)
        if name is None:
            continue
        if name in raw and not cli.is_missing(raw[name]):
            if not cli.is_missing(value):
                warnings.append("Both %s and %s were given; %s was used." % (key, name, name))
            continue
        raw[name] = value
    unknown = sorted(str(k) for k in payload
                     if k not in FIELDS and k not in ALIASES and k not in OBJECT_KEYS
                     and not str(k).startswith("_"))
    if unknown:
        warnings.append("Ignored unknown field(s): %s" % ", ".join(unknown))

    values: Dict[str, Any] = OrderedDict()
    for name, (kind, _label) in FIELDS.items():
        values[name] = _coerce_field(name, kind, raw.get(name), errors, warnings)

    currency = values.get("currency")
    if currency is not None:
        currency = currency.upper()
        if not re.fullmatch(r"[A-Z]{3}", currency):
            errors.append("currency: %r is not a 3-letter ISO 4217 code such as USD or EUR." % values["currency"])
            currency = None
        values["currency"] = currency
    basis = values.get("margin_basis")
    if basis is not None:
        token = basis.strip().lower()
        if token in MARGIN_BASES:
            values["margin_basis"] = MARGIN_BASES[token]
        else:
            warnings.append("margin_basis %r is not one of ebitda, fcf, operating, net; it was ignored." % basis)
            values["margin_basis"] = None

    segment = _normalize_segment(payload.get("segment"), errors, warnings)
    forecast_basis = _normalize_forecast_basis(payload.get("forecast_basis"), errors)
    forecast_opts = payload.get("forecast")
    if forecast_opts is not None and not isinstance(forecast_opts, dict):
        errors.append("forecast: expected an object such as {\"months\": 24}.")
        forecast_opts = None

    errors.extend(_cross_field_errors(values))
    if errors:
        raise InputError(errors)
    warnings.extend(_sanity_warnings(values))
    meta = {
        "segment": segment,
        "forecast": forecast_opts or {},
        "forecast_basis": forecast_basis,
        "ttm_grr_basis": payload.get("_ttm_grr_basis"),
        "source": payload.get("_source") if isinstance(payload.get("_source"), dict) else None,
    }
    return {"values": values, "meta": meta, "warnings": warnings, "notes": notes}


def _cross_field_errors(v: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    start, new, churned = v["customers_start"], v["customers_new"], v["customers_churned"]
    if start is not None and churned is not None:
        available = start + (new or 0)
        if churned > available:
            detail = ("the %s customers at the start of the month" % "{:,}".format(start) if new is None else
                      "the %s customers available (%s at the start + %s new)"
                      % ("{:,}".format(available), "{:,}".format(start), "{:,}".format(new)))
            errors.append("customers_churned: %s churned is more than %s. Check that all counts cover the "
                          "same month." % ("{:,}".format(churned), detail))
    b = v["beginning_mrr"]
    if b is not None and all(v[name] is not None for name in MRR_MOVEMENTS):
        lost = v["contraction_mrr"] + v["churned_mrr"]
        available_mrr = b + v["new_mrr"] + v["expansion_mrr"] + (v["reactivation_mrr"] or 0.0)
        if lost > available_mrr:
            errors.append(
                "churned_mrr + contraction_mrr (%s) is more than the %s of MRR the month had; ending MRR "
                "would be negative. Check that all MRR figures cover the same month."
                % (_num_text(lost), _num_text(available_mrr)))
    return errors


def _sanity_warnings(v: Dict[str, Any]) -> List[str]:
    """Possible but suspicious values: usually an annual or quarterly figure typed as monthly."""
    warnings: List[str] = []
    b = v["beginning_mrr"]
    if b:
        for name in ("new_mrr", "expansion_mrr"):
            value = v[name]
            if value is not None and value > 0.5 * b:
                warnings.append("%s (%s) is more than half of starting MRR (%s). If it is a quarterly or "
                                "annual total, enter one month only." % (name, _num_text(value), _num_text(b)))
        lost = (v["contraction_mrr"] or 0.0) + (v["churned_mrr"] or 0.0)
        if lost > b:
            warnings.append("Churned plus contraction MRR exceed starting MRR; monthly GRR is floored at 0%.")
        elif lost > 0.15 * b:
            warnings.append("Revenue churn is %.1f%% of starting MRR in one month. Confirm churned and "
                            "contraction MRR are monthly figures." % (lost / b * 100))
        big = ["%s %s" % (FIELDS[n][1], _num_text(v[n]))
               for n in ("sales_marketing_spend", "total_operating_costs", "net_burn")
               if v[n] is not None and v[n] > 5 * b]
        if big:
            warnings.append("More than 5x starting MRR (%s): %s. That can be normal early on, but if any is a "
                            "quarterly or annual total, enter one month only." % (_num_text(b), "; ".join(big)))
    start, churned = v["customers_start"], v["customers_churned"]
    if start and churned is not None and churned / start > 0.15:
        warnings.append("Logo churn is %.1f%% in one month. Confirm these are monthly counts, not annual."
                        % (churned / start * 100))
    gm = v["gross_margin_pct"]
    if gm is not None and gm < 20:
        warnings.append("Gross margin is read as %s%%, unusually low for software. Enter 75 or 0.75 for 75%%."
                        % _num_text(gm))
    for name in ("yoy_revenue_growth_pct", "profit_margin_pct"):
        value = v[name]
        if value is not None and value != 0 and -1 < value < 1:
            warnings.append("%s is %g, which is read as %g%%. If you meant %g%%, enter %g."
                            % (name, value, value, value * 100, value * 100))
    if v["ttm_nrr_pct"] is not None and v["ttm_nrr_pct"] > 200:
        warnings.append("ttm_nrr_pct is above 200%, which is unusual. Confirm it is a 12-month cohort figure.")
    return warnings


# ---------------------------------------------------------------------------
# Benchmarks
# ---------------------------------------------------------------------------

BENCH_SPECS = OrderedDict([
    ("grr_ttm", {"metric": "grr", "periods": ("annual",), "compare": "annual"}),
    ("nrr_ttm", {"metric": "nrr", "periods": ("annual",), "compare": "annual"}),
    ("grr_monthly", {"metric": "grr", "periods": ("annual",), "compare": "monthly_equivalent"}),
    ("nrr_monthly", {"metric": "nrr", "periods": ("annual",), "compare": "monthly_equivalent"}),
    ("logo_churn_monthly", {"metric": "logo_churn", "periods": ("monthly",), "compare": "monthly"}),
    ("cac_payback_months", {"metric": "cac_payback", "periods": ("point_in_time",), "compare": "point_in_time"}),
    ("ltv_to_cac", {"metric": "ltv_to_cac", "periods": ("point_in_time",), "compare": "point_in_time"}),
    ("rule_of_40", {"metric": "rule_of_40", "periods": ("annual",), "compare": "annual"}),
    ("rule_of_x", {"metric": "rule_of_x", "periods": ("annual",), "compare": "annual"}),
    ("burn_multiple", {"metric": "burn_multiple", "periods": ("annual",), "compare": "rule_of_thumb"}),
    ("magic_number", {"metric": "magic_number", "periods": ("quarterly",), "compare": "quarterly"}),
    ("quick_ratio", {"metric": "quick_ratio", "periods": ("monthly",), "compare": "rule_of_thumb"}),
    ("yoy_revenue_growth", {"metric": "arr_growth", "periods": ("annual",), "compare": "annual"}),
    ("mrr_growth_annualized", {"metric": "arr_growth", "periods": ("annual",),
                               "compare": "annual (one month annualized)"}),
])
_CONFIDENCE_RANK = {"high": 3, "medium": 2, "low": 1}
_BAND_RE = re.compile(
    r"^\s*(<=|>=|<|>)?\s*\$?\s*(-?[\d.]+)\s*([KMB])?\s*(?:-\s*\$?\s*([\d.]+)\s*([KMB])?)?\s*(%|/month)?\s*$",
    re.I)
_SUFFIX = {"k": 1e3, "m": 1e6, "b": 1e9}


def parse_band(text: Any) -> Optional[Tuple[float, bool, float, bool]]:
    """'<$5M' -> (-inf, False, 5e6, False); '$1M-$3M' -> (1e6, True, 3e6, True)."""
    if not isinstance(text, str):
        return None
    match = _BAND_RE.match(text)
    if not match:
        return None
    op, first, first_suffix, second, second_suffix, _unit = match.groups()
    try:
        low = float(first) * _SUFFIX.get((first_suffix or "").lower(), 1.0)
        high = float(second) * _SUFFIX.get((second_suffix or "").lower(), 1.0) if second else None
    except ValueError:
        return None
    if high is not None:
        if op:
            return None
        return (low, True, high, True)
    if op == "<":
        return (-math.inf, False, low, False)
    if op == "<=":
        return (-math.inf, False, low, True)
    if op == ">":
        return (low, False, math.inf, False)
    if op == ">=":
        return (low, True, math.inf, False)
    return None


def _contains(band: Tuple[float, bool, float, bool], value: float) -> bool:
    low, low_incl, high, high_incl = band
    above = value > low or (low_incl and value == low)
    below = value < high or (high_incl and value == high)
    return above and below


def _member(band: Tuple[float, bool, float, bool], user: Any) -> bool:
    """True only when the user certainly belongs to the band (a point or a [low, high) range)."""
    if isinstance(user, tuple):
        low, high = user
        if not _contains(band, low):
            return False
        if high == math.inf:
            return band[2] == math.inf
        b_high, b_high_incl = band[2], band[3]
        return high <= b_high if not b_high_incl else high <= b_high + 1e-9
    return _contains(band, float(user))


def _band_distance(band: Tuple[float, bool, float, bool], user: Any) -> float:
    if user is None:
        return 0.5
    point = float(user[0] if isinstance(user, tuple) else user)
    if _contains(band, point):
        return 0.0
    edges = [edge for edge in (band[0], band[2]) if math.isfinite(edge) and edge > 0]
    if point <= 0 or not edges:
        return 1.0
    return min(abs(math.log(point / edge)) for edge in edges)


_NUMERIC_DIMS = (
    # (label, where in the row, seg key, weight)
    ("arr_band", "segment", "arr", 4),
    ("acv_band", "segment", "acv", 4),
    ("arpa_band", "extra", "arpa", 4),
    ("price_point", "extra", "arpa", 3),
    ("growth_band", "extra", "growth_pct", 1),
)
_CATEGORY_DIMS = (
    ("pricing_model", "segment", "pricing_model", 3),
    ("motion", "segment", "motion", 2),
    ("funding", "extra", "funding", 2),
    ("contract_term", "extra", "contract_term", 1),
    ("vertical", "extra", "vertical", 1),
)
_KNOWN_EXTRA = {"arpa_band", "price_point", "growth_band", "funding", "contract_term", "vertical",
                "company_type", "cohort"}


def _row_value(row: Dict[str, Any], where: str, label: str) -> Any:
    segment = row.get("segment") or {}
    if where == "extra":
        return (segment.get("extra") or {}).get(label)
    return segment.get(label)


def match_row(row: Dict[str, Any], seg: Dict[str, Any]) -> Optional[Tuple[int, List[str]]]:
    """(score, matched dimensions) when the user is certainly inside the row's segment, else None."""
    segment = row.get("segment") or {}
    extra = segment.get("extra") or {}
    if any(key not in _KNOWN_EXTRA for key in extra):
        return None
    if extra.get("cohort"):
        return None
    company = extra.get("company_type")
    if company == "public_cloud":
        return None
    if company == "b2c_saas" and seg.get("business_model") != "b2c_saas":
        return None
    if company == "b2b_saas" and seg.get("business_model") == "b2c_saas":
        return None
    score = 0
    matched: List[str] = []
    for label, where, key, weight in _NUMERIC_DIMS:
        band_text = _row_value(row, where, label)
        if band_text in (None, "all"):
            continue
        band = parse_band(band_text)
        user = seg.get(key)
        if band is None or user is None or not _member(band, user):
            return None
        score += weight
        matched.append("%s %s" % (label, band_text))
    for label, where, key, weight in _CATEGORY_DIMS:
        value = _row_value(row, where, label)
        if value in (None, "all"):
            continue
        if seg.get(key) != value:
            return None
        score += weight
        matched.append("%s %s" % (label, value))
    ai_native = segment.get("ai_native")
    if ai_native is True:
        if seg.get("ai_native") is not True:
            return None
        score += 2
        matched.append("ai_native")
    elif ai_native is False and seg.get("ai_native") is True:
        return None
    return score, matched


def _fallback_distance(row: Dict[str, Any], seg: Dict[str, Any]) -> float:
    segment = row.get("segment") or {}
    extra = segment.get("extra") or {}
    distance = 3.0 if extra.get("cohort") else 0.0
    for label, where, key, _weight in _NUMERIC_DIMS:
        band_text = _row_value(row, where, label)
        if band_text in (None, "all"):
            continue
        band = parse_band(band_text)
        distance += 1.0 if band is None else _band_distance(band, seg.get(key))
    for label, where, key, _weight in _CATEGORY_DIMS:
        value = _row_value(row, where, label)
        if value not in (None, "all") and seg.get(key) != value:
            distance += 1.0
    if segment.get("ai_native") is True and seg.get("ai_native") is not True:
        distance += 1.0
    if extra.get("company_type") in ("public_cloud", "b2c_saas"):
        distance += 1.0
    return distance


def segment_text(row: Dict[str, Any]) -> str:
    segment = row.get("segment") or {}
    parts = []
    if segment.get("motion") not in (None, "all"):
        parts.append("%s motion" % segment["motion"])
    if segment.get("arr_band") not in (None, "all"):
        parts.append("ARR %s" % segment["arr_band"])
    if segment.get("acv_band") not in (None, "all"):
        parts.append("ACV %s" % segment["acv_band"])
    if segment.get("pricing_model") not in (None, "all"):
        parts.append("%s pricing" % segment["pricing_model"].replace("_", " "))
    if segment.get("ai_native") is True:
        parts.append("AI-native")
    elif segment.get("ai_native") is False:
        parts.append("not AI-native")
    for key, value in sorted((segment.get("extra") or {}).items()):
        parts.append("%s %s" % (key.replace("_", " "), str(value).replace("_", " ")))
    return ", ".join(parts) if parts else "all companies in the sample"


def _row_stats(row: Dict[str, Any], compare: str) -> Dict[str, float]:
    if compare == "monthly_equivalent":
        source = row.get("monthly_equivalent") or {}
        keys = ("p25", "median", "p75", "p90", "value")
    else:
        source = row
        keys = ("p25", "median", "p75", "p90", "mean", "value")
    return OrderedDict((key, source[key]) for key in keys if isinstance(source.get(key), (int, float)))


def performance(value: float, row_stats: Dict[str, float], thresholds: Optional[List[Dict[str, Any]]],
                direction: str) -> Tuple[str, str]:
    """(performance tier, plain position) of a value against one benchmark row.

    Tiers: top_decile, top_quartile, above_median (at or above), below_median,
    bottom_quartile; better/worse_than_mean or _reported_value for rows with
    one figure; the rule-of-thumb band label for threshold rows. Lower-is-better
    metrics (CAC payback) are mirrored: p25 is the efficient edge.
    """
    v = round(float(value), 2)
    cuts = OrderedDict((k, round(float(row_stats[k]), 2)) for k in ("p25", "median", "p75", "p90")
                       if k in row_stats)
    if direction == "context":
        return "context", "context only"
    lower = direction == "lower_is_better"
    if cuts:
        names = list(cuts)
        if v < cuts[names[0]]:
            position = "below %s (%s)" % (names[0], _num_text(cuts[names[0]]))
        elif v >= cuts[names[-1]]:
            position = "at or above %s (%s)" % (names[-1], _num_text(cuts[names[-1]]))
        else:
            for low, high in zip(names, names[1:]):
                if cuts[low] <= v < cuts[high]:
                    position = "between %s (%s) and %s (%s)" % (
                        low, _num_text(cuts[low]), high, _num_text(cuts[high]))
                    break
        if lower:
            for key, tier in (("p25", "top_quartile"), ("median", "above_median"), ("p75", "below_median")):
                if key in cuts and v <= cuts[key]:
                    return tier, position
            if "p75" in cuts:
                return "bottom_quartile", position
            if "median" in cuts:
                return "below_median", position
            return "outside_top_quartile", position
        for key, tier in (("p90", "top_decile"), ("p75", "top_quartile"), ("median", "above_median"),
                          ("p25", "below_median")):
            if key in cuts and v >= cuts[key]:
                return tier, position
        if "p25" in cuts:
            return "bottom_quartile", position
        if "median" in cuts:
            return "below_median", position
        return "below_%s" % names[0], position
    for key, label in (("mean", "mean"), ("value", "reported_value")):
        if key in row_stats:
            ref = round(float(row_stats[key]), 2)
            better = v <= ref if lower else v >= ref
            word = "at or below" if v <= ref else "above"
            if not lower:
                word = "at or above" if v >= ref else "below"
            return ("better_than_%s" % label if better else "worse_than_%s" % label,
                    "%s the %s (%s)" % (word, label.replace("_", " "), _num_text(ref)))
    if thresholds:
        for band in thresholds:
            low = band.get("min")
            high = band.get("max")
            if (low is None or v >= low) and (high is None or v < high):
                return band["label"], "in the '%s' band (%s)" % (band["label"], _band_text(band))
        return "between_bands", "outside every rule-of-thumb band (%s)" % "; ".join(
            "%s %s" % (b["label"], _band_text(b)) for b in thresholds)
    return "unknown", "no comparable figure in the row"


def _band_text(band: Dict[str, Any]) -> str:
    low, high = band.get("min"), band.get("max")
    if low is not None and high is not None:
        return "%s to under %s" % (_num_text(low), _num_text(high))
    if low is not None:
        return "%s or more" % _num_text(low)
    if high is not None:
        return "under %s" % _num_text(high)
    return "any"


class Benchmarks:
    """Reads references/_shared/saas-benchmarks.json and picks the closest row per metric."""

    def __init__(self, path: str = BENCHMARKS_PATH) -> None:
        self.path = path
        self.error: Optional[str] = None
        self.rows: List[Dict[str, Any]] = []
        self.last_verified: Optional[str] = None
        try:
            with open(path, encoding="utf-8") as handle:
                data = json.load(handle)
            self.rows = [row for row in data.get("rows", []) if isinstance(row, dict)]
            self.last_verified = data.get("last_verified")
        except (OSError, ValueError) as exc:
            self.error = "Benchmark file not readable (%s): %s" % (os.path.basename(path), exc)

    def candidates(self, key: str) -> List[Dict[str, Any]]:
        spec = BENCH_SPECS[key]
        return [row for row in self.rows if row.get("metric") == spec["metric"]
                and row.get("period") in spec["periods"] and row.get("verified") is True]

    def select(self, key: str, seg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        rows = self.candidates(key)
        if not rows:
            return None
        matched = []
        for index, row in enumerate(rows):
            result = match_row(row, seg)
            if result is not None:
                matched.append((result[0], result[1], index, row))

        def rank(item: Tuple[Any, ...]) -> Tuple[Any, ...]:
            score, _m, index, row = item
            n_stats = sum(1 for k in ("p25", "median", "p75", "p90") if row.get(k) is not None)
            return (-score, -(row.get("year") or 0), -_CONFIDENCE_RANK.get(row.get("confidence"), 0),
                    -n_stats, index)

        if matched:
            matched.sort(key=rank)
            best = matched[0]
            others = [item for item in matched[1:] if item[0] > 0][:2]
            general = next((item for item in matched[1:] if item[0] == 0), None)
            if general is not None and best[0] > 0:
                others.append(general)
            return {"row": best[3], "match": "segment" if best[0] > 0 else "general",
                    "matched_on": best[1], "others": [item[3] for item in others[:3]]}
        ranked = sorted(enumerate(rows), key=lambda item: (
            _fallback_distance(item[1], seg), -(item[1].get("year") or 0),
            -_CONFIDENCE_RANK.get(item[1].get("confidence"), 0), item[0]))
        return {"row": ranked[0][1], "match": "different_segment", "matched_on": [],
                "others": [item[1] for item in ranked[1:3]]}

    def describe(self, row: Dict[str, Any], key: str, value: Optional[float], full: bool) -> Dict[str, Any]:
        spec = BENCH_SPECS[key]
        row_stats = _row_stats(row, spec["compare"])
        out: Dict[str, Any] = OrderedDict()
        out["row_id"] = row["id"]
        out["source"] = row.get("source_name")
        out["year"] = row.get("year")
        out["segment"] = segment_text(row)
        out["compare_on"] = spec["compare"]
        out["stats"] = OrderedDict((k, _r(x, 2)) for k, x in row_stats.items())
        if row.get("thresholds"):
            out["thresholds"] = [OrderedDict((k, band[k]) for k in ("label", "min", "max") if k in band)
                                 for band in row["thresholds"]]
        out["direction"] = row.get("direction")
        if value is not None:
            tier, position = performance(value, row_stats, row.get("thresholds"), row.get("direction"))
            out["performance"] = tier
            out["position"] = position
        if full:
            out["confidence"] = row.get("confidence")
            out["data_period"] = row.get("data_period")
            out["sample_size"] = row.get("sample_size")
            out["url"] = row.get("source_url")
            out["definition"] = row.get("definition")
            if row.get("value_note"):
                out["caveat"] = row["value_note"]
            if spec["compare"] == "monthly_equivalent":
                out["annual_stats"] = OrderedDict(
                    (k, row[k]) for k in ("p25", "median", "p75", "p90", "value") if row.get(k) is not None)
        return out

    def compare(self, key: str, value: Optional[float], seg: Dict[str, Any],
                state: Optional[str] = None) -> Optional[Dict[str, Any]]:
        if key not in BENCH_SPECS or not self.rows:
            return None
        selected = self.select(key, seg)
        if selected is None:
            return None
        primary = self.describe(selected["row"], key, value, full=True)
        primary["match"] = selected["match"]
        if selected["matched_on"]:
            primary["matched_on"] = selected["matched_on"]
        if state is not None:
            primary["performance"] = state
            primary["position"] = "not comparable (%s)" % state.replace("_", " ")
        also = [self.describe(row, key, value if state is None else None, full=False)
                for row in selected["others"]]
        if also:
            primary["also"] = also
        return primary


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


def _derive_segment(seg_in: Dict[str, Any], values: Dict[str, Any], metrics: Dict[str, Any],
                    notes: List[str]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Segment used for benchmark matching, plus a description for the report."""
    currency = values.get("currency") or "USD"
    bands_ok = currency in BAND_CURRENCIES
    seg: Dict[str, Any] = {}
    shown: Dict[str, Any] = OrderedDict([("currency", currency)])

    def measured(key: str) -> Optional[float]:
        entry = metrics.get(key) or {}
        return entry.get("value") if entry.get("status") == "measured" else None

    arr = measured("arr")
    if arr is not None:
        shown["arr"] = _r(arr)
        shown["arr_source"] = "computed from MRR"
        seg["arr"] = arr
    elif seg_in.get("arr_band"):
        seg["arr"] = ARR_BAND_CONTEXT[seg_in["arr_band"]]
        if seg_in["arr_band"] == "none":
            seg["arr"] = 0.0
        shown["arr_band"] = seg_in["arr_band"]
        shown["arr_source"] = "segment.arr_band"
    arpa = measured("arpa")
    if arpa is not None:
        seg["arpa"] = arpa
        shown["arpa_monthly"] = _r(arpa)
    if seg_in.get("acv") is not None:
        seg["acv"] = seg_in["acv"]
        shown["acv"] = _r(seg_in["acv"])
        shown["acv_source"] = "segment.acv"
    elif arpa is not None:
        seg["acv"] = arpa * 12
        shown["acv"] = _r(arpa * 12)
        shown["acv_source"] = "ARPA x 12"
    growth = values.get("yoy_revenue_growth_pct")
    if growth is not None:
        seg["growth_pct"] = growth
    for key in ("motion", "pricing_model", "ai_native", "funding", "contract_term", "vertical",
                "business_model", "stage"):
        if key in seg_in:
            seg[key] = seg_in[key]
            shown[key] = seg_in[key]
    if not bands_ok:
        for key in ("arr", "acv", "arpa"):
            seg.pop(key, None)
        notes.append("Benchmark ARR, ACV and ARPA bands are in US dollars, so %s amounts were not matched to "
                     "them; rows were chosen on the other segment fields." % currency)
    shown["bands_matched"] = bands_ok
    return seg, shown


def compute(values: Dict[str, Any], meta: Dict[str, Any], bench: Optional[Benchmarks] = None) -> Dict[str, Any]:
    """All metrics from validated inputs. Pure: no I/O except the benchmark object passed in."""
    v = values
    notes: List[str] = []
    assumptions: List[str] = []
    warnings: List[str] = []
    metrics: Dict[str, Dict[str, Any]] = OrderedDict()
    needs: Dict[str, List[str]] = OrderedDict()
    currency = v.get("currency") or "USD"
    exported = (meta.get("source") or {}).get("fields") or []

    def origin(field: str) -> str:
        return "export" if field in exported else "input"

    def put(key: str, value: Optional[float], unit: str, period: str, formula: str, digits: int = 2,
            basis: str = "computed", **extra: Any) -> Dict[str, Any]:
        entry: Dict[str, Any] = OrderedDict()
        entry["status"] = "measured"
        entry["value"] = _r(value, digits) if value is not None else None
        entry["unit"] = unit
        entry["period"] = period
        entry["basis"] = basis
        entry["formula"] = formula
        for name, item in extra.items():
            if item is not None:
                entry[name] = item
        metrics[key] = entry
        return entry

    def missing(key: str, unit: str, period: str, formula: str, fields: Tuple[str, ...] = (),
                reason: Optional[str] = None) -> None:
        absent = [f for f in fields if v.get(f) is None]
        entry: Dict[str, Any] = OrderedDict()
        entry["status"] = "not_measured"
        entry["value"] = None
        entry["unit"] = unit
        entry["period"] = period
        entry["formula"] = formula
        if reason is None:
            reason = "needs %s" % ", ".join(FIELDS[f][1] if f in FIELDS else f for f in absent)
        entry["reason"] = reason
        metrics[key] = entry
        if absent:
            needs[key] = absent

    gm_given = v["gross_margin_pct"] is not None
    gm_pct = v["gross_margin_pct"] if gm_given else DEFAULT_GROSS_MARGIN_PCT
    gm = gm_pct / 100.0
    gm_used: List[str] = []

    b = v["beginning_mrr"]
    new = v["new_mrr"]
    exp = v["expansion_mrr"]
    con = v["contraction_mrr"]
    churned = v["churned_mrr"]
    react = v["reactivation_mrr"] or 0.0
    has_b = b is not None and b > 0

    # --- MRR bridge -------------------------------------------------------
    net_exp: Optional[float] = None
    net_exp_basis = None
    if exp is not None and con is not None:
        net_exp, net_exp_basis = exp - con, "computed"
    bridge_end = None
    if b is not None and new is not None and churned is not None and net_exp is not None:
        bridge_end = b + new + react + net_exp - churned
    end = v["ending_mrr"]
    end_basis = "input"
    if end is None and bridge_end is not None:
        end, end_basis = bridge_end, "computed"
    elif end is not None and bridge_end is not None:
        gap = end - bridge_end
        if abs(gap) > max(1.0, 0.01 * max(abs(end), abs(bridge_end))):
            warnings.append(
                "The MRR bridge does not add up: beginning + new + reactivation + expansion - contraction - "
                "churned = %s, but ending_mrr is %s (difference %s). Check that every movement covers the same "
                "month; ending_mrr was used for MRR and growth." % (
                    _num_text(round(bridge_end, 2)), _num_text(round(end, 2)), _num_text(round(gap, 2))))
    snapshot = (meta.get("source") or {}).get("expansion_observable") is False
    if net_exp is None and not snapshot and v["ending_mrr"] is not None and b is not None and new is not None \
            and churned is not None:
        net_exp = v["ending_mrr"] - b - new - react + churned
        net_exp_basis = "derived"
        notes.append("Net expansion (expansion minus contraction) was derived from the MRR bridge: ending - "
                     "beginning - new - reactivation + churned = %s." % _num_text(round(net_exp, 2)))
    net_new = end - b if (end is not None and b is not None) else None

    cs, cn, cc, ce = v["customers_start"], v["customers_new"], v["customers_churned"], v["customers_end"]
    cust_end = ce
    if cs is not None and cn is not None and cc is not None:
        computed_end = cs + cn - cc
        if ce is None:
            cust_end = computed_end
        elif ce != computed_end:
            warnings.append("customers_end (%s) differs from start + new - churned (%s); reactivated customers "
                            "can explain a small gap. customers_end was used." % (ce, computed_end))

    # --- Size -------------------------------------------------------------
    if end is not None:
        put("mrr", end, "currency", "month_end",
            "ending MRR" if end_basis == "input"
            else "beginning + new + reactivation + expansion - contraction - churned", basis=end_basis)
        put("arr", end * 12, "currency", "run_rate", "ending MRR x 12", basis=end_basis)
    else:
        missing("mrr", "currency", "month_end", "ending MRR", ("ending_mrr",))
        missing("arr", "currency", "run_rate", "ending MRR x 12", ("ending_mrr",))

    committed, usage = v["committed_mrr"], v["usage_mrr"]
    if committed is not None or usage is not None:
        if committed is not None:
            put("arr_committed", committed * 12, "currency", "run_rate", "committed subscription MRR x 12",
                basis="input")
        if usage is not None:
            put("arr_usage_run_rate", usage * 12, "currency", "run_rate",
                "last month's usage MRR x 12 (a run-rate, not contracted revenue)", basis="input")
        if committed is not None and usage is not None and committed + usage > 0:
            share = usage / (committed + usage) * 100
            put("usage_share_of_mrr", share, "percent", "month", "usage MRR / (committed + usage MRR)")
            if end is not None and abs(committed + usage - end) > max(1.0, 0.01 * end):
                warnings.append("committed_mrr + usage_mrr (%s) differs from ending MRR (%s)."
                                % (_num_text(committed + usage), _num_text(end)))

    if net_new is not None:
        put("net_new_mrr", net_new, "currency", "month", "ending MRR - beginning MRR")
    else:
        missing("net_new_mrr", "currency", "month", "ending MRR - beginning MRR", ("beginning_mrr", "ending_mrr"))

    if net_new is not None and has_b:
        growth_m = net_new / b * 100
        put("mrr_growth_monthly", growth_m, "percent", "month", "net new MRR / beginning MRR")
        if growth_m > -100:
            put("mrr_growth_annualized", annualize_growth(growth_m), "percent", "annualized_from_month",
                "(1 + monthly growth) ^ 12 - 1; one month repeated for a year, so it is noisy", digits=1)
    elif b == 0:
        missing("mrr_growth_monthly", "percent", "month", "net new MRR / beginning MRR",
                reason="zero denominator: MRR at the start of the month is 0")
    else:
        missing("mrr_growth_monthly", "percent", "month", "net new MRR / beginning MRR",
                ("beginning_mrr", "ending_mrr"))

    if v["yoy_revenue_growth_pct"] is not None:
        put("yoy_revenue_growth", v["yoy_revenue_growth_pct"], "percent", "annual",
            "revenue now / revenue 12 months ago - 1",
            basis=(meta.get("source") or {}).get("yoy_basis", "input") if "yoy_revenue_growth_pct" in exported
            else "input")
    else:
        missing("yoy_revenue_growth", "percent", "annual", "revenue now / revenue 12 months ago - 1",
                ("yoy_revenue_growth_pct",))

    # --- Churn and retention ---------------------------------------------
    logo_churn: Optional[float] = None
    if cs is not None and cc is not None:
        if cs == 0:
            missing("logo_churn_monthly", "percent", "month", "churned customers / customers at start",
                    reason="zero denominator: no customers at the start of the month")
        else:
            logo_churn = cc / cs * 100
            put("logo_churn_monthly", logo_churn, "percent", "month", "churned customers / customers at start",
                annual_equivalent=_r(annual_churn_from_monthly(logo_churn), 1))
            if v["logo_churn_pct"] is not None and abs(v["logo_churn_pct"] - logo_churn) > 0.5:
                warnings.append("logo_churn_pct (%s%%) differs from the customer counts (%.2f%%); the counts were "
                                "used." % (_num_text(v["logo_churn_pct"]), logo_churn))
    elif v["logo_churn_pct"] is not None:
        logo_churn = v["logo_churn_pct"]
        put("logo_churn_monthly", logo_churn, "percent", "month", "given by the user", basis="input",
            annual_equivalent=_r(annual_churn_from_monthly(logo_churn), 1))
    else:
        missing("logo_churn_monthly", "percent", "month", "churned customers / customers at start",
                ("customers_start", "customers_churned"))

    gross_churn: Optional[float] = None
    gross_basis = "computed"
    gross_bound = None
    if has_b and churned is not None and con is not None:
        gross_churn = (churned + con) / b * 100
        if v["gross_revenue_churn_pct"] is not None and abs(v["gross_revenue_churn_pct"] - gross_churn) > 0.5:
            warnings.append("gross_revenue_churn_pct differs from churned + contraction MRR; the amounts were used.")
    elif v["gross_revenue_churn_pct"] is not None:
        gross_churn, gross_basis = v["gross_revenue_churn_pct"], "input"
    elif has_b and churned is not None:
        # Contraction unknown: cancellations alone give a floor on churn and a
        # ceiling on GRR. Shown with bound and caveat, never as the full figure.
        gross_churn, gross_bound = churned / b * 100, "lower"
    if gross_churn is not None:
        grr_m = max(0.0, 100.0 - gross_churn)
        caveat = None
        if gross_bound:
            caveat = ("Contraction MRR is not known%s, so churn counts cancellations only: true churn is at least "
                      "this and true GRR at most this." % (" (a subscriptions snapshot cannot show downgrades)"
                                                           if snapshot else ""))
        put("gross_mrr_churn_monthly", gross_churn, "percent", "month",
            "(churned + contraction MRR) / beginning MRR" if gross_basis == "computed" else "given by the user",
            basis=gross_basis, bound=gross_bound, caveat=caveat)
        put("grr_monthly", grr_m, "percent", "month", "100 - monthly gross MRR churn", basis=gross_basis,
            annualized=_r(annualize_monthly_pct(grr_m), 1), bound="upper" if gross_bound else None,
            caveat=caveat)
    elif b == 0:
        for key in ("gross_mrr_churn_monthly", "grr_monthly"):
            missing(key, "percent", "month", "(churned + contraction MRR) / beginning MRR",
                    reason="zero denominator: MRR at the start of the month is 0")
    else:
        for key in ("gross_mrr_churn_monthly", "grr_monthly"):
            missing(key, "percent", "month", "(churned + contraction MRR) / beginning MRR",
                    ("beginning_mrr", "churned_mrr", "contraction_mrr"))

    if has_b and churned is not None and net_exp is not None:
        net_churn = (churned - net_exp) / b * 100
        nrr_m = max(0.0, 100.0 - net_churn)
        basis = "derived" if net_exp_basis == "derived" else "computed"
        put("net_mrr_churn_monthly", net_churn, "percent", "month",
            "(churned + contraction - expansion MRR) / beginning MRR; negative means net expansion", basis=basis)
        put("nrr_monthly", nrr_m, "percent", "month", "100 - monthly net MRR churn", basis=basis,
            annualized=_r(annualize_monthly_pct(nrr_m), 1))
    elif b == 0:
        for key in ("net_mrr_churn_monthly", "nrr_monthly"):
            missing(key, "percent", "month", "(churned + contraction - expansion MRR) / beginning MRR",
                    reason="zero denominator: MRR at the start of the month is 0")
    elif snapshot:
        for key in ("net_mrr_churn_monthly", "nrr_monthly"):
            missing(key, "percent", "month", "(churned + contraction - expansion MRR) / beginning MRR",
                    reason="a subscriptions snapshot cannot show upgrades or downgrades; export MRR movements "
                           "(ChartMogul, Stripe Sigma) to measure it")
    else:
        for key in ("net_mrr_churn_monthly", "nrr_monthly"):
            missing(key, "percent", "month", "(churned + contraction - expansion MRR) / beginning MRR",
                    ("beginning_mrr", "churned_mrr", "expansion_mrr", "contraction_mrr"))

    if v["ttm_grr_pct"] is not None:
        extra = {}
        if meta.get("ttm_grr_basis") == "snapshot_upper_bound":
            extra["bound"] = "upper"
            extra["caveat"] = ("Rebuilt from a subscriptions snapshot: downgrades are not visible, so this is an "
                               "upper bound on true GRR.")
        put("grr_ttm", v["ttm_grr_pct"], "percent", "trailing_12_months",
            "MRR kept from customers paying 12 months ago (expansion excluded) / their MRR then",
            basis=origin("ttm_grr_pct"), **extra)
    else:
        missing("grr_ttm", "percent", "trailing_12_months",
                "MRR kept from customers paying 12 months ago / their MRR then", ("ttm_grr_pct",))
    if v["ttm_nrr_pct"] is not None:
        put("nrr_ttm", v["ttm_nrr_pct"], "percent", "trailing_12_months",
            "MRR now from customers paying 12 months ago / their MRR then", basis=origin("ttm_nrr_pct"))
    else:
        missing("nrr_ttm", "percent", "trailing_12_months",
                "MRR now from customers paying 12 months ago / their MRR then", ("ttm_nrr_pct",))

    if has_b and exp is not None:
        put("expansion_rate_monthly", exp / b * 100, "percent", "month", "expansion MRR / beginning MRR")
    elif snapshot:
        missing("expansion_rate_monthly", "percent", "month", "expansion MRR / beginning MRR",
                reason="a subscriptions snapshot cannot show upgrades")
    else:
        missing("expansion_rate_monthly", "percent", "month", "expansion MRR / beginning MRR",
                ("beginning_mrr", "expansion_mrr"),
                reason=None if b != 0 else "zero denominator: MRR at the start of the month is 0")

    # --- Customers and unit economics ------------------------------------
    arpa: Optional[float] = None
    if end is not None and cust_end:
        arpa = end / cust_end
        put("arpa", arpa, "currency", "month", "ending MRR / paying customers at month end")
    elif v["arpa"] is not None:
        arpa = v["arpa"]
        put("arpa", arpa, "currency", "month", "given by the user", basis="input")
    elif cust_end == 0:
        missing("arpa", "currency", "month", "ending MRR / paying customers at month end",
                reason="zero denominator: no paying customers at month end")
    else:
        missing("arpa", "currency", "month", "ending MRR / paying customers at month end",
                ("ending_mrr", "customers_end"))

    if new is not None and cn:
        put("arpa_new", new / cn, "currency", "month", "new MRR / new customers")
    else:
        missing("arpa_new", "currency", "month", "new MRR / new customers", ("new_mrr", "customers_new"),
                reason="zero denominator: no new customers" if cn == 0 else None)

    cac: Optional[float] = None
    sm = v["sales_marketing_spend"]
    if sm is not None and cn:
        cac = sm / cn
        put("cac", cac, "currency", "month", "sales and marketing spend / new customers (blended)")
    else:
        missing("cac", "currency", "month", "sales and marketing spend / new customers",
                ("sales_marketing_spend", "customers_new"),
                reason="zero denominator: no new customers" if cn == 0 else None)

    if sm is not None and new:
        payback = sm / (new * gm)
        gm_used.append("cac_payback_months")
        put("cac_payback_months", payback, "months", "point_in_time",
            "sales and marketing spend / (new MRR x gross margin) = CAC / (new-customer ARPA x gross margin)",
            digits=1, gross_margin_pct=_r(gm_pct, 1), gross_margin_basis="input" if gm_given else "assumed")
    else:
        missing("cac_payback_months", "months", "point_in_time",
                "sales and marketing spend / (new MRR x gross margin)", ("sales_marketing_spend", "new_mrr"),
                reason="zero denominator: no new MRR this month" if new == 0 else None)

    churn_for_ltv: Optional[float] = None
    churn_basis = None
    if v["avg_logo_churn_pct"] is not None:
        churn_for_ltv = v["avg_logo_churn_pct"]
        churn_basis = "average monthly logo churn over %s months" % (v["avg_months"] or "several")
    elif logo_churn is not None:
        churn_for_ltv = logo_churn
        churn_basis = "this month's logo churn"
    ltv: Optional[float] = None
    ltv_formula = "ARPA x gross margin x min(1 / monthly logo churn, %d months)" % LIFETIME_CAP_MONTHS
    if arpa is None or churn_for_ltv is None:
        missing("ltv", "currency", "lifetime", ltv_formula,
                reason="needs ARPA and a monthly logo churn rate")
        needs["ltv"] = [f for f in ("ending_mrr", "customers_end", "customers_start", "customers_churned")
                        if v.get(f) is None and not (f == "customers_end" and cust_end is not None)]
    elif arpa <= 0:
        missing("ltv", "currency", "lifetime", ltv_formula, reason="ARPA is 0")
    elif churn_for_ltv == 0 and v["avg_logo_churn_pct"] is None:
        missing("ltv", "currency", "lifetime", ltv_formula,
                reason="no churn this month, so lifetime is unknown; give avg_logo_churn_pct (a multi-month "
                       "average) to compute it")
    else:
        lifetime_raw = math.inf if churn_for_ltv == 0 else 100.0 / churn_for_ltv
        lifetime = min(lifetime_raw, LIFETIME_CAP_MONTHS)
        ltv = arpa * gm * lifetime
        gm_used.append("ltv")
        put("ltv", ltv, "currency", "lifetime", ltv_formula,
            lifetime_months=_r(lifetime, 1),
            lifetime_uncapped_months=_r(lifetime_raw, 1) if math.isfinite(lifetime_raw) else None,
            lifetime_capped=lifetime_raw > LIFETIME_CAP_MONTHS, churn_basis=churn_basis,
            gross_margin_pct=_r(gm_pct, 1), gross_margin_basis="input" if gm_given else "assumed")
        if gross_churn is not None and gross_churn > 0 and arpa > 0:
            life_rev = min(100.0 / gross_churn, LIFETIME_CAP_MONTHS)
            put("ltv_revenue_churn_basis", arpa * gm * life_rev, "currency", "lifetime",
                "ARPA x gross margin x min(1 / monthly gross MRR churn, %d months); informational"
                % LIFETIME_CAP_MONTHS)

    if ltv is not None and cac is not None:
        if cac == 0:
            missing("ltv_to_cac", "ratio", "point_in_time", "LTV / CAC",
                    reason="zero denominator: sales and marketing spend is 0")
        else:
            put("ltv_to_cac", ltv / cac, "ratio", "point_in_time", "LTV / CAC (LTV lifetime capped at %d months)"
                % LIFETIME_CAP_MONTHS)
    else:
        missing("ltv_to_cac", "ratio", "point_in_time", "LTV / CAC", reason="needs LTV and CAC")
        needs["ltv_to_cac"] = sorted(set(needs.get("ltv", []) + needs.get("cac", [])))

    # --- Growth efficiency ------------------------------------------------
    if all(x is not None for x in (new, exp, con, churned)):
        outflow = churned + con
        if outflow == 0:
            missing("quick_ratio", "ratio", "month", "(new + reactivation + expansion) / (churned + contraction)",
                    reason="zero denominator: no churn or contraction this month")
        else:
            put("quick_ratio", (new + react + exp) / outflow, "ratio", "month",
                "(new + reactivation + expansion MRR) / (churned + contraction MRR)")
    else:
        missing("quick_ratio", "ratio", "month", "(new + reactivation + expansion) / (churned + contraction)",
                MRR_MOVEMENTS)

    burn = v["net_burn"]
    burn_basis = "input"
    if burn is None and v["total_operating_costs"] is not None and end is not None:
        burn = v["total_operating_costs"] - end
        burn_basis = "estimated"
        assumptions.append("Net burn estimated as operating costs - ending MRR (%s), because net burn was not "
                           "given; cash collections can differ from MRR." % _num_text(round(burn, 2)))
    burn_formula = "net burn / net new ARR (monthly net burn / (net new MRR x 12))"
    if burn is None:
        missing("burn_multiple", "multiple", "month", burn_formula, ("net_burn",))
    elif net_new is None:
        missing("burn_multiple", "multiple", "month", burn_formula, ("beginning_mrr", "ending_mrr"))
    else:
        net_new_arr = net_new * 12
        if burn <= 0 and net_new_arr > 0:
            put("burn_multiple", None, "multiple", "month", burn_formula, basis=burn_basis,
                state="cash_flow_positive", net_burn=_r(burn))
        elif burn <= 0:
            put("burn_multiple", None, "multiple", "month", burn_formula, basis=burn_basis,
                state="not_burning_not_growing", net_burn=_r(burn))
        elif net_new_arr <= 0:
            put("burn_multiple", None, "multiple", "month", burn_formula, basis=burn_basis,
                state="burning_while_shrinking", net_burn=_r(burn))
        else:
            put("burn_multiple", burn / net_new_arr, "multiple", "month", burn_formula, basis=burn_basis,
                net_burn=_r(burn))

    pq, qarr = v["prev_quarter_sm_spend"], v["current_quarter_net_new_arr"]
    magic_formula = "net new ARR this quarter / sales and marketing spend last quarter"
    if pq is None or qarr is None:
        missing("magic_number", "multiple", "quarter", magic_formula,
                ("prev_quarter_sm_spend", "current_quarter_net_new_arr"))
    elif pq == 0:
        missing("magic_number", "multiple", "quarter", magic_formula,
                reason="zero denominator: last quarter's sales and marketing spend is 0")
    else:
        put("magic_number", qarr / pq, "multiple", "quarter", magic_formula)

    growth, margin = v["yoy_revenue_growth_pct"], v["profit_margin_pct"]
    if growth is not None and margin is not None:
        basis_note = v["margin_basis"] or "not stated"
        put("rule_of_40", growth + margin, "points", "annual", "YoY revenue growth % + profit margin %", digits=1,
            margin_basis=basis_note)
        put("rule_of_x", RULE_OF_X_GROWTH_MULTIPLIER * growth + margin, "points", "annual",
            "2 x YoY revenue growth % + profit margin % (Bessemer uses free-cash-flow margin)", digits=1,
            margin_basis=basis_note)
    else:
        missing("rule_of_40", "points", "annual", "YoY revenue growth % + profit margin %",
                ("yoy_revenue_growth_pct", "profit_margin_pct"))
        missing("rule_of_x", "points", "annual", "2 x YoY revenue growth % + profit margin %",
                ("yoy_revenue_growth_pct", "profit_margin_pct"))

    cash = v["cash_balance"]
    if cash is not None and burn is not None:
        if burn > 0:
            put("runway_months", cash / burn, "months", "point_in_time",
                "cash balance / monthly net burn (burn held flat)", digits=1, basis=burn_basis)
        else:
            put("runway_months", None, "months", "point_in_time", "cash balance / monthly net burn",
                basis=burn_basis, state="not_burning")
    else:
        missing("runway_months", "months", "point_in_time", "cash balance / monthly net burn",
                ("cash_balance", "net_burn"))

    # --- MRR ceiling ------------------------------------------------------
    # Steady state where new MRR equals net churn: ceiling = new / net churn
    # rate. A trailing average (from an export) is steadier than one month.
    ceiling_formula = "(new + reactivation MRR) / monthly net MRR churn rate"
    fb = meta.get("forecast_basis") or {}
    rate = inflow = None
    ceiling_extra: Dict[str, Any] = {}
    if fb.get("avg_gross_churn_rate_pct") is not None and fb.get("avg_new_mrr") is not None:
        inflow = fb["avg_new_mrr"]
        rate = (fb["avg_gross_churn_rate_pct"] - (fb.get("avg_expansion_rate_pct") or 0.0)) / 100.0
        ceiling_extra["rates_basis"] = "trailing %s-month average" % (fb.get("months") or "")
        if fb.get("avg_expansion_rate_pct") is None:
            ceiling_extra["bound"] = "upper"
            ceiling_extra["caveat"] = ("Upgrades and downgrades are not visible in this export, so churn counts "
                                       "cancellations only and the true ceiling is at most this.")
    elif has_b and new is not None and churned is not None and (net_exp is not None or gross_churn is not None):
        inflow = new + react
        ceiling_extra["rates_basis"] = "this month"
        if net_exp is not None:
            rate = (churned - net_exp) / b
        else:
            rate = gross_churn / 100.0
            assumptions.append("MRR ceiling uses gross churn because expansion was not given (expansion treated "
                               "as 0).")
            if gross_bound:
                ceiling_extra["bound"] = "upper"
                ceiling_extra["caveat"] = "Churn counts cancellations only, so the true ceiling is at most this."
    if rate is None:
        missing("mrr_ceiling", "currency", "steady_state", ceiling_formula,
                ("beginning_mrr", "new_mrr", "churned_mrr"))
    elif rate <= 0:
        put("mrr_ceiling", None, "currency", "steady_state", ceiling_formula, state="no_ceiling",
            note="Expansion covers churn (or there was no churn), so these rates set no ceiling.",
            net_churn_rate_pct=_r(rate * 100, 2), **ceiling_extra)
    elif inflow == 0:
        put("mrr_ceiling", 0.0, "currency", "steady_state", ceiling_formula,
            note="No new MRR: at these rates MRR shrinks toward 0.", net_churn_rate_pct=_r(rate * 100, 2),
            **ceiling_extra)
    else:
        ceiling = inflow / rate
        extra = dict(ceiling_extra)
        if end is not None:
            extra["current_share_pct"] = _r(end / ceiling * 100, 1)
            months90 = months_to_share_of_ceiling(end, ceiling, rate, 0.9)
            extra["months_to_90pct"] = _r(months90, 1) if months90 is not None else None
        put("mrr_ceiling", ceiling, "currency", "steady_state", ceiling_formula,
            net_churn_rate_pct=_r(rate * 100, 2), new_mrr_per_month=_r(inflow), **extra)

    if gm_used and not gm_given:
        assumptions.append("Gross margin assumed %s%% (not given); used for %s. Give gross_margin_pct to replace "
                           "it." % (_num_text(DEFAULT_GROSS_MARGIN_PCT), " and ".join(gm_used)))

    # --- Benchmarks -------------------------------------------------------
    seg, seg_shown = _derive_segment(meta.get("segment") or {}, v, metrics, notes)
    if bench is not None:
        for key in BENCH_SPECS:
            entry = metrics.get(key)
            if not entry or entry["status"] != "measured":
                continue
            if entry.get("value") is None and not entry.get("state"):
                continue
            block = bench.compare(key, entry.get("value"), seg, entry.get("state"))
            if block is not None:
                entry["benchmark"] = block

    internal = {
        "beginning_mrr": b, "ending_mrr": end, "new_inflow": (new + react) if new is not None else None,
        "expansion_mrr": exp, "contraction_mrr": con, "churned_mrr": churned, "net_expansion": net_exp,
        "gross_churn_pct": gross_churn, "net_burn": burn, "net_burn_basis": burn_basis, "cash": cash,
        "gross_margin_pct": gm_pct, "gross_margin_given": gm_given,
    }
    return {"metrics": metrics, "needs": needs, "notes": notes, "assumptions": assumptions,
            "warnings": warnings, "segment": seg_shown, "segment_for_matching": seg, "_internal": internal}


def annualize_growth(monthly_pct: float) -> float:
    return ((1.0 + monthly_pct / 100.0) ** 12 - 1.0) * 100.0


def months_to_share_of_ceiling(start: float, ceiling: float, rate: float, share: float) -> Optional[float]:
    """Months until MRR reaches share x ceiling, for MRR(t) = C - (C - M0)(1 - r)^t."""
    if ceiling <= 0 or not 0 < rate < 1:
        return None
    target = share * ceiling
    if start >= target:
        return 0.0
    gap = ceiling - start
    return math.log((ceiling - target) / gap) / math.log(1.0 - rate)


def dimension_evidence(metrics: Dict[str, Any], needs: Dict[str, List[str]],
                       segment: Dict[str, Any]) -> Dict[str, Any]:
    """Which measured metrics feed each rubric dimension (facts only, no scores)."""
    out: Dict[str, Any] = OrderedDict()
    for dim_id, label, weight in DIMENSIONS:
        spec = DIMENSION_METRICS[dim_id]
        primary = [k for k in spec["primary"] if (metrics.get(k) or {}).get("status") == "measured"]
        supporting = [k for k in spec["supporting"] if (metrics.get(k) or {}).get("status") == "measured"]
        entry: Dict[str, Any] = OrderedDict([("label", label), ("weight", weight),
                                             ("measurable", bool(primary)),
                                             ("primary_measured", primary),
                                             ("supporting_measured", supporting)])
        if not primary:
            missing_fields: List[str] = []
            for key in spec["primary"]:
                for field in needs.get(key, []):
                    if field not in missing_fields:
                        missing_fields.append(field)
            entry["missing_inputs"] = missing_fields
        if dim_id == "retention" and primary and not any(k.endswith("_ttm") for k in primary):
            entry["note"] = "Only one month of retention data: graded on monthly equivalents; noisy."
        if dim_id == "rule_of_40":
            arr = segment.get("arr")
            if isinstance(arr, (int, float)) and arr < 1e6 and segment.get("bands_matched", True):
                entry["applicability"] = (
                    "ARR is under 1M: no benchmark row covers this size and the Aleph row says Rule of 40 "
                    "becomes meaningful near 20M ARR; the rubric marks this dimension na.")
        out[dim_id] = entry
    return out


def missing_inputs_by_impact(needs: Dict[str, List[str]]) -> List[Dict[str, Any]]:
    """Inputs that would unlock the most not-measured metrics, most useful first."""
    unlocks: Dict[str, List[str]] = OrderedDict()
    for metric, fields in needs.items():
        for field in fields:
            unlocks.setdefault(field, [])
            if metric not in unlocks[field]:
                unlocks[field].append(metric)
    ranked = sorted(unlocks.items(), key=lambda item: (-len(item[1]), list(FIELDS).index(item[0])
                                                       if item[0] in FIELDS else 99))
    return [{"field": field, "label": FIELDS[field][1] if field in FIELDS else field, "unlocks": metrics}
            for field, metrics in ranked]


def run_calc(payload: Any, bench: Optional[Benchmarks] = None) -> Dict[str, Any]:
    """Validate a payload and compute everything. Raises InputError."""
    loaded = load_inputs(payload)
    result = compute(loaded["values"], loaded["meta"], bench)
    metrics = result["metrics"]
    measured = [k for k, m in metrics.items() if m["status"] == "measured"]
    not_measured = [OrderedDict([("metric", k), ("reason", m.get("reason"))])
                    for k, m in metrics.items() if m["status"] != "measured"]
    values = loaded["values"]
    provided = OrderedDict((k, _r(x, 4) if isinstance(x, float) else x)
                           for k, x in values.items() if x is not None)
    mode, mode_note = scoring_mode()
    single_month = values.get("ttm_grr_pct") is None and values.get("ttm_nrr_pct") is None
    out: Dict[str, Any] = OrderedDict()
    out["period"] = OrderedDict([
        ("label", values.get("period_label")),
        ("currency", values.get("currency") or "USD"),
        ("basis", (loaded["meta"].get("source") or {}).get("period_basis", "one month of typed numbers")),
        ("retention_basis", "one month (monthly equivalents)" if single_month else "12-month cohort"),
    ])
    out["inputs"] = OrderedDict([
        ("provided", provided),
        ("segment", loaded["meta"]["segment"]),
        ("not_provided", [k for k, x in values.items() if x is None and k not in ("period_label", "currency",
                                                                               "margin_basis")]),
    ])
    out["assumptions"] = result["assumptions"]
    out["warnings"] = loaded["warnings"] + result["warnings"]
    out["segment_used_for_benchmarks"] = result["segment"]
    out["metrics"] = metrics
    out["dimensions"] = dimension_evidence(metrics, result["needs"], result["segment"])
    out["coverage"] = OrderedDict([("measured", measured), ("not_measured", not_measured)])
    out["missing_inputs_by_impact"] = missing_inputs_by_impact(result["needs"])
    out["report_metrics"] = OrderedDict(
        (k, OrderedDict([("value", m["value"]), ("unit", m["unit"]), ("period", m["period"])]))
        for k, m in metrics.items() if m["status"] == "measured" and m.get("value") is not None)
    out["scoring"] = OrderedDict([("mode", mode), ("rubric", RUBRIC_FILE), ("rubric_version", RUBRIC_VERSION),
                                  ("lifetime_cap_months", LIFETIME_CAP_MONTHS)])
    notes = loaded["notes"] + result["notes"]
    if mode_note:
        notes.append(mode_note)
    if bench is not None and bench.error:
        notes.append(bench.error + " Metrics are shown without benchmark rows.")
    elif bench is not None:
        notes.append("Benchmarks: references/_shared/saas-benchmarks.json (last verified %s). Each row says its "
                     "source, year and segment; 'match' says whether the row fits this company's segment."
                     % (bench.last_verified or "unknown"))
    out["notes"] = notes
    out["_internal"] = result["_internal"]
    out["_meta"] = loaded["meta"]
    out["_values"] = values
    return out


# ---------------------------------------------------------------------------
# Forecast
# ---------------------------------------------------------------------------


def _scenario_settings(raw: Any, errors: List[str]) -> "OrderedDict[str, Dict[str, float]]":
    scenarios = copy.deepcopy(DEFAULT_SCENARIOS)
    if raw is None:
        return scenarios
    if not isinstance(raw, dict):
        errors.append("forecast.scenarios: expected an object such as {\"base\": {\"churn_factor\": 1}}.")
        return scenarios
    for name, settings in raw.items():
        if not isinstance(settings, dict):
            errors.append("forecast.scenarios.%s: expected an object." % name)
            continue
        target = scenarios.setdefault(str(name), dict(DEFAULT_SCENARIOS["base"]))
        for key, value in settings.items():
            if key not in SCENARIO_KEYS:
                errors.append("forecast.scenarios.%s.%s: unknown setting (use %s)."
                              % (name, key, ", ".join(SCENARIO_KEYS)))
                continue
            try:
                number = cli.to_number(value, "forecast.scenarios.%s.%s" % (name, key))
            except cli.CoercionError as exc:
                errors.append(str(exc))
                continue
            if number is None or (key != "new_mrr_monthly_growth_pct" and number < 0) \
                    or (key == "new_mrr_monthly_growth_pct" and number <= -100):
                errors.append("forecast.scenarios.%s.%s: %r is out of range." % (name, key, value))
                continue
            target[key] = number
    return scenarios


def _milestones(raw: Any, errors: List[str]) -> List[Dict[str, Any]]:
    if raw is None:
        return [dict(item) for item in DEFAULT_MILESTONES]
    if not isinstance(raw, list):
        errors.append("forecast.milestones: expected a list such as [{\"label\": \"50K MRR\", \"mrr\": 50000}].")
        return []
    out = []
    for item in raw:
        if not isinstance(item, dict):
            errors.append("forecast.milestones: each item needs a label and an mrr or arr amount.")
            continue
        try:
            mrr = cli.to_number(item.get("mrr"), "milestone.mrr", minimum=0)
            arr = cli.to_number(item.get("arr"), "milestone.arr", minimum=0)
        except cli.CoercionError as exc:
            errors.append(str(exc))
            continue
        if mrr is None and arr is None:
            errors.append("forecast.milestones: %r has no mrr or arr amount." % (item,))
            continue
        target = mrr if mrr is not None else arr / 12.0
        out.append({"label": str(item.get("label") or ("%s MRR" % _num_text(target))), "mrr": target})
    return out


def _month_label(start_label: Optional[str], offset: int) -> Optional[str]:
    if not _is_month(start_label):
        return None
    return importers.add_months(start_label, offset)


def simulate(start_mrr: float, new_mrr: float, expansion_rate: float, churn_rate: float, months: int,
             settings: Dict[str, float], cash: Optional[float] = None, net_burn: Optional[float] = None,
             gross_margin: float = DEFAULT_GROSS_MARGIN_PCT / 100.0) -> Dict[str, Any]:
    """Month-by-month MRR: MRR(t) = MRR(t-1) x (1 + expansion - churn) + new(t).

    Rates are monthly fractions of the previous month's MRR. Cash, when given,
    falls by the net burn, which shrinks as MRR grows: burn(t) = burn0 -
    (MRR(t) - MRR0) x gross margin (costs held flat).
    """
    er = expansion_rate * settings["expansion_factor"]
    cr = churn_rate * settings["churn_factor"]
    nf = settings["new_mrr_factor"]
    growth = settings["new_mrr_monthly_growth_pct"] / 100.0
    mrr = start_mrr
    rows = []
    cash_left = cash
    cash_out_month = None
    for month in range(1, months + 1):
        inflow = new_mrr * nf * (1.0 + growth) ** (month - 1)
        mrr = max(0.0, mrr * (1.0 + er - cr) + inflow)
        row = {"m": month, "mrr": mrr}
        if cash_left is not None and net_burn is not None:
            burn = net_burn - (mrr - start_mrr) * gross_margin
            cash_left -= burn
            row["cash"] = cash_left
            if cash_out_month is None and cash_left < 0:
                cash_out_month = month
        rows.append(row)
    ceiling = None
    net_rate = cr - er
    if growth == 0 and net_rate > 0:
        ceiling = new_mrr * nf / net_rate
    return {"rows": rows, "ceiling": ceiling, "net_rate": net_rate, "cash_out_month": cash_out_month,
            "rates": {"new_mrr": new_mrr * nf, "expansion_rate_pct": er * 100, "churn_rate_pct": cr * 100,
                      "new_mrr_monthly_growth_pct": growth * 100}}


def _first_month_at(rows: List[Dict[str, Any]], target: float) -> Optional[int]:
    for row in rows:
        if row["mrr"] >= target:
            return row["m"]
    return None


def build_forecast(calc: Dict[str, Any], months: Optional[int] = None) -> Dict[str, Any]:
    """Deterministic projection from the calc result. Raises MissingInputs or InputError."""
    internal = calc["_internal"]
    meta = calc["_meta"]
    values = calc["_values"]
    opts = meta.get("forecast") or {}
    basis = meta.get("forecast_basis") or {}
    errors: List[str] = []
    assumptions: List[str] = []
    notes: List[str] = []

    horizon = months if months is not None else opts.get("months", DEFAULT_FORECAST_MONTHS)
    try:
        horizon = cli.to_int(horizon, "forecast.months", minimum=1, maximum=MAX_FORECAST_MONTHS)
    except cli.CoercionError as exc:
        errors.append(str(exc))
        horizon = DEFAULT_FORECAST_MONTHS
    scenarios = _scenario_settings(opts.get("scenarios"), errors)
    milestones = _milestones(opts.get("milestones"), errors)
    if errors:
        raise InputError(errors)

    start = internal["ending_mrr"]
    b = internal["beginning_mrr"]
    missing_list: List[str] = []
    if start is None:
        missing_list.append("ending_mrr (or beginning MRR plus every movement)")

    new_base = basis.get("avg_new_mrr")
    rate_source = "trailing %s-month average from the export" % basis.get("months") if new_base is not None \
        else "one month of input"
    if new_base is None:
        new_base = internal["new_inflow"]
    if new_base is None:
        missing_list.append("new_mrr")

    churn_rate = None
    expansion_rate = None
    if basis.get("avg_gross_churn_rate_pct") is not None:
        churn_rate = basis["avg_gross_churn_rate_pct"] / 100.0
    if basis.get("avg_expansion_rate_pct") is not None:
        expansion_rate = basis["avg_expansion_rate_pct"] / 100.0
    if churn_rate is None:
        if internal["gross_churn_pct"] is not None:
            churn_rate = internal["gross_churn_pct"] / 100.0
        elif b and internal["churned_mrr"] is not None and internal["net_expansion"] is not None:
            churn_rate = (internal["churned_mrr"] + max(-internal["net_expansion"], 0.0)) / b
        elif b and internal["churned_mrr"] is not None:
            churn_rate = internal["churned_mrr"] / b
            assumptions.append("Contraction MRR was not given; the churn rate counts churned MRR only.")
    if expansion_rate is None:
        if b and internal["expansion_mrr"] is not None:
            expansion_rate = internal["expansion_mrr"] / b
        elif b and internal["net_expansion"] is not None and internal["gross_churn_pct"] is None:
            expansion_rate = max(internal["net_expansion"], 0.0) / b
        else:
            expansion_rate = 0.0
            assumptions.append("Expansion MRR was not given (or cannot be seen in the export); expansion is "
                               "treated as 0, which makes every scenario more conservative.")
    if churn_rate is None:
        missing_list.append("churned_mrr and beginning_mrr (or gross_revenue_churn_pct)")
    if missing_list:
        raise MissingInputs(missing_list, "The forecast needs: %s." % "; ".join(missing_list))

    cash = internal["cash"]
    burn = internal["net_burn"]
    gm = internal["gross_margin_pct"] / 100.0
    if cash is not None and burn is not None and not internal["gross_margin_given"]:
        assumptions.append("Gross margin assumed %s%% when converting extra MRR into lower burn."
                           % _num_text(DEFAULT_GROSS_MARGIN_PCT))
    if cash is not None and burn is not None:
        assumptions.append("cash_if_costs_flat is the best case: costs stay flat, so each extra MRR dollar lowers "
                           "monthly burn by the gross margin. runway.simple_runway_months (burn held flat) is the "
                           "conservative case; quote both.")
    period_label = values.get("period_label")
    checkpoints = sorted({m for m in (6, 12, 18, 24, horizon) if m <= horizon})

    out_scenarios = []
    base_run = None
    for name, settings in scenarios.items():
        run = simulate(start, new_base, expansion_rate, churn_rate, horizon, settings, cash, burn, gm)
        if name == "base":
            base_run = run
        entry: Dict[str, Any] = OrderedDict()
        entry["name"] = name
        entry["settings"] = OrderedDict((k, settings[k]) for k in SCENARIO_KEYS)
        entry["rates"] = OrderedDict((k, _r(x, 3 if k.endswith("pct") else 2)) for k, x in run["rates"].items())
        entry["checkpoints"] = [OrderedDict([("month", m), ("label", _month_label(period_label, m)),
                                             ("mrr", _r(run["rows"][m - 1]["mrr"])),
                                             ("arr", _r(run["rows"][m - 1]["mrr"] * 12))]) for m in checkpoints]
        if run["ceiling"] is not None:
            entry["mrr_ceiling"] = _r(run["ceiling"])
            entry["share_of_ceiling_now_pct"] = _r(start / run["ceiling"] * 100, 1) if run["ceiling"] else None
        elif run["net_rate"] <= 0:
            entry["mrr_ceiling"] = None
            entry["mrr_ceiling_state"] = "no_ceiling: expansion covers churn"
        else:
            entry["mrr_ceiling"] = None
            entry["mrr_ceiling_state"] = "not defined while new MRR keeps growing"
        stones = []
        for stone in milestones:
            item = OrderedDict([("label", stone["label"]), ("target_mrr", _r(stone["mrr"]))])
            if start >= stone["mrr"]:
                item["status"] = "already_reached"
                item["month"] = 0
            else:
                month = _first_month_at(run["rows"], stone["mrr"])
                if month is not None:
                    item["status"] = "reached"
                    item["month"] = month
                    item["label_month"] = _month_label(period_label, month)
                elif run["ceiling"] is not None and run["ceiling"] < stone["mrr"]:
                    item["status"] = "unreachable_at_these_rates"
                else:
                    item["status"] = "not_within_%d_months" % horizon
            stones.append(item)
        entry["milestones"] = stones
        if cash is not None and burn is not None:
            # Best case for cash: costs held flat while MRR grows. The simple
            # runway (burn held flat) in "runway" is the conservative case.
            if burn <= 0:
                entry["cash_if_costs_flat"] = {"status": "not_burning"}
            elif run["cash_out_month"] is not None:
                entry["cash_if_costs_flat"] = OrderedDict([
                    ("status", "runs_out"), ("month", run["cash_out_month"]),
                    ("label_month", _month_label(period_label, run["cash_out_month"]))])
            else:
                lowest = min(row["cash"] for row in run["rows"])
                entry["cash_if_costs_flat"] = OrderedDict([
                    ("status", "lasts_beyond_horizon"), ("lowest_cash", _r(lowest)),
                    ("cash_at_horizon", _r(run["rows"][-1]["cash"]))])
        entry["monthly"] = [OrderedDict([("m", row["m"]), ("label", _month_label(period_label, row["m"])),
                                         ("mrr", _r(row["mrr"]))]
                                        + ([("cash", _r(row["cash"]))] if "cash" in row else []))
                            for row in run["rows"]]
        out_scenarios.append(entry)

    levers = []
    if base_run is not None:
        base_settings = scenarios["base"]
        for lever, key, factor, label in (
                ("churn", "churn_factor", 1.0 - LEVER_STEP, "gross churn rate 10% lower"),
                ("new_mrr", "new_mrr_factor", 1.0 + LEVER_STEP, "new MRR 10% higher"),
                ("expansion", "expansion_factor", 1.0 + LEVER_STEP, "expansion rate 10% higher")):
            settings = dict(base_settings)
            settings[key] = base_settings[key] * factor
            run = simulate(start, new_base, expansion_rate, churn_rate, horizon, settings)
            m12 = min(12, horizon)
            item = OrderedDict([
                ("lever", lever), ("change", label),
                ("mrr_month_%d" % m12, _r(run["rows"][m12 - 1]["mrr"])),
                ("delta_vs_base_month_%d" % m12, _r(run["rows"][m12 - 1]["mrr"] - base_run["rows"][m12 - 1]["mrr"])),
                ("mrr_at_horizon", _r(run["rows"][-1]["mrr"])),
                ("delta_vs_base_at_horizon", _r(run["rows"][-1]["mrr"] - base_run["rows"][-1]["mrr"])),
                ("mrr_ceiling", _r(run["ceiling"]) if run["ceiling"] is not None else None),
            ])
            if lever == "expansion" and expansion_rate == 0:
                item["note"] = "No expansion in the data, so scaling it changes nothing; this lever needs an " \
                               "expansion motion first."
            levers.append(item)
        levers.sort(key=lambda item: -(item["delta_vs_base_at_horizon"] or 0))

    runway = OrderedDict()
    if cash is not None and burn is not None:
        runway["cash_balance"] = _r(cash)
        runway["net_burn"] = _r(burn)
        runway["net_burn_basis"] = internal["net_burn_basis"]
        runway["simple_runway_months"] = _r(cash / burn, 1) if burn > 0 else None
        runway["state"] = "burning" if burn > 0 else "not_burning"
    else:
        runway["state"] = "not_measured"
        runway["reason"] = "needs cash_balance and net_burn"

    notes.append("Scenario factors are planning assumptions, not probabilities. Change them under "
                 "forecast.scenarios in the input file.")
    if rate_source == "one month of input":
        notes.append("Rates come from one month; one unusual month moves every scenario. A billing export gives "
                     "a trailing 3-month average.")
    if values.get("currency") and values["currency"] != "USD":
        notes.append("Milestone amounts are in %s." % values["currency"])
    return OrderedDict([
        ("start", OrderedDict([("label", period_label), ("mrr", _r(start)), ("arr", _r(start * 12)),
                               ("currency", values.get("currency") or "USD")])),
        ("horizon_months", horizon),
        ("base_rates", OrderedDict([("source", rate_source), ("new_mrr_per_month", _r(new_base)),
                                    ("expansion_rate_pct", _r(expansion_rate * 100, 3)),
                                    ("gross_churn_rate_pct", _r(churn_rate * 100, 3))])),
        ("formula", "MRR(t) = MRR(t-1) x (1 + expansion rate - churn rate) + new MRR(t)"),
        ("scenarios", out_scenarios),
        ("levers", levers),
        ("runway", runway),
        ("assumptions", assumptions),
        ("notes", notes),
    ])


# ---------------------------------------------------------------------------
# Scoring (rubric dimensions -> total)
# ---------------------------------------------------------------------------


def score_dimensions(payload: Any) -> Dict[str, Any]:
    """Weighted total of model-assigned dimension scores. Raises InputError."""
    if isinstance(payload, dict) and isinstance(payload.get("dimensions"), (list, dict)):
        items = payload["dimensions"]
    elif isinstance(payload, list):
        items = payload
    else:
        raise InputError(["Expected {\"dimensions\": [{\"id\": \"retention\", \"score\": 6, \"confidence\": "
                          "\"high\", ...}]}."])
    if isinstance(items, dict):
        items = [dict(value, id=key) if isinstance(value, dict) else {"id": key, "score": value}
                 for key, value in items.items()]
    weights = OrderedDict((dim_id, (label, weight)) for dim_id, label, weight in DIMENSIONS)
    errors: List[str] = []
    seen: Dict[str, Dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict):
            errors.append("Each dimension must be an object, got %r." % (item,))
            continue
        dim_id = str(item.get("id") or "").strip()
        if dim_id not in weights:
            errors.append("Unknown dimension %r; use %s." % (dim_id, ", ".join(weights)))
            continue
        if dim_id in seen:
            errors.append("Dimension %s appears twice." % dim_id)
            continue
        status = str(item.get("status") or "scored").strip().lower()
        if status not in ("scored", "na", "not_measured"):
            errors.append("%s: status must be scored, na or not_measured, got %r." % (dim_id, status))
            continue
        score = None
        if status == "scored":
            try:
                score = cli.to_number(item.get("score"), "%s.score" % dim_id, minimum=0, maximum=10)
            except cli.CoercionError as exc:
                errors.append(str(exc))
                continue
            if score is None:
                errors.append("%s: a scored dimension needs a score from 0 to 10." % dim_id)
                continue
        confidence = str(item.get("confidence") or "").strip().lower() or None
        if status == "scored" and confidence not in ("high", "medium", "low"):
            errors.append("%s: confidence must be high, medium or low." % dim_id)
            continue
        seen[dim_id] = {"status": status, "score": score, "confidence": confidence,
                        "evidence": item.get("evidence") or [], "justification": item.get("justification")}
    if errors:
        raise InputError(errors)

    dims_out = []
    applicable = measured = 0.0
    weighted = 0.0
    conf_weight = {"high": 0.0, "medium": 0.0, "low": 0.0}
    for dim_id, (label, weight) in weights.items():
        item = seen.get(dim_id, {"status": "not_measured", "score": None, "confidence": None, "evidence": [],
                                 "justification": "not scored"})
        if item["status"] != "na":
            applicable += weight
        if item["status"] == "scored":
            measured += weight
            weighted += item["score"] / 10.0 * weight
            conf_weight[item["confidence"]] += weight
        dims_out.append(OrderedDict([("id", dim_id), ("label", label), ("score", item["score"]), ("max", 10),
                                     ("weight", weight), ("status", item["status"]),
                                     ("confidence", item["confidence"]), ("evidence", item["evidence"]),
                                     ("justification", item["justification"])]))
    mode, mode_note = scoring_mode()
    notes: List[str] = []
    if mode_note:
        notes.append(mode_note)
    share = measured / applicable if applicable else 0.0
    composite = None
    reason = None
    if measured == 0:
        reason = "No dimension was scored."
    elif mode != "rubric":
        reason = "scoring_mode is %s in report-contract.md, so no total is shown." % mode
    elif share < MIN_MEASURED_SHARE:
        reason = ("Only %.0f%% of the applicable weight was measured (the minimum is %.0f%%); show the dimension "
                  "scores without a total." % (share * 100, MIN_MEASURED_SHARE * 100))
    else:
        composite = round(weighted / measured * 100.0, 1)
    grade = None
    if composite is not None:
        grade = next(letter for floor, letter in GRADE_BANDS if composite >= floor)
    confidence = None
    if measured:
        if conf_weight["high"] / measured >= 0.8:
            confidence = "high"
        elif conf_weight["low"] / measured > 0.5:
            confidence = "low"
        else:
            confidence = "medium"
    header = None
    if composite is not None:
        header = "%s/100, grade %s (rubric; confidence %s; %.0f%% of weight measured)" % (
            _num_text(composite), grade, confidence, share * 100)
    return OrderedDict([
        ("composite", composite), ("max", 100), ("grade", grade), ("confidence", confidence),
        ("measured_weight", round(share, 3)), ("measured_weight_points", measured),
        ("applicable_weight_points", applicable), ("reason_no_total", reason), ("header_line", header),
        ("noise_note", "Model-assigned scores can move a few points between runs; treat differences under 5 "
                       "points as noise."),
        ("grade_bands", [OrderedDict([("grade", letter), ("min", floor)]) for floor, letter in GRADE_BANDS]),
        ("dimensions", dims_out),
        ("sidecar", OrderedDict([
            ("scoring", OrderedDict([("mode", mode), ("version", RUBRIC_VERSION), ("value", composite),
                                     ("max", 100 if composite is not None else None),
                                     ("grade", grade), ("confidence", confidence if composite is not None else None),
                                     ("measured_weight", round(share, 3) if composite is not None else None)])),
            ("dimensions", [OrderedDict([("id", d["id"]), ("score", d["score"]), ("max", 10),
                                         ("weight", d["weight"]), ("status", "scored" if d["status"] == "scored"
                                                                    else d["status"]),
                                         ("confidence", d["confidence"]), ("evidence", d["evidence"])])
                            for d in dims_out]),
        ])),
        ("notes", notes),
    ])


# ---------------------------------------------------------------------------
# Billing export import
# ---------------------------------------------------------------------------


def _pct(value: Optional[float], digits: int = 2) -> Optional[float]:
    return None if value is None else _r(value * 100.0, digits)


def _bridge_rows_pct(rows: List[Dict[str, Any]], observable: bool) -> List[Dict[str, Any]]:
    out = []
    for row in rows:
        item = OrderedDict()
        for key, value in row.items():
            if key.endswith("_rate"):
                item[key[:-5] + "_pct"] = _pct(value)
            elif key in ("expansion_mrr", "contraction_mrr") and not observable:
                item[key] = None
            else:
                item[key] = value
        out.append(item)
    return out


def _analyze_export(path: str, args: argparse.Namespace, as_of: Optional[str], months: int) -> Dict[str, Any]:
    common = dict(source=args.source, member=args.member, amount_unit=args.amount_unit,
                  currency=args.file_currency, as_of=as_of, months=months)
    try:
        return importers.analyze(path, kind="billing", **common)
    except importers.ImportOptionError:
        raise
    except importers.ImportFormatError as billing_error:
        if args.source:
            raise
        try:
            return importers.analyze(path, kind="invoices", **common)
        except importers.ImportFormatError:
            raise billing_error


def derive_from_export(result: Dict[str, Any], report_currency: Optional[str]) -> Dict[str, Any]:
    """Calc inputs (aggregates only) for the as-of month of a billing summary."""
    billing = result["billing"]
    currency = (report_currency or billing["primary_currency"] or "").upper()
    if currency not in billing["by_currency"]:
        raise InputError(["--currency %s is not in the export; it has %s."
                          % (currency, ", ".join(billing["currencies"]))])
    block = billing["by_currency"][currency]
    rows = block["monthly"]
    last = rows[-1]
    as_of = billing["as_of"]
    observable = billing["expansion_contraction_observable"]
    churn_seen = billing["churn_observable"]
    notes: List[str] = []
    derived: Dict[str, Any] = OrderedDict()
    derived["period_label"] = as_of
    derived["currency"] = currency
    derived["beginning_mrr"] = last["starting_mrr"]
    derived["ending_mrr"] = last["ending_mrr"]
    derived["new_mrr"] = last["new_mrr"]
    derived["reactivation_mrr"] = last["reactivation_mrr"]
    if observable:
        derived["expansion_mrr"] = last["expansion_mrr"]
        derived["contraction_mrr"] = last["contraction_mrr"]
    derived["customers_start"] = last["customers_start"]
    derived["customers_new"] = last["customers_new"]
    derived["customers_end"] = last["customers_end"]
    if churn_seen:
        derived["churned_mrr"] = last["churned_mrr"]
        derived["customers_churned"] = last["customers_churned"]
    else:
        notes.append("The export shows no canceled or ended subscriptions, so churn, GRR and NRR are not measured "
                     "from it. Export subscriptions with every status to measure them.")

    ttm = block.get("ttm_retention") or {}
    ttm_grr_basis = None
    if churn_seen and ttm.get("grr") is not None:
        derived["ttm_grr_pct"] = _pct(ttm["grr"])
        if billing["history_basis"] == "snapshot":
            ttm_grr_basis = "snapshot_upper_bound"
            notes.append("12-month NRR is not measured: a subscriptions snapshot cannot show upgrades or "
                         "downgrades. GRR from it is an upper bound. A ChartMogul MRR movements export or Stripe "
                         "Sigma subscription_item_change_events give both.")
        elif ttm.get("nrr") is not None:
            derived["ttm_nrr_pct"] = _pct(ttm["nrr"])
    elif ttm.get("reason"):
        notes.append("12-month cohort retention not measured: %s." % ttm["reason"])

    full = [row for row in rows if row["customers_start"]]
    churn_rows = full[-CHURN_TRAILING_MONTHS:]
    if churn_seen and len(churn_rows) >= 3:
        started = sum(row["customers_start"] for row in churn_rows)
        lost = sum(row["customers_churned"] for row in churn_rows)
        derived["avg_logo_churn_pct"] = _r(lost / started * 100, 3) if started else None
        derived["avg_months"] = len(churn_rows)

    year_ago = importers.add_months(as_of, -12)
    base_row = next((row for row in rows if row["month"] == year_ago), None)
    yoy_basis = None
    if base_row is not None and base_row["ending_mrr"] > 0:
        derived["yoy_revenue_growth_pct"] = _r((last["ending_mrr"] / base_row["ending_mrr"] - 1) * 100, 2)
        yoy_basis = "export (MRR %s vs %s)" % (as_of, year_ago)

    trailing = [row for row in rows if row["starting_mrr"] > 0][-FORECAST_TRAILING_MONTHS:]
    if trailing:
        start_sum = sum(row["starting_mrr"] for row in trailing)
        basis: Dict[str, Any] = OrderedDict()
        basis["months"] = len(trailing)
        basis["avg_new_mrr"] = _r(sum(row["new_mrr"] + row["reactivation_mrr"] for row in trailing)
                                  / len(trailing), 2)
        if observable:
            basis["avg_expansion_rate_pct"] = _r(sum(row["expansion_mrr"] for row in trailing) / start_sum * 100, 4)
        if churn_seen:
            lost = sum(row["churned_mrr"] + (row["contraction_mrr"] if observable else 0.0) for row in trailing)
            basis["avg_gross_churn_rate_pct"] = _r(lost / start_sum * 100, 4)
        basis["source"] = "export, %s to %s" % (trailing[0]["month"], trailing[-1]["month"])
        if basis.get("avg_gross_churn_rate_pct") is not None:
            derived["forecast_basis"] = basis

    source = OrderedDict([
        ("kind", "export"), ("file", result["file"].get("path_name")),
        ("format", result["format"].get("source")), ("as_of", as_of),
        ("period_basis", "billing export, month %s" % as_of),
    ])
    source["expansion_observable"] = observable
    if yoy_basis:
        source["yoy_basis"] = yoy_basis
    source["fields"] = [key for key in derived if key in FIELDS and key not in ("period_label", "currency")]
    derived["_source"] = source
    if ttm_grr_basis:
        derived["_ttm_grr_basis"] = ttm_grr_basis
    return {"derived": derived, "notes": notes, "currency": currency, "block": block}


def import_summary(result: Dict[str, Any], currency: str, block: Dict[str, Any]) -> Dict[str, Any]:
    billing = result["billing"]
    observable = billing["expansion_contraction_observable"]
    fmt = result["format"]
    cohorts = []
    for cohort in block.get("cohorts") or []:
        cohorts.append(OrderedDict([
            ("cohort", cohort["cohort"]), ("customers", cohort["customers"]),
            ("starting_mrr", cohort["starting_mrr"]),
            ("logo_retention_pct", [_pct(x, 1) for x in cohort["logo_retention"]]),
            ("revenue_retention_pct", [_pct(x, 1) for x in cohort["revenue_retention"]]),
        ]))
    ttm = dict(block.get("ttm_retention") or {})
    for key in ("grr", "nrr", "logo_retention"):
        if key in ttm:
            ttm[key + "_pct"] = _pct(ttm.pop(key))
    mix_plan = [dict(item, mrr_share_pct=_pct(item.pop("mrr_share", None))) for item in
                copy.deepcopy(block.get("plan_mix") or [])][:10]
    mix_interval = [dict(item, mrr_share_pct=_pct(item.pop("mrr_share", None))) for item in
                    copy.deepcopy(block.get("interval_mix") or [])]
    trials = copy.deepcopy(block.get("trials"))
    if isinstance(trials, dict) and "trial_to_paid_rate" in trials:
        trials["trial_to_paid_pct"] = _pct(trials.pop("trial_to_paid_rate"))
    return OrderedDict([
        ("file", result["file"].get("path_name")),
        ("format", OrderedDict((k, fmt.get(k)) for k in ("source", "vendor", "label", "confidence",
                                                          "amount_unit", "column_map", "pii_columns_ignored"))),
        ("rows", result["rows"]),
        ("as_of", billing["as_of"]),
        ("history_basis", billing["history_basis"]),
        ("expansion_contraction_observable", observable),
        ("churn_observable", billing["churn_observable"]),
        ("months_in_data", billing["months_in_data"]),
        ("currencies", billing["currencies"]),
        ("report_currency", currency),
        ("other_currencies", OrderedDict((c, billing["by_currency"][c]["current"])
                                         for c in billing["currencies"] if c != currency)),
        ("current", block["current"]),
        ("mrr_bridge", _bridge_rows_pct(block["monthly"], observable)),
        ("ttm_retention", ttm),
        ("cohorts", cohorts),
        ("churn_by_type", block.get("churn_by_type")),
        ("past_due_subscriptions", block.get("past_due_subscriptions")),
        ("status_counts", block.get("status_counts")),
        ("plan_mix", mix_plan),
        ("interval_mix", mix_interval),
        ("trials", trials),
        ("definitions", billing.get("definitions")),
    ])


def merge_inputs(derived: Dict[str, Any], typed: Optional[Dict[str, Any]], notes: List[str]) -> Dict[str, Any]:
    """Typed numbers fill the gaps of the export (costs, margin, cash, segment); the export wins on revenue."""
    combined: Dict[str, Any] = OrderedDict()
    if typed:
        for key, value in typed.items():
            combined[ALIASES.get(key, key)] = value
    for key, value in derived.items():
        if value is None:
            continue
        old = combined.get(key)
        if key in FIELDS and not cli.is_missing(old) and old != value:
            try:
                differs = abs(float(cli.to_number(old)) - float(value)) > 0.5
            except (cli.CoercionError, TypeError, ValueError):
                differs = True
            if differs:
                notes.append("%s: the export value %s was used instead of the typed %s." % (key, value, old))
        combined[key] = value
    return combined


# ---------------------------------------------------------------------------
# Benchmarks table for the guide
# ---------------------------------------------------------------------------

GUIDE_START = "<!-- generated:benchmarks:start (python3 scripts/metrics_calculator.py benchmarks --write-guide) -->"
GUIDE_END = "<!-- generated:benchmarks:end -->"


def benchmark_rows(bench: Benchmarks) -> List[Dict[str, Any]]:
    seen = []
    out = []
    for key, spec in BENCH_SPECS.items():
        metric = spec["metric"]
        if (metric, spec["periods"]) in seen:
            continue
        seen.append((metric, spec["periods"]))
        for row in bench.candidates(key):
            out.append(row)
    return out


def _fmt_stat(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if isinstance(value, int) and abs(value) >= 10000:
        return "{:,}".format(value)
    return str(value)


def benchmark_markdown(bench: Benchmarks) -> str:
    lines = [
        "| Metric | Row id | Segment | p25 | Median | p75 | Other | Source (year) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for row in benchmark_rows(bench):
        other = []
        for key in ("p90", "mean", "value"):
            if row.get(key) is not None:
                other.append("%s %s" % (key, _fmt_stat(row[key])))
        if row.get("thresholds"):
            other.append("; ".join("%s %s" % (band["label"], _band_text(band)) for band in row["thresholds"]))
        if row.get("monthly_equivalent"):
            me = row["monthly_equivalent"]
            parts = ["%s %s" % (k, _fmt_stat(me[k])) for k in ("p25", "median", "p75", "p90", "value")
                     if me.get(k) is not None]
            other.append("monthly equivalent: " + ", ".join(parts))
        lines.append("| %s (%s) | `%s` | %s | %s | %s | %s | %s | %s (%s) |" % (
            row["metric_label"], row["period"].replace("_", " "), row["id"], segment_text(row),
            _fmt_stat(row.get("p25")), _fmt_stat(row.get("median")), _fmt_stat(row.get("p75")),
            "<br>".join(other) if other else "-", row["source_name"], row["year"]))
    return "\n".join(lines) + "\n"


def write_guide_table(bench: Benchmarks, path: str = GUIDE_PATH) -> bool:
    with open(path, encoding="utf-8") as handle:
        text = handle.read()
    start = text.find(GUIDE_START)
    end = text.find(GUIDE_END)
    if start < 0 or end < 0 or end < start:
        raise InputError(["The guide has no generated-table markers (%s ... %s)." % (GUIDE_START, GUIDE_END)])
    new = text[:start + len(GUIDE_START)] + "\n" + benchmark_markdown(bench) + text[end:]
    if new != text:
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(new)
        return True
    return False


# ---------------------------------------------------------------------------
# Human-readable output
# ---------------------------------------------------------------------------


def _fmt_value(entry: Dict[str, Any], currency: str) -> str:
    if entry.get("status") != "measured":
        return "not measured"
    if entry.get("value") is None:
        return (entry.get("state") or "-").replace("_", " ")
    value = entry["value"]
    unit = entry["unit"]
    if unit == "currency":
        return "%s %s" % ("{:,.2f}".format(value), currency)
    if unit == "percent":
        return "%.2f%%" % value
    if unit == "months":
        return "%.1f months" % value
    if unit == "ratio":
        return "%.2f:1" % value
    if unit == "points":
        return "%.1f points" % value
    return "%.2f" % value


def human_calc(envelope: Dict[str, Any]) -> str:
    currency = (envelope.get("period") or {}).get("currency", "USD")
    lines = ["Subscription metrics (%s)" % ((envelope.get("period") or {}).get("label") or "one month"), ""]
    lines.append("%-28s %-26s %s" % ("Metric", "Value", "Versus benchmark"))
    lines.append("-" * 96)
    for key, entry in (envelope.get("metrics") or {}).items():
        bench = entry.get("benchmark") or {}
        versus = ""
        if bench:
            versus = "%s, %s (%s %s)" % (bench.get("performance", "").replace("_", " "), bench.get("position", ""),
                                         bench.get("source", "")[:28], bench.get("year", ""))
        elif entry.get("status") != "measured":
            versus = entry.get("reason") or ""
        lines.append("%-28s %-26s %s" % (key, _fmt_value(entry, currency), versus))
    for title, key in (("Assumptions", "assumptions"), ("Warnings", "warnings"), ("Notes", "notes")):
        items = envelope.get(key) or []
        if items:
            lines.append("")
            lines.append(title + ":")
            lines.extend("  - " + item for item in items)
    lines.append("")
    lines.append("Use --json for the full result (formulas, benchmark rows, dimensions).")
    return "\n".join(lines)


def human_forecast(envelope: Dict[str, Any]) -> str:
    forecast = envelope.get("forecast") or {}
    lines = ["MRR forecast, %s months (%s)" % (forecast.get("horizon_months"), forecast.get("formula")), ""]
    for scenario in forecast.get("scenarios", []):
        points = ", ".join("m%s %s" % (cp["month"], _num_text(cp["mrr"])) for cp in scenario["checkpoints"])
        ceiling = scenario.get("mrr_ceiling")
        lines.append("%-9s %s | ceiling %s" % (scenario["name"], points,
                                               _num_text(ceiling) if ceiling is not None else
                                               scenario.get("mrr_ceiling_state", "-")))
    runway = forecast.get("runway") or {}
    if runway.get("simple_runway_months") is not None:
        lines.append("")
        lines.append("Simple runway: %s months" % runway["simple_runway_months"])
    lines.append("")
    lines.append("Use --json for monthly values, milestones, cash and levers.")
    return "\n".join(lines)


def human_score(envelope: Dict[str, Any]) -> str:
    lines = []
    for dim in envelope.get("dimensions", []):
        lines.append("%-26s %-6s weight %-3s %s" % (dim["label"], dim["score"] if dim["score"] is not None
                                                    else dim["status"], dim["weight"], dim["confidence"] or ""))
    lines.append("")
    lines.append(envelope.get("header_line") or "No total: %s" % envelope.get("reason_no_total"))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------


def _public(calc: Dict[str, Any]) -> Dict[str, Any]:
    return OrderedDict((k, v) for k, v in calc.items() if not k.startswith("_"))


def _load_payload(args: argparse.Namespace, run: cli.Run) -> Any:
    demo_data = None
    if getattr(args, "demo", False):
        with open(DEMO_PATH, encoding="utf-8") as handle:
            demo_data = json.load(handle)
    data, _source = cli.load_json_input(args.input, expect=dict, demo_data=demo_data,
                                        demo=getattr(args, "demo", False))
    return data


def cmd_calc(args: argparse.Namespace) -> int:
    run = cli.Run(TOOL, args)
    try:
        payload = _load_payload(args, run)
        calc = run_calc(payload, Benchmarks())
    except cli.UsageError as exc:
        return run.fail(cli.STATUS_USAGE, str(exc))
    except InputError as exc:
        return run.fail(cli.STATUS_USAGE, "Invalid input: " + " | ".join(exc.errors),
                        {"command": "calc", "input_errors": exc.errors})
    data = _public(calc)
    data["command"] = "calc"
    for note in data.pop("notes"):
        run.note(note)
    if not data["coverage"]["measured"]:
        return run.fail(cli.STATUS_NOTHING,
                        "No metric could be computed from these inputs. Give at least beginning and ending MRR, "
                        "or the month's MRR movements, or customer counts.", data)
    return run.emit(data, human=human_calc)


def cmd_forecast(args: argparse.Namespace) -> int:
    run = cli.Run(TOOL, args)
    try:
        payload = _load_payload(args, run)
        calc = run_calc(payload, None)
        forecast = build_forecast(calc, args.months)
    except cli.UsageError as exc:
        return run.fail(cli.STATUS_USAGE, str(exc))
    except InputError as exc:
        return run.fail(cli.STATUS_USAGE, "Invalid input: " + " | ".join(exc.errors),
                        {"command": "forecast", "input_errors": exc.errors})
    except MissingInputs as exc:
        return run.fail(cli.STATUS_USAGE, str(exc), {"command": "forecast", "missing_inputs": exc.missing})
    for note in forecast.pop("notes"):
        run.note(note)
    data = OrderedDict([("command", "forecast"), ("forecast", forecast),
                        ("mrr_ceiling_now", calc["metrics"].get("mrr_ceiling")),
                        ("warnings", calc["warnings"]), ("assumptions", calc["assumptions"])])
    return run.emit(data, human=human_forecast)


def cmd_score(args: argparse.Namespace) -> int:
    run = cli.Run(TOOL, args)
    try:
        payload, _source = cli.load_json_input(args.input, expect=(dict, list))
        result = score_dimensions(payload)
    except cli.UsageError as exc:
        return run.fail(cli.STATUS_USAGE, str(exc))
    except InputError as exc:
        return run.fail(cli.STATUS_USAGE, "Invalid scores: " + " | ".join(exc.errors),
                        {"command": "score", "input_errors": exc.errors})
    for note in result.pop("notes"):
        run.note(note)
    data = OrderedDict([("command", "score")])
    data.update(result)
    if result["measured_weight_points"] == 0:
        return run.fail(cli.STATUS_NOTHING, "No dimension was scored, so there is nothing to total.", data)
    return run.emit(data, human=human_score)


def _rate_arg(text: str, name: str, allow_negative: bool = False) -> float:
    token = str(text).strip()
    percent = token.endswith("%")
    try:
        value = float(token.rstrip("%").strip())
    except ValueError:
        raise cli.UsageError("%s: expected a fraction such as 0.03 or a percent such as 3%%, got %r"
                             % (name, text))
    if percent:
        value /= 100.0
    elif abs(value) >= 1:
        raise cli.UsageError("%s: %s is ambiguous; give a fraction (0.03) or a percent with %% (3%%)."
                             % (name, text))
    if not allow_negative and value < 0:
        raise cli.UsageError("%s must not be negative." % name)
    return value


def cmd_test_plan(args: argparse.Namespace) -> int:
    run = cli.Run(TOOL, args)
    try:
        baseline = _rate_arg(args.baseline, "--baseline")
        mde = _rate_arg(args.mde, "--mde", allow_negative=True)
        if args.weekly is None and args.monthly is None:
            raise cli.UsageError("Give --weekly (units entering the test per week) or --monthly.")
        weekly = args.weekly if args.weekly is not None else args.monthly / 4.33
        plan = stats.plan_test(baseline, weekly, mde, relative=not args.absolute, arms=args.arms,
                               max_weeks=args.max_weeks)
    except cli.UsageError as exc:
        return run.fail(cli.STATUS_USAGE, str(exc))
    except ValueError as exc:
        return run.fail(cli.STATUS_USAGE, str(exc))
    test_plan = "ab_test" if plan["feasible"] else "ship_and_measure"
    data = OrderedDict([("command", "test-plan"), ("test_plan", test_plan),
                        ("planned_weeks", max(2, plan["weeks_rounded"]) if plan["feasible"] else None),
                        ("weekly_units", round(weekly, 2)), ("plan", plan)])
    if args.monthly is not None and args.weekly is None:
        run.note("Weekly volume = monthly / 4.33.")
    if not plan["feasible"]:
        run.note("Not testable within %s weeks: ship and measure equal windows of at least 2 full weeks before "
                 "and after, and name the confounders." % _num_text(args.max_weeks))
    return run.emit(data, human=lambda env: "%s: %s" % (env["test_plan"], env["plan"]["verdict"]))


def cmd_benchmarks(args: argparse.Namespace) -> int:
    run = cli.Run(TOOL, args)
    bench = Benchmarks()
    if bench.error:
        return run.fail(cli.STATUS_USAGE, bench.error)
    if args.write_guide:
        try:
            changed = write_guide_table(bench)
        except (OSError, InputError) as exc:
            return run.fail(cli.STATUS_USAGE, str(exc))
        run.note("Guide table %s." % ("updated" if changed else "already current"))
    rows = benchmark_rows(bench)
    data = OrderedDict([("command", "benchmarks"), ("last_verified", bench.last_verified),
                        ("row_count", len(rows)),
                        ("rows", [OrderedDict([("id", r["id"]), ("metric", r["metric"]), ("period", r["period"]),
                                               ("segment", segment_text(r)),
                                               ("stats", OrderedDict((k, r[k]) for k in
                                                                     ("p25", "median", "p75", "p90", "mean", "value")
                                                                     if r.get(k) is not None)),
                                               ("thresholds", r.get("thresholds")),
                                               ("source", r["source_name"]), ("year", r["year"])])
                                  for r in rows])])
    return run.emit(data, human=benchmark_markdown(bench).rstrip("\n"))


def cmd_import(args: argparse.Namespace) -> int:
    run = cli.Run(TOOL, args)
    path = args.input
    if not path or path == "-" or not os.path.isfile(path):
        return run.fail(cli.STATUS_USAGE, "Export file not found: %s. Pass the downloaded CSV or ZIP file."
                        % (path or "(none)"))
    months = max(13, min(int(args.months), importers.MAX_MONTHS))
    try:
        result = _analyze_export(path, args, args.as_of, months)
        if args.as_of is None and "billing" in result:
            this_month = importers.month_key(date.today())
            first_month = result["billing"]["as_of"]
            if first_month >= this_month and result["billing"]["months_in_data"] > 1:
                previous = importers.add_months(this_month, -1)
                result = _analyze_export(path, args, previous, months)
                run.note("The latest month in the export (%s) is the current month and still incomplete, so the "
                         "report uses %s, the last full month. Pass --as-of to choose another month."
                         % (first_month, previous))
    except importers.NothingToImport as exc:
        return run.fail(cli.STATUS_NOTHING, importers.scrub(str(exc)), importers.scrub(exc.details))
    except importers.ImportOptionError as exc:
        return run.fail(cli.STATUS_USAGE, importers.scrub(str(exc)), importers.scrub(exc.details))
    except importers.ImportFormatError as exc:
        details = dict(exc.details)
        details.setdefault("supported_formats", sorted(importers.FORMATS_BY_SOURCE))
        run.note("Run python3 scripts/_growthkit/importers.py --list-formats --json to see each format's columns, "
                 "or save the data in the generic_subscriptions or generic_movements layout.")
        return run.fail(cli.STATUS_USAGE, importers.scrub(str(exc)), importers.scrub(details))

    for note in result.get("notes", []):
        run.note(note)
    rows = result["rows"]
    status = cli.STATUS_OK
    if rows["data_rows"] and rows["unreadable"] / float(rows["data_rows"]) > importers.UNREADABLE_PARTIAL_SHARE:
        run.error("%d of %d rows could not be read." % (rows["unreadable"], rows["data_rows"]))
        status = cli.STATUS_PARTIAL

    if "invoices" in result:
        invoices = copy.deepcopy(result["invoices"])
        for block in invoices.get("by_currency", {}).values():
            for key in ("payment_failure_rate", "recovery_rate"):
                if key in block:
                    block[key[:-5] + "_pct"] = _pct(block.pop(key))
        run.note("This is an invoices export: it shows billings and payment failures, not MRR. Export "
                 "subscriptions (or MRR movements) to compute the metrics.")
        data = OrderedDict([("command", "import"),
                            ("import", OrderedDict([("file", result["file"].get("path_name")),
                                                    ("format", result["format"]), ("rows", rows),
                                                    ("invoices", invoices)]))])
        return run.emit(data, status=status)

    typed = None
    if args.merge:
        try:
            typed, _src = cli.load_json_input(args.merge, expect=dict)
        except cli.UsageError as exc:
            return run.fail(cli.STATUS_USAGE, "--merge: %s" % exc)
    try:
        derived_info = derive_from_export(result, args.currency)
    except InputError as exc:
        return run.fail(cli.STATUS_USAGE, " | ".join(exc.errors))
    merge_notes: List[str] = []
    combined = merge_inputs(derived_info["derived"], typed, merge_notes)
    for note in derived_info["notes"] + merge_notes:
        run.note(note)
    if not result["billing"]["churn_observable"]:
        run.error("Churn is not observable in this export (no canceled or ended subscriptions).")
        status = cli.STATUS_PARTIAL
    try:
        calc = run_calc(combined, Benchmarks())
    except InputError as exc:
        return run.fail(cli.STATUS_USAGE, "Invalid input after merging the export: " + " | ".join(exc.errors),
                        {"command": "import", "input_errors": exc.errors})
    saved = None
    if args.save_input:
        try:
            folder = os.path.dirname(os.path.abspath(args.save_input))
            os.makedirs(folder, exist_ok=True)
            with open(args.save_input, "w", encoding="utf-8") as handle:
                handle.write(json.dumps(combined, indent=2, ensure_ascii=False) + "\n")
            saved = args.save_input
        except OSError as exc:
            run.error("Could not write --save-input %s: %s" % (args.save_input, exc))
            status = cli.STATUS_PARTIAL
    data = OrderedDict([("command", "import")])
    data["import"] = import_summary(result, derived_info["currency"], derived_info["block"])
    data["derived_inputs"] = OrderedDict((k, x) for k, x in derived_info["derived"].items()
                                         if not k.startswith("_"))
    if saved:
        data["saved_input"] = saved
    public = _public(calc)
    for note in public.pop("notes"):
        run.note(note)
    data.update(public)
    return run.emit(data, status=status, human=human_calc)


def build_parser() -> cli.ArgumentParser:
    parser = cli.ArgumentParser(
        prog="metrics_calculator.py",
        description="SaaS subscription metrics: compute, benchmark, import billing exports, forecast and total "
                    "rubric scores. Every command prints one JSON document with --json.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version="%(prog)s " + __version__)
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    sub.required = True

    def common(p: argparse.ArgumentParser, demo: bool = False) -> None:
        p.add_argument("--json", action="store_true", help="print only JSON to stdout (logs go to stderr)")
        p.add_argument("--out", metavar="PATH", help="also save the JSON result to PATH")
        if demo:
            p.add_argument("--demo", action="store_true",
                           help="run on scripts/demo.json (output is labelled DEMO DATA)")

    p = sub.add_parser("calc", help="compute and benchmark one month of numbers",
                       description="Compute every metric from a JSON input file (or '-' for stdin).")
    p.add_argument("input", nargs="?", help="JSON input file, or '-' for stdin")
    common(p, demo=True)
    p.set_defaults(func=cmd_calc)

    p = sub.add_parser("import", help="read a billing export and compute the metrics",
                       description="Read a Stripe, Paddle, Chargebee, ChartMogul, Baremetrics customer x month or "
                                   "generic CSV export. Aggregates only; no customer-level data is printed.")
    p.add_argument("input", nargs="?", help="the downloaded export (.csv, .tsv or .zip)")
    p.add_argument("--as-of", metavar="YYYY-MM", help="month to report on (default: the last full month)")
    p.add_argument("--currency", metavar="CODE", help="which currency to report when the export has several")
    p.add_argument("--file-currency", metavar="CODE", help="currency for files without a currency column")
    p.add_argument("--months", type=int, default=13, help="months of MRR bridge to read (13-36, default 13)")
    p.add_argument("--source", metavar="FORMAT", help="force an export format id (see importers --list-formats)")
    p.add_argument("--member", metavar="NAME", help="CSV file to read inside a .zip")
    p.add_argument("--amount-unit", choices=("auto", "major", "minor"), default="auto",
                   help="amounts in major units (49.00) or minor units/cents (4900); default auto")
    p.add_argument("--merge", metavar="JSON", help="typed inputs to add (costs, margin, cash, segment)")
    p.add_argument("--save-input", metavar="PATH", help="save the derived inputs (aggregates) for forecast")
    common(p)
    p.set_defaults(func=cmd_import)

    p = sub.add_parser("forecast", help="project MRR in three scenarios; ceiling, milestones, runway",
                       description="Project MRR month by month from the input file (calc format).")
    p.add_argument("input", nargs="?", help="JSON input file (calc format), or '-' for stdin")
    p.add_argument("--months", type=int, default=None, help="horizon in months (1-%d, default %d)"
                   % (MAX_FORECAST_MONTHS, DEFAULT_FORECAST_MONTHS))
    common(p, demo=True)
    p.set_defaults(func=cmd_forecast)

    p = sub.add_parser("score", help="total the rubric dimension scores",
                       description="Weighted total of dimension scores written by the model "
                                   "({\"dimensions\": [{\"id\", \"score\", \"status\", \"confidence\", ...}]}).")
    p.add_argument("input", nargs="?", help="JSON file with the dimension scores, or '-' for stdin")
    common(p)
    p.set_defaults(func=cmd_score)

    p = sub.add_parser("test-plan", help="A/B test sizing for a bet",
                       description="Sample size and duration for a two-variant test (shared stats helper).")
    p.add_argument("--baseline", required=True, help="baseline rate: 0.03 or 3%%")
    p.add_argument("--weekly", type=float, help="units entering the test per week")
    p.add_argument("--monthly", type=float, help="units per month (divided by 4.33)")
    p.add_argument("--mde", default="0.2", help="minimum detectable effect, relative by default "
                                                "(0.2 = +20%%, -20%% for a drop)")
    p.add_argument("--absolute", action="store_true", help="read --mde as an absolute change in the rate")
    p.add_argument("--arms", type=int, default=2, help="variants including control (default 2)")
    p.add_argument("--max-weeks", type=float, default=stats.DEFAULT_MAX_WEEKS,
                   help="longest acceptable test (default 4)")
    common(p)
    p.set_defaults(func=cmd_test_plan)

    p = sub.add_parser("benchmarks", help="list the benchmark rows this skill compares against")
    p.add_argument("--markdown", action="store_true", help="print a Markdown table")
    p.add_argument("--write-guide", action="store_true",
                   help="rewrite the generated table in references/saas-metrics-guide.md")
    common(p)
    p.set_defaults(func=cmd_benchmarks)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
