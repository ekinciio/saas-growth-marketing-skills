"""
ASO Health Scorer

Fetches app metadata from the iTunes Search API and calculates an ASO health
score (0-100) based on title optimization, description quality, ratings health,
and metadata completeness.

Usage:
    from aso_scorer import score_app, score_metadata

    # Score by app name (fetches live data from iTunes)
    result = score_app("Slack")

    # Score from a pre-built metadata dictionary
    result = score_metadata({
        "title": "MyApp - Task Manager",
        "subtitle": "Organize Your Life",
        "description": "MyApp helps you stay organized...",
        "average_rating": 4.5,
        "rating_count": 12000,
        "keywords": "todo,tasks,planner",
        "screenshot_count": 6,
    })

Limitation:
    This module uses the free iTunes Search API. It does NOT provide keyword
    search volume, keyword difficulty scores, or download estimates. For those
    metrics, use paid tools like Sensor Tower, data.ai, or Apple Search Ads.
"""

import json
import re
import urllib.request
import urllib.parse
from typing import Any


# ---------------------------------------------------------------------------
# iTunes Search API helpers
# ---------------------------------------------------------------------------

ITUNES_SEARCH_URL = "https://itunes.apple.com/search"


def fetch_app_metadata(app_name: str, country: str = "us") -> dict[str, Any] | None:
    """Fetch app metadata from the iTunes Search API.

    Args:
        app_name: The app name to search for.
        country: Two-letter country code for the store region.

    Returns:
        Dictionary of normalized metadata fields, or None if not found.
    """
    params = urllib.parse.urlencode({
        "term": app_name,
        "entity": "software",
        "country": country,
        "limit": "1",
    })
    url = f"{ITUNES_SEARCH_URL}?{params}"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ASO-Scorer/1.0"})
        with urllib.request.urlopen(req, timeout=15) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        print(f"Error fetching data from iTunes API: {exc}")
        return None

    if not data.get("results"):
        return None

    app = data["results"][0]
    return _normalize_itunes_result(app)


def fetch_competitors(
    genre_id: int,
    country: str = "us",
    limit: int = 5,
    exclude_app: str = "",
) -> list[dict[str, Any]]:
    """Fetch top apps in the same genre for competitor comparison.

    Args:
        genre_id: The iTunes genre ID for the app's primary category.
        country: Two-letter country code.
        limit: Number of competitor apps to return.
        exclude_app: App name to exclude from results.

    Returns:
        List of normalized metadata dictionaries for competitor apps.
    """
    params = urllib.parse.urlencode({
        "term": "",
        "entity": "software",
        "country": country,
        "genreId": str(genre_id),
        "limit": str(limit + 3),  # fetch extra to account for exclusion
    })
    url = f"{ITUNES_SEARCH_URL}?{params}"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ASO-Scorer/1.0"})
        with urllib.request.urlopen(req, timeout=15) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception:
        return []

    competitors = []
    for app in data.get("results", []):
        normalized = _normalize_itunes_result(app)
        if normalized["title"].lower() != exclude_app.lower():
            competitors.append(normalized)
        if len(competitors) >= limit:
            break

    return competitors


def _normalize_itunes_result(app: dict[str, Any]) -> dict[str, Any]:
    """Normalize an iTunes Search API result into a standard metadata dict.

    Args:
        app: Raw app dictionary from the iTunes API.

    Returns:
        Normalized metadata dictionary.
    """
    return {
        "title": app.get("trackName", ""),
        "developer_name": app.get("artistName", ""),
        "description": app.get("description", ""),
        "average_rating": app.get("averageUserRating", 0),
        "rating_count": app.get("userRatingCount", 0),
        "price": app.get("price", 0),
        "currency": app.get("currency", "USD"),
        "primary_genre": app.get("primaryGenreName", ""),
        "primary_genre_id": app.get("primaryGenreId", 0),
        "genres": app.get("genres", []),
        "version": app.get("version", ""),
        "release_notes": app.get("releaseNotes", ""),
        "screenshot_urls": app.get("screenshotUrls", []),
        "screenshot_count": len(app.get("screenshotUrls", [])),
        "icon_url": app.get("artworkUrl512", ""),
        "bundle_id": app.get("bundleId", ""),
        "content_rating": app.get("contentAdvisoryRating", ""),
        "file_size_bytes": app.get("fileSizeBytes", "0"),
        "minimum_os_version": app.get("minimumOsVersion", ""),
        "supported_devices": app.get("supportedDevices", []),
        "store_url": app.get("trackViewUrl", ""),
    }


# ---------------------------------------------------------------------------
# Scoring functions
# ---------------------------------------------------------------------------

def score_title(metadata: dict[str, Any]) -> dict[str, Any]:
    """Score the app title optimization (30% weight).

    Evaluates keyword presence, character length, and brand-keyword balance.

    Args:
        metadata: Normalized metadata dictionary.

    Returns:
        Score breakdown dictionary with score (0-100) and details.
    """
    title = metadata.get("title", "")
    score = 0
    details = []

    # Length scoring (ideal: 25-30 characters)
    title_len = len(title)
    if 25 <= title_len <= 30:
        score += 35
        details.append(f"Title length ({title_len} chars) is in the ideal 25-30 range.")
    elif 20 <= title_len < 25:
        score += 25
        details.append(f"Title length ({title_len} chars) is good but could use more of the 30-char limit.")
    elif 15 <= title_len < 20:
        score += 15
        details.append(f"Title length ({title_len} chars) is short. Aim for 25-30 characters.")
    elif title_len > 30:
        score += 10
        details.append(f"Title length ({title_len} chars) exceeds the 30-char limit.")
    elif title_len > 0:
        score += 5
        details.append(f"Title length ({title_len} chars) is very short. Significant keyword space is unused.")
    else:
        details.append("Title is empty.")

    # Keyword separator check (brand - keyword pattern)
    has_separator = bool(re.search(r"[-:|]", title))
    if has_separator:
        score += 30
        details.append("Title includes a separator for brand-keyword structure.")
    else:
        score += 10
        details.append("Title lacks a separator. Consider 'Brand - Keyword' format.")

    # Word count (ideal: 3-6 words)
    word_count = len(title.split())
    if 3 <= word_count <= 6:
        score += 20
        details.append(f"Title has {word_count} words - good keyword density.")
    elif word_count > 6:
        score += 10
        details.append(f"Title has {word_count} words - may appear cluttered.")
    elif word_count >= 1:
        score += 10
        details.append(f"Title has only {word_count} word(s) - consider adding keywords.")

    # Capitalization check
    words = title.split()
    capitalized = sum(1 for w in words if w[0].isupper()) if words else 0
    if capitalized == len(words) and words:
        score += 15
        details.append("Title uses proper capitalization.")
    elif capitalized > 0:
        score += 10
        details.append("Title has inconsistent capitalization.")

    return {"score": min(score, 100), "details": details}


def score_description(metadata: dict[str, Any]) -> dict[str, Any]:
    """Score the app description quality (25% weight).

    Evaluates length, structure, keyword usage, and CTA presence.

    Args:
        metadata: Normalized metadata dictionary.

    Returns:
        Score breakdown dictionary with score (0-100) and details.
    """
    description = metadata.get("description", "")
    score = 0
    details = []

    desc_len = len(description)

    # Length scoring (ideal: 2000-4000 characters)
    if 2000 <= desc_len <= 4000:
        score += 30
        details.append(f"Description length ({desc_len} chars) is in the ideal 2000-4000 range.")
    elif 1000 <= desc_len < 2000:
        score += 20
        details.append(f"Description length ({desc_len} chars) is decent but could be more detailed.")
    elif 500 <= desc_len < 1000:
        score += 10
        details.append(f"Description length ({desc_len} chars) is short. Add more detail about features.")
    elif desc_len > 4000:
        score += 25
        details.append(f"Description length ({desc_len} chars) exceeds 4000 - will be truncated.")
    elif desc_len > 0:
        score += 5
        details.append(f"Description is very short ({desc_len} chars). Aim for 2000+ characters.")
    else:
        details.append("Description is empty.")

    # Structure check (line breaks, bullet points)
    has_line_breaks = "\n" in description
    has_bullets = bool(re.search(r"[-*]\s", description))
    if has_line_breaks and has_bullets:
        score += 25
        details.append("Description uses line breaks and bullet points for readability.")
    elif has_line_breaks:
        score += 15
        details.append("Description has line breaks. Consider adding bullet points.")
    elif desc_len > 0:
        score += 5
        details.append("Description is a wall of text. Add line breaks and bullet points.")

    # CTA check
    cta_patterns = [
        r"download\s+(now|today|free)",
        r"get\s+started",
        r"try\s+(it\s+)?(now|today|free)",
        r"install\s+(now|today|free)",
        r"start\s+(your|a)\s+",
        r"sign\s+up",
        r"join\s+",
    ]
    has_cta = any(re.search(p, description, re.IGNORECASE) for p in cta_patterns)
    if has_cta:
        score += 20
        details.append("Description includes a call-to-action.")
    else:
        score += 0
        details.append("No clear call-to-action found. Add one near the end.")

    # Feature list detection
    feature_patterns = [r"feature", r"what you.+get", r"why choose", r"highlights"]
    has_features = any(re.search(p, description, re.IGNORECASE) for p in feature_patterns)
    if has_features:
        score += 15
        details.append("Description highlights features or benefits.")
    elif desc_len > 500:
        score += 5
        details.append("Consider adding a clear features or benefits section.")

    # First-line quality (visible before "Read More")
    first_line = description.split("\n")[0] if description else ""
    if len(first_line) >= 80:
        score += 10
        details.append("First line is substantial - good for the preview.")
    elif len(first_line) >= 40:
        score += 5
        details.append("First line is short. Make it more compelling for the preview.")

    return {"score": min(score, 100), "details": details}


def score_ratings(metadata: dict[str, Any]) -> dict[str, Any]:
    """Score the ratings health (25% weight).

    Evaluates average rating, total rating count, and thresholds.

    Args:
        metadata: Normalized metadata dictionary.

    Returns:
        Score breakdown dictionary with score (0-100) and details.
    """
    avg_rating = metadata.get("average_rating", 0) or 0
    rating_count = metadata.get("rating_count", 0) or 0
    score = 0
    details = []

    # Average rating scoring
    if avg_rating >= 4.5:
        score += 50
        details.append(f"Average rating ({avg_rating:.1f}) is excellent (4.5+).")
    elif avg_rating >= 4.0:
        score += 35
        details.append(f"Average rating ({avg_rating:.1f}) is good (4.0+).")
    elif avg_rating >= 3.5:
        score += 20
        details.append(f"Average rating ({avg_rating:.1f}) is below ideal. Aim for 4.0+.")
    elif avg_rating >= 3.0:
        score += 10
        details.append(f"Average rating ({avg_rating:.1f}) is concerning. Address negative feedback.")
    elif avg_rating > 0:
        score += 5
        details.append(f"Average rating ({avg_rating:.1f}) is poor. Urgent improvement needed.")
    else:
        details.append("No rating data available.")

    # Rating count scoring
    if rating_count >= 50000:
        score += 40
        details.append(f"Rating count ({rating_count:,}) is very strong.")
    elif rating_count >= 10000:
        score += 30
        details.append(f"Rating count ({rating_count:,}) is solid.")
    elif rating_count >= 1000:
        score += 20
        details.append(f"Rating count ({rating_count:,}) is moderate. Keep soliciting reviews.")
    elif rating_count >= 100:
        score += 10
        details.append(f"Rating count ({rating_count:,}) is low. Implement review solicitation.")
    elif rating_count > 0:
        score += 5
        details.append(f"Rating count ({rating_count:,}) is very low. Focus on gathering reviews.")
    else:
        details.append("No ratings yet.")

    # Bonus for high rating + high count combination
    if avg_rating >= 4.0 and rating_count >= 5000:
        score += 10
        details.append("Strong combination of high rating and substantial review count.")

    return {"score": min(score, 100), "details": details}


def score_completeness(metadata: dict[str, Any]) -> dict[str, Any]:
    """Score metadata completeness (20% weight).

    Checks whether all important fields are populated and utilized.

    Args:
        metadata: Normalized metadata dictionary.

    Returns:
        Score breakdown dictionary with score (0-100) and details.
    """
    score = 0
    details = []

    # Title present
    if metadata.get("title"):
        score += 15
    else:
        details.append("Title is missing.")

    # Description present and substantial
    desc = metadata.get("description", "")
    if len(desc) >= 1000:
        score += 15
    elif len(desc) > 0:
        score += 8
        details.append("Description is present but short.")
    else:
        details.append("Description is missing.")

    # Subtitle (iOS field - may not be available via API)
    if metadata.get("subtitle"):
        score += 15
        details.append("Subtitle is populated.")
    else:
        details.append("Subtitle not detected (may not be available via API).")

    # Keywords field (iOS field - not exposed via API)
    if metadata.get("keywords"):
        score += 15
        details.append("Keywords field is populated.")
    else:
        details.append("Keywords field not detected (not exposed via iTunes API).")

    # Screenshots
    screenshot_count = metadata.get("screenshot_count", 0)
    if screenshot_count >= 6:
        score += 20
        details.append(f"Good screenshot coverage ({screenshot_count} screenshots).")
    elif screenshot_count >= 3:
        score += 10
        details.append(f"Only {screenshot_count} screenshots. Aim for 6-10.")
    elif screenshot_count > 0:
        score += 5
        details.append(f"Only {screenshot_count} screenshot(s). Add more.")
    else:
        details.append("No screenshot data available.")

    # Developer name
    if metadata.get("developer_name"):
        score += 5

    # Release notes
    if metadata.get("release_notes"):
        score += 10
        details.append("Release notes (What's New) are present.")
    else:
        score += 0
        details.append("Release notes are missing or empty.")

    # Icon
    if metadata.get("icon_url"):
        score += 5

    if not details:
        details.append("All metadata fields are populated.")

    return {"score": min(score, 100), "details": details}


def calculate_aso_score(metadata: dict[str, Any]) -> dict[str, Any]:
    """Calculate the overall ASO health score with weighted breakdown.

    Weights:
        - Title Optimization: 30%
        - Description Quality: 25%
        - Ratings Health: 25%
        - Metadata Completeness: 20%

    Args:
        metadata: Normalized metadata dictionary.

    Returns:
        Dictionary with overall score, category breakdown, and recommendations.
    """
    title_result = score_title(metadata)
    desc_result = score_description(metadata)
    ratings_result = score_ratings(metadata)
    completeness_result = score_completeness(metadata)

    overall_score = round(
        title_result["score"] * 0.30
        + desc_result["score"] * 0.25
        + ratings_result["score"] * 0.25
        + completeness_result["score"] * 0.20
    )

    # Generate grade
    if overall_score >= 90:
        grade = "Excellent"
    elif overall_score >= 70:
        grade = "Good"
    elif overall_score >= 50:
        grade = "Needs Work"
    elif overall_score >= 30:
        grade = "Poor"
    else:
        grade = "Critical"

    # Generate recommendations based on lowest-scoring areas
    recommendations = _generate_recommendations(
        title_result, desc_result, ratings_result, completeness_result
    )

    return {
        "overall_score": overall_score,
        "grade": grade,
        "breakdown": {
            "title_optimization": {
                "score": title_result["score"],
                "weight": "30%",
                "weighted_score": round(title_result["score"] * 0.30, 1),
                "details": title_result["details"],
            },
            "description_quality": {
                "score": desc_result["score"],
                "weight": "25%",
                "weighted_score": round(desc_result["score"] * 0.25, 1),
                "details": desc_result["details"],
            },
            "ratings_health": {
                "score": ratings_result["score"],
                "weight": "25%",
                "weighted_score": round(ratings_result["score"] * 0.25, 1),
                "details": ratings_result["details"],
            },
            "metadata_completeness": {
                "score": completeness_result["score"],
                "weight": "20%",
                "weighted_score": round(completeness_result["score"] * 0.20, 1),
                "details": completeness_result["details"],
            },
        },
        "recommendations": recommendations,
    }


def _generate_recommendations(
    title_result: dict[str, Any],
    desc_result: dict[str, Any],
    ratings_result: dict[str, Any],
    completeness_result: dict[str, Any],
) -> list[str]:
    """Generate prioritized recommendations based on scoring results.

    Args:
        title_result: Title scoring result.
        desc_result: Description scoring result.
        ratings_result: Ratings scoring result.
        completeness_result: Completeness scoring result.

    Returns:
        List of recommendation strings, ordered by priority.
    """
    recommendations = []

    # Title recommendations
    if title_result["score"] < 50:
        recommendations.append(
            "HIGH PRIORITY: Optimize your app title. Use the format "
            "'Brand - Primary Keyword' and aim for 25-30 characters."
        )
    elif title_result["score"] < 75:
        recommendations.append(
            "MEDIUM PRIORITY: Your title has room for improvement. "
            "Ensure it includes a high-value keyword alongside your brand name."
        )

    # Description recommendations
    if desc_result["score"] < 50:
        recommendations.append(
            "HIGH PRIORITY: Rewrite your description. Aim for 2000-4000 "
            "characters with bullet points, feature highlights, and a CTA."
        )
    elif desc_result["score"] < 75:
        recommendations.append(
            "MEDIUM PRIORITY: Improve description structure. Add bullet points, "
            "line breaks, and a clear call-to-action."
        )

    # Ratings recommendations
    if ratings_result["score"] < 50:
        recommendations.append(
            "HIGH PRIORITY: Improve your ratings. Implement in-app review "
            "prompts, respond to negative reviews, and address common complaints."
        )
    elif ratings_result["score"] < 75:
        recommendations.append(
            "MEDIUM PRIORITY: Boost your rating count. Use strategic review "
            "solicitation after positive user actions."
        )

    # Completeness recommendations
    if completeness_result["score"] < 50:
        recommendations.append(
            "HIGH PRIORITY: Fill in all metadata fields. Ensure subtitle, "
            "keywords, screenshots, and release notes are all populated."
        )
    elif completeness_result["score"] < 75:
        recommendations.append(
            "MEDIUM PRIORITY: Some metadata fields are incomplete or "
            "under-utilized. Review and fill any gaps."
        )

    if not recommendations:
        recommendations.append(
            "Your ASO is in good shape. Focus on maintaining current quality "
            "and iterating on keyword strategy based on ranking data."
        )

    return recommendations


# ---------------------------------------------------------------------------
# Public API functions
# ---------------------------------------------------------------------------

def score_app(
    app_name: str,
    country: str = "us",
    include_competitors: bool = True,
) -> dict[str, Any] | None:
    """Fetch app data from iTunes and calculate ASO health score.

    Args:
        app_name: The app name to search for.
        country: Two-letter country code.
        include_competitors: Whether to fetch and score competitor apps.

    Returns:
        Dictionary with app metadata, ASO score, competitor comparison,
        and recommendations. Returns None if the app is not found.
    """
    metadata = fetch_app_metadata(app_name, country)
    if metadata is None:
        print(f"App '{app_name}' not found on the iTunes Store.")
        return None

    aso_result = calculate_aso_score(metadata)

    result: dict[str, Any] = {
        "app_name": metadata["title"],
        "score": aso_result["overall_score"],
        "grade": aso_result["grade"],
        "breakdown": aso_result["breakdown"],
        "recommendations": aso_result["recommendations"],
        "metadata": metadata,
    }

    if include_competitors and metadata.get("primary_genre_id"):
        competitors = fetch_competitors(
            genre_id=metadata["primary_genre_id"],
            country=country,
            limit=5,
            exclude_app=metadata["title"],
        )
        competitor_scores = []
        for comp in competitors:
            comp_score = calculate_aso_score(comp)
            competitor_scores.append({
                "app_name": comp["title"],
                "score": comp_score["overall_score"],
                "grade": comp_score["grade"],
                "rating": comp.get("average_rating", 0),
                "rating_count": comp.get("rating_count", 0),
            })
        result["competitor_comparison"] = competitor_scores

    return result


def score_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    """Calculate ASO health score from a pre-built metadata dictionary.

    Use this when you already have metadata and do not need to fetch from
    the iTunes API.

    Args:
        metadata: Dictionary with metadata fields. Supported keys:
            title, subtitle, keywords, description, average_rating,
            rating_count, screenshot_count, developer_name, release_notes,
            icon_url.

    Returns:
        Dictionary with score, grade, breakdown, and recommendations.
    """
    aso_result = calculate_aso_score(metadata)
    return {
        "app_name": metadata.get("title", "Unknown"),
        "score": aso_result["overall_score"],
        "grade": aso_result["grade"],
        "breakdown": aso_result["breakdown"],
        "recommendations": aso_result["recommendations"],
    }


def format_score_report(result: dict[str, Any]) -> str:
    """Format an ASO score result as a human-readable report.

    Args:
        result: The result dictionary from score_app or score_metadata.

    Returns:
        Formatted string report.
    """
    lines = []
    lines.append(f"ASO Health Score Report: {result['app_name']}")
    lines.append("=" * 60)
    lines.append(f"Overall Score: {result['score']}/100 ({result['grade']})")
    lines.append("")

    lines.append("Category Breakdown:")
    lines.append("-" * 60)
    for category, data in result["breakdown"].items():
        label = category.replace("_", " ").title()
        lines.append(
            f"  {label}: {data['score']}/100 "
            f"(weight: {data['weight']}, "
            f"contributes: {data['weighted_score']} pts)"
        )
        for detail in data["details"]:
            lines.append(f"    - {detail}")

    lines.append("")
    lines.append("Recommendations:")
    lines.append("-" * 60)
    for i, rec in enumerate(result["recommendations"], 1):
        lines.append(f"  {i}. {rec}")

    if result.get("competitor_comparison"):
        lines.append("")
        lines.append("Competitor Comparison:")
        lines.append("-" * 60)
        for comp in result["competitor_comparison"]:
            lines.append(
                f"  {comp['app_name']}: "
                f"Score {comp['score']}/100 ({comp['grade']}), "
                f"Rating {comp.get('rating', 0):.1f} "
                f"({comp.get('rating_count', 0):,} reviews)"
            )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Standalone demo
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("=" * 60)
    print("ASO Scorer - Demo")
    print("=" * 60)
    print()

    # Demo 1: Score from a pre-built metadata dictionary
    print("Demo 1: Scoring from metadata dictionary")
    print("-" * 40)
    sample_metadata = {
        "title": "FocusFlow - Pomodoro Timer",
        "subtitle": "Stay Productive Daily",
        "keywords": "focus,timer,pomodoro,productivity,work,study,concentration,deep,sessions,block",
        "description": (
            "FocusFlow is the simplest way to use the Pomodoro Technique for "
            "better productivity.\n\n"
            "Set a 25-minute focus session, take a short break, and repeat. "
            "FocusFlow tracks your sessions and helps you build a consistent "
            "work habit over time.\n\n"
            "Features:\n"
            "- Customizable timer lengths\n"
            "- Session history and streaks\n"
            "- Focus statistics and weekly reports\n"
            "- Gentle notification sounds\n"
            "- Dark mode support\n\n"
            "Download FocusFlow today and take control of your time."
        ),
        "average_rating": 4.6,
        "rating_count": 8500,
        "screenshot_count": 8,
        "developer_name": "FocusFlow Inc.",
        "release_notes": "Version 2.1: Added weekly focus reports and bug fixes.",
        "icon_url": "https://example.com/icon.png",
    }

    result = score_metadata(sample_metadata)
    print(format_score_report(result))

    print()
    print("=" * 60)
    print()

    # Demo 2: Score a live app from iTunes (requires network)
    print("Demo 2: Fetching and scoring a live app from iTunes")
    print("-" * 40)
    print("Fetching data for 'Slack'...")
    live_result = score_app("Slack", include_competitors=True)
    if live_result:
        print(format_score_report(live_result))
    else:
        print("Could not fetch app data. Check your network connection.")
