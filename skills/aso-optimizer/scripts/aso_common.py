"""Shared helpers for the aso-optimizer scripts (not a command).

Pure text helpers (no third-party imports at module level, so the metadata
validator runs without requests or beautifulsoup4):

    normalize_dashes()   en and em dashes in store text become "-" (same length)
    words()              Unicode word tokens, lower-cased
    split_title()        "Notion: Notes, Tasks, AI" -> ("Notion", "Notes, Tasks, AI")
    singular()           naive English singular for plural-pair checks
    valid_country()      ISO 3166 alpha-2 check

App Store helpers (import _growthkit.http lazily):

    get_json(), get_text()           fetch with retry on 403/429, never raise
    itunes_lookup(), itunes_search() iTunes Lookup and Search APIs
    store_page_data()                serialized-server-data JSON of an
                                     apps.apple.com page
    parse_product_page(), parse_search_page(), parse_hints(), parse_reviews_rss()

Everything here collects facts. Judging them is the model's job.
"""

from __future__ import annotations

import json
import plistlib
import re
import time
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote, urlparse

# ---------------------------------------------------------------------------
# Text
# ---------------------------------------------------------------------------

# Written as chr() codes so this file never contains the characters itself.
_DASHES = {chr(code): "-" for code in (0x2012, 0x2013, 0x2014, 0x2015, 0x2212, 0xFE31, 0xFE32, 0xFE58)}
_DASH_RE = re.compile("[" + "".join(_DASHES) + "]")


def normalize_dashes(text: Any) -> Any:
    """Replace en, em and figure dashes with '-' (one character for one, so counts stay exact)."""
    if not isinstance(text, str):
        return text
    return _DASH_RE.sub("-", text)


def count_dashes(text: Any) -> int:
    return len(_DASH_RE.findall(text)) if isinstance(text, str) else 0


def deep_normalize(value: Any, counter: Optional[List[int]] = None) -> Any:
    """normalize_dashes() on every string inside lists and dicts."""
    if isinstance(value, str):
        if counter is not None:
            counter[0] += count_dashes(value)
        return normalize_dashes(value)
    if isinstance(value, dict):
        return {key: deep_normalize(item, counter) for key, item in value.items()}
    if isinstance(value, list):
        return [deep_normalize(item, counter) for item in value]
    return value


WORD_RE = re.compile(r"[^\W_]+(?:['\u2019][^\W_]+)*", re.UNICODE)

# Function words that never count as keywords in an English listing. Apple's
# search page lists "the" and "to" as filler words to leave out of the
# keyword field (developer.apple.com/app-store/search/).
FILLER_WORDS = frozenset({
    "a", "an", "and", "or", "the", "to", "for", "of", "in", "on", "with", "by",
    "at", "from", "your", "my", "you", "is", "it", "its", "our", "into", "&",
})
GENERIC_WORDS = frozenset({"app", "apps", "game", "games", "application"})


def words(text: Optional[str]) -> List[str]:
    """Lower-cased Unicode word tokens; commas, colons and dashes never stick to words."""
    if not text:
        return []
    return [match.group(0).lower().replace("\u2019", "'") for match in WORD_RE.finditer(text)]


def content_words(text: Optional[str]) -> List[str]:
    """words() without filler words, in order, de-duplicated."""
    seen: List[str] = []
    for word in words(text):
        if word in FILLER_WORDS or word in seen:
            continue
        seen.append(word)
    return seen


_TITLE_SPLIT_RE = re.compile(r"\s*:\s*|\s+[-|]\s+|\s*\|\s*")


def split_title(title: Optional[str]) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Split a store title into (brand segment, keyword segment, separator).

    The brand is the text before the first ':' or ' - ' or '|'. A title with
    no separator returns (title, None, None): it may be all brand or all
    keywords, which the model judges.
    """
    if not title:
        return None, None, None
    text = normalize_dashes(title).strip()
    match = _TITLE_SPLIT_RE.search(text)
    if not match or match.start() == 0:
        return text, None, None
    brand = text[:match.start()].strip()
    rest = text[match.end():].strip() or None
    return brand or None, rest, match.group(0).strip() or " "


def singular(word: str) -> str:
    """Naive English singular: tasks -> task, notes -> note, diaries -> diary, boxes -> box."""
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 4 and word.endswith("es") and word[:-2].endswith(("s", "x", "z", "ch", "sh")):
        return word[:-2]
    if len(word) > 3 and word.endswith("s") and not word.endswith(("ss", "us", "is")):
        return word[:-1]
    return word


def utf8_len(text: Optional[str]) -> int:
    return len((text or "").encode("utf-8"))


def first_chars(text: Optional[str], limit: int) -> str:
    """The first `limit` characters, cut at a word boundary when possible."""
    if not text:
        return ""
    clean = text.strip()
    if len(clean) <= limit:
        return clean
    cut = clean[:limit]
    space = cut.rfind(" ")
    return (cut[:space] if space > limit * 0.6 else cut).rstrip() + " ..."


# Bullet glyphs counted at the start of description lines (facts only).
BULLET_RE = re.compile(r"^\s*([\u2022\u25cf\u25aa\u25b8\u25ba\u2023\u2043\u2713\u2714\u2705\u2192\u279c*+\-]|\d+[.)])\s+")


def description_facts(text: Optional[str], visible_chars: int = 170) -> Dict[str, Any]:
    """Length, line and paragraph counts, bullet glyphs and the first lines.

    visible_chars: roughly what shows before "more" on the product page. The
    exact cut depends on the device, so the model treats it as approximate.
    """
    body = text or ""
    lines = [line for line in body.splitlines()]
    nonblank = [line for line in lines if line.strip()]
    paragraphs = [block for block in re.split(r"\n\s*\n", body) if block.strip()]
    glyphs: Dict[str, int] = {}
    for line in nonblank:
        match = BULLET_RE.match(line)
        if match:
            glyph = match.group(1)
            glyph = "1." if glyph[0].isdigit() else glyph
            glyphs[glyph] = glyphs.get(glyph, 0) + 1
    caps_lines = [line.strip() for line in nonblank
                  if len(line.strip()) >= 4 and line.strip().upper() == line.strip()
                  and any(ch.isalpha() for ch in line)]
    return {
        "length": len(body),
        "lines": len(nonblank),
        "paragraphs": len(paragraphs),
        "bullet_lines": sum(glyphs.values()),
        "bullet_glyphs": glyphs,
        "heading_lines": caps_lines[:12],
        "first_visible": first_chars(body.replace("\n", " "), visible_chars),
        "first_paragraph": paragraphs[0].strip() if paragraphs else "",
    }


# ISO 3166-1 alpha-2 codes. The App Store covers most of them; the API answers
# HTTP 400 for a storefront that does not exist.
ISO_COUNTRIES = frozenset("""
ad ae af ag ai al am ao aq ar as at au aw ax az ba bb bd be bf bg bh bi bj bl bm bn bo bq br bs
bt bv bw by bz ca cc cd cf cg ch ci ck cl cm cn co cr cu cv cw cx cy cz de dj dk dm do dz ec ee
eg eh er es et fi fj fk fm fo fr ga gb gd ge gf gg gh gi gl gm gn gp gq gr gs gt gu gw gy hk hm
hn hr ht hu id ie il im in io iq ir is it je jm jo jp ke kg kh ki km kn kp kr kw ky kz la lb lc
li lk lr ls lt lu lv ly ma mc md me mf mg mh mk ml mm mn mo mp mq mr ms mt mu mv mw mx my mz na
nc ne nf ng ni nl no np nr nu nz om pa pe pf pg ph pk pl pm pn pr ps pt pw py qa re ro rs ru rw
sa sb sc sd se sg sh si sj sk sl sm sn so sr ss st sv sx sy sz tc td tf tg th tj tk tl tm tn to
tr tt tv tw tz ua ug um us uy uz va vc ve vg vi vn vu wf ws ye yt za zm zw
""".split())

# X-Apple-Store-Front ids for the autocomplete endpoint. Checked on
# 2026-10-24 by requesting hints in each storefront's language (us, de, jp,
# kr, ru, mx, br); the others follow the same published sequence.
STOREFRONT_IDS = {
    "us": 143441, "fr": 143442, "de": 143443, "gb": 143444, "at": 143445, "be": 143446,
    "fi": 143447, "gr": 143448, "ie": 143449, "it": 143450, "lu": 143451, "nl": 143452,
    "pt": 143453, "es": 143454, "ca": 143455, "se": 143456, "no": 143457, "dk": 143458,
    "ch": 143459, "au": 143460, "nz": 143461, "jp": 143462, "hk": 143463, "sg": 143464,
    "cn": 143465, "kr": 143466, "in": 143467, "mx": 143468, "ru": 143469, "tw": 143470,
    "vn": 143471, "za": 143472, "my": 143473, "ph": 143474, "th": 143475, "id": 143476,
    "pk": 143477, "pl": 143478, "sa": 143479, "tr": 143480, "ae": 143481, "hu": 143482,
    "cl": 143483, "pa": 143485, "lk": 143486, "ro": 143487, "cz": 143489, "il": 143491,
    "ua": 143492, "kw": 143493, "hr": 143494, "cr": 143495, "sk": 143496, "lb": 143497,
    "qa": 143498, "si": 143499, "co": 143501, "ve": 143502, "br": 143503, "gt": 143504,
    "ar": 143505, "sv": 143506, "pe": 143507, "do": 143508, "ec": 143509, "eg": 143516,
    "kz": 143517, "ee": 143518, "lv": 143519, "lt": 143520, "ng": 143561,
}


def valid_country(code: Optional[str]) -> Optional[str]:
    """Lower-cased code if it is an ISO 3166 alpha-2 code ('uk' is accepted as 'gb'), else None."""
    value = (code or "").strip().lower()
    if value == "uk":
        value = "gb"
    return value if value in ISO_COUNTRIES else None


def parse_countries(text: Optional[str]) -> Tuple[List[str], List[str]]:
    """'us,gb, de' -> (['us', 'gb', 'de'], invalid codes)."""
    good: List[str] = []
    bad: List[str] = []
    for part in re.split(r"[,\s]+", text or ""):
        if not part:
            continue
        code = valid_country(part)
        if code and code not in good:
            good.append(code)
        elif not code:
            bad.append(part)
    return good, bad


def iso_day(value: Any) -> Optional[str]:
    """'2026-10-23T13:31:29Z' or a JS date string -> '2026-10-23'."""
    if not value:
        return None
    text = str(value).strip()
    match = re.match(r"(\d{4}-\d{2}-\d{2})", text)
    if match:
        return match.group(1)
    for pattern in ("%a %b %d %Y", "%b %d, %Y", "%d %b %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(" ".join(text.split()[:4]).rstrip(","), pattern).date().isoformat()
        except ValueError:
            continue
    try:
        return datetime.strptime(text, "%b %d, %Y").date().isoformat()
    except ValueError:
        return None


def days_between(earlier: Optional[str], later: date) -> Optional[int]:
    if not earlier:
        return None
    try:
        return (later - date.fromisoformat(earlier[:10])).days
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# App identifiers
# ---------------------------------------------------------------------------

_APP_ID_RE = re.compile(r"^(?:id)?(\d{6,12})$", re.I)
_APP_URL_RE = re.compile(r"apps\.apple\.com/(?:([a-z]{2})/)?(?:[a-z]+/)?app/(?:[^/?#]+/)?id(\d{6,12})", re.I)


def parse_app_ref(text: Optional[str]) -> Dict[str, Optional[str]]:
    """Classify an iOS app reference: {'kind': 'id'|'url'|'name', 'id', 'country', 'query'}."""
    value = (text or "").strip()
    match = _APP_ID_RE.match(value)
    if match:
        return {"kind": "id", "id": match.group(1), "country": None, "query": value}
    match = _APP_URL_RE.search(value)
    if match:
        return {"kind": "url", "id": match.group(2), "country": (match.group(1) or "").lower() or None,
                "query": value}
    return {"kind": "name", "id": None, "country": None, "query": value}


# ---------------------------------------------------------------------------
# Network (lazy imports; never raise)
# ---------------------------------------------------------------------------

LOOKUP_URL = "https://itunes.apple.com/lookup"
SEARCH_URL = "https://itunes.apple.com/search"
HINTS_URL = "https://search.itunes.apple.com/WebObjects/MZSearchHints.woa/wa/hints"
RSS_URL = "https://itunes.apple.com/{cc}/rss/customerreviews/page={page}/id={id}/sortby=mostrecent/json"
PAGE_URL = "https://apps.apple.com/{cc}/app/id{id}"
WEB_SEARCH_URL = "https://apps.apple.com/{cc}/iphone/search?term={term}"


def _http():
    from _growthkit import http  # noqa: WPS433 - lazy so text helpers need no requests
    return http


def fetch_with_retry(url: str, kind: str = "text", timeout: float = 15.0, session: Any = None,
                     headers: Optional[Dict[str, str]] = None, retries: int = 2,
                     backoff: float = 2.0, sleep=time.sleep) -> Dict[str, Any]:
    """http.fetch() plus up to `retries` retries on HTTP 403/429 (Apple throttling).

    The iTunes APIs allow roughly 20 calls a minute and answer 403 or 429
    when a client goes faster. This is throttling, not a bot wall, so a short
    wait and retry is the documented-by-behaviour fix.
    """
    http = _http()
    attempt = 0
    while True:
        result = http.fetch(url, kind=kind, timeout=timeout, session=session, headers=headers)
        code = result.get("http_status")
        if code in (403, 429) and attempt < retries:
            attempt += 1
            sleep(backoff * attempt)
            continue
        result["attempts"] = attempt + 1
        return result


def classify_failure(result: Dict[str, Any]) -> str:
    """'bad_request' (400), 'not_found' (404), 'throttled' (403/429), 'unreachable', 'http_error'."""
    code = result.get("http_status")
    if code == 400:
        return "bad_request"
    if code == 404:
        return "not_found"
    if code in (403, 429) or result.get("status") == "blocked":
        return "throttled"
    if code is None:
        return "unreachable"
    return "http_error"


def get_json(url: str, **kwargs: Any) -> Tuple[Optional[Any], Dict[str, Any], Optional[str]]:
    """(parsed JSON or None, fetch result, failure kind or None)."""
    result = fetch_with_retry(url, kind="text", **kwargs)
    if result.get("status") not in ("ok", "too_large"):
        return None, result, classify_failure(result)
    try:
        return json.loads(result.get("text") or ""), result, None
    except ValueError:
        return None, result, "bad_json"


def source_entry(name: str, result: Dict[str, Any], failure: Optional[str] = None) -> Dict[str, Any]:
    return {
        "name": name,
        "url": result.get("final_url") or result.get("url"),
        "status": "ok" if not failure else failure,
        "http_status": result.get("http_status"),
    }


def itunes_lookup(ids: List[str], country: str, **kwargs: Any) -> Tuple[List[Dict[str, Any]], Dict[str, Any], Optional[str]]:
    url = "%s?id=%s&country=%s&entity=software" % (LOOKUP_URL, ",".join(ids), country)
    data, result, failure = get_json(url, **kwargs)
    rows = [row for row in (data or {}).get("results", []) if row.get("wrapperType") == "software"
            or row.get("kind") in ("software", "mac-software")] if not failure else []
    return rows, result, failure


def itunes_search(term: str, country: str, limit: int = 15, **kwargs: Any) -> Tuple[List[Dict[str, Any]], Dict[str, Any], Optional[str]]:
    url = "%s?term=%s&country=%s&entity=software&limit=%d" % (SEARCH_URL, quote(term), country, limit)
    data, result, failure = get_json(url, **kwargs)
    return ((data or {}).get("results", []) if not failure else []), result, failure


_SSD_RE = re.compile(r'<script[^>]*id="serialized-server-data"[^>]*>(.*?)</script>', re.S)


def extract_server_data(html_text: Optional[str]) -> Optional[Dict[str, Any]]:
    """The page model apps.apple.com embeds as JSON, or None when missing or invalid."""
    match = _SSD_RE.search(html_text or "")
    if not match:
        return None
    try:
        data = json.loads(match.group(1))
    except ValueError:
        return None
    try:
        return data["data"][0]["data"]
    except (KeyError, IndexError, TypeError):
        return None


def store_page_data(url: str, **kwargs: Any) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any], Optional[str]]:
    """(page model, fetch result, failure). failure 'layout_changed' when the JSON is missing."""
    result = fetch_with_retry(url, kind="html", **kwargs)
    if result.get("status") not in ("ok", "too_large"):
        return None, result, classify_failure(result)
    model = extract_server_data(result.get("html"))
    if model is None:
        return None, result, "layout_changed"
    return model, result, None


# ---------------------------------------------------------------------------
# Parsers (pure; tested offline against saved fixtures)
# ---------------------------------------------------------------------------


def _artwork_url(artwork: Optional[Dict[str, Any]], width: int = 600) -> Optional[str]:
    """Fill an Apple artwork template ('.../{w}x{h}{c}.{f}') at a given width."""
    if not isinstance(artwork, dict):
        return None
    template = artwork.get("template")
    if not template:
        return None
    w = artwork.get("width") or width
    h = artwork.get("height") or width
    height = int(round(width * float(h) / float(w))) if w else width
    return (template.replace("{w}", str(width)).replace("{h}", str(height))
            .replace("{c}", "bb").replace("{f}", "jpg"))


def _shelf(model: Dict[str, Any], key: str) -> Dict[str, Any]:
    shelf = ((model or {}).get("shelfMapping") or {}).get(key)
    return shelf if isinstance(shelf, dict) else {}


def _items(model: Dict[str, Any], key: str) -> List[Dict[str, Any]]:
    return [item for item in (_shelf(model, key).get("items") or []) if isinstance(item, dict)]


def _lockup_summary(item: Dict[str, Any]) -> Dict[str, Any]:
    count = item.get("ratingCount")
    return {
        "id": str(item.get("adamId") or ""),
        "title": item.get("title"),
        "subtitle": item.get("subtitle") or item.get("developerTagline"),
        "developer": item.get("developerName"),
        "rating": item.get("rating"),
        "rating_count_label": count if isinstance(count, str) else None,
        "rating_count": parse_count_label(count),
        "editors_choice": bool(item.get("isEditorsChoice")),
    }


def parse_count_label(value: Any) -> Optional[int]:
    """'15K' -> 15000, '1.1M' -> 1100000, '761' -> 761, '' -> None. Labels are rounded by Apple."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return int(value)
    text = str(value or "").strip().replace(",", "")
    match = re.match(r"^(\d+(?:\.\d+)?)\s*([KkMm]?)$", text)
    if not match:
        return None
    number = float(match.group(1))
    factor = {"k": 1000, "m": 1000000}.get(match.group(2).lower(), 1)
    return int(round(number * factor))


def parse_product_page(model: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    """Facts from an apps.apple.com product page model. Returns (facts, parts that failed)."""
    facts: Dict[str, Any] = {}
    failed: List[str] = []

    def part(name: str, func) -> None:
        try:
            func()
        except Exception as exc:  # noqa: BLE001 - one broken shelf must not lose the rest
            failed.append("%s (%s)" % (name, type(exc).__name__))

    lockup = model.get("lockup") if isinstance(model.get("lockup"), dict) else {}

    def identity() -> None:
        facts["title"] = model.get("title") or lockup.get("title")
        facts["subtitle"] = lockup.get("subtitle") or lockup.get("developerTagline")
        facts["page_editors_choice_flag"] = bool(lockup.get("isEditorsChoice"))
        facts["icon_url"] = _artwork_url(lockup.get("icon"), 512)
        facts["canonical_url"] = model.get("canonicalURL")

    def ratings() -> None:
        items = _items(model, "productRatings")
        if items:
            item = items[0]
            counts = item.get("ratingCounts") or []
            facts["rating_average_display"] = item.get("ratingAverage")
            facts["rating_count_page"] = item.get("totalNumberOfRatings")
            if len(counts) == 5:
                facts["rating_histogram"] = {str(5 - index): int(value) for index, value in enumerate(counts)}

    def ribbon() -> None:
        badges = {}
        for item in _items(model, "informationRibbon"):
            key = item.get("key")
            if key:
                badges[key] = item
        facts["editors_choice"] = "editorsChoice" in badges
        chart = badges.get("chartPosition")
        if chart:
            content = chart.get("content") or {}
            position = content.get("position")
            facts["chart_position"] = {
                "category": chart.get("caption"),
                "position": int(position) if str(position or "").isdigit() else position,
            }
        else:
            facts["chart_position"] = None
        age = badges.get("contentRating")
        if age:
            facts["age_rating"] = (age.get("content") or {}).get("contentRating")

    def editorial() -> None:
        notes = None
        for item in _items(model, "editorsChoiceProductReviews"):
            review = item.get("review") or {}
            notes = review.get("notes") or notes
            if review.get("showsBadge"):
                facts["editors_choice"] = True
        facts["editors_notes"] = notes
        facts["featured_in"] = [
            {"heading": item.get("heading"), "title": item.get("title")}
            for item in _items(model, "featuredIn")
        ][:10]

    def information() -> None:
        for item in _items(model, "information"):
            title = item.get("title")
            if title == "In-App Purchases":
                facts["in_app_purchases"] = [
                    {"name": entry.get("leadingText"), "price": entry.get("trailingText")}
                    for entry in item.get("items") or []
                    if isinstance(entry, dict) and entry.get("$kind") == "textPair"
                ]
            elif title == "Languages":
                texts = []
                for entry in item.get("items") or []:
                    styled = ((entry.get("linkableText") or {}).get("styledText") or {}).get("rawText")
                    if styled:
                        texts.append(styled)
                facts["languages_text"] = texts[0] if texts else item.get("summary")
            elif title == "Size":
                facts["size_label"] = item.get("summary")
            elif title == "Category":
                facts["category_label"] = item.get("summary")
            elif title == "Age Rating" and not facts.get("age_rating"):
                facts["age_rating"] = item.get("summary")
        facts.setdefault("in_app_purchases", [])

    def media() -> None:
        screenshots: Dict[str, Any] = {}
        for key, label in (("product_media_phone_", "iphone"), ("product_media_pad_", "ipad"),
                           ("product_media_mac_", "mac"), ("product_media_watch_", "watch"),
                           ("product_media_tv_", "tv"), ("product_media_vision_", "vision")):
            items = _items(model, key)
            if not items:
                continue
            shots = [item.get("screenshot") for item in items if isinstance(item.get("screenshot"), dict)]
            videos = [item.get("video") for item in items if isinstance(item.get("video"), dict)]
            entry: Dict[str, Any] = {"count": len(shots), "preview_videos": len(videos)}
            if shots:
                first = shots[0]
                entry["width"] = first.get("width")
                entry["height"] = first.get("height")
                if first.get("width") and first.get("height"):
                    entry["orientation"] = "portrait" if first["height"] >= first["width"] else "landscape"
                entry["first_urls"] = [_artwork_url(shot, 600) for shot in shots[:3]]
            if videos:
                entry["first_video_poster"] = _artwork_url((videos[0] or {}).get("preview"), 600)
            platform = (_shelf(model, key).get("contentsMetadata") or {}).get("platform") or {}
            if platform.get("mediaType"):
                entry["media_type"] = platform.get("mediaType")
            screenshots[label] = entry
        facts["screenshots"] = screenshots

    def events() -> None:
        facts["in_app_events"] = [
            {
                "title": item.get("title"),
                "subtitle": item.get("subtitle"),
                "detail": item.get("detail"),
                "badge": item.get("kind"),
                "start": iso_day(item.get("startDate")),
                "end": iso_day(item.get("endDate")),
            }
            for item in _items(model, "appEvents")
        ][:10]

    def neighbours() -> None:
        facts["similar_apps"] = [_lockup_summary(item) for item in _items(model, "similarItems")][:15]
        facts["more_by_developer"] = [item.get("title") for item in _items(model, "moreByDeveloper")][:10]

    def version() -> None:
        items = _items(model, "mostRecentVersion")
        if items:
            item = items[0]
            facts["whats_new"] = {
                "text": item.get("text"),
                "version": (item.get("primarySubtitle") or "").replace("Version ", "") or None,
                "date": iso_day(item.get("secondarySubtitle")),
            }

    def description() -> None:
        items = _items(model, "description")
        if items:
            facts["description_page"] = ((items[0].get("paragraph") or {}).get("text"))

    for name, func in (("identity", identity), ("ratings", ratings), ("ribbon", ribbon),
                       ("editorial", editorial), ("information", information), ("media", media),
                       ("events", events), ("similar", neighbours), ("version", version),
                       ("description", description)):
        part(name, func)
    if not facts.get("title"):
        failed.append("identity (no title in page model)")
    return facts, failed


def parse_search_page(model: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Ranked app results of an apps.apple.com search page (editorial cards skipped).

    rank counts app results only (organic and in-app event results), in page
    order. Ads are not shown on the logged-out web page.
    """
    results: List[Dict[str, Any]] = []
    for shelf in model.get("shelves") or []:
        if not isinstance(shelf, dict) or shelf.get("contentType") != "searchResult":
            continue
        for item in shelf.get("items") or []:
            if not isinstance(item, dict):
                continue
            lockup = item.get("lockup")
            if not isinstance(lockup, dict) or not lockup.get("adamId"):
                continue
            entry = _lockup_summary(lockup)
            entry["rank"] = len(results) + 1
            entry["result_type"] = item.get("resultType")
            entry["has_app_event"] = item.get("$kind") == "AppEventSearchResult"
            entry["trailers"] = len(lockup.get("trailers") or [])
            results.append(entry)
    return results


def parse_hints(payload: Any) -> List[str]:
    """Suggestion terms from the MZSearchHints plist (bytes or str)."""
    if payload is None:
        return []
    raw = payload.encode("utf-8") if isinstance(payload, str) else payload
    try:
        data = plistlib.loads(raw)
    except Exception:  # noqa: BLE001 - plistlib raises several types on bad input
        return []
    hints = data.get("hints") if isinstance(data, dict) else None
    terms: List[str] = []
    for hint in hints or []:
        term = hint.get("term") if isinstance(hint, dict) else None
        if term and term not in terms:
            terms.append(term)
    return terms


def parse_reviews_rss(data: Any) -> List[Dict[str, Any]]:
    """Reviews from the customer-reviews RSS JSON (one page, up to 50)."""
    feed = (data or {}).get("feed") if isinstance(data, dict) else None
    entries = (feed or {}).get("entry") or []
    if isinstance(entries, dict):
        entries = [entries]
    reviews: List[Dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict) or "im:rating" not in entry:
            continue  # the first entry of old feeds described the app itself

        def label(key: str) -> Optional[str]:
            value = entry.get(key)
            return value.get("label") if isinstance(value, dict) else None

        try:
            rating = int(label("im:rating") or 0)
        except ValueError:
            rating = 0
        if not 1 <= rating <= 5:
            continue
        reviews.append({
            "id": label("id"),
            "rating": rating,
            "title": label("title") or "",
            "text": label("content") or "",
            "date": iso_day(label("updated")),
            "version": label("im:version"),
            "votes": int(label("im:voteCount") or 0) if (label("im:voteCount") or "0").isdigit() else 0,
        })
    return reviews


def rating_summary(ratings: List[int]) -> Dict[str, Any]:
    """Count, average and histogram of 1-5 star ratings."""
    histogram = {str(star): 0 for star in (5, 4, 3, 2, 1)}
    for rating in ratings:
        if 1 <= rating <= 5:
            histogram[str(rating)] += 1
    count = sum(histogram.values())
    average = round(sum(int(star) * n for star, n in histogram.items()) / float(count), 2) if count else None
    low = histogram["1"] + histogram["2"]
    return {
        "count": count,
        "average": average,
        "histogram": histogram,
        "share_1_2_star": round(low / float(count), 3) if count else None,
    }


def host_of(url: Optional[str]) -> str:
    try:
        return (urlparse(url or "").hostname or "").lower()
    except ValueError:
        return ""
