"""
Churn Risk Scorer for SaaS Customers

Calculates a churn risk score (0-100) based on customer behavior signals.
Provides risk level classification, top contributing signals, and
recommended intervention actions.

Usage:
    from churn_risk_scorer import score_churn_risk

    customer = {
        "login_frequency_last_30d": 3,
        "login_frequency_prev_30d": 15,
        "features_used_last_30d": 2,
        "features_used_prev_30d": 7,
        "support_tickets_last_90d": 0,
        "last_login_days_ago": 18,
        "contract_renewal_days": 25,
        "has_billing_issues": True,
        "seat_count_change": -2,
        "has_exported_data": False,
        "nps_score": 6,
    }

    result = score_churn_risk(customer)
    print(result)
"""

from typing import Any, Optional


def score_churn_risk(customer: dict[str, Any]) -> dict[str, Any]:
    """
    Calculate churn risk score from customer behavior data.

    Args:
        customer: Dictionary containing customer behavior signals.
            Required keys:
                - login_frequency_last_30d (int): Logins in the last 30 days.
                - login_frequency_prev_30d (int): Logins in the prior 30 days.
                - features_used_last_30d (int): Distinct features used last 30 days.
                - features_used_prev_30d (int): Distinct features used prior 30 days.
                - support_tickets_last_90d (int): Support tickets filed in 90 days.
                - last_login_days_ago (int): Days since the customer last logged in.
                - contract_renewal_days (int): Days until contract renewal.
                - has_billing_issues (bool): Whether there are active billing issues.
                - seat_count_change (int): Change in seat count (negative means reduction).
                - has_exported_data (bool): Whether the customer exported data recently.
            Optional keys:
                - nps_score (int or None): Most recent NPS score (0-10).

    Returns:
        Dictionary with keys:
            - risk_score (int): 0-100, where 0 is safe and 100 is imminent churn.
            - risk_level (str): LOW, MEDIUM, HIGH, or CRITICAL.
            - top_signals (list[str]): Top contributing risk signals, sorted by weight.
            - recommended_actions (list[str]): Intervention recommendations.
            - urgency (str): Description of how quickly to act.
    """
    score = 0
    signals: list[tuple[int, str]] = []

    # Login frequency decline
    prev_logins = customer["login_frequency_prev_30d"]
    curr_logins = customer["login_frequency_last_30d"]
    if prev_logins > 0:
        login_decline = (prev_logins - curr_logins) / prev_logins
        if login_decline > 0.5:
            score += 25
            signals.append((25, f"Login frequency declined {login_decline:.0%} in 30 days"))
    elif curr_logins == 0:
        score += 25
        signals.append((25, "No logins in the last 30 days (and none in prior period)"))

    # Feature abandonment
    prev_features = customer["features_used_prev_30d"]
    curr_features = customer["features_used_last_30d"]
    if prev_features > 0:
        feature_decline = (prev_features - curr_features) / prev_features
        if feature_decline > 0.3:
            score += 20
            signals.append((20, f"Feature usage declined {feature_decline:.0%} in 30 days"))

    # Days since last login
    days_since_login = customer["last_login_days_ago"]
    if days_since_login > 14:
        score += 20
        signals.append((20, f"Last login was {days_since_login} days ago (>14 days)"))
    elif days_since_login > 7:
        score += 10
        signals.append((10, f"Last login was {days_since_login} days ago (7-14 days)"))

    # Billing issues
    if customer["has_billing_issues"]:
        score += 15
        signals.append((15, "Active billing issues detected"))

    # Seat count reduction
    seat_change = customer["seat_count_change"]
    if seat_change < 0:
        score += 15
        signals.append((15, f"Seat count reduced by {abs(seat_change)}"))

    # Data export
    if customer["has_exported_data"]:
        score += 20
        signals.append((20, "Customer recently exported data"))

    # Contract renewal approaching
    renewal_days = customer["contract_renewal_days"]
    if renewal_days < 30:
        score += 10
        signals.append((10, f"Contract renewal in {renewal_days} days"))

    # NPS score
    nps_score: Optional[int] = customer.get("nps_score")
    if nps_score is not None:
        if nps_score < 5:
            score += 20
            signals.append((20, f"NPS score is {nps_score} (detractor, below 5)"))
        elif nps_score < 7:
            score += 10
            signals.append((10, f"NPS score is {nps_score} (passive, below 7)"))

    # Support ticket activity
    tickets = customer["support_tickets_last_90d"]
    if tickets == 0:
        score += 5
        signals.append((5, "Zero support tickets in 90 days (silent customer)"))
    elif tickets > 5:
        score -= 5
        signals.append((-5, f"{tickets} support tickets in 90 days (actively engaged)"))

    # Clamp score to 0-100
    score = max(0, min(100, score))

    # Determine risk level
    if score <= 25:
        risk_level = "LOW"
    elif score <= 50:
        risk_level = "MEDIUM"
    elif score <= 75:
        risk_level = "HIGH"
    else:
        risk_level = "CRITICAL"

    # Sort signals by weight descending
    signals.sort(key=lambda s: s[0], reverse=True)
    top_signals = [desc for _, desc in signals if _ > 0]

    # Determine recommended actions based on risk level
    recommended_actions = _get_recommendations(risk_level, signals, customer)

    # Determine urgency
    urgency = _get_urgency(risk_level)

    return {
        "risk_score": score,
        "risk_level": risk_level,
        "top_signals": top_signals,
        "recommended_actions": recommended_actions,
        "urgency": urgency,
    }


def _get_recommendations(
    risk_level: str,
    signals: list[tuple[int, str]],
    customer: dict[str, Any],
) -> list[str]:
    """Generate intervention recommendations based on risk level and signals."""
    actions: list[str] = []

    if risk_level == "CRITICAL":
        actions.append("Escalate to account manager for immediate personal outreach")
        actions.append("Prepare a custom retention offer (discount, extended trial, or feature unlock)")
        actions.append("Schedule an executive-level check-in call within 48 hours")
        actions.append("Conduct an internal review of the account's support and product history")

    elif risk_level == "HIGH":
        actions.append("Assign a dedicated customer success manager for proactive outreach")
        actions.append("Send a personalized value summary highlighting ROI and usage wins")
        actions.append("Offer a guided training or onboarding refresh session")
        if customer.get("has_billing_issues"):
            actions.append("Resolve billing issues immediately and confirm payment method")

    elif risk_level == "MEDIUM":
        actions.append("Send a re-engagement email series with product tips and new features")
        actions.append("Schedule a quarterly business review to realign on goals")
        actions.append("Share relevant case studies or success stories from similar customers")
        if customer.get("contract_renewal_days", 999) < 60:
            actions.append("Begin the renewal conversation early with a value recap")

    else:  # LOW
        actions.append("Continue standard monitoring cadence")
        actions.append("Include in next NPS or CSAT survey batch")
        actions.append("Consider for upsell or expansion outreach")

    return actions


def _get_urgency(risk_level: str) -> str:
    """Return urgency description for the given risk level."""
    urgency_map = {
        "CRITICAL": "Act within 24-48 hours. This customer is at imminent risk of churning.",
        "HIGH": "Act within 1 week. Proactive intervention is needed to prevent further disengagement.",
        "MEDIUM": "Act within 2-4 weeks. Monitor closely and begin re-engagement efforts.",
        "LOW": "Routine monitoring. No immediate intervention required.",
    }
    return urgency_map[risk_level]


def main() -> None:
    """Standalone demo of the churn risk scorer."""
    print("=" * 60)
    print("Churn Risk Scorer - Demo")
    print("=" * 60)

    # Example: High-risk customer
    high_risk_customer = {
        "login_frequency_last_30d": 2,
        "login_frequency_prev_30d": 20,
        "features_used_last_30d": 1,
        "features_used_prev_30d": 6,
        "support_tickets_last_90d": 0,
        "last_login_days_ago": 18,
        "contract_renewal_days": 25,
        "has_billing_issues": True,
        "seat_count_change": -3,
        "has_exported_data": False,
        "nps_score": 4,
    }

    print("\nCustomer A - Declining engagement with billing issues")
    print("-" * 60)
    result = score_churn_risk(high_risk_customer)
    _print_result(result)

    # Example: Low-risk customer
    low_risk_customer = {
        "login_frequency_last_30d": 22,
        "login_frequency_prev_30d": 20,
        "features_used_last_30d": 8,
        "features_used_prev_30d": 7,
        "support_tickets_last_90d": 3,
        "last_login_days_ago": 1,
        "contract_renewal_days": 200,
        "has_billing_issues": False,
        "seat_count_change": 2,
        "has_exported_data": False,
        "nps_score": 9,
    }

    print("\nCustomer B - Healthy and growing")
    print("-" * 60)
    result = score_churn_risk(low_risk_customer)
    _print_result(result)

    # Example: Medium-risk customer
    medium_risk_customer = {
        "login_frequency_last_30d": 10,
        "login_frequency_prev_30d": 15,
        "features_used_last_30d": 4,
        "features_used_prev_30d": 5,
        "support_tickets_last_90d": 1,
        "last_login_days_ago": 10,
        "contract_renewal_days": 45,
        "has_billing_issues": False,
        "seat_count_change": 0,
        "has_exported_data": True,
        "nps_score": 6,
    }

    print("\nCustomer C - Some warning signs")
    print("-" * 60)
    result = score_churn_risk(medium_risk_customer)
    _print_result(result)


def _print_result(result: dict[str, Any]) -> None:
    """Pretty-print a churn risk result."""
    print(f"  Risk Score: {result['risk_score']}/100")
    print(f"  Risk Level: {result['risk_level']}")
    print(f"  Urgency:    {result['urgency']}")
    print(f"\n  Top Signals:")
    for i, signal in enumerate(result["top_signals"], 1):
        print(f"    {i}. {signal}")
    print(f"\n  Recommended Actions:")
    for i, action in enumerate(result["recommended_actions"], 1):
        print(f"    {i}. {action}")
    print()


if __name__ == "__main__":
    main()
