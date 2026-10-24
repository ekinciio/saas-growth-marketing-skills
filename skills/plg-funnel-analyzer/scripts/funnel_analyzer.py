"""
PLG Funnel Analyzer - Product-Led Growth Funnel Assessment Tool

Accepts user metrics, runs benchmark comparisons with traffic light scoring,
computes a weighted 0-100 funnel score and letter grade, detects the biggest
funnel leak, and generates prioritized recommendations.

Usage:
    python3 funnel_analyzer.py --demo           # built-in sample data
    python3 funnel_analyzer.py metrics.json     # JSON file with metric keys
    cat metrics.json | python3 funnel_analyzer.py

    JSON keys: signup_to_active, free_to_paid, monthly_churn, nrr,
    time_to_value_days, payback_months (all optional).

    Values may be numbers (25 means 25%), strings such as "25%", "3 days"
    or "15 months", or "skip" / null for a metric the user does not have.
    NRR given as a ratio (1.12) is converted to 112%.

Scoring:
    Each metric is placed at an approximate percentile of the benchmark
    range (bottom-25% threshold = 25, median = 50, top-25% threshold = 75).
    The funnel score is the weighted sum of those percentiles (weights in
    SCORE_WEIGHTS, total 100). A metric that is not provided counts as 0,
    so adding a metric can never lower the score or the grade, and leaving
    out a weak metric can never raise it. A letter grade needs at least
    MIN_METRICS_FOR_GRADE metrics; with fewer the grade is "Partial - N of 6".

Exit codes:
    0 success, 2 invalid input (bad JSON, missing file, impossible values;
    every problem is listed on stderr).

Requirements:
    No external dependencies - uses only the Python standard library.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Benchmark data
# ---------------------------------------------------------------------------

@dataclass
class BenchmarkRange:
    """Defines benchmark thresholds for a single metric."""
    name: str
    unit: str
    bottom_25: float
    median: float
    top_25: float
    higher_is_better: bool = True
    description: str = ""


BENCHMARKS: dict[str, BenchmarkRange] = {
    "signup_to_active": BenchmarkRange(
        name="Signup-to-Active",
        unit="%",
        bottom_25=15.0,
        median=25.0,
        top_25=40.0,
        higher_is_better=True,
        description="Percentage of signups who become active users",
    ),
    "free_to_paid": BenchmarkRange(
        name="Free-to-Paid",
        unit="%",
        bottom_25=2.0,
        median=5.0,
        top_25=10.0,
        higher_is_better=True,
        description="Percentage of free users who convert to paid",
    ),
    "monthly_churn": BenchmarkRange(
        name="Monthly Churn",
        unit="%",
        bottom_25=8.0,
        median=5.0,
        top_25=3.0,
        higher_is_better=False,
        description="Percentage of customers who cancel per month",
    ),
    "nrr": BenchmarkRange(
        name="Net Revenue Retention",
        unit="%",
        bottom_25=95.0,
        median=105.0,
        top_25=120.0,
        higher_is_better=True,
        description="Revenue retained from existing customers including expansion",
    ),
    "time_to_value_days": BenchmarkRange(
        name="Time-to-Value",
        unit="days",
        bottom_25=7.0,
        median=3.0,
        top_25=1.0,
        higher_is_better=False,
        description="Days from signup to the user experiencing core value",
    ),
    "payback_months": BenchmarkRange(
        name="Payback Period",
        unit="months",
        bottom_25=24.0,
        median=16.0,  # 2025 actuals ~16 months (Benchmarkit 2025)
        top_25=6.0,
        higher_is_better=False,
        description="Months to recover customer acquisition cost",
    ),
}

# Weight of each metric in the 0-100 funnel score (sums to 100).
# Retention (churn + NRR) 30, activation 20, conversion 20, payback 15, TTV 15.
SCORE_WEIGHTS: dict[str, float] = {
    "signup_to_active": 20.0,
    "free_to_paid": 20.0,
    "monthly_churn": 15.0,
    "nrr": 15.0,
    "time_to_value_days": 15.0,
    "payback_months": 15.0,
}

# A letter grade needs at least this many of the 6 metrics.
MIN_METRICS_FOR_GRADE = 4

# Funnel score -> letter grade (first threshold the score reaches wins).
# All six metrics exactly at the median give 50 (C); all six exactly at the
# top-25% threshold give 75 (A).
GRADE_THRESHOLDS: list[tuple[float, str]] = [
    (70.0, "A"),
    (57.0, "B"),
    (43.0, "C"),
    (30.0, "D"),
    (0.0, "F"),
]

# Plausible ranges after normalization. Anything outside is rejected as a
# typo or unit mix-up rather than graded.
VALID_RANGES: dict[str, tuple[float, float]] = {
    "signup_to_active": (0.0, 100.0),
    "free_to_paid": (0.0, 100.0),
    "monthly_churn": (0.0, 100.0),
    "nrr": (10.0, 300.0),
    "time_to_value_days": (0.0, 365.0),
    "payback_months": (0.0, 120.0),
}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class MetricAssessment:
    """Assessment of a single metric against benchmarks."""
    metric_key: str
    metric_name: str
    value: float
    unit: str
    status: str  # "GREEN", "YELLOW", "RED"
    benchmark_position: str  # Human-readable position description
    gap_to_median: float  # How far from median (negative = below)
    recommendations: list[str] = field(default_factory=list)
    percentile: float = 0.0  # Approximate benchmark percentile, 0-100
    weight: float = 0.0  # Weight in the funnel score


@dataclass
class FunnelAnalysisResult:
    """Complete funnel analysis result."""
    metrics_assessment: list[MetricAssessment]
    overall_health: str  # Letter grade A-F, "Partial - N of 6", or "N/A"
    biggest_leak: Optional[MetricAssessment]
    recommendations: list[str]
    green_count: int = 0
    yellow_count: int = 0
    red_count: int = 0
    score: float = 0.0  # Weighted 0-100; missing metrics count as 0
    best_case_score: float = 0.0  # Score if every missing metric were top-tier
    metrics_provided: int = 0
    missing_metrics: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Input normalization and validation
# ---------------------------------------------------------------------------

class FunnelInputError(ValueError):
    """Raised when funnel metrics cannot be analyzed.

    ``problems`` holds one readable message per bad field.
    """

    def __init__(self, problems: list[str]) -> None:
        self.problems = list(problems)
        super().__init__("; ".join(self.problems))


# Strings that mean "I don't have this metric" (SKILL.md tells users to type
# "skip").
SKIP_STRINGS = {
    "", "skip", "skipped", "n/a", "na", "none", "null", "unknown", "-", "?",
    "not provided", "not tracked",
}

# Accepted unit suffixes per metric and the factor that converts them to the
# benchmark unit (percent, days or months).
_PERCENT_UNITS = {"%": 1.0, "percent": 1.0, "pct": 1.0}
_UNIT_FACTORS: dict[str, dict[str, float]] = {
    "signup_to_active": _PERCENT_UNITS,
    "free_to_paid": _PERCENT_UNITS,
    "monthly_churn": _PERCENT_UNITS,
    "nrr": _PERCENT_UNITS,
    "time_to_value_days": {
        "d": 1.0, "day": 1.0, "days": 1.0,
        "h": 1 / 24, "hr": 1 / 24, "hrs": 1 / 24, "hour": 1 / 24, "hours": 1 / 24,
        # PLG products often quote TTV in minutes ("aha in 5 minutes").
        # A bare "m" is left out on purpose: minutes or months?
        "min": 1 / 1440, "mins": 1 / 1440, "minute": 1 / 1440, "minutes": 1 / 1440,
        "w": 7.0, "wk": 7.0, "wks": 7.0, "week": 7.0, "weeks": 7.0,
    },
    "payback_months": {
        "mo": 1.0, "mos": 1.0, "month": 1.0, "months": 1.0,
        "y": 12.0, "yr": 12.0, "yrs": 12.0, "year": 12.0, "years": 12.0,
    },
}

# Percent metrics where a bare value in (0, FRACTION_MAX] may really be a
# fraction (0.35 meaning 35%). Low churn or free-to-paid like 0.8% is real,
# so a single such value only warns, and a value whose fraction reading is
# impossible (churn 1.2 -> 120%) is not flagged at all; see normalize_metrics().
_FRACTION_KEYS = ("signup_to_active", "free_to_paid", "monthly_churn")
FRACTION_MAX = 1.5
# NRR below this as a bare number is a ratio (1.12 = 112%).
NRR_RATIO_MAX = 3.0

_VALUE_RE = re.compile(r"^([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*([a-z%]*)$")


def _fmt_num(value: float) -> str:
    """Compact number for messages: 25.0 -> '25', 0.35 -> '0.35'."""
    return f"{value:g}"


def _parse_metric(key: str, raw: Any) -> tuple[Optional[float], bool]:
    """Parse one metric value. Returns (value, had_explicit_percent_sign).

    value is None when the metric is skipped. Raises ValueError with a
    readable message for anything that is not a usable number.
    """
    if raw is None:
        return None, False
    if isinstance(raw, bool):
        raise ValueError(f"{key}: {raw!r} is not a number")
    explicit_percent = False
    if isinstance(raw, (int, float)):
        value = float(raw)
    elif isinstance(raw, str):
        text = raw.strip().lower()
        if text in SKIP_STRINGS:
            return None, False
        match = _VALUE_RE.match(text)
        if not match:
            raise ValueError(
                f"{key}: {raw!r} is not a number (use e.g. 25, \"25%\" or "
                "\"skip\")"
            )
        value = float(match.group(1))
        unit = match.group(2)
        if unit:
            factors = _UNIT_FACTORS[key]
            if unit not in factors:
                expected = BENCHMARKS[key].unit
                raise ValueError(
                    f"{key}: unit {unit!r} in {raw!r} does not fit this metric "
                    f"(expected {expected})"
                )
            value *= factors[unit]
            explicit_percent = factors is _PERCENT_UNITS
    else:
        raise ValueError(f"{key}: expected a number, got {type(raw).__name__}")

    if math.isnan(value) or math.isinf(value):
        raise ValueError(f"{key}: {raw!r} is not a finite number")
    if value < 0:
        raise ValueError(f"{key}: {raw!r} is negative")
    return value, explicit_percent


def _range_problem(key: str, value: float) -> Optional[str]:
    """Return a message when a (normalized) value is impossible, else None."""
    low, high = VALID_RANGES[key]
    if low <= value <= high:
        return None
    unit = BENCHMARKS[key].unit
    sep = "" if unit == "%" else " "
    message = (
        f"{key}: {_fmt_num(value)}{sep}{unit} is outside the plausible range "
        f"{_fmt_num(low)}-{_fmt_num(high)}{sep}{unit}"
    )
    if key == "nrr" and value < low:
        message += " (NRR is a percent: 100 means revenue from existing customers stayed flat)"
    return message


def _check_value(key: str, value: Any) -> Optional[str]:
    """Validate an already-numeric metric for analyze_funnel()."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return f"{key}: expected a number, got {type(value).__name__}"
    if math.isnan(value) or math.isinf(value):
        return f"{key}: {value!r} is not a finite number"
    if value < 0:
        return f"{key}: {_fmt_num(value)} is negative"
    return _range_problem(key, float(value))


def normalize_metrics(payload: Any) -> tuple[dict[str, float], list[str]]:
    """Turn raw JSON metrics into clean floats. Returns (metrics, warnings).

    Handles "25%", "skip"/null, unit suffixes and NRR ratios. Raises
    FunnelInputError listing every problem (NaN, negative, impossible
    values, fraction-looking input).
    """
    if not isinstance(payload, dict):
        raise FunnelInputError([
            "the JSON must be an object like {\"signup_to_active\": 25, "
            f"\"nrr\": 105}}, got {type(payload).__name__}"
        ])

    problems: list[str] = []
    warnings: list[str] = []
    metrics: dict[str, float] = {}

    unknown = sorted(str(k) for k in set(payload) - set(BENCHMARKS))
    if unknown:
        warnings.append(f"ignoring unknown metric(s): {', '.join(unknown)}")

    flagged: list[tuple[str, float]] = []
    nrr_was_ratio = False
    for key in BENCHMARKS:
        if key not in payload:
            continue
        try:
            value, explicit_percent = _parse_metric(key, payload[key])
        except ValueError as exc:
            problems.append(str(exc))
            continue
        if value is None:
            continue
        if key == "nrr" and not explicit_percent and 0 < value <= NRR_RATIO_MAX:
            warnings.append(
                f"nrr = {_fmt_num(value)} read as a ratio: using "
                f"{_fmt_num(value * 100)}%"
            )
            value *= 100
            nrr_was_ratio = True
        elif (
            key in _FRACTION_KEYS
            and not explicit_percent
            and 0 < value <= FRACTION_MAX
            # Only when the fraction reading is itself possible: churn 1.2
            # cannot mean 120%, so it is a real 1.2% and is not flagged.
            and _range_problem(key, value * 100) is None
        ):
            flagged.append((key, value))
        metrics[key] = value

    if flagged and (nrr_was_ratio or len(flagged) >= 2):
        # Several tiny percents (or NRR given as a ratio) almost always means
        # the whole input is in fractions. Grading it would be silently wrong.
        listed = ", ".join(
            f"{k} = {_fmt_num(v)} (did you mean {_fmt_num(v * 100)}?)"
            for k, v in flagged
        )
        problems.append(
            f"these values look like fractions, not percents: {listed}. Enter "
            "percents (35 or \"35%\"). To keep a small value as it is, write "
            "it with a % sign, e.g. \"1.2%\""
        )
    else:
        for key, value in flagged:
            warnings.append(
                f"{key} = {_fmt_num(value)} was read as {_fmt_num(value)}%. "
                f"If you meant a fraction ({_fmt_num(value * 100)}%), enter "
                f"{_fmt_num(value * 100)} instead"
            )

    for key, value in metrics.items():
        problem = _range_problem(key, value)
        if problem:
            problems.append(problem)

    if problems:
        raise FunnelInputError(problems)
    return metrics, warnings


# ---------------------------------------------------------------------------
# Traffic light classification
# ---------------------------------------------------------------------------

def classify_metric(key: str, value: float) -> str:
    """
    Classify a metric value as GREEN, YELLOW, or RED based on benchmarks.

    Args:
        key: The metric key matching BENCHMARKS dict.
        value: The user's metric value.

    Returns:
        Traffic light status string.
    """
    bench = BENCHMARKS[key]

    if bench.higher_is_better:
        if value >= bench.top_25:
            return "GREEN"
        elif value > bench.bottom_25:
            return "YELLOW"
        else:
            return "RED"
    else:
        # Lower is better (churn, TTV, payback)
        if value <= bench.top_25:
            return "GREEN"
        elif value < bench.bottom_25:
            return "YELLOW"
        else:
            return "RED"


def calculate_gap_to_median(key: str, value: float) -> float:
    """
    Calculate the relative gap between the value and median benchmark.

    Positive means above median (good for higher-is-better metrics).
    Negative means below median.

    Args:
        key: The metric key.
        value: The user's metric value.

    Returns:
        Relative gap as a percentage of the median.
    """
    bench = BENCHMARKS[key]
    if bench.median == 0:
        return 0.0

    if bench.higher_is_better:
        return ((value - bench.median) / bench.median) * 100
    else:
        # For lower-is-better, invert the comparison
        return ((bench.median - value) / bench.median) * 100


def normalized_position(key: str, value: float) -> float:
    """
    Position of a value within the bottom-25% -> top-25% benchmark range.

    0.0 = at the bottom-25% threshold, 1.0 = at the top-25% threshold.
    Values outside the range extend below 0 or above 1. Lower is worse,
    for both higher-is-better and lower-is-better metrics, which makes
    the score comparable across differently-scaled metrics.

    Args:
        key: The metric key.
        value: The user's metric value.

    Returns:
        Normalized position (dimensionless).
    """
    bench = BENCHMARKS[key]
    span = bench.top_25 - bench.bottom_25
    if span == 0:
        return 0.0
    return (value - bench.bottom_25) / span


def percentile_position(key: str, value: float) -> float:
    """
    Approximate benchmark percentile of a value, from 0 (worst) to 100 (best).

    Piecewise linear through three anchors: bottom-25% threshold = 25,
    median = 50, top-25% threshold = 75. Beyond the outer anchors the line
    is extended with the slope of the nearest segment and capped at 0-100.
    Works the same way for lower-is-better metrics (churn, TTV, payback).

    Args:
        key: The metric key.
        value: The user's metric value.

    Returns:
        Percentile position between 0.0 and 100.0.
    """
    bench = BENCHMARKS[key]
    # Flip lower-is-better metrics so "bigger x" always means "better".
    sign = 1.0 if bench.higher_is_better else -1.0
    x = sign * value
    x_bottom, x_median, x_top = (
        sign * bench.bottom_25, sign * bench.median, sign * bench.top_25,
    )
    if x <= x_median:
        x0, p0, x1, p1 = x_bottom, 25.0, x_median, 50.0
    else:
        x0, p0, x1, p1 = x_median, 50.0, x_top, 75.0
    if x1 == x0:
        pct = p1 if x >= x1 else p0
    else:
        pct = p0 + (x - x0) * (p1 - p0) / (x1 - x0)
    return max(0.0, min(100.0, pct))


def funnel_score(percentiles: dict[str, float]) -> tuple[float, float]:
    """
    Weighted 0-100 funnel score. Returns (score, best_case_score).

    score adds weight x percentile/100 for each provided metric; a missing
    metric adds 0. Every term is >= 0, so adding a metric never lowers the
    score (monotonic) and skipping a weak metric never raises it.
    best_case_score assumes every missing metric would score 100.
    Both are rounded to one decimal (rounding keeps the order).
    """
    score = sum(
        SCORE_WEIGHTS[key] * pct / 100.0 for key, pct in percentiles.items()
    )
    missing_weight = sum(
        weight for key, weight in SCORE_WEIGHTS.items() if key not in percentiles
    )
    return round(score, 1), round(score + missing_weight, 1)


def grade_for_score(score: float) -> str:
    """Map a 0-100 funnel score to a letter grade (A-F)."""
    for threshold, letter in GRADE_THRESHOLDS:
        if score >= threshold:
            return letter
    return "F"


def overall_grade(score: float, metrics_provided: int) -> str:
    """Letter grade, or 'Partial - N of 6' / 'N/A' when data is too thin."""
    if metrics_provided == 0:
        return "N/A"
    if metrics_provided < MIN_METRICS_FOR_GRADE:
        return f"Partial - {metrics_provided} of {len(BENCHMARKS)}"
    return grade_for_score(score)


# ---------------------------------------------------------------------------
# Recommendation engine
# ---------------------------------------------------------------------------

RECOMMENDATIONS: dict[str, dict[str, list[str]]] = {
    "signup_to_active": {
        "RED": [
            "Redesign onboarding to reach the aha moment in 3 steps or fewer",
            "Add a personalized first-run experience based on user role or use case",
            "Implement progress indicators to show users how close they are to getting value",
            "Remove optional setup steps that delay time-to-value",
        ],
        "YELLOW": [
            "A/B test onboarding flows to find the fastest path to activation",
            "Add contextual tooltips at decision points instead of upfront tutorials",
            "Pre-populate templates or sample data so users see value immediately",
        ],
    },
    "free_to_paid": {
        "RED": [
            "Review your free tier limits - ensure they let users experience enough value to want more",
            "Add in-app upgrade prompts at moments when users hit free tier limits",
            "Implement a reverse trial - let free users experience paid features temporarily",
            "Align your pricing metric with the value users actually receive",
        ],
        "YELLOW": [
            "Test different trial lengths (7-day vs 14-day vs 30-day)",
            "Add social proof and case studies on the upgrade page",
            "Create email sequences that highlight paid features based on user behavior",
        ],
    },
    "monthly_churn": {
        "RED": [
            "Implement early warning system to detect at-risk accounts before they churn",
            "Survey churned users to identify the top 3 reasons for cancellation",
            "Add a cancellation flow that offers alternatives (pause, downgrade, support call)",
            "Increase product stickiness by encouraging integrations and data investment",
        ],
        "YELLOW": [
            "Build automated re-engagement campaigns for users showing declining activity",
            "Offer annual plans with discounts to reduce monthly churn opportunities",
            "Identify and double down on the features that correlate with retention",
        ],
    },
    "nrr": {
        "RED": [
            "Build expansion revenue levers - seat-based pricing, usage tiers, or add-on features",
            "Create an in-product growth path that naturally leads to upgrades as teams grow",
            "Implement a customer health score to proactively address contraction risks",
            "Review pricing structure to ensure expansion is natural, not forced",
        ],
        "YELLOW": [
            "Add usage-based pricing elements that grow with customer success",
            "Create upgrade nudges triggered by team growth or feature adoption milestones",
            "Invest in customer success for your highest-expansion-potential accounts",
        ],
    },
    "time_to_value_days": {
        "RED": [
            "Map the critical path from signup to aha moment and remove every unnecessary step",
            "Offer guided setup that walks users through initial configuration in under 5 minutes",
            "Pre-build templates, samples, or demo data so users see value before creating anything",
            "Consider offering a concierge onboarding option for high-value signups",
        ],
        "YELLOW": [
            "A/B test removing onboarding steps to find the minimum viable setup",
            "Add contextual guidance that appears when users seem stuck",
            "Implement progressive profiling - collect setup info over time, not all upfront",
        ],
    },
    "payback_months": {
        "RED": [
            "Reduce CAC by investing more in PLG organic channels (product virality, content, community)",
            "Increase ARPU through better pricing or expansion revenue",
            "Focus acquisition spend on channels with the lowest CAC and highest LTV",
            "Consider product-qualified lead (PQL) scoring to focus sales effort on high-intent users",
        ],
        "YELLOW": [
            "Optimize paid acquisition campaigns to reduce cost per signup",
            "Test pricing changes that increase average deal value without reducing conversion",
            "Shift marketing spend toward channels with proven lower CAC",
        ],
    },
}


def get_recommendations(key: str, status: str) -> list[str]:
    """Get recommendations for a metric based on its traffic light status."""
    metric_recs = RECOMMENDATIONS.get(key, {})
    return metric_recs.get(status, [])


# ---------------------------------------------------------------------------
# Core analysis function
# ---------------------------------------------------------------------------

def analyze_funnel(
    signup_to_active: Optional[float] = None,
    free_to_paid: Optional[float] = None,
    monthly_churn: Optional[float] = None,
    nrr: Optional[float] = None,
    time_to_value_days: Optional[float] = None,
    payback_months: Optional[float] = None,
) -> FunnelAnalysisResult:
    """
    Analyze PLG funnel metrics against industry benchmarks.

    Args:
        signup_to_active: Signup-to-active rate as a percentage (e.g., 25.0 for 25%).
        free_to_paid: Free-to-paid conversion rate as a percentage.
        monthly_churn: Monthly churn rate as a percentage.
        nrr: Net revenue retention as a percentage (e.g., 105.0 for 105%).
        time_to_value_days: Time-to-value in days.
        payback_months: CAC payback period in months.

    Returns:
        FunnelAnalysisResult with assessments, score, health grade, leak,
        and recommendations.

    Raises:
        FunnelInputError: for NaN, negative or impossible values. Use
            normalize_metrics() first to accept strings like "25%" or "skip".
    """
    user_metrics: dict[str, float] = {}
    if signup_to_active is not None:
        user_metrics["signup_to_active"] = signup_to_active
    if free_to_paid is not None:
        user_metrics["free_to_paid"] = free_to_paid
    if monthly_churn is not None:
        user_metrics["monthly_churn"] = monthly_churn
    if nrr is not None:
        user_metrics["nrr"] = nrr
    if time_to_value_days is not None:
        user_metrics["time_to_value_days"] = time_to_value_days
    if payback_months is not None:
        user_metrics["payback_months"] = payback_months

    problems = [
        p for p in (_check_value(k, v) for k, v in user_metrics.items()) if p
    ]
    if problems:
        raise FunnelInputError(problems)

    assessments: list[MetricAssessment] = []
    positions: dict[str, float] = {}
    percentiles: dict[str, float] = {}
    green_count = 0
    yellow_count = 0
    red_count = 0
    all_recs: list[tuple[tuple[int, float], str]] = []

    for key, value in user_metrics.items():
        value = float(value)
        bench = BENCHMARKS[key]
        status = classify_metric(key, value)
        gap = calculate_gap_to_median(key, value)
        norm = normalized_position(key, value)
        positions[key] = norm
        percentiles[key] = percentile_position(key, value)
        recs = get_recommendations(key, status)

        if status == "GREEN":
            position = "Top 25% - outperforming most PLG companies"
            green_count += 1
        elif status == "YELLOW":
            position = "Middle 50% (between bottom-25% and top-25% thresholds)"
            yellow_count += 1
        else:
            position = "Bottom 25% - significant improvement needed"
            red_count += 1

        assessment = MetricAssessment(
            metric_key=key,
            metric_name=bench.name,
            value=value,
            unit=bench.unit,
            status=status,
            benchmark_position=position,
            gap_to_median=gap,
            recommendations=recs,
            percentile=percentiles[key],
            weight=SCORE_WEIGHTS[key],
        )
        assessments.append(assessment)

        # Weight recommendations by status first (RED before YELLOW before
        # GREEN), then by normalized position (worst metrics first).
        status_rank = 0 if status == "RED" else (1 if status == "YELLOW" else 2)
        for rec in recs:
            all_recs.append(((status_rank, norm), rec))

    # Overall health: weighted 0-100 score where missing metrics count as 0,
    # so the grade can only go up as data is added.
    score, best_case = funnel_score(percentiles)
    overall_health = overall_grade(score, len(user_metrics))
    missing = [BENCHMARKS[k].name for k in BENCHMARKS if k not in user_metrics]

    # Find biggest leak: the RED/YELLOW metric that sits lowest within its
    # own bottom-25% -> top-25% benchmark range. Normalizing by range keeps
    # differently-scaled metrics (e.g. TTV vs NRR) comparable.
    biggest_leak: Optional[MetricAssessment] = None
    worst_position = float("inf")
    for a in assessments:
        if a.status in ("RED", "YELLOW") and positions[a.metric_key] < worst_position:
            worst_position = positions[a.metric_key]
            biggest_leak = a

    # Sort and deduplicate recommendations
    all_recs.sort(key=lambda x: x[0])
    seen: set[str] = set()
    final_recs: list[str] = []
    for _, rec in all_recs:
        if rec not in seen:
            seen.add(rec)
            final_recs.append(rec)
        if len(final_recs) >= 5:
            break

    return FunnelAnalysisResult(
        metrics_assessment=assessments,
        overall_health=overall_health,
        biggest_leak=biggest_leak,
        recommendations=final_recs,
        green_count=green_count,
        yellow_count=yellow_count,
        red_count=red_count,
        score=score,
        best_case_score=best_case,
        metrics_provided=len(user_metrics),
        missing_metrics=missing,
    )


# ---------------------------------------------------------------------------
# Report printer
# ---------------------------------------------------------------------------

def format_value(value: float, unit: str) -> str:
    """Format a metric value with its unit: '25.0%', '5.0 days', '15.0 months'."""
    if unit == "%":
        return f"{value:.1f}%"
    return f"{value:.1f} {unit}"


def print_report(result: FunnelAnalysisResult) -> None:
    """Print a formatted funnel analysis report."""
    total_metrics = len(BENCHMARKS)
    print("=" * 70)
    print("  PLG FUNNEL ANALYSIS REPORT")
    print("=" * 70)
    print()

    # Overall health
    health_labels = {
        "A": "Excellent",
        "B": "Good",
        "C": "Fair",
        "D": "Needs Work",
        "F": "Critical",
        "N/A": "Insufficient Data",
    }
    if result.overall_health.startswith("Partial"):
        label = (
            f"no letter grade: provide at least {MIN_METRICS_FOR_GRADE} of the "
            f"{total_metrics} metrics"
        )
    else:
        label = health_labels.get(result.overall_health, "Unknown")
    print(f"  OVERALL FUNNEL HEALTH: {result.overall_health} ({label})")
    coverage = f"{result.metrics_provided} of {total_metrics} metrics"
    if result.missing_metrics:
        coverage += " - missing metrics count as 0"
    print(f"  FUNNEL SCORE: {result.score:.1f}/100 ({coverage})")
    if result.missing_metrics and result.metrics_provided:
        print(f"  Not provided: {', '.join(result.missing_metrics)}")
        print(
            f"  Best case if the missing metrics were top-tier: "
            f"{result.best_case_score:.1f}/100 "
            f"({grade_for_score(result.best_case_score)})"
        )
    print(f"  GREEN: {result.green_count} | YELLOW: {result.yellow_count} | RED: {result.red_count}")
    print()

    # Metric assessments
    print("-" * 70)
    print(f"  {'Metric':<25} {'Value':>12} {'Status':>8} {'vs Median':>11} {'Pctl':>6}")
    print("-" * 70)

    for a in result.metrics_assessment:
        gap_str = f"{a.gap_to_median:+.1f}%"
        value_str = format_value(a.value, a.unit)
        pct_str = f"p{a.percentile:.0f}"
        print(f"  {a.metric_name:<25} {value_str:>12} {a.status:>8} {gap_str:>11} {pct_str:>6}")

    print("-" * 70)
    print()

    # Biggest leak
    if result.biggest_leak:
        leak = result.biggest_leak
        print(f"  BIGGEST FUNNEL LEAK: {leak.metric_name}")
        print(f"  Current: {format_value(leak.value, leak.unit)} | Status: {leak.status}")
        print(f"  Gap to median: {leak.gap_to_median:+.1f}%")
        print()

    # Recommendations
    if result.recommendations:
        print("  TOP RECOMMENDATIONS (by priority):")
        print()
        for i, rec in enumerate(result.recommendations, 1):
            print(f"  {i}. {rec}")
        print()

    # Per-metric detail
    print("  DETAILED BREAKDOWN:")
    print()
    for a in result.metrics_assessment:
        print(f"  [{a.status}] {a.metric_name}: {format_value(a.value, a.unit)}")
        print(f"       {a.benchmark_position}")
        print(
            f"       Approx. percentile: {a.percentile:.0f} "
            f"(weight {a.weight:.0f} of 100 in the funnel score)"
        )
        if a.recommendations:
            for rec in a.recommendations[:2]:
                print(f"       -> {rec}")
        print()


# ---------------------------------------------------------------------------
# Standalone demo
# ---------------------------------------------------------------------------

def main() -> None:
    """Run the funnel analyzer with example data."""
    print("PLG Funnel Analyzer")
    print("=" * 40)
    print()

    # Example: A company with some strong and some weak metrics
    example_metrics = {
        "signup_to_active": 18.0,
        "free_to_paid": 3.0,
        "monthly_churn": 7.0,
        "nrr": 98.0,
        "time_to_value_days": 5.0,
        "payback_months": 15.0,
    }

    print("Running analysis with example metrics:")
    for key, value in example_metrics.items():
        bench = BENCHMARKS[key]
        print(f"  {bench.name}: {format_value(value, bench.unit)}")
    print()

    result = analyze_funnel(**example_metrics)
    print_report(result)

    # Also show what a healthy company looks like
    print()
    print("=" * 70)
    print("  COMPARISON: Top-performing PLG company example")
    print("=" * 70)
    print()

    healthy_metrics = {
        "signup_to_active": 45.0,
        "free_to_paid": 12.0,
        "monthly_churn": 2.5,
        "nrr": 125.0,
        "time_to_value_days": 0.5,
        "payback_months": 5.0,
    }

    print("Top-performer metrics:")
    for key, value in healthy_metrics.items():
        bench = BENCHMARKS[key]
        print(f"  {bench.name}: {format_value(value, bench.unit)}")
    print()

    healthy_result = analyze_funnel(**healthy_metrics)
    print_report(healthy_result)


def _fail(problems: list[str]) -> None:
    """Print readable input errors to stderr and exit with code 2."""
    import sys

    print("Input error - the funnel metrics could not be analyzed:", file=sys.stderr)
    for problem in problems:
        print(f"  - {problem}", file=sys.stderr)
    print(
        "Fix the values above and run again. Use percents as whole numbers "
        "(25 or \"25%\"), days for time_to_value_days, months for "
        "payback_months, and \"skip\" or null for a metric you do not have.",
        file=sys.stderr,
    )
    sys.exit(2)


def _cli() -> None:
    """Command-line entry point: JSON file, stdin, or --demo."""
    import argparse
    import json
    import sys

    parser = argparse.ArgumentParser(
        description="PLG funnel analyzer",
        epilog="JSON keys: signup_to_active, free_to_paid, monthly_churn, "
               "nrr, time_to_value_days, payback_months (all optional). "
               "Values: numbers, strings like \"25%\", or \"skip\"/null.",
    )
    parser.add_argument(
        "input", nargs="?",
        help="Path to a JSON file with funnel metrics (or '-' for stdin)",
    )
    parser.add_argument(
        "--demo", action="store_true", help="Run with built-in sample data"
    )
    args = parser.parse_args()

    if args.demo or (args.input is None and sys.stdin.isatty()):
        main()
        return

    source = "stdin" if args.input in (None, "-") else args.input
    try:
        if source == "stdin":
            payload = json.load(sys.stdin)
        else:
            with open(args.input, "r", encoding="utf-8") as fh:
                payload = json.load(fh)
    except FileNotFoundError:
        _fail([f"input file not found: {args.input}"])
    except (OSError, UnicodeDecodeError) as exc:
        _fail([f"could not read {source}: {exc}"])
    except json.JSONDecodeError as exc:
        _fail([f"{source} is not valid JSON: {exc}"])

    try:
        metrics, warnings = normalize_metrics(payload)
    except FunnelInputError as exc:
        _fail(exc.problems)

    for warning in warnings:
        print(f"Warning: {warning}", file=sys.stderr)

    result = analyze_funnel(**metrics)
    print_report(result)


if __name__ == "__main__":
    _cli()
