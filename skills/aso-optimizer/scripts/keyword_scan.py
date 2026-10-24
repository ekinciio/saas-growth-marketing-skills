#!/usr/bin/env python3
"""Free App Store keyword intelligence: autocomplete, live rank, competitor term matrix.

    python3 keyword_scan.py 1232780281 --seeds "note taking,task manager,project planner" --json
    python3 keyword_scan.py --seeds "habit tracker" --country gb --json
    python3 keyword_scan.py 1232780281 --seeds "notes" --competitors 572688855 --keywords "wiki,docs" --json

For each seed term (3-5 work best):
  1. Apple's search autocomplete (the hints endpoint the App Store uses)
     returns the suggestions people see while typing. A term that shows up
     there is searched often enough for Apple to suggest it; the order is
     Apple's. No search volume number exists in free data.
  2. The logged-out apps.apple.com iPhone search page for the seed and the
     top suggestions gives the ranked results (about 10-12 apps) with their
     titles and subtitles, and the target app's position when it is listed.
Then it builds the competitor set (apps found in those results, the target's
"You Might Also Like" shelf and any --competitors) and a term matrix: for each
word in competitor titles and subtitles, how many competitors use it and
whether the target's title, subtitle or keyword field (--keywords) has it.
"gaps" lists words that at least --min-competitors competitors use and the
target lacks. The model decides which gaps fit the product.

Optional --popularity PATH reads a CSV of Apple Ads popularity scores the
user copied from their Apple Ads account (columns: keyword, popularity).

Exit codes: 0 ok, 2 usage, 3 every Apple request failed (unreachable or
throttled), 4 partial (some terms failed; see "errors").
"""

from __future__ import annotations

import argparse
import csv
import io
import os
import sys
import time
from datetime import date
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _growthkit import cli  # noqa: E402
import aso_common as ac  # noqa: E402

TOOL = "keyword_scan"
MAX_SEEDS = 8
RANK_NOTE = (
    "Ranks are positions among app results on the logged-out apps.apple.com iPhone search page for "
    "this storefront (about 10-12 results). On-device search is personalized, shows more results and "
    "can show ads, so treat a rank as a free proxy, not the exact on-device position."
)
SUGGESTION_NOTE = (
    "Autocomplete suggestions are Apple's, in Apple's order. Appearing there means people search the "
    "term; it is not a volume number."
)


# ---------------------------------------------------------------------------
# Pure helpers (tested offline)
# ---------------------------------------------------------------------------


def parse_seeds(text: Optional[str]) -> Tuple[List[str], List[str]]:
    seeds: List[str] = []
    problems: List[str] = []
    for part in (text or "").split(","):
        term = " ".join(part.strip().lower().split())
        if not term:
            continue
        if len(term) > 60:
            problems.append("seed longer than 60 characters: %r" % term[:40])
            continue
        if term not in seeds:
            seeds.append(term)
    return seeds, problems


def pick_terms(seeds: List[str], suggestions: Dict[str, List[str]], per_seed: int, max_terms: int) -> List[Dict[str, str]]:
    """Seeds first, then the top suggestions of each seed, up to max_terms."""
    terms: List[Dict[str, str]] = [{"term": seed, "source": "seed"} for seed in seeds]
    chosen = {seed for seed in seeds}
    for seed in seeds:
        added = 0
        for suggestion in suggestions.get(seed) or []:
            key = suggestion.lower().strip()
            if added >= per_seed or len(terms) >= max_terms:
                break
            if key in chosen:
                continue
            chosen.add(key)
            terms.append({"term": key, "source": "autocomplete:%s" % seed})
            added += 1
    return terms[:max(max_terms, len(seeds))]


def brand_words(apps: List[Dict[str, Any]]) -> set:
    """Words that name a competitor brand.

    Candidates: the title part before ':' or ' - ' ("Todoist: To Do List" ->
    todoist) and a first title word that is also the first word of the
    developer name ("Microsoft To Do" by Microsoft Corporation -> microsoft).
    A candidate that any competitor uses outside its brand part (in a
    keyword segment or a subtitle) is a normal word, not a brand: "do" in
    "Any.do" stays a keyword because "To Do List" uses it.
    """
    candidates = set()
    plain = set()
    for app in apps:
        title = app.get("title") or ""
        brand, rest, _sep = ac.split_title(title)
        title_words = ac.words(title)
        developer_words = ac.words(app.get("developer"))
        dev_brand = title_words[0] if title_words and developer_words and title_words[0] == developer_words[0] else None
        if rest and brand:
            candidates.update(ac.content_words(brand))
            plain.update(ac.words(rest))
        else:
            plain.update(word for word in title_words if word != dev_brand)
        if dev_brand:
            candidates.add(dev_brand)
        plain.update(ac.words(app.get("subtitle")))
    return {word for word in candidates if word not in plain and ac.singular(word) not in plain}


def term_matrix(competitors: List[Dict[str, Any]], target: Dict[str, Any],
                keyword_field: List[str], min_competitors: int) -> Dict[str, Any]:
    """Word and two-word counts over competitor titles and subtitles, with target coverage."""
    target_title = set(ac.words(target.get("title")))
    target_subtitle = set(ac.words(target.get("subtitle")))
    target_keywords = set()
    for term in keyword_field:
        target_keywords.update(ac.words(term))
    target_all = target_title | target_subtitle | target_keywords
    target_singular = {ac.singular(word) for word in target_all}
    brands = {word for word in brand_words(competitors)
              if word not in target_all and ac.singular(word) not in target_singular}

    # Grouped by singular form, so "list" and "lists" count as one term; the
    # term shown is the form competitors use most.
    words: Dict[str, Dict[str, Any]] = {}
    pairs: Dict[str, Dict[str, Any]] = {}

    def add(bucket: Dict[str, Dict[str, Any]], key: str, surface: str, text: str) -> None:
        entry = bucket.setdefault(key, {"term": surface, "competitors_using": 0, "examples": [], "_forms": {}})
        entry["competitors_using"] += 1
        entry["_forms"][surface] = entry["_forms"].get(surface, 0) + 1
        if len(entry["examples"]) < 2:
            entry["examples"].append(text)

    for comp in competitors:
        text = ("%s | %s" % (comp.get("title") or "", comp.get("subtitle") or "")).strip(" |")
        seen_words: Dict[str, str] = {}
        seen_pairs: Dict[str, str] = {}
        for field in (comp.get("title") or "", comp.get("subtitle") or ""):
            tokens = ac.words(field)
            for word in tokens:
                if word in ac.FILLER_WORDS or word in ac.GENERIC_WORDS or word.isdigit():
                    continue
                seen_words.setdefault(ac.singular(word), word)
            for first, second in zip(tokens, tokens[1:]):
                if first in ac.FILLER_WORDS and second in ac.FILLER_WORDS:
                    continue
                if first.isdigit() or second.isdigit():
                    continue
                seen_pairs.setdefault("%s %s" % (ac.singular(first), ac.singular(second)), "%s %s" % (first, second))
        for key, surface in seen_words.items():
            add(words, key, surface, text)
        for key, surface in seen_pairs.items():
            add(pairs, key, surface, text)
    for bucket in (words, pairs):
        for entry in bucket.values():
            forms = entry.pop("_forms")
            entry["term"] = sorted(forms.items(), key=lambda item: (-item[1], item[0]))[0][0]
            if len(forms) > 1:
                entry["forms"] = sorted(forms)

    def coverage(entry: Dict[str, Any]) -> Dict[str, Any]:
        tokens = entry["term"].split()
        fields = []
        for name, bag in (("title", target_title), ("subtitle", target_subtitle), ("keywords", target_keywords)):
            if all(token in bag or ac.singular(token) in {ac.singular(w) for w in bag} for token in tokens):
                fields.append(name)
        entry["in_target"] = fields
        entry["in_target_any_field"] = all(
            token in target_all or ac.singular(token) in target_singular for token in tokens)
        entry["competitor_brand"] = any(token in brands for token in tokens)
        entry["share"] = round(entry["competitors_using"] / float(len(competitors)), 2) if competitors else None
        return entry

    word_rows = sorted((coverage(e) for e in words.values()), key=lambda e: (-e["competitors_using"], e["term"]))
    pair_rows = sorted((coverage(e) for e in pairs.values() if e["competitors_using"] >= 2),
                       key=lambda e: (-e["competitors_using"], e["term"]))
    gaps = [row for row in word_rows + pair_rows
            if row["competitors_using"] >= min_competitors and not row["in_target_any_field"]
            and not row["competitor_brand"]]
    gap_rows = [{"term": row["term"], "competitors_using": row["competitors_using"], "share": row["share"],
                 "example": row["examples"][0] if row["examples"] else None}
                for row in sorted(gaps, key=lambda e: (-e["competitors_using"], e["term"]))[:30]]
    return {
        "competitor_count": len(competitors),
        "words": word_rows[:40],
        "phrases": pair_rows[:20],
        "gaps": gap_rows,
        "min_competitors": min_competitors,
        "note": "Counts use competitor titles and subtitles only (the parts Apple indexes that are public). "
                "Words already in the target's title, subtitle or --keywords count as covered, singular "
                "and plural alike.",
    }


def read_popularity(path: str) -> Dict[str, float]:
    """CSV with a keyword column and a popularity column (Apple Ads 5-100 scale)."""
    with open(path, "rb") as handle:
        raw = handle.read()
    text = raw.decode("utf-16") if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else raw.decode("utf-8-sig", "replace")
    sample = text[:2000]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.reader(io.StringIO(text), dialect)
    rows = [row for row in reader if any(cell.strip() for cell in row)]
    if not rows:
        raise ValueError("the popularity file is empty")
    header = [cell.strip().lower() for cell in rows[0]]
    term_col = next((i for i, h in enumerate(header) if h in ("keyword", "keywords", "term", "search term")), None)
    pop_col = next((i for i, h in enumerate(header) if "popularity" in h or h in ("score", "volume")), None)
    if term_col is None or pop_col is None:
        raise ValueError("expected a header with 'keyword' and 'popularity' columns, got %s" % rows[0])
    out: Dict[str, float] = {}
    for row in rows[1:]:
        if len(row) <= max(term_col, pop_col):
            continue
        number = cli.to_number(row[pop_col].strip() or None)
        if number is not None:
            out[" ".join(row[term_col].lower().split())] = number
    return out


# ---------------------------------------------------------------------------
# Network
# ---------------------------------------------------------------------------


def fetch_hints(term: str, country: str, timeout: float, session: Any) -> Tuple[List[str], Optional[str]]:
    storefront = ac.STOREFRONT_IDS.get(country)
    if storefront is None:
        return [], "no_storefront_id"
    url = "%s?clientApplication=Software&term=%s" % (ac.HINTS_URL, quote(term))
    result = ac.fetch_with_retry(url, kind="xml", timeout=timeout, session=session,
                                 headers={"X-Apple-Store-Front": "%d-1,29" % storefront})
    if result.get("status") not in ("ok", "too_large"):
        return [], ac.classify_failure(result)
    return ac.parse_hints(result.get("text")), None


def fetch_ranked(term: str, country: str, timeout: float, session: Any) -> Tuple[List[Dict[str, Any]], Optional[str], str]:
    url = ac.WEB_SEARCH_URL.format(cc=country, term=quote(term))
    model, result, failure = ac.store_page_data(url, timeout=timeout, session=session)
    if failure:
        return [], failure, url
    return ac.parse_search_page(model), None, url


def build_parser() -> argparse.ArgumentParser:
    parser = cli.build_parser(
        "Free App Store keyword signals: autocomplete, live rank and competitor term matrix.",
        input_help="optional target app: App Store ID or URL (run aso_fetch.py first for a name)",
        prog="keyword_scan.py",
        epilog=__doc__.split("\n\n", 1)[1],
        demo=False,
    )
    parser.add_argument("--seeds", required=True, help="comma-separated seed terms, 1-8 (3-5 work best)")
    parser.add_argument("--country", default="us", help="storefront, ISO 3166 code (default us)")
    parser.add_argument("--competitors", default="", help="comma-separated App Store IDs to add to the competitor set")
    parser.add_argument("--keywords", default="", help="the target's current keyword field, if the user shared it")
    parser.add_argument("--popularity", metavar="PATH", help="CSV of Apple Ads popularity scores (keyword,popularity)")
    parser.add_argument("--max-terms", type=int, default=12, help="search pages to read (default 12, max 20)")
    parser.add_argument("--suggestions-per-seed", type=int, default=2,
                        help="autocomplete suggestions per seed to rank-check (default 2)")
    parser.add_argument("--no-expand", action="store_true", help="skip autocomplete")
    parser.add_argument("--min-competitors", type=int, default=3, help="gap threshold (default 3)")
    parser.add_argument("--top", type=int, default=10, help="results kept per term (default 10)")
    parser.add_argument("--pause", type=float, default=1.0, help=argparse.SUPPRESS)
    parser.add_argument("--today", help=argparse.SUPPRESS)
    return parser


def run_main(argv: Optional[List[str]] = None, sleep=time.sleep) -> int:
    args = build_parser().parse_args(argv)
    run = cli.Run(TOOL, args)
    today = date.fromisoformat(args.today) if args.today else date.today()
    seeds, problems = parse_seeds(args.seeds)
    if problems:
        return run.fail(cli.STATUS_USAGE, "; ".join(problems))
    if not seeds or len(seeds) > MAX_SEEDS:
        return run.fail(cli.STATUS_USAGE, "Pass 1 to %d seed terms in --seeds." % MAX_SEEDS)
    country = ac.valid_country(args.country)
    if not country:
        return run.fail(cli.STATUS_USAGE, "'%s' is not an ISO 3166 country code." % args.country)
    if not 1 <= args.max_terms <= 20:
        return run.fail(cli.STATUS_USAGE, "--max-terms must be 1-20.")
    target_ref = ac.parse_app_ref(args.input) if args.input else None
    if target_ref and target_ref["kind"] == "name":
        return run.fail(cli.STATUS_USAGE, "Pass the target as an App Store ID or URL. Run aso_fetch.py with the "
                        "app name first to find its ID.")
    comp_ids = [part.strip().lower().replace("id", "") for part in args.competitors.split(",") if part.strip()]
    if any(not part.isdigit() for part in comp_ids):
        return run.fail(cli.STATUS_USAGE, "--competitors takes numeric App Store IDs.")
    keyword_field = [part.strip() for part in args.keywords.split(",") if part.strip()]
    popularity: Dict[str, float] = {}
    if args.popularity:
        try:
            popularity = read_popularity(args.popularity)
        except (OSError, ValueError, UnicodeDecodeError) as exc:
            return run.fail(cli.STATUS_USAGE, "Cannot read --popularity %s: %s" % (args.popularity, exc))

    from _growthkit import http  # noqa: E402
    session = http.new_session()
    timeout = args.timeout
    requests_ok = 0
    requests_failed = 0

    # Target
    target: Dict[str, Any] = {}
    similar: List[Dict[str, Any]] = []
    if target_ref:
        model, result, failure = ac.store_page_data(ac.PAGE_URL.format(cc=country, id=target_ref["id"]),
                                                    timeout=timeout, session=session)
        if failure:
            requests_failed += 1
            run.error("Target product page failed (%s); using the lookup API title only." % failure)
            rows, _r, lookup_failure = ac.itunes_lookup([target_ref["id"]], country, timeout=timeout, session=session)
            if rows:
                target = {"id": target_ref["id"], "title": rows[0].get("trackName"), "subtitle": None}
            elif lookup_failure in (None, "bad_request"):
                return run.fail(cli.STATUS_USAGE, "No app with ID %s in the %s storefront." % (target_ref["id"], country))
        else:
            requests_ok += 1
            page, _failed = ac.parse_product_page(model)
            target = {"id": target_ref["id"], "title": page.get("title"), "subtitle": page.get("subtitle")}
            similar = page.get("similar_apps") or []
        sleep(args.pause)

    # Autocomplete
    suggestions: Dict[str, List[str]] = {}
    hint_status: Dict[str, str] = {}
    if not args.no_expand:
        for seed in seeds:
            terms, failure = fetch_hints(seed, country, timeout, session)
            suggestions[seed] = terms
            hint_status[seed] = failure or "ok"
            if failure == "no_storefront_id":
                run.note("Autocomplete is not available for storefront %s in this script; seeds only." % country)
                break
            if failure:
                requests_failed += 1
                run.error("Autocomplete failed for %r (%s)." % (seed, failure))
            else:
                requests_ok += 1
            sleep(min(args.pause, 0.5))

    # Ranked results
    terms = pick_terms(seeds, suggestions, max(0, args.suggestions_per_seed), args.max_terms)
    competitors: Dict[str, Dict[str, Any]] = {}
    term_rows = []
    for index, item in enumerate(terms):
        if index:
            sleep(args.pause)
        results, failure, url = fetch_ranked(item["term"], country, timeout, session)
        row: Dict[str, Any] = {"term": item["term"], "source": item["source"], "url": url}
        if item["term"] in popularity:
            row["apple_ads_popularity"] = popularity[item["term"]]
        if failure:
            requests_failed += 1
            row["status"] = failure
            run.error("Search page failed for %r (%s)." % (item["term"], failure))
            term_rows.append(row)
            continue
        requests_ok += 1
        row["status"] = "ok"
        row["results_count"] = len(results)
        rank = next((r["rank"] for r in results if target and r["id"] == target.get("id")), None)
        row["target_rank"] = rank
        row["top"] = [{key: r.get(key) for key in ("rank", "id", "title", "subtitle", "rating_count",
                                                     "editors_choice")}
                      for r in results[:max(1, args.top)]]
        term_rows.append(row)
        for r in results[:max(1, args.top)]:
            if target and r["id"] == target.get("id"):
                continue
            entry = competitors.setdefault(r["id"], {
                "id": r["id"], "title": r.get("title"), "subtitle": r.get("subtitle"),
                "developer": r.get("developer"),
                "rating": r.get("rating"), "rating_count": r.get("rating_count"),
                "sources": [], "terms": [], "best_rank": r["rank"],
            })
            source = "search_seed" if item["source"] == "seed" else "search_suggestion"
            if source not in entry["sources"]:
                entry["sources"].append(source)
            entry["terms"].append(item["term"])
            entry["best_rank"] = min(entry["best_rank"], r["rank"])

    for app in similar:
        if not app.get("id") or (target and app["id"] == target.get("id")):
            continue
        entry = competitors.setdefault(app["id"], {
            "id": app["id"], "title": app.get("title"), "subtitle": app.get("subtitle"),
            "rating": app.get("rating"), "rating_count": app.get("rating_count"),
            "sources": [], "terms": [], "best_rank": None,
        })
        entry["sources"].append("similar_shelf")

    for comp_id in comp_ids:
        if comp_id in competitors:
            competitors[comp_id]["sources"].append("user")
            continue
        sleep(args.pause)
        model, result, failure = ac.store_page_data(ac.PAGE_URL.format(cc=country, id=comp_id),
                                                    timeout=timeout, session=session)
        if failure:
            requests_failed += 1
            run.error("Competitor %s product page failed (%s)." % (comp_id, failure))
            continue
        requests_ok += 1
        page, _failed = ac.parse_product_page(model)
        competitors[comp_id] = {"id": comp_id, "title": page.get("title"), "subtitle": page.get("subtitle"),
                                "rating": page.get("rating_average_display"),
                                "rating_count": page.get("rating_count_page"),
                                "sources": ["user"], "terms": [], "best_rank": None}

    if requests_ok == 0 and requests_failed:
        return run.fail(cli.STATUS_UNREACHABLE, "Every App Store request failed; retry later. Nothing was measured.",
                        {"terms": term_rows})

    comp_list = sorted(competitors.values(), key=lambda c: (-len(c["terms"]), c["best_rank"] or 99))
    for comp in comp_list:
        comp["appearances"] = len(comp["terms"])
        # Suggestions can drift away from the product ("project management institute"),
        # so only seed results, the similar shelf and user-named apps feed the matrix.
        comp["in_matrix"] = any(source in ("search_seed", "similar_shelf", "user") for source in comp["sources"])
    matrix = term_matrix([comp for comp in comp_list if comp["in_matrix"]], target, keyword_field,
                         max(1, args.min_competitors))
    if popularity:
        for row in matrix["words"] + matrix["phrases"] + matrix["gaps"]:
            if row["term"] in popularity:
                row["apple_ads_popularity"] = popularity[row["term"]]

    payload = ac.deep_normalize({
        "schema": "aso-keywords/1",
        "country": country,
        "fetched_on": today.isoformat(),
        "target": dict(target, keyword_field=keyword_field or None) if target else None,
        "seeds": seeds,
        "suggestions": [{"seed": seed, "status": hint_status.get(seed, "skipped"), "terms": suggestions.get(seed, [])}
                        for seed in seeds],
        "terms": term_rows,
        "competitors": [dict(comp, terms=comp["terms"][:4]) for comp in comp_list[:25]],
        "matrix": matrix,
        "popularity_source": args.popularity and "Apple Ads popularity pasted by the user (%s)" % args.popularity,
        "notes": [RANK_NOTE, SUGGESTION_NOTE],
    })
    return run.emit(payload, human=human_summary)


def human_summary(envelope: Dict[str, Any]) -> str:
    lines = []
    target = envelope.get("target") or {}
    if target:
        lines.append("Target: %s | %s" % (target.get("title"), target.get("subtitle")))
    for row in envelope.get("terms") or []:
        lines.append("  %-28s rank %-5s (%s)" % (row["term"][:28], row.get("target_rank") or "-", row.get("status")))
    gaps = (envelope.get("matrix") or {}).get("gaps") or []
    if gaps:
        lines.append("Gaps: " + ", ".join("%s (%d)" % (g["term"], g["competitors_using"]) for g in gaps[:12]))
    lines.append("Status: %s" % envelope.get("status"))
    return "\n".join(lines)


def main() -> int:
    return run_main()


if __name__ == "__main__":
    sys.exit(main())
