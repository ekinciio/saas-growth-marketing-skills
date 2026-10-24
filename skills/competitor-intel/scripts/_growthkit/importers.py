"""Read downloaded billing and analytics exports and turn them into aggregates.

Skills never ask users to type MRR, churn or funnel numbers by hand when an
export exists: hand-typed numbers mix monthly and annual periods, cents and
dollars, and currencies. This module reads the file the user downloaded,
detects its format from the header row, normalizes it, and returns
aggregates only. Customer data stays on the user's machine and no personal
data (emails, names, addresses) is ever read into the output: customer ids
are kept only as salted hashes inside the process and leave it as counts.
A table with contact columns (email, phone, name, address) is a list of
people and is never read as a funnel or cohort table, and any email address
left in text taken from the file (a breakdown segment, a step or plan name)
is replaced by a salted tag before the result is returned.

    from _growthkit import importers
    result = importers.analyze("subscriptions.csv")          # detect + summarize
    result["format"]["source"]                              # "stripe_subscriptions"
    result["billing"]["by_currency"]["USD"]["current"]["mrr"]

From a SKILL.md (one Bash call, run from the user's project folder):

    python3 "${CLAUDE_SKILL_DIR}/scripts/_growthkit/importers.py" "exports/subscriptions.csv" --json
    python3 "${CLAUDE_SKILL_DIR}/scripts/_growthkit/importers.py" "exports/events.csv" --json \\
        --step "signed_up" --step "created_project"
    python3 "${CLAUDE_SKILL_DIR}/scripts/_growthkit/importers.py" --list-formats --json

Exit codes follow cli.py: 0 ok, 2 usage or unknown format (the JSON lists
the headers found and the supported formats), 4 partial (more than 5 % of
rows unreadable), 5 nothing to analyze (no usable rows).

Kinds and what each returns
---------------------------
billing    MRR now and per month (bridge: new, expansion, contraction,
           churned, reactivation), logo and MRR churn rates, trailing
           12-month cohort GRR and NRR, monthly signup cohorts, voluntary vs
           involuntary churn, plan and billing-interval mix. Every amount is
           per currency (never summed across currencies), in major units
           (dollars, not cents), as monthly recurring revenue.
           churn_observable is false when a subscriptions snapshot has no
           canceled or ended rows (an active-only export cannot show churn).
invoices   billings per month, invoice status counts, payment failure and
           recovery rates (billings are not MRR; use a subscriptions or MRR
           export for MRR).
funnel     ordered steps with counts, step and overall conversion, drop-off,
           time to convert when the export has it; per breakdown segment.
retention  cohort grid: cohort size, retention per period, and the
           size-weighted average curve.
search     Google Search Console performance rows (query, page, country,
           device, search appearance or date) with clicks, impressions,
           CTR and position, plus totals.
events     a raw event log (one row per event): event and user counts, the
           most frequent event names, weekly (or daily) cohort retention by
           each user's first event, and with --step A --step B ... an ordered
           funnel with step conversion and median time to convert (time to
           activation). User ids are hashed; nothing per user is returned.

Supported formats (column names checked against vendor docs on 2026-10-24)
--------------------------------------------------------------------------
Documented by the vendor (detection confidence "high"):
  chartmogul_mrr_movements   ChartMogul "All MRR Movements" export (and the
                             MRR movements destination dataset).
  chartmogul_customer_mrr    ChartMogul "MRR per Customer per Month" exports.
  chartmogul_cohorts         ChartMogul cohort analysis CSV (kind retention).
  stripe_mrr_events          Stripe Sigma / Data Pipeline
                             subscription_item_change_events (CSV of a query).
  paddle_subscriptions       Paddle Billing subscriptions report.
Field names documented, export header labels not published (confidence
"medium"; the column map in the output says which column was used):
  stripe_subscriptions       Stripe Dashboard subscriptions export.
  stripe_invoices            Stripe Dashboard invoices export.
  chargebee_subscriptions    Chargebee subscriptions export (plain or
                             import-friendly subscription[...] headers).
Read by table shape, because no published CSV layout was found (checked
2026-10-24; the output's column_map shows which columns were used):
  funnel_steps / funnel_wide GA4 funnel exploration, PostHog, Mixpanel and
                             Amplitude funnel exports, or any step table.
  retention_grid             PostHog, Amplitude, Mixpanel, GA4 cohort
                             exports or any cohort table.
  gsc_performance            Google Search Console Performance export
                             (Queries.csv, Pages.csv, ... or the zip).
  customer_mrr_wide          any customer x month MRR table (for example the
                             Baremetrics MRR Per Customer report).
  event_log                  a raw event log: PostHog (event, distinct_id,
                             timestamp), Mixpanel (event, distinct_id, time
                             in unix seconds), Amplitude (event_type,
                             user_id, event_time), GA4 BigQuery export
                             (event_name, user_pseudo_id, event_timestamp in
                             microseconds). Field names are documented by
                             each vendor; CSV header rows are not.
  generic_subscriptions,     the documented fallback schemas below, for any
  generic_movements          other billing system.

Baremetrics documents its exports (help.baremetrics.com, "Data exports") but
not their columns, so only its customer x month MRR report is read, by shape.
Excel files are not read: save the sheet as CSV first.

Generic schemas (any column order, header case and spacing ignored)
-------------------------------------------------------------------
generic_subscriptions: customer_id, start_date, and either mrr or amount +
    interval (day|week|month|year) [+ interval_count] [+ quantity]; optional
    status, end_date (or canceled_at / churn_date), plan, currency,
    cancel_reason.
generic_movements: date, customer_id, type (new|expansion|contraction|
    churn|reactivation), mrr_change (signed); optional currency.

Conventions
-----------
Rates are fractions (0.031 = 3.1 %), like stats.py. Months are "YYYY-MM".
MRR at month M means MRR at the end of month M. Movement and churn amounts
are positive magnitudes; net_new_mrr is signed. Amounts in minor units
(cents) are converted with the currency's exponent: zero-decimal and
three-decimal currencies follow Stripe's currency list, where ISK and UGX are
still written with two decimals (https://docs.stripe.com/currencies).

Sources (checked 2026-10-24):
  ChartMogul exports and their columns: https://help.chartmogul.com/hc/en-us/articles/203359211
  ChartMogul MRR movements dataset (amounts in cents, movement types):
      https://dev.chartmogul.com/docs/destinations/calculated-data/mrr-movements/
  Stripe subscription_item_change_events (mrr_change in minor units, event
      types): https://docs.stripe.com/stripe-data/query-billing-data
  Stripe subscription statuses: https://docs.stripe.com/billing/subscriptions/overview
  Stripe Dashboard invoice export (columns follow "Edit columns"):
      https://docs.stripe.com/invoicing/dashboard/manage-invoices
  Paddle Billing subscriptions report columns:
      https://developer.paddle.com/build/reports/subscriptions
  Chargebee Subscription object (status values, mrr in cents, cancel_reason
      values): https://apidocs.chargebee.com/docs/api/subscriptions
  Chargebee import-friendly CSV headers (subscription[plan_id] style):
      https://www.chargebee.com/docs/billing/2.0/data-operations/bulk-operations
  Baremetrics exports: https://help.baremetrics.com/en/articles/12543014-data-exports
  GA4 funnel report fields (active users, completion rate, abandonments):
      https://developers.google.com/analytics/devguides/reporting/data/v1/funnels
  PostHog retention table (cohort, size, "Day 0" columns):
      https://posthog.com/docs/product-analytics/retention
  PostHog funnels (overall vs relative conversion):
      https://posthog.com/docs/product-analytics/funnels
  Mixpanel report CSV export: https://docs.mixpanel.com/docs/export-methods
  Search Console Performance report (dimensions, CTR, position, "~" and "-"
      exported as 0): https://support.google.com/webmasters/answer/7576553
  PostHog event fields (event, distinct_id, timestamp):
      https://posthog.com/docs/how-posthog-works/data-model
  Mixpanel raw export (event, properties.time): https://docs.mixpanel.com/docs/export-methods
  Amplitude export fields (event_type, user_id, event_time ISO 8601):
      https://amplitude.com/docs/apis/analytics/export
  GA4 BigQuery export (event_timestamp in microseconds, user_pseudo_id):
      https://support.google.com/analytics/answer/7029846
"""

from __future__ import annotations

import os
import sys

if __name__ == "__main__" and not __package__:
    # Run as a file (python3 .../_growthkit/importers.py). Drop this folder
    # from sys.path, because its http.py and html.py would shadow the
    # standard library modules of the same name, then import it as a package
    # so the relative imports below work.
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path[:] = [p for p in sys.path if os.path.abspath(p or os.curdir) != _here]
    sys.path.insert(0, os.path.dirname(_here))
    __package__ = os.path.basename(_here)
    __import__(__package__)

import calendar  # noqa: E402
import csv  # noqa: E402
import hashlib  # noqa: E402
import io  # noqa: E402
import math  # noqa: E402
import re  # noqa: E402
import zipfile  # noqa: E402
from collections import Counter, OrderedDict, defaultdict  # noqa: E402
from datetime import date, datetime, timedelta, timezone  # noqa: E402
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple  # noqa: E402

from . import __version__  # noqa: E402
from . import cli  # noqa: E402

VERIFIED_ON = "2026-10-24"

DOCS = {
    "chartmogul_exports": "https://help.chartmogul.com/hc/en-us/articles/203359211",
    "chartmogul_movements_dataset": "https://dev.chartmogul.com/docs/destinations/calculated-data/mrr-movements/",
    "stripe_sigma_billing": "https://docs.stripe.com/stripe-data/query-billing-data",
    "stripe_subscription_statuses": "https://docs.stripe.com/billing/subscriptions/overview",
    "stripe_invoice_export": "https://docs.stripe.com/invoicing/dashboard/manage-invoices",
    "stripe_currencies": "https://docs.stripe.com/currencies",
    "paddle_subscriptions_report": "https://developer.paddle.com/build/reports/subscriptions",
    "chargebee_subscription_object": "https://apidocs.chargebee.com/docs/api/subscriptions",
    "chargebee_bulk_operations": "https://www.chargebee.com/docs/billing/2.0/data-operations/bulk-operations",
    "baremetrics_exports": "https://help.baremetrics.com/en/articles/12543014-data-exports",
    "ga4_funnels": "https://developers.google.com/analytics/devguides/reporting/data/v1/funnels",
    "posthog_retention": "https://posthog.com/docs/product-analytics/retention",
    "posthog_funnels": "https://posthog.com/docs/product-analytics/funnels",
    "mixpanel_export": "https://docs.mixpanel.com/docs/export-methods",
    "gsc_performance": "https://support.google.com/webmasters/answer/7576553",
    "posthog_data_model": "https://posthog.com/docs/how-posthog-works/data-model",
    "amplitude_export": "https://amplitude.com/docs/apis/analytics/export",
    "ga4_bigquery_schema": "https://support.google.com/analytics/answer/7029846",
}

KINDS = ("billing", "invoices", "funnel", "retention", "search", "events")

MAX_FILE_BYTES = 256 * 1024 * 1024
UNREADABLE_PARTIAL_SHARE = 0.05
DEFAULT_MONTHS = 12
MAX_MONTHS = 36
DEFAULT_TOP = 200

# ---------------------------------------------------------------------------
# Currencies (Stripe's list; ISK and UGX keep two decimals there)
# ---------------------------------------------------------------------------

ZERO_DECIMAL = frozenset({
    "BIF", "CLP", "DJF", "GNF", "JPY", "KMF", "KRW", "MGA", "PYG", "RWF",
    "VND", "VUV", "XAF", "XOF", "XPF",
})
THREE_DECIMAL = frozenset({"BHD", "JOD", "KWD", "OMR", "TND"})
# Currency codes stripped from amounts such as "12 USD". Only real codes, so
# that words like "Day" in "Day 0" are never read as a currency.
_CURRENCY_CODES = frozenset({
    "AED", "ARS", "AUD", "BGN", "BRL", "CAD", "CHF", "CLP", "CNY", "COP", "CZK", "DKK", "EGP", "EUR",
    "GBP", "HKD", "HUF", "IDR", "ILS", "INR", "ISK", "JPY", "KRW", "MXN", "MYR", "NGN", "NOK", "NZD",
    "PEN", "PHP", "PKR", "PLN", "RON", "RUB", "SAR", "SEK", "SGD", "THB", "TRY", "TWD", "UAH", "USD",
    "VND", "ZAR",
}) | ZERO_DECIMAL | THREE_DECIMAL
_CURRENCY_SYMBOLS = {
    "$": "USD", "\u20ac": "EUR", "\u00a3": "GBP", "\u00a5": "JPY", "\u20ba": "TRY",
    "\u20b9": "INR", "\u20a9": "KRW", "\u20bd": "RUB",
}


def currency_exponent(code: Optional[str]) -> int:
    """Digits after the decimal point in a minor-unit amount (2 for USD, 0 for JPY)."""
    code = (code or "").upper()
    if code in ZERO_DECIMAL:
        return 0
    if code in THREE_DECIMAL:
        return 3
    return 2


def from_minor(amount: Optional[float], currency: Optional[str]) -> Optional[float]:
    """Convert an amount in minor units (cents) to major units (dollars)."""
    if amount is None:
        return None
    return amount / (10 ** currency_exponent(currency))


def normalize_currency(value: Any) -> Optional[str]:
    """'usd', 'USD', '$' -> 'USD'. Unknown text -> None."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text in _CURRENCY_SYMBOLS:
        return _CURRENCY_SYMBOLS[text]
    if re.fullmatch(r"[A-Za-z]{3}", text):
        return text.upper()
    return None


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ImportFormatError(ValueError):
    """The file cannot be read as any supported export. Exit code 2."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.details = details or {}


class ImportOptionError(ImportFormatError):
    """A bad option value (for example --as-of). Exit code 2, no format hints."""


class NothingToImport(ValueError):
    """The format was recognized but no row is usable. Exit code 5."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.details = details or {}


# ---------------------------------------------------------------------------
# Value parsing
# ---------------------------------------------------------------------------

MISSING_TEXT = frozenset({
    "", "-", "--", "~", "n/a", "na", "null", "none", "nan", "(not set)", "not set", "undefined",
})
TOTAL_LABELS = frozenset({
    "total", "totals", "grand total", "average", "avg", "mean", "weighted average", "overall",
    "all", "all users", "all cohorts", "sum", "$overall",
})


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    return isinstance(value, str) and value.strip().lower() in MISSING_TEXT


def parse_number(value: Any, decimal_comma: bool = False) -> Optional[float]:
    """Read '1,234.50', '1.234,50', '$49.00', '(12.00)', '45%' (-> 45.0), '12 USD'.

    Returns None for blanks and placeholders ('-', '~', 'n/a'). The percent
    sign is dropped; parse_rate() is the percent-aware reader.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number if math.isfinite(number) else None
    if _is_missing(value):
        return None
    text = str(value).strip().replace("\u2212", "-")
    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative = True
        text = text[1:-1].strip()
    text = text.replace("%", "")
    text = re.sub(r"\b[A-Za-z]{3}\b", lambda m: "" if m.group(0).upper() in _CURRENCY_CODES else m.group(0),
                  text)                                  # "12 USD", "eur 9"
    for symbol in _CURRENCY_SYMBOLS:
        text = text.replace(symbol, "")
    text = re.sub(r"[\s\u00a0\u202f'_]", "", text)
    if text.startswith(("-", "+")):
        negative = negative != text.startswith("-")
        text = text[1:]
    if not text:
        return None
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        if not decimal_comma and re.fullmatch(r"\d{1,3}(?:,\d{3})+", text):
            text = text.replace(",", "")
        elif text.count(",") == 1:
            text = text.replace(",", ".")
        else:
            return None
    elif decimal_comma and re.fullmatch(r"\d{1,3}(?:\.\d{3})+", text):
        text = text.replace(".", "")
    if not re.fullmatch(r"\d+(?:\.\d+)?|\.\d+", text):
        return None
    number = float(text)
    if not math.isfinite(number):
        return None
    return -number if negative else number


def parse_rate(value: Any, decimal_comma: bool = False) -> Optional[float]:
    """'45%' -> 0.45, '0.45' -> 0.45. A bare number above 1 is read as percent."""
    number = parse_number(value, decimal_comma)
    if number is None:
        return None
    if "%" in str(value) or abs(number) > 1.0:
        return number / 100.0
    return number


_MONTHS = {name.lower(): index for index, name in enumerate(calendar.month_name) if name}
_MONTHS.update({name.lower(): index for index, name in enumerate(calendar.month_abbr) if name})
_MONTHS["sept"] = 9


def _safe_date(year: int, month: int, day: int) -> Optional[date]:
    try:
        if year < 100:
            year += 2000
        return date(year, month, day)
    except ValueError:
        return None


def parse_date(value: Any, order: Optional[str] = None) -> Optional[date]:
    """Read ISO dates and datetimes, unix seconds, YYYYMMDD, 'Mar 2024', '15/03/2024'.

    order is 'dmy' or 'mdy' for slashed dates; see date_order(). Times and
    time zones are dropped (the date part as written is used).
    """
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if _is_missing(value):
        return None
    text = str(value).strip()
    if re.fullmatch(r"\d{9,10}(?:\.\d+)?", text):          # unix seconds
        return datetime.fromtimestamp(float(text), tz=timezone.utc).date()
    if re.fullmatch(r"\d{13}", text):                        # unix milliseconds
        return datetime.fromtimestamp(int(text) / 1000.0, tz=timezone.utc).date()
    if re.fullmatch(r"\d{8}", text):                         # GA4 20240315
        return _safe_date(int(text[:4]), int(text[4:6]), int(text[6:]))
    match = re.match(r"(\d{4})[-/.](\d{1,2})(?:[-/.](\d{1,2}))?(?!\d)", text)
    if match:
        return _safe_date(int(match.group(1)), int(match.group(2)), int(match.group(3) or 1))
    match = re.match(r"(\d{1,2})[-/.](\d{1,2})[-/.](\d{4}|\d{2})(?!\d)", text)
    if match:
        first, second, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
        if order is None:
            order = "dmy" if first > 12 else "mdy"
        if order == "dmy":
            return _safe_date(year, second, first)
        return _safe_date(year, first, second)
    lowered = text.lower().replace(",", " ")
    match = re.match(r"([a-z]{3,9})\.?\s+(\d{1,2})(?:st|nd|rd|th)?\s+(\d{4})", lowered)
    if match and match.group(1) in _MONTHS:
        return _safe_date(int(match.group(3)), _MONTHS[match.group(1)], int(match.group(2)))
    match = re.match(r"(\d{1,2})\s+([a-z]{3,9})\.?\s+(\d{4})", lowered)
    if match and match.group(2) in _MONTHS:
        return _safe_date(int(match.group(3)), _MONTHS[match.group(2)], int(match.group(1)))
    match = re.match(r"([a-z]{3,9})\.?\s+(\d{4})", lowered)
    if match and match.group(1) in _MONTHS:
        return _safe_date(int(match.group(2)), _MONTHS[match.group(1)], 1)
    return None


_ISO_DATETIME_RE = re.compile(
    r"(\d{4})-(\d{1,2})-(\d{1,2})[T ](\d{1,2}):(\d{2})(?::(\d{2})(?:[.,](\d{1,6})\d*)?)?\s*"
    r"(Z|UTC|[+-]\d{2}:?\d{2})?$", re.I)


def parse_datetime(value: Any, order: Optional[str] = None) -> Optional[datetime]:
    """Read an event time: ISO 8601 (with or without a zone), unix s / ms / us, or a date.

    Times with a zone are converted to UTC; times without one are used as
    written. The result is naive (no tzinfo) so values compare directly.
    A plain date is read as midnight.
    """
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if _is_missing(value):
        return None
    text = str(value).strip()
    for digits, scale in ((r"\d{9,10}(?:\.\d+)?", 1.0), (r"\d{13}", 1e3), (r"\d{16}", 1e6)):
        if re.fullmatch(digits, text):                       # unix s, ms (Mixpanel), us (GA4 BigQuery)
            return datetime.fromtimestamp(float(text) / scale, tz=timezone.utc).replace(tzinfo=None)
    match = _ISO_DATETIME_RE.match(text)
    if match:
        try:
            moment = datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)),
                              int(match.group(4)), int(match.group(5)), int(match.group(6) or 0),
                              int((match.group(7) or "0").ljust(6, "0")))
        except ValueError:
            return None
        zone = (match.group(8) or "").upper()
        if zone and zone not in ("Z", "UTC"):
            sign = -1 if zone[0] == "-" else 1
            digits = zone[1:].replace(":", "")
            moment -= sign * timedelta(hours=int(digits[:2]), minutes=int(digits[2:]))
        return moment
    day = parse_date(text, order)
    return datetime(day.year, day.month, day.day) if day else None


def date_order(values: Iterable[Any]) -> Tuple[Optional[str], bool]:
    """Decide day-first or month-first for a column of slashed dates.

    Returns (order, ambiguous). ambiguous is True when no value has a part
    above 12; month-first (US) is then assumed and the caller notes it.
    """
    saw_slashed = False
    for value in values:
        if _is_missing(value):
            continue
        match = re.match(r"\s*(\d{1,2})[-/.](\d{1,2})[-/.](\d{4}|\d{2})(?!\d)", str(value))
        if not match:
            continue
        saw_slashed = True
        first, second = int(match.group(1)), int(match.group(2))
        if first > 12:
            return "dmy", False
        if second > 12:
            return "mdy", False
    return ("mdy", True) if saw_slashed else (None, False)


def parse_duration(value: Any) -> Optional[float]:
    """'1h 2m 3s', '2d 4h', '00:03:20', '45s', '3.5 min' -> seconds. Bare numbers -> None."""
    if _is_missing(value):
        return None
    text = str(value).strip().lower()
    match = re.fullmatch(r"(?:(\d+)\s*d(?:ays?)?\s*)?(\d{1,3}):(\d{2})(?::(\d{2}))?", text)
    if match:
        days = int(match.group(1) or 0)
        if match.group(4) is not None:
            hours, minutes, seconds = int(match.group(2)), int(match.group(3)), int(match.group(4))
        else:
            hours, minutes, seconds = 0, int(match.group(2)), int(match.group(3))
        return float(days * 86400 + hours * 3600 + minutes * 60 + seconds)
    units = {"d": 86400, "day": 86400, "days": 86400, "h": 3600, "hr": 3600, "hrs": 3600,
             "hour": 3600, "hours": 3600, "m": 60, "min": 60, "mins": 60, "minute": 60,
             "minutes": 60, "s": 1, "sec": 1, "secs": 1, "second": 1, "seconds": 1}
    parts = re.findall(r"(\d+(?:\.\d+)?)\s*([a-z]+)", text)
    if not parts or re.sub(r"(\d+(?:\.\d+)?)\s*([a-z]+)", "", text).strip(" ,"):
        return None
    total = 0.0
    for number, unit in parts:
        if unit not in units:
            return None
        total += float(number) * units[unit]
    return total


def month_key(day: date) -> str:
    return "%04d-%02d" % (day.year, day.month)


def month_from_key(key: str) -> date:
    return date(int(key[:4]), int(key[5:7]), 1)


def add_months(key: str, count: int) -> str:
    start = month_from_key(key)
    index = start.year * 12 + start.month - 1 + count
    return "%04d-%02d" % (index // 12, index % 12 + 1)


def month_end(key: str) -> date:
    start = month_from_key(key)
    return date(start.year, start.month, calendar.monthrange(start.year, start.month)[1])


def month_range(first: str, last: str) -> List[str]:
    months = []
    current = first
    while current <= last:
        months.append(current)
        current = add_months(current, 1)
    return months


def _ratio(numerator: Optional[float], denominator: Optional[float]) -> Optional[float]:
    if numerator is None or not denominator:
        return None
    return numerator / denominator


def _round(value: Optional[float], digits: int = 2) -> Optional[float]:
    if value is None:
        return None
    return round(value, digits)


def _rate(value: Optional[float]) -> Optional[float]:
    return None if value is None else round(value, 4)


# ---------------------------------------------------------------------------
# Personal data and identifiers
# ---------------------------------------------------------------------------

# Columns that hold personal data. They are never read; their header names
# are reported so the skill can tell the user the file had them.
_PII_RE = re.compile(
    r"(^|_)(e_?mail|emails|phone|telephone|mobile|first_name|last_name|full_name|customer_name|"
    r"company_name|customer_description|description_of_customer|billing_name|shipping_name|"
    r"card|last4|cardholder|address|address_line|line1|line2|street|postal_code|postcode|zip|"
    r"zip_code|ip|ip_address|tax_id|vat_number|vat_id|owner|author)(_|$)"
)
_PII_EXACT = frozenset({"name", "names", "contact", "customer_description", "user", "username"})


def is_pii_header(key: str) -> bool:
    """True for a normalized header that holds personal data."""
    if key in _PII_EXACT:
        return True
    if key.endswith("_id") or key.endswith("_ids") or key.endswith("_uuid"):
        return False
    return bool(_PII_RE.search(key))


# Contact data: columns that only person-level tables have. An aggregated
# funnel or retention export never has them, so a table with one of these is
# a customer or user list and is not read as a funnel or cohort table (its
# rows would be people).
_CONTACT_RE = re.compile(
    r"(^|_)(e_?mail|emails|phone|telephone|mobile|first_name|last_name|full_name|customer_name|"
    r"billing_name|shipping_name|cardholder|last4|address|address_line|street|postal_code|postcode|"
    r"zip_code|ip_address)(_|$)"
)


def _has_contact_columns(table: "Table", allowed: Iterable[Optional[int]] = ()) -> bool:
    allowed_set = {index for index in allowed if index is not None}
    return any(i not in allowed_set and _CONTACT_RE.search(key) and not key.endswith(("_id", "_ids"))
               for i, key in enumerate(table.keys))


_SALT = os.urandom(16)


def pseudonym(value: Any) -> Optional[str]:
    """A per-process salted hash of an id: stable within one run, unlinkable across runs."""
    if _is_missing(value):
        return None
    digest = hashlib.sha256(_SALT + str(value).strip().encode("utf-8", "replace"))
    return digest.hexdigest()[:20]


_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+'-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")


def scrub(value: Any) -> Any:
    """Replace email addresses in every string (and dict key) with a salted tag.

    A safety net for text that comes from the file and reaches the output:
    breakdown segments, step names, plan names, cohort labels, preamble
    lines, Search Console keys and the headers listed in errors. The tag is
    stable within one run, so two different addresses stay two segments.
    """
    if isinstance(value, str):
        if "@" not in value:
            return value
        return _EMAIL_RE.sub(lambda m: "[email %s]" % pseudonym(m.group(0).lower())[:8], value)
    if isinstance(value, dict):
        return {scrub(key): scrub(item) for key, item in value.items()}
    if isinstance(value, list):
        return [scrub(item) for item in value]
    if isinstance(value, tuple):
        return tuple(scrub(item) for item in value)
    return value


# ---------------------------------------------------------------------------
# Reading files into tables
# ---------------------------------------------------------------------------


def normalize_header(header: Any) -> str:
    """'Created (UTC)' -> 'created', 'subscription[plan_id]' -> 'subscription_plan_id'."""
    text = str(header or "").replace("\ufeff", "").strip().strip('"').lower()
    text = re.sub(r"\((?:utc|gmt)\)", "", text)
    text = text.replace("%", " pct ")
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


class Table:
    """One CSV table: raw headers, normalized keys, data rows, preamble lines."""

    def __init__(self, name: str, headers: List[str], rows: List[List[str]], preamble: List[str],
                 delimiter: str, decimal_comma: bool, encoding: str) -> None:
        self.name = name
        self.headers = headers
        self.keys = [normalize_header(h) for h in headers]
        self.rows = rows
        self.preamble = preamble
        self.delimiter = delimiter
        self.decimal_comma = decimal_comma
        self.encoding = encoding
        self.more_sections = False

    def col(self, *aliases: str) -> Optional[int]:
        """Index of the first header whose normalized key equals an alias (in alias order)."""
        for alias in aliases:
            if alias in self.keys:
                return self.keys.index(alias)
        return None

    def value(self, row: List[str], index: Optional[int]) -> Optional[str]:
        if index is None or index >= len(row):
            return None
        cell = row[index]
        return None if _is_missing(cell) else cell.strip()

    def column(self, index: Optional[int]) -> List[Optional[str]]:
        return [self.value(row, index) for row in self.rows]

    def number(self, row: List[str], index: Optional[int]) -> Optional[float]:
        return parse_number(self.value(row, index), self.decimal_comma)

    def pii_headers(self, used: Iterable[int] = ()) -> List[str]:
        """Headers of personal-data columns, except columns a format reads (hashed ids, step names)."""
        used = set(used)
        return [self.headers[i] for i, key in enumerate(self.keys) if i not in used and is_pii_header(key)]

    def describe(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "data_rows": len(self.rows),
            "columns": len(self.headers),
            "delimiter": {",": "comma", ";": "semicolon", "\t": "tab", "|": "pipe"}.get(self.delimiter, self.delimiter),
            "decimal_comma": self.decimal_comma,
            "encoding": self.encoding,
        }


def _decode(raw: bytes) -> Tuple[str, str]:
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16"), "utf-16"
    try:
        return raw.decode("utf-8-sig"), "utf-8"
    except UnicodeDecodeError:
        return raw.decode("cp1252", "replace"), "cp1252"


def _sniff_delimiter(lines: List[str]) -> str:
    sample = [line for line in lines if line.strip() and not line.lstrip().startswith("#")][:30]
    best, best_score = ",", -1.0
    for delimiter in (",", ";", "\t", "|"):
        counts = []
        for row in csv.reader(sample, delimiter=delimiter):
            counts.append(len(row))
        if not counts:
            continue
        common, frequency = Counter(counts).most_common(1)[0]
        if common < 2:
            continue
        score = frequency * 1000 + common
        if score > best_score:
            best, best_score = delimiter, score
    return best


def _width(row: List[str]) -> int:
    width = len(row)
    while width and not row[width - 1].strip():
        width -= 1
    return width


def _looks_numeric(cell: str) -> bool:
    return parse_number(cell) is not None and not re.search(r"[A-Za-z]{4,}", cell)


def parse_table(text: str, name: str = "data.csv", encoding: str = "utf-8") -> Table:
    """Parse CSV text: skip '#' and title lines above the header, sniff the delimiter."""
    lines = text.splitlines()
    preamble: List[str] = []
    while lines and (not lines[0].strip() or lines[0].lstrip().startswith("#")):
        line = lines.pop(0)
        if line.strip():
            preamble.append(line.strip().lstrip("#").strip())
    delimiter = _sniff_delimiter(lines)
    rows = list(csv.reader(lines, delimiter=delimiter))
    widths = [_width(row) for row in rows]
    candidates = [w for w in widths[:500] if w >= 2]
    if not candidates:
        raise ImportFormatError("%s has no table: no line with two or more columns." % name)
    mode = Counter(candidates).most_common(1)[0][0]
    def numeric_share(index: int) -> float:
        cells = [cell for cell in rows[index][:widths[index]] if cell.strip()]
        return sum(1 for cell in cells if _looks_numeric(cell)) / float(len(cells)) if cells else 1.0

    header_index = None
    for index, width in enumerate(widths):
        if width < 2 or width < mode:
            continue
        share = numeric_share(index)
        if share <= 0.5:
            header_index = index
            break
        # Headers such as "Cohort, Size, 0, 1, 2" are mostly numbers too, but
        # less so than the data row under them.
        following = next((i for i in range(index + 1, len(rows)) if widths[i] >= 2), None)
        if share < 1.0 and following is not None and numeric_share(following) > share:
            header_index = index
            break
    if header_index is None:
        raise ImportFormatError("%s has no header row (every wide line is mostly numbers)." % name)
    for row in rows[:header_index]:
        joined = " ".join(cell.strip() for cell in row if cell.strip())
        if joined:
            preamble.append(joined)
    headers = [cell.strip() for cell in rows[header_index]]
    width = max(_width(rows[header_index]), 2)
    headers = headers[:width]
    data = []
    more_sections = False
    for row in rows[header_index + 1:]:
        if not any(cell.strip() for cell in row):
            continue
        if row and row[0].lstrip().startswith("#"):
            # GA4 and similar exports put several tables in one file, each
            # after '#' comment lines. Only the first table is read.
            more_sections = True
            break
        row = [cell for cell in row[:width]] + [""] * max(0, width - len(row))
        data.append(row)
    decimal_comma = delimiter == ";"
    table = Table(name, headers, data, preamble, delimiter, decimal_comma, encoding)
    table.more_sections = more_sections
    return table


def read_tables(path: str, member: Optional[str] = None) -> List[Table]:
    """Read a .csv/.tsv/.txt file, or every CSV inside a .zip (Search Console, Chargebee)."""
    if not os.path.isfile(path):
        raise ImportFormatError("File not found: %s" % path)
    lower = path.lower()
    if lower.endswith((".xlsx", ".xls", ".numbers", ".ods")):
        raise ImportFormatError(
            "%s is a spreadsheet file. Open it and save or export the sheet as CSV, then pass "
            "the .csv file." % os.path.basename(path))
    if os.path.getsize(path) > MAX_FILE_BYTES:
        raise ImportFormatError("%s is larger than %d MB; export a shorter date range."
                                % (os.path.basename(path), MAX_FILE_BYTES // (1024 * 1024)))
    if zipfile.is_zipfile(path):
        tables = []
        with zipfile.ZipFile(path) as archive:
            names = [
                info for info in archive.infolist()
                if not info.is_dir() and not info.filename.startswith("__MACOSX")
                and info.filename.lower().endswith((".csv", ".tsv", ".txt"))
            ]
            if member:
                names = [info for info in names if os.path.basename(info.filename) == member
                         or info.filename == member]
                if not names:
                    raise ImportFormatError("%s has no member named %s." % (os.path.basename(path), member))
            for info in names:
                if info.file_size > MAX_FILE_BYTES:
                    raise ImportFormatError("%s inside the zip is too large." % info.filename)
                text, encoding = _decode(archive.read(info))
                try:
                    tables.append(parse_table(text, os.path.basename(info.filename), encoding))
                except ImportFormatError:
                    continue
        if not tables:
            raise ImportFormatError("%s holds no readable CSV table." % os.path.basename(path))
        return tables
    with open(path, "rb") as handle:
        raw = handle.read()
    text, encoding = _decode(raw)
    return [parse_table(text, os.path.basename(path), encoding)]


# ---------------------------------------------------------------------------
# Format registry and detection
# ---------------------------------------------------------------------------


class Match:
    """A table matched to a format, with the columns it will read."""

    def __init__(self, source: str, score: int, columns: Dict[str, Optional[int]],
                 extra: Optional[Dict[str, Any]] = None) -> None:
        self.source = source
        self.score = score
        self.columns = {key: index for key, index in columns.items() if index is not None}
        self.extra = extra or {}


class Format:
    def __init__(self, source: str, kind: str, vendor: str, label: str, confidence: str,
                 docs: Sequence[str], columns_note: str,
                 matcher: Callable[[Table], Optional[Match]],
                 normalizer: Callable[[Table, Match, Dict[str, Any]], Dict[str, Any]]) -> None:
        self.source = source
        self.kind = kind
        self.vendor = vendor
        self.label = label
        self.confidence = confidence
        self.docs = list(docs)
        self.columns_note = columns_note
        self.matcher = matcher
        self.normalizer = normalizer

    def describe(self) -> Dict[str, Any]:
        return {
            "source": self.source, "kind": self.kind, "vendor": self.vendor, "label": self.label,
            "confidence": self.confidence, "columns": self.columns_note, "docs": self.docs,
        }


def _values(table: Table, index: Optional[int], limit: int = 2000) -> List[str]:
    if index is None:
        return []
    out = []
    for row in table.rows[:limit]:
        value = table.value(row, index)
        if value is not None:
            out.append(value)
    return out


def _distinct_lower(table: Table, index: Optional[int]) -> set:
    return {value.strip().lower() for value in _values(table, index)}


# --- billing column aliases -------------------------------------------------

SUB_ALIASES = {
    "customer": ("customer_id", "customer", "customer_uuid", "customer_external_id", "account_id",
                 "company_id", "user_id", "subscriber_id", "customer_oid", "oid"),
    "subscription": ("id", "subscription_id", "subscription", "subscription_uuid", "sub_id"),
    "status": ("status", "subscription_status", "state"),
    "plan": ("plan", "plan_nickname", "plan_name", "product", "product_name", "price_nickname",
             "price_name", "plan_id", "price_id", "tier"),
    "mrr": ("mrr", "monthly_recurring_revenue", "mrr_amount"),
    "amount": ("amount", "plan_amount", "price_amount", "unit_amount", "price_per_period",
               "recurring_amount", "subscription_amount"),
    "currency": ("currency", "plan_currency", "price_currency", "currency_code"),
    "interval": ("interval", "plan_interval", "price_interval", "billing_interval",
                 "recurring_interval", "billing_period", "billing_cycle", "period"),
    "interval_count": ("interval_count", "plan_interval_count", "price_interval_count",
                       "billing_frequency", "interval_length"),
    "quantity": ("quantity", "plan_quantity", "seats", "units"),
    "created": ("created", "created_at", "created_date", "signup_date"),
    "start": ("start", "start_date", "started_at", "start_at", "subscription_start", "starts_at"),
    "trial_start": ("trial_start", "trial_start_date", "trial_started_at"),
    "trial_end": ("trial_end", "trial_end_date", "trial_ended_at", "trial_ends_at"),
    "canceled_at": ("canceled_at", "cancelled_at", "canceled_date", "cancelled_date", "canceled",
                    "cancellation_date", "cancel_date", "churn_date", "churned_at"),
    "ended_at": ("ended_at", "ended_date", "ended", "end_date", "ends_at", "end"),
    "cancel_at_period_end": ("cancel_at_period_end",),
    "cancel_reason": ("cancellation_reason", "cancellation_details_reason", "cancel_reason",
                      "churn_reason", "cancellation_details"),
    "current_period_start": ("current_period_start",),
    "current_period_end": ("current_period_end",),
}

MRR_STATUSES = frozenset({"active", "past_due", "non_renewing"})
EXCLUDED_STATUSES = frozenset({"trialing", "in_trial", "incomplete", "incomplete_expired", "future", "draft"})
STOPPED_STATUSES = frozenset({"canceled", "cancelled", "ended", "churned", "expired", "transferred"})
HOLD_STATUSES = frozenset({"paused", "unpaid"})

INTERVAL_MONTHS = {
    "day": 1.0 / 30.4375, "daily": 1.0 / 30.4375, "days": 1.0 / 30.4375,
    "week": 7.0 / 30.4375, "weekly": 7.0 / 30.4375, "weeks": 7.0 / 30.4375,
    "month": 1.0, "monthly": 1.0, "months": 1.0, "mo": 1.0,
    "quarter": 3.0, "quarterly": 3.0, "quarters": 3.0,
    "semiannual": 6.0, "half_year": 6.0, "biannual": 6.0,
    "year": 12.0, "yearly": 12.0, "annual": 12.0, "annually": 12.0, "years": 12.0, "yr": 12.0,
}


def _interval_months(unit: Optional[str], count: Optional[float]) -> Optional[float]:
    if not unit:
        return None
    text = unit.strip().lower().replace("-", "_").replace(" ", "_")
    match = re.fullmatch(r"(?:every_)?(\d+)_?([a-z_]+)", text)
    if match:
        count = (count or 1) * float(match.group(1))
        text = match.group(2)
    months = INTERVAL_MONTHS.get(text)
    if months is None:
        return None
    return months * (count if count and count > 0 else 1.0)


def _interval_label(unit: Optional[str], count: Optional[float]) -> str:
    months = _interval_months(unit, count)
    if months is None:
        return "unknown"
    for label, value in (("month", 1.0), ("quarter", 3.0), ("half_year", 6.0), ("year", 12.0),
                         ("two_years", 24.0), ("three_years", 36.0)):
        if abs(months - value) < 1e-6:
            return label
    if months < 1.0:
        return "sub_monthly"
    return "%g_months" % round(months, 2)


def _churn_type(vendor: str, reason: Optional[str], status: Optional[str]) -> str:
    """voluntary, involuntary, other or unknown, from documented reason codes."""
    text = (reason or "").strip().lower().replace(" ", "_")
    if vendor == "chargebee":
        if text in ("not_paid", "no_card"):
            return "involuntary"
        if text in ("fraud_review_failed", "non_compliant_eu_customer", "tax_calculation_failed",
                    "currency_incompatible_with_gateway", "non_compliant_customer"):
            return "other"
        return "voluntary" if text else "unknown"
    if vendor == "paddle":
        if text == "customer_request":
            return "voluntary"
        if text == "chargeback":
            return "involuntary"
        return "other" if text else "unknown"
    if text in ("payment_failed", "payment_disputed", "not_paid", "no_card", "failed_payment",
                "involuntary", "dunning", "card_declined", "chargeback", "unpaid"):
        return "involuntary"
    if text in ("cancellation_requested", "customer_request", "voluntary", "requested_by_customer",
                "too_expensive", "missing_features", "switched_service", "unused", "customer_service",
                "too_complex", "low_quality", "other"):
        return "voluntary"
    if (status or "").lower() in ("unpaid", "incomplete_expired"):
        return "involuntary"
    return "voluntary" if text else "unknown"


def _normalize_status(raw: Optional[str]) -> str:
    text = (raw or "").strip().lower().replace(" ", "_").replace("-", "_")
    aliases = {"cancelled": "canceled", "in_trial": "trialing", "trial": "trialing",
               "pastdue": "past_due", "live": "active"}
    return aliases.get(text, text) or "unknown"


# --- format matchers ----------------------------------------------------------


def _match_chartmogul_movements(table: Table) -> Optional[Match]:
    kind = table.col("movement_type")
    when = table.col("date")
    account = table.col("mrr_movement_in_account_currency")
    invoice = table.col("mrr_movement_in_invoice_currency")
    dataset = table.col("mrr_movement")
    if kind is None or when is None or (account is None and invoice is None and dataset is None):
        return None
    values = _distinct_lower(table, kind)
    if values and not values & {"new_biz", "expansion", "contraction", "churn", "reactivation"}:
        return None
    if account is not None:
        amount, currency, unit = account, table.col("account_currency"), "auto"
    elif invoice is not None:
        amount, currency, unit = invoice, table.col("invoice_currency"), "auto"
    else:
        amount, currency, unit = dataset, table.col("currency_code"), "minor"
    return Match("chartmogul_mrr_movements", 100, {
        "type": kind, "date": when, "amount": amount, "currency": currency,
        "customer": table.col("customer_uuid", "customer_external_id"),
    }, {"amount_unit": unit,
        "amount_unit_basis": "documented (dataset amounts are in cents)" if unit == "minor" else
        "not stated in ChartMogul's export docs"})


_DATE_HEADER_RE = re.compile(r"^(?:mrr_)?(\d{4})_(\d{2})(?:_(\d{2}))?$")


def _month_columns(table: Table) -> Dict[int, str]:
    """{column index: 'YYYY-MM'} for headers such as '2025-12-31', 'mrr_2025-12-31', 'Jan 2025'."""
    found: Dict[int, str] = {}
    for index, (raw, key) in enumerate(zip(table.headers, table.keys)):
        if key.startswith("quantity_"):
            continue
        match = _DATE_HEADER_RE.match(key)
        day = None
        if match:
            day = _safe_date(int(match.group(1)), int(match.group(2)), int(match.group(3) or 1))
        elif re.fullmatch(r"[A-Za-z]{3,9}\.?\s+\d{4}", raw.strip()):
            day = parse_date(raw)
        if day is not None:
            found[index] = month_key(day)
    return found


def _match_customer_mrr(table: Table) -> Optional[Match]:
    months = _month_columns(table)
    if len(months) < 2 or len(set(months.values())) != len(months):
        return None
    customer = table.col("customer_uuid", "customer_external_ids", "customer_external_id",
                         "customer_id", "customer", "customer_oid", "oid", "account_id", "company_id")
    if customer is None:
        return None
    chartmogul = table.col("customer_uuid") is not None and table.col("customer_external_ids") is not None
    source = "chartmogul_customer_mrr" if chartmogul else "customer_mrr_wide"
    return Match(source, 90 if chartmogul else 40, {"customer": customer, "plan": table.col("plan_name")},
                 {"months": months, "amount_unit": "auto",
                  "amount_unit_basis": "not stated in the vendor's export docs"})


def _match_stripe_events(table: Table) -> Optional[Match]:
    kind = table.col("event_type")
    change = table.col("mrr_change")
    when = table.col("local_event_timestamp", "event_timestamp")
    if kind is None or change is None or when is None:
        return None
    values = {value.upper() for value in _values(table, kind)}
    if values and not values & {"ACTIVE_START", "ACTIVE_END", "ACTIVE_UPGRADE", "ACTIVE_DOWNGRADE"}:
        return None
    return Match("stripe_mrr_events", 100, {
        "type": kind, "amount": change, "date": when, "currency": table.col("currency"),
        "customer": table.col("customer_id"), "subscription": table.col("subscription_id"),
    }, {"amount_unit": "minor", "amount_unit_basis": "documented (mrr_change is in the currency's minor unit)"})


def _match_paddle(table: Table) -> Optional[Match]:
    status = table.col("subscription_status")
    amount = table.col("subscription_last_billed_cycle_amount")
    if status is None or amount is None or table.col("subscription_billing_interval") is None:
        return None
    return Match("paddle_subscriptions", 100, {
        "status": status, "amount": amount,
        "currency": table.col("subscription_last_billed_currency_code", "subscription_currency_code"),
        "interval": table.col("subscription_billing_interval"),
        "interval_count": table.col("subscription_billing_frequency"),
        "customer": table.col("customer_id"), "subscription": table.col("subscription_id"),
        "plan": table.col("active_recurring_product_name_list", "historic_product_name_list"),
        "created": table.col("subscription_created_at"),
        "start": table.col("subscription_started_at"),
        "trial_end": table.col("subscription_trial_ended_at"),
        "trial_start": table.col("subscription_trial_started_at"),
        "converted": table.col("subscription_has_converted_from_trial"),
        "canceled_at": table.col("subscription_canceled_at"),
        "ended_at": table.col("subscription_ends_at"),
        "cancel_reason": table.col("subscription_cancellation_reason"),
        "past_due_at": table.col("subscription_past_due_at"),
    }, {"amount_unit": "major", "amount_unit_basis": "documented (decimal strings in the major unit)",
        "vendor": "paddle"})


def _cb(table: Table, *names: str) -> Optional[int]:
    """Chargebee column: plain name, or subscription[name] / customer[name] style."""
    aliases = []
    for name in names:
        aliases.extend([name, "subscription_" + name])
    return table.col(*aliases)


def _match_chargebee(table: Table) -> Optional[Match]:
    status = _cb(table, "status")
    if status is None or table.col("subscription_last_billed_cycle_amount") is not None:
        return None
    bracketed = any(header.strip().lower().startswith(("subscription[", "customer["))
                    for header in table.headers)
    signature = [_cb(table, name) for name in ("billing_period_unit", "cancel_reason_code",
                                               "current_term_end", "current_term_start",
                                               "activated_at", "plan_unit_price", "due_since")]
    statuses = _distinct_lower(table, status)
    chargebee_status = bool(statuses & {"in_trial", "non_renewing", "future"})
    if not (bracketed or sum(1 for s in signature if s is not None) >= 2 or chargebee_status):
        return None
    mrr = _cb(table, "mrr")
    price = _cb(table, "plan_unit_price", "plan_amount")
    price_decimal = _cb(table, "plan_unit_price_in_decimal", "plan_amount_in_decimal")
    if mrr is None and price is None and price_decimal is None:
        return None
    return Match("chargebee_subscriptions", 95, {
        "status": status, "mrr": mrr, "amount": price if price is not None else price_decimal,
        "currency": _cb(table, "currency_code", "currency"),
        "interval": _cb(table, "billing_period_unit"), "interval_count": _cb(table, "billing_period"),
        "quantity": _cb(table, "plan_quantity"),
        "customer": table.col("customer_id", "subscription_customer_id", "customer"),
        "subscription": table.col("subscription_id", "id"),
        "plan": _cb(table, "plan_id", "item_price_id"),
        "created": _cb(table, "created_at"), "start": _cb(table, "started_at", "activated_at"),
        "trial_start": _cb(table, "trial_start"), "trial_end": _cb(table, "trial_end"),
        "canceled_at": _cb(table, "cancelled_at"),
        "cancel_reason": _cb(table, "cancel_reason", "cancel_reason_code"),
    }, {"amount_unit": "minor" if (mrr is not None or price is not None) else "major",
        "amount_unit_basis": "documented for the Subscription object (mrr and prices in cents)"
        if (mrr is not None or price is not None) else "documented (*_in_decimal fields are major units)",
        "vendor": "chargebee"})


def _sub_columns(table: Table) -> Dict[str, Optional[int]]:
    return {field: table.col(*aliases) for field, aliases in SUB_ALIASES.items()}


def _match_stripe_subscriptions(table: Table) -> Optional[Match]:
    columns = _sub_columns(table)
    utc_headers = sum(1 for header in table.headers if "(UTC)" in header)
    stripe_signature = utc_headers >= 2 or columns["cancel_at_period_end"] is not None \
        or columns["current_period_end"] is not None
    if not stripe_signature or columns["status"] is None:
        return None
    if columns["amount"] is None and columns["mrr"] is None:
        return None
    if columns["customer"] is None or (columns["start"] is None and columns["created"] is None):
        return None
    if table.col("amount_due", "billing_reason", "attempt_count") is not None:
        return None
    return Match("stripe_subscriptions", 80, columns,
                 {"amount_unit": "auto", "amount_unit_basis": "Dashboard exports write decimal amounts",
                  "vendor": "stripe"})


INVOICE_ALIASES = {
    "customer": ("customer", "customer_id"),
    "status": ("status",),
    "amount_paid": ("amount_paid",),
    "amount_due": ("amount_due",),
    "total": ("total", "amount"),
    "subtotal": ("subtotal",),
    "currency": ("currency",),
    "date": ("date", "created", "invoice_date", "finalized_at", "finalized"),
    "billing_reason": ("billing_reason",),
    "subscription": ("subscription", "subscription_id"),
    "attempt_count": ("attempt_count", "attempts"),
    "paid": ("paid",),
}


def _match_stripe_invoices(table: Table) -> Optional[Match]:
    columns = {field: table.col(*aliases) for field, aliases in INVOICE_ALIASES.items()}
    if table.col("amount_due", "billing_reason", "attempt_count", "amount_remaining") is None:
        return None
    if columns["date"] is None or (columns["amount_paid"] is None and columns["total"] is None):
        return None
    return Match("stripe_invoices", 80, columns,
                 {"amount_unit": "auto", "amount_unit_basis": "Dashboard exports write decimal amounts",
                  "vendor": "stripe"})


def _match_generic_movements(table: Table) -> Optional[Match]:
    when = table.col("date", "month", "event_date", "occurred_at", "timestamp")
    kind = table.col("type", "movement_type", "movement", "event", "kind", "category")
    amount = table.col("mrr_change", "mrr_movement", "mrr_delta", "change", "delta", "amount")
    customer = table.col(*SUB_ALIASES["customer"])
    if None in (when, kind, amount, customer):
        return None
    values = {value.replace(" ", "_") for value in _distinct_lower(table, kind)}
    if not values or not values <= set(MOVEMENT_TYPES) | {"neutral", "neutral_movement"}:
        return None
    return Match("generic_movements", 30, {"date": when, "type": kind, "amount": amount,
                                           "customer": customer, "currency": table.col("currency")},
                 {"amount_unit": "auto", "amount_unit_basis": "generic schema"})


def _match_generic_subscriptions(table: Table) -> Optional[Match]:
    columns = _sub_columns(table)
    if columns["customer"] is None:
        return None
    if columns["start"] is None and columns["created"] is None:
        return None
    if columns["mrr"] is None and (columns["amount"] is None or columns["interval"] is None):
        return None
    return Match("generic_subscriptions", 20, columns,
                 {"amount_unit": "auto", "amount_unit_basis": "generic schema", "vendor": "generic"})


# --- analytics matchers -------------------------------------------------------

STEP_LABEL_ALIASES = ("step", "step_name", "funnel_step", "funnel_steps", "steps", "stage", "step_label",
                      "event", "event_name", "name", "action")
COUNT_ALIASES = ("count", "users", "active_users", "unique_users", "persons", "people", "uniques",
                 "total_users", "total", "completed", "entered", "visitors", "sessions", "value",
                 "user_count")
STEP_CONVERSION_ALIASES = ("conversion_rate", "conversion", "completion_rate", "overall_conversion",
                           "overall_conversion_rate", "conversion_from_previous", "step_conversion",
                           "conversion_pct", "conversion_rate_pct")
TIME_ALIASES = ("average_time_to_convert", "avg_time_to_convert", "average_conversion_time",
                "avg_conversion_time", "median_time_to_convert", "median_conversion_time",
                "elapsed_time", "average_elapsed_time", "time_to_convert", "avg_time", "average_time",
                "median_time")
BREAKDOWN_ALIASES = ("breakdown", "breakdown_value", "segment", "segment_name", "cohort_name",
                     "device_category", "device", "platform", "country", "browser", "source",
                     "channel", "plan", "variant")


def _text_column(table: Table, aliases: Sequence[str]) -> Optional[int]:
    """First alias column whose values are mostly text (a 'Step' column of 1, 2, 3 is skipped)."""
    fallback = None
    for alias in aliases:
        index = table.col(alias)
        if index is None:
            continue
        fallback = index if fallback is None else fallback
        values = _values(table, index, 200)
        if values and sum(1 for v in values if parse_number(v) is None) * 2 >= len(values):
            return index
    return fallback


# More steps than this in one segment means the rows are not funnel steps
# (for example a customer list with a Name and a Total column).
MAX_FUNNEL_STEPS = 30


def _match_funnel_steps(table: Table) -> Optional[Match]:
    label = _text_column(table, STEP_LABEL_ALIASES)
    count = table.col(*COUNT_ALIASES)
    if label is None or count is None or label == count or len(table.rows) < 2:
        return None
    breakdown = table.col(*BREAKDOWN_ALIASES)
    if _has_contact_columns(table):
        return None                     # a list of people, not funnel steps
    steps_per_segment: Dict[str, set] = defaultdict(set)
    for row in table.rows[:5000]:
        name = table.value(row, label)
        if name is not None and name.strip().lower() not in TOTAL_LABELS:
            steps_per_segment[table.value(row, breakdown) or ""].add(name.strip().lower())
    if steps_per_segment and max(len(names) for names in steps_per_segment.values()) > MAX_FUNNEL_STEPS:
        return None
    numbers = [parse_number(v, table.decimal_comma) for v in _values(table, count)]
    if sum(1 for n in numbers if n is not None) < 2:
        return None
    ga4 = table.col("active_users") is not None and table.col("completion_rate", "abandonments",
                                                              "abandonment_rate") is not None
    preamble = " ".join(table.preamble).lower()
    if "funnel exploration" in preamble or "property:" in preamble:
        ga4 = True
    time_index = table.col(*TIME_ALIASES)
    return Match("funnel_steps", 50, {
        "step": label, "count": count, "conversion": table.col(*STEP_CONVERSION_ALIASES),
        "time": time_index, "breakdown": breakdown,
    }, {"vendor_guess": "GA4 funnel exploration" if ga4 else None})


_WIDE_STEP_RE = re.compile(r"^(?:step_?(\d+)(?:_.*)?|(\d+)_[a-z].*)$")


def _match_funnel_wide(table: Table) -> Optional[Match]:
    steps = []
    for index, key in enumerate(table.keys):
        match = _WIDE_STEP_RE.match(key)
        if match and not re.search(r"(conversion|rate|pct|time|drop)", key):
            steps.append((int(match.group(1) or match.group(2)), index))
    if len(steps) < 2 or _has_contact_columns(table):
        return None
    steps.sort()
    label = None
    step_indexes = {index for _n, index in steps}
    for index in range(len(table.keys)):
        if index not in step_indexes:
            label = index
            break
    if label is not None and table.keys[label] in _PII_EXACT:
        return None                     # one row per person, not per segment
    return Match("funnel_wide", 45, {"segment": label},
                 {"steps": [index for _n, index in steps]})


_PERIOD_RE = re.compile(r"^(?:(hour|day|week|month|period|d|w|m)_?)?(\d{1,3})$")


def _period_columns(table: Table) -> List[Tuple[int, int, Optional[str]]]:
    found = []
    for index, key in enumerate(table.keys):
        match = _PERIOD_RE.match(key)
        if match:
            unit = {"d": "day", "w": "week", "m": "month"}.get(match.group(1) or "", match.group(1))
            found.append((int(match.group(2)), index, unit))
    return found


def _match_retention(table: Table) -> Optional[Match]:
    periods = _period_columns(table)
    if len(periods) < 2:
        return None
    period_indexes = {index for _p, index, _u in periods}
    size = table.col("cohort_value", "size", "cohort_size", "users", "total_users", "total", "count",
                     "persons", "people", "new_users", "initial_users", "initial", "cohort_users",
                     "starting_users", "active_users")
    candidates = [index for index in range(len(table.keys))
                  if index not in period_indexes and index != size and table.keys[index] != "average"]
    if not candidates or _has_contact_columns(table):
        return None

    def date_share(index: int) -> float:
        values = [v for v in _values(table, index, 200) if v.strip().lower() not in TOTAL_LABELS]
        return sum(1 for v in values if parse_date(v) is not None) / float(len(values)) if values else 0.0

    # The cohort label is the first date-like column ("Date", "Start week"),
    # else the first other column. A text column next to it (Amplitude's
    # "Segment") is read as the segment.
    label = next((index for index in candidates if date_share(index) >= 0.8), candidates[0])
    if table.keys[label] in _PII_EXACT:
        return None                     # one row per person, not per cohort
    segment = next((index for index in candidates if index != label and date_share(index) < 0.8
                    and all(parse_number(v) is None for v in _values(table, index, 200))), None)
    chartmogul = table.col("cohort_value") is not None and table.col("average") is not None
    units = {unit for _p, _i, unit in periods if unit}
    posthog = bool(units) and any(raw.strip().lower().startswith(("day ", "week ", "month ", "hour "))
                                  for raw in table.headers)
    source = "chartmogul_cohorts" if chartmogul else "retention_grid"
    return Match(source, 95 if chartmogul else 55, {"label": label, "size": size, "segment": segment},
                 {"periods": sorted(periods), "vendor_guess": "ChartMogul cohort analysis" if chartmogul
                  else ("PostHog-style retention table" if posthog else None)})


GSC_DIMENSIONS = OrderedDict([
    ("query", ("top_queries", "query", "queries", "search_query")),
    ("page", ("top_pages", "page", "pages", "url", "landing_page", "address")),
    ("country", ("country", "countries")),
    ("device", ("device", "devices")),
    ("search_appearance", ("search_appearance", "search_appearances")),
    ("date", ("date", "dates", "day")),
])


def _match_gsc(table: Table) -> Optional[Match]:
    clicks = table.col("clicks")
    impressions = table.col("impressions")
    if clicks is None or impressions is None:
        return None
    for dimension, aliases in GSC_DIMENSIONS.items():
        index = table.col(*aliases)
        if index is not None:
            return Match("gsc_performance", 90, {
                "key": index, "clicks": clicks, "impressions": impressions,
                "ctr": table.col("ctr", "url_ctr", "site_ctr"),
                "position": table.col("position", "average_position", "avg_position"),
            }, {"dimension": dimension})
    return None


# One row per event: PostHog (event, distinct_id, timestamp ISO 8601),
# Mixpanel (event, distinct_id, time in unix seconds; flattened as
# properties.time), Amplitude (event_type, user_id / amplitude_id,
# event_time ISO 8601), GA4 BigQuery export (event_name, user_pseudo_id,
# event_timestamp in microseconds). Customer ids (customer_id) are not in the
# user aliases, so billing event tables never match here.
EVENT_USER_ALIASES = ("distinct_id", "properties_distinct_id", "person_id", "user_id", "user_pseudo_id",
                      "amplitude_id", "anonymous_id", "device_id", "visitor_id", "uid", "user")
EVENT_NAME_ALIASES = ("event", "event_name", "event_type", "event_key", "action")
EVENT_TIME_ALIASES = ("timestamp", "time", "properties_time", "event_time", "event_timestamp",
                      "client_event_time", "server_upload_time", "occurred_at", "created_at", "datetime",
                      "date")


def _match_event_log(table: Table) -> Optional[Match]:
    user = table.col(*EVENT_USER_ALIASES)
    event = table.col(*EVENT_NAME_ALIASES)
    when = table.col(*EVENT_TIME_ALIASES)
    if user is None or event is None or when is None or len({user, event, when}) < 3:
        return None
    sample = table.rows[:200]
    times = [parse_datetime(table.value(row, when)) for row in sample]
    if not sample or sum(1 for t in times if t is not None) < max(2, 0.8 * len(sample)):
        return None
    names = {table.value(row, event) for row in sample} - {None}
    if not names or all(parse_number(name) is not None for name in names):
        return None
    if names <= set(MOVEMENT_TYPES) | {"neutral"}:
        return None                     # an MRR movements table, not product events
    return Match("event_log", 35, {"user": user, "event": event, "time": when}, {})


# ---------------------------------------------------------------------------
# Amount units
# ---------------------------------------------------------------------------


def _resolve_unit(requested: str, match: Match, raw_values: List[Optional[str]],
                  notes: List[str]) -> Tuple[str, str]:
    """Pick 'major' or 'minor' for a format whose unit may not be documented."""
    if requested in ("major", "minor"):
        return requested, "set by --amount-unit"
    unit = match.extra.get("amount_unit", "auto")
    basis = match.extra.get("amount_unit_basis", "")
    # Cents are written as whole numbers; '49.00' or '49,90' means major units.
    has_decimals = any(value is not None and re.search(r"\d[.,]\d{1,2}\s*%?\s*$", str(value).strip())
                       for value in raw_values)
    if unit == "minor" and has_decimals:
        # Documented as cents, but cents are never fractional: this export
        # (for example a UI export rather than the API format) has dollars.
        notes.append("The vendor documents these amounts in cents, but this file writes them with "
                     "decimals, so they are read as major units (dollars). If that is wrong, rerun with "
                     "--amount-unit minor.")
        return "major", "detected (decimals in a field documented in cents)"
    if unit in ("major", "minor"):
        return unit, basis
    if has_decimals:
        return "major", "detected (amounts are written with decimals)"
    notes.append(
        "Amounts in this file are whole numbers, so they are read as major units (dollars, not "
        "cents). If the export is in cents, rerun with --amount-unit minor.")
    return "major", "assumed (whole numbers; " + (basis or "unit not documented") + ")"


def _currencies_in_cells(cells: Iterable[Optional[str]]) -> Dict[str, str]:
    """{currency code: sign as written} for the signs and codes found in amount cells."""
    found: Dict[str, str] = {}
    for cell in cells:
        if not cell:
            continue
        for symbol, code in _CURRENCY_SYMBOLS.items():
            if symbol in cell:
                found.setdefault(code, symbol)
        for word in re.findall(r"[A-Za-z]{3}", cell):
            if word.upper() in _CURRENCY_CODES:
                found.setdefault(word.upper(), word)
    return found


def _amount(table: Table, row: List[str], index: Optional[int], unit: str,
            currency: Optional[str]) -> Optional[float]:
    number = table.number(row, index)
    if number is None:
        return None
    return from_minor(number, currency) if unit == "minor" else number


# ---------------------------------------------------------------------------
# Normalizers: table -> records (no personal data, ids hashed)
# ---------------------------------------------------------------------------

MOVEMENT_TYPES = OrderedDict([
    ("new", "new"), ("new_biz", "new"), ("new_business", "new"), ("newbiz", "new"),
    ("expansion", "expansion"), ("upgrade", "expansion"),
    ("contraction", "contraction"), ("downgrade", "contraction"),
    ("churn", "churn"), ("churned", "churn"), ("cancellation", "churn"),
    ("reactivation", "reactivation"), ("reactivated", "reactivation"),
])


class Skips:
    """Rows left out, by reason. 'excluded' reasons are rules, not read errors."""

    def __init__(self) -> None:
        self.unreadable: Counter = Counter()
        self.excluded: Counter = Counter()

    def bad(self, reason: str) -> None:
        self.unreadable[reason] += 1

    def rule(self, reason: str) -> None:
        self.excluded[reason] += 1

    def as_dict(self) -> Dict[str, Any]:
        return {"unreadable": dict(self.unreadable), "excluded_by_rule": dict(self.excluded)}

    def unreadable_count(self) -> int:
        return sum(self.unreadable.values())


def _date_orders(table: Table, columns: Dict[str, int], fields: Sequence[str],
                 notes: List[str]) -> Dict[str, Optional[str]]:
    orders = {}
    for field in fields:
        index = columns.get(field)
        if index is None:
            continue
        order, ambiguous = date_order(table.column(index))
        orders[field] = order
        if ambiguous:
            notes.append("Dates in column %r could be day-first or month-first; month-first (US) "
                         "was assumed." % table.headers[index])
    return orders


def _to_bool(value: Optional[str]) -> Optional[bool]:
    try:
        return cli.to_bool(value)
    except ValueError:
        return None


def _normalize_subscriptions(table: Table, match: Match, options: Dict[str, Any]) -> Dict[str, Any]:
    columns = match.columns
    notes: List[str] = []
    skips = Skips()
    vendor = match.extra.get("vendor", "generic")
    amount_index = columns.get("mrr", columns.get("amount"))
    unit, unit_basis = _resolve_unit(options.get("amount_unit", "auto"), match,
                                     table.column(amount_index), notes)
    date_fields = ("created", "start", "trial_start", "trial_end", "canceled_at", "ended_at", "past_due_at")
    orders = _date_orders(table, columns, date_fields, notes)
    default_currency = options.get("currency")
    records = []
    latest: Optional[date] = None
    for row in table.rows:
        def get(field: str) -> Optional[str]:
            return table.value(row, columns.get(field))

        def day(field: str) -> Optional[date]:
            return parse_date(get(field), orders.get(field))

        status_raw = get("status")
        status = _normalize_status(status_raw) if status_raw else "unknown"
        # The export date is not in the file; the latest event that has
        # already happened (signup, start, past due, a finished cancellation)
        # stands in for it. Trial ends and scheduled cancellations can lie in
        # the future, so they do not count.
        happened = [day("created"), day("start"), day("trial_start"), day("past_due_at")]
        if status in STOPPED_STATUSES or status == "unknown":
            happened += [day("canceled_at"), day("ended_at")]
        for when in happened:
            if when is not None and (latest is None or when > latest):
                latest = when
        currency = normalize_currency(get("currency")) or default_currency
        quantity = table.number(row, columns.get("quantity"))
        interval_unit = get("interval")
        interval_count = table.number(row, columns.get("interval_count"))
        months = _interval_months(interval_unit, interval_count)
        mrr = None
        if columns.get("mrr") is not None:
            mrr = _amount(table, row, columns.get("mrr"), unit, currency)
        if mrr is None and columns.get("amount") is not None:
            amount = _amount(table, row, columns.get("amount"), unit, currency)
            if amount is not None and months:
                mrr = amount * (quantity if (quantity and vendor not in ("paddle",)) else 1.0) / months
            elif amount is not None:
                skips.bad("billing interval missing or unknown")
                continue
        if mrr is None and status in EXCLUDED_STATUSES:
            mrr = 0.0               # trials and incomplete signups carry no amount yet
        if mrr is None:
            skips.bad("no amount")
            continue
        if mrr < 0:
            skips.bad("negative amount")
            continue
        start = day("start") or day("created")
        trial_end = day("trial_end")
        paid_start = start
        if trial_end and (paid_start is None or trial_end > paid_start):
            paid_start = trial_end
        canceled = day("canceled_at")
        ended = day("ended_at")
        if status in STOPPED_STATUSES or status == "unknown":
            end = ended or canceled
        elif status in MRR_STATUSES:
            end = None              # a cancellation, if any, is scheduled for later
        else:
            end = ended
        if paid_start is None:
            skips.bad("no start date")
            continue
        if status in STOPPED_STATUSES and end is None:
            skips.bad("canceled without an end or cancel date")
            continue
        reason = get("cancel_reason")
        plan = get("plan")
        if plan:
            plan = re.sub(r'^[\[\("\']+|[\]\)"\']+$', "", plan).split('","')[0].split(",")[0].strip() or None
        record = {
            "customer": pseudonym(get("customer") or get("subscription")),
            "status": status,
            "currency": currency or "UNKNOWN",
            "mrr": mrr,
            "plan": plan,
            "interval": _interval_label(interval_unit, interval_count) if columns.get("mrr") is None or interval_unit
            else "unknown",
            "start": paid_start,
            "signup": start,
            "trial_start": day("trial_start"),
            "trial_end": trial_end,
            "end": end,
            "churn_type": _churn_type(vendor, reason, status) if end else None,
            "converted": _to_bool(get("converted")),
            "past_due": status == "past_due" or bool(day("past_due_at") and status not in STOPPED_STATUSES),
        }
        if record["customer"] is None:
            skips.bad("no customer id")
            continue
        records.append(record)
    if columns.get("mrr") is None and columns.get("quantity") is not None and vendor != "paddle":
        notes.append("MRR = %s x %s / billing interval in months. Check one subscription against "
                     "your billing dashboard; if %s is already the total, the quantity is counted twice."
                     % (table.headers[columns["amount"]], table.headers[columns["quantity"]],
                        table.headers[columns["amount"]]))
    if any(r["currency"] == "UNKNOWN" for r in records):
        notes.append("Some rows have no currency column or value; their amounts are grouped under "
                     "'UNKNOWN'. Pass --currency USD (or the right code) to label them.")
    return {"subscriptions": records, "skips": skips, "notes": notes, "latest_event": latest,
            "amount_unit": unit, "amount_unit_basis": unit_basis}


def _normalize_movements(table: Table, match: Match, options: Dict[str, Any]) -> Dict[str, Any]:
    columns = match.columns
    notes: List[str] = []
    skips = Skips()
    unit, unit_basis = _resolve_unit(options.get("amount_unit", "auto"), match,
                                     table.column(columns.get("amount")), notes)
    orders = _date_orders(table, columns, ("date",), notes)
    default_currency = options.get("currency")
    stripe = match.source == "stripe_mrr_events"
    records = []
    for row in table.rows:
        when = parse_date(table.value(row, columns.get("date")), orders.get("date"))
        if when is None:
            skips.bad("no date")
            continue
        raw_type = (table.value(row, columns.get("type")) or "").strip()
        if stripe:
            kind = raw_type.upper()
            if kind.startswith("TRIAL") or kind == "CONVERT_TRIAL":
                skips.rule("trial lifecycle marker (no MRR change)")
                continue
        else:
            kind = MOVEMENT_TYPES.get(raw_type.lower().replace(" ", "_"))
            if kind is None:
                if raw_type.lower() in ("neutral", "neutral_movement"):
                    skips.rule("neutral movement (no MRR change)")
                else:
                    skips.bad("unknown movement type")
                continue
        currency = normalize_currency(table.value(row, columns.get("currency"))) or default_currency
        amount = _amount(table, row, columns.get("amount"), unit, currency)
        if amount is None:
            skips.bad("no amount")
            continue
        customer = pseudonym(table.value(row, columns.get("customer"))
                             or table.value(row, columns.get("subscription")))
        if customer is None:
            skips.bad("no customer id")
            continue
        if not stripe and kind in ("churn", "contraction") and amount > 0:
            amount = -amount
        records.append({"date": when, "customer": customer, "type": kind, "amount": amount,
                        "currency": currency or "UNKNOWN"})
    return {"movements": records, "skips": skips, "notes": notes, "amount_unit": unit,
            "amount_unit_basis": unit_basis, "typed": not stripe}


def _normalize_customer_mrr(table: Table, match: Match, options: Dict[str, Any]) -> Dict[str, Any]:
    notes: List[str] = []
    skips = Skips()
    months: Dict[int, str] = match.extra["months"]
    raw = [table.value(row, index) for row in table.rows for index in months]
    unit, unit_basis = _resolve_unit(options.get("amount_unit", "auto"), match, raw, notes)
    currency = options.get("currency")
    if not currency:
        signs = _currencies_in_cells(raw)
        if len(signs) == 1:
            (currency, sign), = signs.items()
            notes.append("The currency (%s) was read from the %r written in the amounts; pass --currency "
                         "if the account uses another currency with that sign." % (currency, sign))
    if not currency:
        currency = "UNKNOWN"
        if match.source == "chartmogul_customer_mrr":
            notes.append("The file has no currency column; ChartMogul writes these exports in the "
                         "account's primary currency. Pass --currency to label the amounts.")
        else:
            notes.append("The file has no currency column or currency sign. Pass --currency to label "
                         "the amounts.")
    series: Dict[str, Dict[str, float]] = {}
    for row in table.rows:
        customer = pseudonym(table.value(row, match.columns.get("customer")))
        if customer is None:
            skips.bad("no customer id")
            continue
        values = {}
        for index, month in months.items():
            number = table.number(row, index)
            if number is None:
                continue
            values[month] = from_minor(number, currency) if unit == "minor" else number
        if not values:
            skips.bad("no monthly values")
            continue
        existing = series.setdefault(customer, {})
        for month, value in values.items():
            existing[month] = existing.get(month, 0.0) + value
    return {"series": {currency: series}, "skips": skips, "notes": notes, "amount_unit": unit,
            "amount_unit_basis": unit_basis, "first_month": min(months.values()),
            "last_month": max(months.values())}


def _normalize_invoices(table: Table, match: Match, options: Dict[str, Any]) -> Dict[str, Any]:
    columns = match.columns
    notes: List[str] = []
    skips = Skips()
    amount_index = columns.get("amount_paid", columns.get("total"))
    unit, unit_basis = _resolve_unit(options.get("amount_unit", "auto"), match, table.column(amount_index), notes)
    orders = _date_orders(table, columns, ("date",), notes)
    records = []
    for row in table.rows:
        when = parse_date(table.value(row, columns.get("date")), orders.get("date"))
        if when is None:
            skips.bad("no date")
            continue
        currency = normalize_currency(table.value(row, columns.get("currency"))) or options.get("currency") or "UNKNOWN"
        status = _normalize_status(table.value(row, columns.get("status")))
        if status in ("draft", "deleted"):
            skips.rule("draft invoice")
            continue
        records.append({
            "date": when,
            "currency": currency,
            "status": status,
            "amount_paid": _amount(table, row, columns.get("amount_paid"), unit, currency),
            "total": _amount(table, row, columns.get("total"), unit, currency),
            "amount_due": _amount(table, row, columns.get("amount_due"), unit, currency),
            "subscription": table.value(row, columns.get("subscription")) is not None,
            "billing_reason": (table.value(row, columns.get("billing_reason")) or "").lower() or None,
            "attempts": table.number(row, columns.get("attempt_count")),
            "customer": pseudonym(table.value(row, columns.get("customer"))),
        })
    return {"invoices": records, "skips": skips, "notes": notes, "amount_unit": unit,
            "amount_unit_basis": unit_basis}


def _normalize_funnel_steps(table: Table, match: Match, options: Dict[str, Any]) -> Dict[str, Any]:
    columns = match.columns
    skips = Skips()
    notes: List[str] = []
    groups: "OrderedDict[str, List[Dict[str, Any]]]" = OrderedDict()
    for row in table.rows:
        name = table.value(row, columns.get("step"))
        if name is None:
            skips.bad("no step name")
            continue
        if name.strip().lower() in TOTAL_LABELS:
            skips.rule("total row")
            continue
        count = table.number(row, columns.get("count"))
        if count is None:
            skips.bad("no count")
            continue
        segment = table.value(row, columns.get("breakdown")) or "all"
        time_text = table.value(row, columns.get("time"))
        groups.setdefault(segment, []).append({
            "name": re.sub(r"^\s*(?:step\s*)?\d+\s*[.:)-]\s*", "", name, flags=re.I) or name,
            "count": count,
            "time_to_convert_seconds": parse_duration(time_text),
            "time_raw": time_text,
        })
    if columns.get("time") is not None:
        raw = [step["time_raw"] for steps in groups.values() for step in steps if step["time_raw"]]
        if raw and all(parse_duration(value) is None for value in raw):
            notes.append("The time column %r has no units, so time to convert was not read."
                         % table.headers[columns["time"]])
    return {"segments": groups, "skips": skips, "notes": notes}


def _normalize_funnel_wide(table: Table, match: Match, options: Dict[str, Any]) -> Dict[str, Any]:
    skips = Skips()
    groups: "OrderedDict[str, List[Dict[str, Any]]]" = OrderedDict()
    names = [re.sub(r"^\s*(?:step\s*)?\d+\s*[.:)-]?\s*", "", table.headers[i], flags=re.I) or table.headers[i]
             for i in match.extra["steps"]]
    for row in table.rows:
        segment = table.value(row, match.columns.get("segment")) or "all"
        counts = [table.number(row, index) for index in match.extra["steps"]]
        if counts[0] is None:
            skips.bad("no first-step count")
            continue
        percent_cells = [("%" in (table.value(row, i) or "")) for i in match.extra["steps"]]
        steps = []
        for position, (name, count) in enumerate(zip(names, counts)):
            if count is None:
                break
            if position and percent_cells[position]:
                count = counts[0] * count / 100.0
            steps.append({"name": name, "count": count, "time_to_convert_seconds": None, "time_raw": None})
        if segment.strip().lower() in TOTAL_LABELS and len(table.rows) > 1:
            segment = "all"
        groups[segment] = steps
    return {"segments": groups, "skips": skips, "notes": []}


def _normalize_retention(table: Table, match: Match, options: Dict[str, Any]) -> Dict[str, Any]:
    notes: List[str] = []
    skips = Skips()
    periods: List[Tuple[int, int, Optional[str]]] = match.extra["periods"]
    size_index = match.columns.get("size")
    label_index = match.columns.get("label")
    segment_index = match.columns.get("segment")
    segments_seen = {(table.value(row, segment_index) or "").strip() for row in table.rows} - {""}
    total_segments = {s for s in segments_seen if s.lower() in TOTAL_LABELS}
    keep_segment = None
    if len(segments_seen) > 1 and total_segments:
        # "All Users" next to per-segment rows: read the total rows only, so
        # the same users are not counted twice.
        keep_segment = sorted(total_segments)[0]
        notes.append("The table has %d segments in column %r; only the %r rows were read. Export one "
                     "segment at a time to analyze the others." % (
                         len(segments_seen), table.headers[segment_index], keep_segment))
    elif len(segments_seen) > 1:
        notes.append("The table has %d segments in column %r; each cohort label starts with its segment, "
                     "and the average curve pools all segments." % (
                         len(segments_seen), table.headers[segment_index]))
    rows = []
    date_labels = []
    for row in table.rows:
        label = table.value(row, label_index)
        if label is None:
            skips.bad("no cohort label")
            continue
        if label.strip().lower() in TOTAL_LABELS:
            skips.rule("average or total row")
            continue
        segment = (table.value(row, segment_index) or "").strip()
        if keep_segment is not None and segment != keep_segment:
            skips.rule("segment rows other than %s" % keep_segment)
            continue
        date_labels.append(label)
        if keep_segment is None and len(segments_seen) > 1 and segment:
            label = "%s / %s" % (segment, label)
        rows.append((label, table.number(row, size_index),
                     [table.value(row, index) for _p, index, _u in periods]))
    if not rows:
        return {"cohorts": [], "skips": skips, "notes": notes}
    requested = options.get("values", "auto")
    cells = [cell for _l, _s, values in rows for cell in values if cell is not None]
    numbers = [n for n in (parse_number(cell, table.decimal_comma) for cell in cells) if n is not None]
    first = [parse_number(values[0], table.decimal_comma) for _l, _s, values in rows if values and values[0]]
    first = [f for f in first if f is not None]
    sizes = [size for _l, size, _v in rows]

    def all_near(target: float, tolerance: float) -> bool:
        return bool(first) and all(abs(f - target) <= tolerance for f in first)

    if all_near(0.0, 1e-9) and any(n > 0 for n in numbers):
        # Retention starts at the whole cohort; a table that starts at 0 and
        # grows counts the customers or MRR lost (ChartMogul Customer Churn,
        # Net MRR Churn). 100 % minus churn is not retention there (churn is
        # offset by reactivation and expansion), so it is not converted.
        raise ImportFormatError(
            "Period 0 is 0 in every cohort, so this looks like a churn cohort table, not retention. "
            "Export a retention analysis instead (for example ChartMogul Customer Retention or Net MRR "
            "Retention, relative to the cohort value) and rerun.")
    if requested in ("percent", "count", "fraction"):
        value_type = requested
    elif any("%" in cell for cell in cells):
        value_type = "percent"
    elif all_near(1.0, 1e-6) and numbers and max(numbers) <= 10.0:
        value_type = "fraction"
    elif all_near(100.0, 0.5) and not (size_index is not None and all(
            s is not None and abs(s - 100.0) <= 0.5 for s in sizes)):
        value_type = "percent"          # period 0 is 100 % (values above 100 are revenue expansion)
    elif size_index is not None and first and all(
            s is not None and abs(f - s) <= max(1.0, 0.01 * s) for f, s in zip(
                [parse_number(v[0], table.decimal_comma) for _l, _s, v in rows if v and v[0]], sizes)
            if f is not None):
        value_type = "count"
    elif size_index is None and numbers and max(numbers) > 100.0:
        value_type = "count"
    else:
        raise ImportFormatError(
            "Cannot tell whether the retention cells are percentages or user counts. Rerun with "
            "--values percent or --values count.")
    if value_type == "count" and size_index is None:
        notes.append("No cohort size column; the period-0 count is used as the cohort size.")
    if value_type != "count" and size_index is None:
        notes.append("No cohort size column, so the average curve is an unweighted mean of cohorts.")
    if match.source == "chartmogul_cohorts":
        notes.append("ChartMogul cohort cells are read as shares of the cohort value (the 'Relative to: "
                     "cohort value' setting). A table exported relative to the previous period holds "
                     "period-over-period rates instead; check the setting before comparing.")
    label_order, _ambiguous = date_order(date_labels)
    cohorts = []
    for (label, size, values), date_label in zip(rows, date_labels):
        parsed = [parse_number(value, table.decimal_comma) for value in values]
        if value_type == "count":
            base = size if size else (parsed[0] if parsed and parsed[0] else None)
            rates = [None if value is None or not base else value / base for value in parsed]
            counts = parsed
        else:
            scale = 100.0 if value_type == "percent" else 1.0
            rates = [None if value is None else value / scale for value in parsed]
            base = size
            counts = [None if rate is None or base is None else rate * base for rate in rates]
        while rates and rates[-1] is None:
            rates.pop()
            counts.pop()
        cohorts.append({"label": label, "start": parse_date(date_label, label_order), "size": base,
                        "rates": rates, "counts": counts})
    return {"cohorts": cohorts, "value_type": value_type, "skips": skips, "notes": notes,
            "periods": [period for period, _i, _u in periods],
            "unit_hint": next((unit for _p, _i, unit in periods if unit and unit != "period"), None)}


def _normalize_gsc(table: Table, match: Match, options: Dict[str, Any]) -> Dict[str, Any]:
    columns = match.columns
    skips = Skips()
    notes: List[str] = []
    rows = []
    dimension = match.extra["dimension"]
    for row in table.rows:
        key = table.value(row, columns.get("key"))
        if key is None:
            skips.bad("no %s" % dimension)
            continue
        clicks = table.number(row, columns.get("clicks"))
        impressions = table.number(row, columns.get("impressions"))
        if clicks is None or impressions is None:
            skips.bad("no clicks or impressions")
            continue
        ctr_reported = parse_rate(table.value(row, columns.get("ctr")), table.decimal_comma)
        position = table.number(row, columns.get("position"))
        if dimension == "date":
            day = parse_date(key)
            key = day.isoformat() if day else key
        rows.append({
            "key": key, "clicks": clicks, "impressions": impressions,
            "ctr": (clicks / impressions) if impressions else ctr_reported,
            "position": position,
        })
    return {"rows": rows, "dimension": dimension, "skips": skips, "notes": notes}


def _normalize_events(table: Table, match: Match, options: Dict[str, Any]) -> Dict[str, Any]:
    columns = match.columns
    skips = Skips()
    notes: List[str] = []
    orders = _date_orders(table, columns, ("time",), notes)
    events = []
    for row in table.rows:
        user = pseudonym(table.value(row, columns.get("user")))
        if user is None:
            skips.bad("no user id")
            continue
        name = table.value(row, columns.get("event"))
        if name is None:
            skips.bad("no event name")
            continue
        when = parse_datetime(table.value(row, columns.get("time")), orders.get("time"))
        if when is None:
            skips.bad("no event time")
            continue
        events.append((user, name, when))
    if events and all(when.time() == datetime.min.time() for _u, _n, when in events):
        notes.append("Event times have no time of day, so times to convert are in whole days.")
    return {"events": events, "skips": skips, "notes": notes}


FORMATS: List[Format] = [
    Format("chartmogul_mrr_movements", "billing", "ChartMogul", "All MRR Movements export", "high",
           [DOCS["chartmogul_exports"], DOCS["chartmogul_movements_dataset"]],
           "customer_uuid, movement_type, date, mrr_movement_in_account_currency, account_currency "
           "(or the invoice-currency pair; dataset: MOVEMENT_TYPE, MRR_MOVEMENT in cents, CURRENCY_CODE)",
           _match_chartmogul_movements, _normalize_movements),
    Format("chartmogul_customer_mrr", "billing", "ChartMogul", "MRR per Customer per Month export", "high",
           [DOCS["chartmogul_exports"]],
           "customer_uuid, customer_external_ids, then one column per month end (2025-12-31) or mrr_<date>",
           _match_customer_mrr, _normalize_customer_mrr),
    Format("stripe_mrr_events", "billing", "Stripe", "Sigma subscription_item_change_events query", "high",
           [DOCS["stripe_sigma_billing"]],
           "event_timestamp or local_event_timestamp, event_type, mrr_change (minor units), currency, "
           "customer_id, subscription_id",
           _match_stripe_events, _normalize_movements),
    Format("paddle_subscriptions", "billing", "Paddle", "Paddle Billing subscriptions report", "high",
           [DOCS["paddle_subscriptions_report"]],
           "subscription_status, subscription_last_billed_cycle_amount, subscription_last_billed_currency_code, "
           "subscription_billing_interval, subscription_billing_frequency, subscription_started_at, "
           "subscription_ends_at, subscription_cancellation_reason",
           _match_paddle, _normalize_subscriptions),
    Format("chargebee_subscriptions", "billing", "Chargebee", "Subscriptions export", "medium",
           [DOCS["chargebee_subscription_object"], DOCS["chargebee_bulk_operations"]],
           "status, mrr or plan_unit_price (cents), currency_code, billing_period(_unit), started_at, "
           "cancelled_at, cancel_reason; plain or subscription[...] headers",
           _match_chargebee, _normalize_subscriptions),
    Format("stripe_subscriptions", "billing", "Stripe", "Dashboard subscriptions export", "medium",
           [DOCS["stripe_subscription_statuses"]],
           "Customer ID, Status, Plan, Amount, Currency, Interval, Quantity, Start (UTC), "
           "Trial End (UTC), Canceled At (UTC), Ended At (UTC); Stripe does not publish the export's "
           "column list, so common labels are matched",
           _match_stripe_subscriptions, _normalize_subscriptions),
    Format("stripe_invoices", "invoices", "Stripe", "Dashboard invoices export", "medium",
           [DOCS["stripe_invoice_export"]],
           "Date (UTC), Customer, Status, Amount Paid, Amount Due, Total, Currency, Billing Reason, "
           "Subscription, Attempt Count; columns follow the Dashboard's Edit columns setting",
           _match_stripe_invoices, _normalize_invoices),
    Format("generic_movements", "billing", "any", "Generic MRR movements CSV", "medium", [],
           "date, customer_id, type (new|expansion|contraction|churn|reactivation), mrr_change [, currency]",
           _match_generic_movements, _normalize_movements),
    Format("customer_mrr_wide", "billing", "any", "Customer x month MRR table (for example Baremetrics "
           "MRR Per Customer)", "medium", [DOCS["baremetrics_exports"]],
           "a customer id column, then one MRR column per month (2025-01, 2025-01-31 or Jan 2025)",
           _match_customer_mrr, _normalize_customer_mrr),
    Format("generic_subscriptions", "billing", "any", "Generic subscriptions CSV", "medium", [],
           "customer_id, start_date, mrr or amount + interval [, interval_count, quantity, status, "
           "end_date, plan, currency, cancel_reason]",
           _match_generic_subscriptions, _normalize_subscriptions),
    Format("chartmogul_cohorts", "retention", "ChartMogul", "Cohort analysis export", "high",
           [DOCS["chartmogul_exports"]],
           "cohort period, Cohort value, period columns 0, 1, 2 ... (percent), Average",
           _match_retention, _normalize_retention),
    Format("gsc_performance", "search", "Google Search Console", "Performance report export", "medium",
           [DOCS["gsc_performance"]],
           "Top queries | Top pages | Country | Device | Search Appearance | Date, Clicks, Impressions, "
           "CTR, Position",
           _match_gsc, _normalize_gsc),
    Format("retention_grid", "retention", "any", "Cohort retention table (PostHog, Amplitude, Mixpanel, "
           "GA4 or other)", "medium", [DOCS["posthog_retention"], DOCS["mixpanel_export"]],
           "a cohort label column, an optional size column, period columns (0, 1, 2 or Day 0, Week 1 ...)",
           _match_retention, _normalize_retention),
    Format("funnel_wide", "funnel", "any", "Funnel table with one column per step", "medium",
           [DOCS["mixpanel_export"]],
           "a segment column, then Step 1, Step 2 ... count columns",
           _match_funnel_wide, _normalize_funnel_wide),
    Format("funnel_steps", "funnel", "any", "Funnel step table (GA4 funnel exploration, PostHog, "
           "Mixpanel, Amplitude or other)", "medium", [DOCS["ga4_funnels"], DOCS["posthog_funnels"]],
           "a step column and a count column (Step, Active users / Users / Count), optional breakdown "
           "and time-to-convert columns",
           _match_funnel_steps, _normalize_funnel_steps),
    Format("event_log", "events", "any", "Raw event log, one row per event (PostHog, Mixpanel, Amplitude, "
           "GA4 BigQuery or other)", "medium",
           [DOCS["posthog_data_model"], DOCS["mixpanel_export"], DOCS["amplitude_export"],
            DOCS["ga4_bigquery_schema"]],
           "a user id (distinct_id, user_id, user_pseudo_id ...), an event name (event, event_name, "
           "event_type) and an event time (timestamp, time, event_time, event_timestamp)",
           _match_event_log, _normalize_events),
]
FORMATS_BY_SOURCE = {fmt.source: fmt for fmt in FORMATS}


def list_formats() -> List[Dict[str, Any]]:
    """Every supported format with its kind, vendor, confidence, key columns and docs."""
    return [fmt.describe() for fmt in FORMATS]


def detect(table: Table, kind: Optional[str] = None, source: Optional[str] = None) -> Tuple[Format, Match]:
    """Best matching format for a table, or ImportFormatError listing what was found."""
    if source is not None and source not in FORMATS_BY_SOURCE:
        raise ImportFormatError("Unknown --source %r. Supported: %s"
                                % (source, ", ".join(sorted(FORMATS_BY_SOURCE))))
    best: Optional[Tuple[Format, Match]] = None
    for fmt in FORMATS:
        if source is not None and fmt.source != source:
            continue
        if kind is not None and fmt.kind != kind:
            continue
        match = fmt.matcher(table)
        if match is None:
            continue
        if match.source != fmt.source:
            if source != fmt.source:
                continue
            match.source = fmt.source
        if best is None or match.score > best[1].score:
            best = (fmt, match)
    if best is None:
        wanted = source or kind or "any supported"
        raise ImportFormatError(
            "%s does not match %s export format." % (table.name, wanted),
            {"headers": table.headers[:60], "supported_formats": sorted(FORMATS_BY_SOURCE)},
        )
    return best


# ---------------------------------------------------------------------------
# Billing analytics
# ---------------------------------------------------------------------------


def _series_from_subscriptions(subs: List[Dict[str, Any]], last_month: str) -> Dict[str, Dict[str, Dict[str, float]]]:
    """{currency: {customer: {month: mrr}}}: MRR at each month end, from start to end dates."""
    out: Dict[str, Dict[str, Dict[str, float]]] = defaultdict(dict)
    for sub in subs:
        if sub["status"] in EXCLUDED_STATUSES or sub["mrr"] <= 0:
            continue
        first = month_key(sub["start"])
        if first > last_month:
            continue
        end = sub["end"]
        if end is None and sub["status"] in HOLD_STATUSES:
            end = month_from_key(last_month)          # paused or unpaid: not counted now
        series = out[sub["currency"]].setdefault(sub["customer"], {})
        for month in month_range(first, last_month):
            close = month_end(month)
            if sub["start"] > close:
                continue
            if end is not None and end <= close:
                break
            series[month] = series.get(month, 0.0) + sub["mrr"]
    return out


def _series_from_movements(moves: List[Dict[str, Any]], last_month: str,
                           notes: List[str]) -> Dict[str, Dict[str, Dict[str, float]]]:
    out: Dict[str, Dict[str, Dict[str, float]]] = defaultdict(dict)
    by_key: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
    for move in moves:
        by_key[(move["currency"], move["customer"])].append(move)
    clamped = 0
    for (currency, customer), items in by_key.items():
        items.sort(key=lambda m: m["date"])
        monthly: Dict[str, float] = defaultdict(float)
        for move in items:
            monthly[month_key(move["date"])] += move["amount"]
        running = 0.0
        series = {}
        for month in month_range(min(monthly), last_month):
            running += monthly.get(month, 0.0)
            if running < -0.005:
                clamped += 1
                running = 0.0
            if running > 0.005:
                series[month] = running
        out[currency][customer] = series
    if clamped:
        notes.append("%d customer histories went below zero (the export probably starts after "
                     "their first movement); those months were set to 0." % clamped)
    return out


def _bridge(series: Dict[str, Dict[str, float]], months: List[str]) -> List[Dict[str, Any]]:
    """Monthly MRR bridge from customer-month series (customer-level classification)."""
    customers = list(series)
    seen_before: Dict[str, bool] = {}
    first_month = months[0]
    # Customers active before the window start have been seen.
    for customer in customers:
        seen_before[customer] = any(month < first_month and value > 0 for month, value in series[customer].items())
    out = []
    previous_month = add_months(first_month, -1)
    for month in months:
        row = {"month": month, "starting_mrr": 0.0, "new_mrr": 0.0, "expansion_mrr": 0.0,
               "contraction_mrr": 0.0, "churned_mrr": 0.0, "reactivation_mrr": 0.0, "ending_mrr": 0.0,
               "customers_start": 0, "customers_new": 0, "customers_churned": 0,
               "customers_reactivated": 0, "customers_end": 0}
        for customer in customers:
            values = series[customer]
            before = values.get(previous_month, 0.0)
            now = values.get(month, 0.0)
            row["starting_mrr"] += before
            row["ending_mrr"] += now
            if before > 0:
                row["customers_start"] += 1
            if now > 0:
                row["customers_end"] += 1
            if before <= 0 < now:
                if seen_before[customer]:
                    row["reactivation_mrr"] += now
                    row["customers_reactivated"] += 1
                else:
                    row["new_mrr"] += now
                    row["customers_new"] += 1
            elif before > 0 >= now:
                row["churned_mrr"] += before
                row["customers_churned"] += 1
            elif now > before:
                row["expansion_mrr"] += now - before
            elif now < before:
                row["contraction_mrr"] += before - now
            if now > 0:
                seen_before[customer] = True
        out.append(row)
        previous_month = month
    return out


def _bridge_from_typed_movements(moves: List[Dict[str, Any]], currency: str, months: List[str],
                                 base: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Replace the bridge amounts with the vendor's own movement types (ChartMogul, generic)."""
    sums: Dict[Tuple[str, str], float] = defaultdict(float)
    for move in moves:
        if move["currency"] != currency:
            continue
        sums[(month_key(move["date"]), move["type"])] += move["amount"]
    field = {"new": "new_mrr", "expansion": "expansion_mrr", "contraction": "contraction_mrr",
             "churn": "churned_mrr", "reactivation": "reactivation_mrr"}
    for row in base:
        for kind, key in field.items():
            row[key] = abs(sums.get((row["month"], kind), 0.0))
    return base


def _finish_bridge(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    for row in rows:
        start = row["starting_mrr"]
        gains = row["new_mrr"] + row["expansion_mrr"] + row["reactivation_mrr"]
        losses = row["churned_mrr"] + row["contraction_mrr"]
        row["net_new_mrr"] = gains - losses
        row["logo_churn_rate"] = _rate(_ratio(row["customers_churned"], row["customers_start"]))
        row["gross_mrr_churn_rate"] = _rate(_ratio(losses, start))
        row["net_mrr_churn_rate"] = _rate(_ratio(losses - row["expansion_mrr"], start))
        row["quick_ratio"] = _round(_ratio(gains, losses), 2)
        for key in ("starting_mrr", "new_mrr", "expansion_mrr", "contraction_mrr", "churned_mrr",
                    "reactivation_mrr", "ending_mrr", "net_new_mrr"):
            row[key] = round(row[key], 2)
    return rows


def _ttm(series: Dict[str, Dict[str, float]], as_of: str, first_month: str) -> Dict[str, Any]:
    base = add_months(as_of, -12)
    if base < first_month:
        return {"as_of": as_of, "base_month": base, "grr": None, "nrr": None, "logo_retention": None,
                "reason": "needs data from %s; the data starts in %s" % (base, first_month)}
    starting = ending = kept = 0.0
    customers = retained = 0
    for values in series.values():
        then = values.get(base, 0.0)
        if then <= 0:
            continue
        now = values.get(as_of, 0.0)
        customers += 1
        starting += then
        ending += now
        kept += min(now, then)
        if now > 0:
            retained += 1
    if not customers:
        return {"as_of": as_of, "base_month": base, "grr": None, "nrr": None, "logo_retention": None,
                "reason": "no paying customers in %s" % base}
    return {
        "as_of": as_of, "base_month": base, "cohort_customers": customers,
        "starting_mrr": round(starting, 2), "ending_mrr": round(ending, 2),
        "grr": _rate(kept / starting), "nrr": _rate(ending / starting),
        "logo_retention": _rate(retained / customers),
        "definition": "customers paying at the end of %s; GRR = sum(min(MRR %s, MRR %s)) / MRR %s, "
                      "NRR = MRR %s / MRR %s, same customers" % (base, as_of, base, base, as_of, base),
    }


def _cohorts(series: Dict[str, Dict[str, float]], as_of: str, count: int = 12) -> List[Dict[str, Any]]:
    first_paid: Dict[str, str] = {}
    for customer, values in series.items():
        paid = [month for month, value in values.items() if value > 0]
        if paid:
            first_paid[customer] = min(paid)
    cohort_months = [add_months(as_of, -offset) for offset in range(count - 1, -1, -1)]
    out = []
    for cohort in cohort_months:
        members = [customer for customer, month in first_paid.items() if month == cohort]
        if not members:
            continue
        start_mrr = sum(series[c][cohort] for c in members)
        logos, revenue = [], []
        for offset, month in enumerate(month_range(cohort, as_of)):
            if offset > 12:
                break
            active = [series[c].get(month, 0.0) for c in members]
            logos.append(_rate(sum(1 for v in active if v > 0) / len(members)))
            revenue.append(_rate(sum(active) / start_mrr) if start_mrr else None)
        out.append({"cohort": cohort, "customers": len(members), "starting_mrr": round(start_mrr, 2),
                    "logo_retention": logos, "revenue_retention": revenue})
    return out


def _subscription_extras(subs: List[Dict[str, Any]], currency: str, as_of: str,
                         window: int) -> Dict[str, Any]:
    window_start = month_from_key(add_months(as_of, -(window - 1)))
    window_end = month_end(as_of)
    mine = [s for s in subs if s["currency"] == currency]
    status_counts = Counter(s["status"] for s in mine)

    def paying_at_window_end(sub: Dict[str, Any]) -> bool:
        # The same rule as _series_from_subscriptions, so the plan and
        # interval mix add up to the reported MRR for any --as-of month.
        if sub["status"] in EXCLUDED_STATUSES or sub["mrr"] <= 0 or sub["start"] > window_end:
            return False
        if sub["end"] is None:
            return sub["status"] not in HOLD_STATUSES
        return sub["end"] > window_end

    active = [s for s in mine if paying_at_window_end(s)]
    total_mrr = sum(s["mrr"] for s in active)
    plans: Dict[str, List[float]] = defaultdict(list)
    intervals: Dict[str, List[float]] = defaultdict(list)
    for sub in active:
        plans[sub["plan"] or "(no plan label)"].append(sub["mrr"])
        intervals[sub["interval"]].append(sub["mrr"])

    def mix(groups: Dict[str, List[float]], key: str) -> List[Dict[str, Any]]:
        rows = [{key: name, "active_subscriptions": len(values), "mrr": round(sum(values), 2),
                 "mrr_share": _rate(_ratio(sum(values), total_mrr))} for name, values in groups.items()]
        rows.sort(key=lambda r: -r["mrr"])
        return rows[:25]

    churn = {"voluntary": [0, 0.0], "involuntary": [0, 0.0], "other": [0, 0.0], "unknown": [0, 0.0]}
    for sub in mine:
        if sub["end"] is None or not (window_start <= sub["end"] <= window_end):
            continue
        if sub["status"] in EXCLUDED_STATUSES or sub["end"] <= sub["start"]:
            continue                # never paid (for example a trial that was not converted)
        bucket = churn[sub["churn_type"] or "unknown"]
        bucket[0] += 1
        bucket[1] += sub["mrr"]
    churn_out = {key: {"subscriptions": value[0], "mrr": round(value[1], 2)} for key, value in churn.items()}
    trials = [s for s in mine if s["trial_end"] is not None and window_start <= s["trial_end"] <= window_end
              and s["status"] != "trialing"]
    trial_block = None
    if any(s["trial_end"] for s in mine):
        converted = 0
        known = 0
        for sub in trials:
            if sub["converted"] is not None:
                known += 1
                converted += 1 if sub["converted"] else 0
                continue
            if sub["status"] in MRR_STATUSES or (sub["end"] and sub["end"] > sub["trial_end"] + timedelta(days=1)):
                converted += 1
            known += 1
        trial_block = {
            "trials_ended_in_window": len(trials), "converted": converted,
            "trial_to_paid_rate": _rate(_ratio(converted, known)),
            "currently_trialing": status_counts.get("trialing", 0),
            "basis": "converted = still paying, or ended more than a day after the trial ended"
                     + ("; Paddle's subscription_has_converted_from_trial when present"
                        if any(s["converted"] is not None for s in mine) else ""),
        }
    return {
        "status_counts": dict(status_counts),
        "past_due_subscriptions": sum(1 for s in active if s["past_due"]),
        "plan_mix": mix(plans, "plan"),
        "interval_mix": mix(intervals, "interval"),
        "churn_by_type": dict(churn_out, window_months=window,
                              basis="reason codes in the export (involuntary = payment failure)"),
        "trials": trial_block,
    }


def check_as_of(as_of: Optional[str], today: Optional[date] = None) -> None:
    """Reject an --as-of value that is not YYYY-MM or lies after the current month."""
    if not as_of:
        return
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", as_of):
        raise ImportOptionError("--as-of must be YYYY-MM, got %r" % as_of)
    this_month = month_key(today or date.today())
    if as_of > this_month:
        raise ImportOptionError("--as-of %s is in the future (this month is %s); figures for it would be "
                                "a projection, not data." % (as_of, this_month))


def summarize_billing(normalized: Dict[str, Any], as_of: Optional[str] = None,
                      months: int = DEFAULT_MONTHS) -> Dict[str, Any]:
    """MRR, bridge, churn and retention per currency from normalized billing records."""
    notes: List[str] = list(normalized.get("notes", []))
    check_as_of(as_of)
    subs = normalized.get("subscriptions")
    moves = normalized.get("movements")
    churn_observable = True
    if subs is not None:
        if not subs:
            raise NothingToImport("No usable subscription rows.")
        latest = normalized.get("latest_event") or max(d for s in subs for d in (s["signup"], s["start"]) if d)
        last = as_of or month_key(latest)
        series_by_currency = _series_from_subscriptions(subs, last)
        basis = "snapshot"
        held = sum(1 for s in subs if s["status"] in HOLD_STATUSES and s["end"] is None and s["mrr"] > 0)
        if held:
            notes.append("%d paused or unpaid subscription(s) are not counted as paying in %s; the export "
                         "does not say when they stopped paying, so they show as churned in %s."
                         % (held, last, last))
        first_month = min(month_key(s["start"]) for s in subs)
        notes.append(
            "History is rebuilt from a subscriptions snapshot: each subscription counts at its current "
            "price from its paid start to its end. Upgrades and downgrades are not visible, so "
            "expansion and contraction show as 0 and NRR only moves when customers add or end "
            "subscriptions.")
        if not any(s["end"] is not None or s["status"] in STOPPED_STATUSES for s in subs):
            churn_observable = False
            notes.append(
                "The file has no canceled or ended subscriptions. If the export was filtered to active "
                "subscriptions, churn, GRR, NRR and cohort retention cannot be measured from it (they "
                "would show no losses): export subscriptions with every status, or report these "
                "metrics as not measured.")
    elif moves is not None:
        if not moves:
            raise NothingToImport("No usable movement rows.")
        last = as_of or month_key(max(m["date"] for m in moves))
        series_by_currency = _series_from_movements(moves, last, notes)
        basis = "movements"
        first_month = min(month_key(m["date"]) for m in moves)
    else:
        series_by_currency = normalized["series"]
        last = as_of or normalized["last_month"]
        basis = "monthly_mrr"
        first_month = normalized["first_month"]
    if as_of and as_of < first_month:
        raise ImportOptionError("--as-of %s is before the first month in the data (%s)." % (as_of, first_month))
    if not as_of:
        notes.append(
            "Figures are at the end of %s, the latest month in the data. If the export was taken before "
            "%s ended, that month is incomplete (its new and churned MRR are partial); rerun with "
            "--as-of %s to report on the last full month." % (last, last, add_months(last, -1)))
    months = max(1, min(int(months), MAX_MONTHS))
    window = [m for m in month_range(add_months(last, -(months - 1)), last) if m >= first_month] or [last]
    by_currency: Dict[str, Any] = {}
    for currency, series in sorted(series_by_currency.items()):
        bridge = _bridge(series, window)
        if basis == "movements" and normalized.get("typed"):
            bridge = _bridge_from_typed_movements(moves, currency, window, bridge)
        while len(bridge) > 1 and not any(bridge[0][key] for key in (
                "starting_mrr", "ending_mrr", "churned_mrr", "new_mrr", "reactivation_mrr")):
            bridge.pop(0)               # months before this currency had any revenue
        bridge = _finish_bridge(bridge)
        current_mrr = sum(values.get(last, 0.0) for values in series.values())
        paying = sum(1 for values in series.values() if values.get(last, 0.0) > 0)
        block: Dict[str, Any] = {
            "current": {
                "month": last, "mrr": round(current_mrr, 2), "arr": round(current_mrr * 12, 2),
                "paying_customers": paying, "arpa": _round(_ratio(current_mrr, paying), 2),
            },
            "monthly": bridge,
            "ttm_retention": _ttm(series, last, first_month),
            "cohorts": _cohorts(series, last),
        }
        last_full = [row for row in bridge if row["customers_start"]]
        if last_full:
            churned = sum(r["customers_churned"] for r in last_full)
            started = sum(r["customers_start"] for r in last_full)
            losses = sum(r["churned_mrr"] + r["contraction_mrr"] for r in last_full)
            start_mrr = sum(r["starting_mrr"] for r in last_full)
            block["window_averages"] = {
                "months": len(last_full),
                "avg_monthly_logo_churn_rate": _rate(_ratio(churned, started)),
                "avg_monthly_gross_mrr_churn_rate": _rate(_ratio(losses, start_mrr)),
                "basis": "sum of churn over the window / sum of starting values (customer-month weighted)",
            }
        if subs is not None:
            block.update(_subscription_extras(subs, currency, last, months))
        by_currency[currency] = block
    if not by_currency:
        statuses = dict(Counter(s["status"] for s in subs)) if subs is not None else {}
        raise NothingToImport("No paying customers in the file (only trials, incomplete signups or "
                              "zero amounts).", {"status_counts": statuses})
    if len(by_currency) > 1:
        notes.append("The data has %d currencies; each is reported on its own and never summed. "
                     "Convert with your own exchange rates if you need one total." % len(by_currency))
    # Amounts in different currencies cannot be compared, so the primary
    # currency is the one with the most paying customers.
    primary = max(by_currency, key=lambda c: (by_currency[c]["current"]["paying_customers"],
                                              by_currency[c]["current"]["mrr"])) if by_currency else None
    return {
        "as_of": last, "history_basis": basis,
        "expansion_contraction_observable": basis != "snapshot",
        "churn_observable": churn_observable,
        "months_in_data": len(month_range(first_month, last)),
        "currencies": sorted(by_currency), "primary_currency": primary,
        "by_currency": by_currency, "notes": notes,
        "definitions": {
            "mrr": "monthly recurring revenue at month end; annual and other intervals are divided into months",
            "logo_churn_rate": "customers lost in the month / paying customers at the start of the month",
            "gross_mrr_churn_rate": "(churned + contraction MRR) / starting MRR",
            "net_mrr_churn_rate": "(churned + contraction - expansion MRR) / starting MRR; negative means net expansion",
            "quick_ratio": "(new + expansion + reactivation) / (churned + contraction)",
            "primary_currency": "the currency with the most paying customers (amounts are never compared across currencies)",
            "statuses_counted_as_paying": sorted(MRR_STATUSES),
        },
    }


def summarize_invoices(normalized: Dict[str, Any], as_of: Optional[str] = None,
                       months: int = DEFAULT_MONTHS) -> Dict[str, Any]:
    check_as_of(as_of)
    invoices = normalized["invoices"]
    if not invoices:
        raise NothingToImport("No usable invoice rows.")
    last = as_of or month_key(max(i["date"] for i in invoices))
    window = month_range(add_months(last, -(max(1, min(int(months), MAX_MONTHS)) - 1)), last)
    by_currency: Dict[str, Any] = {}
    for currency in sorted({i["currency"] for i in invoices}):
        mine = [i for i in invoices if i["currency"] == currency and month_key(i["date"]) in window]
        monthly = []
        for month in window:
            rows = [i for i in mine if month_key(i["date"]) == month]
            paid = [i for i in rows if i["status"] == "paid"]
            monthly.append({
                "month": month, "invoices": len(rows), "paid": len(paid),
                "amount_paid": round(sum(i["amount_paid"] or (i["total"] or 0.0) for i in paid), 2),
                "billed_total": round(sum(i["total"] or 0.0 for i in rows if i["status"] != "void"), 2),
            })
        while len(monthly) > 1 and not monthly[0]["invoices"]:
            monthly.pop(0)
        finalized = [i for i in mine if i["status"] not in ("void",)]
        retried = [i for i in finalized if (i["attempts"] or 0) > 1]
        failed = [i for i in finalized if (i["attempts"] or 0) > 1 or i["status"] in ("uncollectible",)]
        recovered = [i for i in retried if i["status"] == "paid"]
        by_currency[currency] = {
            "monthly": monthly,
            "status_counts": dict(Counter(i["status"] for i in mine)),
            "payment_failure_rate": _rate(_ratio(len(failed), len(finalized)))
            if any(i["attempts"] is not None for i in finalized) or failed else None,
            "recovery_rate": _rate(_ratio(len(recovered), len(retried))) if retried else None,
            "open_amount_due": round(sum(i["amount_due"] or 0.0 for i in mine if i["status"] == "open"), 2),
            "basis": "failed = more than one payment attempt or uncollectible; recovered = paid after a retry",
        }
    return {"as_of": last, "currencies": sorted(by_currency), "by_currency": by_currency,
            "notes": list(normalized.get("notes", [])) + [
                "Invoices show billings and payment health, not MRR. Annual invoices land in one month."]}


# ---------------------------------------------------------------------------
# Analytics summaries
# ---------------------------------------------------------------------------


def summarize_funnel(normalized: Dict[str, Any]) -> Dict[str, Any]:
    segments = []
    for name, steps in normalized["segments"].items():
        if len(steps) < 2:
            continue
        first = steps[0]["count"]
        out_steps = []
        biggest = None
        for index, step in enumerate(steps):
            previous = steps[index - 1]["count"] if index else None
            from_previous = _ratio(step["count"], previous) if index else 1.0
            drop = (previous - step["count"]) if index else 0.0
            out_steps.append({
                "step": index + 1, "name": step["name"], "count": round(step["count"], 2),
                "conversion_from_previous": _rate(from_previous),
                "conversion_from_start": _rate(_ratio(step["count"], first)),
                "drop_off": round(drop, 2) if index else 0,
                "drop_off_rate": _rate(1 - from_previous) if index and from_previous is not None else None,
                "time_to_convert_seconds": step["time_to_convert_seconds"],
            })
            if index and from_previous is not None and (biggest is None or 1 - from_previous > biggest[2]):
                biggest = (index, index + 1, 1 - from_previous)
        segments.append({
            "segment": name, "steps": out_steps,
            "overall_conversion": _rate(_ratio(steps[-1]["count"], first)),
            "biggest_drop": {"from_step": biggest[0], "to_step": biggest[1], "drop_off_rate": _rate(biggest[2])}
            if biggest else None,
        })
    if not segments:
        raise NothingToImport("The funnel has fewer than two readable steps.")
    increasing = any(s["steps"][i]["count"] > s["steps"][i - 1]["count"] for s in segments
                     for i in range(1, len(s["steps"])))
    notes = list(normalized.get("notes", []))
    if increasing:
        notes.append("Some steps have more users than the step before, which happens in open funnels "
                     "(users can enter at any step) or when the rows are not in funnel order.")
    return {"segments": segments[:50], "segment_count": len(segments), "notes": notes,
            "definitions": {"conversion_from_previous": "step count / previous step count",
                            "conversion_from_start": "step count / first step count"}}


def summarize_retention(normalized: Dict[str, Any]) -> Dict[str, Any]:
    cohorts = normalized["cohorts"]
    if not cohorts:
        raise NothingToImport("No readable cohort rows.")
    unit = normalized.get("unit_hint")
    starts = [c["start"] for c in cohorts if c["start"]]
    if not unit and len(starts) >= 2:
        gaps = sorted((b - a).days for a, b in zip(sorted(starts), sorted(starts)[1:]) if (b - a).days > 0)
        if gaps:
            gap = gaps[len(gaps) // 2]
            unit = "day" if gap == 1 else "week" if gap == 7 else "month" if 28 <= gap <= 31 else None
    periods = normalized["periods"]
    average = []
    for position, period in enumerate(periods):
        reached = [c for c in cohorts if position < len(c["rates"]) and c["rates"][position] is not None]
        if not reached:
            continue
        sized = [c for c in reached if c["size"]]
        if sized and len(sized) == len(reached):
            rate = sum(c["rates"][position] * c["size"] for c in sized) / sum(c["size"] for c in sized)
            basis = "size_weighted"
        else:
            rate = sum(c["rates"][position] for c in reached) / len(reached)
            basis = "unweighted"
        average.append({"period": period, "rate": _rate(rate), "cohorts": len(reached), "basis": basis})
    return {
        "period_unit": unit or "period", "value_type": normalized["value_type"],
        "cohorts": [{"label": c["label"], "start": c["start"].isoformat() if c["start"] else None,
                     "size": _round(c["size"], 2), "rates": [_rate(r) for r in c["rates"]]}
                    for c in cohorts[:60]],
        "cohort_count": len(cohorts), "average": average, "notes": list(normalized.get("notes", [])),
        "definitions": {"rate": "share of the cohort active in that period (period 0 is the cohort itself)"},
    }


def summarize_search(normalized: Dict[str, Any], top: int = DEFAULT_TOP) -> Dict[str, Any]:
    rows = normalized["rows"]
    if not rows:
        raise NothingToImport("No readable Search Console rows.")
    clicks = sum(r["clicks"] for r in rows)
    impressions = sum(r["impressions"] for r in rows)
    positioned = [r for r in rows if r["position"] is not None and r["impressions"]]
    weighted_position = (sum(r["position"] * r["impressions"] for r in positioned)
                         / sum(r["impressions"] for r in positioned)) if positioned else None
    dimension = normalized["dimension"]
    if dimension == "date":
        ordered = sorted(rows, key=lambda r: r["key"])
    else:
        ordered = sorted(rows, key=lambda r: (-r["impressions"], -r["clicks"], r["key"]))
    top = max(1, min(int(top), 5000))
    return {
        "dimension": dimension, "row_count": len(rows),
        "totals": {"clicks": clicks, "impressions": impressions, "ctr": _rate(_ratio(clicks, impressions)),
                   "position_impression_weighted": _round(weighted_position, 2)},
        "rows": [{"key": r["key"], "clicks": r["clicks"], "impressions": r["impressions"],
                  "ctr": _rate(r["ctr"]), "position": _round(r["position"], 2)} for r in ordered[:top]],
        "rows_shown": min(top, len(rows)),
        "notes": list(normalized.get("notes", [])) + [
            "Search Console exports '~' and '-' cells as 0, and the UI export holds at most the rows "
            "the report shows; totals here are sums of the exported rows, not the property total."],
    }


# Event logs ------------------------------------------------------------------

DEFAULT_WINDOW_DAYS = 30
MAX_RETENTION_PERIODS = 26


def _median(values: List[float]) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    return ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2.0


def _event_retention(per_user: Dict[str, List[Tuple[datetime, str]]], last_day: date,
                     cohort_event: Optional[str], active_event: Optional[str], period: str,
                     notes: List[str]) -> Optional[Dict[str, Any]]:
    days = 7 if period == "week" else 1
    cohorts: Dict[date, List[Tuple[str, datetime]]] = defaultdict(list)
    for user, items in per_user.items():
        start = next((when for when, name in items if cohort_event is None or name == cohort_event), None)
        if start is None:
            continue
        day = start.date()
        cohorts[day - timedelta(days=day.weekday()) if period == "week" else day].append((user, start))
    rows = []
    for key in sorted(cohorts):
        members = cohorts[key]
        joined_last = key + timedelta(days=days - 1)        # the last day a member can have joined
        # Period k (days [k*days, k*days + days - 1] after a user's first event)
        # is complete for every member once joined_last + (k + 1) * days - 1 has passed.
        max_period = min(((last_day - joined_last).days + 1) // days - 1, MAX_RETENTION_PERIODS)
        if max_period < 0:
            continue
        active: List[set] = [set() for _ in range(max_period + 1)]
        for user, start in members:
            for when, name in per_user[user]:
                if when < start or (active_event is not None and name != active_event):
                    continue
                offset = (when - start).days // days
                if offset <= max_period:
                    active[offset].add(user)
        size = len(members)
        rows.append({"label": key.isoformat(), "start": key, "size": float(size),
                     "rates": [len(users) / float(size) for users in active],
                     "counts": [float(len(users)) for users in active]})
    if not rows:
        notes.append("The events cover less than one full %s after the first cohort, so retention was not "
                     "computed." % period)
        return None
    periods = list(range(max(len(row["rates"]) for row in rows)))
    retention = summarize_retention({"cohorts": rows, "value_type": "count", "periods": periods,
                                     "unit_hint": period, "notes": []})
    retention["definitions"] = {
        "cohort": "users by the %s of their first %s" % (period, "event" if cohort_event is None
                                                         else "%r event" % cohort_event),
        "rate": "share of the cohort with %s in period k, where period k is days [%d*k, %d*k + %d] after "
                "the user's first event; only periods complete for the whole cohort are shown"
                % ("any event" if active_event is None else "a %r event" % active_event, days, days, days - 1),
    }
    return retention


def _event_funnel(per_user: Dict[str, List[Tuple[datetime, str]]], steps: List[str],
                  window_days: int) -> Dict[str, Any]:
    window = timedelta(days=window_days)
    counts = [0] * len(steps)
    gaps: List[List[float]] = [[] for _ in steps]
    to_last: List[float] = []
    for items in per_user.values():
        position = next((i for i, (_when, name) in enumerate(items) if name == steps[0]), None)
        if position is None:
            continue
        counts[0] += 1
        start = previous = items[position][0]
        for step_index, step in enumerate(steps[1:], 1):
            position = next((i for i in range(position + 1, len(items))
                             if items[i][1] == step and items[i][0] <= start + window), None)
            if position is None:
                break
            counts[step_index] += 1
            gaps[step_index].append((items[position][0] - previous).total_seconds())
            previous = items[position][0]
        else:
            to_last.append((previous - start).total_seconds())
    funnel = summarize_funnel({"segments": OrderedDict([("all", [
        {"name": step, "count": float(counts[i]), "time_to_convert_seconds": _median(gaps[i]) if i else None,
         "time_raw": None} for i, step in enumerate(steps)])]), "notes": []})
    funnel["median_time_to_last_step_seconds"] = _median(to_last)
    funnel["conversion_window_days"] = window_days
    funnel["definitions"].update({
        "funnel": "users whose first %r event is followed, in this order, by each next step within %d days"
                  % (steps[0], window_days),
        "time_to_convert_seconds": "median time from the previous step, among users who reached the step",
        "median_time_to_last_step_seconds": "median time from the first to the last step (time to activation "
                                            "when the last step is the activation event)",
    })
    return funnel


def summarize_events(normalized: Dict[str, Any], steps: Optional[Sequence[str]] = None,
                     window_days: int = DEFAULT_WINDOW_DAYS, cohort_event: Optional[str] = None,
                     active_event: Optional[str] = None, period: str = "week",
                     top: int = 25) -> Dict[str, Any]:
    """Event overview, cohort retention and (with steps) an ordered funnel from a raw event log."""
    events = normalized["events"]
    if not events:
        raise NothingToImport("No readable event rows.")
    if period not in ("week", "day"):
        raise ImportOptionError("--period must be week or day, got %r" % period)
    if window_days < 1:
        raise ImportOptionError("--window-days must be 1 or more")
    steps = [step.strip() for step in (steps or []) if step and step.strip()]
    if len(steps) == 1:
        raise ImportOptionError("A funnel needs at least two --step events.")
    names = Counter(name for _u, name, _t in events)
    for option, wanted in [("--cohort-event", cohort_event), ("--active-event", active_event)] + \
            [("--step", step) for step in steps]:
        if wanted and wanted not in names:
            raise ImportOptionError("%s %r is not an event in the file." % (option, wanted),
                                    {"most_frequent_events": [n for n, _c in names.most_common(20)]})
    per_user: Dict[str, List[Tuple[datetime, str]]] = defaultdict(list)
    users_by_event: Dict[str, set] = defaultdict(set)
    for user, name, when in events:
        per_user[user].append((when, name))
        users_by_event[name].add(user)
    for items in per_user.values():
        items.sort()
    first = min(when for _u, _n, when in events)
    last = max(when for _u, _n, when in events)
    notes = list(normalized.get("notes", []))
    out: Dict[str, Any] = {
        "events": {
            "event_count": len(events), "user_count": len(per_user),
            "first_event": first.isoformat(), "last_event": last.isoformat(),
            "distinct_event_names": len(names),
            "top_events": [{"event": name, "count": count, "users": len(users_by_event[name])}
                           for name, count in names.most_common(max(1, min(int(top), 200)))],
            "notes": notes,
        },
    }
    retention = _event_retention(per_user, last.date(), cohort_event, active_event, period, notes)
    if retention is not None:
        out["retention"] = retention
    if steps:
        out["funnel"] = _event_funnel(per_user, steps, int(window_days))
    else:
        notes.append("Pass --step <event> two or more times (in funnel order) for step conversion and time "
                     "to activation.")
    notes.append("User ids are hashed in memory and only counted; the most frequent event names are listed "
                 "so you can pick funnel steps.")
    return out


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

_MEMBER_PRIORITY = ("queries", "pages", "subscriptions", "subscription", "dates", "countries", "devices")


def load(path: str, kind: Optional[str] = None, source: Optional[str] = None, member: Optional[str] = None,
         amount_unit: str = "auto", currency: Optional[str] = None, values: str = "auto") -> Dict[str, Any]:
    """Read and normalize one export. Returns format info, row counts and normalized records.

    The records hold hashed customer ids, never names or emails. Raises
    ImportFormatError (unknown or unreadable format) or NothingToImport.
    """
    if kind is not None and kind not in KINDS:
        raise ImportFormatError("--kind must be one of %s, got %r" % (", ".join(KINDS), kind))
    if amount_unit not in ("auto", "major", "minor"):
        raise ImportFormatError("--amount-unit must be auto, major or minor")
    tables = read_tables(path, member)
    if len(tables) > 1:
        def priority(table: Table) -> int:
            stem = os.path.splitext(table.name)[0].lower()
            return _MEMBER_PRIORITY.index(stem) if stem in _MEMBER_PRIORITY else len(_MEMBER_PRIORITY)
        tables.sort(key=priority)
    errors = []
    chosen = None
    for table in tables:
        try:
            chosen = (table,) + detect(table, kind, source)
            break
        except ImportFormatError as exc:
            errors.append(exc)
    if chosen is None:
        if len(tables) == 1:
            raise errors[0]
        raise ImportFormatError(
            "None of the %d CSV files in %s matches a supported format." % (len(tables), os.path.basename(path)),
            {"members": [t.name for t in tables], "supported_formats": sorted(FORMATS_BY_SOURCE)})
    table, fmt, match = chosen
    options = {"amount_unit": amount_unit, "currency": normalize_currency(currency) if currency else None,
               "values": values}
    normalized = fmt.normalizer(table, match, options)
    skips: Skips = normalized.pop("skips")
    column_map = {field: table.headers[index] for field, index in match.columns.items()}
    if "months" in match.extra:
        column_map["months"] = "%d month columns (%s to %s)" % (
            len(match.extra["months"]), min(match.extra["months"].values()), max(match.extra["months"].values()))
    if "steps" in match.extra:
        column_map["steps"] = [table.headers[i] for i in match.extra["steps"]]
    if "periods" in match.extra:
        column_map["periods"] = [table.headers[i] for _p, i, _u in match.extra["periods"]]
    format_info = {
        "source": fmt.source, "kind": fmt.kind, "vendor": fmt.vendor, "label": fmt.label,
        "confidence": fmt.confidence, "docs": fmt.docs, "column_map": column_map,
        "vendor_guess": match.extra.get("vendor_guess"),
        "pii_columns_ignored": table.pii_headers(match.columns.values()),
    }
    if "amount_unit" in normalized:
        format_info["amount_unit"] = normalized.pop("amount_unit")
        format_info["amount_unit_basis"] = normalized.pop("amount_unit_basis")
    if "dimension" in match.extra:
        format_info["dimension"] = match.extra["dimension"]
    if table.more_sections:
        normalized.setdefault("notes", []).append(
            "The file has more tables after the first one ('#' section lines); only the first was read.")
    other_members = [t.name for t in tables if t is not table]
    if other_members:
        normalized.setdefault("notes", []).append(
            "The zip also holds %s; pass --member <name> to read one of them." % ", ".join(other_members))
    return {
        "file": dict(table.describe(), path_name=os.path.basename(path)),
        "format": format_info,
        "rows": {"data_rows": len(table.rows), "unreadable": skips.unreadable_count(),
                 "skipped": skips.as_dict()},
        "preamble": table.preamble[:10],
        "normalized": normalized,
    }


def summarize(loaded: Dict[str, Any], as_of: Optional[str] = None, months: int = DEFAULT_MONTHS,
              top: int = DEFAULT_TOP, steps: Optional[Sequence[str]] = None,
              window_days: int = DEFAULT_WINDOW_DAYS, cohort_event: Optional[str] = None,
              active_event: Optional[str] = None, period: str = "week") -> Dict[str, Any]:
    """Aggregates for a load() result, keyed by kind (billing, invoices, funnel, retention, search).

    An event log returns "events" plus "retention" and, with steps, "funnel".
    """
    kind = loaded["format"]["kind"]
    normalized = loaded["normalized"]
    if kind == "events":
        return summarize_events(normalized, steps, window_days, cohort_event, active_event, period,
                                25 if top == DEFAULT_TOP else top)
    if kind == "billing":
        return {"billing": summarize_billing(normalized, as_of, months)}
    if kind == "invoices":
        return {"invoices": summarize_invoices(normalized, as_of, months)}
    if kind == "funnel":
        return {"funnel": summarize_funnel(normalized)}
    if kind == "retention":
        return {"retention": summarize_retention(normalized)}
    return {"search": summarize_search(normalized, top)}


def analyze(path: str, kind: Optional[str] = None, source: Optional[str] = None, member: Optional[str] = None,
            amount_unit: str = "auto", currency: Optional[str] = None, values: str = "auto",
            as_of: Optional[str] = None, months: int = DEFAULT_MONTHS, top: int = DEFAULT_TOP,
            steps: Optional[Sequence[str]] = None, window_days: int = DEFAULT_WINDOW_DAYS,
            cohort_event: Optional[str] = None, active_event: Optional[str] = None,
            period: str = "week") -> Dict[str, Any]:
    """load() + summarize(): a JSON-ready dict with no record-level data.

    Email addresses in any text taken from the file (segments, step and plan
    names, cohort labels, preamble lines) are replaced by salted tags.
    """
    check_as_of(as_of)
    loaded = load(path, kind, source, member, amount_unit, currency, values)
    result = {key: loaded[key] for key in ("file", "format", "rows", "preamble")}
    summary = summarize(loaded, as_of, months, top, steps, window_days, cohort_event, active_event, period)
    result.update(summary)
    notes = []
    for block in summary.values():
        notes.extend(block.pop("notes", []))
    result["notes"] = notes
    return scrub(result)


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------


def _human(envelope: Dict[str, Any]) -> str:
    lines = []
    fmt = envelope.get("format") or {}
    if fmt:
        lines.append("Format: %s (%s, %s confidence)" % (fmt.get("label"), fmt.get("vendor"), fmt.get("confidence")))
    rows = envelope.get("rows") or {}
    if rows:
        lines.append("Rows: %s data rows, %s unreadable" % (rows.get("data_rows"), rows.get("unreadable")))
    billing = envelope.get("billing")
    if billing:
        for currency, block in billing["by_currency"].items():
            current = block["current"]
            lines.append("%s MRR at end of %s: %.2f from %d paying customers"
                         % (currency, current["month"], current["mrr"], current["paying_customers"]))
            ttm = block["ttm_retention"]
            if ttm.get("nrr") is not None:
                lines.append("  TTM NRR %.1f%%, GRR %.1f%% (base %s)" % (ttm["nrr"] * 100, ttm["grr"] * 100,
                                                                     ttm["base_month"]))
    events = envelope.get("events")
    if events:
        lines.append("Events: %d from %d users, %s to %s" % (
            events["event_count"], events["user_count"], events["first_event"][:10], events["last_event"][:10]))
    funnel = envelope.get("funnel")
    if funnel:
        for segment in funnel["segments"][:5]:
            lines.append("Funnel %s: %d steps, overall conversion %s" % (
                segment["segment"], len(segment["steps"]), segment["overall_conversion"]))
    retention = envelope.get("retention")
    if retention:
        lines.append("Retention: %d cohorts, unit %s" % (retention["cohort_count"], retention["period_unit"]))
    search = envelope.get("search")
    if search:
        totals = search["totals"]
        lines.append("Search Console (%s): %d rows, %s clicks, %s impressions"
                     % (search["dimension"], search["row_count"], totals["clicks"], totals["impressions"]))
    if envelope.get("formats"):
        for item in envelope["formats"]:
            lines.append("%-26s %-9s %-22s %s" % (item["source"], item["kind"], item["vendor"], item["confidence"]))
    for note in envelope.get("notes", []):
        lines.append("Note: " + note)
    lines.append("Use --json for the full result.")
    return "\n".join(lines)


def build_parser() -> cli.ArgumentParser:
    parser = cli.build_parser(
        "Read a billing or analytics export (Stripe, Paddle, Chargebee, ChartMogul, GA4, PostHog, "
        "Mixpanel, Amplitude, Search Console or a generic CSV) and print PII-free aggregates.",
        input_help="the downloaded export: .csv, .tsv or .zip",
        prog="importers.py", demo=False, timeout=False,
    )
    parser.add_argument("--kind", choices=KINDS, help="only try formats of this kind")
    parser.add_argument("--source", metavar="FORMAT", help="force a format id (see --list-formats)")
    parser.add_argument("--member", metavar="NAME", help="CSV file to read inside a .zip")
    parser.add_argument("--amount-unit", choices=("auto", "major", "minor"), default="auto",
                        help="amounts are in major units (49.00) or minor units/cents (4900); default auto")
    parser.add_argument("--currency", metavar="CODE", help="currency for files without a currency column")
    parser.add_argument("--values", choices=("auto", "percent", "count", "fraction"), default="auto",
                        help="what retention cells hold (default auto)")
    parser.add_argument("--as-of", metavar="YYYY-MM", help="month to report on (default: latest month in the file)")
    parser.add_argument("--months", type=int, default=DEFAULT_MONTHS,
                        help="months of MRR bridge to return (1-%d, default %d)" % (MAX_MONTHS, DEFAULT_MONTHS))
    parser.add_argument("--top", type=int, default=DEFAULT_TOP,
                        help="Search Console rows to return, by impressions (default %d; event logs list "
                             "25 event names unless set)" % DEFAULT_TOP)
    parser.add_argument("--step", action="append", metavar="EVENT", dest="steps",
                        help="event log: a funnel step event name; repeat in funnel order (two or more)")
    parser.add_argument("--window-days", type=int, default=DEFAULT_WINDOW_DAYS,
                        help="event log: days from step 1 to finish the funnel (default %d)" % DEFAULT_WINDOW_DAYS)
    parser.add_argument("--cohort-event", metavar="EVENT",
                        help="event log: cohorts start at a user's first EVENT (default: any event)")
    parser.add_argument("--active-event", metavar="EVENT",
                        help="event log: a user is retained in a period with this EVENT (default: any event)")
    parser.add_argument("--period", choices=("week", "day"), default="week",
                        help="event log: retention period (default week)")
    parser.add_argument("--list-formats", action="store_true", help="print the supported formats and exit")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    run = cli.Run("importers", args)
    if args.list_formats:
        return run.emit({"formats": list_formats(), "verified_on": VERIFIED_ON}, human=_human)
    if not args.input:
        return run.fail(cli.STATUS_USAGE, "No input file. Pass the downloaded export, or --list-formats.")
    if args.input == "-" or (not os.path.isfile(args.input) and cli.looks_like_url(args.input)
                             and not args.input.lower().endswith((".zip", ".csv", ".tsv"))):
        return run.fail(cli.STATUS_USAGE, "Pass a downloaded export file path (not a URL or stdin).")
    if not os.path.isfile(args.input):
        return run.fail(cli.STATUS_USAGE, "File not found: %s" % args.input)
    try:
        result = analyze(args.input, args.kind, args.source, args.member, args.amount_unit, args.currency,
                         args.values, args.as_of, args.months, args.top, args.steps, args.window_days,
                         args.cohort_event, args.active_event, args.period)
    except NothingToImport as exc:
        return run.fail(cli.STATUS_NOTHING, scrub(str(exc)), scrub(exc.details))
    except ImportOptionError as exc:
        return run.fail(cli.STATUS_USAGE, scrub(str(exc)), scrub(exc.details))
    except ImportFormatError as exc:
        data = dict(exc.details)
        data.setdefault("supported_formats", sorted(FORMATS_BY_SOURCE))
        run.note("Run with --list-formats to see each format's columns, or save the data in the "
                 "generic_subscriptions / generic_movements schema described in --list-formats.")
        return run.fail(cli.STATUS_USAGE, scrub(str(exc)), scrub(data))
    for note in result.pop("notes", []):
        run.note(note)
    rows = result["rows"]
    status = cli.STATUS_OK
    if rows["data_rows"] and rows["unreadable"] / float(rows["data_rows"]) > UNREADABLE_PARTIAL_SHARE:
        run.error("%d of %d rows could not be read (%s)." % (
            rows["unreadable"], rows["data_rows"],
            ", ".join("%s: %d" % item for item in rows["skipped"]["unreadable"].items())))
        status = cli.STATUS_PARTIAL
    elif rows["unreadable"]:
        run.note("%d row(s) could not be read and were skipped." % rows["unreadable"])
    return run.emit(result, status=status, human=_human)


__all__ = [
    "VERIFIED_ON", "DOCS", "KINDS", "FORMATS", "ImportFormatError", "NothingToImport", "Table",
    "parse_number", "parse_rate", "parse_date", "parse_duration", "date_order", "normalize_header",
    "normalize_currency", "currency_exponent", "from_minor", "is_pii_header", "pseudonym", "scrub",
    "check_as_of", "ImportOptionError",
    "parse_table", "read_tables", "detect", "list_formats", "load", "summarize", "analyze",
    "summarize_billing", "summarize_invoices", "summarize_funnel", "summarize_retention",
    "summarize_search", "summarize_events", "parse_datetime", "month_key", "add_months", "main",
]


if __name__ == "__main__":
    sys.exit(main())
