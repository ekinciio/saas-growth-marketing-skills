#!/usr/bin/env python3
"""Copy the shared growthkit package into every skill that has scripts.

Source (edit here):      shared/growthkit/
Copies (never edit):     skills/<skill>/scripts/_growthkit/

Installed skills must be self-contained: install.sh copies each skill folder
on its own into ~/.claude/skills/<skill>, so a skill script cannot reach
shared/ at run time. This tool keeps a byte-identical copy of the package
next to each skill's scripts, and skill scripts import it as

    from _growthkit import cli, http

Only skills with a scripts/ folder get a copy. shared/standards/ and
shared/benchmarks/ are not synced yet (a later batch decides how skills ship
them).

Usage (from anywhere; paths are resolved from this file):

    python3 tools/sync_shared.py            # write the copies, print what changed
    python3 tools/sync_shared.py --check    # CI: exit 1 when any copy differs

The sync is idempotent: a second run writes nothing. It also removes files
from a copy that no longer exist in the source, so renamed or deleted modules
do not linger in skills. __pycache__ folders, *.pyc/*.pyo files and dotfiles
(.DS_Store and similar) are never copied, compared or removed.

Exit codes: 0 in sync (or synced), 1 --check found differences,
2 usage or setup error (for example shared/growthkit/ is missing).
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from typing import Dict, List, Optional, Tuple

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE_REL = "shared/growthkit"
COPY_NAME = "_growthkit"

IGNORED_DIRS = {"__pycache__"}
IGNORED_SUFFIXES = (".pyc", ".pyo")

# Actions in a plan, in the order they are printed.
CREATE = "created"
UPDATE = "updated"
REMOVE = "removed"


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


def skill_targets(repo: str) -> List[Tuple[str, str]]:
    """(skill name, copy dir) for every skills/<skill>/ that has a scripts/ folder."""
    skills_dir = os.path.join(repo, "skills")
    targets: List[Tuple[str, str]] = []
    if not os.path.isdir(skills_dir):
        return targets
    for name in sorted(os.listdir(skills_dir)):
        if name.startswith("."):
            continue
        scripts = os.path.join(skills_dir, name, "scripts")
        if os.path.isdir(scripts):
            targets.append((name, os.path.join(scripts, COPY_NAME)))
    return targets


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
            "Copy shared/growthkit/ into skills/<skill>/scripts/_growthkit/ for every skill "
            "that has a scripts/ folder. With --check, change nothing and exit 1 when any "
            "copy differs from the source."
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


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    repo = os.path.abspath(args.root)
    source_dir = os.path.join(repo, *SOURCE_REL.split("/"))
    source_files = list_files(source_dir)
    if "__init__.py" not in source_files:
        print(
            "sync_shared: %s/__init__.py not found under %s" % (SOURCE_REL, repo),
            file=sys.stderr,
        )
        return 2

    targets = skill_targets(repo)
    if not targets:
        print("sync_shared: no skills/<skill>/scripts/ folders found; nothing to sync.")
        return 0

    total = {CREATE: 0, UPDATE: 0, REMOVE: 0}
    for _skill, target_dir in targets:
        changes = plan_copy(source_files, target_dir)
        if not changes:
            continue
        if not args.check:
            apply_plan(source_files, target_dir, changes)
        for action, rel in changes:
            total[action] += 1
            shown = _display(repo, os.path.join(target_dir, *rel.split("/")))
            if args.check:
                reason = {
                    CREATE: "missing",
                    UPDATE: "differs from %s/%s" % (SOURCE_REL, rel),
                    REMOVE: "not in %s (stale)" % SOURCE_REL,
                }[action]
                print("out of sync: %s (%s)" % (shown, reason))
            else:
                print("%-8s %s" % (action, shown))

    changed = sum(total.values())
    summary_counts = "%d missing, %d different, %d stale" % (total[CREATE], total[UPDATE], total[REMOVE])
    if args.check:
        if changed:
            print(
                "sync_shared --check: %d file(s) out of sync in %d skill copies (%s). "
                "Run: python3 tools/sync_shared.py" % (changed, len(targets), summary_counts)
            )
            return 1
        print(
            "sync_shared --check: all %d skill copies match %s (%d files each)."
            % (len(targets), SOURCE_REL, len(source_files))
        )
        return 0

    if changed:
        print(
            "sync_shared: synced %s (%d files) into %d skills: %d created, %d updated, %d removed."
            % (SOURCE_REL, len(source_files), len(targets), total[CREATE], total[UPDATE], total[REMOVE])
        )
    else:
        print("sync_shared: all %d skill copies already match %s." % (len(targets), SOURCE_REL))
    return 0


if __name__ == "__main__":
    sys.exit(main())
