"""Offline tests for tools/lint_repo.py.

Most tests build a small, clean fake repo in a temporary folder, break one
thing, and check that the lint reports exactly that. The fake repo is walked
(--no-git), so the tests never depend on git.

Dash characters are built with chr() so this file stays free of them.

Run from the repo root:
    python3 -m unittest discover -s tests -t .
"""

import contextlib
import io
import os
import tempfile
import textwrap
import unittest
from datetime import date

from tests.tools import load_tool

lint = load_tool("lint_repo")

EM = chr(0x2014)
EN = chr(0x2013)
MINUS = chr(0x2212)

GOOD_SKILL = """\
---
name: {name}
description: >
  Audits a SaaS thing from a URL and reports facts with evidence.
  Not for other things (use other-skill).
when_to_use: >
  "audit my thing", "score my thing".
argument-hint: "[audit] <url>"
allowed-tools:
  - Bash(python3 "${{CLAUDE_SKILL_DIR}}/scripts/run.py" *)
metadata:
  version: "1.2.3"
  last_verified: "2026-10"
---

# Thing auditor

Run `python3 "${{CLAUDE_SKILL_DIR}}/scripts/run.py" <url> --json`.
"""

GOOD_AGENT = """\
---
name: helper
description: >
  Agent that combines skills.
model: inherit
tools: Read, Write, Bash
skills:
  - alpha
  - beta
---

# Helper
"""

INSTALL = """\
#!/usr/bin/env bash
for skill_dir in "$TEMP_DIR/$REPO_NAME/skills"/*/; do
    cp -r "$skill_dir" "$SKILLS_DIR/x"
done
echo -e "  ${CYAN}Audits${NC}:"
echo -e "    /alpha audit <url>"
echo -e "  ${YELLOW}/beta${NC}"
echo -e "    helper     does things"
echo -e "  ${BLUE}GitHub:${NC} https://github.com/example/repo"
"""

UNINSTALL = """\
#!/usr/bin/env bash
SKILLS=(
    "alpha"
    "beta"
)

AGENTS=(
    "helper.md"
)

TEMPLATES_LIST=(
    "plan.md"   # a comment
)
"""


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


class FakeRepo(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = self.tmp.name
        self.put("shared/growthkit/__init__.py", '__version__ = "1.2.3"\n')
        self.put("shared/growthkit/http.py", 'BROWSER_UA_UPDATED = "2026-10-01"\n')
        for name in ("alpha", "beta"):
            self.put("skills/%s/SKILL.md" % name, GOOD_SKILL.format(name=name))
            self.put("skills/%s/scripts/run.py" % name, "from __future__ import annotations\n\n"
                     "def run(x: int | None) -> str | None:\n    return None\n")
        self.put("agents/helper.md", GOOD_AGENT)
        self.put("templates/plan.md", "# Plan\n")
        self.put("install.sh", INSTALL)
        self.put("uninstall.sh", UNINSTALL)
        self.put("evals/triggering.jsonl", '{"skill": "alpha", "prompt": "x", "should_trigger": true}\n')
        self.put("data/table.json", '{"a": 1}\n')
        self.put("README.md", "Plain - text.\n")

    def put(self, rel, text):
        write(os.path.join(self.root, *rel.split("/")), text)

    def lint(self, *checks, today=date(2026, 10, 24)):
        files, _source = lint.repo_files(self.root, use_git=False)
        return lint.Linter(self.root, files, today).run(checks or lint.CHECKS)

    def errors(self, *checks):
        return [f for f in self.lint(*checks) if f.level == lint.ERROR]

    def assertOneError(self, check, path, needle, line=None):
        found = self.errors(check)
        self.assertEqual(len(found), 1, found)
        self.assertEqual(found[0].path, path)
        self.assertIn(needle, found[0].message)
        if line is not None:
            self.assertEqual(found[0].line, line)


class CleanRepoTests(FakeRepo):
    def test_clean_repo_has_no_findings(self):
        self.assertEqual(self.lint(), [])

    def test_main_exit_codes(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(lint.main(["--root", self.root, "--no-git", "--today", "2026-10-24"]), 0)
        self.assertIn("0 error(s), 0 warning(s)", out.getvalue())
        self.put("docs/note.md", "a %s b\n" % EM)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(lint.main(["--root", self.root, "--no-git", "--check", "dashes"]), 1)
        self.assertIn("docs/note.md:1: error: [dashes] U+2014 EM DASH", out.getvalue())

    def test_github_annotations(self):
        self.put("docs/note.md", "a %s b\n" % EN)
        out = io.StringIO()
        old = os.environ.get("GITHUB_ACTIONS")
        os.environ["GITHUB_ACTIONS"] = "true"
        try:
            with contextlib.redirect_stdout(out):
                lint.main(["--root", self.root, "--no-git", "--check", "dashes"])
        finally:
            if old is None:
                del os.environ["GITHUB_ACTIONS"]
            else:
                os.environ["GITHUB_ACTIONS"] = old
        self.assertIn("::error file=docs/note.md,line=1,title=lint_repo dashes::U+2013 EN DASH", out.getvalue())


class DashTests(FakeRepo):
    def test_em_and_en_dash_are_errors_with_line_and_column(self):
        self.put("skills/alpha/references/guide.md", "ok\nfirst %s second %s third\n" % (EM, EN))
        found = self.errors("dashes")
        self.assertEqual([(f.path, f.line) for f in found], [("skills/alpha/references/guide.md", 2)] * 2)
        messages = " ".join(f.message for f in found)
        self.assertIn("U+2014 EM DASH at column 7", messages)
        self.assertIn("U+2013 EN DASH", messages)

    def test_minus_sign_is_a_warning(self):
        self.put("notes.md", "score = 100 %s risk\n" % MINUS)
        found = self.lint("dashes")
        self.assertEqual([(f.level, f.line) for f in found], [(lint.WARNING, 1)])

    def test_generated_outputs_are_skipped(self):
        self.put("examples/case/reports/scan.md", "Docs %s alternative\n" % EN)
        self.put("growth-reports/2026-10-24-alpha-x.md", "x %s y\n" % EM)
        self.put("app/growth-reports/old.md", "x %s y\n" % EM)
        self.assertEqual(self.lint("dashes"), [])
        self.put("examples/case/README.md", "Hand-written %s here\n" % EM)
        self.assertOneError("dashes", "examples/case/README.md", "EM DASH")

    def test_python_escapes_are_fine_but_literals_are_not(self):
        self.put("tests/t.py", 'TEXT = "a \\u2014 b"\n')
        self.assertEqual(self.lint("dashes"), [])
        self.put("tests/t.py", 'TEXT = "a %s b"\n' % EM)
        self.assertOneError("dashes", "tests/t.py", "EM DASH", line=1)

    def test_binary_and_non_utf8_files(self):
        with open(os.path.join(self.root, "logo.png"), "wb") as handle:
            handle.write(EM.encode("utf-8") + b"\0")
        with open(os.path.join(self.root, "legacy.txt"), "wb") as handle:
            handle.write(b"caf\xe9 \x97 x")
        found = self.lint("dashes")
        self.assertEqual([(f.level, f.path) for f in found], [(lint.WARNING, "legacy.txt")])

    def test_findings_are_capped_per_file(self):
        self.put("big.md", ("x %s y\n" % EM) * 30)
        found = self.errors("dashes")
        self.assertEqual(len(found), lint.MAX_DASH_LINES_PER_FILE + 1)
        self.assertIn("10 more dash finding(s)", found[-1].message)


class FrontmatterTests(FakeRepo):
    def skill(self, text, name="alpha"):
        self.put("skills/%s/SKILL.md" % name, textwrap.dedent(text))

    def test_name_must_match_folder(self):
        self.put("skills/alpha/SKILL.md", GOOD_SKILL.format(name="alpha-v2"))
        self.assertOneError("frontmatter", "skills/alpha/SKILL.md", "but the folder is 'alpha'", line=2)

    def test_name_rules(self):
        self.put("skills/my--claude/SKILL.md", GOOD_SKILL.format(name="my--claude"))
        self.put("skills/my--claude/scripts/run.py", "")
        messages = [f.message for f in self.errors("frontmatter")]
        self.assertTrue(any("single hyphens" in m for m in messages), messages)
        self.assertTrue(any("must not contain 'claude'" in m for m in messages), messages)

    def test_missing_description(self):
        self.skill("""\
            ---
            name: alpha
            metadata:
              version: "1.2.3"
            ---
            """)
        self.assertOneError("frontmatter", "skills/alpha/SKILL.md", "description is missing")

    def test_description_over_limit_and_house_target(self):
        long_text = "word " * 210   # 1,049 characters
        self.skill("""\
            ---
            name: alpha
            description: >
              %s
            metadata:
              version: "1.2.3"
            ---
            """ % long_text)
        self.assertOneError("frontmatter", "skills/alpha/SKILL.md", "description is 1049 characters; the limit is 1024")
        self.skill("""\
            ---
            name: alpha
            description: %s
            metadata:
              version: "1.2.3"
            ---
            """ % ("word " * 110).strip())
        found = self.lint("frontmatter")
        self.assertEqual([f.level for f in found], [lint.WARNING])
        self.assertIn("house target is 500", found[0].message)

    def test_combined_length_with_when_to_use(self):
        self.skill("""\
            ---
            name: alpha
            description: Short description.
            when_to_use: >
              %s
            metadata:
              version: "1.2.3"
            ---
            """ % ("phrase " * 230))
        self.assertOneError("frontmatter", "skills/alpha/SKILL.md", "Claude Code cuts the listing at 1536")

    def test_xml_tags_in_description(self):
        self.skill("""\
            ---
            name: alpha
            description: Audits a <url> for things.
            metadata:
              version: "1.2.3"
            ---
            """)
        self.assertOneError("frontmatter", "skills/alpha/SKILL.md", "XML tags")

    def test_unquoted_colon_breaks_yaml(self):
        self.skill("""\
            ---
            name: alpha
            description: Audits pages: CTA, proof and copy.
            ---
            """)
        found = self.errors("frontmatter")
        self.assertEqual(len(found), 1, found)
        self.assertIn("frontmatter does not parse", found[0].message)
        self.assertIn("contains ': '", found[0].message)
        self.assertEqual(found[0].line, 3)

    def test_no_frontmatter_or_unclosed(self):
        self.put("skills/alpha/SKILL.md", "# Alpha\n")
        self.assertOneError("frontmatter", "skills/alpha/SKILL.md", "first line must be '---'", line=1)
        self.put("skills/alpha/SKILL.md", "---\nname: alpha\n")
        self.assertOneError("frontmatter", "skills/alpha/SKILL.md", "no closing '---'")

    def test_missing_skill_md(self):
        os.remove(os.path.join(self.root, "skills", "beta", "SKILL.md"))
        messages = [(f.check, f.path, f.message) for f in self.errors("frontmatter")]
        self.assertIn(("frontmatter", "skills/beta", "skill folder has no SKILL.md"), messages)

    def test_metadata_version_rules(self):
        self.put("skills/alpha/SKILL.md", GOOD_SKILL.format(name="alpha").replace('"1.2.3"', '"1.0.0"'))
        self.assertOneError("frontmatter", "skills/alpha/SKILL.md", "growthkit __version__ is '1.2.3'")
        self.put("skills/alpha/SKILL.md", GOOD_SKILL.format(name="alpha").replace('"1.2.3"', "1.2"))
        self.assertOneError("frontmatter", "skills/alpha/SKILL.md", "metadata.version must be a quoted string")

    def test_missing_metadata_is_one_warning(self):
        for name in ("alpha", "beta"):
            text = GOOD_SKILL.format(name=name)
            text = text.replace('metadata:\n  version: "1.2.3"\n  last_verified: "2026-10"\n', "")
            self.put("skills/%s/SKILL.md" % name, text)
        found = self.lint("frontmatter")
        self.assertEqual(len(found), 1, found)
        self.assertEqual(found[0].level, lint.WARNING)
        self.assertIn("not set in 2 of 2 skills: alpha, beta", found[0].message)

    def test_forbidden_keys(self):
        self.put("skills/alpha/SKILL.md", GOOD_SKILL.format(name="alpha").replace(
            "argument-hint", 'version: "1.2.3"\nargument-hint'))
        self.assertOneError("frontmatter", "skills/alpha/SKILL.md", "do not use the 'version' key")

    def test_allowed_tools_rules(self):
        base = GOOD_SKILL.format(name="alpha")
        self.put("skills/alpha/SKILL.md", base.replace(
            '  - Bash(python3 "${CLAUDE_SKILL_DIR}/scripts/run.py" *)', "  - Bash(python3 *)"))
        self.assertOneError("frontmatter", "skills/alpha/SKILL.md", "is not of the form")
        self.put("skills/alpha/SKILL.md", base.replace("scripts/run.py\" *)", "scripts/gone.py\" *)"))
        self.assertOneError("frontmatter", "skills/alpha/SKILL.md", "grants scripts/gone.py")

    def test_body_script_reference_must_exist(self):
        self.put("skills/alpha/SKILL.md", GOOD_SKILL.format(name="alpha") +
                 '\nThen `python3 "${CLAUDE_SKILL_DIR}/scripts/missing.py"`.\n')
        self.assertOneError("frontmatter", "skills/alpha/SKILL.md", "runs scripts/missing.py")

    def test_skill_too_long(self):
        self.put("skills/alpha/SKILL.md", GOOD_SKILL.format(name="alpha") + "line\n" * 490)
        self.assertOneError("frontmatter", "skills/alpha/SKILL.md", "lines; keep it at 500 or less")

    def test_agent_checks(self):
        self.put("agents/helper.md", GOOD_AGENT.replace("name: helper", "name: helper-two")
                 .replace("  - beta", "  - gamma"))
        messages = sorted(f.message for f in self.errors("frontmatter"))
        self.assertEqual(len(messages), 2, messages)
        self.assertIn("file is helper.md", messages[0])
        self.assertIn("skills lists 'gamma'", messages[1])


class YamlSubsetTests(unittest.TestCase):
    def parse(self, text, dedent=True):
        text = textwrap.dedent(text) if dedent else text
        lines = [(n + 2, line) for n, line in enumerate(text.split("\n"))]
        return lint.parse_yaml_subset(lines)[0]

    def test_folded_and_literal_blocks(self):
        data = self.parse("""\
            a: >
              one
              two

              three
            b: >-
              x
              y
            c: |
              line 1
              line 2
            """)
        self.assertEqual(data["a"], "one two\nthree\n")
        self.assertEqual(data["b"], "x y")
        self.assertEqual(data["c"], "line 1\nline 2\n")

    def test_scalars_lists_and_mappings(self):
        data = self.parse("""\
            s1: 'it''s'
            s2: "a \\"b\\" \\u0041"
            plain: hello world # comment
            num: 2.0
            flag: no
            flow: [a, "b c"]
            metadata:
              version: "2.0.0"
              other: 3
            skills:
              - one
              - "two"
            hooks:
              PreToolUse:
                - matcher: Bash
            multi: first line
              continues here
            """)
        self.assertEqual(data["s1"], "it's")
        self.assertEqual(data["s2"], 'a "b" A')
        self.assertEqual(data["plain"], "hello world")
        self.assertEqual(data["num"], 2.0)
        self.assertIs(data["flag"], False)
        self.assertEqual(data["flow"], ["a", "b c"])
        self.assertEqual(data["metadata"], {"version": "2.0.0", "other": 3})
        self.assertEqual(data["skills"], ["one", "two"])
        self.assertIsInstance(data["hooks"], lint.Raw)
        self.assertEqual(data["multi"], "first line continues here")

    def test_plain_scalar_on_following_lines(self):
        data = self.parse("""\
            description:
              Audits pages
              and more.
            quoted:
              "on the next line"
            next: 1
            """)
        self.assertEqual(data["description"], "Audits pages and more.")
        self.assertEqual(data["quoted"], "on the next line")
        self.assertEqual(data["next"], 1)

    def test_errors(self):
        for text, needle in (
            ("a: 1\na: 2\n", "duplicate key"),
            ('a: "open\n', "unterminated"),
            ("a: x: y\n", "contains ': '"),
            ("  a: 1\n", "unexpected indentation"),
            ("a: @x\n", "cannot start with"),
            ("a: {b: 1}\n", "flow mappings"),
            ("metadata:\n\tversion: x\n", "tabs"),
            ("just text\n", "expected 'key: value'"),
        ):
            with self.assertRaises(lint.YamlError, msg=text) as ctx:
                self.parse(text, dedent=False)
            self.assertIn(needle, ctx.exception.message, text)


class ListTests(FakeRepo):
    def test_uninstall_missing_skill(self):
        self.put("skills/gamma/SKILL.md", GOOD_SKILL.format(name="gamma"))
        self.put("skills/gamma/scripts/run.py", "")
        self.put("install.sh", INSTALL + 'echo -e "    /gamma run"\n')
        self.assertOneError("lists", "uninstall.sh", "SKILLS in uninstall.sh is missing 'gamma'", line=2)

    def test_uninstall_extra_entries(self):
        self.put("uninstall.sh", UNINSTALL.replace('"beta"', '"beta"\n    "old-skill"')
                 .replace('"plan.md"', '"plan.md" "gone.md"'))
        messages = sorted(f.message for f in self.errors("lists"))
        self.assertEqual(len(messages), 2, messages)
        self.assertIn("SKILLS in uninstall.sh lists 'old-skill'", messages[0])
        self.assertIn("TEMPLATES_LIST in uninstall.sh lists 'gone.md'", messages[1])

    def test_install_menu(self):
        self.put("install.sh", INSTALL.replace("/beta", "/betta"))
        messages = sorted(f.message for f in self.errors("lists"))
        self.assertEqual(len(messages), 2, messages)
        self.assertIn("does not show /beta", messages[0])
        self.assertIn("shows /betta, but skills/betta/ does not exist", messages[1])

    def test_install_agent_and_glob(self):
        self.put("install.sh", INSTALL.replace("helper", "assistant").replace('skills"/*/', "skills/alpha"))
        messages = sorted(f.message for f in self.errors("lists"))
        self.assertEqual(len(messages), 2, messages)
        self.assertIn("neither lists skills", messages[0])
        self.assertIn("does not mention agent 'helper'", messages[1])

    def test_shell_arrays_parser(self):
        arrays = lint.shell_arrays('A=("x" y)\nB=(\n  "p q"  # note\n  r\n)\n')
        self.assertEqual(arrays["A"], (1, ["x", "y"]))
        self.assertEqual(arrays["B"], (2, ["p q", "r"]))


class PythonTests(FakeRepo):
    def test_syntax_error(self):
        self.put("tools/broken.py", "def f(:\n    pass\n")
        self.assertOneError("python", "tools/broken.py", "does not compile", line=1)

    def test_pep604_annotation_without_future_import(self):
        self.put("tools/new.py", "def f(x: int | None) -> None:\n    return None\n")
        self.assertOneError("python", "tools/new.py", "raises TypeError on Python 3.9", line=1)

    def test_pep604_class_and_module_annotations(self):
        self.put("tools/new.py", "from typing import Dict\n\nclass A:\n    x: Dict[str, int | None] = {}\n")
        self.assertOneError("python", "tools/new.py", "raises TypeError", line=4)

    def test_local_annotations_and_strings_are_fine(self):
        self.put("tools/ok.py", textwrap.dedent("""\
            def f() -> "int | None":
                y: int | None = None
                flags = 1 | 2
                return y
            """))
        self.assertEqual(self.errors("python"), [])

    def test_class_inside_function_is_checked(self):
        self.put("tools/new.py", "def f():\n    class A:\n        x: int | None = None\n    return A\n")
        self.assertOneError("python", "tools/new.py", "raises TypeError", line=3)

    def test_invalid_escape_is_a_warning(self):
        self.put("tools/esc.py", 'import re\nPATTERN = re.compile("\\d+")\n')
        found = self.lint("python")
        self.assertEqual([(f.level, f.line) for f in found], [(lint.WARNING, 2)])
        self.assertIn("invalid escape", found[0].message)


class JsonTests(FakeRepo):
    def test_invalid_json(self):
        self.put("data/table.json", '{"a": 1,}\n')
        self.assertOneError("json", "data/table.json", "invalid JSON", line=1)

    def test_invalid_jsonl_line(self):
        self.put("evals/triggering.jsonl", '{"skill": "alpha"}\n{oops}\n')
        self.assertOneError("json", "evals/triggering.jsonl", "invalid JSON line", line=2)

    def test_eval_row_for_unknown_skill(self):
        self.put("evals/triggering.jsonl", '{"skill": "alpha"}\n\n{"skill": "ghost"}\n')
        self.assertOneError("json", "evals/triggering.jsonl", "names skill 'ghost'", line=3)


class FreshnessTests(FakeRepo):
    def test_old_browser_ua_is_a_warning(self):
        self.assertEqual(self.lint("freshness"), [])
        found = self.lint("freshness", today=date(2027, 1, 1))
        self.assertEqual([(f.level, f.line) for f in found], [(lint.WARNING, 1)])
        self.assertIn("92 days ago", found[0].message)


class RealRepoTests(unittest.TestCase):
    def test_lint_source_has_no_literal_dashes(self):
        path = os.path.join(lint.REPO_ROOT, "tools", "lint_repo.py")
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        self.assertEqual([c for c in text if ord(c) > 127], [])


if __name__ == "__main__":
    unittest.main()
