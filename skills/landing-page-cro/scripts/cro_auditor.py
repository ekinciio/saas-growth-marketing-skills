"""
CRO Auditor - Landing Page Conversion Rate Optimization Analyzer

Fetches a landing page and auto-scores it across 10 CRO dimensions.
Detects CTAs, forms, social proof elements, trust signals, and heading
structure. Returns a score breakdown and top 5 recommendations.

Usage:
    python cro_auditor.py <url>

Requirements:
    pip install requests beautifulsoup4
"""

import re
import sys
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class DimensionScore:
    """Score for a single CRO dimension."""
    name: str
    score: int  # 0-10
    evidence: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


@dataclass
class CROAuditResult:
    """Complete CRO audit result."""
    url: str
    total_score: int  # 0-100
    dimensions: list[DimensionScore] = field(default_factory=list)
    top_5_recommendations: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Page fetcher
# ---------------------------------------------------------------------------

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}


def fetch_page(url: str, timeout: int = 15) -> Optional[BeautifulSoup]:
    """Fetch a URL and return a BeautifulSoup object, or None on failure."""
    try:
        response = requests.get(url, headers=HEADERS, timeout=timeout)
        response.raise_for_status()
        return BeautifulSoup(response.text, "html.parser")
    except requests.RequestException as exc:
        print(f"Error fetching {url}: {exc}")
        return None


# ---------------------------------------------------------------------------
# Element detection helpers
# ---------------------------------------------------------------------------

CTA_PATTERNS = re.compile(
    r"(sign\s*up|get\s*started|start|try|buy|subscribe|join|register|"
    r"book\s*a?\s*demo|request|download|free\s*trial|create\s*account|"
    r"add\s*to\s*cart|learn\s*more|contact\s*us|schedule)",
    re.IGNORECASE,
)

WEAK_CTA_PATTERNS = re.compile(
    r"^(submit|click\s*here|go|next|continue|send)$",
    re.IGNORECASE,
)

SOCIAL_PROOF_PATTERNS = re.compile(
    r"(testimonial|review|customer|client|trust|rated|rating|"
    r"case\s*study|success\s*stor|loved\s*by|used\s*by|"
    r"companies\s*use|teams\s*use|\d[\d,]*\+?\s*(users|customers|teams|companies))",
    re.IGNORECASE,
)

TRUST_PATTERNS = re.compile(
    r"(secure|ssl|encrypt|gdpr|soc\s*2|iso\s*27001|hipaa|"
    r"money.back|guarantee|refund|privacy|certified|award|badge|"
    r"as\s*seen\s*in|featured\s*in|partner)",
    re.IGNORECASE,
)

URGENCY_PATTERNS = re.compile(
    r"(limited|hurry|act\s*now|last\s*chance|expires?|deadline|"
    r"only\s*\d|spots?\s*left|ends?\s*(soon|today|tomorrow)|"
    r"early.bird|countdown|don.t\s*miss|while\s*supplies)",
    re.IGNORECASE,
)

OBJECTION_PATTERNS = re.compile(
    r"(faq|frequently\s*asked|question|pricing|compare|comparison|"
    r"vs\.?|versus|how\s*it\s*works|guarantee|refund|cancel\s*any\s*time|"
    r"no\s*credit\s*card|risk.free|support|help\s*center)",
    re.IGNORECASE,
)


def count_ctas(soup: BeautifulSoup) -> tuple[int, int, list[str]]:
    """Count CTA buttons/links. Returns (strong_count, weak_count, cta_texts)."""
    strong = 0
    weak = 0
    texts: list[str] = []

    for el in soup.find_all(["a", "button"]):
        text = el.get_text(strip=True)
        if not text:
            continue
        if CTA_PATTERNS.search(text):
            strong += 1
            texts.append(text)
        elif WEAK_CTA_PATTERNS.search(text):
            weak += 1
            texts.append(text)

    return strong, weak, texts


def count_form_fields(soup: BeautifulSoup) -> tuple[int, int]:
    """Count form fields. Returns (total_forms, avg_field_count)."""
    forms = soup.find_all("form")
    if not forms:
        return 0, 0

    total_fields = 0
    for form in forms:
        inputs = form.find_all(["input", "select", "textarea"])
        visible = [
            i for i in inputs
            if i.get("type", "text") not in ("hidden", "submit", "button")
        ]
        total_fields += len(visible)

    avg = total_fields // len(forms) if forms else 0
    return len(forms), avg


def count_social_proof(soup: BeautifulSoup) -> tuple[int, list[str]]:
    """Count social proof elements. Returns (count, evidence_list)."""
    evidence: list[str] = []
    text = soup.get_text(" ", strip=True)

    # Check for testimonial/review sections
    for section in soup.find_all(["section", "div"]):
        section_text = section.get_text(" ", strip=True)[:200]
        if SOCIAL_PROOF_PATTERNS.search(section_text):
            evidence.append(f"Social proof section detected: {section_text[:80]}...")

    # Check for customer logos (images in logo-like containers)
    for img in soup.find_all("img"):
        alt = (img.get("alt", "") or "").lower()
        src = (img.get("src", "") or "").lower()
        parent_class = " ".join((img.parent or Tag(name="div")).get("class", []))
        if any(k in alt + src + parent_class for k in ["logo", "client", "customer", "partner", "trust"]):
            evidence.append(f"Logo/trust image: {alt or src[:60]}")

    # Check for star ratings
    for el in soup.find_all(string=re.compile(r"[45]\.\d\s*/\s*5|[45]\.\d\s*star", re.IGNORECASE)):
        evidence.append(f"Rating detected: {str(el).strip()[:80]}")

    return len(evidence), evidence


def count_trust_signals(soup: BeautifulSoup) -> tuple[int, list[str]]:
    """Count trust signals. Returns (count, evidence_list)."""
    evidence: list[str] = []
    text = soup.get_text(" ", strip=True)

    matches = TRUST_PATTERNS.findall(text)
    for match in matches[:10]:
        evidence.append(f"Trust signal keyword: {match}")

    # Check for trust-related images
    for img in soup.find_all("img"):
        alt = (img.get("alt", "") or "").lower()
        if any(k in alt for k in ["badge", "secure", "certified", "award", "trust", "ssl"]):
            evidence.append(f"Trust badge image: {alt[:60]}")

    return len(evidence), evidence


def check_headings(soup: BeautifulSoup) -> dict[str, int]:
    """Check heading structure. Returns counts per heading level."""
    counts: dict[str, int] = {}
    for level in range(1, 7):
        tag = f"h{level}"
        counts[tag] = len(soup.find_all(tag))
    return counts


def check_meta(soup: BeautifulSoup) -> dict[str, Optional[str]]:
    """Extract key meta information."""
    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else None

    desc_tag = soup.find("meta", attrs={"name": "description"})
    description = desc_tag.get("content") if desc_tag else None

    viewport_tag = soup.find("meta", attrs={"name": "viewport"})
    viewport = viewport_tag.get("content") if viewport_tag else None

    return {
        "title": title,
        "description": description,
        "viewport": viewport,
    }


def get_text_stats(soup: BeautifulSoup) -> dict[str, int]:
    """Get text statistics."""
    text = soup.get_text(" ", strip=True)
    words = text.split()
    paragraphs = soup.find_all("p")
    lists = soup.find_all(["ul", "ol"])
    return {
        "word_count": len(words),
        "paragraph_count": len(paragraphs),
        "list_count": len(lists),
    }


# ---------------------------------------------------------------------------
# Scoring functions (one per dimension)
# ---------------------------------------------------------------------------

def score_above_fold(soup: BeautifulSoup) -> DimensionScore:
    """Score 1: Above-the-fold clarity."""
    dim = DimensionScore(name="Above-the-fold clarity", score=5)

    h1_tags = soup.find_all("h1")
    if h1_tags:
        h1_text = h1_tags[0].get_text(strip=True)
        dim.evidence.append(f"H1 found: '{h1_text[:80]}'")
        if len(h1_text.split()) >= 3:
            dim.score += 2
            dim.evidence.append("H1 has adequate length")
        if len(h1_tags) == 1:
            dim.score += 1
            dim.evidence.append("Single H1 tag (good practice)")
        elif len(h1_tags) > 1:
            dim.recommendations.append("Use only one H1 tag per page for clear hierarchy")
    else:
        dim.score = 2
        dim.recommendations.append("Add a clear H1 headline that communicates your value proposition")

    # Check for subheadline (h2 or p near h1)
    h2_tags = soup.find_all("h2")
    if h2_tags:
        dim.score = min(dim.score + 1, 10)
        dim.evidence.append(f"Subheadline (H2) found: '{h2_tags[0].get_text(strip=True)[:60]}'")

    # Check for hero image
    first_img = soup.find("img")
    if first_img:
        dim.evidence.append("Hero image detected")
        dim.score = min(dim.score + 1, 10)

    if dim.score < 7:
        dim.recommendations.append("Ensure headline + subheadline communicate value prop within 5 seconds")

    return dim


def score_cta(soup: BeautifulSoup) -> DimensionScore:
    """Score 2: CTA visibility and copy strength."""
    dim = DimensionScore(name="CTA visibility and copy strength", score=0)

    strong, weak, texts = count_ctas(soup)
    total = strong + weak

    dim.evidence.append(f"CTAs found: {strong} strong, {weak} weak")
    if texts:
        dim.evidence.append(f"CTA texts: {', '.join(texts[:5])}")

    if strong >= 3:
        dim.score = 8
    elif strong >= 2:
        dim.score = 7
    elif strong >= 1:
        dim.score = 6
    elif weak >= 1:
        dim.score = 3
    else:
        dim.score = 1

    if weak > 0 and strong == 0:
        dim.recommendations.append(
            "Replace generic CTA text ('Submit', 'Click here') with action-oriented copy "
            "like 'Start Free Trial' or 'Get Started'"
        )

    if total == 0:
        dim.score = 0
        dim.recommendations.append("Add a clear, visible CTA button above the fold")

    if strong >= 1 and strong < 3:
        dim.recommendations.append("Repeat primary CTA at multiple points down the page")

    # Bonus for microcopy near CTA
    for el in soup.find_all(["a", "button"]):
        sibling_text = ""
        next_sib = el.find_next_sibling()
        if next_sib:
            sibling_text = next_sib.get_text(strip=True).lower()
        if any(k in sibling_text for k in ["no credit card", "free", "cancel anytime", "no obligation"]):
            dim.score = min(dim.score + 1, 10)
            dim.evidence.append("Anxiety-reducing microcopy found near CTA")
            break

    return dim


def score_social_proof(soup: BeautifulSoup) -> DimensionScore:
    """Score 3: Social proof presence and quality."""
    dim = DimensionScore(name="Social proof presence and quality", score=0)

    count, evidence = count_social_proof(soup)
    dim.evidence = evidence[:5]

    if count >= 5:
        dim.score = 9
    elif count >= 3:
        dim.score = 7
    elif count >= 2:
        dim.score = 5
    elif count >= 1:
        dim.score = 3
    else:
        dim.score = 1
        dim.recommendations.append("Add social proof: customer logos, testimonials, or usage statistics")

    if count > 0 and count < 3:
        dim.recommendations.append(
            "Strengthen social proof with named testimonials, specific results, and recognizable logos"
        )

    return dim


def score_trust_signals(soup: BeautifulSoup) -> DimensionScore:
    """Score 4: Trust signals."""
    dim = DimensionScore(name="Trust signals", score=0)

    count, evidence = count_trust_signals(soup)
    dim.evidence = evidence[:5]

    if count >= 5:
        dim.score = 9
    elif count >= 3:
        dim.score = 7
    elif count >= 2:
        dim.score = 5
    elif count >= 1:
        dim.score = 3
    else:
        dim.score = 1
        dim.recommendations.append(
            "Add trust signals: security badges, certifications, money-back guarantee, or partner logos"
        )

    # Check for privacy/terms links
    for a in soup.find_all("a"):
        href = (a.get("href", "") or "").lower()
        text = a.get_text(strip=True).lower()
        if "privacy" in text or "privacy" in href:
            dim.score = min(dim.score + 1, 10)
            dim.evidence.append("Privacy policy link found")
            break

    return dim


def score_form_simplicity(soup: BeautifulSoup) -> DimensionScore:
    """Score 5: Form simplicity."""
    dim = DimensionScore(name="Form simplicity", score=5)

    form_count, avg_fields = count_form_fields(soup)

    if form_count == 0:
        dim.score = 7
        dim.evidence.append("No forms detected (may use external form or CTA link)")
        return dim

    dim.evidence.append(f"Forms found: {form_count}, avg fields: {avg_fields}")

    if avg_fields <= 3:
        dim.score = 9
        dim.evidence.append("Low friction - 3 or fewer fields")
    elif avg_fields <= 5:
        dim.score = 7
        dim.evidence.append("Moderate field count (4-5)")
    elif avg_fields <= 8:
        dim.score = 4
        dim.recommendations.append("Reduce form fields to the minimum required - each field increases drop-off")
    else:
        dim.score = 2
        dim.recommendations.append(
            "Form has too many fields. Consider multi-step approach or removing non-essential fields"
        )

    return dim


def score_page_speed_mobile(soup: BeautifulSoup) -> DimensionScore:
    """Score 6: Page speed and mobile responsiveness (estimated from HTML signals)."""
    dim = DimensionScore(name="Page speed and mobile responsiveness", score=5)

    meta = check_meta(soup)

    # Viewport meta check
    if meta.get("viewport"):
        dim.score += 2
        dim.evidence.append("Viewport meta tag present (mobile-friendly signal)")
    else:
        dim.score -= 2
        dim.recommendations.append("Add a viewport meta tag for mobile responsiveness")

    # Check for lazy loading
    lazy_imgs = soup.find_all("img", attrs={"loading": "lazy"})
    if lazy_imgs:
        dim.score = min(dim.score + 1, 10)
        dim.evidence.append(f"Lazy loading detected on {len(lazy_imgs)} images")

    # Check image count (too many unoptimized images slow pages)
    all_imgs = soup.find_all("img")
    if len(all_imgs) > 20:
        dim.recommendations.append(f"Page has {len(all_imgs)} images - ensure they are optimized and lazy-loaded")

    # Check for render-blocking signals
    scripts = soup.find_all("script", src=True)
    if len(scripts) > 15:
        dim.score = max(dim.score - 1, 0)
        dim.recommendations.append(f"Page loads {len(scripts)} external scripts - consider deferring non-critical ones")

    dim.evidence.append(f"Images: {len(all_imgs)}, External scripts: {len(scripts)}")

    return dim


def score_visual_hierarchy(soup: BeautifulSoup) -> DimensionScore:
    """Score 7: Visual hierarchy and scan-ability."""
    dim = DimensionScore(name="Visual hierarchy and scan-ability", score=5)

    headings = check_headings(soup)
    stats = get_text_stats(soup)

    dim.evidence.append(f"Headings: {headings}")
    dim.evidence.append(f"Paragraphs: {stats['paragraph_count']}, Lists: {stats['list_count']}")

    # H1 present
    if headings.get("h1", 0) == 1:
        dim.score += 1

    # Good heading depth (H2 and H3 used)
    if headings.get("h2", 0) >= 2:
        dim.score += 1
    if headings.get("h3", 0) >= 1:
        dim.score += 1

    # Lists improve scan-ability
    if stats["list_count"] >= 2:
        dim.score = min(dim.score + 1, 10)
        dim.evidence.append("Multiple lists found (good for scan-ability)")

    # Too few headings for amount of content
    if stats["word_count"] > 500 and headings.get("h2", 0) < 2:
        dim.recommendations.append("Add more H2 headings to break up content into scannable sections")

    if stats["list_count"] == 0 and stats["word_count"] > 300:
        dim.recommendations.append("Add bullet points or numbered lists to improve scan-ability")

    return dim


def score_objection_handling(soup: BeautifulSoup) -> DimensionScore:
    """Score 8: Objection handling."""
    dim = DimensionScore(name="Objection handling", score=0)

    text = soup.get_text(" ", strip=True).lower()
    matches = OBJECTION_PATTERNS.findall(text)

    unique_matches = list(set(m.lower() for m in matches))
    dim.evidence.append(f"Objection-handling signals: {', '.join(unique_matches[:8])}")

    if len(unique_matches) >= 5:
        dim.score = 9
    elif len(unique_matches) >= 3:
        dim.score = 7
    elif len(unique_matches) >= 2:
        dim.score = 5
    elif len(unique_matches) >= 1:
        dim.score = 3
    else:
        dim.score = 1

    if "faq" not in text:
        dim.recommendations.append("Add an FAQ section to proactively address common buyer questions")
    if "pricing" not in text and "price" not in text:
        dim.recommendations.append("Include pricing information or a clear link to pricing page")

    return dim


def score_urgency(soup: BeautifulSoup) -> DimensionScore:
    """Score 9: Urgency and scarcity."""
    dim = DimensionScore(name="Urgency and scarcity", score=5)

    text = soup.get_text(" ", strip=True)
    matches = URGENCY_PATTERNS.findall(text)

    if matches:
        dim.evidence.append(f"Urgency signals found: {', '.join(matches[:5])}")
        dim.score = min(5 + len(set(matches)), 10)
    else:
        dim.evidence.append("No urgency elements detected (not always negative)")
        dim.score = 5  # Neutral - urgency is optional

    return dim


def score_copy_clarity(soup: BeautifulSoup) -> DimensionScore:
    """Score 10: Copy clarity and benefit-driven language."""
    dim = DimensionScore(name="Copy clarity and benefit-driven language", score=5)

    stats = get_text_stats(soup)
    text = soup.get_text(" ", strip=True).lower()

    # Check for benefit-oriented language
    benefit_words = ["save", "grow", "increase", "reduce", "faster", "easier",
                     "automate", "simplify", "boost", "improve", "achieve",
                     "result", "outcome", "success", "revenue", "profit"]
    feature_words = ["feature", "specification", "technical", "architecture",
                     "module", "component", "algorithm", "infrastructure"]

    benefit_count = sum(1 for w in benefit_words if w in text)
    feature_count = sum(1 for w in feature_words if w in text)

    dim.evidence.append(f"Benefit keywords: {benefit_count}, Feature keywords: {feature_count}")

    if benefit_count > feature_count and benefit_count >= 3:
        dim.score = 8
        dim.evidence.append("Copy appears benefit-driven")
    elif benefit_count >= feature_count:
        dim.score = 6
    else:
        dim.score = 4
        dim.recommendations.append(
            "Rewrite copy to lead with customer benefits instead of product features"
        )

    # Check for "you/your" vs "we/our"
    you_count = text.count(" you ") + text.count(" your ")
    we_count = text.count(" we ") + text.count(" our ")

    if you_count > we_count:
        dim.score = min(dim.score + 1, 10)
        dim.evidence.append("Copy is customer-focused (more 'you' than 'we')")
    elif we_count > you_count * 2:
        dim.recommendations.append("Shift copy focus from 'we/our' to 'you/your' for customer-centric messaging")

    return dim


# ---------------------------------------------------------------------------
# Main audit function
# ---------------------------------------------------------------------------

def audit_page(url: str) -> Optional[CROAuditResult]:
    """
    Run a full CRO audit on the given URL.

    Args:
        url: The landing page URL to audit.

    Returns:
        CROAuditResult with scores and recommendations, or None if fetch fails.
    """
    soup = fetch_page(url)
    if soup is None:
        return None

    # Score all 10 dimensions
    dimensions = [
        score_above_fold(soup),
        score_cta(soup),
        score_social_proof(soup),
        score_trust_signals(soup),
        score_form_simplicity(soup),
        score_page_speed_mobile(soup),
        score_visual_hierarchy(soup),
        score_objection_handling(soup),
        score_urgency(soup),
        score_copy_clarity(soup),
    ]

    total_score = sum(d.score for d in dimensions)

    # Collect all recommendations, prioritize by lowest-scoring dimensions
    all_recs: list[tuple[int, str]] = []
    for dim in dimensions:
        for rec in dim.recommendations:
            all_recs.append((dim.score, rec))

    # Sort by score ascending (lowest score = highest priority)
    all_recs.sort(key=lambda x: x[0])
    top_5 = [rec for _, rec in all_recs[:5]]

    return CROAuditResult(
        url=url,
        total_score=total_score,
        dimensions=dimensions,
        top_5_recommendations=top_5,
    )


def print_report(result: CROAuditResult) -> None:
    """Print a formatted CRO audit report."""
    print("=" * 70)
    print(f"  CRO AUDIT REPORT")
    print(f"  URL: {result.url}")
    print("=" * 70)
    print()

    # Score label
    if result.total_score >= 90:
        label = "Excellent"
    elif result.total_score >= 70:
        label = "Good"
    elif result.total_score >= 50:
        label = "Fair"
    elif result.total_score >= 30:
        label = "Poor"
    else:
        label = "Critical"

    print(f"  OVERALL CRO SCORE: {result.total_score}/100 ({label})")
    print()

    # Dimension breakdown
    print("-" * 70)
    print(f"  {'Dimension':<45} {'Score':>5}")
    print("-" * 70)

    for dim in result.dimensions:
        indicator = "RED" if dim.score <= 3 else ("YEL" if dim.score <= 6 else "GRN")
        print(f"  [{indicator}] {dim.name:<41} {dim.score:>3}/10")

    print("-" * 70)
    print()

    # Top 5 recommendations
    if result.top_5_recommendations:
        print("  TOP 5 RECOMMENDATIONS (by priority):")
        print()
        for i, rec in enumerate(result.top_5_recommendations, 1):
            print(f"  {i}. {rec}")
        print()

    # Detailed evidence
    print("  DETAILED EVIDENCE:")
    print()
    for dim in result.dimensions:
        print(f"  [{dim.score}/10] {dim.name}")
        for ev in dim.evidence[:3]:
            print(f"    - {ev}")
        print()


# ---------------------------------------------------------------------------
# Standalone demo
# ---------------------------------------------------------------------------

def main() -> None:
    """Run the CRO auditor from the command line."""
    if len(sys.argv) < 2:
        # Demo mode with example
        print("Usage: python cro_auditor.py <url>")
        print()
        print("Running demo audit on https://example.com ...")
        print()
        url = "https://example.com"
    else:
        url = sys.argv[1]

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    result = audit_page(url)
    if result is None:
        print(f"Failed to audit {url}. Check the URL and try again.")
        sys.exit(1)

    print_report(result)


if __name__ == "__main__":
    main()
