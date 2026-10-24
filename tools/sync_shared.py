#!/usr/bin/env python3
"""Copy the shared library and the shared references into every skill.

Sources (edit here)                         Copies (generated, never edit)
  shared/growthkit/                         skills/<skill>/scripts/_growthkit/
  shared/standards/report-contract.md       skills/<skill>/references/_shared/
  shared/standards/growth-context.md        (same folder)
  shared/standards/browser-fallback.md      (same folder)
  shared/standards/volatile-facts.md        (same folder)
  shared/benchmarks/saas-benchmarks.json    (same folder)

Installed skills must be self-contained: install.sh copies each skill folder
on its own into ~/.claude/skills/<skill>, so a skill cannot reach shared/ at
run time. This tool keeps byte-identical copies inside each skill:

- scripts/_growthkit/ for every skill that has a scripts/ folder. Skill
  scripts import it as ``from _growthkit import cli, http``.
- references/_shared/ for EVERY skill folder (with or without scripts, and
  any skill added later). SKILL.md files read it as
  ``${CLAUDE_SKILL_DIR}/references/_shared/report-contract.md`` and scripts
  find the benchmark file at ``<skill>/references/_shared/saas-benchmarks.json``.
  The copy is flat: the five files sit side by side, so the standards can
  name each other by file name.

skill-authoring.md and routing-map.md are maintainer standards and stay in
shared/standards/ only.

Usage (from anywhere; paths are resolved from this file):

    python3 tools/sync_shared.py            # write the copies, print what changed
    python3 tools/sync_shared.py --check    # CI: exit 1 when any copy differs

The sync is idempotent: a second run writes nothing. It also removes files
from a copy that no longer exist in the source, so renamed or deleted files
do not linger in skills. __pycache__ folders, *.pyc/*.pyo files and dotfiles
(.DS_Store and similar) are never copied, compared or removed.

Exit codes: 0 in sync (or synced), 1 --check found differences,
2 usage or setup error (for example shared/growthkit/ or a shared reference
is missing).
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from typing import Callable, Dict, List, NamedTuple, Optional, Tuple

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The growthkit package: a folder, copied recursively.
SOURCE_REL = "shared/growthkit"
COPY_NAME = "_growthkit"
GROWTHKIT_COPY_REL = "scripts/" + COPY_NAME

# Shared references: single files, copied flat into references/_shared/.
REFERENCES_COPY_REL = "references/_shared"
SHARED_REFERENCES = (
    "shared/standards/report-contract.md",
    "shared/standards/growth-context.md",
    "shared/standards/browser-fallback.md",
    "shared/standards/volatile-facts.md",
    "shared/benchmarks/saas-benchmarks.json",
)
REFERENCES_LABEL = "shared references"

IGNORED_DIRS = {"__pycache__"}
IGNORED_SUFFIXES = (".pyc", ".pyo")

# Actions in a plan, in the order they are printed.
CREATE = "created"
UPDATE = "updated"
REMOVE = "removed"


class SetupError(Exception):
    """A source is missing; the tool exits 2."""


class Group(NamedTuple):
    """One kind of copy: where it comes from and which skills get it."""

    label: str                                   # shown in messages
    copy_rel: str                                # folder inside each skill
    sources: Callable[[str], Dict[str, str]]     # repo -> {rel: abs path}
    skills: Callable[[str], List[str]]           # repo -> skill names
    source_of: Callable[[str], str]              # rel path in a copy -> source path shown


def is_ignored(name: str, is_dir: bool) -> bool:
    """True for caches and OS litter that never belong in a copy."""
    if name.startswith("."):
        return True
    if is_dir:
        return name in IGNORED_DIRS
    # macOS writes "Icon\r" files into synced folders (this repo can live in
    # Google Drive); they are not part of the package.
    return name.endswith(IGNORED_SUFFIXES) or name == "Icon\r"


def list_files(root: str) -> Dict[str, str]:
    """Map 'relative/posix/path' -> absolute path for every file under root.

    Ignored folders are pruned and ignored files skipped. Returns {} when
    root does not exist.
    """
    files: Dict[str, str] = {}
    if not os.path.isdir(root):
        return files
    for current, dirs, names in os.walk(root):
        dirs[:] = sorted(d for d in dirs if not is_ignored(d, True))
        for name in sorted(names):
            if is_ignored(name, False):
                continue
            path = os.path.join(current, name)
            rel = os.path.relpath(path, root).replace(os.sep, "/")
            files[rel] = path
    return files


def skill_names(repo: str) -> List[str]:
    """Every folder under skills/ (hidden folders skipped), sorted."""
    skills_dir = os.path.join(repo, "skills")
    if not os.path.isdir(skills_dir):
        return []
    return sorted(
        name for name in os.listdir(skills_dir)
        if not name.startswith(".") and os.path.isdir(os.path.join(skills_dir, name))
    )


def skills_with_scripts(repo: str) -> List[str]:
    """Skill folders that have a scripts/ folder (only they get _growthkit)."""
    return [
        name for name in skill_names(repo)
        if os.path.isdir(os.path.join(repo, "skills", name, "scripts"))
    ]


def skill_targets(repo: str) -> List[Tuple[str, str]]:
    """(skill name, copy dir) for every skills/<skill>/ that has a scripts/ folder."""
    return [
        (name, os.path.join(repo, "skills", name, "scripts", COPY_NAME))
        for name in skills_with_scripts(repo)
    ]


def growthkit_sources(repo: str) -> Dict[str, str]:
    source_dir = os.path.join(repo, *SOURCE_REL.split("/"))
    files = list_files(source_dir)
    if "__init__.py" not in files:
        raise SetupError("%s/__init__.py not found under %s" % (SOURCE_REL, repo))
    return files


def reference_sources(repo: str) -> Dict[str, str]:
    files: Dict[str, str] = {}
    missing = []
    for rel in SHARED_REFERENCES:
        path = os.path.join(repo, *rel.split("/"))
        if not os.path.isfile(path):
            missing.append(rel)
            continue
        files[rel.rsplit("/", 1)[-1]] = path
    if missing:
        raise SetupError("shared reference(s) not found under %s: %s" % (repo, ", ".join(missing)))
    return files


def _reference_source_of(rel: str) -> str:
    for source in SHARED_REFERENCES:
        if source.rsplit("/", 1)[-1] == rel:
            return source
    return rel


GROUPS = (
    Group(SOURCE_REL, GROWTHKIT_COPY_REL, growthkit_sources, skills_with_scripts,
          lambda rel: "%s/%s" % (SOURCE_REL, rel)),
    Group(REFERENCES_LABEL, REFERENCES_COPY_REL, reference_sources, skill_names,
          _reference_source_of),
)


def _read(path: str) -> Optional[bytes]:
    try:
        with open(path, "rb") as handle:
            return handle.read()
    except OSError:
        return None


def plan_copy(source_files: Dict[str, str], target_dir: str) -> List[Tuple[str, str]]:
    """List the (action, relative path) changes that make target_dir match the source."""
    changes: List[Tuple[str, str]] = []
    # A symlink would break once install.sh copies the skill on its own, so a
    # linked copy folder counts as missing and gets replaced by a real one.
    target_files = {} if os.path.islink(target_dir) else list_files(target_dir)
    for rel, src in source_files.items():
        dest = os.path.join(target_dir, *rel.split("/"))
        if rel not in target_files:
            changes.append((CREATE, rel))
        elif _read(src) != _read(dest):
            changes.append((UPDATE, rel))
    for rel in target_files:
        if rel not in source_files:
            changes.append((REMOVE, rel))
    return changes


def _remove_empty_dirs(root: str) -> None:
    """Delete folders left empty after stale files were removed (never root itself)."""
    for current, dirs, names in os.walk(root, topdown=False):
        if current == root:
            continue
        try:
            if not os.listdir(current):
                os.rmdir(current)
        except OSError:
            pass


def apply_plan(source_files: Dict[str, str], target_dir: str, changes: List[Tuple[str, str]]) -> None:
    """Carry out the changes from plan_copy()."""
    if os.path.isfile(target_dir) or os.path.islink(target_dir):
        # A file where the copy folder belongs (for example an old
        # single-module _growthkit): the copy is generated, so replace it.
        os.remove(target_dir)
    removed = False
    for action, rel in changes:
        dest = os.path.join(target_dir, *rel.split("/"))
        if action == REMOVE:
            os.remove(dest)
            removed = True
            continue
        src = source_files[rel]
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        if os.path.isdir(dest):
            # A folder where the source has a file: the copy is generated, so
            # replace it.
            shutil.rmtree(dest)
        shutil.copyfile(src, dest)
        shutil.copymode(src, dest)
    if removed:
        _remove_empty_dirs(target_dir)


def _display(repo: str, path: str) -> str:
    return os.path.relpath(path, repo).replace(os.sep, "/")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sync_shared.py",
        description=(
            "Copy shared/growthkit/ into skills/<skill>/scripts/_growthkit/ (skills with a "
            "scripts/ folder) and the shared standards and benchmark file into "
            "skills/<skill>/references/_shared/ (every skill). With --check, change nothing "
            "and exit 1 when any copy differs from its source."
        ),
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="only compare; exit 1 when a copy is missing, stale or has extra files",
    )
    parser.add_argument(
        "--root",
        default=REPO_ROOT,
        help="repository root (default: the folder above tools/)",
    )
    return parser


def _sync_group(repo: str, group: Group, source_files: Dict[str, str], check: bool) -> Tuple[Dict[str, int], int]:
    """Plan (and unless check, apply) one group. Returns (counts, number of skills)."""
    total = {CREATE: 0, UPDATE: 0, REMOVE: 0}
    skills = group.skills(repo)
    for skill in skills:
        target_dir = os.path.join(repo, "skills", skill, *group.copy_rel.split("/"))
        changes = plan_copy(source_files, target_dir)
        if not changes:
            continue
        if not check:
            apply_plan(source_files, target_dir, changes)
        for action, rel in changes:
            total[action] += 1
            shown = _display(repo, os.path.join(target_dir, *rel.split("/")))
            if check:
                reason = {
                    CREATE: "missing",
                    UPDATE: "differs from %s" % group.source_of(rel),
                    REMOVE: "not in %s (stale)" % group.label,
                }[action]
                print("out of sync: %s (%s)" % (shown, reason))
            else:
                print("%-8s %s" % (action, shown))
    return total, len(skills)


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    repo = os.path.abspath(args.root)
    try:
        sources = [(group, group.sources(repo)) for group in GROUPS]
    except SetupError as exc:
        print("sync_shared: %s" % exc, file=sys.stderr)
        return 2

    if not skill_names(repo):
        print("sync_shared: no skills/<skill>/ folders found; nothing to sync.")
        return 0

    out_of_sync = 0
    summaries = []
    for group, source_files in sources:
        total, skills = _sync_group(repo, group, source_files, args.check)
        changed = sum(total.values())
        out_of_sync += changed
        where = "%s/ in %d skill(s)" % (group.copy_rel, skills)
        if args.check:
            if changed:
                summaries.append(
                    "%s: %d file(s) out of sync (%d missing, %d different, %d stale)"
                    % (where, changed, total[CREATE], total[UPDATE], total[REMOVE])
                )
            else:
                summaries.append("%s: all match %s (%d files each)" % (where, group.label, len(source_files)))
        elif changed:
            summaries.append(
                "%s: synced %s (%d files): %d created, %d updated, %d removed"
                % (where, group.label, len(source_files), total[CREATE], total[UPDATE], total[REMOVE])
            )
        else:
            summaries.append("%s: already match %s" % (where, group.label))

    prefix = "sync_shared --check" if args.check else "sync_shared"
    for line in summaries:
        print("%s: %s." % (prefix, line))
    if args.check and out_of_sync:
        print("sync_shared --check: %d file(s) out of sync. Run: python3 tools/sync_shared.py" % out_of_sync)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
