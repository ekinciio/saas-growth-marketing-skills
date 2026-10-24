#!/usr/bin/env python3
"""Read a SaaS pricing page and extract pricing facts (no judgment).

    pricing_page.py https://www.acme.app/pricing --json
    pricing_page.py growth-reports/.cache/acme-pricing-rendered.html --url https://www.acme.app/pricing --json

Output (one JSON envelope):
    page            url, final_url, http_status, title, fetched_on, bot_protection
    plan_sets       groups of plan cards found by page structure: each card has
                    a name, the price texts inside it (amount, currency,
                    period, unit and billing hints), badges ("Most popular"),
                    feature bullets and CTA texts
    price_mentions  every price in the visible text with its context
    tables          comparison tables (header row and body rows as text)
    signals         billing words found on the page (billed annually, per
                    user, credits, contact sales, free trial, save N%)
    json_ld_offers  Offer / AggregateOffer data from JSON-LD, if any
    main_text       the start of the visible text, for anything the
                    structure missed

The model turns this into the pricing_analyzer.py input and shows the user a
confirmation table; nothing here decides what a tier "is". Static HTML only:
a JavaScript-rendered or blocked page exits 5 or 3 (see the skill's failure
handling and browser fallback).

Exit codes: 0 ok, 2 usage, 3 unreachable or blocked, 4 partial (page larger
than the size limit), 5 nothing to analyze (JS shell, empty page).
"""

from __future__ import annotations

import os
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from _growthkit import cli  # noqa: E402

TOOL = "pricing_page"

_CURRENCY = (r"(?:US\$|CA\$|AU\$|A\$|NZ\$|R\$|HK\$|S\$|\$|€|£|¥|₹|₺|₩|"
             r"CHF\s?|USD\s?|EUR\s?|GBP\s?)")
_AMOUNT = r"\d{1,3}(?:[,.]\d{3})+(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?"
PRICE_RE = re.compile(
    r"(?P<cur>" + _CURRENCY + r")\s?(?P<amt>" + _AMOUNT + r")(?![\d])"
    r"|(?P<amt2>" + _AMOUNT + r")\s?(?P<cur2>€|£|₺|zł|kr|USD|EUR|GBP)(?![A-Za-z])"
)
_PERIOD_MONTH_RE = re.compile(r"^\s*(?:[^\d$€£]{0,40}?)(?:/\s*mo(?:nth)?\b|per\s+month|a\s+month|monthly|/\s*month|mo\b)", re.I)
_PERIOD_YEAR_RE = re.compile(r"^\s*(?:[^\d$€£]{0,40}?)(?:/\s*(?:yr|year)\b|per\s+year|a\s+year|/\s*annum|per\s+annum)", re.I)
_SEAT_RE = re.compile(r"(?:\bper|/|\ba|\beach)\s*(?:active\s+)?(user|seat|member|editor|agent|license|licence|"
                      r"teammate|person|creator|host|admin|employee)s?\b", re.I)
_USAGE_RE = re.compile(
    r"\bper\s+(?P<qty>\d[\d,.]*\s*k?\s+)?(?P<unit>(?:monthly\s+)?(?:[a-z]+\s+)?(?:credits?|outcomes?|resolutions?|"
    r"conversations?|actions?|calls?|requests?|messages?|contacts?|emails?|tokens?|minutes?|hours?|runs?|tasks?|"
    r"events?|records?|responses?|transactions?|documents?|pages?|gb|mtus?|maus?))\b", re.I)
_BILLED_ANNUAL_RE = re.compile(r"billed\s+(?:annually|yearly|per\s+year|once\s+a\s+year)|annual(?:ly)?\s+billing|"
                               r"paid\s+(?:annually|yearly)|when\s+billed\s+(?:annually|yearly)", re.I)
_BILLED_MONTH_RE = re.compile(r"billed\s+monthly|monthly\s+billing|if\s+billed\s+monthly|paid\s+monthly", re.I)
_CUSTOM_RE = re.compile(r"contact\s+(?:sales|us)|talk\s+to\s+(?:sales|us)|let'?s\s+talk|custom\s+pricing|"
                        r"request\s+(?:a\s+)?(?:quote|demo|pricing)|get\s+a\s+(?:quote|demo)|book\s+a\s+demo|"
                        r"\bcustom\b", re.I)
_BADGE_RE = re.compile(r"most\s+popular|popular|recommended|best\s+value|best\s+for|most\s+chosen|"
                       r"top\s+pick|new\b|save\s+\d+\s*%", re.I)
_SAVE_RE = re.compile(r"save\s+(?:up\s+to\s+)?(\d{1,2})\s*%|(\d{1,2})\s*%\s+(?:off|discount|savings?)", re.I)
_TRIAL_RE = re.compile(r"(\d{1,3})[-\s]day\s+(?:free\s+)?trial|free\s+trial|try\s+(?:it\s+)?(?:for\s+)?free", re.I)
_NO_CARD_RE = re.compile(r"no\s+credit\s+card|no\s+card\s+required|without\s+a\s+credit\s+card", re.I)
_HEADING_TAGS = ("h1", "h2", "h3", "h4", "h5", "h6")
_NAME_CLASS_RE = re.compile(r"(?:title|name|heading|plan|tier|header)", re.I)

MAX_SETS = 4
MAX_CARDS = 10
MAX_FEATURES = 40
MAX_MENTIONS = 60
MAX_TABLES = 4
MAX_TABLE_ROWS = 80


def _norm(text: str) -> str:
    return " ".join((text or "").split())


def parse_amount(cur: Optional[str], amt: str) -> Optional[float]:
    """'1,200' -> 1200, '9,99' -> 9.99, '1.200,50' -> 1200.5, '10.99' -> 10.99."""
    token = amt.strip()
    if re.match(r"^\d+$", token):
        return float(token)
    if re.match(r"^\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?$", token):
        return float(token.replace(",", ""))
    if re.match(r"^\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?$", token):
        return float(token.replace(".", "").replace(",", "."))
    if re.match(r"^\d+\.\d{1,2}$", token):
        return float(token)
    if re.match(r"^\d+,\d{1,2}$", token):
        return float(token.replace(",", "."))
    return None


def _with_suffix(amount: Optional[float], following: str) -> Optional[float]:
    """'$15k' -> 15000 (a 'k' right after the digits, not the start of a word)."""
    if amount is None or not following:
        return amount
    if following[0] in "kK" and (len(following) == 1 or not following[1].isalpha()):
        return amount * 1000
    return amount


def _currency_code(symbol: str) -> str:
    s = (symbol or "").strip().upper()
    table = {"$": "USD?", "US$": "USD", "CA$": "CAD", "AU$": "AUD", "A$": "AUD", "NZ$": "NZD",
             "R$": "BRL", "HK$": "HKD", "S$": "SGD", "€": "EUR", "£": "GBP", "¥": "JPY?",
             "₹": "INR", "₺": "TRY", "₩": "KRW", "CHF": "CHF", "USD": "USD", "EUR": "EUR",
             "GBP": "GBP", "ZŁ": "PLN", "KR": "SEK/NOK/DKK?"}
    return table.get(s, s)


def describe_price(text: str, match: "re.Match[str]") -> Dict[str, Any]:
    """Amount, currency and the period / unit / billing words right after it."""
    cur = match.group("cur") or match.group("cur2") or ""
    amt = match.group("amt") or match.group("amt2") or ""
    after = text[match.end():match.end() + 70]
    before = text[max(0, match.start() - 50):match.start()]
    near = after[:45]
    info: Dict[str, Any] = {
        "raw": _norm(text[max(0, match.start() - 2):match.end() + 40])[:90],
        "amount": _with_suffix(parse_amount(cur, amt), text[match.end():match.end() + 2]),
        "currency": _currency_code(cur),
        "period": "month" if _PERIOD_MONTH_RE.match(near) else ("year" if _PERIOD_YEAR_RE.match(near) else None),
        "unit": None,
        "billing": None,
    }
    seat = _SEAT_RE.search(near)
    usage = _USAGE_RE.search(near)
    if seat and (not usage or seat.start() <= usage.start()):
        info["unit"] = "per_" + seat.group(1).lower()
    elif usage:
        qty = (usage.group("qty") or "").strip()
        info["unit"] = "per " + (qty + " " if qty else "") + _norm(usage.group("unit")).lower()
    # The billing words right after the price win; words just before it
    # ("Annual billing  Pro, $79 /mo") count only when nothing follows.
    window = after[:60]
    nxt = PRICE_RE.search(window)
    if nxt:
        window = window[:nxt.start()]
    hits = [(m.start(), "annual") for m in _BILLED_ANNUAL_RE.finditer(window)]
    hits += [(m.start(), "monthly") for m in _BILLED_MONTH_RE.finditer(window)]
    if hits:
        info["billing"] = min(hits)[1]
    elif _BILLED_ANNUAL_RE.search(before[-30:]):
        info["billing"] = "annual"
    elif _BILLED_MONTH_RE.search(before[-30:]):
        info["billing"] = "monthly"
    return info


# ---------------------------------------------------------------------------
# Structure: plan cards
# ---------------------------------------------------------------------------

def _price_elements(soup: Any, html: Any) -> List[Any]:
    """Smallest elements whose own short text contains a price ('$' and '10' may be split)."""
    from bs4 import NavigableString, Tag  # type: ignore

    found: List[Any] = []
    seen = set()
    for string in soup.find_all(string=True):
        if not isinstance(string, NavigableString):
            continue
        value = str(string)
        if not re.search(r"\d|[$€£¥₹₺]", value):
            continue
        node = string.parent
        for _ in range(4):
            if not isinstance(node, Tag) or node.name in ("body", "html", "[document]"):
                break
            text = html.clean_text(node, collapse=True)
            if len(text) > 80:
                break
            if PRICE_RE.search(text):
                if id(node) not in seen:
                    seen.add(id(node))
                    found.append(node)
                break
            node = node.parent
    # Keep the innermost: drop an element when one of its descendants is also a price element.
    ids = {id(n) for n in found}
    inner = []
    for node in found:
        if any(id(d) in ids for d in node.find_all(True)):
            continue
        inner.append(node)
    return inner


_UNIT_NAME_RE = re.compile(r"^(?:from|per\b|/|billed|starting|starts\s+at|only|save|up\s+to)", re.I)


def _clean_name(text: str) -> Optional[str]:
    """Drop badge words glued to a plan name ('Business Recommended' -> 'Business')."""
    if not text or _UNIT_NAME_RE.match(text):
        return None
    stripped = _norm(_BADGE_RE.sub(" ", text))
    return (stripped or text)[:60]


def _card_name(card: Any, html: Any) -> Optional[str]:
    for tag in card.find_all(_HEADING_TAGS):
        text = html.clean_text(tag, collapse=True)
        if text and not PRICE_RE.search(text) and len(text.split()) <= 8 and _clean_name(text):
            return _clean_name(text)
    for tag in card.find_all(True):
        classes = " ".join(tag.get("class") or []) if tag.attrs else ""
        if classes and _NAME_CLASS_RE.search(classes):
            text = html.clean_text(tag, collapse=True)
            if text and len(text.split()) <= 5 and not PRICE_RE.search(text) and not _BADGE_RE.fullmatch(text) \
                    and _clean_name(text):
                return _clean_name(text)
    for tag in card.find_all(["strong", "b", "p", "span", "div"]):
        text = html.clean_text(tag, collapse=True)
        if text and len(text.split()) <= 4 and not PRICE_RE.search(text) and not _BADGE_RE.search(text) \
                and not re.search(r"\d", text) and _clean_name(text):
            return _clean_name(text)
    return None


def _card_facts(card: Any, prices: List[Any], html: Any) -> Dict[str, Any]:
    text = html.clean_text(card, collapse=True)
    price_info = []
    seen = set()
    for match in PRICE_RE.finditer(text):
        info = describe_price(text, match)
        key = (info["amount"], info["period"], info["unit"], info["billing"])
        if key in seen:
            continue
        seen.add(key)
        price_info.append(info)
    badges = []
    for tag in card.find_all(True):
        short = html.clean_text(tag, collapse=True)
        if short and len(short.split()) <= 4 and _BADGE_RE.search(short) and short not in badges:
            badges.append(short)
    features = []
    for li in card.find_all("li"):
        item = html.clean_text(li, collapse=True)
        if item and item not in features:
            features.append(item[:160])
        if len(features) >= MAX_FEATURES:
            break
    ctas = []
    for tag in card.find_all(["a", "button"]):
        label = html.clean_text(tag, collapse=True)
        if label and len(label.split()) <= 6 and label not in ctas:
            ctas.append(label)
    return {
        "name": _card_name(card, html),
        "prices": price_info[:6],
        "custom_price_words": bool(_CUSTOM_RE.search(text)) and not price_info,
        "badges": badges[:4],
        "features": features,
        "ctas": ctas[:4],
        "text": text[:500],
        "words": len(text.split()),
    }


def _has_heading(tag: Any) -> bool:
    return tag.name in _HEADING_TAGS or tag.find(_HEADING_TAGS) is not None


def _heading_children(tag: Any) -> int:
    return sum(1 for child in tag.find_all(True, recursive=False) if _has_heading(child))


def _card_of(price: Any, counts: Dict[int, int]) -> Any:
    """The plan card that holds a price element.

    Walk up from the price until the parent is a grid of cards (two or more
    children with their own heading), or until the parent holds another
    plan's price (a price outside a headed element, or any other price when
    the page uses no headings). Monthly and annual prices inside one card
    stay in that card.
    """
    cur = price
    while True:
        parent = cur.parent
        if parent is None or parent.name in ("body", "html", "[document]", "main"):
            return cur
        if _heading_children(parent) >= 2:
            return cur
        if counts.get(id(parent), 0) > counts.get(id(cur), 0) and (_has_heading(cur) or not _has_heading(parent)):
            return cur
        cur = parent


def find_plan_sets(soup: Any, html: Any) -> List[Dict[str, Any]]:
    """Plan cards grouped by their shared parent, in page order."""
    prices = _price_elements(soup, html)
    counts: Dict[int, int] = {}
    for node in prices:
        for parent in [node] + list(node.parents):
            counts[id(parent)] = counts.get(id(parent), 0) + 1
    groups: Dict[int, Tuple[Any, List[Any]]] = {}
    order: List[int] = []
    card_ids = set()
    for node in prices:
        card = _card_of(node, counts)
        if id(card) in card_ids:
            continue
        # A card inside another card (a nested price line) belongs to the outer one.
        if any(id(p) in card_ids for p in card.parents):
            continue
        card_ids.add(id(card))
        parent = card.parent
        if id(parent) not in groups:
            groups[id(parent)] = (parent, [])
            order.append(id(parent))
        groups[id(parent)][1].append(card)
    sets = []
    for key in order:
        parent, cards = groups[key]
        members = []
        for child in parent.find_all(True, recursive=False):
            if child in cards:
                members.append(child)
            elif _has_heading(child):
                text = html.clean_text(child, collapse=True)
                if text and len(text.split()) <= 300 and _CUSTOM_RE.search(text):
                    members.append(child)  # a "Contact sales" card without a number
        facts = [_card_facts(c, prices, html) for c in members]
        facts = [c for c in facts if c["name"] or c["prices"]]
        if not facts or (len(facts) == 1 and not facts[0]["name"]):
            continue
        sets.append({"cards": facts[:MAX_CARDS], "card_count": len(facts)})
        if len(sets) >= MAX_SETS:
            break
    return sets


def extract_tables(soup: Any, html: Any) -> List[Dict[str, Any]]:
    """Comparison tables as text rows (icons read from aria-label, title or alt)."""

    def cell_text(cell: Any) -> str:
        text = html.clean_text(cell, collapse=True)
        if text:
            return text[:120]
        for tag in [cell] + cell.find_all(True):
            for attr in ("aria-label", "title", "alt", "data-tooltip"):
                value = tag.get(attr) if tag.attrs else None
                if value:
                    return "[" + _norm(str(value))[:60] + "]"
        return ""

    out = []
    tables = soup.find_all("table") + soup.find_all(attrs={"role": re.compile(r"^(?:table|grid)$")})
    for table in tables:
        if table.name == "table":
            rows = table.find_all("tr")
            grid = [[cell_text(c) for c in r.find_all(["th", "td"])] for r in rows]
        else:
            rows = table.find_all(attrs={"role": "row"})
            grid = [[cell_text(c) for c in r.find_all(attrs={"role": re.compile(r"^(?:cell|gridcell|columnheader|rowheader)$")})]
                    for r in rows]
        grid = [r for r in grid if any(r)]
        if len(grid) < 2:
            continue
        out.append({"header": grid[0], "rows": grid[1:MAX_TABLE_ROWS + 1], "row_count": len(grid) - 1})
        if len(out) >= MAX_TABLES:
            break
    return out


def _json_ld_offers(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    offers = []

    def walk(node: Any, product: Optional[str]) -> None:
        if isinstance(node, list):
            for item in node:
                walk(item, product)
            return
        if not isinstance(node, dict):
            return
        types = node.get("@type")
        types = types if isinstance(types, list) else [types]
        name = node.get("name") if isinstance(node.get("name"), str) else product
        if any(t in ("Offer", "AggregateOffer") for t in types):
            spec = node.get("priceSpecification")
            offers.append({
                "name": name, "price": node.get("price"), "low_price": node.get("lowPrice"),
                "high_price": node.get("highPrice"), "currency": node.get("priceCurrency"),
                "unit": (spec or {}).get("unitText") if isinstance(spec, dict) else None,
            })
        for key in ("offers", "hasOfferCatalog", "itemListElement", "itemOffered"):
            if key in node:
                walk(node[key], name)

    walk(items, None)
    return offers[:20]


def extract(markup: str, url: Optional[str], max_text: int = 8000) -> Dict[str, Any]:
    """All pricing facts from one HTML document."""
    from _growthkit import html  # imports bs4 (install hint and exit 2 when missing)

    shell = html.js_shell_signals(markup)
    soup = html.parse(markup)
    title = html.extract_title(soup)
    json_ld = html.extract_json_ld(soup)
    html.strip_invisible(soup)
    for tag in soup.find_all(["nav", "footer"]) + soup.find_all(attrs={"role": re.compile(r"^(?:navigation|contentinfo)$")}):
        tag.decompose()
    body = soup.body or soup
    text = html.clean_text(body, collapse=True)
    words = len(text.split())
    h1 = [html.clean_text(h, collapse=True) for h in body.find_all("h1")]

    mentions = []
    seen = set()
    for match in PRICE_RE.finditer(text):
        info = describe_price(text, match)
        context = _norm(text[max(0, match.start() - 60):match.end() + 80])
        key = (info["amount"], context[:40])
        if key in seen:
            continue
        seen.add(key)
        info["context"] = context
        mentions.append(info)
        if len(mentions) >= MAX_MENTIONS:
            break

    saves = sorted({int(m.group(1) or m.group(2)) for m in _SAVE_RE.finditer(text)})
    trials = sorted({int(m.group(1)) for m in _TRIAL_RE.finditer(text) if m.group(1)})
    seat_units = sorted({m.group(1).lower() for m in _SEAT_RE.finditer(text)})
    usage_units = sorted({_norm(m.group("unit")).lower() for m in _USAGE_RE.finditer(text)})[:12]
    signals = {
        "billed_annually_mentions": len(_BILLED_ANNUAL_RE.findall(text)),
        "billed_monthly_mentions": len(_BILLED_MONTH_RE.findall(text)),
        "annual_savings_pct_mentioned": saves,
        "per_seat_words": seat_units,
        "usage_units": usage_units,
        "credits_mentioned": bool(re.search(r"\bcredits?\b", text, re.I)),
        "contact_sales_mentions": len(_CUSTOM_RE.findall(text)),
        "free_trial_days": trials,
        "free_trial_mentioned": bool(_TRIAL_RE.search(text)),
        "no_card_required_mentioned": bool(_NO_CARD_RE.search(text)),
        "free_plan_mentioned": bool(re.search(r"\bfree\s+(?:plan|forever|tier)\b|\$0\b", text, re.I)),
        "currencies_seen": sorted({_currency_code(m.group("cur") or m.group("cur2") or "")
                                   for m in PRICE_RE.finditer(text)}),
    }
    return {
        "page": {"url": url, "title": title, "h1": h1[:3], "words": words,
                 "is_js_shell": shell.get("is_js_shell"), "js_shell_signals": shell},
        "plan_sets": find_plan_sets(body, html),
        "price_mentions": mentions,
        "tables": extract_tables(body, html),
        "signals": signals,
        "json_ld_offers": _json_ld_offers(json_ld.get("items") or []),
        "main_text": text[:max_text],
        "main_text_truncated": len(text) > max_text,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = cli.build_parser(
        "Extract pricing facts (plans, prices, billing words, comparison tables) from a pricing page.",
        input_help="pricing page URL, or a saved HTML file (from the browser fallback)",
        prog="pricing_page.py",
    )
    parser.add_argument("--url", help="the page's original URL when the input is a saved HTML file")
    parser.add_argument("--max-text", type=int, default=8000, metavar="CHARS",
                        help="characters of visible text to include (default 8000)")
    args = parser.parse_args(argv)
    run = cli.Run(TOOL, args)
    if args.out and "growth-reports" in os.path.abspath(args.out).split(os.sep):
        parts = os.path.abspath(args.out).split(os.sep)
        root = os.sep.join(parts[:parts.index("growth-reports") + 1])
        try:
            os.makedirs(root, exist_ok=True)
            if not os.path.exists(os.path.join(root, ".gitignore")):
                with open(os.path.join(root, ".gitignore"), "w", encoding="utf-8") as handle:
                    handle.write("*\n")
        except OSError:
            pass
    if args.demo:
        markup = DEMO_HTML
        source = {"kind": "demo", "value": None}
    else:
        try:
            source = cli.resolve_input(args.input, allow_url=True, allow_file=True, allow_stdin=True)
        except cli.UsageError as exc:
            return run.fail(cli.STATUS_USAGE, str(exc))
        markup = source.get("text")
    page_meta: Dict[str, Any] = {"fetched_on": date.today().isoformat(), "source": source["kind"]}
    status = cli.STATUS_OK
    url = args.url
    if source["kind"] == "url":
        from _growthkit import http  # imports requests (install hint and exit 2 when missing)

        result = http.fetch(source["value"], timeout=args.timeout)
        url = result.get("final_url") or result.get("url")
        page_meta.update({"requested_url": result.get("url"), "final_url": result.get("final_url"),
                          "http_status": result.get("http_status"),
                          "bot_protection": (result.get("bot_protection") or {}).get("vendor")})
        outcome, message = cli.fetch_outcome(result)
        if outcome not in (cli.STATUS_OK, cli.STATUS_PARTIAL):
            return run.fail(outcome, message, data={"page": page_meta})
        if outcome == cli.STATUS_PARTIAL:
            run.error(message)
            status = cli.STATUS_PARTIAL
        markup = result.get("html") or ""
    facts = extract(markup or "", url, max_text=max(500, args.max_text))
    facts["page"].update(page_meta)
    verdict, message = cli.facts_outcome({"word_count": facts["page"]["words"],
                                          "is_js_shell": facts["page"]["is_js_shell"],
                                          "headings": {"h1": facts["page"]["h1"]}})
    if verdict == cli.STATUS_NOTHING:
        return run.fail(cli.STATUS_NOTHING, message, data=facts)
    if message:
        run.note(message)
    if not facts["price_mentions"]:
        run.note("No price amounts found in the static HTML. Prices may be rendered by JavaScript "
                 "(use the browser fallback) or the page may be contact-sales only.")
    if not facts["plan_sets"]:
        run.note("No repeated plan cards found; read prices from price_mentions, tables and main_text.")
    if "USD?" in facts["signals"]["currencies_seen"]:
        run.note("'$' could be USD or another dollar currency; confirm the currency with the user.")
    return run.emit(facts, status=status if status != cli.STATUS_OK else None,
                    human=lambda env: cli.to_json(env, compact=False))


DEMO_HTML = """<!doctype html><html><head><title>Demo pricing</title></head><body><main>
<h1>Simple pricing for teams</h1><p>Billed annually. Save 20% vs monthly.</p>
<div class="plans">
 <div class="plan"><h3>Free</h3><p class="price">$0 per user/month</p><ul><li>3 projects</li><li>Basic reports</li></ul><a href="/signup">Get started</a></div>
 <div class="plan"><span class="badge">Most popular</span><h3>Team</h3><p class="price">$10 per user/month</p><p>Billed annually</p><ul><li>Everything in Free, plus:</li><li>Unlimited projects</li><li>Integrations</li></ul><a href="/signup">Start free trial</a></div>
 <div class="plan"><h3>Business</h3><p class="price">$20 per user/month</p><ul><li>Everything in Team, plus:</li><li>SAML SSO</li><li>Admin roles</li></ul><a href="/signup">Start free trial</a></div>
 <div class="plan"><h3>Enterprise</h3><p>Custom pricing</p><ul><li>SCIM</li><li>Audit log</li></ul><a href="/sales">Contact sales</a></div>
</div>
<p>AI add-on: $8 per 1,000 credits. 14-day free trial, no credit card required.</p>
</main></body></html>"""


if __name__ == "__main__":
    sys.exit(main())
