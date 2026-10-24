#!/usr/bin/env python3
"""Google Play facts pack for one app (same schema as aso_fetch.py).

    python3 play_fetch.py notion.id --json
    python3 play_fetch.py "https://play.google.com/store/apps/details?id=com.todoist" --lang en --country us --json
    python3 play_fetch.py com.todoist --ios ios_facts.json --json

Reads the public play.google.com listing page (no key): title, short
description, full description, developer, category, content rating, rating,
rating histogram, review and download labels, last update, screenshots,
trailer, "What's new" and similar apps. With --ios (the JSON that
aso_fetch.py saved with --out) it adds a cross-store comparison.

The script only collects and counts; the model judges.

Exit codes: 0 ok, 2 usage, or the Play page layout changed (paste the listing
into a JSON file and run metadata_validator.py instead), 3 page unreachable,
blocked, or no listing for that package (HTTP 404), 4 partial (some fields
missing; see "missing").
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _growthkit import cli  # noqa: E402
import aso_common as ac  # noqa: E402

TOOL = "play_fetch"
SCHEMA = "aso-facts/1"
PLAY_URL = "https://play.google.com/store/apps/details?id={pkg}&hl={hl}&gl={gl}"
PACKAGE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+$")
LAYOUT_MESSAGE = (
    "The Google Play page layout changed and the listing could not be read. Paste the listing "
    "(title, short_description, description) into a JSON file and run metadata_validator.py on it."
)
NOT_VISIBLE = [
    "store listing visitors, acquisitions and conversion rate (Play Console only)",
    "custom store listings and their keyword targeting (Play Console only)",
    "store listing experiment results (Play Console only)",
    "search volume and keyword difficulty (no free source)",
]


def parse_package(text: Optional[str]) -> Optional[str]:
    """'notion.id' or a play.google.com details URL -> package name, else None."""
    value = (text or "").strip()
    if not value:
        return None
    if "play.google.com" in value:
        try:
            query = parse_qs(urlparse(value if "://" in value else "https://" + value).query)
        except ValueError:
            return None
        package = (query.get("id") or [None])[0]
        return package if package and PACKAGE_RE.match(package) else None
    return value if PACKAGE_RE.match(value) else None


def _text_after_label(soup: Any, label: str) -> Optional[str]:
    """Text of the element right after a small label element ('Updated on' -> 'Oct 19, 2026')."""
    for node in soup.find_all(string=re.compile(r"^\s*%s\s*$" % re.escape(label))):
        parent = node.parent
        sibling = parent.find_next_sibling() if parent is not None else None
        if sibling is not None and sibling.get_text(strip=True):
            return sibling.get_text(" ", strip=True)
    return None


def _text_before_label(soup: Any, label: str) -> Optional[str]:
    """Text of the element right before a label ('10M+' before 'Downloads')."""
    for node in soup.find_all(string=re.compile(r"^\s*%s\s*$" % re.escape(label))):
        parent = node.parent
        sibling = parent.find_previous_sibling() if parent is not None else None
        if sibling is not None and sibling.get_text(strip=True):
            return sibling.get_text(" ", strip=True)
    return None


def _section_by_heading(soup: Any, heading_re: str) -> Any:
    for heading in soup.find_all(["h2", "h3"]):
        if re.search(heading_re, heading.get_text(" ", strip=True), re.I):
            section = heading.find_parent("section")
            return section if section is not None else heading.parent
    return None


def _multiline(node: Any) -> str:
    """Element text with <br> as newlines and no other separators added."""
    if node is None:
        return ""
    for br in node.find_all("br"):
        br.replace_with("\n")
    text = node.get_text("")
    return "\n".join(line.rstrip() for line in text.replace("\r", "").split("\n")).strip()


def parse_play_page(html_text: str, package: str, today: date) -> Dict[str, Any]:
    """Facts from a Google Play details page. Missing fields are listed in 'missing'."""
    from _growthkit import html as gk_html  # needs beautifulsoup4

    soup = gk_html.parse(html_text)
    missing: List[str] = []
    ld = gk_html.extract_json_ld(soup)
    app_ld = next((item for item in ld.get("items") or []
                   if "SoftwareApplication" in (item.get("@type") if isinstance(item.get("@type"), list)
                                                else [item.get("@type")])), {}) or {}
    name_node = soup.find(attrs={"itemprop": "name"})
    title = app_ld.get("name") or (name_node.get_text(" ", strip=True) if name_node else None)
    short = app_ld.get("description")
    if not short:
        meta = soup.find("meta", attrs={"property": "og:description"})
        short = meta.get("content") if meta else None
    description = _multiline(soup.find(attrs={"data-g-id": "description"}))
    rating = (app_ld.get("aggregateRating") or {}) if isinstance(app_ld.get("aggregateRating"), dict) else {}
    author = app_ld.get("author") if isinstance(app_ld.get("author"), dict) else {}
    offers = app_ld.get("offers")
    offer = offers[0] if isinstance(offers, list) and offers else (offers if isinstance(offers, dict) else {})

    histogram: Dict[str, int] = {}
    for node in soup.find_all(attrs={"aria-label": re.compile(r"reviews for star rating \d")}):
        match = re.match(r"([\d,]+) reviews for star rating (\d)", node.get("aria-label") or "")
        if match and match.group(2) not in histogram:
            histogram[match.group(2)] = int(match.group(1).replace(",", ""))
    histogram_total = sum(histogram.values())

    shots = soup.find_all("img", attrs={"alt": "Screenshot image"})
    shot_urls = []
    for img in shots:
        src = img.get("src")
        if src and src not in shot_urls:
            shot_urls.append(src)
    trailers = soup.find_all(attrs={"data-trailer-url": True})

    whats_new = None
    section = _section_by_heading(soup, r"^what.s new$")
    if section is not None:
        node = section.find(attrs={"itemprop": "description"})
        whats_new = _multiline(node) if node is not None else None

    similar: List[Dict[str, Any]] = []
    section = _section_by_heading(soup, r"^similar (?:apps|games)$")
    if section is not None:
        for link in section.find_all("a", href=re.compile(r"/store/apps/details\?id=")):
            pkg = parse_qs(urlparse(link.get("href")).query).get("id", [None])[0]
            if not pkg or pkg == package or any(item["id"] == pkg for item in similar):
                continue
            parts = [part.strip() for part in link.get_text("|").split("|") if part.strip()]
            parts = [part for part in parts if part not in ("star",)]
            rating_value = next((part for part in parts if re.match(r"^\d\.\d$", part)), None)
            similar.append({
                "id": pkg,
                "title": parts[0] if parts else None,
                "developer": parts[1] if len(parts) > 1 and parts[1] != rating_value else None,
                "rating": float(rating_value) if rating_value else None,
            })

    updated_label = _text_after_label(soup, "Updated on")
    updated = ac.iso_day(updated_label)
    header_text = " ".join(span.get_text(" ", strip=True) for span in soup.find_all("span")[:400])
    brand, keyword_segment, separator = ac.split_title(title)

    def number(value: Any) -> Optional[float]:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    average = number(rating.get("ratingValue"))
    count = number(rating.get("ratingCount"))
    facts = {
        "id": package,
        "url": PLAY_URL.split("&")[0].format(pkg=package),
        "title": title,
        "title_length": len(title or ""),
        "brand_segment": brand,
        "keyword_segment": keyword_segment,
        "title_separator": separator,
        "short_description": short,
        "short_description_length": len(short) if short else None,
        "description": dict(ac.description_facts(description, 250), text=description),
        "developer": author.get("name"),
        "primary_category": app_ld.get("applicationCategory"),
        "content_rating": app_ld.get("contentRating"),
        "price": number(offer.get("price")) if isinstance(offer, dict) else None,
        "contains_ads": "Contains ads" in header_text,
        "in_app_purchases": "In-app purchases" in header_text,
        "downloads_label": _text_before_label(soup, "Downloads"),
        "updated_label": updated_label,
        "current_version_date": updated,
        "days_since_update": ac.days_between(updated, today),
        "ratings": {
            "average": round(average, 2) if average is not None else None,
            "count": int(count) if count is not None else None,
            "histogram": histogram or None,
            "histogram_note": "Play shows the histogram for the device type selected on the page (phone by default)."
            if histogram else None,
            "share_1_2_star": round((histogram.get("1", 0) + histogram.get("2", 0)) / float(histogram_total), 3)
            if histogram_total else None,
        },
        "screenshots": {"all_devices": {"count": len(shot_urls), "first_urls": shot_urls[:3],
                                        "note": "Play lists screenshots of every device type in one strip"}},
        "preview_videos": len(trailers),
        "icon_url": app_ld.get("image"),
        "whats_new": {"text": whats_new} if whats_new else None,
        "similar_apps": similar[:12],
    }
    for key in ("title", "short_description", "developer"):
        if not facts.get(key):
            missing.append(key)
    if not description:
        missing.append("description")
    if average is None:
        missing.append("ratings.average")
    if not updated:
        missing.append("current_version_date")
    facts["missing"] = missing
    return facts


def cross_store(ios: Dict[str, Any], play: Dict[str, Any]) -> Dict[str, Any]:
    """Deterministic iOS vs Play comparison of indexed text and signals."""
    ios_app = ios.get("app") or {}
    ios_words = set(ac.content_words("%s %s" % (ios_app.get("title") or "", ios_app.get("subtitle") or "")))
    play_words = set(ac.content_words("%s %s" % (play.get("title") or "", play.get("short_description") or "")))
    ios_r = ios_app.get("ratings") or {}
    play_r = play.get("ratings") or {}
    return {
        "ios_id": ios_app.get("id"),
        "same_title": (ios_app.get("title") or "").strip().lower() == (play.get("title") or "").strip().lower(),
        "ios_title": ios_app.get("title"),
        "play_title": play.get("title"),
        "ios_subtitle": ios_app.get("subtitle"),
        "play_short_description": play.get("short_description"),
        "words_only_ios": sorted(ios_words - play_words),
        "words_only_play": sorted(play_words - ios_words),
        "words_shared": sorted(ios_words & play_words),
        "rating_ios": ios_r.get("average"),
        "rating_play": play_r.get("average"),
        "rating_count_ios": ios_r.get("count"),
        "rating_count_play": play_r.get("count"),
        "days_since_update_ios": ios_app.get("days_since_update"),
        "days_since_update_play": play.get("days_since_update"),
        "note": "Words are from title plus subtitle (iOS) and title plus short description (Play).",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = cli.build_parser(
        "Collect the Google Play listing facts for one app (no scoring).",
        input_help="package name (com.example.app) or play.google.com details URL",
        prog="play_fetch.py",
        epilog=__doc__.split("\n\n", 1)[1],
    )
    parser.add_argument("--lang", default="en", help="listing language, the hl parameter (default en)")
    parser.add_argument("--country", default="us", help="country, the gl parameter (default us)")
    parser.add_argument("--ios", metavar="PATH", help="aso_fetch.py JSON for the same app (cross-store check)")
    parser.add_argument("--html", metavar="PATH",
                        help="parse a saved Play page instead of fetching (from a browser render)")
    parser.add_argument("--today", help=argparse.SUPPRESS)
    return parser


def run_main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    run = cli.Run(TOOL, args)
    try:
        today = date.fromisoformat(args.today) if args.today else date.today()
    except ValueError:
        return run.fail(cli.STATUS_USAGE, "--today must be YYYY-MM-DD")
    if args.demo:
        return run.fail(cli.STATUS_USAGE, "play_fetch.py has no demo; pass a package name such as notion.id.")
    package = parse_package(args.input)
    if not package:
        return run.fail(cli.STATUS_USAGE, "Pass a package name (com.example.app) or a play.google.com "
                        "details URL; got %r." % (args.input,))
    country = ac.valid_country(args.country)
    if not country:
        return run.fail(cli.STATUS_USAGE, "'%s' is not an ISO 3166 country code." % args.country)
    lang = (args.lang or "en").strip()
    if not re.match(r"^[A-Za-z]{2,3}(?:[-_][A-Za-z0-9]{2,4})?$", lang):
        return run.fail(cli.STATUS_USAGE, "--lang must look like en, de or pt_BR; got %r." % lang)
    ios = None
    if args.ios:
        try:
            with open(args.ios, encoding="utf-8") as handle:
                ios = json.load(handle)
        except (OSError, ValueError) as exc:
            return run.fail(cli.STATUS_USAGE, "Cannot read --ios %s: %s" % (args.ios, exc))
        if not isinstance(ios, dict) or ios.get("platform") != "ios" or not ios.get("app"):
            return run.fail(cli.STATUS_USAGE, "--ios must be the JSON saved by aso_fetch.py --out.")

    url = PLAY_URL.format(pkg=package, hl=lang, gl=country.upper())
    sources: List[Dict[str, Any]] = []
    if args.html:
        try:
            with open(args.html, encoding="utf-8", errors="replace") as handle:
                html_text = handle.read()
        except OSError as exc:
            return run.fail(cli.STATUS_USAGE, "Cannot read --html %s: %s" % (args.html, exc))
        sources.append({"name": "saved Google Play page", "url": args.html, "status": "ok", "http_status": None})
    else:
        result = ac.fetch_with_retry(url, kind="html", timeout=args.timeout, retries=1)
        failure = None if result.get("status") in ("ok", "too_large") else ac.classify_failure(result)
        sources.append(ac.source_entry("play.google.com listing", result, failure))
        if failure == "not_found":
            return run.fail(cli.STATUS_UNREACHABLE, "No Google Play listing for '%s' (HTTP 404) in %s/%s. Check "
                            "the package name, or the app may not be available in that country."
                            % (package, lang, country), {"sources": sources})
        if failure:
            status = cli.STATUS_BLOCKED if failure == "throttled" else cli.STATUS_UNREACHABLE
            return run.fail(status, "Google Play page failed (%s, HTTP %s): %s" % (
                failure, result.get("http_status"), result.get("error")), {"sources": sources})
        html_text = result.get("html") or ""
    facts = parse_play_page(html_text, package, today)
    if not facts.get("title") and not facts.get("short_description"):
        return run.fail(cli.STATUS_USAGE, LAYOUT_MESSAGE, {"sources": sources, "layout_changed": True})
    missing = facts.pop("missing")
    if missing:
        run.error("Fields not found on the Play page (not measured): %s" % ", ".join(missing))
    counter = [0]
    payload = ac.deep_normalize({
        "schema": SCHEMA,
        "platform": "android",
        "country": country,
        "language": lang,
        "fetched_on": today.isoformat(),
        "match": {"method": "package", "query": args.input, "confidence": "exact_id"},
        "coverage": {"listing_page": True, "missing": missing, "not_visible": NOT_VISIBLE},
        "sources": sources,
        "app": facts,
        "cross_store": cross_store(ios, facts) if ios else None,
    }, counter)
    if counter[0]:
        run.note("Replaced %d en or em dashes in store text with '-' (same length, counts unchanged)." % counter[0])
    return run.emit(payload, human=human_summary)


def human_summary(envelope: Dict[str, Any]) -> str:
    app = envelope.get("app") or {}
    if not app:
        return "Status: %s\n%s" % (envelope.get("status"), "\n".join(envelope.get("errors") or []))
    ratings = app.get("ratings") or {}
    return "\n".join([
        "%s (%s, %s/%s)" % (app.get("title"), app.get("id"), envelope.get("language"), envelope.get("country")),
        "  short description: %s" % app.get("short_description"),
        "  rating: %s from %s | downloads: %s | updated: %s" % (
            ratings.get("average"), ratings.get("count"), app.get("downloads_label"), app.get("current_version_date")),
        "  screenshots: %s | trailer: %s" % (
            (app.get("screenshots") or {}).get("all_devices", {}).get("count"), app.get("preview_videos")),
        "Status: %s" % envelope.get("status"),
    ])


def main() -> int:
    return run_main()


if __name__ == "__main__":
    sys.exit(main())
