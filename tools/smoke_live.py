#!/usr/bin/env python3
"""Weekly live smoke test of the shared growthkit fetch and parse pipeline.

Unit tests are offline by design, so nothing else notices when real sites
change in ways that break the shared code: a new bot wall, a markup change
that empties the outline, a redirect the fetcher mishandles. This script
fetches a few well-known SaaS homepages with the real network and checks
the results look sane:

  page     http.fetch() returns status ok (HTTP 200, HTML, not a JS shell)
  facts    html.page_facts() finds a title, an <h1>, at least MIN_WORDS
           visible words and at least one CTA
  robots   http.fetch_site_file(..., "/robots.txt") returns a robots file

It is warn-only: sites change, block datacenter IPs and go down, none of
which should fail the build. Every problem is printed as a warning (and as
a GitHub Actions ::warning annotation plus a step-summary table when run in
Actions), and the exit code is 0 unless --strict is given.

Usage, from the repo root:

    python3 tools/smoke_live.py
    python3 tools/smoke_live.py --site https://example.com --json
    python3 tools/smoke_live.py --strict      # exit 1 on any warning (local use)

It imports the source package (shared/growthkit), not a skill copy;
tools/sync_shared.py --check proves the copies are identical.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHARED_DIR = os.path.join(REPO_ROOT, "shared")

# Three public SaaS homepages that served full HTML to the growthkit fetcher
# when this was written (October 2026). Swap a site out if it starts to block
# GitHub's runners every week; a single bad week is just noise.
DEFAULT_SITES = (
    "https://linear.app",
    "https://cal.com",
    "https://www.notion.com",
)
MIN_WORDS = 100
DEFAULT_TIMEOUT = 20.0

PASS = "pass"
WARN = "warn"

# Site titles often contain em or en dashes. The repo's output rule bans them,
# so details show a plain hyphen instead (chr() keeps this file free of them).
_DASHES = {code: "-" for code in (0x2012, 0x2013, 0x2014, 0x2015, 0x2212)}


def _check(name: str, ok: bool, detail: str) -> Dict[str, Any]:
    return {"check": name, "result": PASS if ok else WARN, "detail": detail.translate(_DASHES)}


def _fetch_detail(result: Dict[str, Any]) -> str:
    """One line that says what came back from http.fetch()."""
    parts = ["status %s" % result.get("status")]
    if result.get("http_status") is not None:
        parts.append("HTTP %s" % result.get("http_status"))
    bot = result.get("bot_protection") or {}
    if bot.get("vendor"):
        parts.append("bot protection: %s%s" % (bot["vendor"], " (challenge)" if bot.get("challenge") else ""))
    if result.get("error"):
        parts.append(str(result["error"]))
    if result.get("elapsed_ms") is not None:
        parts.append("%s ms" % result.get("elapsed_ms"))
    return ", ".join(parts)


def check_site(url: str, http: Any, html: Any, timeout: float = DEFAULT_TIMEOUT) -> Dict[str, Any]:
    """Run the page, facts and robots checks for one site.

    http and html are the growthkit modules (passed in so tests can use fakes).
    Never raises: an unexpected exception becomes a warning.
    """
    site: Dict[str, Any] = {"url": url, "final_url": None, "checks": []}
    checks: List[Dict[str, Any]] = site["checks"]
    try:
        page = http.fetch(url, timeout=timeout)
        site["final_url"] = page.get("final_url")
        page_ok = page.get("status") == "ok" and bool(page.get("html"))
        checks.append(_check("page", page_ok, _fetch_detail(page)))
        if page_ok:
            facts = html.page_facts(page["html"], url=page.get("final_url") or url)
            words = int(facts.get("word_count") or 0)
            h1s = (facts.get("headings") or {}).get("h1") or []
            ctas = facts.get("ctas") or []
            problems = []
            if not facts.get("title"):
                problems.append("no <title>")
            if not h1s:
                problems.append("no <h1>")
            if words < MIN_WORDS:
                problems.append("only %d visible words (expected %d or more)" % (words, MIN_WORDS))
            if not ctas:
                problems.append("no CTAs found")
            if facts.get("is_js_shell"):
                problems.append("looks like a JavaScript shell")
            summary = "title %r, h1 %r, %d words, %d CTAs" % (
                (facts.get("title") or "")[:60],
                (h1s[0] if h1s else "")[:60],
                words,
                len(ctas),
            )
            checks.append(_check("facts", not problems, "; ".join(problems + [summary]) if problems else summary))
        robots = http.fetch_site_file(page.get("final_url") or page.get("url") or url, "/robots.txt",
                                      timeout=timeout)
        text = robots.get("text") or ""
        robots_ok = robots.get("status") == "ok" and "user-agent" in text.lower()
        detail = _fetch_detail(robots)
        if robots.get("status") == "ok" and not robots_ok:
            detail += ", no User-agent line"
        checks.append(_check("robots", robots_ok, detail))
    except Exception as exc:  # noqa: BLE001 - a smoke test reports, it never crashes
        checks.append(_check("error", False, "%s: %s" % (type(exc).__name__, exc)))
    return site


def _load_growthkit() -> Tuple[Optional[Any], Optional[Any], str]:
    """Import growthkit http and html from shared/, or explain why not."""
    if SHARED_DIR not in sys.path:
        sys.path.insert(0, SHARED_DIR)
    try:
        from growthkit import html, http  # noqa: E402
    except SystemExit:
        # growthkit's import guard prints an install hint and exits when
        # requests or beautifulsoup4 is missing.
        return None, None, "requests or beautifulsoup4 is not installed (pip install -r requirements.txt)"
    except Exception as exc:  # noqa: BLE001
        return None, None, "cannot import growthkit: %s: %s" % (type(exc).__name__, exc)
    return http, html, ""


def _host(url: str) -> str:
    return url.split("://", 1)[-1].split("/", 1)[0]


def _escape_annotation(text: str) -> str:
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _summary_table(sites: List[Dict[str, Any]], setup_problem: str) -> str:
    """Markdown for $GITHUB_STEP_SUMMARY."""
    lines = ["## Live smoke test (warn-only)", ""]
    if setup_problem:
        lines.append("Warning: %s" % setup_problem)
        return "\n".join(lines) + "\n"
    lines += ["| Site | Check | Result | Detail |", "|---|---|---|---|"]
    for site in sites:
        for check in site["checks"]:
            detail = check["detail"].replace("|", "/")
            lines.append("| %s | %s | %s | %s |" % (_host(site["url"]), check["check"], check["result"], detail))
    return "\n".join(lines) + "\n"


def run(urls: List[str], timeout: float,
        loader: Callable[[], Tuple[Optional[Any], Optional[Any], str]] = _load_growthkit
        ) -> Tuple[List[Dict[str, Any]], str]:
    """Check every site. Returns (site results, setup problem or "")."""
    http, html, problem = loader()
    if problem:
        return [], problem
    return [check_site(url, http, html, timeout) for url in urls], ""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="smoke_live.py",
        description="Live smoke test of growthkit fetch and page_facts against real sites (warn-only).",
    )
    parser.add_argument("--site", action="append", dest="sites", metavar="URL",
                        help="site to check (repeatable); default: %s" % ", ".join(DEFAULT_SITES))
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help="seconds per request")
    parser.add_argument("--json", action="store_true", help="print the results as JSON on stdout")
    parser.add_argument("--strict", action="store_true", help="exit 1 when any check warns (never in CI)")
    return parser


def main(argv: Optional[List[str]] = None,
         loader: Callable[[], Tuple[Optional[Any], Optional[Any], str]] = _load_growthkit) -> int:
    args = build_parser().parse_args(argv)
    urls = args.sites or list(DEFAULT_SITES)
    started = time.monotonic()
    sites, setup_problem = run(urls, args.timeout, loader)
    warnings = [
        (site, check) for site in sites for check in site["checks"] if check["result"] != PASS
    ]
    in_actions = os.environ.get("GITHUB_ACTIONS") == "true"

    if args.json:
        print(json.dumps({
            "sites": sites,
            "setup_problem": setup_problem or None,
            "warnings": len(warnings) + (1 if setup_problem else 0),
            "elapsed_s": round(time.monotonic() - started, 1),
        }, indent=2))
    else:
        if setup_problem:
            print("WARN  setup: %s" % setup_problem)
        for site in sites:
            for check in site["checks"]:
                print("%-5s %s %s: %s" % (check["result"].upper(), _host(site["url"]), check["check"], check["detail"]))
        print("smoke_live: %d site(s), %d warning(s) in %.1f s (warn-only)."
              % (len(sites), len(warnings) + (1 if setup_problem else 0), time.monotonic() - started))

    if in_actions:
        if setup_problem:
            print("::warning title=Live smoke test::%s" % _escape_annotation(setup_problem), file=sys.stderr)
        for site, check in warnings:
            print("::warning title=Live smoke %s::%s: %s" % (
                _host(site["url"]), check["check"], _escape_annotation(check["detail"])), file=sys.stderr)
        summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary_path:
            try:
                with open(summary_path, "a", encoding="utf-8") as handle:
                    handle.write(_summary_table(sites, setup_problem))
            except OSError:
                pass

    if args.strict and (warnings or setup_problem):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
