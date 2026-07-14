"""
crawler_checker.py - Check AI crawler access via robots.txt.

Parses a site's robots.txt file and determines the access status
for 21 known AI crawler tokens. Reports whether each crawler is
explicitly allowed, allowed by default (wildcard), blocked, or
partially blocked, and generates recommendations.
"""

import os
import re
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

try:
    import requests
except ImportError:
    print(
        "Required packages not installed. Run: pip install requests",
        file=sys.stderr,
    )
    sys.exit(1)


# Known AI crawler tokens with metadata
AI_CRAWLERS = [
    {
        "user_agent": "GPTBot",
        "platform": "OpenAI",
        "purpose": "Model training",
        "category": "training",
        "priority": "high",
    },
    {
        "user_agent": "OAI-SearchBot",
        "platform": "OpenAI",
        "purpose": "ChatGPT search indexing",
        "category": "search",
        "priority": "high",
    },
    {
        "user_agent": "ChatGPT-User",
        "platform": "OpenAI",
        "purpose": "User-initiated fetches / GPT Actions",
        "category": "user-fetch",
        "priority": "high",
    },
    {
        "user_agent": "ClaudeBot",
        "platform": "Anthropic",
        "purpose": "Model training",
        "category": "training",
        "priority": "high",
    },
    {
        "user_agent": "Claude-SearchBot",
        "platform": "Anthropic",
        "purpose": "Claude search indexing",
        "category": "search",
        "priority": "high",
    },
    {
        "user_agent": "Claude-User",
        "platform": "Anthropic",
        "purpose": "User-initiated fetches",
        "category": "user-fetch",
        "priority": "medium",
    },
    {
        "user_agent": "PerplexityBot",
        "platform": "Perplexity",
        "purpose": "Search indexing (not training)",
        "category": "search",
        "priority": "high",
    },
    {
        "user_agent": "Perplexity-User",
        "platform": "Perplexity",
        "purpose": "User-initiated fetches",
        "category": "user-fetch",
        "priority": "medium",
    },
    {
        "user_agent": "Google-Extended",
        "platform": "Google",
        "purpose": (
            "Gemini training + grounding opt-out token (not a crawler; "
            "does NOT govern AI Overviews or Search inclusion)"
        ),
        "category": "training-control",
        "priority": "high",
    },
    {
        "user_agent": "GoogleOther",
        "platform": "Google",
        "purpose": "R&D crawls",
        "category": "other",
        "priority": "low",
    },
    {
        "user_agent": "Google-CloudVertexBot",
        "platform": "Google",
        "purpose": "Vertex AI site ingestion",
        "category": "training",
        "priority": "medium",
    },
    {
        "user_agent": "bingbot",
        "platform": "Microsoft",
        "purpose": "Bing Search + Copilot answers (blocking removes Copilot visibility)",
        "category": "search",
        "priority": "high",
    },
    {
        "user_agent": "meta-externalagent",
        "platform": "Meta",
        "purpose": "AI training + indexing (replaces FacebookBot)",
        "category": "training",
        "priority": "medium",
    },
    {
        "user_agent": "meta-externalfetcher",
        "platform": "Meta",
        "purpose": "User-initiated link fetches",
        "category": "user-fetch",
        "priority": "low",
    },
    {
        "user_agent": "Applebot-Extended",
        "platform": "Apple",
        "purpose": (
            "Apple Intelligence training opt-out token "
            "(doesn't crawl; Applebot does the crawling)"
        ),
        "category": "training-control",
        "priority": "medium",
    },
    {
        "user_agent": "Amazonbot",
        "platform": "Amazon",
        "purpose": "Alexa/AI answers",
        "category": "search",
        "priority": "medium",
    },
    {
        "user_agent": "Bytespider",
        "platform": "ByteDance",
        "purpose": "Model training (poor robots.txt compliance)",
        "category": "training",
        "priority": "medium",
    },
    {
        "user_agent": "CCBot",
        "platform": "Common Crawl",
        "purpose": "Open corpus widely used for AI training",
        "category": "training",
        "priority": "medium",
    },
    {
        "user_agent": "DuckAssistBot",
        "platform": "DuckDuckGo",
        "purpose": "DuckAssist AI answers",
        "category": "search",
        "priority": "medium",
    },
    {
        "user_agent": "MistralAI-User",
        "platform": "Mistral",
        "purpose": "Le Chat citation fetches",
        "category": "user-fetch",
        "priority": "medium",
    },
    {
        "user_agent": "cohere-training-data-crawler",
        "platform": "Cohere",
        "purpose": "Model training",
        "category": "training",
        "priority": "low",
    },
]

# Path keywords that suggest an internal/administrative area rather
# than public content. Wildcard disallows on such paths should not
# count against AI crawler access.
INTERNAL_PATH_KEYWORDS = [
    "admin", "api", "internal", "login", "logout", "signin", "signup",
    "register", "account", "auth", "cart", "checkout", "basket",
    "private", "wp-admin", "wp-login", "wp-json", "cgi-bin", "tmp",
    "cache", "staging", "dev", "test", "search", "ajax", "session",
    "token", "dashboard", "preview", "draft", "plugins", "includes",
    "assets", "static", "media", "uploads", "feed", "trackback",
    "xmlrpc", "settings", "config",
]


@dataclass
class RobotsRule:
    """A single robots.txt rule group for a user-agent."""

    user_agent: str
    allows: List[str] = field(default_factory=list)
    disallows: List[str] = field(default_factory=list)


def fetch_robots_txt(url: str, timeout: int = 15) -> Optional[str]:
    """Fetch the robots.txt file from a given URL's domain.

    Args:
        url: Any URL on the target domain.
        timeout: Request timeout in seconds.

    Returns:
        The robots.txt content string, or None if not accessible.
    """
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; GEOSEOAuditor/1.0)"
        }
        response = requests.get(robots_url, headers=headers, timeout=timeout)
        if response.status_code == 200:
            return response.text
        return None
    except requests.RequestException:
        return None


def parse_robots_txt(content: str) -> List[RobotsRule]:
    """Parse robots.txt content into structured rules.

    Args:
        content: The raw robots.txt file content.

    Returns:
        A list of RobotsRule objects, one per user-agent block.
    """
    rules: List[RobotsRule] = []
    current_agents: List[str] = []
    current_allows: List[str] = []
    current_disallows: List[str] = []

    def flush() -> None:
        """Save the current block of rules."""
        if current_agents:
            for agent in current_agents:
                rules.append(RobotsRule(
                    user_agent=agent,
                    allows=list(current_allows),
                    disallows=list(current_disallows),
                ))

    for line in content.splitlines():
        # Strip comments
        line = line.split("#")[0].strip()
        if not line:
            continue

        lower_line = line.lower()

        if lower_line.startswith("user-agent:"):
            value = line.split(":", 1)[1].strip()
            if current_allows or current_disallows:
                flush()
                current_agents = []
                current_allows = []
                current_disallows = []
            current_agents.append(value)

        elif lower_line.startswith("disallow:"):
            value = line.split(":", 1)[1].strip()
            current_disallows.append(value)

        elif lower_line.startswith("allow:"):
            value = line.split(":", 1)[1].strip()
            current_allows.append(value)

    # Flush remaining
    flush()

    return rules


def merge_rules_for_agent(rules: List[RobotsRule], agent: str) -> Optional[RobotsRule]:
    """Merge all rule groups naming the same user-agent (RFC 9309).

    Args:
        rules: Parsed robots.txt rules.
        agent: The user-agent token to merge rules for.

    Returns:
        A single merged RobotsRule, or None if no group names the agent.
    """
    matching = [r for r in rules if r.user_agent.lower() == agent.lower()]
    if not matching:
        return None
    merged = RobotsRule(user_agent=agent)
    for rule in matching:
        merged.allows.extend(rule.allows)
        merged.disallows.extend(rule.disallows)
    return merged


def is_root_block(path: str) -> bool:
    """Return True if a disallow path blocks the whole site."""
    return path in ("/", "/*", "*")


def is_internal_path(path: str) -> bool:
    """Heuristic: does a disallow path look like an internal/admin area?

    Wildcard disallows on admin/api/internal-style paths are normal
    hygiene and should not downgrade a crawler's access status.
    """
    cleaned = path.replace("*", "").replace("$", "").lower()
    segments = [s for s in re.split(r"[/\-_.?=&]+", cleaned) if s]
    return any(seg in INTERNAL_PATH_KEYWORDS for seg in segments)


def evaluate_rule(rule: RobotsRule) -> Tuple[str, List[str]]:
    """Evaluate a merged rule group into an access status.

    Args:
        rule: A merged RobotsRule for one user-agent.

    Returns:
        Tuple of (status, content_path_disallows) where status is one
        of 'allowed', 'blocked', 'partially_blocked', and the list
        contains disallow paths that plausibly cover public content.
    """
    non_empty_disallows = [d for d in rule.disallows if d]
    has_root_disallow = any(is_root_block(d) for d in non_empty_disallows)
    has_root_allow = "/" in rule.allows

    if has_root_disallow and not has_root_allow:
        return "blocked", []

    # Split remaining disallows into internal-style vs content paths
    scoped = [d for d in non_empty_disallows if not is_root_block(d)]
    content_paths = [d for d in scoped if not is_internal_path(d)]

    if content_paths:
        return "partially_blocked", content_paths

    # Only internal-style disallows (or none): effectively allowed
    return "allowed", []


def check_crawler_status(
    rules: List[RobotsRule], crawler_agent: str
) -> Tuple[str, List[str]]:
    """Determine the access status for a specific crawler.

    Checks crawler-specific rule groups first; if none exist, falls
    back to the wildcard (*) group. Rules from multiple groups naming
    the same agent are merged per RFC 9309.

    Args:
        rules: Parsed robots.txt rules.
        crawler_agent: The user-agent token to check.

    Returns:
        Tuple of (status, blocked_content_paths). Status is one of:
        'allowed' (explicit group), 'allowed_via_wildcard' (no explicit
        group, wildcard permits root), 'blocked', 'partially_blocked',
        or 'not_mentioned' (no explicit group and no wildcard group).
    """
    specific = merge_rules_for_agent(rules, crawler_agent)
    if specific is not None:
        return evaluate_rule(specific)

    wildcard = merge_rules_for_agent(rules, "*")
    if wildcard is not None:
        status, paths = evaluate_rule(wildcard)
        if status == "allowed":
            # Root is reachable by default; keep the default-allow
            # distinct from an explicit allow in the output.
            return "allowed_via_wildcard", paths
        return status, paths

    return "not_mentioned", []


def check_all_crawlers(
    robots_content: Optional[str],
) -> Dict[str, Any]:
    """Check access status for all known AI crawlers.

    Args:
        robots_content: The raw robots.txt content, or None if not found.

    Returns:
        Dictionary containing:
        - robots_found: Whether robots.txt was accessible
        - crawler_status: Dict mapping crawler name to status info
        - summary: Counts by status category
        - recommendations: List of actionable recommendations
    """
    result: Dict[str, Any] = {
        "robots_found": robots_content is not None,
        "crawler_status": {},
        "summary": {
            "allowed": 0,
            "allowed_via_wildcard": 0,
            "blocked": 0,
            "partially_blocked": 0,
            "not_mentioned": 0,
        },
        "recommendations": [],
    }

    if robots_content is None:
        result["recommendations"].append(
            "No robots.txt found. Without one, all crawlers are allowed by "
            "default. Create a robots.txt file if you want explicit control "
            "over AI crawler access."
        )
        for crawler in AI_CRAWLERS:
            result["crawler_status"][crawler["user_agent"]] = {
                "status": "not_mentioned",
                "blocked_paths": [],
                "platform": crawler["platform"],
                "purpose": crawler["purpose"],
                "category": crawler["category"],
                "priority": crawler["priority"],
            }
            result["summary"]["not_mentioned"] += 1
        return result

    rules = parse_robots_txt(robots_content)

    for crawler in AI_CRAWLERS:
        status, blocked_paths = check_crawler_status(rules, crawler["user_agent"])
        result["crawler_status"][crawler["user_agent"]] = {
            "status": status,
            "blocked_paths": blocked_paths,
            "platform": crawler["platform"],
            "purpose": crawler["purpose"],
            "category": crawler["category"],
            "priority": crawler["priority"],
        }
        result["summary"][status] = result["summary"].get(status, 0) + 1

    # Generate recommendations
    result["recommendations"] = generate_recommendations(result["crawler_status"])

    return result


def generate_recommendations(
    crawler_status: Dict[str, Dict[str, Any]],
) -> List[str]:
    """Generate actionable recommendations based on crawler status.

    Args:
        crawler_status: Dictionary of crawler statuses from check_all_crawlers.

    Returns:
        A prioritized list of recommendation strings.
    """
    recommendations: List[str] = []

    def status_of(agent: str) -> str:
        return crawler_status.get(agent, {}).get("status", "not_mentioned")

    # Check high-priority search/answer crawlers
    high_priority_search = [
        ("OAI-SearchBot", "ChatGPT search results"),
        ("Claude-SearchBot", "Claude search results"),
        ("PerplexityBot", "Perplexity search results"),
        ("bingbot", "Bing Search and Copilot answers"),
    ]

    for agent, description in high_priority_search:
        status = status_of(agent)
        if status == "blocked":
            recommendations.append(
                f"CRITICAL: {agent} is blocked. Your content will not appear in {description}. "
                f"Consider allowing this crawler for AI search visibility."
            )
        elif status == "partially_blocked":
            paths = crawler_status.get(agent, {}).get("blocked_paths", [])
            path_note = f" (blocked paths: {', '.join(paths[:5])})" if paths else ""
            recommendations.append(
                f"{agent} is blocked from some content paths{path_note}. "
                f"Verify these exclusions are intentional; they limit visibility in {description}."
            )

    # Google AI Overviews / Google-Extended guidance
    google_ext_status = status_of("Google-Extended")
    if google_ext_status == "blocked":
        recommendations.append(
            "Google-Extended is blocked. Note: this only opts your content out of "
            "Gemini model training and grounding. It does NOT affect Google Search, "
            "AI Overviews, or AI Mode. To appear in AI Overviews, keep Googlebot "
            "allowed and avoid restrictive snippet controls (nosnippet, data-nosnippet, "
            "max-snippet, noindex)."
        )
    else:
        recommendations.append(
            "AI Overviews inclusion is governed by normal Googlebot access plus "
            "snippet controls, not by Google-Extended. To appear in AI Overviews, "
            "keep Googlebot allowed and avoid restrictive snippet controls "
            "(nosnippet, data-nosnippet, max-snippet, noindex)."
        )

    # Check training crawlers
    high_priority_training = [
        ("GPTBot", "OpenAI model knowledge"),
        ("ClaudeBot", "Anthropic Claude knowledge"),
    ]

    for agent, description in high_priority_training:
        status = status_of(agent)
        if status == "blocked":
            recommendations.append(
                f"{agent} is blocked. Your content will not be included in {description}. "
                f"This is acceptable if you do not want AI models trained on your content."
            )

    # User-initiated fetchers: blocking these breaks link opening in chats
    user_fetchers = ["ChatGPT-User", "Claude-User", "Perplexity-User", "MistralAI-User"]
    blocked_fetchers = [a for a in user_fetchers if status_of(a) == "blocked"]
    if blocked_fetchers:
        recommendations.append(
            f"User-initiated fetchers blocked: {', '.join(blocked_fetchers)}. "
            f"These fetch pages when a user explicitly asks an AI assistant to open "
            f"a link, so blocking them degrades the experience of users who already "
            f"know about your site."
        )

    # General recommendations
    statuses = [info.get("status") for info in crawler_status.values()]
    blocked_count = sum(1 for s in statuses if s == "blocked")
    wildcard_count = sum(1 for s in statuses if s == "allowed_via_wildcard")

    if blocked_count == len(crawler_status) and crawler_status:
        recommendations.append(
            "All AI crawlers are blocked. Your site will have minimal AI search visibility. "
            "Consider allowing at least the search-facing crawlers (OAI-SearchBot, "
            "Claude-SearchBot, PerplexityBot, bingbot)."
        )

    if wildcard_count > len(crawler_status) // 2:
        recommendations.append(
            "Most AI crawlers are allowed via the wildcard (*) rules rather than "
            "explicit groups. This is fine for visibility; add explicit per-crawler "
            "rules only if you want different policies for specific bots."
        )

    return recommendations


STATUS_DISPLAY = {
    "allowed": "Allowed",
    "allowed_via_wildcard": "Allowed (default)",
    "blocked": "Blocked",
    "partially_blocked": "Partially Blocked",
    "not_mentioned": "Not Mentioned",
}


def format_report(results: Dict[str, Any]) -> str:
    """Format crawler check results into a human-readable report.

    Args:
        results: The result dictionary from check_all_crawlers().

    Returns:
        A formatted string report.
    """
    lines = []
    lines.append("AI Crawler Access Report")
    lines.append("=" * 60)

    lines.append(f"\nrobots.txt found: {'Yes' if results['robots_found'] else 'No'}")

    summary = results["summary"]
    lines.append(f"\nSummary:")
    lines.append(f"  Allowed (explicit): {summary.get('allowed', 0)}")
    lines.append(f"  Allowed (default via *): {summary.get('allowed_via_wildcard', 0)}")
    lines.append(f"  Blocked: {summary.get('blocked', 0)}")
    lines.append(f"  Partially blocked: {summary.get('partially_blocked', 0)}")
    lines.append(f"  Not mentioned: {summary.get('not_mentioned', 0)}")

    # Status table
    lines.append(f"\n{'Crawler':<30} {'Platform':<14} {'Status':<20} {'Category':<16}")
    lines.append("-" * 82)

    for agent, info in results["crawler_status"].items():
        status_display = STATUS_DISPLAY.get(info["status"], info["status"])
        lines.append(
            f"{agent:<30} {info['platform']:<14} {status_display:<20} {info['category']:<16}"
        )
        if info.get("blocked_paths"):
            lines.append(f"{'':<30} blocked paths: {', '.join(info['blocked_paths'][:5])}")

    # Recommendations
    recs = results.get("recommendations", [])
    if recs:
        lines.append(f"\n--- Recommendations ({len(recs)}) ---")
        for i, rec in enumerate(recs, 1):
            lines.append(f"\n  {i}. {rec}")

    return "\n".join(lines)


if __name__ == "__main__":
    import json

    if len(sys.argv) >= 2:
        source = sys.argv[1]

        if os.path.exists(source):
            # Read from file
            with open(source, "r", encoding="utf-8") as f:
                robots_content = f.read()
            print(f"Reading robots.txt from file: {source}\n")
        else:
            # Treat as URL; prepend https:// if no scheme given
            if not source.startswith(("http://", "https://")):
                source = f"https://{source}"
            print(f"Fetching robots.txt from: {source}\n")
            robots_content = fetch_robots_txt(source)
    else:
        # Sample robots.txt for demonstration
        robots_content = """
User-agent: GPTBot
Disallow: /

User-agent: OAI-SearchBot
Allow: /

User-agent: ClaudeBot
Disallow: /private/
Allow: /

User-agent: *
Disallow: /admin/
Disallow: /private/
"""
        print("Running with sample robots.txt content...\n")

    results = check_all_crawlers(robots_content)
    print(format_report(results))

    print("\n--- Raw JSON ---")
    print(json.dumps(results, indent=2, default=str))
