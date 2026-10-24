"""Tests for skills/plg-funnel-analyzer/scripts/funnel_analyzer.py.

Backlog item B20 (monotonic grade and input validation):
  - The old grade was non-monotonic: one GREEN metric gave C, 5 GREEN + 1 RED
    equalled 6 YELLOW, and 1 RED + 2 YELLOW (D) was worse than 1 RED alone
    (C), so adding data could lower the grade.
  - "skip" (which SKILL.md tells users to type) and "25%" crashed.
  - NaN, negative and impossible values were graded; fractions were misread.
  - Bad JSON gave a traceback; units printed as "5.0days".

The monotonicity proof is exhaustive over every subset of the 6 metrics with
4 representative values each, so it is deterministic and offline.
Run with: python3 -m unittest discover -s tests -t .
"""

import importlib.util
import itertools
import json
import os
import re
import subprocess
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SKILL_DIR = os.path.join(REPO_ROOT, "skills", "plg-funnel-analyzer")
SCRIPT = os.path.join(SKILL_DIR, "scripts", "funnel_analyzer.py")
SKILL_MD = os.path.join(SKILL_DIR, "SKILL.md")


def _load_module():
    """Import funnel_analyzer.py by file path (skills/ is not a package)."""
    name = "funnel_analyzer_under_test"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    module = importlib.util.module_from_spec(spec)
    # dataclasses with postponed annotations look the module up in
    # sys.modules, so register it before executing.
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


fa = _load_module()
KEYS = list(fa.BENCHMARKS)

# Grade order for comparisons. Only letter grades are compared with each
# other; "Partial" and "N/A" are not grades.
GRADE_RANK = {"F": 0, "D": 1, "C": 2, "B": 3, "A": 4}


def _run_cli(args=None, stdin_text=None):
    return subprocess.run(
        [sys.executable, SCRIPT] + list(args or []),
        input=stdin_text, capture_output=True, text=True, timeout=60,
    )


def _sample_values(key):
    """Four values per metric: far below bottom-25%, RED edge, median, far above top-25%."""
    b = fa.BENCHMARKS[key]
    if b.higher_is_better:
        far_bad = max(b.bottom_25 - (b.median - b.bottom_25) * 2, 0.0)
        far_good = b.top_25 + (b.top_25 - b.median) * 2
    else:
        far_bad = b.bottom_25 + (b.bottom_25 - b.median) * 2
        far_good = max(b.top_25 - (b.median - b.top_25) * 2, 0.0)
    lo, hi = fa.VALID_RANGES[key]
    return [min(max(v, lo), hi) for v in (far_bad, b.bottom_25, b.median, far_good)]


class PercentileTests(unittest.TestCase):

    def test_weights_sum_to_100(self):
        self.assertEqual(sum(fa.SCORE_WEIGHTS.values()), 100.0)
        self.assertEqual(set(fa.SCORE_WEIGHTS), set(fa.BENCHMARKS))
        # Retention (churn + NRR) 30, activation 20, conversion 20, payback 15, TTV 15
        w = fa.SCORE_WEIGHTS
        self.assertEqual(w["monthly_churn"] + w["nrr"], 30.0)
        self.assertEqual(w["signup_to_active"], 20.0)
        self.assertEqual(w["free_to_paid"], 20.0)
        self.assertEqual(w["payback_months"], 15.0)
        self.assertEqual(w["time_to_value_days"], 15.0)

    def test_anchors(self):
        for key, b in fa.BENCHMARKS.items():
            with self.subTest(metric=key):
                self.assertAlmostEqual(fa.percentile_position(key, b.bottom_25), 25.0)
                self.assertAlmostEqual(fa.percentile_position(key, b.median), 50.0)
                self.assertAlmostEqual(fa.percentile_position(key, b.top_25), 75.0)

    def test_percentile_is_monotonic_in_goodness_and_capped(self):
        for key, b in fa.BENCHMARKS.items():
            lo, hi = fa.VALID_RANGES[key]
            values = [lo + (hi - lo) * i / 400 for i in range(401)]
            if not b.higher_is_better:
                values.reverse()  # from worst to best
            pcts = [fa.percentile_position(key, v) for v in values]
            with self.subTest(metric=key):
                self.assertEqual(pcts, sorted(pcts))
                self.assertGreaterEqual(min(pcts), 0.0)
                self.assertLessEqual(max(pcts), 100.0)

    def test_status_matches_percentile_bands(self):
        for key in KEYS:
            for value in _sample_values(key):
                pct = fa.percentile_position(key, value)
                status = fa.classify_metric(key, value)
                with self.subTest(metric=key, value=value):
                    if status == "GREEN":
                        self.assertGreaterEqual(pct, 75.0)
                    elif status == "RED":
                        self.assertLessEqual(pct, 25.0)
                    else:
                        self.assertTrue(25.0 < pct < 75.0)


class MonotonicityTests(unittest.TestCase):
    """Adding a metric never lowers the score or the letter grade."""

    def test_exhaustive_add_one_metric(self):
        samples = {key: _sample_values(key) for key in KEYS}
        options = [[None] + samples[key] for key in KEYS]  # None = missing
        cache = {}

        def run(state):
            if state not in cache:
                kwargs = {k: v for k, v in zip(KEYS, state) if v is not None}
                cache[state] = fa.analyze_funnel(**kwargs)
            return cache[state]

        checked = 0
        for state in itertools.product(*options):
            before = run(state)
            for i, key in enumerate(KEYS):
                if state[i] is not None:
                    continue
                for value in samples[key]:
                    after_state = state[:i] + (value,) + state[i + 1:]
                    after = run(after_state)
                    checked += 1
                    self.assertGreaterEqual(
                        after.score, before.score,
                        f"adding {key}={value} to {state} lowered the score",
                    )
                    if before.overall_health in GRADE_RANK:
                        self.assertIn(after.overall_health, GRADE_RANK)
                        self.assertGreaterEqual(
                            GRADE_RANK[after.overall_health],
                            GRADE_RANK[before.overall_health],
                            f"adding {key}={value} to {state} lowered the grade",
                        )
                    # Best case can only shrink toward the real score.
                    self.assertLessEqual(after.best_case_score, before.best_case_score)
        self.assertGreater(checked, 10000)

    def test_missing_metric_never_beats_worst_value(self):
        # Skipping a terrible metric must not score better than reporting it.
        base = {"signup_to_active": 40, "free_to_paid": 10, "nrr": 120,
                "time_to_value_days": 1}
        skipped = fa.analyze_funnel(**base)
        reported = fa.analyze_funnel(monthly_churn=60, payback_months=100, **base)
        self.assertGreaterEqual(reported.score, skipped.score)
        self.assertGreaterEqual(GRADE_RANK[reported.overall_health],
                                GRADE_RANK[skipped.overall_health])

    def test_score_formula_is_sum_of_nonnegative_terms(self):
        pcts = {"signup_to_active": 50.0, "nrr": 0.0}
        score, best = fa.funnel_score(pcts)
        self.assertEqual(score, 10.0)  # 20 x 0.5 + 15 x 0
        self.assertEqual(best, 75.0)   # + 20 + 15 + 15 + 15 for the 4 missing


class GradeTests(unittest.TestCase):

    @staticmethod
    def _at(attr):
        return {k: getattr(b, attr) for k, b in fa.BENCHMARKS.items()}

    def test_reference_grades(self):
        self.assertEqual(fa.analyze_funnel(**self._at("median")).overall_health, "C")
        self.assertEqual(fa.analyze_funnel(**self._at("median")).score, 50.0)
        self.assertEqual(fa.analyze_funnel(**self._at("top_25")).overall_health, "A")
        self.assertEqual(fa.analyze_funnel(**self._at("bottom_25")).overall_health, "F")

    def test_single_metric_is_partial_not_c(self):
        # Old behaviour: any single metric (GREEN or RED) gave C.
        for kwargs in ({"signup_to_active": 50}, {"monthly_churn": 12}):
            with self.subTest(**kwargs):
                result = fa.analyze_funnel(**kwargs)
                self.assertEqual(result.overall_health, "Partial - 1 of 6")

    def test_needs_four_metrics_for_a_letter(self):
        top = self._at("top_25")
        three = {k: top[k] for k in KEYS[:3]}
        four = {k: top[k] for k in KEYS[:4]}
        self.assertEqual(fa.analyze_funnel(**three).overall_health, "Partial - 3 of 6")
        self.assertIn(fa.analyze_funnel(**four).overall_health, GRADE_RANK)
        self.assertEqual(fa.analyze_funnel().overall_health, "N/A")

    def test_five_green_one_red_beats_six_yellow(self):
        # Old behaviour: both were C.
        five_green_one_red = dict(self._at("top_25"), payback_months=30)
        six_yellow = self._at("median")
        a = fa.analyze_funnel(**five_green_one_red)
        b = fa.analyze_funnel(**six_yellow)
        self.assertEqual((a.green_count, a.red_count), (5, 1))
        self.assertEqual(b.yellow_count, 6)
        self.assertGreater(GRADE_RANK[a.overall_health], GRADE_RANK[b.overall_health])

    def test_more_yellow_data_does_not_lower_score(self):
        # Old behaviour: 1 RED alone = C, 1 RED + 2 YELLOW = D.
        red_only = fa.analyze_funnel(monthly_churn=10)
        more = fa.analyze_funnel(monthly_churn=10, signup_to_active=20, free_to_paid=4)
        self.assertGreaterEqual(more.score, red_only.score)

    def test_demo_metrics(self):
        result = fa.analyze_funnel(signup_to_active=18, free_to_paid=3,
                                   monthly_churn=7, nrr=98,
                                   time_to_value_days=5, payback_months=15)
        self.assertEqual(result.yellow_count, 6)
        self.assertEqual(result.score, 36.5)
        self.assertEqual(result.overall_health, "D")
        self.assertEqual(result.best_case_score, result.score)
        self.assertEqual(result.missing_metrics, [])


class NormalizeTests(unittest.TestCase):

    def test_percent_strings_skip_and_units(self):
        metrics, warnings = fa.normalize_metrics({
            "signup_to_active": "25%",
            "free_to_paid": "skip",
            "monthly_churn": None,
            "nrr": " 112 % ",
            "time_to_value_days": "2 weeks",
            "payback_months": "1.5 years",
        })
        self.assertEqual(metrics, {"signup_to_active": 25.0, "nrr": 112.0,
                                   "time_to_value_days": 14.0,
                                   "payback_months": 18.0})
        self.assertEqual(warnings, [])

    def test_skip_spellings(self):
        for raw in ("skip", "SKIP", "", "n/a", "N/A", "unknown", "-", None):
            with self.subTest(raw=raw):
                metrics, _ = fa.normalize_metrics({"nrr": raw})
                self.assertEqual(metrics, {})

    def test_more_units(self):
        metrics, _ = fa.normalize_metrics({"time_to_value_days": "36 hours",
                                           "payback_months": "15mo"})
        self.assertAlmostEqual(metrics["time_to_value_days"], 1.5)
        self.assertEqual(metrics["payback_months"], 15.0)

    def test_minutes_and_spelled_out_percent(self):
        # "aha in 30 minutes" is a common way to state PLG time-to-value.
        metrics, warnings = fa.normalize_metrics({
            "time_to_value_days": "30 minutes",
            "monthly_churn": "0.5 percent",
            "free_to_paid": "0.8 pct",
        })
        self.assertAlmostEqual(metrics["time_to_value_days"], 30 / 1440)
        self.assertEqual(metrics["monthly_churn"], 0.5)
        self.assertEqual(metrics["free_to_paid"], 0.8)
        # A spelled-out percent counts as explicit, like "0.5%": no warning.
        self.assertEqual(warnings, [])
        # A bare "m" stays ambiguous (minutes or months) and is rejected.
        with self.assertRaises(fa.FunnelInputError):
            fa.normalize_metrics({"time_to_value_days": "30m"})

    def test_nrr_ratio_converted_with_warning(self):
        metrics, warnings = fa.normalize_metrics({"nrr": 1.12})
        self.assertAlmostEqual(metrics["nrr"], 112.0)
        self.assertTrue(any("ratio" in w for w in warnings))

    def test_fraction_payload_rejected(self):
        with self.assertRaises(fa.FunnelInputError) as ctx:
            fa.normalize_metrics({"signup_to_active": 0.35, "free_to_paid": 0.06,
                                  "monthly_churn": 0.03, "nrr": 1.12})
        text = " ".join(ctx.exception.problems)
        self.assertIn("look like fractions", text)
        self.assertIn("did you mean 35?", text)

    def test_single_small_value_only_warns(self):
        metrics, warnings = fa.normalize_metrics({"monthly_churn": 0.5,
                                                  "signup_to_active": 30})
        self.assertEqual(metrics["monthly_churn"], 0.5)
        self.assertEqual(len(warnings), 1)
        self.assertIn("monthly_churn = 0.5", warnings[0])

    def test_plausible_low_percent_not_flagged(self):
        # 1.2% churn is real; reading it as a fraction would mean 120%.
        _, warnings = fa.normalize_metrics({"monthly_churn": 1.2})
        self.assertEqual(warnings, [])
        # An explicit % sign confirms a small value.
        _, warnings = fa.normalize_metrics({"monthly_churn": "0.5%",
                                            "free_to_paid": "0.8%"})
        self.assertEqual(warnings, [])

    def test_bad_values_all_reported(self):
        with self.assertRaises(fa.FunnelInputError) as ctx:
            fa.normalize_metrics({
                "nrr": float("nan"),
                "monthly_churn": -2,
                "signup_to_active": 140,
                "free_to_paid": True,
                "time_to_value_days": "3 months",
                "payback_months": [1],
            })
        problems = ctx.exception.problems
        self.assertEqual(len(problems), 6)
        text = "\n".join(problems)
        for fragment in ("nrr: nan is not a finite number",
                         "monthly_churn: -2 is negative",
                         "signup_to_active: 140% is outside",
                         "free_to_paid: True is not a number",
                         "unit 'months'",
                         "payback_months: expected a number, got list"):
            self.assertIn(fragment, text)

    def test_impossible_values(self):
        for payload in ({"nrr": 5000}, {"nrr": "1.12%"}, {"nrr": 5},
                        {"time_to_value_days": 400}, {"payback_months": 500},
                        {"free_to_paid": float("inf")}, {"signup_to_active": "abc"}):
            with self.subTest(payload=payload):
                with self.assertRaises(fa.FunnelInputError):
                    fa.normalize_metrics(payload)

    def test_unknown_keys_warn(self):
        metrics, warnings = fa.normalize_metrics({"nrr": 105, "dau_mau": 20})
        self.assertEqual(metrics, {"nrr": 105.0})
        self.assertTrue(any("dau_mau" in w for w in warnings))

    def test_non_object_payload(self):
        with self.assertRaises(fa.FunnelInputError):
            fa.normalize_metrics([1, 2])

    def test_analyze_funnel_rejects_nan_directly(self):
        with self.assertRaises(fa.FunnelInputError):
            fa.analyze_funnel(nrr=float("nan"))
        with self.assertRaises(fa.FunnelInputError):
            fa.analyze_funnel(monthly_churn=-1)


class CliTests(unittest.TestCase):

    def assertCleanExit2(self, proc, *fragments):
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)
        self.assertIn("Input error", proc.stderr)
        for fragment in fragments:
            self.assertIn(fragment, proc.stderr)

    def test_skip_and_percent_strings_run(self):
        payload = json.dumps({"signup_to_active": "25%", "free_to_paid": "skip",
                              "monthly_churn": "4%", "nrr": "skip",
                              "time_to_value_days": 3, "payback_months": "skip"})
        proc = _run_cli(["-"], stdin_text=payload)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("OVERALL FUNNEL HEALTH: Partial - 3 of 6", proc.stdout)
        self.assertIn("Not provided: Free-to-Paid, Net Revenue Retention, Payback Period",
                      proc.stdout)

    def test_bad_json_exit_2(self):
        self.assertCleanExit2(_run_cli(["-"], stdin_text="{oops"), "not valid JSON")

    def test_missing_file_exit_2(self):
        missing = os.path.join(os.path.dirname(__file__), "no-such-metrics.json")
        self.assertCleanExit2(_run_cli([missing]), "not found")

    def test_fractions_exit_2(self):
        payload = json.dumps({"signup_to_active": 0.35, "free_to_paid": 0.06,
                              "monthly_churn": 0.03, "nrr": 1.12})
        self.assertCleanExit2(_run_cli(["-"], stdin_text=payload), "fractions")

    def test_list_payload_exit_2(self):
        self.assertCleanExit2(_run_cli(["-"], stdin_text="[1, 2]"), "must be an object")

    def test_demo_units_are_spaced(self):
        proc = _run_cli(["--demo"])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("5.0 days", proc.stdout)
        self.assertIn("15.0 months", proc.stdout)
        self.assertIsNone(re.search(r"\d(days|months)\b", proc.stdout))
        self.assertIn("FUNNEL SCORE: 36.5/100 (6 of 6 metrics)", proc.stdout)

    def test_skill_md_demo_block_runs(self):
        with open(SKILL_MD, encoding="utf-8") as fh:
            text = fh.read()
        match = re.search(r"### Demo Mode.*?```json\n(.*?)```", text, re.S)
        self.assertIsNotNone(match, "Demo Mode JSON block not found in SKILL.md")
        proc = _run_cli(["-"], stdin_text=match.group(1))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertRegex(proc.stdout, r"OVERALL FUNNEL HEALTH: [A-F] ")


if __name__ == "__main__":
    unittest.main()
