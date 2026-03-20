"""
citability_scorer.py - Score web page content for AI citation readiness.

Extracts content blocks from HTML and evaluates each block on four
dimensions: structure clarity, factual density, self-containment,
and question-answer format. Produces per-block and overall page scores.
"""

import re
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

try:
    from bs4 import BeautifulSoup, Tag
except ImportError:
    print(
        "Required packages not installed. Run: pip install beautifulsoup4",
        file=sys.stderr,
    )
    sys.exit(1)


# Optimal passage length range for AI citations (words)
OPTIMAL_MIN_WORDS = 134
OPTIMAL_MAX_WORDS = 167

# Minimum word count to consider a block scorable
MIN_BLOCK_WORDS = 30

# Patterns that indicate factual density
FACTUAL_PATTERNS = [
    r"\d+%",                          # Percentages
    r"\$[\d,]+",                      # Dollar amounts
    r"\d{4}",                         # Years
    r"\d+\.\d+",                      # Decimal numbers
    r"\d+[,]\d{3}",                   # Large numbers with commas
    r"\b\d+x\b",                      # Multipliers (e.g., 3x)
    r"\b(?:million|billion|trillion)\b",  # Large quantity words
    r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\b",
    r"\b(?:Q[1-4])\b",               # Quarter references
    r"\b(?:according to|study|research|survey|report)\b",  # Source references
]

# Patterns indicating vague or weak language
VAGUE_PATTERNS = [
    r"\b(?:many|some|various|several|numerous|a lot of|lots of)\b",
    r"\b(?:basically|essentially|generally|typically|usually)\b",
    r"\b(?:we believe|we think|in our opinion|it seems)\b",
    r"\b(?:cutting-edge|world-class|best-in-class|next-generation)\b",
    r"\b(?:synergy|leverage|paradigm|holistic|robust)\b",
]

# Patterns indicating self-containment issues
CONTEXT_DEPENDENT_PATTERNS = [
    r"^(?:This|That|These|Those|It|They)\s",  # Pronoun-heavy openings
    r"\b(?:as mentioned|see above|see below|as noted)\b",
    r"\b(?:the above|the below|the following|the previous)\b",
    r"\b(?:Section \d|Chapter \d|Figure \d|Table \d)\b",
]

# Patterns indicating Q&A format
QA_PATTERNS = [
    r"^(?:What|How|Why|When|Where|Who|Which)\s",  # Question starters
    r"\bis\s+(?:a|an|the)\s",                      # Definition pattern
    r"^(?:The best way|The most|To\s\w+,\syou)",   # Direct answer starters
    r"\b(?:steps?|ways?|methods?|tips?|reasons?)\s+(?:to|for|why)\b",
    r":\s*$",                                        # Ends with colon (list intro)
]


@dataclass
class BlockScore:
    """Score for a single content block."""

    text: str
    word_count: int
    structure_score: float = 0.0
    factual_score: float = 0.0
    self_containment_score: float = 0.0
    qa_score: float = 0.0
    total_score: float = 0.0
    recommendations: List[str] = field(default_factory=list)

    @property
    def excerpt(self) -> str:
        """Return a truncated excerpt of the block text."""
        if len(self.text) <= 150:
            return self.text
        return self.text[:147] + "..."


def extract_content_blocks(html: str) -> List[str]:
    """Extract meaningful content blocks from HTML.

    Extracts paragraphs, list items (grouped by parent list), and
    definition terms. Filters out blocks that are too short to be
    meaningful for citation purposes.

    Args:
        html: Raw HTML string.

    Returns:
        A list of text content blocks.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Remove non-content elements
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
        tag.decompose()

    blocks: List[str] = []

    # Extract paragraphs
    for p in soup.find_all("p"):
        text = p.get_text(strip=True)
        if text and len(text.split()) >= MIN_BLOCK_WORDS:
            blocks.append(text)

    # Extract list groups (combine list items under one parent)
    for ul in soup.find_all(["ul", "ol"]):
        items = ul.find_all("li", recursive=False)
        combined = " ".join(li.get_text(strip=True) for li in items if li.get_text(strip=True))
        if combined and len(combined.split()) >= MIN_BLOCK_WORDS:
            blocks.append(combined)

    # Extract blockquotes
    for bq in soup.find_all("blockquote"):
        text = bq.get_text(strip=True)
        if text and len(text.split()) >= MIN_BLOCK_WORDS:
            blocks.append(text)

    # Deduplicate while preserving order
    seen = set()
    unique_blocks: List[str] = []
    for block in blocks:
        normalized = block.strip().lower()
        if normalized not in seen:
            seen.add(normalized)
            unique_blocks.append(block)

    return unique_blocks


def score_structure(text: str, word_count: int) -> Tuple[float, List[str]]:
    """Score a block for structural clarity (0-25).

    Args:
        text: The content block text.
        word_count: Number of words in the block.

    Returns:
        A tuple of (score, list of recommendations).
    """
    score = 0.0
    recommendations: List[str] = []

    # Optimal length bonus
    if OPTIMAL_MIN_WORDS <= word_count <= OPTIMAL_MAX_WORDS:
        score += 8.0
    elif word_count < OPTIMAL_MIN_WORDS:
        score += 4.0
        recommendations.append(
            f"Block has {word_count} words. Aim for {OPTIMAL_MIN_WORDS}-{OPTIMAL_MAX_WORDS} words."
        )
    else:
        score += 3.0
        recommendations.append(
            f"Block has {word_count} words. Consider splitting into shorter passages "
            f"({OPTIMAL_MIN_WORDS}-{OPTIMAL_MAX_WORDS} words each)."
        )

    # Sentence structure
    sentences = re.split(r"[.!?]+", text)
    sentences = [s.strip() for s in sentences if s.strip()]
    sentence_count = len(sentences)

    if 3 <= sentence_count <= 7:
        score += 6.0
    elif sentence_count > 0:
        score += 3.0

    # Contains list-like patterns (semicolons, numbered items, dashes)
    if re.search(r"(?:\d+[.)]\s|[-*]\s|;\s)", text):
        score += 5.0
    else:
        recommendations.append("Consider using lists or numbered steps for multi-point information.")

    # Contains a clear topic sentence (first sentence is declarative and informative)
    if sentences and len(sentences[0].split()) >= 5:
        score += 3.0

    # Contains emphasis markers or key terms
    if re.search(r"\b[A-Z][A-Z]+\b", text) or ":" in text:
        score += 3.0

    return min(score, 25.0), recommendations


def score_factual_density(text: str) -> Tuple[float, List[str]]:
    """Score a block for factual density (0-25).

    Args:
        text: The content block text.

    Returns:
        A tuple of (score, list of recommendations).
    """
    score = 0.0
    recommendations: List[str] = []

    # Count factual patterns
    factual_matches = 0
    for pattern in FACTUAL_PATTERNS:
        matches = re.findall(pattern, text, re.IGNORECASE)
        factual_matches += len(matches)

    if factual_matches >= 4:
        score += 15.0
    elif factual_matches >= 2:
        score += 10.0
    elif factual_matches >= 1:
        score += 5.0
    else:
        recommendations.append(
            "Add specific data points: statistics, dates, percentages, or named entities."
        )

    # Penalize vague language
    vague_matches = 0
    for pattern in VAGUE_PATTERNS:
        matches = re.findall(pattern, text, re.IGNORECASE)
        vague_matches += len(matches)

    if vague_matches == 0:
        score += 5.0
    elif vague_matches <= 2:
        score += 2.0
    else:
        recommendations.append(
            "Replace vague language (many, some, various) with specific numbers or examples."
        )

    # Named entities (capitalized multi-word phrases)
    named_entities = re.findall(r"\b[A-Z][a-z]+(?:\s[A-Z][a-z]+)+\b", text)
    if len(named_entities) >= 2:
        score += 5.0
    elif len(named_entities) >= 1:
        score += 2.0

    return min(score, 25.0), recommendations


def score_self_containment(text: str) -> Tuple[float, List[str]]:
    """Score a block for self-containment (0-25).

    Args:
        text: The content block text.

    Returns:
        A tuple of (score, list of recommendations).
    """
    score = 15.0  # Start with a baseline - most well-written paragraphs are somewhat self-contained
    recommendations: List[str] = []

    # Check for context-dependent patterns
    context_issues = 0
    for pattern in CONTEXT_DEPENDENT_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            context_issues += 1

    if context_issues == 0:
        score += 10.0
    elif context_issues == 1:
        score += 5.0
        recommendations.append(
            "Reduce reliance on context. Replace pronouns like 'this' or 'it' with explicit subjects."
        )
    else:
        score -= 5.0
        recommendations.append(
            "Block is heavily context-dependent. Rewrite to be self-contained - "
            "define subjects explicitly and avoid references to other sections."
        )

    # Check if the block defines its subject early
    first_sentence = text.split(".")[0] if "." in text else text
    first_words = first_sentence.split()[:3]
    pronoun_starts = {"this", "that", "these", "those", "it", "they", "he", "she"}
    if first_words and first_words[0].lower() not in pronoun_starts:
        score += 0.0  # No penalty
    else:
        score -= 3.0

    return max(min(score, 25.0), 0.0), recommendations


def score_qa_format(text: str) -> Tuple[float, List[str]]:
    """Score a block for question-answer format (0-25).

    Args:
        text: The content block text.

    Returns:
        A tuple of (score, list of recommendations).
    """
    score = 0.0
    recommendations: List[str] = []

    # Check for Q&A patterns
    qa_matches = 0
    for pattern in QA_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE | re.MULTILINE):
            qa_matches += 1

    if qa_matches >= 3:
        score += 15.0
    elif qa_matches >= 2:
        score += 10.0
    elif qa_matches >= 1:
        score += 6.0

    # Check if the block starts with a direct answer
    first_sentence = text.split(".")[0].strip() if "." in text else text.strip()
    direct_answer_starters = [
        r"^[A-Z][\w\s]+ is ",
        r"^The (?:best|most|primary|main|key) ",
        r"^To \w+",
        r"^There are \d+",
        r"^You (?:can|should|need to)",
    ]
    for pattern in direct_answer_starters:
        if re.match(pattern, first_sentence):
            score += 5.0
            break

    # Check for instructional or comparative content
    if re.search(r"\b(?:step \d|first|second|third|finally|next)\b", text, re.IGNORECASE):
        score += 5.0
    elif re.search(r"\b(?:compared to|versus|vs\.|better than|faster than)\b", text, re.IGNORECASE):
        score += 5.0

    if score < 10.0:
        recommendations.append(
            "Restructure content to directly answer a question someone might ask an AI assistant."
        )

    return min(score, 25.0), recommendations


def score_block(text: str) -> BlockScore:
    """Calculate the full citability score for a content block.

    Args:
        text: The content block text.

    Returns:
        A BlockScore object with dimension scores and recommendations.
    """
    word_count = len(text.split())
    all_recommendations: List[str] = []

    structure, rec = score_structure(text, word_count)
    all_recommendations.extend(rec)

    factual, rec = score_factual_density(text)
    all_recommendations.extend(rec)

    containment, rec = score_self_containment(text)
    all_recommendations.extend(rec)

    qa, rec = score_qa_format(text)
    all_recommendations.extend(rec)

    total = structure + factual + containment + qa

    return BlockScore(
        text=text,
        word_count=word_count,
        structure_score=round(structure, 1),
        factual_score=round(factual, 1),
        self_containment_score=round(containment, 1),
        qa_score=round(qa, 1),
        total_score=round(total, 1),
        recommendations=all_recommendations,
    )


def score_page(html: str) -> Dict[str, Any]:
    """Score an entire page for AI citability.

    Extracts content blocks, scores each one, and computes an
    overall page citability score.

    Args:
        html: Raw HTML string of the page.

    Returns:
        Dictionary containing:
        - overall_score: Average score across all blocks (0-100)
        - block_count: Number of scored blocks
        - block_scores: List of per-block score details
        - top_recommendations: Deduplicated, prioritized list of suggestions
        - top_blocks: The highest-scoring blocks
        - bottom_blocks: The lowest-scoring blocks
    """
    blocks = extract_content_blocks(html)

    if not blocks:
        return {
            "overall_score": 0.0,
            "block_count": 0,
            "block_scores": [],
            "top_recommendations": [
                "No scorable content blocks found. The page may rely on "
                "client-side rendering, or content blocks are too short to evaluate."
            ],
            "top_blocks": [],
            "bottom_blocks": [],
        }

    scored_blocks = [score_block(block) for block in blocks]

    # Calculate overall score
    overall = sum(b.total_score for b in scored_blocks) / len(scored_blocks)

    # Sort by score
    sorted_blocks = sorted(scored_blocks, key=lambda b: b.total_score, reverse=True)

    # Collect unique recommendations, prioritized by frequency
    rec_counts: Dict[str, int] = {}
    for block in scored_blocks:
        for rec in block.recommendations:
            rec_counts[rec] = rec_counts.get(rec, 0) + 1
    top_recommendations = sorted(rec_counts.keys(), key=lambda r: rec_counts[r], reverse=True)

    # Format block scores for output
    block_details = []
    for b in sorted_blocks:
        block_details.append({
            "excerpt": b.excerpt,
            "word_count": b.word_count,
            "total_score": b.total_score,
            "structure": b.structure_score,
            "factual_density": b.factual_score,
            "self_containment": b.self_containment_score,
            "qa_format": b.qa_score,
            "recommendations": b.recommendations,
        })

    top_blocks = block_details[:5]
    bottom_blocks = block_details[-5:] if len(block_details) > 5 else []

    return {
        "overall_score": round(overall, 1),
        "block_count": len(scored_blocks),
        "block_scores": block_details,
        "top_recommendations": top_recommendations[:10],
        "top_blocks": top_blocks,
        "bottom_blocks": bottom_blocks,
    }


def format_report(results: Dict[str, Any]) -> str:
    """Format citability results into a human-readable report.

    Args:
        results: The result dictionary from score_page().

    Returns:
        A formatted string report.
    """
    lines = []
    lines.append("AI Citability Score Report")
    lines.append("=" * 50)

    overall = results["overall_score"]
    block_count = results["block_count"]

    # Rating label
    if overall >= 90:
        rating = "Excellent"
    elif overall >= 70:
        rating = "Good"
    elif overall >= 50:
        rating = "Fair"
    elif overall >= 30:
        rating = "Poor"
    else:
        rating = "Critical"

    lines.append(f"\nOverall Citability Score: {overall}/100 ({rating})")
    lines.append(f"Content Blocks Analyzed: {block_count}")

    # Top blocks
    top_blocks = results.get("top_blocks", [])
    if top_blocks:
        lines.append("\n--- Top Citable Passages ---")
        for i, block in enumerate(top_blocks, 1):
            lines.append(f"\n  #{i} (Score: {block['total_score']}/100)")
            lines.append(f"  Words: {block['word_count']}")
            lines.append(f"  Structure: {block['structure']}/25 | "
                         f"Factual: {block['factual_density']}/25 | "
                         f"Self-contained: {block['self_containment']}/25 | "
                         f"Q&A: {block['qa_format']}/25")
            lines.append(f"  Excerpt: {block['excerpt']}")

    # Bottom blocks
    bottom_blocks = results.get("bottom_blocks", [])
    if bottom_blocks:
        lines.append("\n--- Lowest-Scoring Passages ---")
        for i, block in enumerate(bottom_blocks, 1):
            lines.append(f"\n  #{i} (Score: {block['total_score']}/100)")
            lines.append(f"  Excerpt: {block['excerpt']}")
            if block["recommendations"]:
                lines.append(f"  Fix: {block['recommendations'][0]}")

    # Top recommendations
    top_recs = results.get("top_recommendations", [])
    if top_recs:
        lines.append("\n--- Top Recommendations ---")
        for i, rec in enumerate(top_recs, 1):
            lines.append(f"  {i}. {rec}")

    return "\n".join(lines)


if __name__ == "__main__":
    import json

    # Demo mode: accept HTML from file, URL, or use sample
    if len(sys.argv) >= 2:
        source = sys.argv[1]

        if source.startswith(("http://", "https://")):
            # Fetch from URL
            try:
                import requests
                print(f"Fetching: {source}\n")
                response = requests.get(
                    source,
                    headers={"User-Agent": "GEOSEOAuditor/1.0"},
                    timeout=15,
                )
                html_content = response.text
            except ImportError:
                print("Install requests to fetch URLs: pip install requests", file=sys.stderr)
                sys.exit(1)
            except Exception as e:
                print(f"Failed to fetch URL: {e}", file=sys.stderr)
                sys.exit(1)
        else:
            # Read from file
            try:
                with open(source, "r", encoding="utf-8") as f:
                    html_content = f.read()
            except FileNotFoundError:
                print(f"File not found: {source}", file=sys.stderr)
                sys.exit(1)
    else:
        # Sample HTML for demonstration
        html_content = """
        <html>
        <body>
            <h1>Understanding API Rate Limiting</h1>
            <p>API rate limiting is a technique used to control the number of requests
            a client can make to an API within a specified time window. Most production
            APIs implement rate limiting to prevent abuse, ensure fair usage, and maintain
            service reliability. Common implementations use token bucket or sliding window
            algorithms. For example, the GitHub API allows 5,000 requests per hour for
            authenticated users and 60 requests per hour for unauthenticated requests.
            Rate limits are typically communicated through HTTP response headers including
            X-RateLimit-Limit, X-RateLimit-Remaining, and X-RateLimit-Reset.</p>

            <p>When building applications that consume APIs, developers should implement
            exponential backoff strategies to handle rate limit responses gracefully.
            A typical approach starts with a 1-second delay after receiving a 429 status
            code, then doubles the wait time with each subsequent retry up to a maximum
            of 32 seconds. According to a 2023 survey by Postman, 73% of API providers
            enforce rate limits, and 45% of API integration failures are caused by
            improper rate limit handling.</p>

            <p>This is really important for many reasons and various stakeholders
            generally agree that it helps a lot with things.</p>
        </body>
        </html>
        """
        print("Running with sample HTML content...\n")

    results = score_page(html_content)
    print(format_report(results))

    print("\n--- Raw JSON ---")
    print(json.dumps(results, indent=2, default=str))
