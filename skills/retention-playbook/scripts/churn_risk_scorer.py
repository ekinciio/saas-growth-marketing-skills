#!/usr/bin/env python3
"""Per-account churn risk signals and engagement scores for SaaS customers.

The script reads one row per customer account (JSON or CSV), coerces the
values people export from a CRM or analytics tool, and returns facts:

- risk: which early-warning signals fired (ids from
  references/churn-signals.md), their severity and weights, the alert tier
  from the reference's combination rules (red, orange, yellow, green), a
  risk level floored by that tier, an uncapped raw score for ranking, and
  MRR-weighted risk when the account's MRR is known;
- engagement: a separate positive-usage score (frequency, recency, breadth,
  seat use, trend) with data coverage; below 60% coverage it says
  "insufficient_data" instead of guessing;
- summary: accounts and MRR by risk level and alert tier, MRR at risk, the
  most common signals and the data coverage of each field;
- calibrate (optional): with a churned label per account, per-signal churn
  lift with Wilson intervals, churn by alert tier and the AUC of the score.

It never recommends actions: the model maps each fired signal to an
intervention using references/churn-signals.md. Missing data is reported as
missing, never as healthy: an empty record is "NOT_MEASURED" and an account
with too little data and no fired signal is "UNKNOWN", not "LOW".

Usage (one row per account):

    python3 churn_risk_scorer.py accounts.csv --json
    python3 churn_risk_scorer.py accounts.json --json --top 20 --cadence-days 7
    python3 churn_risk_scorer.py accounts.csv --json --summary --accounts-out ranked.csv
    python3 churn_risk_scorer.py history.csv --json --calibrate
    python3 churn_risk_scorer.py --demo --json

Exit codes (shared CLI contract): 0 ok, 2 usage or input error (including
aggregate metrics passed instead of accounts), 4 partial (more than 5% of
rows had values that could not be read), 5 nothing to analyze.
"""

from __future__ import annotations

import csv
import json
import math
import os
import re
import sys
from collections import Counter, OrderedDict
from typing import Any, Dict, List, Optional, Tuple

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from _growthkit import cli, importers, stats  # noqa: E402

TOOL = "churn_risk_scorer"
SCORER_VERSION = "risk-v2"
DEFAULT_CADENCE_DAYS = 7.0
DEFAULT_TOP = 10
ENGAGEMENT_MIN_COVERAGE = 0.6
PARTIAL_ROW_SHARE = 0.05
MAX_TICKET_SUBJECTS = 5
MAX_TEXT = 120
MIN_LOGIN_BASELINE = 5          # login decline needs a real baseline
MIN_FEATURE_BASELINE = 3
SEAT_CUT_HIGH_SHARE = 0.20      # seat cut of 20%+ of the previous seats is HIGH

SEVERITY_RANK = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}
LEVELS = ("LOW", "MEDIUM", "HIGH", "CRITICAL")
TIER_ORDER = {"red": 4, "orange": 3, "yellow": 2, "green": 1}
TIER_FLOOR = {"red": "CRITICAL", "orange": "HIGH", "yellow": "MEDIUM", "green": None}
RESPONSE_WINDOW = {
    "CRITICAL": "same business day",
    "HIGH": "within 2 business days",
    "MEDIUM": "within 1 week",
    "LOW": "routine monitoring",
    "UNKNOWN": "collect the missing data first",
    "NOT_MEASURED": "no data for this account",
}

# ---------------------------------------------------------------------------
# Input schema: canonical field, kind, accepted column names (normalized)
# ---------------------------------------------------------------------------

FIELD_SPECS: List[Tuple[str, str, Tuple[str, ...]]] = [
    ("account_id", "id", ("account_id", "customer_id", "customerid", "account", "customer", "id",
                          "company_id", "org_id", "organization_id", "workspace_id", "subscriber_id",
                          "user_id", "userid")),
    ("mrr", "money", ("mrr", "monthly_recurring_revenue", "mrr_usd", "monthly_revenue", "monthly_charge",
                      "monthly_charges", "monthlycharges")),
    ("arr", "money", ("arr", "annual_recurring_revenue", "acv", "annual_contract_value")),
    ("segment", "label", ("segment", "plan", "tier", "plan_name", "contract", "contract_type")),
    ("churned", "bool", ("churned", "churn", "is_churned", "churn_label", "churn_value", "churn_flag",
                         "has_churned")),
    ("login_frequency_last_30d", "count", ("login_frequency_last_30d", "logins_last_30d", "logins_30d",
                                           "sessions_last_30d", "sessions_30d", "login_count_30d")),
    ("login_frequency_prev_30d", "count", ("login_frequency_prev_30d", "logins_prev_30d",
                                           "logins_previous_30d", "sessions_prev_30d", "login_count_prev_30d")),
    ("active_days_last_30d", "count", ("active_days_last_30d", "active_days_30d", "days_active_30d")),
    ("last_login_days_ago", "days", ("last_login_days_ago", "days_since_last_login", "days_since_login",
                                     "days_since_last_seen", "last_seen_days_ago", "days_since_last_activity",
                                     "days_inactive")),
    ("expected_cadence_days", "days_pos", ("expected_cadence_days", "cadence_days", "usage_cadence_days")),
    ("features_used_last_30d", "count", ("features_used_last_30d", "features_used_30d",
                                         "distinct_features_30d")),
    ("features_used_prev_30d", "count", ("features_used_prev_30d", "features_used_previous_30d",
                                         "distinct_features_prev_30d")),
    ("features_total", "count_pos", ("features_total", "features_available")),
    ("key_actions_used_30d", "count", ("key_actions_used_30d", "key_actions_30d", "value_actions_30d")),
    ("key_actions_total", "count_pos", ("key_actions_total", "key_actions_defined")),
    ("core_action_days_ago", "days", ("core_action_days_ago", "days_since_core_action",
                                      "days_since_key_action")),
    ("seats", "count", ("seats", "licensed_seats", "seat_count", "seats_purchased", "licenses", "quantity")),
    ("active_users_30d", "count", ("active_users_30d", "active_users", "active_seats", "mau")),
    ("seat_count_change", "signed", ("seat_count_change", "seat_change", "seats_change", "seat_delta")),
    ("nps_score", "nps", ("nps_score", "nps", "latest_nps", "nps_latest")),
    ("prev_nps_score", "nps", ("prev_nps_score", "previous_nps", "prev_nps", "nps_previous")),
    ("onboarding_completed", "bool", ("onboarding_completed", "onboarded", "completed_onboarding")),
    ("account_age_days", "days", ("account_age_days", "tenure_days", "days_since_signup", "customer_age_days")),
    ("emails_unopened_streak", "count", ("emails_unopened_streak", "unopened_emails_streak",
                                         "emails_unopened")),
    ("support_tickets_last_90d", "count", ("support_tickets_last_90d", "support_tickets_90d", "tickets_90d",
                                           "tickets_last_90d", "support_tickets")),
    ("billing_tickets_last_90d", "count", ("billing_tickets_last_90d", "billing_tickets_90d")),
    ("ticket_subjects", "text_list", ("ticket_subjects", "recent_ticket_subjects")),
    ("has_billing_issues", "bool", ("has_billing_issues", "billing_issue", "billing_issues", "payment_failed",
                                    "failed_payment", "has_failed_payment", "past_due")),
    ("has_downgrade_inquiry", "bool", ("has_downgrade_inquiry", "downgrade_inquiry", "asked_to_downgrade")),
    ("contract_renewal_days", "days_signed", ("contract_renewal_days", "days_to_renewal", "renewal_days",
                                              "days_until_renewal")),
    ("champion_left", "bool", ("champion_left", "stakeholder_change", "champion_changed", "sponsor_left")),
    ("has_exported_data", "bool", ("has_exported_data", "data_export", "exported_data", "bulk_export")),
    ("has_visited_cancellation_page", "bool", ("has_visited_cancellation_page", "cancel_page_visit",
                                               "visited_cancel_page", "cancellation_page_visit")),
    ("has_removed_integration", "bool", ("has_removed_integration", "integration_removed",
                                         "removed_integration")),
    ("has_competitor_mention", "bool", ("has_competitor_mention", "competitor_mention",
                                        "mentioned_competitor")),
]
FIELD_KIND = {name: kind for name, kind, _ in FIELD_SPECS}
SIGNAL_INPUT_FIELDS = [name for name, _, _ in FIELD_SPECS
                       if name not in ("account_id", "mrr", "arr", "segment", "churned", "ticket_subjects",
                                       "expected_cadence_days", "features_total", "key_actions_total")]

# Keys that mean "these are company-level metrics, not one account".
AGGREGATE_KEYS = frozenset({
    "monthly_logo_churn", "monthly_revenue_churn", "logo_churn", "revenue_churn", "nrr", "grr",
    "net_revenue_retention", "gross_revenue_retention", "churn_rate", "monthly_churn", "mrr_churn",
    "monthly_churn_rate", "logo_churn_rate", "revenue_churn_rate",
})

# Coverage families: an account is only called LOW risk when its usage
# activity and at least two other families were measured.
FAMILIES = OrderedDict([
    ("activity", ("login_frequency_last_30d", "last_login_days_ago", "active_days_last_30d")),
    ("breadth", ("features_used_last_30d", "key_actions_used_30d", "core_action_days_ago")),
    ("sentiment", ("nps_score",)),
    ("billing", ("has_billing_issues",)),
    ("intent", ("has_visited_cancellation_page", "has_downgrade_inquiry", "has_exported_data")),
    ("commercial", ("seat_count_change", "active_users_30d", "contract_renewal_days", "champion_left")),
])
MIN_FAMILIES_FOR_LOW = 3

# ---------------------------------------------------------------------------
# Signal catalog. Ids, severities and weights match references/churn-signals.md.
# Signals in the same group describe one behaviour: the group counts once (at
# its highest severity) in the combination rules and its weights are capped.
# ---------------------------------------------------------------------------

SIGNALS: "OrderedDict[str, Dict[str, Any]]" = OrderedDict([
    ("cancel_page_visit", {"label": "Visited the cancellation page", "severity": "CRITICAL", "weight": 30,
                           "category": "behavioral"}),
    ("downgrade_inquiry", {"label": "Asked about downgrading or cancelling", "severity": "CRITICAL",
                           "weight": 25, "category": "account"}),
    ("data_export", {"label": "Bulk data export", "severity": "CRITICAL", "weight": 20,
                     "category": "behavioral"}),
    ("login_decline", {"label": "Logins fell more than 50% from the previous 30 days", "severity": "HIGH",
                       "weight": 25, "category": "usage", "group": "activity"}),
    ("dormant", {"label": "No login for more than 2x the expected cadence", "severity": "HIGH", "weight": 20,
                 "category": "usage", "group": "activity"}),
    ("idle", {"label": "No login for longer than the expected cadence", "severity": "MEDIUM", "weight": 10,
              "category": "usage", "group": "activity"}),
    ("core_feature_disuse", {"label": "Core value action not used recently", "severity": "HIGH", "weight": 20,
                             "category": "usage"}),
    ("feature_abandonment", {"label": "Distinct features used fell 30% or more", "severity": "MEDIUM",
                             "weight": 15, "category": "usage"}),
    ("single_user", {"label": "Only one active user on a multi-seat plan", "severity": "MEDIUM", "weight": 10,
                     "category": "usage"}),
    ("onboarding_incomplete", {"label": "Onboarding not completed after 14 days", "severity": "HIGH",
                               "weight": 20, "category": "engagement"}),
    ("nps_detractor", {"label": "Latest NPS response 0-6 (detractor)", "severity": "HIGH", "weight": 20,
                       "category": "engagement", "group": "nps"}),
    ("nps_drop", {"label": "NPS fell 3 or more points", "severity": "HIGH", "weight": 15,
                  "category": "engagement", "group": "nps"}),
    ("nps_passive", {"label": "Latest NPS response 7-8 (passive)", "severity": "LOW", "weight": 5,
                     "category": "engagement", "group": "nps"}),
    ("email_unresponsive", {"label": "3 or more emails in a row unopened", "severity": "MEDIUM", "weight": 10,
                            "category": "engagement"}),
    ("silent_low_usage", {"label": "No support tickets in 90 days and low usage", "severity": "LOW",
                          "weight": 5, "category": "engagement"}),
    ("payment_failed", {"label": "Failed payment or past-due invoice (involuntary churn risk)",
                        "severity": "HIGH", "weight": 15, "category": "account"}),
    ("billing_dispute", {"label": "2 or more billing tickets in 90 days", "severity": "MEDIUM", "weight": 10,
                         "category": "account"}),
    ("champion_left", {"label": "Champion or decision-maker changed", "severity": "HIGH", "weight": 20,
                       "category": "account"}),
    ("renewal_at_risk", {"label": "Renewal within 30 days (or overdue) with other risk signals",
                         "severity": "MEDIUM", "weight": 10, "category": "account"}),
    ("seat_reduction", {"label": "Seat count reduced", "severity": "HIGH", "weight": 15,
                        "category": "behavioral"}),
    ("integration_removed", {"label": "Removed an active integration", "severity": "HIGH", "weight": 15,
                             "category": "behavioral"}),
    ("competitor_mention", {"label": "Mentioned a competitor or switching", "severity": "HIGH", "weight": 15,
                            "category": "behavioral"}),
])
GROUP_CAPS = {"activity": 35, "nps": 25}

ENGAGEMENT_WEIGHTS = OrderedDict([
    ("frequency", 30.0), ("recency", 20.0), ("breadth", 25.0), ("seat_utilization", 15.0), ("trend", 10.0),
])
ENGAGEMENT_TIERS = (("champion", 80), ("healthy", 60), ("at_risk", 40), ("disengaging", 20), ("ghost", 0))

_PHONE_RE = re.compile(r"\+?\d[\d ()./-]{7,}\d")


# ---------------------------------------------------------------------------
# Reading and coercing input
# ---------------------------------------------------------------------------


def _norm_key(key: Any) -> str:
    return importers.normalize_header(key)


def _alias_map(keys: List[str], overrides: Dict[str, str]) -> Tuple[Dict[str, str], List[str]]:
    """{canonical: source key} for the keys present, plus the keys left unused."""
    present = list(keys)
    used = set()
    mapping: Dict[str, str] = {}
    for canonical, column in overrides.items():
        column_key = _norm_key(column)
        if column_key in present:
            mapping[canonical] = column_key
            used.add(column_key)
    for canonical, _kind, aliases in FIELD_SPECS:
        if canonical in mapping:
            continue
        for alias in aliases:
            if alias in present and alias not in used:
                mapping[canonical] = alias
                used.add(alias)
                break
    unused = [key for key in present if key not in used]
    return mapping, unused


def _clean_text(value: Any, limit: int = MAX_TEXT) -> Optional[str]:
    text = cli.to_text(value) if not isinstance(value, (list, dict)) else None
    if not text:
        return None
    text = importers.scrub(" ".join(text.split()))
    text = _PHONE_RE.sub("[phone]", text)
    return text[:limit]


def _coerce_value(name: str, kind: str, value: Any) -> Any:
    """Coerce one field. Raises cli.CoercionError with a readable message."""
    if kind == "id":
        return _clean_text(value, 80)
    if kind == "label":
        return _clean_text(value, 60)
    if kind == "text_list":
        if isinstance(value, list):
            items = value
        elif cli.is_missing(value):
            return None
        else:
            items = re.split(r"\s*[;|]\s*", str(value))
        cleaned = [_clean_text(item) for item in items]
        cleaned = [item for item in cleaned if item]
        return cleaned[:MAX_TICKET_SUBJECTS] or None
    if kind == "bool":
        return cli.to_bool(value, name)
    if kind == "money":
        return cli.to_number(value, name, minimum=0)
    if kind == "count":
        return cli.to_number(value, name, minimum=0)
    if kind == "count_pos":
        return cli.to_number(value, name, minimum=1)
    if kind == "days":
        return cli.to_number(value, name, minimum=0)
    if kind == "days_pos":
        number = cli.to_number(value, name, minimum=0)
        if number is not None and number <= 0:
            raise cli.CoercionError("must be greater than 0, got %r" % (value,), name, value)
        return number
    if kind in ("days_signed", "signed"):
        return cli.to_number(value, name)
    if kind == "nps":
        return cli.to_number(value, name, minimum=0, maximum=10)
    raise ValueError("unknown field kind %r" % kind)


def coerce_account(raw: Dict[str, Any], overrides: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Map aliases to canonical fields and coerce types.

    Returns {"fields": {...}, "warnings": [...], "unused": [...]}; a value
    that cannot be read is dropped (treated as missing) with a warning.
    """
    normalized: Dict[str, Any] = {}
    for key, value in raw.items():
        normalized.setdefault(_norm_key(key), value)
    mapping, unused = _alias_map(list(normalized), overrides or {})
    fields: Dict[str, Any] = {}
    warnings: List[str] = []
    for canonical, source in mapping.items():
        try:
            value = _coerce_value(canonical, FIELD_KIND[canonical], normalized[source])
        except cli.CoercionError as exc:
            warnings.append("%s: %s" % (source, str(exc).split(": ", 1)[-1]))
            continue
        if value is not None:
            fields[canonical] = value
    if "mrr" not in fields and fields.get("arr") is not None:
        fields["mrr"] = fields["arr"] / 12.0
    return {"fields": fields, "warnings": warnings, "unused": unused}


def _looks_aggregate(record: Dict[str, Any]) -> bool:
    keys = {_norm_key(key) for key in record}
    if not keys & AGGREGATE_KEYS:
        return False
    mapping, _ = _alias_map(list(keys), {})
    return not any(name in mapping for name in SIGNAL_INPUT_FIELDS)


def _rows_from_json(data: Any) -> List[Dict[str, Any]]:
    if isinstance(data, dict):
        for key in ("customers", "accounts", "data", "rows", "records", "items"):
            if isinstance(data.get(key), list):
                return list(data[key])
        return [data]
    if isinstance(data, list):
        return data
    raise cli.UsageError("Expected a JSON object, a list of objects, or {\"customers\": [...]}, got %s."
                         % type(data).__name__)


def _rows_from_csv(text: str, name: str) -> Tuple[List[Dict[str, Any]], List[str]]:
    try:
        table = importers.parse_table(text, name)
    except importers.ImportFormatError as exc:
        raise cli.UsageError(str(exc))
    pii = table.pii_headers()
    rows = []
    for row in table.rows:
        record = OrderedDict()
        for index, key in enumerate(table.keys):
            if table.headers[index] in pii or not key:
                continue
            record[key] = row[index] if index < len(row) else ""
        rows.append(record)
    return rows, pii


def load_rows(value: Optional[str]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Read accounts from a JSON or CSV file or '-' (stdin). Returns (rows, info)."""
    source = cli.resolve_input(value, allow_url=False, allow_file=True, allow_stdin=True)
    label = "stdin" if source["kind"] == "stdin" else os.path.basename(source["value"])
    text = source["text"] or ""
    stripped = text.lstrip()
    is_json = stripped.startswith(("{", "[")) or label.lower().endswith((".json", ".jsonl"))
    info: Dict[str, Any] = {"source": label, "format": None, "pii_columns_ignored": []}
    if label.lower().endswith(".jsonl"):
        rows = []
        for number, line in enumerate(text.splitlines(), 1):
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except ValueError as exc:
                    raise cli.UsageError("Invalid JSON on line %d of %s: %s" % (number, label, exc))
        info["format"] = "jsonl"
        return rows, info
    if is_json:
        try:
            data = json.loads(text)
        except ValueError as exc:
            raise cli.UsageError("Invalid JSON in %s: %s" % (label, exc))
        info["format"] = "json"
        return _rows_from_json(data), info
    rows, pii = _rows_from_csv(text, label)
    info["format"] = "csv"
    info["pii_columns_ignored"] = pii
    return rows, info


# ---------------------------------------------------------------------------
# Assessment of one account
# ---------------------------------------------------------------------------


def _fire(fired: List[Dict[str, Any]], signal_id: str, evidence: str,
          severity: Optional[str] = None, weight: Optional[int] = None) -> None:
    spec = SIGNALS[signal_id]
    fired.append({
        "id": signal_id,
        "label": spec["label"],
        "severity": severity or spec["severity"],
        "weight": spec["weight"] if weight is None else weight,
        "category": spec["category"],
        "group": spec.get("group"),
        "evidence": evidence,
    })


def _fmt(number: Optional[float]) -> str:
    if number is None:
        return "?"
    return str(int(number)) if float(number).is_integer() else "%.1f" % number


def assess_risk(f: Dict[str, Any], cadence_default: float) -> Dict[str, Any]:
    """Fired signals, alert tier, risk level and coverage for coerced fields."""
    fired: List[Dict[str, Any]] = []
    evaluated: List[str] = []
    cadence = float(f.get("expected_cadence_days") or cadence_default)

    def has(*names: str) -> bool:
        return all(f.get(name) is not None for name in names)

    # Intent signals
    for signal_id, field in (("cancel_page_visit", "has_visited_cancellation_page"),
                             ("downgrade_inquiry", "has_downgrade_inquiry"),
                             ("data_export", "has_exported_data"),
                             ("champion_left", "champion_left"),
                             ("integration_removed", "has_removed_integration"),
                             ("competitor_mention", "has_competitor_mention"),
                             ("payment_failed", "has_billing_issues")):
        if has(field):
            evaluated.append(signal_id)
            if f[field]:
                _fire(fired, signal_id, "%s = true" % field)

    # Activity: login decline needs a real baseline; recency scales with cadence.
    last, prev = f.get("login_frequency_last_30d"), f.get("login_frequency_prev_30d")
    if has("login_frequency_last_30d", "login_frequency_prev_30d"):
        if prev >= MIN_LOGIN_BASELINE:
            evaluated.append("login_decline")
            decline = (prev - last) / prev
            if decline > 0.5:
                _fire(fired, "login_decline", "logins %s -> %s in 30 days (%d%% decline)"
                      % (_fmt(prev), _fmt(last), round(decline * 100)))
    days = f.get("last_login_days_ago")
    if days is not None:
        evaluated.extend(["dormant", "idle"])
        if days > 2 * cadence:
            weight = 30 if days > 4 * cadence else 20
            _fire(fired, "dormant", "last login %s days ago; expected cadence %s days"
                  % (_fmt(days), _fmt(cadence)), weight=weight)
        elif days > cadence:
            _fire(fired, "idle", "last login %s days ago; expected cadence %s days" % (_fmt(days), _fmt(cadence)))
    elif last is not None and last == 0 and 2 * cadence < 30:
        evaluated.extend(["dormant", "idle"])
        _fire(fired, "dormant", "0 logins in the last 30 days; expected cadence %s days" % _fmt(cadence))
    elif f.get("active_users_30d") == 0 and 2 * cadence < 30:
        evaluated.extend(["dormant", "idle"])
        _fire(fired, "dormant", "0 active users in the last 30 days; expected cadence %s days" % _fmt(cadence))

    core_days = f.get("core_action_days_ago")
    if core_days is not None:
        evaluated.append("core_feature_disuse")
        limit = max(14.0, 2 * cadence)
        if core_days >= limit:
            _fire(fired, "core_feature_disuse", "core action last used %s days ago (limit %s)"
                  % (_fmt(core_days), _fmt(limit)))

    fl, fp = f.get("features_used_last_30d"), f.get("features_used_prev_30d")
    if fl is not None and fp is not None and fp >= MIN_FEATURE_BASELINE:
        evaluated.append("feature_abandonment")
        drop = (fp - fl) / fp
        if drop >= 0.3:
            _fire(fired, "feature_abandonment", "features used %s -> %s (%d%% fewer)"
                  % (_fmt(fp), _fmt(fl), round(drop * 100)))

    seats, active = f.get("seats"), f.get("active_users_30d")
    if seats is not None and active is not None:
        evaluated.append("single_user")
        if seats >= 2 and active == 1:
            _fire(fired, "single_user", "1 active user on %s seats" % _fmt(seats))

    change = f.get("seat_count_change")
    if change is not None:
        evaluated.append("seat_reduction")
        if change < 0:
            cut = -change
            if seats is not None and seats + cut > 0:
                share = cut / (seats + cut)
                severity = "HIGH" if share >= SEAT_CUT_HIGH_SHARE else "MEDIUM"
                weight = 15 if severity == "HIGH" else 5
                _fire(fired, "seat_reduction", "seats %s -> %s (%d%% cut)"
                      % (_fmt(seats + cut), _fmt(seats), round(share * 100)), severity=severity, weight=weight)
            else:
                _fire(fired, "seat_reduction", "seats reduced by %s; seat base unknown" % _fmt(cut),
                      severity="MEDIUM", weight=10)

    # Engagement and sentiment
    if f.get("onboarding_completed") is not None:
        age = f.get("account_age_days")
        if age is not None:
            evaluated.append("onboarding_incomplete")
            if f["onboarding_completed"] is False and age > 14:
                _fire(fired, "onboarding_incomplete", "onboarding not completed; account is %s days old" % _fmt(age))

    nps, prev_nps = f.get("nps_score"), f.get("prev_nps_score")
    if nps is not None:
        evaluated.extend(["nps_detractor", "nps_passive"])
        if nps <= 6:
            _fire(fired, "nps_detractor", "NPS %s" % _fmt(nps))
        elif nps <= 8:
            _fire(fired, "nps_passive", "NPS %s" % _fmt(nps))
        if prev_nps is not None:
            evaluated.append("nps_drop")
            if prev_nps - nps >= 3:
                _fire(fired, "nps_drop", "NPS %s -> %s" % (_fmt(prev_nps), _fmt(nps)))

    streak = f.get("emails_unopened_streak")
    if streak is not None:
        evaluated.append("email_unresponsive")
        if streak >= 3:
            _fire(fired, "email_unresponsive", "%s emails in a row unopened" % _fmt(streak))

    tickets = f.get("support_tickets_last_90d")
    if tickets is not None and last is not None:
        evaluated.append("silent_low_usage")
        expected = 30.0 / cadence
        if tickets == 0 and last < expected / 2:
            _fire(fired, "silent_low_usage", "0 tickets in 90 days; %s logins in 30 days vs about %s expected"
                  % (_fmt(last), _fmt(round(expected, 1))))

    billing_tickets = f.get("billing_tickets_last_90d")
    if billing_tickets is not None:
        evaluated.append("billing_dispute")
        if billing_tickets >= 2:
            _fire(fired, "billing_dispute", "%s billing tickets in 90 days" % _fmt(billing_tickets))

    # Renewal timing escalates only accounts that already show risk.
    renewal = f.get("contract_renewal_days")
    renewal_info = None
    if renewal is not None:
        window = "overdue" if renewal < 0 else "30d" if renewal <= 30 else "60d" if renewal <= 60 else "later"
        renewal_info = {"days": renewal, "window": window}
        evaluated.append("renewal_at_risk")
        other_risk = any(SEVERITY_RANK[s["severity"]] >= 2 for s in fired)
        if window in ("overdue", "30d") and other_risk:
            text = ("renewal date passed %s days ago" % _fmt(-renewal)) if renewal < 0 else \
                "renewal in %s days" % _fmt(renewal)
            _fire(fired, "renewal_at_risk", text)

    # Effective weights: group caps, applied in order of weight.
    group_used: Counter = Counter()
    for signal in sorted(fired, key=lambda s: -s["weight"]):
        group = signal["group"]
        if group in GROUP_CAPS:
            room = max(0, GROUP_CAPS[group] - group_used[group])
            signal["effective_weight"] = min(signal["weight"], room)
            group_used[group] += signal["effective_weight"]
        else:
            signal["effective_weight"] = signal["weight"]
    fired.sort(key=lambda s: (-SEVERITY_RANK[s["severity"]], -s["effective_weight"]))
    raw = sum(s["effective_weight"] for s in fired)

    # Combination rules: each group counts once, at its highest severity.
    counted: Dict[str, int] = {}
    singles: List[int] = []
    for signal in fired:
        rank = SEVERITY_RANK[signal["severity"]]
        if signal["group"]:
            counted[signal["group"]] = max(counted.get(signal["group"], 0), rank)
        else:
            singles.append(rank)
    ranks = singles + list(counted.values())
    crit, high, med = ranks.count(4), ranks.count(3), ranks.count(2)
    if crit >= 2 or (crit >= 1 and high >= 2):
        tier = "red"
    elif crit >= 1 or high >= 2:
        tier = "orange"
    elif high >= 1 or med >= 3:
        tier = "yellow"
    else:
        tier = "green"

    families = OrderedDict((name, any(f.get(field) is not None for field in fields))
                           for name, fields in FAMILIES.items())
    measured_families = [name for name, ok in families.items() if ok]
    score = min(100, raw)
    if not evaluated and not fired:
        level = "NOT_MEASURED"
    else:
        band = "LOW" if score <= 25 else "MEDIUM" if score <= 50 else "HIGH" if score <= 75 else "CRITICAL"
        floor = TIER_FLOOR[tier]
        level = band if floor is None or LEVELS.index(band) >= LEVELS.index(floor) else floor
        enough = families["activity"] and len(measured_families) >= MIN_FAMILIES_FOR_LOW
        if level == "LOW" and not fired and not enough:
            level = "UNKNOWN"
    return {
        "risk_score": score if level != "NOT_MEASURED" else None,
        "raw_score": raw if level != "NOT_MEASURED" else None,
        "risk_level": level,
        "alert_tier": tier if level not in ("NOT_MEASURED", "UNKNOWN") else None,
        "response_window": RESPONSE_WINDOW[level],
        "signals": fired,
        "evaluated_signals": sorted(set(evaluated)),
        "involuntary_risk": any(s["id"] == "payment_failed" for s in fired),
        "renewal": renewal_info,
        "coverage": {"families_measured": measured_families,
                     "families_missing": [name for name, ok in families.items() if not ok]},
    }


def assess_engagement(f: Dict[str, Any], cadence_default: float, weights: Dict[str, float],
                      key_actions_total: Optional[float], features_total: Optional[float]) -> Dict[str, Any]:
    """Positive-usage score from the components that were measured."""
    cadence = float(f.get("expected_cadence_days") or cadence_default)
    expected_sessions = 30.0 / cadence
    parts: Dict[str, Optional[float]] = OrderedDict((name, None) for name in ENGAGEMENT_WEIGHTS)
    basis: Dict[str, str] = {}
    if f.get("active_days_last_30d") is not None:
        target = min(30.0, expected_sessions)
        parts["frequency"] = min(1.0, f["active_days_last_30d"] / target)
        basis["frequency"] = "active days %s of about %s expected" % (_fmt(f["active_days_last_30d"]),
                                                                     _fmt(round(target, 1)))
    elif f.get("login_frequency_last_30d") is not None:
        parts["frequency"] = min(1.0, f["login_frequency_last_30d"] / expected_sessions)
        basis["frequency"] = "logins %s of about %s expected" % (_fmt(f["login_frequency_last_30d"]),
                                                                _fmt(round(expected_sessions, 1)))
    if f.get("last_login_days_ago") is not None:
        days = f["last_login_days_ago"]
        if days <= cadence:
            value = 1.0
        elif days >= 4 * cadence:
            value = 0.0
        else:
            value = 1.0 - (days - cadence) / (3 * cadence)
        parts["recency"] = value
        basis["recency"] = "last login %s days ago, cadence %s" % (_fmt(days), _fmt(cadence))
    used = f.get("key_actions_used_30d")
    total = f.get("key_actions_total") or key_actions_total
    if used is not None and total:
        parts["breadth"] = min(1.0, used / total)
        basis["breadth"] = "key actions %s of %s" % (_fmt(used), _fmt(total))
    else:
        fused = f.get("features_used_last_30d")
        ftotal = f.get("features_total") or features_total
        if fused is not None and ftotal:
            parts["breadth"] = min(1.0, fused / ftotal)
            basis["breadth"] = "features %s of %s" % (_fmt(fused), _fmt(ftotal))
    seats, active = f.get("seats"), f.get("active_users_30d")
    if seats and active is not None:
        parts["seat_utilization"] = min(1.0, active / seats)
        basis["seat_utilization"] = "%s active users on %s seats" % (_fmt(active), _fmt(seats))
    last, prev = f.get("login_frequency_last_30d"), f.get("login_frequency_prev_30d")
    if last is not None and prev is not None and prev >= MIN_LOGIN_BASELINE:
        parts["trend"] = min(1.0, last / prev)
        basis["trend"] = "logins %s vs %s in the previous 30 days" % (_fmt(last), _fmt(prev))
    total_weight = sum(weights.values()) or 1.0
    measured_weight = sum(weights[name] for name, value in parts.items() if value is not None)
    coverage = measured_weight / total_weight
    components = OrderedDict(
        (name, {"value": None if value is None else round(value, 3), "weight": weights[name],
                "basis": basis.get(name, "not measured")})
        for name, value in parts.items())
    if coverage < ENGAGEMENT_MIN_COVERAGE or measured_weight == 0:
        return {"score": None, "tier": "insufficient_data", "coverage": round(coverage, 2),
                "components": components}
    score = sum(weights[name] * value for name, value in parts.items() if value is not None) / measured_weight * 100
    tier = next(name for name, floor in ENGAGEMENT_TIERS if score >= floor)
    return {"score": round(score, 1), "tier": tier, "coverage": round(coverage, 2), "components": components}


def assess_account(raw: Dict[str, Any], index: int, cadence: float, weights: Dict[str, float],
                   key_actions_total: Optional[float] = None, features_total: Optional[float] = None,
                   overrides: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Coerce one input row and return its risk and engagement facts."""
    if not isinstance(raw, dict):
        return {"account": "row %d" % index, "row": index, "risk_level": "NOT_MEASURED", "risk_score": None,
                "raw_score": None, "alert_tier": None, "signals": [], "engagement": None, "mrr": None,
                "warnings": ["row %d is not an object with named fields" % index], "unused": []}
    coerced = coerce_account(raw, overrides)
    f = coerced["fields"]
    risk = assess_risk(f, cadence)
    engagement = assess_engagement(f, cadence, weights, key_actions_total, features_total)
    mrr = f.get("mrr")
    result: Dict[str, Any] = OrderedDict()
    result["account"] = f.get("account_id") or "row %d" % index
    result["row"] = index
    result["segment"] = f.get("segment")
    result["mrr"] = round(mrr, 2) if mrr is not None else None
    result.update(risk)
    result["mrr_weighted_risk"] = (round(mrr * risk["risk_score"] / 100.0, 2)
                                   if mrr is not None and risk["risk_score"] is not None else None)
    result["engagement"] = engagement
    if f.get("ticket_subjects"):
        result["ticket_subjects"] = f["ticket_subjects"]
    result["churned"] = f.get("churned")
    result["warnings"] = coerced["warnings"]
    result["unused"] = coerced["unused"]
    result["fields_present"] = sorted(f)
    return result


def _sort_key(account: Dict[str, Any]) -> Tuple:
    tier = TIER_ORDER.get(account.get("alert_tier") or "", 0)
    level = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}.get(account.get("risk_level"), 0)
    weighted = account.get("mrr_weighted_risk")
    return (-tier, -level, -(weighted if weighted is not None else -1), -(account.get("raw_score") or 0))


# ---------------------------------------------------------------------------
# Summary and calibration
# ---------------------------------------------------------------------------


def _bucket() -> Dict[str, Any]:
    return {"accounts": 0, "mrr": 0.0, "accounts_with_mrr": 0}


def summarize(accounts: List[Dict[str, Any]], field_counts: Counter) -> Dict[str, Any]:
    by_level: "OrderedDict[str, Dict[str, Any]]" = OrderedDict(
        (name, _bucket()) for name in ("CRITICAL", "HIGH", "MEDIUM", "LOW", "UNKNOWN", "NOT_MEASURED"))
    by_tier: "OrderedDict[str, Dict[str, Any]]" = OrderedDict((name, _bucket()) for name in
                                                               ("red", "orange", "yellow", "green"))
    signals: Dict[str, Dict[str, Any]] = {}
    engagement_tiers: Counter = Counter()
    engagement_scores: List[float] = []
    total_mrr = 0.0
    with_mrr = 0
    involuntary = _bucket()
    for account in accounts:
        mrr = account.get("mrr")
        if mrr is not None:
            total_mrr += mrr
            with_mrr += 1
        targets = [by_level[account["risk_level"]]]
        if account.get("alert_tier"):
            targets.append(by_tier[account["alert_tier"]])
        if account.get("involuntary_risk"):
            targets.append(involuntary)
        for target in targets:
            target["accounts"] += 1
            if mrr is not None:
                target["mrr"] += mrr
                target["accounts_with_mrr"] += 1
        for signal in account.get("signals", []):
            entry = signals.setdefault(signal["id"], {"id": signal["id"], "label": SIGNALS[signal["id"]]["label"],
                                                      "severity": SIGNALS[signal["id"]]["severity"],
                                                      "accounts": 0, "mrr": 0.0})
            entry["accounts"] += 1
            if mrr is not None:
                entry["mrr"] += mrr
        engagement = account.get("engagement") or {}
        engagement_tiers[engagement.get("tier") or "insufficient_data"] += 1
        if engagement.get("score") is not None:
            engagement_scores.append(engagement["score"])
    n = len(accounts)
    for block in list(by_level.values()) + list(by_tier.values()) + [involuntary]:
        block["mrr"] = round(block["mrr"], 2)
        block["share_of_accounts"] = round(block["accounts"] / n, 4) if n else None
        block["share_of_mrr"] = round(block["mrr"] / total_mrr, 4) if total_mrr else None
    signal_rows = sorted(signals.values(), key=lambda s: (-s["accounts"], -s["mrr"]))
    for row in signal_rows:
        row["mrr"] = round(row["mrr"], 2)
        row["share_of_accounts"] = round(row["accounts"] / n, 4) if n else None
    at_risk_mrr = by_tier["red"]["mrr"] + by_tier["orange"]["mrr"]
    engagement_scores.sort()
    median = None
    if engagement_scores:
        mid = len(engagement_scores) // 2
        median = engagement_scores[mid] if len(engagement_scores) % 2 else \
            round((engagement_scores[mid - 1] + engagement_scores[mid]) / 2.0, 1)
    return {
        "accounts": n,
        "scored": n - by_level["NOT_MEASURED"]["accounts"] - by_level["UNKNOWN"]["accounts"],
        "unknown": by_level["UNKNOWN"]["accounts"],
        "not_measured": by_level["NOT_MEASURED"]["accounts"],
        "accounts_with_mrr": with_mrr,
        "total_mrr": round(total_mrr, 2) if with_mrr else None,
        "mrr_at_risk": {
            "red_orange_mrr": round(at_risk_mrr, 2) if with_mrr else None,
            "share_of_mrr": round(at_risk_mrr / total_mrr, 4) if total_mrr else None,
            "basis": "MRR of accounts in the red or orange alert tier (accounts without MRR are not counted)",
        },
        "involuntary_risk": involuntary,
        "by_risk_level": by_level,
        "by_alert_tier": by_tier,
        "signals": signal_rows,
        "engagement": {"by_tier": dict(engagement_tiers), "median_score": median,
                       "scored_accounts": len(engagement_scores)},
        "field_coverage": OrderedDict((name, field_counts.get(name, 0)) for name, _, _ in FIELD_SPECS
                                      if field_counts.get(name, 0)),
        "fields_missing_everywhere": [name for name in SIGNAL_INPUT_FIELDS if not field_counts.get(name)],
    }


def _auc(scores_pos: List[float], scores_neg: List[float]) -> Optional[float]:
    """Mann-Whitney AUC: chance that a churned account scores higher (ties count half)."""
    if not scores_pos or not scores_neg:
        return None
    combined = sorted([(s, 1) for s in scores_pos] + [(s, 0) for s in scores_neg])
    rank_sum = 0.0
    index = 0
    while index < len(combined):
        end = index
        while end + 1 < len(combined) and combined[end + 1][0] == combined[index][0]:
            end += 1
        average_rank = (index + end) / 2.0 + 1
        rank_sum += average_rank * sum(1 for k in range(index, end + 1) if combined[k][1] == 1)
        index = end + 1
    n_pos, n_neg = len(scores_pos), len(scores_neg)
    return round((rank_sum - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg), 3)


def _rate_block(churned: int, n: int) -> Dict[str, Any]:
    if not n:
        return {"accounts": 0, "churned": 0, "churn_rate": None, "ci95": None}
    low, high = stats.wilson_interval(churned, n)
    return {"accounts": n, "churned": churned, "churn_rate": round(churned / n, 4),
            "ci95": [round(low, 4), round(high, 4)]}


def calibrate(accounts: List[Dict[str, Any]]) -> Dict[str, Any]:
    labelled = [a for a in accounts if a.get("churned") is not None and a["risk_level"] != "NOT_MEASURED"]
    churned = [a for a in labelled if a["churned"]]
    kept = [a for a in labelled if not a["churned"]]
    notes = [
        "Signals must be measured before the churn date. A signal recorded at or after cancellation (for "
        "example the cancel-page visit that ends in cancellation) inflates its lift and the AUC.",
        "Lift compares churn among accounts where the signal fired with accounts where it was evaluated and "
        "did not fire. Treat signals with fewer than 10 fired accounts as unknown.",
    ]
    if len(labelled) < 20 or len(churned) < 5 or len(kept) < 5:
        return {"status": "insufficient_labels", "labelled_accounts": len(labelled), "churned": len(churned),
                "retained": len(kept),
                "message": "Calibration needs at least 20 labelled accounts with 5 churned and 5 retained.",
                "notes": notes}
    base = _rate_block(len(churned), len(labelled))
    rows = []
    for signal_id in SIGNALS:
        evaluated = [a for a in labelled if signal_id in a.get("evaluated_signals", [])]
        if not evaluated:
            continue
        with_signal = [a for a in evaluated if any(s["id"] == signal_id for s in a["signals"])]
        fired_ids = {id(a) for a in with_signal}
        without = [a for a in evaluated if id(a) not in fired_ids]
        fired = _rate_block(sum(1 for a in with_signal if a["churned"]), len(with_signal))
        not_fired = _rate_block(sum(1 for a in without if a["churned"]), len(without))
        lift = None
        if fired["churn_rate"] is not None and not_fired["churn_rate"]:
            lift = round(fired["churn_rate"] / not_fired["churn_rate"], 2)
        if fired["accounts"] < 10:
            verdict = "too_few_fired"
        elif not_fired["churn_rate"] is not None and fired["ci95"][0] > not_fired["churn_rate"]:
            verdict = "higher_churn_when_fired"
        elif not_fired["churn_rate"] is not None and fired["ci95"][1] < not_fired["churn_rate"]:
            verdict = "lower_churn_when_fired"
        else:
            verdict = "no_clear_difference"
        rows.append({"id": signal_id, "severity": SIGNALS[signal_id]["severity"],
                     "weight": SIGNALS[signal_id]["weight"], "fired": fired, "not_fired": not_fired,
                     "lift": lift, "verdict": verdict})
    rows.sort(key=lambda r: (-(r["lift"] or 0), -r["fired"]["accounts"]))
    by_tier = OrderedDict()
    for tier in ("red", "orange", "yellow", "green"):
        members = [a for a in labelled if a.get("alert_tier") == tier]
        by_tier[tier] = _rate_block(sum(1 for a in members if a["churned"]), len(members))
    unknown = [a for a in labelled if a["risk_level"] == "UNKNOWN"]
    by_tier["unknown"] = _rate_block(sum(1 for a in unknown if a["churned"]), len(unknown))
    scored = [a for a in labelled if a.get("raw_score") is not None]
    auc_risk = _auc([a["raw_score"] for a in scored if a["churned"]],
                    [a["raw_score"] for a in scored if not a["churned"]])
    eng = [a for a in labelled if (a.get("engagement") or {}).get("score") is not None]
    auc_engagement = _auc([100 - a["engagement"]["score"] for a in eng if a["churned"]],
                          [100 - a["engagement"]["score"] for a in eng if not a["churned"]])
    return {
        "status": "ok",
        "labelled_accounts": len(labelled),
        "base_churn": base,
        "auc_raw_risk_score": auc_risk,
        "auc_low_engagement": auc_engagement,
        "auc_note": "0.5 = no better than chance, 1.0 = perfect ranking; computed on labelled accounts that "
                    "have a score",
        "churn_by_alert_tier": by_tier,
        "signals": rows,
        "notes": notes,
    }


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------

DEMO_ACCOUNTS = [
    {"account_id": "demo-001", "mrr": 1200, "login_frequency_last_30d": 14, "login_frequency_prev_30d": 15,
     "last_login_days_ago": 2, "has_exported_data": True, "has_downgrade_inquiry": True, "nps_score": 8,
     "has_billing_issues": False, "seats": 12, "active_users_30d": 9, "contract_renewal_days": 40},
    {"account_id": "demo-002", "mrr": 300, "login_frequency_last_30d": 22, "login_frequency_prev_30d": 20,
     "last_login_days_ago": 1, "has_billing_issues": True, "nps_score": 9, "has_exported_data": False,
     "has_visited_cancellation_page": False, "seats": 3, "active_users_30d": 3},
    {"account_id": "demo-003", "mrr": 450, "login_frequency_last_30d": 0, "login_frequency_prev_30d": 0,
     "last_login_days_ago": 60, "has_billing_issues": False, "seats": 5, "active_users_30d": 0,
     "has_exported_data": False},
    {"account_id": "demo-004", "mrr": 2400, "login_frequency_last_30d": 3, "login_frequency_prev_30d": 21,
     "last_login_days_ago": 12, "seat_count_change": -4, "seats": 16, "active_users_30d": 6, "nps_score": 5,
     "prev_nps_score": 8, "has_billing_issues": False, "contract_renewal_days": 25},
    {"account_id": "demo-005", "mrr": 800, "login_frequency_last_30d": 26, "login_frequency_prev_30d": 24,
     "last_login_days_ago": 0, "key_actions_used_30d": 4, "key_actions_total": 5, "seats": 10,
     "active_users_30d": 9, "nps_score": 10, "has_billing_issues": False, "has_exported_data": False,
     "has_visited_cancellation_page": False, "has_downgrade_inquiry": False},
    {"account_id": "demo-006"},
]


def _parse_weights(text: Optional[str]) -> Dict[str, float]:
    weights = OrderedDict(ENGAGEMENT_WEIGHTS)
    if not text:
        return weights
    for part in text.split(","):
        if not part.strip():
            continue
        if "=" not in part:
            raise cli.UsageError("--engagement-weights expects name=number pairs, got %r" % part)
        name, value = (item.strip() for item in part.split("=", 1))
        if name not in weights:
            raise cli.UsageError("--engagement-weights: unknown component %r (use %s)"
                                 % (name, ", ".join(ENGAGEMENT_WEIGHTS)))
        number = cli.to_number(value, name, minimum=0)
        weights[name] = float(number or 0)
    if sum(weights.values()) <= 0:
        raise cli.UsageError("--engagement-weights must not all be 0")
    return weights


def _parse_map(items: Optional[List[str]]) -> Dict[str, str]:
    overrides: Dict[str, str] = {}
    known = {name for name, _, _ in FIELD_SPECS}
    for item in items or []:
        if "=" not in item:
            raise cli.UsageError("--map expects FIELD=COLUMN, got %r" % item)
        field, column = (part.strip() for part in item.split("=", 1))
        if field not in known:
            raise cli.UsageError("--map: unknown field %r. Fields: %s" % (field, ", ".join(sorted(known))))
        overrides[field] = column
    return overrides


def _public_account(account: Dict[str, Any]) -> Dict[str, Any]:
    out = OrderedDict((key, value) for key, value in account.items()
                      if key not in ("unused", "evaluated_signals", "row", "fields_present"))
    out["signals"] = [{key: s[key] for key in ("id", "severity", "effective_weight", "evidence")}
                      for s in account.get("signals", [])]
    if not out.get("warnings"):
        out.pop("warnings", None)
    if out.get("churned") is None:
        out.pop("churned", None)
    if not out.get("segment"):
        out.pop("segment", None)
    return out


def write_accounts_csv(path: str, accounts: List[Dict[str, Any]]) -> None:
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    columns = ["rank", "account", "segment", "mrr", "risk_level", "alert_tier", "risk_score", "raw_score",
               "mrr_weighted_risk", "response_window", "signals", "engagement_score", "engagement_tier",
               "engagement_coverage", "renewal_days"]
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(columns)
        for rank, account in enumerate(accounts, 1):
            engagement = account.get("engagement") or {}
            renewal = account.get("renewal") or {}
            writer.writerow([
                rank, account["account"], account.get("segment") or "", account.get("mrr"),
                account["risk_level"], account.get("alert_tier") or "", account.get("risk_score"),
                account.get("raw_score"), account.get("mrr_weighted_risk"), account.get("response_window"),
                ";".join(s["id"] for s in account.get("signals", [])), engagement.get("score"),
                engagement.get("tier"), engagement.get("coverage"), renewal.get("days"),
            ])


def _human(envelope: Dict[str, Any]) -> str:
    lines = []
    summary = envelope.get("summary") or {}
    if summary:
        lines.append("Accounts: %d (scored %d, unknown %d, no data %d)" % (
            summary["accounts"], summary["scored"], summary["unknown"], summary["not_measured"]))
        for tier, block in summary["by_alert_tier"].items():
            lines.append("  %-7s %4d accounts  MRR %s" % (tier, block["accounts"], block["mrr"]))
        risk = summary["mrr_at_risk"]
        if risk["red_orange_mrr"] is not None:
            lines.append("MRR at risk (red + orange): %s (%s of MRR)" % (
                risk["red_orange_mrr"], "%.1f%%" % (risk["share_of_mrr"] * 100) if risk["share_of_mrr"] else "-"))
        if summary["signals"]:
            lines.append("Top signals: " + ", ".join("%s (%d)" % (s["id"], s["accounts"])
                                                     for s in summary["signals"][:6]))
    for account in envelope.get("top_accounts", []):
        signals = ", ".join(s["id"] for s in account["signals"]) or "none"
        engagement = account.get("engagement") or {}
        lines.append("- %s: %s / %s (raw %s) signals: %s | engagement %s (%s)" % (
            account["account"], account["risk_level"], account.get("alert_tier") or "-", account.get("raw_score"),
            signals, engagement.get("score"), engagement.get("tier")))
    calibration = envelope.get("calibration")
    if calibration and calibration.get("status") == "ok":
        lines.append("Calibration: AUC %s on %d labelled accounts" % (calibration["auc_raw_risk_score"],
                                                                     calibration["labelled_accounts"]))
    for note in envelope.get("notes", []):
        lines.append("Note: " + note)
    lines.append("Use --json for the full result.")
    return "\n".join(lines)


def build_parser() -> cli.ArgumentParser:
    parser = cli.build_parser(
        "Score churn risk signals and engagement for SaaS accounts (one row per account) and summarize "
        "accounts and MRR at risk.",
        input_help="accounts file (.csv, .tsv, .json, .jsonl) or '-' for stdin",
        prog="churn_risk_scorer.py", timeout=False,
    )
    parser.add_argument("--top", type=int, default=DEFAULT_TOP,
                        help="accounts to list, highest priority first (default %d; 0 for none)" % DEFAULT_TOP)
    parser.add_argument("--summary", action="store_true", help="summary only (same as --top 0)")
    parser.add_argument("--cadence-days", type=float, default=DEFAULT_CADENCE_DAYS,
                        help="expected days between uses for a healthy account (default 7 = weekly)")
    parser.add_argument("--key-actions-total", type=float,
                        help="number of key value actions you defined (breadth denominator)")
    parser.add_argument("--features-total", type=float,
                        help="number of trackable features (breadth denominator when key actions are absent)")
    parser.add_argument("--engagement-weights", metavar="NAME=W,...",
                        help="override engagement weights: frequency, recency, breadth, seat_utilization, trend")
    parser.add_argument("--map", action="append", metavar="FIELD=COLUMN",
                        help="map one of your column names to a field, for example last_login_days_ago=inactive_days")
    parser.add_argument("--calibrate", action="store_true",
                        help="with a churned column: per-signal churn lift, churn by tier and AUC")
    parser.add_argument("--accounts-out", metavar="PATH",
                        help="write every account, ranked, to this CSV (stays on your machine)")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    run = cli.Run(TOOL, args)
    try:
        if args.cadence_days <= 0:
            raise cli.UsageError("--cadence-days must be greater than 0")
        if args.top < 0:
            raise cli.UsageError("--top must be 0 or more")
        weights = _parse_weights(args.engagement_weights)
        overrides = _parse_map(args.map)
        if args.demo:
            rows, info = [dict(row) for row in DEMO_ACCOUNTS], {"source": "demo", "format": "json",
                                                                  "pii_columns_ignored": []}
        else:
            rows, info = load_rows(args.input)
    except (cli.UsageError, cli.CoercionError) as exc:
        return run.fail(cli.STATUS_USAGE, str(exc))
    if not rows:
        return run.fail(cli.STATUS_NOTHING, "The input has no account rows.")
    dict_rows = [row for row in rows if isinstance(row, dict)]
    if dict_rows and all(_looks_aggregate(row) for row in dict_rows):
        return run.fail(cli.STATUS_USAGE,
                        "This looks like company-level metrics (churn rate, NRR, GRR), not one row per account. "
                        "The scorer needs account-level data; check aggregate metrics with "
                        "retention_facts.py check instead.")
    accounts = [assess_account(row, index, args.cadence_days, weights, args.key_actions_total,
                               args.features_total, overrides)
                for index, row in enumerate(rows, 1)]
    field_counts: Counter = Counter()
    unused: Counter = Counter()
    rows_with_warnings = 0
    warning_fields: Counter = Counter()
    for account in accounts:
        field_counts.update(account.get("fields_present", []))
        unused.update(account.get("unused", []))
        if account.get("warnings"):
            rows_with_warnings += 1
            warning_fields.update(w.split(":", 1)[0] for w in account["warnings"])
    if not any(field_counts.get(name) for name in SIGNAL_INPUT_FIELDS):
        return run.fail(cli.STATUS_NOTHING,
                        "No row has a recognized risk or usage field (logins, last login, NPS, billing issue, "
                        "seats, cancel-page visit...). Rename the columns, pass --map FIELD=COLUMN, or see "
                        "references/health-score.md for the field list. A customer table with only a churn flag "
                        "and plan or contract columns fits retention_facts.py segments instead.",
                        {"columns_found": [key for key, _ in unused.most_common(40)]})
    accounts.sort(key=_sort_key)
    summary = summarize(accounts, field_counts)
    status = cli.STATUS_OK
    if rows_with_warnings:
        detail = ", ".join("%s (%d)" % item for item in warning_fields.most_common(8))
        message = "%d of %d rows had values that could not be read and were treated as missing: %s." % (
            rows_with_warnings, len(rows), detail)
        if rows_with_warnings / float(len(rows)) > PARTIAL_ROW_SHARE:
            run.error(message)
            status = cli.STATUS_PARTIAL
        else:
            run.note(message)
    if unused:
        run.note("Columns not used (rename or --map them if they hold a signal): %s"
                 % ", ".join(key for key, _ in unused.most_common(25)))
    if info.get("pii_columns_ignored"):
        run.note("Personal-data columns were not read: %s" % ", ".join(info["pii_columns_ignored"]))
    if summary["unknown"]:
        run.note("%d account(s) are UNKNOWN: no signal fired but too little data to call them low risk "
                 "(needs usage activity plus two other signal families)." % summary["unknown"])
    if summary["accounts_with_mrr"] < summary["accounts"]:
        run.note("MRR is missing for %d account(s); they are ranked by risk only and left out of MRR totals."
                 % (summary["accounts"] - summary["accounts_with_mrr"]))
    top_n = 0 if args.summary else args.top
    data: Dict[str, Any] = OrderedDict()
    data["scorer_version"] = SCORER_VERSION
    data["input"] = info
    data["settings"] = {"cadence_days": args.cadence_days, "engagement_weights": weights,
                        "engagement_min_coverage": ENGAGEMENT_MIN_COVERAGE,
                        "key_actions_total": args.key_actions_total, "features_total": args.features_total}
    data["summary"] = summary
    data["top_accounts"] = [_public_account(a) for a in accounts[:top_n]]
    if args.calibrate:
        data["calibration"] = calibrate(accounts)
        if data["calibration"]["status"] != "ok":
            run.note(data["calibration"]["message"])
    if args.accounts_out:
        try:
            write_accounts_csv(args.accounts_out, accounts)
            data["accounts_file"] = args.accounts_out
            run.note("Ranked account list written to %s (keep it local; reports show aggregates only)."
                     % args.accounts_out)
        except OSError as exc:
            run.error("Could not write --accounts-out %s: %s" % (args.accounts_out, exc))
            status = cli.STATUS_PARTIAL
    return run.emit(data, status=status, human=_human)


if __name__ == "__main__":
    sys.exit(main())
