"""Offline tests for growthkit.html (text cleaning, hidden nodes, page facts).

Run from the repo root:
    python3 -m unittest discover -s tests -t .
"""

import json
import unittest

from tests import _paths
from growthkit import html  # noqa: E402

FIXTURES = ("shared", "fixtures")


def fixture(name):
    return _paths.read_fixture(*FIXTURES, name)


class CleanTextTests(unittest.TestCase):
    def test_words_are_never_glued_across_elements(self):
        soup = html.parse('<h1>Where teams and agents<br><span>Think</span><span>together.</span></h1>')
        self.assertEqual(html.clean_text(soup.h1), "Where teams and agents Think together.")

    def test_inline_emphasis_keeps_spaces(self):
        soup = html.parse("<h3>The best AI is<em>your</em>AI</h3>")
        self.assertEqual(html.clean_text(soup.h3), "The best AI is your AI")

    def test_no_space_before_punctuation(self):
        soup = html.parse("<p>Price: $10 <span>/ month</span><span>, billed yearly</span> .</p>")
        self.assertEqual(html.clean_text(soup.p), "Price: $10 / month, billed yearly.")

    def test_leading_dot_words_keep_their_space(self):
        cases = {
            "<p>Built with <b>.NET</b> and Node</p>": "Built with .NET and Node",
            "<p>Import <code>.csv</code> or <code>.xlsx</code> files</p>": "Import .csv or .xlsx files",
            "<p>It costs <span>.5</span> cents</p>": "It costs .5 cents",
            "<p>Hello <b>world</b> !</p>": "Hello world!",
            "<p>Save <b>50</b> %</p>": "Save 50%",
        }
        for markup, expected in cases.items():
            with self.subTest(markup=markup):
                self.assertEqual(html.clean_text(html.parse(markup).p), expected)

    def test_whitespace_and_newlines_collapse(self):
        self.assertEqual(html.clean_text("  a\n\n  b\t c  "), "a b c")
        self.assertEqual(html.clean_text(None), "")

    def test_collapse_repeats_reduces_responsive_variants(self):
        text = " ".join(["The product development system for teams and agents"] * 3)
        self.assertEqual(html.collapse_repeats(text), "The product development system for teams and agents")
        soup = html.parse("<h2><span>The product</span><span>development system</span>"
                          "<span>The product development</span><span>system</span></h2>")
        self.assertEqual(html.clean_text(soup.h2, collapse=True), "The product development system")

    def test_collapse_repeats_leaves_short_or_distinct_text(self):
        self.assertEqual(html.collapse_repeats("Go Go"), "Go Go")
        self.assertEqual(html.collapse_repeats("one two three four five six"), "one two three four five six")

    def test_word_count(self):
        self.assertEqual(html.word_count("Hello, world - 42 times"), 4)
        self.assertEqual(html.word_count(""), 0)
        # Ten CJK characters count as about five words.
        self.assertEqual(html.word_count("\u65e5\u672c\u8a9e\u306e\u6587\u7ae0\u3067\u3059\u3088\u306d"), 6)

    def test_dedupe_texts(self):
        self.assertEqual(html.dedupe_texts(["Pricing", "pricing.", "Docs", ""]), ["Pricing", "Docs"])
        self.assertEqual(
            html.dedupe_texts(["Get started", "Get started free", "Docs"], containment=True),
            ["Get started free", "Docs"],
        )


class DecodeTests(unittest.TestCase):
    def test_meta_charset_is_used_when_header_has_none(self):
        body = '<html><head><meta charset="windows-1252"></head><body>caf\xe9 \u20ac na\xefve</body></html>'
        raw = body.encode("cp1252")
        text, encoding = html.decode_bytes(raw, None)
        self.assertEqual(encoding, "windows-1252")
        self.assertIn("caf\xe9", text)

    def test_utf8_without_any_charset_is_not_mangled(self):
        # requests' response.text would decode this as ISO-8859-1 (mojibake).
        raw = "<p>caf\xe9 \u2192 na\xefve</p>".encode("utf-8")
        text, encoding = html.decode_bytes(raw, None)
        self.assertEqual(encoding, "utf-8")
        self.assertIn("caf\xe9 \u2192", text)

    def test_header_charset_wins_over_meta(self):
        raw = '<meta charset="utf-8"><p>\xe9</p>'.encode("latin-1")
        text, encoding = html.decode_bytes(raw, "ISO-8859-1")
        # ISO-8859-1 is decoded as Windows-1252, as browsers do.
        self.assertEqual(encoding, "cp1252")
        self.assertIn("\xe9", text)

    def test_latin1_label_keeps_cp1252_curly_quotes(self):
        raw = "<p>\u201cHello\u201d \u2026 caf\xe9</p>".encode("cp1252")
        text, _ = html.decode_bytes(raw, "iso-8859-1")
        self.assertIn("\u201cHello\u201d", text)
        self.assertNotIn("\x93", text)

    def test_utf8_body_with_a_latin1_label_is_read_as_utf8(self):
        raw = "<p>M\xfcnchen caf\xe9</p>".encode("utf-8")
        text, encoding = html.decode_bytes(raw, "ISO-8859-1")
        self.assertEqual(encoding, "utf-8")
        self.assertIn("M\xfcnchen caf\xe9", text)

    def test_one_stray_byte_does_not_garble_a_declared_utf8_page(self):
        raw = "<p>Caf\xe9 M\xfcnchen</p><p>w".encode("utf-8") + b"\xff" + b"rd</p>"
        text, encoding = html.decode_bytes(raw, "utf-8")
        self.assertEqual(encoding, "utf-8")
        self.assertIn("Caf\xe9 M\xfcnchen", text)
        self.assertIn("\ufffd", text)

    def test_undeclared_non_utf8_falls_back_to_cp1252(self):
        text, encoding = html.decode_bytes("<p>caf\xe9</p>".encode("cp1252"), None)
        self.assertEqual(encoding, "cp1252")
        self.assertIn("caf\xe9", text)

    def test_bom_and_unknown_charset(self):
        text, encoding = html.decode_bytes(b"\xef\xbb\xbfUser-agent: *", None, is_html=False)
        self.assertEqual(text, "User-agent: *")
        text, encoding = html.decode_bytes("x\xe9".encode("utf-8"), "no-such-charset")
        self.assertEqual(text, "x\xe9")


class HiddenNodeTests(unittest.TestCase):
    def reason(self, markup):
        return html.hidden_reason(html.parse(markup).find(True))

    def test_hidden_reasons(self):
        self.assertEqual(self.reason("<div hidden>x</div>"), "hidden-attribute")
        self.assertIsNone(self.reason('<div hidden="until-found">x</div>'))
        self.assertEqual(self.reason('<div aria-hidden="true">x</div>'), "aria-hidden")
        self.assertEqual(self.reason('<div style="color:red; display: none !important">x</div>'), "inline-style")
        self.assertEqual(self.reason('<div style="visibility:hidden">x</div>'), "inline-style")
        self.assertIsNone(self.reason('<div style="opacity:0">x</div>'))  # fade-in animations
        self.assertEqual(self.reason('<span class="sr-only">x</span>'), "screen-reader-only")
        self.assertEqual(self.reason('<div class="hidden">x</div>'), "hidden-class")
        self.assertIsNone(self.reason('<div class="hidden md:block">x</div>'))
        self.assertIsNone(self.reason('<div class="d-none d-md-block">x</div>'))
        self.assertIsNone(self.reason('<div class="md:hidden">x</div>'))
        self.assertEqual(self.reason("<dialog>x</dialog>"), "closed-dialog")
        self.assertIsNone(self.reason("<dialog open>x</dialog>"))
        self.assertEqual(self.reason('<input type="hidden" name="a">'), "hidden-input")

    def test_is_hidden_checks_ancestors(self):
        soup = html.parse('<div style="display:none"><p><input name="x"></p></div><input name="y">')
        inputs = soup.find_all("input")
        self.assertTrue(html.is_hidden(inputs[0]))
        self.assertFalse(html.is_hidden(inputs[1]))

    def test_strip_invisible_removes_keyword_stuffing(self):
        soup = html.parse(fixture("saas_home.html"))
        counts = html.strip_invisible(soup)
        text = html.clean_text(soup.body)
        self.assertNotIn("award winning", text)
        self.assertNotIn("Screen reader note", text)
        self.assertNotIn("Closed dialog text", text)
        self.assertNotIn("window.dataLayer", text)
        self.assertIn("Everything your team needs", text)
        # The desktop nav uses "hidden md:flex" and must survive.
        self.assertIn("Pricing", text)
        self.assertEqual(counts.get("inline-style"), 1)
        self.assertEqual(counts.get("responsive-duplicate"), 1)
        self.assertEqual(text.count("Trusted by the world's best teams"), 1)

    def test_aria_label_rescues_split_letter_headline(self):
        soup = html.parse(fixture("glued_headings.html"))
        html.strip_invisible(soup)
        self.assertIn("Ship faster", [html.clean_text(h) for h in soup.find_all("h2")])

    def test_mobile_only_element_without_twin_is_kept(self):
        soup = html.parse('<div><a class="md:hidden" href="/signup">Start free</a><p>Other</p></div>')
        html.strip_invisible(soup)
        self.assertIn("Start free", html.clean_text(soup))

    def test_visible_text(self):
        text = html.visible_text('<p>Shown</p><p hidden>Gone</p><script>var x</script>')
        self.assertEqual(text, "Shown")


class JsShellTests(unittest.TestCase):
    def test_spa_shell(self):
        signals = html.js_shell_signals(fixture("spa_shell.html"))
        self.assertTrue(signals["is_js_shell"])
        self.assertEqual(signals["empty_root"], "root")
        self.assertTrue(signals["noscript_js_required"])
        self.assertEqual(signals["visible_words"], 0)

    def test_real_page_is_not_a_shell(self):
        self.assertFalse(html.js_shell_signals(fixture("saas_home.html"))["is_js_shell"])

    def test_short_static_page_with_headline_is_not_a_shell(self):
        signals = html.js_shell_signals(fixture("static_small.html"))
        self.assertFalse(signals["is_js_shell"])
        self.assertEqual(signals["script_count"], 3)

    def test_page_with_only_scripts_is_a_shell(self):
        markup = "<html><body>" + "<script src='/a.js'></script>" * 8 + "</body></html>"
        self.assertTrue(html.js_shell_signals(markup)["is_js_shell"])

    def test_large_inline_bundle_with_little_text(self):
        markup = "<html><body><h1>App</h1><p>Loading your workspace</p><script>%s</script></body></html>" % ("x" * 25000)
        self.assertTrue(html.js_shell_signals(markup)["is_js_shell"])

    def test_next_root_with_ssr_content_is_not_a_shell(self):
        body = " ".join(["word"] * 80)
        markup = '<div id="__next"><h1>Hi</h1><p>%s</p></div><script src="a"></script>' % body
        self.assertFalse(html.js_shell_signals(markup)["is_js_shell"])

    def test_bytes_input(self):
        self.assertTrue(html.js_shell_signals(fixture("spa_shell.html").encode("utf-8"))["is_js_shell"])


class ClassifierTests(unittest.TestCase):
    def test_classify_href(self):
        host = "www.acme.test"
        cases = {
            "https://www.acme.test/signup": "signup",
            "https://www.acme.test/login?signup=true": "signup",
            "https://app.acme.test/login": "login",
            "https://app.acme.test/": "app",
            "https://www.acme.test/contact-sales": "demo",
            "https://calendly.com/acme/30min": "demo",
            "https://www.acme.test/pricing": "pricing",
            "https://www.acme.test/checkout?plan=pro": "buy",
            "https://apps.apple.com/app/id123": "download",
            "https://www.acme.test/download/Acme.dmg": "download",
            "mailto:hi@acme.test": "contact",
            "https://www.acme.test/docs/api": "docs",
            "https://twitter.com/AcmeHQ": "social",
            "https://example.org/blog/how-to-start-a-company": "external",
            "https://www.acme.test/blog/startups": None,
            "#features": None,
            "javascript:void(0)": None,
        }
        for href, expected in cases.items():
            with self.subTest(href=href):
                self.assertEqual(html.classify_href(href, host), expected)

    def test_classify_cta_text_uses_word_boundaries(self):
        cases = {
            "Get started": "signup",
            "Get Notion free": "signup",
            "Start for free": "signup",
            "Book a demo": "demo",
            "Talk to sales": "demo",
            "Log in": "login",
            "See plans": "pricing",
            "Subscribe": "subscribe",
            "Learn more": "learn",
            "Startups": None,
            "Industry": None,
            "Customer Requests": None,
            "Buyer guide": None,
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(html.classify_cta_text(text), expected)

    def test_classify_social_excludes_share_links(self):
        self.assertEqual(html.classify_social("https://x.com/AcmeHQ"), "x")
        self.assertEqual(html.classify_social("https://www.linkedin.com/company/acme/"), "linkedin")
        self.assertEqual(html.classify_social("https://www.youtube.com/@acme"), "youtube")
        self.assertEqual(html.classify_social("https://bsky.app/profile/acme.test"), "bluesky")
        self.assertIsNone(html.classify_social("https://twitter.com/intent/tweet?text=x"))
        self.assertIsNone(html.classify_social("https://www.facebook.com/sharer/sharer.php?u=x"))
        self.assertIsNone(html.classify_social("https://www.linkedin.com/shareArticle?url=x"))
        self.assertIsNone(html.classify_social("https://github.com/features/actions"))
        self.assertIsNone(html.classify_social("not a url"))

    def test_site_domain(self):
        self.assertEqual(html.site_domain("app.linear.app"), "linear.app")
        self.assertEqual(html.site_domain("www.example.co.uk"), "example.co.uk")
        self.assertEqual(html.site_domain("localhost"), "localhost")


class PageFactsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.facts = html.page_facts(fixture("saas_home.html"), "https://www.acme.test/")

    def test_json_serializable(self):
        json.dumps(self.facts)

    def test_head_facts(self):
        facts = self.facts
        self.assertEqual(facts["title"], "Acme - The AI workspace for teams")
        self.assertEqual(facts["lang"], "en")
        self.assertEqual(facts["meta"]["canonical"], "https://www.acme.test/")
        self.assertEqual(facts["meta"]["robots"], {"robots": "index, follow, max-snippet:-1"})
        self.assertEqual(facts["meta"]["og"]["site_name"], "Acme")
        self.assertEqual(facts["meta"]["twitter"]["card"], "summary_large_image")
        self.assertEqual(facts["meta"]["hreflang_count"], 2)

    def test_headings_are_clean_and_deduplicated(self):
        headings = self.facts["headings"]
        self.assertEqual(headings["h1"], ["Where teams and agents Think together."])
        self.assertEqual(headings["h2"].count("Trusted by the world's best teams"), 1)
        self.assertNotIn("Product", headings["h2"])

    def test_outline_is_ordered_main_content(self):
        outline = self.facts["outline"]
        self.assertEqual([b["heading"] for b in outline][:3], [
            "Where teams and agents Think together.",
            "Trusted by the world's best teams",
            "Everything your team needs",
        ])
        self.assertEqual(outline[0]["heading_level"], 1)
        self.assertTrue(any(b["has_blockquote"] for b in outline))
        self.assertTrue(any(b["has_details"] for b in outline))
        all_text = " ".join(b["text"] for b in outline)
        self.assertNotIn("We use cookies", all_text)
        self.assertNotIn("Careers", all_text)
        self.assertEqual(self.facts["main_text"].count("Trusted by the world's best teams"), 1)

    def test_cta_inventory_has_zones_and_href_intent(self):
        ctas = self.facts["ctas"]
        hero = [c for c in ctas if c["zone"] == "hero"]
        self.assertEqual([c["text"] for c in hero], ["Get Acme free", "Request a demo"])
        self.assertEqual(hero[0]["intent"], "signup")
        self.assertEqual(hero[0]["intent_source"], "href")
        self.assertEqual(hero[1]["intent"], "demo")
        nav = {c["text"]: c["intent"] for c in ctas if c["zone"] == "nav"}
        self.assertEqual(nav, {"Pricing": "pricing", "Log in": "login", "Get Acme free": "signup"})
        texts = [c["text"] for c in ctas]
        for noise in ("Accept all", "Reject all", "Menu", "Previous slide", "Inbox", "Product", "Careers",
                      "See features"):
            self.assertNotIn(noise, texts)
        book = [c for c in ctas if c["text"] == "Book a call"][0]
        self.assertEqual(book["intent"], "demo")
        self.assertGreaterEqual(self.facts["cta_scan"]["ui_controls_skipped"], 3)

    def test_hero_mockup_buttons_and_logo_links_are_not_ctas(self):
        markup = ("<main><section><h1>Plan and build products together</h1>"
                  "<a href='https://app.acme.test/auth/sso/google'>Sign up with Google</a>"
                  "<a href='/customers/openai'>OpenAI</a><button>Copy issue URL</button>"
                  "<div class='logoWallMarquee'><a class='btn ghost' href='/customers/figma'>Figma</a></div>"
                  "<button>Start free trial</button></section><section><h2>More</h2><p>x</p></section></main>")
        facts = html.page_facts(markup, "https://www.acme.test/")
        ctas = {c["text"]: c for c in facts["ctas"]}
        self.assertEqual(set(ctas), {"Sign up with Google", "Start free trial"})
        self.assertEqual(ctas["Sign up with Google"]["intent"], "signup")
        self.assertEqual(ctas["Sign up with Google"]["intent_source"], "text")
        self.assertEqual(ctas["Start free trial"]["zone"], "hero")

    def test_forms_count_questions_not_elements(self):
        forms = self.facts["forms"]
        signup = forms[0]
        self.assertEqual(signup["kind"], "signup")
        self.assertTrue(signup["primary_candidate"])
        self.assertEqual(signup["zone"], "body")
        # email, password, team size (3 radios), company, terms checkbox
        self.assertEqual(signup["questions"], 5)
        self.assertEqual(signup["dropped"], {"hidden": 1, "honeypot": 1, "non_field": 1})
        radio = [f for f in signup["fields"] if f["type"] == "radio"][0]
        self.assertEqual(radio["options"], 3)
        self.assertEqual(radio["label"], "Team size")
        company = [f for f in signup["fields"] if f["name"] == "company"][0]
        self.assertTrue(company["optional_label"])
        self.assertFalse(company["required"])
        self.assertTrue(signup["has_new_password"])
        self.assertEqual(forms[1]["kind"], "newsletter")
        self.assertEqual(forms[1]["zone"], "footer")
        self.assertEqual(forms[2]["kind"], "search")
        self.assertEqual(sum(1 for f in forms if f["primary_candidate"]), 1)

    def test_visible_website_field_with_autocomplete_off_is_a_question(self):
        markup = ("<main><section><h1>Talk to our sales team</h1><form action='/demo' autocomplete='off'>"
                  "<label for='n'>Name</label><input id='n' name='name' autocomplete='off' required>"
                  "<label for='w'>Company website</label><input id='w' name='website' autocomplete='off' required>"
                  "<input name='url' tabindex='-1'>"
                  "<button type='submit'>Request demo</button></form></section></main>")
        form = html.page_facts(markup, "https://acme.test/")["forms"][0]
        self.assertEqual([q["name"] for q in form["fields"]], ["name", "website"])
        self.assertEqual(form["dropped"]["honeypot"], 1)  # the tabindex=-1 "url" trap

    def test_embedded_forms(self):
        self.assertEqual([f["provider"] for f in self.facts["embedded_forms"]], ["hubspot"])

    def test_json_ld_graph_and_errors(self):
        ld = self.facts["json_ld"]
        self.assertEqual(ld["blocks"], 2)
        self.assertEqual(ld["types"], ["Organization", "WebSite", "SoftwareApplication"])
        self.assertEqual(len(ld["errors"]), 1)
        self.assertEqual(ld["errors"][0]["block"], 2)

    def test_social_links_merge_anchor_and_same_as(self):
        social = {s["platform"]: s for s in self.facts["social_links"]}
        self.assertEqual(set(social), {"x", "linkedin", "youtube", "github"})
        self.assertEqual(social["x"]["sources"], ["json-ld", "anchor"])
        self.assertEqual(social["linkedin"]["sources"], ["json-ld"])

    def test_third_party_scripts(self):
        scripts = self.facts["scripts"]
        self.assertEqual([s["host"] for s in scripts["third_party"]],
                         ["www.googletagmanager.com", "js.hs-scripts.com"])
        self.assertEqual(scripts["first_party_count"], 2)

    def test_media_and_words(self):
        media = self.facts["media"]
        self.assertEqual(media["images"], 3)  # the aria-hidden marquee clone is not counted
        self.assertEqual(media["images_lazy"], 2)
        self.assertEqual(media["images_missing_alt"], 1)
        self.assertFalse(self.facts["is_js_shell"])
        self.assertGreater(self.facts["word_count"], self.facts["main_word_count"])
        self.assertGreater(self.facts["main_word_count"], 100)

    def test_glued_heading_fixture(self):
        facts = html.page_facts(fixture("glued_headings.html"))
        self.assertEqual(facts["headings"]["h2"], [
            "The product development system for teams and agents", "Ship faster"])
        self.assertIn("Enterprise plan workspaces Zero data retention", facts["main_text"])
        self.assertEqual(facts["main_text"].count("The product development system"), 1)

    def test_spa_shell_facts(self):
        facts = html.page_facts(fixture("spa_shell.html"), "https://app.acme.test/")
        self.assertTrue(facts["is_js_shell"])
        self.assertEqual(facts["word_count"], 0)
        self.assertEqual(facts["outline"], [])
        json.dumps(facts)

    def test_empty_and_bytes_input(self):
        facts = html.page_facts(b"")
        self.assertEqual(facts["word_count"], 0)
        json.dumps(facts)
        facts = html.page_facts('<html><head><meta charset="utf-8"></head><body><p>caf\xe9</p></body></html>'.encode("utf-8"))
        self.assertIn("caf\xe9", facts["main_text"])

    def test_text_chars_cap(self):
        facts = html.page_facts(fixture("saas_home.html"), text_chars=40)
        self.assertEqual(len(facts["main_text"]), 40)
        self.assertTrue(facts["main_text_truncated"])

    def test_hero_outside_main_is_first_block(self):
        markup = ("<body><header><nav><a href='/'>Home</a></nav><h1>Payroll for small teams done in minutes</h1>"
                  "<a href='/signup'>Start free</a></header><main><section><h2>Features</h2><p>Fast.</p></section>"
                  "<section><h2>Pricing</h2><p>Cheap.</p></section></main></body>")
        facts = html.page_facts(markup, "https://pay.test/")
        self.assertEqual(facts["outline"][0]["heading"], "Payroll for small teams done in minutes")
        start = [c for c in facts["ctas"] if c["text"] == "Start free"][0]
        self.assertEqual(start["zone"], "hero")

    def test_content_sections_are_not_mistaken_for_chrome(self):
        # "trusted-by" contains "truste" (a consent vendor), AEM components use
        # "cmp-", a GDPR feature section is not a cookie banner, and a
        # <header> inside a <section> is that section's heading, not site nav.
        markup = (
            "<body><header><nav><a href='/pricing'>Pricing</a></nav></header><main>"
            "<section class='hero'><h1>Payroll for small teams done fast</h1>"
            "<a class='btn' href='/signup'>Start free</a></section>"
            "<section class='trusted-by'><h2>Trusted by 5,000 teams</h2><p>Alpha, Beta and Gamma.</p></section>"
            "<section class='cmp-container'><h2>Features that matter</h2><p>Docs and projects.</p>"
            "<a class='cmp-button' href='/demo'>Book a demo</a></section>"
            "<section id='gdpr-compliance'><h2>GDPR ready</h2><p>Data stays in the EU.</p></section>"
            "<section><header><h2>Pricing that scales</h2><p>Simple plans.</p></header>"
            "<a href='/pricing'>See plans</a></section>"
            "</main><div id='onetrust-banner-sdk'><p>We use cookies.</p><button>Accept all</button></div>"
            "<div class='consent-bar'><p>This site uses cookies to improve your visit.</p>"
            "<a href='/privacy'>Learn more</a></div></body>")
        facts = html.page_facts(markup, "https://acme.test/")
        self.assertEqual(facts["headings"]["h2"], [
            "Trusted by 5,000 teams", "Features that matter", "GDPR ready", "Pricing that scales"])
        self.assertEqual([b["heading"] for b in facts["outline"]], [
            "Payroll for small teams done fast", "Trusted by 5,000 teams", "Features that matter",
            "GDPR ready", "Pricing that scales"])
        zones = {c["text"]: c["zone"] for c in facts["ctas"]}
        self.assertEqual(zones["Book a demo"], "body")
        self.assertEqual(zones["See plans"], "body")
        self.assertEqual(zones["Pricing"], "nav")
        self.assertNotIn("Learn more", zones)  # the consent bar's link
        self.assertNotIn("We use cookies", facts["main_text"])
        self.assertNotIn("uses cookies", facts["main_text"])

    def test_wrapper_of_sections_is_split_into_blocks(self):
        # hubspot.com shape: hero and every later section share one wrapper, so
        # the outline had 2 blocks and later CTAs were labelled "hero".
        markup = (
            "<main><div class='page'>"
            "<section class='hero'><div class='left'><h1>Plan and ship together fast</h1>"
            "<a class='btn' href='/signup'>Start free</a></div>"
            "<div class='right'><h2>Start your trial</h2><form><input type='email' name='email'>"
            "<button type='submit'>Start trial</button></form></div></section>"
            "<div class='module'><h2>Docs</h2><p>Write things down.</p><a href='/demo'>Book a demo</a></div>"
            "<div class='module'><h2>Projects</h2><p>Plan the work.</p></div>"
            "</div><section class='cta'><h2>Ready to start?</h2><p>Join today.</p></section></main>")
        facts = html.page_facts(markup, "https://acme.test/")
        self.assertEqual([b["heading"] for b in facts["outline"]], [
            "Plan and ship together fast", "Docs", "Projects", "Ready to start?"])
        zones = {c["text"]: c["zone"] for c in facts["ctas"]}
        self.assertEqual(zones["Start free"], "hero")
        self.assertEqual(zones["Book a demo"], "body")
        # A split hero (headline left, form with its own <h2> right) stays one block.
        self.assertEqual(zones["Start trial"], "hero")
        self.assertEqual(facts["forms"][0]["zone"], "hero")

    def test_responsive_duplicates_stay_fast_on_large_pages(self):
        # Many sibling cards that each carry a mobile-only twin used to make
        # remove_responsive_duplicates quadratic (10 s for 500 KB).
        import time
        cards = "".join(
            "<section><h2>Card %d</h2><p>%s</p><div class='md:hidden'>Card %d</div>"
            "<div class='md:hidden'>Only on mobile %d</div></section>" % (i, "lorem ipsum " * 40, i, i)
            for i in range(800))
        markup = "<html><body><main>%s</main></body></html>" % cards
        started = time.monotonic()
        soup = html.parse(markup)
        removed = html.remove_responsive_duplicates(soup)
        self.assertLess(time.monotonic() - started, 5.0)
        self.assertEqual(removed, 800)  # each "Card N" twin; "Only on mobile N" has no twin
        self.assertEqual(html.clean_text(soup).count("Only on mobile 7 "), 1)

    def test_json_ld_nan_becomes_null(self):
        facts = html.page_facts('<script type="application/ld+json">{"@type": "Product", "rating": NaN}</script>'
                                "<h1>Product page</h1>")
        self.assertIsNone(facts["json_ld"]["items"][0]["rating"])
        json.dumps(facts, allow_nan=False)

    def test_logo_h1_in_header_is_chrome(self):
        markup = ("<body><header><h1><a href='/'>Acme</a></h1><nav><a href='/pricing'>Pricing</a></nav></header>"
                  "<main><section><h2>Ship faster with Acme today</h2><p>Text here.</p></section>"
                  "<section><h2>More</h2><p>More text.</p></section></main></body>")
        facts = html.page_facts(markup, "https://acme.test/")
        self.assertEqual(facts["outline"][0]["heading"], "Ship faster with Acme today")


if __name__ == "__main__":
    unittest.main()
