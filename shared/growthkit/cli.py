"""Shared command-line contract for every skill script.

Contract (documented for the model in shared/standards/skill-authoring.md):

    script.py <input> [--json] [--out PATH] [--demo] [--timeout N]

    input       a URL, a file path, or '-' to read stdin. stdin is read ONLY
                when '-' is given, so a script never blocks on (or crashes
                over) the non-TTY stdin that agent shells provide.
    --json      stdout carries exactly one JSON document; logs go to stderr.
    --out PATH  also save the JSON envelope to PATH.
    --demo      run on built-in sample data. Never automatic, and the output
                says DEMO DATA at the top.

Exit codes:
    0  ok
    2  usage or input error (bad arguments, missing file, invalid JSON)
    3  target unreachable or blocked (DNS, timeout, HTTP error, bot wall)
    4  partial result (some parts failed; see "errors" and "notes")
    5  nothing to analyze (empty page, JS shell, no rows)
    1  is left to Python for unexpected crashes (a bug)

Every JSON envelope has a top-level "status", "errors" and "notes".

Coercion helpers turn what people (and models) type into clean values:
"yes"/"no"/"true"/"false" into bools, "25%", "$1,200", "12k" and "1/4" into
numbers, and "skip", "n/a", "" or "unknown" into None.
"""

from __future__ import annotations

import argparse
import importlib
import json
import math
import os
import re
import sys
from datetime import date, datetime
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple, Union

from . import INSTALL_HINT, __version__

# ---------------------------------------------------------------------------
# Exit codes and statuses
# ---------------------------------------------------------------------------

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_UNREACHABLE = 3
EXIT_PARTIAL = 4
EXIT_NOTHING = 5

STATUS_OK = "ok"
STATUS_PARTIAL = "partial"
STATUS_UNREACHABLE = "unreachable"
STATUS_BLOCKED = "blocked"
STATUS_NOTHING = "nothing_to_analyze"
STATUS_USAGE = "usage_error"

STATUS_EXIT = {
    STATUS_OK: EXIT_OK,
    STATUS_PARTIAL: EXIT_PARTIAL,
    STATUS_UNREACHABLE: EXIT_UNREACHABLE,
    STATUS_BLOCKED: EXIT_UNREACHABLE,
    STATUS_NOTHING: EXIT_NOTHING,
    STATUS_USAGE: EXIT_USAGE,
}

DEMO_BANNER = "DEMO DATA - built-in sample input, not an analysis of a real product"


def exit_code_for(status: str) -> int:
    """Map an envelope status to its exit code (unknown statuses count as partial)."""
    return STATUS_EXIT.get(status, EXIT_PARTIAL)


class UsageError(Exception):
    """Bad arguments or unusable input. Scripts turn it into exit code 2."""


# ---------------------------------------------------------------------------
# Logging (always stderr, so stdout stays machine-readable)
# ---------------------------------------------------------------------------


def log(message: str, tool: Optional[str] = None) -> None:
    """Print a progress or diagnostic line to stderr."""
    prefix = "[%s] " % tool if tool else ""
    print(prefix + message, file=sys.stderr, flush=True)


def _wants_json(argv: Optional[List[str]] = None) -> bool:
    """True when --json appears on the command line (used before parsing)."""
    args = sys.argv[1:] if argv is None else argv
    return "--json" in args


def import_or_exit(module: str, package: Optional[str] = None) -> Any:
    """Import a third-party module or exit 2 with a one-line install hint.

    Used at the top of http.py and html.py so a missing dependency gives the
    same clear message everywhere instead of a ModuleNotFoundError traceback.
    """
    try:
        return importlib.import_module(module)
    except ImportError:
        name = package or module
        message = "Missing Python package '%s'. Install with: %s" % (name, INSTALL_HINT)
        print(message, file=sys.stderr)
        if _wants_json():
            print(json.dumps({"status": STATUS_USAGE, "errors": [message], "notes": []}))
        raise SystemExit(EXIT_USAGE)


# ---------------------------------------------------------------------------
# JSON helpers
# ---------------------------------------------------------------------------


def _json_default(value: Any) -> Any:
    """Make common non-JSON values serializable instead of crashing."""
    if isinstance(value, (set, frozenset, tuple)):
        return list(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    if hasattr(value, "__fspath__"):
        return os.fspath(value)
    return str(value)


def to_json(data: Any, compact: bool = True) -> str:
    """Serialize to JSON. Compact by default to save the model's tokens."""
    if compact:
        return json.dumps(data, ensure_ascii=False, separators=(",", ":"), default=_json_default)
    return json.dumps(data, ensure_ascii=False, indent=2, default=_json_default)


def _write_stdout(text: str) -> None:
    """Print text, falling back to ASCII escapes if the console cannot encode it."""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode("ascii", "backslashreplace").decode("ascii"))
    sys.stdout.flush()


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------


class ArgumentParser(argparse.ArgumentParser):
    """argparse with the shared contract for usage errors.

    A usage error exits 2 (argparse's default too). With --json on the
    command line it also prints a JSON envelope to stdout, so a caller that
    always parses stdout gets {"status": "usage_error", ...} instead of
    nothing.
    """

    def error(self, message: str) -> None:  # type: ignore[override]
        self.print_usage(sys.stderr)
        print("%s: error: %s" % (self.prog, message), file=sys.stderr)
        if _wants_json():
            _write_stdout(to_json({
                "tool": self.prog,
                "version": __version__,
                "status": STATUS_USAGE,
                "errors": [message],
                "notes": ["Run with --help to see the arguments."],
            }))
        raise SystemExit(EXIT_USAGE)


def build_parser(
    description: str,
    input_help: str = "URL, file path, or '-' to read stdin",
    prog: Optional[str] = None,
    epilog: Optional[str] = None,
    input_required: bool = False,
    demo: bool = True,
    timeout: bool = True,
) -> ArgumentParser:
    """Return a parser with the shared flags. Scripts add their own on top.

    The positional input is optional at the parser level so --demo can run
    without it; call resolve_input() afterwards to enforce "input or --demo".
    """
    parser = ArgumentParser(
        prog=prog,
        description=description,
        epilog=epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("input", nargs=None if input_required else "?", help=input_help)
    parser.add_argument(
        "--json", action="store_true",
        help="print only JSON to stdout (logs go to stderr)",
    )
    parser.add_argument(
        "--out", metavar="PATH",
        help="also save the JSON result to PATH",
    )
    if demo:
        parser.add_argument(
            "--demo", action="store_true",
            help="run on built-in sample data (output is labelled DEMO DATA)",
        )
    if timeout:
        parser.add_argument(
            "--timeout", type=float, default=15.0, metavar="SECONDS",
            help="network timeout per request (default: 15)",
        )
    parser.add_argument("--version", action="version", version="%(prog)s " + __version__)
    return parser


# ---------------------------------------------------------------------------
# Input resolution: URL, file, or explicit stdin
# ---------------------------------------------------------------------------

# Endings that mean "this was meant to be a local file", even though some are
# also real top-level domains (.md is Moldova). A missing file with one of
# these endings is reported as a missing file, not fetched as a website.
_FILE_EXTENSIONS = {
    "html", "htm", "xhtml", "json", "jsonl", "csv", "tsv", "txt", "md",
    "markdown", "xml", "yaml", "yml", "xlsx", "xls", "pdf",
}

_DOMAIN_RE = re.compile(
    r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z][a-z0-9-]{1,62}(?::\d{1,5})?(?:[/?#].*)?$",
    re.IGNORECASE,
)


def looks_like_url(text: str) -> bool:
    """True for 'https://x.y/...' and bare domains such as 'linear.app/pricing'."""
    value = (text or "").strip()
    if not value or any(ch.isspace() for ch in value):
        return False
    if re.match(r"^https?://", value, re.IGNORECASE):
        return True
    if value.startswith(("/", ".", "~", "-")):
        return False
    if not _DOMAIN_RE.match(value):
        return False
    host = re.split(r"[/?#:]", value, maxsplit=1)[0]
    return host.rsplit(".", 1)[-1].lower() not in _FILE_EXTENSIONS


def read_stdin_text() -> str:
    """Read all of stdin. Only called when the user passed '-' explicitly."""
    stream = sys.stdin
    if stream is None or getattr(stream, "closed", False):
        raise UsageError("'-' means read stdin, but stdin is not available.")
    try:
        if stream.isatty():
            log("Reading input from the terminal; finish with Ctrl-D.")
    except (AttributeError, ValueError):
        pass
    text = stream.read()
    if not text.strip():
        raise UsageError("'-' means read stdin, but stdin was empty.")
    return text


def resolve_input(
    value: Optional[str],
    allow_url: bool = True,
    allow_file: bool = True,
    allow_stdin: bool = True,
    demo: bool = False,
) -> Dict[str, Any]:
    """Classify the positional input and load it when it is a file or stdin.

    Returns {"kind": "url"|"file"|"stdin"|"demo", "value": str|None,
    "text": str|None}. URLs are returned as typed; normalize them with
    http.normalize_url() before fetching. Raises UsageError (exit 2) for a
    missing input, a missing file, or an input type the script does not take.
    """
    if demo:
        return {"kind": "demo", "value": None, "text": None}
    accepted = []
    if allow_url:
        accepted.append("a URL")
    if allow_file:
        accepted.append("a file path")
    if allow_stdin:
        accepted.append("'-' to read stdin")
    accepted_text = ", ".join(accepted)
    if value is None or not str(value).strip():
        raise UsageError(
            "No input given. Pass %s, or --demo for sample data." % accepted_text
        )
    value = str(value).strip()
    if value == "-":
        if not allow_stdin:
            raise UsageError("This script does not read stdin. Pass %s." % accepted_text)
        return {"kind": "stdin", "value": "-", "text": read_stdin_text()}
    if allow_file and os.path.isfile(value):
        try:
            with open(value, "rb") as handle:
                raw = handle.read()
        except OSError as exc:
            raise UsageError("Cannot read %s: %s" % (value, exc))
        return {"kind": "file", "value": value, "text": raw.decode("utf-8-sig", "replace")}
    if allow_url and looks_like_url(value):
        return {"kind": "url", "value": value, "text": None}
    if os.path.isdir(value):
        raise UsageError("%s is a folder; pass a file inside it." % value)
    if allow_file:
        hint = ""
        if allow_url and "." in value and "/" not in value:
            hint = " If you meant a website, pass it as https://%s" % value
        raise UsageError("File not found: %s.%s" % (value, hint))
    raise UsageError("Not a valid URL: %s" % value)


def load_json_input(
    value: Optional[str],
    expect: Union[type, Tuple[type, ...]] = dict,
    demo_data: Any = None,
    demo: bool = False,
) -> Tuple[Any, Dict[str, Any]]:
    """Load JSON from a file path or '-' (stdin). Returns (data, source).

    With demo=True returns demo_data (a deep copy is the caller's choice).
    Raises UsageError for missing input, invalid JSON, or a top-level value
    of the wrong type (for example a list where an object is expected).
    """
    if demo:
        return demo_data, {"kind": "demo", "value": None, "text": None}
    source = resolve_input(value, allow_url=False, allow_file=True, allow_stdin=True)
    label = "stdin" if source["kind"] == "stdin" else source["value"]
    try:
        data = json.loads(source["text"])
    except ValueError as exc:
        raise UsageError("Invalid JSON in %s: %s" % (label, exc))
    if expect is not None and not isinstance(data, expect):
        names = expect.__name__ if isinstance(expect, type) else "/".join(t.__name__ for t in expect)
        kind = {"dict": "a JSON object", "list": "a JSON array"}.get(names, names)
        raise UsageError(
            "Expected %s in %s, got %s." % (kind, label, type(data).__name__)
        )
    return data, source


# ---------------------------------------------------------------------------
# Run: collects errors/notes and emits the envelope with the right exit code
# ---------------------------------------------------------------------------


class Run:
    """One script invocation: logging, errors, notes, and the final output.

    Typical use:

        parser = cli.build_parser("CRO fact extractor")
        args = parser.parse_args()
        run = cli.Run("cro_auditor", args)
        try:
            source = cli.resolve_input(args.input, demo=args.demo)
        except cli.UsageError as exc:
            return run.fail(cli.STATUS_USAGE, str(exc))
        ...
        return run.emit({"facts": facts}, human=format_report)
    """

    def __init__(
        self,
        tool: str,
        args: Optional[argparse.Namespace] = None,
        json_mode: Optional[bool] = None,
        out: Optional[str] = None,
        demo: Optional[bool] = None,
    ) -> None:
        self.tool = tool
        self.json_mode = bool(getattr(args, "json", False)) if json_mode is None else json_mode
        self.out = getattr(args, "out", None) if out is None else out
        self.demo = bool(getattr(args, "demo", False)) if demo is None else demo
        self.errors: List[str] = []
        self.notes: List[str] = []
        if self.demo:
            self.notes.append(DEMO_BANNER)
            self.log(DEMO_BANNER)

    # -- collection ---------------------------------------------------------

    def log(self, message: str) -> None:
        """Progress line to stderr (never stdout)."""
        log(message, self.tool)

    def note(self, message: str) -> None:
        """Something the reader should know that is not a failure."""
        if message not in self.notes:
            self.notes.append(message)

    def error(self, message: str) -> None:
        """Something that failed. A run with errors is at best 'partial'."""
        if message not in self.errors:
            self.errors.append(message)
        self.log("error: " + message)

    # -- output -------------------------------------------------------------

    def envelope(self, data: Optional[Dict[str, Any]] = None, status: Optional[str] = None) -> Dict[str, Any]:
        """Build {tool, version, status, demo, errors, notes, ...data}."""
        payload = dict(data or {})
        errors = list(self.errors)
        notes = list(self.notes)
        for item in payload.pop("errors", None) or []:
            if item not in errors:
                errors.append(item)
        for item in payload.pop("notes", None) or []:
            if item not in notes:
                notes.append(item)
        payload.pop("status", None)
        if status is None:
            status = STATUS_PARTIAL if errors else STATUS_OK
        envelope: Dict[str, Any] = {
            "tool": self.tool,
            "version": __version__,
            "status": status,
            "demo": self.demo,
            "errors": errors,
            "notes": notes,
        }
        envelope.update(payload)
        return envelope

    def emit(
        self,
        data: Optional[Dict[str, Any]] = None,
        status: Optional[str] = None,
        human: Union[None, str, Callable[[Dict[str, Any]], str]] = None,
    ) -> int:
        """Print the result and return the exit code for it.

        JSON mode prints the envelope only. Human mode prints `human` (a
        string, or a function of the envelope), or pretty JSON when no
        formatter is given. --out always saves the JSON envelope.
        """
        envelope = self.envelope(data, status)
        if self.out:
            try:
                directory = os.path.dirname(os.path.abspath(self.out))
                os.makedirs(directory, exist_ok=True)
                with open(self.out, "w", encoding="utf-8") as handle:
                    handle.write(to_json(envelope, compact=False) + "\n")
                self.log("Saved JSON to %s" % self.out)
            except OSError as exc:
                envelope["errors"].append("Could not write --out file %s: %s" % (self.out, exc))
                if envelope["status"] == STATUS_OK:
                    envelope["status"] = STATUS_PARTIAL
        if self.json_mode:
            _write_stdout(to_json(envelope))
        else:
            if self.demo:
                _write_stdout("=" * 70 + "\n  " + DEMO_BANNER + "\n" + "=" * 70)
            if callable(human):
                text = human(envelope)
            elif isinstance(human, str):
                text = human
            else:
                text = to_json(envelope, compact=False)
            _write_stdout(text)
            # Errors recorded with error() were already logged; log the ones
            # that arrived inside `data` so a human run still shows them.
            for item in envelope["errors"]:
                if item not in self.errors:
                    log("error: " + item, self.tool)
        return exit_code_for(envelope["status"])

    def fail(self, status: str, message: str, data: Optional[Dict[str, Any]] = None) -> int:
        """Record an error and emit an envelope with the given failure status."""
        self.error(message)
        return self.emit(data or {}, status=status, human="Error: " + message)


def fetch_outcome(result: Dict[str, Any]) -> Tuple[str, str]:
    """Translate an http.fetch() result into (envelope status, message).

    ok -> ok; too_large -> partial; js_shell / not_html -> nothing_to_analyze;
    blocked -> blocked; http_error / unreachable -> unreachable.
    The message is written for the model and says what to do next.
    """
    status = result.get("status")
    url = result.get("final_url") or result.get("url") or "the page"
    code = result.get("http_status")
    if status == "ok":
        return STATUS_OK, ""
    if status == "too_large":
        return STATUS_PARTIAL, (
            "%s is larger than the %d-byte limit; only the first part was analyzed."
            % (url, result.get("bytes") or 0)
        )
    if status == "js_shell":
        signals = result.get("js_shell_signals") or {}
        return STATUS_NOTHING, (
            "%s returned a JavaScript shell (%s visible words), so static HTML has nothing "
            "to analyze. Render it in a browser and pass the saved HTML file."
            % (url, signals.get("visible_words", 0))
        )
    if status == "not_html":
        return STATUS_NOTHING, "%s returned %s, not an HTML page." % (
            url, result.get("content_type") or "an unknown content type")
    if status == "blocked":
        bot = result.get("bot_protection") or {}
        vendor = bot.get("vendor") or "unknown"
        return STATUS_BLOCKED, (
            "%s blocked the request (HTTP %s, bot protection: %s). Do not score it; "
            "use a browser or a saved HTML file instead." % (url, code, vendor)
        )
    if status == "http_error":
        return STATUS_UNREACHABLE, "%s returned HTTP %s. %s" % (
            url, code, result.get("error") or "")
    return STATUS_UNREACHABLE, "%s could not be reached: %s" % (url, result.get("error") or "unknown error")


def facts_outcome(facts: Dict[str, Any], thin_words: int = 150) -> Tuple[str, str]:
    """Decide whether html.page_facts() output is worth analyzing.

    Use it for file input too (a saved page can be an empty shell).
    Returns (status, message):
      nothing_to_analyze  JS shell, or no visible words at all
      ok + message        thin page: under thin_words words and no <h1>
                          (add the message as a note; a browser render
                          may show more)
      ok + ""             normal page
    """
    words = int(facts.get("word_count") or 0)
    if facts.get("is_js_shell"):
        return STATUS_NOTHING, (
            "The HTML is a JavaScript shell (%d visible words). Render the page in a browser "
            "and pass the saved HTML file." % words
        )
    if words == 0:
        return STATUS_NOTHING, "The page has no visible text to analyze."
    has_h1 = bool((facts.get("headings") or {}).get("h1"))
    if words < thin_words and not has_h1:
        return STATUS_OK, (
            "Thin page: %d visible words and no <h1>. A browser render may show more content." % words
        )
    return STATUS_OK, ""


# ---------------------------------------------------------------------------
# Coercion helpers
# ---------------------------------------------------------------------------

MISSING_TOKENS = frozenset({
    "", "skip", "skipped", "n/a", "na", "n.a.", "none", "null", "nil", "nan",
    "unknown", "not sure", "unsure", "no idea", "idk", "dont know", "don't know",
    "do not know", "?", "-", "--", "tbd", "not applicable", "not available",
})

TRUE_TOKENS = frozenset({"yes", "y", "true", "t", "1", "on", "enabled", "required"})
FALSE_TOKENS = frozenset({"no", "n", "false", "f", "0", "off", "disabled", "not required"})


class CoercionError(ValueError):
    """A value could not be read as the expected type."""

    def __init__(self, message: str, field: Optional[str] = None, value: Any = None) -> None:
        self.field = field
        self.value = value
        prefix = "%s: " % field if field else ""
        super().__init__(prefix + message)


def _norm_token(value: str) -> str:
    return " ".join(value.strip().lower().replace("\u2019", "'").split())


def is_missing(value: Any) -> bool:
    """True for None, NaN, empty strings and words like 'skip' or 'n/a'."""
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    if isinstance(value, str):
        return _norm_token(value) in MISSING_TOKENS
    return False


def to_bool(value: Any, field: Optional[str] = None) -> Optional[bool]:
    """Read yes/no answers. 'no', 'false' and '0' are False (not truthy strings)."""
    if is_missing(value):
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        if value in (0, 1):
            return bool(value)
        raise CoercionError("expected yes/no, got the number %r" % value, field, value)
    if isinstance(value, str):
        token = _norm_token(value)
        if token in TRUE_TOKENS:
            return True
        if token in FALSE_TOKENS:
            return False
        # Accept a leading yes/no followed by an explanation: "no - email only".
        first = re.split(r"[\s,;:.!()/-]+", token, maxsplit=1)[0]
        if first in ("yes", "y", "true"):
            return True
        if first in ("no", "n", "false"):
            return False
    raise CoercionError("expected yes/no, got %r" % (value,), field, value)


_CURRENCY_RE = re.compile(r"[$\u20ac\u00a3\u00a5\u20ba\u20b9]|\b(?:usd|eur|gbp|try|inr|jpy|cad|aud)\b", re.I)
_SUFFIX = {"k": 1e3, "m": 1e6, "mm": 1e6, "b": 1e9, "bn": 1e9}
_NUMBER_RE = re.compile(r"^([+-]?)(\d+(?:\.\d+)?|\.\d+)\s*(k|m|mm|b|bn)?$", re.I)
_FRACTION_RE = re.compile(r"^([+-]?\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)$")


def _parse_number_text(text: str, field: Optional[str], original: Any) -> Tuple[float, bool]:
    """Parse a numeric string. Returns (value, had_percent_sign)."""
    token = text.strip().lower()
    token = token.replace("\u2212", "-")  # unicode minus
    token = re.sub(r"^(?:~|approx\.?|about|around|ca\.?)\s*", "", token)
    had_percent = "%" in token
    token = token.replace("%", "").replace("percent", "")
    token = _CURRENCY_RE.sub("", token)
    token = token.replace("_", "").replace(" ", "")
    fraction = _FRACTION_RE.match(token)
    if fraction:
        denominator = float(fraction.group(2))
        if denominator == 0:
            raise CoercionError("division by zero in %r" % (original,), field, original)
        return float(fraction.group(1)) / denominator, had_percent
    # Thousands separators: "1,200,000" -> 1200000. A single comma with one
    # or two decimals ("2,5") is a decimal comma.
    if re.match(r"^[+-]?\d{1,3}(?:,\d{3})+(?:\.\d+)?(?:k|m|mm|b|bn)?$", token):
        token = token.replace(",", "")
    elif re.match(r"^[+-]?\d+,\d{1,2}$", token):
        token = token.replace(",", ".")
    match = _NUMBER_RE.match(token)
    if not match:
        if re.match(r"^[+-]?\d+(?:\.\d+)?-\d+(?:\.\d+)?$", token):
            raise CoercionError("expected one number, got the range %r" % (original,), field, original)
        raise CoercionError("expected a number, got %r" % (original,), field, original)
    sign, digits, suffix = match.groups()
    number = float(digits) * (_SUFFIX[suffix.lower()] if suffix else 1.0)
    return (-number if sign == "-" else number), had_percent


def _check_range(number: float, field: Optional[str], original: Any,
                 minimum: Optional[float], maximum: Optional[float]) -> float:
    if minimum is not None and number < minimum:
        raise CoercionError("must be at least %s, got %r" % (_fmt(minimum), original), field, original)
    if maximum is not None and number > maximum:
        raise CoercionError("must be at most %s, got %r" % (_fmt(maximum), original), field, original)
    return number


def _fmt(number: float) -> str:
    return str(int(number)) if float(number).is_integer() else str(number)


def to_number(
    value: Any,
    field: Optional[str] = None,
    minimum: Optional[float] = None,
    maximum: Optional[float] = None,
) -> Optional[float]:
    """Read a number from 42, '42', '$1,200', '12k', '1.5M', '25%' or '1/4'.

    '25%' returns 25.0 (the number as written); use to_percent() when the
    field is a percentage and fractions like '1/4' should become 25.0.
    Booleans are rejected: True is almost always a mistake for a number.
    """
    if is_missing(value):
        return None
    if isinstance(value, bool):
        raise CoercionError("expected a number, got %r" % value, field, value)
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        number, _ = _parse_number_text(value, field, value)
    else:
        raise CoercionError("expected a number, got %s" % type(value).__name__, field, value)
    if math.isnan(number) or math.isinf(number):
        raise CoercionError("expected a finite number, got %r" % (value,), field, value)
    return _check_range(number, field, value, minimum, maximum)


def to_int(
    value: Any,
    field: Optional[str] = None,
    minimum: Optional[float] = None,
    maximum: Optional[float] = None,
) -> Optional[int]:
    """Like to_number() but requires a whole number ('1,200' -> 1200)."""
    number = to_number(value, field, minimum, maximum)
    if number is None:
        return None
    if not float(number).is_integer():
        raise CoercionError("expected a whole number, got %r" % (value,), field, value)
    return int(number)


def to_percent(
    value: Any,
    field: Optional[str] = None,
    assume_fraction: bool = False,
    minimum: Optional[float] = None,
    maximum: Optional[float] = None,
) -> Optional[float]:
    """Read a percentage in percent units: '25%', '25', 25 and '1/4' -> 25.0.

    A bare number is taken as already being in percent (0.8 means 0.8%,
    which is a normal monthly churn). Pass assume_fraction=True only for
    fields where people type rates as fractions; then 0.25 -> 25.0.
    """
    if is_missing(value):
        return None
    if isinstance(value, bool):
        raise CoercionError("expected a percentage, got %r" % value, field, value)
    if isinstance(value, (int, float)):
        number = float(value)
        if assume_fraction and 0 <= abs(number) <= 1:
            number *= 100.0
    elif isinstance(value, str):
        is_fraction = bool(_FRACTION_RE.match(value.strip().replace(" ", "")))
        number, had_percent = _parse_number_text(value, field, value)
        if is_fraction and not had_percent:
            number *= 100.0
        elif assume_fraction and not had_percent and 0 <= abs(number) <= 1:
            number *= 100.0
    else:
        raise CoercionError("expected a percentage, got %s" % type(value).__name__, field, value)
    if math.isnan(number) or math.isinf(number):
        raise CoercionError("expected a finite percentage, got %r" % (value,), field, value)
    return _check_range(number, field, value, minimum, maximum)


def to_text(value: Any, field: Optional[str] = None) -> Optional[str]:
    """Strip a string; missing tokens become None. Numbers become strings."""
    if is_missing(value):
        return None
    if isinstance(value, (str, int, float)) and not isinstance(value, bool):
        return str(value).strip()
    raise CoercionError("expected text, got %s" % type(value).__name__, field, value)


_COERCERS: Dict[str, Callable[..., Any]] = {
    "bool": to_bool,
    "number": to_number,
    "int": to_int,
    "percent": to_percent,
    "str": to_text,
    "text": to_text,
}


def coerce_record(
    payload: Dict[str, Any],
    schema: Dict[str, Union[str, Callable[..., Any]]],
) -> Tuple[Dict[str, Any], List[str], List[str]]:
    """Coerce every schema field of a dict. Returns (clean, errors, unknown).

    schema maps field -> "bool" | "number" | "int" | "percent" | "str", or a
    callable(value, field) such as functools.partial(to_number, minimum=0).
    Missing fields come back as None. Errors are human-readable strings
    naming the field ("monthly_churn: expected a number, got 'abc'").
    unknown lists payload keys that are not in the schema.
    """
    if not isinstance(payload, dict):
        raise UsageError("Expected a JSON object with named fields, got %s." % type(payload).__name__)
    clean: Dict[str, Any] = {}
    errors: List[str] = []
    for name, kind in schema.items():
        coercer = _COERCERS[kind] if isinstance(kind, str) else kind
        try:
            clean[name] = coercer(payload.get(name), field=name)
        except CoercionError as exc:
            clean[name] = None
            errors.append(str(exc))
    unknown = [key for key in payload if key not in schema]
    return clean, errors, unknown


__all__ = [
    "EXIT_OK", "EXIT_USAGE", "EXIT_UNREACHABLE", "EXIT_PARTIAL", "EXIT_NOTHING",
    "STATUS_OK", "STATUS_PARTIAL", "STATUS_UNREACHABLE", "STATUS_BLOCKED",
    "STATUS_NOTHING", "STATUS_USAGE", "DEMO_BANNER",
    "UsageError", "CoercionError", "ArgumentParser", "Run",
    "build_parser", "resolve_input", "load_json_input", "read_stdin_text",
    "looks_like_url", "fetch_outcome", "facts_outcome", "exit_code_for", "import_or_exit",
    "log", "to_json", "is_missing", "to_bool", "to_number", "to_int",
    "to_percent", "to_text", "coerce_record",
]
