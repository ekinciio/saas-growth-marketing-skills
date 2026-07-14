#!/usr/bin/env python3
"""Review Sentiment Analyzer - Keyword-based sentiment and theme extraction.

Analyzes customer reviews for sentiment (positive, negative, neutral),
detects themes (UX/UI, Performance, Pricing, Support, Features, Bugs,
Onboarding), and produces aggregate statistics with keyword frequency.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
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
    "good", "nice", "works", "worth", "incredible", "top-notch",
}

NEGATIVE_WORDS: set[str] = {
    "terrible", "awful", "horrible", "worst", "broken", "slow", "frustrating",
    "annoying", "useless", "buggy", "confusing", "complicated", "expensive",
    "overpriced", "unreliable", "disappointed", "unresponsive", "clunky",
    "laggy", "outdated", "crash", "crashes", "error", "bug", "glitch",
    "fail", "failure", "ugly", "nightmare", "waste", "regret", "hate",
    "poor", "lacking", "bad", "worse", "painful", "unusable", "garbage",
    "mediocre", "rude", "unhelpful", "unacceptable",
    "scam", "refund", "cancel", "uninstall", "uninstalled", "limited",
    "steep", "stole", "ghosted", "misleading", "dealbreaker",
}

# Multi-word phrases are matched (and masked) before single-token matching.
# A matched phrase counts as a strong (2x) sentiment signal. Lists are
# aligned with references/sentiment-categories.md.
POSITIVE_PHRASES: tuple[str, ...] = (
    "highly recommend", "works great", "game changer", "love it",
    "life saver",
)

NEGATIVE_PHRASES: tuple[str, ...] = (
    "waste of money", "doesn't work", "does not work", "not worth",
    "going to cancel", "asked for refund", "rip-off", "rip off",
    "stopped working",
)

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
    "slightly", "somewhat", "fairly", "rather", "quite", "mostly",
}

# Multi-word downtoners are checked against the full text, since they can
# never match in the single-token loop.
MULTIWORD_DOWNTONERS: tuple[str, ...] = (
    "a bit", "a little", "kind of", "sort of",
)

# Star-rating priors for the documented star -> sentiment mapping
# (1-2 stars: negative, 3 stars: neutral, 4-5 stars: positive).
RATING_PRIORS: dict[int, float] = {1: -1.0, 2: -0.6, 3: 0.0, 4: 0.6, 5: 1.0}

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
        "chat", "email", "phone", "wait", "agent", "representative",
        "resolve", "solution", "helpful", "unhelpful", "rude", "friendly",
        "knowledgeable", "documentation", "faq", "community",
    },
    "Features": {
        "feature", "functionality", "capability", "tool", "option",
        "setting", "integration", "api", "export", "import", "automation",
        "workflow", "customization", "template", "report", "analytics",
        "notification", "search", "filter", "sort", "missing", "wish",
        "request",
    },
    "Bugs": {
        # Generic words like "issue"/"problem" are excluded: they spuriously
        # tag support/pricing reviews as Bugs.
        "bug", "error", "glitch", "broken", "fix",
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


def _expand_tokens(tokens: list[str]) -> set[str]:
    """Expand tokens with naive suffix-stripped variants (s, es, ed, ing).

    This lets theme keywords match simple inflections, e.g. "crashes" ->
    "crash", "integrations" -> "integration", "waited" -> "wait".
    """
    expanded = set(tokens)
    for token in tokens:
        for suffix in ("ing", "ed", "es", "s"):
            if token.endswith(suffix) and len(token) - len(suffix) >= 3:
                expanded.add(token[: -len(suffix)])
    return expanded


# ---------------------------------------------------------------------------
# Core analysis
# ---------------------------------------------------------------------------

def analyze_sentiment(text: str, rating: int | None = None) -> dict[str, Any]:
    """Classify a single review's sentiment.

    A phrase-matching pass runs first: multi-word phrases (e.g. "not worth",
    "works great") count as strong (2x) signals and are masked from the text
    so their words are not double-counted or flipped by negation. Then a
    token pass handles single sentiment words with negation (negation resets
    at sentence-ending punctuation and after 3 non-sentiment tokens). When a
    star rating is provided, it acts as a prior (1-2 stars negative, 3
    neutral, 4-5 positive) that blends with the text score; strong text
    signals can override the rating.

    Args:
        text: The review text to analyze.
        rating: Optional star rating (1-5) used as a sentiment prior.

    Returns:
        Dictionary with keys:
            sentiment - "positive", "negative", or "neutral"
            confidence - float between 0.3 and 0.95
            positive_count - number of positive signals
            negative_count - number of negative signals
    """
    text_lower = text.lower()

    # Signal counts (int) and strengths (float; phrases count 2x,
    # negated negatives count 0.5x)
    pos_signals = 0
    neg_signals = 0
    pos_strength = 0.0
    neg_strength = 0.0
    intensity = 1.0

    # Phrase pass: match multi-word phrases first, mask them out so their
    # words are not re-counted or mis-flipped by the token pass.
    masked = text_lower
    for phrase in NEGATIVE_PHRASES:
        occurrences = masked.count(phrase)
        if occurrences:
            neg_signals += occurrences
            neg_strength += 2.0 * occurrences
            masked = masked.replace(phrase, " ")
    for phrase in POSITIVE_PHRASES:
        occurrences = masked.count(phrase)
        if occurrences:
            pos_signals += occurrences
            pos_strength += 2.0 * occurrences
            masked = masked.replace(phrase, " ")

    tokens = _tokenize(masked)

    # Check for amplifiers / downtoners (global influence)
    for token in tokens:
        if token in AMPLIFIERS:
            intensity = min(intensity + 0.05, 1.3)
        elif token in DOWNTONERS:
            intensity = max(intensity - 0.05, 0.7)
    for downtoner in MULTIWORD_DOWNTONERS:
        if downtoner in masked:
            intensity = max(intensity - 0.05, 0.7)

    # Token pass with negation handling. Negation never crosses a sentence
    # boundary and expires after 3 non-sentiment tokens.
    for sentence in re.split(r"[.!?]+", masked):
        negation_active = False
        tokens_since_negation = 0
        for token in _tokenize(sentence):
            if token in NEGATION_WORDS:
                negation_active = True
                tokens_since_negation = 0
                continue

            is_positive = token in POSITIVE_WORDS
            is_negative = token in NEGATIVE_WORDS

            if negation_active and (is_positive or is_negative):
                # Flip sentiment
                if is_positive:
                    neg_signals += 1
                    neg_strength += 1.0
                else:
                    # Negated negative is mildly positive
                    pos_signals += 1
                    pos_strength += 0.5
                negation_active = False
            elif is_positive:
                pos_signals += 1
                pos_strength += 1.0
            elif is_negative:
                neg_signals += 1
                neg_strength += 1.0
            elif negation_active:
                # Negation persists across at most 3 intervening
                # non-sentiment tokens ("never experienced a single crash")
                tokens_since_negation += 1
                if tokens_since_negation > 3:
                    negation_active = False

    total_strength = pos_strength + neg_strength
    total_signals = pos_signals + neg_signals

    if total_strength == 0 and rating is None:
        return {
            "sentiment": "neutral",
            "confidence": 0.3,
            "positive_count": 0,
            "negative_count": 0,
        }

    # Raw score (-1 to +1 range) from text signals
    raw_score = (
        (pos_strength - neg_strength) / total_strength if total_strength else 0.0
    )

    # Blend with the star-rating prior when available. The rating shifts the
    # score; a strong contrary text signal keeps most of its weight.
    if rating is not None:
        prior = RATING_PRIORS.get(int(rating))
        if prior is not None:
            if total_strength == 0:
                raw_score = prior
            elif abs(raw_score) >= 0.6 and total_signals >= 3:
                raw_score = 0.75 * raw_score + 0.25 * prior
            else:
                raw_score = 0.5 * raw_score + 0.5 * prior

    # Determine sentiment label
    if raw_score > 0.15:
        sentiment = "positive"
    elif raw_score < -0.15:
        sentiment = "negative"
    else:
        sentiment = "neutral"

    # Confidence: floored at the 0.3 no-signal baseline, scaled by score
    # magnitude and signal count, capped at 0.95.
    base_confidence = (
        0.3 + abs(raw_score) * 0.4 + min(total_signals, 6) / 6 * 0.25
    )
    confidence = round(min(0.95, max(0.3, base_confidence * intensity)), 2)

    return {
        "sentiment": sentiment,
        "confidence": confidence,
        "positive_count": pos_signals,
        "negative_count": neg_signals,
    }


def detect_themes(text: str) -> list[str]:
    """Detect theme categories present in a review.

    Args:
        text: The review text to analyze.

    Returns:
        List of matched theme names (e.g., ["UX/UI", "Performance"]).
    """
    text_lower = text.lower()
    tokens_set = _expand_tokens(_tokenize(text))
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
        "too", "only", "don't", "doesn't", "there", "here",
        "every", "after", "before", "into", "over", "still", "other",
    }
    tokens = _tokenize(text)
    filtered = [t for t in tokens if t not in stopwords and len(t) > 2]
    return Counter(filtered).most_common(top_n)


# ---------------------------------------------------------------------------
# Batch analysis
# ---------------------------------------------------------------------------

def _normalize_review_item(item: Any) -> tuple[str, int | None]:
    """Normalize a review item into a (text, rating) pair.

    Accepts a plain string, a (text, rating) tuple/list, or a dict with
    "text" and optional "rating" keys. Ratings outside 1-5 are ignored.
    """
    text: str = ""
    rating: int | None = None
    if isinstance(item, dict):
        text = str(item.get("text", ""))
        rating = item.get("rating")
    elif isinstance(item, (tuple, list)):
        text = str(item[0]) if item else ""
        if len(item) > 1:
            rating = item[1]
    else:
        text = str(item)

    if rating is not None:
        try:
            rating = int(rating)
        except (TypeError, ValueError):
            rating = None
        else:
            if not 1 <= rating <= 5:
                rating = None
    return text, rating


def analyze_reviews(reviews: list[Any]) -> dict[str, Any]:
    """Analyze a batch of reviews and return aggregate results.

    Args:
        reviews: List of reviews. Each item may be a plain text string, a
            (text, rating) tuple, or a dict {"text": ..., "rating": ...}.
            When a star rating (1-5) is present it is blended into the
            sentiment score as a prior.

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

    for item in reviews:
        review_text, rating = _normalize_review_item(item)
        sentiment_result = analyze_sentiment(review_text, rating=rating)
        themes = detect_themes(review_text)

        per_review_results.append({
            "text": review_text[:200] + ("..." if len(review_text) > 200 else ""),
            "rating": rating,
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
# Command-line interface
# ---------------------------------------------------------------------------

def _print_results(results: dict[str, Any]) -> None:
    """Print batch analysis results and executive summary as text."""
    print(f"\nReviews analyzed: {results['review_count']}")
    print(f"Positive: {results['positive_pct']}%")
    print(f"Negative: {results['negative_pct']}%")
    print(f"Neutral:  {results['neutral_pct']}%")
    print(f"Average confidence: {results['average_confidence']}")

    print("\nPer-review results:")
    for i, r in enumerate(results["reviews"], 1):
        themes_str = ", ".join(r["detected_themes"]) if r["detected_themes"] else "none"
        rating_str = f", {r['rating']} stars" if r.get("rating") else ""
        print(f"  {i}. {r['sentiment'].upper()} ({r['confidence']}{rating_str}) - Themes: {themes_str}")
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


def run_demo(as_json: bool = False) -> None:
    """Run the built-in demo on 10 hardcoded sample reviews."""
    if not as_json:
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
    if as_json:
        print(json.dumps(results, indent=2))
    else:
        _print_results(results)


def _parse_review_line(line: str) -> tuple[str, int | None] | None:
    """Parse one input line into (text, rating). Blank lines return None.

    Lines may optionally be prefixed with a star rating and a pipe,
    e.g. "5|Great app". Lines without the prefix are plain review text.
    """
    line = line.strip()
    if not line:
        return None
    prefix, sep, rest = line.partition("|")
    if sep and prefix.strip().isdigit() and 1 <= int(prefix.strip()) <= 5:
        return rest.strip(), int(prefix.strip())
    return line, None


def main(argv: list[str] | None = None) -> int:
    """Command-line entry point.

    Usage:
        python3 sentiment_analyzer.py reviews.txt          # one review per line
        python3 sentiment_analyzer.py -                    # read from stdin
        python3 sentiment_analyzer.py reviews.txt --json   # JSON output
        python3 sentiment_analyzer.py --demo               # built-in demo
    """
    parser = argparse.ArgumentParser(
        description=(
            "Analyze customer review sentiment. Input is one review per "
            "line (blank lines skipped); a line may start with an optional "
            'star rating, e.g. "5|Great app".'
        ),
    )
    parser.add_argument(
        "input",
        nargs="?",
        help="Path to a reviews text file, or '-' to read from stdin.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output full results as JSON instead of a text report.",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run the built-in demo on 10 sample reviews.",
    )
    args = parser.parse_args(argv)

    if args.demo:
        run_demo(as_json=args.json)
        return 0

    if not args.input:
        parser.error("provide a reviews file (or '-' for stdin), or use --demo")

    if args.input == "-":
        lines = sys.stdin.read().splitlines()
    else:
        try:
            with open(args.input, "r", encoding="utf-8") as fh:
                lines = fh.read().splitlines()
        except OSError as exc:
            print(f"Error reading reviews file '{args.input}': {exc}", file=sys.stderr)
            return 1

    reviews: list[tuple[str, int | None]] = []
    for line in lines:
        parsed = _parse_review_line(line)
        if parsed is not None:
            reviews.append(parsed)

    if not reviews:
        print("No reviews found in the input.", file=sys.stderr)
        return 1

    results = analyze_reviews(reviews)
    if args.json:
        print(json.dumps(results, indent=2))
    else:
        _print_results(results)
    return 0


if __name__ == "__main__":
    sys.exit(main())
