"""Offline tests for growthkit.importers (billing and analytics export import).

Fixtures live in tests/shared/fixtures/importers/. They are small, made-up
exports: every name, email and id in them is fictional, and the expected
numbers below were worked out by hand from the fixture rows.

Run from the repo root:
    python3 -m unittest discover -s tests -t .
"""

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from datetime import date, datetime

from tests import _paths
from growthkit import importers as im  # noqa: E402

FIXTURES = _paths.fixture_path("shared", "fixtures", "importers")


def fx(name):
    return os.path.join(FIXTURES, name)


def run_cli(*args):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = im.main(list(args))
    return code, out.getvalue(), err.getvalue()


class TempDir(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="importers_")
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def write(self, name, text):
        path = os.path.join(self.tmp, name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
        return path


# ---------------------------------------------------------------------------
# Value parsing
# ---------------------------------------------------------------------------


class ParseNumberTests(unittest.TestCase):
    def test_separators_signs_and_symbols(self):
        cases = {
            "1,234.50": 1234.5, "1.234,50": 1234.5, "$49.00": 49.0, "(12.00)": -12.0,
            "45%": 45.0, "12 USD": 12.0, "eur 9,50": 9.5, "49,90": 49.9, "1,234": 1234.0,
            "-3.5": -3.5, "1 234": 1234.0, "\u221212": -12.0, "\u20ac1.200,00": 1200.0,
        }
        for text, expected in cases.items():
            self.assertEqual(im.parse_number(text), expected, text)

    def test_decimal_comma_files(self):
        self.assertEqual(im.parse_number("1,234", decimal_comma=True), 1.234)
        self.assertEqual(im.parse_number("1.234", decimal_comma=True), 1234.0)

    def test_placeholders_and_non_numbers(self):
        for text in ("", "-", "~", "n/a", "(not set)", "Day 0", "2024-03-01", "abc", None, True):
            self.assertIsNone(im.parse_number(text), text)

    def test_parse_rate(self):
        self.assertEqual(im.parse_rate("45%"), 0.45)
        self.assertEqual(im.parse_rate("0.45"), 0.45)
        self.assertEqual(im.parse_rate("3.2"), 0.032)
        self.assertIsNone(im.parse_rate("-"))


class ParseDateTests(unittest.TestCase):
    def test_formats(self):
        cases = {
            "2024-03-15": date(2024, 3, 15), "2024-03-15 10:22:33": date(2024, 3, 15),
            "2025-12-31T00:00:00Z": date(2025, 12, 31), "20240315": date(2024, 3, 15),
            "2024-03": date(2024, 3, 1), "Mar 2024": date(2024, 3, 1),
            "Jan 5, 2024": date(2024, 1, 5), "5 January 2024": date(2024, 1, 5),
            "1700000000": date(2023, 11, 14), "15/03/2024": date(2024, 3, 15),
        }
        for text, expected in cases.items():
            self.assertEqual(im.parse_date(text), expected, text)
        self.assertIsNone(im.parse_date("not a date"))
        self.assertIsNone(im.parse_date("2024-13-01"))

    def test_slashed_dates_follow_the_column(self):
        self.assertEqual(im.date_order(["01/02/2026", "15/01/2026"]), ("dmy", False))
        self.assertEqual(im.date_order(["01/02/2026", "01/15/2026"]), ("mdy", False))
        self.assertEqual(im.date_order(["01/02/2026", "03/04/2026"]), ("mdy", True))
        self.assertEqual(im.date_order(["2026-01-02"]), (None, False))
        self.assertEqual(im.parse_date("01/02/2026", "dmy"), date(2026, 2, 1))
        self.assertEqual(im.parse_date("01/02/2026", "mdy"), date(2026, 1, 2))

    def test_durations(self):
        self.assertEqual(im.parse_duration("1h 2m 3s"), 3723)
        self.assertEqual(im.parse_duration("00:03:20"), 200)
        self.assertEqual(im.parse_duration("1d 2h"), 93600)
        self.assertEqual(im.parse_duration("3.5 min"), 210)
        self.assertIsNone(im.parse_duration("12"))
        self.assertIsNone(im.parse_duration("soon"))

    def test_months(self):
        self.assertEqual(im.add_months("2026-01", -1), "2025-12")
        self.assertEqual(im.add_months("2025-11", 14), "2027-01")
        self.assertEqual(im.month_key(date(2026, 9, 30)), "2026-09")


class CurrencyAndPrivacyTests(unittest.TestCase):
    def test_minor_units_follow_stripe_currency_exponents(self):
        self.assertEqual(im.from_minor(4900, "USD"), 49.0)
        self.assertEqual(im.from_minor(5000, "JPY"), 5000.0)
        self.assertEqual(im.from_minor(12345, "KWD"), 12.345)
        self.assertEqual(im.from_minor(500, "ISK"), 5.0)       # two decimals at Stripe
        self.assertEqual(im.from_minor(100, None), 1.0)

    def test_normalize_currency(self):
        self.assertEqual(im.normalize_currency("usd"), "USD")
        self.assertEqual(im.normalize_currency("$"), "USD")
        self.assertIsNone(im.normalize_currency("dollars"))

    def test_pii_headers(self):
        for key in ("email", "customer_email", "customer_name", "company_name", "customer_description",
                    "customer_first_name", "phone", "billing_address_line1", "name"):
            self.assertTrue(im.is_pii_header(key), key)
        for key in ("plan_name", "customer_id", "address_id", "customer_uuid", "product_name", "users"):
            self.assertFalse(im.is_pii_header(key), key)

    def test_pseudonym_is_stable_and_not_the_id(self):
        first = im.pseudonym("cus_A001")
        self.assertEqual(first, im.pseudonym(" cus_A001 "))
        self.assertNotEqual(first, im.pseudonym("cus_B001"))
        self.assertNotIn("A001", first)
        self.assertIsNone(im.pseudonym(""))

    def test_headers_normalize(self):
        self.assertEqual(im.normalize_header("Created (UTC)"), "created")
        self.assertEqual(im.normalize_header("subscription[plan_id]"), "subscription_plan_id")
        self.assertEqual(im.normalize_header("\ufeffTop queries"), "top_queries")
        self.assertEqual(im.normalize_header("Day 0"), "day_0")


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------


class ParseTableTests(unittest.TestCase):
    def test_comment_preamble_is_kept_and_skipped(self):
        table = im.read_tables(fx("ga4_funnel_exploration.csv"))[0]
        self.assertEqual(table.headers[0], "Step")
        self.assertIn("Funnel exploration", table.preamble)
        self.assertEqual(len(table.rows), 8)

    def test_title_line_above_header(self):
        table = im.read_tables(fx("funnel_wide_segments.csv"))[0]
        self.assertEqual(table.headers[0], "Segment")
        self.assertEqual(table.preamble, ["Funnel: Signup (last 30 days)"])

    def test_numeric_period_headers(self):
        table = im.read_tables(fx("chartmogul_cohorts.csv"))[0]
        self.assertEqual(table.headers, ["Cohort", "Cohort value", "0", "1", "2", "3", "Average"])

    def test_semicolon_and_bom(self):
        table = im.parse_table("\ufeffa;b;c\n1;2,5;x\n", "x.csv")
        self.assertEqual(table.delimiter, ";")
        self.assertTrue(table.decimal_comma)
        self.assertEqual(table.keys, ["a", "b", "c"])
        self.assertEqual(table.number(table.rows[0], 1), 2.5)

    def test_only_the_first_section_is_read(self):
        text = "Step,Users\nA,10\nB,5\n\n# Second table\nX,Y\n1,2\n"
        table = im.parse_table(text, "two.csv")
        self.assertEqual(len(table.rows), 2)
        self.assertTrue(table.more_sections)

    def test_not_a_table(self):
        with self.assertRaises(im.ImportFormatError):
            im.parse_table("just one line\nand another\n", "x.csv")


class FileHandlingTests(TempDir):
    def test_missing_file_and_spreadsheets(self):
        with self.assertRaises(im.ImportFormatError):
            im.load(os.path.join(self.tmp, "missing.csv"))
        xlsx = self.write("export.xlsx", "not really excel")
        with self.assertRaisesRegex(im.ImportFormatError, "save or export the sheet as CSV"):
            im.load(xlsx)

    def test_unknown_format_lists_headers(self):
        with self.assertRaises(im.ImportFormatError) as ctx:
            im.load(fx("unknown_format.csv"))
        self.assertEqual(ctx.exception.details["headers"], ["foo", "bar", "baz"])
        self.assertIn("stripe_subscriptions", ctx.exception.details["supported_formats"])

    def test_kind_and_source_filters(self):
        with self.assertRaises(im.ImportFormatError):
            im.load(fx("gsc_queries.csv"), kind="billing")
        with self.assertRaises(im.ImportFormatError):
            im.load(fx("gsc_queries.csv"), source="no_such_format")
        loaded = im.load(fx("chartmogul_mrr_per_customer.csv"), source="customer_mrr_wide", currency="USD")
        self.assertEqual(loaded["format"]["source"], "customer_mrr_wide")

    def test_headers_only_is_nothing_to_import(self):
        with self.assertRaises(im.NothingToImport):
            im.analyze(fx("stripe_subscriptions_headers_only.csv"))

    def test_zip_member_choice(self):
        archive = os.path.join(self.tmp, "gsc.zip")
        with zipfile.ZipFile(archive, "w") as handle:
            handle.write(fx("gsc_pages.csv"), "Pages.csv")
            handle.write(fx("gsc_filters.csv"), "Filters.csv")
            handle.write(fx("gsc_queries.csv"), "Queries.csv")
        result = im.analyze(archive)
        self.assertEqual(result["file"]["name"], "Queries.csv")
        self.assertEqual(result["search"]["dimension"], "query")
        self.assertTrue(any("Pages.csv" in note for note in result["notes"]))
        pages = im.analyze(archive, member="Pages.csv")
        self.assertEqual(pages["search"]["dimension"], "page")
        self.assertEqual(pages["search"]["totals"]["clicks"], 245)
        with self.assertRaises(im.ImportFormatError):
            im.analyze(archive, member="Nope.csv")


class DetectionTests(unittest.TestCase):
    EXPECTED = {
        "stripe_subscriptions.csv": ("stripe_subscriptions", "billing"),
        "stripe_invoices.csv": ("stripe_invoices", "invoices"),
        "chartmogul_all_mrr_movements.csv": ("chartmogul_mrr_movements", "billing"),
        "chartmogul_mrr_per_customer.csv": ("chartmogul_customer_mrr", "billing"),
        "chartmogul_cohorts.csv": ("chartmogul_cohorts", "retention"),
        "stripe_sigma_mrr_events.csv": ("stripe_mrr_events", "billing"),
        "paddle_subscriptions_report.csv": ("paddle_subscriptions", "billing"),
        "chargebee_subscriptions_import_friendly.csv": ("chargebee_subscriptions", "billing"),
        "generic_subscriptions_semicolon.csv": ("generic_subscriptions", "billing"),
        "generic_movements.csv": ("generic_movements", "billing"),
        "ga4_funnel_exploration.csv": ("funnel_steps", "funnel"),
        "funnel_steps_time.csv": ("funnel_steps", "funnel"),
        "funnel_wide_segments.csv": ("funnel_wide", "funnel"),
        "retention_day_percent.csv": ("retention_grid", "retention"),
        "retention_week_counts.csv": ("retention_grid", "retention"),
        "gsc_queries.csv": ("gsc_performance", "search"),
        "gsc_pages.csv": ("gsc_performance", "search"),
        "posthog_events.csv": ("event_log", "events"),
    }

    def test_every_fixture_is_detected(self):
        for name, (source, kind) in self.EXPECTED.items():
            table = im.read_tables(fx(name))[0]
            fmt, _match = im.detect(table)
            self.assertEqual((fmt.source, fmt.kind), (source, kind), name)

    def test_format_registry(self):
        sources = [fmt["source"] for fmt in im.list_formats()]
        self.assertEqual(len(sources), len(set(sources)))
        for fmt in im.list_formats():
            self.assertIn(fmt["kind"], im.KINDS)
            self.assertIn(fmt["confidence"], ("high", "medium"))
            if fmt["confidence"] == "high":
                self.assertTrue(fmt["docs"], fmt["source"])
            for url in fmt["docs"]:
                self.assertTrue(url.startswith("https://"), url)


# ---------------------------------------------------------------------------
# Billing
# ---------------------------------------------------------------------------


def by_month(block):
    return {row["month"]: row for row in block["monthly"]}


class StripeSubscriptionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = im.analyze(fx("stripe_subscriptions.csv"))
        cls.billing = cls.result["billing"]
        cls.usd = cls.billing["by_currency"]["USD"]

    def test_format_and_privacy(self):
        fmt = self.result["format"]
        self.assertEqual(fmt["confidence"], "medium")
        self.assertEqual(fmt["amount_unit"], "major")
        self.assertEqual(fmt["column_map"]["amount"], "Amount")
        self.assertEqual(sorted(fmt["pii_columns_ignored"]), ["Customer Description", "Customer Email"])
        text = json.dumps(self.result)
        for secret in ("@example.com", "cus_", "sub_1", "Example Co"):
            self.assertNotIn(secret, text)

    def test_current_mrr_per_currency(self):
        self.assertEqual(self.billing["as_of"], "2026-09")
        self.assertEqual(self.billing["currencies"], ["EUR", "USD"])
        self.assertEqual(self.billing["primary_currency"], "USD")
        self.assertEqual(self.usd["current"], {"month": "2026-09", "mrr": 305.0, "arr": 3660.0,
                                               "paying_customers": 6, "arpa": 50.83})
        self.assertEqual(self.billing["by_currency"]["EUR"]["current"]["mrr"], 45.0)
        self.assertFalse(self.billing["expansion_contraction_observable"])

    def test_bridge(self):
        months = by_month(self.usd)
        self.assertEqual(sorted(months), im.month_range("2025-10", "2026-09"))
        march = months["2026-03"]
        self.assertEqual((march["starting_mrr"], march["churned_mrr"], march["ending_mrr"]), (344.0, 49.0, 295.0))
        self.assertEqual(march["customers_start"], 7)
        self.assertEqual(march["logo_churn_rate"], round(1 / 7.0, 4))
        self.assertEqual(march["gross_mrr_churn_rate"], round(49 / 344.0, 4))
        self.assertEqual(months["2025-12"]["churned_mrr"], 49.0)          # cus_L001 ended on Dec 31
        self.assertEqual(months["2026-06"]["reactivation_mrr"], 49.0)     # cus_L001 came back
        self.assertEqual(months["2026-07"]["expansion_mrr"], 10.0)        # cus_A001 added an add-on
        self.assertEqual(sum(m["new_mrr"] for m in self.usd["monthly"]), 147.0)
        self.assertEqual(months["2026-02"]["new_mrr"], 49.0)              # paid after the trial ended

    def test_ttm_retention(self):
        ttm = self.usd["ttm_retention"]
        self.assertEqual(ttm["base_month"], "2025-09")
        self.assertEqual((ttm["starting_mrr"], ttm["ending_mrr"]), (246.0, 207.0))
        self.assertEqual(ttm["grr"], round(197 / 246.0, 4))
        self.assertEqual(ttm["nrr"], round(207 / 246.0, 4))
        self.assertEqual(ttm["logo_retention"], 0.8)

    def test_churn_types_trials_and_mix(self):
        churn = self.usd["churn_by_type"]
        self.assertEqual(churn["voluntary"], {"subscriptions": 1, "mrr": 49.0})
        self.assertEqual(churn["involuntary"], {"subscriptions": 1, "mrr": 49.0})
        self.assertEqual(churn["unknown"], {"subscriptions": 1, "mrr": 49.0})   # no reason given
        trials = self.usd["trials"]
        self.assertEqual((trials["trials_ended_in_window"], trials["converted"]), (2, 1))
        self.assertEqual(trials["currently_trialing"], 1)
        plans = {row["plan"]: row for row in self.usd["plan_mix"]}
        self.assertEqual(plans["Pro Monthly"]["active_subscriptions"], 4)
        self.assertEqual(plans["Team Monthly"]["mrr"], 60.0)              # 3 seats x 20
        intervals = {row["interval"]: row["mrr"] for row in self.usd["interval_mix"]}
        self.assertEqual(intervals, {"month": 266.0, "year": 39.0})
        self.assertEqual(self.usd["status_counts"]["incomplete_expired"], 1)
        self.assertEqual(self.usd["past_due_subscriptions"], 1)

    def test_as_of_override(self):
        earlier = im.analyze(fx("stripe_subscriptions.csv"), as_of="2026-03", months=3)
        usd = earlier["billing"]["by_currency"]["USD"]
        self.assertEqual(usd["current"]["mrr"], 295.0)
        self.assertEqual([m["month"] for m in usd["monthly"]], ["2026-01", "2026-02", "2026-03"])
        self.assertIsNone(usd["ttm_retention"]["nrr"])
        self.assertIn("2025-03", usd["ttm_retention"]["reason"])
        with self.assertRaises(im.ImportFormatError):
            im.analyze(fx("stripe_subscriptions.csv"), as_of="2026-13")


class StripeInvoiceTests(unittest.TestCase):
    def test_payment_health(self):
        result = im.analyze(fx("stripe_invoices.csv"))
        self.assertEqual(result["rows"]["skipped"]["excluded_by_rule"], {"draft invoice": 1})
        usd = result["invoices"]["by_currency"]["USD"]
        self.assertEqual(usd["payment_failure_rate"], 0.5)
        self.assertEqual(usd["recovery_rate"], round(1 / 3.0, 4))
        self.assertEqual(usd["open_amount_due"], 49.0)
        september = {m["month"]: m for m in usd["monthly"]}["2026-09"]
        self.assertEqual((september["invoices"], september["paid"], september["amount_paid"]), (2, 1, 468.0))
        self.assertEqual(usd["status_counts"], {"paid": 4, "open": 1, "uncollectible": 1, "void": 1})
        self.assertEqual(result["invoices"]["by_currency"]["EUR"]["monthly"][0]["month"], "2026-09")
        self.assertNotIn("@example.com", json.dumps(result))


class ChartMogulTests(unittest.TestCase):
    def test_mrr_movements_use_vendor_types(self):
        result = im.analyze(fx("chartmogul_all_mrr_movements.csv"))
        self.assertEqual(result["format"]["confidence"], "high")
        self.assertEqual(result["format"]["column_map"]["amount"], "mrr_movement_in_account_currency")
        self.assertEqual(result["format"]["pii_columns_ignored"], ["customer_name"])
        billing = result["billing"]
        self.assertEqual(billing["history_basis"], "movements")
        usd = billing["by_currency"]["USD"]
        self.assertEqual(usd["current"]["mrr"], 500.0)
        self.assertEqual(usd["current"]["paying_customers"], 4)
        months = by_month(usd)
        self.assertEqual(months["2025-10"]["new_mrr"], 480.0)
        self.assertEqual(months["2025-12"]["churned_mrr"], 80.0)
        self.assertEqual(months["2026-02"]["expansion_mrr"], 50.0)
        self.assertEqual(months["2026-03"]["contraction_mrr"], 80.0)
        self.assertEqual(months["2026-04"]["churned_mrr"], 300.0)
        self.assertEqual(months["2026-05"]["reactivation_mrr"], 80.0)
        self.assertEqual(months["2026-04"]["starting_mrr"], 720.0)
        self.assertIsNone(usd["ttm_retention"]["nrr"])
        october = [c for c in usd["cohorts"] if c["cohort"] == "2025-10"][0]
        self.assertEqual((october["customers"], october["starting_mrr"]), (3, 480.0))
        text = json.dumps(result)
        self.assertNotIn("Example", text)
        self.assertNotIn("cus_000", text)

    def test_mrr_per_customer_per_month(self):
        result = im.analyze(fx("chartmogul_mrr_per_customer.csv"), currency="USD")
        usd = result["billing"]["by_currency"]["USD"]
        self.assertEqual(usd["current"]["mrr"], 380.0)
        ttm = usd["ttm_retention"]
        self.assertEqual((ttm["starting_mrr"], ttm["ending_mrr"]), (230.0, 180.0))
        self.assertEqual(ttm["nrr"], round(180 / 230.0, 4))
        self.assertEqual(ttm["grr"], round(160 / 230.0, 4))
        months = by_month(usd)
        self.assertEqual(months["2026-06"]["expansion_mrr"], 20.0)
        self.assertEqual(months["2026-08"]["contraction_mrr"], 20.0)
        self.assertEqual(months["2026-03"]["churned_mrr"], 50.0)
        self.assertEqual(months["2026-01"]["new_mrr"], 200.0)
        unlabeled = im.analyze(fx("chartmogul_mrr_per_customer.csv"))
        self.assertEqual(unlabeled["billing"]["currencies"], ["UNKNOWN"])
        self.assertTrue(any("--currency" in note for note in unlabeled["notes"]))


class StripeSigmaTests(unittest.TestCase):
    def test_minor_units_and_events(self):
        result = im.analyze(fx("stripe_sigma_mrr_events.csv"))
        self.assertEqual(result["format"]["amount_unit"], "minor")
        self.assertEqual(result["rows"]["skipped"]["excluded_by_rule"],
                         {"trial lifecycle marker (no MRR change)": 1})
        billing = result["billing"]
        self.assertEqual(billing["by_currency"]["JPY"]["current"]["mrr"], 5000.0)
        usd = billing["by_currency"]["USD"]
        self.assertEqual(usd["current"]["mrr"], 128.0)
        months = by_month(usd)
        self.assertEqual(months["2026-01"]["new_mrr"], 148.0)
        self.assertEqual(months["2026-03"]["expansion_mrr"], 50.0)
        self.assertEqual(months["2026-04"]["churned_mrr"], 99.0)
        self.assertEqual(billing["primary_currency"], "USD")


class PaddleAndChargebeeTests(unittest.TestCase):
    def test_paddle_report(self):
        result = im.analyze(fx("paddle_subscriptions_report.csv"))
        self.assertEqual(result["format"]["confidence"], "high")
        billing = result["billing"]
        self.assertEqual(billing["as_of"], "2026-09")
        usd = billing["by_currency"]["USD"]
        # 29 monthly + 300 yearly (25) + 90 quarterly (30) + 29 converted trial
        self.assertEqual(usd["current"]["mrr"], 113.0)
        self.assertEqual(usd["churn_by_type"]["voluntary"]["subscriptions"], 1)
        self.assertEqual(usd["churn_by_type"]["involuntary"]["subscriptions"], 1)
        self.assertEqual(usd["trials"]["trial_to_paid_rate"], 1.0)
        self.assertEqual(usd["status_counts"], {"active": 4, "canceled": 2, "trialing": 1, "paused": 1})
        self.assertEqual(by_month(usd)["2026-06"]["churned_mrr"], 29.0)
        self.assertEqual({row["plan"] for row in usd["plan_mix"]}, {"Starter", "Team"})
        self.assertTrue(any("paused or unpaid" in note for note in result["notes"]))
        eur = billing["by_currency"]["EUR"]
        self.assertEqual((eur["current"]["mrr"], eur["past_due_subscriptions"]), (25.0, 1))
        self.assertNotIn("@example.com", json.dumps(result))

    def test_chargebee_import_friendly(self):
        result = im.analyze(fx("chargebee_subscriptions_import_friendly.csv"))
        fmt = result["format"]
        self.assertEqual(fmt["amount_unit"], "minor")
        self.assertEqual(sorted(fmt["pii_columns_ignored"]), ["customer[email]", "customer[first_name]"])
        billing = result["billing"]
        usd = billing["by_currency"]["USD"]
        self.assertEqual(usd["current"]["mrr"], 158.0)     # 29 + 2 x 600 / 12 + 29 (non_renewing)
        self.assertEqual(usd["churn_by_type"]["involuntary"], {"subscriptions": 1, "mrr": 29.0})
        self.assertEqual(billing["by_currency"]["JPY"]["current"]["mrr"], 3000.0)
        self.assertEqual(billing["primary_currency"], "USD")
        text = json.dumps(result)
        self.assertNotIn("Ana", text)
        self.assertNotIn("cust_1", text)


class GenericBillingTests(TempDir):
    def test_semicolon_decimal_comma_and_day_first_dates(self):
        result = im.analyze(fx("generic_subscriptions_semicolon.csv"))
        eur = result["billing"]["by_currency"]["EUR"]
        self.assertEqual(result["billing"]["as_of"], "2026-04")
        self.assertEqual(eur["current"]["mrr"], 68.9)
        self.assertEqual(by_month(eur)["2026-04"]["churned_mrr"], 49.0)
        self.assertEqual(eur["churn_by_type"]["voluntary"]["subscriptions"], 1)

    def test_movements_with_positive_churn_and_unit_override(self):
        result = im.analyze(fx("generic_movements.csv"))
        usd = result["billing"]["by_currency"]["USD"]
        self.assertEqual(usd["current"]["mrr"], 1250.0)
        self.assertEqual(by_month(usd)["2026-03"]["churned_mrr"], 500.0)
        self.assertTrue(any("--amount-unit minor" in note for note in result["notes"]))
        cents = im.analyze(fx("generic_movements.csv"), amount_unit="minor")
        self.assertEqual(cents["billing"]["by_currency"]["USD"]["current"]["mrr"], 12.5)
        self.assertEqual(cents["format"]["amount_unit_basis"], "set by --amount-unit")

    def test_amount_and_interval(self):
        path = self.write("subs.csv", "customer,amount,interval,start_date,status\n"
                                      "a,120,year,2026-01-05,active\nb,30,quarter,2026-02-01,active\n"
                                      "c,10,week,2026-03-01,active\n")
        usd = im.analyze(path, currency="usd")["billing"]["by_currency"]["USD"]
        self.assertAlmostEqual(usd["current"]["mrr"], round(10 + 10 + 10 * 30.4375 / 7, 2), places=2)

    def test_only_trials_is_nothing_to_import(self):
        path = self.write("trials.csv", "customer_id,mrr,start_date,status\na,0,2026-01-01,trialing\n"
                                        "b,,2026-01-02,trialing\n")
        with self.assertRaises(im.NothingToImport) as ctx:
            im.analyze(path)
        self.assertEqual(ctx.exception.details["status_counts"], {"trialing": 2})

    def test_mostly_unreadable_rows_make_the_cli_partial(self):
        rows = ["customer,amount,interval,start_date"] + ["c%d,10,fortnightly,2026-01-01" % i for i in range(3)]
        rows += ["d%d,10,month,2026-01-01" % i for i in range(7)]
        path = self.write("bad.csv", "\n".join(rows) + "\n")
        code, out, _err = run_cli(path, "--json")
        self.assertEqual(code, 4)
        payload = json.loads(out)
        self.assertEqual(payload["status"], "partial")
        self.assertEqual(payload["rows"]["skipped"]["unreadable"], {"billing interval missing or unknown": 3})


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------


class FunnelTests(unittest.TestCase):
    def test_ga4_funnel_with_breakdown(self):
        result = im.analyze(fx("ga4_funnel_exploration.csv"))
        self.assertEqual(result["format"]["vendor_guess"], "GA4 funnel exploration")
        segments = {s["segment"]: s for s in result["funnel"]["segments"]}
        desktop = segments["desktop"]
        self.assertEqual([step["name"] for step in desktop["steps"]],
                         ["Visit pricing", "Start signup", "Complete signup", "Create project"])
        self.assertEqual([step["conversion_from_previous"] for step in desktop["steps"]], [1.0, 0.45, 0.5, 0.4])
        self.assertEqual(desktop["overall_conversion"], 0.09)
        self.assertEqual(desktop["biggest_drop"], {"from_step": 3, "to_step": 4, "drop_off_rate": 0.6})
        self.assertEqual(segments["mobile"]["biggest_drop"]["from_step"], 1)
        self.assertEqual(segments["mobile"]["overall_conversion"], 0.06)

    def test_step_table_with_time_to_convert(self):
        funnel = im.analyze(fx("funnel_steps_time.csv"))["funnel"]
        steps = funnel["segments"][0]["steps"]
        self.assertEqual(steps[1]["name"], "Created workspace")
        self.assertEqual([s["time_to_convert_seconds"] for s in steps], [None, 270.0, 93600.0, 518400.0])
        self.assertEqual(funnel["segments"][0]["overall_conversion"], round(94 / 1200.0, 4))

    def test_wide_funnel(self):
        funnel = im.analyze(fx("funnel_wide_segments.csv"))["funnel"]
        segments = {s["segment"]: s for s in funnel["segments"]}
        self.assertEqual(sorted(segments), ["Organic Search", "Paid Social", "all"])
        self.assertEqual(segments["all"]["overall_conversion"], 0.1)
        self.assertEqual(segments["Paid Social"]["steps"][2]["count"], 100)
        self.assertEqual(segments["Organic Search"]["steps"][0]["name"], "Viewed landing page")


class RetentionTests(TempDir):
    def test_percent_grid_by_day(self):
        retention = im.analyze(fx("retention_day_percent.csv"))["retention"]
        self.assertEqual((retention["period_unit"], retention["value_type"]), ("day", "percent"))
        average = {row["period"]: row for row in retention["average"]}
        self.assertEqual(average[1]["rate"], 0.418)
        self.assertEqual(average[7]["rate"], round(111 / 450.0, 4))
        self.assertEqual((average[30]["rate"], average[30]["cohorts"]), (0.15, 1))
        self.assertEqual(len(retention["cohorts"][3]["rates"]), 2)        # newest cohort is short

    def test_count_grid_by_week(self):
        result = im.analyze(fx("retention_week_counts.csv"))
        retention = result["retention"]
        self.assertEqual(result["rows"]["skipped"]["excluded_by_rule"], {"average or total row": 1})
        self.assertEqual((retention["period_unit"], retention["value_type"]), ("week", "count"))
        average = {row["period"]: row["rate"] for row in retention["average"]}
        self.assertEqual(average[1], round(430 / 950.0, 4))
        self.assertEqual(average[2], 0.35)
        self.assertEqual(retention["cohorts"][0]["rates"], [1.0, 0.45, 0.35, 0.3])

    def test_chartmogul_revenue_cohorts_above_100_percent(self):
        result = im.analyze(fx("chartmogul_cohorts.csv"))
        self.assertEqual(result["format"]["source"], "chartmogul_cohorts")
        retention = result["retention"]
        self.assertEqual((retention["value_type"], retention["period_unit"]), ("percent", "month"))
        self.assertEqual(retention["cohorts"][0]["rates"], [1.0, 1.025, 1.04, 1.01])
        average = {row["period"]: row["rate"] for row in retention["average"]}
        self.assertEqual(average[1], round(30410 / 30000.0, 4))

    def test_ambiguous_values_need_a_flag(self):
        path = self.write("grid.csv", "cohort,size,0,1,2\nA,50,40,20,10\nB,60,45,30,\n")
        with self.assertRaisesRegex(im.ImportFormatError, "--values"):
            im.analyze(path)
        forced = im.analyze(path, values="count")["retention"]
        self.assertEqual(forced["cohorts"][0]["rates"], [0.8, 0.4, 0.2])


class SearchConsoleTests(unittest.TestCase):
    def test_queries_totals_and_order(self):
        search = im.analyze(fx("gsc_queries.csv"))["search"]
        self.assertEqual(search["totals"], {"clicks": 245.0, "impressions": 8000.0, "ctr": 0.0306,
                                            "position_impression_weighted": 8.54})
        self.assertEqual([row["key"] for row in search["rows"]],
                         ["project management software", "free kanban board", "best task app for teams",
                          "gantt chart template"])
        self.assertEqual(search["rows"][0]["ctr"], 0.03)
        top = im.analyze(fx("gsc_queries.csv"), top=2)["search"]
        self.assertEqual((top["rows_shown"], len(top["rows"]), top["row_count"]), (2, 2, 4))


class EventLogTests(TempDir):
    """posthog_events.csv: 5 users, 18 events, 2026-08-03 to 2026-08-31 (expected values by hand)."""

    STEPS = ["signed_up", "created_project", "invited_teammate"]

    def test_parse_datetime(self):
        self.assertEqual(im.parse_datetime("2026-08-11T13:00:00+02:00"), datetime(2026, 8, 11, 11, 0))
        self.assertEqual(im.parse_datetime("2026-08-11 10:00:00.250000"), datetime(2026, 8, 11, 10, 0, 0, 250000))
        self.assertEqual(im.parse_datetime("1786442400"), datetime(2026, 8, 11, 10, 0))        # Mixpanel seconds
        self.assertEqual(im.parse_datetime("1786442400000000"), datetime(2026, 8, 11, 10, 0))  # GA4 microseconds
        self.assertEqual(im.parse_datetime("2026-08-11"), datetime(2026, 8, 11))
        self.assertIsNone(im.parse_datetime("soon"))

    def test_overview_and_privacy(self):
        result = im.analyze(fx("posthog_events.csv"))
        self.assertEqual(result["format"]["source"], "event_log")
        self.assertEqual(result["format"]["pii_columns_ignored"], ["person.properties.email"])
        events = result["events"]
        self.assertEqual((events["event_count"], events["user_count"]), (18, 5))
        self.assertEqual(events["top_events"][0], {"event": "$pageview", "count": 7, "users": 5})
        text = json.dumps(result)
        for secret in ("@example.com", "u-00"):
            self.assertNotIn(secret, text)
        self.assertNotIn("funnel", result)
        self.assertIn("--step", " ".join(result["notes"]))

    def test_weekly_retention_by_first_event(self):
        retention = im.analyze(fx("posthog_events.csv"))["retention"]
        self.assertEqual(retention["period_unit"], "week")
        cohorts = {c["label"]: c for c in retention["cohorts"]}
        self.assertEqual(cohorts["2026-08-03"]["size"], 3)
        self.assertEqual(cohorts["2026-08-03"]["rates"], [1.0, round(2 / 3.0, 4), round(1 / 3.0, 4)])
        self.assertEqual(cohorts["2026-08-10"]["rates"], [1.0, 0.5])         # week 2 not complete yet
        average = {row["period"]: row["rate"] for row in retention["average"]}
        self.assertEqual(average, {0: 1.0, 1: 0.6, 2: round(1 / 3.0, 4)})

    def test_ordered_funnel_and_time_to_activation(self):
        funnel = im.analyze(fx("posthog_events.csv"), steps=self.STEPS)["funnel"]
        steps = funnel["segments"][0]["steps"]
        self.assertEqual([s["count"] for s in steps], [4, 4, 3])
        self.assertEqual(funnel["segments"][0]["overall_conversion"], 0.75)
        self.assertEqual([s["time_to_convert_seconds"] for s in steps], [None, 7200.0, 172800.0])
        self.assertEqual(funnel["median_time_to_last_step_seconds"], 174600.0)
        short = im.analyze(fx("posthog_events.csv"), steps=self.STEPS, window_days=7)["funnel"]
        self.assertEqual([s["count"] for s in short["segments"][0]["steps"]], [4, 3, 2])

    def test_cli_and_bad_steps(self):
        code, out, _err = run_cli(fx("posthog_events.csv"), "--step", "signed_up", "--step", "created_project",
                                  "--json")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["funnel"]["segments"][0]["steps"][1]["count"], 4)
        code, out, _err = run_cli(fx("posthog_events.csv"), "--step", "signed_up", "--step", "paid", "--json")
        self.assertEqual(code, 2)
        payload = json.loads(out)
        self.assertIn("'paid' is not an event", payload["errors"][0])
        self.assertIn("signed_up", payload["most_frequent_events"])
        with self.assertRaises(im.ImportOptionError):
            im.analyze(fx("posthog_events.csv"), steps=["signed_up"])

    def test_movements_and_billing_events_are_not_event_logs(self):
        for name in ("generic_movements.csv", "stripe_sigma_mrr_events.csv"):
            self.assertNotEqual(im.analyze(fx(name))["format"]["source"], "event_log", name)


class PersonLevelDataTests(TempDir):
    """Lists of people must never come out as funnels, cohorts or labels."""

    def test_customer_list_is_not_a_funnel(self):
        rows = "".join("Person %d,p%d@mail.test,US,%d\n" % (i, i, 100 + i) for i in range(40))
        path = self.write("customers.csv", "Name,Email,Country,Total\n" + rows)
        with self.assertRaises(im.ImportFormatError):
            im.analyze(path)
        # Without the email column, 40 different "steps" is still not a funnel.
        no_email = self.write("names.csv", "Name,Total\n" + "".join(
            "Person %d,%d\n" % (i, 100 + i) for i in range(40)))
        with self.assertRaises(im.ImportFormatError):
            im.analyze(no_email, kind="funnel")

    def test_per_user_retention_and_wide_funnel_tables_are_refused(self):
        retention = self.write("users.csv", "user,day_0,day_1\nann,1,0\nbob,1,1\n")
        with self.assertRaises(im.ImportFormatError):
            im.analyze(retention, kind="retention")
        wide = self.write("wide.csv", "Email,Step 1,Step 2\na@mail.test,1,1\nb@mail.test,1,0\n")
        with self.assertRaises(im.ImportFormatError):
            im.analyze(wide, kind="funnel")

    def test_emails_in_segments_and_preamble_are_scrubbed(self):
        funnel = self.write("by_email.csv", "Step,Breakdown,Count\n1. Signed up,ann@mail.test,1\n"
                            "2. Activated,ann@mail.test,1\n1. Signed up,bob@mail.test,1\n"
                            "2. Activated,bob@mail.test,0\n")
        result = im.analyze(funnel)
        text = json.dumps(result)
        self.assertNotIn("@mail.test", text)
        segments = [s["segment"] for s in result["funnel"]["segments"]]
        self.assertEqual(len(set(segments)), 2)                            # still two segments
        self.assertTrue(all(s.startswith("[email ") for s in segments))
        subs = self.write("subs.csv", "Exported by ops@acme.test\ncustomer_id,mrr,start_date,status\n"
                          "c1,49,2026-01-05,active\nc2,99,2026-02-05,active\n")
        self.assertNotIn("ops@acme.test", json.dumps(im.analyze(subs)))

    def test_scrub(self):
        self.assertEqual(im.scrub("no address here"), "no address here")
        tagged = im.scrub({"a@b.co": ["x c.d@e.org y"]})
        key, = tagged
        self.assertTrue(key.startswith("[email ") and "@" not in json.dumps(tagged))
        self.assertEqual(im.scrub("A@B.CO"), im.scrub("a@b.co"))

    def test_unknown_format_error_scrubs_headers(self):
        path = self.write("shifted.csv", "customer_id,status,mrr,start_date,\nann@corp.test,active,49,"
                          "2026-01-01,x\nbob@corp.test,active,49,2026-01-01,x\ncy@corp.test,active,9,"
                          "2026-01-01,y\n")
        code, out, _err = run_cli(path, "--json")
        self.assertEqual(code, 2)
        self.assertNotIn("@corp.test", out)


class RetentionShapeTests(TempDir):
    def test_churn_cohort_table_is_refused(self):
        path = self.write("churn.csv", "Cohort,Cohort value,0,1,2,Average\nJan 2026,40,0.0%,5.0%,10.0%,\n"
                          "Feb 2026,30,0.0%,6.7%,,\n")
        with self.assertRaisesRegex(im.ImportFormatError, "churn cohort"):
            im.analyze(path)

    def test_date_column_is_the_label_next_to_a_segment(self):
        header = '"Segment","Date","Users","Day 0","Day 1"\n'
        single = self.write("one.csv", header + '"All Users","Sep 1, 2026","1,200","100%","35%"\n'
                            '"All Users","Sep 8, 2026","1,000","100%","32%"\n')
        retention = im.analyze(single)["retention"]
        self.assertEqual([c["start"] for c in retention["cohorts"]], ["2026-09-01", "2026-09-08"])
        self.assertEqual(retention["period_unit"], "day")
        mixed = self.write("mixed.csv", header + '"All Users","Sep 1, 2026","1000","100%","35%"\n'
                           '"Country = US","Sep 1, 2026","600","100%","40%"\n')
        result = im.analyze(mixed)
        self.assertEqual([c["label"] for c in result["retention"]["cohorts"]], ["Sep 1, 2026"])
        self.assertIn("only the 'All Users' rows", " ".join(result["notes"]))
        two = self.write("two.csv", header + '"Country = US","Sep 1, 2026","600","100%","40%"\n'
                         '"Country = DE","Sep 1, 2026","400","100%","30%"\n')
        cohorts = im.analyze(two)["retention"]["cohorts"]
        self.assertEqual([c["label"] for c in cohorts], ["Country = US / Sep 1, 2026", "Country = DE / Sep 1, 2026"])
        self.assertEqual(cohorts[0]["start"], "2026-09-01")


class BillingCaveatTests(TempDir):
    def test_active_only_snapshot_cannot_show_churn(self):
        path = self.write("active.csv", "customer_id,mrr,start_date,status\nc1,49,2025-01-05,active\n"
                          "c2,99,2025-02-05,active\n")
        result = im.analyze(path, as_of="2026-02")
        self.assertFalse(result["billing"]["churn_observable"])
        self.assertIn("no canceled or ended subscriptions", " ".join(result["notes"]))
        self.assertTrue(im.analyze(fx("stripe_subscriptions.csv"))["billing"]["churn_observable"])

    def test_latest_month_may_be_partial(self):
        default = " ".join(im.analyze(fx("chartmogul_all_mrr_movements.csv"))["notes"])
        self.assertIn("that month is incomplete", default)
        pinned = " ".join(im.analyze(fx("chartmogul_all_mrr_movements.csv"), as_of="2026-01")["notes"])
        self.assertNotIn("that month is incomplete", pinned)

    def test_as_of_outside_the_data(self):
        with self.assertRaisesRegex(im.ImportOptionError, "before the first month"):
            im.analyze(fx("stripe_subscriptions.csv"), as_of="2020-01")
        with self.assertRaisesRegex(im.ImportOptionError, "in the future"):
            im.check_as_of("2026-11", today=date(2026, 10, 24))
        im.check_as_of("2026-10", today=date(2026, 10, 24))
        code, out, _err = run_cli(fx("stripe_subscriptions.csv"), "--as-of", "2020-01", "--json")
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(out)["notes"], [])                   # no format hints for a bad option

    def test_plan_and_interval_mix_add_up_to_mrr_for_past_months(self):
        for as_of in (None, "2026-03", "2025-12"):
            usd = im.analyze(fx("stripe_subscriptions.csv"), as_of=as_of)["billing"]["by_currency"]["USD"]
            mrr = usd["current"]["mrr"]
            self.assertAlmostEqual(sum(row["mrr"] for row in usd["plan_mix"]), mrr, places=2, msg=as_of)
            self.assertAlmostEqual(sum(row["mrr"] for row in usd["interval_mix"]), mrr, places=2, msg=as_of)

    def test_decimals_in_a_field_documented_in_cents_are_dollars(self):
        path = self.write("cb.csv", "subscription[id],subscription[customer_id],subscription[plan_unit_price],"
                          "subscription[currency_code],subscription[billing_period],"
                          "subscription[billing_period_unit],subscription[status],subscription[started_at]\n"
                          "s1,c1,29.00,USD,1,month,active,2026-01-01\ns2,c2,49.00,USD,1,month,active,2026-02-01\n")
        result = im.analyze(path, as_of="2026-02")
        self.assertEqual(result["format"]["source"], "chargebee_subscriptions")
        self.assertEqual(result["format"]["amount_unit"], "major")
        self.assertEqual(result["billing"]["by_currency"]["USD"]["current"]["mrr"], 78.0)
        self.assertIn("documents these amounts in cents", " ".join(result["notes"]))
        forced = im.analyze(path, as_of="2026-02", amount_unit="minor")
        self.assertEqual(forced["billing"]["by_currency"]["USD"]["current"]["mrr"], 0.78)

    def test_customer_month_currency_from_signs(self):
        path = self.write("bm.csv", "Customer,Jan 2026,Feb 2026\nc1,$100.00,$120.00\nc2,$50.00,$0.00\n")
        result = im.analyze(path)
        self.assertEqual(result["billing"]["currencies"], ["USD"])
        self.assertNotIn("ChartMogul", " ".join(result["notes"]))
        plain = self.write("plain.csv", "Customer,Jan 2026,Feb 2026\nc1,100.00,120.00\nc2,50.00,0.00\n")
        notes = " ".join(im.analyze(plain)["notes"])
        self.assertIn("no currency column or currency sign", notes)
        self.assertNotIn("ChartMogul", notes)


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------


class CliTests(unittest.TestCase):
    def test_ok_unknown_nothing_and_list(self):
        code, out, _err = run_cli(fx("stripe_subscriptions.csv"), "--json")
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["billing"]["by_currency"]["USD"]["current"]["mrr"], 305.0)
        self.assertTrue(payload["notes"])
        self.assertNotIn("@example.com", out)

        code, out, _err = run_cli(fx("unknown_format.csv"), "--json")
        self.assertEqual(code, 2)
        payload = json.loads(out)
        self.assertEqual(payload["status"], "usage_error")
        self.assertEqual(payload["headers"], ["foo", "bar", "baz"])

        code, out, _err = run_cli(fx("stripe_subscriptions_headers_only.csv"), "--json")
        self.assertEqual(code, 5)
        self.assertEqual(json.loads(out)["status"], "nothing_to_analyze")

        code, out, _err = run_cli("--list-formats", "--json")
        self.assertEqual(code, 0)
        self.assertEqual(len(json.loads(out)["formats"]), len(im.FORMATS))

        code, out, _err = run_cli("--json")
        self.assertEqual(code, 2)
        code, out, _err = run_cli("https://example.com/export", "--json")
        self.assertEqual(code, 2)
        code, out, _err = run_cli(fx("missing.csv"), "--json")
        self.assertEqual(code, 2)
        self.assertIn("File not found", json.loads(out)["errors"][0])

    def test_human_output(self):
        code, out, _err = run_cli(fx("gsc_queries.csv"))
        self.assertEqual(code, 0)
        self.assertIn("Search Console (query): 4 rows", out)

    def test_runs_as_a_file(self):
        script = os.path.join(_paths.SHARED_DIR, "growthkit", "importers.py")
        proc = subprocess.run(
            [sys.executable, script, fx("chartmogul_all_mrr_movements.csv"), "--json"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=FIXTURES, timeout=60,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr.decode("utf-8", "replace"))
        payload = json.loads(proc.stdout.decode("utf-8"))
        self.assertEqual(payload["billing"]["by_currency"]["USD"]["current"]["mrr"], 500.0)


if __name__ == "__main__":
    unittest.main()
