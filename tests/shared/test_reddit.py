"""Offline tests for growthkit.reddit (fake session, fake clock, no sleeping).

Run from the repo root:
    python3 -m unittest discover -s tests -t .
"""

import json
import os
import sys
import unittest

_SHARED = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "shared")
if _SHARED not in sys.path:
    sys.path.insert(0, _SHARED)

from growthkit import reddit  # noqa: E402

# Imported after growthkit.reddit, which silences urllib3's LibreSSL warning.
import requests  # noqa: E402


# --------------------------------------------------------------------------
# Fixtures: shaped like real Reddit search.rss output (Oct 2026), shortened.
# Entry content is HTML escaped once for XML, so '&amp;amp;' is a literal '&'
# in the post and '&amp;#32;' is Reddit's space entity.
# --------------------------------------------------------------------------

FEED_HEAD = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<feed xmlns="http://www.w3.org/2005/Atom" xmlns:media="http://search.yahoo.com/mrss/">'
    '<category term=" reddit.com" label="r/ reddit.com"/>'
    '<updated>2026-10-24T18:31:02+00:00</updated>'
    '<id>/search.rss?q=notion+alternative</id>'
    '<title>reddit.com: search results - notion alternative</title>'
)

SELF_POST = (
    '<entry><author><name>/u/founder_jane</name>'
    '<uri>https://www.reddit.com/user/founder_jane</uri></author>'
    '<category term="productivity" label="r/productivity"/>'
    '<content type="html">&lt;!-- SC_OFF --&gt;&lt;div class=&quot;md&quot;&gt;&lt;p&gt;I need a '
    'Notion alternative that works offline &amp;amp; syncs.&lt;/p&gt; &lt;p&gt;Budget is '
    '$10/mo.&lt;/p&gt; &lt;/div&gt;&lt;!-- SC_ON --&gt; &amp;#32; submitted by &amp;#32; '
    '&lt;a href=&quot;https://www.reddit.com/user/founder_jane&quot;&gt; /u/founder_jane &lt;/a&gt; '
    '&amp;#32; to &amp;#32; &lt;a href=&quot;https://www.reddit.com/r/productivity/&quot;&gt; '
    'r/productivity &lt;/a&gt; &lt;br/&gt; &lt;span&gt;&lt;a href=&quot;https://www.reddit.com/r/'
    'productivity/comments/1abcde/x/&quot;&gt;[link]&lt;/a&gt;&lt;/span&gt; &amp;#32; '
    '&lt;span&gt;&lt;a href=&quot;https://www.reddit.com/r/productivity/comments/1abcde/x/&quot;'
    '&gt;[comments]&lt;/a&gt;&lt;/span&gt;</content>'
    '<id>t3_1abcde</id>'
    '<link href="https://www.reddit.com/r/productivity/comments/1abcde/looking_for_a_notion_alternative/" />'
    '<updated>2026-10-24T18:22:13+00:00</updated>'
    '<published>2026-10-24T18:22:13+00:00</published>'
    '<title>Looking for a Notion alternative</title></entry>'
)

PROFILE_LINK_POST = (
    '<entry><author><name>/u/singularity-mkting</name></author>'
    '<category term="u_singularity-mkting" label="r/u_singularity-mkting"/>'
    '<content type="html">&lt;table&gt; &lt;tr&gt;&lt;td&gt; &lt;a href=&quot;https://example.com/app'
    '&quot;&gt; &lt;img src=&quot;https://b.thumbs.redditmedia.com/x.jpg&quot; alt=&quot;My app'
    '&quot; /&gt; &lt;/a&gt; &lt;/td&gt;&lt;td&gt; &amp;#32; submitted by &amp;#32; &lt;a href='
    '&quot;https://www.reddit.com/user/singularity-mkting&quot;&gt; /u/singularity-mkting &lt;/a'
    '&gt; &lt;br/&gt; &lt;span&gt;&lt;a href=&quot;https://example.com/app&quot;&gt;[link]&lt;/a'
    '&gt;&lt;/span&gt; &amp;#32; &lt;span&gt;&lt;a href=&quot;https://www.reddit.com/user/'
    'singularity-mkting/comments/2xyz/&quot;&gt;[comments]&lt;/a&gt;&lt;/span&gt; &lt;/td&gt;'
    '&lt;/tr&gt;&lt;/table&gt;</content>'
    '<id>t3_2xyz</id>'
    '<link href="https://www.reddit.com/user/singularity-mkting/comments/2xyz/best_notion_alternative/" />'
    '<updated>2026-10-24T18:25:00+00:00</updated>'
    '<title>Best Notion alternative in 2026</title></entry>'
)

SUBREDDIT_ENTRY = (
    '<entry><id>t5_2qh1i</id><title>r/Notion</title>'
    '<link href="https://www.reddit.com/r/Notion/" /></entry>'
)

FEED = FEED_HEAD + SELF_POST + PROFILE_LINK_POST + SUBREDDIT_ENTRY + "</feed>"
EMPTY_FEED = FEED_HEAD + "</feed>"

LISTING = {
    "kind": "Listing",
    "data": {
        "children": [
            {
                "kind": "t3",
                "data": {
                    "id": "1abcde",
                    "name": "t3_1abcde",
                    "title": "Looking for a Notion alternative",
                    "subreddit": "productivity",
                    "author": "founder_jane",
                    "permalink": "/r/productivity/comments/1abcde/looking_for_a_notion_alternative/",
                    "url": "https://www.reddit.com/r/productivity/comments/1abcde/looking_for_a_notion_alternative/",
                    "is_self": True,
                    "created_utc": 1792866133.0,
                    "selftext": "I need a Notion alternative that works offline.",
                    "score": 14,
                    "num_comments": 9,
                    "upvote_ratio": 0.93,
                    "locked": False,
                    "archived": False,
                    "over_18": False,
                    "link_flair_text": "Question",
                },
            },
            {
                "kind": "t3",
                "data": {
                    "id": "2xyz",
                    "title": "Best Notion alternative in 2026",
                    "subreddit": "u_singularity-mkting",
                    "author": "singularity-mkting",
                    "permalink": "/user/singularity-mkting/comments/2xyz/best/",
                    "url": "https://example.com/app",
                    "is_self": False,
                    "created_utc": 1792866300,
                    "selftext": "",
                    "score": 1,
                    "num_comments": 0,
                    "locked": True,
                    "archived": False,
                },
            },
        ]
    },
}


# --------------------------------------------------------------------------
# Fakes
# --------------------------------------------------------------------------


class FakeResponse:
    def __init__(self, status_code=200, text="", headers=None, json_data=None):
        self.status_code = status_code
        self.text = text if json_data is None else json.dumps(json_data)
        self.headers = dict(headers or {})
        self._json = json_data

    def json(self):
        if self._json is not None:
            return self._json
        return json.loads(self.text)  # raises ValueError like requests does


class FakeSession:
    """Returns queued responses in order and records every call."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append({"method": method, "url": url, **kwargs})
        if not self.responses:
            raise AssertionError("unexpected request: %s %s" % (method, url))
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class FakeClock:
    """Monotonic clock whose sleep() only advances time."""

    def __init__(self):
        self.now = 1000.0
        self.sleeps = []

    def clock(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


def rss(text=FEED, remaining="99.0", reset="300", status=200):
    headers = {}
    if remaining is not None:
        headers["x-ratelimit-remaining"] = remaining
        headers["x-ratelimit-used"] = "1"
    if reset is not None:
        headers["x-ratelimit-reset"] = reset
    return FakeResponse(status, text=text, headers=headers)


def make_client(session, env=None, clock=None):
    clock = clock or FakeClock()
    client = reddit.RedditClient(
        session=session, env=env or {}, sleep=clock.sleep, clock=clock.clock,
        log=lambda message: None,
    )
    return client, clock


# --------------------------------------------------------------------------
# Tests
# --------------------------------------------------------------------------


class UserAgentTests(unittest.TestCase):
    def test_default_names_no_person(self):
        self.assertNotIn("/u/", reddit.DEFAULT_USER_AGENT)
        self.assertNotIn("ekinci", reddit.DEFAULT_USER_AGENT.lower())
        self.assertEqual(reddit.resolve_user_agent({}), reddit.DEFAULT_USER_AGENT)
        self.assertEqual(reddit.resolve_user_agent({"REDDIT_USER_AGENT": "  "}), reddit.DEFAULT_USER_AGENT)

    def test_env_override_is_sent(self):
        ua = "python:acme-growth:2.0 (by /u/acme_dev)"
        session = FakeSession(rss())
        client, _ = make_client(session, env={"REDDIT_USER_AGENT": ua})
        client.search("notion")
        self.assertEqual(session.calls[0]["headers"]["User-Agent"], ua)


class AtomParserTests(unittest.TestCase):
    def test_parses_posts_only(self):
        posts = reddit.parse_atom(FEED)
        self.assertEqual([p["id"] for p in posts], ["1abcde", "2xyz"])  # t5_ entry skipped

    def test_self_post_fields(self):
        post = reddit.parse_atom(FEED)[0]
        self.assertEqual(post["fullname"], "t3_1abcde")
        self.assertEqual(post["title"], "Looking for a Notion alternative")
        self.assertEqual(post["subreddit"], "productivity")
        self.assertFalse(post["is_user_profile"])
        self.assertEqual(post["author"], "founder_jane")
        self.assertTrue(post["url"].startswith("https://www.reddit.com/r/productivity/comments/1abcde/"))
        self.assertEqual(post["created_utc"], 1792866133.0)  # 2026-10-24T18:22:13Z
        # Entities decoded once, tags stripped, Reddit's footer removed.
        self.assertEqual(post["body_text"],
                         "I need a Notion alternative that works offline & syncs. Budget is $10/mo.")
        self.assertIsNone(post["score"])
        self.assertIsNone(post["num_comments"])
        self.assertEqual(post["source"], "rss")

    def test_profile_link_post(self):
        post = reddit.parse_atom(FEED)[1]
        self.assertTrue(post["is_user_profile"])
        self.assertEqual(post["body_text"], "")  # only a thumbnail and the footer
        self.assertEqual(post["created_utc"], 1792866300.0)  # falls back to <updated>
        # The shared URL survives although the footer holding it is dropped.
        self.assertEqual(post["external_url"], "https://example.com/app")

    def test_self_post_has_no_external_url(self):
        # Its '[link]' points back at its own thread (here under another slug).
        self.assertIsNone(reddit.parse_atom(FEED)[0]["external_url"])

    def test_crosspost_link_is_made_absolute(self):
        entry = SELF_POST.replace(
            "&lt;a href=&quot;https://www.reddit.com/r/productivity/comments/1abcde/x/&quot;&gt;[link]",
            "&lt;a href=&quot;/r/notioncreations/comments/9zzz/original/&quot;&gt;[link]",
        )
        post = reddit.parse_atom(FEED_HEAD + entry + "</feed>")[0]
        self.assertEqual(post["external_url"],
                         "https://www.reddit.com/r/notioncreations/comments/9zzz/original/")

    def test_empty_feed(self):
        self.assertEqual(reddit.parse_atom(EMPTY_FEED), [])

    def test_rejects_non_feeds(self):
        with self.assertRaises(ValueError):
            reddit.parse_atom("<html><body>whoa there, pardner!</body></html>")
        with self.assertRaises(ValueError):
            reddit.parse_atom("<html><body><p>unclosed")
        with self.assertRaises(ValueError):
            reddit.parse_atom("<!DOCTYPE html><html><body>blocked</body></html>")
        with self.assertRaises(ValueError):
            reddit.parse_atom('<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]>'
                              '<feed xmlns="http://www.w3.org/2005/Atom">&a;</feed>')
        with self.assertRaises(ValueError):
            reddit.parse_atom("")


class ListingParserTests(unittest.TestCase):
    def test_keeps_counts_and_moderation_flags(self):
        posts = reddit.parse_listing_json(LISTING, source="oauth")
        first, second = posts
        self.assertEqual(first["score"], 14)
        self.assertEqual(first["num_comments"], 9)
        self.assertEqual(first["upvote_ratio"], 0.93)
        self.assertFalse(first["locked"])
        self.assertEqual(first["link_flair_text"], "Question")
        self.assertIsNone(first["external_url"])
        self.assertEqual(first["url"], "https://www.reddit.com/r/productivity/comments/1abcde/looking_for_a_notion_alternative/")
        self.assertEqual(first["source"], "oauth")

        self.assertTrue(second["is_user_profile"])
        self.assertTrue(second["locked"])
        self.assertEqual(second["fullname"], "t3_2xyz")
        self.assertEqual(second["external_url"], "https://example.com/app")
        self.assertEqual(second["created_utc"], 1792866300.0)

    def test_rejects_non_listing(self):
        with self.assertRaises(ValueError):
            reddit.parse_listing_json({"error": 403})
        with self.assertRaises(ValueError):
            reddit.parse_listing_json([])

    def test_skips_malformed_children(self):
        good = LISTING["data"]["children"][0]
        listing = {"data": {"children": [{"kind": "t3", "data": "oops"}, "x", good]}}
        self.assertEqual([p["id"] for p in reddit.parse_listing_json(listing)], ["1abcde"])


class QueryHelperTests(unittest.TestCase):
    def test_build_or_query(self):
        query = reddit.build_or_query(["notion alternative", " obsidian ", "", '"exact phrase"', "a OR b"])
        self.assertEqual(query, '"notion alternative" OR obsidian OR "exact phrase" OR (a OR b)')
        self.assertEqual(reddit.build_or_query(["crm"]), "crm")

    def test_operators_inside_a_term_stay_grouped(self):
        # Two phrases or an AND inside one term must not leak into the OR chain.
        self.assertEqual(reddit.build_or_query(['"a" AND "b"', "c"]), '("a" AND "b") OR c')
        self.assertEqual(reddit.build_or_query(['"a b" "c d"', "e"]), '("a b" "c d") OR e')
        self.assertEqual(reddit.build_or_query(["notion", "NOT spam"]), "notion OR (NOT spam)")
        # Lower-case 'or' is not an operator for Reddit, so it stays a phrase.
        self.assertEqual(reddit.build_or_query(["this or that"]), '"this or that"')

    def test_build_or_query_errors(self):
        with self.assertRaises(ValueError):
            reddit.build_or_query([" ", ""])
        with self.assertRaises(ValueError):
            reddit.build_or_query(["word%d long keyword" % i for i in range(40)])

    def test_normalize_subreddit(self):
        self.assertEqual(reddit.normalize_subreddit("r/SaaS"), "SaaS")
        self.assertEqual(reddit.normalize_subreddit("/r/SaaS/"), "SaaS")
        self.assertEqual(reddit.normalize_subreddit("SaaS+startups"), "SaaS+startups")
        self.assertIsNone(reddit.normalize_subreddit(None))
        with self.assertRaises(ValueError):
            reddit.normalize_subreddit("SaaS/../x")

    def test_within_time_filter(self):
        now = 2_000_000.0
        posts = [{"created_utc": now - 3600}, {"created_utc": now - 10 * 86400}, {"created_utc": None}]
        kept = reddit.within_time_filter(posts, "week", now=now)
        self.assertEqual(kept, [posts[0], posts[2]])
        self.assertEqual(reddit.within_time_filter(posts, "all", now=now), posts)

    def test_rate_headers_any_case(self):
        rate = reddit.parse_rate_headers({"X-Ratelimit-Remaining": "0.0", "X-Ratelimit-Reset": "42"})
        self.assertEqual(rate, {"used": None, "remaining": 0.0, "reset": 42.0})


class RssSearchTests(unittest.TestCase):
    def test_ok(self):
        session = FakeSession(rss())
        client, clock = make_client(session)
        result = client.search("notion alternative")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["method"], "rss")
        self.assertEqual(result["http_status"], 200)
        self.assertEqual(len(result["posts"]), 2)
        self.assertEqual(result["errors"], [])
        self.assertIn(reddit.RSS_NOTE, result["notes"])
        self.assertEqual(len(result["requests"]), 1)
        self.assertEqual(result["requests"][0]["status"], "ok")
        call = session.calls[0]
        self.assertEqual(call["url"], "https://www.reddit.com/search.rss")
        self.assertEqual(call["params"]["sort"], "relevance")
        self.assertEqual(call["params"]["limit"], 100)
        self.assertEqual(call["params"]["t"], "week")
        self.assertNotIn("restrict_sr", call["params"])
        self.assertEqual(clock.sleeps, [])

    def test_subreddit_search(self):
        session = FakeSession(rss())
        client, _ = make_client(session)
        result = client.search("crm", subreddit="r/SaaS", sort="new", time_filter="month", limit=25)
        call = session.calls[0]
        self.assertEqual(call["url"], "https://www.reddit.com/r/SaaS/search.rss")
        self.assertEqual(call["params"]["restrict_sr"], 1)
        self.assertEqual(result["subreddit"], "SaaS")

    def test_empty_is_not_failure(self):
        session = FakeSession(rss(text=EMPTY_FEED))
        client, _ = make_client(session)
        result = client.search("zqxvbrandnotreal")
        self.assertEqual(result["status"], "empty")
        self.assertEqual(result["method"], "rss")
        self.assertEqual(result["errors"], [])
        self.assertEqual(len(session.calls), 1)  # no JSON fallback for a valid empty feed

    def test_invalid_arguments(self):
        client, _ = make_client(FakeSession())
        for kwargs in [{"sort": "best"}, {"time_filter": "decade"}, {"limit": 0},
                       {"limit": 101}, {"limit": True}, {"subreddit": "a b"}]:
            with self.assertRaises(ValueError):
                client.search("crm", **kwargs)
        with self.assertRaises(ValueError):
            client.search("   ")


class RateLimitTests(unittest.TestCase):
    def test_waits_until_reset_before_next_request(self):
        session = FakeSession(rss(remaining="0.0", reset="42"), rss())
        client, clock = make_client(session)
        client.search("first")
        self.assertEqual(clock.sleeps, [])  # no sleep until another request is due
        result = client.search("second")
        self.assertEqual(clock.sleeps, [43.0])  # reset + 1 s margin
        self.assertEqual(result["requests"][0]["waited_seconds"], 43.0)
        self.assertEqual(result["status"], "ok")

    def test_wait_counts_time_already_elapsed(self):
        session = FakeSession(rss(remaining="0", reset="42"), rss())
        client, clock = make_client(session)
        client.search("first")
        clock.now += 30
        client.search("second")
        self.assertEqual(clock.sleeps, [13.0])

    def test_wait_is_capped_at_70_seconds(self):
        session = FakeSession(rss(remaining="0.0", reset="600"), rss())
        client, clock = make_client(session)
        client.search("first")
        client.search("second")
        self.assertEqual(clock.sleeps, [70.0])

    def test_no_wait_while_quota_remains(self):
        session = FakeSession(rss(remaining="3.0", reset="42"), rss())
        client, clock = make_client(session)
        client.search("first")
        client.search("second")
        self.assertEqual(clock.sleeps, [])

    def test_429_sleeps_for_reset_and_retries_once(self):
        session = FakeSession(rss(status=429, text="", remaining="0.0", reset="10"), rss())
        client, clock = make_client(session)
        result = client.search("notion")
        self.assertEqual(clock.sleeps, [11.0])
        self.assertEqual(result["status"], "ok")
        self.assertEqual([r["status"] for r in result["requests"]], ["rate_limited", "ok"])
        self.assertEqual([r["attempt"] for r in result["requests"]], [1, 2])
        self.assertEqual(result["errors"], [])

    def test_second_429_fails_without_json_fallback(self):
        session = FakeSession(
            rss(status=429, text="", remaining="0.0", reset="10"),
            rss(status=429, text="", remaining="0.0", reset="10"),
        )
        client, clock = make_client(session)
        result = client.search("notion")
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["failure_reason"], "rate_limited")
        self.assertEqual(len(session.calls), 2)  # JSON shares the quota, so it is skipped
        self.assertEqual(len(result["errors"]), 1)
        self.assertIn("rate_limited", result["errors"][0])
        self.assertEqual(clock.sleeps, [11.0])

    def test_429_without_reset_header_uses_default_wait(self):
        session = FakeSession(rss(status=429, text="", remaining=None, reset=None), rss())
        client, clock = make_client(session)
        client.search("notion")
        self.assertEqual(clock.sleeps, [reddit.DEFAULT_429_WAIT_SECONDS])

    def test_429_honours_retry_after_if_sent(self):
        response = FakeResponse(429, headers={"Retry-After": "5"})
        session = FakeSession(response, rss())
        client, clock = make_client(session)
        client.search("notion")
        self.assertEqual(clock.sleeps, [6.0])


class FallbackTests(unittest.TestCase):
    def test_rss_error_recovered_by_json(self):
        session = FakeSession(rss(status=500, text="oops"), FakeResponse(200, json_data=LISTING))
        client, _ = make_client(session)
        result = client.search("notion")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["method"], "json")
        self.assertEqual(result["posts"][0]["score"], 14)
        self.assertEqual(result["errors"], [])
        self.assertTrue(any("RSS feed failed: http_error (HTTP 500)" in n for n in result["notes"]))
        self.assertEqual(session.calls[1]["url"], "https://www.reddit.com/search.json")

    def test_block_page_then_json_403_and_json_is_not_retried(self):
        session = FakeSession(
            rss(text="<html><body>whoa there, pardner!</body></html>"),
            FakeResponse(403, text="Forbidden"),
            rss(status=503, text=""),
        )
        client, _ = make_client(session)
        result = client.search("notion")
        self.assertEqual(result["status"], "failed")
        self.assertEqual([r["status"] for r in result["requests"]], ["parse_error", "blocked"])
        self.assertEqual(len(result["errors"]), 2)
        self.assertTrue(client.json_blocked)

        second = client.search("obsidian")
        self.assertEqual(second["status"], "failed")
        self.assertEqual(len(session.calls), 3)  # JSON not tried again after its 403
        self.assertEqual(second["failure_reason"], "http_error")

    def test_unexpected_json_shape_is_parse_error_not_crash(self):
        # 'children' as a number raises TypeError inside the parser.
        session = FakeSession(rss(status=500, text=""),
                              FakeResponse(200, json_data={"data": {"children": 5}}))
        client, _ = make_client(session)
        result = client.search("notion")
        self.assertEqual(result["status"], "failed")
        self.assertEqual([r["status"] for r in result["requests"]], ["http_error", "parse_error"])
        self.assertEqual(result["failure_reason"], "parse_error")

    def test_network_error(self):
        session = FakeSession(requests.ConnectionError("proxy down"), requests.ConnectionError("proxy down"))
        client, _ = make_client(session)
        result = client.search("notion")
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["failure_reason"], "network_error")
        self.assertIn("proxy down", result["errors"][0])


class OAuthTests(unittest.TestCase):
    ENV = {"REDDIT_CLIENT_ID": "cid", "REDDIT_CLIENT_SECRET": "secret"}

    def test_oauth_preferred_when_credentials_exist(self):
        session = FakeSession(
            FakeResponse(200, json_data={"access_token": "tok", "expires_in": 86400}),
            FakeResponse(200, json_data=LISTING, headers={"x-ratelimit-remaining": "99"}),
            FakeResponse(200, json_data=LISTING),
        )
        client, _ = make_client(session, env=self.ENV)
        result = client.search("notion", subreddit="SaaS")
        token_call, search_call = session.calls[0], session.calls[1]
        self.assertEqual(token_call["method"], "POST")
        self.assertEqual(token_call["url"], reddit.TOKEN_URL)
        self.assertEqual(token_call["auth"], ("cid", "secret"))
        self.assertEqual(token_call["data"], {"grant_type": "client_credentials"})
        self.assertEqual(search_call["url"], "https://oauth.reddit.com/r/SaaS/search")
        self.assertEqual(search_call["headers"]["Authorization"], "bearer tok")
        self.assertEqual(search_call["params"]["raw_json"], 1)
        self.assertEqual(result["method"], "oauth")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["posts"][0]["num_comments"], 9)
        self.assertNotIn(reddit.RSS_NOTE, result["notes"])

        client.search("obsidian")
        self.assertEqual(len(session.calls), 3)  # token reused

    def test_rejected_credentials_fall_back_to_rss_once(self):
        session = FakeSession(FakeResponse(401, text="unauthorized"), rss(), rss())
        client, _ = make_client(session, env=self.ENV)
        result = client.search("notion")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["method"], "rss")
        self.assertEqual(result["errors"], [])
        self.assertTrue(any("OAuth token request failed: auth_error (HTTP 401)" in n
                            and "REDDIT_CLIENT_ID" in n for n in result["notes"]))
        second = client.search("obsidian")
        self.assertEqual(len(session.calls), 3)  # no second token attempt
        self.assertTrue(any("OAuth skipped" in n for n in second["notes"]))

    def test_oauth_host_has_its_own_rate_window(self):
        session = FakeSession(
            FakeResponse(200, json_data={"access_token": "tok", "expires_in": 86400}),
            FakeResponse(200, json_data=LISTING,
                         headers={"x-ratelimit-remaining": "0", "x-ratelimit-reset": "20"}),
            FakeResponse(200, json_data=LISTING),
        )
        client, clock = make_client(session, env=self.ENV)
        client.search("notion")
        client.search("obsidian")
        self.assertEqual(clock.sleeps, [21.0])


if __name__ == "__main__":
    unittest.main()
