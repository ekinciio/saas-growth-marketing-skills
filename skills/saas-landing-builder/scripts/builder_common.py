"""Small helpers shared by the saas-landing-builder scripts.

Paths are found from this file (never from ${CLAUDE_SKILL_DIR}), so the
scripts work from any working directory and any install location.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, Optional

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPTS_DIR)
SECTION_SETS_PATH = os.path.join(SCRIPTS_DIR, "section_sets.json")
SHARED_REFS_DIR = os.path.join(SKILL_DIR, "references", "_shared")
REPORT_CONTRACT_PATH = os.path.join(SHARED_REFS_DIR, "report-contract.md")
BENCHMARKS_PATH = os.path.join(SHARED_REFS_DIR, "saas-benchmarks.json")

_SCORING_RE = re.compile(r"^scoring_mode: *(deterministic|rubric|none) *$", re.MULTILINE)
SCORING_MODES = ("deterministic", "rubric", "none")


def load_section_sets(path: Optional[str] = None) -> Dict[str, Any]:
    """section_sets.json as a dict (raises OSError / ValueError when broken)."""
    with open(path or SECTION_SETS_PATH, encoding="utf-8") as handle:
        return json.load(handle)


def scoring_mode(path: Optional[str] = None) -> Optional[str]:
    """The scoring switch from references/_shared/report-contract.md, or None."""
    try:
        with open(path or REPORT_CONTRACT_PATH, encoding="utf-8") as handle:
            match = _SCORING_RE.search(handle.read())
    except OSError:
        return None
    return match.group(1) if match else None


def ensure_private_reports_dir(out_path: Optional[str], log: Any = None) -> None:
    """When --out points inside growth-reports/, make sure its .gitignore exists.

    Reports and cached facts about clients or competitors are confidential;
    report.ensure_reports_dir() writes growth-reports/.gitignore with '*'.
    """
    if not out_path:
        return
    parts = os.path.abspath(out_path).split(os.sep)
    if "growth-reports" not in parts:
        return
    base = os.sep.join(parts[:parts.index("growth-reports")]) or os.sep
    try:
        from _growthkit import report
        report.ensure_reports_dir(base)
    except OSError as exc:
        if log is not None:
            log("could not create growth-reports/.gitignore: %s" % exc)


__all__ = [
    "SCRIPTS_DIR", "SKILL_DIR", "SECTION_SETS_PATH", "SHARED_REFS_DIR",
    "REPORT_CONTRACT_PATH", "BENCHMARKS_PATH", "SCORING_MODES",
    "load_section_sets", "scoring_mode", "ensure_private_reports_dir",
]
