"""Tests for growthkit.stats against published reference values.

Run from the repo root:
    python3 -m unittest discover -s tests -t .
"""

import math
import os
import sys
import unittest

_SHARED = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "shared")
if _SHARED not in sys.path:
    sys.path.insert(0, _SHARED)

from growthkit import stats  # noqa: E402


class TwoProportionSizingTests(unittest.TestCase):
    # Reference values: the examples in R's documentation for
    # stats::power.prop.test (R 4.x, ?power.prop.test):
    #   power.prop.test(n = 50, p1 = .50, p2 = .75)      ## => power = 0.740
    #   power.prop.test(p1 = .50, p2 = .75, power = .90) ## =>     n = 76.7
    #   power.prop.test(n = 50, p1 = .5, power = .90)    ## =>    p2 = 0.8026
    # power.prop.test uses the same pooled-variance closed form as
    # stats.two_proportion_n, so these must match to the printed precision.

    def test_power_matches_r_example(self):
        self.assertAlmostEqual(stats.power_two_proportions(50, 0.50, 0.75), 0.740, places=3)

    def test_sample_size_matches_r_example(self):
        n = stats.two_proportion_n(0.50, 0.75, power=0.90)
        self.assertAlmostEqual(n, 76.7, places=1)
        # Rounded up for planning.
        self.assertEqual(stats.sample_size_per_arm(0.50, 0.25, relative=False, power=0.90), 77)
        self.assertEqual(stats.sample_size_per_arm(0.50, 0.50, relative=True, power=0.90), 77)

    def test_mde_matches_r_example(self):
        result = stats.minimum_detectable_effect(0.5, 50, power=0.90)
        self.assertAlmostEqual(result["target_rate"], 0.8026, places=4)
        self.assertAlmostEqual(result["absolute"], 0.3026, places=4)
        self.assertAlmostEqual(result["relative"], 0.6053, places=3)

    def test_power_at_returned_n_reaches_target(self):
        # Self-consistency: the unrounded n gives exactly the requested power,
        # and the rounded-up n gives at least that much.
        for p1, p2, power in [(0.038, 0.0456, 0.8), (0.2, 0.25, 0.8), (0.1, 0.08, 0.9)]:
            n = stats.two_proportion_n(p1, p2, power=power)
            self.assertAlmostEqual(stats.power_two_proportions(n, p1, p2), power, places=9)
            self.assertGreaterEqual(stats.power_two_proportions(math.ceil(n), p1, p2), power)

    def test_saas_landing_page_example(self):
        # 3.8 % baseline (Unbounce 2024 SaaS median), +20 % relative MDE,
        # alpha 0.05 two-sided, power 0.8: 10,884.2 -> 10,885 per arm.
        self.assertEqual(stats.sample_size_per_arm(0.038, 0.20), 10885)

    def test_one_sided_needs_fewer_visitors(self):
        two = stats.sample_size_per_arm(0.1, 0.2)
        one = stats.sample_size_per_arm(0.1, 0.2, two_sided=False)
        self.assertLess(one, two)

    def test_mde_round_trips_sample_size(self):
        n = stats.two_proportion_n(0.05, 0.06)
        result = stats.minimum_detectable_effect(0.05, n)
        self.assertAlmostEqual(result["target_rate"], 0.06, places=6)

    def test_mde_none_when_traffic_too_small(self):
        self.assertIsNone(stats.minimum_detectable_effect(0.5, 1))
        self.assertIsNone(stats.minimum_detectable_effect(0.5, 1, direction="down"))

    def test_downward_mde(self):
        # A drop is easier to detect than a lift of the same size below 50 %,
        # because variance shrinks with the rate; at 50 % they are symmetric.
        up = stats.minimum_detectable_effect(0.05, 5000)
        down = stats.minimum_detectable_effect(0.05, 5000, direction="down")
        self.assertEqual(down["direction"], "down")
        self.assertLess(down["target_rate"], 0.05)
        self.assertLess(down["relative"], 0)
        self.assertLess(abs(down["relative"]), up["relative"])
        # Round trip through the forward formula.
        self.assertAlmostEqual(stats.two_proportion_n(0.05, down["target_rate"]), 5000, delta=1e-3)
        sym_down = stats.minimum_detectable_effect(0.5, 50, direction="down")
        sym_up = stats.minimum_detectable_effect(0.5, 50)
        self.assertAlmostEqual(sym_down["relative"], -sym_up["relative"], places=6)
        with self.assertRaises(ValueError):
            stats.minimum_detectable_effect(0.05, 5000, direction="sideways")

    def test_invalid_inputs(self):
        with self.assertRaises(ValueError):
            stats.sample_size_per_arm(3.8, 0.2)  # percent instead of fraction
        with self.assertRaises(ValueError):
            stats.sample_size_per_arm(0.5, 1.5)  # variant rate above 1
        with self.assertRaises(ValueError):
            stats.sample_size_per_arm(0.5, 0)
        with self.assertRaises(ValueError):
            stats.two_proportion_n(0.2, 0.2)
        with self.assertRaises(ValueError):
            stats.sample_size_per_arm(True, 0.2)


class TrafficPlanningTests(unittest.TestCase):
    def test_weeks_to_significance(self):
        # 10,885 per arm x 2 arms / 1,250 weekly visitors = 17.4 weeks.
        weeks = stats.weeks_to_significance(0.038, 0.20, weekly_visitors=1250)
        self.assertAlmostEqual(weeks, 10885 * 2 / 1250, places=9)

    def test_bonferroni_for_more_variants(self):
        # Three arms compare two variants against control: alpha 0.025 each.
        plan = stats.plan_test(0.1, 10000, 0.1, arms=3)
        self.assertAlmostEqual(plan["alpha_used"], 0.025)
        self.assertEqual(plan["n_per_arm"], stats.sample_size_per_arm(0.1, 0.1, alpha=0.025))
        no_corr = stats.plan_test(0.1, 10000, 0.1, arms=3, bonferroni=False)
        self.assertLess(no_corr["n_per_arm"], plan["n_per_arm"])

    def test_mde_for_traffic_shrinks_with_more_traffic(self):
        small = stats.mde_for_traffic(0.038, weekly_visitors=1000, weeks=4)
        large = stats.mde_for_traffic(0.038, weekly_visitors=20000, weeks=4)
        self.assertGreater(small["relative"], large["relative"])
        self.assertEqual(small["n_per_arm"], 2000)
        # Consistent with the forward formula.
        self.assertAlmostEqual(
            stats.two_proportion_n(0.038, large["target_rate"]), 40000, delta=1e-3
        )

    def test_plan_test_feasible_and_not(self):
        ok = stats.plan_test(0.05, weekly_visitors=50000, mde=0.10)
        self.assertTrue(ok["feasible"])
        self.assertTrue(ok["verdict"].startswith("testable"))
        self.assertEqual(ok["weeks_rounded"], max(1, math.ceil(ok["weeks"])))

        low = stats.plan_test(0.038, weekly_visitors=1250, mde=0.20)
        self.assertFalse(low["feasible"])
        self.assertIn("before/after", low["verdict"])
        self.assertIsNotNone(low["mde_at_max_weeks"])
        self.assertGreater(low["mde_at_max_weeks"]["relative"], 0.20)

    def test_plan_for_a_drop_uses_downward_mde(self):
        # Planning a 20 % churn reduction: the verdict must quote the smallest
        # detectable decrease, not the (larger) smallest detectable increase.
        plan = stats.plan_test(0.05, weekly_visitors=1000, mde=-0.20)
        self.assertFalse(plan["feasible"])
        at_max = plan["mde_at_max_weeks"]
        self.assertEqual(at_max["direction"], "down")
        self.assertLess(at_max["relative"], 0)
        self.assertIn("relative decrease", plan["verdict"])
        self.assertIn("%.0f%%" % (abs(at_max["relative"]) * 100), plan["verdict"])
        lift = stats.plan_test(0.05, weekly_visitors=1000, mde=0.20)
        self.assertIn("relative increase", lift["verdict"])

    def test_default_limit_is_the_report_contract_4_weeks(self):
        # report-contract.md section 6: no A/B test that needs more than 4 weeks.
        self.assertEqual(stats.DEFAULT_MAX_WEEKS, 4)
        # 3.5 weeks of traffic needed: testable by default ...
        n = stats.sample_size_per_arm(0.05, 0.20)
        weekly = n * 2 / 3.5
        self.assertTrue(stats.plan_test(0.05, weekly, 0.20)["feasible"])
        self.assertEqual(stats.plan_test(0.05, weekly, 0.20)["max_weeks"], 4)
        # ... 5 weeks needed: not testable by default, testable with a 6-week limit.
        weekly = n * 2 / 5.0
        self.assertFalse(stats.plan_test(0.05, weekly, 0.20)["feasible"])
        self.assertIn("not testable in 4 weeks", stats.plan_test(0.05, weekly, 0.20)["verdict"])
        self.assertTrue(stats.plan_test(0.05, weekly, 0.20, max_weeks=6)["feasible"])

    def test_plan_rejects_bad_traffic(self):
        with self.assertRaises(ValueError):
            stats.plan_test(0.05, 0, 0.1)
        with self.assertRaises(ValueError):
            stats.plan_test(0.05, 1000, 0.1, arms=1)


class WilsonIntervalTests(unittest.TestCase):
    # Reference values: Newcombe RG (1998), "Two-sided confidence intervals
    # for the single proportion: comparison of seven methods", Statistics
    # in Medicine 17: 857-872, Table I, method 3 (Wilson score, no
    # continuity correction), 95 % intervals to 4 decimals.
    CASES = [
        (81, 263, 0.2553, 0.3662),
        (15, 148, 0.0624, 0.1605),
        (0, 20, 0.0000, 0.1611),
        (1, 29, 0.0061, 0.1718),
    ]

    def test_newcombe_table(self):
        for x, n, low, high in self.CASES:
            got_low, got_high = stats.wilson_interval(x, n)
            self.assertAlmostEqual(got_low, low, places=4, msg="%d/%d" % (x, n))
            self.assertAlmostEqual(got_high, high, places=4, msg="%d/%d" % (x, n))

    def test_edges_are_clamped(self):
        low, high = stats.wilson_interval(0, 5)
        self.assertEqual(low, 0.0)
        low, high = stats.wilson_interval(5, 5)
        self.assertEqual(high, 1.0)

    def test_wider_at_higher_confidence(self):
        l95, h95 = stats.wilson_interval(30, 100)
        l99, h99 = stats.wilson_interval(30, 100, confidence=0.99)
        self.assertLess(l99, l95)
        self.assertGreater(h99, h95)

    def test_invalid(self):
        for args in [(5, 0), (6, 5), (-1, 5), (1.5, 5), (True, 5), ("81", 263)]:
            with self.assertRaises(ValueError):
                stats.wilson_interval(*args)

    def test_whole_floats_are_counts(self):
        # Counts read from JSON or CSV often arrive as 81.0.
        self.assertEqual(stats.wilson_interval(81.0, 263.0), stats.wilson_interval(81, 263))


class TrialModelTests(unittest.TestCase):
    def test_paying_per_1000(self):
        self.assertAlmostEqual(stats.paying_per_1000_visitors(0.10, 0.182), 18.2)
        self.assertEqual(stats.paying_per_1000_visitors(0, 0.5), 0.0)

    def test_compare_models(self):
        # Trial-to-paid inputs are First Page Sage's 2022-2025 SaaS averages
        # (opt-in 18.2 %, opt-out 48.8 %); the visitor-to-trial rates are
        # illustrative. Expected values are plain arithmetic.
        result = stats.compare_trial_models(0.08, 0.182, 0.025, 0.488)
        self.assertAlmostEqual(result["no_card"]["paying_per_1000"], 14.56)
        self.assertAlmostEqual(result["card_required"]["paying_per_1000"], 12.2)
        self.assertAlmostEqual(result["difference_per_1000"], 12.2 - 14.56)
        self.assertEqual(result["better_model"], "no_card")
        self.assertAlmostEqual(result["ratio"], 12.2 / 14.56)
        # No-card would tie at 12.2 / 80 trials = 15.25 % trial-to-paid.
        self.assertAlmostEqual(result["breakeven_no_card_trial_to_paid"], 0.1525)
        # Card would tie at 14.56 / 1000 / 0.488 = 2.98 % visitor-to-trial.
        self.assertAlmostEqual(result["breakeven_card_visitor_to_trial"], 0.01456 / 0.488)
        self.assertTrue(result["breakeven_no_card_reachable"])
        self.assertTrue(result["breakeven_card_reachable"])

    def test_unreachable_breakeven_is_flagged(self):
        # No-card: 10 trials per 1,000; card: 25 paying per 1,000. No-card would
        # need 250 % trial-to-paid, which no funnel can reach.
        result = stats.compare_trial_models(0.01, 0.2, 0.05, 0.5)
        self.assertAlmostEqual(result["breakeven_no_card_trial_to_paid"], 2.5)
        self.assertFalse(result["breakeven_no_card_reachable"])
        self.assertTrue(result["breakeven_card_reachable"])

    def test_card_wins_and_tie(self):
        self.assertEqual(stats.compare_trial_models(0.05, 0.15, 0.03, 0.5)["better_model"], "card_required")
        self.assertEqual(stats.compare_trial_models(0.1, 0.2, 0.04, 0.5)["better_model"], "tie")

    def test_zero_no_card_ratio_is_none(self):
        result = stats.compare_trial_models(0.0, 0.2, 0.03, 0.5)
        self.assertIsNone(result["ratio"])
        self.assertIsNone(result["breakeven_no_card_trial_to_paid"])
        self.assertIsNone(result["breakeven_no_card_reachable"])

    def test_rates_must_be_fractions(self):
        with self.assertRaises(ValueError):
            stats.compare_trial_models(8, 18.2, 2.5, 48.8)


class PriceIncreaseTests(unittest.TestCase):
    def test_revenue_breakeven(self):
        # increase / (1 + increase): 10 % -> 9.09 %, 25 % -> 20 %, 100 % -> 50 %.
        self.assertAlmostEqual(stats.price_increase_breakeven_churn(0.10), 0.0909, places=4)
        self.assertAlmostEqual(stats.price_increase_breakeven_churn(0.25), 0.20)
        self.assertAlmostEqual(stats.price_increase_breakeven_churn(1.0), 0.50)
        self.assertEqual(stats.price_increase_breakeven_churn(0), 0.0)

    def test_revenue_is_unchanged_at_breakeven(self):
        for inc in (0.05, 0.1, 0.3):
            churn = stats.price_increase_breakeven_churn(inc)
            self.assertAlmostEqual((1 + inc) * (1 - churn), 1.0)

    def test_contribution_margin(self):
        # Break-even sales change formula, -dP / (CM + dP), from Nagle, Hogan
        # and Zale, "The Strategy and Tactics of Pricing": a 5 % price cut at
        # a 25 % contribution margin needs 0.05 / 0.20 = 25 % more volume.
        self.assertAlmostEqual(stats.price_increase_breakeven_churn(-0.05, 0.25), -0.25)
        # A 10 % increase at an 80 % margin tolerates 11.1 % churn.
        self.assertAlmostEqual(stats.price_increase_breakeven_churn(0.10, 0.80), 0.1 / 0.9)

    def test_invalid(self):
        with self.assertRaises(ValueError):
            stats.price_increase_breakeven_churn(0.1, 0)
        with self.assertRaises(ValueError):
            stats.price_increase_breakeven_churn(-1.0)
        with self.assertRaises(ValueError):
            stats.price_increase_breakeven_churn("10%")


if __name__ == "__main__":
    unittest.main()
