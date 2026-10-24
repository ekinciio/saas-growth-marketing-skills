"""Deterministic growth math shared by the skills.

Everything here is pure standard-library arithmetic, so skills can quote
numbers instead of inventing lift ranges:

- A/B test sizing for two proportions: sample size per arm, power, minimum
  detectable effect (MDE) for a given traffic level, and weeks needed.
- Wilson score interval for a single proportion (better than the normal
  approximation for small n or rates near 0 or 1).
- Paying customers per 1,000 visitors for a no-card trial versus a
  card-required trial, from the user's own funnel rates.
- Price-increase break-even churn.

Conventions
    Rates are fractions (0.038 means 3.8 %). Functions raise ValueError
    with a plain-language message on bad input instead of returning
    nonsense. Nothing here rounds except where the docstring says so.

Formulas
    Sample size uses the standard normal-approximation formula for a
    two-proportion z-test with pooled variance under H0 and no continuity
    correction (as in Fleiss, Levin and Paik, "Statistical Methods for Rates
    and Proportions", 3rd ed., 2003). It is the same closed form R's
    power.prop.test() solves, so its documented examples are used as test
    reference values. Evan Miller's online calculator uses the baseline
    variance under H0 instead, which gives a few percent fewer visitors.
"""

from __future__ import annotations

import math
from statistics import NormalDist

_STD_NORMAL = NormalDist()

DEFAULT_ALPHA = 0.05
DEFAULT_POWER = 0.8
# Tests longer than this are usually not worth running: cookie churn, seasonality
# and opportunity cost start to dominate. Callers can pass their own limit.
DEFAULT_MAX_WEEKS = 6.0


# --------------------------------------------------------------------------
# Validation helpers
# --------------------------------------------------------------------------


def _number(name: str, value) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("%s must be a number, got %r" % (name, value))
    if math.isnan(value) or math.isinf(value):
        raise ValueError("%s must be a finite number" % name)
    return float(value)


def _open_rate(name: str, value) -> float:
    """A rate strictly between 0 and 1 (needed wherever variance is used)."""
    value = _number(name, value)
    if not 0.0 < value < 1.0:
        raise ValueError(
            "%s must be a fraction between 0 and 1 (exclusive), e.g. 0.038 for 3.8%%; got %r"
            % (name, value)
        )
    return value


def _closed_rate(name: str, value) -> float:
    """A rate from 0 to 1 inclusive (a funnel step can be 0 % or 100 %)."""
    value = _number(name, value)
    if not 0.0 <= value <= 1.0:
        raise ValueError(
            "%s must be a fraction from 0 to 1, e.g. 0.18 for 18%%; got %r" % (name, value)
        )
    return value


def _alpha_power(alpha, power):
    alpha = _open_rate("alpha", alpha)
    power = _open_rate("power", power)
    return alpha, power


def _z_alpha(alpha: float, two_sided: bool) -> float:
    return _STD_NORMAL.inv_cdf(1.0 - (alpha / 2.0 if two_sided else alpha))


# --------------------------------------------------------------------------
# Two-proportion test sizing
# --------------------------------------------------------------------------


def target_rate(baseline, mde, relative: bool = True) -> float:
    """Variant conversion rate implied by a baseline and an effect size.

    Args:
        baseline: control conversion rate, e.g. 0.038.
        mde: effect to detect. Relative by default (0.2 = +20 %, so
            0.038 -> 0.0456); absolute when ``relative`` is False
            (0.01 = +1 percentage point).
        relative: see ``mde``.

    Raises:
        ValueError: when the effect is zero or pushes the rate outside (0, 1).
    """
    baseline = _open_rate("baseline", baseline)
    mde = _number("mde", mde)
    if mde == 0:
        raise ValueError("mde must not be zero")
    p2 = baseline * (1.0 + mde) if relative else baseline + mde
    if not 0.0 < p2 < 1.0:
        raise ValueError(
            "baseline %r with mde %r gives a variant rate of %r, outside (0, 1)"
            % (baseline, mde, p2)
        )
    return p2


def power_two_proportions(n_per_arm, p1, p2, alpha=DEFAULT_ALPHA, two_sided: bool = True) -> float:
    """Power of a two-proportion z-test with ``n_per_arm`` visitors in each arm.

    Like R's power.prop.test (strict = FALSE), only the tail in the
    direction of the effect is counted.
    """
    n = _number("n_per_arm", n_per_arm)
    if n <= 0:
        raise ValueError("n_per_arm must be positive")
    p1 = _open_rate("p1", p1)
    p2 = _open_rate("p2", p2)
    alpha = _open_rate("alpha", alpha)
    if p1 == p2:
        return alpha / 2.0 if two_sided else alpha
    q1, q2 = 1.0 - p1, 1.0 - p2
    pooled_sd = math.sqrt((p1 + p2) * (q1 + q2) / 2.0)  # sqrt(2 * pbar * qbar)
    alt_sd = math.sqrt(p1 * q1 + p2 * q2)
    z = (math.sqrt(n) * abs(p1 - p2) - _z_alpha(alpha, two_sided) * pooled_sd) / alt_sd
    return _STD_NORMAL.cdf(z)


def two_proportion_n(p1, p2, alpha=DEFAULT_ALPHA, power=DEFAULT_POWER, two_sided: bool = True) -> float:
    """Exact (unrounded) visitors per arm to detect p1 vs p2. See module docstring."""
    p1 = _open_rate("p1", p1)
    p2 = _open_rate("p2", p2)
    if p1 == p2:
        raise ValueError("p1 and p2 must differ")
    alpha, power = _alpha_power(alpha, power)
    pbar = (p1 + p2) / 2.0
    numerator = (
        _z_alpha(alpha, two_sided) * math.sqrt(2.0 * pbar * (1.0 - pbar))
        + _STD_NORMAL.inv_cdf(power) * math.sqrt(p1 * (1.0 - p1) + p2 * (1.0 - p2))
    )
    return numerator ** 2 / (p1 - p2) ** 2


def sample_size_per_arm(baseline, mde, relative: bool = True, alpha=DEFAULT_ALPHA,
                        power=DEFAULT_POWER, two_sided: bool = True) -> int:
    """Visitors needed in each arm (rounded up) to detect ``mde`` from ``baseline``.

    Defaults: two-sided alpha 0.05, power 0.8, relative MDE.
    Example: baseline 0.038, mde 0.2 -> 10,885 visitors per arm.
    """
    p2 = target_rate(baseline, mde, relative)
    return int(math.ceil(two_proportion_n(baseline, p2, alpha, power, two_sided)))


def minimum_detectable_effect(baseline, n_per_arm, alpha=DEFAULT_ALPHA, power=DEFAULT_POWER,
                              two_sided: bool = True, direction: str = "up"):
    """Smallest change detectable with ``n_per_arm`` visitors per arm.

    Solved by bisection on the variant rate so that power reaches the
    target, the inverse of two_proportion_n. ``direction`` is 'up' (a lift,
    the default) or 'down' (a drop, e.g. churn or bounce rate). The two
    differ because the variance of a proportion depends on its level.

    Returns:
        dict with baseline, target_rate, absolute (percentage points as a
        fraction, negative for 'down'), relative (fraction of baseline,
        negative for 'down'), direction and n_per_arm; or None when no
        variant rate inside (0, 1) could be detected at this n.
    """
    p1 = _open_rate("baseline", baseline)
    n = _number("n_per_arm", n_per_arm)
    if n <= 0:
        raise ValueError("n_per_arm must be positive")
    alpha, power = _alpha_power(alpha, power)
    if direction not in ("up", "down"):
        raise ValueError("direction must be 'up' or 'down'")

    # ``near`` stays below the target power, ``far`` at or above it.
    near, far = p1, (1.0 - 1e-12 if direction == "up" else 1e-12)
    if power_two_proportions(n, p1, far, alpha, two_sided) < power:
        return None
    for _ in range(200):  # 200 halvings is far below float resolution
        mid = (near + far) / 2.0
        if mid in (near, far):
            break
        if power_two_proportions(n, p1, mid, alpha, two_sided) < power:
            near = mid
        else:
            far = mid
    return {
        "baseline": p1,
        "target_rate": far,
        "absolute": far - p1,
        "relative": (far - p1) / p1,
        "direction": direction,
        "n_per_arm": n,
    }


def _check_traffic(weekly_visitors, arms):
    weekly = _number("weekly_visitors", weekly_visitors)
    if weekly <= 0:
        raise ValueError("weekly_visitors must be positive")
    if isinstance(arms, bool) or not isinstance(arms, int) or arms < 2:
        raise ValueError("arms must be an integer of at least 2 (control + 1 variant)")
    return weekly, arms


def _corrected_alpha(alpha, arms: int, bonferroni: bool) -> float:
    """Bonferroni: split alpha across the variant-vs-control comparisons."""
    alpha = _open_rate("alpha", alpha)
    return alpha / (arms - 1) if bonferroni and arms > 2 else alpha


def weeks_to_significance(baseline, mde, weekly_visitors, relative: bool = True, arms: int = 2,
                          alpha=DEFAULT_ALPHA, power=DEFAULT_POWER, two_sided: bool = True,
                          bonferroni: bool = True) -> float:
    """Weeks of traffic needed to finish a test (unrounded).

    ``weekly_visitors`` is the traffic that enters the experiment, split
    evenly across ``arms``. With more than one variant, alpha is Bonferroni
    corrected unless ``bonferroni`` is False.
    """
    weekly, arms = _check_traffic(weekly_visitors, arms)
    alpha_used = _corrected_alpha(alpha, arms, bonferroni)
    n = sample_size_per_arm(baseline, mde, relative, alpha_used, power, two_sided)
    return n * arms / weekly


def mde_for_traffic(baseline, weekly_visitors, weeks, arms: int = 2, alpha=DEFAULT_ALPHA,
                    power=DEFAULT_POWER, two_sided: bool = True, bonferroni: bool = True,
                    direction: str = "up"):
    """Smallest detectable change if the test runs for ``weeks`` at this traffic.

    Returns the minimum_detectable_effect dict (plus weeks, arms and
    alpha_used), or None when nothing is detectable. ``direction`` is 'up'
    (lift, default) or 'down' (drop).
    """
    weekly, arms = _check_traffic(weekly_visitors, arms)
    weeks = _number("weeks", weeks)
    if weeks <= 0:
        raise ValueError("weeks must be positive")
    alpha_used = _corrected_alpha(alpha, arms, bonferroni)
    result = minimum_detectable_effect(baseline, weekly * weeks / arms, alpha_used, power,
                                       two_sided, direction)
    if result is not None:
        result.update({"weeks": weeks, "arms": arms, "alpha_used": alpha_used})
    return result


def plan_test(baseline, weekly_visitors, mde, relative: bool = True, arms: int = 2,
              alpha=DEFAULT_ALPHA, power=DEFAULT_POWER, two_sided: bool = True,
              max_weeks=DEFAULT_MAX_WEEKS, bonferroni: bool = True) -> dict:
    """Everything a skill needs to say whether an A/B test is worth running.

    Returns:
        dict with the inputs, target_rate, n_per_arm, total_visitors,
        weeks (unrounded), weeks_rounded (whole weeks, at least 1, so the
        test covers full weekly cycles), feasible (weeks <= max_weeks),
        mde_at_max_weeks (what this traffic can detect in max_weeks, in the
        same direction as ``mde``, or None) and a one-line verdict.
    """
    weekly, arms = _check_traffic(weekly_visitors, arms)
    max_weeks = _number("max_weeks", max_weeks)
    if max_weeks <= 0:
        raise ValueError("max_weeks must be positive")
    alpha_used = _corrected_alpha(alpha, arms, bonferroni)
    p2 = target_rate(baseline, mde, relative)
    n = sample_size_per_arm(baseline, mde, relative, alpha_used, power, two_sided)
    weeks = n * arms / weekly
    feasible = weeks <= max_weeks
    # A planned drop (e.g. churn) is compared with the smallest detectable
    # drop, not the smallest detectable lift.
    direction = "down" if p2 < baseline else "up"
    at_max = mde_for_traffic(baseline, weekly, max_weeks, arms, alpha, power, two_sided,
                             bonferroni, direction)

    if feasible:
        verdict = "testable: about %d week(s) at this traffic" % max(1, math.ceil(weeks))
    elif at_max is not None:
        verdict = (
            "not testable in %g weeks: this traffic can only detect a %.0f%% relative "
            "%s; ship and measure before/after instead"
            % (max_weeks, abs(at_max["relative"]) * 100,
               "increase" if direction == "up" else "decrease")
        )
    else:
        verdict = "not testable: too little traffic; ship and measure before/after instead"

    return {
        "baseline": float(baseline),
        "mde": float(mde),
        "relative": relative,
        "target_rate": p2,
        "weekly_visitors": weekly,
        "arms": arms,
        "alpha": float(alpha),
        "alpha_used": alpha_used,
        "power": float(power),
        "two_sided": two_sided,
        "n_per_arm": n,
        "total_visitors": n * arms,
        "weeks": weeks,
        "weeks_rounded": max(1, int(math.ceil(weeks))),
        "max_weeks": max_weeks,
        "feasible": feasible,
        "mde_at_max_weeks": at_max,
        "verdict": verdict,
    }


# --------------------------------------------------------------------------
# Intervals
# --------------------------------------------------------------------------


def _whole(name: str, value) -> int:
    """A count: an int, or a float with no fractional part (e.g. 42.0 from JSON or CSV)."""
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("%s must be a whole number, got %r" % (name, value))
    return value


def wilson_interval(successes, n, confidence: float = 0.95):
    """Wilson score interval for a proportion, as (low, high) fractions.

    Wilson (1927), "Probable inference, the law of succession, and
    statistical inference", JASA 22: 209-212. Recommended over the
    normal-approximation (Wald) interval by Newcombe (1998).
    """
    successes = _whole("successes", successes)
    n = _whole("n", n)
    if n <= 0:
        raise ValueError("n must be a positive whole number")
    if not 0 <= successes <= n:
        raise ValueError("successes must be between 0 and n")
    confidence = _open_rate("confidence", confidence)

    z = _STD_NORMAL.inv_cdf(1.0 - (1.0 - confidence) / 2.0)
    p = successes / n
    z2 = z * z
    denom = 1.0 + z2 / n
    centre = (p + z2 / (2.0 * n)) / denom
    half = z * math.sqrt(p * (1.0 - p) / n + z2 / (4.0 * n * n)) / denom
    # Clamp float noise at the edges (x = 0 or x = n).
    return max(0.0, centre - half), min(1.0, centre + half)


# --------------------------------------------------------------------------
# Trial models
# --------------------------------------------------------------------------


def paying_per_1000_visitors(visitor_to_trial, trial_to_paid) -> float:
    """Paying customers per 1,000 visitors = 1000 x visitor-to-trial x trial-to-paid."""
    v2t = _closed_rate("visitor_to_trial", visitor_to_trial)
    t2p = _closed_rate("trial_to_paid", trial_to_paid)
    return 1000.0 * v2t * t2p


def compare_trial_models(no_card_visitor_to_trial, no_card_trial_to_paid,
                         card_visitor_to_trial, card_trial_to_paid) -> dict:
    """Compare a no-card (opt-in) trial with a card-required (opt-out) trial.

    A card at signup usually cuts trial starts but raises trial-to-paid, so
    neither model wins by default; this shows which one yields more paying
    customers for the same 1,000 visitors, from the user's own rates.

    Returns:
        dict with per-model trials_per_1000 and paying_per_1000,
        difference_per_1000 (card minus no-card), better_model
        ('card_required' | 'no_card' | 'tie'), ratio (card / no-card, None
        when no-card yields 0), and two break-even rates:
        breakeven_no_card_trial_to_paid (the trial-to-paid the no-card model
        needs to match the card model) and breakeven_card_visitor_to_trial
        (the visitor-to-trial the card model needs to match the no-card one).
        A break-even is None when it cannot be computed (zero denominator).
        A break-even above 1 is a rate no funnel can reach, so
        breakeven_no_card_reachable and breakeven_card_reachable say whether
        each one is at most 1 (None when the break-even is None); quote
        "cannot catch up" rather than a rate above 100 %.
    """
    no_card = {
        "visitor_to_trial": _closed_rate("no_card_visitor_to_trial", no_card_visitor_to_trial),
        "trial_to_paid": _closed_rate("no_card_trial_to_paid", no_card_trial_to_paid),
    }
    card = {
        "visitor_to_trial": _closed_rate("card_visitor_to_trial", card_visitor_to_trial),
        "trial_to_paid": _closed_rate("card_trial_to_paid", card_trial_to_paid),
    }
    for model in (no_card, card):
        model["trials_per_1000"] = 1000.0 * model["visitor_to_trial"]
        model["paying_per_1000"] = paying_per_1000_visitors(
            model["visitor_to_trial"], model["trial_to_paid"]
        )

    diff = card["paying_per_1000"] - no_card["paying_per_1000"]
    if abs(diff) < 1e-9:
        better = "tie"
    else:
        better = "card_required" if diff > 0 else "no_card"

    def _ratio(a, b):
        return a / b if b else None

    def _reachable(rate):
        return None if rate is None else rate <= 1.0 + 1e-12

    breakeven_no_card = _ratio(card["paying_per_1000"], no_card["trials_per_1000"])
    breakeven_card = _ratio(no_card["paying_per_1000"] / 1000.0, card["trial_to_paid"])
    return {
        "no_card": no_card,
        "card_required": card,
        "difference_per_1000": diff,
        "better_model": better,
        "ratio": _ratio(card["paying_per_1000"], no_card["paying_per_1000"]),
        "breakeven_no_card_trial_to_paid": breakeven_no_card,
        "breakeven_no_card_reachable": _reachable(breakeven_no_card),
        "breakeven_card_visitor_to_trial": breakeven_card,
        "breakeven_card_reachable": _reachable(breakeven_card),
    }


# --------------------------------------------------------------------------
# Pricing
# --------------------------------------------------------------------------


def price_increase_breakeven_churn(increase, contribution_margin: float = 1.0) -> float:
    """Share of affected customers you can lose before a price rise loses money.

    With the default contribution_margin of 1.0 this is revenue break-even:
    increase / (1 + increase), so a 10 % increase breaks even at 9.09 % churn
    of the affected revenue. With a contribution margin m (as a fraction of
    the old price) it is the profit break-even from the standard break-even
    sales-change formula, increase / (m + increase) (Nagle, Hogan and Zale,
    "The Strategy and Tactics of Pricing").

    A negative ``increase`` (a price cut) returns a negative number: the
    extra share of customers needed to break even.
    """
    increase = _number("increase", increase)
    margin = _number("contribution_margin", contribution_margin)
    if not 0.0 < margin <= 1.0:
        raise ValueError("contribution_margin must be a fraction in (0, 1], e.g. 0.8 for 80%")
    if increase == 0:
        return 0.0
    if increase <= -margin:
        raise ValueError("a price cut of the full contribution margin or more can never break even")
    return increase / (margin + increase)
