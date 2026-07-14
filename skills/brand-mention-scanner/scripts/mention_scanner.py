#!/usr/bin/env python3
"""
Brand Mention Scanner

Scans Reddit, Hacker News, and GitHub for brand or product mentions.
Aggregates results across platforms, classifies sentiment, and generates
a comprehensive mention report.

Hacker News and GitHub work without authentication. Reddit requires
OAuth credentials (REDDIT_CLIENT_ID + REDDIT_CLIENT_SECRET) for full
data; without them the scanner falls back to Reddit's public RSS feed,
which returns no upvote or comment counts. Set GITHUB_TOKEN for a
higher GitHub search rate limit. Per-platform failures are recorded in
the report's errors list and surfaced in the formatted output.

Usage:
    python3 mention_scanner.py <brand_name> [--platforms reddit,hn,github] [--time week]

Example:
    python3 mention_scanner.py "vercel"
    python3 mention_scanner.py "supabase" --platforms reddit,hn
"""

import json
import os
import re
import sys
import time as time_module
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from html import unescape
from typing import Optional

try:
    import requests
except ImportError:
    print("Required dependency: requests")
    print("Install with: pip install requests")
    sys.exit(1)


# Configuration
USER_AGENT = "script:saas-growth-skills:1.0 (by /u/ekinciio)"
RATE_LIMIT_SECONDS = 2

REDDIT_TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
REDDIT_OAUTH_SEARCH_URL = "https://oauth.reddit.com/search"
REDDIT_PUBLIC_SEARCH_URL = "https://www.reddit.com/search.json"
REDDIT_RSS_SEARCH_URL = "https://www.reddit.com/search.rss"

ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}

# --time filter mapped to a lookback window in seconds ("all" = no limit)
TIME_FILTER_SECONDS: dict[str, int] = {
    "hour": 3600,
    "day": 86400,
    "week": 604800,
    "month": 2592000,
    "year": 31536000,
}

# Sentiment keywords (matched at word boundaries; entries act as prefixes,
# e.g. "recommend" also matches "recommendation")
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


def time_filter_cutoff(time_filter: str) -> Optional[datetime]:
    """Return the UTC datetime cutoff for a --time filter, or None for 'all'."""
    seconds = TIME_FILTER_SECONDS.get(time_filter)
    if seconds is None:
        return None
    return datetime.now(timezone.utc) - timedelta(seconds=seconds)


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

    # Count positive and negative signals (word-boundary matches so
    # e.g. "bug" does not match inside "debug")
    positive_count = sum(
        1 for kw in POSITIVE_KEYWORDS
        if re.search(r"\b" + re.escape(kw), text_lower)
    )
    negative_count = sum(
        1 for kw in NEGATIVE_KEYWORDS
        if re.search(r"\b" + re.escape(kw), text_lower)
    )

    if positive_count > negative_count and positive_count > 0:
        return "positive"
    elif negative_count > positive_count and negative_count > 0:
        return "negative"

    return "neutral"


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
            f"reddit: OAuth token request failed - {e} "
            f"(check REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET)"
        )
        return None


def parse_reddit_rss_entries(xml_text: str) -> list[dict]:
    """Parse a Reddit search Atom feed into simple entry dicts.

    The RSS feed carries title, URL, author, subreddit, and timestamp but
    NOT upvote or comment counts.

    Args:
        xml_text: Raw Atom XML from the search.rss endpoint.

    Returns:
        List of entry dicts with title, url, author, created_at, and text.
    """
    entries = []
    root = ET.fromstring(xml_text)
    for entry in root.findall("atom:entry", ATOM_NS):
        entry_id = entry.findtext("atom:id", default="", namespaces=ATOM_NS)
        if not entry_id.startswith("t3_"):
            continue  # keep posts only (skip subreddit/user entries)

        link = entry.find("atom:link", ATOM_NS)
        url = link.get("href", "") if link is not None else ""
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

        entries.append({
            "title": entry.findtext("atom:title", default="", namespaces=ATOM_NS),
            "url": url,
            "author": author.replace("/u/", "") or "[unknown]",
            "created_at": published,
            "text": body,
        })
    return entries


def scan_reddit(
    brand_name: str,
    time_filter: str = "month",
    errors: Optional[list] = None,
) -> list[Mention]:
    """Scan Reddit for brand mentions.

    Access strategy: OAuth API (if REDDIT_CLIENT_ID/SECRET are set) ->
    public JSON API (usually blocked with 403) -> public RSS feed
    (no upvote/comment data). Failures are appended to `errors`.

    Args:
        brand_name: The brand name to search for.
        time_filter: Time range (hour, day, week, month, year, all).
        errors: Error list to append per-platform failures to.

    Returns:
        List of Mention objects from Reddit.
    """
    if errors is None:
        errors = []
    mentions = []
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

    data = None

    # 1) OAuth API (preferred - full data)
    token = get_reddit_oauth_token(errors)
    if token:
        oauth_headers = dict(headers)
        oauth_headers["Authorization"] = f"bearer {token}"
        try:
            response = request_with_retry(
                "GET", REDDIT_OAUTH_SEARCH_URL,
                params=params, headers=oauth_headers,
            )
            response.raise_for_status()
            data = response.json()
        except (requests.RequestException, ValueError) as e:
            errors.append(f"reddit: OAuth search failed - {e}")

    # 2) Public JSON API (blocked with 403 in most environments)
    if data is None:
        try:
            response = request_with_retry(
                "GET", REDDIT_PUBLIC_SEARCH_URL,
                params=params, headers=headers,
            )
            response.raise_for_status()
            data = response.json()
        except (requests.RequestException, ValueError) as e:
            status = getattr(getattr(e, "response", None), "status_code", None)
            if status == 403:
                errors.append(
                    "reddit: public JSON API blocked (403) - set "
                    "REDDIT_CLIENT_ID/REDDIT_CLIENT_SECRET for OAuth access; "
                    "trying RSS fallback"
                )
            else:
                errors.append(
                    f"reddit: JSON search failed - {e}; trying RSS fallback"
                )

    if data is not None:
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

    # 3) RSS/Atom feed fallback (no auth, limited data)
    try:
        response = request_with_retry(
            "GET", REDDIT_RSS_SEARCH_URL,
            params=params, headers={"User-Agent": USER_AGENT},
        )
        response.raise_for_status()
        entries = parse_reddit_rss_entries(response.text)
    except (requests.RequestException, ET.ParseError) as e:
        errors.append(f"reddit: RSS fallback failed - {e}")
        return mentions

    for entry in entries:
        text = entry["text"]
        text_preview = text[:150] + "..." if len(text) > 150 else text
        mention = Mention(
            platform="reddit",
            title=entry["title"],
            url=entry["url"],
            author=entry["author"],
            score=0,
            num_comments=0,
            created_at=entry["created_at"],
            text_preview=text_preview,
            sentiment=classify_sentiment(f"{entry['title']} {text}"),
        )
        mentions.append(mention)

    if mentions:
        errors.append(
            "reddit: used RSS fallback - upvote/comment counts unavailable "
            "(recorded as 0); set REDDIT_CLIENT_ID/REDDIT_CLIENT_SECRET "
            "for full data"
        )

    return mentions


def scan_hacker_news(
    brand_name: str,
    time_filter: str = "month",
    errors: Optional[list] = None,
) -> list[Mention]:
    """Scan Hacker News for brand mentions using the Algolia API.

    Searches both stories and comments endpoints, restricted to the
    --time window via numericFilters on created_at_i.

    Args:
        brand_name: The brand name to search for.
        time_filter: Time range (hour, day, week, month, year, all).
        errors: Error list to append per-platform failures to.

    Returns:
        List of Mention objects from Hacker News.
    """
    if errors is None:
        errors = []
    mentions = []

    cutoff = time_filter_cutoff(time_filter)
    if cutoff is not None:
        # Recency-filtered search sorted by date
        base_url = "https://hn.algolia.com/api/v1/search_by_date"
        numeric_filters = f"created_at_i>{int(cutoff.timestamp())}"
    else:
        # No time window: relevance-ranked search
        base_url = "https://hn.algolia.com/api/v1/search"
        numeric_filters = None

    def hn_search(tags: str, hits_per_page: int) -> dict:
        params = {
            "query": f'"{brand_name}"',
            "tags": tags,
            "hitsPerPage": hits_per_page,
        }
        if numeric_filters:
            params["numericFilters"] = numeric_filters
        response = request_with_retry("GET", base_url, params=params)
        response.raise_for_status()
        return response.json()

    # Search stories
    try:
        data = hn_search("story", 30)
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
    except (requests.RequestException, ValueError) as e:
        errors.append(f"hn: story search failed - {e}")

    time_module.sleep(RATE_LIMIT_SECONDS)

    # Search comments
    try:
        data = hn_search("comment", 20)
        for hit in data.get("hits", []):
            comment_text = hit.get("comment_text", "")
            # Strip HTML tags for clean text
            clean_text = re.sub(r"<[^>]+>", "", comment_text)
            text_preview = clean_text[:150] + "..." if len(clean_text) > 150 else clean_text

            # Link directly to the comment itself
            hn_url = f"https://news.ycombinator.com/item?id={hit.get('objectID', '')}"

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
    except (requests.RequestException, ValueError) as e:
        errors.append(f"hn: comment search failed - {e}")

    return mentions


def scan_github(
    brand_name: str,
    time_filter: str = "month",
    errors: Optional[list] = None,
) -> list[Mention]:
    """Scan GitHub for repositories related to the brand.

    Uses GITHUB_TOKEN from the environment when set (30 search requests/min
    instead of 10). The --time filter is applied with a pushed:> qualifier.

    Args:
        brand_name: The brand name to search for.
        time_filter: Time range (hour, day, week, month, year, all).
        errors: Error list to append per-platform failures to.

    Returns:
        List of Mention objects from GitHub.
    """
    if errors is None:
        errors = []
    mentions = []
    url = "https://api.github.com/search/repositories"

    query = brand_name
    cutoff = time_filter_cutoff(time_filter)
    if cutoff is not None:
        query = f"{brand_name} pushed:>{cutoff.strftime('%Y-%m-%d')}"

    params = {
        "q": query,
        "sort": "stars",
        "order": "desc",
        "per_page": 30,
    }
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": USER_AGENT,
    }
    github_token = os.environ.get("GITHUB_TOKEN")
    if github_token:
        headers["Authorization"] = f"Bearer {github_token}"

    try:
        response = request_with_retry("GET", url, params=params, headers=headers)
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError) as e:
        status = getattr(getattr(e, "response", None), "status_code", None)
        hint = ""
        if status in (403, 429) and not github_token:
            hint = " (set GITHUB_TOKEN for a higher search rate limit)"
        errors.append(f"github: search failed - {e}{hint}")
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
        elif (
            mention.num_comments == 0
            and mention.score > 0
            and mention.mention_type != "repository"
        ):
            # Repositories are excluded: their num_comments field holds
            # open_issues_count, not discussion comments
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
        time_filter: Time range applied to all platforms.

    Returns:
        ScanReport with aggregated results. Per-platform failures are
        recorded in ScanReport.errors - never silently dropped.
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
        reddit_mentions = scan_reddit(brand_name, time_filter, report.errors)
        all_mentions.extend(reddit_mentions)
        platform_counts["reddit"] = len(reddit_mentions)
        time_module.sleep(RATE_LIMIT_SECONDS)

    # Scan Hacker News
    if "hn" in platforms:
        print("  Scanning Hacker News...")
        hn_mentions = scan_hacker_news(brand_name, time_filter, report.errors)
        all_mentions.extend(hn_mentions)
        platform_counts["hn"] = len(hn_mentions)
        time_module.sleep(RATE_LIMIT_SECONDS)

    # Scan GitHub
    if "github" in platforms:
        print("  Scanning GitHub...")
        github_mentions = scan_github(brand_name, time_filter, report.errors)
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

    # Group errors by platform prefix ("reddit: ...", "hn: ...", ...)
    platform_errors: dict[str, list[str]] = {}
    for err in report.errors:
        key = err.split(":", 1)[0].strip().lower()
        platform_errors.setdefault(key, []).append(err)

    for platform, count in report.platform_breakdown.items():
        platform_name = {"reddit": "Reddit", "hn": "Hacker News", "github": "GitHub"}.get(
            platform, platform
        )
        if count == 0 and platform in platform_errors:
            detail = platform_errors[platform][0].split(":", 1)[-1].strip()
            lines.append(f"  {platform_name}: FAILED - {detail}")
        elif platform in platform_errors:
            lines.append(
                f"  {platform_name}: {count} mentions (degraded - see Errors below)"
            )
        else:
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

    if report.errors:
        lines.extend(["", "--- Errors ---"])
        for error in report.errors:
            lines.append(f"  ! {error}")

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
        help="Time filter applied to all platforms (default: month)",
    )

    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(1)

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
    print(json.dumps(asdict(report), indent=2))


if __name__ == "__main__":
    main()
