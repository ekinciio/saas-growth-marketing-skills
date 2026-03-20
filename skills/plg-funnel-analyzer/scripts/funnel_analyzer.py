"""
PLG Funnel Analyzer - Product-Led Growth Funnel Assessment Tool

Accepts user metrics, runs benchmark comparisons with traffic light scoring,
detects the biggest funnel leak, and generates prioritized recommendations.

Usage:
    python funnel_analyzer.py

Requirements:
    No external dependencies - uses only the Python standard library.
"""

import sys
from dataclasses import dataclass, field
from typing import Optional


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
        bottom_25=18.0,
        median=12.0,
        top_25=6.0,
        higher_is_better=False,
        description="Months to recover customer acquisition cost",
    ),
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


@dataclass
class FunnelAnalysisResult:
    """Complete funnel analysis result."""
    metrics_assessment: list[MetricAssessment]
    overall_health: str  # Letter grade A-F
    biggest_leak: Optional[MetricAssessment]
    recommendations: list[str]
    green_count: int = 0
    yellow_count: int = 0
    red_count: int = 0


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
        elif value >= bench.median:
            return "YELLOW"
        else:
            return "RED"
    else:
        # Lower is better (churn, TTV, payback)
        if value <= bench.top_25:
            return "GREEN"
        elif value <= bench.median:
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
        FunnelAnalysisResult with assessments, health grade, leak, and recommendations.
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

    assessments: list[MetricAssessment] = []
    green_count = 0
    yellow_count = 0
    red_count = 0
    all_recs: list[tuple[float, str]] = []

    for key, value in user_metrics.items():
        bench = BENCHMARKS[key]
        status = classify_metric(key, value)
        gap = calculate_gap_to_median(key, value)
        recs = get_recommendations(key, status)

        if status == "GREEN":
            position = "Top 25% - outperforming most PLG companies"
            green_count += 1
        elif status == "YELLOW":
            position = "Median range - room for improvement"
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
        )
        assessments.append(assessment)

        # Weight recommendations by severity
        priority = 0 if status == "RED" else (1 if status == "YELLOW" else 2)
        for rec in recs:
            all_recs.append((priority + abs(gap) * -0.01, rec))

    # Determine overall health
    total = green_count + yellow_count + red_count
    if total == 0:
        overall_health = "N/A"
    elif red_count >= 3:
        overall_health = "F"
    elif red_count >= 2:
        overall_health = "D"
    elif red_count >= 1 and yellow_count >= 2:
        overall_health = "D"
    elif yellow_count >= 3 and green_count < 2:
        overall_health = "C"
    elif green_count >= 5:
        overall_health = "A"
    elif green_count >= 3:
        overall_health = "B"
    elif green_count >= 1 and yellow_count >= 2:
        overall_health = "C"
    else:
        overall_health = "C"

    # Find biggest leak (worst relative gap among RED/YELLOW metrics)
    biggest_leak: Optional[MetricAssessment] = None
    worst_gap = float("inf")
    for a in assessments:
        if a.status in ("RED", "YELLOW") and a.gap_to_median < worst_gap:
            worst_gap = a.gap_to_median
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
    )


# ---------------------------------------------------------------------------
# Report printer
# ---------------------------------------------------------------------------

def print_report(result: FunnelAnalysisResult) -> None:
    """Print a formatted funnel analysis report."""
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
    label = health_labels.get(result.overall_health, "Unknown")
    print(f"  OVERALL FUNNEL HEALTH: {result.overall_health} ({label})")
    print(f"  GREEN: {result.green_count} | YELLOW: {result.yellow_count} | RED: {result.red_count}")
    print()

    # Metric assessments
    print("-" * 70)
    print(f"  {'Metric':<25} {'Value':>10} {'Status':>8} {'vs Median':>12}")
    print("-" * 70)

    for a in result.metrics_assessment:
        gap_str = f"{a.gap_to_median:+.1f}%"
        value_str = f"{a.value:.1f}{a.unit}"
        print(f"  {a.metric_name:<25} {value_str:>10} {a.status:>8} {gap_str:>12}")

    print("-" * 70)
    print()

    # Biggest leak
    if result.biggest_leak:
        leak = result.biggest_leak
        print(f"  BIGGEST FUNNEL LEAK: {leak.metric_name}")
        print(f"  Current: {leak.value:.1f}{leak.unit} | Status: {leak.status}")
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
        print(f"  [{a.status}] {a.metric_name}: {a.value:.1f}{a.unit}")
        print(f"       {a.benchmark_position}")
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
        print(f"  {bench.name}: {value}{bench.unit}")
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
        print(f"  {bench.name}: {value}{bench.unit}")
    print()

    healthy_result = analyze_funnel(**healthy_metrics)
    print_report(healthy_result)


if __name__ == "__main__":
    main()
