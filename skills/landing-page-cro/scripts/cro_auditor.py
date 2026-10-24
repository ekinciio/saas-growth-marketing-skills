#!/usr/bin/env python3
"""Landing page CRO fact extractor and rubric scorer (landing-page-cro skill).

This script never judges a page. It collects facts the model needs to score
a page against references/scoring-rubric.md, and it does the arithmetic once
the model has scored each dimension.

Extract facts (a live URL, a saved HTML file, up to two competitors):

    python3 cro_auditor.py https://acme.app --json
    python3 cro_auditor.py rendered.html --url https://acme.app --json
    python3 cro_auditor.py https://acme.app --vs https://rival.com --json
    python3 cro_auditor.py https://acme.app --psi on --json

Compute the weighted score from the model's dimension scores:

    python3 cro_auditor.py --score scores.json --json

What the extractor reports (all from visible content: display:none, the
hidden attribute, aria-hidden, screen-reader-only text, <template> and
<noscript> are removed first, so hidden keyword stuffing earns nothing):

    hero          headline (h1, role=heading or first heading), subheadline,
                  hero text, hero CTAs, risk reducers, media (image, video,
                  interactive demo)
    outline       ordered main-content sections with heading, words, CTAs
    ctas          inventory with zone (hero, body, nav, footer) and intent
                  taken mainly from the href (signup, demo, pricing, login),
                  the primary CTA guess and button-looking non-buttons
    forms         visible fields per form, the primary form, forms that a
                  third party renders with JavaScript (HubSpot, Marketo, ...)
    proof         logo walls with names, quotes with attribution, ratings
                  with platform, numeric claims, case-study links
    trust         compliance mentions (SOC 2, ISO 27001, GDPR, ...) by zone,
                  legal and security links, guarantee sentences
    objections    FAQ questions (details, FAQPage JSON-LD, question
                  headings), prices on the page, comparison links
    urgency       urgency phrases with context, countdown elements
    navigation    nav and footer links (exits from a landing page)
    measurement   analytics, session replay, experimentation, chat and
                  consent tools found in the static HTML
    speed         diagnostics only (bytes, blocking scripts, lazy hero
                  image); Core Web Vitals come only from PageSpeed field
                  data (--psi), never from HTML guesses

Text-pattern candidates (urgency, risk reducers, guarantees, numeric claims)
are English patterns; every structural fact works in any language, and the
model reads the quoted text either way.

Exit codes (shared contract, _growthkit/cli.py):
    0 ok; 2 usage error; 3 blocked or unreachable; 4 partial (a competitor
    or the PageSpeed call failed, or the page was truncated); 5 nothing to
    analyze (JavaScript shell, empty page). No exit code comes with a score.
"""

from __future__ import annotations

import os
import re
import sys
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from _growthkit import cli  # noqa: E402

TOOL = "cro_auditor"

# ---------------------------------------------------------------------------
# Rubric weights (references/scoring-rubric.md). Weights are relative impact
# on conversion; they do not need to add up to 100 because the total is
# renormalized over the dimensions that were scored.
# ---------------------------------------------------------------------------

RUBRIC_VERSION = "cro-rubric-v2"
DIMENSIONS: Tuple[Tuple[str, str, int], ...] = (
    ("value_prop", "Value proposition and first screen", 20),
    ("cta", "Primary CTA and next step", 15),
    ("proof", "Social proof specificity", 15),
    ("objections", "Objection handling and risk reversal", 10),
    ("copy", "Copy clarity and customer language", 10),
    ("trust", "Trust and security signals", 10),
    ("form", "Form friction", 10),
    ("hierarchy", "Visual hierarchy and scannability", 5),
    ("speed", "Speed and mobile experience", 5),
    ("urgency", "Offer timing and urgency", 5),
)
DIMENSION_IDS = tuple(d[0] for d in DIMENSIONS)
BANDS = ((90, "Excellent"), (70, "Good"), (50, "Fair"), (30, "Poor"), (0, "Critical"))
MIN_MEASURED_SHARE = 0.6  # report-contract.md section 4: no composite below 60%
CONFIDENCE_LEVELS = ("high", "medium", "low")
STATUSES = ("scored", "na", "not_measured")

MAX_COMPETITORS = 2
SAME_HOST_DELAY = 2.0  # browser-fallback.md: at least 2 s between loads on one host
MAX_BLOCKS = 40

# ---------------------------------------------------------------------------
# Text patterns. Every group is non-capturing (?:...), and matches are read
# with finditer().group(0), so findall() can never return tuples (the 2026-10
# crash on 9 of 24 SaaS homepages). tests/landing_page_cro checks both.
# ---------------------------------------------------------------------------

# Word boundaries keep "unlimited" from matching "limited"; a bare "limited"
# ("limited history on the Free plan") is not urgency either.
URGENCY_PATTERNS = re.compile(
    r"\b(?:limited[\s-]+(?:time|offer)|hurry|"
    r"act\s+now|last\s+chance|expires?|deadline|"
    r"only\s+\d+\s+(?:left|spots?|seats?|places?)|\d+\s+(?:spots?|seats?)\s+left|"
    r"\d+\s+(?:days?|hours?)\s+left|spots?\s+left|"
    r"ends?\s+(?:soon|today|tomorrow|tonight|this\s+week|(?:on\s+)?(?:mon|tues|wednes|thurs|fri|satur|sun)day|"
    r"(?:on\s+)?(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s+\d{1,2})|"
    r"early[\s-]?bird|countdown|don.t\s+miss|while\s+supplies)\b",
    re.IGNORECASE,
)

RISK_REDUCER_PATTERNS = re.compile(
    r"\b(?:no\s+credit\s+card(?:\s+(?:required|needed))?|no\s+card\s+(?:required|needed)|"
    r"without\s+(?:a\s+)?credit\s+card|free\s+(?:for\s+\d+\s+days|trial|plan|forever|tier|to\s+start)|"
    r"\d+[\s-]day\s+(?:free\s+)?trial|cancel\s+(?:any\s?time|at\s+any\s+time)|money[\s-]back|"
    r"no\s+(?:setup|hidden)\s+fees?|no\s+(?:long[\s-]term\s+)?(?:contracts?|commitment)|"
    r"free\s+(?:migration|onboarding|setup)|risk[\s-]free|setup\s+in\s+\d+\s+minutes?)\b",
    re.IGNORECASE,
)

GUARANTEE_PATTERNS = re.compile(
    r"\b(?:money[\s-]back|refunds?|guarantee[ds]?|no\s+questions\s+asked|"
    r"cancel\s+(?:any\s?time|at\s+any\s+time))\b",
    re.IGNORECASE,
)

RATING_PATTERNS = re.compile(
    r"\b\d(?:[.,]\d{1,2})?\s*(?:/\s*5|out\s+of\s+5|of\s+5\s+stars?|stars?)\b|"
    r"\brated\s+\d(?:[.,]\d{1,2})?\b|★{3,5}",
    re.IGNORECASE,
)

PLATFORM_PATTERNS = re.compile(
    r"\b(?:G2(?:\s?Crowd)?|Capterra|GetApp|Software\s+Advice|TrustRadius|Trustpilot|"
    r"Gartner\s+Peer\s+Insights|Product\s+Hunt|App\s+Store|Google\s+Play|Chrome\s+Web\s+Store|"
    r"Shopify\s+App\s+Store|Atlassian\s+Marketplace|AppExchange|Clutch|Google\s+Reviews?)\b",
    re.IGNORECASE,
)

NUMERIC_CLAIM_PATTERNS = re.compile(
    r"\d[\d.,]*\s?(?:%|\+|x\b|×|k\+?\b|K\+?\b|M\+?\b|million\b|billion\b|bn\b)|"
    r"\b\d[\d.,]*\+?\s+(?:teams|customers|companies|businesses|organi[sz]ations|users|"
    r"developers|people|brands|countries|reviews|hours|minutes|days|weeks|employees|"
    r"integrations|members|creators|stores|merchants)\b",
    re.IGNORECASE,
)

PRICE_PATTERNS = re.compile(
    r"(?:[$€£¥₹₺]\s?\d[\d.,]*(?:\s?[kKmM]\b)?|"
    r"\b\d[\d.,]*\s?(?:€|₺|zł|kr\b|USD\b|EUR\b|GBP\b|TL\b))"
    r"(?:\s?(?:/|per)\s?(?:mo(?:nth)?|user|seat|member|editor|yr|year|annum)\b)?",
)

COMPARISON_HREF = re.compile(
    r"(?:/vs[-/]|-vs-|/versus\b|/compare\b|/comparison\b|/alternatives?\b|-alternatives?\b)",
    re.IGNORECASE,
)
CASE_STUDY_HREF = re.compile(
    r"/(?:customers?|case-stud(?:y|ies)|customer-stories|stories|success-stor(?:y|ies)|"
    r"testimonials|reviews|wall-of-love)(?:/|$|\?|#)",
    re.IGNORECASE,
)
TESTIMONIAL_CLASS = re.compile(
    r"testimonial|customer-?quote|quote-?card|review-?card|(?:^|[-_\s])quote(?:[-_\s]|$)",
    re.IGNORECASE,
)
QUOTE_START = re.compile(r"^\s*[\"“„«‘「']")
QUESTION_END = re.compile(r"[?？]\s*$")
COUNTDOWN_CLASS = re.compile(r"countdown|count-down", re.IGNORECASE)
# A class token that names a button: "btn", "button", "cta", "btn-primary",
# "hero-button". Not "cta-microcopy" or "button-group".
BUTTONISH_CLASS = re.compile(
    r"^(?:btn|button|cta)(?:[-_]{1,2}(?:primary|secondary|main|large|lg|md|sm|small|default|solid|outline|"
    r"filled|dark|light|blue|black|white|brand|accent|cta|link|xl))*$|^[a-z0-9]+[-_](?:btn|button|cta)$",
    re.IGNORECASE,
)
ATTRIBUTION_CLASS = re.compile(r"author|attribution|byline|\bcite\b|person|customer-?name|quote-?name|signature",
                               re.IGNORECASE)
REVIEW_PLATFORMS = re.compile(
    r"\b(?:G2|Capterra|GetApp|Software\s+Advice|TrustRadius|Trustpilot|Gartner\s+Peer\s+Insights|Product\s+Hunt|"
    r"Clutch)\b",
    re.IGNORECASE,
)
RATING_WORDS = re.compile(r"\b(?:badge|leader|award|rated|rating|reviews?|stars?|winner|high\s+performer|best)\b",
                          re.IGNORECASE)
VIDEO_SRC = re.compile(
    r"youtube\.com|youtube-nocookie\.com|youtu\.be|player\.vimeo\.com|wistia|loom\.com/embed|"
    r"vidyard|fast\.wistia",
    re.IGNORECASE,
)
DEMO_SRC = re.compile(
    r"navattic|storylane|arcade\.software|supademo|walnut\.io|getreprise|reprise\.com|"
    r"howdygo|tourial|consensus\.com|demoboost|saleo",
    re.IGNORECASE,
)
SENTENCE_SPLIT = re.compile(r"(?<=[.!?。])\s+")
HASHY_NAME = re.compile(r"^(?:[0-9a-f]{8,}|[0-9a-z]{20,}|image|img|logo|icon|asset|group|frame|vector|untitled)\d*$", re.IGNORECASE)

# (name, pattern) pairs. Text from visible content and image alt text.
COMPLIANCE_PATTERNS: Tuple[Tuple[str, re.Pattern], ...] = (
    ("SOC 2", re.compile(r"\bSOC\s?2(?:\s+Type\s+(?:I{1,2}|1|2))?\b|\bSOC\s?II\b", re.IGNORECASE)),
    ("ISO 27001", re.compile(r"\bISO(?:/IEC)?\s?27001\b", re.IGNORECASE)),
    ("ISO 27701", re.compile(r"\bISO(?:/IEC)?\s?27701\b", re.IGNORECASE)),
    ("ISO 27017/27018", re.compile(r"\bISO(?:/IEC)?\s?2701[78]\b", re.IGNORECASE)),
    ("ISO 42001", re.compile(r"\bISO(?:/IEC)?\s?42001\b", re.IGNORECASE)),
    ("GDPR", re.compile(r"\bGDPR\b|\bDSGVO\b|\bRGPD\b", re.IGNORECASE)),
    ("HIPAA", re.compile(r"\bHIPAA\b", re.IGNORECASE)),
    ("CCPA/CPRA", re.compile(r"\bCCPA\b|\bCPRA\b", re.IGNORECASE)),
    ("PCI DSS", re.compile(r"\bPCI[\s-]?DSS\b", re.IGNORECASE)),
    ("FedRAMP", re.compile(r"\bFedRAMP\b", re.IGNORECASE)),
    ("CSA STAR", re.compile(r"\bCSA\s+STAR\b", re.IGNORECASE)),
    ("HITRUST", re.compile(r"\bHITRUST\b", re.IGNORECASE)),
    ("TISAX", re.compile(r"\bTISAX\b", re.IGNORECASE)),
    ("Cyber Essentials", re.compile(r"\bCyber\s+Essentials\b", re.IGNORECASE)),
    ("KVKK", re.compile(r"\bKVKK\b")),
)

LEGAL_LINKS: Tuple[Tuple[str, re.Pattern], ...] = (
    ("privacy", re.compile(r"privacy|datenschutz|privacidad|confidentialit|gizlilik|/kvkk", re.IGNORECASE)),
    ("security", re.compile(r"/security\b|/trust(?:-center)?(?:/|$)|^https?://trust\.|/compliance\b", re.IGNORECASE)),
    ("terms", re.compile(r"/terms|/tos\b|/legal/?(?:$|\?|#)|/conditions|/agb\b|/impressum|/kosullar", re.IGNORECASE)),
    ("status", re.compile(r"^https?://status\.|/status(?:/|$)", re.IGNORECASE)),
    ("dpa", re.compile(r"/dpa\b|subprocessors|data-processing", re.IGNORECASE)),
    ("accessibility", re.compile(r"/accessibility\b", re.IGNORECASE)),
)

# (category, tool, pattern) matched against script, iframe, link and
# noscript markup only. Tools loaded through a tag manager are invisible here.
MEASUREMENT_SIGNATURES: Tuple[Tuple[str, str, re.Pattern], ...] = (
    ("tag_manager", "Google Tag Manager", re.compile(r"googletagmanager\.com/gtm\.js|GTM-[A-Z0-9]{4,}")),
    ("tag_manager", "Tealium", re.compile(r"tags\.tiqcdn\.com|utag\.js", re.IGNORECASE)),
    ("tag_manager", "Adobe Launch", re.compile(r"assets\.adobedtm\.com", re.IGNORECASE)),
    ("analytics", "Google Analytics 4", re.compile(r"googletagmanager\.com/gtag/js\?id=G-|['\"]G-[A-Z0-9]{6,}['\"]")),
    ("analytics", "Segment", re.compile(r"cdn\.segment\.com|segment\.io/analytics", re.IGNORECASE)),
    ("analytics", "PostHog", re.compile(r"posthog", re.IGNORECASE)),
    ("analytics", "Amplitude", re.compile(r"amplitude\.com|cdn\.amplitude|amplitude\.getInstance|@amplitude", re.IGNORECASE)),
    ("analytics", "Mixpanel", re.compile(r"mixpanel", re.IGNORECASE)),
    ("analytics", "Heap", re.compile(r"heapanalytics\.com|heap\.load\(", re.IGNORECASE)),
    ("analytics", "Plausible", re.compile(r"plausible\.io", re.IGNORECASE)),
    ("analytics", "Fathom", re.compile(r"usefathom\.com", re.IGNORECASE)),
    ("analytics", "Matomo", re.compile(r"matomo|piwik", re.IGNORECASE)),
    ("analytics", "Vercel Analytics", re.compile(r"/_vercel/insights|va\.vercel-scripts\.com", re.IGNORECASE)),
    ("analytics", "RudderStack", re.compile(r"rudderlabs|rudderstack", re.IGNORECASE)),
    ("analytics", "HubSpot tracking", re.compile(r"js\.hs-scripts\.com|js\.hs-analytics\.net|js\.hsadspixel", re.IGNORECASE)),
    ("analytics", "Adobe Analytics", re.compile(r"AppMeasurement|omtrdc\.net", re.IGNORECASE)),
    ("session_replay", "Hotjar", re.compile(r"hotjar", re.IGNORECASE)),
    ("session_replay", "Microsoft Clarity", re.compile(r"clarity\.ms", re.IGNORECASE)),
    ("session_replay", "FullStory", re.compile(r"fullstory", re.IGNORECASE)),
    ("session_replay", "LogRocket", re.compile(r"logrocket", re.IGNORECASE)),
    ("session_replay", "Contentsquare", re.compile(r"contentsquare", re.IGNORECASE)),
    ("session_replay", "Mouseflow", re.compile(r"mouseflow", re.IGNORECASE)),
    ("session_replay", "Smartlook", re.compile(r"smartlook", re.IGNORECASE)),
    ("experimentation", "Optimizely", re.compile(r"optimizely", re.IGNORECASE)),
    ("experimentation", "VWO", re.compile(r"visualwebsiteoptimizer|vwo_code|dev\.visualwebsiteoptimizer", re.IGNORECASE)),
    ("experimentation", "AB Tasty", re.compile(r"abtasty", re.IGNORECASE)),
    ("experimentation", "Convert", re.compile(r"convertexperiments", re.IGNORECASE)),
    ("experimentation", "GrowthBook", re.compile(r"growthbook", re.IGNORECASE)),
    ("experimentation", "Statsig", re.compile(r"statsig", re.IGNORECASE)),
    ("experimentation", "LaunchDarkly", re.compile(r"launchdarkly", re.IGNORECASE)),
    ("experimentation", "Kameleoon", re.compile(r"kameleoon", re.IGNORECASE)),
    ("experimentation", "Mutiny", re.compile(r"mutinycdn|mutinyhq", re.IGNORECASE)),
    ("experimentation", "Intellimize", re.compile(r"intellimize", re.IGNORECASE)),
    ("experimentation", "Split", re.compile(r"cdn\.split\.io|sdk\.split\.io", re.IGNORECASE)),
    ("experimentation", "Google Optimize (discontinued 2023)", re.compile(r"googleoptimize\.com|optimize\.google\.com", re.IGNORECASE)),
    ("chat", "Intercom", re.compile(r"widget\.intercom\.io|intercomSettings|js\.intercomcdn", re.IGNORECASE)),
    ("chat", "Drift", re.compile(r"js\.driftt\.com|drift\.load", re.IGNORECASE)),
    ("chat", "Qualified", re.compile(r"js\.qualified\.com", re.IGNORECASE)),
    ("chat", "HubSpot chat", re.compile(r"js\.usemessages\.com", re.IGNORECASE)),
    ("chat", "Zendesk", re.compile(r"static\.zdassets\.com|zopim", re.IGNORECASE)),
    ("chat", "Crisp", re.compile(r"client\.crisp\.chat", re.IGNORECASE)),
    ("chat", "Tidio", re.compile(r"code\.tidio\.co", re.IGNORECASE)),
    ("chat", "LiveChat", re.compile(r"livechatinc\.com", re.IGNORECASE)),
    ("chat", "Help Scout Beacon", re.compile(r"beacon-v2\.helpscout\.net", re.IGNORECASE)),
    ("chat", "Freshchat", re.compile(r"wchat\.freshchat|freshworks\.com/live-chat", re.IGNORECASE)),
    ("consent", "OneTrust", re.compile(r"onetrust|cookielaw\.org|otSDKStub", re.IGNORECASE)),
    ("consent", "Cookiebot", re.compile(r"cookiebot", re.IGNORECASE)),
    ("consent", "Usercentrics", re.compile(r"usercentrics", re.IGNORECASE)),
    ("consent", "Didomi", re.compile(r"didomi", re.IGNORECASE)),
    ("consent", "Osano", re.compile(r"osano\.com", re.IGNORECASE)),
    ("consent", "TrustArc", re.compile(r"trustarc|consent\.truste\.com", re.IGNORECASE)),
    ("consent", "Termly", re.compile(r"termly\.io", re.IGNORECASE)),
    ("consent", "iubenda", re.compile(r"iubenda", re.IGNORECASE)),
    ("consent", "CookieYes", re.compile(r"cookieyes", re.IGNORECASE)),
    ("consent", "Ketch", re.compile(r"ketchcdn\.com", re.IGNORECASE)),
    ("consent", "Transcend", re.compile(r"transcend-cdn|transcend\.io", re.IGNORECASE)),
    ("consent", "Sourcepoint", re.compile(r"sourcepoint|sp-prod\.net", re.IGNORECASE)),
    ("scheduler", "Chili Piper", re.compile(r"chilipiper", re.IGNORECASE)),
    ("scheduler", "Calendly", re.compile(r"calendly\.com", re.IGNORECASE)),
    ("scheduler", "HubSpot meetings", re.compile(r"meetings\.hubspot\.com|MeetingsEmbed", re.IGNORECASE)),
    ("scheduler", "Default", re.compile(r"import\.cdn\.default\.com|cdn\.default\.com", re.IGNORECASE)),
    ("scheduler", "RevenueHero", re.compile(r"revenuehero", re.IGNORECASE)),
)
MEASUREMENT_CATEGORIES = ("tag_manager", "analytics", "session_replay", "experimentation", "chat",
                          "consent", "scheduler")

_TECH_MARKUP_RE = re.compile(
    r"<script\b[^>]*>.*?</script\s*>|<iframe\b[^>]*>|<link\b[^>]*>|<noscript\b[^>]*>.*?</noscript\s*>",
    re.IGNORECASE | re.DOTALL,
)
_HEAD_RE = re.compile(r"<head\b[^>]*>(.*?)</head\s*>", re.IGNORECASE | re.DOTALL)
_SCRIPT_TAG_RE = re.compile(r"<script\b([^>]*)>", re.IGNORECASE)
_LINK_TAG_RE = re.compile(r"<link\b([^>]*)>", re.IGNORECASE)

BLOCK_TAGS = frozenset({
    "p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6", "section", "article", "ul", "ol",
    "table", "tbody", "thead", "tr", "td", "th", "blockquote", "figure", "figcaption",
    "header", "footer", "main", "aside", "nav", "dl", "dt", "dd", "form", "label",
    "details", "summary", "fieldset", "body",
})
SKIP_ZONES = ("nav", "cookie", "dialog", "hidden")


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _html():
    """The growthkit html module (imported late: it needs beautifulsoup4)."""
    from _growthkit import html as gk_html
    return gk_html


def _http():
    """The growthkit http module (imported late: it needs requests)."""
    from _growthkit import http as gk_http
    return gk_http


def _norm(text: str) -> str:
    return " ".join(re.sub(r"[\W_]+", " ", (text or "").casefold()).split())


def _match_texts(pattern: re.Pattern, text: str) -> List[str]:
    """Full text of every match, in order (never tuples)."""
    return [m.group(0) for m in pattern.finditer(text or "")]


def _unique(items: List[str], limit: Optional[int] = None) -> List[str]:
    seen = set()
    out: List[str] = []
    for item in items:
        key = _norm(item)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item)
        if limit is not None and len(out) >= limit:
            break
    return out


def _clip(text: str, limit: int) -> str:
    text = text or ""
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


def _classes(tag: Any) -> str:
    value = tag.get("class") if getattr(tag, "attrs", None) else None
    if isinstance(value, (list, tuple)):
        return " ".join(str(v) for v in value)
    return str(value or "")


def _host(url: Optional[str]) -> str:
    try:
        return (urlparse(url or "").hostname or "").lower()
    except ValueError:
        return ""


# ---------------------------------------------------------------------------
# Visible DOM with zones
# ---------------------------------------------------------------------------


def _svg_label(svg: Any) -> Optional[str]:
    label = svg.get("aria-label") or svg.get("title")
    if not label:
        title = svg.find("title")
        if title is not None:
            label = title.get_text(" ", strip=True)
    if not label:
        parent = svg.parent
        for _ in range(2):
            if parent is None or not getattr(parent, "attrs", None):
                break
            if parent.get("aria-label") or parent.get("title"):
                if not parent.get_text(strip=True):
                    label = parent.get("aria-label") or parent.get("title")
                break
            parent = parent.parent
    return " ".join(str(label).split()) if label else None


def _logo_context(tag: Any) -> bool:
    node = tag
    for _ in range(3):
        if node is None or not getattr(node, "attrs", None):
            return False
        if re.search(r"logo|brand|customer|client|partner|trusted", _classes(node) + " " + str(node.get("id") or ""), re.I):
            return True
        node = node.parent
    return False


def _placeholders(soup: Any) -> None:
    """Keep what non-rendered tags would hide: labelled SVG logos and media.

    strip_invisible(non_rendered=True) removes <svg>, <video> and <iframe>.
    Logo walls are often inline SVGs and hero media is often a video or an
    interactive demo, so each is replaced by an <img data-cro-...> stand-in
    first. Unlabelled decorative SVGs are left alone (and removed later).
    """
    for svg in list(soup.find_all("svg")):
        if svg.parent is None or svg.find_parent("svg") is not None:
            continue
        label = _svg_label(svg)
        role_img = str(svg.get("role") or "").lower() == "img"
        if label or role_img or _logo_context(svg):
            stand_in = soup.new_tag("img")
            stand_in["alt"] = label or ""
            stand_in["data-cro-svg"] = "1"
            svg.replace_with(stand_in)
    # Unlabelled SVG logos in a row: 4+ sibling items that each hold only an
    # SVG (linear.app's customer row). Decorative single icons stay out.
    for parent in list(soup.find_all(["ul", "ol", "div"])):
        kids = parent.find_all(True, recursive=False)
        if len(kids) < 4:
            continue
        holders = [kid for kid in kids
                   if (kid.name == "svg" or kid.find("svg") is not None)
                   and not kid.get_text(strip=True) and kid.find("img") is None]
        if len(holders) < 4 or len(holders) < 0.6 * len(kids):
            continue
        for kid in holders:
            svg = kid if kid.name == "svg" else kid.find("svg")
            if svg is None or svg.parent is None or svg.find_parent("svg") is not None:
                continue
            stand_in = soup.new_tag("img")
            stand_in["alt"] = ""
            stand_in["data-cro-svg"] = "1"
            svg.replace_with(stand_in)
    for tag in list(soup.find_all(["video", "iframe"])):
        if tag.parent is None:
            continue
        src = " ".join(str(tag.get(a) or "") for a in ("src", "data-src", "title"))
        if tag.name == "video" or VIDEO_SRC.search(src):
            kind = "video"
        elif DEMO_SRC.search(src):
            kind = "interactive_demo"
        else:
            continue
        stand_in = soup.new_tag("img")
        stand_in["alt"] = "[%s]" % kind
        stand_in["data-cro-media"] = kind
        tag.replace_with(stand_in)


class _Dom:
    """Visible DOM (hidden and non-rendered nodes removed) plus its layout."""

    def __init__(self, markup: str) -> None:
        H = _html()
        self.H = H
        self.soup = H.parse(markup)
        self.hidden_removed = H.strip_invisible(self.soup, hidden=True, non_rendered=False)
        _placeholders(self.soup)
        H.strip_invisible(self.soup, hidden=False, non_rendered=True)
        # The layout class is growthkit's own (the same zones page_facts uses).
        self.layout = H._Layout(self.soup)
        self.body = self.soup.body or self.soup
        self._zone_cache: Dict[int, Tuple[str, Optional[int]]] = {}

    def zone(self, tag: Any) -> Tuple[str, Optional[int]]:
        key = id(tag)
        if key not in self._zone_cache:
            self._zone_cache[key] = self.layout.locate(tag)
        return self._zone_cache[key]

    def hero_block(self) -> Optional[Any]:
        index = self.layout.hero_index
        if index is None or index >= len(self.layout.blocks):
            return None
        return self.layout.blocks[index]


def _own_text(H: Any, el: Any) -> str:
    """Text of an element without the text of its block-level descendants."""
    parts: List[str] = []
    for child in el.children:
        name = getattr(child, "name", None)
        if name is None:
            text = str(child)
            if text.strip():
                parts.append(text)
        elif name not in BLOCK_TAGS:
            text = H.clean_text(child)
            if text:
                parts.append(text)
    return H.clean_text(" ".join(parts))


def _segments(dom: _Dom) -> List[Dict[str, Any]]:
    """Visible text units in document order: {text, zone, block, tag}.

    Each piece of text appears in exactly one segment: a block element
    without block descendants gives its whole text, a container gives only
    its own inline text.
    """
    H = dom.H
    out: List[Dict[str, Any]] = []
    for el in dom.body.find_all(True):
        if el.name not in BLOCK_TAGS:
            continue
        has_block_child = el.find(lambda t: t.name in BLOCK_TAGS) is not None
        text = _own_text(H, el) if has_block_child else H.clean_text(el)
        if not text or not re.search(r"\w", text):
            continue
        zone, block = dom.zone(el)
        if zone in ("cookie", "dialog", "hidden"):
            continue
        out.append({"text": text, "zone": zone, "block": block, "tag": el.name, "_el": el})
    return out


def _sentences(text: str) -> List[str]:
    return [s.strip() for s in SENTENCE_SPLIT.split(text or "") if s.strip()]


# ---------------------------------------------------------------------------
# Hero
# ---------------------------------------------------------------------------


def _hero(dom: _Dom, facts: Dict[str, Any], segments: List[Dict[str, Any]]) -> Dict[str, Any]:
    H = dom.H
    h1s = (facts.get("headings") or {}).get("h1") or []
    headline, source, headline_el = None, None, None
    if h1s:
        headline, source = h1s[0], "h1"
        for tag in dom.body.find_all("h1"):
            if H.clean_text(tag, collapse=True) == headline:
                headline_el = tag
                break
    if headline is None:
        tag = dom.body.find(attrs={"role": "heading", "aria-level": "1"})
        if tag is not None and H.clean_text(tag):
            headline, source, headline_el = H.clean_text(tag, collapse=True), "role=heading aria-level=1", tag
    block = dom.hero_block()
    if headline is None and block is not None:
        tag = block.find(re.compile(r"^h[2-3]$"))
        if tag is not None and H.clean_text(tag):
            headline, source, headline_el = H.clean_text(tag, collapse=True), "first heading in the first block (no h1)", tag

    hero_segments = [s for s in segments if s["zone"] == "hero"]
    subheadline = None
    seen_headline = headline_el is None
    for seg in hero_segments:
        if not seen_headline:
            if headline_el is not None and (seg["_el"] is headline_el or headline_el in seg["_el"].descendants
                                            or seg["_el"] in headline_el.parents):
                seen_headline = True
            continue
        words = H.word_count(seg["text"])
        if 5 <= words <= 60 and _norm(seg["text"]) != _norm(headline or ""):
            subheadline = seg["text"]
            break

    hero_text = H.clean_text(block) if block is not None else ""
    media = {"images": 0, "videos": 0, "interactive_demos": 0}
    first_img_lazy = None
    if block is not None:
        for img in block.find_all("img"):
            kind = img.get("data-cro-media")
            if kind == "video":
                media["videos"] += 1
            elif kind == "interactive_demo":
                media["interactive_demos"] += 1
            elif not img.get("data-cro-svg"):
                media["images"] += 1
                if first_img_lazy is None:
                    first_img_lazy = str(img.get("loading") or "").lower() == "lazy"
    ctas = [c for c in facts.get("ctas") or [] if c.get("zone") == "hero"]
    risk = _unique([m for s in hero_segments for m in _match_texts(RISK_REDUCER_PATTERNS, s["text"])], 10)
    return {
        "headline": headline,
        "headline_source": source,
        "h1_count": len(h1s),
        "subheadline": subheadline,
        "text": _clip(hero_text, 700),
        "words": H.word_count(hero_text),
        "ctas": [_cta_view(c) for c in ctas][:8],
        "risk_reducers": risk,
        "media": media,
        "first_image_lazy_loaded": first_img_lazy,
    }


# ---------------------------------------------------------------------------
# CTAs
# ---------------------------------------------------------------------------

CONVERSION_INTENTS = ("signup", "demo", "buy", "download", "contact", "app")


def _cta_view(cta: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "text": cta.get("text"),
        "href": cta.get("href"),
        "intent": cta.get("intent"),
        "intent_source": cta.get("intent_source"),
        "zone": cta.get("zone"),
        "style": cta.get("style"),
        "count": cta.get("count", 1),
    }


def _ctas(dom: _Dom, facts: Dict[str, Any]) -> Dict[str, Any]:
    H = dom.H
    items = facts.get("ctas") or []
    by_zone: Dict[str, int] = {}
    by_intent: Dict[str, int] = {}
    for cta in items:
        by_zone[cta.get("zone") or "body"] = by_zone.get(cta.get("zone") or "body", 0) + cta.get("count", 1)
        intent = cta.get("intent") or "none"
        by_intent[intent] = by_intent.get(intent, 0) + cta.get("count", 1)
    hero = [c for c in items if c.get("zone") == "hero"]
    primary = None
    for pool in (
        [c for c in hero if c.get("intent") in CONVERSION_INTENTS and c.get("style") == "button"],
        [c for c in hero if c.get("intent") in CONVERSION_INTENTS],
        [c for c in items if c.get("zone") == "body" and c.get("intent") in CONVERSION_INTENTS],
        [c for c in items if c.get("zone") == "nav" and c.get("intent") in ("signup", "demo", "buy")],
    ):
        if pool:
            primary = pool[0]
            break
    repeats = 0
    if primary is not None:
        repeats = sum(c.get("count", 1) for c in items
                      if c.get("zone") == "body" and c.get("intent") == primary.get("intent"))
    hero_intents = sorted({c.get("intent") for c in hero
                           if c.get("intent") and c.get("intent") not in ("login", "learn")})

    # Button-looking elements that are neither links nor buttons: keyboard
    # and assistive technology users may not reach them.
    non_semantic: List[Dict[str, Any]] = []
    for el in dom.body.find_all(["div", "span", "li", "p"]):
        tokens = _classes(el).split()
        if not (any(BUTTONISH_CLASS.match(t) for t in tokens) or el.get("onclick")):
            continue
        if el.find(["a", "button", "input"]) is not None or el.find_parent(["a", "button"]) is not None:
            continue
        if str(el.get("role") or "").lower() in ("button", "link"):
            continue
        text = H.clean_text(el)
        if not text or H.word_count(text) > 8:
            continue
        zone, _ = dom.zone(el)
        if zone in ("hero", "body"):
            non_semantic.append({"text": text, "zone": zone, "element": el.name})
        if len(non_semantic) >= 8:
            break

    ordered = hero + [c for c in items if c.get("zone") == "body"] + \
        [c for c in items if c.get("zone") not in ("hero", "body")]
    return {
        "count": len(items),
        "by_zone": by_zone,
        "by_intent": by_intent,
        "primary_guess": _cta_view(primary) if primary else None,
        "primary_repeats_in_body": repeats,
        "hero_conversion_intents": hero_intents,
        "non_semantic_buttons": non_semantic,
        "items": [_cta_view(c) for c in ordered][:40],
        "items_truncated": len(ordered) > 40,
        "scan": facts.get("cta_scan"),
    }


# ---------------------------------------------------------------------------
# Forms
# ---------------------------------------------------------------------------


def _forms(facts: Dict[str, Any]) -> Dict[str, Any]:
    forms = [f for f in facts.get("forms") or [] if not f.get("hidden")]
    views = []
    for form in forms:
        views.append({
            "index": form.get("index"),
            "zone": form.get("zone"),
            "kind": form.get("kind"),
            "primary_candidate": form.get("primary_candidate"),
            "submit_text": form.get("submit_text"),
            "visible_fields": form.get("questions"),
            "required_fields": form.get("required_count"),
            "has_email": form.get("has_email"),
            "has_password": form.get("has_password"),
            "action_host": form.get("action_host"),
            "dropped": form.get("dropped"),
            "fields": [
                {"label": f.get("label"), "type": f.get("type"), "required": f.get("required"),
                 "label_source": f.get("label_source")}
                for f in (form.get("fields") or [])[:12]
            ],
        })
    primary = next((v for v in views if v["primary_candidate"]), None)
    hidden = sum(1 for f in facts.get("forms") or [] if f.get("hidden"))
    return {
        "count": len(views),
        "hidden_forms_ignored": hidden,
        "primary": primary,
        "items": views[:6],
        "embedded_by_javascript": facts.get("embedded_forms") or [],
    }


# ---------------------------------------------------------------------------
# Proof
# ---------------------------------------------------------------------------


def _image_name(img: Any) -> Optional[str]:
    alt = " ".join(str(img.get("alt") or "").split())
    if alt and not alt.startswith("["):
        alt = re.sub(r"\s*\blogo(?:type)?\b\s*$", "", alt, flags=re.I).strip() or alt
        return alt[:60]
    src = str(img.get("src") or img.get("data-src") or "")
    if not src or src.startswith("data:"):
        return None
    stem = os.path.basename(urlparse(src).path)
    stem = re.sub(r"\.(?:svg|png|jpe?g|webp|avif|gif)$", "", stem, flags=re.I)
    stem = re.sub(r"(?:[-_](?:logo|logotype|color|colour|white|black|dark|light|mono|grey|gray|\d+x?))+$", "", stem, flags=re.I)
    stem = re.sub(r"^(?:logo|logos|customer|client)[-_]", "", stem, flags=re.I)
    stem = stem.replace("-", " ").replace("_", " ").strip()
    if not stem or HASHY_NAME.match(stem.replace(" ", "")):
        return None
    return stem[:60]


TRUST_CONTEXT = re.compile(
    r"\b(?:trusted|customers?|companies|teams|businesses|brands|organi[sz]ations|used\s+by|loved\s+by|"
    r"run\s+on|powering|partners?|clients?|backed\s+by|investors|featured\s+in|as\s+seen|choose|rely)\b",
    re.IGNORECASE,
)
LOGO_CLASS = re.compile(r"logo|customer|client|brand|partner|trusted|marquee|wall", re.IGNORECASE)


def _logo_items(dom: _Dom) -> List[Any]:
    """Elements that can be one logo: images (and SVG stand-ins), role=img
    elements with a label, and labelled links with no text or image inside.
    Icons inside buttons (toolbar mockups) are never logos."""
    H = dom.H
    items = []
    for el in dom.body.find_all(True):
        if el.find_parent("button") is not None:
            continue
        if el.name == "img":
            if not el.get("data-cro-media"):
                items.append(el)
        elif str(el.get("role") or "").lower() == "img" and el.get("aria-label"):
            if el.find("img") is None:
                items.append(el)
        elif el.name == "a" and el.get("aria-label") and not H.clean_text(el):
            if el.find("img") is None and el.find(attrs={"role": "img"}) is None:
                items.append(el)
    return items


def _item_name(el: Any) -> Optional[str]:
    if el.name == "img":
        return _image_name(el)
    label = " ".join(str(el.get("aria-label") or el.get("title") or "").split())
    return label[:60] or None


def _following_text(dom: _Dom, node: Any) -> Optional[str]:
    """The first short text right after a wall, inside its grandparent (a
    caption such as "Powering the companies building the future")."""
    H = dom.H
    scope = node.parent.parent if node.parent is not None and node.parent.parent is not None else node.parent
    if scope is None:
        return None
    inside = set(id(t) for t in node.descendants)
    for candidate in node.find_all_next(["p", "h2", "h3", "h4", "span", "div"], limit=40):
        if id(candidate) in inside:
            continue
        if candidate is not scope and scope not in candidate.parents:
            return None
        text = H.clean_text(candidate)
        if text:
            return text if H.word_count(text) <= 20 else None
    return None


def _logo_walls(dom: _Dom) -> Tuple[List[Dict[str, Any]], int]:
    """Rows of 4+ logo-like items with little text, and the reason each one
    looks like a logo wall. Groups without any signal (product screenshots,
    icon grids) are only counted."""
    H = dom.H
    counts: Dict[int, List[Any]] = {}
    for item in _logo_items(dom):
        zone, _ = dom.zone(item)
        if zone in SKIP_ZONES:
            continue
        node = item.parent
        for _ in range(6):
            if node is None or node.name in ("body", "html", "[document]", "main"):
                break
            entry = counts.setdefault(id(node), [node, 0, []])
            entry[1] += 1
            entry[2].append(item)
            node = node.parent
    qualifying: Dict[int, Tuple[Any, int, List[Any], int]] = {}
    for node_id, (node, n, items) in counts.items():
        if n < 4:
            continue
        words = H.word_count(H.clean_text(node))
        if words > 2 * n + 12:
            continue
        qualifying[node_id] = (node, n, items, words)
    # Innermost containers: a wall whose descendant also qualifies with
    # the same number of items is a wrapper of that wall.
    walls = []
    for node_id, (node, n, items, words) in qualifying.items():
        inner = False
        for other_id, (other, other_n, _, _) in qualifying.items():
            if other_id != node_id and other_n >= 4 and node in other.parents:
                inner = True
                break
        if not inner:
            walls.append((node, n, items, words))
    out: List[Dict[str, Any]] = []
    other_groups = 0
    seen_names = []
    for node, n, items, words in walls:
        names = _unique([x for x in (_item_name(i) for i in items) if x], 30)
        heading = node.find_previous(re.compile(r"^h[1-6]$"))
        heading_text = H.clean_text(heading, collapse=True) if heading is not None else None
        after = _following_text(dom, node)
        own = H.clean_text(node)
        signals = []
        ident = " ".join(_classes(a) + " " + str(a.get("id") or "") for a in [node] + list(node.parents)[:3]
                         if getattr(a, "attrs", None) is not None)
        if LOGO_CLASS.search(ident):
            signals.append("logo-like class or id")
        if any(re.search(r"logo", " ".join(str(i.get(k) or "") for k in ("alt", "src", "aria-label", "class")), re.I)
               for i in items):
            signals.append("'logo' in image names")
        for label, text in (("heading", heading_text), ("text", own), ("caption after", after)):
            if text and TRUST_CONTEXT.search(text) and H.word_count(text) <= 25:
                signals.append("%s: %s" % (label, _clip(text, 80)))
                break
        if not signals:
            # A textless row alone is also what product mockups look like.
            other_groups += 1
            continue
        if words == 0 and len({id(i.parent) for i in items}) >= 4:
            signals.append("row of 4+ textless items")
        key = sorted(_norm(x) for x in names) if names else ["#%d" % n, _norm(after or ""), _norm(heading_text or "")]
        if key in seen_names:
            continue
        seen_names.append(key)
        zone, block = dom.zone(node)
        out.append({
            "zone": zone,
            "block": block,
            "items": n,
            "names": names,
            "unnamed": max(0, n - len(names)),
            "text": _clip(own, 160) or None,
            "nearest_heading": _clip(heading_text, 120) if heading_text else None,
            "caption_after": after,
            "signals": signals,
        })
    return out[:6], other_groups


def _attribution_after(text: str) -> Optional[str]:
    """'"We cut close to 3 days." - Maria Lopez, Controller' -> 'Maria Lopez, Controller'."""
    match = re.search(r"[\"”»’']\s*[-,]?\s*([^\"“”]{3,120})$", text)
    if match:
        tail = match.group(1).strip(" -,")
        if 1 <= len(tail.split()) <= 16:
            return tail
    return None


def _quotes(dom: _Dom) -> List[Dict[str, Any]]:
    H = dom.H
    candidates: List[Tuple[str, Any]] = []
    for tag in dom.body.find_all(["blockquote", "q"]):
        candidates.append(("blockquote" if tag.name == "blockquote" else "q", tag))
    for tag in dom.body.find_all(True):
        ident = _classes(tag) + " " + str(tag.get("id") or "")
        if TESTIMONIAL_CLASS.search(ident):
            candidates.append(("testimonial class", tag))
    for tag in dom.body.find_all(["p", "span", "div", "figcaption"]):
        if tag.name == "div" and tag.find(["div", "p", "section", "ul"]) is not None:
            continue
        text = H.clean_text(tag)
        if QUOTE_START.match(text) and H.word_count(text) >= 6:
            candidates.append(("quoted text", tag))
    kept: List[Dict[str, Any]] = []
    keys: List[str] = []
    for source, tag in candidates:
        text = H.clean_text(tag)
        words = H.word_count(text)
        if words < 6 or words > 150:
            continue
        zone, block = dom.zone(tag)
        if zone in SKIP_ZONES:
            continue
        key = _norm(text)
        if any(key in k or k in key for k in keys):
            continue
        attribution = None
        for name in ("cite", "figcaption", "footer"):
            found = tag.find(name)
            if found is None and tag.parent is not None and tag.parent.name == "figure":
                found = tag.parent.find(name)
            if found is not None and H.clean_text(found):
                attribution = H.clean_text(found)
                break
        if attribution is None:
            for found in tag.find_all(True):
                ident = _classes(found) + " " + str(found.get("id") or "")
                if ATTRIBUTION_CLASS.search(ident) and H.clean_text(found) and H.word_count(H.clean_text(found)) <= 20:
                    attribution = H.clean_text(found)
                    break
        if attribution is None:
            attribution = _attribution_after(text)
        if attribution is None:
            sibling = tag.find_next_sibling()
            if sibling is not None:
                sib_text = H.clean_text(sibling)
                if sib_text and H.word_count(sib_text) <= 14:
                    attribution = sib_text
        keys.append(key)
        kept.append({
            "text": _clip(text, 400),
            "attribution": _clip(attribution, 160) if attribution else None,
            "zone": zone,
            "block": block,
            "source": source,
        })
        if len(kept) >= 12:
            break
    return kept


def _ratings(segments: List[Dict[str, Any]], dom: _Dom, facts: Dict[str, Any]) -> Dict[str, Any]:
    found: List[Dict[str, Any]] = []
    for index, seg in enumerate(segments):
        if seg["zone"] in SKIP_ZONES:
            continue
        matches = _match_texts(RATING_PATTERNS, seg["text"])
        if not matches:
            continue
        window = " ".join(s["text"] for s in segments[max(0, index - 1): index + 2]
                          if s["block"] == seg["block"])
        platforms = _unique(_match_texts(PLATFORM_PATTERNS, window), 3)
        found.append({"text": _clip(seg["text"], 200), "rating": matches[0],
                      "platforms": platforms, "zone": seg["zone"]})
    badges = []
    for img in dom.body.find_all("img"):
        alt = " ".join(str(img.get("alt") or "").split())
        if alt and (REVIEW_PLATFORMS.search(alt) or (PLATFORM_PATTERNS.search(alt) and RATING_WORDS.search(alt))):
            zone, _ = dom.zone(img)
            if zone not in SKIP_ZONES:
                badges.append({"alt": alt[:120], "zone": zone})
    aggregate = []
    for item in (facts.get("json_ld") or {}).get("items") or []:
        rating = item.get("aggregateRating") if isinstance(item, dict) else None
        if isinstance(item, dict) and str(item.get("@type")) == "AggregateRating":
            rating = item
        if isinstance(rating, dict):
            aggregate.append({
                "type": item.get("@type"),
                "name": item.get("name"),
                "rating_value": rating.get("ratingValue"),
                "rating_count": rating.get("ratingCount") or rating.get("reviewCount"),
                "best_rating": rating.get("bestRating"),
            })
    unique_found = []
    seen = set()
    for entry in found:
        key = _norm(entry["text"])
        if key not in seen:
            seen.add(key)
            unique_found.append(entry)
    return {"mentions": unique_found[:8], "platform_badges": badges[:8], "json_ld_aggregate": aggregate[:4]}


def _numeric_claims(segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    seen = set()
    for seg in segments:
        if seg["zone"] in SKIP_ZONES or seg["zone"] == "footer":
            continue
        for sentence in _sentences(seg["text"]):
            if len(sentence) > 240 or len(sentence.split()) < 3 or not NUMERIC_CLAIM_PATTERNS.search(sentence):
                continue
            stripped = RISK_REDUCER_PATTERNS.sub("", PRICE_PATTERNS.sub("", sentence))
            if not NUMERIC_CLAIM_PATTERNS.search(stripped):
                continue
            key = _norm(sentence)
            if key in seen:
                continue
            seen.add(key)
            out.append({"text": sentence, "zone": seg["zone"], "block": seg["block"]})
            if len(out) >= 15:
                return out
    return out


def _links(dom: _Dom, page_url: Optional[str]) -> List[Dict[str, Any]]:
    H = dom.H
    out = []
    for a in dom.body.find_all("a", href=True):
        href = str(a.get("href") or "").strip()
        if not href or href.lower().startswith(("javascript:", "mailto:", "tel:")):
            continue
        if page_url:
            try:
                from urllib.parse import urljoin
                href = urljoin(page_url, href)
            except ValueError:
                pass
        zone, block = dom.zone(a)
        out.append({"href": href, "text": _clip(H.clean_text(a), 80), "zone": zone, "block": block})
    return out


def _proof(dom: _Dom, segments: List[Dict[str, Any]], facts: Dict[str, Any],
           links: List[Dict[str, Any]]) -> Dict[str, Any]:
    case_links = _unique([l["href"] for l in links if CASE_STUDY_HREF.search(urlparse(l["href"]).path + "/")
                          and l["zone"] not in ("cookie", "dialog")], 8)
    walls, other_groups = _logo_walls(dom)
    return {
        "logo_walls": walls,
        "other_image_groups": other_groups,
        "quotes": _quotes(dom),
        "ratings": _ratings(segments, dom, facts),
        "numeric_claims": _numeric_claims(segments),
        "case_study_links": case_links,
    }


# ---------------------------------------------------------------------------
# Trust
# ---------------------------------------------------------------------------


def _trust(dom: _Dom, segments: List[Dict[str, Any]], links: List[Dict[str, Any]]) -> Dict[str, Any]:
    compliance: Dict[str, Dict[str, Any]] = {}

    def add(name: str, zone: str, evidence: str) -> None:
        entry = compliance.setdefault(name, {"name": name, "zones": [], "mentions": 0, "example": evidence})
        entry["mentions"] += 1
        if zone not in entry["zones"]:
            entry["zones"].append(zone)

    for seg in segments:
        for name, pattern in COMPLIANCE_PATTERNS:
            match = pattern.search(seg["text"])
            if match:
                add(name, seg["zone"], _clip(seg["text"], 160))
    badges = []
    for img in dom.body.find_all("img"):
        alt = " ".join(str(img.get("alt") or "").split())
        if not alt:
            continue
        zone, _ = dom.zone(img)
        for name, pattern in COMPLIANCE_PATTERNS:
            if pattern.search(alt):
                add(name, zone, "image: " + alt[:100])
                badges.append({"alt": alt[:100], "zone": zone})
                break
    legal: Dict[str, Dict[str, Any]] = {}
    for link in links:
        for kind, pattern in LEGAL_LINKS:
            if pattern.search(link["href"]):
                if kind not in legal:
                    legal[kind] = {"href": link["href"], "zone": link["zone"]}
                break
    guarantees = []
    seen = set()
    for seg in segments:
        if seg["zone"] in SKIP_ZONES:
            continue
        for sentence in _sentences(seg["text"]):
            if GUARANTEE_PATTERNS.search(sentence) and len(sentence) <= 240:
                key = _norm(sentence)
                if key not in seen:
                    seen.add(key)
                    guarantees.append({"text": sentence, "zone": seg["zone"]})
    return {
        "compliance": list(compliance.values()),
        "badge_images": badges[:8],
        "legal_links": legal,
        "guarantee_sentences": guarantees[:8],
    }


# ---------------------------------------------------------------------------
# Objections
# ---------------------------------------------------------------------------


def _faq_items(item: Dict[str, Any]) -> List[str]:
    out = []
    entities = item.get("mainEntity")
    if isinstance(entities, dict):
        entities = [entities]
    if isinstance(entities, list):
        for entity in entities:
            if isinstance(entity, dict) and entity.get("name"):
                out.append(" ".join(str(entity["name"]).split()))
    return out


def _objections(dom: _Dom, segments: List[Dict[str, Any]], facts: Dict[str, Any],
                links: List[Dict[str, Any]]) -> Dict[str, Any]:
    H = dom.H
    questions: List[Tuple[str, str]] = []
    for summary in dom.body.find_all("summary"):
        text = H.clean_text(summary)
        if text:
            questions.append((text, "details/summary"))
    for item in (facts.get("json_ld") or {}).get("items") or []:
        types = item.get("@type") if isinstance(item, dict) else None
        types = types if isinstance(types, list) else [types]
        if "FAQPage" in [str(t) for t in types]:
            questions.extend((q, "FAQPage JSON-LD") for q in _faq_items(item))
    for tag in dom.body.find_all(["h2", "h3", "h4", "h5", "dt", "button"]):
        text = H.clean_text(tag, collapse=True)
        if text and QUESTION_END.search(text) and H.word_count(text) <= 25:
            zone, _ = dom.zone(tag)
            if zone not in SKIP_ZONES:
                source = "accordion button" if tag.name == "button" else "question heading"
                questions.append((text, source))
    seen = set()
    faq = []
    sources = []
    for text, source in questions:
        key = _norm(text)
        if key in seen:
            continue
        seen.add(key)
        faq.append(text)
        if source not in sources:
            sources.append(source)
    prices = []
    price_zones: Dict[str, int] = {}
    for seg in segments:
        if seg["zone"] in SKIP_ZONES:
            continue
        for match in _match_texts(PRICE_PATTERNS, seg["text"]):
            prices.append(match.strip())
            price_zones[seg["zone"]] = price_zones.get(seg["zone"], 0) + 1
    ctas = facts.get("ctas") or []
    pricing_links = _unique([c["href"] for c in ctas if c.get("intent") == "pricing" and c.get("href")], 3)
    if not pricing_links:
        pricing_links = _unique([l["href"] for l in links if re.search(r"/(?:pricing|plans|prices)(?:/|$|\?|#)",
                                                                         urlparse(l["href"]).path + "/")], 3)
    comparison = _unique([l["href"] for l in links if COMPARISON_HREF.search(urlparse(l["href"]).path)], 8)
    risk = []
    seen_risk = set()
    for seg in segments:
        if seg["zone"] in SKIP_ZONES:
            continue
        for match in _match_texts(RISK_REDUCER_PATTERNS, seg["text"]):
            key = _norm(match)
            if key not in seen_risk:
                seen_risk.add(key)
                risk.append({"text": match, "context": _clip(seg["text"], 160), "zone": seg["zone"]})
    tables = sum(1 for block in facts.get("outline") or [] if block.get("has_table"))
    return {
        "faq": {"count": len(faq), "sources": sources, "questions": faq[:20]},
        "pricing": {
            "prices_on_page": len(prices),
            "price_examples": _unique(prices, 8),
            "price_zones": price_zones,
            "pricing_links": pricing_links,
            "sales_contact_ctas": sum(1 for c in ctas if c.get("intent") == "demo"),
        },
        "comparison_links": comparison,
        "tables": tables,
        "risk_reducers": risk[:10],
    }


# ---------------------------------------------------------------------------
# Urgency, navigation, measurement, speed diagnostics
# ---------------------------------------------------------------------------


def _urgency(dom: _Dom, segments: List[Dict[str, Any]]) -> Dict[str, Any]:
    candidates = []
    seen = set()
    for seg in segments:
        if seg["zone"] in SKIP_ZONES:
            continue
        for match in _match_texts(URGENCY_PATTERNS, seg["text"]):
            key = (_norm(match), _norm(seg["text"])[:80])
            if key in seen:
                continue
            seen.add(key)
            candidates.append({"phrase": match, "context": _clip(seg["text"], 200), "zone": seg["zone"]})
    countdowns = 0
    for el in dom.body.find_all(True):
        if COUNTDOWN_CLASS.search(_classes(el) + " " + str(el.get("id") or "")):
            countdowns += 1
    return {"candidates": candidates[:10], "countdown_elements": countdowns}


def _navigation(links: List[Dict[str, Any]], page_url: Optional[str]) -> Dict[str, Any]:
    nav = [l for l in links if l["zone"] == "nav"]
    footer = [l for l in links if l["zone"] == "footer"]
    page = (page_url or "").split("#")[0]
    exits = _unique([l["href"].split("#")[0] for l in nav if l["href"].split("#")[0] not in ("", page)])
    return {
        "nav_links": len(nav),
        "nav_exits": len(exits),
        "nav_examples": _unique([l["text"] for l in nav if l["text"]], 12),
        "footer_links": len(footer),
        "body_links": sum(1 for l in links if l["zone"] in ("hero", "body")),
    }


def _measurement(markup: str) -> Dict[str, Any]:
    blob = "\n".join(m.group(0)[:100000] for m in _TECH_MARKUP_RE.finditer(markup or ""))
    found: Dict[str, List[str]] = {c: [] for c in MEASUREMENT_CATEGORIES}
    for category, name, pattern in MEASUREMENT_SIGNATURES:
        if pattern.search(blob) and name not in found[category]:
            found[category].append(name)
    notes = []
    if found["tag_manager"]:
        notes.append("A tag manager is present: tools it loads at run time are not visible in static HTML.")
    if not found["experimentation"]:
        notes.append("No client-side experimentation tool seen in static HTML (server-side or tag-manager "
                     "tools would not show here).")
    found["notes"] = notes
    return found


def _speed_diagnostics(markup: str, facts: Dict[str, Any], dom: _Dom,
                       fetch: Optional[Dict[str, Any]], hero: Dict[str, Any]) -> Dict[str, Any]:
    head_match = _HEAD_RE.search(markup or "")
    head = head_match.group(1) if head_match else ""
    blocking = []
    for attrs in _SCRIPT_TAG_RE.findall(head):
        if not re.search(r"\bsrc\s*=", attrs, re.I):
            continue
        if re.search(r"\b(?:async|defer)\b", attrs, re.I) or re.search(r"type\s*=\s*[\"']?module", attrs, re.I):
            continue
        src = re.search(r"\bsrc\s*=\s*[\"']?([^\"'\s>]+)", attrs, re.I)
        blocking.append(src.group(1)[:120] if src else "?")
    stylesheets = preconnect = preload = 0
    for attrs in _LINK_TAG_RE.findall(head):
        rel = re.search(r"\brel\s*=\s*[\"']?([^\"'>]+)", attrs, re.I)
        rel_value = rel.group(1).lower() if rel else ""
        if "stylesheet" in rel_value:
            stylesheets += 1
        if "preconnect" in rel_value:
            preconnect += 1
        if "preload" in rel_value:
            preload += 1
    formats: Dict[str, int] = {}
    for img in dom.body.find_all("img"):
        if img.get("data-cro-svg") or img.get("data-cro-media"):
            continue
        src = str(img.get("src") or img.get("data-src") or "")
        ext = re.search(r"\.(avif|webp|png|jpe?g|gif|svg)(?:$|\?)", urlparse(src).path if src else "", re.I)
        key = ext.group(1).lower().replace("jpeg", "jpg") if ext else ("data-uri" if src.startswith("data:") else "other")
        formats[key] = formats.get(key, 0) + 1
    media = facts.get("media") or {}
    scripts = facts.get("scripts") or {}
    return {
        "html_bytes": (fetch or {}).get("bytes") or len((markup or "").encode("utf-8")),
        "fetch_ms": (fetch or {}).get("elapsed_ms"),
        "render_blocking_head_scripts": len(blocking),
        "render_blocking_examples": blocking[:5],
        "head_stylesheets": stylesheets,
        "preconnect_hints": preconnect,
        "preload_hints": preload,
        "fetchpriority_high": bool(re.search(r"fetchpriority\s*=\s*[\"']?high", markup or "", re.I)),
        "images": media.get("images"),
        "images_lazy": media.get("images_lazy"),
        "image_formats": formats,
        "hero_first_image_lazy": hero.get("first_image_lazy_loaded"),
        "third_party_script_hosts": len(scripts.get("third_party") or []),
        "inline_scripts": scripts.get("inline_count"),
        "viewport_meta": (facts.get("meta") or {}).get("viewport"),
        "note": "Diagnostics from static HTML only. Core Web Vitals pass or fail needs PageSpeed field data (--psi).",
    }


# ---------------------------------------------------------------------------
# Page extraction (pure: no network)
# ---------------------------------------------------------------------------


def _outline(facts: Dict[str, Any], max_blocks: int) -> List[Dict[str, Any]]:
    out = []
    for block in (facts.get("outline") or [])[:max_blocks]:
        out.append({
            "index": block.get("index"),
            "heading": block.get("heading"),
            "heading_level": block.get("heading_level"),
            "words": block.get("words"),
            "text": _clip(block.get("text") or "", 240),
            "ctas": block.get("ctas"),
            "images": block.get("images"),
            "has_form": block.get("has_form"),
            "has_blockquote": block.get("has_blockquote"),
            "has_details": block.get("has_details"),
            "has_table": block.get("has_table"),
        })
    return out


def extract_page(markup: str, url: Optional[str] = None, fetch: Optional[Dict[str, Any]] = None,
                 max_blocks: int = MAX_BLOCKS) -> Dict[str, Any]:
    """Facts for one page. Returns {"status", "message", "page"}.

    status is cli.STATUS_OK or cli.STATUS_NOTHING (JS shell or no visible
    text, page None). message is a note for the model ("" when none).
    """
    H = _html()
    facts = H.page_facts(markup, url, text_chars=0, max_blocks=200, max_ctas=120)
    status, message = cli.facts_outcome(facts)
    if status == cli.STATUS_NOTHING:
        return {"status": status, "message": message, "page": None,
                "shell": facts.get("js_shell_signals"), "title": facts.get("title")}
    dom = _Dom(markup)
    segments = _segments(dom)
    links = _links(dom, url)
    hero = _hero(dom, facts, segments)
    headings = facts.get("headings") or {}
    json_ld = facts.get("json_ld") or {}
    meta = facts.get("meta") or {}
    page = {
        "url": url,
        "title": facts.get("title"),
        "lang": facts.get("lang"),
        "meta_description": meta.get("description"),
        "word_count": facts.get("word_count"),
        "main_word_count": facts.get("main_word_count"),
        "hero": hero,
        "headings": {
            "h1": headings.get("h1") or [],
            "h2": (headings.get("h2") or [])[:30],
            "h3_count": len(headings.get("h3") or []),
        },
        "outline": _outline(facts, max_blocks),
        "outline_blocks_total": len(facts.get("outline") or []),
        "ctas": _ctas(dom, facts),
        "forms": _forms(facts),
        "proof": _proof(dom, segments, facts, links),
        "trust": _trust(dom, segments, links),
        "objections": _objections(dom, segments, facts, links),
        "urgency": _urgency(dom, segments),
        "navigation": _navigation(links, url),
        "measurement": _measurement(markup),
        "speed_diagnostics": None,
        "accessibility_hints": {
            "images_missing_alt": (facts.get("media") or {}).get("images_missing_alt"),
            "h1_count": len(headings.get("h1") or []),
        },
        "json_ld_types": json_ld.get("types") or [],
        "hidden_removed": facts.get("hidden_removed") or {},
        "notes": list(facts.get("notes") or []),
    }
    page["speed_diagnostics"] = _speed_diagnostics(markup, facts, dom, fetch, hero)
    if page["hero"]["headline"] is None:
        page["notes"].append("No h1 or heading-role headline found in the first block.")
    lang = (facts.get("lang") or "").lower()
    if lang and not lang.startswith("en"):
        page["notes"].append(
            "Page language is %s: text-pattern candidates (urgency, risk reducers, guarantees, numeric "
            "claims) use English patterns and may miss local phrasing. Read hero.text and outline text "
            "for those dimensions; structural facts are language independent." % facts.get("lang"))
    if message:
        page["notes"].append(message)
    return {"status": cli.STATUS_OK, "message": message, "page": page}


def competitor_summary(page: Dict[str, Any]) -> Dict[str, Any]:
    """The comparison facts for one page (B83 side-by-side)."""
    hero = page.get("hero") or {}
    proof = page.get("proof") or {}
    objections = page.get("objections") or {}
    primary = (page.get("ctas") or {}).get("primary_guess") or {}
    quotes = proof.get("quotes") or []
    walls = proof.get("logo_walls") or []
    ratings = proof.get("ratings") or {}
    return {
        "headline": hero.get("headline"),
        "subheadline": hero.get("subheadline"),
        "primary_cta": {"text": primary.get("text"), "intent": primary.get("intent"), "zone": primary.get("zone")},
        "hero_risk_reducers": hero.get("risk_reducers"),
        "hero_media": hero.get("media"),
        "proof": {
            "logo_names": sum(len(w.get("names") or []) for w in walls),
            "logo_examples": [n for w in walls for n in (w.get("names") or [])][:8],
            "quotes": len(quotes),
            "quotes_with_attribution": sum(1 for q in quotes if q.get("attribution")),
            "ratings": [r.get("text") for r in ratings.get("mentions") or []][:3],
            "numeric_claims": [c.get("text") for c in proof.get("numeric_claims") or []][:4],
        },
        "pricing": {
            "prices_on_page": (objections.get("pricing") or {}).get("prices_on_page"),
            "price_examples": ((objections.get("pricing") or {}).get("price_examples") or [])[:4],
            "pricing_link": bool((objections.get("pricing") or {}).get("pricing_links")),
        },
        "faq_questions": (objections.get("faq") or {}).get("count"),
        "compliance": [c.get("name") for c in (page.get("trust") or {}).get("compliance") or []],
        "nav_exits": (page.get("navigation") or {}).get("nav_exits"),
    }


# ---------------------------------------------------------------------------
# PageSpeed Insights (field data first)
# ---------------------------------------------------------------------------


def psi_summary(result: Dict[str, Any]) -> Dict[str, Any]:
    field = result.get("field") or {}
    metrics = field.get("metrics") or {}

    def metric(name: str) -> Optional[Dict[str, Any]]:
        entry = metrics.get(name)
        if not entry:
            return None
        return {"p75": entry.get("value"), "unit": entry.get("unit"), "category": entry.get("category")}

    lab = result.get("lab") or {}
    return {
        "strategy": result.get("strategy"),
        "status": result.get("status"),
        "key_source": result.get("key_source"),
        "field_scope": field.get("scope"),
        "cwv_assessment": field.get("cwv_assessment"),
        "lcp": metric("lcp"),
        "inp": metric("inp"),
        "cls": metric("cls"),
        "collection_period": field.get("collection_period"),
        "lab_diagnostics": {
            "performance_score": lab.get("performance_score"),
            "lcp_ms": lab.get("lcp_ms"),
            "cls": lab.get("cls"),
            "tbt_ms": lab.get("tbt_ms"),
        } if lab else None,
        "notes": result.get("notes") or [],
        "errors": result.get("errors") or [],
    }


def run_psi(url: str, strategies: List[str], timeout: float) -> Dict[str, Any]:
    from _growthkit import psi
    out = {}
    for strategy in strategies:
        try:
            result = psi.fetch(url, strategy=strategy, timeout=max(timeout, 60.0))
        except (ValueError, RuntimeError) as exc:
            result = {"status": "usage_error", "strategy": strategy, "errors": [str(exc)], "notes": []}
        out[strategy] = psi_summary(result)
    return out


def psi_key_present() -> Optional[str]:
    for name in ("PAGESPEED_API_KEY", "GOOGLE_API_KEY"):
        if (os.environ.get(name) or "").strip():
            return name
    return None


# ---------------------------------------------------------------------------
# --score: deterministic arithmetic over the model's rubric scores
# ---------------------------------------------------------------------------


def _band(value: float) -> str:
    for floor, label in BANDS:
        if value >= floor:
            return label
    return BANDS[-1][1]


def _dimension_entries(raw: Any) -> Dict[str, Dict[str, Any]]:
    if isinstance(raw, list):
        entries: Dict[str, Dict[str, Any]] = {}
        for item in raw:
            if not isinstance(item, dict) or not item.get("id"):
                raise cli.UsageError("Each item in 'dimensions' needs an 'id'.")
            entries[str(item["id"])] = item
        return entries
    if isinstance(raw, dict):
        out = {}
        for key, value in raw.items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                value = {"score": value}
            if not isinstance(value, dict):
                raise cli.UsageError("Dimension %r must be an object such as {\"score\": 6, \"confidence\": \"high\"}." % key)
            out[str(key)] = value
        return out
    raise cli.UsageError("'dimensions' must be an object keyed by dimension id, or a list.")


def compute_score(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Weighted composite from per-dimension rubric scores (0-10 each).

    Dimensions marked "na" or "not_measured", or missing, are dropped and the
    weights renormalized. A composite is shown only when the scored weight is
    at least 60% of the applicable weight. Raises cli.UsageError on bad input.
    """
    if not isinstance(payload, dict):
        raise cli.UsageError("The scores file must hold a JSON object.")
    entries = _dimension_entries(payload.get("dimensions", payload if "value_prop" in payload else None))
    unknown = sorted(set(entries) - set(DIMENSION_IDS))
    if unknown:
        raise cli.UsageError("Unknown dimension id(s): %s. Valid ids: %s." % (", ".join(unknown), ", ".join(DIMENSION_IDS)))
    notes: List[str] = []
    version = payload.get("rubric_version")
    if version and version != RUBRIC_VERSION:
        notes.append("rubric_version %r differs from this script's %s; scores may not be comparable." % (version, RUBRIC_VERSION))
    rows = []
    missing = []
    for dim_id, label, weight in DIMENSIONS:
        entry = entries.get(dim_id)
        if entry is None:
            missing.append(dim_id)
            entry = {"status": "not_measured", "reason": "not in the scores file"}
        status = str(entry.get("status") or ("scored" if entry.get("score") is not None else "not_measured")).lower()
        status = status.replace("n/a", "na").replace("not measured", "not_measured")
        if status not in STATUSES:
            raise cli.UsageError("%s: status must be one of %s, got %r." % (dim_id, ", ".join(STATUSES), entry.get("status")))
        score = None
        if status == "scored":
            try:
                score = cli.to_number(entry.get("score"), field=dim_id, minimum=0, maximum=10)
            except cli.CoercionError as exc:
                raise cli.UsageError(str(exc))
            if score is None:
                raise cli.UsageError("%s: status is scored but no score (0-10) was given." % dim_id)
            if float(score).is_integer():
                score = int(score)
        confidence = str(entry.get("confidence") or "").lower() or None
        if status == "scored":
            if confidence is None:
                confidence = "medium"
                notes.append("%s had no confidence; medium was assumed." % dim_id)
            elif confidence not in CONFIDENCE_LEVELS:
                raise cli.UsageError("%s: confidence must be high, medium or low, got %r." % (dim_id, entry.get("confidence")))
        evidence = entry.get("evidence") or []
        if isinstance(evidence, str):
            evidence = [evidence]
        if status == "scored" and not evidence:
            notes.append("%s has no evidence IDs; every score must cite evidence." % dim_id)
        rows.append({
            "id": dim_id,
            "label": label,
            "score": score,
            "max": 10,
            "weight": weight,
            "status": status,
            "confidence": confidence if status == "scored" else None,
            "evidence": [str(e) for e in evidence],
            "justification": entry.get("justification") or entry.get("reason"),
        })
    if missing:
        notes.append("Not in the scores file, counted as not measured: %s." % ", ".join(missing))
    applicable = [r for r in rows if r["status"] != "na"]
    scored = [r for r in rows if r["status"] == "scored"]
    applicable_weight = sum(r["weight"] for r in applicable)
    scored_weight = sum(r["weight"] for r in scored)
    for row in rows:
        if row["status"] == "scored" and scored_weight:
            row["weight_share"] = round(row["weight"] / scored_weight, 4)
            row["points"] = round(100.0 * row["weight"] * row["score"] / 10.0 / scored_weight, 2)
            row["points_lost"] = round(100.0 * row["weight"] * (10 - row["score"]) / 10.0 / scored_weight, 2)
        else:
            row["weight_share"] = None
            row["points"] = None
            row["points_lost"] = None
    share = (scored_weight / applicable_weight) if applicable_weight else 0.0
    value = None
    exact = None
    if scored_weight:
        exact = 100.0 * sum(r["weight"] * r["score"] / 10.0 for r in scored) / scored_weight
    show = bool(scored) and share >= MIN_MEASURED_SHARE
    reason = None
    if not scored:
        reason = "No dimension was scored."
    elif not show:
        reason = ("Only %d%% of the applicable weight was measured (at least %d%% is needed for a total); "
                  "show per-dimension scores only." % (round(share * 100), round(MIN_MEASURED_SHARE * 100)))
    if show:
        value = int(round(exact))
    confidence = None
    if scored_weight:
        high = sum(r["weight"] for r in scored if r["confidence"] == "high") / scored_weight
        low = sum(r["weight"] for r in scored if r["confidence"] == "low") / scored_weight
        confidence = "high" if high >= 0.8 else ("low" if low > 0.5 else "medium")
    ranked = sorted([r for r in scored], key=lambda r: (-(r["points_lost"] or 0), r["id"]))
    header = None
    if show:
        header = ("**Score:** %d/100 (rubric; confidence %s; %d%% of weight measured)"
                  % (value, confidence, round(share * 100)))
    return {
        "mode": "score",
        "scoring": {
            "mode": "rubric",
            "version": RUBRIC_VERSION,
            "value": value,
            "max": 100,
            "exact": round(exact, 2) if exact is not None and show else None,
            "band": _band(value) if value is not None else None,
            "confidence": confidence,
            "measured_weight": round(share, 4),
            "scored_weight": scored_weight,
            "applicable_weight": applicable_weight,
            "show_composite": show,
            "no_composite_reason": reason,
            "header_line": header,
            "noise_note": "Model-assigned scores can move a few points between runs; treat differences under 5 points as noise.",
        },
        "dimensions": rows,
        "biggest_gaps": [{"id": r["id"], "label": r["label"], "score": r["score"], "points_lost": r["points_lost"]}
                         for r in ranked[:3]],
        "notes": notes,
    }


# ---------------------------------------------------------------------------
# Demo page (only with --demo; labelled DEMO DATA)
# ---------------------------------------------------------------------------

DEMO_HTML = """<!doctype html><html lang="en"><head><title>Ledgerly - month-end close for finance teams</title>
<meta name="viewport" content="width=device-width, initial-scale=1"></head><body>
<nav><a href="/">Ledgerly</a><a href="/product">Product</a><a href="/pricing">Pricing</a><a href="/login">Log in</a>
<a class="btn" href="/signup">Start free</a></nav>
<main><section><h1>Close your books in days, not weeks</h1>
<p>Ledgerly matches bank, card and invoice data automatically so finance teams of 2 to 20 stop living in spreadsheets.</p>
<a class="btn btn-primary" href="/signup">Start your free trial</a><a href="/demo">Book a demo</a>
<p>14-day free trial. No credit card required.</p></section>
<section><h2>Trusted by finance teams</h2><ul class="logos"><li><img src="/l/a.svg" alt="Example Co"></li>
<li><img src="/l/b.svg" alt="Sample Labs"></li><li><img src="/l/c.svg" alt="Demo Corp"></li><li><img src="/l/d.svg" alt="Placeholder Inc"></li></ul></section>
<section><h2>Questions</h2><details><summary>Do I need a credit card?</summary><p>No.</p></details></section>
</main><footer><a href="/privacy">Privacy</a><a href="/terms">Terms</a></footer></body></html>"""


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------


def _human(envelope: Dict[str, Any]) -> str:
    if envelope.get("mode") == "score":
        scoring = envelope.get("scoring") or {}
        lines = ["CRO rubric score (%s)" % scoring.get("version")]
        if scoring.get("show_composite"):
            lines.append("Total: %s/100 (%s), confidence %s, %d%% of weight measured" % (
                scoring.get("value"), scoring.get("band"), scoring.get("confidence"),
                round((scoring.get("measured_weight") or 0) * 100)))
        else:
            lines.append("No total: %s" % scoring.get("no_composite_reason"))
        for row in envelope.get("dimensions") or []:
            shown = "%s/10" % _fmt_num(row["score"]) if row["status"] == "scored" else row["status"]
            lines.append("  %-42s w%-3d %s" % (row["label"], row["weight"], shown))
        return "\n".join(lines)
    page = envelope.get("page")
    if not page:
        return "No page facts (status %s). %s" % (envelope.get("status"), " ".join(envelope.get("errors") or []))
    hero = page.get("hero") or {}
    proof = page.get("proof") or {}
    lines = [
        "CRO facts for %s" % (page.get("url") or envelope.get("input", {}).get("value")),
        "Headline (%s): %s" % (hero.get("headline_source"), hero.get("headline")),
        "Subheadline: %s" % hero.get("subheadline"),
        "Hero CTAs: %s" % ", ".join("%s [%s]" % (c["text"], c["intent"]) for c in hero.get("ctas") or []),
        "Risk reducers in hero: %s" % ", ".join(hero.get("risk_reducers") or []),
        "Logo walls: %d, quotes: %d, rating mentions: %d, numeric claims: %d" % (
            len(proof.get("logo_walls") or []), len(proof.get("quotes") or []),
            len((proof.get("ratings") or {}).get("mentions") or []), len(proof.get("numeric_claims") or [])),
        "FAQ questions: %d, forms: %d" % ((page.get("objections") or {}).get("faq", {}).get("count", 0),
                                          (page.get("forms") or {}).get("count", 0)),
        "Use --json for the full fact set.",
    ]
    return "\n".join(lines)


def _fmt_num(value: Any) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def build_parser() -> cli.ArgumentParser:
    parser = cli.build_parser(
        "Collect conversion facts from a landing page (URL or saved HTML), or compute the weighted "
        "rubric score with --score. The script never judges copy or design.",
        input_help="page URL or saved HTML file (omit with --score)",
        prog="cro_auditor.py",
        epilog=("Exit codes" + __doc__.split("Exit codes", 1)[1]) if __doc__ else None,
    )
    parser.add_argument("--url", metavar="URL",
                        help="original URL of a saved HTML file (resolves links; used for --psi)")
    parser.add_argument("--vs", metavar="URL", action="append", default=[],
                        help="competitor page to extract for a side-by-side (repeat, at most %d)" % MAX_COMPETITORS)
    parser.add_argument("--psi", choices=("auto", "on", "off"), default="auto",
                        help="PageSpeed Insights field data: auto runs it when PAGESPEED_API_KEY or "
                             "GOOGLE_API_KEY is set (default), on runs it keyless too, off skips it")
    parser.add_argument("--psi-strategy", choices=("mobile", "desktop", "both"), default="mobile",
                        help="PageSpeed strategy (default: mobile)")
    parser.add_argument("--max-blocks", type=int, default=MAX_BLOCKS, metavar="N",
                        help="outline blocks to include (default: %d)" % MAX_BLOCKS)
    parser.add_argument("--score", metavar="SCORES_JSON",
                        help="compute the weighted rubric total from a JSON file of dimension scores")
    return parser


def _fetch_markup(target: str, timeout: float, run: cli.Run) -> Tuple[Optional[Dict[str, Any]], str, str]:
    """(fetch result, status, message) for a URL."""
    result = _http().fetch(target, kind="html", timeout=timeout)
    status, message = cli.fetch_outcome(result)
    return result, status, message


def _extract_target(target: str, timeout: float, run: cli.Run, max_blocks: int) -> Dict[str, Any]:
    result, status, message = _fetch_markup(target, timeout, run)
    summary = _http().summarize(result)
    if status not in (cli.STATUS_OK, cli.STATUS_PARTIAL):
        return {"status": status, "message": message, "fetch": summary, "page": None}
    url = result.get("final_url") or result.get("url")
    extracted = extract_page(result.get("html") or "", url, result, max_blocks)
    if extracted["status"] == cli.STATUS_NOTHING:
        return {"status": extracted["status"], "message": extracted["message"], "fetch": summary,
                "page": None, "shell": extracted.get("shell")}
    return {"status": status, "message": message, "fetch": summary, "page": extracted["page"]}


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    run = cli.Run(TOOL, args)

    if args.score:
        if args.input or args.vs:
            return run.fail(cli.STATUS_USAGE, "--score takes only the scores file; run the extraction separately.")
        try:
            payload, _ = cli.load_json_input(args.score, expect=dict)
            result = compute_score(payload)
        except cli.UsageError as exc:
            return run.fail(cli.STATUS_USAGE, str(exc))
        for note in result.pop("notes"):
            run.note(note)
        return run.emit(result, human=_human)

    if len(args.vs) > MAX_COMPETITORS:
        return run.fail(cli.STATUS_USAGE, "At most %d competitor pages (--vs); deeper competitor work belongs "
                                          "to competitor-intel." % MAX_COMPETITORS)
    if args.max_blocks < 1:
        return run.fail(cli.STATUS_USAGE, "--max-blocks must be at least 1.")
    try:
        source = cli.resolve_input(args.input, allow_stdin=False, demo=args.demo)
    except cli.UsageError as exc:
        return run.fail(cli.STATUS_USAGE, str(exc))

    data: Dict[str, Any] = {"mode": "extract", "input": {"kind": source["kind"], "value": source["value"]}}
    page_url: Optional[str] = None
    status = cli.STATUS_OK
    if source["kind"] == "url":
        target = _extract_target(source["value"], args.timeout, run, args.max_blocks)
        data["fetch"] = target["fetch"]
        if target["status"] in (cli.STATUS_BLOCKED, cli.STATUS_UNREACHABLE, cli.STATUS_NOTHING):
            data["page"] = None
            if target.get("shell"):
                data["shell"] = target["shell"]
            return run.fail(target["status"], target["message"], data)
        if target["status"] == cli.STATUS_PARTIAL:
            run.error(target["message"])
            status = cli.STATUS_PARTIAL
        data["page"] = target["page"]
        page_url = (target["fetch"] or {}).get("final_url") or (target["fetch"] or {}).get("url")
    else:
        markup = DEMO_HTML if source["kind"] == "demo" else (source["text"] or "")
        page_url = args.url
        if page_url:
            try:
                page_url = _http().normalize_url(page_url)
            except ValueError as exc:
                return run.fail(cli.STATUS_USAGE, "--url: %s" % exc)
        elif source["kind"] == "demo":
            page_url = "https://ledgerly.example/"
        data["fetch"] = None
        extracted = extract_page(markup, page_url, None, args.max_blocks)
        if extracted["status"] == cli.STATUS_NOTHING:
            data["page"] = None
            data["shell"] = extracted.get("shell")
            return run.fail(cli.STATUS_NOTHING, extracted["message"], data)
        data["page"] = extracted["page"]
        if source["kind"] == "file" and not args.url:
            run.note("Saved file without --url: relative links were not resolved and PageSpeed was skipped.")

    # Competitors (B83): the same extractor, compact summary only.
    competitors = []
    last_host = _host(page_url)
    for competitor in args.vs:
        if _host(competitor) == last_host and last_host:
            time.sleep(SAME_HOST_DELAY)
        last_host = _host(competitor)
        target = _extract_target(competitor, args.timeout, run, args.max_blocks)
        entry = {"url": competitor, "status": target["status"], "fetch": target["fetch"]}
        if target["page"] is not None:
            entry["summary"] = competitor_summary(target["page"])
            if target["status"] == cli.STATUS_PARTIAL:
                entry["note"] = target["message"]
        else:
            entry["error"] = target["message"]
            run.error("Competitor %s: %s" % (competitor, target["message"]))
            status = cli.STATUS_PARTIAL
        competitors.append(entry)
    if args.vs:
        data["you"] = competitor_summary(data["page"])
        data["competitors"] = competitors

    # Core Web Vitals: field data only, never guessed from HTML.
    key_env = psi_key_present()
    speed: Dict[str, Any] = {"psi_key_env": key_env, "psi": None}
    want_psi = args.psi == "on" or (args.psi == "auto" and key_env)
    if want_psi and page_url and source["kind"] != "demo":
        strategies = ["mobile", "desktop"] if args.psi_strategy == "both" else [args.psi_strategy]
        speed["psi"] = run_psi(page_url, strategies, args.timeout)
        failed = [s for s, r in speed["psi"].items() if r["status"] not in ("ok", "no_field_data")]
        if failed:
            message = "PageSpeed Insights failed for %s: %s" % (
                ", ".join(failed), "; ".join(e for s in failed for e in speed["psi"][s]["errors"])[:300])
            if args.psi == "on":
                run.error(message)
                status = cli.STATUS_PARTIAL
            else:
                run.note(message)
    elif args.psi != "off" and not key_env:
        run.note("No PAGESPEED_API_KEY or GOOGLE_API_KEY set: Core Web Vitals not measured (speed dimension is "
                 "not_measured unless the user supplies field data).")
    data["speed"] = speed

    data["coverage"] = _coverage(data)
    return run.emit(data, status=status if status != cli.STATUS_OK else None, human=_human)


def _coverage(data: Dict[str, Any]) -> Dict[str, List[str]]:
    page = data.get("page") or {}
    measured = ["static HTML with hidden and non-rendered content removed"]
    not_measured = [
        "visual hierarchy, contrast, first-screen layout and mobile layout (needs desktop and 390 px screenshots)",
        "conversion rate, traffic and traffic source (needs the user's analytics)",
    ]
    psi = (data.get("speed") or {}).get("psi") or {}
    ok_field = [s for s, r in psi.items() if r.get("status") == "ok"]
    if ok_field:
        measured.append("Core Web Vitals field data (PageSpeed Insights, %s)" % ", ".join(ok_field))
    elif psi and all(r.get("status") == "no_field_data" for r in psi.values()):
        not_measured.append("Core Web Vitals (no CrUX field data for this page or origin; lab numbers are diagnostics only)")
    else:
        not_measured.append("Core Web Vitals field data (PageSpeed Insights not run or failed)")
    embedded = (page.get("forms") or {}).get("embedded_by_javascript") or []
    if embedded:
        not_measured.append("fields of forms rendered by JavaScript (%s); render the page to see them"
                            % ", ".join(e.get("provider", "?") for e in embedded))
    if (page.get("measurement") or {}).get("tag_manager"):
        not_measured.append("tools loaded through the tag manager")
    return {"measured": measured, "not_measured": not_measured}


if __name__ == "__main__":
    sys.exit(main())
