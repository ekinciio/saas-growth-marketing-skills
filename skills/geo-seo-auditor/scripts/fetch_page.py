"""
fetch_page.py - Fetch and extract SEO-relevant data from a web page.

Retrieves HTML content from a URL and extracts metadata, headings,
structured data, robots.txt rules, and sitemap availability.
"""

import json
import re
import sys
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
USER_AGENT = (
    "Mozilla/5.0 (compatible; GEOSEOAuditor/1.0; "
    "+https://github.com/geo-seo-auditor)"
)


def fetch_html(url: str, timeout: int = DEFAULT_TIMEOUT) -> Tuple[str, int]:
    """Fetch raw HTML content from a URL.

    Args:
        url: The URL to fetch.
        timeout: Request timeout in seconds.

    Returns:
        A tuple of (html_content, status_code).

    Raises:
        requests.RequestException: If the request fails.
    """
    headers = {"User-Agent": USER_AGENT}
    response = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
    response.raise_for_status()
    return response.text, response.status_code


def extract_metadata(soup: BeautifulSoup) -> Dict[str, Optional[str]]:
    """Extract page metadata from parsed HTML.

    Args:
        soup: A BeautifulSoup object of the parsed page.

    Returns:
        Dictionary containing title, meta_description, canonical_url,
        and Open Graph tags.
    """
    metadata: Dict[str, Optional[str]] = {
        "title": None,
        "meta_description": None,
        "canonical_url": None,
        "og_title": None,
        "og_description": None,
        "og_image": None,
        "og_type": None,
        "og_url": None,
        "robots_meta": None,
    }

    # Title
    title_tag = soup.find("title")
    if title_tag and title_tag.string:
        metadata["title"] = title_tag.string.strip()

    # Meta description
    meta_desc = soup.find("meta", attrs={"name": re.compile(r"^description$", re.I)})
    if meta_desc and meta_desc.get("content"):
        metadata["meta_description"] = meta_desc["content"].strip()

    # Canonical URL
    canonical = soup.find("link", attrs={"rel": "canonical"})
    if canonical and canonical.get("href"):
        metadata["canonical_url"] = canonical["href"].strip()

    # Open Graph tags
    og_tags = {
        "og_title": "og:title",
        "og_description": "og:description",
        "og_image": "og:image",
        "og_type": "og:type",
        "og_url": "og:url",
    }
    for key, property_name in og_tags.items():
        tag = soup.find("meta", attrs={"property": property_name})
        if tag and tag.get("content"):
            metadata[key] = tag["content"].strip()

    # Robots meta tag
    robots_meta = soup.find("meta", attrs={"name": re.compile(r"^robots$", re.I)})
    if robots_meta and robots_meta.get("content"):
        metadata["robots_meta"] = robots_meta["content"].strip()

    return metadata


def extract_headings(soup: BeautifulSoup) -> Dict[str, List[str]]:
    """Extract all heading tags (H1-H6) from the page.

    Args:
        soup: A BeautifulSoup object of the parsed page.

    Returns:
        Dictionary with keys 'h1' through 'h6', each containing a list
        of heading text strings.
    """
    headings: Dict[str, List[str]] = {}
    for level in range(1, 7):
        tag_name = f"h{level}"
        found = soup.find_all(tag_name)
        headings[tag_name] = [h.get_text(strip=True) for h in found if h.get_text(strip=True)]
    return headings


def detect_schema_markup(soup: BeautifulSoup) -> List[Dict[str, Any]]:
    """Detect JSON-LD structured data on the page.

    Args:
        soup: A BeautifulSoup object of the parsed page.

    Returns:
        A list of parsed JSON-LD objects found on the page.
    """
    schemas: List[Dict[str, Any]] = []
    script_tags = soup.find_all("script", attrs={"type": "application/ld+json"})
    for script in script_tags:
        if script.string:
            try:
                data = json.loads(script.string)
                if isinstance(data, list):
                    schemas.extend(data)
                else:
                    schemas.append(data)
            except (json.JSONDecodeError, TypeError):
                continue
    return schemas


def fetch_robots_txt(url: str, timeout: int = DEFAULT_TIMEOUT) -> Optional[str]:
    """Fetch the robots.txt file from the site root.

    Args:
        url: Any URL on the target site.
        timeout: Request timeout in seconds.

    Returns:
        The robots.txt content as a string, or None if not found.
    """
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    try:
        headers = {"User-Agent": USER_AGENT}
        response = requests.get(robots_url, headers=headers, timeout=timeout)
        if response.status_code == 200:
            return response.text
        return None
    except requests.RequestException:
        return None


def check_sitemap(url: str, timeout: int = DEFAULT_TIMEOUT) -> Dict[str, Any]:
    """Check for sitemap.xml availability.

    Args:
        url: Any URL on the target site.
        timeout: Request timeout in seconds.

    Returns:
        Dictionary with 'exists' (bool) and 'url' (str) keys.
    """
    parsed = urlparse(url)
    sitemap_url = f"{parsed.scheme}://{parsed.netloc}/sitemap.xml"
    try:
        headers = {"User-Agent": USER_AGENT}
        response = requests.head(sitemap_url, headers=headers, timeout=timeout, allow_redirects=True)
        exists = response.status_code == 200
        return {"exists": exists, "url": sitemap_url}
    except requests.RequestException:
        return {"exists": False, "url": sitemap_url}


def check_llmstxt(url: str, timeout: int = DEFAULT_TIMEOUT) -> Dict[str, Any]:
    """Check for llms.txt file availability.

    Args:
        url: Any URL on the target site.
        timeout: Request timeout in seconds.

    Returns:
        Dictionary with 'exists' (bool), 'url' (str), and 'content' (str or None).
    """
    parsed = urlparse(url)
    llms_url = f"{parsed.scheme}://{parsed.netloc}/llms.txt"
    try:
        headers = {"User-Agent": USER_AGENT}
        response = requests.get(llms_url, headers=headers, timeout=timeout)
        if response.status_code == 200:
            return {"exists": True, "url": llms_url, "content": response.text}
        return {"exists": False, "url": llms_url, "content": None}
    except requests.RequestException:
        return {"exists": False, "url": llms_url, "content": None}


def fetch_page(url: str, timeout: int = DEFAULT_TIMEOUT) -> Dict[str, Any]:
    """Perform a full page fetch and extraction.

    This is the main entry point that combines all extraction functions
    into a single structured result.

    Args:
        url: The URL to audit.
        timeout: Request timeout in seconds.

    Returns:
        A dictionary containing all extracted data:
        - url: The target URL
        - status_code: HTTP response status
        - metadata: Title, description, OG tags, canonical
        - headings: H1-H6 text content
        - schema_markup: JSON-LD structured data
        - robots_txt: Raw robots.txt content (or None)
        - sitemap: Sitemap availability info
        - llmstxt: llms.txt availability and content
        - word_count: Approximate word count of visible text
        - errors: List of any non-fatal errors encountered
    """
    result: Dict[str, Any] = {
        "url": url,
        "status_code": None,
        "metadata": {},
        "headings": {},
        "schema_markup": [],
        "robots_txt": None,
        "sitemap": {"exists": False, "url": ""},
        "llmstxt": {"exists": False, "url": "", "content": None},
        "word_count": 0,
        "errors": [],
    }

    # Fetch main page
    try:
        html, status_code = fetch_html(url, timeout=timeout)
        result["status_code"] = status_code
    except requests.RequestException as e:
        result["errors"].append(f"Failed to fetch page: {str(e)}")
        return result

    # Parse HTML
    try:
        soup = BeautifulSoup(html, "html.parser")
    except Exception as e:
        result["errors"].append(f"Failed to parse HTML: {str(e)}")
        return result

    # Extract data
    try:
        result["metadata"] = extract_metadata(soup)
    except Exception as e:
        result["errors"].append(f"Metadata extraction failed: {str(e)}")

    try:
        result["headings"] = extract_headings(soup)
    except Exception as e:
        result["errors"].append(f"Heading extraction failed: {str(e)}")

    try:
        result["schema_markup"] = detect_schema_markup(soup)
    except Exception as e:
        result["errors"].append(f"Schema detection failed: {str(e)}")

    # Word count from visible text
    try:
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        visible_text = soup.get_text(separator=" ", strip=True)
        result["word_count"] = len(visible_text.split())
    except Exception as e:
        result["errors"].append(f"Word count failed: {str(e)}")

    # Fetch supplementary files
    try:
        result["robots_txt"] = fetch_robots_txt(url, timeout=timeout)
    except Exception as e:
        result["errors"].append(f"robots.txt fetch failed: {str(e)}")

    try:
        result["sitemap"] = check_sitemap(url, timeout=timeout)
    except Exception as e:
        result["errors"].append(f"Sitemap check failed: {str(e)}")

    try:
        result["llmstxt"] = check_llmstxt(url, timeout=timeout)
    except Exception as e:
        result["errors"].append(f"llms.txt check failed: {str(e)}")

    return result


def format_report(data: Dict[str, Any]) -> str:
    """Format the fetched page data into a human-readable report.

    Args:
        data: The result dictionary from fetch_page().

    Returns:
        A formatted string report.
    """
    lines = []
    lines.append(f"Page Fetch Report: {data['url']}")
    lines.append("=" * 60)

    lines.append(f"\nHTTP Status: {data['status_code']}")
    lines.append(f"Word Count: {data['word_count']}")

    # Metadata
    lines.append("\n--- Metadata ---")
    meta = data.get("metadata", {})
    for key, value in meta.items():
        if value:
            lines.append(f"  {key}: {value}")

    # Headings
    lines.append("\n--- Headings ---")
    headings = data.get("headings", {})
    for level, texts in headings.items():
        if texts:
            for text in texts:
                lines.append(f"  <{level}> {text}")

    # Schema markup
    schemas = data.get("schema_markup", [])
    lines.append(f"\n--- Schema Markup ({len(schemas)} found) ---")
    for schema in schemas:
        schema_type = schema.get("@type", "Unknown")
        lines.append(f"  Type: {schema_type}")

    # Robots.txt
    lines.append(f"\n--- robots.txt ---")
    if data.get("robots_txt"):
        lines.append("  Found (content available)")
    else:
        lines.append("  Not found or inaccessible")

    # Sitemap
    sitemap = data.get("sitemap", {})
    lines.append(f"\n--- Sitemap ---")
    lines.append(f"  URL: {sitemap.get('url', 'N/A')}")
    lines.append(f"  Exists: {sitemap.get('exists', False)}")

    # llms.txt
    llmstxt = data.get("llmstxt", {})
    lines.append(f"\n--- llms.txt ---")
    lines.append(f"  URL: {llmstxt.get('url', 'N/A')}")
    lines.append(f"  Exists: {llmstxt.get('exists', False)}")

    # Errors
    errors = data.get("errors", [])
    if errors:
        lines.append(f"\n--- Errors ({len(errors)}) ---")
        for error in errors:
            lines.append(f"  - {error}")

    return "\n".join(lines)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python fetch_page.py <url>")
        print("Example: python fetch_page.py https://example.com")
        sys.exit(1)

    target_url = sys.argv[1]

    # Ensure URL has a scheme
    if not target_url.startswith(("http://", "https://")):
        target_url = f"https://{target_url}"

    print(f"Fetching: {target_url}\n")

    page_data = fetch_page(target_url)
    print(format_report(page_data))

    # Also output raw JSON for programmatic use
    print("\n--- Raw JSON ---")
    # Remove large fields for readable output
    json_output = {k: v for k, v in page_data.items() if k != "robots_txt"}
    json_output["robots_txt"] = (
        "[present]" if page_data.get("robots_txt") else None
    )
    print(json.dumps(json_output, indent=2, default=str))
