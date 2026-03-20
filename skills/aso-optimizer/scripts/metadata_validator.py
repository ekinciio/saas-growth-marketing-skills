"""
ASO Metadata Validator

Validates app store metadata fields against platform-specific character limits
for iOS (Apple App Store) and Android (Google Play Store).

Usage:
    from metadata_validator import validate_metadata

    metadata = {
        "title": "MyApp - Task Manager",
        "subtitle": "Organize Your Life",
        "keywords": "todo,tasks,planner,organizer,productivity",
        "short_description": "Simple and powerful task management for everyone.",
        "description": "MyApp helps you stay organized...",
        "whats_new": "Bug fixes and performance improvements.",
        "promotional_text": "Now with dark mode support!",
        "developer_name": "My Company Inc."
    }

    results = validate_metadata(metadata, platform="both")
"""

from typing import Any


# Character limits per platform
IOS_LIMITS: dict[str, int] = {
    "title": 30,
    "subtitle": 30,
    "keywords": 100,
    "promotional_text": 170,
    "description": 4000,
    "whats_new": 4000,
    "developer_name": 50,
}

ANDROID_LIMITS: dict[str, int] = {
    "title": 30,
    "short_description": 80,
    "description": 4000,
    "whats_new": 500,
}

# Fields that are platform-specific
IOS_ONLY_FIELDS: set[str] = {"subtitle", "keywords", "promotional_text"}
ANDROID_ONLY_FIELDS: set[str] = {"short_description"}


def validate_field(
    field_name: str,
    value: str,
    max_chars: int,
) -> dict[str, Any]:
    """Validate a single metadata field against its character limit.

    Args:
        field_name: Name of the metadata field.
        value: The content of the field.
        max_chars: Maximum allowed characters for this field.

    Returns:
        Dictionary with validation results including pass/fail status,
        character count, limit, and remaining characters.
    """
    char_count = len(value)
    remaining = max_chars - char_count
    passed = char_count <= max_chars

    # Determine utilization level
    utilization = char_count / max_chars if max_chars > 0 else 0
    if not passed:
        status = "over_limit"
    elif utilization >= 0.8:
        status = "well_utilized"
    elif utilization >= 0.5:
        status = "under_utilized"
    elif utilization > 0:
        status = "poorly_utilized"
    else:
        status = "empty"

    return {
        "field": field_name,
        "passed": passed,
        "char_count": char_count,
        "max_chars": max_chars,
        "remaining": remaining,
        "utilization_pct": round(utilization * 100, 1),
        "status": status,
    }


def validate_metadata(
    metadata: dict[str, str],
    platform: str = "both",
) -> dict[str, Any]:
    """Validate all metadata fields against platform character limits.

    Args:
        metadata: Dictionary of metadata fields and their values.
            Supported keys: title, subtitle, keywords, short_description,
            description, whats_new, promotional_text, developer_name.
        platform: Target platform - "ios", "android", or "both".

    Returns:
        Dictionary containing:
            - platform: The validated platform(s)
            - overall_passed: True if all fields pass validation
            - fields: List of per-field validation results
            - summary: Counts of passed, failed, and missing fields
            - warnings: List of warning messages for potential issues

    Raises:
        ValueError: If platform is not "ios", "android", or "both".
    """
    platform = platform.lower().strip()
    if platform not in ("ios", "android", "both"):
        raise ValueError(
            f"Invalid platform '{platform}'. Must be 'ios', 'android', or 'both'."
        )

    results: dict[str, Any] = {
        "platform": platform,
        "overall_passed": True,
        "fields": [],
        "summary": {"passed": 0, "failed": 0, "missing": 0, "warnings": 0},
        "warnings": [],
    }

    # Determine which limits to check
    limits_to_check: dict[str, int] = {}
    if platform in ("ios", "both"):
        limits_to_check.update(IOS_LIMITS)
    if platform in ("android", "both"):
        limits_to_check.update(ANDROID_LIMITS)

    for field_name, max_chars in limits_to_check.items():
        # Skip platform-specific fields when validating the other platform
        if platform == "ios" and field_name in ANDROID_ONLY_FIELDS:
            continue
        if platform == "android" and field_name in IOS_ONLY_FIELDS:
            continue

        value = metadata.get(field_name, "")

        if not value:
            results["fields"].append({
                "field": field_name,
                "passed": True,
                "char_count": 0,
                "max_chars": max_chars,
                "remaining": max_chars,
                "utilization_pct": 0.0,
                "status": "missing",
            })
            results["summary"]["missing"] += 1
            results["warnings"].append(
                f"'{field_name}' is empty or not provided. "
                f"Consider filling this field (max {max_chars} chars)."
            )
            results["summary"]["warnings"] += 1
            continue

        field_result = validate_field(field_name, value, max_chars)
        results["fields"].append(field_result)

        if not field_result["passed"]:
            results["overall_passed"] = False
            results["summary"]["failed"] += 1
        else:
            results["summary"]["passed"] += 1

        # Add warnings for under-utilization
        if field_result["status"] == "poorly_utilized":
            results["warnings"].append(
                f"'{field_name}' is only {field_result['utilization_pct']}% utilized "
                f"({field_result['char_count']}/{max_chars} chars). "
                f"Consider using more of the available space."
            )
            results["summary"]["warnings"] += 1
        elif field_result["status"] == "under_utilized":
            results["warnings"].append(
                f"'{field_name}' is {field_result['utilization_pct']}% utilized "
                f"({field_result['char_count']}/{max_chars} chars). "
                f"You have room for more keywords or detail."
            )
            results["summary"]["warnings"] += 1

    # Check for keyword repetition between iOS fields
    if platform in ("ios", "both"):
        _check_keyword_repetition(metadata, results)

    return results


def _check_keyword_repetition(
    metadata: dict[str, str],
    results: dict[str, Any],
) -> None:
    """Check for repeated words across iOS indexed fields.

    Apple indexes the title, subtitle, and keyword field separately. Repeating
    words across these fields wastes valuable keyword space.

    Args:
        metadata: The metadata dictionary.
        results: The results dictionary to append warnings to.
    """
    title_words = _extract_words(metadata.get("title", ""))
    subtitle_words = _extract_words(metadata.get("subtitle", ""))
    keyword_words = _extract_words(
        metadata.get("keywords", "").replace(",", " ")
    )

    # Check subtitle for words already in title
    title_subtitle_overlap = title_words & subtitle_words
    if title_subtitle_overlap:
        results["warnings"].append(
            f"Words repeated in both title and subtitle: "
            f"{', '.join(sorted(title_subtitle_overlap))}. "
            f"On iOS, this wastes subtitle space since title words are already indexed."
        )
        results["summary"]["warnings"] += 1

    # Check keywords field for words already in title or subtitle
    indexed_words = title_words | subtitle_words
    keyword_overlap = indexed_words & keyword_words
    if keyword_overlap:
        results["warnings"].append(
            f"Words in the keyword field already present in title/subtitle: "
            f"{', '.join(sorted(keyword_overlap))}. "
            f"Remove these from the keyword field to free up space for new terms."
        )
        results["summary"]["warnings"] += 1


def _extract_words(text: str) -> set[str]:
    """Extract lowercase words from text, ignoring short common words.

    Args:
        text: Input string.

    Returns:
        Set of lowercase words with 2+ characters.
    """
    if not text:
        return set()
    # Remove common punctuation
    for char in "-:.|/&":
        text = text.replace(char, " ")
    return {
        word.lower()
        for word in text.split()
        if len(word) >= 2
    }


def format_results(results: dict[str, Any]) -> str:
    """Format validation results as a human-readable string.

    Args:
        results: The validation results dictionary from validate_metadata.

    Returns:
        Formatted string summarizing all validation results.
    """
    lines = []
    lines.append(f"ASO Metadata Validation - Platform: {results['platform'].upper()}")
    lines.append("=" * 60)

    overall = "PASS" if results["overall_passed"] else "FAIL"
    lines.append(f"Overall: {overall}")
    lines.append(
        f"Fields: {results['summary']['passed']} passed, "
        f"{results['summary']['failed']} failed, "
        f"{results['summary']['missing']} missing"
    )
    lines.append("")

    # Field details
    lines.append("Field Details:")
    lines.append("-" * 60)
    for field in results["fields"]:
        icon = "PASS" if field["passed"] else "FAIL"
        if field["status"] == "missing":
            icon = "MISS"
        lines.append(
            f"  [{icon}] {field['field']}: "
            f"{field['char_count']}/{field['max_chars']} chars "
            f"({field['utilization_pct']}% used, "
            f"{field['remaining']} remaining) - {field['status']}"
        )

    if results["warnings"]:
        lines.append("")
        lines.append("Warnings:")
        lines.append("-" * 60)
        for warning in results["warnings"]:
            lines.append(f"  - {warning}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Standalone demo
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    sample_metadata = {
        "title": "FocusFlow - Pomodoro Timer",
        "subtitle": "Stay Productive Daily",
        "keywords": "focus,timer,pomodoro,productivity,work,study,concentration,deep,sessions,block",
        "short_description": "A simple Pomodoro timer that helps you stay focused and get more done every day.",
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
        "whats_new": "Version 2.1:\n- Added weekly focus reports\n- Bug fixes and performance improvements",
        "promotional_text": "New: Weekly focus reports are here! See how your productivity trends over time.",
        "developer_name": "FocusFlow Inc.",
    }

    print("Validating for iOS:")
    print(format_results(validate_metadata(sample_metadata, platform="ios")))
    print("\n")
    print("Validating for Android:")
    print(format_results(validate_metadata(sample_metadata, platform="android")))
    print("\n")
    print("Validating for both platforms:")
    print(format_results(validate_metadata(sample_metadata, platform="both")))
