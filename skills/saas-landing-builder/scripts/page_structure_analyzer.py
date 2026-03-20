#!/usr/bin/env python3
"""
Landing Page Structure Analyzer

Analyzes SaaS landing pages against the 12-section anatomy framework.
Detects which sections are present, evaluates section order, and provides
recommendations for missing sections.

Usage:
    python page_structure_analyzer.py <landing_page_url>

Example:
    python page_structure_analyzer.py https://example.com
"""

import json
import re
import sys
from dataclasses import dataclass, field, asdict
from typing import Optional
from urllib.parse import urlparse

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("Required dependencies: requests, beautifulsoup4")
    print("Install with: pip install requests beautifulsoup4")
    sys.exit(1)


# The 12 landing page sections and their detection patterns
SECTION_DEFINITIONS: dict[str, dict] = {
    "hero": {
        "name": "Hero Section",
        "order": 1,
        "description": "Primary headline, subheadline, CTA, and visual",
        "html_patterns": ["h1", "hero", "banner", "jumbotron", "masthead"],
        "text_patterns": [
            r"get\s+started", r"start\s+free", r"try\s+free", r"sign\s+up",
            r"book\s+a?\s*demo", r"request\s+demo",
        ],
        "recommendation": (
            "Add a hero section with a clear headline stating your core value "
            "proposition, a supporting subheadline, and a single primary CTA."
        ),
    },
    "social_proof": {
        "name": "Social Proof Bar",
        "order": 2,
        "description": "Company logos, user counts, or trust badges",
        "html_patterns": ["logo-bar", "logos", "trusted", "clients", "customers", "partners"],
        "text_patterns": [
            r"trusted\s+by", r"used\s+by", r"loved\s+by", r"join\s+\d",
            r"\d+[,.]?\d*[kKmM]?\+?\s*(companies|teams|users|customers)",
        ],
        "recommendation": (
            "Add a social proof bar with customer logos or a user count "
            "directly below the hero section to build immediate credibility."
        ),
    },
    "problem": {
        "name": "Problem Statement",
        "order": 3,
        "description": "Articulation of the customer's pain points",
        "html_patterns": ["problem", "pain", "challenge", "struggle", "frustrat"],
        "text_patterns": [
            r"tired\s+of", r"struggle", r"frustrated", r"wast(e|ing)\s+time",
            r"the\s+problem", r"sound\s+familiar", r"you\s+know\s+the\s+feeling",
        ],
        "recommendation": (
            "Add a problem statement section that articulates your "
            "audience's pain points in their own language."
        ),
    },
    "solution": {
        "name": "Solution Overview",
        "order": 4,
        "description": "How your product solves the stated problem",
        "html_patterns": ["solution", "how-we-help", "what-we-do", "overview", "about"],
        "text_patterns": [
            r"the\s+solution", r"we\s+help", r"our\s+platform", r"with\s+\w+\s*,?\s*you\s+can",
            r"introducing", r"meet\s+\w+",
        ],
        "recommendation": (
            "Add a solution overview that directly connects your product "
            "to the problems described above."
        ),
    },
    "features": {
        "name": "Feature Grid",
        "order": 5,
        "description": "3-4 key features with benefit descriptions",
        "html_patterns": [
            "feature", "benefit", "capability", "what-you-get",
            "highlights", "advantages",
        ],
        "text_patterns": [
            r"features", r"what\s+you\s+get", r"capabilities",
            r"why\s+choose", r"highlights",
        ],
        "recommendation": (
            "Add a feature grid showcasing 3-4 key features. Lead with "
            "benefits, not technical specifications."
        ),
    },
    "how_it_works": {
        "name": "How It Works",
        "order": 6,
        "description": "Simple 3-step process explanation",
        "html_patterns": ["how-it-works", "steps", "process", "getting-started"],
        "text_patterns": [
            r"how\s+it\s+works", r"step\s+[123]", r"getting\s+started",
            r"in\s+3\s+steps", r"simple\s+steps", r"easy\s+as",
        ],
        "recommendation": (
            "Add a 'How It Works' section with 3 simple steps. Make step 1 "
            "feel effortless and step 3 be the desired outcome."
        ),
    },
    "testimonials": {
        "name": "Testimonials / Case Studies",
        "order": 7,
        "description": "Customer success stories and quotes",
        "html_patterns": [
            "testimonial", "review", "case-stud", "quote", "customer-stor",
            "success-stor", "what-customers-say",
        ],
        "text_patterns": [
            r"testimonial", r"what\s+(our\s+)?customers\s+say",
            r"case\s+stud", r"success\s+stor", r"hear\s+from",
        ],
        "recommendation": (
            "Add 2-3 testimonials with real names, photos, titles, and "
            "specific outcomes. Video testimonials perform 2-3x better."
        ),
    },
    "pricing": {
        "name": "Pricing Section",
        "order": 8,
        "description": "Pricing plans and comparison",
        "html_patterns": ["pricing", "plans", "packages", "price"],
        "text_patterns": [
            r"pricing", r"\$\d+", r"per\s+month", r"/mo", r"/month",
            r"free\s+plan", r"enterprise", r"starter",
            r"professional", r"business\s+plan",
        ],
        "recommendation": (
            "Consider adding a pricing section with 2-3 tiers. Transparent "
            "pricing builds trust for SMB and mid-market buyers."
        ),
    },
    "faq": {
        "name": "FAQ Section",
        "order": 9,
        "description": "Frequently asked questions addressing objections",
        "html_patterns": ["faq", "frequently-asked", "questions", "accordion"],
        "text_patterns": [
            r"faq", r"frequently\s+asked", r"common\s+questions",
            r"have\s+questions", r"q\s*&\s*a",
        ],
        "recommendation": (
            "Add an FAQ section with 5-8 questions that address common "
            "objections about pricing, security, setup time, and cancellation."
        ),
    },
    "integrations": {
        "name": "Integrations / Compatibility",
        "order": 10,
        "description": "Supported integrations and ecosystem fit",
        "html_patterns": [
            "integrat", "connect", "compatible", "works-with",
            "ecosystem", "plugins", "extensions",
        ],
        "text_patterns": [
            r"integrat", r"connect\s+with", r"works\s+with",
            r"compatible", r"plug[\s-]?ins", r"extensions",
            r"api\s+access", r"zapier", r"webhook",
        ],
        "recommendation": (
            "Add an integrations section showing logos of popular tools "
            "your product connects with. This reduces switching cost concerns."
        ),
    },
    "final_cta": {
        "name": "Final CTA",
        "order": 11,
        "description": "Bottom-of-page conversion section",
        "html_patterns": ["final-cta", "bottom-cta", "cta-section", "cta-banner"],
        "text_patterns": [
            r"ready\s+to", r"get\s+started\s+today", r"start\s+your",
            r"join\s+\d", r"try\s+it\s+free", r"what\s+are\s+you\s+waiting",
        ],
        "recommendation": (
            "Add a final CTA section near the bottom with a restated value "
            "proposition and a clear call-to-action button."
        ),
    },
    "footer": {
        "name": "Footer",
        "order": 12,
        "description": "Navigation, legal links, and trust signals",
        "html_patterns": ["footer"],
        "text_patterns": [
            r"privacy\s+policy", r"terms\s+of\s+service", r"terms\s+and\s+conditions",
            r"\u00a9\s*\d{4}", r"copyright", r"all\s+rights\s+reserved",
        ],
        "recommendation": (
            "Add a proper footer with organized link columns, legal pages, "
            "social media links, and compliance badges."
        ),
    },
}


@dataclass
class SectionResult:
    """Result for a single section detection."""

    key: str
    name: str
    order: int
    detected: bool = False
    confidence: str = "none"
    signals: list = field(default_factory=list)


@dataclass
class PageAnalysisResult:
    """Complete page structure analysis result."""

    url: str
    sections_found: list = field(default_factory=list)
    sections_missing: list = field(default_factory=list)
    completeness_score: float = 0.0
    section_order_optimal: bool = True
    section_details: list = field(default_factory=list)
    recommendations: list = field(default_factory=list)
    errors: list = field(default_factory=list)


def fetch_page(url: str, timeout: int = 15) -> Optional[BeautifulSoup]:
    """Fetch a web page and return a BeautifulSoup object.

    Args:
        url: The URL to fetch.
        timeout: Request timeout in seconds.

    Returns:
        BeautifulSoup object or None if fetch failed.
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }
    try:
        response = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
        response.raise_for_status()
        return BeautifulSoup(response.text, "html.parser")
    except requests.RequestException as e:
        print(f"Error fetching {url}: {e}")
        return None


def detect_section(soup: BeautifulSoup, section_key: str, definition: dict) -> SectionResult:
    """Detect whether a specific section exists on the page.

    Uses a combination of HTML structure analysis (class names, IDs, tag names)
    and text content pattern matching.

    Args:
        soup: Parsed HTML page.
        section_key: The section identifier.
        definition: The section definition with detection patterns.

    Returns:
        SectionResult with detection status and confidence.
    """
    result = SectionResult(
        key=section_key,
        name=definition["name"],
        order=definition["order"],
    )

    page_html = str(soup).lower()
    page_text = soup.get_text().lower()
    signals = []

    # Check HTML patterns (class names, IDs, data attributes)
    for pattern in definition["html_patterns"]:
        # Check element IDs
        elements_by_id = soup.find_all(id=re.compile(pattern, re.IGNORECASE))
        if elements_by_id:
            signals.append(f"Found element with ID matching '{pattern}'")

        # Check class names
        elements_by_class = soup.find_all(class_=re.compile(pattern, re.IGNORECASE))
        if elements_by_class:
            signals.append(f"Found element with class matching '{pattern}'")

        # Check tag-specific patterns (e.g., footer tag)
        if pattern in ("footer", "header", "nav"):
            tag_elements = soup.find_all(pattern)
            if tag_elements:
                signals.append(f"Found <{pattern}> tag")

    # Check text patterns
    for pattern in definition["text_patterns"]:
        if re.search(pattern, page_text, re.IGNORECASE):
            signals.append(f"Found text matching '{pattern}'")

    # Determine detection and confidence
    result.signals = signals
    if len(signals) >= 3:
        result.detected = True
        result.confidence = "high"
    elif len(signals) >= 2:
        result.detected = True
        result.confidence = "medium"
    elif len(signals) >= 1:
        result.detected = True
        result.confidence = "low"
    else:
        result.detected = False
        result.confidence = "none"

    return result


def evaluate_section_order(detected_sections: list[SectionResult]) -> bool:
    """Evaluate whether detected sections follow the optimal order.

    Args:
        detected_sections: List of detected section results.

    Returns:
        True if sections are in optimal order.
    """
    found_orders = [s.order for s in detected_sections if s.detected]
    if len(found_orders) <= 1:
        return True

    # Check if the found sections are in ascending order
    for i in range(1, len(found_orders)):
        if found_orders[i] < found_orders[i - 1]:
            return False
    return True


def analyze_page_structure(url: str) -> PageAnalysisResult:
    """Perform a complete page structure analysis.

    Fetches the landing page and checks for the presence of all 12
    sections in the landing page anatomy framework.

    Args:
        url: The landing page URL to analyze.

    Returns:
        PageAnalysisResult with findings and recommendations.
    """
    result = PageAnalysisResult(url=url)

    # Validate URL
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        result.errors.append("Invalid URL. Please provide a full URL including https://")
        return result

    # Fetch the page
    soup = fetch_page(url)
    if soup is None:
        result.errors.append(
            "Could not fetch the page. This may be due to JavaScript rendering "
            "(SPA), access restrictions, or network issues."
        )
        return result

    # Detect each section
    section_results = []
    for section_key, definition in SECTION_DEFINITIONS.items():
        section_result = detect_section(soup, section_key, definition)
        section_results.append(section_result)

    # Sort by order for display
    section_results.sort(key=lambda s: s.order)

    # Categorize found and missing
    result.sections_found = [s.name for s in section_results if s.detected]
    result.sections_missing = [s.name for s in section_results if not s.detected]

    # Calculate completeness
    total_sections = len(SECTION_DEFINITIONS)
    found_count = len(result.sections_found)
    result.completeness_score = round((found_count / total_sections) * 100, 1)

    # Evaluate section order
    result.section_order_optimal = evaluate_section_order(section_results)

    # Build section details
    result.section_details = [
        {
            "section": s.name,
            "detected": s.detected,
            "confidence": s.confidence,
            "signals_count": len(s.signals),
        }
        for s in section_results
    ]

    # Generate recommendations
    for section_key, definition in SECTION_DEFINITIONS.items():
        matching = [s for s in section_results if s.key == section_key]
        if matching and not matching[0].detected:
            result.recommendations.append(
                f"[Missing: {definition['name']}] {definition['recommendation']}"
            )

    if not result.section_order_optimal:
        result.recommendations.append(
            "[Section Order] Consider reordering your page sections to follow "
            "the optimal flow: Hero > Social Proof > Problem > Solution > "
            "Features > How It Works > Testimonials > Pricing > FAQ > "
            "Integrations > Final CTA > Footer."
        )

    if result.completeness_score < 50:
        result.recommendations.insert(
            0,
            f"[Low Completeness] Your page has only {found_count}/12 recommended "
            f"sections ({result.completeness_score}%). Adding the missing sections "
            f"could significantly improve conversion rates."
        )

    return result


def format_report(result: PageAnalysisResult) -> str:
    """Format the analysis result as a readable report.

    Args:
        result: The completed analysis result.

    Returns:
        Formatted report string.
    """
    lines = [
        "=" * 60,
        "LANDING PAGE STRUCTURE ANALYSIS",
        "=" * 60,
        f"URL: {result.url}",
        "",
        f"COMPLETENESS: {len(result.sections_found)}/12 sections "
        f"({result.completeness_score}%)",
        f"Section Order: {'Optimal' if result.section_order_optimal else 'Suboptimal'}",
        "",
        "--- Sections Found ---",
    ]

    for detail in result.section_details:
        if detail["detected"]:
            lines.append(
                f"  [+] {detail['section']} "
                f"(confidence: {detail['confidence']})"
            )

    lines.append("")
    lines.append("--- Sections Missing ---")

    for detail in result.section_details:
        if not detail["detected"]:
            lines.append(f"  [-] {detail['section']}")

    lines.append("")
    lines.append("--- Recommendations ---")

    for i, rec in enumerate(result.recommendations, 1):
        lines.append(f"  {i}. {rec}")

    if result.errors:
        lines.extend(["", "--- Warnings ---"])
        for error in result.errors:
            lines.append(f"  ! {error}")

    lines.append("=" * 60)
    return "\n".join(lines)


def main() -> None:
    """Run the page structure analyzer from the command line."""
    if len(sys.argv) < 2:
        print("Usage: python page_structure_analyzer.py <landing_page_url>")
        print("Example: python page_structure_analyzer.py https://example.com")
        sys.exit(1)

    url = sys.argv[1]

    # Ensure URL has scheme
    if not url.startswith("http"):
        url = "https://" + url

    print(f"Analyzing page structure: {url}")
    print("Fetching page...")
    print()

    result = analyze_page_structure(url)

    # Print formatted report
    print(format_report(result))

    # Also output JSON for programmatic use
    print("\n--- JSON Output ---")
    print(json.dumps(asdict(result), indent=2))


if __name__ == "__main__":
    main()
