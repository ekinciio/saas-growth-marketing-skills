"""Offline checks for shared/benchmarks/saas-benchmarks.json and its README.

saas-benchmarks.json is the single source for benchmark numbers (synced into
every skill as references/_shared/saas-benchmarks.json). These tests keep
its schema, its derived values and its documentation consistent, so a skill
or script can rely on the documented fields.

Run from the repo root:
    python3 -m unittest discover -s tests -t .
"""

import json
import os
import re
import unittest
from datetime import date

from tests import _paths

BENCH_DIR = os.path.join(_paths.SHARED_DIR, "benchmarks")
JSON_PATH = os.path.join(BENCH_DIR, "saas-benchmarks.json")
README_PATH = os.path.join(BENCH_DIR, "README.md")

UNITS = {"percent", "months", "hours", "ratio", "multiple", "percentage_points", "usd"}
PERIODS = {"annual", "monthly", "quarterly", "cohort", "point_in_time"}
DIRECTIONS = {"higher_is_better", "lower_is_better", "context"}
CONFIDENCE = {"high", "medium", "low"}
STATS = ("p25", "median", "p75", "p90", "mean", "value")
PERCENTILES = ("p25", "median", "p75", "p90")
TOP_LEVEL = ("schema_version", "last_verified", "freshness_rule", "conventions", "sources",
             "rows", "retention_conversions")
REQUIRED_FIELDS = (
    "id", "metric", "metric_label", "definition", "unit", "period", "window", "direction",
    "segment", "p25", "median", "p75", "p90", "mean", "value", "thresholds", "value_note",
    "source_id", "source_name", "source_url", "year", "data_period", "sample_size",
    "sample_note", "verified", "verified_on", "verification_note", "confidence",
)
SEGMENT_KEYS = ("motion", "arr_band", "acv_band", "pricing_model", "ai_native", "extra")
# Metrics the skills grade against. Removing one breaks a skill.
REQUIRED_METRICS = {
    "nrr", "grr", "logo_churn", "cac_payback", "ltv_to_cac", "rule_of_40", "burn_multiple",
    "magic_number", "quick_ratio", "free_to_paid", "trial_to_paid", "activation_rate",
    "time_to_value", "tour_completion", "landing_page_conversion", "form_view_to_completion",
    "form_start_to_completion", "arr_growth",
}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _parse_date(text):
    return date(*(int(part) for part in text.split("-")))


def _load():
    with open(JSON_PATH, encoding="utf-8") as handle:
        text = handle.read()
    return text, json.loads(text)


class BenchmarkSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text, cls.doc = _load()
        cls.rows = cls.doc["rows"]
        cls.by_id = {row["id"]: row for row in cls.rows}

    def test_top_level_keys(self):
        for key in TOP_LEVEL:
            self.assertIn(key, self.doc)
        self.assertRegex(self.doc["schema_version"], r"^\d+\.\d+$")
        self.assertRegex(self.doc["last_verified"], DATE_RE)
        self.assertIsInstance(self.doc["sources"], dict)
        self.assertGreater(len(self.rows), 0)

    def test_rows_have_required_fields_and_valid_enums(self):
        ids = set()
        for row in self.rows:
            rid = row.get("id")
            for field in REQUIRED_FIELDS:
                self.assertIn(field, row, "%s is missing %s" % (rid, field))
            self.assertNotIn(rid, ids, "duplicate id " + str(rid))
            ids.add(rid)
            self.assertIn(row["unit"], UNITS, rid)
            self.assertIn(row["period"], PERIODS, rid)
            self.assertIn(row["direction"], DIRECTIONS, rid)
            self.assertIn(row["confidence"], CONFIDENCE, rid)
            self.assertIsInstance(row["verified"], bool, rid)
            self.assertIsInstance(row["year"], int, rid)
            self.assertTrue(row["source_url"].startswith("https://"), rid)
            self.assertIn(row["source_id"], self.doc["sources"], rid)

    def test_ids_follow_the_documented_pattern(self):
        # <metric>.<source+year>[.<segment>]: the README pattern, where a few
        # all-segment rows (for example passkey_signin_share.fido2026) omit
        # the segment part.
        for row in self.rows:
            self.assertRegex(row["id"], r"^[a-z0-9_]+\.[a-z0-9_]+(\.[a-z0-9_.]+)?$", row["id"])
            self.assertTrue(row["id"].startswith(row["metric"] + "."), row["id"])

    def test_dates(self):
        last = _parse_date(self.doc["last_verified"])
        for row in self.rows:
            self.assertRegex(row["verified_on"], DATE_RE, row["id"])
            self.assertLessEqual(_parse_date(row["verified_on"]), last,
                                 "%s verified after last_verified" % row["id"])
            self.assertLessEqual(row["year"], last.year, row["id"])

    def test_segments_are_complete(self):
        for row in self.rows:
            segment = row["segment"]
            for key in SEGMENT_KEYS:
                self.assertIn(key, segment, row["id"])
            self.assertIn(segment["ai_native"], (True, False, "mixed", None), row["id"])
            self.assertIsInstance(segment["extra"], dict, row["id"])

    def test_every_row_has_a_number(self):
        for row in self.rows:
            has_number = any(row[stat] is not None for stat in STATS) or bool(row["thresholds"])
            self.assertTrue(has_number, "row has no value: " + row["id"])
            for stat in STATS:
                if row[stat] is not None:
                    self.assertIsInstance(row[stat], (int, float), "%s.%s" % (row["id"], stat))
                    self.assertNotIsInstance(row[stat], bool, "%s.%s" % (row["id"], stat))

    def test_percentiles_are_ordered(self):
        for row in self.rows:
            values = [row[stat] for stat in PERCENTILES if row[stat] is not None]
            self.assertEqual(values, sorted(values), row["id"])

    def test_no_row_mixes_mean_and_value(self):
        # value means "statistic not named"; a row with a mean as well would be ambiguous.
        for row in self.rows:
            self.assertFalse(row["mean"] is not None and row["value"] is not None, row["id"])

    def test_unverified_rows_are_low_confidence(self):
        for row in self.rows:
            if not row["verified"]:
                self.assertEqual(row["confidence"], "low", row["id"])
                self.assertTrue(row["verification_note"].startswith("NOT verified"), row["id"])

    def test_thresholds_are_well_formed(self):
        for row in self.rows:
            for band in row["thresholds"] or []:
                self.assertIn("label", band, row["id"])
                self.assertTrue("min" in band or "max" in band, row["id"])
                if "min" in band and "max" in band and band["min"] is not None and band["max"] is not None:
                    self.assertLess(band["min"], band["max"], row["id"])

    def test_sources_are_complete(self):
        for source_id, source in self.doc["sources"].items():
            for key in ("name", "url", "year"):
                self.assertIn(key, source, source_id)
            self.assertTrue(source["url"].startswith("https://"), source_id)

    def test_required_metrics_are_covered(self):
        metrics = {row["metric"] for row in self.rows}
        self.assertTrue(REQUIRED_METRICS <= metrics, sorted(REQUIRED_METRICS - metrics))
        motions = {row["segment"]["motion"] for row in self.rows if row["metric"] == "trial_to_paid"}
        self.assertTrue({"trial_opt_in", "trial_opt_out", "freemium"} <= motions, motions)

    def test_one_row_per_line(self):
        # The README tells readers to grep rows; that only works with one row per line.
        lines = [line for line in self.text.splitlines() if line.lstrip().startswith('{"id": ')]
        self.assertEqual(len(lines), len(self.rows))

    def test_no_em_or_en_dashes(self):
        for path in (JSON_PATH, README_PATH):
            with open(path, encoding="utf-8") as handle:
                text = handle.read()
            self.assertNotIn(chr(0x2014), text, path)
            self.assertNotIn(chr(0x2013), text, path)


class DerivedValueTests(unittest.TestCase):
    """monthly/annual equivalents must match the documented formulas."""

    @classmethod
    def setUpClass(cls):
        _text, cls.doc = _load()
        cls.rows = cls.doc["rows"]

    def test_monthly_equivalents_of_annual_retention(self):
        checked = 0
        for row in self.rows:
            if row["metric"] not in ("nrr", "grr") or row["period"] != "annual" or row["unit"] != "percent":
                continue
            equivalent = row.get("monthly_equivalent")
            self.assertIsInstance(equivalent, dict, row["id"])
            self.assertIn("formula", equivalent, row["id"])
            for stat in STATS:
                if row[stat] is None or stat not in equivalent:
                    continue
                expected = ((row[stat] / 100.0) ** (1.0 / 12.0)) * 100.0
                self.assertAlmostEqual(equivalent[stat], expected, delta=0.006,
                                       msg="%s %s" % (row["id"], stat))
                checked += 1
        self.assertGreater(checked, 0)

    def test_annual_equivalents_of_monthly_logo_churn(self):
        checked = 0
        for row in self.rows:
            equivalent = row.get("annual_equivalent")
            if row["metric"] != "logo_churn" or not isinstance(equivalent, dict):
                continue
            for stat in STATS:
                if row[stat] is None or stat not in equivalent:
                    continue
                expected = (1 - (1 - row[stat] / 100.0) ** 12) * 100
                self.assertAlmostEqual(equivalent[stat], expected, delta=0.06,
                                       msg="%s %s" % (row["id"], stat))
                checked += 1
        self.assertGreater(checked, 0)

    def test_retention_conversion_tables(self):
        conversions = self.doc["retention_conversions"]
        for item in conversions["grr"]:
            monthly = ((item["annual_grr"] / 100.0) ** (1.0 / 12.0)) * 100.0
            self.assertAlmostEqual(item["monthly_grr"], monthly, delta=0.006, msg=item)
            self.assertAlmostEqual(item["monthly_gross_revenue_churn"], 100.0 - item["monthly_grr"],
                                   delta=0.011, msg=item)
        for item in conversions["nrr"]:
            monthly = ((item["annual_nrr"] / 100.0) ** (1.0 / 12.0)) * 100.0
            self.assertAlmostEqual(item["monthly_nrr"], monthly, delta=0.006, msg=item)
            self.assertAlmostEqual(item["monthly_net_revenue_churn"], 100.0 - item["monthly_nrr"],
                                   delta=0.011, msg=item)


class ReadmeConsistencyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _text, cls.doc = _load()
        cls.by_id = {row["id"]: row for row in cls.doc["rows"]}
        with open(README_PATH, encoding="utf-8") as handle:
            cls.readme = handle.read()

    def test_row_count_matches(self):
        self.assertIn("## Coverage (%d rows)" % len(self.doc["rows"]), self.readme)

    def test_cited_row_ids_exist(self):
        ids = set(re.findall(r"`([a-z_0-9]+\.[a-z_0-9]+\.[a-z_0-9.]+)`", self.readme))
        ids = {
            rid for rid in ids
            if not rid.startswith("retention_conversions")
            and not rid.endswith((".py", ".md", ".json"))
        }
        for rid in sorted(ids):
            self.assertIn(rid, self.by_id, "README cites unknown row id " + rid)

    def test_segment_values_are_documented(self):
        for row in self.doc["rows"]:
            segment = row["segment"]
            for key in ("motion", "arr_band", "acv_band", "pricing_model"):
                self.assertIn("`%s`" % segment[key], self.readme, "%s %s=%s" % (row["id"], key, segment[key]))
            for key in segment["extra"]:
                self.assertIn("`%s`" % key, self.readme, "%s extra.%s" % (row["id"], key))

    def test_markdown_tables_have_even_columns(self):
        block = []
        for line in self.readme.splitlines() + [""]:
            if line.startswith("|"):
                block.append(line)
                continue
            if block:
                widths = {len(row.strip().strip("|").split("|")) for row in block
                          if "\\|" not in row}
                self.assertLessEqual(len(widths), 1, block[0][:80])
                block = []


if __name__ == "__main__":
    unittest.main()
