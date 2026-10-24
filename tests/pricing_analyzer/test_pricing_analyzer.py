"""Tests for skills/pricing-analyzer/scripts/pricing_analyzer.py.

Backlog item B18 (crash fixes and input validation):
  - SKILL.md's own demo JSON used {"name", "prices"} competitors and crashed
    with KeyError 'tiers'.
  - A "Contact sales" / custom-priced tier (Notion, Linear, Asana all have
    one) crashed the sort with TypeError.
  - plg_motion "false" (a string) was treated as True.
  - Empty tiers, missing features, bad prices: raw tracebacks.
  - The fallback advice suggested adding competitor data even when it was
    already supplied.

All tests are offline and use only the standard library.
Run with: python3 -m unittest discover -s tests -t .
"""

import importlib.util
import json
import os
import re
import subprocess
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SKILL_DIR = os.path.join(REPO_ROOT, "skills", "pricing-analyzer")
SCRIPT = os.path.join(SKILL_DIR, "scripts", "pricing_analyzer.py")
SKILL_MD = os.path.join(SKILL_DIR, "SKILL.md")
FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _load_module():
    """Import pricing_analyzer.py by file path (skills/ is not a package)."""
    name = "pricing_analyzer_under_test"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


pa = _load_module()


def _fixture(name):
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as fh:
        return json.load(fh)


def _run_cli(args=None, stdin_text=None):
    """Run the script as a user would; returns the CompletedProcess."""
    return subprocess.run(
        [sys.executable, SCRIPT] + list(args or []),
        input=stdin_text,
        capture_output=True,
        text=True,
        timeout=60,
    )


def _features(n, prefix="f"):
    return [f"{prefix}{i}" for i in range(n)]


class SkillMdDemoTests(unittest.TestCase):
    """The demo flow in SKILL.md must run end to end."""

    def _skill_md_demo_json(self):
        with open(SKILL_MD, encoding="utf-8") as fh:
            text = fh.read()
        match = re.search(r"### Demo Mode.*?```json\n(.*?)```", text, re.S)
        self.assertIsNotNone(match, "Demo Mode JSON block not found in SKILL.md")
        return match.group(1)

    def test_skill_md_demo_block_runs(self):
        # Whatever shape SKILL.md documents today must work.
        proc = _run_cli(["-"], stdin_text=self._skill_md_demo_json())
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)
        self.assertIn("Competitive Positioning:", proc.stdout)

    def test_name_prices_shorthand_fixture(self):
        # Frozen copy of the SKILL.md demo as it was when B18 was filed.
        proc = _run_cli([os.path.join(FIXTURES, "skillmd_demo.json")])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("vs Competitor A:", proc.stdout)
        self.assertIn("vs Competitor B:", proc.stdout)

    def test_shorthand_matches_canonical_shape(self):
        data = _fixture("skillmd_demo.json")
        canonical = [
            {
                "company": comp["name"],
                "tiers": [
                    {"name": f"Tier {i + 1}", "price": p, "features": []}
                    for i, p in enumerate(comp["prices"])
                ],
            }
            for comp in data["competitors"]
        ]
        short = pa.analyze_pricing({"tiers": data["tiers"]}, data["competitors"])
        full = pa.analyze_pricing({"tiers": data["tiers"]}, canonical)
        self.assertEqual(short["competitive_positioning"], full["competitive_positioning"])
        # (0 + 19 + 79) / 3 and (15 + 49 + 149) / 3
        avgs = [c["avg_price"] for c in short["competitive_positioning"]["competitors"]]
        self.assertEqual(avgs, [32.67, 71.0])


class ContactSalesTierTests(unittest.TestCase):

    def test_notion_fixture_runs(self):
        proc = _run_cli([os.path.join(FIXTURES, "notion_contact_sales.json")])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("Enterprise: custom price (Contact sales)", proc.stdout)
        self.assertIn("vs Linear:", proc.stdout)
        self.assertIn("vs Asana:", proc.stdout)

    def test_custom_tier_sorts_last_and_is_counted(self):
        data = _fixture("notion_contact_sales.json")
        result = pa.analyze_pricing({"tiers": data["tiers"]}, data["competitors"])
        ta = result["tier_analysis"]
        self.assertEqual(ta["tier_count"], 4)
        self.assertEqual(ta["custom_tier_count"], 1)
        self.assertEqual([t["name"] for t in ta["tiers"]],
                         ["Free", "Plus", "Business", "Enterprise"])
        self.assertTrue(ta["tiers"][-1]["custom_price"])
        self.assertIsNone(ta["tiers"][-1]["price"])
        self.assertEqual(ta["price_range"], {"min": 0, "max": 20})
        self.assertIn("Enterprise is custom-priced", result["positioning_summary"])

    def test_custom_tier_excluded_from_price_math(self):
        data = _fixture("notion_contact_sales.json")
        result = pa.analyze_pricing({"tiers": data["tiers"]}, data["competitors"])
        cp = result["competitive_positioning"]
        self.assertEqual(cp["your_avg_price"], 10.0)  # (0 + 10 + 20) / 3
        linear, asana = cp["competitors"]
        self.assertEqual(linear["avg_price"], 8.67)  # (0 + 10 + 16) / 3
        self.assertEqual(asana["avg_price"], 11.99)  # (0 + 10.99 + 24.99) / 3
        self.assertEqual(linear["tier_count"], 4)
        self.assertEqual(linear["custom_tier_count"], 1)
        self.assertEqual(asana["price_range"], {"min": 0, "max": 24.99})
        business = result["tier_analysis"]["tiers"][2]
        self.assertNotIn("price_jump_to_next", business)

    def test_custom_price_spellings(self):
        for raw in (None, "custom", "Custom", "Contact sales", "Contact us",
                    "Let's talk", "Talk to sales", "Get a quote", "On request"):
            with self.subTest(price=raw):
                price, custom = pa._parse_price(raw, "price")
                self.assertIsNone(price)
                self.assertTrue(custom)

    def test_numeric_price_strings(self):
        cases = {"$10": 10, "10.99": 10.99, "1,200": 1200, "Free": 0,
                 "Free for 3 users": 0, "$0": 0, "€8 per seat": 8,
                 "$10/mo billed yearly": 10, " 29 ": 29}
        for raw, expected in cases.items():
            with self.subTest(price=raw):
                self.assertEqual(pa._parse_price(raw, "price"), (expected, False))

    def test_decimal_comma_and_thousands(self):
        # "9,99" used to be read as 9 (the ",99" was dropped silently).
        cases = {"9,99": 9.99, "€19,90/mo": 19.9, "1.200,50": 1200.5,
                 "1,200.50": 1200.5, "1,234,567": 1234567}
        for raw, expected in cases.items():
            with self.subTest(price=raw):
                self.assertEqual(pa._parse_price(raw, "price"), (expected, False))

    def test_unclear_numbers_are_rejected_not_truncated(self):
        # "1.5k" used to be read as 1.5 and "1,2000" as 1200.
        for raw in ("1.5k", "$2K/mo", "1,2000", "10.99.5", "3m"):
            with self.subTest(price=raw):
                with self.assertRaises(ValueError) as ctx:
                    pa._parse_price(raw, "price")
                self.assertIn("not a clear number", str(ctx.exception))
        # A unit word that starts with m is not a magnitude suffix.
        self.assertEqual(pa._parse_price("10 mo", "price"), (10, False))
        self.assertEqual(pa._parse_price("$10 monthly", "price"), (10, False))

    def test_custom_top_tier_removes_anchor_exemption(self):
        # A big jump into the top tier is exempt (anchoring). With a custom
        # tier on top, the last published jump is no longer into the top tier.
        priced_only = [
            {"name": "A", "price": 10, "features": _features(2)},
            {"name": "B", "price": 60, "features": _features(6)},
        ]
        with_custom = priced_only + [{"name": "Ent", "price": "custom"}]

        def gap_issues(tiers):
            result = pa.analyze_pricing({"tiers": tiers}, plg_motion=False)
            return [i for i in result["tier_analysis"]["issues"] if "Large price gap" in i]

        self.assertEqual(gap_issues(priced_only), [])
        self.assertEqual(len(gap_issues(with_custom)), 1)

    def test_all_custom_tiers(self):
        result = pa.analyze_pricing(
            {"tiers": [{"name": "Enterprise", "price": "Contact sales"}]},
            [{"name": "Rival", "prices": [10, 20]}],
        )
        self.assertIsNone(result["competitive_positioning"])
        self.assertEqual(result["tier_analysis"]["price_range"], {"min": None, "max": None})
        self.assertTrue(any("custom-priced" in w for w in result["warnings"]))
        self.assertIn("custom-priced", result["positioning_summary"])


class CoercionTests(unittest.TestCase):

    def test_plg_motion_string_false_is_false(self):
        tiers = [{"name": "Pro", "price": 29, "features": _features(3)}]
        for raw in (False, "false", "False", "no", "0", 0):
            with self.subTest(plg_motion=raw):
                result = pa.analyze_pricing({"tiers": tiers}, plg_motion=raw)
                issues = " ".join(result["tier_analysis"]["issues"])
                self.assertNotIn("No free tier", issues)

    def test_plg_motion_string_true_and_unknown(self):
        tiers = [{"name": "Pro", "price": 29, "features": _features(3)}]
        firm = pa.analyze_pricing({"tiers": tiers}, plg_motion="true")
        self.assertIn("for a PLG/self-serve motion",
                      " ".join(firm["tier_analysis"]["issues"]))
        unknown = pa.analyze_pricing({"tiers": tiers}, plg_motion="unknown")
        self.assertIn("consider whether a free tier fits",
                      " ".join(unknown["tier_analysis"]["issues"]))

    def test_features_default_to_empty_list(self):
        result = pa.analyze_pricing({"tiers": [
            {"name": "Free", "price": 0},
            {"name": "Pro", "price": 10},
            {"name": "Team", "price": 20},
        ]})
        counts = [t["feature_count"] for t in result["tier_analysis"]["tiers"]]
        self.assertEqual(counts, [0, 0, 0])
        # No features means no per-feature price, not a fake "$0/feature".
        ppf = [t["price_per_feature"] for t in result["tier_analysis"]["tiers"]]
        self.assertEqual(ppf, [None, None, None])
        # No feature lists means no "weak upgrade" judgment either.
        issues = " ".join(result["tier_analysis"]["issues"])
        self.assertNotIn("new feature(s)", issues)

    def test_features_string_is_split_not_counted_by_character(self):
        result = pa.analyze_pricing({"tiers": [
            {"name": "Pro", "price": 10, "features": "SSO, audit log; API access"},
        ]})
        self.assertEqual(result["tier_analysis"]["tiers"][0]["feature_count"], 3)

    def test_survey_numeric_strings_match_numbers(self):
        survey = {
            "too_cheap": [10, 15, 20, 25, 30],
            "bargain": [20, 25, 30, 35, 40],
            "expensive": [40, 45, 50, 55, 60],
            "too_expensive": [60, 65, 70, 75, 80],
        }
        as_strings = {k: [f"${v}" for v in vals] for k, vals in survey.items()}
        tiers = {"tiers": [{"name": "Pro", "price": 29}]}
        a = pa.analyze_pricing(tiers, survey_data=survey)["van_westendorp"]
        b = pa.analyze_pricing(tiers, survey_data=as_strings)["van_westendorp"]
        self.assertEqual(a, b)
        self.assertIsNotNone(a["optimal_price_point"])


class CompetitorSkipTests(unittest.TestCase):

    def test_competitor_without_published_price_is_skipped(self):
        result = pa.analyze_pricing(
            {"tiers": [{"name": "Pro", "price": 20}]},
            [
                {"name": "SalesOnly", "prices": ["Contact sales"]},
                {"company": "NoData"},
                {"company": "Real", "tiers": [{"name": "Team", "price": 25}]},
            ],
        )
        names = [c["company"] for c in result["competitive_positioning"]["competitors"]]
        self.assertEqual(names, ["Real"])
        warnings = " ".join(result["warnings"])
        self.assertIn("SalesOnly", warnings)
        self.assertIn("NoData", warnings)

    def test_all_competitors_skipped(self):
        result = pa.analyze_pricing(
            {"tiers": [{"name": "Pro", "price": 20}]},
            [{"name": "SalesOnly", "prices": [None]}, {"name": "Empty", "prices": []}],
        )
        self.assertIsNone(result["competitive_positioning"])
        self.assertTrue(any("competitive positioning skipped" in w
                            for w in result["warnings"]))


class FallbackMessageTests(unittest.TestCase):
    """The 'no issues' advice is built from what is actually missing."""

    TIERS = {"tiers": [
        {"name": "Free", "price": 0, "features": _features(2)},
        {"name": "Pro", "price": 10, "features": _features(4)},
        {"name": "Team", "price": 20, "features": _features(6)},
    ]}
    AT_MARKET = [{"company": "Twin", "tiers": [
        {"name": "Free", "price": 0}, {"name": "Pro", "price": 10},
        {"name": "Team", "price": 20},
    ]}]
    SURVEY = {
        "too_cheap": [5, 6, 7, 8], "bargain": [9, 10, 11, 12],
        "expensive": [18, 20, 22, 24], "too_expensive": [28, 30, 32, 34],
    }

    def test_competitors_given_at_market(self):
        result = pa.analyze_pricing(self.TIERS, self.AT_MARKET)
        self.assertEqual(result["competitive_positioning"]["your_position"], "at market")
        recs = result["recommended_changes"]
        self.assertEqual(len(recs), 1)
        self.assertIn("Van Westendorp", recs[0])
        self.assertNotIn("competitor", recs[0])

    def test_nothing_extra_given(self):
        recs = pa.analyze_pricing(self.TIERS)["recommended_changes"]
        self.assertEqual(len(recs), 1)
        self.assertIn("Van Westendorp", recs[0])
        self.assertIn("competitor data", recs[0])

    def test_survey_given_without_competitors(self):
        result = pa.analyze_pricing(self.TIERS, survey_data=self.SURVEY)
        joined = " ".join(result["recommended_changes"])
        self.assertNotIn("running a Van Westendorp survey", joined)


class ValidationTests(unittest.TestCase):

    def assertProblems(self, call, *fragments):
        with self.assertRaises(pa.PricingInputError) as ctx:
            call()
        text = "\n".join(ctx.exception.problems)
        for fragment in fragments:
            self.assertIn(fragment, text)
        return ctx.exception.problems

    def test_empty_and_missing_tiers(self):
        self.assertProblems(lambda: pa.analyze_pricing({"tiers": []}), "list is empty")
        self.assertProblems(lambda: pa.analyze_pricing({}), "tiers: missing")

    def test_all_problems_reported_together(self):
        problems = self.assertProblems(
            lambda: pa.analyze_pricing(
                {"tiers": [
                    {"name": "A", "price": "abc"},
                    {"name": "B"},
                    {"name": "C", "price": -5},
                    {"name": "D", "price": True},
                    {"name": "E", "price": float("nan")},
                    {"name": "F", "price": "$1,200/yr"},
                ]},
                [{"name": "X", "prices": [0, "zz"]}],
                plg_motion="maybe",
            ),
            "tiers[0].price: 'abc' is not a number",
            "tiers[1].price is missing",
            "tiers[2].price: -5 is negative",
            "tiers[3].price: True is not a number",
            "tiers[4].price: nan is not a finite number",
            "tiers[5].price: '$1,200/yr' looks like a yearly price",
            "competitors[0].prices[1]: 'zz' is not a number",
            "plg_motion: 'maybe'",
        )
        self.assertEqual(len(problems), 8)

    def test_bad_survey(self):
        self.assertProblems(
            lambda: pa.analyze_pricing(
                {"tiers": [{"name": "Pro", "price": 10}]},
                survey_data={"too_cheap": [1, "x"], "bargain": "nope"},
            ),
            "missing key(s) expensive, too_expensive",
            "survey_data.too_cheap[1]: 'x' is not a number",
            "survey_data.bargain: expected a list",
        )


class CliErrorTests(unittest.TestCase):

    def assertCleanExit2(self, proc, *fragments):
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)
        self.assertIn("Input error", proc.stderr)
        for fragment in fragments:
            self.assertIn(fragment, proc.stderr)

    def test_invalid_fields_exit_2(self):
        payload = json.dumps({"tiers": [{"name": "A", "price": "abc"}],
                              "plg_motion": "sometimes"})
        proc = _run_cli(["-"], stdin_text=payload)
        self.assertCleanExit2(proc, "tiers[0].price", "plg_motion")

    def test_empty_tiers_exit_2(self):
        self.assertCleanExit2(_run_cli(["-"], stdin_text='{"tiers": []}'), "empty")

    def test_bad_json_exit_2(self):
        self.assertCleanExit2(_run_cli(["-"], stdin_text="{not json"), "not valid JSON")

    def test_missing_file_exit_2(self):
        missing = os.path.join(FIXTURES, "does-not-exist.json")
        self.assertCleanExit2(_run_cli([missing]), "not found")

    def test_wrong_top_level_exit_2(self):
        self.assertCleanExit2(_run_cli(["-"], stdin_text='"text"'), "must be an object")
        self.assertCleanExit2(_run_cli(["-"], stdin_text='{"foo": 1}'), "'tiers' list")

    def test_bad_survey_file_exit_2(self):
        payload = json.dumps({"too_cheap": [1, 2], "bargain": [3, "x"],
                              "expensive": [5, 6], "too_expensive": [7, 8]})
        self.assertCleanExit2(_run_cli(["-"], stdin_text=payload), "survey.bargain[1]")

    def test_tiers_without_features_print_no_fake_per_feature_price(self):
        payload = json.dumps({"tiers": [{"name": "Pro", "price": 10},
                                        {"name": "Ent", "price": None}]})
        proc = _run_cli(["-"], stdin_text=payload)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("Pro: $10/mo - no features listed", proc.stdout)
        self.assertIn("Ent: custom price (Contact sales) - no features listed",
                      proc.stdout)
        self.assertNotIn("$0/feature", proc.stdout)

    def test_demo_still_runs(self):
        proc = _run_cli(["--demo"])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("Van Westendorp Analysis (n=15)", proc.stdout)


if __name__ == "__main__":
    unittest.main()
