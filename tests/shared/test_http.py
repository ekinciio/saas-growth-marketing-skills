"""Offline tests for growthkit.http.

Most tests drive fetch() with a fake session that returns real
requests.Response objects, so the production code path is exercised
without the network. One test class runs a throwaway HTTP server on
127.0.0.1 to check redirects, streaming and the size cap end to end.

Run from the repo root:
    python3 -m unittest discover -s tests -t .
"""

import gzip
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from tests import _paths
from growthkit import http  # noqa: E402  (silences urllib3's LibreSSL warning first)

import requests  # noqa: E402
from requests.cookies import cookiejar_from_dict  # noqa: E402
from requests.structures import CaseInsensitiveDict  # noqa: E402

FIXTURES = ("shared", "fixtures")


def fixture(name, mode="r"):
    return _paths.read_fixture(*FIXTURES, name, mode=mode)


def make_response(status=200, body=b"", headers=None, url="https://www.acme.test/",
                  history=(), cookies=None, reason="OK"):
    """A real requests.Response with an in-memory body."""
    if isinstance(body, str):
        body = body.encode("utf-8")
    response = requests.Response()
    response.status_code = status
    response.reason = reason
    response._content = body
    response._content_consumed = True  # iter_content() then yields slices of _content
    response.headers = CaseInsensitiveDict(headers or {})
    response.url = url
    response.history = list(history)
    response.cookies = cookiejar_from_dict(cookies or {})
    return response


class FakeSession:
    """Returns queued responses (or raises queued exceptions) and records calls."""

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = []
        self.closed = False

    def get(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        outcome = self.outcomes.pop(0) if len(self.outcomes) > 1 else self.outcomes[0]
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    def close(self):
        self.closed = True


def html_response(body, status=200, headers=None, **kwargs):
    merged = {"Content-Type": "text/html; charset=utf-8"}
    merged.update(headers or {})
    return make_response(status, body, merged, **kwargs)


class NormalizeUrlTests(unittest.TestCase):
    def test_valid_inputs(self):
        cases = {
            "linear.app": "https://linear.app/",
            "  HTTPS://Notion.com/Pricing#plans ": "https://notion.com/Pricing",
            "//cal.com/x": "https://cal.com/x",
            "http://localhost:8000/a?b=1": "http://localhost:8000/a?b=1",
            "<https://www.acme.test>": "https://www.acme.test/",
            "http://127.0.0.1:5000": "http://127.0.0.1:5000/",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(http.normalize_url(raw), expected)

    def test_invalid_inputs(self):
        for raw in ("", "not a url", "--json", "ftp://acme.test/file", "mailto:a@b.c",
                    "file:///etc/passwd", "https://", "javascript:alert(1)", "https://acme"):
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError):
                    http.normalize_url(raw)

    def test_site_helpers(self):
        self.assertEqual(http.site_root("www.acme.test/pricing?x=1"), "https://www.acme.test")
        self.assertEqual(http.site_url("https://www.acme.test/a/b", "/llms.txt"), "https://www.acme.test/llms.txt")


class LooksLikeHtmlTests(unittest.TestCase):
    def test_sniffing(self):
        self.assertTrue(http.looks_like_html("<!DOCTYPE html><html><body>x</body></html>"))
        self.assertTrue(http.looks_like_html("\ufeff  <html lang='en'>"))
        self.assertTrue(http.looks_like_html(fixture("spa_shell.html")))
        self.assertFalse(http.looks_like_html(fixture("robots.txt")))
        self.assertFalse(http.looks_like_html(fixture("llms.txt")))
        self.assertFalse(http.looks_like_html(fixture("sitemap.xml")))
        self.assertFalse(http.looks_like_html(""))
        self.assertFalse(http.looks_like_html(None))


class BotProtectionTests(unittest.TestCase):
    def test_nothing_detected(self):
        self.assertIsNone(http.detect_bot_protection(200, {"server": "nginx"}, "<p>hi</p>", [], 300))

    def test_cdn_presence_on_a_normal_page_is_not_a_challenge(self):
        bot = http.detect_bot_protection(
            200, {"Server": "cloudflare", "CF-RAY": "8f00-AMS"},
            "<script src='/cdn-cgi/challenge-platform/scripts/jsd/main.js'></script><p>plenty</p>",
            ["__cf_bm"], 900)
        self.assertEqual(bot["vendor"], "cloudflare")
        self.assertFalse(bot["challenge"])
        self.assertIn("cookie __cf_bm", bot["signals"])

    def test_cloudflare_challenge(self):
        bot = http.detect_bot_protection(403, {"cf-mitigated": "challenge", "server": "cloudflare"},
                                         fixture("cloudflare_challenge.html"), [], 0)
        self.assertEqual(bot["vendor"], "cloudflare")
        self.assertTrue(bot["challenge"])

    def test_datadome_header_only_still_names_vendor(self):
        bot = http.detect_bot_protection(403, {"x-datadome": "protected", "server": "cloudflare"}, "", [], None)
        self.assertEqual(bot["vendor"], "datadome")
        self.assertEqual(set(bot["vendors"]), {"datadome", "cloudflare"})
        self.assertFalse(bot["challenge"])

    def test_datadome_captcha_page(self):
        bot = http.detect_bot_protection(403, {}, fixture("datadome_block.html"), ["datadome"], 8)
        self.assertEqual(bot["vendor"], "datadome")
        self.assertTrue(bot["challenge"])

    def test_akamai_access_denied(self):
        bot = http.detect_bot_protection(403, {"server": "AkamaiGHost"}, fixture("akamai_denied.html"), [], 15)
        self.assertEqual(bot["vendor"], "akamai")
        self.assertTrue(bot["challenge"])

    def test_injected_vendor_scripts_on_sparse_200_page_are_not_a_challenge(self):
        body = "<html><body><div id='root'></div><script src='https://client.px-cloud.net/PX1/main.min.js'></script>" \
               "<script src='/_Incapsula_Resource?SWJIYLWA=1'></script><script src='/ips.js?kpsdk=1'></script></body></html>"
        self.assertIsNone(http.detect_bot_protection(200, {}, body, [], 0))

    def test_generic_wording_only_on_error_status(self):
        body = "<html><body>Please verify you are a human</body></html>"
        bot = http.detect_bot_protection(403, {}, body, [], 5)
        self.assertTrue(bot["challenge"])
        self.assertEqual(bot["vendor"], "unknown")
        self.assertIsNone(http.detect_bot_protection(200, {}, body, [], 5))


class FetchTests(unittest.TestCase):
    def fetch(self, *outcomes, **kwargs):
        session = FakeSession(*outcomes)
        kwargs.setdefault("retry_backoff", 0)
        result = http.fetch(kwargs.pop("url", "https://www.acme.test/"), session=session, **kwargs)
        json.dumps(result)  # always serializable
        return result, session

    def test_ok_page(self):
        result, session = self.fetch(html_response(fixture("saas_home.html"), headers={"Server": "nginx"}))
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["http_status"], 200)
        self.assertEqual(result["content_type"], "text/html")
        self.assertIn("Where teams and agents", result["html"])
        self.assertIsNone(result["text"])
        self.assertFalse(result["is_js_shell"])
        self.assertIsNone(result["bot_protection"])
        self.assertIsNone(result["error"])
        self.assertEqual(result["headers"]["server"], "nginx")
        call = session.calls[0]
        self.assertEqual(call["headers"]["User-Agent"], http.BROWSER_UA)
        self.assertIn("Accept-Language", call["headers"])
        self.assertTrue(call["stream"])
        self.assertFalse(session.closed)  # a caller's session is left open

    def test_text_resources_use_the_tool_user_agent(self):
        result, session = self.fetch(make_response(200, fixture("llms.txt"), {"Content-Type": "text/plain"}),
                                     url="https://www.acme.test/llms.txt", kind="text")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(session.calls[0]["headers"]["User-Agent"], http.TOOL_UA)
        self.assertIn("SaaSGrowthSkills/", http.TOOL_UA)
        self.assertTrue(result["text"].startswith("# Acme"))
        self.assertIsNone(result["html"])

    def test_http_404_keeps_body_and_never_raises(self):
        result, _ = self.fetch(html_response("<html><body><h1>Not found</h1></body></html>", 404, reason="Not Found"))
        self.assertEqual(result["status"], "http_error")
        self.assertEqual(result["http_status"], 404)
        self.assertEqual(result["error"], "HTTP 404 Not Found")
        self.assertIn("Not found", result["html"])

    def test_500_and_503_without_challenge_are_http_errors(self):
        result, _ = self.fetch(html_response("<p>Server error</p>", 500, reason="Internal Server Error"))
        self.assertEqual(result["status"], "http_error")
        result, _ = self.fetch(html_response("<p>Down for maintenance</p>", 503, {"Server": "cloudflare"}))
        self.assertEqual(result["status"], "http_error")
        self.assertEqual(result["bot_protection"]["vendor"], "cloudflare")

    def test_datadome_403_is_blocked(self):
        result, _ = self.fetch(html_response(
            fixture("datadome_block.html"), 403, {"X-DataDome": "protected", "Set-Cookie": "datadome=abc; Path=/"}))
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["bot_protection"]["vendor"], "datadome")
        self.assertIn("datadome", result["cookie_names"])
        self.assertNotIn("set-cookie", result["headers"])
        self.assertIn("Blocked by bot protection (datadome), HTTP 403", result["error"])

    def test_cloudflare_challenge_is_blocked(self):
        result, _ = self.fetch(html_response(
            fixture("cloudflare_challenge.html"), 403, {"cf-mitigated": "challenge", "Server": "cloudflare"}))
        self.assertEqual(result["status"], "blocked")
        self.assertTrue(result["bot_protection"]["challenge"])

    def test_challenge_served_with_200_is_blocked_not_js_shell(self):
        result, _ = self.fetch(html_response(fixture("cloudflare_challenge.html"), 200))
        self.assertEqual(result["status"], "blocked")

    def test_plain_429_is_blocked(self):
        result, _ = self.fetch(make_response(429, "slow down", {"Content-Type": "text/plain"}, reason="Too Many Requests"))
        self.assertEqual(result["status"], "blocked")
        self.assertIsNone(result["bot_protection"])
        self.assertIn("429", result["error"])

    def test_401_behind_cdn_is_not_called_a_bot_wall(self):
        result, _ = self.fetch(html_response("<p>Login required</p>", 401, {"Server": "cloudflare"}))
        self.assertEqual(result["status"], "http_error")

    def test_js_shell(self):
        result, _ = self.fetch(html_response(fixture("spa_shell.html")))
        self.assertEqual(result["status"], "js_shell")
        self.assertTrue(result["is_js_shell"])
        self.assertEqual(result["js_shell_signals"]["empty_root"], "root")
        self.assertIsNotNone(result["html"])

    def test_not_html(self):
        result, _ = self.fetch(make_response(200, b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n1 0 obj", {"Content-Type": "application/pdf"}))
        self.assertEqual(result["status"], "not_html")
        self.assertIsNone(result["html"])
        self.assertIsNone(result["text"])
        result, _ = self.fetch(make_response(200, b'{"ok": true}', {"Content-Type": "application/json"}))
        self.assertEqual(result["status"], "not_html")
        self.assertEqual(result["text"], '{"ok": true}')

    def test_mislabelled_html_is_still_html(self):
        result, _ = self.fetch(make_response(200, fixture("saas_home.html"), {"Content-Type": "text/plain"}))
        self.assertEqual(result["status"], "ok")

    def test_too_large(self):
        body = "<html><body><h1>Big</h1>" + "<p>%s</p>" % ("word " * 50000) + "</body></html>"
        result, _ = self.fetch(html_response(body), max_bytes=10000)
        self.assertEqual(result["status"], "too_large")
        self.assertTrue(result["truncated"])
        self.assertEqual(result["bytes"], 10000)
        self.assertEqual(len(result["html"]), 10000)

    def test_meta_charset_decoding(self):
        body = '<html><head><meta charset="windows-1252"><title>Caf\xe9</title></head><body><h1>Caf\xe9 \u20ac men\xfc</h1>' \
               + "<p>%s</p></body></html>" % ("text " * 60)
        result, _ = self.fetch(make_response(200, body.encode("cp1252"), {"Content-Type": "text/html"}))
        self.assertEqual(result["encoding"], "windows-1252")
        self.assertIn("Caf\xe9 \u20ac men\xfc", result["html"])

    def test_redirect_chain(self):
        hop1 = make_response(301, b"", {"Location": "https://acme.test/"}, url="http://acme.test/")
        hop2 = make_response(308, b"", {"Location": "https://www.acme.test/"}, url="https://acme.test/")
        final = html_response(fixture("saas_home.html"), url="https://www.acme.test/", history=[hop1, hop2])
        result, _ = self.fetch(final, url="http://acme.test")
        self.assertEqual(result["url"], "http://acme.test/")
        self.assertEqual(result["final_url"], "https://www.acme.test/")
        self.assertEqual(result["redirect_chain"], [
            {"url": "http://acme.test/", "status": 301},
            {"url": "https://acme.test/", "status": 308},
        ])

    def test_connection_error_is_retried_then_unreachable(self):
        error = requests.exceptions.ConnectionError(
            "HTTPSConnectionPool: Max retries exceeded (Caused by NameResolutionError: "
            "Failed to resolve 'nope.acme.test' ([Errno 8] nodename nor servname provided, or not known))")
        result, session = self.fetch(error, error)
        self.assertEqual(result["status"], "unreachable")
        self.assertEqual(len(session.calls), 2)
        self.assertEqual(result["error"], "DNS lookup failed: the domain does not resolve")
        self.assertIsNone(result["http_status"])

    def test_retry_recovers(self):
        result, session = self.fetch(requests.exceptions.ReadTimeout("slow"), html_response(fixture("saas_home.html")))
        self.assertEqual(result["status"], "ok")
        self.assertEqual(len(session.calls), 2)

    def test_ssl_error_is_not_retried(self):
        result, session = self.fetch(requests.exceptions.SSLError("certificate verify failed"))
        self.assertEqual(result["status"], "unreachable")
        self.assertEqual(len(session.calls), 1)
        self.assertTrue(result["error"].startswith("TLS/SSL error"))

    def test_other_request_errors(self):
        result, _ = self.fetch(requests.exceptions.TooManyRedirects("Exceeded 30 redirects."))
        self.assertEqual(result["status"], "unreachable")
        self.assertIn("redirect loop", result["error"])
        result, _ = self.fetch(requests.exceptions.InvalidURL("bad"))
        self.assertEqual(result["status"], "unreachable")

    def test_body_read_failure(self):
        class Broken(requests.Response):
            def iter_content(self, chunk_size=1, decode_unicode=False):
                yield b"<html>"
                raise requests.exceptions.ChunkedEncodingError("connection broken")

        response = Broken()
        response.status_code = 200
        response.headers = CaseInsensitiveDict({"Content-Type": "text/html"})
        response.url = "https://www.acme.test/"
        result, _ = self.fetch(response)
        self.assertEqual(result["status"], "unreachable")
        self.assertEqual(result["http_status"], 200)
        self.assertIn("reading the response body", result["error"])

    def test_invalid_url_makes_no_request(self):
        result, session = self.fetch(html_response("<p>x</p>"), url="not a url")
        self.assertEqual(result["status"], "unreachable")
        self.assertEqual(session.calls, [])
        self.assertIn("Invalid URL", result["error"])

    def test_bad_kind_is_a_programming_error(self):
        with self.assertRaises(ValueError):
            http.fetch("https://www.acme.test/", kind="pdf", session=FakeSession(html_response("x")))

    def test_robots_soft_404(self):
        result, _ = self.fetch(html_response(fixture("spa_shell.html")),
                               url="https://www.acme.test/robots.txt", kind="text")
        self.assertEqual(result["status"], "http_error")
        self.assertTrue(result["soft_404"])
        self.assertIsNone(result["text"])

    def test_robots_with_bom_and_wrong_content_type(self):
        result, _ = self.fetch(make_response(200, fixture("robots.txt", "rb"), {"Content-Type": "text/html"}),
                               url="https://www.acme.test/robots.txt", kind="text")
        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["text"].startswith("User-agent: GPTBot"))

    def test_robots_with_unusual_content_type_is_still_read(self):
        result, _ = self.fetch(make_response(200, b"User-agent: *\nDisallow: /private\n",
                                             {"Content-Type": "application/x-unknown"}),
                               url="https://www.acme.test/robots.txt", kind="text")
        self.assertEqual(result["status"], "ok")
        self.assertIn("Disallow: /private", result["text"])

    def test_empty_robots_is_ok(self):
        result, _ = self.fetch(make_response(200, b"", {"Content-Type": "text/plain"}),
                               url="https://www.acme.test/robots.txt", kind="text")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["text"], "")

    def test_robots_behind_challenge_is_blocked(self):
        result, _ = self.fetch(html_response(fixture("cloudflare_challenge.html"), 403, {"cf-mitigated": "challenge"}),
                               url="https://www.acme.test/robots.txt", kind="text")
        self.assertEqual(result["status"], "blocked")

    def test_sitemap_xml_and_gzip(self):
        xml = fixture("sitemap.xml")
        result, _ = self.fetch(make_response(200, xml, {"Content-Type": "application/xml"}),
                               url="https://www.acme.test/sitemap.xml", kind="xml")
        self.assertEqual(result["status"], "ok")
        self.assertIn("<urlset", result["text"])
        packed = gzip.compress(xml.encode("utf-8"))
        result, _ = self.fetch(make_response(200, packed, {"Content-Type": "application/x-gzip"},
                                             url="https://www.acme.test/sitemap.xml.gz"),
                               url="https://www.acme.test/sitemap.xml.gz", kind="xml")
        self.assertEqual(result["status"], "ok")
        self.assertIn("<loc>https://www.acme.test/pricing</loc>", result["text"])

    def test_sitemap_soft_404(self):
        result, _ = self.fetch(html_response("<!doctype html><html><body>Home</body></html>"),
                               url="https://www.acme.test/sitemap.xml", kind="xml")
        self.assertEqual(result["status"], "http_error")
        self.assertTrue(result["soft_404"])

    def test_fetch_site_file_picks_kind(self):
        session = FakeSession(make_response(200, fixture("sitemap.xml"), {"Content-Type": "text/xml"}))
        result = http.fetch_site_file("https://www.acme.test/pricing", "/sitemap.xml", session=session)
        self.assertEqual(result["kind"], "xml")
        self.assertEqual(session.calls[0]["url"], "https://www.acme.test/sitemap.xml")
        result = http.fetch_site_file("not a url", "/robots.txt", session=session)
        self.assertEqual(result["status"], "unreachable")

    def test_summarize_drops_bodies(self):
        result, _ = self.fetch(html_response(fixture("spa_shell.html")))
        summary = http.summarize(result)
        self.assertNotIn("html", summary)
        self.assertNotIn("headers", summary)
        self.assertEqual(summary["status"], "js_shell")
        self.assertIn("js_shell_signals", summary)

    def test_result_has_every_key_for_every_status(self):
        keys = set(http._empty_result("x", "html"))
        for outcome in (html_response("<p>x</p>"), html_response("x", 404), requests.exceptions.ConnectTimeout("t")):
            result, _ = self.fetch(outcome, retries=0)
            self.assertEqual(set(result), keys)
            self.assertIn(result["status"], http.STATUSES)


class _Handler(BaseHTTPRequestHandler):
    routes = {}

    def do_GET(self):  # noqa: N802 - http.server API
        status, headers, body = self.routes.get(self.path, (404, {"Content-Type": "text/plain"}, b"missing"))
        self.send_response(status)
        for key, value in headers.items():
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # keep test output quiet
        pass


class LocalServerTests(unittest.TestCase):
    """End to end against 127.0.0.1 (no internet needed)."""

    @classmethod
    def setUpClass(cls):
        try:
            cls.server = HTTPServer(("127.0.0.1", 0), _Handler)
        except OSError as exc:  # sandboxes without socket permission
            raise unittest.SkipTest("cannot bind a local port: %s" % exc)
        base = "http://127.0.0.1:%d" % cls.server.server_address[1]
        cls.base = base
        page = _paths.read_fixture(*FIXTURES, "saas_home.html", mode="rb")
        _Handler.routes = {
            "/": (200, {"Content-Type": "text/html; charset=utf-8", "X-Robots-Tag": "noai"}, page),
            "/old": (301, {"Location": base + "/"}, b""),
            "/big": (200, {"Content-Type": "text/html"}, b"<html><body>" + b"<p>word word</p>" * 20000 + b"</body></html>"),
            "/robots.txt": (200, {"Content-Type": "text/html"}, _paths.read_fixture(*FIXTURES, "spa_shell.html", mode="rb")),
            "/llms.txt": (200, {"Content-Type": "text/plain; charset=utf-8"}, _paths.read_fixture(*FIXTURES, "llms.txt", mode="rb")),
        }
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def session(self):
        session = requests.Session()
        session.trust_env = False  # ignore any proxy settings for 127.0.0.1
        return session

    def test_redirect_and_headers(self):
        result = http.fetch(self.base + "/old", session=self.session(), timeout=5)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["final_url"], self.base + "/")
        self.assertEqual(result["redirect_chain"], [{"url": self.base + "/old", "status": 301}])
        self.assertEqual(result["headers"]["x-robots-tag"], "noai")

    def test_streamed_size_cap(self):
        result = http.fetch(self.base + "/big", session=self.session(), timeout=5, max_bytes=50000)
        self.assertEqual(result["status"], "too_large")
        self.assertEqual(result["bytes"], 50000)

    def test_text_files(self):
        robots = http.fetch_site_file(self.base + "/pricing", "/robots.txt", session=self.session(), timeout=5)
        self.assertEqual(robots["status"], "http_error")
        self.assertTrue(robots["soft_404"])
        llms = http.fetch_site_file(self.base, "/llms.txt", session=self.session(), timeout=5)
        self.assertEqual(llms["status"], "ok")
        missing = http.fetch_site_file(self.base, "/sitemap.xml", session=self.session(), timeout=5)
        self.assertEqual(missing["status"], "http_error")
        self.assertEqual(missing["http_status"], 404)

    def test_refused_port_is_unreachable(self):
        probe = HTTPServer(("127.0.0.1", 0), _Handler)
        port = probe.server_address[1]
        probe.server_close()  # nothing listens on this port now
        result = http.fetch("http://127.0.0.1:%d/" % port, session=self.session(), timeout=2, retry_backoff=0)
        self.assertEqual(result["status"], "unreachable")
        self.assertIsNone(result["http_status"])


if __name__ == "__main__":
    unittest.main()
