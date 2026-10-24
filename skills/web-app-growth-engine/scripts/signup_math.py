#!/usr/bin/env python3
"""Deterministic math for web-app-growth-engine. The model judges; this adds up.

Subcommands (each prints the shared JSON envelope with --json):

    score       weighted signup ease score from the model's rubric scores
                (references/signup-friction-rubric.md). Drops na and
                not_measured dimensions, renormalizes, and withholds the
                composite when the full flow was not seen or less than 60%
                of the applicable weight was measured.
    test-plan   A/B sample size and duration for a signup change, or the
                "ship and measure" verdict when traffic is too low
                (shared stats helper, two proportions, alpha 0.05,
                power 0.8, 4-week limit).
    trial-model paying customers per 1,000 visitors for a no-card trial
                versus a card-required trial, from the user's rates or
                labelled benchmark rows.
    benchmarks  the sourced benchmark rows this skill may cite
                (references/_shared/saas-benchmarks.json).
    teardown    side-by-side facts from several signup_extractor JSON
                files (your signup and competitors'), grouped by site.

Examples:

    python3 signup_math.py score scores.json --json
    python3 signup_math.py test-plan --baseline 0.31 --weekly-visitors 2400 --json
    python3 signup_math.py trial-model --no-card-v2t 0.06 --no-card-t2p 0.15 --json
    python3 signup_math.py benchmarks --json
    python3 signup_math.py teardown us.json rival-a.json rival-b.json --json

Exit codes: 0 ok, 2 usage or input error, 4 partial (some teardown files
unreadable), 5 nothing to analyze.
"""

from __future__ import annotations

import json
import math
import os
import sys
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from _growthkit import cli  # noqa: E402
from _growthkit import stats  # noqa: E402

TOOL = "signup_math"
RUBRIC_VERSION = "signup-rubric-v1"
BENCHMARKS_PATH = os.path.join(os.path.dirname(_HERE), "references", "_shared", "saas-benchmarks.json")

# Dimension weights. Keep in sync with references/signup-friction-rubric.md.
DIMENSIONS: Dict[str, int] = {
    "auth_path": 25,
    "questions": 25,
    "gates": 20,
    "payment": 15,
    "clarity": 10,
    "challenge": 5,
}
STATUSES = ("scored", "na", "not_measured")
CONFIDENCES = ("high", "medium", "low")
MIN_MEASURED_SHARE = 0.6
NOISE_NOTE = ("Model-assigned scores can move a few points between runs; treat differences under 5 "
              "points as noise.")

# Benchmark rows this skill cites (ids from saas-benchmarks.json).
BENCHMARK_METRICS = (
    "visitor_to_signup", "trial_to_paid", "free_to_paid", "form_view_to_completion",
    "form_start_to_completion", "landing_page_conversion", "passkey_signin_share",
    "signin_success_rate",
)
TRIAL_DEFAULTS = {
    "organic": {
        "no_card_v2t": "visitor_to_signup.fps2025.trial_opt_in.organic",
        "no_card_t2p": "trial_to_paid.fps2025.trial_opt_in.organic",
        "card_v2t": "visitor_to_signup.fps2025.trial_opt_out.organic",
        "card_t2p": "trial_to_paid.fps2025.trial_opt_out.organic",
    },
    "paid": {
        "no_card_v2t": "visitor_to_signup.fps2025.trial_opt_in.paid",
        "no_card_t2p": "trial_to_paid.fps2025.trial_opt_in.paid",
        "card_v2t": "visitor_to_signup.fps2025.trial_opt_out.paid",
        "card_t2p": "trial_to_paid.fps2025.trial_opt_out.paid",
    },
}
WEEKS_PER_MONTH = 4.33


# ---------------------------------------------------------------------------
# score
# ---------------------------------------------------------------------------


def score(payload: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str], List[str]]:
    """Composite signup ease score from rubric scores. Returns (result, errors, notes).

    errors are input problems (exit 2 when any); notes explain withheld totals.
    """
    errors: List[str] = []
    notes: List[str] = []
    if not isinstance(payload, dict):
        return {}, ["Expected a JSON object with 'dimensions'."], notes
    raw_dims = payload.get("dimensions")
    if isinstance(raw_dims, dict):
        raw_dims = [dict(value, id=key) for key, value in raw_dims.items() if isinstance(value, dict)]
    if not isinstance(raw_dims, list) or not raw_dims:
        return {}, ["'dimensions' must be a non-empty list of {id, score, status, confidence, evidence}."], notes
    try:
        full_flow = cli.to_bool(payload.get("full_flow_seen"), "full_flow_seen")
    except cli.CoercionError as exc:
        errors.append(str(exc))
        full_flow = None
    dims: Dict[str, Dict[str, Any]] = {}
    for item in raw_dims:
        if not isinstance(item, dict):
            errors.append("Each dimension must be an object, got %r." % (item,))
            continue
        dim_id = str(item.get("id") or "").strip()
        if dim_id not in DIMENSIONS:
            errors.append("Unknown dimension %r; use one of: %s." % (dim_id, ", ".join(DIMENSIONS)))
            continue
        if dim_id in dims:
            errors.append("Dimension %r appears twice." % dim_id)
            continue
        status = str(item.get("status") or ("scored" if item.get("score") is not None else "not_measured")).strip()
        if status not in STATUSES:
            errors.append("%s: status must be scored, na or not_measured, got %r." % (dim_id, status))
            continue
        value = None
        if status == "scored":
            try:
                value = cli.to_number(item.get("score"), dim_id, minimum=0, maximum=10)
            except cli.CoercionError as exc:
                errors.append(str(exc))
                continue
            if value is None:
                errors.append("%s: status is scored but score is missing." % dim_id)
                continue
        confidence = str(item.get("confidence") or "").strip().lower() or None
        if status == "scored" and confidence not in CONFIDENCES:
            errors.append("%s: confidence must be high, medium or low." % dim_id)
            continue
        evidence = item.get("evidence") or []
        if isinstance(evidence, str):
            evidence = [evidence]
        if status == "scored" and not evidence:
            errors.append("%s: every scored dimension needs at least one evidence id." % dim_id)
            continue
        dims[dim_id] = {
            "id": dim_id, "status": status, "score": value, "max": 10, "weight": DIMENSIONS[dim_id],
            "confidence": confidence if status == "scored" else None,
            "evidence": list(evidence), "justification": item.get("justification"),
        }
    if errors:
        return {}, errors, notes
    for dim_id in DIMENSIONS:
        if dim_id not in dims:
            dims[dim_id] = {"id": dim_id, "status": "not_measured", "score": None, "max": 10,
                            "weight": DIMENSIONS[dim_id], "confidence": None, "evidence": [],
                            "justification": "not provided"}
            notes.append("%s was not provided and counts as not measured." % dim_id)

    total = sum(DIMENSIONS.values())
    applicable = sum(d["weight"] for d in dims.values() if d["status"] != "na")
    scored = [d for d in dims.values() if d["status"] == "scored"]
    measured = sum(d["weight"] for d in scored)
    share = (measured / applicable) if applicable else 0.0
    composite = None
    if measured:
        composite = sum(d["score"] * d["weight"] for d in scored) / measured * 10.0
        for d in scored:
            d["normalized_weight"] = round(d["weight"] / measured, 4)
    withheld = None
    if not scored:
        withheld = "no dimension was scored"
    elif full_flow is not True:
        withheld = ("the full signup flow was not seen (full_flow_seen is not true): show the friction "
                    "ledger and per-dimension scores only")
    elif share < MIN_MEASURED_SHARE:
        withheld = "only %.0f%% of the applicable weight was measured (needs %.0f%%)" % (
            share * 100, MIN_MEASURED_SHARE * 100)
    if withheld:
        notes.append("Composite withheld: %s." % withheld)

    def weight_share(level: str) -> float:
        return sum(d["weight"] for d in scored if d["confidence"] == level) / measured if measured else 0.0

    if not measured:
        overall = None
    elif weight_share("high") >= 0.8:
        overall = "high"
    elif weight_share("low") > 0.5:
        overall = "low"
    else:
        overall = "medium"
    shown = None if withheld else int(round(composite))
    result = {
        "scoring": {
            "mode": "rubric",
            "version": str(payload.get("rubric_version") or RUBRIC_VERSION),
            "name": "signup ease score (higher means less friction)",
            "value": shown,
            "max": 100,
            "confidence": overall if shown is not None else None,
            "measured_weight": round(share, 4),
            "applicable_weight": applicable,
            "total_weight": total,
            "full_flow_seen": full_flow,
            "withheld_reason": withheld,
            "unrounded": round(composite, 2) if (composite is not None and shown is not None) else None,
            "noise_note": NOISE_NOTE,
        },
        "dimensions": [dims[d] for d in DIMENSIONS],
        "header_line": (
            "**Score:** %d/100 (rubric; confidence %s; %.0f%% of weight measured)" % (shown, overall, share * 100)
            if shown is not None else None
        ),
    }
    if str(payload.get("rubric_version") or RUBRIC_VERSION) != RUBRIC_VERSION:
        notes.append("rubric_version %r differs from this script's %s; scores are not comparable across versions."
                     % (payload.get("rubric_version"), RUBRIC_VERSION))
    return result, [], notes


# ---------------------------------------------------------------------------
# test-plan
# ---------------------------------------------------------------------------


def test_plan(baseline: float, weekly: Optional[float], mde: float, relative: bool,
              max_weeks: float) -> Dict[str, Any]:
    """Wrap stats.plan_test with the report contract's decision rules."""
    if weekly is None:
        n = stats.sample_size_per_arm(baseline, mde, relative)
        needed = n * 2 / max_weeks
        return {
            "baseline": baseline, "mde": mde, "relative": relative,
            "target_rate": stats.target_rate(baseline, mde, relative),
            "n_per_arm": n, "total_visitors": n * 2, "max_weeks": max_weeks,
            "weekly_visitors": None, "feasible": None,
            "weekly_visitors_needed": int(math.ceil(needed)),
            "test_plan": None,
            "verdict": ("traffic unknown: an A/B test needs about %d visitors per week to the tested step "
                        "to finish within %g weeks" % (int(math.ceil(needed)), max_weeks)),
        }
    plan = stats.plan_test(baseline, weekly, mde, relative=relative, max_weeks=max_weeks)
    plan["weekly_visitors_needed"] = int(math.ceil(plan["n_per_arm"] * plan["arms"] / max_weeks))
    if plan["feasible"]:
        plan["test_plan"] = "ab_test"
        plan["weeks_to_run"] = max(2, plan["weeks_rounded"])
        plan["stopping_rule"] = ("run %d full weeks, then read the result once; do not stop early on a peek"
                                 % plan["weeks_to_run"])
    else:
        plan["test_plan"] = "ship_and_measure"
        plan["weeks_to_run"] = None
        plan["stopping_rule"] = ("ship the change and compare equal windows of at least 2 full weeks before "
                                 "and after; watch launches, campaigns and seasonality")
    return plan


# ---------------------------------------------------------------------------
# benchmarks and trial-model
# ---------------------------------------------------------------------------


def load_benchmarks(path: str = BENCHMARKS_PATH) -> Dict[str, Any]:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def benchmark_rows(data: Dict[str, Any], metric: Optional[str] = None,
                   motion: Optional[str] = None) -> List[Dict[str, Any]]:
    rows = []
    for row in data.get("rows") or []:
        if row.get("metric") not in BENCHMARK_METRICS or not row.get("verified"):
            continue
        if metric and row.get("metric") != metric:
            continue
        segment = row.get("segment") or {}
        if motion and segment.get("motion") not in (motion, "all"):
            continue
        rows.append({
            "id": row.get("id"),
            "metric": row.get("metric"),
            "label": row.get("metric_label"),
            "segment": {"motion": segment.get("motion"), "extra": segment.get("extra") or {}},
            "median": row.get("median"), "mean": row.get("mean"), "value": row.get("value"),
            "thresholds": row.get("thresholds"),
            "unit": row.get("unit"), "period": row.get("period"),
            "definition": row.get("definition"),
            "source": row.get("source_name"), "year": row.get("year"), "url": row.get("source_url"),
            "confidence": row.get("confidence"), "note": row.get("value_note"),
            "verified_on": row.get("verified_on"),
        })
    return rows


def _row_rate(rows_by_id: Dict[str, Dict[str, Any]], row_id: str) -> Tuple[Optional[float], Optional[Dict[str, Any]]]:
    row = rows_by_id.get(row_id)
    if row is None:
        return None, None
    for key in ("median", "mean", "value"):
        if row.get(key) is not None:
            return float(row[key]) / 100.0, row
    return None, row


def trial_model(inputs: Dict[str, Optional[float]], traffic: str,
                data: Optional[Dict[str, Any]]) -> Tuple[Dict[str, Any], List[str]]:
    """Fill missing rates from benchmark rows (labelled) and compare the two trial models."""
    notes: List[str] = []
    sources: Dict[str, Dict[str, Any]] = {}
    rows_by_id = {r["id"]: r for r in (data or {}).get("rows") or []}
    values: Dict[str, float] = {}
    for key in ("no_card_v2t", "no_card_t2p", "card_v2t", "card_t2p"):
        if inputs.get(key) is not None:
            values[key] = inputs[key]
            sources[key] = {"source": "user"}
            continue
        row_id = TRIAL_DEFAULTS[traffic][key]
        rate, row = _row_rate(rows_by_id, row_id)
        if rate is None:
            raise cli.UsageError("Missing --%s and benchmark row %s is not available." % (key.replace("_", "-"), row_id))
        values[key] = rate
        sources[key] = {"source": "benchmark", "row_id": row_id, "source_name": row.get("source_name"),
                        "year": row.get("year"), "statistic": "mean" if row.get("mean") is not None else "value",
                        "note": row.get("value_note")}
    if any(s["source"] == "benchmark" for s in sources.values()):
        notes.append("Benchmark defaults are agency-client averages (First Page Sage 2025); the card-required "
                     "trial-to-paid counts a single paid month as a conversion. Replace them with your own rates "
                     "before deciding.")
    result = stats.compare_trial_models(values["no_card_v2t"], values["no_card_t2p"],
                                        values["card_v2t"], values["card_t2p"])
    result["inputs"] = {k: {"rate": values[k], **sources[k]} for k in values}
    result["traffic_source"] = traffic
    return result, notes


# ---------------------------------------------------------------------------
# teardown
# ---------------------------------------------------------------------------


def _site_key(envelope: Dict[str, Any]) -> str:
    source = envelope.get("source") or {}
    url = source.get("page_url") or (envelope.get("page") or {}).get("url") or source.get("input") or ""
    host = (urlparse(url).hostname or "").lower() if "://" in str(url) else str(url)
    return host[4:] if host.startswith("www.") else host


def teardown(envelopes: List[Tuple[str, Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """One row of facts per site, merging every step file of that site."""
    sites: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []
    for path, env in envelopes:
        key = _site_key(env)
        if key not in sites:
            order.append(key)
            sites[key] = {
                "site": key, "files": [], "signup_statuses": [], "steps_seen": 0, "step_labels": [],
                "sign_in_options": [], "sdk_only_options": [], "questions_seen": 0, "question_purposes": [],
                "optional_labelled": 0, "password_at_signup": False, "email_path": False,
                "card_fields_seen": None, "visible_challenge": [], "invisible_protection": [],
                "verification_hints": 0, "work_email_hint": False, "consent_boxes": 0,
                "plan_hints": [], "no_card_claims": 0,
            }
        row = sites[key]
        row["files"].append(os.path.basename(path))
        row["signup_statuses"].append(env.get("signup_status"))
        step = env.get("primary_step")
        if env.get("signup_status") == "ok" and step:
            row["steps_seen"] += 1
            label = (env.get("source") or {}).get("step_label") or (env.get("page") or {}).get("step_label")
            if label:
                row["step_labels"].append(label)
            row["questions_seen"] += sum(1 for q in step.get("questions") or [] if q.get("purpose") != "consent")
            row["optional_labelled"] += int(step.get("optional_labelled_count") or 0)
            row["consent_boxes"] += len(step.get("consent") or [])
            for q in step.get("questions") or []:
                if q.get("purpose") not in row["question_purposes"] and q.get("purpose") != "consent":
                    row["question_purposes"].append(q.get("purpose"))
            if any(q.get("purpose") == "password" for q in step.get("questions") or []):
                row["password_at_signup"] = True
            card = (env.get("payment") or {}).get("card_fields_seen")
            if card is not None:
                row["card_fields_seen"] = bool(row["card_fields_seen"]) or bool(card)
        methods = env.get("auth_methods") or {}
        if methods.get("email_question_seen") or methods.get("email_path_control"):
            row["email_path"] = True
        for option in env.get("auth_options") or []:
            name = option.get("provider")
            target = "sign_in_options" if option.get("control_seen") else "sdk_only_options"
            if name and name not in row[target]:
                row[target].append(name)
        for item in env.get("bot_protection") or []:
            label = "%s (%s)" % (item.get("vendor"), item.get("mode"))
            target = "visible_challenge" if item.get("mode") in ("visible_checkbox", "conflicting") else "invisible_protection"
            if label not in row[target]:
                row[target].append(label)
        hints = env.get("hints") or {}
        row["verification_hints"] += len(hints.get("verification") or [])
        if hints.get("work_email"):
            row["work_email_hint"] = True
        for item in (hints.get("plan_and_trial") or [])[:2]:
            text = item.get("text") if isinstance(item, dict) else str(item)
            if text and text not in row["plan_hints"] and len(row["plan_hints"]) < 3:
                row["plan_hints"].append(text[:160])
        row["no_card_claims"] += sum(1 for m in (env.get("payment") or {}).get("page_mentions") or [] if m.get("negated"))
    rows = []
    for key in order:
        row = sites[key]
        row["sdk_only_options"] = [p for p in row["sdk_only_options"] if p not in row["sign_in_options"]]
        rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------


def _rate(value: Optional[str], field: str) -> Optional[float]:
    """'31%', '31' and '0.31' all mean 31 percent; returns a fraction."""
    number = cli.to_percent(value, field, assume_fraction=True, minimum=0, maximum=100)
    return None if number is None else number / 100.0


def build_parser() -> cli.ArgumentParser:
    parser = cli.ArgumentParser(
        prog="signup_math.py",
        description="Deterministic math for signup audits: rubric score, test plans, trial models, "
                    "benchmarks and competitor teardowns.",
    )
    parser.add_argument("--version", action="version", version="%(prog)s " + cli.__version__)
    sub = parser.add_subparsers(dest="command")

    def common(p: cli.ArgumentParser) -> None:
        p.add_argument("--json", action="store_true", help="print only JSON to stdout")
        p.add_argument("--out", metavar="PATH", help="also save the JSON result to PATH")

    p_score = sub.add_parser("score", help="weighted score from rubric scores (JSON file or '-')")
    p_score.add_argument("input", nargs="?", help="scores JSON file, or '-' for stdin")
    common(p_score)

    p_test = sub.add_parser("test-plan", help="A/B sample size and duration, or ship-and-measure")
    p_test.add_argument("--baseline", required=True, help="baseline rate of the primary metric (0.31 or 31%%)")
    group = p_test.add_mutually_exclusive_group()
    group.add_argument("--weekly-visitors", help="visitors per week reaching the tested step")
    group.add_argument("--monthly-visitors", help="visitors per month reaching the tested step (divided by 4.33)")
    p_test.add_argument("--mde", default="0.2", help="minimum detectable effect (default 0.2 = 20%% relative)")
    p_test.add_argument("--absolute", action="store_true", help="treat --mde as absolute percentage points")
    p_test.add_argument("--max-weeks", default="4", help="longest acceptable test (default 4)")
    common(p_test)

    p_trial = sub.add_parser("trial-model", help="no-card vs card-required trial, paying per 1,000 visitors")
    p_trial.add_argument("--no-card-v2t", help="visitor-to-trial rate without a card")
    p_trial.add_argument("--no-card-t2p", help="trial-to-paid rate without a card")
    p_trial.add_argument("--card-v2t", help="visitor-to-trial rate with a card required")
    p_trial.add_argument("--card-t2p", help="trial-to-paid rate with a card required")
    p_trial.add_argument("--traffic", choices=("organic", "paid"), default="organic",
                         help="benchmark segment for missing rates (default organic)")
    common(p_trial)

    p_bench = sub.add_parser("benchmarks", help="sourced benchmark rows this skill may cite")
    p_bench.add_argument("--metric", choices=BENCHMARK_METRICS)
    p_bench.add_argument("--motion", help="segment motion, e.g. trial_opt_in, trial_opt_out, freemium, plg")
    common(p_bench)

    p_tear = sub.add_parser("teardown", help="side-by-side facts from signup_extractor JSON files")
    p_tear.add_argument("inputs", nargs="+", help="JSON files written by signup_extractor.py --out")
    common(p_tear)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_usage(sys.stderr)
        print("signup_math.py: error: choose a subcommand: score, test-plan, trial-model, benchmarks, teardown",
              file=sys.stderr)
        if "--json" in (argv if argv is not None else sys.argv[1:]):
            print(cli.to_json({"tool": TOOL, "status": cli.STATUS_USAGE, "errors": ["no subcommand"], "notes": []}))
        return cli.EXIT_USAGE
    run = cli.Run(TOOL, args, demo=False)
    try:
        if args.command == "score":
            payload, _ = cli.load_json_input(args.input, expect=dict)
            result, errors, notes = score(payload)
            for note in notes:
                run.note(note)
            if errors:
                return run.fail(cli.STATUS_USAGE, "; ".join(errors))
            result["command"] = "score"
            return run.emit(result)
        if args.command == "test-plan":
            baseline = _rate(args.baseline, "baseline")
            if baseline is None or not 0 < baseline < 1:
                raise cli.UsageError("--baseline must be a rate between 0 and 100%.")
            weekly = None
            if args.weekly_visitors is not None:
                weekly = cli.to_number(args.weekly_visitors, "weekly_visitors", minimum=1)
            elif args.monthly_visitors is not None:
                monthly = cli.to_number(args.monthly_visitors, "monthly_visitors", minimum=1)
                weekly = None if monthly is None else monthly / WEEKS_PER_MONTH
                run.note("weekly visitors = monthly / %.2f" % WEEKS_PER_MONTH)
            relative = not args.absolute
            mde = cli.to_number(args.mde, "mde", minimum=0)
            if mde is None or mde <= 0:
                raise cli.UsageError("--mde must be greater than 0.")
            if relative and mde >= 1:
                mde = mde / 100.0  # "20" means 20% relative
            if not relative:
                mde = mde / 100.0 if mde >= 1 else mde
            max_weeks = cli.to_number(args.max_weeks, "max_weeks", minimum=1)
            try:
                plan = test_plan(baseline, weekly, mde, relative, max_weeks)
            except ValueError as exc:
                raise cli.UsageError(str(exc))
            if weekly is None:
                run.note("Traffic unknown: say so in the report and state the weekly traffic the test would need.")
            plan["command"] = "test-plan"
            return run.emit(plan)
        if args.command == "trial-model":
            inputs = {
                "no_card_v2t": _rate(args.no_card_v2t, "no_card_v2t"),
                "no_card_t2p": _rate(args.no_card_t2p, "no_card_t2p"),
                "card_v2t": _rate(args.card_v2t, "card_v2t"),
                "card_t2p": _rate(args.card_t2p, "card_t2p"),
            }
            data = None
            if any(v is None for v in inputs.values()):
                data = load_benchmarks()
            try:
                result, notes = trial_model(inputs, args.traffic, data)
            except ValueError as exc:
                raise cli.UsageError(str(exc))
            for note in notes:
                run.note(note)
            result["command"] = "trial-model"
            return run.emit(result)
        if args.command == "benchmarks":
            data = load_benchmarks()
            rows = benchmark_rows(data, args.metric, args.motion)
            run.note("Cite value, source, year and segment for every number; mean values are averages, not medians.")
            if not rows:
                return run.emit({"command": "benchmarks", "rows": []}, status=cli.STATUS_NOTHING)
            return run.emit({"command": "benchmarks", "last_verified": data.get("last_verified"), "rows": rows})
        if args.command == "teardown":
            envelopes: List[Tuple[str, Dict[str, Any]]] = []
            for path in args.inputs:
                try:
                    payload, _ = cli.load_json_input(path, expect=dict)
                except cli.UsageError as exc:
                    run.error(str(exc))
                    continue
                if payload.get("tool") != "signup_extractor":
                    run.error("%s is not a signup_extractor result." % path)
                    continue
                envelopes.append((path, payload))
            if not envelopes:
                return run.fail(cli.STATUS_NOTHING, "No readable signup_extractor files.")
            rows = teardown(envelopes)
            run.note("Facts only: judge each site with the rubric, and mark steps you did not see as not measured.")
            return run.emit({"command": "teardown", "sites": rows})
    except cli.UsageError as exc:
        return run.fail(cli.STATUS_USAGE, str(exc))
    except cli.CoercionError as exc:
        return run.fail(cli.STATUS_USAGE, str(exc))
    except OSError as exc:
        return run.fail(cli.STATUS_USAGE, "Cannot read the benchmark file: %s" % exc)
    return cli.EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
