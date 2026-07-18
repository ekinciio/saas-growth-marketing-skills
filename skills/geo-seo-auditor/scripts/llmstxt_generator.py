"""
llmstxt_generator.py - Analyze, validate, and generate llms.txt files.

Checks whether a site has an llms.txt file, validates it against the
llms.txt proposal (llmstxt.org), and generates a recommended llms.txt
if one is missing or incomplete.

The llms.txt format is pure Markdown:
- A required H1 with the site/project name (the only hard requirement)
- A recommended blockquote summary directly after the H1
- Optional free-form markdown details (no headings)
- Zero or more H2 sections containing link lists of the form
  `- [name](url): optional notes`
- A special `## Optional` section whose links AI systems may skip
  when a shorter context is needed
"""

import re
import sys
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

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

# Delay between sequential requests to the same site (politeness)
REQUEST_DELAY_SECONDS = 1

# A curated llms.txt should stay small; warn beyond these bounds
MAX_RECOMMENDED_LINES = 500
MAX_RECOMMENDED_LINKS = 200

# Matches `- [title](url)` or `* [title](url)`, optionally `: notes`
LINK_ENTRY_RE = re.compile(
    r"^[-*]\s+\[(?P<title>[^\]]+)\]\((?P<url>[^)\s]+)\)\s*(?::\s*(?P<notes>.*))?$"
)


def fetch_llmstxt(url: str, timeout: int = DEFAULT_TIMEOUT) -> Tuple[bool, Optional[str]]:
    """Fetch the llms.txt file from a domain.

    Args:
        url: Any URL on the target domain.
        timeout: Request timeout in seconds.

    Returns:
        A tuple of (exists, content). exists is True if the file
        was found, returned HTTP 200, and is not an HTML page
        (SPA catch-all routes often return the app shell for any
        path, which is not a real llms.txt). content is the file
        text or None.
    """
    parsed = urlparse(url)
    llms_url = f"{parsed.scheme}://{parsed.netloc}/llms.txt"
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; GEOSEOAuditor/1.0)"
        }
        response = requests.get(llms_url, headers=headers, timeout=timeout)
        if response.status_code == 200:
            body = response.text
            # Sniff for HTML bodies: a SPA catch-all serving index.html
            # at /llms.txt is a false positive, not a real llms.txt.
            body_head = body.lstrip()[:200].lower()
            if body_head.startswith("<!doctype") or body_head.startswith("<html"):
                return False, None
            return True, body
        return False, None
    except requests.RequestException:
        return False, None


def parse_llmstxt(content: str) -> Dict[str, Any]:
    """Parse an llms.txt file into structured data.

    Args:
        content: The raw llms.txt file content.

    Returns:
        Dictionary with:
        - title: The H1 text (site/project name), or None
        - summary: The blockquote summary text, or None
        - details: Free-form markdown lines before the first H2
        - sections: Dict mapping H2 section name to a list of link
          entries ({title, url, notes})
        - has_optional_section: Whether an `## Optional` section exists
    """
    result: Dict[str, Any] = {
        "title": None,
        "summary": None,
        "details": [],
        "sections": {},
        "has_optional_section": False,
    }

    # Strip an optional byte-order mark
    content = content.lstrip("\ufeff")

    current_section: Optional[str] = None
    summary_lines: List[str] = []

    for line in content.splitlines():
        stripped = line.strip()

        # H1 title (first one wins)
        if stripped.startswith("# ") and result["title"] is None:
            result["title"] = stripped[2:].strip()
            continue

        # H2 section header
        if stripped.startswith("## "):
            current_section = stripped[3:].strip()
            result["sections"].setdefault(current_section, [])
            if current_section.lower() == "optional":
                result["has_optional_section"] = True
            continue

        # Blockquote summary (before the first H2 only)
        if stripped.startswith(">") and current_section is None:
            summary_lines.append(stripped.lstrip("> ").strip())
            continue

        if not stripped:
            continue

        # Link-list entries inside H2 sections
        if current_section is not None:
            match = LINK_ENTRY_RE.match(stripped)
            if match:
                result["sections"][current_section].append({
                    "title": match.group("title").strip(),
                    "url": match.group("url").strip(),
                    "notes": (match.group("notes") or "").strip() or None,
                })
            continue

        # Free-form details between the summary and the first H2
        result["details"].append(stripped)

    if summary_lines:
        result["summary"] = " ".join(summary_lines).strip() or None

    return result


def validate_llmstxt(content: str) -> Dict[str, Any]:
    """Validate an llms.txt file against the llms.txt proposal.

    The only hard requirement is an H1 with the site/project name.
    Everything else (blockquote summary, H2 link-list sections,
    valid URLs, reasonable length) is a recommendation and produces
    warnings rather than errors.

    Args:
        content: The raw llms.txt file content.

    Returns:
        Dictionary containing:
        - valid: Whether the file passes the required checks
        - errors: List of validation errors (required checks)
        - warnings: List of non-critical issues (recommendations)
        - parsed: The parsed file structure
        - coverage: Percentage of recommended checks passed
    """
    errors: List[str] = []
    warnings: List[str] = []

    parsed = parse_llmstxt(content)

    # Required: H1 with the site/project name
    if not parsed["title"]:
        errors.append(
            "Missing required H1 title. The file must start with "
            "'# Site Name' (the only hard requirement of the spec)."
        )

    # Recommended: blockquote summary after the H1
    has_summary = bool(parsed["summary"])
    if not has_summary:
        warnings.append(
            "No blockquote summary found. Add '> One-line summary' "
            "directly after the H1 so AI systems get key context first."
        )

    # Recommended: at least one H2 section containing link entries
    all_links: List[Dict[str, Any]] = []
    for entries in parsed["sections"].values():
        all_links.extend(entries)

    has_sections = bool(parsed["sections"])
    has_links = bool(all_links)
    if not has_sections:
        warnings.append(
            "No H2 sections found. Add sections like '## Docs' containing "
            "'- [title](url): notes' link lists."
        )
    elif not has_links:
        warnings.append(
            "H2 sections exist but contain no '- [title](url)' link entries. "
            "Each section should be a markdown list of links."
        )

    # Recommended: link URLs are well-formed absolute URLs
    urls_ok = True
    for link in all_links:
        if not link["url"].startswith(("http://", "https://")):
            urls_ok = False
            warnings.append(
                f"Link '{link['title']}' does not use an absolute http(s) URL: {link['url']}"
            )

    # Recommended: reasonable length (curated overview, not a sitemap dump)
    line_count = len(content.splitlines())
    length_ok = True
    if line_count > MAX_RECOMMENDED_LINES or len(all_links) > MAX_RECOMMENDED_LINKS:
        length_ok = False
        warnings.append(
            f"File is very long ({line_count} lines, {len(all_links)} links). "
            "llms.txt should be a curated overview, not an exhaustive sitemap."
        )

    # Coverage of recommended elements
    checks = [
        bool(parsed["title"]),
        has_summary,
        has_sections,
        has_links,
        urls_ok,
        length_ok,
    ]
    coverage = (sum(1 for c in checks if c) / len(checks)) * 100

    is_valid = len(errors) == 0

    return {
        "valid": is_valid,
        "errors": errors,
        "warnings": warnings,
        "parsed": parsed,
        "coverage": round(coverage, 1),
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

        # Extract navigation links for section link lists
        nav_links = []
        for nav in soup.find_all("nav"):
            for a_tag in nav.find_all("a", href=True):
                href = a_tag["href"]
                text = a_tag.get_text(strip=True)
                if text and href and not href.startswith(("#", "javascript:", "mailto:")):
                    # urljoin handles relative, root-relative, and
                    # protocol-relative (//host/path) URLs correctly
                    href = urljoin(base_url + "/", href)
                    if href.startswith(("http://", "https://")):
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
    and generates an llms.txt file in the real markdown format:
    H1 title, blockquote summary, free-form details, and H2
    sections containing link lists (including an Optional section).

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
        or f"[Add a one-paragraph summary of what {domain} is and does.]"
    )

    base_url = site_info["base_url"]

    lines = []
    lines.append(f"# {name}")
    lines.append("")
    lines.append(f"> {description}")
    lines.append("")
    lines.append(
        "[Optional: add a few short paragraphs or bullet points with key facts "
        "an AI should know before reading the linked pages. Delete this placeholder.]"
    )
    lines.append("")

    links = site_info["important_links"]
    if links:
        # Primary links go in a Key Pages section; extras go in Optional
        primary = links[:6]
        extras = links[6:]

        lines.append("## Key Pages")
        lines.append("")
        for link in primary:
            lines.append(f"- [{link['title']}]({link['url']})")
        lines.append("")

        lines.append("## Optional")
        lines.append("")
        if extras:
            for link in extras:
                lines.append(f"- [{link['title']}]({link['url']})")
        else:
            lines.append(f"- [Blog]({base_url}/blog): Articles and updates")
        lines.append("")
    else:
        lines.append("## Key Pages")
        lines.append("")
        lines.append(f"- [Home]({base_url}): Main landing page")
        lines.append(f"- [About]({base_url}/about): Company background")
        lines.append(f"- [Contact]({base_url}/contact): How to get in touch")
        lines.append("")
        lines.append("## Optional")
        lines.append("")
        lines.append(f"- [Blog]({base_url}/blog): Articles and updates")
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

        if validation["coverage"] < 70:
            result["recommendations"].append(
                f"Recommended-element coverage is {validation['coverage']}%. "
                f"Consider adding the missing recommended elements (summary, "
                f"link-list sections) for better AI usability."
            )

    else:
        result["recommendations"].append(
            "No llms.txt file found. llms.txt is an emerging (not yet universally "
            "adopted) convention that helps AI systems find your key content. "
            "See the generated example below."
        )

    # Politeness delay before the next request to the same site
    time.sleep(REQUEST_DELAY_SECONDS)

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
        lines.append(f"Recommended-element coverage: {validation['coverage']}%")

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
        if parsed.get("title"):
            lines.append(f"\nTitle (H1): {parsed['title']}")
        if parsed.get("summary"):
            summary = parsed["summary"]
            if len(summary) > 120:
                summary = summary[:117] + "..."
            lines.append(f"Summary: {summary}")

        if parsed.get("sections"):
            lines.append("\n--- Detected Sections ---")
            for section_name, entries in parsed["sections"].items():
                lines.append(f"  [{section_name}] {len(entries)} links")
                for entry in entries[:5]:
                    lines.append(f"    - {entry['title']}: {entry['url']}")
                if len(entries) > 5:
                    lines.append(f"    ... and {len(entries) - 5} more")

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
        # Demo with sample llms.txt content (real markdown format)
        sample_content = """# Acme Corp

> Acme Corp is a cloud-based project management platform for engineering
> teams, combining sprint planning, roadmaps, and automated reporting.

Key facts:

- The docs are the authoritative source for feature behavior.
- The API is REST with token authentication.

## Docs

- [Product documentation](https://docs.acmecorp.com/index.md): Full user guide
- [API reference](https://docs.acmecorp.com/api.md): Endpoints and authentication
- [Quick start](https://docs.acmecorp.com/quickstart.md): Set up in 10 minutes

## Company

- [About](https://www.acmecorp.com/about): Company background
- [Pricing](https://www.acmecorp.com/pricing): Plans and limits

## Optional

- [Blog](https://www.acmecorp.com/blog): Product updates
- [Case studies](https://www.acmecorp.com/case-studies)
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
