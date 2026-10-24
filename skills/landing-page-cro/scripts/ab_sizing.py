#!/usr/bin/env python3
"""Traffic-aware test plans for landing-page-cro bets.

Wraps the shared stats helper (_growthkit/stats.py: two-proportion z-test,
alpha 0.05 two-sided, power 0.8) so the model never estimates sample sizes
or lift itself. For each minimum detectable effect it says whether an A/B
test fits in the time limit (default 4 weeks, report-contract.md section 6)
or whether the bet should ship and be measured before and after.

    python3 ab_sizing.py --baseline 3.8% --monthly-visitors 18000 --json
    python3 ab_sizing.py --baseline 2.1 --weekly-visitors 900 --mde 10 20 30 --json
    python3 ab_sizing.py --mde 20 --json

--baseline is the page's own conversion rate in percent ("3.8%" or "3.8").
Without it the SaaS landing-page median from the shared benchmark file is
used and marked as an assumption. Without traffic the output gives the
weekly visitors a test would need.

Exit codes: 0 ok, 2 usage error (bad or impossible inputs).
"""

from __future__ import annotations

import json
import math
import os
import sys
from typing import Any, Dict, List, Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from _growthkit import __version__, cli, stats  # noqa: E402

TOOL = "ab_sizing"
WEEKS_PER_MONTH = 4.33  # report-contract.md section 6
DEFAULT_MDE = 20.0      # percent relative; stated as an assumption when used
MIN_TEST_WEEKS = 2      # cover two full weekly cycles
DEFAULT_BENCHMARK = "landing_page_conversion.unbounce2024.saas"
BENCHMARK_FILE = os.path.join(os.path.dirname(_HERE), "references", "_shared", "saas-benchmarks.json")


def load_benchmark(row_id: str, path: str = BENCHMARK_FILE) -> Dict[str, Any]:
    """A verified row from the shared benchmark file, or UsageError."""
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError) as exc:
        raise cli.UsageError("Cannot read the benchmark file (%s): %s. Pass --baseline instead." % (path, exc))
    for row in data.get("rows") or []:
        if row.get("id") == row_id:
            if not row.get("verified"):
                raise cli.UsageError("Benchmark row %s is not verified; pass --baseline instead." % row_id)
            value = row.get("median")
            if value is None:
                value = row.get("mean") if row.get("mean") is not None else row.get("value")
            if value is None or row.get("unit") != "percent":
                raise cli.UsageError("Benchmark row %s has no percent value to use as a baseline." % row_id)
            statistic = "median" if row.get("median") is not None else ("mean" if row.get("mean") is not None else "value")
            return {
                "kind": "benchmark",
                "row_id": row_id,
                "value_percent": value,
                "statistic": statistic,
                "source_name": row.get("source_name"),
                "source_url": row.get("source_url"),
                "year": row.get("year"),
                "segment": row.get("segment"),
                "definition": row.get("definition"),
                "verified_on": row.get("verified_on"),
            }
    raise cli.UsageError("Benchmark row %s not found in %s." % (row_id, path))


def build_plans(baseline: float, weekly: Optional[float], mdes: List[float], arms: int = 2,
                max_weeks: float = stats.DEFAULT_MAX_WEEKS, alpha: float = stats.DEFAULT_ALPHA,
                power: float = stats.DEFAULT_POWER) -> List[Dict[str, Any]]:
    """One plan per relative MDE (fractions in, fractions out)."""
    plans = []
    for mde in mdes:
        if weekly:
            plan = stats.plan_test(baseline, weekly, mde, relative=True, arms=arms, alpha=alpha,
                                   power=power, max_weeks=max_weeks)
            at_max = plan.get("mde_at_max_weeks") or {}
            feasible = bool(plan["feasible"])
            plans.append({
                "mde_relative": mde,
                "target_rate": round(plan["target_rate"], 6),
                "n_per_arm": plan["n_per_arm"],
                "total_visitors": plan["total_visitors"],
                "weeks": round(plan["weeks"], 2),
                "recommended_weeks": max(MIN_TEST_WEEKS, plan["weeks_rounded"]) if feasible else None,
                "feasible": feasible,
                "test_plan": "ab_test" if feasible else "ship_and_measure",
                "weekly_visitors_needed": int(math.ceil(plan["total_visitors"] / max_weeks)),
                "smallest_detectable_relative_lift_in_max_weeks": round(at_max["relative"], 4) if at_max else None,
                "verdict": ("testable: run %d full weeks (the sample needs %.1f weeks of traffic)"
                            % (max(MIN_TEST_WEEKS, plan["weeks_rounded"]), plan["weeks"])) if feasible else plan["verdict"],
            })
        else:
            alpha_used = alpha / (arms - 1) if arms > 2 else alpha
            n = stats.sample_size_per_arm(baseline, mde, relative=True, alpha=alpha_used, power=power)
            plans.append({
                "mde_relative": mde,
                "target_rate": round(stats.target_rate(baseline, mde), 6),
                "n_per_arm": n,
                "total_visitors": n * arms,
                "weeks": None,
                "recommended_weeks": None,
                "feasible": None,
                "test_plan": "unknown_traffic",
                "weekly_visitors_needed": int(math.ceil(n * arms / max_weeks)),
                "smallest_detectable_relative_lift_in_max_weeks": None,
                "verdict": "traffic unknown: an A/B test needs about %d visitors a week to finish in %g weeks"
                           % (int(math.ceil(n * arms / max_weeks)), max_weeks),
            })
    return plans


def _human(envelope: Dict[str, Any]) -> str:
    inputs = envelope.get("inputs") or {}
    lines = ["Test sizing (two-sided alpha %s, power %s, %d arms, limit %g weeks)" % (
        inputs.get("alpha"), inputs.get("power"), inputs.get("arms") or 2, inputs.get("max_weeks") or 4)]
    lines.append("Baseline %.2f%% (%s), weekly visitors %s" % (
        (inputs.get("baseline") or 0) * 100, (inputs.get("baseline_source") or {}).get("kind"),
        inputs.get("weekly_visitors") if inputs.get("weekly_visitors") else "unknown"))
    for plan in envelope.get("plans") or []:
        lines.append("  MDE %+.0f%%: %s per arm -> %s" % (plan["mde_relative"] * 100, plan["n_per_arm"], plan["verdict"]))
    return "\n".join(lines)


def build_parser() -> cli.ArgumentParser:
    parser = cli.ArgumentParser(
        prog="ab_sizing.py",
        description="Sample size, duration and A/B feasibility for landing page bets.",
        epilog="Exit codes: 0 ok, 2 usage error.",
    )
    parser.add_argument("--baseline", metavar="PERCENT",
                        help="current conversion rate of the page in percent, e.g. 3.8%% (default: benchmark row)")
    parser.add_argument("--benchmark", metavar="ROW_ID", default=DEFAULT_BENCHMARK,
                        help="benchmark row used when --baseline is missing (default: %(default)s)")
    traffic = parser.add_mutually_exclusive_group()
    traffic.add_argument("--monthly-visitors", metavar="N", help="visitors per month that reach the page")
    traffic.add_argument("--weekly-visitors", metavar="N", help="visitors per week that reach the page")
    parser.add_argument("--mde", nargs="+", metavar="PERCENT",
                        help="relative minimum detectable effects in percent (default: 20)")
    parser.add_argument("--arms", type=int, default=2, help="control plus variants (default: 2)")
    parser.add_argument("--max-weeks", type=float, default=stats.DEFAULT_MAX_WEEKS,
                        help="longest acceptable test in weeks (default: %(default)s)")
    parser.add_argument("--alpha", type=float, default=stats.DEFAULT_ALPHA, help="two-sided alpha (default: 0.05)")
    parser.add_argument("--power", type=float, default=stats.DEFAULT_POWER, help="power (default: 0.8)")
    parser.add_argument("--json", action="store_true", help="print only JSON to stdout")
    parser.add_argument("--out", metavar="PATH", help="also save the JSON result to PATH")
    parser.add_argument("--version", action="version", version="%(prog)s " + __version__)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    run = cli.Run(TOOL, args, demo=False)
    try:
        if not 2 <= args.arms <= 6:
            raise cli.UsageError("--arms must be between 2 and 6.")
        if not 0 < args.max_weeks <= 26:
            raise cli.UsageError("--max-weeks must be above 0 and at most 26.")
        if args.baseline is not None:
            percent = cli.to_percent(args.baseline, field="--baseline")
            if percent is None:
                raise cli.UsageError("--baseline is empty; pass a percent such as 3.8% or leave it out.")
            source: Dict[str, Any] = {"kind": "user", "value_percent": percent}
        else:
            source = load_benchmark(args.benchmark)
            percent = float(source["value_percent"])
            run.note("No --baseline: using %s %s %.1f%% (%s %s) as an ASSUMED baseline; replace it with the "
                     "page's own conversion rate when known." % (
                         source["row_id"], source["statistic"], percent, source["source_name"], source["year"]))
        if not 0 < percent < 100:
            raise cli.UsageError("--baseline must be between 0%% and 100%%, got %s." % args.baseline)
        weekly = None
        weekly_source = None
        if args.monthly_visitors is not None:
            monthly = cli.to_number(args.monthly_visitors, field="--monthly-visitors", minimum=0)
            if monthly:
                weekly = monthly / WEEKS_PER_MONTH
                weekly_source = "monthly_visitors / %s" % WEEKS_PER_MONTH
        elif args.weekly_visitors is not None:
            weekly = cli.to_number(args.weekly_visitors, field="--weekly-visitors", minimum=0) or None
            weekly_source = "weekly_visitors" if weekly else None
        mde_values = args.mde or [str(DEFAULT_MDE)]
        mdes = []
        for raw in mde_values:
            value = cli.to_percent(raw, field="--mde")
            if value is None or value <= 0:
                raise cli.UsageError("--mde values must be positive percents such as 20 for +20% relative.")
            mdes.append(value / 100.0)
        if not args.mde:
            run.note("No --mde: a 20% relative effect is the ASSUMED minimum detectable effect.")
        if weekly is None:
            run.note("Traffic unknown: no feasibility verdict; each plan gives the weekly visitors a test would need.")
        plans = build_plans(percent / 100.0, weekly, mdes, args.arms, args.max_weeks, args.alpha, args.power)
    except cli.CoercionError as exc:
        return run.fail(cli.STATUS_USAGE, str(exc))
    except cli.UsageError as exc:
        return run.fail(cli.STATUS_USAGE, str(exc))
    except ValueError as exc:  # stats.py explains impossible inputs in plain words
        return run.fail(cli.STATUS_USAGE, str(exc))
    data = {
        "inputs": {
            "baseline": percent / 100.0,
            "baseline_source": source,
            "weekly_visitors": round(weekly, 1) if weekly else None,
            "weekly_source": weekly_source,
            "arms": args.arms,
            "alpha": args.alpha,
            "power": args.power,
            "two_sided": True,
            "max_weeks": args.max_weeks,
            "method": "two-proportion z-test, pooled variance, no continuity correction (stats.py)",
        },
        "plans": plans,
        "low_traffic_alternatives": [
            "ship the change and compare equal windows of at least 2 full weeks before and after",
            "5 target-user sessions or a 5-second test on the first screen",
            "session recordings and heatmaps on the changed section",
            "objections from sales calls, support tickets and chat logs",
        ] if any(p["test_plan"] != "ab_test" for p in plans) else [],
    }
    return run.emit(data, human=_human)


if __name__ == "__main__":
    sys.exit(main())
