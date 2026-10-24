#!/usr/bin/env python3
"""iOS App Store facts pack for one app: listing, ratings, reviews, peers.

    python3 aso_fetch.py 1232780281 --country us --json
    python3 aso_fetch.py "https://apps.apple.com/us/app/notion/id1232780281" --json
    python3 aso_fetch.py "Notion" --peers 572688855,626144601 --countries gb,de --json

Sources (all free, no key):
    iTunes Lookup / Search API     identity, description, release notes,
                                   lifetime rating, languages, categories
    apps.apple.com product page    subtitle, rating histogram, Editors' Choice,
                                   chart position, in-app purchases, screenshots
                                   and preview videos, in-app events, similar apps
    customer reviews RSS           up to 500 most recent written reviews

The script only collects and counts. It gives no score: the model judges the
listing with references/scoring-rubric.md.

App selection: an ID or App Store URL is used as given. A name is searched,
and the best name match is taken only when it is clearly the one people mean
(exact, brand or prefix match with at least 10x the ratings of any other name
match). Otherwise the script exits 2 with a "candidates" list so the model can
confirm the app with the user.

Exit codes: 0 ok, 2 usage (bad country, no or ambiguous match, ID not in
that storefront), 3 Apple API unreachable or throttled, 4 partial (product
page, reviews, a peer or a storefront failed; see "errors" and "coverage").
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _growthkit import cli  # noqa: E402
import aso_common as ac  # noqa: E402

TOOL = "aso_fetch"
SCHEMA = "aso-facts/1"
MAX_REVIEW_PAGES = 10
MAX_PEERS = 6
MAX_COUNTRIES = 8
CONFIDENT_RATIO = 10.0

REVIEW_CAVEAT = (
    "Written reviews skew more negative than star-only ratings (most ratings come from the in-app "
    "prompt without text). Compare the recent written-review average with peers' recent written "
    "reviews (peers[].recent_reviews), not only with the lifetime rating."
)
NOT_VISIBLE = [
    "keyword field (private to the developer)",
    "promotional text (not exposed to the web page or API)",
    "impressions, product page views and conversion rate (App Store Connect only)",
    "search volume and keyword difficulty (no free source; Apple Ads popularity only if the user pastes it)",
    "custom product pages and their keyword assignments",
    "Product Page Optimization tests and results",
]


# ---------------------------------------------------------------------------
# App selection
# ---------------------------------------------------------------------------


def _norm(text: Optional[str]) -> str:
    return " ".join(ac.words(ac.normalize_dashes(text or "")))


def name_match(query: str, track_name: str) -> Optional[str]:
    """'exact', 'brand' or 'prefix' when track_name plausibly is the app called `query`."""
    q = _norm(query)
    name = _norm(track_name)
    if not q or not name:
        return None
    if name == q:
        return "exact"
    brand, _rest, _sep = ac.split_title(track_name)
    if brand and _norm(brand) == q:
        return "brand"
    if name.startswith(q + " "):
        return "prefix"
    return None


def candidate_row(row: Dict[str, Any], match: Optional[str] = None) -> Dict[str, Any]:
    return {
        "id": str(row.get("trackId")),
        "title": ac.normalize_dashes(row.get("trackName")),
        "developer": ac.normalize_dashes(row.get("artistName")),
        "rating_count": row.get("userRatingCount") or 0,
        "rating": round(float(row.get("averageUserRating") or 0), 2) or None,
        "url": (row.get("trackViewUrl") or "").split("?")[0],
        "name_match": match,
    }


def choose_app(query: str, rows: List[Dict[str, Any]]) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
    """Pick the app a name refers to. Returns (row or None, match info with candidates)."""
    scored = []
    for row in rows:
        kind = name_match(query, row.get("trackName") or "")
        if kind:
            scored.append((int(row.get("userRatingCount") or 0), kind, row))
    scored.sort(key=lambda item: -item[0])
    info: Dict[str, Any] = {
        "method": "name_search",
        "query": query,
        "candidates": [candidate_row(row, name_match(query, row.get("trackName") or "")) for row in rows[:8]],
    }
    if not scored:
        info["confidence"] = "no_match"
        info["reason"] = "No search result is named '%s' (exact, brand or prefix match)." % query
        return None, info
    top_count, top_kind, top = scored[0]
    if len(scored) > 1:
        second = scored[1][0]
        if second > 0 and top_count < CONFIDENT_RATIO * second:
            info["confidence"] = "ambiguous"
            info["reason"] = (
                "Several apps match '%s' with similar rating counts (%d vs %d); confirm which one."
                % (query, top_count, second))
            info["candidates"] = [candidate_row(row, kind) for _c, kind, row in scored[:8]]
            return None, info
    info["confidence"] = "high"
    info["matched_by"] = top_kind
    info["alternatives"] = [candidate_row(row, kind) for _c, kind, row in scored[1:4]]
    return top, info


# ---------------------------------------------------------------------------
# Facts assembly
# ---------------------------------------------------------------------------


def api_screenshots(row: Dict[str, Any]) -> Dict[str, Any]:
    shots: Dict[str, Any] = {}
    for key, label in (("screenshotUrls", "iphone"), ("ipadScreenshotUrls", "ipad"),
                       ("appletvScreenshotUrls", "tv")):
        urls = row.get(key) or []
        if urls:
            shots[label] = {"count": len(urls), "first_urls": urls[:3], "source": "itunes_api"}
    return shots


def app_facts(row: Dict[str, Any], page: Optional[Dict[str, Any]], today: date) -> Dict[str, Any]:
    """Merge the lookup row and the product page facts into one app record."""
    page = page or {}
    title = row.get("trackName") or page.get("title")
    brand, keyword_segment, separator = ac.split_title(title)
    subtitle = page.get("subtitle")
    description = row.get("description") or page.get("description_page") or ""
    current_date = ac.iso_day(row.get("currentVersionReleaseDate"))
    histogram = page.get("rating_histogram")
    histogram_total = sum(histogram.values()) if histogram else 0
    share_low = None
    if histogram_total:
        share_low = round((histogram.get("1", 0) + histogram.get("2", 0)) / float(histogram_total), 3)
    screenshots = page.get("screenshots") or api_screenshots(row)
    preview_videos = sum((entry or {}).get("preview_videos", 0) for entry in screenshots.values()) \
        if page.get("screenshots") else None
    release_notes = row.get("releaseNotes") or ((page.get("whats_new") or {}).get("text"))
    iap = page.get("in_app_purchases")
    facts = {
        "id": str(row.get("trackId")),
        "bundle_id": row.get("bundleId"),
        "url": (row.get("trackViewUrl") or page.get("canonical_url") or "").split("?")[0],
        "title": title,
        "title_length": len(title or ""),
        "brand_segment": brand,
        "keyword_segment": keyword_segment,
        "title_separator": separator,
        "subtitle": subtitle,
        "subtitle_length": len(subtitle) if subtitle else None,
        "developer": row.get("artistName"),
        "seller": row.get("sellerName"),
        "primary_category": row.get("primaryGenreName"),
        "categories": row.get("genres") or [],
        "price": row.get("price"),
        "formatted_price": row.get("formattedPrice"),
        "in_app_purchases": iap,
        "in_app_purchase_count": len(iap) if isinstance(iap, list) else None,
        "age_rating": page.get("age_rating") or row.get("trackContentRating"),
        "languages": row.get("languageCodesISO2A") or [],
        "languages_count": len(row.get("languageCodesISO2A") or []),
        "size_mb": round(int(row.get("fileSizeBytes") or 0) / 1048576.0, 1) if row.get("fileSizeBytes") else None,
        "minimum_os": row.get("minimumOsVersion"),
        "release_date": ac.iso_day(row.get("releaseDate")),
        "current_version": row.get("version"),
        "current_version_date": current_date,
        "days_since_update": ac.days_between(current_date, today),
        "release_notes": {"text": release_notes, "length": len(release_notes or "")},
        "description": dict(ac.description_facts(description), text=description),
        "ratings": {
            "average": round(float(row["averageUserRating"]), 2) if row.get("averageUserRating") else None,
            "count": row.get("userRatingCount"),
            "current_version_average": round(float(row["averageUserRatingForCurrentVersion"]), 2)
            if row.get("averageUserRatingForCurrentVersion") else None,
            "current_version_count": row.get("userRatingCountForCurrentVersion"),
            "histogram": histogram,
            "share_1_2_star": share_low,
        },
        "chart_position": page.get("chart_position"),
        "editors_choice": page.get("editors_choice") if page else None,
        "editors_notes": ac.first_chars(page.get("editors_notes"), 300) if page.get("editors_notes") else None,
        "featured_in": page.get("featured_in"),
        "screenshots": screenshots,
        "preview_videos": preview_videos,
        "icon_url": page.get("icon_url") or row.get("artworkUrl512"),
        "in_app_events": page.get("in_app_events"),
        "similar_apps": page.get("similar_apps"),
        "more_by_developer": page.get("more_by_developer"),
        "whats_new": page.get("whats_new"),
    }
    return facts


def review_facts(reviews: List[Dict[str, Any]], row: Dict[str, Any], today: date,
                 pages: int) -> Dict[str, Any]:
    ratings = [review["rating"] for review in reviews]
    recent = ac.rating_summary(ratings)
    last_30 = [review["rating"] for review in reviews
               if review.get("date") and (ac.days_between(review["date"], today) or 0) <= 30]
    lifetime = round(float(row["averageUserRating"]), 2) if row.get("averageUserRating") else None
    dates = sorted(review["date"] for review in reviews if review.get("date"))
    versions: Dict[str, List[int]] = {}
    for review in reviews:
        versions.setdefault(review.get("version") or "unknown", []).append(review["rating"])
    by_version = sorted(
        ({"version": key, "count": len(values), "average": round(sum(values) / float(len(values)), 2)}
         for key, values in versions.items()),
        key=lambda item: -item["count"])[:6]

    def sample(stars, limit):
        picked = [review for review in reviews if review["rating"] in stars][:limit]
        return [{"rating": review["rating"], "date": review["date"], "version": review.get("version"),
                 "title": ac.first_chars(review.get("title"), 80),
                 "excerpt": ac.first_chars((review.get("text") or "").replace("\n", " "), 220)}
                for review in picked]

    return {
        "source": "App Store customer reviews RSS, most recent first",
        "pages_fetched": pages,
        "count": recent["count"],
        "first_date": dates[0] if dates else None,
        "last_date": dates[-1] if dates else None,
        "span_days": ac.days_between(dates[0], date.fromisoformat(dates[-1])) if dates else None,
        "recent": recent,
        "last_30_days": ac.rating_summary(last_30),
        "lifetime_average": lifetime,
        "delta_recent_vs_lifetime": round(recent["average"] - lifetime, 2)
        if recent["average"] is not None and lifetime is not None else None,
        "by_version": by_version,
        "low_star_sample": sample((1, 2), 8),
        "high_star_sample": sample((5,), 3),
        "caveat": REVIEW_CAVEAT,
    }


def fetch_reviews(app_id: str, country: str, pages: int, timeout: float, session: Any,
                  sleep=time.sleep) -> Tuple[List[Dict[str, Any]], int, Optional[str], List[Dict[str, Any]]]:
    """Fetch up to `pages` RSS pages. Returns (reviews, pages fetched, failure, sources)."""
    reviews: List[Dict[str, Any]] = []
    sources: List[Dict[str, Any]] = []
    fetched = 0
    for page in range(1, pages + 1):
        url = ac.RSS_URL.format(cc=country, page=page, id=app_id)
        data, result, failure = ac.get_json(url, timeout=timeout, session=session)
        if page == 1:
            sources.append(ac.source_entry("customer reviews RSS", result, failure))
        if failure:
            if fetched == 0:
                return reviews, fetched, failure, sources
            break
        fetched += 1
        batch = ac.parse_reviews_rss(data)
        if not batch:
            break
        reviews.extend(batch)
        if len(batch) < 50:
            break
        sleep(0.5)
    return reviews, fetched, None, sources


def peer_facts(rows: List[Dict[str, Any]], country: str, today: date, timeout: float, session: Any,
               run: cli.Run, sleep=time.sleep) -> List[Dict[str, Any]]:
    peers = []
    for row in rows:
        app_id = str(row.get("trackId"))
        reviews, _pages, failure, _sources = fetch_reviews(app_id, country, 1, timeout, session, sleep)
        if failure:
            run.error("Recent reviews for peer %s (%s) could not be fetched: %s"
                      % (row.get("trackName"), app_id, failure))
        summary = ac.rating_summary([review["rating"] for review in reviews]) if not failure else None
        current_date = ac.iso_day(row.get("currentVersionReleaseDate"))
        peers.append({
            "id": app_id,
            "title": row.get("trackName"),
            "developer": row.get("artistName"),
            "primary_category": row.get("primaryGenreName"),
            "rating_average": round(float(row["averageUserRating"]), 2) if row.get("averageUserRating") else None,
            "rating_count": row.get("userRatingCount"),
            "days_since_update": ac.days_between(current_date, today),
            "screenshots_api": len(row.get("screenshotUrls") or []),
            "languages_count": len(row.get("languageCodesISO2A") or []),
            "recent_reviews": summary,
            "recent_reviews_window": "most recent page (up to 50 written reviews)",
        })
        sleep(0.5)
    return peers


def storefront_facts(app_id: str, countries: List[str], primary: Dict[str, Any], timeout: float,
                     session: Any, run: cli.Run, sleep=time.sleep) -> List[Dict[str, Any]]:
    out = []
    for code in countries:
        rows, result, failure = ac.itunes_lookup([app_id], code, timeout=timeout, session=session)
        entry: Dict[str, Any] = {"country": code, "status": "ok"}
        if failure or not rows:
            entry["status"] = failure or "not_available"
            if failure:
                run.error("Storefront %s lookup failed: %s" % (code, failure))
            else:
                run.note("App %s is not available in the %s storefront." % (app_id, code))
            out.append(entry)
            continue
        row = rows[0]
        entry.update({
            "title": ac.normalize_dashes(row.get("trackName")),
            "rating_average": round(float(row["averageUserRating"]), 2) if row.get("averageUserRating") else None,
            "rating_count": row.get("userRatingCount"),
        })
        model, page_result, page_failure = ac.store_page_data(
            ac.PAGE_URL.format(cc=code, id=app_id), timeout=timeout, session=session)
        if page_failure:
            entry["subtitle"] = None
            entry["page_status"] = page_failure
            run.error("Storefront %s product page failed: %s" % (code, page_failure))
        else:
            page, _failed = ac.parse_product_page(model)
            entry["subtitle"] = ac.normalize_dashes(page.get("subtitle"))
            entry["page_status"] = "ok"
        entry["title_differs_from_primary"] = entry.get("title") != primary.get("title")
        entry["subtitle_differs_from_primary"] = (
            entry.get("subtitle") != primary.get("subtitle") if entry.get("subtitle") is not None else None)
        entry["localized_metadata"] = bool(entry["title_differs_from_primary"] or entry["subtitle_differs_from_primary"])
        out.append(entry)
        sleep(0.5)
    return out


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------


def demo_payload(today: date) -> Dict[str, Any]:
    row = {
        "trackId": 0, "trackName": "FocusFlow: Pomodoro Timer", "artistName": "Demo Studio",
        "sellerName": "Demo Studio", "primaryGenreName": "Productivity", "genres": ["Productivity"],
        "price": 0, "formattedPrice": "Free", "averageUserRating": 4.6, "userRatingCount": 1200,
        "currentVersionReleaseDate": "2026-09-01T00:00:00Z", "releaseDate": "2024-01-10T00:00:00Z",
        "version": "3.2", "languageCodesISO2A": ["EN"], "trackViewUrl": "https://apps.apple.com/us/app/id0",
        "description": "FocusFlow helps you focus in 25-minute sessions.\n\n- Timer\n- Stats\n",
        "screenshotUrls": ["https://example.invalid/1.jpg", "https://example.invalid/2.jpg"],
    }
    page = {"subtitle": "Focus timer and task list", "editors_choice": False,
            "rating_histogram": {"5": 900, "4": 150, "3": 60, "2": 30, "1": 60}}
    reviews = [{"rating": 2, "title": "Sync broke", "text": "Lost my sessions after the update.",
                "date": "2026-09-20", "version": "3.2"},
               {"rating": 5, "title": "Love it", "text": "Simple and clean.", "date": "2026-09-18", "version": "3.2"}]
    return {
        "schema": SCHEMA, "platform": "ios", "country": "us", "fetched_on": today.isoformat(),
        "match": {"method": "demo", "query": None, "confidence": "demo"},
        "coverage": {"lookup_api": True, "product_page": True, "reviews_rss": True, "not_visible": NOT_VISIBLE},
        "sources": [],
        "app": app_facts(row, page, today),
        "reviews": review_facts(reviews, row, today, 1),
        "peers": [], "storefronts": [],
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = cli.build_parser(
        "Collect the iOS App Store facts for one app (no scoring).",
        input_help="App Store ID (1232780281 or id1232780281), App Store URL, or app name",
        prog="aso_fetch.py",
        epilog=__doc__.split("\n\n", 1)[1],
    )
    parser.add_argument("--country", default=None,
                        help="App Store storefront, ISO 3166 code (default: from the URL, else us)")
    parser.add_argument("--countries", default="",
                        help="extra storefronts to compare localized title and subtitle, e.g. gb,de,jp")
    parser.add_argument("--peers", default="",
                        help="comma-separated App Store IDs of competitors for rating momentum (max 6)")
    parser.add_argument("--reviews-pages", type=int, default=2, metavar="N",
                        help="customer-review RSS pages to read, 50 reviews each (0-10, default 2)")
    parser.add_argument("--reviews-out", metavar="PATH",
                        help="also save the fetched reviews as a JSON list (for review-sentiment)")
    parser.add_argument("--no-page", action="store_true",
                        help="skip the apps.apple.com product page (API data only)")
    parser.add_argument("--today", help=argparse.SUPPRESS)
    return parser


def run_main(argv: Optional[List[str]] = None, sleep=time.sleep) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    run = cli.Run(TOOL, args)
    try:
        today = date.fromisoformat(args.today) if args.today else date.today()
    except ValueError:
        return run.fail(cli.STATUS_USAGE, "--today must be YYYY-MM-DD")
    if args.demo:
        return run.emit(demo_payload(today), human=human_summary)
    if not args.input or not str(args.input).strip():
        return run.fail(cli.STATUS_USAGE, "Pass an App Store ID, App Store URL or app name.")
    if not 0 <= args.reviews_pages <= MAX_REVIEW_PAGES:
        return run.fail(cli.STATUS_USAGE, "--reviews-pages must be between 0 and %d" % MAX_REVIEW_PAGES)

    ref = ac.parse_app_ref(args.input)
    country_text = args.country or ref.get("country") or "us"
    country = ac.valid_country(country_text)
    if not country:
        return run.fail(cli.STATUS_USAGE, "'%s' is not an ISO 3166 country code (examples: us, gb, de, tr)."
                        % country_text)
    extra, bad = ac.parse_countries(args.countries)
    if bad:
        return run.fail(cli.STATUS_USAGE, "Not ISO 3166 country codes in --countries: %s" % ", ".join(bad))
    extra = [code for code in extra if code != country][:MAX_COUNTRIES]
    peer_ids = [part.strip().lower().replace("id", "") for part in args.peers.split(",") if part.strip()]
    if any(not part.isdigit() for part in peer_ids):
        return run.fail(cli.STATUS_USAGE, "--peers takes numeric App Store IDs, e.g. 572688855,626144601")
    peer_ids = peer_ids[:MAX_PEERS]

    timeout = args.timeout
    from _growthkit import http  # noqa: E402 - needs requests; imported after usage checks
    session = http.new_session()
    sources: List[Dict[str, Any]] = []

    # 1. Identify the app.
    if ref["kind"] in ("id", "url"):
        rows, result, failure = ac.itunes_lookup([ref["id"]], country, timeout=timeout, session=session)
        sources.append(ac.source_entry("iTunes Lookup API", result, failure))
        if failure == "bad_request":
            return run.fail(cli.STATUS_USAGE, "Apple rejected storefront '%s' (HTTP 400). Use a storefront "
                            "where the App Store operates." % country, {"sources": sources})
        if failure:
            return run.fail(cli.STATUS_UNREACHABLE, "iTunes Lookup API failed (%s, HTTP %s). Retry later; do "
                            "not score the app." % (failure, result.get("http_status")), {"sources": sources})
        if not rows:
            return run.fail(cli.STATUS_USAGE, "No app with ID %s in the '%s' storefront. Check the ID, or try "
                            "--country us." % (ref["id"], country), {"sources": sources})
        row = rows[0]
        match = {"method": ref["kind"], "query": ref["query"], "confidence": "exact_id"}
    else:
        rows, result, failure = ac.itunes_search(ref["query"], country, 15, timeout=timeout, session=session)
        sources.append(ac.source_entry("iTunes Search API", result, failure))
        if failure == "bad_request":
            return run.fail(cli.STATUS_USAGE, "Apple rejected storefront '%s' (HTTP 400)." % country,
                            {"sources": sources})
        if failure:
            return run.fail(cli.STATUS_UNREACHABLE, "iTunes Search API failed (%s, HTTP %s)."
                            % (failure, result.get("http_status")), {"sources": sources})
        row, match = choose_app(ref["query"], rows)
        if row is None:
            match["needs_confirmation"] = True
            return run.fail(cli.STATUS_USAGE, match.get("reason") or "No matching app.",
                            {"match": match, "candidates": match.get("candidates", []), "sources": sources})
        match["matched"] = candidate_row(row, match.get("matched_by"))
        # The search row lacks nothing we need, but a lookup keeps fields identical across paths.
        rows, result, failure = ac.itunes_lookup([str(row.get("trackId"))], country, timeout=timeout, session=session)
        sources.append(ac.source_entry("iTunes Lookup API", result, failure))
        if rows:
            row = rows[0]
    app_id = str(row.get("trackId"))

    # 2. Product page.
    page: Optional[Dict[str, Any]] = None
    coverage: Dict[str, Any] = {"lookup_api": True, "product_page": "skipped", "reviews_rss": "skipped"}
    if not args.no_page:
        page_url = ac.PAGE_URL.format(cc=country, id=app_id)
        model, result, failure = ac.store_page_data(page_url, timeout=timeout, session=session)
        sources.append(ac.source_entry("apps.apple.com product page", result, failure))
        if failure:
            coverage["product_page"] = False
            coverage["product_page_reason"] = failure
            run.error("Product page not read (%s): subtitle, rating histogram, screenshots detail, in-app "
                      "purchases, in-app events and similar apps are not measured." % failure)
        else:
            page, failed_parts = ac.parse_product_page(model)
            coverage["product_page"] = True
            if failed_parts:
                coverage["product_page_parts_failed"] = failed_parts
                run.error("Product page parts not parsed: %s" % ", ".join(failed_parts))

    # 3. Reviews.
    reviews_block = None
    if args.reviews_pages:
        reviews, pages, failure, review_sources = fetch_reviews(
            app_id, country, args.reviews_pages, timeout, session, sleep)
        sources.extend(review_sources)
        if failure:
            coverage["reviews_rss"] = False
            run.error("Customer reviews RSS failed (%s); recent rating trend not measured." % failure)
        else:
            coverage["reviews_rss"] = True
            if not reviews:
                run.note("The reviews RSS returned no written reviews for this storefront.")
            reviews_block = review_facts(reviews, row, today, pages)
            if args.reviews_out:
                saved = save_reviews(args.reviews_out, reviews, app_id, country)
                if saved:
                    run.error(saved)
                else:
                    run.note("Saved %d reviews to %s" % (len(reviews), args.reviews_out))

    app = app_facts(row, page, today)
    if page is None:
        app["subtitle"] = None
        run.note("Subtitle not measured: it is only on the product page.")

    # 4. Peers and storefronts.
    peers: List[Dict[str, Any]] = []
    if peer_ids:
        peer_rows, result, failure = ac.itunes_lookup(peer_ids, country, timeout=timeout, session=session)
        sources.append(ac.source_entry("iTunes Lookup API (peers)", result, failure))
        if failure:
            run.error("Peer lookup failed (%s); rating momentum vs peers not measured." % failure)
        else:
            missing = sorted(set(peer_ids) - {str(r.get("trackId")) for r in peer_rows})
            if missing:
                run.note("Peer IDs not found in the %s storefront: %s" % (country, ", ".join(missing)))
            peers = peer_facts(peer_rows, country, today, timeout, session, run, sleep)
    storefronts = storefront_facts(app_id, extra, app, timeout, session, run, sleep) if extra else []

    counter = [0]
    payload = ac.deep_normalize({
        "schema": SCHEMA,
        "platform": "ios",
        "country": country,
        "fetched_on": today.isoformat(),
        "match": match,
        "coverage": dict(coverage, not_visible=NOT_VISIBLE),
        "sources": sources,
        "app": app,
        "reviews": reviews_block,
        "peers": peers,
        "storefronts": storefronts,
    }, counter)
    if counter[0]:
        run.note("Replaced %d en or em dashes in store text with '-' (same length, counts unchanged)." % counter[0])
    return run.emit(payload, human=human_summary)


def save_reviews(path: str, reviews: List[Dict[str, Any]], app_id: str, country: str) -> Optional[str]:
    rows = [{"text": ((review.get("title") or "") + ". " + (review.get("text") or "")).strip(". "),
             "rating": review["rating"], "date": review.get("date"), "version": review.get("version"),
             "source": "app_store_%s_%s" % (country, app_id)} for review in reviews]
    try:
        directory = os.path.dirname(os.path.abspath(path))
        os.makedirs(directory, exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(cli.to_json(ac.deep_normalize(rows), compact=False) + "\n")
    except OSError as exc:
        return "Could not write --reviews-out %s: %s" % (path, exc)
    return None


def human_summary(envelope: Dict[str, Any]) -> str:
    app = envelope.get("app") or {}
    if not app:
        lines = ["Status: %s" % envelope.get("status")]
        for item in envelope.get("errors") or []:
            lines.append("Error: %s" % item)
        for cand in envelope.get("candidates") or []:
            lines.append("  candidate %s  %s  (%s, %s ratings)" % (
                cand.get("id"), cand.get("title"), cand.get("developer"), cand.get("rating_count")))
        return "\n".join(lines)
    ratings = app.get("ratings") or {}
    reviews = envelope.get("reviews") or {}
    lines = [
        "%s (id %s, %s storefront)" % (app.get("title"), app.get("id"), envelope.get("country")),
        "  subtitle: %s" % app.get("subtitle"),
        "  developer: %s | category: %s" % (app.get("developer"), app.get("primary_category")),
        "  rating: %s from %s ratings | days since update: %s" % (
            ratings.get("average"), ratings.get("count"), app.get("days_since_update")),
    ]
    if reviews:
        lines.append("  recent written reviews: %s avg over %s (lifetime %s)" % (
            (reviews.get("recent") or {}).get("average"), reviews.get("count"), reviews.get("lifetime_average")))
    shots = app.get("screenshots") or {}
    lines.append("  screenshots: %s" % ", ".join("%s %s" % (k, (v or {}).get("count")) for k, v in shots.items()))
    lines.append("Status: %s" % envelope.get("status"))
    return "\n".join(lines)


def main() -> int:
    return run_main()


if __name__ == "__main__":
    sys.exit(main())
