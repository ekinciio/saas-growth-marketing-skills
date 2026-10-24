"""Regression tests for skills/subscription-metrics/scripts/metrics_calculator.py.

Backlog item B02: NRR, GRR and revenue churn come from ONE month of MRR
movements but were graded on annual thresholds. The demo showed monthly
revenue churn 5% RED next to GRR 95% GREEN, although 95% a month is about
54% a year. They are now labeled monthly, graded on monthly-equivalent
thresholds (monthly = annual ^ (1/12)), shown with an annualized
approximation, and can be overridden with ttm_nrr_pct / ttm_grr_pct.

Backlog item B19: skipped inputs defaulted to 0 and were graded ({} earned
4 GREEN, a skipped margin gave "Rule of 40 0% RED"), and gross_margin_pct=80
was read as 8000%, inflating LTV 100x. Inputs now default to None (N/A, not
graded), zero denominators give N/A, gross margin accepts 80 or 0.80,
numeric strings and "skip" are coerced, impossible values exit 2.

All tests are offline and use in-memory inputs or temp files.
Run with: python3 -m unittest discover -s tests -t .
"""

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCRIPT = os.path.join(
    REPO_ROOT, "skills", "subscription-metrics", "scripts", "metrics_calculator.py"
)


def _load_module():
    """Import metrics_calculator.py by file path (the skills folder is not a package)."""
    name = "metrics_calculator_under_test"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    module = importlib.util.module_from_spec(spec)
    # dataclasses with postponed annotations look the module up in
    # sys.modules, so register it before executing.
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


mc = _load_module()

# One month for a healthy-looking company: every input provided.
FULL_INPUT = {
    "beginning_mrr": 100000,
    "new_mrr": 15000,
    "expansion_mrr": 3000,
    "contraction_mrr": 1000,
    "churned_mrr": 2000,
    "customers_start": 200,
    "customers_new": 25,
    "customers_churned": 8,
    "total_sales_marketing_spend": 30000,
    "net_burn": 40000,
    "yoy_revenue_growth_pct": 80,
    "profit_margin_pct": -20,
}


def _calc(payload):
    """Load a payload and return (metrics, health, recommendations, warnings)."""
    data, warnings = mc.load_business_data(payload)
    metrics, health, recs = mc.calculate_all_metrics(data)
    return metrics, health, recs, warnings


def _run_cli(*args, stdin=None):
    """Run the script as a subprocess and return the CompletedProcess."""
    return subprocess.run(
        [sys.executable, SCRIPT, *args],
        input=stdin,
        capture_output=True,
        text=True,
        timeout=60,
    )


def _with_mrr(beginning, expansion, contraction, churned, new=0):
    """MRR-only payload for retention threshold tests."""
    return {
        "beginning_mrr": beginning,
        "new_mrr": new,
        "expansion_mrr": expansion,
        "contraction_mrr": contraction,
        "churned_mrr": churned,
    }


class MonthlyRetentionMathTest(unittest.TestCase):
    """B02: the monthly-equivalent conversion and the annualized approximation."""

    def test_monthly_equivalent_thresholds(self):
        self.assertAlmostEqual(mc.monthly_equivalent_pct(90), 99.13, places=2)
        self.assertAlmostEqual(mc.monthly_equivalent_pct(80), 98.16, places=2)
        self.assertAlmostEqual(mc.monthly_equivalent_pct(110), 100.80, places=2)
        self.assertEqual(mc.monthly_equivalent_pct(100), 100.0)

    def test_annualized_approximation(self):
        self.assertAlmostEqual(mc.annualize_monthly_pct(95), 54.04, places=2)
        self.assertAlmostEqual(mc.annualize_monthly_pct(103), 142.58, places=2)
        # The two conversions are inverses.
        self.assertAlmostEqual(
            mc.annualize_monthly_pct(mc.monthly_equivalent_pct(90)), 90.0, places=9
        )


class DemoConsistencyTest(unittest.TestCase):
    """B02: the demo can no longer show revenue churn RED next to GRR GREEN."""

    def setUp(self):
        self.metrics, self.health, self.recs, _ = _calc(mc.DEMO_INPUT)

    def test_demo_grr_and_revenue_churn_agree(self):
        churn = self.metrics["monthly_revenue_churn"]
        grr = self.metrics["grr"]
        self.assertAlmostEqual(churn.value, 5.0)
        self.assertAlmostEqual(grr.value, 95.0)
        self.assertEqual(churn.status, "RED")
        self.assertEqual(grr.status, "RED")  # was GREEN on the annual 90% threshold

    def test_demo_rows_are_labeled_monthly_with_annualized_value(self):
        grr = self.metrics["grr"]
        nrr = self.metrics["nrr"]
        self.assertEqual(grr.name, "Monthly GRR")
        self.assertEqual(nrr.name, "Monthly NRR")
        self.assertEqual(grr.period, "monthly")
        self.assertAlmostEqual(grr.annualized, 54.04, places=2)
        self.assertIn("~54.0%/yr", grr.benchmark_note)
        self.assertIn("99.13%/mo", grr.benchmark_note)
        # Monthly NRR 103% clears the 100.80%/mo bar for annual 110%.
        self.assertEqual(nrr.status, "GREEN")

    def test_demo_cli_output(self):
        result = _run_cli("--demo")
        self.assertEqual(result.returncode, 0, result.stderr)
        out = result.stdout
        grr_line = next(line for line in out.splitlines() if line.startswith("Monthly GRR"))
        churn_line = next(
            line for line in out.splitlines() if line.startswith("Monthly Revenue Churn")
        )
        # Columns: name words, value, status, benchmark note.
        self.assertEqual(grr_line.split()[2:4], ["95.00%", "RED"])
        self.assertEqual(churn_line.split()[3:5], ["5.00%", "RED"])
        # The formula and caveat are shown, not just the numbers.
        self.assertIn("monthly = annual^(1/12)", out)
        self.assertIn("90%/yr = 99.13%/mo", out)
        self.assertIn("ttm_nrr_pct / ttm_grr_pct", out)
        self.assertIn("assumes the month repeats", out)

    def test_revenue_churn_rows_are_not_double_counted(self):
        # GRR and revenue churn are one number (100 - x); only GRR is graded.
        self.assertNotIn("Monthly Revenue Churn", self.health.improvements)
        self.assertEqual(self.health.red_count, 1)


class MonthlyThresholdTest(unittest.TestCase):
    """B02: single-month values are graded on monthly-equivalent thresholds."""

    def _status(self, key, payload):
        metrics, _, _, _ = _calc(payload)
        return metrics[key].status

    def test_monthly_grr_bands(self):
        # churn 0.5% -> GRR 99.5%/mo (~94%/yr) GREEN
        self.assertEqual(self._status("grr", _with_mrr(100000, 0, 0, 500)), "GREEN")
        # churn 1.5% -> GRR 98.5%/mo (~83.4%/yr) YELLOW
        self.assertEqual(self._status("grr", _with_mrr(100000, 0, 0, 1500)), "YELLOW")
        # churn 3% -> GRR 97%/mo (~69%/yr) RED (was GREEN before)
        self.assertEqual(self._status("grr", _with_mrr(100000, 0, 1000, 2000)), "RED")

    def test_revenue_churn_mirrors_grr_for_every_case(self):
        for churned in (0, 500, 874, 875, 1500, 1840, 1850, 3000, 5000, 20000):
            metrics, _, _, _ = _calc(_with_mrr(100000, 0, 0, churned))
            self.assertEqual(
                metrics["monthly_revenue_churn"].status,
                metrics["grr"].status,
                f"churned_mrr={churned}",
            )

    def test_monthly_nrr_bands(self):
        # NRR 101%/mo -> GREEN (>= 100.80%/mo)
        self.assertEqual(self._status("nrr", _with_mrr(100000, 1500, 0, 500)), "GREEN")
        # NRR 100.5%/mo -> YELLOW
        self.assertEqual(self._status("nrr", _with_mrr(100000, 1000, 0, 500)), "YELLOW")
        # NRR 98%/mo (~78%/yr) -> RED, and was treated like annual 98% before
        self.assertEqual(self._status("nrr", _with_mrr(100000, 0, 0, 2000)), "RED")

    def test_net_revenue_churn_mirrors_nrr(self):
        for expansion in (0, 500, 1000, 1300, 2000, 5000):
            metrics, _, _, _ = _calc(_with_mrr(100000, expansion, 200, 1000))
            self.assertEqual(
                metrics["net_revenue_churn"].status,
                metrics["nrr"].status,
                f"expansion_mrr={expansion}",
            )

    def test_same_displayed_value_never_gets_two_statuses(self):
        # With one decimal, churn 0.86% and 0.88% both showed "0.9%" (GREEN and
        # YELLOW), and NRR 100.775% showed "100.8% YELLOW" beside ">=100.80% GREEN".
        # Monthly rows now show two decimals and are graded at that precision.
        seen = {}
        for churned in range(800, 1900, 5):
            for expansion in (0, 775, 780, 790, 800):
                metrics, _, _, _ = _calc(_with_mrr(100000, expansion, 0, churned))
                for key in ("monthly_revenue_churn", "net_revenue_churn", "grr", "nrr"):
                    m = metrics[key]
                    previous = seen.setdefault((key, m.formatted), m.status)
                    self.assertEqual(previous, m.status, f"{key} {m.formatted}")
                # The mirror rows print numbers that add up to exactly 100.
                for churn_key, rate_key in (("monthly_revenue_churn", "grr"),
                                            ("net_revenue_churn", "nrr")):
                    total = (float(metrics[churn_key].formatted.rstrip("%"))
                             + float(metrics[rate_key].formatted.rstrip("%")))
                    self.assertAlmostEqual(total, 100.0, places=9,
                                           msg=f"{churn_key} churned={churned}")

    def test_threshold_edges_match_the_printed_thresholds(self):
        cases = [
            # (churned, expansion, key, formatted, status)
            (870, 0, "monthly_revenue_churn", "0.87%", "GREEN"),   # <= 0.87% GREEN
            (880, 0, "monthly_revenue_churn", "0.88%", "YELLOW"),
            (870, 0, "grr", "99.13%", "GREEN"),                    # >= 99.13% GREEN
            (1840, 0, "grr", "98.16%", "YELLOW"),                  # >= 98.16% YELLOW
            (1850, 0, "grr", "98.15%", "RED"),
            (0, 800, "nrr", "100.80%", "GREEN"),                   # >= 100.80% GREEN
            (0, 790, "nrr", "100.79%", "YELLOW"),
            (0, 800, "net_revenue_churn", "-0.80%", "GREEN"),      # <= -0.80% GREEN
            (500, 500, "net_revenue_churn", "0.00%", "YELLOW"),    # never "-0.00%"
        ]
        for churned, expansion, key, formatted, status in cases:
            metrics, _, _, _ = _calc(_with_mrr(100000, expansion, 0, churned))
            self.assertEqual(
                (metrics[key].formatted, metrics[key].status), (formatted, status),
                f"{key} churned={churned} expansion={expansion}",
            )


class TrailingTwelveMonthOverrideTest(unittest.TestCase):
    """B02: ttm_nrr_pct / ttm_grr_pct replace the monthly rows."""

    def test_ttm_values_override_and_use_annual_thresholds(self):
        payload = dict(mc.DEMO_INPUT, ttm_grr_pct=92, ttm_nrr_pct=105)
        metrics, _, _, _ = _calc(payload)
        grr, nrr = metrics["grr"], metrics["nrr"]
        self.assertEqual(grr.name, "GRR (trailing 12 mo)")
        self.assertEqual(grr.value, 92)
        self.assertEqual(grr.status, "GREEN")  # >= 90% a year
        self.assertEqual(grr.period, "trailing 12 months")
        self.assertIn("this month 95.00%/mo", grr.benchmark_note)
        self.assertEqual(nrr.name, "NRR (trailing 12 mo)")
        self.assertEqual(nrr.status, "YELLOW")  # 100-110% a year

    def test_ttm_without_monthly_data(self):
        metrics, _, _, _ = _calc({"ttm_grr_pct": 78, "ttm_nrr_pct": "115%"})
        self.assertEqual(metrics["grr"].status, "RED")
        self.assertEqual(metrics["nrr"].status, "GREEN")

    def test_ttm_fraction_is_read_as_percent_with_warning(self):
        metrics, _, _, warnings = _calc(dict(FULL_INPUT, ttm_grr_pct=0.91))
        self.assertAlmostEqual(metrics["grr"].value, 91.0)
        self.assertTrue(any("ttm_grr_pct" in w and "91.0%" in w for w in warnings))

    def test_ttm_grr_fraction_above_one_names_the_typed_value(self):
        with self.assertRaises(mc.InputError) as ctx:
            mc.load_business_data({"ttm_grr_pct": 1.5})
        self.assertIn("ttm_grr_pct: 1.5 read as a fraction is 150%", ctx.exception.errors[0])

    def test_period_notes_only_for_monthly_rows(self):
        metrics, _, _, _ = _calc({"ttm_grr_pct": 92, "ttm_nrr_pct": 105})
        self.assertEqual(mc.period_notes(metrics), [])
        metrics, _, _, _ = _calc(FULL_INPUT)
        notes = "\n".join(mc.period_notes(metrics))
        self.assertIn("rows marked Monthly come from ONE month", notes)
        self.assertIn("Annualized approximation (monthly^12): GRR 97.00%/mo ~ 69.4%/yr", notes)

    def test_period_notes_with_ttm_overrides(self):
        # Both overridden: the revenue churn rows are still one month and need
        # the footnote, but there is no monthly NRR/GRR to annualize.
        metrics, _, _, _ = _calc(dict(FULL_INPUT, ttm_grr_pct=92, ttm_nrr_pct=105))
        notes = "\n".join(mc.period_notes(metrics))
        self.assertIn("rows marked Monthly come from ONE month", notes)
        self.assertIn("NRR (trailing 12 mo) and GRR (trailing 12 mo): from your 12-month", notes)
        self.assertNotIn("Annualized approximation", notes)
        self.assertNotIn("pass ttm_nrr_pct", notes)
        # Only GRR overridden: GRR is described as a cohort figure and only NRR
        # is annualized (it used to say "NRR, GRR ... come from ONE month").
        metrics, _, _, _ = _calc(dict(FULL_INPUT, ttm_grr_pct=92))
        notes = "\n".join(mc.period_notes(metrics))
        self.assertNotIn("NRR, GRR", notes)
        self.assertIn("GRR (trailing 12 mo): from your 12-month cohort", notes)
        self.assertIn("Annualized approximation (monthly^12): NRR 100.00%/mo ~ 100.0%/yr.", notes)


class SkipHandlingTest(unittest.TestCase):
    """B19: missing inputs are N/A and never graded."""

    def test_empty_input_earns_no_green_and_no_grade(self):
        metrics, health, recs, _ = _calc({})
        greens = [m.name for m in metrics.values() if m.status == "GREEN"]
        self.assertEqual(greens, [])
        self.assertTrue(all(m.status == "N/A" for m in metrics.values()))
        self.assertEqual(health.grade, "N/A")
        self.assertEqual(health.total_count, 0)
        self.assertEqual(health.green_count, 0)
        self.assertEqual(recs, [])

    def test_empty_input_cli(self):
        result = _run_cli("-", stdin="{}")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("Infinite", result.stdout)
        self.assertIn("Overall Health Grade: N/A", result.stdout)
        self.assertIn("GREEN: 0 | YELLOW: 0 | RED: 0", result.stdout)

    def test_mrr_only_input_does_not_fabricate_other_metrics(self):
        payload = _with_mrr(100000, 1000, 1000, 2000, new=8000)
        metrics, health, _, _ = _calc(payload)
        self.assertEqual(metrics["rule_of_40"].status, "N/A")  # was 0.0% RED
        self.assertEqual(metrics["monthly_logo_churn"].status, "N/A")  # was 0.0% GREEN
        self.assertEqual(metrics["cac"].status, "N/A")
        self.assertIn("YoY revenue growth", health.not_provided)
        self.assertIn("profit margin", health.not_provided)
        self.assertIn("Not provided", metrics["rule_of_40"].benchmark_note)

    def test_skip_words_null_and_missing_are_equivalent(self):
        base = dict(FULL_INPUT)
        del base["yoy_revenue_growth_pct"]
        for variant in (None, "skip", "SKIP", "n/a", ""):
            payload = dict(base, yoy_revenue_growth_pct=variant)
            metrics, _, _, _ = _calc(payload)
            self.assertEqual(metrics["rule_of_40"].status, "N/A", repr(variant))
        metrics, _, _, _ = _calc(base)
        self.assertEqual(metrics["rule_of_40"].status, "N/A")

    def test_na_metrics_are_excluded_from_grade(self):
        _, full_health, _, _ = _calc(FULL_INPUT)
        payload = dict(FULL_INPUT, yoy_revenue_growth_pct="skip")
        _, health, _, _ = _calc(payload)
        self.assertEqual(health.total_count, full_health.total_count - 1)

    def test_too_few_graded_metrics_gives_no_letter_grade(self):
        _, health, _, _ = _calc({"yoy_revenue_growth_pct": 90, "profit_margin_pct": 10})
        self.assertEqual(health.total_count, 1)
        self.assertEqual(health.grade, "N/A")
        self.assertIn("at least", health.grade_note)


class ZeroDenominatorTest(unittest.TestCase):
    """B19: a zero denominator gives N/A, not Infinite GREEN or 0.00 RED."""

    def test_quick_ratio_without_outflows(self):
        metrics, _, _, _ = _calc(_with_mrr(100000, 2000, 0, 0, new=5000))
        self.assertEqual(metrics["quick_ratio"].status, "N/A")
        self.assertIn("zero denominator", metrics["quick_ratio"].benchmark_note)

    def test_magic_number_with_zero_prior_spend(self):
        metrics, _, _, _ = _calc(
            dict(FULL_INPUT, prev_quarter_sm_spend=0, current_quarter_net_new_arr=50000)
        )
        self.assertEqual(metrics["magic_number"].status, "N/A")

    def test_no_starting_customers_or_mrr(self):
        payload = dict(FULL_INPUT, customers_start=0, customers_churned=0, beginning_mrr=0,
                       contraction_mrr=0, churned_mrr=0, expansion_mrr=0)
        metrics, _, _, _ = _calc(payload)
        for key in ("monthly_logo_churn", "monthly_revenue_churn", "grr", "nrr",
                    "expansion_mrr_rate"):
            self.assertEqual(metrics[key].status, "N/A", key)

    def test_no_new_customers_gives_na_cac(self):
        metrics, _, _, _ = _calc(dict(FULL_INPUT, customers_new=0))
        self.assertEqual(metrics["cac"].status, "N/A")
        self.assertEqual(metrics["ltv_cac_ratio"].status, "N/A")


class GrossMarginTest(unittest.TestCase):
    """B19: gross margin as 80 or 0.80 means the same; the 70% default is disclosed."""

    def test_percent_and_fraction_give_same_ltv(self):
        pct, _, _, _ = _calc(dict(FULL_INPUT, gross_margin_pct=80))
        frac, _, _, _ = _calc(dict(FULL_INPUT, gross_margin_pct=0.80))
        text, _, _, _ = _calc(dict(FULL_INPUT, gross_margin_pct="80%"))
        self.assertAlmostEqual(pct["ltv"].value, frac["ltv"].value)
        self.assertAlmostEqual(pct["ltv"].value, text["ltv"].value)
        self.assertAlmostEqual(pct["ltv_cac_ratio"].value, frac["ltv_cac_ratio"].value)

    def test_gross_margin_80_does_not_inflate_ltv_100x(self):
        metrics, _, _, _ = _calc(dict(FULL_INPUT, gross_margin_pct=80))
        arpu = metrics["arpu"].value
        churn = metrics["monthly_logo_churn"].value / 100
        self.assertAlmostEqual(metrics["ltv"].value, arpu * 0.80 / churn)
        self.assertLess(metrics["ltv_cac_ratio"].value, 20)  # was 1000:1 class
        self.assertGreaterEqual(metrics["payback_period"].value, 1)  # was 0 months

    def test_direct_dataclass_construction_is_normalized_too(self):
        data = mc.BusinessData(**dict(FULL_INPUT, gross_margin_pct=80))
        metrics, _, _ = mc.calculate_all_metrics(data)
        expected, _, _, _ = _calc(dict(FULL_INPUT, gross_margin_pct=0.8))
        self.assertAlmostEqual(metrics["ltv"].value, expected["ltv"].value)

    def test_implausibly_low_margin_warns(self):
        # 1.5 is a percent (above 1), i.e. 1.5%: legal but almost surely a typo.
        _, _, _, warnings = _calc(dict(FULL_INPUT, gross_margin_pct=1.5))
        self.assertTrue(any("Gross margin is read as 1.5%" in w for w in warnings))
        _, _, _, warnings = _calc(dict(FULL_INPUT, gross_margin_pct=75))
        self.assertEqual(warnings, [])

    def test_default_margin_is_disclosed(self):
        metrics, health, _, _ = _calc(FULL_INPUT)
        self.assertTrue(any("70%" in a for a in health.assumptions))
        self.assertIn("70% margin assumed", metrics["ltv"].benchmark_note)
        _, health, _, _ = _calc(dict(FULL_INPUT, gross_margin_pct=75))
        self.assertEqual(health.assumptions, [])


class CoercionTest(unittest.TestCase):
    """B19: numeric strings are accepted; unreadable values are reported."""

    def test_numeric_strings(self):
        payload = dict(FULL_INPUT, beginning_mrr="$100,000", new_mrr="15K",
                       customers_start="200", total_sales_marketing_spend=" 30000 ")
        metrics, _, _, _ = _calc(payload)
        expected, _, _, _ = _calc(FULL_INPUT)
        for key in ("mrr", "monthly_logo_churn", "cac", "grr"):
            self.assertAlmostEqual(metrics[key].value, expected[key].value, msg=key)

    def test_unreadable_values_list_every_problem(self):
        with self.assertRaises(mc.InputError) as ctx:
            mc.load_business_data({"new_mrr": "abc", "net_burn": True, "churned_mrr": [1]})
        errors = ctx.exception.errors
        self.assertEqual(len(errors), 3)
        self.assertTrue(any(e.startswith("new_mrr:") for e in errors))

    def test_non_object_payload(self):
        with self.assertRaises(mc.InputError):
            mc.load_business_data([1])

    def test_unknown_fields_warn(self):
        _, warnings = mc.load_business_data({"beginning_mrr": 1000, "mrr_growth": 5})
        self.assertTrue(any("mrr_growth" in w for w in warnings))


class ImpossibleValueTest(unittest.TestCase):
    """B19: impossible values are rejected with readable errors."""

    def assertRejected(self, payload, fragment):
        with self.assertRaises(mc.InputError) as ctx:
            mc.load_business_data(payload)
        self.assertTrue(
            any(fragment in e for e in ctx.exception.errors),
            f"{fragment!r} not in {ctx.exception.errors}",
        )

    def test_more_churned_than_existed(self):
        self.assertRejected(
            {"customers_start": 5, "customers_new": 0, "customers_churned": 9},
            "customers_churned",
        )

    def test_churn_from_new_customers_is_allowed(self):
        data, _ = mc.load_business_data(
            {"customers_start": 5, "customers_new": 6, "customers_churned": 9}
        )
        self.assertEqual(data.customers_churned, 9)

    def test_negative_and_out_of_range(self):
        self.assertRejected({"churned_mrr": -2000}, "positive amount")
        self.assertRejected({"gross_margin_pct": 150}, "gross_margin_pct")
        self.assertRejected({"gross_margin_pct": 0}, "gross_margin_pct")
        self.assertRejected({"profit_margin_pct": 120}, "profit_margin_pct")
        self.assertRejected({"yoy_revenue_growth_pct": -150}, "yoy_revenue_growth_pct")
        self.assertRejected({"ttm_grr_pct": 120}, "ttm_grr_pct")
        self.assertRejected({"customers_new": 2.5}, "whole number")

    def test_mrr_lost_exceeds_mrr_available(self):
        self.assertRejected(_with_mrr(100000, 0, 50000, 60000, new=1000), "ending MRR")

    def test_cli_exit_code_2_with_readable_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "bad.json")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump({"customers_start": 5, "customers_new": 0,
                           "customers_churned": 9, "new_mrr": "abc"}, fh)
            result = _run_cli(path)
        self.assertEqual(result.returncode, 2)
        self.assertIn("customers_churned", result.stderr)
        self.assertIn("new_mrr", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_cli_bad_json_and_list(self):
        for text in ("[1]", "{not json", "null"):
            result = _run_cli("-", stdin=text)
            self.assertEqual(result.returncode, 2, text)
            self.assertNotIn("Traceback", result.stderr, text)

    def test_cli_file_encodings(self):
        with tempfile.TemporaryDirectory() as tmp:
            # A byte-order mark (Windows editors) is accepted.
            bom = os.path.join(tmp, "bom.json")
            with open(bom, "wb") as fh:
                fh.write(b'\xef\xbb\xbf{"beginning_mrr": 1000}')
            result = _run_cli(bom)
            self.assertEqual(result.returncode, 0, result.stderr)
            # A non-UTF-8 file is an input error (exit 2), not a traceback.
            binary = os.path.join(tmp, "binary.json")
            with open(binary, "wb") as fh:
                fh.write(b"\xff\xfe\x00\x81garbage")
            result = _run_cli(binary)
        self.assertEqual(result.returncode, 2)
        self.assertIn("not UTF-8", result.stderr)
        self.assertNotIn("Traceback", result.stderr)


class SanityWarningTest(unittest.TestCase):
    """B19: values that look annual or fractional produce warnings, not errors."""

    def test_annual_looking_values(self):
        payload = dict(FULL_INPUT, new_mrr=70000, total_operating_costs=1800000,
                       customers_churned=40, yoy_revenue_growth_pct=0.6)
        payload.pop("net_burn")
        _, _, _, warnings = _calc(payload)
        joined = " | ".join(warnings)
        self.assertIn("new_mrr", joined)
        self.assertIn("operating costs", joined)
        self.assertIn("Logo churn is 20.0%", joined)
        self.assertIn("If you meant 60%", joined)

    def test_clean_input_has_no_warnings(self):
        _, _, _, warnings = _calc(FULL_INPUT)
        self.assertEqual(warnings, [])


class BurnMultipleLabelTest(unittest.TestCase):
    """Edge labels that used to show 'N/A' with a RED status or '-0.4x GREEN'."""

    def test_shrinking_arr_while_burning_is_red_not_na(self):
        payload = dict(FULL_INPUT, new_mrr=0, expansion_mrr=0)
        metrics, _, _, _ = _calc(payload)
        bm = metrics["burn_multiple"]
        self.assertEqual(bm.status, "RED")
        self.assertEqual(bm.formatted, "ARR not growing")

    def test_cash_flow_positive(self):
        metrics, _, _, _ = _calc(dict(FULL_INPUT, net_burn=-10000))
        self.assertEqual(metrics["burn_multiple"].formatted, "Cash-flow positive")

    def test_missing_burn_is_na(self):
        payload = dict(FULL_INPUT)
        payload.pop("net_burn")
        metrics, _, _, _ = _calc(payload)
        self.assertEqual(metrics["burn_multiple"].status, "N/A")


if __name__ == "__main__":
    unittest.main()
