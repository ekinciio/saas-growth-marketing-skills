#!/usr/bin/env python3
"""Onboarding Flow Scorer.

Evaluates SaaS user onboarding flows on a 0-100 scale based on friction
factors, guidance quality, and time-to-value. Recommends an onboarding
pattern and produces a prioritized improvement list with estimated
activation lift.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class OnboardingFlow:
    """Details of an onboarding flow to evaluate."""

    total_steps: int = 5
    required_fields: int = 3
    has_progress_indicator: bool = False
    has_skip_option: bool = False
    has_template_gallery: bool = False
    has_empty_state_education: bool = False
    time_to_first_value_minutes: float = 10.0
    requires_credit_card_upfront: bool = False
    has_welcome_email_sequence: bool = False
    has_in_app_guidance: bool = False
    product_type: Optional[str] = None  # visual, data, collaboration, developer, business_ops, content


@dataclass
class ScoreBreakdown:
    """Individual scoring adjustment with explanation."""

    factor: str
    adjustment: int
    detail: str


@dataclass
class Improvement:
    """A recommended improvement with expected impact."""

    action: str
    reason: str
    estimated_activation_lift_pct: Tuple[float, float]  # (low, high) range
    difficulty: str  # low, medium, high
    priority: int  # 1 = highest


@dataclass
class ScoringResult:
    """Complete scoring result for an onboarding flow."""

    score: int
    grade: str
    breakdown: List[ScoreBreakdown] = field(default_factory=list)
    recommended_pattern: str = ""
    pattern_rationale: str = ""
    improvements: List[Improvement] = field(default_factory=list)
    estimated_activation_lift_pct: Tuple[float, float] = (0.0, 0.0)


# ---------------------------------------------------------------------------
# Pattern mapping
# ---------------------------------------------------------------------------

PATTERN_MAP: Dict[str, Tuple[str, str]] = {
    "visual": (
        "Product Tour",
        "Visual products benefit most from a guided tour that highlights key tools "
        "and interface elements. Users need to learn where things are before they "
        "can create value.",
    ),
    "data": (
        "Empty State Education",
        "Data-dependent products start empty. Educational empty states guide users "
        "to populate their workspace and understand what each section does, "
        "accelerating the path to meaningful insights.",
    ),
    "collaboration": (
        "Checklist/Wizard",
        "Collaboration tools require team setup, invitations, and workspace "
        "configuration. A structured checklist ensures all critical setup tasks "
        "are completed before the team starts working.",
    ),
    "developer": (
        "Progressive Disclosure",
        "Developer tools have deep feature sets that can overwhelm on first use. "
        "Progressive disclosure lets developers start with core functionality and "
        "discover advanced features as they build proficiency.",
    ),
    "business_ops": (
        "Checklist/Wizard",
        "Business operations tools (CRM, ERP) need meaningful configuration - "
        "connecting accounts, importing data, defining workflows. A setup wizard "
        "ensures the system is properly configured before daily use.",
    ),
    "content": (
        "Template Gallery",
        "Content and creative tools suffer from blank-canvas paralysis. Templates "
        "give users an immediate starting point, showcase what is possible, and "
        "dramatically reduce time-to-first-output.",
    ),
}

DEFAULT_PATTERN = (
    "Checklist/Wizard",
    "When the product type is unknown, a setup checklist is the safest default - "
    "it provides structure without assuming too much about the product's interface.",
)


# ---------------------------------------------------------------------------
# Scoring logic
# ---------------------------------------------------------------------------

def score_onboarding(flow: OnboardingFlow) -> ScoringResult:
    """Score an onboarding flow on a 0-100 scale.

    Scoring starts at a base of 50 and applies adjustments based on
    onboarding flow characteristics. The final score is capped at 0-100.

    Args:
        flow: Onboarding flow details to evaluate.

    Returns:
        ScoringResult with score, grade, breakdown, pattern recommendation,
        and improvement suggestions.
    """
    base_score = 50
    breakdown: List[ScoreBreakdown] = []
    adjustments = 0

    breakdown.append(ScoreBreakdown(
        factor="Base score",
        adjustment=base_score,
        detail="Starting point for all onboarding flows",
    ))

    # --- Total steps ---
    if flow.total_steps > 7:
        adj = -15
        detail = f"{flow.total_steps} steps is too many; aim for under 5"
    elif flow.total_steps >= 5:
        adj = -5
        detail = f"{flow.total_steps} steps is acceptable but could be tighter"
    else:
        adj = 0
        detail = f"{flow.total_steps} steps is optimal (under 5)"
    adjustments += adj
    breakdown.append(ScoreBreakdown(factor="Total steps", adjustment=adj, detail=detail))

    # --- Required fields ---
    if flow.required_fields > 5:
        adj = -15
        detail = f"{flow.required_fields} required fields creates heavy signup friction"
    elif flow.required_fields >= 3:
        adj = -5
        detail = f"{flow.required_fields} required fields is moderate friction"
    else:
        adj = 0
        detail = f"{flow.required_fields} required fields is minimal friction"
    adjustments += adj
    breakdown.append(ScoreBreakdown(factor="Required fields", adjustment=adj, detail=detail))

    # --- Progress indicator ---
    if flow.has_progress_indicator:
        adj = 10
        detail = "Progress indicator reduces perceived effort and drop-off"
    else:
        adj = 0
        detail = "No progress indicator; users cannot gauge remaining effort"
    adjustments += adj
    breakdown.append(ScoreBreakdown(factor="Progress indicator", adjustment=adj, detail=detail))

    # --- Skip option ---
    if flow.has_skip_option:
        adj = 10
        detail = "Skip option lets eager users reach value faster"
    else:
        adj = 0
        detail = "No skip option; users may abandon if stuck on a step"
    adjustments += adj
    breakdown.append(ScoreBreakdown(factor="Skip option", adjustment=adj, detail=detail))

    # --- Template gallery ---
    if flow.has_template_gallery:
        adj = 5
        detail = "Template gallery reduces blank-canvas friction"
    else:
        adj = 0
        detail = "No template gallery"
    adjustments += adj
    breakdown.append(ScoreBreakdown(factor="Template gallery", adjustment=adj, detail=detail))

    # --- Empty state education ---
    if flow.has_empty_state_education:
        adj = 5
        detail = "Educational empty states guide users through initial population"
    else:
        adj = 0
        detail = "No empty state education"
    adjustments += adj
    breakdown.append(ScoreBreakdown(factor="Empty state education", adjustment=adj, detail=detail))

    # --- Time to first value ---
    if flow.time_to_first_value_minutes < 5:
        adj = 15
        detail = f"{flow.time_to_first_value_minutes:.0f} min to value is excellent"
    elif flow.time_to_first_value_minutes <= 15:
        adj = 5
        detail = f"{flow.time_to_first_value_minutes:.0f} min to value is acceptable"
    else:
        adj = -10
        detail = f"{flow.time_to_first_value_minutes:.0f} min to value is too long; aim for under 15"
    adjustments += adj
    breakdown.append(ScoreBreakdown(factor="Time to first value", adjustment=adj, detail=detail))

    # --- Credit card upfront ---
    if flow.requires_credit_card_upfront:
        adj = -15
        detail = "Credit card upfront significantly reduces trial signups"
    else:
        adj = 0
        detail = "No credit card required upfront"
    adjustments += adj
    breakdown.append(ScoreBreakdown(factor="Credit card upfront", adjustment=adj, detail=detail))

    # --- Welcome email sequence ---
    if flow.has_welcome_email_sequence:
        adj = 10
        detail = "Welcome emails re-engage users who do not activate on first visit"
    else:
        adj = 0
        detail = "No welcome email sequence"
    adjustments += adj
    breakdown.append(ScoreBreakdown(factor="Welcome email sequence", adjustment=adj, detail=detail))

    # --- In-app guidance ---
    if flow.has_in_app_guidance:
        adj = 10
        detail = "In-app guidance (tooltips, checklists) accelerates feature discovery"
    else:
        adj = 0
        detail = "No in-app guidance"
    adjustments += adj
    breakdown.append(ScoreBreakdown(factor="In-app guidance", adjustment=adj, detail=detail))

    # --- Calculate final score ---
    raw_score = base_score + adjustments
    final_score = max(0, min(100, raw_score))

    # --- Grade ---
    grade = _score_to_grade(final_score)

    # --- Pattern recommendation ---
    pattern_name, pattern_rationale = PATTERN_MAP.get(
        flow.product_type or "", DEFAULT_PATTERN
    )

    # --- Improvements ---
    improvements = _generate_improvements(flow)

    # --- Estimated total activation lift ---
    total_lift_low = sum(imp.estimated_activation_lift_pct[0] for imp in improvements)
    total_lift_high = sum(imp.estimated_activation_lift_pct[1] for imp in improvements)
    # Cap at reasonable range
    total_lift_low = min(total_lift_low, 50.0)
    total_lift_high = min(total_lift_high, 80.0)

    return ScoringResult(
        score=final_score,
        grade=grade,
        breakdown=breakdown,
        recommended_pattern=pattern_name,
        pattern_rationale=pattern_rationale,
        improvements=improvements,
        estimated_activation_lift_pct=(total_lift_low, total_lift_high),
    )


def _score_to_grade(score: int) -> str:
    """Convert numeric score to letter grade.

    Args:
        score: Score from 0 to 100.

    Returns:
        Letter grade A through F.
    """
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 60:
        return "D"
    return "F"


def _generate_improvements(flow: OnboardingFlow) -> List[Improvement]:
    """Generate prioritized improvement recommendations.

    Args:
        flow: The onboarding flow being evaluated.

    Returns:
        Sorted list of Improvement objects, highest priority first.
    """
    improvements: List[Improvement] = []
    priority = 1

    # Credit card removal is the single highest-impact change
    if flow.requires_credit_card_upfront:
        improvements.append(Improvement(
            action="Remove credit card requirement from trial signup",
            reason="Requiring a credit card upfront typically reduces signups by 50-70%. "
                   "Collect payment info at the end of trial when users have seen value.",
            estimated_activation_lift_pct=(15.0, 30.0),
            difficulty="low",
            priority=priority,
        ))
        priority += 1

    # Time to value improvements
    if flow.time_to_first_value_minutes > 15:
        improvements.append(Improvement(
            action="Reduce time-to-first-value to under 15 minutes",
            reason="Users who do not experience value in the first session rarely return. "
                   "Identify the shortest path to an aha-moment and remove every barrier.",
            estimated_activation_lift_pct=(10.0, 25.0),
            difficulty="high",
            priority=priority,
        ))
        priority += 1
    elif flow.time_to_first_value_minutes > 5:
        improvements.append(Improvement(
            action="Optimize time-to-first-value to under 5 minutes",
            reason="Sub-5-minute value delivery correlates with the highest activation rates. "
                   "Consider pre-populating data, using templates, or simplifying the first task.",
            estimated_activation_lift_pct=(5.0, 12.0),
            difficulty="medium",
            priority=priority,
        ))
        priority += 1

    # Step count reduction
    if flow.total_steps > 7:
        improvements.append(Improvement(
            action="Reduce onboarding to 5 or fewer steps",
            reason="Each additional step beyond 5 increases drop-off by roughly 10%. "
                   "Defer non-critical setup to post-activation.",
            estimated_activation_lift_pct=(10.0, 20.0),
            difficulty="medium",
            priority=priority,
        ))
        priority += 1
    elif flow.total_steps >= 5:
        improvements.append(Improvement(
            action="Reduce onboarding steps from {0} to under 5".format(flow.total_steps),
            reason="Fewer steps mean less friction. Move optional configuration to "
                   "settings that users can customize after activation.",
            estimated_activation_lift_pct=(3.0, 8.0),
            difficulty="medium",
            priority=priority,
        ))
        priority += 1

    # Required fields reduction
    if flow.required_fields > 5:
        improvements.append(Improvement(
            action="Reduce required signup fields to 3 or fewer",
            reason="Each additional form field reduces conversion by approximately 5-10%. "
                   "Ask only for email, name, and password at signup; collect the rest later.",
            estimated_activation_lift_pct=(8.0, 18.0),
            difficulty="low",
            priority=priority,
        ))
        priority += 1
    elif flow.required_fields >= 3:
        improvements.append(Improvement(
            action="Minimize required fields to under 3 (consider social login)",
            reason="Reducing fields below 3 has diminishing returns, but social login "
                   "can eliminate the form entirely for a portion of users.",
            estimated_activation_lift_pct=(2.0, 5.0),
            difficulty="low",
            priority=priority,
        ))
        priority += 1

    # Missing elements
    if not flow.has_progress_indicator and flow.total_steps >= 3:
        improvements.append(Improvement(
            action="Add a progress indicator to the onboarding flow",
            reason="Progress indicators reduce abandonment by setting expectations "
                   "about remaining effort. Especially important for 3+ step flows.",
            estimated_activation_lift_pct=(3.0, 8.0),
            difficulty="low",
            priority=priority,
        ))
        priority += 1

    if not flow.has_skip_option:
        improvements.append(Improvement(
            action="Add skip buttons for non-critical onboarding steps",
            reason="Letting users skip optional steps respects their time and lets "
                   "power users reach the product faster.",
            estimated_activation_lift_pct=(3.0, 7.0),
            difficulty="low",
            priority=priority,
        ))
        priority += 1

    if not flow.has_in_app_guidance:
        improvements.append(Improvement(
            action="Implement in-app guidance (tooltips, checklists, or coach marks)",
            reason="In-app guidance helps users discover features in context. "
                   "Users who receive guidance activate at 2-3x the rate of those without.",
            estimated_activation_lift_pct=(5.0, 15.0),
            difficulty="medium",
            priority=priority,
        ))
        priority += 1

    if not flow.has_welcome_email_sequence:
        improvements.append(Improvement(
            action="Create a welcome email sequence (3-5 emails over 14 days)",
            reason="Welcome emails re-engage users who signed up but did not activate. "
                   "A good sequence brings back 10-20% of dormant signups.",
            estimated_activation_lift_pct=(3.0, 10.0),
            difficulty="medium",
            priority=priority,
        ))
        priority += 1

    if not flow.has_template_gallery and flow.product_type in ("visual", "content", None):
        improvements.append(Improvement(
            action="Add a template gallery with 5-10 high-quality starter templates",
            reason="Templates eliminate the blank-canvas problem and demonstrate "
                   "what the product can do. Particularly effective for creative tools.",
            estimated_activation_lift_pct=(5.0, 12.0),
            difficulty="medium",
            priority=priority,
        ))
        priority += 1

    if not flow.has_empty_state_education and flow.product_type in ("data", "business_ops", None):
        improvements.append(Improvement(
            action="Design educational empty states for all unpopulated sections",
            reason="Empty screens are dead ends. Educational empty states with clear "
                   "CTAs guide users to populate their workspace and discover features.",
            estimated_activation_lift_pct=(3.0, 8.0),
            difficulty="medium",
            priority=priority,
        ))
        priority += 1

    return improvements


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def print_score_report(result: ScoringResult) -> None:
    """Print a formatted scoring report to stdout.

    Args:
        result: The complete scoring result.
    """
    print(f"\n{'=' * 55}")
    print(f"  Onboarding Score: {result.score}/100 (Grade: {result.grade})")
    print(f"{'=' * 55}")

    print("\n  Scoring Breakdown:")
    for item in result.breakdown:
        sign = "+" if item.adjustment >= 0 else ""
        if item.factor == "Base score":
            print(f"    {item.factor:<28} {item.adjustment:>4}  ({item.detail})")
        else:
            print(f"    {item.factor:<28} {sign}{item.adjustment:>3}  ({item.detail})")

    print(f"\n  Recommended Pattern: {result.recommended_pattern}")
    print(f"  Rationale: {result.pattern_rationale}")

    if result.improvements:
        print(f"\n  {'=' * 55}")
        print("  Improvement Recommendations (by priority):")
        print(f"  {'=' * 55}")
        for imp in result.improvements:
            lift_low, lift_high = imp.estimated_activation_lift_pct
            print(f"\n  [{imp.priority}] {imp.action}")
            print(f"      Why: {imp.reason}")
            print(f"      Estimated lift: {lift_low:.0f}-{lift_high:.0f}% activation improvement")
            print(f"      Difficulty: {imp.difficulty}")

        lift_low, lift_high = result.estimated_activation_lift_pct
        print(f"\n  Total estimated activation lift: {lift_low:.0f}-{lift_high:.0f}%")
        print("  (Note: individual lifts are not strictly additive; actual results vary)")


# ---------------------------------------------------------------------------
# Standalone demo
# ---------------------------------------------------------------------------

def main() -> None:
    """Run a demo scoring with a sample onboarding flow."""
    sample_flow = OnboardingFlow(
        total_steps=8,
        required_fields=6,
        has_progress_indicator=True,
        has_skip_option=False,
        has_template_gallery=False,
        has_empty_state_education=False,
        time_to_first_value_minutes=20.0,
        requires_credit_card_upfront=True,
        has_welcome_email_sequence=True,
        has_in_app_guidance=False,
        product_type="collaboration",
    )

    print("Onboarding Flow Scorer")
    print("=" * 55)
    print("\nSample Flow Details:")
    print(f"  Total steps: {sample_flow.total_steps}")
    print(f"  Required fields: {sample_flow.required_fields}")
    print(f"  Progress indicator: {sample_flow.has_progress_indicator}")
    print(f"  Skip option: {sample_flow.has_skip_option}")
    print(f"  Template gallery: {sample_flow.has_template_gallery}")
    print(f"  Empty state education: {sample_flow.has_empty_state_education}")
    print(f"  Time to first value: {sample_flow.time_to_first_value_minutes} min")
    print(f"  Credit card upfront: {sample_flow.requires_credit_card_upfront}")
    print(f"  Welcome email sequence: {sample_flow.has_welcome_email_sequence}")
    print(f"  In-app guidance: {sample_flow.has_in_app_guidance}")
    print(f"  Product type: {sample_flow.product_type}")

    result = score_onboarding(sample_flow)
    print_score_report(result)


if __name__ == "__main__":
    main()
