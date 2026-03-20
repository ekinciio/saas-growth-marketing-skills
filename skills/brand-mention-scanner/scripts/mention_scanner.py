#!/usr/bin/env python3
"""
Brand Mention Scanner

Scans Reddit, Hacker News, and GitHub for brand or product mentions.
Aggregates results across platforms, classifies sentiment, and generates
a comprehensive mention report.

All APIs are public and require no authentication.

Usage:
    python mention_scanner.py <brand_name> [--platforms reddit,hn,github] [--time week]

Example:
    python mention_scanner.py "vercel"
    python mention_scanner.py "supabase" --platforms reddit,hn
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


# Configuration
USER_AGENT = "saas-growth-skills/1.0 (by /u/ekinciio)"
RATE_LIMIT_SECONDS = 2

# Sentiment keywords
POSITIVE_KEYWORDS: list[str] = [
    "love", "great", "best", "amazing", "awesome", "excellent",
    "fantastic", "wonderful", "brilliant", "impressive", "perfect",
    "recommend", "solid", "fast", "reliable",
]

NEGATIVE_KEYWORDS: list[str] = [
    "hate", "worst", "terrible", "bug", "broken", "awful",
    "horrible", "sucks", "slow", "crash", "frustrat", "disappoint",
    "unusable", "nightmare", "regret",
]

QUESTION_PATTERNS: list[str] = [
    r"\?", r"how\s+to", r"anyone\s+know", r"help\s+with",
    r"can\s+I", r"is\s+it\s+possible", r"does\s+anyone",
]

COMPARISON_PATTERNS: list[str] = [
    r"\bvs\b", r"\bversus\b", r"compared\s+to", r"alternative",
    r"switch\s+from", r"migrate\s+from", r"better\s+than",
]


@dataclass
class Mention:
    """A single brand mention from any platform."""

    platform: str
    title: str
    url: str
    author: str
    score: int = 0
    num_comments: int = 0
    created_at: str = ""
    text_preview: str = ""
    sentiment: str = "neutral"
    mention_type: str = "direct"


@dataclass
class SentimentSummary:
    """Aggregated sentiment analysis."""

    positive: int = 0
    negative: int = 0
    neutral: int = 0
    question: int = 0
    comparison: int = 0


@dataclass
class ScanReport:
    """Complete multi-platform scan report."""

    brand_name: str
    scan_date: str = ""
    total_mentions: int = 0
    platform_breakdown: dict = field(default_factory=dict)
    sentiment_summary: dict = field(default_factory=dict)
    top_mentions: list = field(default_factory=list)
    opportunities: list = field(default_factory=list)
    recommendations: list = field(default_factory=list)
    errors: list = field(default_factory=list)


def classify_sentiment(text: str) -> str:
    """Classify the sentiment of a text snippet.

    Uses keyword-based heuristics to classify text into:
    positive, negative, question, comparison, or neutral.

    Args:
        text: The text to classify.

    Returns:
        Sentiment label string.
    """
    text_lower = text.lower()

    # Check for comparison first (specific context)
    for pattern in COMPARISON_PATTERNS:
        if re.search(pattern, text_lower):
            return "comparison"

    # Check for question
    for pattern in QUESTION_PATTERNS:
        if re.search(pattern, text_lower):
            return "question"

    # Count positive and negative signals
    positive_count = sum(1 for kw in POSITIVE_KEYWORDS if kw in text_lower)
    negative_count = sum(1 for kw in NEGATIVE_KEYWORDS if kw in text_lower)

    if positive_count > negative_count and positive_count > 0:
        return "positive"
    elif negative_count > positive_count and negative_count > 0:
        return "negative"

    return "neutral"


def scan_reddit(brand_name: str, time_filter: str = "month") -> list[Mention]:
    """Scan Reddit for brand mentions.

    Args:
        brand_name: The brand name to search for.
        time_filter: Time range (hour, day, week, month, year, all).

    Returns:
        List of Mention objects from Reddit.
    """
    mentions = []
    url = "https://www.reddit.com/search.json"
    params = {
        "q": f'"{brand_name}"',
        "sort": "new",
        "limit": 50,
        "t": time_filter,
        "type": "link",
    }
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    }

    try:
        response = requests.get(url, params=params, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as e:
        print(f"Reddit scan error: {e}")
        return mentions

    children = data.get("data", {}).get("children", [])

    for child in children:
        post = child.get("data", {})
        title = post.get("title", "")
        selftext = post.get("selftext", "")
        combined_text = f"{title} {selftext}"
        text_preview = selftext[:150] + "..." if len(selftext) > 150 else selftext

        created_utc = post.get("created_utc", 0)
        created_str = ""
        if created_utc:
            created_str = datetime.fromtimestamp(
                created_utc, tz=timezone.utc
            ).isoformat()

        mention = Mention(
            platform="reddit",
            title=title,
            url=f"https://www.reddit.com{post.get('permalink', '')}",
            author=post.get("author", "[deleted]"),
            score=post.get("score", 0),
            num_comments=post.get("num_comments", 0),
            created_at=created_str,
            text_preview=text_preview,
            sentiment=classify_sentiment(combined_text),
        )
        mentions.append(mention)

    return mentions


def scan_hacker_news(brand_name: str) -> list[Mention]:
    """Scan Hacker News for brand mentions using the Algolia API.

    Searches both stories and comments endpoints.

    Args:
        brand_name: The brand name to search for.

    Returns:
        List of Mention objects from Hacker News.
    """
    mentions = []

    # Search stories
    stories_url = "https://hn.algolia.com/api/v1/search"
    params = {
        "query": f'"{brand_name}"',
        "tags": "story",
        "hitsPerPage": 30,
    }

    try:
        response = requests.get(stories_url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as e:
        print(f"HN stories scan error: {e}")
        return mentions

    for hit in data.get("hits", []):
        title = hit.get("title", "")
        story_text = hit.get("story_text") or ""
        combined_text = f"{title} {story_text}"

        hn_url = f"https://news.ycombinator.com/item?id={hit.get('objectID', '')}"

        mention = Mention(
            platform="hn",
            title=title,
            url=hit.get("url") or hn_url,
            author=hit.get("author", "unknown"),
            score=hit.get("points", 0) or 0,
            num_comments=hit.get("num_comments", 0) or 0,
            created_at=hit.get("created_at", ""),
            text_preview=story_text[:150] + "..." if len(story_text) > 150 else story_text,
            sentiment=classify_sentiment(combined_text),
        )
        mentions.append(mention)

    time_module.sleep(RATE_LIMIT_SECONDS)

    # Search comments
    comments_url = "https://hn.algolia.com/api/v1/search"
    comment_params = {
        "query": f'"{brand_name}"',
        "tags": "comment",
        "hitsPerPage": 20,
    }

    try:
        response = requests.get(comments_url, params=comment_params, timeout=15)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as e:
        print(f"HN comments scan error: {e}")
        return mentions

    for hit in data.get("hits", []):
        comment_text = hit.get("comment_text", "")
        # Strip HTML tags for clean text
        clean_text = re.sub(r"<[^>]+>", "", comment_text)
        text_preview = clean_text[:150] + "..." if len(clean_text) > 150 else clean_text

        story_id = hit.get("story_id", hit.get("objectID", ""))
        hn_url = f"https://news.ycombinator.com/item?id={story_id}"

        mention = Mention(
            platform="hn",
            title=f"Comment on: {hit.get('story_title', 'Unknown thread')}",
            url=hn_url,
            author=hit.get("author", "unknown"),
            score=hit.get("points", 0) or 0,
            num_comments=0,
            created_at=hit.get("created_at", ""),
            text_preview=text_preview,
            sentiment=classify_sentiment(clean_text),
            mention_type="comment",
        )
        mentions.append(mention)

    return mentions


def scan_github(brand_name: str) -> list[Mention]:
    """Scan GitHub for repositories related to the brand.

    Args:
        brand_name: The brand name to search for.

    Returns:
        List of Mention objects from GitHub.
    """
    mentions = []
    url = "https://api.github.com/search/repositories"
    params = {
        "q": brand_name,
        "sort": "stars",
        "order": "desc",
        "per_page": 30,
    }
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": USER_AGENT,
    }

    try:
        response = requests.get(url, params=params, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as e:
        print(f"GitHub scan error: {e}")
        return mentions

    for repo in data.get("items", []):
        description = repo.get("description") or ""

        mention = Mention(
            platform="github",
            title=repo.get("full_name", ""),
            url=repo.get("html_url", ""),
            author=repo.get("owner", {}).get("login", "unknown"),
            score=repo.get("stargazers_count", 0),
            num_comments=repo.get("open_issues_count", 0),
            created_at=repo.get("updated_at", ""),
            text_preview=description[:150] + "..." if len(description) > 150 else description,
            sentiment=classify_sentiment(f"{repo.get('full_name', '')} {description}"),
            mention_type="repository",
        )
        mentions.append(mention)

    return mentions


def aggregate_sentiment(mentions: list[Mention]) -> dict:
    """Aggregate sentiment counts across all mentions.

    Args:
        mentions: List of all mentions.

    Returns:
        Dict with sentiment category counts.
    """
    summary = SentimentSummary()

    for mention in mentions:
        if mention.sentiment == "positive":
            summary.positive += 1
        elif mention.sentiment == "negative":
            summary.negative += 1
        elif mention.sentiment == "question":
            summary.question += 1
        elif mention.sentiment == "comparison":
            summary.comparison += 1
        else:
            summary.neutral += 1

    return asdict(summary)


def find_opportunities(mentions: list[Mention]) -> list[dict]:
    """Find unresponded opportunities from mentions.

    Opportunities are mentions that are questions, have low comment counts,
    or have negative sentiment that could be addressed.

    Args:
        mentions: List of all mentions.

    Returns:
        List of opportunity dicts.
    """
    opportunities = []

    for mention in mentions:
        is_opportunity = False
        reason = ""

        if mention.sentiment == "question":
            is_opportunity = True
            reason = "Unanswered question about your brand"
        elif mention.sentiment == "negative":
            is_opportunity = True
            reason = "Negative mention - opportunity to address concerns"
        elif mention.sentiment == "comparison":
            is_opportunity = True
            reason = "Brand comparison - opportunity to highlight strengths"
        elif mention.num_comments == 0 and mention.score > 0:
            is_opportunity = True
            reason = "Engaged post with no comments - opportunity to respond"

        if is_opportunity:
            opportunities.append({
                "platform": mention.platform,
                "title": mention.title,
                "url": mention.url,
                "reason": reason,
                "sentiment": mention.sentiment,
                "score": mention.score,
            })

    # Sort by score descending
    opportunities.sort(key=lambda x: x.get("score", 0), reverse=True)
    return opportunities[:15]


def generate_recommendations(
    mentions: list[Mention],
    sentiment: dict,
    platform_counts: dict,
) -> list[str]:
    """Generate actionable recommendations based on scan results.

    Args:
        mentions: All mentions found.
        sentiment: Aggregated sentiment summary.
        platform_counts: Mention counts per platform.

    Returns:
        List of recommendation strings.
    """
    recs = []

    total = len(mentions)
    if total == 0:
        recs.append(
            "No mentions found. Consider building initial presence through "
            "community engagement, content marketing, and strategic product launches."
        )
        return recs

    # Sentiment-based recommendations
    if sentiment.get("negative", 0) > sentiment.get("positive", 0):
        recs.append(
            "Negative sentiment outweighs positive. Prioritize responding to "
            "negative mentions with helpful, professional responses. Address "
            "specific complaints with action items."
        )
    elif sentiment.get("positive", 0) > 0:
        recs.append(
            "Positive sentiment detected. Amplify these mentions by thanking "
            "advocates, sharing their feedback (with permission), and nurturing "
            "relationships with brand champions."
        )

    if sentiment.get("question", 0) > 0:
        recs.append(
            f"Found {sentiment['question']} question mentions. Respond to these "
            f"promptly with helpful answers. Questions represent high-intent "
            f"opportunities to demonstrate expertise."
        )

    if sentiment.get("comparison", 0) > 0:
        recs.append(
            f"Found {sentiment['comparison']} comparison mentions. Monitor these "
            f"closely and ensure your product's strengths are represented "
            f"accurately in competitive discussions."
        )

    # Platform-specific recommendations
    if platform_counts.get("reddit", 0) > 0:
        recs.append(
            "Active Reddit presence detected. Maintain authentic engagement "
            "following the 10% self-promotion rule. Focus on providing value "
            "in discussions rather than direct promotion."
        )

    if platform_counts.get("hn", 0) > 0:
        recs.append(
            "Hacker News mentions found. HN audiences value technical depth "
            "and transparency. Engage with substantive, technical responses."
        )

    if platform_counts.get("github", 0) > 0:
        recs.append(
            "GitHub presence detected. Ensure your repositories are well-documented, "
            "issues are responded to promptly, and community contributions "
            "are acknowledged."
        )

    return recs


def scan_brand(
    brand_name: str,
    platforms: Optional[list[str]] = None,
    time_filter: str = "month",
) -> ScanReport:
    """Perform a complete brand mention scan across all platforms.

    Args:
        brand_name: The brand or product name to search for.
        platforms: List of platforms to scan (default: all three).
        time_filter: Time range for Reddit results.

    Returns:
        ScanReport with aggregated results.
    """
    if platforms is None:
        platforms = ["reddit", "hn", "github"]

    report = ScanReport(
        brand_name=brand_name,
        scan_date=datetime.now(timezone.utc).isoformat(),
    )

    all_mentions: list[Mention] = []
    platform_counts: dict[str, int] = {}

    # Scan Reddit
    if "reddit" in platforms:
        print("  Scanning Reddit...")
        reddit_mentions = scan_reddit(brand_name, time_filter)
        all_mentions.extend(reddit_mentions)
        platform_counts["reddit"] = len(reddit_mentions)
        time_module.sleep(RATE_LIMIT_SECONDS)

    # Scan Hacker News
    if "hn" in platforms:
        print("  Scanning Hacker News...")
        hn_mentions = scan_hacker_news(brand_name)
        all_mentions.extend(hn_mentions)
        platform_counts["hn"] = len(hn_mentions)
        time_module.sleep(RATE_LIMIT_SECONDS)

    # Scan GitHub
    if "github" in platforms:
        print("  Scanning GitHub...")
        github_mentions = scan_github(brand_name)
        all_mentions.extend(github_mentions)
        platform_counts["github"] = len(github_mentions)

    # Aggregate results
    report.total_mentions = len(all_mentions)
    report.platform_breakdown = platform_counts

    # Sentiment analysis
    report.sentiment_summary = aggregate_sentiment(all_mentions)

    # Top mentions (sorted by score)
    sorted_mentions = sorted(all_mentions, key=lambda m: m.score, reverse=True)
    report.top_mentions = [asdict(m) for m in sorted_mentions[:20]]

    # Opportunities
    report.opportunities = find_opportunities(all_mentions)

    # Recommendations
    report.recommendations = generate_recommendations(
        all_mentions,
        report.sentiment_summary,
        platform_counts,
    )

    return report


def format_report(report: ScanReport) -> str:
    """Format the scan report as a readable output.

    Args:
        report: The completed scan report.

    Returns:
        Formatted report string.
    """
    lines = [
        "=" * 70,
        "BRAND MENTION SCAN REPORT",
        "=" * 70,
        f"Brand: {report.brand_name}",
        f"Scan date: {report.scan_date}",
        f"Total mentions: {report.total_mentions}",
        "",
        "--- Platform Breakdown ---",
    ]

    for platform, count in report.platform_breakdown.items():
        platform_name = {"reddit": "Reddit", "hn": "Hacker News", "github": "GitHub"}.get(
            platform, platform
        )
        lines.append(f"  {platform_name}: {count} mentions")

    lines.extend(["", "--- Sentiment Summary ---"])
    sentiment = report.sentiment_summary
    lines.append(f"  Positive: {sentiment.get('positive', 0)}")
    lines.append(f"  Negative: {sentiment.get('negative', 0)}")
    lines.append(f"  Neutral: {sentiment.get('neutral', 0)}")
    lines.append(f"  Questions: {sentiment.get('question', 0)}")
    lines.append(f"  Comparisons: {sentiment.get('comparison', 0)}")

    lines.extend(["", "--- Top Mentions ---", ""])

    for i, mention in enumerate(report.top_mentions[:10], 1):
        platform_label = {
            "reddit": "Reddit", "hn": "HN", "github": "GitHub"
        }.get(mention["platform"], mention["platform"])

        lines.extend([
            f"  #{i} [{platform_label}] [{mention['sentiment']}]",
            f"  {mention['title']}",
            f"  Score: {mention['score']} | Comments: {mention['num_comments']}",
            f"  URL: {mention['url']}",
            "",
        ])

    if report.opportunities:
        lines.extend(["--- Opportunities ---", ""])
        for i, opp in enumerate(report.opportunities[:10], 1):
            lines.extend([
                f"  #{i} [{opp['platform']}] {opp['reason']}",
                f"  {opp['title']}",
                f"  URL: {opp['url']}",
                "",
            ])

    lines.extend(["--- Recommendations ---"])
    for i, rec in enumerate(report.recommendations, 1):
        lines.append(f"  {i}. {rec}")

    lines.append("=" * 70)
    return "\n".join(lines)


def main() -> None:
    """Run the mention scanner from the command line."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Scan multiple platforms for brand mentions"
    )
    parser.add_argument(
        "brand_name",
        type=str,
        help="Brand or product name to search for",
    )
    parser.add_argument(
        "--platforms",
        type=str,
        default="reddit,hn,github",
        help="Comma-separated platforms to scan (default: reddit,hn,github)",
    )
    parser.add_argument(
        "--time",
        type=str,
        default="month",
        choices=["hour", "day", "week", "month", "year", "all"],
        help="Time filter for Reddit results (default: month)",
    )

    args = parser.parse_args()

    platforms = [p.strip() for p in args.platforms.split(",") if p.strip()]

    print(f"Scanning for brand: {args.brand_name}")
    print(f"Platforms: {', '.join(platforms)}")
    print()

    report = scan_brand(
        brand_name=args.brand_name,
        platforms=platforms,
        time_filter=args.time,
    )

    # Print formatted report
    print(format_report(report))

    # Also output JSON for programmatic use
    print("\n--- JSON Output ---")
    print(json.dumps(asdict(report) if hasattr(report, "__dataclass_fields__") else {
        "brand_name": report.brand_name,
        "scan_date": report.scan_date,
        "total_mentions": report.total_mentions,
        "platform_breakdown": report.platform_breakdown,
        "sentiment_summary": report.sentiment_summary,
        "top_mentions": report.top_mentions,
        "opportunities": report.opportunities,
        "recommendations": report.recommendations,
        "errors": report.errors,
    }, indent=2))


if __name__ == "__main__":
    # If no arguments provided, run demo
    if len(sys.argv) < 2:
        print("Running demo scan for: vercel")
        print()
        report = scan_brand(brand_name="vercel")
        print(format_report(report))
    else:
        main()
