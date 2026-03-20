#!/usr/bin/env python3
"""Review Sentiment Analyzer - Keyword-based sentiment and theme extraction.

Analyzes customer reviews for sentiment (positive, negative, neutral),
detects themes (UX/UI, Performance, Pricing, Support, Features, Bugs,
Onboarding), and produces aggregate statistics with keyword frequency.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any


# ---------------------------------------------------------------------------
# Lexicons
# ---------------------------------------------------------------------------

POSITIVE_WORDS: set[str] = {
    "love", "great", "excellent", "amazing", "fantastic", "perfect", "awesome",
    "wonderful", "brilliant", "outstanding", "impressive", "smooth", "intuitive",
    "easy", "fast", "reliable", "helpful", "beautiful", "clean", "powerful",
    "recommend", "best", "solid", "superb", "delightful", "pleasant", "enjoy",
    "happy", "satisfied", "convenient", "efficient", "elegant", "polished",
    "seamless", "responsive", "quick", "simple", "friendly", "clear",
}

NEGATIVE_WORDS: set[str] = {
    "terrible", "awful", "horrible", "worst", "broken", "slow", "frustrating",
    "annoying", "useless", "buggy", "confusing", "complicated", "expensive",
    "overpriced", "unreliable", "disappointed", "unresponsive", "clunky",
    "laggy", "outdated", "crash", "crashes", "error", "bug", "glitch",
    "fail", "failure", "ugly", "nightmare", "waste", "regret", "hate",
    "poor", "lacking", "bad", "worse", "painful", "unusable", "garbage",
    "mediocre", "rude", "unhelpful", "unacceptable",
}

NEGATION_WORDS: set[str] = {
    "not", "no", "never", "don't", "doesn't", "won't", "can't", "couldn't",
    "shouldn't", "hardly", "barely", "isn't", "aren't", "wasn't", "weren't",
    "neither", "nor", "without",
}

AMPLIFIERS: set[str] = {
    "very", "extremely", "incredibly", "absolutely", "totally", "completely",
    "so", "really", "truly", "remarkably", "highly", "super",
}

DOWNTONERS: set[str] = {
    "slightly", "somewhat", "a bit", "a little", "kind of", "sort of",
    "fairly", "rather", "quite", "mostly",
}

# ---------------------------------------------------------------------------
# Theme keyword mappings
# ---------------------------------------------------------------------------

THEME_KEYWORDS: dict[str, set[str]] = {
    "UX/UI": {
        "design", "ui", "ux", "interface", "layout", "navigation", "menu",
        "button", "screen", "dashboard", "visual", "clean", "modern",
        "intuitive", "confusing", "cluttered", "ugly", "beautiful", "sleek",
        "user-friendly", "dark mode", "theme", "color", "redesign",
    },
    "Performance": {
        "fast", "slow", "speed", "loading", "crash", "freeze", "lag",
        "performance", "responsive", "quick", "instant", "hang", "timeout",
        "down", "outage", "uptime", "reliable", "unreliable", "stable",
        "unstable", "memory", "battery", "latency",
    },
    "Pricing": {
        "price", "pricing", "cost", "expensive", "cheap", "affordable",
        "value", "money", "subscription", "plan", "tier", "billing",
        "invoice", "refund", "trial", "free", "premium", "upgrade",
        "downgrade", "worth", "overpriced", "budget", "roi",
    },
    "Support": {
        "support", "help", "customer service", "response", "reply", "ticket",
        "chat", "agent", "representative", "resolve", "solution", "helpful",
        "unhelpful", "rude", "friendly", "knowledgeable", "documentation",
        "faq",
    },
    "Features": {
        "feature", "functionality", "capability", "tool", "integration",
        "api", "export", "import", "automation", "workflow", "customization",
        "template", "report", "analytics", "notification", "search",
        "filter", "missing", "wish", "request",
    },
    "Bugs": {
        "bug", "error", "glitch", "broken", "fix", "issue", "problem",
        "fail", "failure", "crash", "unexpected", "wrong", "incorrect",
        "stuck", "loop", "blank", "lost data", "corrupt", "regression",
    },
    "Onboarding": {
        "onboarding", "setup", "getting started", "tutorial", "guide",
        "documentation", "docs", "walkthrough", "learning curve",
        "configuration", "install", "registration", "sign up", "welcome",
        "intro", "training", "first time",
    },
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_WORD_RE = re.compile(r"[a-z]+(?:[-'][a-z]+)*")


def _tokenize(text: str) -> list[str]:
    """Lowercase and split text into word tokens."""
    return _WORD_RE.findall(text.lower())


def _has_phrase(text_lower: str, phrase: str) -> bool:
    """Check if a multi-word phrase appears in the lowered text."""
    return phrase in text_lower


# ---------------------------------------------------------------------------
# Core analysis
# ---------------------------------------------------------------------------

def analyze_sentiment(text: str) -> dict[str, Any]:
    """Classify a single review's sentiment.

    Args:
        text: The review text to analyze.

    Returns:
        Dictionary with keys:
            sentiment - "positive", "negative", or "neutral"
            confidence - float between 0.0 and 1.0
            positive_count - number of positive signals
            negative_count - number of negative signals
    """
    tokens = _tokenize(text)
    text_lower = text.lower()

    pos_count = 0
    neg_count = 0
    intensity = 1.0

    # Check for amplifiers / downtoners (global influence)
    for token in tokens:
        if token in AMPLIFIERS:
            intensity = min(intensity + 0.05, 1.3)
        elif token in DOWNTONERS:
            intensity = max(intensity - 0.05, 0.7)

    # Sliding window for negation handling
    negation_active = False
    for i, token in enumerate(tokens):
        if token in NEGATION_WORDS:
            negation_active = True
            continue

        is_positive = token in POSITIVE_WORDS
        is_negative = token in NEGATIVE_WORDS

        if negation_active:
            # Flip sentiment
            if is_positive:
                neg_count += 1
            elif is_negative:
                pos_count += 0.5  # Negated negative is mildly positive
            negation_active = False
        else:
            if is_positive:
                pos_count += 1
            elif is_negative:
                neg_count += 1

        # Negation expires after one relevant word
        if is_positive or is_negative:
            negation_active = False

    # Calculate raw score (-1 to +1 range)
    total = pos_count + neg_count
    if total == 0:
        return {
            "sentiment": "neutral",
            "confidence": 0.3,
            "positive_count": 0,
            "negative_count": 0,
        }

    raw_score = (pos_count - neg_count) / total  # -1 to +1

    # Determine sentiment label
    if raw_score > 0.15:
        sentiment = "positive"
    elif raw_score < -0.15:
        sentiment = "negative"
    else:
        sentiment = "neutral"

    # Confidence based on signal strength and count
    base_confidence = min(1.0, abs(raw_score) * 0.6 + (total / 10) * 0.4)
    confidence = round(min(1.0, base_confidence * intensity), 2)

    return {
        "sentiment": sentiment,
        "confidence": confidence,
        "positive_count": int(pos_count),
        "negative_count": int(neg_count),
    }


def detect_themes(text: str) -> list[str]:
    """Detect theme categories present in a review.

    Args:
        text: The review text to analyze.

    Returns:
        List of matched theme names (e.g., ["UX/UI", "Performance"]).
    """
    text_lower = text.lower()
    tokens_set = set(_tokenize(text))
    matched: list[str] = []

    for theme, keywords in THEME_KEYWORDS.items():
        for kw in keywords:
            if " " in kw:
                if _has_phrase(text_lower, kw):
                    matched.append(theme)
                    break
            elif kw in tokens_set:
                matched.append(theme)
                break

    return matched


def extract_keywords(text: str, top_n: int = 20) -> list[tuple[str, int]]:
    """Extract most frequent meaningful words from text.

    Args:
        text: The text to analyze.
        top_n: Number of top keywords to return.

    Returns:
        List of (word, count) tuples sorted by frequency descending.
    """
    stopwords = {
        "the", "a", "an", "is", "it", "to", "and", "of", "in", "for",
        "on", "with", "that", "this", "was", "are", "be", "have", "has",
        "had", "but", "or", "not", "from", "at", "by", "as", "my", "me",
        "we", "our", "i", "you", "they", "their", "them", "its", "so",
        "if", "can", "do", "did", "been", "just", "very", "really",
        "would", "could", "should", "will", "also", "than", "then",
        "when", "what", "which", "who", "how", "all", "more", "some",
        "about", "up", "out", "no", "get", "got", "even", "much",
        "too", "only", "don't", "doesn't", "there", "here", "been",
        "every", "after", "before", "into", "over", "still", "other",
    }
    tokens = _tokenize(text)
    filtered = [t for t in tokens if t not in stopwords and len(t) > 2]
    return Counter(filtered).most_common(top_n)


# ---------------------------------------------------------------------------
# Batch analysis
# ---------------------------------------------------------------------------

def analyze_reviews(reviews: list[str]) -> dict[str, Any]:
    """Analyze a batch of reviews and return aggregate results.

    Args:
        reviews: List of review text strings.

    Returns:
        Dictionary with keys:
            review_count - number of reviews analyzed
            reviews - list of per-review result dicts
            positive_pct - percentage of positive reviews
            negative_pct - percentage of negative reviews
            neutral_pct - percentage of neutral reviews
            average_confidence - mean confidence across reviews
            top_themes - list of (theme, count) sorted by frequency
            keyword_frequency - list of (word, count) top keywords
            summary - brief text summary of findings
    """
    if not reviews:
        return {
            "review_count": 0,
            "reviews": [],
            "positive_pct": 0.0,
            "negative_pct": 0.0,
            "neutral_pct": 0.0,
            "average_confidence": 0.0,
            "top_themes": [],
            "keyword_frequency": [],
            "summary": "No reviews provided.",
        }

    per_review_results: list[dict[str, Any]] = []
    sentiment_counts: dict[str, int] = {"positive": 0, "negative": 0, "neutral": 0}
    theme_counter: Counter[str] = Counter()
    all_text = ""
    total_confidence = 0.0

    for review_text in reviews:
        sentiment_result = analyze_sentiment(review_text)
        themes = detect_themes(review_text)

        per_review_results.append({
            "text": review_text[:200] + ("..." if len(review_text) > 200 else ""),
            "sentiment": sentiment_result["sentiment"],
            "confidence": sentiment_result["confidence"],
            "detected_themes": themes,
        })

        sentiment_counts[sentiment_result["sentiment"]] += 1
        total_confidence += sentiment_result["confidence"]
        theme_counter.update(themes)
        all_text += " " + review_text

    total = len(reviews)
    positive_pct = round((sentiment_counts["positive"] / total) * 100, 1)
    negative_pct = round((sentiment_counts["negative"] / total) * 100, 1)
    neutral_pct = round((sentiment_counts["neutral"] / total) * 100, 1)
    average_confidence = round(total_confidence / total, 2)

    top_themes = theme_counter.most_common()
    keyword_freq = extract_keywords(all_text, top_n=20)

    # Build summary
    dominant = max(sentiment_counts, key=sentiment_counts.get)  # type: ignore[arg-type]
    summary_parts = [
        f"Analyzed {total} reviews.",
        f"Overall sentiment is predominantly {dominant} "
        f"({positive_pct}% positive, {negative_pct}% negative, {neutral_pct}% neutral).",
    ]
    if top_themes:
        top_three = [t[0] for t in top_themes[:3]]
        summary_parts.append(f"Most discussed themes: {', '.join(top_three)}.")

    return {
        "review_count": total,
        "reviews": per_review_results,
        "positive_pct": positive_pct,
        "negative_pct": negative_pct,
        "neutral_pct": neutral_pct,
        "average_confidence": average_confidence,
        "top_themes": top_themes,
        "keyword_frequency": keyword_freq,
        "summary": " ".join(summary_parts),
    }


def generate_executive_summary(results: dict[str, Any]) -> dict[str, Any]:
    """Generate an executive summary from analysis results.

    Args:
        results: Output from analyze_reviews.

    Returns:
        Dictionary with executive summary fields.
    """
    if results["review_count"] == 0:
        return {"error": "No reviews to summarize."}

    # Derive a 1-5 score from sentiment distribution
    score = round(
        (results["positive_pct"] * 5 + results["neutral_pct"] * 3 + results["negative_pct"] * 1) / 100,
        1,
    )

    # Identify strengths (themes common in positive reviews)
    positive_reviews = [r for r in results["reviews"] if r["sentiment"] == "positive"]
    negative_reviews = [r for r in results["reviews"] if r["sentiment"] == "negative"]

    pos_themes: Counter[str] = Counter()
    neg_themes: Counter[str] = Counter()
    feature_requests: list[str] = []

    for r in positive_reviews:
        pos_themes.update(r["detected_themes"])
    for r in negative_reviews:
        neg_themes.update(r["detected_themes"])
        # Simple heuristic: if "Features" is a theme in a negative review, it may be a feature request
        if "Features" in r["detected_themes"]:
            feature_requests.append(r["text"])

    strengths = [t[0] for t in pos_themes.most_common(3)]
    weaknesses = [t[0] for t in neg_themes.most_common(3)]

    # Recommended actions
    actions: list[str] = []
    if "Support" in neg_themes:
        actions.append("Improve customer support response times and quality")
    if "Bugs" in neg_themes:
        actions.append("Prioritize bug fixes mentioned in negative reviews")
    if "Performance" in neg_themes:
        actions.append("Investigate and resolve performance and stability issues")
    if "Pricing" in neg_themes:
        actions.append("Review pricing strategy and communicate value more clearly")
    if "Onboarding" in neg_themes:
        actions.append("Simplify onboarding flow and improve documentation")
    if not actions:
        actions.append("Continue monitoring review sentiment for emerging issues")

    return {
        "sentiment_score": score,
        "total_reviews": results["review_count"],
        "sentiment_distribution": {
            "positive": results["positive_pct"],
            "negative": results["negative_pct"],
            "neutral": results["neutral_pct"],
        },
        "strengths": strengths,
        "weaknesses": weaknesses,
        "feature_requests_count": len(feature_requests),
        "recommended_actions": actions,
        "summary_text": results["summary"],
    }


# ---------------------------------------------------------------------------
# Standalone demo
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("Review Sentiment Analyzer - Demo")
    print("=" * 60)

    sample_reviews = [
        "Love the new dashboard! So much easier to navigate now. The charts are beautiful and load instantly.",
        "Terrible customer support. Waited 3 days for a response and they didn't even solve my problem.",
        "It's okay. Does what I need but the pricing feels high for what you get. Would be nice to have a cheaper plan.",
        "App crashes every time I try to export a PDF. Very frustrating. This has been broken for weeks.",
        "Onboarding was smooth and the docs are great. Had everything set up in under 10 minutes.",
        "The automation features save us hours every week. Best tool we've adopted this year.",
        "UI is clunky and outdated. Feels like a product from 2010. Please redesign the interface.",
        "Fast, reliable, and the integrations with Slack and Jira work perfectly. Highly recommend.",
        "Not worth the premium price. The free tier is too limited and the jump to paid is too steep.",
        "Great product overall but there's a persistent bug where notifications don't appear on mobile.",
    ]

    results = analyze_reviews(sample_reviews)

    print(f"\nReviews analyzed: {results['review_count']}")
    print(f"Positive: {results['positive_pct']}%")
    print(f"Negative: {results['negative_pct']}%")
    print(f"Neutral:  {results['neutral_pct']}%")
    print(f"Average confidence: {results['average_confidence']}")

    print("\nPer-review results:")
    for i, r in enumerate(results["reviews"], 1):
        themes_str = ", ".join(r["detected_themes"]) if r["detected_themes"] else "none"
        print(f"  {i}. {r['sentiment'].upper()} ({r['confidence']}) - Themes: {themes_str}")
        print(f"     \"{r['text'][:80]}...\"")

    print("\nTop themes:")
    for theme, count in results["top_themes"]:
        print(f"  {theme}: {count} mentions")

    print("\nTop keywords:")
    for word, count in results["keyword_frequency"][:10]:
        print(f"  {word}: {count}")

    print("\n" + "=" * 60)
    print("Executive Summary")
    print("=" * 60)

    summary = generate_executive_summary(results)
    print(f"\nSentiment Score: {summary['sentiment_score']}/5.0")
    print(f"Strengths: {', '.join(summary['strengths']) if summary['strengths'] else 'N/A'}")
    print(f"Weaknesses: {', '.join(summary['weaknesses']) if summary['weaknesses'] else 'N/A'}")
    print(f"Feature requests found: {summary['feature_requests_count']}")
    print("\nRecommended actions:")
    for action in summary["recommended_actions"]:
        print(f"  - {action}")
    print(f"\n{summary['summary_text']}")
