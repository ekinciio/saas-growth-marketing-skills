"""Offline tests for growthkit.cli (input handling, envelope, exit codes, coercion).

Run from the repo root:
    python3 -m unittest discover -s tests -t .
"""

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest import mock

from tests import _paths
from growthkit import cli  # noqa: E402


class _NoReadStdin(io.StringIO):
    """A stdin that fails the test if anything reads it."""

    def read(self, *args):
        raise AssertionError("stdin was read without '-'")

    def isatty(self):
        return False


class _PipeStdin(io.StringIO):
    def isatty(self):
        return False


def capture(func, *args, **kwargs):
    """Run func and return (result, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        result = func(*args, **kwargs)
    return result, out.getvalue(), err.getvalue()


class LooksLikeUrlTests(unittest.TestCase):
    def test_table(self):
        cases = {
            "https://linear.app": True,
            "http://localhost:8000": True,
            "linear.app": True,
            "notion.com/pricing": True,
            "www.acme.co.uk": True,
            "page.html": False,
            "data.json": False,
            "notes.md": False,
            "./page.html": False,
            "/tmp/x": False,
            "--json": False,
            "not a url": False,
            "": False,
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(cli.looks_like_url(text), expected)


class ResolveInputTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_no_input_is_a_usage_error_and_never_reads_stdin(self):
        with mock.patch.object(sys, "stdin", _NoReadStdin()):
            with self.assertRaises(cli.UsageError) as ctx:
                cli.resolve_input(None)
        self.assertIn("--demo", str(ctx.exception))

    def test_demo_needs_no_input(self):
        with mock.patch.object(sys, "stdin", _NoReadStdin()):
            self.assertEqual(cli.resolve_input(None, demo=True)["kind"], "demo")

    def test_dash_reads_stdin(self):
        with mock.patch.object(sys, "stdin", _PipeStdin('{"a": 1}')):
            source = cli.resolve_input("-")
        self.assertEqual(source, {"kind": "stdin", "value": "-", "text": '{"a": 1}'})

    def test_empty_stdin_is_a_usage_error(self):
        with mock.patch.object(sys, "stdin", _PipeStdin("  \n")):
            with self.assertRaises(cli.UsageError):
                cli.resolve_input("-")

    def test_stdin_not_allowed(self):
        with self.assertRaises(cli.UsageError):
            cli.resolve_input("-", allow_stdin=False)

    def test_file_input(self):
        path = os.path.join(self.tmp.name, "page.html")
        with open(path, "wb") as handle:
            handle.write("\ufeff<h1>caf\xe9</h1>".encode("utf-8"))
        source = cli.resolve_input(path)
        self.assertEqual(source["kind"], "file")
        self.assertEqual(source["text"], "<h1>caf\xe9</h1>")

    def test_url_input(self):
        self.assertEqual(cli.resolve_input("linear.app")["kind"], "url")
        with self.assertRaises(cli.UsageError):
            cli.resolve_input("linear.app", allow_url=False)

    def test_missing_file_message(self):
        with self.assertRaises(cli.UsageError) as ctx:
            cli.resolve_input("missing-page.html")
        self.assertIn("File not found", str(ctx.exception))
        self.assertNotIn("https://", str(ctx.exception))  # no "website" hint for a file name
        with self.assertRaises(cli.UsageError):
            cli.resolve_input(self.tmp.name)  # a folder


class LoadJsonInputTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def write(self, text):
        path = os.path.join(self.tmp.name, "in.json")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
        return path

    def test_object(self):
        data, source = cli.load_json_input(self.write('{"mrr": "12k"}'))
        self.assertEqual(data, {"mrr": "12k"})
        self.assertEqual(source["kind"], "file")

    def test_wrong_top_level_type(self):
        with self.assertRaises(cli.UsageError) as ctx:
            cli.load_json_input(self.write("[1, 2]"))
        self.assertIn("Expected a JSON object", str(ctx.exception))

    def test_invalid_json(self):
        with self.assertRaises(cli.UsageError) as ctx:
            cli.load_json_input(self.write("{not json"))
        self.assertIn("Invalid JSON", str(ctx.exception))

    def test_demo(self):
        data, source = cli.load_json_input(None, demo=True, demo_data={"x": 1})
        self.assertEqual((data, source["kind"]), ({"x": 1}, "demo"))


class RunTests(unittest.TestCase):
    def test_json_mode_prints_only_one_json_document(self):
        run = cli.Run("tool", json_mode=True)
        _, _, log_err = capture(run.log, "progress line")
        self.assertEqual(log_err, "[tool] progress line\n")
        code, out, err = capture(run.emit, {"facts": {"words": 3}})
        self.assertEqual(code, cli.EXIT_OK)
        envelope = json.loads(out)
        self.assertEqual(envelope["status"], "ok")
        self.assertEqual(envelope["errors"], [])
        self.assertEqual(envelope["notes"], [])
        self.assertEqual(envelope["facts"], {"words": 3})
        self.assertEqual(envelope["tool"], "tool")
        self.assertIn("version", envelope)
        self.assertEqual(out.count("\n"), 1)
        self.assertNotIn("progress", out)

    def test_errors_make_a_partial_run(self):
        run = cli.Run("tool", json_mode=True)
        _, _, err = capture(run.error, "robots.txt unreachable")
        self.assertIn("robots.txt unreachable", err)
        code, out, _ = capture(run.emit, {"notes": ["used cached sitemap"], "errors": ["llms.txt timed out"]})
        envelope = json.loads(out)
        self.assertEqual(code, cli.EXIT_PARTIAL)
        self.assertEqual(envelope["status"], "partial")
        self.assertEqual(envelope["errors"], ["robots.txt unreachable", "llms.txt timed out"])
        self.assertEqual(envelope["notes"], ["used cached sitemap"])

    def test_explicit_statuses_map_to_exit_codes(self):
        for status, code in (("ok", 0), ("partial", 4), ("unreachable", 3), ("blocked", 3),
                             ("nothing_to_analyze", 5), ("usage_error", 2)):
            run = cli.Run("tool", json_mode=True)
            result, out, _ = capture(run.emit, {}, status)
            self.assertEqual(result, code)
            self.assertEqual(json.loads(out)["status"], status)

    def test_fail(self):
        run = cli.Run("tool", json_mode=True)
        code, out, err = capture(run.fail, cli.STATUS_BLOCKED, "g2.com blocked the request")
        self.assertEqual(code, 3)
        self.assertEqual(json.loads(out)["errors"], ["g2.com blocked the request"])

    def test_demo_is_labelled(self):
        args = cli.build_parser("x").parse_args(["--demo", "--json"])
        run, _, err = capture(cli.Run, "tool", args)
        self.assertIn(cli.DEMO_BANNER, err)
        _, out, _ = capture(run.emit, {"score": 1})
        envelope = json.loads(out)
        self.assertTrue(envelope["demo"])
        self.assertIn(cli.DEMO_BANNER, envelope["notes"])
        human, _, _ = capture(cli.Run, "tool", demo=True, json_mode=False)
        _, out, _ = capture(human.emit, {}, None, "report body")
        self.assertTrue(out.startswith("=" * 70 + "\n  " + cli.DEMO_BANNER))
        self.assertIn("report body", out)

    def test_human_formatter_and_out_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_path = os.path.join(tmp, "nested", "result.json")
            run = cli.Run("tool", json_mode=False, out=out_path)
            code, out, err = capture(run.emit, {"score": 7}, None, lambda env: "Score: %d" % env["score"])
            self.assertEqual(code, 0)
            self.assertEqual(out.strip(), "Score: 7")
            with open(out_path, encoding="utf-8") as handle:
                self.assertEqual(json.load(handle)["score"], 7)
            self.assertIn("Saved JSON", err)

    def test_non_ascii_output(self):
        run = cli.Run("tool", json_mode=True)
        _, out, _ = capture(run.emit, {"title": "Caf\xe9 \u2192 Men\xfc"})
        self.assertEqual(json.loads(out)["title"], "Caf\xe9 \u2192 Men\xfc")

    def test_nan_and_infinity_become_null(self):
        run = cli.Run("tool", json_mode=True)
        _, out, _ = capture(run.emit, {"ratio": float("nan"), "nested": {"x": [float("inf"), 1.5]}})
        self.assertNotIn("NaN", out)
        self.assertNotIn("Infinity", out)
        envelope = json.loads(out)
        self.assertIsNone(envelope["ratio"])
        self.assertEqual(envelope["nested"]["x"], [None, 1.5])

    def test_non_json_values_are_serialized(self):
        import datetime
        run = cli.Run("tool", json_mode=True)
        _, out, _ = capture(run.emit, {"when": datetime.date(2026, 10, 24), "tags": {"a"}})
        envelope = json.loads(out)
        self.assertEqual(envelope["when"], "2026-10-24")
        self.assertEqual(envelope["tags"], ["a"])


class ParserTests(unittest.TestCase):
    def test_shared_flags(self):
        args = cli.build_parser("x").parse_args(["linear.app", "--json", "--out", "r.json", "--timeout", "5"])
        self.assertEqual((args.input, args.json, args.out, args.demo, args.timeout),
                         ("linear.app", True, "r.json", False, 5.0))

    def test_usage_error_with_json_prints_envelope(self):
        parser = cli.build_parser("x", prog="tool")
        with mock.patch.object(sys, "argv", ["tool", "--json", "--bogus"]):
            with self.assertRaises(SystemExit) as ctx:
                capture(parser.parse_args, ["--json", "--bogus"])
        self.assertEqual(ctx.exception.code, 2)

    def test_usage_error_output(self):
        parser = cli.build_parser("x", prog="tool")
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(sys, "argv", ["tool", "--json", "--bogus"]):
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                with self.assertRaises(SystemExit):
                    parser.parse_args(["--json", "--bogus"])
        envelope = json.loads(out.getvalue())
        self.assertEqual(envelope["status"], "usage_error")
        self.assertIs(envelope["demo"], False)
        self.assertIn("--bogus", envelope["errors"][0])
        self.assertIn("usage:", err.getvalue())

    def test_usage_error_uses_the_parsed_args_not_sys_argv(self):
        parser = cli.build_parser("x", prog="tool")
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(sys, "argv", ["tool"]):  # no --json here
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                with self.assertRaises(SystemExit):
                    parser.parse_args(["--json", "--bogus"])
        self.assertEqual(json.loads(out.getvalue())["status"], "usage_error")

    def test_timeout_must_be_positive(self):
        parser = cli.build_parser("x", prog="tool")
        for bad in ("0", "-1", "abc", "nan"):
            with self.subTest(timeout=bad):
                with contextlib.redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit) as ctx:
                        parser.parse_args(["linear.app", "--timeout", bad])
                self.assertEqual(ctx.exception.code, 2)

    def test_import_or_exit(self):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(sys, "argv", ["tool"]):
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                with self.assertRaises(SystemExit) as ctx:
                    cli.import_or_exit("growthkit_no_such_module", "nosuchpkg")
        self.assertEqual(ctx.exception.code, 2)
        self.assertIn("pip install", err.getvalue())
        self.assertEqual(out.getvalue(), "")
        self.assertIs(cli.import_or_exit("json"), json)


class FetchOutcomeTests(unittest.TestCase):
    def test_mapping(self):
        cases = [
            ({"status": "ok"}, "ok"),
            ({"status": "too_large", "bytes": 5000000}, "partial"),
            ({"status": "js_shell", "js_shell_signals": {"visible_words": 3}}, "nothing_to_analyze"),
            ({"status": "not_html", "content_type": "application/pdf"}, "nothing_to_analyze"),
            ({"status": "blocked", "http_status": 403, "bot_protection": {"vendor": "datadome"}}, "blocked"),
            ({"status": "http_error", "http_status": 404, "error": "HTTP 404"}, "unreachable"),
            ({"status": "unreachable", "error": "DNS lookup failed"}, "unreachable"),
        ]
        for result, expected in cases:
            with self.subTest(status=result["status"]):
                status, message = cli.fetch_outcome(dict(result, url="https://x.test/"))
                self.assertEqual(status, expected)
                if expected != "ok":
                    self.assertTrue(message)
        status, message = cli.fetch_outcome({"status": "not_html", "http_status": 200, "bytes": 0,
                                              "content_type": "text/html", "url": "https://x.test/"})
        self.assertEqual(status, "nothing_to_analyze")
        self.assertIn("empty body", message)
        status, message = cli.fetch_outcome({"status": "blocked", "http_status": 403,
                                              "bot_protection": {"vendor": "datadome"}, "url": "https://g2.test/"})
        self.assertIn("datadome", message)
        self.assertEqual(cli.exit_code_for(status), 3)


class FactsOutcomeTests(unittest.TestCase):
    def test_mapping(self):
        shell = {"is_js_shell": True, "word_count": 3, "headings": {"h1": []}}
        self.assertEqual(cli.facts_outcome(shell)[0], "nothing_to_analyze")
        empty = {"is_js_shell": False, "word_count": 0, "headings": {"h1": []}}
        self.assertEqual(cli.facts_outcome(empty)[0], "nothing_to_analyze")
        thin = {"is_js_shell": False, "word_count": 40, "headings": {"h1": []}}
        status, message = cli.facts_outcome(thin)
        self.assertEqual(status, "ok")
        self.assertIn("Thin page", message)
        short_with_h1 = {"is_js_shell": False, "word_count": 40, "headings": {"h1": ["Payroll"]}}
        self.assertEqual(cli.facts_outcome(short_with_h1), ("ok", ""))


class CoercionTests(unittest.TestCase):
    def test_is_missing(self):
        for value in (None, "", "  ", "skip", "N/A", "n/a", "unknown", "Not sure", "idk", "-", "null", float("nan")):
            with self.subTest(value=value):
                self.assertTrue(cli.is_missing(value))
        for value in (0, "0", False, "no", [], "abc"):
            with self.subTest(value=value):
                self.assertFalse(cli.is_missing(value))

    def test_to_bool(self):
        truthy = (True, 1, "yes", "Y", "true", "TRUE", "on", "Yes - card required")
        falsy = (False, 0, "no", "No", "false", "f", "0", "off", "no, email only")
        for value in truthy:
            with self.subTest(value=value):
                self.assertIs(cli.to_bool(value), True)
        for value in falsy:
            with self.subTest(value=value):
                self.assertIs(cli.to_bool(value), False)
        for value in ("skip", "", None, "not sure", "no idea"):
            with self.subTest(value=value):
                self.assertIsNone(cli.to_bool(value))
        for value in ("maybe", 2, "nope sometimes", [1]):
            with self.subTest(value=value):
                with self.assertRaises(cli.CoercionError):
                    cli.to_bool(value, field="requires_card")

    def test_to_number(self):
        cases = {
            "42": 42.0, 42: 42.0, 3.5: 3.5, "$1,200": 1200.0, "1,200,000.50": 1200000.5,
            "12k": 12000.0, "1.5M": 1500000.0, "2,5": 2.5, "25%": 25.0, "1/4": 0.25,
            " ~ 30 ": 30.0, "-5": -5.0, "\u20ac99": 99.0, "\u20ba1,250": 1250.0, ".5": 0.5,
            "skip": None, "": None, None: None,
        }
        for value, expected in cases.items():
            with self.subTest(value=value):
                self.assertEqual(cli.to_number(value), expected)

    def test_to_number_rejects(self):
        for value in ("abc", "10-20", True, "1/0", float("inf"), {"a": 1}):
            with self.subTest(value=value):
                with self.assertRaises(cli.CoercionError):
                    cli.to_number(value, field="mrr")
        with self.assertRaises(cli.CoercionError) as ctx:
            cli.to_number("-5", field="signups", minimum=0)
        self.assertIn("signups", str(ctx.exception))
        self.assertIn("at least 0", str(ctx.exception))

    def test_to_int(self):
        self.assertEqual(cli.to_int("1,200"), 1200)
        self.assertEqual(cli.to_int(7.0), 7)
        with self.assertRaises(cli.CoercionError):
            cli.to_int("2.5")

    def test_to_percent(self):
        cases = {"25%": 25.0, "25": 25.0, 25: 25.0, "1/4": 25.0, 0.8: 0.8, "0.8%": 0.8, "3 / 4": 75.0,
                 "n/a": None}
        for value, expected in cases.items():
            with self.subTest(value=value):
                self.assertEqual(cli.to_percent(value), expected)
        self.assertEqual(cli.to_percent(0.25, assume_fraction=True), 25.0)
        self.assertEqual(cli.to_percent("0.25", assume_fraction=True), 25.0)
        self.assertEqual(cli.to_percent("0.25%", assume_fraction=True), 0.25)
        # "percent" spelled out counts as a percent sign, never as a fraction.
        self.assertEqual(cli.to_percent("0.5 percent", assume_fraction=True), 0.5)
        self.assertEqual(cli.to_percent("25 percent"), 25.0)
        with self.assertRaises(cli.CoercionError):
            cli.to_percent("120%", maximum=100)

    def test_coerce_record(self):
        schema = {"has_trial": "bool", "monthly_churn": "percent", "signups": "int", "plan": "str",
                  "mrr": lambda v, field=None: cli.to_number(v, field=field, minimum=0)}
        payload = {"has_trial": "no", "monthly_churn": "3%", "signups": "1,200", "plan": " Pro ",
                   "mrr": "-10", "extra": 1}
        clean, errors, unknown = cli.coerce_record(payload, schema)
        self.assertEqual(clean, {"has_trial": False, "monthly_churn": 3.0, "signups": 1200,
                                 "plan": "Pro", "mrr": None})
        self.assertEqual(len(errors), 1)
        self.assertTrue(errors[0].startswith("mrr:"))
        self.assertEqual(unknown, ["extra"])
        clean, errors, _ = cli.coerce_record({}, {"has_trial": "bool"})
        self.assertEqual((clean, errors), ({"has_trial": None}, []))
        with self.assertRaises(cli.UsageError):
            cli.coerce_record([1, 2], schema)


SCRIPT = textwrap.dedent('''
    import sys
    sys.path.insert(0, {shared!r})
    from growthkit import cli

    def main():
        parser = cli.build_parser("demo tool", prog="demo_tool")
        args = parser.parse_args()
        run = cli.Run("demo_tool", args)
        try:
            data, source = cli.load_json_input(args.input, demo=args.demo, demo_data={{"mrr": "1k"}})
        except cli.UsageError as exc:
            return run.fail(cli.STATUS_USAGE, str(exc))
        return run.emit({{"mrr": cli.to_number(data.get("mrr")), "source": source["kind"]}})

    sys.exit(main())
''')


class SubprocessContractTests(unittest.TestCase):
    """The real process contract: non-TTY stdin, exit codes, stdout is JSON only."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.script = os.path.join(cls.tmp.name, "demo_tool.py")
        with open(cls.script, "w", encoding="utf-8") as handle:
            handle.write(SCRIPT.format(shared=_paths.SHARED_DIR))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_tool(self, *args, stdin=subprocess.DEVNULL, input_text=None):
        return subprocess.run(
            [sys.executable, self.script] + list(args),
            stdin=None if input_text is not None else stdin,
            input=input_text, capture_output=True, text=True, timeout=30,
        )

    def test_no_input_with_closed_stdin_exits_2_without_hanging(self):
        proc = self.run_tool("--json")
        self.assertEqual(proc.returncode, 2)
        envelope = json.loads(proc.stdout)
        self.assertEqual(envelope["status"], "usage_error")
        self.assertNotIn("Traceback", proc.stderr)

    def test_open_pipe_without_dash_is_not_read(self):
        # A pipe that never closes would hang a script that reads stdin implicitly.
        # stdin stays open for the whole run; wait() fails after 30 s if the
        # script blocks on it.
        proc = subprocess.Popen([sys.executable, self.script, "--json"], stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            proc.wait(timeout=30)
            out = proc.stdout.read()
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            self.fail("script blocked reading stdin")
        finally:
            proc.stdin.close()
            proc.stdout.close()
            proc.stderr.close()
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(json.loads(out)["status"], "usage_error")

    def test_explicit_demo(self):
        proc = self.run_tool("--demo", "--json")
        self.assertEqual(proc.returncode, 0)
        envelope = json.loads(proc.stdout)
        self.assertTrue(envelope["demo"])
        self.assertEqual(envelope["mrr"], 1000.0)

    def test_stdin_with_dash(self):
        proc = self.run_tool("-", "--json", input_text='{"mrr": "$2,500"}')
        self.assertEqual(proc.returncode, 0, proc.stderr)
        envelope = json.loads(proc.stdout)
        self.assertEqual((envelope["mrr"], envelope["source"]), (2500.0, "stdin"))

    def test_bad_flag_in_json_mode(self):
        proc = self.run_tool("--json", "--nope")
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(json.loads(proc.stdout)["status"], "usage_error")


if __name__ == "__main__":
    unittest.main()
