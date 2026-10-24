"""Offline tests for tools/smoke_live.py.

The live script is only ever run against real sites by the weekly CI job.
These tests feed it fake growthkit modules, so they need no network.

Run from the repo root:
    python3 -m unittest discover -s tests -t .
"""

import contextlib
import io
import json
import os
import tempfile
import unittest

from tests.tools import load_tool

smoke = load_tool("smoke_live")

GOOD_PAGE = {
    "status": "ok", "http_status": 200, "url": "https://site.test/", "final_url": "https://site.test/",
    "html": "<html>...</html>", "error": None, "bot_protection": None, "elapsed_ms": 120,
}
GOOD_FACTS = {
    "title": "Site", "headings": {"h1": ["Ship faster"]}, "word_count": 800,
    "ctas": [{"text": "Start free"}], "is_js_shell": False,
}
GOOD_ROBOTS = {"status": "ok", "http_status": 200, "text": "User-agent: *\nAllow: /\n", "error": None}


class FakeHttp:
    def __init__(self, page=None, robots=None, raise_on_fetch=None):
        self.page = page or GOOD_PAGE
        self.robots = robots or GOOD_ROBOTS
        self.raise_on_fetch = raise_on_fetch
        self.calls = []

    def fetch(self, url, timeout=None):
        self.calls.append(("fetch", url, timeout))
        if self.raise_on_fetch:
            raise self.raise_on_fetch
        return dict(self.page)

    def fetch_site_file(self, page_url, path, timeout=None):
        self.calls.append(("site_file", page_url, path))
        return dict(self.robots)


class FakeHtml:
    def __init__(self, facts=None):
        self.facts = facts or GOOD_FACTS

    def page_facts(self, markup, url=None):
        return dict(self.facts)


def results(site):
    return {check["check"]: check["result"] for check in site["checks"]}


class CheckSiteTests(unittest.TestCase):
    def test_healthy_site_passes_all_checks(self):
        http = FakeHttp()
        site = smoke.check_site("https://site.test", http, FakeHtml(), timeout=5)
        self.assertEqual(results(site), {"page": "pass", "facts": "pass", "robots": "pass"})
        self.assertEqual(http.calls[0], ("fetch", "https://site.test", 5))
        self.assertEqual(http.calls[1], ("site_file", "https://site.test/", "/robots.txt"))

    def test_blocked_page_warns_and_skips_facts(self):
        page = dict(GOOD_PAGE, status="blocked", http_status=403, html=None,
                    bot_protection={"vendor": "cloudflare", "challenge": True}, error="Bot wall")
        site = smoke.check_site("https://site.test", FakeHttp(page=page), FakeHtml())
        self.assertEqual(results(site), {"page": "warn", "robots": "pass"})
        detail = site["checks"][0]["detail"]
        self.assertIn("status blocked", detail)
        self.assertIn("bot protection: cloudflare (challenge)", detail)

    def test_thin_page_warns_with_reasons(self):
        facts = dict(GOOD_FACTS, title="", headings={"h1": []}, word_count=12, ctas=[])
        site = smoke.check_site("https://site.test", FakeHttp(), FakeHtml(facts))
        self.assertEqual(results(site)["facts"], "warn")
        detail = site["checks"][1]["detail"]
        for needle in ("no <title>", "no <h1>", "only 12 visible words", "no CTAs"):
            self.assertIn(needle, detail)

    def test_robots_without_user_agent_warns(self):
        robots = dict(GOOD_ROBOTS, text="<html>not robots</html>")
        site = smoke.check_site("https://site.test", FakeHttp(robots=robots), FakeHtml())
        self.assertEqual(results(site)["robots"], "warn")
        self.assertIn("no User-agent line", site["checks"][-1]["detail"])

    def test_dashes_in_site_text_become_hyphens(self):
        facts = dict(GOOD_FACTS, title="Linear %s The system" % chr(0x2013), headings={"h1": ["A %s B" % chr(0x2014)]})
        site = smoke.check_site("https://site.test", FakeHttp(), FakeHtml(facts))
        detail = site["checks"][1]["detail"]
        self.assertIn("'Linear - The system'", detail)
        self.assertIn("'A - B'", detail)

    def test_exception_becomes_a_warning(self):
        site = smoke.check_site("https://site.test", FakeHttp(raise_on_fetch=RuntimeError("boom")), FakeHtml())
        self.assertEqual(site["checks"], [{"check": "error", "result": "warn", "detail": "RuntimeError: boom"}])


class MainTests(unittest.TestCase):
    def run_main(self, argv, loader, env=None):
        out, err = io.StringIO(), io.StringIO()
        old = {key: os.environ.get(key) for key in ("GITHUB_ACTIONS", "GITHUB_STEP_SUMMARY")}
        for key in old:
            os.environ.pop(key, None)
        os.environ.update(env or {})
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = smoke.main(argv, loader=loader)
        finally:
            for key, value in old.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
        return code, out.getvalue(), err.getvalue()

    def test_warnings_never_fail_without_strict(self):
        page = dict(GOOD_PAGE, status="unreachable", http_status=None, html=None, error="DNS failed")
        loader = lambda: (FakeHttp(page=page), FakeHtml(), "")  # noqa: E731
        code, out, _err = self.run_main(["--site", "https://a.test", "--site", "https://b.test"], loader)
        self.assertEqual(code, 0)
        self.assertIn("WARN  a.test page: status unreachable, DNS failed", out)
        self.assertIn("2 site(s), 2 warning(s)", out)
        code, _out, _err = self.run_main(["--site", "https://a.test", "--strict"], loader)
        self.assertEqual(code, 1)

    def test_default_sites_and_json_output(self):
        loader = lambda: (FakeHttp(), FakeHtml(), "")  # noqa: E731
        code, out, _err = self.run_main(["--json"], loader)
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertEqual([site["url"] for site in data["sites"]], list(smoke.DEFAULT_SITES))
        self.assertEqual(len(smoke.DEFAULT_SITES), 3)
        self.assertEqual(data["warnings"], 0)

    def test_missing_dependencies_warn_only(self):
        loader = lambda: (None, None, "requests or beautifulsoup4 is not installed")  # noqa: E731
        code, out, _err = self.run_main([], loader)
        self.assertEqual(code, 0)
        self.assertIn("WARN  setup: requests or beautifulsoup4 is not installed", out)
        self.assertEqual(self.run_main(["--strict"], loader)[0], 1)

    def test_github_annotations_and_step_summary(self):
        page = dict(GOOD_PAGE, status="blocked", http_status=429, html=None, error="Rate limited")
        loader = lambda: (FakeHttp(page=page), FakeHtml(), "")  # noqa: E731
        with tempfile.TemporaryDirectory() as tmp:
            summary = os.path.join(tmp, "summary.md")
            code, _out, err = self.run_main(
                ["--site", "https://a.test/path"], loader,
                env={"GITHUB_ACTIONS": "true", "GITHUB_STEP_SUMMARY": summary},
            )
            with open(summary, encoding="utf-8") as handle:
                table = handle.read()
        self.assertEqual(code, 0)
        self.assertIn("::warning title=Live smoke a.test::page: status blocked, HTTP 429", err)
        self.assertIn("| a.test | page | warn |", table)
        self.assertIn("| a.test | robots | pass |", table)


if __name__ == "__main__":
    unittest.main()
