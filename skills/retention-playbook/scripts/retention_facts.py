#!/usr/bin/env python3
"""Deterministic retention facts for the retention-playbook skill.

Scripts collect and count; the model judges. Each subcommand prints one JSON
envelope with the shared CLI contract (status, errors, notes, exit codes):

  billing   <export>        Billing export (Stripe, Paddle, Chargebee, ChartMogul,
                            Baremetrics MRR per customer, generic) through the
                            shared importer: MRR bridge, logo and MRR churn,
                            trailing-12-month cohort GRR and NRR, voluntary vs
                            involuntary churn, plus retention facts: time to
                            churn, the size-weighted cohort curve and how fast
                            it flattens, and cancel-reason counts. An invoices
                            export gives payment failure and recovery rates.
  segments  <file>          A customer table with a churn flag (CRM or billing
                            snapshot): churn share by segment value with Wilson
                            intervals, churned MRR share, churn by tenure.
  reasons   <file>          Exit-survey or cancel-reason text (CSV column, .txt
                            or JSON): de-duplicated reasons with ids, counts and
                            MRR, emails and phone numbers removed, ready for the
                            model to code with references/rubric.md.
  tally     --reasons R --coding C
                            Counts and shares per churn bucket and theme from
                            the model's coding of the reasons output.
  check                     Sanity check of typed metrics (monthly logo and
                            revenue churn, GRR, NRR): period conversions and
                            combinations that cannot all be true.
  benchmarks                Matching rows from references/_shared/saas-benchmarks.json
                            (GRR, NRR, monthly logo churn) for the user's segment.
  test-plan                 A/B test sizing for a retention bet (shared stats
                            helper, 4-week limit).
  score     <dimensions.json>
                            Composite of the model's rubric scores (program or
                            cancel_flow rubric), dropping na and not_measured
                            dimensions and renormalizing.

Customer data stays local: ids are hashed by the importer, personal-data
columns are never read, and outputs hold aggregates and de-identified text.

Exit codes: 0 ok, 2 usage or input error, 4 partial, 5 nothing to analyze.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from collections import Counter, OrderedDict, defaultdict
from datetime import date
from typing import Any, Dict, List, Optional, Sequence, Tuple

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from _growthkit import cli, importers, stats  # noqa: E402

TOOL = "retention_facts"
BENCHMARK_FILE = os.path.join(os.path.dirname(_HERE), "references", "_shared", "saas-benchmarks.json")
RUBRIC_VERSION = "retention-rubric-v1"
STALE_DAYS = 183
PARTIAL_SHARE = 0.05

STOPPED = frozenset({"canceled", "cancelled", "ended", "churned", "expired", "transferred"})
CHURN_TRUE = frozenset({"churned", "canceled", "cancelled", "ended", "expired", "inactive", "lapsed", "lost",
                        "terminated", "closed"})
CHURN_FALSE = frozenset({"active", "stayed", "retained", "joined", "trialing", "trial", "past_due", "live",
                         "current", "paying", "renewed", "new"})

# ---------------------------------------------------------------------------
# Rubric weights (must match references/rubric.md)
# ---------------------------------------------------------------------------

RUBRICS: Dict[str, "OrderedDict[str, int]"] = {
    "program": OrderedDict([
        ("measurement", 15), ("involuntary_defense", 15), ("early_life", 15), ("risk_detection", 15),
        ("save_flow", 15), ("winback", 10), ("commitment_expansion", 15),
    ]),
    "cancel_flow": OrderedDict([
        ("exit_ease_compliance", 25), ("reason_capture", 15), ("offer_targeting", 20), ("alternatives", 15),
        ("confirmation_followup", 10), ("measurement", 15),
    ]),
}
DIMENSION_STATUSES = ("scored", "na", "not_measured")
CONFIDENCES = ("high", "medium", "low")
CHURN_BUCKETS = ("preventable", "structural", "competitive", "natural", "involuntary", "unclear")

DEMO_CHECK = {"logo_churn": 3.5, "revenue_churn": 1.8, "grr": 80.0, "nrr": 97.0}


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _r(value: Optional[float], digits: int = 4) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return round(value, digits)


def _quantile(values: Sequence[float], q: float) -> Optional[float]:
    """Linear-interpolation quantile (the same as numpy's default)."""
    if not values:
        return None
    data = sorted(values)
    position = (len(data) - 1) * q
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return data[lower]
    return data[lower] + (data[upper] - data[lower]) * (position - lower)


def _rate(successes: int, n: int) -> Dict[str, Any]:
    if not n:
        return {"n": 0, "count": 0, "rate": None, "ci95": None}
    low, high = stats.wilson_interval(successes, n)
    return {"n": n, "count": successes, "rate": _r(successes / float(n)), "ci95": [_r(low), _r(high)]}


_PHONE_RE = re.compile(r"\+?\d[\d ()./-]{7,}\d")
_URL_RE = re.compile(r"https?://\S+|www\.\S+", re.I)


# Only these count as "no answer" in a reason column. "Don't know", "not sure"
# and "none" are answers (the unclear bucket), unlike cli.is_missing().
EMPTY_ANSWERS = frozenset({"", "-", "--", "n/a", "na", "n.a.", "null", "nil", "nan", "(blank)"})


def clean_text(value: Any, limit: int = 280) -> Optional[str]:
    """De-identify and normalize a free-text answer."""
    if value is None:
        return None
    text = " ".join(str(value).split())
    if text.lower() in EMPTY_ANSWERS:
        return None
    text = importers.scrub(text)
    text = _URL_RE.sub("[link]", text)
    text = _PHONE_RE.sub("[phone]", text)
    if len(text) > limit:
        text = text[:limit - 3].rstrip() + "..."
    return text


def _group_key(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _read_table(path: str) -> importers.Table:
    """First CSV table in a file (csv, tsv, txt with a header, or zip)."""
    try:
        tables = importers.read_tables(path)
    except importers.ImportFormatError as exc:
        raise cli.UsageError(str(exc))
    return tables[0]


def _resolve_column(table: importers.Table, requested: Optional[str], aliases: Sequence[str],
                    label: str) -> Optional[int]:
    if requested:
        key = importers.normalize_header(requested)
        if key in table.keys:
            return table.keys.index(key)
        if requested in table.headers:
            return table.headers.index(requested)
        raise cli.UsageError("Column %r (%s) is not in the file. Columns: %s"
                             % (requested, label, ", ".join(table.headers[:60])))
    return table.col(*aliases)


def _churn_value(value: Optional[str]) -> Optional[bool]:
    if value is None:
        return None
    token = " ".join(str(value).strip().lower().replace("-", "_").split())
    if token in CHURN_TRUE:
        return True
    if token in CHURN_FALSE:
        return False
    try:
        return cli.to_bool(value)
    except cli.CoercionError:
        return None


def _load_records(path: str) -> Tuple[List[str], List[Dict[str, Any]], List[str]]:
    """(headers, rows as {header: value}, pii headers) from CSV or a JSON list of objects."""
    if path.lower().endswith(".json"):
        try:
            with open(path, encoding="utf-8-sig") as handle:
                data = json.load(handle)
        except (OSError, ValueError) as exc:
            raise cli.UsageError("Cannot read %s: %s" % (path, exc))
        if isinstance(data, dict):
            for key in ("customers", "accounts", "rows", "data", "records"):
                if isinstance(data.get(key), list):
                    data = data[key]
                    break
        if not isinstance(data, list) or not all(isinstance(row, dict) for row in data):
            raise cli.UsageError("Expected a JSON list of objects in %s." % path)
        headers: List[str] = []
        for row in data:
            for key in row:
                if key not in headers:
                    headers.append(str(key))
        rows = [{h: (None if row.get(h) is None else str(row.get(h))) for h in headers} for row in data]
        pii = [h for h in headers if importers.is_pii_header(importers.normalize_header(h))]
        return headers, rows, pii
    table = _read_table(path)
    rows = []
    for raw in table.rows:
        rows.append({table.headers[i]: table.value(raw, i) for i in range(len(table.headers))})
    return list(table.headers), rows, table.pii_headers()


def _find_header(headers: Sequence[str], requested: Optional[str], aliases: Sequence[str],
                 label: str) -> Optional[str]:
    keys = {importers.normalize_header(h): h for h in headers}
    if requested:
        if requested in headers:
            return requested
        key = importers.normalize_header(requested)
        if key in keys:
            return keys[key]
        raise cli.UsageError("Column %r (%s) is not in the file. Columns: %s"
                             % (requested, label, ", ".join(list(headers)[:60])))
    for alias in aliases:
        if alias in keys:
            return keys[alias]
    return None


def _number(value: Any) -> Optional[float]:
    try:
        return importers.parse_number(value)
    except Exception:  # noqa: BLE001 - any unreadable cell counts as missing
        return None


# ---------------------------------------------------------------------------
# billing
# ---------------------------------------------------------------------------

TENURE_BUCKETS_DAYS = ((0, 30, "0-30 days"), (31, 90, "31-90 days"), (91, 180, "91-180 days"),
                       (181, 365, "181-365 days"), (366, 730, "1-2 years"), (731, None, "2+ years"))


def _time_to_churn(subs: List[Dict[str, Any]], currency: str, as_of: str, months: int) -> Dict[str, Any]:
    window_start = importers.month_from_key(importers.add_months(as_of, -(months - 1)))
    window_end = importers.month_end(as_of)
    churned = [s for s in subs if s["currency"] == currency and s["end"] is not None
               and window_start <= s["end"] <= window_end and s["status"] not in importers.EXCLUDED_STATUSES
               and s["mrr"] > 0 and s["end"] > s["start"]]
    if not churned:
        return {"status": "no_churn_in_window", "window_months": months}
    days = [(s["end"] - s["start"]).days for s in churned]
    total_mrr = sum(s["mrr"] for s in churned)
    buckets = []
    for low, high, label in TENURE_BUCKETS_DAYS:
        members = [s for s, d in zip(churned, days) if d >= low and (high is None or d <= high)]
        mrr = sum(s["mrr"] for s in members)
        buckets.append({"tenure": label, "subscriptions": len(members),
                        "share": _r(len(members) / float(len(churned))), "mrr": round(mrr, 2),
                        "mrr_share": _r(mrr / total_mrr) if total_mrr else None})
    early = [s for s, d in zip(churned, days) if d <= 90]
    by_type = OrderedDict()
    for kind in ("voluntary", "involuntary", "other", "unknown"):
        typed = [d for s, d in zip(churned, days) if (s["churn_type"] or "unknown") == kind]
        if typed:
            by_type[kind] = {"subscriptions": len(typed), "median_days": _quantile(typed, 0.5)}
    return {
        "status": "ok",
        "window_months": months,
        "churned_subscriptions": len(churned),
        "median_days": _quantile(days, 0.5),
        "p25_days": _quantile(days, 0.25),
        "p75_days": _quantile(days, 0.75),
        "buckets": buckets,
        "churned_within_90_days": {"subscriptions": len(early), "share": _r(len(early) / float(len(churned))),
                                   "mrr_share": _r(sum(s["mrr"] for s in early) / total_mrr) if total_mrr else None},
        "by_churn_type": by_type,
        "basis": "days from paid start (after any trial) to the end of each subscription that ended in the window; "
                 "per subscription, not per customer",
    }


def _average_curve(cohorts: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Size-weighted average logo and revenue retention by months since the cohort started."""
    if not cohorts:
        return {"status": "no_cohorts"}
    longest = max(len(c["logo_retention"]) for c in cohorts)
    curve = []
    for offset in range(longest):
        members = [c for c in cohorts if len(c["logo_retention"]) > offset
                   and c["logo_retention"][offset] is not None]
        if not members:
            continue
        customers = sum(c["customers"] for c in members)
        logo = sum(c["customers"] * c["logo_retention"][offset] for c in members) / float(customers)
        revenue_members = [c for c in members if c.get("starting_mrr") and len(c["revenue_retention"]) > offset
                           and c["revenue_retention"][offset] is not None]
        start_mrr = sum(c["starting_mrr"] for c in revenue_members)
        revenue = (sum(c["starting_mrr"] * c["revenue_retention"][offset] for c in revenue_members) / start_mrr
                   if start_mrr else None)
        curve.append({"month": offset, "cohorts": len(members), "customers": customers,
                      "logo_retention": _r(logo), "revenue_retention": _r(revenue)})
    usable = [point for point in curve if point["cohorts"] >= 2] or curve
    drops = []
    for previous, current in zip(usable, usable[1:]):
        drops.append({"from_month": previous["month"], "to_month": current["month"],
                      "logo_drop": _r(previous["logo_retention"] - current["logo_retention"])})
    flattening = None
    if len(drops) >= 6:
        early = sum(d["logo_drop"] for d in drops[:3]) / 3.0
        late = sum(d["logo_drop"] for d in drops[-3:]) / 3.0
        flattening = {
            "early_avg_monthly_drop": _r(early), "late_avg_monthly_drop": _r(late),
            "late_to_early_ratio": _r(late / early) if early > 0 else None,
            "basis": "average logo-retention drop in the first 3 vs the last 3 month steps that have 2+ cohorts; "
                     "a ratio near 0 means the curve has flattened",
        }
    last = usable[-1]
    early_share = None
    third = next((p for p in usable if p["month"] == 3), None)
    if third and last["logo_retention"] is not None and last["logo_retention"] < 1:
        early_share = _r((1 - third["logo_retention"]) / (1 - last["logo_retention"]))
    return {"status": "ok", "curve": curve, "drops": drops, "flattening": flattening,
            "share_of_loss_by_month_3": early_share,
            "share_of_loss_basis": "logo loss by month 3 / logo loss by month %d (cohorts with 2+ data points)"
                                   % last["month"],
            "note": "The latest month in the data may be incomplete; month 0 is the cohort's first paid month."}


def _cancel_reason_counts(path: str, source: Optional[str]) -> Optional[Dict[str, Any]]:
    """Counts of the cancel reason and feedback columns among ended subscriptions."""
    try:
        tables = importers.read_tables(path)
    except importers.ImportFormatError:
        return None
    for table in tables:
        try:
            _fmt, match = importers.detect(table, "billing", source)
        except importers.ImportFormatError:
            continue
        columns = match.columns
        status_index = columns.get("status")
        end_indexes = [columns.get(k) for k in ("canceled_at", "ended_at") if columns.get(k) is not None]
        reason_indexes = []
        if columns.get("cancel_reason") is not None:
            reason_indexes.append(columns["cancel_reason"])
        for index, key in enumerate(table.keys):
            if index in reason_indexes:
                continue
            if re.search(r"(cancel|churn).*(feedback|comment|reason)|(feedback|comment)$", key):
                reason_indexes.append(index)
        if not reason_indexes:
            return {"status": "no_reason_column"}
        out = []
        for index in reason_indexes:
            counter: Counter = Counter()
            ended_rows = 0
            for row in table.rows:
                status = (table.value(row, status_index) or "").lower().replace(" ", "_")
                ended = status in STOPPED or (not status and any(table.value(row, i) for i in end_indexes))
                if not ended:
                    continue
                ended_rows += 1
                text = clean_text(table.value(row, index), 120)
                if text:
                    counter[text] += 1
            answered = sum(counter.values())
            out.append({"column": table.headers[index], "ended_subscriptions": ended_rows, "answered": answered,
                        "answer_rate": _r(answered / float(ended_rows)) if ended_rows else None,
                        "distinct": len(counter),
                        "top": [{"reason": text, "count": count} for text, count in counter.most_common(25)]})
        return {"status": "ok", "columns": out,
                "note": "Raw codes and text from the export. Code them into churn buckets with the reasons and "
                        "tally commands; free-text comments need the reasons command."}
    return None


def cmd_billing(args: Any, run: cli.Run) -> int:
    path = args.input
    if not path or not os.path.isfile(path):
        return run.fail(cli.STATUS_USAGE, "File not found: %s" % path)
    loaded = None
    errors = []
    kinds = ("billing", "invoices") if not args.source else (None,)
    for kind in kinds:
        try:
            loaded = importers.load(path, kind=kind, source=args.source, amount_unit=args.amount_unit,
                                    currency=args.currency)
            break
        except importers.NothingToImport as exc:
            return run.fail(cli.STATUS_NOTHING, importers.scrub(str(exc)), importers.scrub(exc.details))
        except importers.ImportFormatError as exc:
            errors.append(exc)
    if loaded is None:
        details = dict(getattr(errors[-1], "details", {}) or {}) if errors else {}
        run.note("Use a subscriptions export with every status (active and canceled), an MRR movements export, "
                 "an MRR-per-customer export or an invoices export; or the generic_subscriptions schema "
                 "(customer_id, start_date, end_date, mrr, status, cancel_reason).")
        return run.fail(cli.STATUS_USAGE, importers.scrub(str(errors[0] if errors else "Unknown format")),
                        importers.scrub(details))
    kind = loaded["format"]["kind"]
    if kind not in ("billing", "invoices"):
        return run.fail(cli.STATUS_USAGE, "%s is a %s export, not a billing export." % (path, kind))
    subs = loaded["normalized"].get("subscriptions")
    try:
        summary = importers.summarize(loaded, as_of=args.as_of, months=args.months)
    except importers.NothingToImport as exc:
        return run.fail(cli.STATUS_NOTHING, importers.scrub(str(exc)), importers.scrub(exc.details))
    except importers.ImportFormatError as exc:
        return run.fail(cli.STATUS_USAGE, importers.scrub(str(exc)))
    result: Dict[str, Any] = OrderedDict()
    result["file"] = loaded["file"]
    result["format"] = loaded["format"]
    result["rows"] = loaded["rows"]
    for block in summary.values():
        for note in block.pop("notes", []) or []:
            run.note(importers.scrub(note))
    result.update(importers.scrub(summary))
    status = cli.STATUS_OK
    rows = loaded["rows"]
    if rows["data_rows"] and rows["unreadable"] / float(rows["data_rows"]) > PARTIAL_SHARE:
        run.error("%d of %d rows could not be read (%s)." % (
            rows["unreadable"], rows["data_rows"],
            ", ".join("%s: %d" % item for item in rows["skipped"]["unreadable"].items())))
        status = cli.STATUS_PARTIAL
    elif rows["unreadable"]:
        run.note("%d row(s) could not be read and were skipped." % rows["unreadable"])
    if kind == "billing":
        billing = result["billing"]
        if not billing.get("churn_observable", True):
            run.error("The export has no canceled or ended subscriptions, so churn, GRR, NRR, cohort retention "
                      "and time to churn cannot be measured. Export subscriptions with every status.")
            status = cli.STATUS_PARTIAL
        retention: Dict[str, Any] = OrderedDict()
        for currency, block in billing["by_currency"].items():
            entry: Dict[str, Any] = OrderedDict()
            entry["cohort_curve"] = _average_curve(block.get("cohorts") or [])
            if subs is not None:
                entry["time_to_churn"] = _time_to_churn(subs, currency, billing["as_of"], args.months)
            else:
                entry["time_to_churn"] = {"status": "not_measured",
                                          "reason": "needs a subscriptions export with start and end dates"}
            retention[currency] = entry
        result["retention"] = retention
        reasons = _cancel_reason_counts(path, args.source)
        result["cancel_reasons"] = reasons or {"status": "not_measured", "reason": "no subscriptions table"}
    else:
        run.note("Invoices export: use payment failure and recovery rates as the dunning baseline. Invoices are "
                 "billings, not MRR; use a subscriptions export for churn and cohort retention.")
    return run.emit(result, status=status, human=_human_billing)


def _human_billing(envelope: Dict[str, Any]) -> str:
    lines = []
    fmt = envelope.get("format") or {}
    if fmt:
        lines.append("Format: %s (%s confidence)" % (fmt.get("label"), fmt.get("confidence")))
    billing = envelope.get("billing")
    if billing:
        for currency, block in billing["by_currency"].items():
            current = block["current"]
            lines.append("%s: MRR %.2f, %d paying customers at end of %s" % (
                currency, current["mrr"], current["paying_customers"], current["month"]))
            ttm = block["ttm_retention"]
            if ttm.get("grr") is not None:
                lines.append("  TTM GRR %.1f%%, NRR %.1f%%" % (ttm["grr"] * 100, ttm["nrr"] * 100))
            ttc = (envelope.get("retention") or {}).get(currency, {}).get("time_to_churn") or {}
            if ttc.get("status") == "ok":
                lines.append("  Median days to churn %s; within 90 days: %s" % (
                    ttc["median_days"], ttc["churned_within_90_days"]["share"]))
    for note in envelope.get("notes", []):
        lines.append("Note: " + note)
    lines.append("Use --json for the full result.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# segments
# ---------------------------------------------------------------------------

CHURN_COLUMNS = ("churned", "churn", "is_churned", "churn_label", "churn_value", "churn_flag", "has_churned",
                 "customer_status", "status", "subscription_status", "account_status")
MRR_COLUMNS = ("mrr", "monthly_recurring_revenue", "mrr_usd", "monthly_revenue", "monthly_charge", "monthlycharges",
               "monthly_charges")
ARR_COLUMNS = ("arr", "annual_recurring_revenue")
TENURE_MONTH_COLUMNS = ("tenure_in_months", "tenure_months", "tenure", "months_active", "customer_tenure_months",
                        "lifetime_months")
TENURE_DAY_COLUMNS = ("tenure_days", "account_age_days", "days_since_signup", "customer_age_days")
TENURE_MONTH_BUCKETS = ((0, 1, "0-1 months"), (2, 3, "2-3 months"), (4, 6, "4-6 months"), (7, 12, "7-12 months"),
                        (13, 24, "13-24 months"), (25, None, "25+ months"))
LEAK_RE = re.compile(r"(^|_)(churn|cancel|cancellation|reason|status)(_|$)")
ID_RE = re.compile(r"(^|_)(id|uuid|key)$|^id_|(^|_)(zip|zip_code|postal|lat|latitude|longitude|lat_long)(_|$)")


def _detect_churn_column(headers: Sequence[str], rows: List[Dict[str, Any]],
                         requested: Optional[str]) -> Tuple[Optional[str], Dict[str, Optional[bool]]]:
    candidates = [requested] if requested else []
    keys = {importers.normalize_header(h): h for h in headers}
    if not requested:
        candidates = [keys[alias] for alias in CHURN_COLUMNS if alias in keys]
    for header in candidates:
        if header not in headers:
            header = _find_header(headers, header, (), "churn flag")
        values = [row.get(header) for row in rows if row.get(header) not in (None, "")]
        if not values:
            continue
        mapping = {}
        for value in set(values):
            mapping[value] = _churn_value(value)
        readable = sum(1 for value in values if mapping[value] is not None)
        if readable / float(len(values)) >= 0.95:
            return header, mapping
        if requested:
            unread = sorted(v for v in mapping if mapping[v] is None)[:10]
            raise cli.UsageError("Column %r is not a churn flag: values %s are not churned/active or yes/no."
                                 % (header, ", ".join(repr(v) for v in unread)))
    return None, {}


def _tenure_bucket(months: float) -> str:
    for low, high, label in TENURE_MONTH_BUCKETS:
        if months >= low and (high is None or months <= high):
            return label
    return TENURE_MONTH_BUCKETS[-1][2]


def cmd_segments(args: Any, run: cli.Run) -> int:
    if not args.input or not os.path.isfile(args.input):
        return run.fail(cli.STATUS_USAGE, "File not found: %s" % args.input)
    try:
        headers, rows, pii = _load_records(args.input)
        churn_col, mapping = _detect_churn_column(headers, rows, args.churn_col)
        if churn_col is None:
            raise cli.UsageError("No churn flag column found. Pass --churn-col COLUMN (values like yes/no, "
                                 "true/false, 1/0, churned/active). Columns: %s" % ", ".join(headers[:60]))
        mrr_col = _find_header(headers, args.mrr_col, MRR_COLUMNS, "MRR")
        arr_col = None if mrr_col else _find_header(headers, None, ARR_COLUMNS, "ARR")
        tenure_col = _find_header(headers, args.tenure_col, TENURE_MONTH_COLUMNS + TENURE_DAY_COLUMNS, "tenure")
    except cli.UsageError as exc:
        return run.fail(cli.STATUS_USAGE, importers.scrub(str(exc)))
    tenure_unit = args.tenure_unit
    if tenure_col and tenure_unit == "auto":
        tenure_unit = "days" if importers.normalize_header(tenure_col) in TENURE_DAY_COLUMNS else "months"
    records = []
    unreadable = 0
    for row in rows:
        flag = mapping.get(row.get(churn_col)) if row.get(churn_col) not in (None, "") else None
        if flag is None:
            unreadable += 1
            continue
        mrr = None
        if mrr_col:
            mrr = _number(row.get(mrr_col))
        elif arr_col:
            arr = _number(row.get(arr_col))
            mrr = arr / 12.0 if arr is not None else None
        tenure = _number(row.get(tenure_col)) if tenure_col else None
        if tenure is not None and tenure_unit == "days":
            tenure = tenure / 30.4375
        records.append({"row": row, "churned": flag, "mrr": mrr, "tenure": tenure})
    if not records:
        return run.fail(cli.STATUS_NOTHING, "No rows with a readable churn flag in %r." % churn_col)
    churned_n = sum(1 for r in records if r["churned"])
    if churned_n == 0:
        run.note("No churned customers in the file: segment churn shares are all 0. If the export was filtered "
                 "to active customers, export every customer with a churn flag.")
    excluded = {churn_col, mrr_col, arr_col, tenure_col}
    pii_set = set(pii)
    try:
        dimensions = [_find_header(headers, name, (), "--by") for name in (args.by or [])]
    except cli.UsageError as exc:
        return run.fail(cli.STATUS_USAGE, importers.scrub(str(exc)))
    for header in dimensions:
        if header in pii_set:
            return run.fail(cli.STATUS_USAGE, "Column %r holds personal data and is never used as a segment." % header)
    auto = not dimensions
    skipped_auto: List[str] = []
    if auto:
        for header in headers:
            key = importers.normalize_header(header)
            if header in excluded or header in pii_set or not key:
                continue
            if LEAK_RE.search(key) or ID_RE.search(key) or key in ("id",):
                skipped_auto.append(header)
                continue
            values = {r["row"].get(header) for r in records if r["row"].get(header) not in (None, "")}
            if 2 <= len(values) <= args.max_values:
                dimensions.append(header)
        dimensions = dimensions[:args.max_dimensions]
    overall = _rate(churned_n, len(records))
    total_mrr = sum(r["mrr"] for r in records if r["mrr"] is not None)
    churned_mrr = sum(r["mrr"] for r in records if r["mrr"] is not None and r["churned"])
    has_mrr = any(r["mrr"] is not None for r in records)
    results = []
    for header in dimensions:
        values = [r["row"].get(header) for r in records]
        numeric = [v for v in values if v not in (None, "") and _number(v) is not None]
        distinct = {v for v in values if v not in (None, "")}
        labels: List[Optional[str]]
        if len(distinct) > args.max_values and len(numeric) >= 0.9 * len([v for v in values if v not in (None, "")]):
            cuts = [_quantile([_number(v) for v in numeric], q) for q in (0.25, 0.5, 0.75)]
            labels = []
            for v in values:
                number = _number(v) if v not in (None, "") else None
                if number is None:
                    labels.append(None)
                elif number <= cuts[0]:
                    labels.append("Q1 (<= %s)" % _fmt_num(cuts[0]))
                elif number <= cuts[1]:
                    labels.append("Q2 (<= %s)" % _fmt_num(cuts[1]))
                elif number <= cuts[2]:
                    labels.append("Q3 (<= %s)" % _fmt_num(cuts[2]))
                else:
                    labels.append("Q4 (> %s)" % _fmt_num(cuts[2]))
            kind = "numeric_quartiles"
        elif len(distinct) > args.max_values:
            counts = Counter(v for v in values if v not in (None, ""))
            keep = {v for v, _ in counts.most_common(args.max_values)}
            labels = [(v if v in keep else "(other values)") if v not in (None, "") else None for v in values]
            kind = "top_values"
        else:
            labels = [v if v not in (None, "") else None for v in values]
            kind = "categories"
        groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for label, record in zip(labels, records):
            groups[importers.scrub(label) if label is not None else "(blank)"].append(record)
        rows_out = []
        for label, members in groups.items():
            churned = sum(1 for m in members if m["churned"])
            block = _rate(churned, len(members))
            mrr = sum(m["mrr"] for m in members if m["mrr"] is not None)
            lost = sum(m["mrr"] for m in members if m["mrr"] is not None and m["churned"])
            rows_out.append({
                "value": str(label)[:80], "customers": len(members), "churned": churned,
                "churn_share": block["rate"], "ci95": block["ci95"],
                "relative_to_overall": _r(block["rate"] / overall["rate"], 2) if overall["rate"] else None,
                "mrr": round(mrr, 2) if has_mrr else None,
                "share_of_churned_mrr": _r(lost / churned_mrr) if has_mrr and churned_mrr else None,
                "small_sample": len(members) < args.min_n,
            })
        rows_out.sort(key=lambda r: -r["customers"])
        big = [r for r in rows_out if not r["small_sample"] and r["churn_share"] is not None]
        spread = _r(max(r["churn_share"] for r in big) - min(r["churn_share"] for r in big)) if len(big) >= 2 else None
        results.append({"column": header, "kind": kind, "values": rows_out, "spread": spread})
    results.sort(key=lambda d: -(d["spread"] if d["spread"] is not None else -1))
    tenure_block = None
    with_tenure = [r for r in records if r["tenure"] is not None]
    if with_tenure:
        churned_t = [r["tenure"] for r in with_tenure if r["churned"]]
        kept_t = [r["tenure"] for r in with_tenure if not r["churned"]]
        buckets = []
        for low, high, label in TENURE_MONTH_BUCKETS:
            members = [r for r in with_tenure if _tenure_bucket(r["tenure"]) == label]
            churned = sum(1 for m in members if m["churned"])
            block = _rate(churned, len(members))
            buckets.append({"tenure": label, "customers": len(members), "churned": churned,
                            "churn_share": block["rate"], "ci95": block["ci95"],
                            "share_of_all_churned": _r(churned / float(len(churned_t))) if churned_t else None})
        tenure_block = {
            "column": tenure_col, "unit_read_as": tenure_unit,
            "churned_median_months": _r(_quantile(churned_t, 0.5), 1),
            "churned_p25_months": _r(_quantile(churned_t, 0.25), 1),
            "churned_p75_months": _r(_quantile(churned_t, 0.75), 1),
            "retained_median_months": _r(_quantile(kept_t, 0.5), 1),
            "buckets": buckets,
            "basis": "for churned customers the tenure column is read as tenure at churn; check this in the "
                     "export's documentation",
        }
    if unreadable:
        message = "%d of %d rows had no readable churn flag and were left out." % (unreadable, len(rows))
        if unreadable / float(len(rows)) > PARTIAL_SHARE:
            run.error(message)
        else:
            run.note(message)
    if pii:
        run.note("Personal-data columns were not read: %s" % ", ".join(pii))
    if auto and skipped_auto:
        run.note("Left out of automatic segments (ids, locations, or columns that describe the churn itself): %s"
                 % ", ".join(skipped_auto[:20]))
    run.note("Churn share = churned customers / customers in this file. Its period is whatever the export "
             "covers, so it is not a monthly churn rate; do not compare it with monthly benchmarks.")
    result = OrderedDict([
        ("file", os.path.basename(args.input)),
        ("churn_column", churn_col), ("mrr_column", mrr_col or arr_col), ("tenure_column", tenure_col),
        ("overall", {"customers": len(records), "churned": churned_n, "churn_share": overall["rate"],
                     "ci95": overall["ci95"], "mrr": round(total_mrr, 2) if has_mrr else None,
                     "churned_mrr": round(churned_mrr, 2) if has_mrr else None,
                     "churned_mrr_share": _r(churned_mrr / total_mrr) if has_mrr and total_mrr else None}),
        ("segments", results),
        ("tenure", tenure_block),
        ("min_n", args.min_n),
    ])
    return run.emit(result, status=cli.STATUS_PARTIAL if run.errors else cli.STATUS_OK)


def _fmt_num(value: Optional[float]) -> str:
    if value is None:
        return "?"
    return str(int(value)) if float(value).is_integer() else "%.2f" % value


# ---------------------------------------------------------------------------
# reasons and tally
# ---------------------------------------------------------------------------

REASON_COLUMNS = ("cancel_reason", "cancellation_reason", "churn_reason", "exit_reason", "reason",
                  "cancellation_feedback", "cancellation_details_feedback", "feedback", "cancellation_comment",
                  "cancellation_details_comment", "comment", "comments", "why", "exit_survey", "survey_response",
                  "response", "answer")


def cmd_reasons(args: Any, run: cli.Run) -> int:
    path = args.input
    if not path or (path != "-" and not os.path.isfile(path)):
        return run.fail(cli.STATUS_USAGE, "File not found: %s" % path)
    entries: List[Tuple[str, Optional[float]]] = []
    column = None
    other_columns: List[str] = []
    skipped_retained = 0
    empty = 0
    lower = path.lower()
    try:
        if path == "-" or lower.endswith((".txt", ".md")):
            if path == "-":
                text = cli.read_stdin_text()
            else:
                with open(path, encoding="utf-8-sig") as handle:
                    text = handle.read()
            for line in text.splitlines():
                cleaned = clean_text(line.strip().lstrip("-*").strip())
                if cleaned:
                    entries.append((cleaned, None))
                elif line.strip():
                    empty += 1
        elif lower.endswith(".json"):
            with open(path, encoding="utf-8-sig") as handle:
                data = json.load(handle)
            if isinstance(data, dict):
                data = data.get("reasons") or data.get("items") or data.get("responses") or []
            if not isinstance(data, list):
                raise cli.UsageError("Expected a JSON list of reasons (strings or objects) in %s." % path)
            for item in data:
                if isinstance(item, dict):
                    key = next((k for k in item if importers.normalize_header(k) in REASON_COLUMNS
                                or importers.normalize_header(k) == "text"), None)
                    cleaned = clean_text(item.get(key)) if key else None
                    mrr = _number(item.get("mrr")) if "mrr" in item else None
                else:
                    cleaned, mrr = clean_text(item), None
                if cleaned:
                    entries.append((cleaned, mrr))
                else:
                    empty += 1
        else:
            headers, rows, pii = _load_records(path)
            column = _find_header(headers, args.column, REASON_COLUMNS, "reason")
            if column is None:
                raise cli.UsageError("No reason column found. Pass --column NAME. Columns: %s"
                                     % ", ".join(headers[:60]))
            if column in pii:
                run.note("Column %r looks like personal data by name; its text was de-identified." % column)
            keys = {importers.normalize_header(h): h for h in headers}
            other_columns = [keys[a] for a in REASON_COLUMNS if a in keys and keys[a] != column]
            mrr_col = _find_header(headers, args.mrr_col, MRR_COLUMNS, "MRR")
            churn_col = None
            mapping: Dict[str, Optional[bool]] = {}
            if args.churn_col or any(importers.normalize_header(h) in CHURN_COLUMNS for h in headers):
                try:
                    churn_col, mapping = _detect_churn_column(headers, rows, args.churn_col)
                except cli.UsageError:
                    if args.churn_col:
                        raise
            for row in rows:
                if churn_col and mapping.get(row.get(churn_col)) is False:
                    skipped_retained += 1
                    continue
                cleaned = clean_text(row.get(column))
                if not cleaned:
                    empty += 1
                    continue
                entries.append((cleaned, _number(row.get(mrr_col)) if mrr_col else None))
    except (OSError, ValueError, cli.UsageError) as exc:
        return run.fail(cli.STATUS_USAGE, importers.scrub(str(exc)))
    if not entries:
        return run.fail(cli.STATUS_NOTHING, "No cancellation reasons found%s." % (
            " in column %r" % column if column else ""))
    groups: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
    for text, mrr in entries:
        key = _group_key(text) or text
        group = groups.setdefault(key, {"text": text, "count": 0, "mrr": 0.0, "mrr_known": 0})
        group["count"] += 1
        if mrr is not None:
            group["mrr"] += mrr
            group["mrr_known"] += 1
    ordered = sorted(groups.values(), key=lambda g: (-g["count"], -g["mrr"]))
    has_mrr = any(g["mrr_known"] for g in ordered)
    items = []
    for index, group in enumerate(ordered[:args.max], 1):
        items.append({"id": "R%d" % index, "text": group["text"], "count": group["count"],
                      "mrr": round(group["mrr"], 2) if has_mrr else None})
    not_listed = ordered[args.max:]
    short_share = sum(1 for g in ordered if len(g["text"].split()) <= 6) / float(len(ordered))
    repeat_ratio = len(entries) / float(len(ordered))
    if short_share >= 0.8 and repeat_ratio >= 3:
        style = "picklist"
    elif short_share < 0.5 or repeat_ratio < 1.5:
        style = "free_text"
    else:
        style = "mixed"
    if not_listed:
        run.note("%d rarer distinct reasons (%d responses) are not listed; raise --max to code them, or they count "
                 "as not coded in tally." % (len(not_listed), sum(g["count"] for g in not_listed)))
    if len(entries) < 30:
        run.note("Fewer than 30 responses: treat bucket and theme shares as directional (low confidence).")
    if skipped_retained:
        run.note("%d rows of customers who did not churn were left out." % skipped_retained)
    if other_columns:
        run.note("Other reason-like columns in the file: %s (pass --column to read one of them)."
                 % ", ".join(other_columns))
    result = OrderedDict([
        ("source", os.path.basename(path) if path != "-" else "stdin"),
        ("column", column),
        ("responses", len(entries)),
        ("empty_or_blank", empty),
        ("distinct", len(ordered)),
        ("style", style),
        ("mrr_column_used", has_mrr),
        ("total_mrr", round(sum(g["mrr"] for g in ordered), 2) if has_mrr else None),
        ("items", items),
        ("not_listed", {"distinct": len(not_listed), "responses": sum(g["count"] for g in not_listed),
                        "mrr": round(sum(g["mrr"] for g in not_listed), 2) if has_mrr else None}),
        ("next_step", "Code every item id into a churn bucket and a theme (references/rubric.md section 2), "
                      "save the coding as JSON and run the tally command with this output saved via --out."),
    ])
    return run.emit(result)


def _load_json_file(path: str, label: str) -> Any:
    try:
        with open(path, encoding="utf-8-sig") as handle:
            return json.load(handle)
    except OSError as exc:
        raise cli.UsageError("Cannot read %s %s: %s" % (label, path, exc))
    except ValueError as exc:
        raise cli.UsageError("Invalid JSON in %s %s: %s" % (label, path, exc))


def cmd_tally(args: Any, run: cli.Run) -> int:
    try:
        reasons = _load_json_file(args.reasons, "--reasons")
        coding = _load_json_file(args.coding, "--coding")
    except cli.UsageError as exc:
        return run.fail(cli.STATUS_USAGE, str(exc))
    if not isinstance(reasons, dict) or not isinstance(reasons.get("items"), list):
        return run.fail(cli.STATUS_USAGE, "--reasons must be the saved output of the reasons command (with items).")
    if isinstance(coding, dict) and isinstance(coding.get("items"), list):
        coded_list = coding["items"]
    elif isinstance(coding, list):
        coded_list = coding
    elif isinstance(coding, dict):
        coded_list = [dict(value, id=key) for key, value in coding.items() if isinstance(value, dict)]
    else:
        return run.fail(cli.STATUS_USAGE, "--coding must be {\"items\": [{\"id\", \"bucket\", \"theme\"}, ...]}.")
    items = {item["id"]: item for item in reasons["items"] if isinstance(item, dict) and "id" in item}
    codes: Dict[str, Dict[str, Any]] = {}
    problems = []
    unknown_ids = []
    for entry in coded_list:
        if not isinstance(entry, dict) or "id" not in entry:
            problems.append("coding entry without an id: %r" % (entry,))
            continue
        bucket = str(entry.get("bucket") or "").strip().lower()
        if bucket not in CHURN_BUCKETS:
            problems.append("%s: bucket %r is not one of %s" % (entry["id"], entry.get("bucket"),
                                                                 ", ".join(CHURN_BUCKETS)))
            continue
        theme = clean_text(entry.get("theme"), 80) or "(no theme)"
        if entry["id"] not in items:
            unknown_ids.append(str(entry["id"]))
            continue
        codes[entry["id"]] = {"bucket": bucket, "theme": theme}
    if problems:
        return run.fail(cli.STATUS_USAGE, "; ".join(problems[:10]))
    if unknown_ids:
        run.note("Coding ids not in the reasons file were ignored: %s" % ", ".join(unknown_ids[:20]))
    has_mrr = any(item.get("mrr") is not None for item in items.values())
    not_listed = reasons.get("not_listed") or {}
    total = sum(item["count"] for item in items.values()) + int(not_listed.get("responses") or 0)
    total_mrr = (sum(item.get("mrr") or 0.0 for item in items.values()) + float(not_listed.get("mrr") or 0.0)
                 if has_mrr else None)
    buckets: "OrderedDict[str, Dict[str, Any]]" = OrderedDict(
        (name, {"responses": 0, "mrr": 0.0, "reasons": 0}) for name in CHURN_BUCKETS)
    themes: Dict[Tuple[str, str], Dict[str, Any]] = {}
    uncoded = {"responses": int(not_listed.get("responses") or 0), "mrr": float(not_listed.get("mrr") or 0.0),
               "ids": []}
    for item_id, item in items.items():
        code = codes.get(item_id)
        mrr = item.get("mrr") or 0.0
        if code is None:
            uncoded["responses"] += item["count"]
            uncoded["mrr"] += mrr
            uncoded["ids"].append(item_id)
            continue
        bucket = buckets[code["bucket"]]
        bucket["responses"] += item["count"]
        bucket["mrr"] += mrr
        bucket["reasons"] += 1
        theme = themes.setdefault((code["theme"].lower(), code["bucket"]),
                                  {"theme": code["theme"], "bucket": code["bucket"], "responses": 0, "mrr": 0.0,
                                   "ids": []})
        theme["responses"] += item["count"]
        theme["mrr"] += mrr
        theme["ids"].append(item_id)

    def finish(block: Dict[str, Any]) -> Dict[str, Any]:
        block["share"] = _r(block["responses"] / float(total)) if total else None
        if has_mrr:
            block["mrr"] = round(block["mrr"], 2)
            block["mrr_share"] = _r(block["mrr"] / total_mrr) if total_mrr else None
        else:
            block["mrr"] = None
            block["mrr_share"] = None
        return block

    bucket_rows = [dict(finish(block), bucket=name) for name, block in buckets.items() if block["responses"]]
    bucket_rows.sort(key=lambda b: -b["responses"])
    theme_rows = [finish(theme) for theme in themes.values()]
    theme_rows.sort(key=lambda t: (-t["responses"], -(t["mrr"] or 0)))
    for theme in theme_rows:
        theme["ids"] = theme["ids"][:12]
    finish(uncoded)
    uncoded["ids"] = uncoded["ids"][:30]
    status = cli.STATUS_OK
    if uncoded["responses"]:
        message = "%d of %d responses are not coded (%s)." % (
            uncoded["responses"], total, "share %.1f%%" % (uncoded["share"] * 100) if uncoded["share"] else "")
        if uncoded["share"] and uncoded["share"] > PARTIAL_SHARE:
            run.error(message + " Code the remaining ids or report the shares as partial.")
            status = cli.STATUS_PARTIAL
        else:
            run.note(message)
    addressable = sum(b["responses"] for b in bucket_rows if b["bucket"] in ("preventable", "involuntary"))
    result = OrderedDict([
        ("responses", total),
        ("by_bucket", bucket_rows),
        ("by_theme", theme_rows[:25]),
        ("not_coded", uncoded),
        ("addressable_share", _r(addressable / float(total)) if total else None),
        ("addressable_basis", "preventable + involuntary responses / all responses (references/rubric.md)"),
        ("small_sample", total < 30),
    ])
    return run.emit(result, status=status)


# ---------------------------------------------------------------------------
# check
# ---------------------------------------------------------------------------


def _pct(value: Any, name: str, minimum: Optional[float] = None, maximum: Optional[float] = None) -> Optional[float]:
    number = cli.to_percent(value, name, minimum=minimum, maximum=maximum)
    return None if number is None else number / 100.0


def _benchmark_gap(path: str = BENCHMARK_FILE) -> Optional[Dict[str, Any]]:
    """Median NRR minus median GRR from the newest all-segment rows of one source."""
    try:
        with open(path, encoding="utf-8") as handle:
            rows = json.load(handle).get("rows", [])
    except (OSError, ValueError):
        return None

    def overall(metric: str) -> Dict[str, Dict[str, Any]]:
        found = {}
        for row in rows:
            segment = row.get("segment") or {}
            if (row.get("metric") == metric and row.get("verified") and row.get("period") == "annual"
                    and row.get("median") is not None
                    and all(segment.get(k) in (None, "all", "mixed") for k in ("arr_band", "acv_band", "pricing_model",
                                                                             "motion", "ai_native"))
                    and not (segment.get("extra") or {})):
                found[row["source_id"]] = row
        return found

    nrr_rows, grr_rows = overall("nrr"), overall("grr")
    shared = [key for key in nrr_rows if key in grr_rows]
    if not shared:
        return None
    best = max(shared, key=lambda key: (int(nrr_rows[key].get("year") or 0), key))
    nrr_row, grr_row = nrr_rows[best], grr_rows[best]
    return {"gap_points": round(nrr_row["median"] - grr_row["median"], 1), "source": nrr_row.get("source_name"),
            "year": nrr_row.get("year"), "rows": [nrr_row["id"], grr_row["id"]]}


def cmd_check(args: Any, run: cli.Run) -> int:
    raw = dict(DEMO_CHECK) if args.demo else {
        "logo_churn": args.logo_churn, "revenue_churn": args.revenue_churn, "grr": args.grr, "nrr": args.nrr,
        "grr_monthly": args.grr_monthly, "nrr_monthly": args.nrr_monthly, "expansion": args.expansion,
    }
    try:
        logo = _pct(raw.get("logo_churn"), "--logo-churn", 0, 100)
        rev = _pct(raw.get("revenue_churn"), "--revenue-churn", 0, 100)
        grr = _pct(raw.get("grr"), "--grr", 0, None)
        nrr = _pct(raw.get("nrr"), "--nrr", 0, None)
        grr_m = _pct(raw.get("grr_monthly"), "--grr-monthly", 0, None)
        nrr_m = _pct(raw.get("nrr_monthly"), "--nrr-monthly", 0, None)
        expansion = _pct(raw.get("expansion"), "--expansion", 0, 100)
    except cli.CoercionError as exc:
        return run.fail(cli.STATUS_USAGE, str(exc))
    if all(v is None for v in (logo, rev, grr, nrr, grr_m, nrr_m, expansion)):
        return run.fail(cli.STATUS_USAGE, "Pass at least one metric: --logo-churn, --revenue-churn, --grr, --nrr, "
                                          "--grr-monthly, --nrr-monthly or --expansion (percent).")
    derived: "OrderedDict[str, Any]" = OrderedDict()
    flags: List[Dict[str, str]] = []
    if logo is not None:
        derived["annual_logo_churn_from_monthly"] = _r(1 - (1 - logo) ** 12)
    if rev is not None:
        derived["implied_annual_grr_from_monthly_revenue_churn"] = _r((1 - rev) ** 12)
    if grr_m is not None:
        derived["annual_grr_from_monthly"] = _r(grr_m ** 12)
        if grr_m > 1:
            flags.append({"level": "impossible", "message": "Monthly GRR above 100% is impossible: GRR excludes "
                                                            "expansion. Check whether this is NRR."})
        if grr is None:
            grr = grr_m ** 12
    if nrr_m is not None:
        derived["annual_nrr_from_monthly"] = _r(nrr_m ** 12)
        if nrr is None:
            nrr = nrr_m ** 12
    if grr is not None:
        derived["monthly_gross_revenue_churn_from_grr"] = _r(1 - grr ** (1 / 12.0)) if grr <= 1 else None
        if grr > 1:
            flags.append({"level": "impossible", "message": "GRR above 100% is impossible: GRR counts only churn "
                                                            "and contraction. A value above 100% is NRR."})
    if nrr is not None:
        derived["monthly_nrr_equivalent"] = _r(nrr ** (1 / 12.0))
    if grr is not None and nrr is not None:
        derived["implied_annual_expansion_points"] = _r((nrr - grr) * 100, 1)
        if nrr < grr - 1e-9:
            flags.append({"level": "impossible", "message": "NRR below GRR is impossible for the same cohort and "
                                                            "period: NRR = GRR + expansion. One of them uses a "
                                                            "different period, cohort or formula."})
    elif rev is not None and nrr is not None:
        implied_grr = (1 - rev) ** 12
        derived["implied_annual_expansion_points"] = _r((nrr - implied_grr) * 100, 1)
        if nrr < implied_grr - 0.05:
            flags.append({"level": "inconsistent", "message": "NRR %.1f%% is below the GRR of about %.1f%% that "
                          "%.2f%% monthly revenue churn implies; NRR cannot be below GRR. Check the periods."
                          % (nrr * 100, implied_grr * 100, rev * 100)})
    gap = _benchmark_gap()
    expansion_points = derived.get("implied_annual_expansion_points")
    if gap and expansion_points is not None and expansion_points > gap["gap_points"]:
        flags.append({"level": "check", "message": "These numbers imply about %.0f points of expansion a year "
                      "(NRR minus GRR). The median NRR and median GRR in %s (%s) differ by %.0f points. Confirm that "
                      "NRR and GRR (or revenue churn) cover the same 12-month cohort before planning on expansion."
                      % (expansion_points, gap["source"], gap["year"], gap["gap_points"])})
        derived["benchmark_median_gap"] = gap
    if rev is not None and grr is not None and grr <= 1:
        implied = (1 - rev) ** 12
        gap = abs(implied - grr) * 100
        derived["gap_points_grr_vs_revenue_churn"] = _r(gap, 1)
        if gap > 5:
            flags.append({"level": "inconsistent", "message": "Monthly revenue churn %.2f%% compounds to an annual "
                          "GRR of about %.1f%%, but GRR was given as %.1f%% (gap %.1f points). One number is probably "
                          "monthly and the other annual, or they cover different periods."
                          % (rev * 100, implied * 100, grr * 100, gap)})
    if rev is not None and expansion is not None:
        monthly_nrr = 1 - rev + expansion
        derived["implied_annual_nrr_from_monthly_movements"] = _r(monthly_nrr ** 12)
        if nrr is not None:
            gap = abs(monthly_nrr ** 12 - nrr) * 100
            if gap > 5:
                flags.append({"level": "inconsistent", "message": "Monthly revenue churn and expansion compound to "
                              "an annual NRR of about %.1f%%, but NRR was given as %.1f%%."
                              % (monthly_nrr ** 12 * 100, nrr * 100)})
    if logo is not None and rev is not None and rev > logo * 3 and logo > 0:
        flags.append({"level": "check", "message": "Revenue churn is more than 3x logo churn: the customers who left "
                      "were much larger than average, or contraction is high. Confirm both use the same month."})
    if nrr is not None and grr is None and rev is None and grr_m is None:
        flags.append({"level": "check", "message": "NRR without GRR hides churn behind expansion. Ask for GRR or a "
                                                   "billing export."})
    if (nrr is not None or grr is not None) and not (args.nrr_monthly or args.grr_monthly):
        run.note("--grr and --nrr are read as trailing-12-month cohort values (annual). Use --grr-monthly or "
                 "--nrr-monthly for one month of movement.")
    result = OrderedDict([
        ("inputs", OrderedDict((k, _r(v)) for k, v in (("monthly_logo_churn", logo), ("monthly_revenue_churn", rev),
                                                        ("annual_grr", grr), ("annual_nrr", nrr),
                                                        ("monthly_expansion", expansion)) if v is not None)),
        ("derived", derived),
        ("flags", flags),
        ("consistent", not any(f["level"] in ("impossible", "inconsistent") for f in flags)),
        ("formulas", {
            "annual_from_monthly_churn": "1 - (1 - monthly) ** 12",
            "annual_from_monthly_retention": "monthly ** 12",
            "monthly_from_annual_retention": "annual ** (1/12)",
            "note": "constant-rate compounding; real cohorts churn faster early, so treat gaps under 5 points as noise",
        }),
    ])
    return run.emit(result)


# ---------------------------------------------------------------------------
# benchmarks
# ---------------------------------------------------------------------------

_MONEY_RE = re.compile(r"\$?\s*([0-9]+(?:\.[0-9]+)?)\s*([KMB])?", re.I)
_SCALE = {"K": 1e3, "M": 1e6, "B": 1e9, None: 1.0}


def _money(text: str) -> float:
    match = _MONEY_RE.search(text)
    if not match:
        raise ValueError(text)
    return float(match.group(1)) * _SCALE[(match.group(2) or "").upper() or None]


def band_contains(band: str, value: float) -> Optional[bool]:
    """'<$5M', '>=$250K', '$12K-$25K', '>$500/month' -> whether value is inside; None if unparseable."""
    text = band.replace(",", "").replace("/month", "").strip()
    try:
        if text.startswith(">="):
            return value >= _money(text[2:])
        if text.startswith("<="):
            return value <= _money(text[2:])
        if text.startswith(">"):
            return value > _money(text[1:])
        if text.startswith("<"):
            return value < _money(text[1:])
        if "-" in text:
            low, high = text.split("-", 1)
            return _money(low) <= value < _money(high)
    except ValueError:
        return None
    return None


MOTION_MAP = {"plg": "plg", "product-led": "plg", "sales-led": "sales_led", "sales_led": "sales_led",
              "hybrid": "hybrid"}
PRICING_MAP = {"per-seat": "seat", "seat": "seat", "usage": "usage", "hybrid": "hybrid", "flat": "non_seat_subscription",
               "tiered": "non_seat_subscription"}
CONTRACT_MAP = {"month-to-month": "month_to_month", "monthly": "month_to_month", "annual": "annual",
                "multi-year": "multi_year"}
FUNDING_MAP = {"bootstrapped": "bootstrapped", "equity-backed": "equity_backed", "vc": "equity_backed"}
DIM_WEIGHTS = {"acv_band": 4, "arr_band": 4, "arpa_band": 4, "pricing_model": 3, "motion": 2, "ai_native": 1,
               "company_type": 2, "contract_term": 1, "funding": 1, "growth_band": 1, "price_point": 1}


def match_row(row: Dict[str, Any], user: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Score how well a benchmark row's segment fits the user; None when it contradicts the user."""
    segment = row.get("segment") or {}
    dims: Dict[str, Any] = {}
    for key in ("arr_band", "acv_band", "pricing_model", "motion"):
        value = segment.get(key)
        if value not in (None, "all"):
            dims[key] = value
    ai = segment.get("ai_native")
    if ai is True or ai is False:
        dims["ai_native"] = ai
    for key, value in (segment.get("extra") or {}).items():
        dims[key] = value
    matched, unknown = [], []
    score = 0
    for key, value in dims.items():
        if key in ("arr_band", "acv_band", "arpa_band", "price_point"):
            known = {"arr_band": user.get("arr"), "acv_band": user.get("acv"), "arpa_band": user.get("arpa"),
                     "price_point": user.get("arpa")}[key]
            if known is None:
                unknown.append(key)
                continue
            inside = band_contains(str(value), known)
            if inside is None:
                unknown.append(key)
            elif inside:
                matched.append(key)
                score += DIM_WEIGHTS[key]
            else:
                return None
        elif key == "ai_native":
            if user.get("ai_native") is None:
                if value is True:
                    return None  # AI-native rows only for AI-native products
                unknown.append(key)
            elif user["ai_native"] == value:
                matched.append(key)
                score += DIM_WEIGHTS[key]
            else:
                return None
        elif key == "company_type":
            wanted = user.get("company_type")
            if wanted is None:
                if value == "b2c_saas":
                    return None
                unknown.append(key)
            elif wanted == value:
                matched.append(key)
                score += DIM_WEIGHTS[key]
            else:
                return None
        else:
            known = user.get(key)
            if known is None:
                unknown.append(key)
            elif known == value:
                matched.append(key)
                score += DIM_WEIGHTS.get(key, 1)
            else:
                return None
    return {"score": score, "matched": matched, "unknown": unknown}


def cmd_benchmarks(args: Any, run: cli.Run) -> int:
    path = args.file or BENCHMARK_FILE
    try:
        data = _load_json_file(path, "benchmark file")
    except cli.UsageError as exc:
        return run.fail(cli.STATUS_USAGE, str(exc) + " Run tools/sync_shared.py or reinstall the skill.")
    try:
        user = {
            "acv": cli.to_number(args.acv, "--acv", minimum=0),
            "arr": cli.to_number(args.arr, "--arr", minimum=0),
            "arpa": cli.to_number(args.arpa, "--arpa", minimum=0),
            "motion": MOTION_MAP.get((args.motion or "").lower()) if args.motion else None,
            "pricing_model": PRICING_MAP.get((args.pricing_model or "").lower()) if args.pricing_model else None,
            "contract_term": CONTRACT_MAP.get((args.contract_term or "").lower()) if args.contract_term else None,
            "funding": FUNDING_MAP.get((args.funding or "").lower()) if args.funding else None,
            "ai_native": cli.to_bool(args.ai_native, "--ai-native") if args.ai_native is not None else None,
            "company_type": {"b2b": "b2b_saas", "b2c": "b2c_saas"}.get((args.company_type or "").lower()),
        }
    except cli.CoercionError as exc:
        return run.fail(cli.STATUS_USAGE, str(exc))
    if user["arpa"] is None and user["acv"] is not None:
        user["arpa"] = round(user["acv"] / 12.0, 2)
        run.note("ARPA per month taken as ACV / 12 = %s for the ARPA and price-point rows." % user["arpa"])
    if user["company_type"] == "b2c_saas":
        run.note("Rows without a company_type come from B2B SaaS samples; quote them for a B2C product only as "
                 "context, with that caveat.")
    for flag, value, table in (("--motion", args.motion, MOTION_MAP), ("--pricing-model", args.pricing_model, PRICING_MAP),
                               ("--contract-term", args.contract_term, CONTRACT_MAP), ("--funding", args.funding, FUNDING_MAP)):
        if value and value.lower() not in table:
            return run.fail(cli.STATUS_USAGE, "%s must be one of %s" % (flag, ", ".join(sorted(table))))
    if user["pricing_model"] == "non_seat_subscription":
        run.note("Flat and tiered pricing are matched to the 'non_seat_subscription' segment where a source has it.")
    metrics = args.metric or ["grr", "nrr", "logo_churn"]
    today = date.today()
    out: "OrderedDict[str, Any]" = OrderedDict()
    for metric in metrics:
        candidates = []
        for row in data.get("rows", []):
            if row.get("metric") != metric or not row.get("verified"):
                continue
            fit = match_row(row, user)
            if fit is None:
                continue
            candidates.append((row, fit))
        confidence_rank = {"high": 3, "medium": 2, "low": 1}
        candidates.sort(key=lambda pair: (-pair[1]["score"], len(pair[1]["unknown"]), -int(pair[0].get("year") or 0),
                                          -confidence_rank.get(pair[0].get("confidence"), 0)))
        chosen = candidates[:args.limit]
        general = [pair for pair in candidates if not pair[1]["matched"] and not pair[1]["unknown"]]
        for pair in general[:2]:
            if pair not in chosen:
                chosen.append(pair)
        rows_out = []
        for row, fit in chosen:
            verified_on = row.get("verified_on")
            age = None
            try:
                age = (today - date.fromisoformat(verified_on)).days if verified_on else None
            except ValueError:
                age = None
            rows_out.append(OrderedDict([
                ("id", row["id"]), ("label", row.get("metric_label")), ("period", row.get("period")),
                ("unit", row.get("unit")), ("direction", row.get("direction")), ("segment", row.get("segment")),
                ("p25", row.get("p25")), ("median", row.get("median")), ("p75", row.get("p75")),
                ("p90", row.get("p90")), ("mean", row.get("mean")), ("value", row.get("value")),
                ("monthly_equivalent", row.get("monthly_equivalent")),
                ("annual_equivalent", row.get("annual_equivalent")),
                ("source", row.get("source_name")), ("url", row.get("source_url")), ("year", row.get("year")),
                ("data_period", row.get("data_period")), ("sample_size", row.get("sample_size")),
                ("confidence", row.get("confidence")), ("verified_on", verified_on),
                ("stale", age is not None and age > STALE_DAYS),
                ("definition", row.get("definition")), ("note", (row.get("value_note") or "")[:300] or None),
                ("fit", fit),
            ]))
        out[metric] = rows_out
        if not rows_out:
            run.note("No verified %s row fits this segment." % metric)
        if any(r["stale"] for r in rows_out):
            run.note("Some %s rows were verified more than 6 months ago; re-check them before quoting." % metric)
    unknown_inputs = [k for k in ("acv", "arr", "motion", "pricing_model") if user.get(k) is None]
    if unknown_inputs:
        run.note("Segment inputs not given: %s. Rows whose segment needs them are marked fit.unknown; say so when "
                 "you quote them." % ", ".join(unknown_inputs))
    result = OrderedDict([
        ("benchmark_file_verified", data.get("last_verified")),
        ("segment_inputs", user),
        ("rows", out),
        ("conversions", (data.get("retention_conversions") or {}).get("formulas")),
        ("rules", "Compare like with like: annual cohort GRR/NRR with annual rows; one month of movement with "
                  "monthly_equivalent; monthly logo churn with logo_churn rows. Quote source, year and segment."),
    ])
    return run.emit(result)


# ---------------------------------------------------------------------------
# test-plan and score
# ---------------------------------------------------------------------------


def cmd_test_plan(args: Any, run: cli.Run) -> int:
    try:
        baseline = cli.to_percent(args.baseline, "--baseline", assume_fraction=True, minimum=0, maximum=100)
        weekly = cli.to_number(args.weekly, "--weekly", minimum=0)
        mde = cli.to_percent(args.mde, "--mde", assume_fraction=True)
    except cli.CoercionError as exc:
        return run.fail(cli.STATUS_USAGE, str(exc))
    if baseline is None or weekly is None or mde is None:
        return run.fail(cli.STATUS_USAGE, "--baseline, --weekly and --mde are required.")
    try:
        plan = stats.plan_test(baseline / 100.0, weekly, mde / 100.0, relative=not args.absolute,
                               max_weeks=args.max_weeks)
    except ValueError as exc:
        return run.fail(cli.STATUS_USAGE, str(exc))
    plan["test_plan"] = "ab_test" if plan["feasible"] else "ship_and_measure"
    plan["weeks_to_run"] = max(2, plan["weeks_rounded"]) if plan["feasible"] else None
    plan["unit_note"] = ("weekly = units entering the test per week (for example cancel-flow starts, failed "
                         "payments or churned customers contacted), not site visitors")
    return run.emit(plan)


def cmd_score(args: Any, run: cli.Run) -> int:
    try:
        data = _load_json_file(args.input, "dimensions file") if args.input else None
    except cli.UsageError as exc:
        return run.fail(cli.STATUS_USAGE, str(exc))
    if not isinstance(data, dict) or not isinstance(data.get("dimensions"), list):
        return run.fail(cli.STATUS_USAGE, "Expected {\"rubric\": \"program\", \"dimensions\": [{\"id\", \"score\", "
                                          "\"status\", \"confidence\", \"evidence\"}]}.")
    name = args.rubric or data.get("rubric")
    if name not in RUBRICS:
        return run.fail(cli.STATUS_USAGE, "rubric must be one of %s" % ", ".join(RUBRICS))
    weights = RUBRICS[name]
    given: Dict[str, Dict[str, Any]] = {}
    problems = []
    for entry in data["dimensions"]:
        if not isinstance(entry, dict) or entry.get("id") not in weights:
            problems.append("unknown dimension %r (expected %s)" % (
                entry.get("id") if isinstance(entry, dict) else entry, ", ".join(weights)))
            continue
        status = entry.get("status") or ("scored" if entry.get("score") is not None else "not_measured")
        if status not in DIMENSION_STATUSES:
            problems.append("%s: status must be one of %s" % (entry["id"], ", ".join(DIMENSION_STATUSES)))
            continue
        score = entry.get("score")
        if status == "scored":
            try:
                score = cli.to_number(score, entry["id"], minimum=0, maximum=10)
            except cli.CoercionError as exc:
                problems.append(str(exc))
                continue
            if score is None:
                problems.append("%s: status scored needs a score 0-10" % entry["id"])
                continue
        confidence = (entry.get("confidence") or "").lower() or None
        if status == "scored" and confidence not in CONFIDENCES:
            problems.append("%s: confidence must be high, medium or low" % entry["id"])
            continue
        given[entry["id"]] = {"status": status, "score": score if status == "scored" else None,
                              "confidence": confidence if status == "scored" else None,
                              "evidence": entry.get("evidence") or []}
    if problems:
        return run.fail(cli.STATUS_USAGE, "; ".join(problems[:10]))
    missing = [dim for dim in weights if dim not in given]
    if missing:
        run.note("Dimensions not in the file count as not_measured: %s" % ", ".join(missing))
    rows = []
    applicable = measured = earned = 0.0
    weight_by_conf: Counter = Counter()
    for dim, weight in weights.items():
        entry = given.get(dim, {"status": "not_measured", "score": None, "confidence": None, "evidence": []})
        if entry["status"] != "na":
            applicable += weight
        if entry["status"] == "scored":
            measured += weight
            earned += weight * entry["score"] / 10.0
            weight_by_conf[entry["confidence"]] += weight
        if entry["status"] == "scored" and not entry["evidence"]:
            run.note("%s has a score but no evidence ids; every score needs evidence." % dim)
        rows.append(OrderedDict([("id", dim), ("weight", weight), ("status", entry["status"]),
                                 ("score", entry["score"]), ("max", 10), ("confidence", entry["confidence"]),
                                 ("evidence", entry["evidence"])]))
    measured_share = measured / applicable if applicable else 0.0
    composite = round(earned / measured * 100) if measured else None
    show = measured_share >= 0.6 and composite is not None
    if measured:
        if weight_by_conf["high"] / measured >= 0.8:
            confidence = "high"
        elif weight_by_conf["low"] / measured > 0.5:
            confidence = "low"
        else:
            confidence = "medium"
    else:
        confidence = None
    result = OrderedDict([
        ("rubric", name), ("rubric_version", RUBRIC_VERSION),
        ("value", composite if show else None), ("max", 100),
        ("composite_if_shown", composite),
        ("measured_weight", _r(measured_share, 2)),
        ("show_composite", show),
        ("reason", None if show else "less than 60% of the applicable weight was measured; show dimension scores only"),
        ("confidence", confidence),
        ("dimensions", rows),
    ])
    return run.emit(result)


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------


def _common(parser: cli.ArgumentParser, demo: bool = False) -> None:
    parser.add_argument("--json", action="store_true", help="print only JSON to stdout (logs go to stderr)")
    parser.add_argument("--out", metavar="PATH", help="also save the JSON result to PATH")
    if demo:
        parser.add_argument("--demo", action="store_true", help="run on built-in sample numbers (labelled DEMO)")


def build_parser() -> cli.ArgumentParser:
    parser = cli.ArgumentParser(
        prog="retention_facts.py",
        description="Deterministic retention facts and math for the retention-playbook skill.",
    )
    parser.add_argument("--version", action="version", version="%(prog)s " + importers.__version__)
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("billing", help="billing or invoices export: churn, cohorts, GRR/NRR, time to churn")
    p.add_argument("input", nargs="?", help="the downloaded export (.csv, .tsv or .zip)")
    p.add_argument("--as-of", metavar="YYYY-MM", help="month to report on (default: latest month in the file)")
    p.add_argument("--months", type=int, default=12, help="months of history to summarize (default 12)")
    p.add_argument("--currency", metavar="CODE", help="currency for files without a currency column")
    p.add_argument("--amount-unit", choices=("auto", "major", "minor"), default="auto")
    p.add_argument("--source", metavar="FORMAT", help="force an importer format id")
    _common(p)

    p = sub.add_parser("segments", help="customer table with a churn flag: churn share by segment and tenure")
    p.add_argument("input", nargs="?", help="CSV or JSON list, one row per customer")
    p.add_argument("--churn-col", metavar="COLUMN")
    p.add_argument("--by", action="append", metavar="COLUMN", help="segment column (repeat); default: automatic")
    p.add_argument("--mrr-col", metavar="COLUMN")
    p.add_argument("--tenure-col", metavar="COLUMN")
    p.add_argument("--tenure-unit", choices=("auto", "months", "days"), default="auto")
    p.add_argument("--max-values", type=int, default=12, help="most values per segment column (default 12)")
    p.add_argument("--max-dimensions", type=int, default=12, help="most automatic segment columns (default 12)")
    p.add_argument("--min-n", type=int, default=30, help="segments smaller than this are flagged (default 30)")
    _common(p)

    p = sub.add_parser("reasons", help="cancellation reasons: de-duplicated, de-identified, with ids")
    p.add_argument("input", nargs="?", help="CSV, .txt (one reason per line), JSON, or '-' for stdin")
    p.add_argument("--column", metavar="COLUMN", help="reason column in a CSV")
    p.add_argument("--mrr-col", metavar="COLUMN")
    p.add_argument("--churn-col", metavar="COLUMN", help="only rows where this flag is churned")
    p.add_argument("--max", type=int, default=200, help="most distinct reasons to list (default 200)")
    _common(p)

    p = sub.add_parser("tally", help="shares per churn bucket and theme from the model's coding")
    p.add_argument("--reasons", required=True, metavar="PATH", help="saved JSON from the reasons command (--out)")
    p.add_argument("--coding", required=True, metavar="PATH", help="JSON with id, bucket and theme per reason")
    _common(p)

    p = sub.add_parser("check", help="sanity check of typed churn, GRR and NRR")
    p.add_argument("--logo-churn", metavar="PCT", help="monthly logo churn, percent")
    p.add_argument("--revenue-churn", metavar="PCT", help="monthly gross revenue churn (churn + contraction), percent")
    p.add_argument("--grr", metavar="PCT", help="trailing-12-month cohort GRR, percent")
    p.add_argument("--nrr", metavar="PCT", help="trailing-12-month cohort NRR, percent")
    p.add_argument("--grr-monthly", metavar="PCT", help="one month of GRR, percent")
    p.add_argument("--nrr-monthly", metavar="PCT", help="one month of NRR, percent")
    p.add_argument("--expansion", metavar="PCT", help="monthly expansion MRR as percent of starting MRR")
    _common(p, demo=True)

    p = sub.add_parser("benchmarks", help="matching GRR, NRR and logo churn rows from the shared benchmark file")
    p.add_argument("--acv", metavar="USD", help="average annual contract value per customer")
    p.add_argument("--arr", metavar="USD", help="company ARR")
    p.add_argument("--arpa", metavar="USD", help="average revenue per account per month")
    p.add_argument("--motion", metavar="MOTION", help="plg, sales-led or hybrid")
    p.add_argument("--pricing-model", metavar="MODEL", help="per-seat, usage, hybrid, flat or tiered")
    p.add_argument("--contract-term", metavar="TERM", help="month-to-month, annual or multi-year")
    p.add_argument("--funding", metavar="FUNDING", help="bootstrapped or equity-backed")
    p.add_argument("--ai-native", metavar="YES/NO")
    p.add_argument("--company-type", choices=("b2b", "b2c"))
    p.add_argument("--metric", action="append", choices=("grr", "nrr", "logo_churn", "month_1_retention"))
    p.add_argument("--limit", type=int, default=4, help="rows per metric (default 4)")
    p.add_argument("--file", metavar="PATH", help=argparse.SUPPRESS)
    _common(p)

    p = sub.add_parser("test-plan", help="A/B test sizing for a retention bet (4-week limit)")
    p.add_argument("--baseline", required=True, metavar="RATE", help="current rate, for example 0.25 or 25%%")
    p.add_argument("--weekly", required=True, metavar="N", help="units entering the test per week")
    p.add_argument("--mde", required=True, metavar="CHANGE", help="relative change to detect, for example 0.2 or -20%%")
    p.add_argument("--absolute", action="store_true", help="--mde is an absolute change in the rate")
    p.add_argument("--max-weeks", type=float, default=4.0)
    _common(p)

    p = sub.add_parser("score", help="composite from rubric dimension scores")
    p.add_argument("input", nargs="?", help="JSON file with rubric and dimensions")
    p.add_argument("--rubric", choices=tuple(RUBRICS))
    _common(p)
    return parser


COMMANDS = {
    "billing": cmd_billing, "segments": cmd_segments, "reasons": cmd_reasons, "tally": cmd_tally,
    "check": cmd_check, "benchmarks": cmd_benchmarks, "test-plan": cmd_test_plan, "score": cmd_score,
}


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        run = cli.Run(TOOL, json_mode="--json" in (argv if argv is not None else sys.argv[1:]))
        return run.fail(cli.STATUS_USAGE, "Choose a command: %s" % ", ".join(COMMANDS))
    run = cli.Run("%s %s" % (TOOL, args.command), args)
    return COMMANDS[args.command](args, run)


if __name__ == "__main__":
    sys.exit(main())
