"""
Competitor Scanner for SaaS Competitive Analysis

Fetches a competitor's webpage and extracts publicly available signals
including page title, meta description, headers, CTAs, social links,
tech stack hints, and trust signals.

Requirements:
    pip install requests beautifulsoup4

Usage:
    from competitor_scanner import scan_competitor

    result = scan_competitor("https://example.com")
    print(result)
"""

import re
from typing import Any, Optional
from urllib.parse import urljoin, urlparse

try:
    import requests
    from bs4 import BeautifulSoup

    HAS_DEPENDENCIES = True
except ImportError:
    HAS_DEPENDENCIES = False


def scan_competitor(url: str) -> dict[str, Any]:
    """
    Scan a competitor's webpage and extract key signals.

    Fetches only the single provided URL (does not crawl additional pages).

    Args:
        url: The full URL to scan (e.g., "https://competitor.com").

    Returns:
        Dictionary with keys:
            - url (str): The scanned URL.
            - company_name (str): Inferred company name from domain or title.
            - value_proposition (str): Extracted from meta description or first H1.
            - pricing_url (str or None): Detected pricing page link.
            - tech_stack (list[str]): Hints about technology from page source.
            - social_links (dict[str, str]): Social media profile URLs found.
            - cta_texts (list[str]): Call-to-action button/link texts.
            - trust_signal_count (int): Count of trust indicators found.
            - has_blog (bool): Whether a blog link was detected.
            - has_integrations (bool): Whether an integrations page link was detected.
            - has_careers (bool): Whether a careers page link was detected.
            - raw_headers (dict[str, list[str]]): H1 and H2 header texts.
    """
    if not HAS_DEPENDENCIES:
        return {
            "error": (
                "Missing dependencies. Install with: pip install requests beautifulsoup4"
            ),
            "url": url,
        }

    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        }
        response = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
        response.raise_for_status()
    except requests.RequestException as e:
        return {"error": f"Failed to fetch URL: {e}", "url": url}

    soup = BeautifulSoup(response.text, "html.parser")
    parsed_url = urlparse(url)
    base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"

    # Extract company name from domain
    company_name = _extract_company_name(soup, parsed_url)

    # Extract page title
    page_title = soup.title.string.strip() if soup.title and soup.title.string else ""

    # Extract meta description
    meta_desc = _extract_meta(soup, "description")

    # Extract OG tags
    og_tags = _extract_og_tags(soup)

    # Extract headers
    h1_texts = [h.get_text(strip=True) for h in soup.find_all("h1")]
    h2_texts = [h.get_text(strip=True) for h in soup.find_all("h2")]

    # Determine value proposition
    value_proposition = _determine_value_proposition(meta_desc, og_tags, h1_texts)

    # Find pricing page link
    pricing_url = _find_link_by_keywords(
        soup, base_url, ["pricing", "plans", "packages"]
    )

    # Find social links
    social_links = _extract_social_links(soup)

    # Detect tech stack hints
    tech_stack = _detect_tech_stack(response.text, soup)

    # Extract CTA texts
    cta_texts = _extract_ctas(soup)

    # Count trust signals
    trust_signal_count = _count_trust_signals(soup)

    # Check for blog, integrations, careers pages
    has_blog = _find_link_by_keywords(
        soup, base_url, ["blog", "articles", "resources", "news"]
    ) is not None

    has_integrations = _find_link_by_keywords(
        soup, base_url, ["integrations", "apps", "marketplace", "connect"]
    ) is not None

    has_careers = _find_link_by_keywords(
        soup, base_url, ["careers", "jobs", "hiring", "join-us", "open-positions"]
    ) is not None

    return {
        "url": url,
        "company_name": company_name,
        "page_title": page_title,
        "meta_description": meta_desc,
        "og_tags": og_tags,
        "value_proposition": value_proposition,
        "pricing_url": pricing_url,
        "tech_stack": tech_stack,
        "social_links": social_links,
        "cta_texts": cta_texts,
        "trust_signal_count": trust_signal_count,
        "has_blog": has_blog,
        "has_integrations": has_integrations,
        "has_careers": has_careers,
        "raw_headers": {"h1": h1_texts, "h2": h2_texts},
    }


def _extract_company_name(soup: Any, parsed_url: Any) -> str:
    """Infer company name from OG site name, title, or domain."""
    og_site = soup.find("meta", property="og:site_name")
    if og_site and og_site.get("content"):
        return og_site["content"].strip()

    if soup.title and soup.title.string:
        title = soup.title.string.strip()
        # Take the first segment before common separators
        for sep in [" | ", " - ", " : "]:
            if sep in title:
                return title.split(sep)[0].strip()
        return title

    # Fall back to domain name
    domain = parsed_url.netloc.replace("www.", "")
    return domain.split(".")[0].capitalize()


def _extract_meta(soup: Any, name: str) -> str:
    """Extract a meta tag content by name."""
    tag = soup.find("meta", attrs={"name": name})
    if tag and tag.get("content"):
        return tag["content"].strip()
    return ""


def _extract_og_tags(soup: Any) -> dict[str, str]:
    """Extract Open Graph meta tags."""
    og_tags: dict[str, str] = {}
    for tag in soup.find_all("meta", property=re.compile(r"^og:")):
        prop = tag.get("property", "")
        content = tag.get("content", "")
        if prop and content:
            key = prop.replace("og:", "")
            og_tags[key] = content.strip()
    return og_tags


def _determine_value_proposition(
    meta_desc: str, og_tags: dict[str, str], h1_texts: list[str]
) -> str:
    """Determine the value proposition from available signals."""
    if og_tags.get("description"):
        return og_tags["description"]
    if meta_desc:
        return meta_desc
    if h1_texts:
        return h1_texts[0]
    return "Could not determine value proposition from page content"


def _find_link_by_keywords(
    soup: Any, base_url: str, keywords: list[str]
) -> Optional[str]:
    """Find the first link whose href or text matches any keyword."""
    for link in soup.find_all("a", href=True):
        href = link["href"].lower()
        text = link.get_text(strip=True).lower()
        for kw in keywords:
            if kw in href or kw in text:
                full_url = urljoin(base_url, link["href"])
                return full_url
    return None


def _extract_social_links(soup: Any) -> dict[str, str]:
    """Extract social media profile links."""
    social_patterns = {
        "twitter": r"(twitter\.com|x\.com)/[^/\s\"']+",
        "linkedin": r"linkedin\.com/(company|in)/[^/\s\"']+",
        "facebook": r"facebook\.com/[^/\s\"']+",
        "youtube": r"youtube\.com/(c/|channel/|@)[^/\s\"']+",
        "instagram": r"instagram\.com/[^/\s\"']+",
        "github": r"github\.com/[^/\s\"']+",
    }

    social_links: dict[str, str] = {}
    for link in soup.find_all("a", href=True):
        href = link["href"]
        for platform, pattern in social_patterns.items():
            if platform not in social_links and re.search(pattern, href, re.IGNORECASE):
                social_links[platform] = href
    return social_links


def _detect_tech_stack(html: str, soup: Any) -> list[str]:
    """Detect technology hints from page source."""
    tech_signals: list[str] = []

    # Check for common frameworks and tools
    checks = {
        "React": [r"react", r"__next", r"_next/static"],
        "Next.js": [r"__next", r"_next/static", r"next/router"],
        "Vue.js": [r"vue\.js", r"__vue", r"v-cloak"],
        "Angular": [r"ng-version", r"angular"],
        "WordPress": [r"wp-content", r"wp-includes"],
        "Webflow": [r"webflow\.com", r"wf-"],
        "Framer": [r"framer\.com", r"framer-"],
        "Intercom": [r"intercom", r"intercomSettings"],
        "Drift": [r"drift\.com", r"driftt"],
        "HubSpot": [r"hubspot", r"hs-scripts"],
        "Google Analytics": [r"google-analytics", r"gtag", r"googletagmanager"],
        "Segment": [r"segment\.com/analytics", r"analytics\.js"],
        "Hotjar": [r"hotjar"],
        "Stripe": [r"stripe\.com", r"js\.stripe"],
        "Cloudflare": [r"cloudflare", r"cf-ray"],
    }

    html_lower = html.lower()
    for tech, patterns in checks.items():
        for pattern in patterns:
            if re.search(pattern, html_lower):
                tech_signals.append(tech)
                break

    return sorted(set(tech_signals))


def _extract_ctas(soup: Any) -> list[str]:
    """Extract call-to-action texts from buttons and prominent links."""
    cta_texts: list[str] = []

    # Check buttons
    for button in soup.find_all("button"):
        text = button.get_text(strip=True)
        if text and len(text) < 50:
            cta_texts.append(text)

    # Check links with CTA-like classes or common CTA phrases
    cta_keywords = [
        "sign up", "get started", "start free", "try free", "book a demo",
        "request demo", "schedule demo", "free trial", "start trial",
        "contact sales", "talk to sales", "learn more", "see pricing",
    ]

    for link in soup.find_all("a", href=True):
        text = link.get_text(strip=True)
        if not text or len(text) > 50:
            continue
        text_lower = text.lower()
        # Check if it matches CTA keywords
        for kw in cta_keywords:
            if kw in text_lower:
                cta_texts.append(text)
                break
        # Check for CTA-like CSS classes
        classes = " ".join(link.get("class", []))
        if any(c in classes.lower() for c in ["cta", "btn-primary", "button"]):
            if text not in cta_texts:
                cta_texts.append(text)

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique_ctas: list[str] = []
    for cta in cta_texts:
        if cta not in seen:
            seen.add(cta)
            unique_ctas.append(cta)

    return unique_ctas


def _count_trust_signals(soup: Any) -> int:
    """Count trust signals on the page (testimonials, logos, badges, reviews)."""
    count = 0

    # Check for common trust signal patterns in class names and IDs
    trust_keywords = [
        "testimonial", "review", "customer-logo", "client-logo", "trust",
        "social-proof", "case-study", "badge", "certification", "award",
        "as-seen", "featured-in", "partner-logo",
    ]

    for element in soup.find_all(True):
        classes = " ".join(element.get("class", [])).lower()
        element_id = (element.get("id") or "").lower()
        for kw in trust_keywords:
            if kw in classes or kw in element_id:
                count += 1
                break

    # Check for star rating patterns
    star_elements = soup.find_all(
        True, class_=re.compile(r"star|rating", re.IGNORECASE)
    )
    count += len(star_elements)

    # Check for blockquotes (often used for testimonials)
    count += len(soup.find_all("blockquote"))

    return count


def main() -> None:
    """Standalone demo of the competitor scanner."""
    print("=" * 60)
    print("Competitor Scanner - Demo")
    print("=" * 60)

    if not HAS_DEPENDENCIES:
        print("\nDependencies not installed.")
        print("Install with: pip install requests beautifulsoup4")
        print("\nShowing sample output structure instead:\n")

        sample_result = {
            "url": "https://example.com",
            "company_name": "Example",
            "page_title": "Example - The Best Tool for Teams",
            "meta_description": "Example helps teams collaborate better.",
            "og_tags": {"title": "Example", "description": "Collaborate better."},
            "value_proposition": "Example helps teams collaborate better.",
            "pricing_url": "https://example.com/pricing",
            "tech_stack": ["Google Analytics", "Intercom", "React"],
            "social_links": {
                "twitter": "https://twitter.com/example",
                "linkedin": "https://linkedin.com/company/example",
            },
            "cta_texts": ["Get Started Free", "Book a Demo"],
            "trust_signal_count": 12,
            "has_blog": True,
            "has_integrations": True,
            "has_careers": True,
            "raw_headers": {
                "h1": ["Collaborate better with your team"],
                "h2": ["Features", "Pricing", "Testimonials"],
            },
        }

        _print_result(sample_result)
        return

    # Demo with a real URL
    demo_url = "https://example.com"
    print(f"\nScanning: {demo_url}")
    print("-" * 60)

    result = scan_competitor(demo_url)

    if "error" in result:
        print(f"Error: {result['error']}")
    else:
        _print_result(result)


def _print_result(result: dict[str, Any]) -> None:
    """Pretty-print a scanner result."""
    print(f"\n  URL:               {result['url']}")
    print(f"  Company Name:      {result['company_name']}")
    print(f"  Page Title:        {result.get('page_title', 'N/A')}")
    print(f"  Value Proposition: {result['value_proposition']}")
    print(f"  Pricing URL:       {result.get('pricing_url', 'Not found')}")

    tech = result.get("tech_stack", [])
    print(f"  Tech Stack:        {', '.join(tech) if tech else 'None detected'}")

    social = result.get("social_links", {})
    if social:
        print(f"  Social Links:")
        for platform, link in social.items():
            print(f"    - {platform}: {link}")
    else:
        print(f"  Social Links:      None found")

    ctas = result.get("cta_texts", [])
    if ctas:
        print(f"  CTAs Found:")
        for cta in ctas:
            print(f"    - {cta}")
    else:
        print(f"  CTAs:              None found")

    print(f"  Trust Signals:     {result.get('trust_signal_count', 0)}")
    print(f"  Has Blog:          {'Yes' if result.get('has_blog') else 'No'}")
    print(f"  Has Integrations:  {'Yes' if result.get('has_integrations') else 'No'}")
    print(f"  Has Careers:       {'Yes' if result.get('has_careers') else 'No'}")

    headers = result.get("raw_headers", {})
    h1s = headers.get("h1", [])
    h2s = headers.get("h2", [])
    if h1s:
        print(f"  H1 Headers:")
        for h in h1s[:5]:
            print(f"    - {h}")
    if h2s:
        print(f"  H2 Headers:")
        for h in h2s[:10]:
            print(f"    - {h}")


if __name__ == "__main__":
    main()
