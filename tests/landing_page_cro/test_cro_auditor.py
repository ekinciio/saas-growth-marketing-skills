"""Regression tests for skills/landing-page-cro/scripts/cro_auditor.py.

Backlog item B01: URGENCY_PATTERNS had a nested capturing group, so
re.findall() returned tuples and ', '.join() crashed with
"TypeError: sequence item 0: expected str instance, tuple found". It also had
no word boundaries, so "unlimited" (on almost every SaaS page) matched
"limited". 9 of 24 live SaaS homepages crashed (asana, monday, posthog, ...).

All tests are offline: they audit a local fixture file, never a URL.
Run with: python3 -m unittest discover -s tests -t .
"""

import importlib.util
import os
import re
import subprocess
import sys
import unittest
import warnings

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCRIPT = os.path.join(
    REPO_ROOT, "skills", "landing-page-cro", "scripts", "cro_auditor.py"
)
FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
URGENCY_FIXTURE = os.path.join(FIXTURES, "urgency_unlimited.html")


def _load_module():
    """Import cro_auditor.py by file path (the skills folder is not a package)."""
    name = "cro_auditor_under_test"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    module = importlib.util.module_from_spec(spec)
    # dataclasses with postponed annotations look the module up in
    # sys.modules, so register it before executing.
    sys.modules[name] = module
    with warnings.catch_warnings():
        # urllib3 warns about LibreSSL on the macOS system Python; not our concern.
        warnings.simplefilter("ignore")
        spec.loader.exec_module(module)
    return module


cro = _load_module()


def _module_patterns():
    """Every compiled regex defined at module level in cro_auditor.py."""
    return {
        name: value
        for name, value in vars(cro).items()
        if isinstance(value, re.Pattern)
    }


class PatternSafetyTests(unittest.TestCase):
    """Guard the whole file against the tuple-from-findall crash class."""

    def test_patterns_found(self):
        names = set(_module_patterns())
        for expected in (
            "CTA_PATTERNS",
            "SOCIAL_PROOF_PATTERNS",
            "TRUST_PATTERNS",
            "URGENCY_PATTERNS",
            "OBJECTION_PATTERNS",
        ):
            self.assertIn(expected, names)

    def test_no_pattern_has_capturing_groups(self):
        for name, pattern in _module_patterns().items():
            with self.subTest(pattern=name):
                self.assertEqual(
                    pattern.groups, 0,
                    f"{name} has {pattern.groups} capturing group(s); use (?:...) "
                    "so findall() returns strings, not tuples",
                )

    def test_findall_returns_strings_for_every_pattern(self):
        with open(URGENCY_FIXTURE, encoding="utf-8") as fh:
            text = fh.read()
        # Extra copy that hits every old nested group at least once.
        text += (
            " ends soon. ends today. case studies. trusted by 3,000 customers."
            " SOC 2. money-back guarantee. FAQ. vs. Sign up. Submit"
        )
        for name, pattern in _module_patterns().items():
            with self.subTest(pattern=name):
                for match in pattern.findall(text):
                    self.assertIsInstance(match, str)
                for match in cro._match_texts(pattern, text):
                    self.assertIsInstance(match, str)


class UrgencyPatternTests(unittest.TestCase):

    def _urgency(self, text):
        return [m.lower() for m in cro._match_texts(cro.URGENCY_PATTERNS, text)]

    def test_unlimited_is_not_urgency(self):
        self.assertEqual(self._urgency("Unlimited projects for your team"), [])
        self.assertEqual(self._urgency("UNLIMITED seats and unlimited guests"), [])

    def test_bare_limited_feature_copy_is_not_urgency(self):
        # Free-plan limits and beta-feature notes are not scarcity marketing
        # (the second string is real copy from mailchimp.com, Oct 2026).
        self.assertEqual(self._urgency("Limited history on the Free plan"), [])
        self.assertEqual(
            self._urgency("Intuit Intelligence (beta) has limited availability"), []
        )

    def test_limited_time_is_urgency(self):
        self.assertEqual(self._urgency("Limited time: 20% off"), ["limited time"])
        self.assertEqual(self._urgency("A limited-time offer"), ["limited-time"])

    def test_formerly_nested_group_returns_full_phrase(self):
        # "ends?\s*(soon|today|tomorrow)" used to make findall return tuples.
        self.assertEqual(self._urgency("Sale ends soon"), ["ends soon"])
        self.assertEqual(self._urgency("Offer ends tomorrow"), ["ends tomorrow"])

    def test_other_urgency_phrases(self):
        found = self._urgency(
            "Hurry! Only 3 spots left. Early-bird pricing. Don't miss it. "
            "Last chance. Act now. Countdown. The deal expires Friday."
        )
        for phrase in ("hurry", "only 3 spots", "early-bird", "don't miss",
                       "last chance", "act now", "countdown", "expires"):
            self.assertIn(phrase, found)

    def test_word_boundaries_inside_other_words(self):
        # "expires?" must not match inside "expired" (a past deadline is not
        # urgency), and "countdown" must not match inside "countdowns".
        self.assertEqual(self._urgency("This offer expired last week"), [])
        self.assertEqual(self._urgency("Our countdowns widget"), [])


class AuditFixtureTests(unittest.TestCase):

    def test_audit_fixture_does_not_crash(self):
        result = cro.audit_page(URGENCY_FIXTURE)
        self.assertIsNotNone(result)
        self.assertGreater(result.total_score, 0)
        self.assertEqual(len(result.dimensions), 10)

    def test_urgency_evidence_is_plain_text_without_unlimited(self):
        result = cro.audit_page(URGENCY_FIXTURE)
        urgency = next(d for d in result.dimensions if d.name == "Urgency and scarcity")
        evidence = " | ".join(urgency.evidence)
        self.assertIn("Limited time", evidence)
        self.assertIn("ends soon", evidence)
        self.assertNotIn("(", evidence)  # no tuple reprs
        # Two real signals: "Limited time" and "ends soon". The three
        # "Unlimited" mentions must not add anything.
        self.assertEqual(urgency.score, 7)

    def test_unlimited_only_page_scores_neutral_urgency(self):
        soup = cro.BeautifulSoup(
            "<html><body><h1>Unlimited projects for your team</h1></body></html>",
            "html.parser",
        )
        dim = cro.score_urgency(soup)
        self.assertEqual(dim.score, 5)
        self.assertIn("No urgency elements detected", dim.evidence[0])

    def test_repeated_signal_counts_once(self):
        soup = cro.BeautifulSoup(
            "<p>Limited time offer.</p><p>LIMITED TIME offer.</p>", "html.parser"
        )
        dim = cro.score_urgency(soup)
        self.assertEqual(dim.score, 6)

    def test_objection_evidence_is_in_page_order(self):
        # It used list(set(...)), so the order (and the 8 signals shown)
        # changed from run to run with Python's hash seed.
        soup = cro.BeautifulSoup(
            "<p>Pricing. FAQ. Pricing again. No credit card. Support.</p>",
            "html.parser",
        )
        dim = cro.score_objection_handling(soup)
        self.assertEqual(
            dim.evidence[0],
            "Objection-handling signals: pricing, faq, no credit card, support",
        )
        self.assertEqual(dim.score, 7)

    def test_trust_and_objection_evidence_are_strings(self):
        result = cro.audit_page(URGENCY_FIXTURE)
        for dim in result.dimensions:
            for item in dim.evidence:
                self.assertIsInstance(item, str)


class CliTests(unittest.TestCase):

    def test_cli_on_fixture_exits_zero(self):
        proc = subprocess.run(
            [sys.executable, "-W", "ignore", SCRIPT, URGENCY_FIXTURE],
            capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("OVERALL CRO SCORE:", proc.stdout)
        self.assertIn("Urgency signals found: Limited time", proc.stdout)
        self.assertNotIn("Traceback", proc.stderr)


if __name__ == "__main__":
    unittest.main()
