#!/usr/bin/env python3
"""SaaS Subscription Metrics Calculator.

Computes MRR, ARR, churn rates, CAC, LTV, LTV:CAC ratio, payback period,
Rule of 40, burn multiple, NRR, GRR, ARPU, Quick Ratio, Magic Number,
and expansion MRR rate from ONE MONTH of raw business data.

Each metric receives a traffic-light status (GREEN, YELLOW, RED) based on
industry benchmarks, and the calculator produces an overall health
assessment with actionable recommendations.

Period handling:
    NRR, GRR and revenue churn computed from one month of MRR movements are
    monthly rates. They are labeled "Monthly", graded on monthly-equivalent
    thresholds (monthly = annual ^ (1/12), so an annual GRR of 90% is
    99.13% a month) and shown with an annualized approximation
    (monthly ^ 12). Pass ttm_nrr_pct / ttm_grr_pct (trailing 12-month
    cohort figures, in percent) to grade the real annual values instead.

Skip handling:
    Every input is optional. A missing input (left out, null, or "skip")
    makes the metrics that need it N/A. A zero denominator also gives N/A.
    N/A metrics are excluded from the grade and listed under "Not provided".
    Use 0 only when the true value is zero (e.g. no contraction this month).

Input forms:
    Numbers may be JSON numbers or strings such as "15000", "$15,000",
    "15K" or "75%". gross_margin_pct accepts 75 or 0.75 (both mean 75%);
    when it is missing, 70% is assumed and disclosed in the output.
    Impossible values (negative MRR, more churned customers than existed,
    a margin above 100%) are rejected with a readable error and exit code 2.

Usage:
    python3 metrics_calculator.py --demo          # built-in sample data
    python3 metrics_calculator.py data.json       # JSON file with BusinessData fields
    cat data.json | python3 metrics_calculator.py # JSON via stdin
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field, fields
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class BusinessData:
    """Raw business inputs for one month. None means "not provided"."""

    # MRR components for the month (dollars)
    new_mrr: Optional[float] = None
    expansion_mrr: Optional[float] = None
    contraction_mrr: Optional[float] = None
    churned_mrr: Optional[float] = None
    beginning_mrr: Optional[float] = None

    # Customer counts for the month
    customers_start: Optional[int] = None
    customers_new: Optional[int] = None
    customers_churned: Optional[int] = None

    # Cost data for the month (dollars)
    total_sales_marketing_spend: Optional[float] = None
    total_operating_costs: Optional[float] = None
    # Accepts 75 (percent) or 0.75 (fraction); stored as a fraction after
    # load_business_data(). None means 70% is assumed and disclosed.
    gross_margin_pct: Optional[float] = None

    # Annual growth data (percent)
    yoy_revenue_growth_pct: Optional[float] = None
    profit_margin_pct: Optional[float] = None  # EBITDA or FCF margin

    # Optional: monthly net burn for the burn multiple
    net_burn: Optional[float] = None

    # Optional: previous quarter S&M and this quarter's net new ARR (Magic Number)
    prev_quarter_sm_spend: Optional[float] = None
    current_quarter_net_new_arr: Optional[float] = None

    # Optional: trailing 12-month cohort NRR / GRR (percent). When given they
    # replace the single-month NRR / GRR rows and are graded on the annual
    # thresholds.
    ttm_nrr_pct: Optional[float] = None
    ttm_grr_pct: Optional[float] = None


@dataclass
class MetricResult:
    """A single computed metric with its assessment."""

    name: str
    value: Optional[float]  # None when the metric is N/A or not a finite number
    formatted: str
    status: str  # GREEN, YELLOW, RED, INFO, or N/A
    benchmark_note: str
    period: str = ""  # "monthly", "trailing 12 months", "annual", or ""
    annualized: Optional[float] = None  # monthly^12 approximation (retention rates only)


@dataclass
class HealthAssessment:
    """Overall SaaS health assessment."""

    grade: str  # A through F, or N/A
    green_count: int
    yellow_count: int
    red_count: int
    total_count: int
    strengths: List[str] = field(default_factory=list)
    improvements: List[str] = field(default_factory=list)
    grade_note: str = ""
    # Input labels whose absence made at least one metric N/A
    not_provided: List[str] = field(default_factory=list)
    # Defaults the calculator applied (e.g. 70% gross margin)
    assumptions: List[str] = field(default_factory=list)


class InputError(ValueError):
    """Raised when inputs are unreadable or impossible. Holds every problem found."""

    def __init__(self, errors: List[str]):
        super().__init__("; ".join(errors))
        self.errors = list(errors)


# ---------------------------------------------------------------------------
# Benchmark thresholds
# ---------------------------------------------------------------------------

THRESHOLDS = {
    "monthly_logo_churn": {"green": 2.0, "yellow": 5.0},
    # NRR and GRR thresholds are ANNUAL (12-month) values, the way these
    # benchmarks are published. Single-month rates are graded against the
    # monthly equivalents from monthly_equivalent_pct(). Monthly revenue
    # churn and monthly net revenue churn are 100 minus monthly GRR / NRR,
    # so their status is taken from the same thresholds and the mirror rows
    # can never disagree (the old fixed 2%/4% revenue churn bands did).
    "nrr": {"green_min": 110.0, "yellow_min": 100.0},
    "grr": {"green_min": 90.0, "yellow_min": 80.0},
    "ltv_cac_ratio": {"green_min": 3.0, "yellow_min": 2.0, "over_invest": 5.0},
    "payback_months": {"green": 18.0, "yellow": 24.0},
    "rule_of_40": {"green_min": 40.0, "yellow_min": 30.0},
    "burn_multiple": {"green": 1.5, "yellow": 3.0},
    "quick_ratio": {"green_min": 4.0, "yellow_min": 2.0},
    "magic_number": {"green_min": 0.75, "yellow_min": 0.5},
    "expansion_mrr_rate": {"green_min": 5.0, "yellow_min": 2.0},
}

# Used for LTV and CAC payback when gross_margin_pct is not provided.
# The output always says when this default was applied.
DEFAULT_GROSS_MARGIN = 0.70

# A letter grade from one or two metrics would be misleading.
MIN_GRADED_METRICS = 3

# Metrics shown but excluded from the health grade:
# - ARPU, CAC, and LTV have no universal traffic-light thresholds (they are
#   assessed via the LTV:CAC ratio and payback period).
# - MRR/ARR duplicate the Net New MRR signal.
# - Monthly revenue churn and net revenue churn are exactly 100 - GRR and
#   100 - NRR for the same month; grading both would count one number twice.
NON_ASSESSED_KEYS = {
    "mrr", "arr", "arpu", "cac", "ltv",
    "monthly_revenue_churn", "net_revenue_churn",
}

# Human-readable input names for "Not provided" lists and error messages.
FIELD_LABELS = {
    "beginning_mrr": "MRR at start of month",
    "new_mrr": "new MRR",
    "expansion_mrr": "expansion MRR",
    "contraction_mrr": "contraction MRR",
    "churned_mrr": "churned MRR",
    "customers_start": "customers at start of month",
    "customers_new": "new customers",
    "customers_churned": "churned customers",
    "total_sales_marketing_spend": "S&M spend",
    "total_operating_costs": "operating costs",
    "gross_margin_pct": "gross margin",
    "yoy_revenue_growth_pct": "YoY revenue growth",
    "profit_margin_pct": "profit margin",
    "net_burn": "net burn",
    "prev_quarter_sm_spend": "previous-quarter S&M spend",
    "current_quarter_net_new_arr": "this quarter's net new ARR",
    "ttm_nrr_pct": "trailing 12-month NRR",
    "ttm_grr_pct": "trailing 12-month GRR",
}

MRR_FIELDS = ("beginning_mrr", "new_mrr", "expansion_mrr", "contraction_mrr", "churned_mrr")
MOVEMENT_FIELDS = ("new_mrr", "expansion_mrr", "contraction_mrr", "churned_mrr")
COUNT_FIELDS = ("customers_start", "customers_new", "customers_churned")
NON_NEGATIVE_FIELDS = MRR_FIELDS + COUNT_FIELDS + (
    "total_sales_marketing_spend",
    "total_operating_costs",
    "prev_quarter_sm_spend",
)

# Strings that mean "not provided" (compared lower-cased and stripped).
SKIP_WORDS = {"", "skip", "skipped", "n/a", "na", "none", "null", "unknown", "-", "?"}


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def monthly_equivalent_pct(annual_pct: float) -> float:
    """Convert an annual retention rate (percent) to its monthly equivalent.

    monthly = annual ^ (1/12). Example: 90% a year is 99.13% a month,
    because 0.9913 ^ 12 = 0.90.
    """
    return 100.0 * (annual_pct / 100.0) ** (1.0 / 12.0)


def annualize_monthly_pct(monthly_pct: float) -> float:
    """Approximate an annual retention rate from one month: monthly ^ 12.

    This is an approximation: it assumes the month repeats for 12 months.
    A real annual NRR/GRR comes from a 12-month cohort.
    """
    return 100.0 * (monthly_pct / 100.0) ** 12


def _status_lower_is_better(value: float, green_max: float, yellow_max: float) -> str:
    """Return status where lower values are better."""
    if value <= green_max:
        return "GREEN"
    if value <= yellow_max:
        return "YELLOW"
    return "RED"


def _status_higher_is_better(value: float, green_min: float, yellow_min: float) -> str:
    """Return status where higher values are better."""
    if value >= green_min:
        return "GREEN"
    if value >= yellow_min:
        return "YELLOW"
    return "RED"


def _retention_bounds(key: str, monthly: bool) -> Tuple[float, float]:
    """Return (green_min, yellow_min) for "nrr"/"grr", monthly or annual.

    Monthly-equivalent thresholds are rounded to 2 decimals (99.13, 98.16,
    100.80, 100.00), the precision monthly rows are shown and graded at, so
    a displayed value and its status can never disagree.
    """
    t = THRESHOLDS[key]
    if monthly:
        return (
            round(monthly_equivalent_pct(t["green_min"]), 2),
            round(monthly_equivalent_pct(t["yellow_min"]), 2),
        )
    return t["green_min"], t["yellow_min"]


def _retention_status(value_pct: float, key: str, monthly: bool) -> str:
    """Grade an NRR/GRR value on monthly-equivalent or annual thresholds.

    Monthly values are compared at the 2-decimal precision they are shown with.
    """
    green, yellow = _retention_bounds(key, monthly)
    if monthly:
        value_pct = round(value_pct, 2)
    return _status_higher_is_better(value_pct, green, yellow)


def _fmt_pct(value: float) -> str:
    """Format as percentage with one decimal."""
    return f"{value:.1f}%"


def _fmt_pct2(value: float) -> str:
    """Format a monthly retention rate with two decimals (thresholds are 99.13%, 100.80%)."""
    return f"{value:.2f}%"


def _fmt_currency(value: float) -> str:
    """Format as currency with appropriate scale."""
    if abs(value) >= 1_000_000:
        return f"${value / 1_000_000:.2f}M"
    if abs(value) >= 1_000:
        return f"${value / 1_000:.1f}K"
    return f"${value:.0f}"


def _fmt_ratio(value: float) -> str:
    """Format as ratio."""
    return f"{value:.1f}:1"


def _fmt_months(value: float) -> str:
    """Format as months."""
    return f"{value:.0f} months"


def _fmt_multiple(value: float) -> str:
    """Format as multiple."""
    return f"{value:.1f}x"


def _fmt_input(value: float) -> str:
    """Echo a user input in error messages without float noise (1500.0 -> 1,500)."""
    if float(value).is_integer():
        return f"{int(value):,}"
    return f"{value:,}"


def _na_metric(name: str, note: str) -> MetricResult:
    """Build a metric result that cannot be assessed from the given data."""
    return MetricResult(
        name=name,
        value=None,
        formatted="N/A",
        status="N/A",
        benchmark_note=note,
    )


# ---------------------------------------------------------------------------
# Input loading: coercion, unit normalization, validation
# ---------------------------------------------------------------------------

def _coerce_number(name: str, raw: Any) -> Tuple[Optional[float], Optional[str]]:
    """Turn one raw input into a float or None.

    Returns (value, error). None and skip words ("skip", "n/a", "") mean
    "not provided". Strings may carry "$", ",", "%", spaces and a K/M
    suffix ("15K" = 15000).
    """
    if raw is None:
        return None, None
    # bool is a subclass of int; true/false is never a valid metric input.
    if isinstance(raw, bool):
        return None, f"{name}: expected a number, got {str(raw).lower()}."
    if isinstance(raw, (int, float)):
        value = float(raw)
    elif isinstance(raw, str):
        text = raw.strip().lower()
        if text in SKIP_WORDS:
            return None, None
        cleaned = text
        for ch in ("$", ",", "%", "_", " "):
            cleaned = cleaned.replace(ch, "")
        multiplier = 1.0
        if cleaned.endswith("k"):
            multiplier, cleaned = 1_000.0, cleaned[:-1]
        elif cleaned.endswith("m"):
            multiplier, cleaned = 1_000_000.0, cleaned[:-1]
        try:
            value = float(cleaned) * multiplier
        except ValueError:
            return None, (
                f"{name}: could not read {raw!r} as a number. "
                "Use digits (e.g. 15000) or 'skip'."
            )
    else:
        return None, (
            f"{name}: expected a number, got {type(raw).__name__}. "
            "Use digits (e.g. 15000) or 'skip'."
        )
    if math.isnan(value) or math.isinf(value):
        return None, f"{name}: {raw!r} is not a finite number."
    return value, None


def _normalize_units(values: Dict[str, Optional[float]], errors: List[str],
                     warnings: List[str]) -> None:
    """Normalize units in place: whole customer counts, gross margin, TTM rates."""
    # Customer counts must be whole numbers.
    for name in COUNT_FIELDS:
        value = values.get(name)
        if value is None:
            continue
        if not float(value).is_integer():
            errors.append(f"{name}: {_fmt_input(value)} is not a whole number of customers.")
            values[name] = None
        else:
            values[name] = int(value)

    # Gross margin: 75 and 0.75 both mean 75%. Values above 1 are percents.
    gm = values.get("gross_margin_pct")
    if gm is not None:
        fraction = gm / 100.0 if gm > 1 else gm
        if not 0 < fraction <= 1:
            errors.append(
                f"gross_margin_pct: {_fmt_input(gm)} is not a valid gross margin. "
                "Use a percent above 0 and up to 100 (e.g. 75) or a fraction (e.g. 0.75)."
            )
            values["gross_margin_pct"] = None
        else:
            values["gross_margin_pct"] = fraction

    # TTM NRR/GRR are percents. A value of 2 or less (0.92, 1.05) is surely a
    # fraction, since a real 12-month NRR/GRR of 2% does not happen.
    for name in ("ttm_nrr_pct", "ttm_grr_pct"):
        value = values.get(name)
        if value is not None and 0 < value <= 2:
            if name == "ttm_grr_pct" and value > 1:
                # Report the number the user typed, not the converted 150%.
                errors.append(
                    f"ttm_grr_pct: {value:g} read as a fraction is {value * 100:.0f}%, but GRR "
                    "cannot exceed 100% because it excludes expansion. Enter a percent (e.g. 92)."
                )
                values[name] = None
                continue
            values[name] = value * 100.0
            warnings.append(
                f"{name}: read {value:g} as a fraction, i.e. {value * 100:.1f}%. "
                "Enter percents (e.g. 92) to avoid this."
            )


def _range_errors(data: BusinessData) -> List[str]:
    """Return readable errors for impossible values and impossible combinations."""
    errors: List[str] = []

    for name in NON_NEGATIVE_FIELDS:
        value = getattr(data, name)
        if value is not None and value < 0:
            hint = ""
            if name in ("contraction_mrr", "churned_mrr"):
                hint = " Enter MRR lost as a positive amount (e.g. 2000, not -2000)."
            errors.append(f"{name}: {_fmt_input(value)} cannot be negative.{hint}")

    if data.yoy_revenue_growth_pct is not None and data.yoy_revenue_growth_pct < -100:
        errors.append(
            f"yoy_revenue_growth_pct: {_fmt_input(data.yoy_revenue_growth_pct)}% is impossible; "
            "revenue cannot fall by more than 100%."
        )
    if data.profit_margin_pct is not None and data.profit_margin_pct > 100:
        errors.append(
            f"profit_margin_pct: {_fmt_input(data.profit_margin_pct)}% is impossible; "
            "a margin cannot exceed 100%."
        )
    if data.ttm_grr_pct is not None and not 0 <= data.ttm_grr_pct <= 100:
        errors.append(
            f"ttm_grr_pct: {_fmt_input(data.ttm_grr_pct)}% is impossible; GRR is between 0% "
            "and 100% because it excludes expansion."
        )
    if data.ttm_nrr_pct is not None and data.ttm_nrr_pct < 0:
        errors.append(f"ttm_nrr_pct: {_fmt_input(data.ttm_nrr_pct)}% cannot be negative.")

    # More customers cannot churn than existed during the month.
    start, new, churned = data.customers_start, data.customers_new, data.customers_churned
    if start is not None and churned is not None and start >= 0 and churned >= 0:
        available = start + (new if new is not None and new >= 0 else 0)
        if churned > available:
            if new is None:
                detail = f"the {start:,} customers at start of month"
            else:
                detail = f"the {available:,} customers available ({start:,} at start + {new:,} new)"
            errors.append(
                f"customers_churned: {churned:,} churned is more than {detail}. "
                "Check that all counts cover the same month."
            )

    # MRR lost cannot exceed all MRR the month had (ending MRR would be negative).
    if all(getattr(data, n) is not None and getattr(data, n) >= 0 for n in MRR_FIELDS):
        lost = data.contraction_mrr + data.churned_mrr
        available_mrr = data.beginning_mrr + data.new_mrr + data.expansion_mrr
        if lost > available_mrr:
            errors.append(
                f"churned_mrr + contraction_mrr ({_fmt_currency(lost)}) is more than the "
                f"{_fmt_currency(available_mrr)} of MRR the month had; ending MRR would be "
                "negative. Check that all MRR figures cover the same month."
            )
    return errors


def _sanity_warnings(data: BusinessData) -> List[str]:
    """Return warnings for values that are possible but look like the wrong period."""
    warnings: List[str] = []
    b = data.beginning_mrr

    if b:  # non-zero starting MRR
        for name in ("new_mrr", "expansion_mrr"):
            value = getattr(data, name)
            if value is not None and value > 0.5 * b:
                warnings.append(
                    f"{name} ({_fmt_currency(value)}) is more than half of starting MRR "
                    f"({_fmt_currency(b)}). If it is a quarterly or annual total, enter one month only."
                )
        lost = (data.contraction_mrr or 0) + (data.churned_mrr or 0)
        if lost > b:
            warnings.append(
                "Churned plus contraction MRR exceed starting MRR; monthly GRR is floored at 0%."
            )
        elif lost > 0.15 * b:
            warnings.append(
                f"Revenue churn is {lost / b * 100:.1f}% of starting MRR in one month. "
                "Confirm churned and contraction MRR are monthly figures."
            )

        # Monthly cost fields far above MRR often mean an annual figure was entered.
        big = [
            f"{FIELD_LABELS[n]} {_fmt_currency(getattr(data, n))}"
            for n in ("total_sales_marketing_spend", "total_operating_costs", "net_burn")
            if getattr(data, n) is not None and getattr(data, n) > 5 * b
        ]
        if big:
            warnings.append(
                f"More than 5x starting MRR ({_fmt_currency(b)}): {', '.join(big)}. "
                "That can be normal early on, but if any is a quarterly or annual total, "
                "enter one month only."
            )

    start, churned = data.customers_start, data.customers_churned
    if start and churned is not None and churned / start > 0.15:
        warnings.append(
            f"Logo churn is {churned / start * 100:.1f}% in one month. "
            "Confirm these are monthly counts, not annual."
        )

    # Stored as a fraction. 1.5 is read as 1.5% (values above 1 are percents),
    # which silently wrecks LTV and payback, so flag implausibly low margins.
    gm = data.gross_margin_pct
    if gm is not None and gm < 0.2:
        warnings.append(
            f"Gross margin is read as {gm * 100:g}%, unusually low for SaaS (typically "
            "60-85%). Enter 75 or 0.75 for 75%."
        )

    for name in ("yoy_revenue_growth_pct", "profit_margin_pct"):
        value = getattr(data, name)
        if value is not None and value != 0 and -1 < value < 1:
            warnings.append(
                f"{name} is {value:g}, which is read as {value:g}%. "
                f"If you meant {value * 100:g}%, enter {value * 100:g}."
            )

    if data.ttm_nrr_pct is not None and data.ttm_nrr_pct > 200:
        warnings.append(
            "ttm_nrr_pct is above 200%, which is unusual. Confirm it is a 12-month cohort figure."
        )
    return warnings


def load_business_data(payload: Any) -> Tuple[BusinessData, List[str]]:
    """Build validated BusinessData from a raw JSON payload.

    Args:
        payload: dict using BusinessData field names. Values may be numbers,
            numeric strings, null, or "skip".

    Returns:
        Tuple of (BusinessData, warnings). Warnings never block the report.

    Raises:
        InputError: with every unreadable or impossible value listed.
    """
    if not isinstance(payload, dict):
        raise InputError([
            f"Input must be a JSON object such as {{\"beginning_mrr\": 100000}}, "
            f"got {type(payload).__name__}."
        ])

    errors: List[str] = []
    warnings: List[str] = []
    valid = [f.name for f in fields(BusinessData)]

    unknown = sorted(str(k) for k in payload if k not in valid)
    if unknown:
        warnings.append(f"Ignored unknown field(s): {', '.join(unknown)}")

    # Collect every problem in one pass so the user can fix them all at once.
    # A field that fails a step is set to None so later checks skip it.
    values: Dict[str, Optional[float]] = {}
    for name in valid:
        value, error = _coerce_number(name, payload.get(name))
        if error:
            errors.append(error)
        values[name] = value

    _normalize_units(values, errors, warnings)

    data = BusinessData(**values)
    errors.extend(_range_errors(data))
    if errors:
        raise InputError(errors)

    warnings.extend(_sanity_warnings(data))
    return data, warnings


# ---------------------------------------------------------------------------
# Core calculator
# ---------------------------------------------------------------------------

def calculate_all_metrics(data: BusinessData) -> Tuple[Dict[str, MetricResult], HealthAssessment, List[str]]:
    """Calculate all SaaS metrics from one month of raw business data.

    Missing inputs (None) make the metrics that need them N/A; N/A metrics
    are excluded from the health grade.

    Args:
        data: Raw business inputs. Strings, "skip" and gross margin as a
            percent are accepted; they are normalized first.

    Returns:
        Tuple of (all_metrics dict, health_assessment, recommendations list).

    Raises:
        InputError: if any input is unreadable or impossible.
    """
    # Normalize and validate even when called directly (not via the CLI).
    # Re-running on already-loaded data is a no-op.
    data, _ = load_business_data(asdict(data))

    metrics: Dict[str, MetricResult] = {}
    recommendations: List[str] = []
    blocked: List[str] = []  # input fields whose absence made a metric N/A

    def na_if_missing(key: str, name: str, *needed: str) -> bool:
        """Store an N/A row and return True when any needed input is missing."""
        missing = [n for n in needed if getattr(data, n) is None]
        if not missing:
            return False
        for n in missing:
            if n not in blocked:
                blocked.append(n)
        labels = ", ".join(FIELD_LABELS[n] for n in missing)
        metrics[key] = _na_metric(name, f"Not provided: {labels}")
        return True

    # --- Shared intermediate values (None when inputs are missing) ---
    net_new_mrr: Optional[float] = None
    if all(getattr(data, n) is not None for n in MOVEMENT_FIELDS):
        net_new_mrr = data.new_mrr + data.expansion_mrr - data.contraction_mrr - data.churned_mrr
    ending_mrr: Optional[float] = None
    if net_new_mrr is not None and data.beginning_mrr is not None:
        ending_mrr = data.beginning_mrr + net_new_mrr

    # Single-month GRR / NRR in percent. They need a non-zero starting MRR.
    has_base = data.beginning_mrr is not None and data.beginning_mrr > 0
    monthly_grr: Optional[float] = None
    if has_base and data.contraction_mrr is not None and data.churned_mrr is not None:
        monthly_grr = (
            (data.beginning_mrr - data.contraction_mrr - data.churned_mrr)
            / data.beginning_mrr
        ) * 100
        monthly_grr = max(min(monthly_grr, 100.0), 0.0)  # GRR lives in 0-100%
    monthly_nrr: Optional[float] = None
    if monthly_grr is not None and data.expansion_mrr is not None:
        monthly_nrr = (
            (data.beginning_mrr + data.expansion_mrr - data.contraction_mrr - data.churned_mrr)
            / data.beginning_mrr
        ) * 100
        monthly_nrr = max(monthly_nrr, 0.0)
    zero_base_note = "MRR at start of month is 0 (zero denominator)"

    # --- MRR ---
    if not na_if_missing("mrr", "MRR", *MRR_FIELDS):
        metrics["mrr"] = MetricResult(
            name="MRR",
            value=ending_mrr,
            formatted=_fmt_currency(ending_mrr),
            status="GREEN" if net_new_mrr > 0 else "RED",
            benchmark_note="End of month; positive net new MRR expected",
            period="monthly",
        )

    # --- ARR ---
    if not na_if_missing("arr", "ARR", *MRR_FIELDS):
        arr = ending_mrr * 12
        metrics["arr"] = MetricResult(
            name="ARR",
            value=arr,
            formatted=_fmt_currency(arr),
            status="GREEN" if net_new_mrr > 0 else "RED",
            benchmark_note="ARR = MRR x 12",
            period="annual",
        )

    # --- Net New MRR ---
    if not na_if_missing("net_new_mrr", "Net New MRR", *MOVEMENT_FIELDS):
        metrics["net_new_mrr"] = MetricResult(
            name="Net New MRR",
            value=net_new_mrr,
            formatted=_fmt_currency(net_new_mrr),
            status="GREEN" if net_new_mrr > 0 else "RED",
            benchmark_note="Should be positive every month",
            period="monthly",
        )

    # --- Monthly Logo Churn ---
    logo_churn: Optional[float] = None
    name = "Monthly Logo Churn"
    if not na_if_missing("monthly_logo_churn", name, "customers_start", "customers_churned"):
        if data.customers_start == 0:
            metrics["monthly_logo_churn"] = _na_metric(
                name, "No customers at start of month (zero denominator)"
            )
        else:
            logo_churn = (data.customers_churned / data.customers_start) * 100
            t = THRESHOLDS["monthly_logo_churn"]
            metrics["monthly_logo_churn"] = MetricResult(
                name=name,
                value=logo_churn,
                formatted=_fmt_pct(logo_churn),
                status=_status_lower_is_better(logo_churn, t["green"], t["yellow"]),
                benchmark_note="<2% GREEN, 2-5% YELLOW, >5% RED",
                period="monthly",
            )
            if logo_churn > t["green"]:
                recommendations.append(
                    "Reduce logo churn: implement customer health scoring, improve onboarding, "
                    "and build proactive churn prevention workflows."
                )

    grr_green, grr_yellow = _retention_bounds("grr", monthly=True)
    nrr_green, nrr_yellow = _retention_bounds("nrr", monthly=True)

    # --- Monthly Revenue Churn (Gross) = 100 - monthly GRR ---
    name = "Monthly Revenue Churn"
    if not na_if_missing("monthly_revenue_churn", name,
                         "beginning_mrr", "contraction_mrr", "churned_mrr"):
        if not has_base:
            metrics["monthly_revenue_churn"] = _na_metric(name, zero_base_note)
        else:
            gross_rev_churn = (
                (data.churned_mrr + data.contraction_mrr) / data.beginning_mrr
            ) * 100
            # Print 100 - the rounded monthly GRR (the number that is graded), so
            # the two rows always show matching values and share one status even
            # at rounding ties. Raw churn only when GRR is floored at 0%.
            shown = gross_rev_churn if gross_rev_churn > 100 else 100.0 - round(monthly_grr, 2)
            metrics["monthly_revenue_churn"] = MetricResult(
                name=name,
                value=gross_rev_churn,
                formatted=_fmt_pct2(shown),
                # Same thresholds as monthly GRR, so the two rows always agree.
                status=_retention_status(monthly_grr, "grr", monthly=True),
                benchmark_note=(
                    f"<={100 - grr_green:.2f}% GREEN, <={100 - grr_yellow:.2f}% YELLOW "
                    "(= GRR 90%/80% a year)"
                ),
                period="monthly",
            )

    # --- Monthly Net Revenue Churn = 100 - monthly NRR ---
    name = "Monthly Net Revenue Churn"
    if not na_if_missing("net_revenue_churn", name, "beginning_mrr", "expansion_mrr",
                         "contraction_mrr", "churned_mrr"):
        if not has_base:
            metrics["net_revenue_churn"] = _na_metric(name, zero_base_note)
        else:
            net_rev_churn = (
                (data.churned_mrr + data.contraction_mrr - data.expansion_mrr)
                / data.beginning_mrr
            ) * 100
            # Same idea: 100 - the rounded monthly NRR that is graded. Raw value
            # only when NRR is floored at 0%. 100 - 100.0 is +0.0, never "-0.00%".
            shown = net_rev_churn if net_rev_churn > 100 else 100.0 - round(monthly_nrr, 2)
            metrics["net_revenue_churn"] = MetricResult(
                name=name,
                value=net_rev_churn,
                formatted=_fmt_pct2(shown),
                # Same thresholds as monthly NRR, so the two rows always agree.
                status=_retention_status(monthly_nrr, "nrr", monthly=True),
                benchmark_note=(
                    f"<={100 - nrr_green:.2f}% GREEN, <={100 - nrr_yellow:.2f}% YELLOW "
                    "(= NRR 110%/100% a year)"
                ),
                period="monthly",
            )

    # --- NRR: trailing 12-month override, else single month ---
    if data.ttm_nrr_pct is not None:
        nrr = data.ttm_nrr_pct
        note = ">=110% GREEN, >=100% YELLOW (12-month cohort)"
        if monthly_nrr is not None:
            note += f"; this month {monthly_nrr:.2f}%/mo"
        metrics["nrr"] = MetricResult(
            name="NRR (trailing 12 mo)",
            value=nrr,
            formatted=_fmt_pct(nrr),
            status=_retention_status(nrr, "nrr", monthly=False),
            benchmark_note=note,
            period="trailing 12 months",
        )
    elif not na_if_missing("nrr", "Monthly NRR", "beginning_mrr", "expansion_mrr",
                           "contraction_mrr", "churned_mrr"):
        if not has_base:
            metrics["nrr"] = _na_metric("Monthly NRR", zero_base_note)
        else:
            annual = annualize_monthly_pct(monthly_nrr)
            metrics["nrr"] = MetricResult(
                name="Monthly NRR",
                value=monthly_nrr,
                formatted=_fmt_pct2(monthly_nrr),
                status=_retention_status(monthly_nrr, "nrr", monthly=True),
                benchmark_note=(
                    f">={nrr_green:.2f}%/mo GREEN, >={nrr_yellow:.2f}%/mo YELLOW; "
                    f"~{annual:.1f}%/yr*"
                ),
                period="monthly",
                annualized=annual,
            )
    if "nrr" in metrics and metrics["nrr"].status == "RED":
        recommendations.append(
            "Improve NRR: drive expansion revenue through upsells and usage-based pricing, "
            "and reduce downgrades with proactive customer success."
        )

    # --- GRR: trailing 12-month override, else single month ---
    if data.ttm_grr_pct is not None:
        grr = data.ttm_grr_pct
        note = ">=90% GREEN, >=80% YELLOW (12-month cohort)"
        if monthly_grr is not None:
            note += f"; this month {monthly_grr:.2f}%/mo"
        metrics["grr"] = MetricResult(
            name="GRR (trailing 12 mo)",
            value=grr,
            formatted=_fmt_pct(grr),
            status=_retention_status(grr, "grr", monthly=False),
            benchmark_note=note,
            period="trailing 12 months",
        )
    elif not na_if_missing("grr", "Monthly GRR", "beginning_mrr", "contraction_mrr",
                           "churned_mrr"):
        if not has_base:
            metrics["grr"] = _na_metric("Monthly GRR", zero_base_note)
        else:
            annual = annualize_monthly_pct(monthly_grr)
            metrics["grr"] = MetricResult(
                name="Monthly GRR",
                value=monthly_grr,
                formatted=_fmt_pct2(monthly_grr),
                status=_retention_status(monthly_grr, "grr", monthly=True),
                benchmark_note=(
                    f">={grr_green:.2f}%/mo GREEN, >={grr_yellow:.2f}%/mo YELLOW; "
                    f"~{annual:.1f}%/yr*"
                ),
                period="monthly",
                annualized=annual,
            )
    if "grr" in metrics and metrics["grr"].status == "RED":
        recommendations.append(
            "Improve GRR: focus on reducing cancellations through better product-market fit, "
            "onboarding improvements, and proactive support."
        )

    # --- ARPU ---
    arpu: Optional[float] = None
    if not na_if_missing("arpu", "ARPU", *(MRR_FIELDS + COUNT_FIELDS)):
        customers_end = data.customers_start + data.customers_new - data.customers_churned
        if customers_end <= 0:
            metrics["arpu"] = _na_metric(
                "ARPU", "No customers at end of month (zero denominator)"
            )
        else:
            arpu = ending_mrr / customers_end
            metrics["arpu"] = MetricResult(
                name="ARPU",
                value=arpu,
                formatted=_fmt_currency(arpu),
                status="INFO",  # context-dependent, no universal threshold
                benchmark_note="Varies by segment (not graded)",
                period="monthly",
            )

    # --- CAC ---
    cac: Optional[float] = None
    name = "CAC (Blended)"
    if not na_if_missing("cac", name, "total_sales_marketing_spend", "customers_new"):
        if data.customers_new == 0:
            metrics["cac"] = _na_metric(name, "No new customers this month (zero denominator)")
        else:
            cac = data.total_sales_marketing_spend / data.customers_new
            metrics["cac"] = MetricResult(
                name=name,
                value=cac,
                formatted=_fmt_currency(cac),
                status="INFO",  # assessed via LTV:CAC ratio
                benchmark_note="Assessed via LTV:CAC ratio",
                period="monthly",
            )

    # Gross margin is stored as a fraction by load_business_data().
    gm_provided = data.gross_margin_pct is not None
    gross_margin = data.gross_margin_pct if gm_provided else DEFAULT_GROSS_MARGIN
    gm_suffix = "" if gm_provided else f" ({gross_margin * 100:.0f}% margin assumed)"
    gm_used = False

    # --- LTV (Simple Method, margin-adjusted) ---
    ltv: Optional[float] = None
    if arpu is None or logo_churn is None:
        metrics["ltv"] = _na_metric("LTV (Simple)", "Requires ARPU and monthly logo churn")
    elif arpu <= 0:
        metrics["ltv"] = _na_metric("LTV (Simple)", "ARPU is 0; LTV cannot be computed")
    elif logo_churn == 0:
        metrics["ltv"] = _na_metric(
            "LTV (Simple)", "No churn observed; LTV undefined from this period's data"
        )
    else:
        ltv = arpu * gross_margin / (logo_churn / 100)
        gm_used = True
        metrics["ltv"] = MetricResult(
            name="LTV (Simple)",
            value=ltv,
            formatted=_fmt_currency(ltv),
            status="INFO",  # assessed via LTV:CAC ratio
            benchmark_note="LTV = ARPU x gross margin / monthly churn" + gm_suffix,
        )

    # --- LTV:CAC Ratio ---
    if ltv is None or cac is None:
        metrics["ltv_cac_ratio"] = _na_metric("LTV:CAC Ratio", "Requires both LTV and CAC")
    elif cac == 0:
        metrics["ltv_cac_ratio"] = _na_metric(
            "LTV:CAC Ratio", "S&M spend is 0, so CAC is 0 (zero denominator)"
        )
    else:
        ltv_cac = ltv / cac

        t = THRESHOLDS["ltv_cac_ratio"]
        if ltv_cac >= t["over_invest"]:
            ltv_cac_status = "YELLOW"
            ltv_cac_note = ">5:1 may indicate under-investment in growth"
        elif ltv_cac >= t["green_min"]:
            ltv_cac_status = "GREEN"
            ltv_cac_note = "3:1-5:1 is the sweet spot"
        elif ltv_cac >= t["yellow_min"]:
            ltv_cac_status = "YELLOW"
            ltv_cac_note = "2:1-3:1, room for improvement"
        else:
            ltv_cac_status = "RED"
            ltv_cac_note = "<2:1, unit economics need work"

        metrics["ltv_cac_ratio"] = MetricResult(
            name="LTV:CAC Ratio",
            value=ltv_cac,
            formatted=_fmt_ratio(ltv_cac),
            status=ltv_cac_status,
            benchmark_note=ltv_cac_note,
        )
        if ltv_cac < t["green_min"]:
            recommendations.append(
                "Improve LTV:CAC ratio: reduce CAC through organic channels and better conversion, "
                "or increase LTV by reducing churn and driving expansion."
            )

    # --- CAC Payback Period ---
    if cac is None or arpu is None or arpu <= 0:
        metrics["payback_period"] = _na_metric(
            "CAC Payback Period", "Requires CAC and a positive ARPU"
        )
    else:
        payback_months = cac / (arpu * gross_margin)
        gm_used = True

        t = THRESHOLDS["payback_months"]
        metrics["payback_period"] = MetricResult(
            name="CAC Payback Period",
            value=payback_months,
            formatted=_fmt_months(payback_months),
            status=_status_lower_is_better(payback_months, t["green"], t["yellow"]),
            benchmark_note="<18mo GREEN, 18-24mo YELLOW, >24mo RED" + gm_suffix,
        )
        if payback_months > t["green"]:
            recommendations.append(
                "Shorten CAC payback: increase ARPU, improve gross margins, "
                "or reduce acquisition costs to recover CAC faster."
            )

    # --- Rule of 40 ---
    if not na_if_missing("rule_of_40", "Rule of 40",
                         "yoy_revenue_growth_pct", "profit_margin_pct"):
        rule_of_40 = data.yoy_revenue_growth_pct + data.profit_margin_pct

        t = THRESHOLDS["rule_of_40"]
        metrics["rule_of_40"] = MetricResult(
            name="Rule of 40",
            value=rule_of_40,
            formatted=_fmt_pct(rule_of_40),
            status=_status_higher_is_better(rule_of_40, t["green_min"], t["yellow_min"]),
            benchmark_note=">40% GREEN, 30-40% YELLOW, <30% RED",
            period="annual",
        )
        if rule_of_40 < t["yellow_min"]:
            recommendations.append(
                "Improve Rule of 40 score: if growth is strong, focus on margins; "
                "if margins are healthy, invest more aggressively in growth."
            )

    # --- Burn Multiple ---
    name = "Burn Multiple"
    net_burn = data.net_burn
    burn_note = "<1.5x GREEN, 1.5-3x YELLOW, >3x RED"
    burn_estimated = False
    if net_burn is None and data.total_operating_costs is not None and ending_mrr is not None:
        # Fallback estimate when net burn is not provided directly.
        net_burn = data.total_operating_costs - ending_mrr
        burn_estimated = True
        burn_note += " (burn estimated as operating costs - MRR)"

    if net_burn is None:
        if data.total_operating_costs is None:
            na_if_missing("burn_multiple", name, "net_burn")
        else:
            # Operating costs given, but the MRR inputs needed to estimate burn are not.
            na_if_missing("burn_multiple", name, "net_burn", *MRR_FIELDS)
    elif not na_if_missing("burn_multiple", name, *MOVEMENT_FIELDS):
        net_new_arr = net_new_mrr * 12
        t = THRESHOLDS["burn_multiple"]
        if net_burn <= 0 and net_new_arr <= 0:
            metrics["burn_multiple"] = _na_metric(
                name, "Not burning cash and ARR not growing; multiple undefined"
            )
        elif net_burn <= 0:
            metrics["burn_multiple"] = MetricResult(
                name=name,
                value=net_burn / net_new_arr,
                formatted="Cash-flow positive",
                status="GREEN",
                benchmark_note="Growing ARR without burning cash",
            )
        elif net_new_arr <= 0:
            metrics["burn_multiple"] = MetricResult(
                name=name,
                value=None,
                formatted="ARR not growing",
                status="RED",
                benchmark_note="Burning cash while net new ARR is zero or negative",
            )
        else:
            burn_multiple = net_burn / net_new_arr
            metrics["burn_multiple"] = MetricResult(
                name=name,
                value=burn_multiple,
                formatted=_fmt_multiple(burn_multiple),
                status=_status_lower_is_better(burn_multiple, t["green"], t["yellow"]),
                benchmark_note=burn_note,
            )
            if burn_multiple > t["green"]:
                recommendations.append(
                    "Reduce burn multiple: improve capital efficiency by growing ARR faster "
                    "relative to cash burn, or cut low-ROI spend."
                )

    # --- Quick Ratio ---
    if not na_if_missing("quick_ratio", "Quick Ratio", *MOVEMENT_FIELDS):
        outflows = data.contraction_mrr + data.churned_mrr
        if outflows == 0:
            metrics["quick_ratio"] = _na_metric(
                "Quick Ratio", "No churn or contraction this month (zero denominator)"
            )
        else:
            quick_ratio = (data.new_mrr + data.expansion_mrr) / outflows
            t = THRESHOLDS["quick_ratio"]
            metrics["quick_ratio"] = MetricResult(
                name="Quick Ratio",
                value=quick_ratio,
                formatted=f"{quick_ratio:.1f}",
                status=_status_higher_is_better(quick_ratio, t["green_min"], t["yellow_min"]),
                benchmark_note=">4 GREEN, 2-4 YELLOW, <2 RED",
                period="monthly",
            )

    # --- Magic Number ---
    if not na_if_missing("magic_number", "Magic Number",
                         "prev_quarter_sm_spend", "current_quarter_net_new_arr"):
        if data.prev_quarter_sm_spend == 0:
            metrics["magic_number"] = _na_metric(
                "Magic Number", "Previous-quarter S&M spend is 0 (zero denominator)"
            )
        else:
            magic_number = data.current_quarter_net_new_arr / data.prev_quarter_sm_spend
            t = THRESHOLDS["magic_number"]
            metrics["magic_number"] = MetricResult(
                name="Magic Number",
                value=magic_number,
                formatted=f"{magic_number:.2f}",
                status=_status_higher_is_better(magic_number, t["green_min"], t["yellow_min"]),
                benchmark_note=">0.75 GREEN, 0.5-0.75 YELLOW, <0.5 RED",
                period="quarterly",
            )

    # --- Expansion MRR Rate ---
    name = "Expansion MRR Rate"
    if not na_if_missing("expansion_mrr_rate", name, "beginning_mrr", "expansion_mrr"):
        if not has_base:
            metrics["expansion_mrr_rate"] = _na_metric(name, zero_base_note)
        else:
            expansion_rate = (data.expansion_mrr / data.beginning_mrr) * 100
            t = THRESHOLDS["expansion_mrr_rate"]
            metrics["expansion_mrr_rate"] = MetricResult(
                name=name,
                value=expansion_rate,
                formatted=_fmt_pct(expansion_rate),
                status=_status_higher_is_better(expansion_rate, t["green_min"], t["yellow_min"]),
                benchmark_note=">5% GREEN, 2-5% YELLOW, <2% RED",
                period="monthly",
            )
            if expansion_rate < t["yellow_min"]:
                recommendations.append(
                    "Boost expansion MRR: introduce usage-based pricing tiers, "
                    "add-on features, and proactive upsell motions through customer success."
                )

    # --- Health Assessment ---
    health = _compute_health_assessment(metrics)
    field_order = [f.name for f in fields(BusinessData)]
    health.not_provided = [FIELD_LABELS[n] for n in sorted(blocked, key=field_order.index)]
    if gm_used and not gm_provided:
        health.assumptions.append(
            f"Gross margin assumed {DEFAULT_GROSS_MARGIN * 100:.0f}% (not provided); "
            "used for LTV and CAC payback."
        )
    if burn_estimated:
        health.assumptions.append(
            "Net burn estimated as operating costs - ending MRR (net burn not provided)."
        )

    return metrics, health, recommendations


def _compute_health_assessment(metrics: Dict[str, MetricResult]) -> HealthAssessment:
    """Compute overall health grade from individual metric statuses.

    Informational metrics (see NON_ASSESSED_KEYS) and metrics that could
    not be computed (status N/A) are excluded from grading. Fewer than
    MIN_GRADED_METRICS graded metrics gives grade N/A.

    Args:
        metrics: Dictionary of computed metric results.

    Returns:
        HealthAssessment with grade, counts, strengths, and improvements.
    """
    assessed = {
        key: m
        for key, m in metrics.items()
        if key not in NON_ASSESSED_KEYS and m.status in ("GREEN", "YELLOW", "RED")
    }

    green_count = sum(1 for m in assessed.values() if m.status == "GREEN")
    yellow_count = sum(1 for m in assessed.values() if m.status == "YELLOW")
    red_count = sum(1 for m in assessed.values() if m.status == "RED")
    total = len(assessed)

    green_pct = (green_count / total * 100) if total > 0 else 0

    # Determine grade (over assessed metrics only)
    grade_note = ""
    if total < MIN_GRADED_METRICS:
        grade = "N/A"
        grade_note = (
            f"needs at least {MIN_GRADED_METRICS} graded metrics, {total} could be graded"
        )
    elif red_count >= 3 or green_pct < 20:
        grade = "F"
    elif red_count == 2:
        grade = "D"
    elif green_pct >= 80 and red_count == 0:
        grade = "A"
    elif green_pct >= 60 and red_count <= 1:
        grade = "B"
    elif green_pct >= 40:
        grade = "C"
    else:
        grade = "D"

    # Identify strengths (GREEN assessed metrics)
    strengths = [m.name for m in assessed.values() if m.status == "GREEN"][:3]

    # Identify improvements (RED first, then YELLOW)
    reds = [m.name for m in assessed.values() if m.status == "RED"]
    yellows = [m.name for m in assessed.values() if m.status == "YELLOW"]
    improvements = (reds + yellows)[:3]

    return HealthAssessment(
        grade=grade,
        green_count=green_count,
        yellow_count=yellow_count,
        red_count=red_count,
        total_count=total,
        strengths=strengths,
        improvements=improvements,
        grade_note=grade_note,
    )


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def print_metrics_table(metrics: Dict[str, MetricResult]) -> None:
    """Print a formatted metrics table to stdout.

    Args:
        metrics: Dictionary of computed metric results.
    """
    print(f"\n{'Metric':<28} {'Value':<18} {'Status':<8} {'Benchmark'}")
    print("-" * 95)
    for m in metrics.values():
        print(f"{m.name:<28} {m.formatted:<18} {m.status:<8} {m.benchmark_note}")


def period_notes(metrics: Dict[str, MetricResult]) -> List[str]:
    """Explain monthly grading and annualized approximations, when they apply.

    Args:
        metrics: Dictionary of computed metric results.

    Returns:
        Lines to print under the table (empty when no monthly retention row
        was computed).
    """
    # Revenue churn rows stay monthly even when ttm_* overrides replace NRR/GRR.
    retention_keys = ("monthly_revenue_churn", "net_revenue_churn", "nrr", "grr")
    if not any(k in metrics and metrics[k].period == "monthly" for k in retention_keys):
        return []

    grr_g, grr_y = _retention_bounds("grr", monthly=True)
    nrr_g, nrr_y = _retention_bounds("nrr", monthly=True)
    t_grr, t_nrr = THRESHOLDS["grr"], THRESHOLDS["nrr"]
    lines = [
        "* Period: retention and revenue churn rows marked Monthly come from ONE month of",
        "  data, so they are graded on monthly-equivalent thresholds: monthly = annual^(1/12).",
        f"    GRR: {t_grr['green_min']:.0f}%/yr = {grr_g:.2f}%/mo (GREEN), "
        f"{t_grr['yellow_min']:.0f}%/yr = {grr_y:.2f}%/mo (YELLOW)",
        f"    NRR: {t_nrr['green_min']:.0f}%/yr = {nrr_g:.2f}%/mo (GREEN), "
        f"{t_nrr['yellow_min']:.0f}%/yr = {nrr_y:.2f}%/mo (YELLOW)",
    ]

    annualized_rows = [
        metrics[k] for k in ("grr", "nrr")
        if k in metrics and metrics[k].period == "monthly" and metrics[k].annualized is not None
    ]
    if annualized_rows:
        approx = "; ".join(
            f"{m.name.replace('Monthly ', '')} {m.value:.2f}%/mo ~ {m.annualized:.1f}%/yr"
            for m in annualized_rows
        )
        lines += [
            f"  Annualized approximation (monthly^12): {approx}.",
            "  Caveat: this assumes the month repeats for 12 months, and one month is noisy.",
        ]

    ttm_names = [
        metrics[k].name for k in ("nrr", "grr")
        if k in metrics and metrics[k].period == "trailing 12 months"
    ]
    if ttm_names:
        lines.append(
            f"  {' and '.join(ttm_names)}: from your 12-month cohort, graded on the "
            "annual thresholds."
        )
    if len(ttm_names) < 2:
        lines.append(
            "  For the real annual figure, pass ttm_nrr_pct / ttm_grr_pct from a 12-month cohort."
        )
    return lines


def print_input_notes(health: HealthAssessment, warnings: Optional[List[str]] = None) -> None:
    """Print missing inputs, applied assumptions, and input warnings.

    Args:
        health: Computed health assessment (carries not_provided and assumptions).
        warnings: Input warnings from load_business_data().
    """
    if health.not_provided:
        print("\nNot provided (metrics shown as N/A and excluded from the grade):")
        for label in health.not_provided:
            print(f"  - {label}")
    if health.assumptions:
        print("\nAssumptions:")
        for note in health.assumptions:
            print(f"  - {note}")
    if warnings:
        print("\nWarnings (check these inputs):")
        for note in warnings:
            print(f"  - {note}")


def print_health_assessment(health: HealthAssessment) -> None:
    """Print the health assessment summary.

    Args:
        health: Computed health assessment.
    """
    grade = health.grade
    if health.grade_note:
        grade += f" ({health.grade_note})"
    print(f"\n{'=' * 50}")
    print(f"  Overall Health Grade: {grade}")
    print(
        f"  GREEN: {health.green_count} | YELLOW: {health.yellow_count} | "
        f"RED: {health.red_count}  ({health.total_count} metrics graded)"
    )
    print("  Not graded: N/A rows, MRR, ARR, ARPU, CAC, LTV; revenue churn rows")
    print("  mirror GRR/NRR and are counted once through them.")
    print(f"{'=' * 50}")

    if health.strengths:
        print("\n  Top Strengths:")
        for s in health.strengths:
            print(f"    + {s}")

    if health.improvements:
        print("\n  Areas for Improvement:")
        for i in health.improvements:
            print(f"    - {i}")


def print_recommendations(recommendations: List[str]) -> None:
    """Print actionable recommendations.

    Args:
        recommendations: List of recommendation strings.
    """
    if not recommendations:
        print("\n  No critical recommendations from the metrics that could be calculated.")
        return

    print(f"\n{'=' * 50}")
    print("  Recommendations")
    print(f"{'=' * 50}")
    for idx, rec in enumerate(recommendations, 1):
        print(f"\n  {idx}. {rec}")


def print_report(data: BusinessData, warnings: Optional[List[str]] = None) -> HealthAssessment:
    """Calculate everything and print the full text report.

    Args:
        data: Loaded business inputs.
        warnings: Input warnings from load_business_data().

    Returns:
        The health assessment (useful for callers and tests).
    """
    all_metrics, health, recommendations = calculate_all_metrics(data)
    print_metrics_table(all_metrics)
    notes = period_notes(all_metrics)
    if notes:
        print()
        for line in notes:
            print(line)
    print_input_notes(health, warnings)
    print_health_assessment(health)
    print_recommendations(recommendations)
    return health


# ---------------------------------------------------------------------------
# Standalone demo
# ---------------------------------------------------------------------------

# Sample company: one month of data. Gross margin is given as a fraction
# here; 75 would mean the same thing.
DEMO_INPUT = {
    "beginning_mrr": 100_000,
    "new_mrr": 15_000,
    "expansion_mrr": 8_000,
    "contraction_mrr": 2_000,
    "churned_mrr": 3_000,
    "customers_start": 500,
    "customers_new": 60,
    "customers_churned": 12,
    "total_sales_marketing_spend": 80_000,
    "total_operating_costs": 150_000,
    "gross_margin_pct": 0.75,
    "yoy_revenue_growth_pct": 85,
    "profit_margin_pct": -20,
    "net_burn": 120_000,
    "prev_quarter_sm_spend": 220_000,
    "current_quarter_net_new_arr": 200_000,
}


def main() -> None:
    """Run a demo calculation with sample SaaS data."""
    sample_data, warnings = load_business_data(DEMO_INPUT)

    print("SaaS Subscription Metrics Calculator")
    print("=" * 50)
    print("\nSample Business Data (one month):")
    print(f"  Beginning MRR: {_fmt_currency(sample_data.beginning_mrr)}")
    print(f"  New MRR: {_fmt_currency(sample_data.new_mrr)}")
    print(f"  Expansion MRR: {_fmt_currency(sample_data.expansion_mrr)}")
    print(f"  Contraction MRR: {_fmt_currency(sample_data.contraction_mrr)}")
    print(f"  Churned MRR: {_fmt_currency(sample_data.churned_mrr)}")
    print(f"  Customers: {sample_data.customers_start} start, "
          f"+{sample_data.customers_new} new, -{sample_data.customers_churned} churned")
    print(f"  S&M Spend: {_fmt_currency(sample_data.total_sales_marketing_spend)}")
    print(f"  Gross Margin: {sample_data.gross_margin_pct * 100:.0f}%")
    print(f"  YoY Growth: {sample_data.yoy_revenue_growth_pct:g}%")
    print(f"  Profit Margin: {sample_data.profit_margin_pct:g}%")

    print_report(sample_data, warnings)


def _cli() -> None:
    """Command-line entry point: JSON file, stdin, or --demo.

    Exit codes: 0 on success, 2 on unreadable or invalid input.
    """
    import argparse
    import json
    import sys

    parser = argparse.ArgumentParser(
        description="SaaS subscription metrics calculator (one month of data)",
        epilog="JSON keys use the BusinessData field names, e.g. "
               '{"beginning_mrr": 100000, "new_mrr": 15000, ...}. '
               'Use null or "skip" for unknown values; gross_margin_pct accepts 75 or 0.75.',
    )
    parser.add_argument(
        "input", nargs="?",
        help="Path to a JSON file with BusinessData fields (or '-' for stdin)",
    )
    parser.add_argument(
        "--demo", action="store_true", help="Run with built-in sample data"
    )
    args = parser.parse_args()

    if args.demo or (args.input is None and sys.stdin.isatty()):
        main()
        return

    def fail(lines: List[str]) -> None:
        print("Error: invalid input.", file=sys.stderr)
        for line in lines:
            print(f"  - {line}", file=sys.stderr)
        sys.exit(2)

    source = "stdin" if args.input is None or args.input == "-" else args.input
    try:
        if source == "stdin":
            text = sys.stdin.read()
        else:
            # utf-8-sig also accepts files saved with a byte-order mark (Windows editors).
            with open(args.input, "r", encoding="utf-8-sig") as fh:
                text = fh.read()
        payload = json.loads(text.lstrip("﻿"))
    except OSError as exc:
        fail([f"could not read {source}: {exc.strerror or exc}"])
    except UnicodeDecodeError:
        fail([f"could not read {source}: it is not UTF-8 text. Save the input as a UTF-8 JSON file."])
    except json.JSONDecodeError as exc:
        fail([f"not valid JSON (line {exc.lineno}, column {exc.colno}): {exc.msg}"])

    try:
        data, warnings = load_business_data(payload)
    except InputError as exc:
        fail(exc.errors)

    print("SaaS Subscription Metrics Calculator")
    print("=" * 50)
    print_report(data, warnings)


if __name__ == "__main__":
    _cli()
