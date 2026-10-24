"""PageSpeed Insights (v5) client focused on Core Web Vitals field data.

Why field data
    Google's Core Web Vitals assessment uses the 75th percentile of real
    Chrome users (CrUX) for LCP, INP and CLS. PSI returns that as
    ``loadingExperience`` (this URL) and ``originLoadingExperience`` (the
    whole site). INP exists only there: a Lighthouse navigation run has no
    INP audit, so pass/fail must never be judged from lab data. This module
    reads field data first and reports Lighthouse lab numbers only as
    diagnostics.

Field source order
    1. loadingExperience, when it has metrics. If PSI marks it
       ``origin_fallback`` the data is really origin-level and is labelled so.
    2. originLoadingExperience.
    3. Neither: status 'no_field_data' (too little Chrome traffic). Lab
       diagnostics are still returned, but no Core Web Vitals verdict.

API key
    Read from PAGESPEED_API_KEY, then GOOGLE_API_KEY (which Gemini SDKs
    also use, so it may be a key without the PSI API enabled). The key is
    sent in the X-Goog-Api-Key header, never in the URL, and never appears
    in the returned dict or error text. Keyless calls share a small daily
    quota and often get HTTP 429; a free key fixes that.

Usage:

    from _growthkit import psi
    result = psi.fetch("https://example.com", strategy="mobile")
    if result["status"] == "ok":
        print(result["field"]["cwv_assessment"])

Tests inject ``session`` (anything with ``request(method, url, **kwargs)``),
``env`` and ``sleep``; ``parse_response`` is pure and works on saved JSON.
"""

from __future__ import annotations

import os
import re
import time
import warnings

with warnings.catch_warnings():
    warnings.filterwarnings("ignore", message=".*OpenSSL.*")
    try:
        import requests
    except ImportError:  # pragma: no cover - only hit when requests is missing
        requests = None

if requests is not None:
    _NETWORK_ERRORS = (requests.RequestException, OSError)
else:  # pragma: no cover
    _NETWORK_ERRORS = (OSError,)


PSI_ENDPOINT = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
KEY_ENV_VARS = ("PAGESPEED_API_KEY", "GOOGLE_API_KEY")
STRATEGIES = ("mobile", "desktop")
DEFAULT_TIMEOUT = 90.0  # a PSI run loads the page in Lighthouse; 20-60 s is normal

# (short name, PSI metric key(s), unit, good if <=, poor if >)
# Thresholds: https://web.dev/articles/vitals (LCP, INP, CLS) and
# https://web.dev/articles/fcp, https://web.dev/articles/ttfb.
CORE_METRICS = (
    ("lcp", ("LARGEST_CONTENTFUL_PAINT_MS",), "ms", 2500, 4000),
    ("inp", ("INTERACTION_TO_NEXT_PAINT", "EXPERIMENTAL_INTERACTION_TO_NEXT_PAINT"), "ms", 200, 500),
    ("cls", ("CUMULATIVE_LAYOUT_SHIFT_SCORE",), "unitless", 0.1, 0.25),
)
OTHER_FIELD_METRICS = (
    ("fcp", ("FIRST_CONTENTFUL_PAINT_MS",), "ms", 1800, 3000),
    ("ttfb", ("EXPERIMENTAL_TIME_TO_FIRST_BYTE",), "ms", 800, 1800),
)

# PSI reports CLS percentiles and distribution bounds multiplied by 100
# (percentile 5 means CLS 0.05).
CLS_SCALE = 100.0

PSI_CATEGORY_MAP = {"FAST": "good", "AVERAGE": "needs_improvement", "SLOW": "poor"}

LAB_NOTE = (
    "Lab data from a single Lighthouse run. Use it to diagnose causes, not to "
    "pass or fail Core Web Vitals (Lighthouse has no INP)."
)
NO_FIELD_NOTE = (
    "No CrUX field data for this URL or its origin (too little Chrome traffic). "
    "Core Web Vitals pass/fail cannot be stated; lab numbers are diagnostics only."
)
ORIGIN_NOTE = (
    "No URL-level field data; showing origin-level data (all pages of the site), "
    "not this page alone."
)
NO_KEY_NOTE = (
    "No API key set: keyless PageSpeed Insights calls share a small daily quota and "
    "often fail with HTTP 429. A free key fixes this; set PAGESPEED_API_KEY."
)

# Lighthouse audit id -> lab diagnostic name
LAB_AUDITS = (
    ("lcp_ms", "largest-contentful-paint"),
    ("cls", "cumulative-layout-shift"),
    ("tbt_ms", "total-blocking-time"),
    ("fcp_ms", "first-contentful-paint"),
    ("speed_index_ms", "speed-index"),
    ("ttfb_ms", "server-response-time"),
)


# --------------------------------------------------------------------------
# Key handling
# --------------------------------------------------------------------------


def api_key_from_env(env=None):
    """Return (key, env var name) from PAGESPEED_API_KEY then GOOGLE_API_KEY, or (None, None)."""
    env = os.environ if env is None else env
    for name in KEY_ENV_VARS:
        value = (env.get(name) or "").strip()
        if value:
            return value, name
    return None, None


def _redact(text: str, key) -> str:
    """Remove an API key from any text (error messages can echo URLs)."""
    text = str(text)
    if key:
        text = text.replace(key, "[REDACTED]")
    return re.sub(r"(?i)([?&]key=)[^&\s'\"]+", r"\1[REDACTED]", text)


# --------------------------------------------------------------------------
# Parsing (pure)
# --------------------------------------------------------------------------


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def _threshold_category(value, good, poor):
    if value is None:
        return None
    if value <= good:
        return "good"
    if value > poor:
        return "poor"
    return "needs_improvement"


def _parse_metric(raw, unit, good, poor):
    percentile = _number(raw.get("percentile"))
    if percentile is None:
        return None
    scale = CLS_SCALE if unit == "unitless" else 1.0
    value = percentile / scale
    psi_category = raw.get("category") if isinstance(raw.get("category"), str) else None
    category = PSI_CATEGORY_MAP.get(psi_category) or _threshold_category(value, good, poor)
    distribution = []
    for bucket in raw.get("distributions") or []:
        if not isinstance(bucket, dict):
            continue
        low = _number(bucket.get("min"))
        high = _number(bucket.get("max"))
        distribution.append({
            "min": low / scale if low is not None else None,
            "max": high / scale if high is not None else None,
            "proportion": _number(bucket.get("proportion")),
        })
    return {
        "percentile": percentile,  # raw p75 as PSI reports it
        "value": value,            # p75 in the unit below (CLS unscaled)
        "unit": unit,
        "category": category,
        "psi_category": psi_category,
        "distribution": distribution,
    }


def _date(parts):
    if not isinstance(parts, dict):
        return None
    try:
        return "%04d-%02d-%02d" % (int(parts["year"]), int(parts["month"]), int(parts["day"]))
    except (KeyError, TypeError, ValueError):
        return None


def parse_field_block(block, source: str):
    """Parse one CrUX block from PSI (loadingExperience or originLoadingExperience).

    Returns:
        dict (scope, source, id, metrics, missing_core_metrics,
        cwv_assessment, ...) or None when the block holds no metrics.
    """
    if not isinstance(block, dict):
        return None
    raw_metrics = block.get("metrics")
    if not isinstance(raw_metrics, dict) or not raw_metrics:
        return None

    metrics = {}
    for short, keys, unit, good, poor in CORE_METRICS + OTHER_FIELD_METRICS:
        for key in keys:
            raw = raw_metrics.get(key)
            if isinstance(raw, dict):
                parsed = _parse_metric(raw, unit, good, poor)
                if parsed is not None:
                    parsed["key"] = key
                    metrics[short] = parsed
                    break
    if not metrics:
        return None

    core = [m[0] for m in CORE_METRICS]
    missing = [name for name in core if name not in metrics]

    # Google's assessment: pass when every core metric with data is good.
    # LCP and CLS are required; INP can be missing on low-interaction pages,
    # and then the verdict rests on LCP and CLS alone.
    if "lcp" in missing or "cls" in missing:
        assessment = "insufficient_data"
    elif all(metrics[name]["category"] == "good" for name in core if name in metrics):
        assessment = "passed"
    else:
        assessment = "failed"

    origin_fallback = bool(block.get("origin_fallback"))
    scope = "origin" if source == "originLoadingExperience" or origin_fallback else "url"
    period = block.get("collectionPeriod")
    period = period if isinstance(period, dict) else {}
    overall = block.get("overall_category") if isinstance(block.get("overall_category"), str) else None
    return {
        "scope": scope,
        "source": source,
        "origin_fallback": origin_fallback,
        "id": block.get("id"),
        "overall_category": PSI_CATEGORY_MAP.get(overall),
        "psi_overall_category": overall,
        "metrics": metrics,
        "missing_core_metrics": missing,
        "cwv_assessment": assessment,
        "collection_period": {
            "first_date": _date(period.get("firstDate")),
            "last_date": _date(period.get("lastDate")),
        } if period else None,
    }


def parse_lab(data):
    """Lighthouse lab diagnostics from a PSI response, or None when absent."""
    lighthouse = data.get("lighthouseResult") if isinstance(data, dict) else None
    if not isinstance(lighthouse, dict):
        return None
    audits = lighthouse.get("audits")
    audits = audits if isinstance(audits, dict) else {}
    lab = {}
    for name, audit_id in LAB_AUDITS:
        audit = audits.get(audit_id)
        lab[name] = _number(audit.get("numericValue")) if isinstance(audit, dict) else None
    categories = lighthouse.get("categories")
    performance = categories.get("performance") if isinstance(categories, dict) else None
    score = _number(performance.get("score")) if isinstance(performance, dict) else None
    lab["performance_score"] = int(round(score * 100)) if score is not None else None
    runtime_error = lighthouse.get("runtimeError")
    lab["runtime_error"] = (
        {"code": runtime_error.get("code"), "message": runtime_error.get("message")}
        if isinstance(runtime_error, dict) and runtime_error.get("code") else None
    )
    run_warnings = lighthouse.get("runWarnings")
    lab["warnings"] = [str(w) for w in run_warnings] if isinstance(run_warnings, list) else []
    lab["lighthouse_version"] = lighthouse.get("lighthouseVersion")
    lab["fetch_time"] = lighthouse.get("fetchTime")
    lab["final_url"] = lighthouse.get("finalDisplayedUrl") or lighthouse.get("finalUrl")
    lab["note"] = LAB_NOTE
    return lab


def parse_response(data, url=None, strategy=None) -> dict:
    """Turn a PSI v5 JSON response into the module's result dict (no network).

    Status is 'ok' when field data exists (URL or origin level) and
    'no_field_data' otherwise.
    """
    if not isinstance(data, dict):
        raise ValueError("PSI response is not a JSON object")
    result = _empty_result(url or data.get("id"), strategy)
    url_block = parse_field_block(data.get("loadingExperience"), "loadingExperience")
    origin_block = parse_field_block(data.get("originLoadingExperience"), "originLoadingExperience")

    field = url_block if url_block is not None else origin_block
    result["field"] = field
    # Keep origin data alongside URL data for context (e.g. INP missing for the page).
    result["origin_field"] = origin_block if (url_block is not None and url_block["scope"] == "url") else None
    result["lab"] = parse_lab(data)
    result["final_url"] = (result["lab"] or {}).get("final_url") or data.get("id")
    result["analysis_utc"] = data.get("analysisUTCTimestamp")

    if field is None:
        result["status"] = "no_field_data"
        result["notes"].append(NO_FIELD_NOTE)
    else:
        result["status"] = "ok"
        if field["scope"] == "origin":
            result["notes"].append(ORIGIN_NOTE)
        if "inp" in field["missing_core_metrics"] and field["cwv_assessment"] != "insufficient_data":
            result["notes"].append(
                "INP has no field data at this scope; the assessment uses LCP and CLS only."
            )
        if field["cwv_assessment"] == "insufficient_data":
            result["notes"].append(
                "Field data lacks LCP or CLS, so no Core Web Vitals verdict is given."
            )
    if result["lab"] and result["lab"]["runtime_error"]:
        result["notes"].append(
            "Lighthouse reported %s; lab numbers may be missing." % result["lab"]["runtime_error"]["code"]
        )
    return result


def _empty_result(url, strategy) -> dict:
    return {
        "status": None,
        "url": url,
        "final_url": None,
        "strategy": strategy,
        "key_source": None,
        "http_status": None,
        "analysis_utc": None,
        "field": None,
        "origin_field": None,
        "lab": None,
        "notes": [],
        "errors": [],
    }


# --------------------------------------------------------------------------
# Network
# --------------------------------------------------------------------------


def _default_session():
    if requests is None:
        raise RuntimeError(
            "Missing dependency 'requests'. Install it with: pip install requests"
        )
    return requests.Session()


def _error_message(response):
    """Google's error message ({"error": {"message": ...}}), else the start of the body."""
    try:
        body = response.json()
    except ValueError:
        body = None
    error = body.get("error") if isinstance(body, dict) else None
    if isinstance(error, dict) and error.get("message"):
        return str(error["message"])
    if isinstance(error, str) and error:
        return error
    return str(getattr(response, "text", "") or "")[:300]


def _classify_error(http_status: int, message: str) -> str:
    lowered = message.lower()
    if http_status == 429:
        return "rate_limited"
    if http_status in (401, 403) or "api key" in lowered or "api_key" in lowered:
        return "auth_error"
    if http_status == 400:
        return "bad_request"
    if http_status == 500 and "lighthouse" in lowered:
        return "lighthouse_error"  # e.g. FAILED_DOCUMENT_REQUEST: site unreachable
    return "http_error"


def fetch(url: str, strategy: str = "mobile", session=None, env=None, api_key=None,
          categories=("performance",), timeout: float = DEFAULT_TIMEOUT,
          retries_on_5xx: int = 1, sleep=time.sleep) -> dict:
    """Run PageSpeed Insights for ``url`` and return parsed field and lab data.

    Args:
        url: page to test; 'https://' is added when the scheme is missing.
        strategy: 'mobile' (default, what Google ranks on) or 'desktop'.
        session: object with ``request(method, url, **kwargs)`` (defaults to requests).
        env: mapping for the key variables (defaults to os.environ).
        api_key: explicit key; overrides the environment.
        categories: Lighthouse categories to run (performance is enough).
        timeout: seconds to wait for PSI.
        retries_on_5xx: extra attempts after a 5xx (Lighthouse runs flake).
        sleep: wait function between retries (injected in tests).

    Returns:
        dict with status ('ok' | 'no_field_data' | 'rate_limited' |
        'auth_error' | 'bad_request' | 'lighthouse_error' | 'http_error' |
        'network_error' | 'parse_error'), url, final_url, strategy,
        key_source (env var name or 'argument', never the key), http_status,
        analysis_utc, field, origin_field, lab, notes, errors.
    """
    if strategy not in STRATEGIES:
        raise ValueError("strategy must be 'mobile' or 'desktop'")
    url = (url or "").strip()
    if not url:
        raise ValueError("url is empty")
    if not re.match(r"(?i)^https?://", url):
        url = "https://" + url

    if isinstance(categories, str):
        categories = (categories,)  # a bare string would be sent letter by letter
    if api_key and api_key.strip():
        key, key_source = api_key.strip(), "argument"
    else:
        key, key_source = api_key_from_env(env)

    result = _empty_result(url, strategy)
    result["key_source"] = key_source
    if not key:
        result["notes"].append(NO_KEY_NOTE)

    session = session if session is not None else _default_session()
    params = [("url", url), ("strategy", strategy)] + [("category", c) for c in categories]
    headers = {"Accept": "application/json"}
    if key:
        headers["X-Goog-Api-Key"] = key  # header, so the key never sits in a URL

    response = None
    for attempt in range(1 + max(0, retries_on_5xx)):
        try:
            response = session.request("GET", PSI_ENDPOINT, params=params,
                                       headers=headers, timeout=timeout)
        except _NETWORK_ERRORS as exc:
            result["status"] = "network_error"
            result["errors"].append(_redact("%s: %s" % (type(exc).__name__, exc), key))
            return result
        if response.status_code >= 500 and attempt < retries_on_5xx:
            sleep(2.0)
            continue
        break

    result["http_status"] = response.status_code
    if response.status_code != 200:
        message = _redact(_error_message(response), key)
        status = _classify_error(response.status_code, message)
        result["status"] = status
        result["errors"].append("PageSpeed Insights HTTP %d: %s" % (response.status_code, message))
        if status == "rate_limited" and key:
            # The keyless case is already explained by NO_KEY_NOTE.
            result["notes"].append(
                "Quota exceeded for this API key (per-minute or per-day limit); try again later."
            )
        elif status == "auth_error" and key_source == "GOOGLE_API_KEY":
            result["notes"].append(
                "GOOGLE_API_KEY may be a Gemini or other Google key without the PageSpeed "
                "Insights API enabled. Create a PSI key and set PAGESPEED_API_KEY."
            )
        return result

    try:
        data = response.json()
        parsed = parse_response(data, url=url, strategy=strategy)
    except (ValueError, TypeError, AttributeError, KeyError) as exc:
        # Unreadable or unexpectedly shaped JSON is a status, not a crash.
        result["status"] = "parse_error"
        result["errors"].append(_redact(
            "PageSpeed Insights returned unreadable JSON: %s: %s" % (type(exc).__name__, exc), key))
        return result

    parsed["key_source"] = key_source
    parsed["http_status"] = response.status_code
    parsed["notes"] = result["notes"] + parsed["notes"]
    return parsed
