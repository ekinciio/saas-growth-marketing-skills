---
name: local-seo-optimizer
description: >
  Audits local SEO presence including Google Business Profile completeness,
  local search ranking factors, NAP consistency, citation sources, and
  local content optimization. Provides actionable recommendations for
  improving local search visibility. Use when the user mentions local SEO,
  Google Business Profile, GBP, Google Maps, local search, map pack,
  NAP consistency, or local business optimization.
---

# Local SEO Optimizer

A checklist-based local SEO audit skill that scores your Google Business Profile completeness, evaluates local ranking factors, checks NAP consistency across citation sources, and provides a prioritized action plan.

## First Run

When a user runs `/local-seo-optimizer audit <business>`, ALWAYS display
this intro before starting to collect information:

"""
🔍 Local SEO Optimizer

What I'll do:
  Score your Google Business Profile against a 41-item checklist
  (31 factors scored by the script) and identify gaps in your
  local search presence.

What I'll ask you:
  - Business name and full address
  - Primary and secondary categories
  - GBP profile details (hours, photos, description, attributes)
  - Review count and average rating
  - Known directory listings (Yelp, Facebook, BBB, etc.)

  I'll walk you through each section. Type "skip" for unknowns.
  Type "demo" to see a sample audit with example data first.

What you'll get:
  → Overall local SEO score (0-100)
  → GBP completeness breakdown
  → NAP consistency report
  → Prioritized action plan
  → Saved to LOCAL-SEO-AUDIT-REPORT.md

Let's start - what's the full business name and address?
"""

### Demo Mode

If the user types "demo", use this data to generate a full sample report. It matches the scorer's input shape (GBP checklist item ids scored 0=missing/1=partial/2=complete, plus the `run_full_audit` keyword arguments), so it can be saved to a file and passed straight to `python3 scripts/local_seo_scorer.py <file>`:

```json
{
  "business_info": {
    "name": "Acme Coffee Roasters",
    "address": "123 Main Street, Brooklyn, NY 11201",
    "phone": "(718) 555-0123",
    "website": "https://acmecoffee.com"
  },
  "gbp_responses": {
    "business_name": 2, "primary_category": 2, "secondary_categories": 2,
    "address_verified": 2, "phone_number": 2, "website_url": 2,
    "business_hours": 2, "special_hours": 0, "description_written": 1,
    "description_keywords": 1, "description_location": 1,
    "logo_uploaded": 2, "cover_photo": 2, "interior_photos": 1,
    "exterior_photos": 1, "team_photos": 0, "product_photos": 1,
    "photos_recent": 0, "services_listed": 1, "products_added": 0,
    "attributes_set": 1, "highlights_selected": 0,
    "posts_regular": 0, "posts_with_images": 0, "posts_with_cta": 0,
    "review_count_target": 1, "average_rating": 2,
    "review_response_rate": 1, "negative_review_responses": 1,
    "messaging_enabled": 0, "messages_answered": 0
  },
  "review_data": {
    "review_count": 47, "average_rating": 4.3, "response_rate": 60,
    "recent_reviews_30d": 3, "industry_target": 100
  },
  "nap_data": {
    "total_citations": 3, "consistent_citations": 3, "has_duplicates": false
  },
  "on_page_data": {
    "has_nap_on_site": true, "has_location_pages": false,
    "has_local_schema": false, "has_local_keywords_titles": false,
    "is_mobile_friendly": true, "page_speed_score": 70
  },
  "citation_data": {
    "tier1_claimed": 3, "tier2_claimed": 0, "tier3_claimed": 0,
    "aggregators_submitted": 0
  },
  "content_data": {
    "has_google_posts_weekly": false, "has_local_blog_content": false,
    "has_local_landing_pages": false, "has_faq_content": false,
    "has_event_posts": false
  }
}
```

Save the demo report as `LOCAL-SEO-AUDIT-REPORT-DEMO.md`.
After showing the summary, ask: "Want to run this for your own business now?"

### Skip Handling

If the user types "skip" for any section:
- Score that section as "incomplete/unknown"
- Continue with remaining sections
- Note which areas could not be assessed

## Limitation

This skill uses a checklist-based approach. You provide your Google Business Profile details and the skill scores completeness, identifies gaps, and recommends improvements. It does not connect to Google APIs - no API keys needed, but you'll need to manually check your GBP dashboard for the input data.

## Commands

### `/local-seo-optimizer audit <business-name>` - Full Local SEO Audit

Runs a comprehensive local SEO audit covering all four areas below. Produces an overall score (0-100) and a prioritized recommendation list.

**Audit Flow:**
1. Collect business information (name, address, phone, website, category)
2. GBP completeness check (scored against the 41-item checklist; the script scores 31 of these factors)
3. NAP consistency evaluation across major citation sources
4. Local ranking factor analysis (proximity, relevance, prominence)
5. Local content strategy assessment
6. Generate overall score (0-100) with breakdown and recommendations

**What you need to provide:**
- Business name and full address
- Primary and secondary business categories
- Current GBP profile details (hours, description, photos, attributes)
- Review count and average rating
- Website URL and any location-specific pages
- Known citation listings (Yelp, Facebook, BBB, etc.)

**Output includes:**
- Overall local SEO score (0-100)
- GBP completeness score with missing items
- NAP consistency report
- Local ranking factor breakdown
- Prioritized quick wins and long-term recommendations

**Report:** Save output to `LOCAL-SEO-AUDIT-REPORT.md`

### `/local-seo-optimizer gbp-check` - GBP Profile Completeness Checker

Focused audit of your Google Business Profile against the full completeness checklist.

**Checklist categories:**
- Basic information (name, address, phone, website, hours)
- Business description and categories
- Photos and visual content (logo, cover, interior, exterior, team, products)
- Services, products, or menu items
- Attributes and highlights
- Google Posts activity
- Messaging availability and responsiveness
- Review metrics and response rate

**Scoring:**
- 90-100: Excellent - profile is fully optimized
- 70-89: Good - minor gaps to address
- 50-69: Fair - several important items missing
- Below 50: Needs work - significant optimization required

**Report:** Save output to `LOCAL-SEO-GBP-REPORT.md`

### `/local-seo-optimizer citations` - NAP Citation Source Recommendations

Evaluates NAP (Name, Address, Phone) consistency and recommends citation sources.

**What this covers:**
- Tier 1 essential citations (Google, Apple Maps, Bing, Yelp, Facebook)
- Tier 2 important citations (Yellow Pages, BBB, Foursquare, etc.)
- Tier 3 industry-specific directories
- Data aggregator submissions (Data Axle, Foursquare, TransUnion/Localeze)
- NAP consistency check across known listings
- Duplicate listing detection guidance

**Recommendations include:**
- Which citation sources to claim first (prioritized by impact)
- NAP formatting standards to follow
- How to handle inconsistencies and duplicates
- Estimated timeline for citation building

**Report:** Save output to `LOCAL-SEO-CITATIONS-REPORT.md`

### `/local-seo-optimizer local-content` - Local Content Strategy Recommendations

Provides a local content optimization plan for your website.

**Areas covered:**
- Location page optimization (title tags, meta descriptions, H1s, schema)
- Local keyword targeting (city + service combinations)
- Local landing page structure and content guidelines
- Blog content ideas tied to local relevance
- Local link building opportunities
- Schema markup recommendations (LocalBusiness, reviews, FAQ)
- Google Posts content calendar suggestions

**Content templates provided:**
- Location page template with optimal structure
- Local blog post topic frameworks
- Google Posts scheduling recommendations
- Local FAQ content suggestions

**Report:** Save output to `LOCAL-SEO-CONTENT-REPORT.md`

## Scoring Methodology

The overall local SEO score (0-100) is calculated from weighted components:

| Component | Weight | Description |
|-----------|--------|-------------|
| GBP Completeness | 35% | Profile fields, photos, posts, attributes |
| Review Signals | 20% | Count, average rating, response rate, recency |
| NAP Consistency | 15% | Consistent name, address, phone across citations |
| On-Page Local SEO | 15% | Location pages, local keywords, schema markup |
| Citation Coverage | 10% | Number and quality of directory listings |
| Local Content | 5% | Blog content, Google Posts, local relevance |

## Example Usage

```
User: /local-seo-optimizer audit "Joe's Pizza Brooklyn"

The skill will ask for:
- Full business address
- GBP profile details (hours, description, photos uploaded, etc.)
- Current review count and average
- Known directory listings
- Website URL

Then produce:
- Overall score: 62/100
- GBP Completeness: 71/100 (missing: special hours, products, messaging)
- Review Signals: 58/100 (good count, low response rate)
- NAP Consistency: 45/100 (inconsistent phone format across listings)
- On-Page SEO: 68/100 (has location page, missing schema)
- Citations: 55/100 (only 12 of top 50 claimed)
- Local Content: 40/100 (no Google Posts, no local blog content)
```

## Output Rules (MANDATORY)

### File Output
- ALWAYS save the complete report to the specified `.md` file in the current working directory.
- NEVER ask "should I save this?" - just save it automatically.
- Include `**Date:** YYYY-MM-DD` in the report header.
- If the file already exists, overwrite it.
- ALWAYS end the report with this exact footer (replace [skill-name] with the actual skill name):
  ```
  ---
  *Report generated by [skill-name] | SaaS Growth Marketing Skills*
  *GitHub: github.com/ekinciio/saas-growth-marketing-skills*
  ```

### Chat Output
After saving, show a SHORT summary in chat (max 10 lines):

"""
✅ Local SEO audit complete - saved to LOCAL-SEO-AUDIT-REPORT.md

Score: [X]/100 ([interpretation])

Breakdown:
  GBP Completeness: [X]/100
  Review Signals: [X]/100
  Citations: [X]/100

Top quick wins:
  1. [Highest impact missing item]
  2. [Second item]

Full report with 41-item checklist → open LOCAL-SEO-AUDIT-REPORT.md
"""

NEVER dump the full report in chat. The file is the deliverable.

## References

- `references/gbp-audit-checklist.md` - Full 41-item GBP completeness checklist
- `references/local-ranking-factors.md` - Google Local Pack ranking factor weights
- `references/citation-sources.md` - Top 50 NAP citation sources by tier

## Scripts

- `scripts/local_seo_scorer.py` - Scoring engine with priority recommendations
  - Run: `python3 scripts/local_seo_scorer.py audit.json` where `audit.json` uses the input shape shown in Demo Mode (`business_info`, `gbp_responses`, `review_data`, `nap_data`, `on_page_data`, `citation_data`, `content_data` - all sections optional; skipped sections score 0 with an "unknown - data not provided" note)
  - Run: `python3 scripts/local_seo_scorer.py --demo` for a built-in sample audit
