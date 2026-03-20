"""
SaaS Pricing Analyzer

Analyzes pricing strategy through tier gap analysis, competitive positioning,
and Van Westendorp price sensitivity calculations.

Usage:
    from pricing_analyzer import analyze_pricing

    own_pricing = {
        "tiers": [
            {"name": "Starter", "price": 29, "features": ["5 users", "Basic analytics", "Email support"]},
            {"name": "Pro", "price": 79, "features": ["25 users", "Advanced analytics", "Priority support", "API access"]},
            {"name": "Enterprise", "price": 199, "features": ["Unlimited users", "Custom analytics", "Dedicated support", "API access", "SSO", "SLA"]},
        ]
    }

    result = analyze_pricing(own_pricing)
    print(result)
"""

from typing import Any, Optional


def analyze_pricing(
    own_pricing: dict[str, Any],
    competitor_pricing: Optional[list[dict[str, Any]]] = None,
    survey_data: Optional[dict[str, list[float]]] = None,
) -> dict[str, Any]:
    """
    Analyze SaaS pricing strategy.

    Args:
        own_pricing: Dictionary with key "tiers", a list of tier dicts.
            Each tier dict has:
                - name (str): Tier name.
                - price (float): Monthly price in dollars.
                - features (list[str]): List of feature descriptions.
        competitor_pricing: Optional list of competitor dicts, each with:
                - company (str): Competitor name.
                - tiers (list[dict]): Same format as own_pricing tiers.
            Note: All competitor data must be manually entered by the user.
        survey_data: Optional Van Westendorp survey results with keys:
                - too_cheap (list[float]): Prices respondents consider too cheap.
                - bargain (list[float]): Prices respondents consider a bargain.
                - expensive (list[float]): Prices respondents consider getting expensive.
                - too_expensive (list[float]): Prices respondents consider too expensive.

    Returns:
        Dictionary with keys:
            - tier_analysis (dict): Gap analysis of current tiers.
            - competitive_positioning (dict or None): Positioning vs competitors.
            - van_westendorp (dict or None): Price sensitivity results.
            - recommended_changes (list[str]): Prioritized recommendations.
            - positioning_summary (str): Overall positioning assessment.
    """
    tier_analysis = _analyze_tiers(own_pricing["tiers"])

    competitive_positioning = None
    if competitor_pricing:
        competitive_positioning = _analyze_competitive_positioning(
            own_pricing["tiers"], competitor_pricing
        )

    van_westendorp = None
    if survey_data:
        van_westendorp = _calculate_van_westendorp(survey_data)

    recommended_changes = _generate_recommendations(
        tier_analysis, competitive_positioning, van_westendorp
    )

    positioning_summary = _generate_positioning_summary(
        own_pricing["tiers"], competitive_positioning
    )

    return {
        "tier_analysis": tier_analysis,
        "competitive_positioning": competitive_positioning,
        "van_westendorp": van_westendorp,
        "recommended_changes": recommended_changes,
        "positioning_summary": positioning_summary,
    }


def _analyze_tiers(tiers: list[dict[str, Any]]) -> dict[str, Any]:
    """Analyze tier structure for gaps and issues."""
    if not tiers:
        return {"error": "No tiers provided"}

    sorted_tiers = sorted(tiers, key=lambda t: t["price"])
    analysis: dict[str, Any] = {
        "tier_count": len(sorted_tiers),
        "price_range": {
            "min": sorted_tiers[0]["price"],
            "max": sorted_tiers[-1]["price"],
        },
        "tiers": [],
        "issues": [],
    }

    for i, tier in enumerate(sorted_tiers):
        tier_info: dict[str, Any] = {
            "name": tier["name"],
            "price": tier["price"],
            "feature_count": len(tier["features"]),
            "price_per_feature": (
                round(tier["price"] / len(tier["features"]), 2)
                if tier["features"]
                else 0
            ),
        }

        # Check price jump to next tier
        if i < len(sorted_tiers) - 1:
            next_tier = sorted_tiers[i + 1]
            price_jump = next_tier["price"] - tier["price"]
            price_jump_pct = (
                (price_jump / tier["price"] * 100) if tier["price"] > 0 else 0
            )
            feature_jump = len(next_tier["features"]) - len(tier["features"])

            tier_info["price_jump_to_next"] = price_jump
            tier_info["price_jump_pct"] = round(price_jump_pct, 1)
            tier_info["feature_jump_to_next"] = feature_jump

            # Flag issues
            if price_jump_pct > 200:
                analysis["issues"].append(
                    f"Large price gap ({price_jump_pct:.0f}%) between "
                    f"{tier['name']} and {next_tier['name']} - "
                    f"consider adding an intermediate tier"
                )

            if feature_jump <= 1 and price_jump > 0:
                analysis["issues"].append(
                    f"Only {feature_jump} new feature(s) between "
                    f"{tier['name']} (${tier['price']}) and "
                    f"{next_tier['name']} (${next_tier['price']}) - "
                    f"weak upgrade justification"
                )

        analysis["tiers"].append(tier_info)

    # Check tier count
    if len(sorted_tiers) < 3:
        analysis["issues"].append(
            "Fewer than 3 tiers - consider adding tiers for better price anchoring"
        )
    elif len(sorted_tiers) > 4:
        analysis["issues"].append(
            "More than 4 tiers may create decision paralysis - consider consolidating"
        )

    # Check if lowest tier is free
    if sorted_tiers[0]["price"] > 0:
        analysis["issues"].append(
            "No free tier - consider freemium or reverse trial for top-of-funnel growth"
        )

    return analysis


def _analyze_competitive_positioning(
    own_tiers: list[dict[str, Any]],
    competitors: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compare pricing against competitors."""
    own_sorted = sorted(own_tiers, key=lambda t: t["price"])
    own_avg_price = sum(t["price"] for t in own_sorted) / len(own_sorted)
    own_avg_features = sum(len(t["features"]) for t in own_sorted) / len(own_sorted)

    competitor_analysis = []
    for comp in competitors:
        comp_tiers = sorted(comp["tiers"], key=lambda t: t["price"])
        comp_avg_price = sum(t["price"] for t in comp_tiers) / len(comp_tiers)
        comp_avg_features = (
            sum(len(t["features"]) for t in comp_tiers) / len(comp_tiers)
        )

        price_diff_pct = ((own_avg_price - comp_avg_price) / comp_avg_price * 100) if comp_avg_price > 0 else 0

        positioning = "similar"
        if price_diff_pct > 20:
            positioning = "premium"
        elif price_diff_pct < -20:
            positioning = "value"

        competitor_analysis.append(
            {
                "company": comp["company"],
                "avg_price": round(comp_avg_price, 2),
                "avg_features": round(comp_avg_features, 1),
                "tier_count": len(comp_tiers),
                "price_range": {
                    "min": comp_tiers[0]["price"],
                    "max": comp_tiers[-1]["price"],
                },
                "your_price_diff_pct": round(price_diff_pct, 1),
                "relative_positioning": positioning,
            }
        )

    all_avg_prices = [c["avg_price"] for c in competitor_analysis]
    market_avg = sum(all_avg_prices) / len(all_avg_prices) if all_avg_prices else 0

    return {
        "your_avg_price": round(own_avg_price, 2),
        "your_avg_features": round(own_avg_features, 1),
        "market_avg_price": round(market_avg, 2),
        "competitors": competitor_analysis,
        "your_position": (
            "above market" if own_avg_price > market_avg * 1.1
            else "below market" if own_avg_price < market_avg * 0.9
            else "at market"
        ),
    }


def _calculate_van_westendorp(
    survey_data: dict[str, list[float]],
) -> dict[str, Any]:
    """
    Calculate Van Westendorp price sensitivity intersections.

    The four intersection points:
        - OPP (Optimal Price Point): too_cheap and too_expensive intersect
        - IDP (Indifference Price Point): bargain and expensive intersect
        - PME (Point of Marginal Expensiveness): bargain cumulative and too_expensive cumulative
        - PMC (Point of Marginal Cheapness): too_cheap cumulative and expensive cumulative
    """
    too_cheap = sorted(survey_data["too_cheap"])
    bargain = sorted(survey_data["bargain"])
    expensive = sorted(survey_data["expensive"])
    too_expensive = sorted(survey_data["too_expensive"])

    # Build a common price range
    all_prices = too_cheap + bargain + expensive + too_expensive
    if not all_prices:
        return {"error": "No survey data provided"}

    min_price = min(all_prices)
    max_price = max(all_prices)
    step = (max_price - min_price) / 200
    if step == 0:
        return {"error": "All survey responses are the same price"}

    price_points = [min_price + i * step for i in range(201)]

    def cumulative_pct_below(data: list[float], price: float) -> float:
        count = sum(1 for v in data if v <= price)
        return count / len(data) * 100 if data else 0

    def cumulative_pct_above(data: list[float], price: float) -> float:
        count = sum(1 for v in data if v >= price)
        return count / len(data) * 100 if data else 0

    # Find intersections by scanning price points
    opp = _find_intersection(
        price_points,
        lambda p: cumulative_pct_below(too_cheap, p),
        lambda p: cumulative_pct_above(too_expensive, p),
    )

    idp = _find_intersection(
        price_points,
        lambda p: cumulative_pct_below(bargain, p),
        lambda p: cumulative_pct_above(expensive, p),
    )

    pme = _find_intersection(
        price_points,
        lambda p: cumulative_pct_below(expensive, p),
        lambda p: cumulative_pct_below(too_expensive, p),
    )

    pmc = _find_intersection(
        price_points,
        lambda p: cumulative_pct_above(too_cheap, p),
        lambda p: cumulative_pct_above(bargain, p),
    )

    acceptable_range = {
        "low": round(pmc, 2) if pmc else None,
        "high": round(pme, 2) if pme else None,
    }

    return {
        "optimal_price_point": round(opp, 2) if opp else None,
        "indifference_price_point": round(idp, 2) if idp else None,
        "point_of_marginal_expensiveness": round(pme, 2) if pme else None,
        "point_of_marginal_cheapness": round(pmc, 2) if pmc else None,
        "acceptable_price_range": acceptable_range,
        "sample_size": len(too_cheap),
        "recommendation": (
            f"Set price between ${acceptable_range['low']} and "
            f"${acceptable_range['high']}, targeting ${round(opp, 2) if opp else 'N/A'} "
            f"as the optimal price point."
            if opp and pmc and pme
            else "Insufficient data to determine optimal price point."
        ),
    }


def _find_intersection(
    price_points: list[float],
    curve_a: Any,
    curve_b: Any,
) -> Optional[float]:
    """Find the price where two cumulative curves intersect."""
    prev_diff = None
    for price in price_points:
        val_a = curve_a(price)
        val_b = curve_b(price)
        diff = val_a - val_b
        if prev_diff is not None and prev_diff * diff < 0:
            return price
        prev_diff = diff
    return None


def _generate_recommendations(
    tier_analysis: dict[str, Any],
    competitive: Optional[dict[str, Any]],
    van_westendorp: Optional[dict[str, Any]],
) -> list[str]:
    """Generate prioritized pricing recommendations."""
    recommendations: list[str] = []

    # Tier-based recommendations
    for issue in tier_analysis.get("issues", []):
        recommendations.append(f"Tier structure: {issue}")

    # Competitive recommendations
    if competitive:
        position = competitive.get("your_position", "")
        if position == "above market":
            recommendations.append(
                "Your average price is above market - ensure your premium positioning "
                "is justified by clear feature differentiation and brand strength."
            )
        elif position == "below market":
            recommendations.append(
                "Your average price is below market - you may have room for a price "
                "increase. Test a 10-15% increase on new customers first."
            )

    # Van Westendorp recommendations
    if van_westendorp and van_westendorp.get("optimal_price_point"):
        opp = van_westendorp["optimal_price_point"]
        recommendations.append(
            f"Van Westendorp analysis suggests an optimal price point of ${opp}. "
            f"Align your most popular tier close to this price."
        )

    if not recommendations:
        recommendations.append(
            "No major issues detected. Consider running a Van Westendorp survey "
            "or adding competitor data for deeper analysis."
        )

    return recommendations


def _generate_positioning_summary(
    own_tiers: list[dict[str, Any]],
    competitive: Optional[dict[str, Any]],
) -> str:
    """Generate a text summary of pricing positioning."""
    sorted_tiers = sorted(own_tiers, key=lambda t: t["price"])
    price_range = f"${sorted_tiers[0]['price']} - ${sorted_tiers[-1]['price']}/mo"
    tier_names = ", ".join(t["name"] for t in sorted_tiers)

    summary = (
        f"Your pricing spans {price_range} across {len(sorted_tiers)} tiers "
        f"({tier_names})."
    )

    if competitive:
        position = competitive["your_position"]
        market_avg = competitive["market_avg_price"]
        summary += (
            f" Relative to competitors, you are positioned {position} "
            f"(market average: ${market_avg}/mo)."
        )

    return summary


def main() -> None:
    """Standalone demo of the pricing analyzer."""
    print("=" * 60)
    print("Pricing Analyzer - Demo")
    print("=" * 60)

    # Example: Own pricing
    own_pricing = {
        "tiers": [
            {
                "name": "Starter",
                "price": 29,
                "features": [
                    "5 users",
                    "Basic analytics",
                    "Email support",
                    "1 GB storage",
                ],
            },
            {
                "name": "Pro",
                "price": 79,
                "features": [
                    "25 users",
                    "Advanced analytics",
                    "Priority support",
                    "API access",
                    "10 GB storage",
                    "Custom reports",
                ],
            },
            {
                "name": "Enterprise",
                "price": 199,
                "features": [
                    "Unlimited users",
                    "Custom analytics",
                    "Dedicated support",
                    "API access",
                    "Unlimited storage",
                    "SSO",
                    "SLA",
                    "Custom integrations",
                ],
            },
        ]
    }

    # Example: Competitor pricing (manually entered)
    competitors = [
        {
            "company": "Competitor A",
            "tiers": [
                {"name": "Basic", "price": 19, "features": ["3 users", "Basic reporting", "Email support"]},
                {"name": "Business", "price": 59, "features": ["15 users", "Advanced reporting", "Chat support", "API"]},
                {"name": "Enterprise", "price": 149, "features": ["Unlimited users", "Custom reporting", "Phone support", "API", "SSO"]},
            ],
        },
        {
            "company": "Competitor B",
            "tiers": [
                {"name": "Free", "price": 0, "features": ["2 users", "Basic features"]},
                {"name": "Team", "price": 49, "features": ["10 users", "Core features", "Email support"]},
                {"name": "Business", "price": 99, "features": ["50 users", "All features", "Priority support", "API"]},
                {"name": "Enterprise", "price": 249, "features": ["Unlimited users", "All features", "Dedicated CSM", "SLA", "SSO"]},
            ],
        },
    ]

    # Example: Van Westendorp survey data
    survey_data = {
        "too_cheap": [10, 15, 15, 20, 20, 20, 25, 25, 30, 30, 30, 35, 35, 40, 40],
        "bargain": [25, 30, 35, 35, 40, 40, 45, 45, 50, 50, 55, 55, 60, 60, 65],
        "expensive": [60, 65, 70, 70, 75, 80, 80, 85, 85, 90, 90, 95, 100, 100, 110],
        "too_expensive": [80, 90, 95, 100, 100, 110, 110, 120, 120, 130, 130, 140, 150, 150, 160],
    }

    print("\n--- Analysis with all data ---\n")
    result = analyze_pricing(own_pricing, competitors, survey_data)

    print("Positioning Summary:")
    print(f"  {result['positioning_summary']}")

    print(f"\nTier Analysis ({result['tier_analysis']['tier_count']} tiers):")
    for tier in result["tier_analysis"]["tiers"]:
        print(f"  {tier['name']}: ${tier['price']}/mo - {tier['feature_count']} features (${tier['price_per_feature']}/feature)")

    if result["tier_analysis"]["issues"]:
        print("\n  Issues:")
        for issue in result["tier_analysis"]["issues"]:
            print(f"    - {issue}")

    if result["competitive_positioning"]:
        cp = result["competitive_positioning"]
        print(f"\nCompetitive Positioning:")
        print(f"  Your avg price: ${cp['your_avg_price']}")
        print(f"  Market avg price: ${cp['market_avg_price']}")
        print(f"  Position: {cp['your_position']}")
        for comp in cp["competitors"]:
            print(f"  vs {comp['company']}: {comp['your_price_diff_pct']:+.1f}% ({comp['relative_positioning']})")

    if result["van_westendorp"]:
        vw = result["van_westendorp"]
        print(f"\nVan Westendorp Analysis (n={vw['sample_size']}):")
        print(f"  Optimal Price Point: ${vw['optimal_price_point']}")
        print(f"  Indifference Price Point: ${vw['indifference_price_point']}")
        print(f"  Acceptable Range: ${vw['acceptable_price_range']['low']} - ${vw['acceptable_price_range']['high']}")
        print(f"  Recommendation: {vw['recommendation']}")

    print(f"\nRecommended Changes:")
    for i, rec in enumerate(result["recommended_changes"], 1):
        print(f"  {i}. {rec}")


if __name__ == "__main__":
    main()
