#!/usr/bin/env python3
"""
Reddit Opportunity Scanner

Searches Reddit for high-intent threads matching specified keywords,
scores them by opportunity value (recency, engagement, intent signals),
and returns sorted results for SaaS growth teams.

Reddit access strategy (tried in order):
    1. OAuth API - set REDDIT_CLIENT_ID + REDDIT_CLIENT_SECRET (full data,
       100 queries/min averaged over a 10-minute window on the free tier)
    2. Public JSON API - tried once, but blocked with 403 in most
       environments since Reddit closed unauthenticated API access
    3. Public RSS/Atom search feed - no auth required, but returns no
       upvote or comment counts (results are marked as limited data)

Usage:
    python3 reddit_scanner.py <keywords> [--subreddit SUBREDDIT] [--time day|week|month] [--min-upvotes N]

Example:
    python3 reddit_scanner.py "best review management tool"
    python3 reddit_scanner.py "code review automation" --subreddit SaaS --time week
"""

import json
import os
import re
import sys
import time as time_module
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from html import unescape
from typing import Optional

try:
    import requests
except ImportError:
    print("Required dependency: requests")
    print("Install with: pip install requests")
    sys.exit(1)


# Reddit API configuration
REDDIT_TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
REDDIT_OAUTH_SEARCH_URL = "https://oauth.reddit.com/search"
REDDIT_PUBLIC_SEARCH_URL = "https://www.reddit.com/search.json"
REDDIT_RSS_SEARCH_URL = "https://www.reddit.com/search.rss"
USER_AGENT = "script:saas-growth-skills:1.0 (by /u/ekinciio)"
RATE_LIMIT_SECONDS = 2

ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}

RSS_LIMITED_DATA_NOTE = "limited data - RSS fallback (no upvote/comment counts)"

ACCESS_METHOD_LABELS = {
    "oauth": "Reddit OAuth API (full data)",
    "json": "Reddit public JSON API (full data)",
    "rss": "Reddit RSS fallback (limited data - no upvote/comment counts)",
}

# Known good subreddits for SaaS opportunities
GOOD_SUBREDDITS: set[str] = {
    "saas", "startups", "entrepreneur", "smallbusiness", "marketing",
    "seo", "webdev", "artificial", "chatgpt", "digital_marketing",
    "content_marketing", "programming", "devops", "crm", "analytics",
    "projectmanagement", "ecommerce", "emailmarketing", "accounting",
    "nocode", "lowcode", "indiehackers",
}

# Intent signal patterns mapped to human-readable signal names
INTENT_PATTERNS: dict[str, str] = {
    r"\?": "Question format",
    r"\bbest\b": "Best-of query",
    r"\brecommend": "Recommendation request",
    r"\blooking\s+for\b": "Active search",
    r"\bsuggestion": "Suggestion request",
    r"\balternative": "Alternative search",
    r"\bwhat\s+(do\s+you|should\s+I)\s+use": "Tool selection question",
    r"\bwhich\s+(tool|software|platform|app|service)": "Product comparison",
    r"\bany(one|body)\s+(use|know|recommend)": "Community recommendation",
    r"\bhelp\s+me\s+(find|choose|pick)": "Decision help request",
    r"\bvs\b": "Direct comparison",
    r"\bcompar": "Comparison query",
}


@dataclass
class RedditThread:
    """A single Reddit thread with opportunity metadata."""

    title: str
    subreddit: str
    author: str
    url: str
    score: int
    num_comments: int
    created_utc: float
    selftext_preview: str
    age_hours: float = 0.0
    opportunity_score: int = 0
    intent_signals: list = field(default_factory=list)
    data_note: str = ""


@dataclass
class ScanResult:
    """Complete scan result for a keyword search."""

    keyword: str
    total_found: int = 0
    opportunities: list = field(default_factory=list)
    top_subreddits: list = field(default_factory=list)
    scan_timestamp: str = ""
    access_method: str = ""
    errors: list = field(default_factory=list)


def request_with_retry(
    method: str,
    url: str,
    timeout: int = 15,
    **kwargs,
) -> "requests.Response":
    """Issue an HTTP request, retrying once on 429 (honoring Retry-After).

    Args:
        method: HTTP method ("GET" or "POST").
        url: Request URL.
        timeout: Request timeout in seconds.
        **kwargs: Extra arguments passed to requests.request.

    Returns:
        The final requests.Response (may still be an error response).
    """
    response = requests.request(method, url, timeout=timeout, **kwargs)
    if response.status_code == 429:
        retry_after = response.headers.get("Retry-After")
        try:
            delay = min(max(float(retry_after), 1.0), 60.0)
        except (TypeError, ValueError):
            delay = 5.0
        print(f"  Rate limited (429), retrying in {delay:.0f}s...")
        time_module.sleep(delay)
        response = requests.request(method, url, timeout=timeout, **kwargs)
    return response


def get_reddit_oauth_token(errors: list) -> Optional[str]:
    """Fetch an application-only OAuth token if credentials are set.

    Reads REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET from the environment
    and exchanges them for a bearer token via the client_credentials grant.

    Args:
        errors: Error list to append failures to.

    Returns:
        Bearer token string, or None when credentials are missing or invalid.
    """
    client_id = os.environ.get("REDDIT_CLIENT_ID")
    client_secret = os.environ.get("REDDIT_CLIENT_SECRET")
    if not client_id or not client_secret:
        return None
    try:
        response = request_with_retry(
            "POST",
            REDDIT_TOKEN_URL,
            auth=(client_id, client_secret),
            data={"grant_type": "client_credentials"},
            headers={"User-Agent": USER_AGENT},
        )
        response.raise_for_status()
        token = response.json().get("access_token")
        if not token:
            raise ValueError("no access_token in response")
        return token
    except (requests.RequestException, ValueError) as e:
        errors.append(
            f"Reddit OAuth token request failed: {e} "
            f"(check REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET)"
        )
        return None


def iso_to_epoch(timestamp: str) -> float:
    """Convert an ISO 8601 timestamp string to a Unix epoch float."""
    if not timestamp:
        return 0.0
    try:
        return datetime.fromisoformat(timestamp.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def parse_reddit_json_posts(data: dict) -> list[dict]:
    """Normalize a Reddit JSON API search response into post dicts.

    Args:
        data: Parsed JSON response from the search endpoint.

    Returns:
        List of normalized post dicts.
    """
    posts = []
    for child in data.get("data", {}).get("children", []):
        post = child.get("data", {})
        posts.append({
            "title": post.get("title", ""),
            "subreddit": post.get("subreddit", ""),
            "author": post.get("author", "[deleted]"),
            "url": f"https://www.reddit.com{post.get('permalink', '')}",
            "score": post.get("score", 0),
            "num_comments": post.get("num_comments", 0),
            "created_utc": post.get("created_utc", 0),
            "selftext": post.get("selftext", ""),
        })
    return posts


def parse_reddit_rss_posts(xml_text: str) -> list[dict]:
    """Parse a Reddit search Atom feed into normalized post dicts.

    The RSS feed carries title, URL, author, subreddit, and timestamp but
    NOT upvote or comment counts, so score and num_comments are None.

    Args:
        xml_text: Raw Atom XML from the search.rss endpoint.

    Returns:
        List of normalized post dicts (score/num_comments set to None).
    """
    posts = []
    root = ET.fromstring(xml_text)
    for entry in root.findall("atom:entry", ATOM_NS):
        entry_id = entry.findtext("atom:id", default="", namespaces=ATOM_NS)
        if not entry_id.startswith("t3_"):
            continue  # keep posts only (skip subreddit/user entries)

        link = entry.find("atom:link", ATOM_NS)
        url = link.get("href", "") if link is not None else ""
        category = entry.find("atom:category", ATOM_NS)
        subreddit = category.get("term", "") if category is not None else ""
        author = entry.findtext(
            "atom:author/atom:name", default="", namespaces=ATOM_NS
        )
        published = (
            entry.findtext("atom:published", default="", namespaces=ATOM_NS)
            or entry.findtext("atom:updated", default="", namespaces=ATOM_NS)
        )
        content_html = entry.findtext(
            "atom:content", default="", namespaces=ATOM_NS
        ) or ""
        body = unescape(re.sub(r"<[^>]+>", " ", content_html))
        body = re.sub(r"\s+", " ", body).strip()

        posts.append({
            "title": entry.findtext("atom:title", default="", namespaces=ATOM_NS),
            "subreddit": subreddit,
            "author": author.replace("/u/", "") or "[unknown]",
            "url": url,
            "score": None,
            "num_comments": None,
            "created_utc": iso_to_epoch(published),
            "selftext": body,
        })
    return posts


def fetch_reddit_posts(
    query: str,
    time_filter: str,
    limit: int,
    state: dict,
    errors: list,
) -> Optional[list[dict]]:
    """Fetch Reddit posts for a query using the tiered access strategy.

    Order: OAuth API (if credentials set) -> public JSON API (tried once,
    usually 403) -> public RSS feed (limited data).

    Args:
        query: Search query string.
        time_filter: Time range filter (hour, day, week, month, year, all).
        limit: Maximum results to request.
        state: Mutable dict shared across keywords with keys
            "token" (OAuth bearer or None), "mode" (resolved access method),
            and "json_blocked" (True once the public JSON API returned 403).
        errors: Error list to append failures to.

    Returns:
        List of normalized post dicts, or None if every method failed.
    """
    params = {
        "q": query,
        "sort": "new",
        "limit": limit,
        "t": time_filter,
        "type": "link",
    }
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}

    # 1) OAuth API (preferred - full data)
    if state.get("token"):
        oauth_headers = dict(headers)
        oauth_headers["Authorization"] = f"bearer {state['token']}"
        try:
            response = request_with_retry(
                "GET", REDDIT_OAUTH_SEARCH_URL,
                params=params, headers=oauth_headers,
            )
            response.raise_for_status()
            state["mode"] = "oauth"
            return parse_reddit_json_posts(response.json())
        except (requests.RequestException, ValueError) as e:
            errors.append(f"Reddit OAuth search failed for '{query}': {e}")

    # 2) Public JSON API (tried once; blocked with 403 in most environments)
    if not state.get("json_blocked"):
        try:
            response = request_with_retry(
                "GET", REDDIT_PUBLIC_SEARCH_URL,
                params=params, headers=headers,
            )
            response.raise_for_status()
            state["mode"] = "json"
            return parse_reddit_json_posts(response.json())
        except (requests.RequestException, ValueError) as e:
            status = getattr(getattr(e, "response", None), "status_code", None)
            if status == 403:
                state["json_blocked"] = True
                msg = (
                    "Reddit public JSON API blocked (403). Set REDDIT_CLIENT_ID "
                    "and REDDIT_CLIENT_SECRET for OAuth access. Falling back to "
                    "the RSS feed (no upvote/comment data)."
                )
                print(f"  ! {msg}")
                if msg not in errors:
                    errors.append(msg)
            else:
                errors.append(f"Reddit JSON search failed for '{query}': {e}")

    # 3) RSS/Atom feed fallback (no auth, limited data)
    try:
        response = request_with_retry(
            "GET", REDDIT_RSS_SEARCH_URL,
            params=params, headers={"User-Agent": USER_AGENT},
        )
        response.raise_for_status()
        state["mode"] = "rss"
        return parse_reddit_rss_posts(response.text)
    except (requests.RequestException, ET.ParseError) as e:
        errors.append(f"Reddit RSS fallback failed for '{query}': {e}")

    return None


def calculate_age_hours(created_utc: float) -> float:
    """Calculate the age of a post in hours.

    Args:
        created_utc: Unix timestamp of post creation.

    Returns:
        Age in hours.
    """
    now = datetime.now(timezone.utc).timestamp()
    return (now - created_utc) / 3600


def detect_intent_signals(title: str, selftext: str) -> list[str]:
    """Detect intent signals in the thread title and body.

    Args:
        title: Thread title.
        selftext: Thread body text.

    Returns:
        List of detected intent signal descriptions.
    """
    combined_text = f"{title} {selftext}".lower()
    signals = []

    for pattern, name in INTENT_PATTERNS.items():
        if re.search(pattern, combined_text):
            signals.append(name)

    return signals


def calculate_opportunity_score(thread: RedditThread) -> int:
    """Calculate the opportunity score for a Reddit thread.

    Scoring breakdown:
        - Recency <24h: +30, <72h: +20, <1 week: +10
        - Engagement >50 upvotes: +20, >20: +10, >5: +5
        - Comments >20: +15, >5: +10
        - Question/recommendation format: +20
        - Known good subreddit: +15

    Note: threads fetched via the RSS fallback have unknown upvote and
    comment counts (stored as 0), so their engagement components score 0.

    Args:
        thread: The Reddit thread to score.

    Returns:
        Opportunity score from 0 to 100.
    """
    score = 0

    # Recency scoring
    if thread.age_hours < 24:
        score += 30
    elif thread.age_hours < 72:
        score += 20
    elif thread.age_hours < 168:  # 1 week
        score += 10

    # Engagement scoring (upvotes)
    if thread.score > 50:
        score += 20
    elif thread.score > 20:
        score += 10
    elif thread.score > 5:
        score += 5

    # Comment scoring
    if thread.num_comments > 20:
        score += 15
    elif thread.num_comments > 5:
        score += 10

    # Intent signal scoring
    if thread.intent_signals:
        score += 20

    # Known good subreddit scoring
    if thread.subreddit.lower() in GOOD_SUBREDDITS:
        score += 15

    return min(score, 100)


def search_reddit(
    keywords: list[str],
    subreddit: Optional[str] = None,
    time_filter: str = "week",
    min_upvotes: int = 0,
    limit: int = 25,
) -> ScanResult:
    """Search Reddit for threads matching the given keywords.

    Args:
        keywords: List of keyword strings to search for.
        subreddit: Optional subreddit to restrict search to.
        time_filter: Time range filter (hour, day, week, month, year, all).
        min_upvotes: Minimum upvote threshold.
        limit: Maximum results per keyword search.

    Returns:
        ScanResult with scored and sorted opportunities. Failures are
        recorded in ScanResult.errors - never silently dropped.
    """
    combined_keyword = " OR ".join(keywords)
    result = ScanResult(
        keyword=combined_keyword,
        scan_timestamp=datetime.now(timezone.utc).isoformat(),
    )

    all_threads: list[RedditThread] = []
    subreddit_counts: dict[str, int] = {}

    # Resolve OAuth once; access mode is shared across keywords
    state = {
        "token": get_reddit_oauth_token(result.errors),
        "mode": None,
        "json_blocked": False,
    }

    for i, keyword in enumerate(keywords):
        # Build search query
        query = keyword
        if subreddit:
            query = f"{keyword} subreddit:{subreddit}"

        posts = fetch_reddit_posts(query, time_filter, limit, state, result.errors)

        if posts is None:
            result.errors.append(
                f"All Reddit access methods failed for keyword: {keyword}"
            )
            posts = []

        for post in posts:
            # Skip if below minimum upvotes (RSS results have unknown
            # scores, so the filter is not applied to them)
            if post["score"] is not None and post["score"] < min_upvotes:
                continue

            # Create thread object
            selftext = post["selftext"]
            selftext_preview = selftext[:200] + "..." if len(selftext) > 200 else selftext

            thread = RedditThread(
                title=post["title"],
                subreddit=post["subreddit"],
                author=post["author"],
                url=post["url"],
                score=post["score"] if post["score"] is not None else 0,
                num_comments=(
                    post["num_comments"] if post["num_comments"] is not None else 0
                ),
                created_utc=post["created_utc"],
                selftext_preview=selftext_preview,
                data_note=RSS_LIMITED_DATA_NOTE if post["score"] is None else "",
            )

            # Calculate age
            thread.age_hours = round(calculate_age_hours(thread.created_utc), 1)

            # Detect intent signals
            thread.intent_signals = detect_intent_signals(thread.title, selftext)

            # Calculate opportunity score
            thread.opportunity_score = calculate_opportunity_score(thread)

            all_threads.append(thread)

            # Count subreddit occurrences
            sub = thread.subreddit.lower()
            subreddit_counts[sub] = subreddit_counts.get(sub, 0) + 1

        # Rate limiting between keyword requests (not after the last one)
        if i < len(keywords) - 1:
            time_module.sleep(RATE_LIMIT_SECONDS)

    # Deduplicate by URL
    seen_urls: set[str] = set()
    unique_threads: list[RedditThread] = []
    for thread in all_threads:
        if thread.url not in seen_urls:
            seen_urls.add(thread.url)
            unique_threads.append(thread)

    # Sort by opportunity score descending
    unique_threads.sort(key=lambda t: t.opportunity_score, reverse=True)

    result.total_found = len(unique_threads)
    result.opportunities = [asdict(t) for t in unique_threads]
    result.access_method = state["mode"] or ""

    # Top subreddits
    sorted_subs = sorted(subreddit_counts.items(), key=lambda x: x[1], reverse=True)
    result.top_subreddits = [
        {"subreddit": f"r/{sub}", "count": count}
        for sub, count in sorted_subs[:10]
    ]

    return result


def format_report(result: ScanResult) -> str:
    """Format the scan result as a readable report.

    Args:
        result: The completed scan result.

    Returns:
        Formatted report string.
    """
    lines = [
        "=" * 70,
        "REDDIT OPPORTUNITY SCAN",
        "=" * 70,
        f"Keywords: {result.keyword}",
        f"Scan time: {result.scan_timestamp}",
        f"Total threads found: {result.total_found}",
    ]

    if result.access_method:
        label = ACCESS_METHOD_LABELS.get(result.access_method, result.access_method)
        lines.append(f"Data source: {label}")

    if result.total_found == 0 and result.errors:
        lines.append("")
        lines.append("!!! SCAN FAILED - no results retrieved. See Errors below.")
    elif result.errors:
        lines.append(f"Warnings/errors during scan: {len(result.errors)} (see Errors below)")

    lines.append("")

    if result.top_subreddits:
        lines.append("--- Top Subreddits ---")
        for sub_info in result.top_subreddits:
            lines.append(f"  {sub_info['subreddit']}: {sub_info['count']} threads")
        lines.append("")

    lines.append("--- Top Opportunities ---")
    lines.append("")

    for i, opp in enumerate(result.opportunities[:15], 1):
        age_str = f"{opp['age_hours']:.0f}h ago"
        if opp["age_hours"] > 48:
            age_str = f"{opp['age_hours'] / 24:.1f}d ago"

        lines.extend([
            f"  #{i} [Score: {opp['opportunity_score']}/100]",
            f"  Title: {opp['title']}",
            f"  r/{opp['subreddit']} | {opp['score']} upvotes | "
            f"{opp['num_comments']} comments | {age_str}",
            f"  URL: {opp['url']}",
        ])

        if opp["intent_signals"]:
            lines.append(f"  Intent: {', '.join(opp['intent_signals'])}")

        if opp["data_note"]:
            lines.append(f"  Note: {opp['data_note']}")

        lines.append("")

    if result.errors:
        lines.extend(["--- Errors ---"])
        for error in result.errors:
            lines.append(f"  ! {error}")

    lines.append("=" * 70)
    return "\n".join(lines)


def main() -> None:
    """Run the Reddit scanner from the command line."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Scan Reddit for SaaS growth opportunities"
    )
    parser.add_argument(
        "keywords",
        type=str,
        help="Keywords to search for (comma-separated for multiple)",
    )
    parser.add_argument(
        "--subreddit",
        type=str,
        default=None,
        help="Restrict search to a specific subreddit",
    )
    parser.add_argument(
        "--time",
        type=str,
        default="week",
        choices=["hour", "day", "week", "month", "year", "all"],
        help="Time filter for results (default: week)",
    )
    parser.add_argument(
        "--min-upvotes",
        type=int,
        default=0,
        help="Minimum upvote threshold (default: 0)",
    )

    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(1)

    args = parser.parse_args()

    # Parse comma-separated keywords
    keywords = [kw.strip() for kw in args.keywords.split(",") if kw.strip()]

    print(f"Scanning Reddit for: {', '.join(keywords)}")
    if args.subreddit:
        print(f"Subreddit filter: r/{args.subreddit}")
    print(f"Time range: {args.time}")
    print("Searching...")
    print()

    result = search_reddit(
        keywords=keywords,
        subreddit=args.subreddit,
        time_filter=args.time,
        min_upvotes=args.min_upvotes,
    )

    # Print formatted report
    print(format_report(result))

    # Also output JSON for programmatic use
    print("\n--- JSON Output ---")
    print(json.dumps(asdict(result), indent=2))


if __name__ == "__main__":
    main()
