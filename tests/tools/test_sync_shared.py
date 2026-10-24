"""Offline tests for tools/sync_shared.py.

Every test builds a small fake repo in a temporary folder and points the
tool at it with --root, so the real skills/ folders are never touched.

Run from the repo root:
    python3 -m unittest discover -s tests -t .
"""

import contextlib
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

from tests import _paths
from tests.tools import load_tool

sync_shared = load_tool("sync_shared")


def write(path, text, mode="w"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, mode) as handle:
        handle.write(text)


def read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


class FakeRepo(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = self.tmp.name
        self.src = os.path.join(self.root, "shared", "growthkit")
        write(os.path.join(self.src, "__init__.py"), '__version__ = "9.9.9"\n')
        write(os.path.join(self.src, "cli.py"), "from . import __version__\n")
        # Litter that must never be copied.
        write(os.path.join(self.src, "__pycache__", "cli.cpython-39.pyc"), b"\0\1", mode="wb")
        write(os.path.join(self.src, ".DS_Store"), b"\0", mode="wb")
        write(os.path.join(self.src, "old.pyc"), b"\0", mode="wb")
        for skill in ("alpha", "beta"):
            write(os.path.join(self.root, "skills", skill, "SKILL.md"), "---\nname: %s\n---\n" % skill)
            write(os.path.join(self.root, "skills", skill, "scripts", "tool.py"), "print('hi')\n")
        # A skill without scripts/ gets no _growthkit copy, but it does get
        # references/_shared/.
        write(os.path.join(self.root, "skills", "docs-only", "SKILL.md"), "---\nname: docs-only\n---\n")
        # The shared references (flat copies in references/_shared/).
        for rel in sync_shared.SHARED_REFERENCES:
            write(os.path.join(self.root, *rel.split("/")), "# %s\n" % rel)

    def copy_dir(self, skill):
        return os.path.join(self.root, "skills", skill, "scripts", "_growthkit")

    def refs_dir(self, skill):
        return os.path.join(self.root, "skills", skill, "references", "_shared")

    def sync_quietly(self):
        code, _out, _err = self.run_tool()
        self.assertEqual(code, 0)

    def run_tool(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = sync_shared.main(["--root", self.root] + list(args))
        return code, out.getvalue(), err.getvalue()


class SyncTests(FakeRepo):
    def test_creates_copies_only_in_skills_with_scripts(self):
        code, out, _err = self.run_tool()
        self.assertEqual(code, 0)
        for skill in ("alpha", "beta"):
            self.assertEqual(sorted(os.listdir(self.copy_dir(skill))), ["__init__.py", "cli.py"])
            self.assertEqual(read(os.path.join(self.copy_dir(skill), "cli.py")), "from . import __version__\n")
        self.assertFalse(os.path.exists(os.path.join(self.root, "skills", "docs-only", "scripts")))
        self.assertIn("created  skills/alpha/scripts/_growthkit/cli.py", out)
        self.assertIn("scripts/_growthkit/ in 2 skill(s): synced shared/growthkit (2 files): "
                      "4 created, 0 updated, 0 removed", out)

    def test_second_run_is_a_no_op(self):
        self.run_tool()
        path = os.path.join(self.copy_dir("alpha"), "cli.py")
        os.utime(path, (1000000000, 1000000000))
        code, out, _err = self.run_tool()
        self.assertEqual(code, 0)
        self.assertIn("scripts/_growthkit/ in 2 skill(s): already match shared/growthkit", out)
        self.assertIn("references/_shared/ in 3 skill(s): already match shared references", out)
        self.assertNotIn("created", out)
        self.assertEqual(os.stat(path).st_mtime, 1000000000)

    def test_check_passes_after_sync(self):
        self.run_tool()
        code, out, _err = self.run_tool("--check")
        self.assertEqual(code, 0)
        self.assertIn("scripts/_growthkit/ in 2 skill(s): all match shared/growthkit (2 files each)", out)
        self.assertIn("references/_shared/ in 3 skill(s): all match shared references (5 files each)", out)

    def test_check_reports_missing_copies_and_writes_nothing(self):
        code, out, _err = self.run_tool("--check")
        self.assertEqual(code, 1)
        self.assertIn("out of sync: skills/alpha/scripts/_growthkit/__init__.py (missing)", out)
        self.assertIn("Run: python3 tools/sync_shared.py", out)
        self.assertFalse(os.path.exists(self.copy_dir("alpha")))

    def test_check_reports_edited_copy_and_sync_restores_it(self):
        self.run_tool()
        edited = os.path.join(self.copy_dir("beta"), "cli.py")
        write(edited, "# edited by hand\n")
        code, out, _err = self.run_tool("--check")
        self.assertEqual(code, 1)
        self.assertIn("skills/beta/scripts/_growthkit/cli.py (differs from shared/growthkit/cli.py)", out)
        self.assertNotIn("skills/alpha", out)
        code, out, _err = self.run_tool()
        self.assertEqual(code, 0)
        self.assertIn("updated  skills/beta/scripts/_growthkit/cli.py", out)
        self.assertEqual(read(edited), "from . import __version__\n")

    def test_source_edit_propagates(self):
        self.run_tool()
        write(os.path.join(self.src, "cli.py"), "VALUE = 2\n")
        self.assertEqual(self.run_tool("--check")[0], 1)
        code, out, _err = self.run_tool()
        self.assertIn("synced shared/growthkit (2 files): 0 created, 2 updated, 0 removed", out)
        self.assertEqual(read(os.path.join(self.copy_dir("alpha"), "cli.py")), "VALUE = 2\n")

    def test_stale_files_are_reported_and_removed(self):
        self.run_tool()
        stale = os.path.join(self.copy_dir("alpha"), "sub", "gone.py")
        write(stale, "x = 1\n")
        code, out, _err = self.run_tool("--check")
        self.assertEqual(code, 1)
        self.assertIn("skills/alpha/scripts/_growthkit/sub/gone.py (not in shared/growthkit (stale))", out)
        code, out, _err = self.run_tool()
        self.assertIn("removed  skills/alpha/scripts/_growthkit/sub/gone.py", out)
        self.assertFalse(os.path.exists(stale))
        self.assertFalse(os.path.exists(os.path.dirname(stale)))   # emptied folder removed too

    def test_caches_in_copies_are_ignored(self):
        self.run_tool()
        write(os.path.join(self.copy_dir("alpha"), "__pycache__", "cli.cpython-312.pyc"), b"\0", mode="wb")
        write(os.path.join(self.copy_dir("alpha"), ".DS_Store"), b"\0", mode="wb")
        self.assertEqual(self.run_tool("--check")[0], 0)
        self.run_tool()
        self.assertTrue(os.path.exists(os.path.join(self.copy_dir("alpha"), "__pycache__")))

    def test_new_subpackage_is_copied(self):
        write(os.path.join(self.src, "data", "__init__.py"), "")
        write(os.path.join(self.src, "data", "table.json"), "{}\n")
        self.run_tool()
        self.assertTrue(os.path.isfile(os.path.join(self.copy_dir("beta"), "data", "table.json")))
        self.assertEqual(self.run_tool("--check")[0], 0)

    def test_file_in_place_of_copy_folder_is_replaced(self):
        write(self.copy_dir("alpha"), "# old single-module copy\n")
        self.assertEqual(self.run_tool("--check")[0], 1)
        self.assertEqual(self.run_tool()[0], 0)
        self.assertTrue(os.path.isfile(os.path.join(self.copy_dir("alpha"), "__init__.py")))
        self.assertEqual(self.run_tool("--check")[0], 0)

    def test_missing_source_exits_2(self):
        shutil.rmtree(self.src)
        code, _out, err = self.run_tool()
        self.assertEqual(code, 2)
        self.assertIn("shared/growthkit/__init__.py not found", err)
        self.assertEqual(self.run_tool("--check")[0], 2)

    def test_no_skill_folders_is_a_no_op(self):
        shutil.rmtree(os.path.join(self.root, "skills"))
        code, out, _err = self.run_tool("--check")
        self.assertEqual(code, 0)
        self.assertIn("nothing to sync", out)


class SharedReferencesTests(FakeRepo):
    """references/_shared/: standards and the benchmark file in every skill."""

    REFS = sorted(rel.rsplit("/", 1)[-1] for rel in sync_shared.SHARED_REFERENCES)

    def test_reference_list_is_the_documented_one(self):
        self.assertEqual(self.REFS, [
            "browser-fallback.md", "growth-context.md", "report-contract.md",
            "saas-benchmarks.json", "volatile-facts.md",
        ])

    def test_every_skill_gets_flat_copies_even_without_scripts(self):
        code, out, _err = self.run_tool()
        self.assertEqual(code, 0)
        for skill in ("alpha", "beta", "docs-only"):
            self.assertEqual(sorted(os.listdir(self.refs_dir(skill))), self.REFS)
            self.assertEqual(
                read(os.path.join(self.refs_dir(skill), "saas-benchmarks.json")),
                "# shared/benchmarks/saas-benchmarks.json\n",
            )
        self.assertIn("created  skills/docs-only/references/_shared/report-contract.md", out)
        self.assertIn("references/_shared/ in 3 skill(s): synced shared references (5 files): "
                      "15 created, 0 updated, 0 removed", out)
        # The skill without scripts still gets no scripts/ folder.
        self.assertFalse(os.path.exists(os.path.join(self.root, "skills", "docs-only", "scripts")))

    def test_check_reports_missing_reference_copies(self):
        code, out, _err = self.run_tool("--check")
        self.assertEqual(code, 1)
        self.assertIn("out of sync: skills/docs-only/references/_shared/growth-context.md (missing)", out)
        self.assertFalse(os.path.exists(self.refs_dir("docs-only")))

    def test_edited_reference_copy_is_reported_and_restored(self):
        self.sync_quietly()
        edited = os.path.join(self.refs_dir("alpha"), "report-contract.md")
        write(edited, "scoring_mode: none\n")
        code, out, _err = self.run_tool("--check")
        self.assertEqual(code, 1)
        self.assertIn(
            "skills/alpha/references/_shared/report-contract.md "
            "(differs from shared/standards/report-contract.md)", out)
        self.assertIn("references/_shared/ in 3 skill(s): 1 file(s) out of sync "
                      "(0 missing, 1 different, 0 stale)", out)
        self.assertIn("scripts/_growthkit/ in 2 skill(s): all match", out)
        self.sync_quietly()
        self.assertEqual(read(edited), "# shared/standards/report-contract.md\n")

    def test_source_edit_reaches_every_skill(self):
        self.sync_quietly()
        write(os.path.join(self.root, "shared", "benchmarks", "saas-benchmarks.json"), '{"rows": []}\n')
        code, out, _err = self.run_tool()
        self.assertIn("synced shared references (5 files): 0 created, 3 updated, 0 removed", out)
        for skill in ("alpha", "beta", "docs-only"):
            self.assertEqual(read(os.path.join(self.refs_dir(skill), "saas-benchmarks.json")), '{"rows": []}\n')

    def test_stale_reference_is_removed_but_own_references_stay(self):
        self.sync_quietly()
        own = os.path.join(self.root, "skills", "beta", "references", "rubric.md")
        write(own, "# rubric\n")
        stale = os.path.join(self.refs_dir("beta"), "routing-map.md")
        write(stale, "# old\n")
        code, out, _err = self.run_tool("--check")
        self.assertEqual(code, 1)
        self.assertIn("skills/beta/references/_shared/routing-map.md (not in shared references (stale))", out)
        self.assertNotIn("rubric.md", out)
        self.sync_quietly()
        self.assertFalse(os.path.exists(stale))
        self.assertEqual(read(own), "# rubric\n")

    def test_new_skill_is_picked_up(self):
        self.sync_quietly()
        write(os.path.join(self.root, "skills", "gamma", "SKILL.md"), "---\nname: gamma\n---\n")
        code, out, _err = self.run_tool("--check")
        self.assertEqual(code, 1)
        self.assertIn("skills/gamma/references/_shared/volatile-facts.md (missing)", out)
        self.sync_quietly()
        self.assertEqual(sorted(os.listdir(self.refs_dir("gamma"))), self.REFS)
        # gamma has no scripts/, so it gets no _growthkit.
        self.assertFalse(os.path.exists(os.path.join(self.root, "skills", "gamma", "scripts")))
        write(os.path.join(self.root, "skills", "gamma", "scripts", "x.py"), "")
        self.assertEqual(self.run_tool("--check")[0], 1)
        self.sync_quietly()
        self.assertTrue(os.path.isfile(os.path.join(self.copy_dir("gamma"), "__init__.py")))
        self.assertEqual(self.run_tool("--check")[0], 0)

    def test_hidden_folders_and_files_under_skills_are_skipped(self):
        write(os.path.join(self.root, "skills", ".cache", "x.txt"), "x\n")
        write(os.path.join(self.root, "skills", "README.md"), "# skills\n")
        self.sync_quietly()
        self.assertFalse(os.path.exists(os.path.join(self.root, "skills", ".cache", "references")))
        self.assertEqual(self.run_tool("--check")[0], 0)

    def test_missing_shared_reference_exits_2(self):
        os.remove(os.path.join(self.root, "shared", "standards", "browser-fallback.md"))
        code, _out, err = self.run_tool("--check")
        self.assertEqual(code, 2)
        self.assertIn("shared/standards/browser-fallback.md", err)
        self.assertEqual(self.run_tool()[0], 2)
        self.assertFalse(os.path.exists(self.refs_dir("alpha")))


class RealRepoTests(unittest.TestCase):
    def test_shared_reference_sources_exist(self):
        for rel in sync_shared.SHARED_REFERENCES:
            self.assertTrue(os.path.isfile(os.path.join(_paths.REPO_ROOT, *rel.split("/"))), rel)


class RealPackageCopyTests(unittest.TestCase):
    """Sync the real shared/growthkit into a fake skill and import it there.

    This proves the package works under its synced name (_growthkit), which
    only holds while its modules import each other with relative imports.
    """

    def test_synced_copy_imports_as_growthkit_underscore(self):
        try:
            import bs4  # noqa: F401
            import requests  # noqa: F401
        except ImportError:
            self.skipTest("requests and beautifulsoup4 are needed to import every module")
        with tempfile.TemporaryDirectory() as root:
            shutil.copytree(
                _paths.SHARED_DIR,
                os.path.join(root, "shared"),
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            )
            scripts = os.path.join(root, "skills", "demo-skill", "scripts")
            os.makedirs(scripts)
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(sync_shared.main(["--root", root]), 0)
            copy_dir = os.path.join(scripts, "_growthkit")
            before = sorted(name for name in os.listdir(copy_dir) if name != "__pycache__")
            modules = sorted(
                name[:-3] for name in os.listdir(copy_dir)
                if name.endswith(".py") and name != "__init__.py"
            )
            self.assertIn("http", modules)
            code = (
                "import importlib, sys\n"
                "sys.path.insert(0, sys.argv[1])\n"
                "for name in sys.argv[2:]:\n"
                "    importlib.import_module('_growthkit.' + name)\n"
                "import os, _growthkit\n"
                "here = os.path.realpath(_growthkit.__file__)\n"
                "assert here.startswith(os.path.realpath(sys.argv[1])), here\n"
                "print(_growthkit.__version__)\n"
            )
            proc = subprocess.run(
                [sys.executable, "-c", code, scripts] + modules,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=root,
                timeout=60,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr.decode("utf-8", "replace"))
            self.assertRegex(proc.stdout.decode().strip(), r"^\d+\.\d+\.\d+$")
            # Importing must not write anything but caches into the copy.
            after = sorted(name for name in os.listdir(copy_dir) if name != "__pycache__")
            self.assertEqual(after, before)


if __name__ == "__main__":
    unittest.main()
