#!/usr/bin/env python3
"""SaaS Subscription Metrics Calculator.

Computes MRR, ARR, churn rates, CAC, LTV, LTV:CAC ratio, payback period,
Rule of 40, burn multiple, NRR, GRR, ARPU, Quick Ratio, Magic Number,
and expansion MRR rate from raw business data.

Each metric receives a traffic-light status (GREEN, YELLOW, RED) based on
industry benchmarks, and the calculator produces an overall health
assessment with actionable recommendations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class BusinessData:
    """Raw business inputs for metric calculation."""

    # MRR components
    new_mrr: float = 0.0
    expansion_mrr: float = 0.0
    contraction_mrr: float = 0.0
    churned_mrr: float = 0.0
    beginning_mrr: float = 0.0

    # Customer counts
    customers_start: int = 0
    customers_new: int = 0
    customers_churned: int = 0

    # Cost data
    total_sales_marketing_spend: float = 0.0
    total_operating_costs: float = 0.0
    gross_margin_pct: float = 0.70  # default 70%

    # Growth data
    yoy_revenue_growth_pct: float = 0.0
    profit_margin_pct: float = 0.0  # EBITDA margin

    # Optional: for burn multiple
    net_burn: Optional[float] = None

    # Optional: previous quarter S&M for Magic Number
    prev_quarter_sm_spend: Optional[float] = None
    current_quarter_net_new_arr: Optional[float] = None


@dataclass
class MetricResult:
    """A single computed metric with its assessment."""

    name: str
    value: float
    formatted: str
    status: str  # GREEN, YELLOW, RED
    benchmark_note: str


@dataclass
class HealthAssessment:
    """Overall SaaS health assessment."""

    grade: str  # A through F
    green_count: int
    yellow_count: int
    red_count: int
    total_count: int
    strengths: List[str] = field(default_factory=list)
    improvements: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Benchmark thresholds
# ---------------------------------------------------------------------------

THRESHOLDS = {
    "monthly_logo_churn": {"green": 2.0, "yellow": 5.0},
    "monthly_revenue_churn": {"green": 2.0, "yellow": 4.0},
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


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

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


def _fmt_pct(value: float) -> str:
    """Format as percentage with one decimal."""
    return f"{value:.1f}%"


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


# ---------------------------------------------------------------------------
# Core calculator
# ---------------------------------------------------------------------------

def calculate_all_metrics(data: BusinessData) -> Tuple[Dict[str, MetricResult], HealthAssessment, List[str]]:
    """Calculate all SaaS metrics from raw business data.

    Args:
        data: Raw business inputs.

    Returns:
        Tuple of (all_metrics dict, health_assessment, recommendations list).
    """
    metrics: Dict[str, MetricResult] = {}
    recommendations: List[str] = []

    # --- MRR ---
    ending_mrr = (
        data.beginning_mrr
        + data.new_mrr
        + data.expansion_mrr
        - data.contraction_mrr
        - data.churned_mrr
    )
    net_new_mrr = data.new_mrr + data.expansion_mrr - data.contraction_mrr - data.churned_mrr

    metrics["mrr"] = MetricResult(
        name="MRR",
        value=ending_mrr,
        formatted=_fmt_currency(ending_mrr),
        status="GREEN" if net_new_mrr > 0 else "RED",
        benchmark_note="Positive net new MRR expected",
    )

    # --- ARR ---
    arr = ending_mrr * 12
    metrics["arr"] = MetricResult(
        name="ARR",
        value=arr,
        formatted=_fmt_currency(arr),
        status="GREEN" if net_new_mrr > 0 else "RED",
        benchmark_note="ARR = MRR x 12",
    )

    # --- Net New MRR ---
    metrics["net_new_mrr"] = MetricResult(
        name="Net New MRR",
        value=net_new_mrr,
        formatted=_fmt_currency(net_new_mrr),
        status="GREEN" if net_new_mrr > 0 else "RED",
        benchmark_note="Should be positive every month",
    )

    # --- Monthly Logo Churn ---
    if data.customers_start > 0:
        logo_churn = (data.customers_churned / data.customers_start) * 100
    else:
        logo_churn = 0.0

    t = THRESHOLDS["monthly_logo_churn"]
    metrics["monthly_logo_churn"] = MetricResult(
        name="Monthly Logo Churn",
        value=logo_churn,
        formatted=_fmt_pct(logo_churn),
        status=_status_lower_is_better(logo_churn, t["green"], t["yellow"]),
        benchmark_note="<2% GREEN, 2-5% YELLOW, >5% RED",
    )
    if logo_churn > t["green"]:
        recommendations.append(
            "Reduce logo churn: implement customer health scoring, improve onboarding, "
            "and build proactive churn prevention workflows."
        )

    # --- Monthly Revenue Churn (Gross) ---
    if data.beginning_mrr > 0:
        gross_rev_churn = ((data.churned_mrr + data.contraction_mrr) / data.beginning_mrr) * 100
    else:
        gross_rev_churn = 0.0

    t = THRESHOLDS["monthly_revenue_churn"]
    metrics["monthly_revenue_churn"] = MetricResult(
        name="Monthly Revenue Churn",
        value=gross_rev_churn,
        formatted=_fmt_pct(gross_rev_churn),
        status=_status_lower_is_better(gross_rev_churn, t["green"], t["yellow"]),
        benchmark_note="<2% GREEN, 2-4% YELLOW, >4% RED",
    )

    # --- Net Revenue Churn ---
    if data.beginning_mrr > 0:
        net_rev_churn = (
            (data.churned_mrr + data.contraction_mrr - data.expansion_mrr)
            / data.beginning_mrr
        ) * 100
    else:
        net_rev_churn = 0.0

    metrics["net_revenue_churn"] = MetricResult(
        name="Net Revenue Churn",
        value=net_rev_churn,
        formatted=_fmt_pct(net_rev_churn),
        status="GREEN" if net_rev_churn < 0 else ("YELLOW" if net_rev_churn <= 1 else "RED"),
        benchmark_note="Negative is best (expansion exceeds churn)",
    )

    # --- NRR (Net Revenue Retention) ---
    if data.beginning_mrr > 0:
        nrr = (
            (data.beginning_mrr + data.expansion_mrr - data.contraction_mrr - data.churned_mrr)
            / data.beginning_mrr
        ) * 100
    else:
        nrr = 100.0

    t = THRESHOLDS["nrr"]
    metrics["nrr"] = MetricResult(
        name="Net Revenue Retention",
        value=nrr,
        formatted=_fmt_pct(nrr),
        status=_status_higher_is_better(nrr, t["green_min"], t["yellow_min"]),
        benchmark_note=">110% GREEN, 100-110% YELLOW, <100% RED",
    )
    if nrr < t["yellow_min"]:
        recommendations.append(
            "Improve NRR: drive expansion revenue through upsells and usage-based pricing, "
            "and reduce downgrades with proactive customer success."
        )

    # --- GRR (Gross Revenue Retention) ---
    if data.beginning_mrr > 0:
        grr = (
            (data.beginning_mrr - data.contraction_mrr - data.churned_mrr)
            / data.beginning_mrr
        ) * 100
        grr = min(grr, 100.0)  # capped at 100%
    else:
        grr = 100.0

    t = THRESHOLDS["grr"]
    metrics["grr"] = MetricResult(
        name="Gross Revenue Retention",
        value=grr,
        formatted=_fmt_pct(grr),
        status=_status_higher_is_better(grr, t["green_min"], t["yellow_min"]),
        benchmark_note=">90% GREEN, 80-90% YELLOW, <80% RED",
    )
    if grr < t["yellow_min"]:
        recommendations.append(
            "Improve GRR: focus on reducing cancellations through better product-market fit, "
            "onboarding improvements, and proactive support."
        )

    # --- ARPU ---
    customers_end = data.customers_start + data.customers_new - data.customers_churned
    if customers_end > 0:
        arpu = ending_mrr / customers_end
    else:
        arpu = 0.0

    metrics["arpu"] = MetricResult(
        name="ARPU",
        value=arpu,
        formatted=_fmt_currency(arpu),
        status="GREEN",  # context-dependent, no universal threshold
        benchmark_note="Varies by segment",
    )

    # --- CAC ---
    if data.customers_new > 0:
        cac = data.total_sales_marketing_spend / data.customers_new
    else:
        cac = 0.0

    metrics["cac"] = MetricResult(
        name="CAC (Blended)",
        value=cac,
        formatted=_fmt_currency(cac),
        status="GREEN",  # assessed via LTV:CAC ratio
        benchmark_note="Assessed via LTV:CAC ratio",
    )

    # --- LTV (Simple Method) ---
    monthly_churn_rate = logo_churn / 100 if logo_churn > 0 else 0.01
    ltv = arpu / monthly_churn_rate if monthly_churn_rate > 0 else 0.0

    metrics["ltv"] = MetricResult(
        name="LTV (Simple)",
        value=ltv,
        formatted=_fmt_currency(ltv),
        status="GREEN",  # assessed via LTV:CAC ratio
        benchmark_note="LTV = ARPU / monthly churn rate",
    )

    # --- LTV:CAC Ratio ---
    if cac > 0:
        ltv_cac = ltv / cac
    else:
        ltv_cac = 0.0

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
    if ltv_cac < t["green_min"] and ltv_cac > 0:
        recommendations.append(
            "Improve LTV:CAC ratio: reduce CAC through organic channels and better conversion, "
            "or increase LTV by reducing churn and driving expansion."
        )

    # --- CAC Payback Period ---
    monthly_gross_revenue_per_customer = arpu * data.gross_margin_pct
    if monthly_gross_revenue_per_customer > 0:
        payback_months = cac / monthly_gross_revenue_per_customer
    else:
        payback_months = 0.0

    t = THRESHOLDS["payback_months"]
    metrics["payback_period"] = MetricResult(
        name="CAC Payback Period",
        value=payback_months,
        formatted=_fmt_months(payback_months),
        status=_status_lower_is_better(payback_months, t["green"], t["yellow"]),
        benchmark_note="<18mo GREEN, 18-24mo YELLOW, >24mo RED",
    )
    if payback_months > t["green"]:
        recommendations.append(
            "Shorten CAC payback: increase ARPU, improve gross margins, "
            "or reduce acquisition costs to recover CAC faster."
        )

    # --- Rule of 40 ---
    rule_of_40 = data.yoy_revenue_growth_pct + data.profit_margin_pct

    t = THRESHOLDS["rule_of_40"]
    metrics["rule_of_40"] = MetricResult(
        name="Rule of 40",
        value=rule_of_40,
        formatted=_fmt_pct(rule_of_40),
        status=_status_higher_is_better(rule_of_40, t["green_min"], t["yellow_min"]),
        benchmark_note=">40% GREEN, 30-40% YELLOW, <30% RED",
    )
    if rule_of_40 < t["yellow_min"]:
        recommendations.append(
            "Improve Rule of 40 score: if growth is strong, focus on margins; "
            "if margins are healthy, invest more aggressively in growth."
        )

    # --- Burn Multiple ---
    if data.net_burn is not None:
        net_new_arr = net_new_mrr * 12
        if net_new_arr > 0:
            burn_multiple = data.net_burn / net_new_arr
        else:
            burn_multiple = float("inf")

        t = THRESHOLDS["burn_multiple"]
        if burn_multiple == float("inf"):
            bm_status = "RED"
        else:
            bm_status = _status_lower_is_better(burn_multiple, t["green"], t["yellow"])

        metrics["burn_multiple"] = MetricResult(
            name="Burn Multiple",
            value=burn_multiple,
            formatted=_fmt_multiple(burn_multiple) if burn_multiple != float("inf") else "N/A",
            status=bm_status,
            benchmark_note="<1.5x GREEN, 1.5-3x YELLOW, >3x RED",
        )
        if burn_multiple > t["green"] and burn_multiple != float("inf"):
            recommendations.append(
                "Reduce burn multiple: improve capital efficiency by growing ARR faster "
                "relative to cash burn, or cut low-ROI spend."
            )

    # --- Quick Ratio ---
    outflows = data.contraction_mrr + data.churned_mrr
    if outflows > 0:
        quick_ratio = (data.new_mrr + data.expansion_mrr) / outflows
    else:
        quick_ratio = float("inf")

    t = THRESHOLDS["quick_ratio"]
    if quick_ratio == float("inf"):
        qr_status = "GREEN"
        qr_formatted = "Infinite (no outflows)"
    else:
        qr_status = _status_higher_is_better(quick_ratio, t["green_min"], t["yellow_min"])
        qr_formatted = f"{quick_ratio:.1f}"

    metrics["quick_ratio"] = MetricResult(
        name="Quick Ratio",
        value=quick_ratio,
        formatted=qr_formatted,
        status=qr_status,
        benchmark_note=">4 GREEN, 2-4 YELLOW, <2 RED",
    )

    # --- Magic Number ---
    if data.prev_quarter_sm_spend is not None and data.current_quarter_net_new_arr is not None:
        if data.prev_quarter_sm_spend > 0:
            magic_number = data.current_quarter_net_new_arr / data.prev_quarter_sm_spend
        else:
            magic_number = 0.0

        t = THRESHOLDS["magic_number"]
        metrics["magic_number"] = MetricResult(
            name="Magic Number",
            value=magic_number,
            formatted=f"{magic_number:.2f}",
            status=_status_higher_is_better(magic_number, t["green_min"], t["yellow_min"]),
            benchmark_note=">0.75 GREEN, 0.5-0.75 YELLOW, <0.5 RED",
        )

    # --- Expansion MRR Rate ---
    if data.beginning_mrr > 0:
        expansion_rate = (data.expansion_mrr / data.beginning_mrr) * 100
    else:
        expansion_rate = 0.0

    t = THRESHOLDS["expansion_mrr_rate"]
    metrics["expansion_mrr_rate"] = MetricResult(
        name="Expansion MRR Rate",
        value=expansion_rate,
        formatted=_fmt_pct(expansion_rate),
        status=_status_higher_is_better(expansion_rate, t["green_min"], t["yellow_min"]),
        benchmark_note=">5% GREEN, 2-5% YELLOW, <2% RED",
    )
    if expansion_rate < t["yellow_min"]:
        recommendations.append(
            "Boost expansion MRR: introduce usage-based pricing tiers, "
            "add-on features, and proactive upsell motions through customer success."
        )

    # --- Health Assessment ---
    health = _compute_health_assessment(metrics)

    return metrics, health, recommendations


def _compute_health_assessment(metrics: Dict[str, MetricResult]) -> HealthAssessment:
    """Compute overall health grade from individual metric statuses.

    Args:
        metrics: Dictionary of computed metric results.

    Returns:
        HealthAssessment with grade, counts, strengths, and improvements.
    """
    green_count = sum(1 for m in metrics.values() if m.status == "GREEN")
    yellow_count = sum(1 for m in metrics.values() if m.status == "YELLOW")
    red_count = sum(1 for m in metrics.values() if m.status == "RED")
    total = len(metrics)

    green_pct = (green_count / total * 100) if total > 0 else 0

    # Determine grade
    if green_pct >= 80:
        grade = "A"
    elif green_pct >= 60 and red_count == 0:
        grade = "B"
    elif green_pct >= 40 or red_count <= 1:
        grade = "C"
    elif green_pct >= 20 or red_count <= 2:
        grade = "D"
    else:
        grade = "F"

    # Identify strengths (GREEN metrics)
    strengths = [m.name for m in metrics.values() if m.status == "GREEN"][:3]

    # Identify improvements (RED first, then YELLOW)
    reds = [m.name for m in metrics.values() if m.status == "RED"]
    yellows = [m.name for m in metrics.values() if m.status == "YELLOW"]
    improvements = (reds + yellows)[:3]

    return HealthAssessment(
        grade=grade,
        green_count=green_count,
        yellow_count=yellow_count,
        red_count=red_count,
        total_count=total,
        strengths=strengths,
        improvements=improvements,
    )


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def print_metrics_table(metrics: Dict[str, MetricResult]) -> None:
    """Print a formatted metrics table to stdout.

    Args:
        metrics: Dictionary of computed metric results.
    """
    print(f"\n{'Metric':<28} {'Value':<16} {'Status':<10} {'Benchmark'}")
    print("-" * 85)
    for m in metrics.values():
        print(f"{m.name:<28} {m.formatted:<16} {m.status:<10} {m.benchmark_note}")


def print_health_assessment(health: HealthAssessment) -> None:
    """Print the health assessment summary.

    Args:
        health: Computed health assessment.
    """
    print(f"\n{'=' * 50}")
    print(f"  Overall Health Grade: {health.grade}")
    print(f"  GREEN: {health.green_count} | YELLOW: {health.yellow_count} | RED: {health.red_count}")
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
        print("\n  No critical recommendations - metrics look healthy.")
        return

    print(f"\n{'=' * 50}")
    print("  Recommendations")
    print(f"{'=' * 50}")
    for idx, rec in enumerate(recommendations, 1):
        print(f"\n  {idx}. {rec}")


# ---------------------------------------------------------------------------
# Standalone demo
# ---------------------------------------------------------------------------

def main() -> None:
    """Run a demo calculation with sample SaaS data."""
    sample_data = BusinessData(
        beginning_mrr=100_000,
        new_mrr=15_000,
        expansion_mrr=8_000,
        contraction_mrr=2_000,
        churned_mrr=3_000,
        customers_start=500,
        customers_new=60,
        customers_churned=12,
        total_sales_marketing_spend=80_000,
        total_operating_costs=150_000,
        gross_margin_pct=0.75,
        yoy_revenue_growth_pct=85,
        profit_margin_pct=-20,
        net_burn=120_000,
        prev_quarter_sm_spend=220_000,
        current_quarter_net_new_arr=200_000,
    )

    print("SaaS Subscription Metrics Calculator")
    print("=" * 50)
    print("\nSample Business Data:")
    print(f"  Beginning MRR: {_fmt_currency(sample_data.beginning_mrr)}")
    print(f"  New MRR: {_fmt_currency(sample_data.new_mrr)}")
    print(f"  Expansion MRR: {_fmt_currency(sample_data.expansion_mrr)}")
    print(f"  Contraction MRR: {_fmt_currency(sample_data.contraction_mrr)}")
    print(f"  Churned MRR: {_fmt_currency(sample_data.churned_mrr)}")
    print(f"  Customers: {sample_data.customers_start} start, "
          f"+{sample_data.customers_new} new, -{sample_data.customers_churned} churned")
    print(f"  S&M Spend: {_fmt_currency(sample_data.total_sales_marketing_spend)}")
    print(f"  YoY Growth: {sample_data.yoy_revenue_growth_pct}%")
    print(f"  Profit Margin: {sample_data.profit_margin_pct}%")

    all_metrics, health, recommendations = calculate_all_metrics(sample_data)

    print_metrics_table(all_metrics)
    print_health_assessment(health)
    print_recommendations(recommendations)


if __name__ == "__main__":
    main()
