#!/usr/bin/env python3
"""Repository lint for SaaS Growth Marketing Skills (stdlib only, Python 3.9+).

Checks (all run by default; pick some with --check NAME):

  dashes       No em or en dashes (U+2014, U+2013) or their look-alikes in
               any text file. Generated outputs that quote third-party text
               verbatim are skipped: growth-reports/ and
               examples/<case>/reports/. A minus sign (U+2212) is a warning.
  frontmatter  skills/<name>/SKILL.md and agents/*.md frontmatter, against
               shared/standards/skill-authoring.md section 1: the YAML parses,
               name equals the folder, description is present, at most 1,024
               characters and has no XML tags, description + when_to_use is
               at most 1,536 characters, metadata.version equals growthkit
               __version__, allowed-tools grants only the skill's own scripts,
               and the file is at most 500 lines. House targets (500 and 900
               characters) and a missing metadata.version are warnings.
  lists        uninstall.sh SKILLS / AGENTS / TEMPLATES_LIST arrays and the
               install.sh skill menu match skills/, agents/ and templates/.
  python       Every .py file compiles (py_compile) and has nothing Python 3.9
               rejects at import time: match, except*, or 'X | Y' in an
               annotation that is evaluated at run time.
  json         Every .json file and every .jsonl line parses, and every
               evals/triggering.jsonl row names an existing skill.
  freshness    Warning when growthkit's BROWSER_UA_UPDATED is over 8 weeks old.

Files: everything git tracks plus untracked files that are not ignored
(git ls-files --cached --others --exclude-standard), so new files are linted
before their first commit. Without git (or with --no-git) the tree is walked.

Usage, from the repo root:

    python3 tools/lint_repo.py
    python3 tools/lint_repo.py --check dashes --check python

Exit codes: 0 no errors (warnings are printed but never fail the run),
1 errors found, 2 usage error. Inside GitHub Actions every finding is also
printed as a workflow annotation.
"""

from __future__ import annotations

import argparse
import ast
import fnmatch
import json
import os
import py_compile
import re
import shlex
import subprocess
import sys
import tempfile
import warnings
from datetime import date, datetime
from typing import Any, Dict, Iterable, List, NamedTuple, Optional, Tuple

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CHECKS = ("dashes", "frontmatter", "lists", "python", "json", "freshness")

ERROR = "error"
WARNING = "warning"

# ---------------------------------------------------------------------------
# Limits, from shared/standards/skill-authoring.md section 1
# ---------------------------------------------------------------------------

DESCRIPTION_MAX = 1024          # Agent Skills spec, hard limit
DESCRIPTION_TARGET = 500        # house target
COMBINED_MAX = 1536             # description + when_to_use, Claude Code listing cut
COMBINED_TARGET = 900           # house target
SKILL_MAX_LINES = 500           # CONTRIBUTING.md and skill-authoring.md section 2
NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
NAME_MAX = 64
RESERVED_NAME_WORDS = ("anthropic", "claude")
# Keys a SKILL.md must not use (skill-authoring.md "Do not use").
FORBIDDEN_SKILL_KEYS = {
    "version": "use metadata.version (a top-level version key is ignored by Claude Code)",
    "tools": "'tools' is an agent field; skills use allowed-tools",
    "disable-model-invocation": "our skills must auto-trigger",
}
# The only allowed-tools rule shape: one Bash rule per skill script.
ALLOWED_TOOL_RE = re.compile(
    r'^Bash\(python3 "\$\{CLAUDE_SKILL_DIR\}/scripts/([A-Za-z0-9_][A-Za-z0-9_./-]*\.py)"(?: \*)?\)$'
)
SCRIPT_REF_RE = re.compile(r"\$\{CLAUDE_SKILL_DIR\}/scripts/([A-Za-z0-9_][A-Za-z0-9_./-]*\.py)")

# ---------------------------------------------------------------------------
# Dash characters, written as chr() codes so this file passes its own check
# (editors and tools tend to turn \u escapes into the literal characters).
# ---------------------------------------------------------------------------

DASH_ERRORS = {
    chr(0x2012): "FIGURE DASH",
    chr(0x2013): "EN DASH",
    chr(0x2014): "EM DASH",
    chr(0x2015): "HORIZONTAL BAR",
    chr(0xFE31): "VERTICAL EM DASH",
    chr(0xFE32): "VERTICAL EN DASH",
    chr(0xFE58): "SMALL EM DASH",
}
DASH_WARNINGS = {
    chr(0x2212): "MINUS SIGN",
}
# Generated outputs that quote page titles and posts verbatim. Hand-written
# files next to them (examples/<case>/README.md) are still checked.
DASH_SKIP_GLOBS = (
    "growth-reports/*",
    "*/growth-reports/*",
    "examples/*/reports/*",
)
MAX_DASH_LINES_PER_FILE = 20

BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".icns", ".bmp", ".tiff",
    ".pdf", ".zip", ".gz", ".tgz", ".bz2", ".xz", ".7z",
    ".woff", ".woff2", ".ttf", ".otf", ".eot",
    ".mp3", ".mp4", ".mov", ".webm", ".wav",
    ".pyc", ".pyo", ".so", ".dylib", ".dll", ".exe",
    ".xlsx", ".docx", ".pptx", ".key", ".numbers", ".pages",
}

# Folders never walked when git is not available.
WALK_SKIP_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv", "env", "build", "dist",
    "growth-reports", ".mypy_cache", ".pytest_cache", ".idea", ".vscode",
}

BROWSER_UA_MAX_AGE_DAYS = 56     # 8 weeks, see the comment above BROWSER_UA in http.py


class Finding(NamedTuple):
    level: str
    check: str
    path: str
    line: Optional[int]
    message: str


# ---------------------------------------------------------------------------
# File discovery and reading
# ---------------------------------------------------------------------------

def repo_files(repo: str, use_git: bool = True) -> Tuple[List[str], str]:
    """Relative POSIX paths of the files to lint, and how they were found."""
    if use_git:
        try:
            proc = subprocess.run(
                ["git", "-C", repo, "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=60,
            )
        except (OSError, subprocess.SubprocessError):
            proc = None
        if proc is not None and proc.returncode == 0:
            names = proc.stdout.decode("utf-8", "surrogateescape").split("\0")
            rels = sorted({name for name in names if name})
            # --cached also lists files deleted from the working tree.
            return [rel for rel in rels if os.path.isfile(os.path.join(repo, rel))], "git"
    rels = []
    for current, dirs, names in os.walk(repo):
        dirs[:] = sorted(d for d in dirs if d not in WALK_SKIP_DIRS and not d.endswith(".egg-info"))
        for name in sorted(names):
            if name == ".DS_Store" or name.endswith((".pyc", ".pyo")):
                continue
            path = os.path.join(current, name)
            rels.append(os.path.relpath(path, repo).replace(os.sep, "/"))
    return rels, "walk"


def read_text(path: str) -> Tuple[Optional[str], str]:
    """(text, "") for a UTF-8 text file, or (None, reason) for binary/undecodable files."""
    if os.path.splitext(path)[1].lower() in BINARY_EXTENSIONS:
        return None, "binary"
    try:
        with open(path, "rb") as handle:
            data = handle.read()
    except OSError as exc:
        return None, "unreadable (%s)" % exc
    if b"\0" in data[:8192]:
        return None, "binary"
    try:
        return data.decode("utf-8"), ""
    except UnicodeDecodeError:
        return None, "not UTF-8"


# ---------------------------------------------------------------------------
# Frontmatter: a small, strict YAML subset
# ---------------------------------------------------------------------------
#
# The repo has no PyYAML (runtime deps are requests and beautifulsoup4 only),
# so frontmatter is read with this parser. It covers what SKILL.md and agent
# files use: "key: value" with plain, single- or double-quoted scalars, block
# scalars (>, >-, |, |-), lists of scalars ("- item"), one level of nested
# mapping (metadata:) and simple flow lists ([a, b]). It reports the YAML
# mistakes that silently break a skill: a plain value containing ": ", tabs
# for indentation, unterminated quotes, duplicate keys. Nested blocks under
# keys the lint does not inspect are kept as raw text and not validated.

class Raw(str):
    """Unparsed nested block under a key the lint does not inspect."""


STRICT_NESTED_KEYS = {"metadata", "allowed-tools", "skills"}
_KEY_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*):(?:[ \t]+(.*?))?[ \t]*$")
_BLOCK_RE = re.compile(r"^([|>])(?:([1-9])([-+])?|([-+])([1-9])?)?$")
_BOOL_WORDS = {
    "true": True, "false": False, "yes": True, "no": False, "on": True, "off": False,
    "y": True, "n": False,
}
_INT_RE = re.compile(r"^[-+]?(?:0|[1-9][0-9_]*)$|^0x[0-9a-fA-F]+$|^0o?[0-7]+$")
_FLOAT_RE = re.compile(
    r"^[-+]?(?:[0-9][0-9_]*)?\.[0-9_]*(?:[eE][-+]?[0-9]+)?$"
    r"|^[-+]?\.(?:inf|Inf|INF)$"
    r"|^\.(?:nan|NaN|NAN)$"
)


class YamlError(Exception):
    def __init__(self, line: int, message: str) -> None:
        super().__init__(message)
        self.line = line
        self.message = message


def _resolve_plain(text: str) -> Any:
    """YAML 1.1 type resolution for a plain scalar (what PyYAML would return)."""
    lowered = text.lower()
    if text in ("", "~") or lowered == "null":
        return None
    if lowered in _BOOL_WORDS:
        return _BOOL_WORDS[lowered]
    if _INT_RE.match(text):
        try:
            return int(text.replace("_", ""), 0)
        except ValueError:
            return text
    if _FLOAT_RE.match(text) and any(ch.isdigit() for ch in text) or lowered in (".inf", "-.inf", "+.inf", ".nan"):
        try:
            return float(text.replace("_", "").replace(".inf", "inf").replace(".nan", "nan"))
        except ValueError:
            return text
    return text


def _strip_comment(text: str) -> str:
    """Drop a ' #' comment from a plain scalar."""
    if text.startswith("#"):
        return ""
    index = text.find(" #")
    if index < 0:
        index = text.find("\t#")
    return text[:index].rstrip() if index >= 0 else text


def _parse_quoted(text: str, line: int) -> Tuple[str, str]:
    """Parse a quoted scalar at the start of text. Returns (value, rest after the quote)."""
    quote = text[0]
    i = 1
    out: List[str] = []
    while i < len(text):
        ch = text[i]
        if quote == "'":
            if ch == "'":
                if text[i + 1:i + 2] == "'":
                    out.append("'")
                    i += 2
                    continue
                return "".join(out), text[i + 1:]
            out.append(ch)
            i += 1
            continue
        if ch == "\\":
            i += 2
            continue
        if ch == '"':
            inner = text[1:i]
            try:
                value = json.loads('"' + inner + '"', strict=False)
            except ValueError:
                raise YamlError(line, "unsupported escape sequence in a double-quoted value") from None
            return value, text[i + 1:]
        i += 1
    raise YamlError(line, "unterminated %s-quoted value" % ("single" if quote == "'" else "double"))


def _parse_scalar(text: str, line: int) -> Any:
    """A flow scalar on one (already joined) line: quoted, flow list, or plain."""
    text = text.strip()
    if not text:
        return None
    if text[0] in "'\"":
        value, rest = _parse_quoted(text, line)
        rest = rest.strip()
        if rest and not rest.startswith("#"):
            raise YamlError(line, "unexpected text after a quoted value: %r" % rest[:40])
        return value
    if text[0] == "[":
        body = _strip_comment(text)
        if not body.endswith("]"):
            raise YamlError(line, "unterminated flow list")
        items = [item.strip() for item in body[1:-1].split(",")]
        return [_parse_scalar(item, line) for item in items if item]
    if text[0] == "{":
        raise YamlError(line, "flow mappings ({...}) are not supported in frontmatter; use block style")
    if text[0] in "&*!%@`|>?" or text.startswith("- ") or text == "-":
        raise YamlError(line, "a plain value cannot start with %r; quote the value" % text[0])
    plain = _strip_comment(text)
    if ": " in plain or plain.endswith(":"):
        raise YamlError(line, "a plain value contains ': '; quote the value or use a folded block (>)")
    return _resolve_plain(plain)


def _indent_of(text: str, line: int) -> int:
    stripped = text.lstrip(" ")
    if stripped.startswith("\t"):
        raise YamlError(line, "tabs are not allowed for indentation in YAML")
    return len(text) - len(stripped)


def _block_scalar(header: str, block: List[Tuple[int, str]], line: int) -> str:
    """Fold (>) or keep (|) an indented block scalar, with chomping."""
    match = _BLOCK_RE.match(header)
    if not match:
        raise YamlError(line, "bad block scalar header %r" % header)
    style = match.group(1)
    explicit = match.group(2) or match.group(5)
    chomp = match.group(3) or match.group(4) or ""
    indent: Optional[int] = int(explicit) if explicit else None
    texts: List[str] = []
    for number, raw in block:
        if not raw.strip():
            texts.append("")
            continue
        current = _indent_of(raw, number)
        if indent is None:
            indent = current
        if current < indent:
            raise YamlError(number, "line is indented less than the first line of the block")
        texts.append(raw[indent:])
    trailing = 0
    while texts and texts[-1] == "":
        texts.pop()
        trailing += 1
    if style == "|":
        value = "\n".join(texts)
    else:
        value = _fold(texts)
    if not texts:
        return "" if chomp != "+" else "\n" * trailing
    if chomp == "-":
        return value
    if chomp == "+":
        return value + "\n" * (1 + trailing)
    return value + "\n"


def _fold(texts: List[str]) -> str:
    """YAML folding: line breaks between normal lines become spaces, blank lines become newlines."""
    out: List[str] = []
    previous: Optional[str] = None      # "normal" or "more" (more-indented)
    empties = 0
    for text in texts:
        if text == "":
            empties += 1
            continue
        more = text[0] in " \t"
        if previous is None:
            out.append("\n" * empties)
        elif previous == "normal" and not more:
            out.append("\n" * empties if empties else " ")
        else:
            out.append("\n" * (empties + 1))
        out.append(text)
        previous = "more" if more else "normal"
        empties = 0
    return "".join(out)


def _join_flow_lines(first: str, more: List[Tuple[int, str]]) -> str:
    """A multi-line plain or quoted scalar: continuation lines fold to spaces."""
    parts = [first.strip()]
    for _number, raw in more:
        parts.append(raw.strip() if raw.strip() else "\n")
    joined = ""
    for part in parts:
        if part == "\n":
            joined += "\n"
        elif not joined or joined.endswith("\n"):
            joined += part
        else:
            joined += " " + part
    return joined


def _nested(key: str, block: List[Tuple[int, str]]) -> Any:
    """The indented block under 'key:' with no inline value: a list or a mapping."""
    content = [(n, raw) for n, raw in block if raw.strip() and not raw.strip().startswith("#")]
    if not content:
        return None
    first_no, first = content[0]
    indent = _indent_of(first, first_no)
    if first.strip().startswith("-"):
        items: List[Any] = []
        current: Optional[Tuple[int, str, List[Tuple[int, str]]]] = None
        for number, raw in content:
            here = _indent_of(raw, number)
            body = raw.strip()
            if here == indent and (body == "-" or body.startswith("- ")):
                if current is not None:
                    items.append(_parse_scalar(_join_flow_lines(current[1], current[2]), current[0]))
                current = (number, body[1:].strip(), [])
            elif here > indent and current is not None:
                current[2].append((number, raw))
            else:
                raise YamlError(number, "expected a '- item' line under %r" % key)
        if current is not None:
            items.append(_parse_scalar(_join_flow_lines(current[1], current[2]), current[0]))
        return items
    mapping: Dict[str, Any] = {}
    pending: Optional[Tuple[int, str, str, List[Tuple[int, str]]]] = None

    def flush() -> None:
        if pending is None:
            return
        number, sub_key, rest, more = pending
        if sub_key in mapping:
            raise YamlError(number, "duplicate key %r under %r" % (sub_key, key))
        if _BLOCK_RE.match(rest or ""):
            mapping[sub_key] = _block_scalar(rest, more, number)
        elif not rest:
            mapping[sub_key] = Raw("\n".join(raw for _n, raw in more)) if more else None
        else:
            mapping[sub_key] = _parse_scalar(_join_flow_lines(rest, more), number)

    for number, raw in block:
        if not raw.strip() or raw.strip().startswith("#"):
            if pending is not None:
                pending[3].append((number, raw))
            continue
        here = _indent_of(raw, number)
        if here == indent:
            flush()
            match = _KEY_RE.match(raw.strip())
            if not match:
                raise YamlError(number, "expected 'key: value' under %r" % key)
            pending = (number, match.group(1), match.group(2) or "", [])
        elif here > indent and pending is not None:
            pending[3].append((number, raw))
        else:
            raise YamlError(number, "inconsistent indentation under %r" % key)
    flush()
    return mapping


def parse_yaml_subset(lines: List[Tuple[int, str]]) -> Tuple[Dict[str, Any], Dict[str, int]]:
    """Parse frontmatter lines [(line number, text)]. Returns (data, key -> line number).

    Raises YamlError for anything a YAML parser would reject (within the
    supported subset) or that the subset does not support.
    """
    data: Dict[str, Any] = {}
    key_lines: Dict[str, int] = {}
    i = 0
    while i < len(lines):
        number, raw = lines[i]
        if not raw.strip() or raw.lstrip().startswith("#"):
            i += 1
            continue
        if raw[0] in " \t":
            raise YamlError(number, "unexpected indentation (top-level keys start in column 1)")
        match = _KEY_RE.match(raw)
        if not match:
            raise YamlError(number, "expected 'key: value'")
        key, rest = match.group(1), match.group(2) or ""
        if key in data:
            raise YamlError(number, "duplicate key %r" % key)
        key_lines[key] = number
        j = i + 1
        block: List[Tuple[int, str]] = []
        while j < len(lines) and (not lines[j][1].strip() or lines[j][1][0] in " \t"):
            block.append(lines[j])
            j += 1
        rest_body = rest.strip()
        header = rest_body.split(" #", 1)[0].strip()
        if _BLOCK_RE.match(header):
            data[key] = _block_scalar(header, block, number)
        elif not rest_body or rest_body.startswith("#"):
            content = [raw_line.strip() for _n, raw_line in block
                       if raw_line.strip() and not raw_line.strip().startswith("#")]
            if content and not (content[0].startswith("-") or _KEY_RE.match(content[0])):
                # "key:" followed by indented text is a multi-line plain
                # scalar ("description:\n  Audits ...").
                data[key] = _parse_scalar(_join_flow_lines("", block), number)
            elif key in STRICT_NESTED_KEYS:
                data[key] = _nested(key, block)
            else:
                text = "\n".join(raw_line for _n, raw_line in block).strip("\n")
                data[key] = Raw(text) if text.strip() else None
        else:
            data[key] = _parse_scalar(_join_flow_lines(rest_body, block), number)
        i = j
    return data, key_lines


def split_frontmatter(text: str) -> Tuple[Optional[List[Tuple[int, str]]], Optional[str]]:
    """The frontmatter lines (numbered from 2), or (None, reason) when there is none."""
    lines = text.split("\n")
    if not lines or lines[0].rstrip("\r") != "---":
        return None, "the first line must be '---' (YAML frontmatter)"
    for index in range(1, len(lines)):
        if lines[index].rstrip("\r").rstrip() == "---":
            return [(n + 1, lines[n].rstrip("\r")) for n in range(1, index)], None
    return None, "the frontmatter has no closing '---' line"


# ---------------------------------------------------------------------------
# Python 3.9 compatibility (runtime traps that py_compile on 3.9 cannot see
# when the lint runs on a newer interpreter, and annotation traps it never sees)
# ---------------------------------------------------------------------------

def _has_future_annotations(tree: ast.Module) -> bool:
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module == "__future__":
            if any(alias.name == "annotations" for alias in node.names):
                return True
    return False


def _runtime_annotations(tree: ast.AST) -> List[ast.expr]:
    """Annotations Python evaluates when the code runs (without the future import).

    Function parameter and return annotations are evaluated when the def
    statement runs; variable annotations only at module or class level.
    Local variable annotations inside a function body are never evaluated.
    """
    found: List[ast.expr] = []

    def visit(node: ast.AST, in_function_scope: bool) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                args = child.args
                params = list(getattr(args, "posonlyargs", [])) + list(args.args) + list(args.kwonlyargs)
                params += [arg for arg in (args.vararg, args.kwarg) if arg is not None]
                found.extend(arg.annotation for arg in params if arg.annotation is not None)
                if child.returns is not None:
                    found.append(child.returns)
                visit(child, True)
            elif isinstance(child, ast.Lambda):
                visit(child, True)
            elif isinstance(child, ast.ClassDef):
                visit(child, False)
            elif isinstance(child, ast.AnnAssign):
                if not in_function_scope:
                    found.append(child.annotation)
                visit(child, in_function_scope)
            else:
                visit(child, in_function_scope)

    visit(tree, False)
    return found


def py39_problems(tree: ast.Module) -> List[Tuple[int, str]]:
    """(line, message) for constructs that fail on Python 3.9."""
    problems: List[Tuple[int, str]] = []
    match_node = getattr(ast, "Match", None)
    try_star = getattr(ast, "TryStar", None)
    for node in ast.walk(tree):
        if match_node is not None and isinstance(node, match_node):
            problems.append((node.lineno, "'match' statement needs Python 3.10+; the floor is 3.9"))
        elif try_star is not None and isinstance(node, try_star):
            problems.append((node.lineno, "'except*' needs Python 3.11+; the floor is 3.9"))
    if not _has_future_annotations(tree):
        for annotation in _runtime_annotations(tree):
            for sub in ast.walk(annotation):
                if isinstance(sub, ast.BinOp) and isinstance(sub.op, ast.BitOr):
                    problems.append((
                        annotation.lineno,
                        "'X | Y' in an annotation raises TypeError on Python 3.9; add "
                        "'from __future__ import annotations' or use Optional/Union",
                    ))
                    break
    return problems


# ---------------------------------------------------------------------------
# Shell array parsing (uninstall.sh / install.sh)
# ---------------------------------------------------------------------------

_ARRAY_START_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)=\((.*)$")


def shell_arrays(text: str) -> Dict[str, Tuple[int, List[str]]]:
    """NAME -> (line number, items) for every NAME=( ... ) array in a shell script."""
    arrays: Dict[str, Tuple[int, List[str]]] = {}
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        match = _ARRAY_START_RE.match(lines[i])
        if not match:
            i += 1
            continue
        name, start_line = match.group(1), i + 1
        chunk = match.group(2)
        while ")" not in _strip_shell_comment(chunk) and i + 1 < len(lines):
            i += 1
            chunk += "\n" + lines[i]
        body = _strip_shell_comment(chunk)
        body = body[:body.rfind(")")] if ")" in body else body
        try:
            items = shlex.split(body, comments=True)
        except ValueError:
            items = []
        arrays[name] = (start_line, items)
        i += 1
    return arrays


def _strip_shell_comment(chunk: str) -> str:
    return "\n".join(re.sub(r"(^|\s)#.*$", "", line) for line in chunk.split("\n"))


# install.sh prints a menu of slash commands: "/geo-seo-auditor audit <url>".
_MENU_COMMAND_RE = re.compile(r"(?:^|(?<=[\s\"'}(]))/([a-z0-9][a-z0-9-]*)(?![\w/.-])")


# ---------------------------------------------------------------------------
# The linter
# ---------------------------------------------------------------------------

class Linter:
    def __init__(self, repo: str, files: List[str], today: Optional[date] = None) -> None:
        self.repo = repo
        self.files = files
        self.today = today or date.today()
        self.findings: List[Finding] = []
        self._text_cache: Dict[str, Tuple[Optional[str], str]] = {}

    # -- helpers ------------------------------------------------------------

    def add(self, level: str, check: str, path: str, line: Optional[int], message: str) -> None:
        self.findings.append(Finding(level, check, path, line, message))

    def abspath(self, rel: str) -> str:
        return os.path.join(self.repo, *rel.split("/"))

    def text(self, rel: str) -> Tuple[Optional[str], str]:
        if rel not in self._text_cache:
            self._text_cache[rel] = read_text(self.abspath(rel))
        return self._text_cache[rel]

    def skill_names(self) -> List[str]:
        """Folders under skills/ (each must hold a SKILL.md; the frontmatter check says so)."""
        skills_dir = os.path.join(self.repo, "skills")
        if not os.path.isdir(skills_dir):
            return []
        return sorted(
            name for name in os.listdir(skills_dir)
            if not name.startswith(".") and os.path.isdir(os.path.join(skills_dir, name))
        )

    def md_names(self, folder: str) -> List[str]:
        path = os.path.join(self.repo, folder)
        if not os.path.isdir(path):
            return []
        return sorted(n for n in os.listdir(path) if n.endswith(".md") and not n.startswith("."))

    def toolkit_version(self) -> Optional[str]:
        text, _ = read_text(os.path.join(self.repo, "shared", "growthkit", "__init__.py"))
        if not text:
            return None
        match = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', text, re.M)
        return match.group(1) if match else None

    # -- dashes ---------------------------------------------------------------

    def check_dashes(self) -> None:
        for rel in self.files:
            if any(fnmatch.fnmatch(rel, pattern) for pattern in DASH_SKIP_GLOBS):
                continue
            text, reason = self.text(rel)
            if text is None:
                if reason == "not UTF-8":
                    self.add(WARNING, "dashes", rel, None, "not UTF-8 text, so the dash check skipped it")
                continue
            if not any(ch in text for ch in DASH_ERRORS) and not any(ch in text for ch in DASH_WARNINGS):
                continue
            reported = 0
            extra = 0
            for number, line in enumerate(text.split("\n"), 1):
                for table, level in ((DASH_ERRORS, ERROR), (DASH_WARNINGS, WARNING)):
                    for ch, label in table.items():
                        col = line.find(ch)
                        if col < 0:
                            continue
                        if reported >= MAX_DASH_LINES_PER_FILE:
                            extra += 1
                            continue
                        reported += 1
                        fix = "use a regular hyphen '-'" if level == ERROR else "use '-' for a minus"
                        self.add(level, "dashes", rel, number,
                                 "U+%04X %s at column %d; %s" % (ord(ch), label, col + 1, fix))
            if extra:
                self.add(ERROR, "dashes", rel, None, "%d more dash finding(s) not shown" % extra)

    # -- frontmatter ----------------------------------------------------------

    def _frontmatter(self, rel: str, check: str) -> Tuple[Optional[Dict[str, Any]], Dict[str, int], str]:
        text, reason = self.text(rel)
        if text is None:
            self.add(ERROR, check, rel, None, "cannot read the file (%s)" % reason)
            return None, {}, ""
        lines, problem = split_frontmatter(text)
        if lines is None:
            self.add(ERROR, check, rel, 1, problem or "no frontmatter")
            return None, {}, text
        try:
            data, key_lines = parse_yaml_subset(lines)
        except YamlError as exc:
            self.add(ERROR, check, rel, exc.line,
                     "frontmatter does not parse: %s (Claude Code then loads the skill with no "
                     "description, so it never auto-triggers)" % exc.message)
            return None, {}, text
        return data, key_lines, text

    def _check_description(self, rel: str, data: Dict[str, Any], key_lines: Dict[str, int], skill: bool) -> None:
        check = "frontmatter"
        description = data.get("description")
        line = key_lines.get("description", 2)
        if description is None or (isinstance(description, str) and not description.strip()):
            self.add(ERROR, check, rel, line, "description is missing or empty")
            return
        if not isinstance(description, str) or isinstance(description, Raw):
            self.add(ERROR, check, rel, line, "description must be a text value")
            return
        length = len(description.strip())
        if length > DESCRIPTION_MAX:
            self.add(ERROR, check, rel, line,
                     "description is %d characters; the limit is %d" % (length, DESCRIPTION_MAX))
        elif skill and length > DESCRIPTION_TARGET:
            self.add(WARNING, check, rel, line,
                     "description is %d characters; the house target is %d or less"
                     % (length, DESCRIPTION_TARGET))
        if skill and re.search(r"[<>]", description):
            self.add(ERROR, check, rel, line,
                     "description contains '<' or '>'; XML tags are not allowed in descriptions")
        if not skill:
            return
        when = data.get("when_to_use")
        if when is not None and (not isinstance(when, str) or isinstance(when, Raw)):
            self.add(ERROR, check, rel, key_lines.get("when_to_use"), "when_to_use must be a text value")
            return
        combined = length + (len(when.strip()) if when else 0)
        if when:
            if combined > COMBINED_MAX:
                self.add(ERROR, check, rel, key_lines.get("when_to_use"),
                         "description + when_to_use is %d characters; Claude Code cuts the "
                         "listing at %d" % (combined, COMBINED_MAX))
            elif combined > COMBINED_TARGET:
                self.add(WARNING, check, rel, key_lines.get("when_to_use"),
                         "description + when_to_use is %d characters; the house target is %d or less"
                         % (combined, COMBINED_TARGET))

    def check_frontmatter(self) -> None:
        version = self.toolkit_version()
        skills = set(self.skill_names())
        self._no_metadata: List[str] = []
        for skill in sorted(skills):
            rel = "skills/%s/SKILL.md" % skill
            if not os.path.isfile(self.abspath(rel)):
                self.add(ERROR, "frontmatter", "skills/%s" % skill, None, "skill folder has no SKILL.md")
                continue
            data, key_lines, text = self._frontmatter(rel, "frontmatter")
            line_count = len(text.split("\n")) - (1 if text.endswith("\n") else 0) if text else 0
            if line_count > SKILL_MAX_LINES:
                self.add(ERROR, "frontmatter", rel, None,
                         "SKILL.md is %d lines; keep it at %d or less and move detail to references/"
                         % (line_count, SKILL_MAX_LINES))
            if data is None:
                continue
            self._check_skill_data(rel, skill, data, key_lines, version)
            # Commands in the body (allowed-tools rules are checked above).
            body_offset = _body_offset(text)
            body = text[body_offset:]
            for ref in sorted(set(SCRIPT_REF_RE.findall(body))):
                if not os.path.isfile(self.abspath("skills/%s/scripts/%s" % (skill, ref))):
                    line = text[:body_offset].count("\n") + (_line_of(body, ref) or 1)
                    self.add(ERROR, "frontmatter", rel, line,
                             "SKILL.md runs scripts/%s, which does not exist" % ref)
        if self._no_metadata:
            self.add(WARNING, "frontmatter", "skills", None,
                     "metadata.version (required by skill-authoring.md, equal to growthkit __version__ "
                     "%s) is not set in %d of %d skills: %s"
                     % (version or "?", len(self._no_metadata), len(skills), ", ".join(self._no_metadata)))
        for name in self.md_names("agents"):
            rel = "agents/%s" % name
            data, key_lines, _text = self._frontmatter(rel, "frontmatter")
            if data is None:
                continue
            stem = name[:-3]
            if data.get("name") != stem:
                self.add(ERROR, "frontmatter", rel, key_lines.get("name", 2),
                         "name is %r but the file is %s; they must match" % (data.get("name"), name))
            self._check_description(rel, data, key_lines, skill=False)
            listed = data.get("skills")
            if listed is not None:
                if not isinstance(listed, list):
                    self.add(ERROR, "frontmatter", rel, key_lines.get("skills"), "skills must be a list")
                else:
                    for item in listed:
                        if item not in skills:
                            self.add(ERROR, "frontmatter", rel, key_lines.get("skills"),
                                     "skills lists %r, but skills/%s/ does not exist" % (item, item))

    def _check_skill_data(self, rel: str, skill: str, data: Dict[str, Any], key_lines: Dict[str, int],
                          version: Optional[str]) -> None:
        check = "frontmatter"
        name = data.get("name")
        name_line = key_lines.get("name", 2)
        if name is None:
            self.add(ERROR, check, rel, name_line, "name is missing")
        elif not isinstance(name, str):
            self.add(ERROR, check, rel, name_line, "name must be a text value")
        else:
            if name != skill:
                self.add(ERROR, check, rel, name_line,
                         "name is %r but the folder is %r; they must match" % (name, skill))
            if len(name) > NAME_MAX or not NAME_RE.match(name):
                self.add(ERROR, check, rel, name_line,
                         "name must be 1-%d characters of lowercase a-z, 0-9 and single hyphens" % NAME_MAX)
            for word in RESERVED_NAME_WORDS:
                if word in name:
                    self.add(ERROR, check, rel, name_line, "name must not contain %r" % word)
        self._check_description(rel, data, key_lines, skill=True)
        for key, why in FORBIDDEN_SKILL_KEYS.items():
            if key in data:
                self.add(ERROR, check, rel, key_lines.get(key), "do not use the %r key: %s" % (key, why))

        metadata = data.get("metadata")
        meta_line = key_lines.get("metadata")
        if metadata is None:
            # Reported once for all skills (see check_frontmatter): every skill
            # lacks it until its migration batch lands.
            self._no_metadata.append(skill)
        elif not isinstance(metadata, dict):
            self.add(ERROR, check, rel, meta_line, "metadata must be a mapping of string to string")
        else:
            for key, value in metadata.items():
                if not isinstance(value, str) or isinstance(value, Raw):
                    self.add(ERROR, check, rel, meta_line,
                             "metadata.%s must be a quoted string (got %r)" % (key, value))
            meta_version = metadata.get("version")
            if meta_version is None:
                self.add(WARNING, check, rel, meta_line,
                         "metadata.version is not set (expected %r)" % (version or "?"))
            elif version and isinstance(meta_version, str) and meta_version != version:
                self.add(ERROR, check, rel, meta_line,
                         "metadata.version is %r but growthkit __version__ is %r" % (meta_version, version))

        tools = data.get("allowed-tools")
        tools_line = key_lines.get("allowed-tools")
        if tools is not None:
            if not isinstance(tools, list):
                self.add(ERROR, check, rel, tools_line,
                         "allowed-tools must be a YAML list with one Bash rule per script")
            else:
                for rule in tools:
                    match = ALLOWED_TOOL_RE.match(rule) if isinstance(rule, str) else None
                    if not match:
                        self.add(ERROR, check, rel, tools_line,
                                 "allowed-tools rule %r is not of the form "
                                 'Bash(python3 "${CLAUDE_SKILL_DIR}/scripts/<script>.py" *)' % (rule,))
                        continue
                    script = match.group(1)
                    if not os.path.isfile(self.abspath("skills/%s/scripts/%s" % (skill, script))):
                        self.add(ERROR, check, rel, tools_line,
                                 "allowed-tools grants scripts/%s, which does not exist" % script)

    # -- install / uninstall lists --------------------------------------------

    def _compare(self, rel: str, line: Optional[int], label: str, listed: Iterable[str],
                 actual: Iterable[str], where: str) -> None:
        listed_set, actual_set = set(listed), set(actual)
        for missing in sorted(actual_set - listed_set):
            self.add(ERROR, "lists", rel, line, "%s is missing %r (it exists in %s)" % (label, missing, where))
        for extra in sorted(listed_set - actual_set):
            self.add(ERROR, "lists", rel, line, "%s lists %r, which is not in %s" % (label, extra, where))

    def check_lists(self) -> None:
        skills = [s for s in self.skill_names() if os.path.isfile(self.abspath("skills/%s/SKILL.md" % s))]
        agents = self.md_names("agents")
        templates = self.md_names("templates")

        rel = "uninstall.sh"
        text, _ = self.text(rel) if os.path.isfile(self.abspath(rel)) else (None, "")
        if text is None:
            self.add(ERROR, "lists", rel, None, "uninstall.sh is missing or unreadable")
        else:
            arrays = shell_arrays(text)
            for array, actual, where, required in (
                ("SKILLS", skills, "skills/", True),
                ("AGENTS", agents, "agents/", bool(agents)),
                ("TEMPLATES_LIST", templates, "templates/", bool(templates)),
            ):
                if array not in arrays:
                    if required:
                        self.add(ERROR, "lists", rel, None, "no %s=( ... ) array found" % array)
                    continue
                line, items = arrays[array]
                self._compare(rel, line, "%s in uninstall.sh" % array, items, actual, where)

        rel = "install.sh"
        text, _ = self.text(rel) if os.path.isfile(self.abspath(rel)) else (None, "")
        if text is None:
            self.add(ERROR, "lists", rel, None, "install.sh is missing or unreadable")
            return
        arrays = shell_arrays(text)
        if "SKILLS" in arrays:
            line, items = arrays["SKILLS"]
            self._compare(rel, line, "SKILLS in install.sh", items, skills, "skills/")
        elif not re.search(r"skills\"?/\*/?", text):
            self.add(ERROR, "lists", rel, None,
                     "install.sh neither lists skills in SKILLS=( ... ) nor copies skills/*/")
        menu: Dict[str, int] = {}
        for number, line in enumerate(text.split("\n"), 1):
            if "echo" not in line:
                continue
            for name in _MENU_COMMAND_RE.findall(line):
                menu.setdefault(name, number)
        for name, number in sorted(menu.items()):
            if name not in skills:
                self.add(ERROR, "lists", rel, number,
                         "the install menu shows /%s, but skills/%s/ does not exist" % (name, name))
        for skill in skills:
            if skill not in menu:
                self.add(ERROR, "lists", rel, None,
                         "the install menu (WHAT'S INSTALLED) does not show /%s" % skill)
        for agent in agents:
            stem = agent[:-3]
            if not re.search(r"(?<![\w-])%s(?![\w-])" % re.escape(stem), text):
                self.add(ERROR, "lists", rel, None, "the install menu does not mention agent %r" % stem)

    # -- python ---------------------------------------------------------------

    def check_python(self) -> None:
        with tempfile.TemporaryDirectory(prefix="lint_repo_") as tmp:
            cfile = os.path.join(tmp, "compiled.pyc")
            for rel in self.files:
                if not rel.endswith(".py"):
                    continue
                path = self.abspath(rel)
                with warnings.catch_warnings(record=True) as caught:
                    warnings.simplefilter("always")
                    try:
                        py_compile.compile(path, cfile=cfile, doraise=True)
                    except py_compile.PyCompileError as exc:
                        err = exc.exc_value
                        line = getattr(err, "lineno", None)
                        detail = getattr(err, "msg", None) or str(err)
                        self.add(ERROR, "python", rel, line,
                                 "does not compile on Python %d.%d: %s: %s"
                                 % (sys.version_info[0], sys.version_info[1], exc.exc_type_name, detail))
                        continue
                    except (OSError, ValueError) as exc:
                        self.add(ERROR, "python", rel, None, "cannot compile: %s" % exc)
                        continue
                for warning in caught:
                    self.add(WARNING, "python", rel, getattr(warning, "lineno", None),
                             "%s: %s" % (warning.category.__name__, warning.message))
                text, _reason = self.text(rel)
                if text is None:
                    continue
                try:
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore")
                        tree = ast.parse(text, filename=rel)
                except (SyntaxError, ValueError):
                    continue
                for line, message in py39_problems(tree):
                    self.add(ERROR, "python", rel, line, message)

    # -- json -----------------------------------------------------------------

    def check_json(self) -> None:
        skills = set(self.skill_names())
        for rel in self.files:
            lower = rel.lower()
            if not lower.endswith((".json", ".jsonl")):
                continue
            text, reason = self.text(rel)
            if text is None:
                self.add(ERROR, "json", rel, None, "cannot read as UTF-8 text (%s)" % reason)
                continue
            if lower.endswith(".json"):
                try:
                    json.loads(text)
                except ValueError as exc:
                    self.add(ERROR, "json", rel, getattr(exc, "lineno", None), "invalid JSON: %s" % exc)
                continue
            for number, line in enumerate(text.split("\n"), 1):
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except ValueError as exc:
                    self.add(ERROR, "json", rel, number, "invalid JSON line: %s" % exc)
                    continue
                if rel == "evals/triggering.jsonl" and isinstance(row, dict):
                    skill = row.get("skill")
                    if skill not in skills:
                        self.add(ERROR, "json", rel, number,
                                 "row names skill %r, but skills/%s/ does not exist" % (skill, skill))

    # -- freshness ------------------------------------------------------------

    def check_freshness(self) -> None:
        rel = "shared/growthkit/http.py"
        if not os.path.isfile(self.abspath(rel)):
            return
        text, _ = self.text(rel)
        match = re.search(r'^BROWSER_UA_UPDATED\s*=\s*["\'](\d{4}-\d{2}-\d{2})["\']', text or "", re.M)
        if not match:
            self.add(WARNING, "freshness", rel, None, "BROWSER_UA_UPDATED = \"YYYY-MM-DD\" not found")
            return
        line = (text or "")[:match.start()].count("\n") + 1
        try:
            updated = datetime.strptime(match.group(1), "%Y-%m-%d").date()
        except ValueError:
            self.add(WARNING, "freshness", rel, line, "BROWSER_UA_UPDATED is not a valid date")
            return
        age = (self.today - updated).days
        if age > BROWSER_UA_MAX_AGE_DAYS:
            self.add(WARNING, "freshness", rel, line,
                     "BROWSER_UA was last updated %s (%d days ago); update the Chrome version in it "
                     "to the current stable release and bump BROWSER_UA_UPDATED" % (match.group(1), age))

    # -- run ------------------------------------------------------------------

    def run(self, checks: Iterable[str]) -> List[Finding]:
        for check in checks:
            getattr(self, "check_" + check)()
        return self.findings


def _body_offset(text: str) -> int:
    """Character offset where the body starts (just after the closing '---' line)."""
    match = re.match(r"---[ \t]*\r?\n.*?^---[ \t]*\r?$\n?", text, re.S | re.M)
    return match.end() if match else 0


def _line_of(text: str, needle: str) -> Optional[int]:
    index = text.find(needle)
    return text[:index].count("\n") + 1 if index >= 0 else None


def _annotation(finding: Finding) -> str:
    """A GitHub Actions workflow command for one finding."""
    def escape(value: str, prop: bool = False) -> str:
        value = value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        if prop:
            value = value.replace(":", "%3A").replace(",", "%2C")
        return value

    props = "file=%s" % escape(finding.path, True)
    if finding.line:
        props += ",line=%d" % finding.line
    props += ",title=%s" % escape("lint_repo " + finding.check, True)
    return "::%s %s::%s" % (finding.level, props, escape(finding.message))


def format_finding(finding: Finding) -> str:
    where = finding.path + (":%d" % finding.line if finding.line else "")
    return "%s: %s: [%s] %s" % (where, finding.level, finding.check, finding.message)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lint_repo.py",
        description="Lint the repo: dashes, SKILL.md/agent frontmatter, install lists, "
                    "Python compilation and 3.9 compatibility, JSON, UA freshness.",
    )
    parser.add_argument("--check", action="append", choices=CHECKS,
                        help="run only this check (repeatable); default: all")
    parser.add_argument("--root", default=REPO_ROOT, help="repository root (default: the folder above tools/)")
    parser.add_argument("--no-git", action="store_true", help="walk the folder instead of asking git for files")
    parser.add_argument("--no-warnings", action="store_true", help="do not print warnings (they never fail)")
    parser.add_argument("--today", help=argparse.SUPPRESS)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    repo = os.path.abspath(args.root)
    if not os.path.isdir(repo):
        print("lint_repo: %s is not a folder" % repo, file=sys.stderr)
        return 2
    today = None
    if args.today:
        try:
            today = datetime.strptime(args.today, "%Y-%m-%d").date()
        except ValueError:
            print("lint_repo: --today must be YYYY-MM-DD", file=sys.stderr)
            return 2
    checks = args.check or list(CHECKS)
    files, source = repo_files(repo, use_git=not args.no_git)
    findings = Linter(repo, files, today).run(checks)
    findings.sort(key=lambda f: (f.path, f.line or 0, f.level, f.check, f.message))

    errors = [f for f in findings if f.level == ERROR]
    warnings_found = [f for f in findings if f.level == WARNING]
    in_actions = os.environ.get("GITHUB_ACTIONS") == "true"
    for finding in findings:
        if finding.level == WARNING and args.no_warnings:
            continue
        print(format_finding(finding))
        if in_actions:
            print(_annotation(finding))
    print(
        "lint_repo: %d files (%s), checks: %s. %d error(s), %d warning(s)."
        % (len(files), source, ", ".join(checks), len(errors), len(warnings_found))
    )
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
