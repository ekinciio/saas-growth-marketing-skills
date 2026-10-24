"""Path helpers for the test suite.

Importing this module puts <repo>/shared on sys.path, so tests can
``import growthkit`` straight from the source package:

    from tests import _paths  # noqa: F401  (sets up sys.path)
    from growthkit import html

Run every test from the repo root:

    python3 -m unittest discover -s tests -t .
"""

import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHARED_DIR = os.path.join(REPO_ROOT, "shared")
SKILLS_DIR = os.path.join(REPO_ROOT, "skills")
TESTS_DIR = os.path.join(REPO_ROOT, "tests")

if SHARED_DIR not in sys.path:
    sys.path.insert(0, SHARED_DIR)


def fixture_path(*parts: str) -> str:
    """Absolute path of a fixture, relative to tests/ (e.g. 'shared', 'fixtures', 'x.html')."""
    return os.path.join(TESTS_DIR, *parts)


def read_fixture(*parts: str, mode: str = "r") -> "str | bytes":
    """Read a fixture file as text (UTF-8) or, with mode='rb', as bytes."""
    path = fixture_path(*parts)
    if "b" in mode:
        with open(path, "rb") as handle:
            return handle.read()
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def skill_scripts_dir(skill: str) -> str:
    """skills/<skill>/scripts, for tests that import a skill script."""
    return os.path.join(SKILLS_DIR, skill, "scripts")
