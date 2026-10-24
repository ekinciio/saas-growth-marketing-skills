"""Tests for skills/landing-page-cro/scripts/ab_sizing.py.

The v1 ab-ideas command asked the model for an "expected lift range" per
test and never asked for traffic, so it proposed A/B tests to sites that
could never reach significance (audit: at a 3.8% baseline and a 20%
relative MDE a test needs about 10,900 visitors per arm). ab_sizing.py
wraps the shared stats helper and decides test versus ship-and-measure.

Offline and deterministic. Run with: python3 -m unittest discover -s tests -t .
"""

import contextlib
import importlib.util
import io
import json
import os
import sys
import unittest
import warnings

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCRIPT = os.path.join(REPO_ROOT, "skills", "landing-page-cro", "scripts", "ab_sizing.py")


def _load_module():
    name = "ab_sizing_under_test"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        spec.loader.exec_module(module)
    return module


ab = _load_module()


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = ab.main(argv + ["--json"])
        except SystemExit as exc:
            code = exc.code
    return code, json.loads(out.getvalue())


class SizingTests(unittest.TestCase):

    def test_reference_sample_size(self):
        # stats.py docstring: baseline 0.038, mde 0.2 -> 10,885 visitors per arm.
        code, data = run(["--baseline", "3.8%", "--weekly-visitors", "100000"])
        self.assertEqual(code, 0)
        plan = data["plans"][0]
        self.assertEqual(plan["n_per_arm"], 10885)
        self.assertEqual(plan["total_visitors"], 21770)
        self.assertTrue(plan["feasible"])
        self.assertEqual(plan["test_plan"], "ab_test")
        self.assertEqual(plan["recommended_weeks"], 2, "a test always covers at least 2 full weeks")

    def test_monthly_traffic_is_divided_by_4_33(self):
        code, data = run(["--baseline", "3.8", "--monthly-visitors", "18000"])
        self.assertEqual(code, 0)
        self.assertAlmostEqual(data["inputs"]["weekly_visitors"], round(18000 / 4.33, 1))
        self.assertEqual(data["inputs"]["weekly_source"], "monthly_visitors / 4.33")

    def test_low_traffic_means_ship_and_measure(self):
        code, data = run(["--baseline", "3.8%", "--monthly-visitors", "5000"])
        self.assertEqual(code, 0)
        plan = data["plans"][0]
        self.assertFalse(plan["feasible"])
        self.assertEqual(plan["test_plan"], "ship_and_measure")
        self.assertIsNone(plan["recommended_weeks"])
        self.assertGreater(plan["smallest_detectable_relative_lift_in_max_weeks"], 0.2)
        self.assertTrue(data["low_traffic_alternatives"])

    def test_several_mdes(self):
        code, data = run(["--baseline", "2.5", "--weekly-visitors", "20000", "--mde", "10", "20", "30"])
        self.assertEqual(code, 0)
        sizes = [p["n_per_arm"] for p in data["plans"]]
        self.assertEqual(len(sizes), 3)
        self.assertTrue(sizes[0] > sizes[1] > sizes[2])

    def test_unknown_traffic_gives_weekly_need(self):
        code, data = run(["--baseline", "3.8%"])
        self.assertEqual(code, 0)
        plan = data["plans"][0]
        self.assertEqual(plan["test_plan"], "unknown_traffic")
        self.assertEqual(plan["weekly_visitors_needed"], 5443)  # 21,770 / 4 weeks, rounded up
        self.assertTrue(any("Traffic unknown" in n for n in data["notes"]))

    def test_benchmark_baseline_is_sourced_and_flagged(self):
        code, data = run([])
        self.assertEqual(code, 0)
        source = data["inputs"]["baseline_source"]
        self.assertEqual(source["kind"], "benchmark")
        self.assertEqual(source["row_id"], "landing_page_conversion.unbounce2024.saas")
        self.assertEqual(source["value_percent"], 3.8)
        self.assertIn("Unbounce", source["source_name"])
        self.assertTrue(any("ASSUMED baseline" in n for n in data["notes"]))
        self.assertTrue(any("ASSUMED minimum detectable effect" in n for n in data["notes"]))

    def test_more_arms_need_more_traffic(self):
        _, two = run(["--baseline", "3.8", "--weekly-visitors", "5000"])
        _, three = run(["--baseline", "3.8", "--weekly-visitors", "5000", "--arms", "3"])
        self.assertGreater(three["plans"][0]["weeks"], two["plans"][0]["weeks"])

    def test_usage_errors(self):
        for argv in (["--baseline", "150"], ["--baseline", "0"], ["--baseline", "abc"],
                     ["--baseline", "3.8", "--mde", "-5"], ["--baseline", "3.8", "--arms", "1"],
                     ["--baseline", "90", "--mde", "20"], ["--benchmark", "no.such.row"],
                     ["--monthly-visitors", "1000", "--weekly-visitors", "200"]):
            with self.subTest(argv=argv):
                code, data = run(argv)
                self.assertEqual(code, 2)
                self.assertEqual(data["status"], "usage_error")


if __name__ == "__main__":
    unittest.main()
