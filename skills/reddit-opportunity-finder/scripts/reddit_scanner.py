#!/usr/bin/env python3
"""
Reddit Opportunity Scanner

Searches Reddit for high-intent threads matching specified keywords,
scores them by opportunity value (recency, engagement, intent signals),
and returns sorted results for SaaS growth teams.

Uses Reddit's public JSON API (no authentication required).

Usage:
    python reddit_scanner.py <keywords> [--subreddit SUBREDDIT] [--time day|week|month] [--min-upvotes N]

Example:
    python reddit_scanner.py "best review management tool"
    python reddit_scanner.py "code review automation" --subreddit SaaS --time week
"""

import json
import re
import sys
import time as time_module
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import quote_plus

try:
    import requests
except ImportError:
    print("Required dependency: requests")
    print("Install with: pip install requests")
    sys.exit(1)


# Reddit API configuration
REDDIT_SEARCH_URL = "https://www.reddit.com/search.json"
USER_AGENT = "saas-growth-skills/1.0 (by /u/ekinciio)"
RATE_LIMIT_SECONDS = 2

# Known good subreddits for SaaS opportunities
GOOD_SUBREDDITS: set[str] = {
    "saas", "startups", "entrepreneur", "smallbusiness", "marketing",
    "seo", "webdev", "artificial", "chatgpt", "digital_marketing",
    "content_marketing", "programming", "devops", "crm", "analytics",
    "projectmanagement", "ecommerce", "emailmarketing", "accounting",
    "nocode", "lowcode", "indiehackers",
}

# Intent signal patterns (questions and recommendation requests)
INTENT_PATTERNS: list[str] = [
    r"\?",
    r"\bbest\b",
    r"\brecommend",
    r"\blooking\s+for\b",
    r"\bsuggestion",
    r"\balternative",
    r"\bwhat\s+(do\s+you|should\s+I)\s+use",
    r"\bwhich\s+(tool|software|platform|app|service)",
    r"\bany(one|body)\s+(use|know|recommend)",
    r"\bhelp\s+me\s+(find|choose|pick)",
    r"\bvs\b",
    r"\bcompar",
]


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


@dataclass
class ScanResult:
    """Complete scan result for a keyword search."""

    keyword: str
    total_found: int = 0
    opportunities: list = field(default_factory=list)
    top_subreddits: list = field(default_factory=list)
    scan_timestamp: str = ""
    errors: list = field(default_factory=list)


def make_reddit_request(
    url: str,
    params: dict,
    timeout: int = 15,
) -> Optional[dict]:
    """Make a rate-limited request to Reddit's JSON API.

    Args:
        url: The API endpoint URL.
        params: Query parameters.
        timeout: Request timeout in seconds.

    Returns:
        JSON response dict or None on failure.
    """
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    }
    try:
        response = requests.get(
            url, params=params, headers=headers, timeout=timeout
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"Reddit API error: {e}")
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

    signal_names = {
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

    for pattern, name in signal_names.items():
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
        ScanResult with scored and sorted opportunities.
    """
    combined_keyword = " OR ".join(keywords)
    result = ScanResult(
        keyword=combined_keyword,
        scan_timestamp=datetime.now(timezone.utc).isoformat(),
    )

    all_threads: list[RedditThread] = []
    subreddit_counts: dict[str, int] = {}

    for keyword in keywords:
        # Build search query
        query = keyword
        if subreddit:
            query = f"{keyword} subreddit:{subreddit}"

        params = {
            "q": query,
            "sort": "new",
            "limit": limit,
            "t": time_filter,
            "type": "link",
        }

        data = make_reddit_request(REDDIT_SEARCH_URL, params)

        if data is None:
            result.errors.append(f"Failed to search for keyword: {keyword}")
            continue

        # Parse results
        children = data.get("data", {}).get("children", [])

        for child in children:
            post = child.get("data", {})

            # Skip if below minimum upvotes
            if post.get("score", 0) < min_upvotes:
                continue

            # Create thread object
            selftext = post.get("selftext", "")
            selftext_preview = selftext[:200] + "..." if len(selftext) > 200 else selftext

            thread = RedditThread(
                title=post.get("title", ""),
                subreddit=post.get("subreddit", ""),
                author=post.get("author", "[deleted]"),
                url=f"https://www.reddit.com{post.get('permalink', '')}",
                score=post.get("score", 0),
                num_comments=post.get("num_comments", 0),
                created_utc=post.get("created_utc", 0),
                selftext_preview=selftext_preview,
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

        # Rate limiting between requests
        if len(keywords) > 1:
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
        "",
    ]

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
    output = asdict(result) if hasattr(result, "__dataclass_fields__") else {
        "keyword": result.keyword,
        "total_found": result.total_found,
        "opportunities": result.opportunities,
        "top_subreddits": result.top_subreddits,
        "scan_timestamp": result.scan_timestamp,
        "errors": result.errors,
    }
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    # If no arguments provided, run demo
    if len(sys.argv) < 2:
        print("Running demo scan: 'best review management tool'")
        print()
        result = search_reddit(
            keywords=["best review management tool"],
            time_filter="week",
        )
        print(format_report(result))
    else:
        main()
