---
name: aso-optimizer
description: >
  App Store Optimization toolkit for iOS and Android apps. Fetches live app
  metadata from the iTunes Search API, validates character limits, scores
  metadata quality against best practices, and compares with competitor apps.
  Use when the user mentions ASO, app store optimization, app metadata,
  app title optimization, or app store listing improvement.
---

# ASO Optimizer Skill

App Store Optimization toolkit that helps improve app visibility and conversion
rates on the Apple App Store and Google Play Store.

## Commands

### `/aso-optimizer analyze <app-name>`

Fetch live app metadata from the iTunes Search API and score it against ASO
best practices.

**Example:**
```
/aso-optimizer analyze "Slack"
```

### `/aso-optimizer validate`

Validate metadata fields against platform-specific character limits for iOS,
Android, or both.

**Report:** Save output to `ASO-VALIDATION-REPORT.md`

**Example:**
```
/aso-optimizer validate
```

### `/aso-optimizer compare <app1> <app2>`

Side-by-side metadata comparison between two apps. Highlights strengths and
weaknesses of each listing.

**Report:** Save output to `ASO-COMPARE-REPORT.md`

**Example:**
```
/aso-optimizer compare "Slack" "Microsoft Teams"
```

### `/aso-optimizer score`

Calculate a detailed ASO health score (0-100) with a breakdown across four
weighted categories.

**Report:** Save output to `ASO-SCORE-REPORT.md`

**Example:**
```
/aso-optimizer score
```

### `/aso-optimizer optimize`

Generate improved metadata suggestions based on the current listing analysis
and competitor benchmarks.

**Report:** Save output to `ASO-OPTIMIZE-REPORT.md`

**Example:**
```
/aso-optimizer optimize
```

## Full Analyze Flow

When running the `analyze` command, the skill follows this sequence:

1. **Fetch live data** - Query the iTunes Search API for the target app
   (`https://itunes.apple.com/search?term={app_name}&entity=software&country=us&limit=1`)
2. **Evaluate metadata** - Compare metadata against best practices including
   title keyword placement, description structure, ratings health, and
   screenshot count
3. **Fetch competitors** - Pull the top 5 competitor apps in the same primary
   category for benchmarking
4. **Calculate ASO health score** - Generate a weighted score from 0 to 100
5. **Generate recommendations** - Produce prioritized, actionable suggestions
   for improving the listing

**Report:** Save output to `ASO-REPORT.md`
6. **Generate report** - Save the complete analysis to `ASO-REPORT.md` in the
   current working directory

## Report Output

Every command MUST save its output as a markdown report file:

| Command | Output File |
|---------|-------------|
| `analyze` | `ASO-REPORT.md` |
| `validate` | `ASO-VALIDATION-REPORT.md` |
| `compare` | `ASO-COMPARE-REPORT.md` |
| `score` | `ASO-SCORE-REPORT.md` |
| `optimize` | `ASO-OPTIMIZE-REPORT.md` |

The report file should include:
- Date of analysis
- App name and store URL
- Full analysis results with scores and breakdowns
- Prioritized recommendations
- Competitor comparison data (when available)

Always inform the user where the report was saved after completion.

## ASO Health Score Breakdown

The health score is calculated across four weighted categories:

| Category | Weight | What It Measures |
|----------|--------|------------------|
| Title Optimization | 30% | Keyword presence, character length usage, brand-keyword balance |
| Description Quality | 25% | Length (ideal 2000-4000 chars), structural formatting, keyword density, call-to-action presence |
| Ratings Health | 25% | Average rating (4.0+ good, 4.5+ great), total rating count, recent review sentiment |
| Metadata Completeness | 20% | All fields populated, subtitle utilized, keyword field maximized, screenshots present |

### Score Ranges

- **90-100**: Excellent - App listing is highly optimized
- **70-89**: Good - Minor improvements possible
- **50-69**: Needs Work - Several optimization opportunities exist
- **30-49**: Poor - Significant gaps in metadata strategy
- **0-29**: Critical - Listing needs a complete overhaul

## Metadata Best Practices

### Title (30 characters max)
- Place the highest-value keyword after the brand name
- Use the full 30 characters when possible
- Format: `Brand - Primary Keyword` or `Brand: Primary Keyword`

### Subtitle (iOS only, 30 characters)
- Include secondary keywords not in the title
- Describe the core value proposition
- Avoid repeating title keywords

### Keywords Field (iOS only, 100 characters)
- Use commas to separate terms, no spaces after commas
- Never repeat words already in the title or subtitle
- Prioritize single words over phrases (the system combines them)
- Use all 100 characters

### Description (4,000 characters max)
- Front-load the first 3 lines (visible before "Read More")
- Use line breaks and bullet points for readability
- Include keywords naturally - not stuffed
- End with a clear call-to-action

### Ratings and Reviews
- Aim for 4.0+ average rating
- Higher rating counts build trust
- Respond to negative reviews promptly
- Use in-app review prompts strategically

## Platform Character Limits Reference

| Field | Apple App Store | Google Play Store |
|-------|----------------|-------------------|
| App Name/Title | 30 chars | 30 chars |
| Subtitle | 30 chars | N/A |
| Short Description | N/A | 80 chars |
| Keywords Field | 100 chars | N/A |
| Promotional Text | 170 chars | N/A |
| Full Description | 4,000 chars | 4,000 chars |
| What's New | 4,000 chars | 500 chars |
| Developer Name | 50 chars | varies |

## Scripts

### `scripts/metadata_validator.py`

Validates metadata fields against platform character limits. Accepts a metadata
dictionary and platform target (ios, android, or both). Returns pass/fail
status and remaining character counts per field.

### `scripts/aso_scorer.py`

Fetches app data from the iTunes Search API and calculates an ASO health score.
Accepts an app name string or a pre-built metadata dictionary. Returns a score
breakdown, competitor comparison, and prioritized recommendations.

## API Integrations (Optional)

This skill works out of the box with the free iTunes Search API. However, the free API does not provide keyword search volume, keyword difficulty scores, or download estimates.

If the user provides their own API keys, use them for deeper ASO intelligence.

| Environment Variable | Service | What It Unlocks |
|---------------------|---------|-----------------|
| `APPSTORE_CONNECT_KEY_ID` + `APPSTORE_CONNECT_ISSUER_ID` + `APPSTORE_CONNECT_KEY_PATH` | App Store Connect API | Real download counts, conversion rates, keyword rankings, A/B test results |
| `SENSOR_TOWER_API_KEY` | Sensor Tower API | Keyword search volume, keyword difficulty scores, download estimates, category rankings |
| `DATA_AI_API_KEY` | data.ai (App Annie) API | Market data, competitive downloads, revenue estimates, usage metrics |

**How to set up:**
```bash
# App Store Connect (optional)
export APPSTORE_CONNECT_KEY_ID="your_key_id"
export APPSTORE_CONNECT_ISSUER_ID="your_issuer_id"
export APPSTORE_CONNECT_KEY_PATH="/path/to/AuthKey.p8"

# Sensor Tower (optional)
export SENSOR_TOWER_API_KEY="your_api_key"

# data.ai (optional)
export DATA_AI_API_KEY="your_api_key"
```

**Behavior:**
- If API keys are set → Enrich the analysis with keyword volume, downloads, and market data
- If not set → Use free iTunes Search API (current default behavior, no change)
- Each integration is independent - you can set one without the others

## Limitation

This skill uses the free iTunes Search API for live app data by default. Without
optional API integrations above, it does not provide keyword search volume,
keyword difficulty scores, or download estimates. It focuses on what is freely
measurable: metadata quality, best practice compliance, and competitor metadata
comparison.

## References

- `references/aso-checklist.md` - Pre-launch and post-launch ASO checklists
- `references/keyword-strategy.md` - Keyword research and placement strategy
- `references/metadata-limits.md` - Detailed platform character limits
