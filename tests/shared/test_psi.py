"""Offline tests for growthkit.psi (fixture JSON shaped like PSI v5, fake session).

Run from the repo root:
    python3 -m unittest discover -s tests -t .
"""

import copy
import json
import os
import sys
import unittest

_SHARED = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "shared")
if _SHARED not in sys.path:
    sys.path.insert(0, _SHARED)

from growthkit import psi  # noqa: E402

# Imported after growthkit.psi, which silences urllib3's LibreSSL warning.
import requests  # noqa: E402


# --------------------------------------------------------------------------
# Fixtures (field names and scales as documented for PSI v5: CLS
# percentiles and bucket bounds are x100; categories FAST/AVERAGE/SLOW).
# --------------------------------------------------------------------------

def _metric(percentile, category=None, distributions=None):
    raw = {"percentile": percentile}
    if category is not None:
        raw["category"] = category
    if distributions is not None:
        raw["distributions"] = distributions
    return raw


URL_EXPERIENCE = {
    "id": "https://example.com/pricing",
    "initial_url": "https://example.com/pricing",
    "overall_category": "FAST",
    "metrics": {
        "LARGEST_CONTENTFUL_PAINT_MS": _metric(2100, "FAST", [
            {"min": 0, "max": 2500, "proportion": 0.81},
            {"min": 2500, "max": 4000, "proportion": 0.12},
            {"min": 4000, "proportion": 0.07},
        ]),
        "INTERACTION_TO_NEXT_PAINT": _metric(180, "FAST"),
        "CUMULATIVE_LAYOUT_SHIFT_SCORE": _metric(5, "FAST", [
            {"min": 0, "max": 10, "proportion": 0.9},
            {"min": 10, "max": 25, "proportion": 0.06},
            {"min": 25, "proportion": 0.04},
        ]),
        "FIRST_CONTENTFUL_PAINT_MS": _metric(1500, "FAST"),
        "EXPERIMENTAL_TIME_TO_FIRST_BYTE": _metric(900, "AVERAGE"),
    },
}

ORIGIN_EXPERIENCE = {
    "id": "https://example.com",
    "overall_category": "AVERAGE",
    "metrics": {
        "LARGEST_CONTENTFUL_PAINT_MS": _metric(2900, "AVERAGE"),
        "INTERACTION_TO_NEXT_PAINT": _metric(250, "AVERAGE"),
        "CUMULATIVE_LAYOUT_SHIFT_SCORE": _metric(12, "AVERAGE"),
    },
}

LIGHTHOUSE = {
    "lighthouseVersion": "12.8.2",
    "fetchTime": "2026-10-24T15:00:00.000Z",
    "finalDisplayedUrl": "https://example.com/pricing",
    "categories": {"performance": {"score": 0.67}},
    "audits": {
        "largest-contentful-paint": {"numericValue": 4123.4},
        "cumulative-layout-shift": {"numericValue": 0.021},
        "total-blocking-time": {"numericValue": 512.0},
        "first-contentful-paint": {"numericValue": 1800.1},
        "speed-index": {"numericValue": 3900},
        "server-response-time": {"numericValue": 220},
    },
    "runWarnings": [],
}


def psi_response(loading=URL_EXPERIENCE, origin=ORIGIN_EXPERIENCE, lighthouse=LIGHTHOUSE):
    data = {
        "id": "https://example.com/pricing",
        "analysisUTCTimestamp": "2026-10-24T15:00:01.000Z",
        "lighthouseResult": copy.deepcopy(lighthouse),
    }
    # PSI sends a loadingExperience with only id/initial_url when there is no data.
    data["loadingExperience"] = copy.deepcopy(loading) if loading is not None else {
        "initial_url": "https://example.com/pricing"}
    if origin is not None:
        data["originLoadingExperience"] = copy.deepcopy(origin)
    return data


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, text=None):
        self.status_code = status_code
        self._json = json_data
        self.text = text if text is not None else json.dumps(json_data)

    def json(self):
        if self._json is not None:
            return self._json
        return json.loads(self.text)


class FakeSession:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append({"method": method, "url": url, **kwargs})
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def run_fetch(*responses, env=None, url="https://example.com/pricing", **kwargs):
    session = FakeSession(*responses)
    sleeps = []
    result = psi.fetch(url, session=session, env=env if env is not None else {},
                       sleep=sleeps.append, **kwargs)
    return result, session, sleeps


# --------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------


class FieldDataTests(unittest.TestCase):
    def test_url_level_field_data(self):
        result = psi.parse_response(psi_response(), strategy="mobile")
        self.assertEqual(result["status"], "ok")
        field = result["field"]
        self.assertEqual(field["scope"], "url")
        self.assertEqual(field["source"], "loadingExperience")
        self.assertEqual(field["cwv_assessment"], "passed")
        self.assertEqual(field["missing_core_metrics"], [])
        self.assertEqual(field["overall_category"], "good")

        lcp = field["metrics"]["lcp"]
        self.assertEqual(lcp["key"], "LARGEST_CONTENTFUL_PAINT_MS")
        self.assertEqual((lcp["value"], lcp["unit"], lcp["category"]), (2100, "ms", "good"))
        self.assertEqual(field["metrics"]["inp"]["value"], 180)

        cls = field["metrics"]["cls"]
        self.assertEqual(cls["percentile"], 5)  # raw, as PSI reports it
        self.assertAlmostEqual(cls["value"], 0.05)  # unscaled CLS
        self.assertEqual([b["max"] for b in cls["distribution"]], [0.1, 0.25, None])

        self.assertEqual(field["metrics"]["ttfb"]["category"], "needs_improvement")
        # Origin data is kept alongside for context.
        self.assertEqual(result["origin_field"]["scope"], "origin")
        self.assertEqual(result["origin_field"]["cwv_assessment"], "failed")

    def test_lab_is_diagnostic_only(self):
        result = psi.parse_response(psi_response())
        lab = result["lab"]
        self.assertEqual(lab["performance_score"], 67)
        self.assertEqual(lab["lcp_ms"], 4123.4)
        self.assertEqual(lab["tbt_ms"], 512.0)
        self.assertEqual(lab["ttfb_ms"], 220)
        self.assertNotIn("inp_ms", lab)  # Lighthouse navigation runs have no INP
        self.assertIn("diagnose", lab["note"])
        # Slow lab LCP does not change the field verdict.
        self.assertEqual(result["field"]["cwv_assessment"], "passed")
        self.assertEqual(result["final_url"], "https://example.com/pricing")

    def test_origin_fallback_flag_is_labelled_origin(self):
        loading = copy.deepcopy(ORIGIN_EXPERIENCE)
        loading["origin_fallback"] = True
        result = psi.parse_response(psi_response(loading=loading))
        self.assertEqual(result["field"]["scope"], "origin")
        self.assertTrue(result["field"]["origin_fallback"])
        self.assertIsNone(result["origin_field"])
        self.assertIn(psi.ORIGIN_NOTE, result["notes"])

    def test_falls_back_to_origin_experience(self):
        result = psi.parse_response(psi_response(loading=None))
        field = result["field"]
        self.assertEqual(result["status"], "ok")
        self.assertEqual((field["scope"], field["source"]), ("origin", "originLoadingExperience"))
        self.assertAlmostEqual(field["metrics"]["cls"]["value"], 0.12)
        self.assertEqual(field["metrics"]["cls"]["category"], "needs_improvement")
        self.assertEqual(field["cwv_assessment"], "failed")
        self.assertIn(psi.ORIGIN_NOTE, result["notes"])

    def test_no_field_data(self):
        result = psi.parse_response(psi_response(loading=None, origin=None))
        self.assertEqual(result["status"], "no_field_data")
        self.assertIsNone(result["field"])
        self.assertIn(psi.NO_FIELD_NOTE, result["notes"])
        self.assertEqual(result["lab"]["performance_score"], 67)  # lab still reported

    def test_missing_inp_uses_lcp_and_cls(self):
        loading = copy.deepcopy(URL_EXPERIENCE)
        del loading["metrics"]["INTERACTION_TO_NEXT_PAINT"]
        result = psi.parse_response(psi_response(loading=loading))
        self.assertEqual(result["field"]["missing_core_metrics"], ["inp"])
        self.assertEqual(result["field"]["cwv_assessment"], "passed")
        self.assertTrue(any("INP has no field data" in n for n in result["notes"]))

    def test_missing_lcp_is_insufficient(self):
        loading = copy.deepcopy(URL_EXPERIENCE)
        del loading["metrics"]["LARGEST_CONTENTFUL_PAINT_MS"]
        result = psi.parse_response(psi_response(loading=loading))
        self.assertEqual(result["field"]["cwv_assessment"], "insufficient_data")

    def test_one_slow_metric_fails(self):
        loading = copy.deepcopy(URL_EXPERIENCE)
        loading["metrics"]["INTERACTION_TO_NEXT_PAINT"] = _metric(620, "SLOW")
        result = psi.parse_response(psi_response(loading=loading))
        self.assertEqual(result["field"]["metrics"]["inp"]["category"], "poor")
        self.assertEqual(result["field"]["cwv_assessment"], "failed")

    def test_threshold_categories_when_psi_omits_them(self):
        # web.dev thresholds: good <= 2500 ms / 200 ms / 0.1, poor > 4000 ms / 500 ms / 0.25.
        cases = [
            ("LARGEST_CONTENTFUL_PAINT_MS", "lcp", 2500, "good"),
            ("LARGEST_CONTENTFUL_PAINT_MS", "lcp", 2501, "needs_improvement"),
            ("LARGEST_CONTENTFUL_PAINT_MS", "lcp", 4001, "poor"),
            ("INTERACTION_TO_NEXT_PAINT", "inp", 200, "good"),
            ("INTERACTION_TO_NEXT_PAINT", "inp", 500, "needs_improvement"),
            ("CUMULATIVE_LAYOUT_SHIFT_SCORE", "cls", 10, "good"),
            ("CUMULATIVE_LAYOUT_SHIFT_SCORE", "cls", 25, "needs_improvement"),
            ("CUMULATIVE_LAYOUT_SHIFT_SCORE", "cls", 26, "poor"),
        ]
        for key, short, percentile, expected in cases:
            block = {"metrics": {key: _metric(percentile)}}
            parsed = psi.parse_field_block(block, "loadingExperience")
            self.assertEqual(parsed["metrics"][short]["category"], expected, (key, percentile))

    def test_legacy_inp_key_and_collection_period(self):
        block = {
            "metrics": {
                "LARGEST_CONTENTFUL_PAINT_MS": _metric(1200, "FAST"),
                "CUMULATIVE_LAYOUT_SHIFT_SCORE": _metric(0, "FAST"),
                "EXPERIMENTAL_INTERACTION_TO_NEXT_PAINT": _metric(150, "FAST"),
            },
            "collectionPeriod": {
                "firstDate": {"year": 2026, "month": 9, "day": 26},
                "lastDate": {"year": 2026, "month": 10, "day": 23},
            },
        }
        parsed = psi.parse_field_block(block, "loadingExperience")
        self.assertEqual(parsed["metrics"]["inp"]["key"], "EXPERIMENTAL_INTERACTION_TO_NEXT_PAINT")
        self.assertEqual(parsed["collection_period"],
                         {"first_date": "2026-09-26", "last_date": "2026-10-23"})

    def test_runtime_error_note(self):
        lighthouse = copy.deepcopy(LIGHTHOUSE)
        lighthouse["runtimeError"] = {"code": "NO_FCP", "message": "The page did not paint"}
        result = psi.parse_response(psi_response(lighthouse=lighthouse))
        self.assertEqual(result["lab"]["runtime_error"]["code"], "NO_FCP")
        self.assertTrue(any("NO_FCP" in n for n in result["notes"]))

    def test_rejects_non_object(self):
        with self.assertRaises(ValueError):
            psi.parse_response([])


# --------------------------------------------------------------------------
# Network behaviour
# --------------------------------------------------------------------------


class KeyTests(unittest.TestCase):
    def test_pagespeed_key_wins_and_stays_out_of_urls_and_output(self):
        env = {"PAGESPEED_API_KEY": "psi-key-123", "GOOGLE_API_KEY": "gemini-key-456"}
        result, session, _ = run_fetch(FakeResponse(200, psi_response()), env=env)
        call = session.calls[0]
        self.assertEqual(call["url"], psi.PSI_ENDPOINT)
        self.assertEqual(call["headers"]["X-Goog-Api-Key"], "psi-key-123")
        self.assertNotIn("key", [name for name, _ in call["params"]])
        self.assertIn(("strategy", "mobile"), call["params"])
        self.assertIn(("category", "performance"), call["params"])
        self.assertEqual(result["key_source"], "PAGESPEED_API_KEY")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["http_status"], 200)
        self.assertNotIn("psi-key-123", json.dumps(result))
        self.assertNotIn(psi.NO_KEY_NOTE, result["notes"])

    def test_google_key_is_second_choice(self):
        self.assertEqual(psi.api_key_from_env({"GOOGLE_API_KEY": "g"}), ("g", "GOOGLE_API_KEY"))
        self.assertEqual(psi.api_key_from_env({"PAGESPEED_API_KEY": " ", "GOOGLE_API_KEY": "g"}),
                         ("g", "GOOGLE_API_KEY"))
        self.assertEqual(psi.api_key_from_env({}), (None, None))

    def test_google_key_without_psi_enabled(self):
        error = {"error": {"code": 403, "message": "PageSpeed Insights API has not been used in "
                                                    "project 123 before or it is disabled."}}
        result, _, _ = run_fetch(FakeResponse(403, error), env={"GOOGLE_API_KEY": "gemini-key"})
        self.assertEqual(result["status"], "auth_error")
        self.assertTrue(any("Gemini" in n for n in result["notes"]))
        self.assertIn("HTTP 403", result["errors"][0])

    def test_invalid_key_message_is_auth_error(self):
        error = {"error": {"code": 400, "message": "API key not valid. Please pass a valid API key."}}
        result, _, _ = run_fetch(FakeResponse(400, error), env={"PAGESPEED_API_KEY": "bad"})
        self.assertEqual(result["status"], "auth_error")

    def test_keyless_call_and_quota(self):
        error = {"error": {"code": 429, "message": "Quota exceeded for quota metric 'Queries' "
                                                    "and limit 'Queries per day'"}}
        result, session, _ = run_fetch(FakeResponse(429, error))
        self.assertNotIn("X-Goog-Api-Key", session.calls[0]["headers"])
        self.assertIsNone(result["key_source"])
        self.assertEqual(result["status"], "rate_limited")
        self.assertEqual(result["notes"], [psi.NO_KEY_NOTE])
        self.assertIn("Queries per day", result["errors"][0])

    def test_keyed_quota_note(self):
        error = {"error": {"code": 429, "message": "Quota exceeded"}}
        result, _, _ = run_fetch(FakeResponse(429, error), env={"PAGESPEED_API_KEY": "k"})
        self.assertEqual(result["status"], "rate_limited")
        self.assertTrue(any("this API key" in n for n in result["notes"]))

    def test_network_error_is_redacted(self):
        exc = requests.ConnectionError(
            "Max retries exceeded with url: /pagespeedonline/v5/runPagespeed?url=x&key=secret-k")
        result, _, _ = run_fetch(exc, env={"PAGESPEED_API_KEY": "secret-k"})
        self.assertEqual(result["status"], "network_error")
        self.assertNotIn("secret-k", json.dumps(result))
        self.assertIn("[REDACTED]", result["errors"][0])


class FetchStatusTests(unittest.TestCase):
    def test_no_field_data_status(self):
        result, _, _ = run_fetch(FakeResponse(200, psi_response(loading=None, origin=None)))
        self.assertEqual(result["status"], "no_field_data")
        self.assertIn(psi.NO_FIELD_NOTE, result["notes"])
        self.assertIn(psi.NO_KEY_NOTE, result["notes"])

    def test_lighthouse_5xx_retried_once(self):
        failure = FakeResponse(500, {"error": {"code": 500, "message": "Lighthouse returned error: "
                                                                     "FAILED_DOCUMENT_REQUEST"}})
        result, session, sleeps = run_fetch(failure, FakeResponse(200, psi_response()))
        self.assertEqual(result["status"], "ok")
        self.assertEqual(len(session.calls), 2)
        self.assertEqual(sleeps, [2.0])

        result, session, _ = run_fetch(failure, failure)
        self.assertEqual(result["status"], "lighthouse_error")
        self.assertEqual(len(session.calls), 2)

    def test_bad_request(self):
        error = {"error": {"code": 400, "message": "Invalid value at 'url'"}}
        result, _, _ = run_fetch(FakeResponse(400, error))
        self.assertEqual(result["status"], "bad_request")

    def test_unreadable_json(self):
        result, _, _ = run_fetch(FakeResponse(200, text="<html>not json</html>"))
        self.assertEqual(result["status"], "parse_error")

    def test_scheme_added_and_desktop_strategy(self):
        result, session, _ = run_fetch(FakeResponse(200, psi_response()), url="example.com",
                                       strategy="desktop")
        self.assertIn(("url", "https://example.com"), session.calls[0]["params"])
        self.assertIn(("strategy", "desktop"), session.calls[0]["params"])
        self.assertEqual(result["strategy"], "desktop")

    def test_odd_error_bodies_do_not_crash(self):
        for body in ({"error": "quota exceeded"}, ["x"], None):
            response = FakeResponse(429, body, text=None if body is not None else "Too Many Requests")
            result, _, _ = run_fetch(response)
            self.assertEqual(result["status"], "rate_limited")
            self.assertTrue(result["errors"][0].startswith("PageSpeed Insights HTTP 429"))

    def test_unexpected_200_shape_is_not_a_crash(self):
        odd = psi_response()
        odd["lighthouseResult"]["categories"] = []
        odd["lighthouseResult"]["audits"] = []
        odd["loadingExperience"]["collectionPeriod"] = "last 28 days"
        result, _, _ = run_fetch(FakeResponse(200, odd))
        self.assertEqual(result["status"], "ok")
        self.assertIsNone(result["lab"]["performance_score"])
        self.assertIsNone(result["field"]["collection_period"])

    def test_category_string_and_blank_key_argument(self):
        result, session, _ = run_fetch(FakeResponse(200, psi_response()),
                                       categories="performance", api_key="   ")
        params = session.calls[0]["params"]
        self.assertEqual([v for k, v in params if k == "category"], ["performance"])
        self.assertNotIn("X-Goog-Api-Key", session.calls[0]["headers"])
        self.assertIsNone(result["key_source"])  # a blank argument is no key
        self.assertIn(psi.NO_KEY_NOTE, result["notes"])

    def test_invalid_arguments(self):
        with self.assertRaises(ValueError):
            psi.fetch("https://example.com", strategy="tablet", session=FakeSession())
        with self.assertRaises(ValueError):
            psi.fetch("  ", session=FakeSession())


if __name__ == "__main__":
    unittest.main()
