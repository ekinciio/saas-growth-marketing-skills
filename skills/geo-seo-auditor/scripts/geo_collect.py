#!/usr/bin/env python3
"""Collect AI-search readiness facts for a SaaS site in one pass (geo-seo-auditor).

    python3 geo_collect.py https://linear.app --pages 6 --json \
        --out growth-reports/.cache/2026-10-24-geo-linear-app-facts.json \
        --blocks-out growth-reports/.cache/2026-10-24-geo-linear-app-blocks.jsonl

Fetches each URL once and reports facts, never scores:
- the start page: HTTP status chain, final URL, bot-protection vendor
- robots.txt per host, read per RFC 9309 (404 = allowed, 5xx = assume
  disallow, 403/bot wall = unverifiable, HTML = no rules), Content-Signal
  lines, legacy tokens, declared sitemaps
- crawler access: every roster token (references/ai-crawlers.json) tested
  against real sampled URLs, with the deciding rule and blocked samples
- platforms: ChatGPT, Claude, Perplexity, Google AI Overviews, Copilot and
  others, combining crawler verdicts with page controls
- sitemaps (index followed into up to 3 children, newest lastmod)
- llms.txt (validated, links checked), llms-full.txt, Markdown versions
- sampled pages (home, pricing, two docs pages, a comparison page, a recent
  post, then other types): AI controls (X-Robots-Tag, meta robots per bot,
  noarchive/nocache, data-nosnippet), rendering, lang, canonical, JSON-LD key
  fields, microdata, dates, authorship
- content blocks per page (heading-scoped passages with numbers, entities,
  source links) written to --blocks-out as JSON Lines for the model to read
- numeric claims across the homepage, meta, JSON-LD and llms.txt, with
  possible contradictions lined up
- Wikidata: items for the brand and whether one lists this domain as its
  official website

Exit codes: 0 ok; 2 usage; 3 start page unreachable (DNS, 404, refused);
4 partial (start page blocked or a JS shell, or robots.txt unverifiable;
site-level facts still returned); 1 bug.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from _growthkit import cli, http
from _growthkit import report as gk_report
from geokit import blocks as blocks_mod
from geokit import discovery, llms, page, robots, roster, site

TOOL = "geo_collect"
# Fetch outcomes whose HTML is the real page (a bot wall or error page is not).
ANALYZABLE = ("ok", "too_large", "js_shell")


def _parse_page_overrides(values: Optional[List[str]]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for value in values or []:
        if "=" not in value:
            raise cli.UsageError("--page expects TYPE=URL, for example --page pricing=https://acme.app/pricing")
        kind, _, url = value.partition("=")
        kind = kind.strip().lower()
        try:
            out[kind] = http.normalize_url(url.strip())
        except ValueError as exc:
            raise cli.UsageError("--page %s: %s" % (kind, exc))
    return out


def ensure_private_dir(path: Optional[str]) -> None:
    """Create the parent folder; inside growth-reports/ also add its '*' .gitignore."""
    if not path:
        return
    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, exist_ok=True)
    parts = folder.split(os.sep)
    if gk_report.REPORTS_DIRNAME in parts:
        index = len(parts) - 1 - parts[::-1].index(gk_report.REPORTS_DIRNAME)
        gk_report.ensure_reports_dir(os.sep.join(parts[:index]) or os.sep)


# ---------------------------------------------------------------------------
# Crawler access over several hosts
# ---------------------------------------------------------------------------


def crawler_access(robots_by_host: Dict[str, Dict[str, Any]], samples: List[str]) -> Dict[str, Any]:
    """Per-token verdict over sample URLs, each judged by its own host's robots.txt."""
    rows = []
    for entry in roster.crawlers():
        blocked: List[Dict[str, Any]] = []
        allowed = 0
        unverifiable = 0
        groups = set()
        rule_seen = None
        for url in samples:
            host = (urlparse(url).hostname or "").lower()
            info = robots_by_host.get(host)
            if info is None:
                unverifiable += 1
                continue
            fixed = robots.verdict_without_rules(info["status"])
            if fixed == robots.ALLOWED or (fixed is None and info.get("parsed") is None):
                allowed += 1
                groups.add("none")
                continue
            if fixed == robots.UNVERIFIABLE:
                unverifiable += 1
                continue
            if fixed == robots.ASSUMED_BLOCKED:
                blocked.append({"url": url, "rule": "robots.txt %s (assume complete disallow)" % info["status"]})
                continue
            rules, group = robots.rules_for(info["parsed"], entry["token"])
            groups.add(group)
            ok, rule = robots.decide(rules, robots.path_of(url))
            if ok:
                allowed += 1
                if rule is not None and rule_seen is None:
                    rule_seen = robots.rule_text(rule)
            else:
                blocked.append({"url": url, "rule": robots.rule_text(rule)})
        judged = allowed + len(blocked)
        if judged == 0:
            verdict = robots.UNVERIFIABLE
        elif not blocked:
            verdict = robots.ALLOWED
        elif allowed == 0:
            verdict = robots.ASSUMED_BLOCKED if all("assume" in (b["rule"] or "") for b in blocked) else robots.BLOCKED
        else:
            verdict = robots.PARTIAL
        row = {
            "token": entry["token"],
            "type": entry["type"],
            "priority": entry["priority"],
            "verdict": verdict,
            "group": "explicit" if "explicit" in groups else ("wildcard" if "wildcard" in groups else "none"),
        }
        rule = blocked[0]["rule"] if blocked else rule_seen
        if rule:
            row["rule"] = rule
        if blocked:
            row["blocked_samples"] = [b["url"] for b in blocked[:4]]
        if unverifiable:
            row["unverifiable_samples"] = unverifiable
        if entry["robots_respected"] != "yes":
            row["robots_respected"] = entry["robots_respected"]
        if entry["status"] != "verified":
            row["registry_status"] = entry["status"]
        rows.append(row)
    return {"samples": samples, "tokens": rows, "summary": robots.summarize(rows)}


def platform_table(tokens: List[Dict[str, Any]], pages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Per AI platform: open / limited / partial / blocked / unverifiable, with reasons."""
    verdicts = {row["token"]: row["verdict"] for row in tokens}
    analyzed = [p for p in pages if p.get("ai_controls")]
    walled = [p["type"] for p in pages if p.get("status") == "blocked"]
    out = []
    for platform in roster.platforms():
        search = {t: verdicts.get(t) for t in platform["search_tokens"]}
        reasons: List[str] = []
        values = set(search.values())
        if values & {robots.BLOCKED, robots.ASSUMED_BLOCKED}:
            status = "blocked"
            reasons.append("search crawler blocked: " + ", ".join(t for t, v in search.items()
                                                                    if v in (robots.BLOCKED, robots.ASSUMED_BLOCKED)))
        elif robots.PARTIAL in values:
            status = "partial"
            reasons.append("search crawler blocked on some sampled URLs")
        elif robots.UNVERIFIABLE in values or not values:
            status = "unverifiable"
            reasons.append("robots.txt could not be read from here")
        else:
            status = "open"
        controls = platform.get("page_controls")
        if controls in ("google", "bing"):
            noindex = [p["type"] for p in analyzed if p["ai_controls"][controls].get("noindex")]
            if noindex:
                reasons.append("noindex on: " + ", ".join(noindex))
            if controls == "google":
                snip = [p["type"] for p in analyzed if p["ai_controls"]["google"].get("snippet_blocked")]
                if snip:
                    reasons.append("nosnippet or max-snippet:0 on: " + ", ".join(snip))
            else:
                noarchive = [p["type"] for p in analyzed if p["ai_controls"]["bing"].get("noarchive")]
                nocache = [p["type"] for p in analyzed if p["ai_controls"]["bing"].get("nocache")]
                if noarchive:
                    reasons.append("NOARCHIVE (kept out of Copilot answers) on: " + ", ".join(noarchive))
                if nocache:
                    reasons.append("NOCACHE (Copilot limited to URL, title, snippet) on: " + ", ".join(nocache))
            if status == "open" and len(reasons) > 0:
                status = "limited"
        if walled:
            reasons.append("bot protection answered a browser-like request for: %s; confirm the CDN/WAF lets "
                           "verified crawlers through" % ", ".join(walled))
        out.append({
            "id": platform["id"],
            "name": platform["name"],
            "status": status,
            "search_tokens": search,
            "user_fetch_tokens": {t: verdicts.get(t) for t in platform["user_fetch_tokens"]},
            "training_tokens": {t: verdicts.get(t) for t in platform["training_tokens"]},
            "owner_setting": platform.get("owner_setting"),
            "reasons": reasons,
        })
    return out


# ---------------------------------------------------------------------------
# Main collection
# ---------------------------------------------------------------------------


def _blocks_summary(result: Dict[str, Any]) -> Dict[str, Any]:
    return {k: result[k] for k in ("status", "reason", "raw_text_words", "count", "with_numbers",
                                   "with_source_links", "question_headings", "pronoun_openings")}


def collect(url: str, args: Any, run: cli.Run, fetcher: Optional[site.Fetcher] = None) -> Dict[str, Any]:
    fetcher = fetcher or site.Fetcher(timeout=args.timeout)
    overrides = _parse_page_overrides(getattr(args, "page", None))
    max_pages = max(1, min(int(args.pages), 10))
    run.log("Fetching %s" % url)
    home = fetcher.get(url, kind="html")
    home_markup = None
    if getattr(args, "html_file", None):
        with open(args.html_file, "rb") as handle:
            home_markup = handle.read().decode("utf-8-sig", "replace")
        run.note("Start page facts come from the saved HTML file %s (rendered copy); headers and status from "
                 "a live fetch." % args.html_file)
    status, message = cli.fetch_outcome(home)
    if status == cli.STATUS_UNREACHABLE and home_markup is None:
        return {"_fail": (status, message), "target": http.summarize(home)}
    if status != cli.STATUS_OK and home_markup is None:
        run.error(message)
    base = home.get("final_url") or home.get("url") or url
    site_domain = discovery.registrable_domain(urlparse(base).hostname or "")

    # Site-level files on the start host.
    robots_main = site.fetch_robots(fetcher, base)
    robots_by_host = {(urlparse(robots_main["url"]).hostname or "").lower(): robots_main}
    if robots_main["status"] in ("forbidden", "blocked"):
        run.error("robots.txt on %s is unverifiable from here (%s)." % (urlparse(base).hostname, robots_main["status"]))
    sitemaps = site.discover_sitemaps(fetcher, base, robots_main.get("sitemaps_declared") or [])
    llms_info = site.fetch_llms(fetcher, base)
    llms_full = site.fetch_llms_full(fetcher, base)

    # Home page facts and links.
    markup = home_markup if home_markup is not None else (
        home.get("html") if home.get("status") in ANALYZABLE else None)
    home_record = page.page_record(home, "home", markup=markup or "", url=base)
    pages = [home_record]
    nav_links = discovery.links_from_html(markup, base) if markup else []
    llms_links = [l["url"] for l in llms.all_links(llms_info["validation"]["parsed"])] if llms_info.get("validation") else []
    grouped = discovery.build_candidates(nav_links, sitemaps["entries"], llms_links, site_domain)
    picks = discovery.sample_pages(base, grouped, max_pages, overrides)
    all_blocks: List[Dict[str, Any]] = []
    page_blocks: Dict[str, Dict[str, Any]] = {}
    if markup:
        result = blocks_mod.extract_blocks(markup, base, page_key="home", page_type="home")
        page_blocks["home"] = result
        home_record["blocks"] = _blocks_summary(result)
        all_blocks.extend(result["blocks"])

    # Sampled pages.
    counts: Dict[str, int] = {}
    for pick in picks[1:]:
        counts[pick["type"]] = counts.get(pick["type"], 0) + 1
        key = pick["type"] if counts[pick["type"]] == 1 else "%s%d" % (pick["type"], counts[pick["type"]])
        run.log("Fetching %s page %s" % (pick["type"], pick["url"]))
        result = fetcher.get(pick["url"], kind="html")
        record = page.page_record(result, pick["type"],
                                  markup=result.get("html") if result.get("status") in ANALYZABLE else "")
        record["key"] = key
        record["source"] = pick["source"]
        if record.get("title") is None and result.get("status") != "ok":
            record["note"] = cli.fetch_outcome(result)[1]
        if result.get("html") and result.get("status") in ANALYZABLE:
            extracted = blocks_mod.extract_blocks(result["html"], record["final_url"], page_key=key,
                                                  page_type=pick["type"])
            record["blocks"] = _blocks_summary(extracted)
            page_blocks[key] = extracted
            all_blocks.extend(extracted["blocks"])
        pages.append(record)
    home_record["key"] = "home"
    home_record["source"] = "input"

    # robots.txt for other hosts among the samples (docs subdomains), at most 2 more.
    samples = discovery.robots_samples(base, grouped, picks)
    for url_ in samples:
        host = (urlparse(url_).hostname or "").lower()
        if host and host not in robots_by_host and len(robots_by_host) < 3:
            robots_by_host[host] = site.fetch_robots(fetcher, "https://%s/" % host)
    access = crawler_access(robots_by_host, samples)
    platforms = platform_table(access["tokens"], pages)

    # Markdown versions: the first docs page, else home.
    md_target = next((p for p in pages if p["type"] == "docs" and p.get("http_status") == 200), None) or home_record
    markdown = site.markdown_checks(fetcher, md_target["final_url"] or base) if md_target.get("final_url") else None

    # llms.txt link check.
    if llms_info.get("validation") and args.check_links > 0:
        links = [l["url"] for l in llms.all_links(llms_info["validation"]["parsed"])]
        llms_info["link_check"] = site.check_links(fetcher, links, limit=args.check_links)

    # Entity.
    brand = llms.brand_name(home_record, base) if home_record.get("title") or home_record.get("og") else \
        {"name": site_domain.split(".")[0].capitalize() if site_domain else None, "source": "domain label (check it)"}
    if getattr(args, "brand", None):
        brand = {"name": args.brand, "source": "--brand"}
    entity: Dict[str, Any] = {
        "brand": brand,
        "same_as": ((home_record.get("schema") or {}).get("organization") or {}).get("same_as", []),
        "social_links": home_record.get("social_links", []),
    }
    if args.no_entity:
        entity["wikidata"] = {"status": "skipped"}
    else:
        entity["wikidata"] = site.wikidata(fetcher, brand.get("name"), site_domain)

    # Numeric claims across sources.
    claims: List[Dict[str, Any]] = []
    home_text = " ".join(b["text"] for b in (page_blocks.get("home") or {}).get("blocks", []))
    claims += blocks_mod.extract_claims(home_text, "homepage text")
    claims += blocks_mod.extract_claims(home_record.get("meta_description"), "homepage meta description")
    claims += blocks_mod.extract_claims((home_record.get("og") or {}).get("description"), "homepage og:description")
    for item in (home_record.get("schema") or {}).get("descriptions", []):
        claims += blocks_mod.extract_claims(item.get("text"), "JSON-LD %s description" % (item.get("type") or ""))
    if llms_info.get("validation"):
        parsed = llms_info["validation"]["parsed"]
        claims += blocks_mod.extract_claims(parsed.get("summary"), "llms.txt summary")
        claims += blocks_mod.extract_claims(" ".join(parsed.get("details") or []), "llms.txt details")
    for p in pages[1:]:
        if p.get("type") in ("about", "customers") and p.get("meta_description"):
            claims += blocks_mod.extract_claims(p["meta_description"], "%s meta description" % p["type"])

    # Coverage.
    measured, not_measured = [], []
    if robots_main["status"] in ("forbidden", "blocked"):
        not_measured.append("crawler rules on %s (robots.txt %s)" % (urlparse(base).hostname, robots_main["status"]))
    else:
        measured.append("robots.txt on %d host(s), %d sample URLs, %d tokens"
                        % (len(robots_by_host), len(samples), len(access["tokens"])))
    ok_pages = [p for p in pages if p.get("rendering")]
    measured.append("%d of %d sampled page(s) analyzed: %s" % (
        len(ok_pages), len(pages), ", ".join(p.get("key", p["type"]) for p in ok_pages)))
    for p in pages:
        if not p.get("rendering"):
            not_measured.append("%s page %s (%s)" % (p["type"], p.get("url"), p.get("status")))
    missing_types = [t for t in ("pricing", "docs", "comparison", "blog") if t not in [p["type"] for p in pages]]
    if missing_types:
        not_measured.append("no %s page found in homepage links, sitemap or llms.txt" % ", ".join(missing_types))
    not_measured += [
        "Search Console 'Search generative AI' setting and Generative AI performance report (owner access)",
        "Bing Webmaster Tools AI Performance (owner access)",
        "how often AI answers mention the brand (Visibility; run ai-answer-share-of-voice)",
        "real crawler behaviour (needs server logs; see ai_log_analyzer.py)",
    ]

    sitemap_public = site.public_sitemap(sitemaps)
    data: Dict[str, Any] = {
        "input": {"url": url, "pages_requested": max_pages, "overrides": overrides or None,
                  "html_file": getattr(args, "html_file", None)},
        "target": http.summarize(home),
        "site": {
            "root": http.site_root(base),
            "domain": site_domain,
            "robots": site.public_robots(robots_main),
            "robots_other_hosts": [site.public_robots(v) for k, v in robots_by_host.items()
                                   if v is not robots_main],
            "sitemap": sitemap_public,
            "llms_txt": site.public_llms(llms_info),
            "llms_full_txt": llms_full,
            "markdown": markdown,
            "entity": entity,
        },
        "crawler_access": access,
        "platforms": platforms,
        "pages": pages,
        "consistency": {"claims": claims[:30], "possible_conflicts": blocks_mod.find_conflicts(claims)},
        "candidates": {kind: [e["url"] for e in entries[:3]] for kind, entries in grouped.items()},
        "coverage": {"measured": measured, "not_measured": not_measured},
        "requests": len(fetcher.log),
    }
    # robots text is kept only in --out (for draft diffs); stdout stays small.
    data["site"]["robots"].pop("text", None)
    for other in data["site"]["robots_other_hosts"]:
        other.pop("text", None)
    data["_robots_text"] = robots_main.get("text")
    data["_blocks"] = all_blocks
    data["_llms_text"] = llms_info.get("text")
    return data


def write_blocks(path: str, blocks: List[Dict[str, Any]]) -> None:
    ensure_private_dir(path)
    with open(path, "w", encoding="utf-8") as handle:
        for block in blocks:
            handle.write(json.dumps(block, ensure_ascii=False) + "\n")


def human(envelope: Dict[str, Any]) -> str:
    lines = ["GEO facts for %s" % (envelope.get("input") or {}).get("url")]
    target = envelope.get("target") or {}
    lines.append("Start page: HTTP %s, %s" % (target.get("http_status"), target.get("status")))
    robots_info = (envelope.get("site") or {}).get("robots") or {}
    lines.append("robots.txt: %s - %s" % (robots_info.get("status"), robots_info.get("meaning")))
    for row in (envelope.get("crawler_access") or {}).get("tokens", []):
        if row["priority"] in ("critical", "high") or row["verdict"] != "allowed":
            lines.append("  %-22s %-10s %-12s %s" % (row["token"], row["type"], row["verdict"], row.get("rule") or ""))
    for p in envelope.get("platforms") or []:
        lines.append("Platform %-36s %s %s" % (p["name"], p["status"], "; ".join(p["reasons"])))
    for p in envelope.get("pages") or []:
        b = p.get("blocks") or {}
        lines.append("Page %-10s %s HTTP %s blocks %s" % (p.get("key", p["type"]), p.get("final_url"),
                                                         p.get("http_status"), b.get("count")))
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    parser = cli.build_parser(
        "Collect AI-search readiness facts for a SaaS site (fetch once, no scoring).",
        input_help="the site URL (homepage or any page); bare domains work",
        demo=False,
    )
    parser.add_argument("--pages", type=int, default=6, help="pages to sample including the start page (1-10, default 6)")
    parser.add_argument("--page", action="append", metavar="TYPE=URL",
                        help="force a page for a type, e.g. --page pricing=https://acme.app/pricing (repeatable)")
    parser.add_argument("--html-file", metavar="PATH", help="saved, rendered HTML of the start page (browser fallback)")
    parser.add_argument("--brand", help="brand name for the entity check (default: from og:site_name, schema or title)")
    parser.add_argument("--no-entity", action="store_true", help="skip the Wikidata lookup")
    parser.add_argument("--check-links", type=int, default=10, metavar="N",
                        help="check up to N llms.txt links (default 10, 0 to skip)")
    parser.add_argument("--blocks-out", metavar="PATH", help="write every content block as JSON Lines to PATH")
    args = parser.parse_args(argv)
    run = cli.Run(TOOL, args)
    try:
        source = cli.resolve_input(args.input, allow_file=False, allow_stdin=False)
        url = http.normalize_url(source["value"])
        if args.html_file and not os.path.isfile(args.html_file):
            raise cli.UsageError("--html-file not found: %s" % args.html_file)
        if args.pages < 1:
            raise cli.UsageError("--pages must be at least 1")
    except (cli.UsageError, ValueError) as exc:
        return run.fail(cli.STATUS_USAGE, str(exc))
    if args.out:
        ensure_private_dir(args.out)
    data = collect(url, args, run)
    if "_fail" in data:
        status, message = data.pop("_fail")
        return run.fail(status, message + " Check the URL with the user; nothing was scored.", data)
    blocks = data.pop("_blocks")
    data.pop("_llms_text", None)
    robots_text = data.pop("_robots_text", None)
    if args.blocks_out:
        try:
            write_blocks(args.blocks_out, blocks)
            data["blocks_file"] = {"path": args.blocks_out, "blocks": len(blocks)}
        except OSError as exc:
            run.error("Could not write --blocks-out %s: %s" % (args.blocks_out, exc))
    else:
        data["blocks_preview"] = [
            {"id": b["id"], "heading_path": b["heading_path"], "words": b["words"], "numbers": b["numbers"],
             "text": b["text"][:240]}
            for b in blocks[:20]
        ]
        run.note("No --blocks-out given: only a preview of %d of %d blocks is included." % (min(20, len(blocks)), len(blocks)))
    if robots_text:
        data["site"]["robots"]["text"] = robots_text[:6000]
        data["site"]["robots"]["text_truncated"] = len(robots_text) > 6000
    return run.emit(data, human=human)


if __name__ == "__main__":
    sys.exit(main())
