"""
crawler_checker.py - Check AI crawler access via robots.txt.

Parses a site's robots.txt file and determines the access status
for 14+ known AI crawlers. Reports whether each crawler is allowed,
blocked, or not mentioned, and generates recommendations.
"""

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


# Known AI crawlers with metadata
AI_CRAWLERS = [
    {
        "user_agent": "GPTBot",
        "platform": "OpenAI",
        "purpose": "GPT model training data collection",
        "category": "training",
        "priority": "high",
    },
    {
        "user_agent": "OAI-SearchBot",
        "platform": "OpenAI",
        "purpose": "ChatGPT real-time web search",
        "category": "search",
        "priority": "high",
    },
    {
        "user_agent": "ClaudeBot",
        "platform": "Anthropic",
        "purpose": "Claude AI training and web features",
        "category": "training",
        "priority": "high",
    },
    {
        "user_agent": "PerplexityBot",
        "platform": "Perplexity AI",
        "purpose": "Perplexity search and answer engine",
        "category": "search",
        "priority": "high",
    },
    {
        "user_agent": "Google-Extended",
        "platform": "Google",
        "purpose": "Gemini AI and AI Overviews",
        "category": "search",
        "priority": "high",
    },
    {
        "user_agent": "Bytespider",
        "platform": "ByteDance/TikTok",
        "purpose": "AI model training and content indexing",
        "category": "training",
        "priority": "medium",
    },
    {
        "user_agent": "CCBot",
        "platform": "Common Crawl",
        "purpose": "Open web archive for AI training datasets",
        "category": "training",
        "priority": "medium",
    },
    {
        "user_agent": "Amazonbot",
        "platform": "Amazon",
        "purpose": "Alexa AI answers and Amazon search",
        "category": "search",
        "priority": "medium",
    },
    {
        "user_agent": "FacebookBot",
        "platform": "Meta",
        "purpose": "Meta AI features and link previews",
        "category": "training",
        "priority": "medium",
    },
    {
        "user_agent": "Applebot-Extended",
        "platform": "Apple",
        "purpose": "Apple Intelligence and Siri AI features",
        "category": "search",
        "priority": "medium",
    },
    {
        "user_agent": "cohere-ai",
        "platform": "Cohere",
        "purpose": "Enterprise AI model training",
        "category": "training",
        "priority": "low",
    },
    {
        "user_agent": "Diffbot",
        "platform": "Diffbot",
        "purpose": "AI knowledge graph construction",
        "category": "training",
        "priority": "low",
    },
    {
        "user_agent": "Timpibot",
        "platform": "Timpi",
        "purpose": "Decentralized search indexing",
        "category": "search",
        "priority": "low",
    },
    {
        "user_agent": "webzio-extended",
        "platform": "Webz.io",
        "purpose": "Web data platform for AI companies",
        "category": "training",
        "priority": "low",
    },
]


@dataclass
class RobotsRule:
    """A single robots.txt rule for a user-agent."""

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


def check_crawler_status(
    rules: List[RobotsRule], crawler_agent: str
) -> str:
    """Determine the access status for a specific crawler.

    Checks both crawler-specific rules and wildcard (*) rules.
    Crawler-specific rules take precedence over wildcard rules.

    Args:
        rules: Parsed robots.txt rules.
        crawler_agent: The user-agent string to check.

    Returns:
        One of: 'allowed', 'blocked', 'partially_blocked', 'not_mentioned'.
    """
    # Find rules specific to this crawler
    specific_rules = [
        r for r in rules
        if r.user_agent.lower() == crawler_agent.lower()
    ]

    # Find wildcard rules
    wildcard_rules = [r for r in rules if r.user_agent == "*"]

    # Specific rules take precedence
    if specific_rules:
        rule = specific_rules[0]
        has_root_disallow = "/" in rule.disallows
        has_root_allow = "/" in rule.allows
        has_any_disallow = bool(rule.disallows) and any(d for d in rule.disallows)
        has_any_allow = bool(rule.allows)

        if has_root_disallow and not has_root_allow:
            return "blocked"
        elif has_root_allow:
            if has_any_disallow and len(rule.disallows) > 0:
                non_empty_disallows = [d for d in rule.disallows if d]
                if non_empty_disallows:
                    return "partially_blocked"
            return "allowed"
        elif has_any_disallow:
            non_empty = [d for d in rule.disallows if d]
            if non_empty:
                return "partially_blocked"
            return "allowed"
        else:
            # Empty disallow means allowed
            return "allowed"

    # Fall back to wildcard rules
    if wildcard_rules:
        rule = wildcard_rules[0]
        has_root_disallow = "/" in rule.disallows
        if has_root_disallow:
            return "blocked"
        non_empty_disallows = [d for d in rule.disallows if d]
        if non_empty_disallows:
            return "partially_blocked"

    return "not_mentioned"


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
            "blocked": 0,
            "partially_blocked": 0,
            "not_mentioned": 0,
        },
        "recommendations": [],
    }

    if robots_content is None:
        result["recommendations"].append(
            "No robots.txt found. Create a robots.txt file to control AI crawler access. "
            "Without one, all crawlers are allowed by default."
        )
        for crawler in AI_CRAWLERS:
            result["crawler_status"][crawler["user_agent"]] = {
                "status": "not_mentioned",
                "platform": crawler["platform"],
                "purpose": crawler["purpose"],
                "category": crawler["category"],
                "priority": crawler["priority"],
            }
            result["summary"]["not_mentioned"] += 1
        return result

    rules = parse_robots_txt(robots_content)

    for crawler in AI_CRAWLERS:
        status = check_crawler_status(rules, crawler["user_agent"])
        result["crawler_status"][crawler["user_agent"]] = {
            "status": status,
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
    crawler_status: Dict[str, Dict[str, str]],
) -> List[str]:
    """Generate actionable recommendations based on crawler status.

    Args:
        crawler_status: Dictionary of crawler statuses from check_all_crawlers.

    Returns:
        A prioritized list of recommendation strings.
    """
    recommendations: List[str] = []

    # Check high-priority search crawlers
    high_priority_search = [
        ("OAI-SearchBot", "ChatGPT search results"),
        ("PerplexityBot", "Perplexity search results"),
        ("Google-Extended", "Google AI Overviews"),
    ]

    for agent, description in high_priority_search:
        info = crawler_status.get(agent, {})
        status = info.get("status", "not_mentioned")
        if status == "blocked":
            recommendations.append(
                f"CRITICAL: {agent} is blocked. Your content will not appear in {description}. "
                f"Consider allowing this crawler for AI search visibility."
            )
        elif status == "not_mentioned":
            recommendations.append(
                f"Consider explicitly allowing {agent} in robots.txt to ensure "
                f"visibility in {description}."
            )

    # Check training crawlers
    high_priority_training = [
        ("GPTBot", "OpenAI model knowledge"),
        ("ClaudeBot", "Anthropic Claude knowledge"),
    ]

    for agent, description in high_priority_training:
        info = crawler_status.get(agent, {})
        status = info.get("status", "not_mentioned")
        if status == "blocked":
            recommendations.append(
                f"{agent} is blocked. Your content will not be included in {description}. "
                f"This is acceptable if you do not want AI models trained on your content."
            )
        elif status == "not_mentioned":
            recommendations.append(
                f"Consider explicitly setting a policy for {agent} (allow or disallow) "
                f"to control inclusion in {description}."
            )

    # General recommendations
    blocked_count = sum(
        1 for info in crawler_status.values()
        if info.get("status") == "blocked"
    )
    not_mentioned_count = sum(
        1 for info in crawler_status.values()
        if info.get("status") == "not_mentioned"
    )

    if blocked_count == len(crawler_status):
        recommendations.append(
            "All AI crawlers are blocked. Your site will have minimal AI search visibility. "
            "Consider allowing at least the search-facing crawlers (OAI-SearchBot, "
            "PerplexityBot, Google-Extended)."
        )

    if not_mentioned_count > len(crawler_status) // 2:
        recommendations.append(
            "Most AI crawlers are not explicitly mentioned in robots.txt. "
            "Add explicit allow/disallow rules for each AI crawler to have "
            "clear control over your AI search presence."
        )

    return recommendations


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
    lines.append(f"  Allowed: {summary.get('allowed', 0)}")
    lines.append(f"  Blocked: {summary.get('blocked', 0)}")
    lines.append(f"  Partially blocked: {summary.get('partially_blocked', 0)}")
    lines.append(f"  Not mentioned: {summary.get('not_mentioned', 0)}")

    # Status table
    lines.append(f"\n{'Crawler':<22} {'Platform':<18} {'Status':<18} {'Category':<10}")
    lines.append("-" * 70)

    for agent, info in results["crawler_status"].items():
        status_display = info["status"].replace("_", " ").title()
        lines.append(
            f"{agent:<22} {info['platform']:<18} {status_display:<18} {info['category']:<10}"
        )

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

        if source.startswith(("http://", "https://")):
            # Fetch robots.txt from URL
            if not source.startswith(("http://", "https://")):
                source = f"https://{source}"
            print(f"Fetching robots.txt from: {source}\n")
            robots_content = fetch_robots_txt(source)
        else:
            # Read from file
            try:
                with open(source, "r", encoding="utf-8") as f:
                    robots_content = f.read()
                print(f"Reading robots.txt from file: {source}\n")
            except FileNotFoundError:
                print(f"File not found: {source}", file=sys.stderr)
                sys.exit(1)
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
