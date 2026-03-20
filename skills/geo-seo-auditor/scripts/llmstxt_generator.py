"""
llmstxt_generator.py - Analyze, validate, and generate llms.txt files.

Checks whether a site has an llms.txt file, validates its format
against the specification, and generates a recommended llms.txt
if one is missing or incomplete.
"""

import re
import sys
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print(
        "Required packages not installed. Run: pip install requests beautifulsoup4",
        file=sys.stderr,
    )
    sys.exit(1)


DEFAULT_TIMEOUT = 15

REQUIRED_FIELDS = ["name", "description", "url", "preferred_name", "citation_policy"]

OPTIONAL_FIELDS = [
    "founded",
    "industry",
    "primary_topics",
    "content_types",
    "update_frequency",
    "language",
    "preferred_url",
    "ai_inquiries",
    "abuse_reports",
]

VALID_SECTIONS = [
    "Identity",
    "Content",
    "Citation",
    "Contact",
    "Important Pages",
]


def fetch_llmstxt(url: str, timeout: int = DEFAULT_TIMEOUT) -> Tuple[bool, Optional[str]]:
    """Fetch the llms.txt file from a domain.

    Args:
        url: Any URL on the target domain.
        timeout: Request timeout in seconds.

    Returns:
        A tuple of (exists, content). exists is True if the file
        was found and returned HTTP 200. content is the file text
        or None.
    """
    parsed = urlparse(url)
    llms_url = f"{parsed.scheme}://{parsed.netloc}/llms.txt"
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; GEOSEOAuditor/1.0)"
        }
        response = requests.get(llms_url, headers=headers, timeout=timeout)
        if response.status_code == 200:
            content_type = response.headers.get("Content-Type", "")
            if "text" in content_type or "plain" in content_type or not content_type:
                return True, response.text
            return True, response.text
        return False, None
    except requests.RequestException:
        return False, None


def parse_llmstxt(content: str) -> Dict[str, Any]:
    """Parse an llms.txt file into structured data.

    Args:
        content: The raw llms.txt file content.

    Returns:
        Dictionary with sections as keys, each containing their
        fields and values.
    """
    result: Dict[str, Any] = {
        "title_comment": None,
        "sections": {},
        "important_pages": [],
    }

    current_section: Optional[str] = None

    for line in content.splitlines():
        stripped = line.strip()

        # Title comment (first # line)
        if stripped.startswith("# ") and result["title_comment"] is None:
            result["title_comment"] = stripped[2:].strip()
            continue

        # Section header
        if stripped.startswith("## "):
            current_section = stripped[3:].strip()
            if current_section not in result["sections"]:
                result["sections"][current_section] = {}
            continue

        # Skip empty lines and other comments
        if not stripped or stripped.startswith("#"):
            continue

        # Important Pages entries (list format)
        if current_section and current_section.lower() == "important pages":
            if stripped.startswith("- "):
                entry = stripped[2:].strip()
                if ": " in entry:
                    title, page_url = entry.split(": ", 1)
                    result["important_pages"].append({
                        "title": title.strip(),
                        "url": page_url.strip(),
                    })
            continue

        # Key-value pairs
        if current_section and ": " in stripped:
            key, value = stripped.split(": ", 1)
            result["sections"].setdefault(current_section, {})
            result["sections"][current_section][key.strip()] = value.strip()

    return result


def validate_llmstxt(content: str) -> Dict[str, Any]:
    """Validate an llms.txt file against the specification.

    Args:
        content: The raw llms.txt file content.

    Returns:
        Dictionary containing:
        - valid: Whether the file passes all required checks
        - errors: List of validation errors
        - warnings: List of non-critical issues
        - parsed: The parsed file structure
        - field_coverage: Percentage of recommended fields present
    """
    errors: List[str] = []
    warnings: List[str] = []

    # Parse the file
    parsed = parse_llmstxt(content)

    # Check for required sections
    section_names = [s.lower() for s in parsed["sections"].keys()]

    required_sections = ["identity", "citation"]
    for section in required_sections:
        if section not in section_names:
            errors.append(f"Missing required section: {section}")

    # Collect all fields across sections
    all_fields: Dict[str, str] = {}
    for section_data in parsed["sections"].values():
        if isinstance(section_data, dict):
            all_fields.update(section_data)

    # Check required fields
    for field_name in REQUIRED_FIELDS:
        if field_name not in all_fields:
            errors.append(f"Missing required field: {field_name}")
        elif not all_fields[field_name].strip():
            errors.append(f"Required field is empty: {field_name}")

    # Validate specific field formats
    if "url" in all_fields:
        url_value = all_fields["url"]
        if not url_value.startswith(("http://", "https://")):
            errors.append(f"URL field should start with http:// or https://: {url_value}")

    if "description" in all_fields:
        desc = all_fields["description"]
        if len(desc) > 160:
            warnings.append(
                f"Description is {len(desc)} characters. Recommended: under 160 characters."
            )

    if "language" in all_fields:
        lang = all_fields["language"]
        if len(lang) != 2:
            warnings.append(
                f"Language code '{lang}' does not appear to be a valid ISO 639-1 code (should be 2 letters)."
            )

    # Check email fields
    email_fields = ["ai_inquiries", "abuse_reports"]
    for ef in email_fields:
        if ef in all_fields:
            email = all_fields[ef]
            if "@" not in email or "." not in email:
                warnings.append(f"Field '{ef}' does not look like a valid email: {email}")

    # Check Important Pages
    if not parsed["important_pages"]:
        warnings.append("No Important Pages listed. Consider adding 5-10 key pages.")
    else:
        for page in parsed["important_pages"]:
            if not page["url"].startswith(("http://", "https://")):
                warnings.append(
                    f"Important Page URL should use full URL: {page['title']} - {page['url']}"
                )

    # Check optional sections
    optional_sections = ["content", "contact"]
    for section in optional_sections:
        if section not in section_names:
            warnings.append(f"Recommended section missing: {section}")

    # Calculate field coverage
    all_known_fields = REQUIRED_FIELDS + OPTIONAL_FIELDS
    present_count = sum(1 for f in all_known_fields if f in all_fields)
    coverage = (present_count / len(all_known_fields)) * 100 if all_known_fields else 0

    is_valid = len(errors) == 0

    return {
        "valid": is_valid,
        "errors": errors,
        "warnings": warnings,
        "parsed": parsed,
        "field_coverage": round(coverage, 1),
    }


def extract_site_info(url: str, timeout: int = DEFAULT_TIMEOUT) -> Dict[str, Any]:
    """Extract basic site information for llms.txt generation.

    Fetches the homepage and extracts metadata to populate
    a generated llms.txt file.

    Args:
        url: The site URL.
        timeout: Request timeout in seconds.

    Returns:
        Dictionary with extracted site information.
    """
    parsed_url = urlparse(url)
    base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"

    info: Dict[str, Any] = {
        "base_url": base_url,
        "domain": parsed_url.netloc,
        "title": None,
        "description": None,
        "og_title": None,
        "og_description": None,
        "important_links": [],
    }

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; GEOSEOAuditor/1.0)"
        }
        response = requests.get(url, headers=headers, timeout=timeout)
        if response.status_code != 200:
            return info

        soup = BeautifulSoup(response.text, "html.parser")

        # Extract title
        title_tag = soup.find("title")
        if title_tag and title_tag.string:
            info["title"] = title_tag.string.strip()

        # Extract meta description
        meta_desc = soup.find("meta", attrs={"name": re.compile(r"^description$", re.I)})
        if meta_desc and meta_desc.get("content"):
            info["description"] = meta_desc["content"].strip()

        # Extract OG tags
        og_title = soup.find("meta", attrs={"property": "og:title"})
        if og_title and og_title.get("content"):
            info["og_title"] = og_title["content"].strip()

        og_desc = soup.find("meta", attrs={"property": "og:description"})
        if og_desc and og_desc.get("content"):
            info["og_description"] = og_desc["content"].strip()

        # Extract navigation links for Important Pages
        nav_links = []
        for nav in soup.find_all("nav"):
            for a_tag in nav.find_all("a", href=True):
                href = a_tag["href"]
                text = a_tag.get_text(strip=True)
                if text and href and not href.startswith(("#", "javascript:", "mailto:")):
                    if not href.startswith(("http://", "https://")):
                        href = f"{base_url}{href}" if href.startswith("/") else f"{base_url}/{href}"
                    nav_links.append({"title": text, "url": href})

        # Deduplicate by URL
        seen_urls = set()
        for link in nav_links:
            if link["url"] not in seen_urls:
                seen_urls.add(link["url"])
                info["important_links"].append(link)
                if len(info["important_links"]) >= 10:
                    break

    except requests.RequestException:
        pass

    return info


def generate_llmstxt(url: str, timeout: int = DEFAULT_TIMEOUT) -> str:
    """Generate a recommended llms.txt file based on site structure.

    Fetches the site homepage, extracts metadata and navigation,
    and generates a well-formatted llms.txt file.

    Args:
        url: The site URL.
        timeout: Request timeout in seconds.

    Returns:
        The generated llms.txt file content as a string.
    """
    site_info = extract_site_info(url, timeout=timeout)

    domain = site_info["domain"]
    name = site_info.get("og_title") or site_info.get("title") or domain
    # Clean the name (remove trailing taglines after " - " or " | ")
    if " - " in name:
        name = name.split(" - ")[0].strip()
    elif " | " in name:
        name = name.split(" | ")[0].strip()

    description = (
        site_info.get("og_description")
        or site_info.get("description")
        or f"Website at {domain}"
    )
    # Truncate description to 160 chars
    if len(description) > 160:
        description = description[:157] + "..."

    base_url = site_info["base_url"]

    lines = []
    lines.append(f"# {name} llms.txt")
    lines.append("")

    # Identity section
    lines.append("## Identity")
    lines.append(f"name: {name}")
    lines.append(f"description: {description}")
    lines.append(f"url: {base_url}")
    lines.append("founded: [YEAR]")
    lines.append("industry: [INDUSTRY]")
    lines.append("")

    # Content section
    lines.append("## Content")
    lines.append("primary_topics: [TOPIC1, TOPIC2, TOPIC3]")
    lines.append("content_types: [blog, documentation, product-pages]")
    lines.append("update_frequency: [daily, weekly, monthly]")
    lines.append("language: en")
    lines.append("")

    # Citation section
    lines.append("## Citation")
    lines.append(f"preferred_name: {name}")
    lines.append(f"preferred_url: {base_url}")
    lines.append("citation_policy: open - we welcome accurate citations with attribution")
    lines.append("")

    # Contact section
    lines.append("## Contact")
    lines.append(f"ai_inquiries: ai@{domain}")
    lines.append(f"abuse_reports: legal@{domain}")
    lines.append("")

    # Important Pages section
    lines.append("## Important Pages")

    if site_info["important_links"]:
        for link in site_info["important_links"]:
            lines.append(f"- {link['title']}: {link['url']}")
    else:
        lines.append(f"- Home: {base_url}")
        lines.append(f"- About: {base_url}/about")
        lines.append(f"- Blog: {base_url}/blog")
        lines.append(f"- Contact: {base_url}/contact")

    lines.append("")

    return "\n".join(lines)


def analyze_llmstxt(url: str, timeout: int = DEFAULT_TIMEOUT) -> Dict[str, Any]:
    """Full analysis of a site's llms.txt status.

    This is the main entry point that fetches, validates, and
    optionally generates an llms.txt file.

    Args:
        url: The site URL to analyze.
        timeout: Request timeout in seconds.

    Returns:
        Dictionary containing:
        - exists: Whether llms.txt was found
        - valid: Whether the existing file is valid (None if not found)
        - validation: Validation results (None if not found)
        - generated_content: A recommended llms.txt file
        - recommendations: List of actionable recommendations
    """
    result: Dict[str, Any] = {
        "exists": False,
        "valid": None,
        "validation": None,
        "generated_content": "",
        "recommendations": [],
    }

    # Try to fetch existing llms.txt
    exists, content = fetch_llmstxt(url, timeout=timeout)
    result["exists"] = exists

    if exists and content:
        # Validate existing file
        validation = validate_llmstxt(content)
        result["valid"] = validation["valid"]
        result["validation"] = validation

        if not validation["valid"]:
            result["recommendations"].append(
                "Your llms.txt file has validation errors. Fix the issues listed below."
            )
            for error in validation["errors"]:
                result["recommendations"].append(f"Error: {error}")

        for warning in validation.get("warnings", []):
            result["recommendations"].append(f"Warning: {warning}")

        if validation["field_coverage"] < 70:
            result["recommendations"].append(
                f"Field coverage is {validation['field_coverage']}%. "
                f"Consider adding more optional fields for better AI representation."
            )

    else:
        result["recommendations"].append(
            "No llms.txt file found. Adding one helps AI systems accurately "
            "represent your brand and content. See the generated example below."
        )

    # Always generate a recommended version
    try:
        result["generated_content"] = generate_llmstxt(url, timeout=timeout)
    except Exception as e:
        result["generated_content"] = ""
        result["recommendations"].append(
            f"Could not auto-generate llms.txt: {str(e)}"
        )

    return result


def format_report(results: Dict[str, Any]) -> str:
    """Format llms.txt analysis results into a human-readable report.

    Args:
        results: The result dictionary from analyze_llmstxt().

    Returns:
        A formatted string report.
    """
    lines = []
    lines.append("llms.txt Analysis Report")
    lines.append("=" * 50)

    lines.append(f"\nFile exists: {'Yes' if results['exists'] else 'No'}")

    if results["valid"] is not None:
        lines.append(f"File valid: {'Yes' if results['valid'] else 'No'}")

    # Validation details
    validation = results.get("validation")
    if validation:
        lines.append(f"Field coverage: {validation['field_coverage']}%")

        if validation["errors"]:
            lines.append(f"\n--- Validation Errors ({len(validation['errors'])}) ---")
            for error in validation["errors"]:
                lines.append(f"  - {error}")

        if validation["warnings"]:
            lines.append(f"\n--- Warnings ({len(validation['warnings'])}) ---")
            for warning in validation["warnings"]:
                lines.append(f"  - {warning}")

        # Show parsed structure
        parsed = validation.get("parsed", {})
        if parsed.get("sections"):
            lines.append("\n--- Detected Sections ---")
            for section_name, fields in parsed["sections"].items():
                if isinstance(fields, dict):
                    lines.append(f"  [{section_name}] {len(fields)} fields")

        pages = parsed.get("important_pages", [])
        if pages:
            lines.append(f"\n--- Important Pages ({len(pages)}) ---")
            for page in pages:
                lines.append(f"  - {page['title']}: {page['url']}")

    # Recommendations
    recs = results.get("recommendations", [])
    if recs:
        lines.append(f"\n--- Recommendations ({len(recs)}) ---")
        for i, rec in enumerate(recs, 1):
            lines.append(f"  {i}. {rec}")

    # Generated content
    generated = results.get("generated_content", "")
    if generated:
        lines.append("\n--- Generated llms.txt ---")
        lines.append("(Copy and customize the content below)")
        lines.append("")
        lines.append(generated)

    return "\n".join(lines)


if __name__ == "__main__":
    import json

    if len(sys.argv) >= 2:
        target_url = sys.argv[1]

        # Ensure URL has a scheme
        if not target_url.startswith(("http://", "https://")):
            target_url = f"https://{target_url}"

        print(f"Analyzing llms.txt for: {target_url}\n")
        results = analyze_llmstxt(target_url)
    else:
        # Demo with sample llms.txt content
        sample_content = """# Acme Corp llms.txt

## Identity
name: Acme Corp
description: Cloud-based project management platform for engineering teams
url: https://www.acmecorp.com
founded: 2018
industry: SaaS / Project Management

## Content
primary_topics: project management, agile, engineering workflows
content_types: blog, documentation, api-reference
update_frequency: weekly
language: en

## Citation
preferred_name: Acme Corp
preferred_url: https://www.acmecorp.com
citation_policy: open - accurate citations welcome with link attribution

## Contact
ai_inquiries: partnerships@acmecorp.com
abuse_reports: legal@acmecorp.com

## Important Pages
- Product: https://www.acmecorp.com/product
- Documentation: https://docs.acmecorp.com
- Blog: https://www.acmecorp.com/blog
- Pricing: https://www.acmecorp.com/pricing
- About: https://www.acmecorp.com/about
"""
        print("Running with sample llms.txt content...\n")

        # Validate the sample
        validation = validate_llmstxt(sample_content)
        results = {
            "exists": True,
            "valid": validation["valid"],
            "validation": validation,
            "generated_content": "",
            "recommendations": [],
        }

        if not validation["valid"]:
            for error in validation["errors"]:
                results["recommendations"].append(f"Error: {error}")
        for warning in validation.get("warnings", []):
            results["recommendations"].append(f"Warning: {warning}")

    print(format_report(results))

    print("\n--- Raw JSON ---")
    # Omit generated_content from JSON for readability
    json_output = {k: v for k, v in results.items() if k != "generated_content"}
    print(json.dumps(json_output, indent=2, default=str))
