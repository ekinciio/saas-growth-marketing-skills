#!/usr/bin/env python3
"""Local SEO Scorer - Scores local SEO presence and provides recommendations.

Takes business information and GBP checklist responses, then calculates
a comprehensive local SEO score (0-100) with a breakdown by category
and prioritized recommendations.
"""

from typing import Any


# ---------------------------------------------------------------------------
# Category weights (must sum to 1.0)
# ---------------------------------------------------------------------------
CATEGORY_WEIGHTS: dict[str, float] = {
    "gbp_completeness": 0.35,
    "review_signals": 0.20,
    "nap_consistency": 0.15,
    "on_page_seo": 0.15,
    "citation_coverage": 0.10,
    "local_content": 0.05,
}

# ---------------------------------------------------------------------------
# GBP checklist items with individual weights
# ---------------------------------------------------------------------------
GBP_CHECKLIST_ITEMS: list[dict[str, Any]] = [
    {"id": "business_name", "label": "Business name matches signage", "weight": 3},
    {"id": "primary_category", "label": "Primary category selected", "weight": 3},
    {"id": "secondary_categories", "label": "Secondary categories added", "weight": 2},
    {"id": "address_verified", "label": "Address verified", "weight": 3},
    {"id": "phone_number", "label": "Phone number listed", "weight": 3},
    {"id": "website_url", "label": "Website URL set", "weight": 3},
    {"id": "business_hours", "label": "Business hours configured", "weight": 3},
    {"id": "special_hours", "label": "Special/holiday hours set", "weight": 2},
    {"id": "description_written", "label": "Description written (750 chars)", "weight": 3},
    {"id": "description_keywords", "label": "Description includes keywords", "weight": 2},
    {"id": "description_location", "label": "Description mentions location", "weight": 2},
    {"id": "logo_uploaded", "label": "Logo uploaded", "weight": 3},
    {"id": "cover_photo", "label": "Cover photo set", "weight": 3},
    {"id": "interior_photos", "label": "Interior photos (3+)", "weight": 2},
    {"id": "exterior_photos", "label": "Exterior photos (2+)", "weight": 2},
    {"id": "team_photos", "label": "Team/staff photos (2+)", "weight": 2},
    {"id": "product_photos", "label": "Product/service photos (5+)", "weight": 2},
    {"id": "photos_recent", "label": "Photos updated in last 30 days", "weight": 2},
    {"id": "services_listed", "label": "Services listed with descriptions", "weight": 3},
    {"id": "products_added", "label": "Products or menu added", "weight": 2},
    {"id": "attributes_set", "label": "Business attributes configured", "weight": 2},
    {"id": "highlights_selected", "label": "Highlights selected", "weight": 1},
    {"id": "posts_regular", "label": "Google Posts published regularly", "weight": 3},
    {"id": "posts_with_images", "label": "Posts include images", "weight": 2},
    {"id": "posts_with_cta", "label": "Posts include CTAs", "weight": 2},
    {"id": "review_count_target", "label": "Review count meets industry target", "weight": 3},
    {"id": "average_rating", "label": "Average rating 4.0+", "weight": 3},
    {"id": "review_response_rate", "label": "Owner responds to 90%+ reviews", "weight": 3},
    {"id": "negative_review_responses", "label": "All negative reviews addressed", "weight": 3},
    {"id": "qa_prepopulated", "label": "Q&A pre-populated with common questions", "weight": 2},
    {"id": "qa_monitored", "label": "Q&A monitored and answered", "weight": 2},
]


def score_gbp_completeness(checklist_responses: dict[str, int]) -> dict[str, Any]:
    """Score GBP profile completeness based on checklist responses.

    Args:
        checklist_responses: Mapping of checklist item ID to score.
            Values: 0 = missing, 1 = partial, 2 = complete.

    Returns:
        Dictionary with score (0-100), completed items, and missing items.
    """
    total_weighted = 0
    earned_weighted = 0
    completed: list[str] = []
    partial: list[str] = []
    missing: list[str] = []

    for item in GBP_CHECKLIST_ITEMS:
        item_id = item["id"]
        weight = item["weight"]
        value = checklist_responses.get(item_id, 0)

        total_weighted += weight * 2  # max score per item is 2
        earned_weighted += weight * min(value, 2)

        if value == 2:
            completed.append(item["label"])
        elif value == 1:
            partial.append(item["label"])
        else:
            missing.append(item["label"])

    score = round((earned_weighted / total_weighted) * 100) if total_weighted > 0 else 0

    return {
        "score": score,
        "completed_count": len(completed),
        "partial_count": len(partial),
        "missing_count": len(missing),
        "completed": completed,
        "partial": partial,
        "missing": missing,
        "total_items": len(GBP_CHECKLIST_ITEMS),
    }


def score_review_signals(
    review_count: int,
    average_rating: float,
    response_rate: float,
    recent_reviews_30d: int = 0,
    industry_target: int = 30,
) -> dict[str, Any]:
    """Score review signals.

    Args:
        review_count: Total number of Google reviews.
        average_rating: Average star rating (1.0-5.0).
        response_rate: Percentage of reviews with owner response (0-100).
        recent_reviews_30d: Number of reviews received in the last 30 days.
        industry_target: Target review count for the industry.

    Returns:
        Dictionary with score (0-100) and sub-scores.
    """
    count_score = min(100, (review_count / max(industry_target, 1)) * 100)
    rating_score = max(0, (average_rating - 1) / 4 * 100)
    response_score = min(100, response_rate)
    velocity_score = min(100, (recent_reviews_30d / max(industry_target * 0.1, 1)) * 100)

    weighted = (count_score * 0.3) + (rating_score * 0.3) + (response_score * 0.25) + (velocity_score * 0.15)
    score = round(min(100, weighted))

    return {
        "score": score,
        "count_score": round(count_score),
        "rating_score": round(rating_score),
        "response_score": round(response_score),
        "velocity_score": round(velocity_score),
    }


def score_nap_consistency(
    total_citations: int,
    consistent_citations: int,
    has_duplicates: bool = False,
) -> dict[str, Any]:
    """Score NAP consistency across citations.

    Args:
        total_citations: Total number of known citation listings.
        consistent_citations: Number of citations with correct NAP data.
        has_duplicates: Whether duplicate listings are known to exist.

    Returns:
        Dictionary with score (0-100) and details.
    """
    if total_citations == 0:
        return {"score": 0, "consistency_pct": 0, "has_duplicates": has_duplicates}

    consistency_pct = (consistent_citations / total_citations) * 100
    score = round(consistency_pct)

    if has_duplicates:
        score = max(0, score - 15)

    return {
        "score": score,
        "consistency_pct": round(consistency_pct),
        "consistent_count": consistent_citations,
        "total_count": total_citations,
        "has_duplicates": has_duplicates,
    }


def score_on_page_seo(
    has_nap_on_site: bool = False,
    has_location_pages: bool = False,
    has_local_schema: bool = False,
    has_local_keywords_titles: bool = False,
    is_mobile_friendly: bool = False,
    page_speed_score: int = 50,
) -> dict[str, Any]:
    """Score on-page local SEO factors.

    Args:
        has_nap_on_site: NAP present on website (footer recommended).
        has_location_pages: Dedicated location/service area pages exist.
        has_local_schema: LocalBusiness schema markup implemented.
        has_local_keywords_titles: Local keywords in title tags.
        is_mobile_friendly: Website is mobile-responsive.
        page_speed_score: Google PageSpeed score (0-100).

    Returns:
        Dictionary with score (0-100) and details.
    """
    points = 0
    max_points = 100
    details: dict[str, bool | int] = {}

    checks = [
        ("nap_on_site", has_nap_on_site, 20),
        ("location_pages", has_location_pages, 20),
        ("local_schema", has_local_schema, 20),
        ("local_keywords_titles", has_local_keywords_titles, 15),
        ("mobile_friendly", is_mobile_friendly, 15),
    ]

    for name, value, weight in checks:
        if value:
            points += weight
        details[name] = value

    speed_points = (min(100, max(0, page_speed_score)) / 100) * 10
    points += speed_points
    details["page_speed_score"] = page_speed_score

    score = round(min(100, (points / max_points) * 100))
    return {"score": score, "details": details}


def score_citation_coverage(
    tier1_claimed: int,
    tier2_claimed: int,
    tier3_claimed: int,
    aggregators_submitted: int,
    tier1_total: int = 5,
    tier2_total: int = 10,
    tier3_total: int = 10,
    aggregators_total: int = 4,
) -> dict[str, Any]:
    """Score citation coverage across tiers.

    Args:
        tier1_claimed: Number of Tier 1 citations claimed.
        tier2_claimed: Number of Tier 2 citations claimed.
        tier3_claimed: Number of Tier 3 (industry-specific) citations claimed.
        aggregators_submitted: Number of data aggregators submitted to.
        tier1_total: Total Tier 1 sources.
        tier2_total: Total Tier 2 sources.
        tier3_total: Total relevant Tier 3 sources.
        aggregators_total: Total data aggregators.

    Returns:
        Dictionary with score (0-100) and tier breakdown.
    """
    tier1_pct = (tier1_claimed / max(tier1_total, 1)) * 100
    tier2_pct = (tier2_claimed / max(tier2_total, 1)) * 100
    tier3_pct = (tier3_claimed / max(tier3_total, 1)) * 100
    agg_pct = (aggregators_submitted / max(aggregators_total, 1)) * 100

    weighted = (tier1_pct * 0.40) + (tier2_pct * 0.25) + (tier3_pct * 0.15) + (agg_pct * 0.20)
    score = round(min(100, weighted))

    return {
        "score": score,
        "tier1": {"claimed": tier1_claimed, "total": tier1_total, "pct": round(tier1_pct)},
        "tier2": {"claimed": tier2_claimed, "total": tier2_total, "pct": round(tier2_pct)},
        "tier3": {"claimed": tier3_claimed, "total": tier3_total, "pct": round(tier3_pct)},
        "aggregators": {"submitted": aggregators_submitted, "total": aggregators_total, "pct": round(agg_pct)},
    }


def score_local_content(
    has_google_posts_weekly: bool = False,
    has_local_blog_content: bool = False,
    has_local_landing_pages: bool = False,
    has_faq_content: bool = False,
    has_event_posts: bool = False,
) -> dict[str, Any]:
    """Score local content efforts.

    Args:
        has_google_posts_weekly: Publishing Google Posts at least weekly.
        has_local_blog_content: Blog posts with local relevance.
        has_local_landing_pages: City or neighborhood-specific landing pages.
        has_faq_content: FAQ content addressing local questions.
        has_event_posts: Event-type Google Posts for upcoming events.

    Returns:
        Dictionary with score (0-100) and details.
    """
    points = 0
    checks = [
        ("google_posts_weekly", has_google_posts_weekly, 30),
        ("local_blog_content", has_local_blog_content, 25),
        ("local_landing_pages", has_local_landing_pages, 25),
        ("faq_content", has_faq_content, 10),
        ("event_posts", has_event_posts, 10),
    ]

    details: dict[str, bool] = {}
    for name, value, weight in checks:
        if value:
            points += weight
        details[name] = value

    return {"score": points, "details": details}


def generate_recommendations(
    gbp_result: dict[str, Any],
    review_result: dict[str, Any],
    nap_result: dict[str, Any],
    on_page_result: dict[str, Any],
    citation_result: dict[str, Any],
    content_result: dict[str, Any],
) -> list[dict[str, str]]:
    """Generate prioritized recommendations based on scoring results.

    Args:
        gbp_result: Output from score_gbp_completeness.
        review_result: Output from score_review_signals.
        nap_result: Output from score_nap_consistency.
        on_page_result: Output from score_on_page_seo.
        citation_result: Output from score_citation_coverage.
        content_result: Output from score_local_content.

    Returns:
        List of recommendation dicts sorted by priority (quick wins first).
        Each dict has keys: priority, category, action, impact.
    """
    recs: list[dict[str, str]] = []

    # GBP recommendations
    if gbp_result["missing_count"] > 0:
        for item in gbp_result["missing"][:5]:
            recs.append({
                "priority": "high",
                "category": "GBP Completeness",
                "action": f"Add missing: {item}",
                "impact": "Directly improves GBP completeness (35% of score)",
            })

    if gbp_result["partial_count"] > 0:
        for item in gbp_result["partial"][:3]:
            recs.append({
                "priority": "medium",
                "category": "GBP Completeness",
                "action": f"Improve: {item}",
                "impact": "Completing partial items boosts profile score",
            })

    # Review recommendations
    if review_result["response_score"] < 80:
        recs.append({
            "priority": "high",
            "category": "Reviews",
            "action": "Respond to all unanswered reviews within 48 hours",
            "impact": "Review response rate is a key ranking and trust signal",
        })

    if review_result["count_score"] < 60:
        recs.append({
            "priority": "high",
            "category": "Reviews",
            "action": "Implement a review generation process (ask after positive experiences)",
            "impact": "More reviews improve rankings and conversion rates",
        })

    if review_result["rating_score"] < 75:
        recs.append({
            "priority": "medium",
            "category": "Reviews",
            "action": "Address common complaints to improve average rating",
            "impact": "Higher ratings improve click-through rate from search results",
        })

    # NAP recommendations
    if nap_result["score"] < 80:
        recs.append({
            "priority": "high",
            "category": "NAP Consistency",
            "action": "Audit and fix NAP inconsistencies across all citations",
            "impact": "Consistent NAP data is foundational for local rankings",
        })

    if nap_result.get("has_duplicates"):
        recs.append({
            "priority": "high",
            "category": "NAP Consistency",
            "action": "Find and merge or remove duplicate listings",
            "impact": "Duplicates confuse search engines and split ranking signals",
        })

    # On-page recommendations
    details = on_page_result.get("details", {})
    if not details.get("nap_on_site"):
        recs.append({
            "priority": "high",
            "category": "On-Page SEO",
            "action": "Add consistent NAP data to your website footer",
            "impact": "Reinforces location signals for search engines",
        })

    if not details.get("local_schema"):
        recs.append({
            "priority": "high",
            "category": "On-Page SEO",
            "action": "Implement LocalBusiness schema markup on your website",
            "impact": "Helps search engines understand your business details",
        })

    if not details.get("location_pages"):
        recs.append({
            "priority": "medium",
            "category": "On-Page SEO",
            "action": "Create dedicated location pages for each service area",
            "impact": "Location pages target city-specific searches",
        })

    if not details.get("mobile_friendly"):
        recs.append({
            "priority": "high",
            "category": "On-Page SEO",
            "action": "Make your website mobile-responsive",
            "impact": "Most local searches happen on mobile devices",
        })

    # Citation recommendations
    if citation_result["tier1"]["pct"] < 100:
        recs.append({
            "priority": "high",
            "category": "Citations",
            "action": "Claim all Tier 1 citations (Google, Apple Maps, Bing, Yelp, Facebook)",
            "impact": "Essential citations that all businesses should have",
        })

    if citation_result["aggregators"]["pct"] < 75:
        recs.append({
            "priority": "medium",
            "category": "Citations",
            "action": "Submit to data aggregators (Neustar, Factual, Data Axle, Acxiom)",
            "impact": "Aggregators distribute data to hundreds of smaller directories",
        })

    # Content recommendations
    content_details = content_result.get("details", {})
    if not content_details.get("google_posts_weekly"):
        recs.append({
            "priority": "medium",
            "category": "Local Content",
            "action": "Start publishing Google Posts at least once per week",
            "impact": "Active posting signals an engaged business to Google",
        })

    if not content_details.get("local_blog_content"):
        recs.append({
            "priority": "low",
            "category": "Local Content",
            "action": "Create blog content with local relevance (events, guides, news)",
            "impact": "Local content supports organic rankings and link building",
        })

    # Sort: high first, then medium, then low
    priority_order = {"high": 0, "medium": 1, "low": 2}
    recs.sort(key=lambda r: priority_order.get(r["priority"], 3))

    return recs


def run_full_audit(
    business_info: dict[str, Any],
    gbp_responses: dict[str, int],
    review_data: dict[str, Any],
    nap_data: dict[str, Any],
    on_page_data: dict[str, Any],
    citation_data: dict[str, Any],
    content_data: dict[str, Any],
) -> dict[str, Any]:
    """Run a full local SEO audit and return combined results.

    Args:
        business_info: Basic business details (name, address, etc.).
        gbp_responses: GBP checklist responses (item_id -> 0/1/2).
        review_data: Keyword args for score_review_signals.
        nap_data: Keyword args for score_nap_consistency.
        on_page_data: Keyword args for score_on_page_seo.
        citation_data: Keyword args for score_citation_coverage.
        content_data: Keyword args for score_local_content.

    Returns:
        Full audit results with overall score, category breakdown,
        and prioritized recommendations.
    """
    gbp_result = score_gbp_completeness(gbp_responses)
    review_result = score_review_signals(**review_data)
    nap_result = score_nap_consistency(**nap_data)
    on_page_result = score_on_page_seo(**on_page_data)
    citation_result = score_citation_coverage(**citation_data)
    content_result = score_local_content(**content_data)

    # Calculate overall weighted score
    category_scores = {
        "gbp_completeness": gbp_result["score"],
        "review_signals": review_result["score"],
        "nap_consistency": nap_result["score"],
        "on_page_seo": on_page_result["score"],
        "citation_coverage": citation_result["score"],
        "local_content": content_result["score"],
    }

    overall_score = round(
        sum(
            category_scores[cat] * weight
            for cat, weight in CATEGORY_WEIGHTS.items()
        )
    )

    recommendations = generate_recommendations(
        gbp_result, review_result, nap_result,
        on_page_result, citation_result, content_result,
    )

    # Score label
    if overall_score >= 90:
        label = "Excellent"
    elif overall_score >= 70:
        label = "Good"
    elif overall_score >= 50:
        label = "Fair"
    elif overall_score >= 30:
        label = "Needs Improvement"
    else:
        label = "Critical"

    return {
        "business_name": business_info.get("name", "Unknown"),
        "overall_score": overall_score,
        "score_label": label,
        "category_scores": category_scores,
        "category_details": {
            "gbp_completeness": gbp_result,
            "review_signals": review_result,
            "nap_consistency": nap_result,
            "on_page_seo": on_page_result,
            "citation_coverage": citation_result,
            "local_content": content_result,
        },
        "recommendations": recommendations,
        "recommendations_count": len(recommendations),
    }


# ---------------------------------------------------------------------------
# Standalone demo
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("=" * 60)
    print("Local SEO Scorer - Demo Audit")
    print("=" * 60)

    # Sample business
    business = {"name": "Joe's Pizza Brooklyn", "address": "123 Main St, Brooklyn, NY 11201"}

    # Sample GBP responses (0=missing, 1=partial, 2=complete)
    gbp = {
        "business_name": 2, "primary_category": 2, "secondary_categories": 1,
        "address_verified": 2, "phone_number": 2, "website_url": 2,
        "business_hours": 2, "special_hours": 0, "description_written": 1,
        "description_keywords": 0, "description_location": 0,
        "logo_uploaded": 2, "cover_photo": 2, "interior_photos": 1,
        "exterior_photos": 1, "team_photos": 0, "product_photos": 1,
        "photos_recent": 0, "services_listed": 1, "products_added": 0,
        "attributes_set": 1, "highlights_selected": 0,
        "posts_regular": 0, "posts_with_images": 0, "posts_with_cta": 0,
        "review_count_target": 2, "average_rating": 2,
        "review_response_rate": 1, "negative_review_responses": 1,
        "qa_prepopulated": 0, "qa_monitored": 0,
    }

    results = run_full_audit(
        business_info=business,
        gbp_responses=gbp,
        review_data={
            "review_count": 85,
            "average_rating": 4.3,
            "response_rate": 45.0,
            "recent_reviews_30d": 4,
            "industry_target": 100,
        },
        nap_data={
            "total_citations": 20,
            "consistent_citations": 12,
            "has_duplicates": True,
        },
        on_page_data={
            "has_nap_on_site": True,
            "has_location_pages": False,
            "has_local_schema": False,
            "has_local_keywords_titles": True,
            "is_mobile_friendly": True,
            "page_speed_score": 65,
        },
        citation_data={
            "tier1_claimed": 4,
            "tier2_claimed": 3,
            "tier3_claimed": 2,
            "aggregators_submitted": 0,
        },
        content_data={
            "has_google_posts_weekly": False,
            "has_local_blog_content": False,
            "has_local_landing_pages": False,
            "has_faq_content": False,
            "has_event_posts": False,
        },
    )

    print(f"\nBusiness: {results['business_name']}")
    print(f"Overall Score: {results['overall_score']}/100 ({results['score_label']})")
    print("\nCategory Breakdown:")
    for category, score in results["category_scores"].items():
        weight = CATEGORY_WEIGHTS[category]
        print(f"  {category:25s} {score:3d}/100 (weight: {weight:.0%})")

    print(f"\nTop Recommendations ({results['recommendations_count']} total):")
    for i, rec in enumerate(results["recommendations"][:10], 1):
        print(f"  {i}. [{rec['priority'].upper()}] {rec['category']}: {rec['action']}")
