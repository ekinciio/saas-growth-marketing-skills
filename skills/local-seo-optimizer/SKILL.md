---
name: local-seo-optimizer
description: >
  Audit local SEO presence including Google Business Profile completeness,
  local search ranking factors, NAP consistency, citation sources, and
  local content optimization. Provides actionable recommendations for
  improving local search visibility. Use when the user mentions local SEO,
  Google Business Profile, GBP, Google Maps, local search, map pack,
  NAP consistency, or local business optimization.
---

# Local SEO Optimizer

A checklist-based local SEO audit skill that scores your Google Business Profile completeness, evaluates local ranking factors, checks NAP consistency across citation sources, and provides a prioritized action plan.

## Limitation

This skill uses a checklist-based approach. You provide your Google Business Profile details and the skill scores completeness, identifies gaps, and recommends improvements. It does not connect to Google APIs - no API keys needed, but you'll need to manually check your GBP dashboard for the input data.

## Commands

### `/local-seo-optimizer audit <business-name>` - Full Local SEO Audit

Runs a comprehensive local SEO audit covering all four areas below. Produces an overall score (0-100) and a prioritized recommendation list.

**Audit Flow:**
1. Collect business information (name, address, phone, website, category)
2. GBP completeness check (scored against 30+ item checklist)
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

### `/local-seo-optimizer gbp-check` - GBP Profile Completeness Checker

Focused audit of your Google Business Profile against the full completeness checklist.

**Checklist categories:**
- Basic information (name, address, phone, website, hours)
- Business description and categories
- Photos and visual content (logo, cover, interior, exterior, team, products)
- Services, products, or menu items
- Attributes and highlights
- Google Posts activity
- Q&A section management
- Review metrics and response rate

**Scoring:**
- 90-100: Excellent - profile is fully optimized
- 70-89: Good - minor gaps to address
- 50-69: Fair - several important items missing
- Below 50: Needs work - significant optimization required

### `/local-seo-optimizer citations` - NAP Citation Source Recommendations

Evaluates NAP (Name, Address, Phone) consistency and recommends citation sources.

**What this covers:**
- Tier 1 essential citations (Google, Apple Maps, Bing, Yelp, Facebook)
- Tier 2 important citations (Yellow Pages, BBB, Foursquare, etc.)
- Tier 3 industry-specific directories
- Data aggregator submissions (Neustar, Factual, Infogroup, Acxiom)
- NAP consistency check across known listings
- Duplicate listing detection guidance

**Recommendations include:**
- Which citation sources to claim first (prioritized by impact)
- NAP formatting standards to follow
- How to handle inconsistencies and duplicates
- Estimated timeline for citation building

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
- GBP Completeness: 71/100 (missing: special hours, products, Q&A)
- Review Signals: 58/100 (good count, low response rate)
- NAP Consistency: 45/100 (inconsistent phone format across listings)
- On-Page SEO: 68/100 (has location page, missing schema)
- Citations: 55/100 (only 12 of top 50 claimed)
- Local Content: 40/100 (no Google Posts, no local blog content)
```

## References

- `references/gbp-audit-checklist.md` - Full 30+ item GBP completeness checklist
- `references/local-ranking-factors.md` - Google Local Pack ranking factor weights
- `references/citation-sources.md` - Top 50 NAP citation sources by tier

## Scripts

- `scripts/local_seo_scorer.py` - Scoring engine with priority recommendations
