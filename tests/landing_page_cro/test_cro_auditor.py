"""Tests for skills/landing-page-cro/scripts/cro_auditor.py (v2 fact extractor).

The v1 script scored pages with keyword counts. The October 2026 audit found
that it crashed on 9 of 24 SaaS homepages (a capturing group in the urgency
regex made findall() return tuples), scored a keyword-stuffed page with
hidden text 84/100 while a strong div-built page got 34/100, counted nav
links as CTAs and a 1-field prompt box as a 13-field form, and printed
"0/100 Critical" with exit 0 for a JavaScript shell. v2 only extracts facts;
the model scores against references/scoring-rubric.md and --score does the
arithmetic. These tests pin the regressions and the new contract.

All tests are offline: they read local fixtures, never a URL.
Run with: python3 -m unittest discover -s tests -t .
"""

import contextlib
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
import warnings

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCRIPT = os.path.join(REPO_ROOT, "skills", "landing-page-cro", "scripts", "cro_auditor.py")
FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def fixture(name):
    return os.path.join(FIXTURES, name)


def read(name):
    with open(fixture(name), encoding="utf-8") as handle:
        return handle.read()


def _load_module():
    """Import cro_auditor.py by file path (the skills folder is not a package)."""
    name = "cro_auditor_under_test"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        spec.loader.exec_module(module)
    return module


cro = _load_module()


def run_main(argv):
    """Run cro.main() in-process. Returns (exit code, parsed JSON stdout)."""
    out = io.StringIO()
    err = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = cro.main(argv)
        except SystemExit as exc:  # argparse usage errors
            code = exc.code
    text = out.getvalue().strip()
    return code, (json.loads(text) if text else None)


def page_of(name, url="https://example.test/"):
    result = cro.extract_page(read(name), url)
    return result


def all_patterns():
    """Every public compiled regex in the module, including those inside tuples.

    Private markup helpers (_HEAD_RE, ...) are used with group(1) on purpose
    and never with findall() over page text, so they are left out.
    """
    found = {}
    for name, value in vars(cro).items():
        if name.startswith("_"):
            continue
        if isinstance(value, re.Pattern):
            found[name] = value
        elif isinstance(value, tuple):
            for index, item in enumerate(value):
                if isinstance(item, tuple):
                    for part in item:
                        if isinstance(part, re.Pattern):
                            found["%s[%d]" % (name, index)] = part
    return found


# ---------------------------------------------------------------------------
# Regex safety (backlog B01: the crash on asana, monday, posthog, ...)
# ---------------------------------------------------------------------------


class PatternSafetyTests(unittest.TestCase):

    def test_expected_patterns_exist(self):
        names = set(all_patterns())
        for expected in ("URGENCY_PATTERNS", "RISK_REDUCER_PATTERNS", "RATING_PATTERNS",
                         "NUMERIC_CLAIM_PATTERNS", "PRICE_PATTERNS", "COMPLIANCE_PATTERNS[0]",
                         "MEASUREMENT_SIGNATURES[0]"):
            self.assertIn(expected, names)

    def test_no_pattern_has_capturing_groups(self):
        for name, pattern in all_patterns().items():
            with self.subTest(pattern=name):
                self.assertEqual(pattern.groups, 0,
                                 "%s has capturing groups; use (?:...) so findall() returns strings" % name)

    def test_findall_returns_strings_for_every_pattern(self):
        text = read("urgency_unlimited.html") + read("full_page.html")
        for name, pattern in all_patterns().items():
            with self.subTest(pattern=name):
                for match in pattern.findall(text):
                    self.assertIsInstance(match, str)


class UrgencyPatternTests(unittest.TestCase):

    def _urgency(self, text):
        return [m.lower() for m in cro._match_texts(cro.URGENCY_PATTERNS, text)]

    def test_unlimited_is_not_urgency(self):
        self.assertEqual(self._urgency("Unlimited projects for your team"), [])
        self.assertEqual(self._urgency("UNLIMITED seats and unlimited guests"), [])

    def test_bare_limited_feature_copy_is_not_urgency(self):
        self.assertEqual(self._urgency("Limited history on the Free plan"), [])
        self.assertEqual(self._urgency("Intuit Intelligence (beta) has limited availability"), [])

    def test_limited_time_is_urgency(self):
        self.assertEqual(self._urgency("Limited time: 20% off"), ["limited time"])
        self.assertEqual(self._urgency("A limited-time offer"), ["limited-time"])

    def test_formerly_nested_group_returns_full_phrase(self):
        self.assertEqual(self._urgency("Sale ends soon"), ["ends soon"])
        self.assertEqual(self._urgency("Offer ends tomorrow"), ["ends tomorrow"])

    def test_dated_deadlines(self):
        self.assertEqual(self._urgency("Launch offer ends Friday"), ["ends friday"])
        self.assertEqual(self._urgency("Offer ends Nov 30"), ["ends nov 30"])
        self.assertEqual(self._urgency("Only 3 days left"), ["3 days left"])

    def test_word_boundaries_inside_other_words(self):
        self.assertEqual(self._urgency("This offer expired last week"), [])
        self.assertEqual(self._urgency("Our countdowns widget"), [])

    def test_unlimited_fixture_extracts_without_crash(self):
        result = page_of("urgency_unlimited.html")
        self.assertEqual(result["status"], "ok")
        phrases = [c["phrase"].lower() for c in result["page"]["urgency"]["candidates"]]
        self.assertIn("limited time", phrases)
        self.assertIn("ends soon", phrases)
        self.assertFalse(any("unlimited" in p for p in phrases))


# ---------------------------------------------------------------------------
# Gameability (audit evidence: stuffed.html 84/100, good_divs.html 34/100)
# ---------------------------------------------------------------------------


class HiddenContentTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.page = page_of("stuffed_hidden.html")["page"]

    def test_hidden_text_gives_no_trust_proof_or_objection_facts(self):
        page = self.page
        self.assertEqual(page["trust"]["compliance"], [])
        self.assertEqual(page["trust"]["guarantee_sentences"], [])
        self.assertEqual(page["objections"]["faq"]["count"], 0)
        self.assertEqual(page["objections"]["pricing"]["prices_on_page"], 0)
        self.assertEqual(page["objections"]["risk_reducers"], [])
        self.assertEqual(page["proof"]["ratings"]["mentions"], [])
        self.assertEqual(page["proof"]["numeric_claims"], [])
        self.assertEqual(page["urgency"]["candidates"], [])

    def test_hidden_nodes_are_counted(self):
        removed = self.page["hidden_removed"]
        self.assertGreaterEqual(removed.get("inline-style", 0), 1)
        self.assertGreaterEqual(removed.get("hidden-attribute", 0), 1)
        self.assertGreaterEqual(removed.get("aria-hidden", 0), 1)
        self.assertGreaterEqual(removed.get("screen-reader-only", 0), 1)

    def test_company_centric_headline_is_quoted_verbatim_for_the_model(self):
        hero = self.page["hero"]
        self.assertEqual(hero["headline"], "We are the leading synergistic platform company")
        self.assertEqual(hero["headline_source"], "h1")

    def test_dead_links_are_not_conversion_ctas(self):
        ctas = self.page["ctas"]
        self.assertEqual(ctas["hero_conversion_intents"], [])
        # "#" links resolve to the page itself: nothing to convert on.
        self.assertTrue(all(c["href"] == "https://example.test/" for c in ctas["items"]))

    def test_no_score_is_ever_emitted_by_extraction(self):
        result = page_of("stuffed_hidden.html")
        self.assertNotIn("score", json.dumps(result["page"]["hero"]))
        self.assertNotIn("total_score", json.dumps(result))


class DivBuiltPageTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.page = page_of("good_divs.html")["page"]

    def test_role_heading_is_the_headline(self):
        hero = self.page["hero"]
        self.assertEqual(hero["headline"], "Close your books in 2 days, not 2 weeks")
        self.assertEqual(hero["headline_source"], "role=heading aria-level=1")
        self.assertIn("finance teams of 2-20", hero["subheadline"])

    def test_risk_reducers_in_hero(self):
        self.assertEqual(self.page["hero"]["risk_reducers"], ["Free for 30 days", "No card needed"])

    def test_div_button_is_reported_as_non_semantic(self):
        buttons = self.page["ctas"]["non_semantic_buttons"]
        self.assertEqual(buttons, [{"text": "Get my month-end back", "zone": "hero", "element": "div"}])

    def test_quote_with_attribution(self):
        quotes = self.page["proof"]["quotes"]
        self.assertEqual(len(quotes), 1)
        self.assertTrue(quotes[0]["text"].startswith('"We cut close from 11 days to 3."'))
        self.assertEqual(quotes[0]["attribution"], "Maria Lopez, Controller, Northwind Finance (1,200 employees)")

    def test_rating_with_platform(self):
        mentions = self.page["proof"]["ratings"]["mentions"]
        self.assertEqual(mentions[0]["rating"], "4.9 out of 5")
        self.assertEqual(mentions[0]["platforms"], ["G2"])

    def test_compliance(self):
        names = [c["name"] for c in self.page["trust"]["compliance"]]
        self.assertEqual(names, ["SOC 2"])


# ---------------------------------------------------------------------------
# Full fixture: every fact group
# ---------------------------------------------------------------------------


class FullPageTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.result = page_of("full_page.html", "https://shiftly.example/")
        cls.page = cls.result["page"]

    def test_status_ok(self):
        self.assertEqual(self.result["status"], "ok")

    def test_hero(self):
        hero = self.page["hero"]
        self.assertEqual(hero["headline"], "Build next week's staff schedule in 10 minutes")
        self.assertTrue(hero["subheadline"].startswith("Shiftly fills shifts"))
        self.assertEqual([c["text"] for c in hero["ctas"]], ["Start your free trial", "Book a demo"])
        self.assertIn("No credit card required", hero["risk_reducers"])
        self.assertEqual(hero["media"]["interactive_demos"], 1)
        self.assertTrue(hero["first_image_lazy_loaded"])

    def test_cta_zones_and_primary(self):
        ctas = self.page["ctas"]
        self.assertEqual(ctas["primary_guess"]["text"], "Start your free trial")
        self.assertEqual(ctas["primary_guess"]["intent"], "signup")
        self.assertEqual(ctas["hero_conversion_intents"], ["demo", "signup"])
        nav = [c for c in ctas["items"] if c["zone"] == "nav"]
        self.assertTrue(nav, "nav CTAs are reported, in their own zone")
        self.assertNotIn("nav", [c["zone"] for c in ctas["items"][:2]])

    def test_forms(self):
        forms = self.page["forms"]
        primary = forms["primary"]
        self.assertEqual(primary["visible_fields"], 2)
        self.assertEqual(primary["required_fields"], 1)
        self.assertEqual(primary["dropped"]["honeypot"], 1)
        self.assertEqual(primary["submit_text"], "Request a demo")
        self.assertEqual([e["provider"] for e in forms["embedded_by_javascript"]], ["hubspot"])

    def test_logo_wall(self):
        walls = self.page["proof"]["logo_walls"]
        self.assertEqual(len(walls), 1)
        self.assertEqual(walls[0]["names"], ["Example Grill", "Sample Bistro", "Demo Diner", "Placeholder Cafe",
                                             "Test Tacos"])
        self.assertEqual(walls[0]["nearest_heading"], "Trusted by restaurant groups")

    def test_quotes_with_attribution(self):
        quotes = self.page["proof"]["quotes"]
        self.assertEqual([q["attribution"] for q in quotes],
                         ["Dana Lee, Operations Director, Example Grill", "Sam Ortiz, General Manager"])

    def test_ratings(self):
        ratings = self.page["proof"]["ratings"]
        self.assertEqual(ratings["mentions"][0]["platforms"], ["Capterra"])
        self.assertEqual(ratings["platform_badges"][0]["alt"], "G2 Leader Fall badge")
        self.assertEqual(ratings["json_ld_aggregate"][0]["rating_value"], "4.7")

    def test_numeric_claims(self):
        claims = [c["text"] for c in self.page["proof"]["numeric_claims"]]
        self.assertIn("Cut scheduling time from 4 hours to 30 minutes a week.", claims)
        self.assertIn("Used by 1,200 restaurants in 14 countries.", claims)
        self.assertFalse(any(c.startswith("Starter $29") for c in claims), "prices are not proof claims")

    def test_trust(self):
        trust = self.page["trust"]
        self.assertEqual([c["name"] for c in trust["compliance"]], ["SOC 2", "GDPR", "ISO 27001"])
        self.assertEqual(sorted(trust["legal_links"]), ["privacy", "security", "status", "terms"])
        self.assertEqual(trust["legal_links"]["security"]["href"], "https://trust.shiftly.example/")
        self.assertIn("30-day money-back guarantee.", [g["text"] for g in trust["guarantee_sentences"]])

    def test_objections(self):
        objections = self.page["objections"]
        self.assertEqual(objections["faq"]["count"], 4)
        self.assertEqual(objections["faq"]["sources"], ["details/summary", "FAQPage JSON-LD", "question heading"])
        self.assertEqual(objections["pricing"]["price_examples"], ["$29/mo", "$59/mo"])
        self.assertEqual(objections["pricing"]["pricing_links"], ["https://shiftly.example/pricing"])
        self.assertEqual(objections["comparison_links"], ["https://shiftly.example/vs/when-i-work"])

    def test_urgency(self):
        urgency = self.page["urgency"]
        phrases = [c["phrase"] for c in urgency["candidates"]]
        self.assertIn("ends Friday", phrases)
        self.assertIn("3 days left", phrases)
        self.assertEqual(urgency["countdown_elements"], 1)

    def test_navigation(self):
        nav = self.page["navigation"]
        self.assertEqual(nav["nav_links"], 7)
        self.assertEqual(nav["footer_links"], 4)

    def test_measurement(self):
        m = self.page["measurement"]
        self.assertEqual(m["tag_manager"], ["Google Tag Manager"])
        self.assertEqual(m["session_replay"], ["Hotjar"])
        self.assertEqual(m["experimentation"], ["Optimizely"])
        self.assertEqual(m["chat"], ["Intercom"])
        self.assertEqual(m["consent"], ["OneTrust"])

    def test_speed_diagnostics_are_not_a_score(self):
        speed = self.page["speed_diagnostics"]
        self.assertEqual(speed["render_blocking_head_scripts"], 2)
        self.assertTrue(speed["hero_first_image_lazy"])
        self.assertIn("PageSpeed field data", speed["note"])
        self.assertNotIn("score", speed)

    def test_competitor_summary_shape(self):
        summary = cro.competitor_summary(self.page)
        self.assertEqual(summary["primary_cta"]["text"], "Start your free trial")
        self.assertEqual(summary["proof"]["quotes_with_attribution"], 2)
        self.assertEqual(summary["pricing"]["price_examples"], ["$29/mo", "$59/mo"])
        self.assertEqual(summary["compliance"], ["SOC 2", "GDPR", "ISO 27001"])


class FormRegressionTests(unittest.TestCase):

    def test_aria_hidden_inputs_do_not_count(self):
        page = page_of("prompt_form.html")["page"]
        primary = page["forms"]["primary"]
        self.assertEqual(primary["visible_fields"], 1)
        self.assertEqual(primary["dropped"]["hidden"], 11)


class LanguageTests(unittest.TestCase):

    def test_non_english_page_gets_a_note_and_structure(self):
        page = page_of("german_page.html")["page"]
        self.assertEqual(page["hero"]["headline"], "Projekte pünktlich abschließen, jedes Mal")
        self.assertEqual(page["ctas"]["primary_guess"]["intent"], "signup")
        self.assertEqual(page["objections"]["faq"]["questions"], ["Kann ich jederzeit kündigen?"])
        self.assertTrue(any("English patterns" in n for n in page["notes"]))


class ShellTests(unittest.TestCase):

    def test_js_shell_is_nothing_to_analyze(self):
        result = cro.extract_page(read("js_shell.html"), "https://example.test/")
        self.assertEqual(result["status"], "nothing_to_analyze")
        self.assertIsNone(result["page"])


# ---------------------------------------------------------------------------
# --score arithmetic (D1)
# ---------------------------------------------------------------------------


def scores(**dims):
    return {"rubric_version": cro.RUBRIC_VERSION, "dimensions": dims}


class ScoreTests(unittest.TestCase):

    def test_weights_are_documented_impact_weights(self):
        weights = {d[0]: d[2] for d in cro.DIMENSIONS}
        self.assertEqual(weights, {"value_prop": 20, "cta": 15, "proof": 15, "objections": 10, "copy": 10,
                                   "trust": 10, "form": 10, "hierarchy": 5, "speed": 5, "urgency": 5})

    def test_all_tens_is_100(self):
        payload = scores(**{d: {"score": 10, "confidence": "high", "evidence": ["E1"]} for d in cro.DIMENSION_IDS})
        result = cro.compute_score(payload)
        self.assertEqual(result["scoring"]["value"], 100)
        self.assertEqual(result["scoring"]["confidence"], "high")
        self.assertEqual(result["scoring"]["band"], "Excellent")

    def test_na_and_not_measured_are_dropped_and_renormalized(self):
        payload = scores(
            value_prop={"score": 6, "confidence": "high", "evidence": ["E1"]},
            cta={"score": 7, "confidence": "high", "evidence": ["E2"]},
            proof={"score": 8, "confidence": "medium", "evidence": ["E3"]},
            objections={"score": 4, "confidence": "medium", "evidence": ["E4"]},
            copy={"score": 6, "confidence": "medium", "evidence": ["E1"]},
            trust={"score": 5, "confidence": "high", "evidence": ["E5"]},
            form={"status": "na"},
            hierarchy={"status": "not_measured"},
            speed={"status": "not_measured"},
            urgency={"status": "na"},
        )
        result = cro.compute_score(payload)
        scoring = result["scoring"]
        # (20*6 + 15*7 + 15*8 + 10*4 + 10*6 + 10*5) / 80 * 10 = 61.875
        self.assertEqual(scoring["exact"], 61.88)
        self.assertEqual(scoring["value"], 62)
        self.assertEqual(scoring["scored_weight"], 80)
        self.assertEqual(scoring["applicable_weight"], 90)
        self.assertAlmostEqual(scoring["measured_weight"], 0.8889, places=4)
        self.assertTrue(scoring["show_composite"])
        self.assertEqual(scoring["band"], "Fair")
        self.assertEqual(scoring["confidence"], "medium")
        self.assertEqual(scoring["header_line"],
                         "**Score:** 62/100 (rubric; confidence medium; 89% of weight measured)")
        na = [d for d in result["dimensions"] if d["status"] != "scored"]
        self.assertTrue(all(d["points"] is None and d["score"] is None for d in na))

    def test_biggest_gaps_ranked_by_points_lost(self):
        payload = scores(value_prop={"score": 5, "confidence": "high", "evidence": ["E1"]},
                         cta={"score": 9, "confidence": "high", "evidence": ["E2"]},
                         proof={"score": 3, "confidence": "high", "evidence": ["E3"]},
                         copy={"score": 8, "confidence": "high", "evidence": ["E4"]})
        result = cro.compute_score(payload)
        self.assertEqual([g["id"] for g in result["biggest_gaps"]], ["proof", "value_prop", "copy"])

    def test_no_composite_below_60_percent_measured(self):
        # Copy review: only the copy dimensions can be judged (45 of 105).
        payload = scores(value_prop={"score": 7, "confidence": "medium", "evidence": ["E1"]},
                         cta={"score": 5, "confidence": "medium", "evidence": ["E2"]},
                         copy={"score": 6, "confidence": "medium", "evidence": ["E3"]})
        result = cro.compute_score(payload)
        scoring = result["scoring"]
        self.assertFalse(scoring["show_composite"])
        self.assertIsNone(scoring["value"])
        self.assertIsNone(scoring["header_line"])
        self.assertIn("43%", scoring["no_composite_reason"])
        self.assertTrue(any("not in the scores file" in n.lower() or "counted as not measured" in n
                            for n in result["notes"]))

    def test_confidence_rules(self):
        base = {"score": 5, "evidence": ["E1"]}
        mostly_low = scores(value_prop=dict(base, confidence="low"), cta=dict(base, confidence="low"),
                            proof=dict(base, confidence="low"), objections=dict(base, confidence="high"),
                            copy=dict(base, confidence="high"), trust=dict(base, confidence="high"))
        self.assertEqual(cro.compute_score(mostly_low)["scoring"]["confidence"], "low")
        missing = scores(value_prop={"score": 5, "evidence": ["E1"]})
        result = cro.compute_score(missing)
        self.assertEqual(result["dimensions"][0]["confidence"], "medium")
        self.assertTrue(any("no confidence" in n for n in result["notes"]))

    def test_list_form_and_bare_numbers(self):
        listed = {"dimensions": [{"id": "value_prop", "score": 8, "confidence": "high", "evidence": ["E1"]}]}
        self.assertEqual(cro.compute_score(listed)["dimensions"][0]["score"], 8)
        bare = {"dimensions": {"value_prop": 8}}
        self.assertEqual(cro.compute_score(bare)["dimensions"][0]["score"], 8)

    def test_bad_inputs_are_usage_errors(self):
        for payload in (
            {"dimensions": {"vibes": {"score": 3}}},
            {"dimensions": {"cta": {"score": 11}}},
            {"dimensions": {"cta": {"score": "great"}}},
            {"dimensions": {"cta": {"score": 5, "confidence": "certain"}}},
            {"dimensions": {"cta": {"status": "maybe"}}},
            {"dimensions": {"cta": {"status": "scored"}}},
            {"dimensions": "all good"},
        ):
            with self.subTest(payload=payload):
                with self.assertRaises(cro.cli.UsageError):
                    cro.compute_score(payload)

    def test_missing_evidence_is_flagged(self):
        result = cro.compute_score({"dimensions": {"cta": {"score": 5, "confidence": "high"}}})
        self.assertTrue(any("no evidence" in n for n in result["notes"]))

    def test_rubric_version_mismatch_is_noted(self):
        result = cro.compute_score({"rubric_version": "cro-rubric-v1", "dimensions": {"cta": 5}})
        self.assertTrue(any("differs" in n for n in result["notes"]))


# ---------------------------------------------------------------------------
# Command line contract
# ---------------------------------------------------------------------------


class FakeHttp:
    """Stands in for _growthkit.http in main(): no network."""

    def __init__(self, results):
        self.results = results
        self.calls = []

    def fetch(self, url, kind="html", timeout=15):
        self.calls.append(url)
        return self.results[url]

    @staticmethod
    def summarize(result):
        return {k: result.get(k) for k in ("status", "url", "final_url", "http_status", "error", "bytes")}

    @staticmethod
    def normalize_url(url):
        return url


def fetch_result(url, status="ok", html=None, http_status=200, error=None, bot=None):
    return {"status": status, "url": url, "final_url": url, "http_status": http_status, "html": html,
            "error": error, "bytes": len(html or ""), "elapsed_ms": 5, "bot_protection": bot,
            "js_shell_signals": {"visible_words": 0} if status == "js_shell" else None,
            "content_type": "text/html"}


class CliTests(unittest.TestCase):

    def setUp(self):
        self._real_http = cro._http
        self.addCleanup(setattr, cro, "_http", self._real_http)

    def use_fake(self, results):
        fake = FakeHttp(results)
        cro._http = lambda: fake
        return fake

    def test_file_input_exit_0_with_facts_and_no_score(self):
        code, data = run_main([fixture("full_page.html"), "--url", "https://shiftly.example/", "--json",
                               "--psi", "off"])
        self.assertEqual(code, 0)
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["mode"], "extract")
        self.assertIn("hero", data["page"])
        self.assertNotIn("scoring", data)
        self.assertIn("coverage", data)

    def test_js_shell_file_exits_5_without_page(self):
        code, data = run_main([fixture("js_shell.html"), "--json", "--psi", "off"])
        self.assertEqual(code, 5)
        self.assertEqual(data["status"], "nothing_to_analyze")
        self.assertIsNone(data["page"])
        self.assertNotIn("scoring", data)

    def test_blocked_url_exits_3(self):
        url = "https://blocked.example/"
        self.use_fake({url: fetch_result(url, "blocked", None, 403, "Blocked by bot protection (datadome), HTTP 403",
                                         {"vendor": "datadome", "challenge": True})})
        code, data = run_main([url, "--json", "--psi", "off"])
        self.assertEqual(code, 3)
        self.assertEqual(data["status"], "blocked")
        self.assertIsNone(data["page"])

    def test_unreachable_url_exits_3(self):
        url = "https://gone.example/"
        self.use_fake({url: fetch_result(url, "unreachable", None, None, "DNS lookup failed")})
        code, data = run_main([url, "--json", "--psi", "off"])
        self.assertEqual(code, 3)
        self.assertEqual(data["status"], "unreachable")

    def test_js_shell_url_exits_5(self):
        url = "https://shell.example/"
        self.use_fake({url: fetch_result(url, "js_shell", read("js_shell.html"))})
        code, data = run_main([url, "--json", "--psi", "off"])
        self.assertEqual(code, 5)
        self.assertEqual(data["status"], "nothing_to_analyze")

    def test_competitor_side_by_side_and_partial_on_failure(self):
        you, rival, blocked = "https://you.example/", "https://rival.example/", "https://walled.example/"
        fake = self.use_fake({
            you: fetch_result(you, html=read("full_page.html")),
            rival: fetch_result(rival, html=read("good_divs.html")),
            blocked: fetch_result(blocked, "blocked", None, 403, "Blocked", {"vendor": "cloudflare", "challenge": True}),
        })
        code, data = run_main([you, "--vs", rival, "--vs", blocked, "--json", "--psi", "off"])
        self.assertEqual(code, 4)
        self.assertEqual(data["status"], "partial")
        self.assertEqual(fake.calls, [you, rival, blocked])
        self.assertEqual(data["you"]["primary_cta"]["text"], "Start your free trial")
        self.assertEqual(data["competitors"][0]["summary"]["headline"], "Close your books in 2 days, not 2 weeks")
        self.assertEqual(data["competitors"][1]["status"], "blocked")
        self.assertIn("error", data["competitors"][1])

    def test_competitor_limit(self):
        code, data = run_main([fixture("full_page.html"), "--vs", "a.example", "--vs", "b.example",
                               "--vs", "c.example", "--json"])
        self.assertEqual(code, 2)
        self.assertIn("competitor-intel", data["errors"][0])

    def test_psi_auto_without_key_is_a_note_not_an_error(self):
        saved = {k: os.environ.pop(k) for k in ("PAGESPEED_API_KEY", "GOOGLE_API_KEY") if k in os.environ}
        self.addCleanup(os.environ.update, saved)
        code, data = run_main([fixture("full_page.html"), "--url", "https://shiftly.example/", "--json"])
        self.assertEqual(code, 0)
        self.assertIsNone(data["speed"]["psi"])
        self.assertTrue(any("PAGESPEED_API_KEY" in n for n in data["notes"]))

    def test_missing_file_is_usage_error(self):
        code, data = run_main([os.path.join(FIXTURES, "nope.html"), "--json"])
        self.assertEqual(code, 2)
        self.assertEqual(data["status"], "usage_error")

    def test_demo_is_labelled(self):
        code, data = run_main(["--demo", "--json"])
        self.assertEqual(code, 0)
        self.assertTrue(data["demo"])
        self.assertTrue(any("DEMO DATA" in n for n in data["notes"]))

    def test_score_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "scores.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(scores(value_prop={"score": 8, "confidence": "high", "evidence": ["E1"]},
                                 cta={"score": 6, "confidence": "high", "evidence": ["E2"]},
                                 proof={"score": 4, "confidence": "medium", "evidence": ["E3"]},
                                 objections={"score": 5, "confidence": "medium", "evidence": ["E4"]},
                                 copy={"score": 7, "confidence": "high", "evidence": ["E5"]},
                                 trust={"score": 6, "confidence": "high", "evidence": ["E6"]},
                                 form={"status": "na"}, urgency={"status": "na"},
                                 hierarchy={"score": 7, "confidence": "medium", "evidence": ["E7"]},
                                 speed={"status": "not_measured"}), handle)
            code, data = run_main(["--score", path, "--json"])
            self.assertEqual(code, 0)
            self.assertEqual(data["mode"], "score")
            self.assertTrue(data["scoring"]["show_composite"])
            bad = os.path.join(tmp, "bad.json")
            with open(bad, "w", encoding="utf-8") as handle:
                handle.write("{not json")
            code, data = run_main(["--score", bad, "--json"])
            self.assertEqual(code, 2)
            code, data = run_main(["--score", path, fixture("full_page.html"), "--json"])
            self.assertEqual(code, 2)

    def test_subprocess_run_prints_only_json(self):
        proc = subprocess.run(
            [sys.executable, SCRIPT, fixture("urgency_unlimited.html"), "--json", "--psi", "off"],
            capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        data = json.loads(proc.stdout)
        self.assertEqual(data["tool"], "cro_auditor")
        self.assertNotIn("Traceback", proc.stderr)


if __name__ == "__main__":
    unittest.main()
