#!/usr/bin/env python3
"""Onboarding funnel from the user's own analytics data (counts only, no PII).

Reads what the user downloaded and computes the numbers the rubric and the
report need. The model interprets them; nothing here judges.

Inputs (detected automatically):
  event log     a raw event export, one row per event: PostHog (event,
                distinct_id, timestamp), Mixpanel (event, distinct_id, time),
                Amplitude (event_type, user_id, event_time), GA4 BigQuery
                (event_name, user_pseudo_id, event_timestamp) or any table
                with a user, an event name and a time column.
                Pass the onboarding steps in order with --step (first step =
                the cohort entry, usually signup; last step = the activation
                event). Output: per-step conversion, the biggest drop, median
                and p75 time to each step and to activation, and activation
                by weekly (or monthly) signup cohort with 95 % Wilson
                intervals. Only cohorts whose whole conversion window has
                elapsed count toward the activation rate.
  funnel export a funnel table exported from GA4, PostHog, Mixpanel or
                Amplitude (step and count columns, optional breakdown and
                time to convert), or any step,count CSV.
  step counts   a JSON file the model writes from numbers the user typed:
                {"steps": [{"name": "Signed up", "count": 1200}, ...]}
                or {"segments": {"Organic": [...], "Paid": [...]}}.

Usage (from the user's project folder):
    python3 onboarding_funnel.py exports/events.csv --step signed_up \\
        --step created_project --step invited_teammate --window-days 14 --json
    python3 onboarding_funnel.py exports/funnel.csv --json
    python3 onboarding_funnel.py growth-reports/.cache/steps.json --json
    python3 onboarding_funnel.py --demo --json

User ids are hashed inside growthkit importers and only counted; contact
columns (email, name, phone) are never read. Exit codes: 0 ok, 2 usage or
unsupported file, 4 partial (more than 5 % of rows unreadable), 5 nothing to
analyze.
"""

from __future__ import annotations

import json
import math
import os
import random
import sys
from collections import Counter, OrderedDict, defaultdict
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence, Tuple

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from _growthkit import cli, importers, stats  # noqa: E402

TOOL = "onboarding_funnel"
DEFAULT_WINDOW_DAYS = 14
SMALL_COHORT = 30
MAX_STEPS = 12
OTHER_KIND_HINTS = {
    "billing": "subscription-metrics (MRR, churn, NRR)",
    "invoices": "subscription-metrics (billing and payment failures)",
    "retention": "plg-funnel-analyzer (retention curves) or retention-playbook",
    "search": "geo-seo-auditor or the search-console analysis skill",
}


# ---------------------------------------------------------------------------
# Small math helpers
# ---------------------------------------------------------------------------


def quantile(values: Sequence[float], q: float) -> Optional[float]:
    """Linear interpolation between closest ranks (R type 7, numpy default)."""
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    position = (len(ordered) - 1) * q
    low = int(math.floor(position))
    high = int(math.ceil(position))
    if low == high:
        return float(ordered[low])
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def hours(seconds: Optional[float]) -> Optional[float]:
    return None if seconds is None else round(seconds / 3600.0, 2)


def time_summary(seconds: Sequence[float]) -> Dict[str, Any]:
    return OrderedDict([
        ("n", len(seconds)),
        ("median_hours", hours(quantile(seconds, 0.5))),
        ("p75_hours", hours(quantile(seconds, 0.75))),
        ("p90_hours", hours(quantile(seconds, 0.9))),
    ])


def wilson(successes: float, n: float) -> Optional[List[float]]:
    """95 % Wilson interval as fractions, or None when counts are not whole numbers."""
    if n is None or n <= 0 or successes is None:
        return None
    if float(successes) != int(successes) or float(n) != int(n) or successes > n or successes < 0:
        return None
    low, high = stats.wilson_interval(int(successes), int(n))
    return [round(low, 4), round(high, 4)]


# ---------------------------------------------------------------------------
# Event log
# ---------------------------------------------------------------------------


def _cohort_key(day: date, period: str) -> date:
    if period == "month":
        return day.replace(day=1)
    return day - timedelta(days=day.weekday())


def _cohort_last_day(key: date, period: str) -> date:
    if period == "month":
        following = (key.replace(day=28) + timedelta(days=4)).replace(day=1)
        return following - timedelta(days=1)
    return key + timedelta(days=6)


def event_funnel(events: List[Tuple[str, str, datetime]], steps: List[str], window_days: int,
                 period: str = "week") -> Dict[str, Any]:
    """Ordered funnel, time to activation and cohort activation from (user, event, time) rows.

    A user enters at their FIRST steps[0] event. Each later step must happen
    after the previous one (other events may happen in between) and within
    window_days of the entry. The last step is the activation event.
    """
    per_user: Dict[str, List[Tuple[datetime, str]]] = defaultdict(list)
    for user, name, when in events:
        per_user[user].append((when, name))
    for items in per_user.values():
        items.sort()
    data_end = max(when for _u, _n, when in events)
    window = timedelta(days=window_days)
    counts = [0] * len(steps)
    from_previous: List[List[float]] = [[] for _ in steps]
    from_start: List[List[float]] = [[] for _ in steps]
    entries: List[Tuple[date, Optional[float]]] = []    # (cohort day, seconds to activation or None)
    for items in per_user.values():
        position = next((i for i, (_w, name) in enumerate(items) if name == steps[0]), None)
        if position is None:
            continue
        start = previous = items[position][0]
        counts[0] += 1
        activated_after: Optional[float] = None
        for index, step in enumerate(steps[1:], 1):
            position = next((i for i in range(position + 1, len(items))
                             if items[i][1] == step and items[i][0] <= start + window), None)
            if position is None:
                break
            when = items[position][0]
            counts[index] += 1
            from_previous[index].append((when - previous).total_seconds())
            from_start[index].append((when - start).total_seconds())
            previous = when
            if index == len(steps) - 1:
                activated_after = (when - start).total_seconds()
        entries.append((start.date(), activated_after))

    normalized = {"segments": OrderedDict([("all", [
        {"name": step, "count": float(counts[i]),
         "time_to_convert_seconds": quantile(from_previous[i], 0.5) if i else None, "time_raw": None}
        for i, step in enumerate(steps)])]), "notes": []}
    funnel = importers.summarize_funnel(normalized)
    segment = funnel["segments"][0]
    for i, step in enumerate(segment["steps"]):
        step["ci95_from_start"] = wilson(counts[i], counts[0])
        step["hours_from_previous"] = time_summary(from_previous[i]) if i else None
        step["hours_from_start"] = time_summary(from_start[i]) if i else None
        step.pop("time_to_convert_seconds", None)

    cohorts: Dict[date, List[Optional[float]]] = defaultdict(list)
    for day, seconds in entries:
        cohorts[_cohort_key(day, period)].append(seconds)
    cohort_rows = []
    complete_size = complete_activated = 0
    for key in sorted(cohorts):
        members = cohorts[key]
        activated = [s for s in members if s is not None]
        complete = _cohort_last_day(key, period) + window <= data_end.date()
        row = OrderedDict([
            ("cohort", key.isoformat()), ("period", period), ("size", len(members)),
            ("activated", len(activated)),
            ("activation_rate", round(len(activated) / float(len(members)), 4)),
            ("ci95", wilson(len(activated), len(members))),
            ("window_complete", complete), ("small", len(members) < SMALL_COHORT),
            ("time_to_activation", time_summary(activated)),
        ])
        if complete:
            complete_size += len(members)
            complete_activated += len(activated)
        cohort_rows.append(row)
    all_activation = [s for _d, s in entries if s is not None]
    complete_rate = (complete_activated / float(complete_size)) if complete_size else None
    return OrderedDict([
        ("funnel", OrderedDict([
            ("steps", segment["steps"]), ("overall_conversion", segment["overall_conversion"]),
            ("biggest_drop", segment["biggest_drop"]),
        ])),
        ("activation", OrderedDict([
            ("users_entered", counts[0]),
            ("activated_so_far", counts[-1]),
            ("rate_so_far", round(counts[-1] / float(counts[0]), 4) if counts[0] else None),
            ("users_in_complete_cohorts", complete_size),
            ("activated_in_complete_cohorts", complete_activated),
            ("rate_complete_cohorts", round(complete_rate, 4) if complete_rate is not None else None),
            ("ci95_complete_cohorts", wilson(complete_activated, complete_size)),
        ])),
        ("time_to_activation", time_summary(all_activation)),
        ("cohorts", cohort_rows),
        ("data_window", OrderedDict([
            ("first_event", min(when for _u, _n, when in events).isoformat()),
            ("last_event", data_end.isoformat()),
            ("users_in_file", len(per_user)),
            ("events_in_file", len(events)),
        ])),
        ("definitions", OrderedDict([
            ("entry", "a user's first %r event" % steps[0]),
            ("step_order", "each step after the previous one (other events may happen in between), "
                           "within %d days of entry" % window_days),
            ("activation", "reaching %r within %d days of entry" % (steps[-1], window_days)),
            ("rate_complete_cohorts", "activation among %s cohorts whose last member's %d-day window ended "
                                      "before the last event in the file" % (period, window_days)),
            ("rate_so_far", "activation among everyone who entered, including users still inside their "
                            "window (biased low)"),
            ("quantiles", "median, p75 and p90 by linear interpolation; hours"),
            ("ci95", "95% Wilson score interval"),
        ])),
    ])


def analyze_events(normalized: Dict[str, Any], steps: List[str], window_days: int,
                   period: str) -> Tuple[Dict[str, Any], List[str]]:
    events = normalized["events"]
    notes = list(normalized.get("notes", []))
    if not events:
        raise importers.NothingToImport("No readable event rows.")
    names = Counter(name for _u, name, _t in events)
    top = [OrderedDict([("event", name), ("count", count)]) for name, count in names.most_common(30)]
    if not steps:
        notes.append("Pick the onboarding steps from top_events and run again with --step <event> for each "
                     "step in order (first: the signup or account-created event; last: the activation event).")
        return OrderedDict([("events_overview", OrderedDict([
            ("events_in_file", len(events)), ("distinct_events", len(names)), ("top_events", top)])),
            ("funnel", None)]), notes
    missing = [step for step in steps if step not in names]
    if missing:
        raise importers.ImportOptionError(
            "--step %s %s not an event in the file." % (", ".join(repr(m) for m in missing),
                                                       "is" if len(missing) == 1 else "are"),
            {"top_events": top})
    result = event_funnel(events, steps, window_days, period)
    result["events_overview"] = OrderedDict([("events_in_file", len(events)), ("distinct_events", len(names)),
                                             ("top_events", top[:15])])
    cohorts = result["cohorts"]
    if not any(c["window_complete"] for c in cohorts):
        notes.append("No cohort has a complete %d-day window yet (the file ends too soon after the last "
                     "entries), so only the biased-low rate_so_far is available." % window_days)
    if any(c["small"] for c in cohorts):
        notes.append("Cohorts under %d users are flagged small; read their rates through the ci95 interval."
                     % SMALL_COHORT)
    return result, notes


# ---------------------------------------------------------------------------
# Funnel exports and typed step counts
# ---------------------------------------------------------------------------


def _decorate_funnel(summary: Dict[str, Any]) -> Dict[str, Any]:
    for segment in summary["segments"]:
        first = segment["steps"][0]["count"]
        for step in segment["steps"]:
            step["ci95_from_start"] = wilson(step["count"], first)
            seconds = step.pop("time_to_convert_seconds", None)
            step["hours_from_previous_reported"] = hours(seconds)
        segment["ci95_overall"] = wilson(segment["steps"][-1]["count"], first)
    return summary


def step_counts_from_json(payload: Any) -> Dict[str, Any]:
    """{"steps": [...]} or {"segments": {name: [...]}} -> importers' normalized funnel."""
    if not isinstance(payload, dict):
        raise cli.UsageError("Expected a JSON object with 'steps' or 'segments'.")
    unknown = [key for key in payload if key not in ("steps", "segments", "period", "source", "notes")]
    if unknown:
        raise cli.UsageError("Unknown key(s) %s; use steps, segments, period, source, notes."
                             % ", ".join(sorted(unknown)))
    groups: "OrderedDict[str, List[Dict[str, Any]]]" = OrderedDict()
    if payload.get("steps") is not None:
        groups["all"] = payload["steps"]
    for name, steps in (payload.get("segments") or {}).items():
        groups[str(name)] = steps
    if not groups:
        raise cli.UsageError("Give 'steps': [{\"name\": ..., \"count\": ...}, ...] in funnel order.")
    normalized: "OrderedDict[str, List[Dict[str, Any]]]" = OrderedDict()
    for segment, steps in groups.items():
        if not isinstance(steps, list):
            raise cli.UsageError("%s: expected a list of {name, count} objects" % segment)
        clean = []
        for position, step in enumerate(steps, 1):
            if not isinstance(step, dict):
                raise cli.UsageError("%s step %d: expected an object with name and count" % (segment, position))
            name = cli.to_text(step.get("name"), "name") or "Step %d" % position
            count = cli.to_number(step.get("count"), "%s step %d count" % (segment, position), minimum=0)
            if count is None:
                raise cli.UsageError("%s step %d (%s): count is unknown; leave the step out or get the "
                                     "number" % (segment, position, name))
            clean.append({"name": name, "count": count, "time_to_convert_seconds": None, "time_raw": None})
        if clean and clean[0]["count"] <= 0:
            raise importers.NothingToImport("%s: the first step has no users." % segment)
        normalized[segment] = clean
    return {"segments": normalized, "notes": []}


# ---------------------------------------------------------------------------
# Demo data (fictional, deterministic)
# ---------------------------------------------------------------------------

DEMO_STEPS = ["signed_up", "created_workspace", "connected_data_source", "viewed_first_report"]


def demo_events() -> List[Tuple[str, str, datetime]]:
    """A fictional product's events: 8 weekly cohorts, seeded so output is stable."""
    rng = random.Random(20261024)
    start = datetime(2026, 7, 6, 9, 0, 0)
    events: List[Tuple[str, str, datetime]] = []
    for user in range(640):
        uid = "demo-%04d" % user
        signup = start + timedelta(hours=rng.randint(0, 24 * 7 * 8 - 1))
        events.append((uid, "signed_up", signup))
        events.append((uid, "page_viewed", signup + timedelta(minutes=1)))
        if rng.random() < 0.82:
            t1 = signup + timedelta(minutes=rng.randint(2, 30))
            events.append((uid, "created_workspace", t1))
            if rng.random() < 0.41:
                t2 = t1 + timedelta(hours=rng.choice([0.2, 0.5, 2, 6, 20, 30, 50, 90]))
                events.append((uid, "connected_data_source", t2))
                if rng.random() < 0.7:
                    events.append((uid, "viewed_first_report", t2 + timedelta(minutes=rng.randint(3, 600))))
    return events


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------


def _human(env: Dict[str, Any]) -> str:
    if env.get("status") not in ("ok", "partial"):
        return "Errors:\n  " + "\n  ".join(env.get("errors") or [])
    lines = []
    funnel = env.get("funnel")
    if funnel and "steps" in funnel:
        lines.append("Funnel (%s):" % env.get("input", {}).get("kind"))
        for step in funnel["steps"]:
            lines.append("  %d. %-28s %8s  from start %s" % (step["step"], step["name"][:28], int(step["count"]),
                                                            step["conversion_from_start"]))
        lines.append("Biggest drop: %s" % funnel.get("biggest_drop"))
        activation = env.get("activation") or {}
        lines.append("Activation (complete cohorts): %s %s" % (activation.get("rate_complete_cohorts"),
                                                              activation.get("ci95_complete_cohorts")))
        lines.append("Time to activation: %s" % env.get("time_to_activation"))
    elif funnel and "segments" in funnel:
        for segment in funnel["segments"]:
            lines.append("Segment %s: overall %s %s" % (segment["segment"], segment["overall_conversion"],
                                                       segment.get("ci95_overall")))
    overview = env.get("events_overview")
    if overview and not funnel:
        lines.append("Top events: " + ", ".join(e["event"] for e in overview["top_events"][:15]))
    lines += ["Note: " + n for n in env.get("notes") or []]
    return "\n".join(lines)


def build_parser() -> cli.ArgumentParser:
    parser = cli.build_parser(
        "Onboarding funnel, time to activation and cohort activation from an analytics export "
        "(PII-free aggregates).",
        input_help="event log or funnel export (.csv, .tsv, .zip), or a step-count .json",
        prog="onboarding_funnel.py", timeout=False,
    )
    parser.add_argument("--step", action="append", dest="steps", metavar="EVENT",
                        help="event log: an onboarding step event, repeated in order (first = entry, "
                             "last = activation event)")
    parser.add_argument("--window-days", type=int, default=DEFAULT_WINDOW_DAYS,
                        help="event log: days from entry to reach the last step (default %d; use the "
                             "window in the activation definition)" % DEFAULT_WINDOW_DAYS)
    parser.add_argument("--period", choices=("week", "month"), default="week",
                        help="event log: signup cohort period (default week)")
    parser.add_argument("--member", metavar="NAME", help="CSV file to read inside a .zip")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    run = cli.Run(TOOL, args)
    steps = [s.strip() for s in (args.steps or []) if s and s.strip()]
    if len(steps) == 1:
        return run.fail(cli.STATUS_USAGE, "A funnel needs at least two --step events (entry and activation).")
    if len(steps) > MAX_STEPS:
        return run.fail(cli.STATUS_USAGE, "At most %d steps; keep the ones on the path to activation." % MAX_STEPS)
    if len(set(steps)) != len(steps):
        return run.fail(cli.STATUS_USAGE, "Each --step must be a different event.")
    if args.window_days < 1 or args.window_days > 365:
        return run.fail(cli.STATUS_USAGE, "--window-days must be between 1 and 365.")
    try:
        if args.demo:
            normalized = {"events": demo_events(), "notes": []}
            result, notes = analyze_events(normalized, steps or DEMO_STEPS, args.window_days, args.period)
            result["input"] = OrderedDict([("kind", "event_log"), ("file", "demo (fictional product)")])
            for note in notes:
                run.note(note)
            return run.emit(importers.scrub(result), human=_human)
        if not args.input:
            return run.fail(cli.STATUS_USAGE, "Pass the export file (or a step-count .json), or --demo.")
        if not os.path.isfile(args.input):
            hint = " Pass a downloaded file, not a URL." if cli.looks_like_url(args.input) else ""
            return run.fail(cli.STATUS_USAGE, "File not found: %s.%s" % (args.input, hint))
        if args.input.lower().endswith(".json"):
            payload, _source = cli.load_json_input(args.input, expect=dict)
            summary = _decorate_funnel(importers.summarize_funnel(step_counts_from_json(payload)))
            for note in summary.pop("notes", []):
                run.note(note)
            run.note("Counts were typed or copied by hand (not read from an export), so evidence "
                     "confidence is medium at most.")
            result = OrderedDict([("input", OrderedDict([("kind", "step_counts"),
                                                         ("file", os.path.basename(args.input))])),
                                  ("funnel", summary)])
            return run.emit(importers.scrub(result), human=_human)

        loaded = importers.load(args.input, member=args.member)
        kind = loaded["format"]["kind"]
        info = OrderedDict([("file", loaded["file"].get("path_name")), ("format", loaded["format"]),
                            ("rows", loaded["rows"])])
        if kind not in ("events", "funnel"):
            return run.fail(cli.STATUS_USAGE, "%s looks like a %s export (%s). This script reads raw event "
                            "logs and funnel exports; use %s for that file." % (
                                os.path.basename(args.input), kind, loaded["format"]["label"],
                                OTHER_KIND_HINTS.get(kind, "another skill")), importers.scrub({"input": info}))
        for note in loaded["normalized"].get("notes", []):
            run.note(note)
        if kind == "events":
            result, notes = analyze_events(loaded["normalized"], steps, args.window_days, args.period)
            info["kind"] = "event_log"
        else:
            if steps:
                run.note("--step is ignored for a funnel export: the steps come from the file.")
            result = OrderedDict([("funnel", _decorate_funnel(importers.summarize_funnel(loaded["normalized"])))])
            notes = result["funnel"].pop("notes", [])
            info["kind"] = "funnel_export"
            run.note("A funnel export has no per-user times, so time to activation and cohort activation "
                     "need the raw event log.")
        for note in notes:
            run.note(note)
        result["input"] = info
        rows = loaded["rows"]
        status = cli.STATUS_OK
        if rows["data_rows"] and rows["unreadable"] / float(rows["data_rows"]) > importers.UNREADABLE_PARTIAL_SHARE:
            run.error("%d of %d rows could not be read and were skipped." % (rows["unreadable"], rows["data_rows"]))
            status = cli.STATUS_PARTIAL
        elif rows["unreadable"]:
            run.note("%d row(s) could not be read and were skipped." % rows["unreadable"])
        return run.emit(importers.scrub(result), status=status, human=_human)
    except importers.NothingToImport as exc:
        return run.fail(cli.STATUS_NOTHING, importers.scrub(str(exc)), importers.scrub(exc.details))
    except importers.ImportOptionError as exc:
        return run.fail(cli.STATUS_USAGE, importers.scrub(str(exc)), importers.scrub(exc.details))
    except importers.ImportFormatError as exc:
        details = dict(exc.details)
        run.note("Supported: raw event logs (user, event, time columns), funnel step exports (step and "
                 "count columns) or a step-count .json. Contact-list files are refused on purpose.")
        return run.fail(cli.STATUS_USAGE, importers.scrub(str(exc)), importers.scrub(details))
    except (cli.UsageError, cli.CoercionError) as exc:
        return run.fail(cli.STATUS_USAGE, str(exc))


if __name__ == "__main__":
    sys.exit(main())
