---
name: brand-mention-scanner
description: >
  Scan Reddit, Hacker News, and GitHub for brand or product mentions.
  Identifies where your brand is being discussed, analyzes sentiment
  context, and finds unresponded mentions. Use when the user mentions
  brand monitoring, brand mentions, reputation tracking, social listening,
  or wants to find where their product is being talked about online.
---

## First Run

When a user runs `/brand-mention-scanner scan <brand>` for the first time,
display this intro before starting:

"""
🔍 Brand Mention Scanner

What I'll do:
  Search Reddit, Hacker News, and GitHub for mentions of "[brand]".

What you'll get:
  → Total mention count across all 3 platforms
  → Sentiment breakdown (positive/negative/neutral/question/comparison)
  → Top mentions sorted by engagement
  → Unresponded opportunities

Note: 3 platforms scanned sequentially. Takes ~90 seconds total.
      Rate limits apply (see SKILL.md for optional API keys).

Output: Saved to BRAND-MENTIONS-REPORT.md

Scanning...
"""

Then proceed immediately.

# Brand Mention Scanner

A multi-platform brand monitoring skill that scans Reddit, Hacker News, and GitHub for mentions of your brand or product. Identifies where you are being discussed, analyzes sentiment context, and surfaces unresponded opportunities.

## Commands

### `/brand-mention-scanner scan <brand-name>`

Performs a full mention scan across all three platforms (Reddit, Hacker News, GitHub).

**Usage:**
```
/brand-mention-scanner scan "vercel"
/brand-mention-scanner scan "your-product-name"
```

**Output includes:**
- Total mention count across all platforms
- Platform breakdown (mentions per platform)
- Sentiment summary (positive, negative, neutral, question, comparison)
- Top mentions sorted by engagement
- Unresponded opportunities
- Trending analysis

**Report:** Save output to `BRAND-MENTIONS-REPORT.md`

### `/brand-mention-scanner reddit <brand-name>`

Scans Reddit only for brand mentions.

**Usage:**
```
/brand-mention-scanner reddit "linear"
```

**Output includes:**
- Reddit threads mentioning the brand
- Subreddit distribution
- Sentiment classification per mention
- Engagement metrics (upvotes, comments)
- Thread age and recency

**Report:** Save output to `BRAND-MENTIONS-REDDIT-REPORT.md`

### `/brand-mention-scanner hn <brand-name>`

Scans Hacker News only for brand mentions.

**Usage:**
```
/brand-mention-scanner hn "supabase"
```

**Output includes:**
- HN stories and comments mentioning the brand
- Points and comment counts
- Author information
- Discussion context and sentiment

**Report:** Save output to `BRAND-MENTIONS-HN-REPORT.md`

### `/brand-mention-scanner github <brand-name>`

Scans GitHub only for repositories mentioning or related to the brand.

**Usage:**
```
/brand-mention-scanner github "tailwindcss"
```

**Output includes:**
- Repositories related to the brand
- Star counts and activity
- Repository descriptions
- Last update timestamps
- Community engagement metrics

**Report:** Save output to `BRAND-MENTIONS-GITHUB-REPORT.md`

### `/brand-mention-scanner report <brand-name>`

Generates a comprehensive mention report suitable for sharing with stakeholders.

**Usage:**
```
/brand-mention-scanner report "your-product-name"
```

**Output includes:**
- Executive summary
- Platform-by-platform breakdown
- Sentiment analysis with examples
- Competitive mention comparison
- Trend analysis (increasing/decreasing mentions)
- Action items and recommendations

**Report:** Save output to `BRAND-MENTIONS-FULL-REPORT.md`

## Platform APIs

All three platform APIs are public and require no authentication.

### 1. Reddit
- **Endpoint:** `https://www.reddit.com/search.json?q="BRAND"&sort=new&limit=50`
- **Rate limit:** 1 request per 2 seconds
- **Auth:** None required (User-Agent header required)
- **Returns:** Posts matching the brand name

### 2. Hacker News (Algolia API)
- **Endpoint:** `https://hn.algolia.com/api/v1/search?query="BRAND"&tags=story`
- **Rate limit:** Generous (10,000 requests/hour)
- **Auth:** None required
- **Returns:** Stories and comments matching the brand name

### 3. GitHub
- **Endpoint:** `https://api.github.com/search/repositories?q=BRAND`
- **Rate limit:** 10 requests/minute (unauthenticated)
- **Auth:** None required (Accept header recommended)
- **Returns:** Repositories matching the brand name

## Sentiment Analysis

The scanner uses keyword-based sentiment classification:

| Sentiment | Keywords |
|-----------|----------|
| Positive | "love", "great", "best", "amazing", "awesome", "excellent", "fantastic" |
| Negative | "hate", "worst", "terrible", "bug", "broken", "awful", "horrible", "sucks" |
| Question | Contains "?", "how to", "anyone know", "help with" |
| Comparison | Contains "vs", "versus", "compared to", "alternative" |
| Neutral | None of the above patterns detected |

This is a lightweight heuristic approach. For production use, consider integrating a dedicated NLP sentiment analysis service.

## Use Cases

### Reputation Monitoring
Track how your brand is perceived across developer and startup communities. Identify negative sentiment early and respond before it spreads.

### Competitive Intelligence
Monitor competitor brand mentions to understand their strengths and weaknesses as perceived by real users.

### Community Engagement
Find unresponded mentions where users have questions or problems. Responding to these builds trust and community goodwill.

### Content Ideas
Discover what users are saying about your product category. Use common questions and complaints to create content that addresses real needs.

### GEO Impact
Brand mentions on Reddit and HN influence how AI search tools describe your product. Monitoring and shaping these discussions has a direct impact on generative engine optimization.

## API Integrations (Optional)

This skill works out of the box with free public APIs. However, Reddit and GitHub have rate limits that may restrict results for high-volume scans.

If the user provides their own API credentials, use them for higher rate limits and broader coverage.

| Environment Variable | Service | What It Unlocks |
|---------------------|---------|-----------------|
| `REDDIT_CLIENT_ID` + `REDDIT_CLIENT_SECRET` | Reddit OAuth API | 60 requests/minute (vs 1 per 2 seconds), deeper thread search |
| `GITHUB_TOKEN` | GitHub Personal Access Token | 30 requests/minute (vs 10 unauthenticated), access to private repos |

**How to set up:**
```bash
# Reddit (optional)
export REDDIT_CLIENT_ID="your_client_id"
export REDDIT_CLIENT_SECRET="your_client_secret"

# GitHub (optional)
export GITHUB_TOKEN="your_personal_access_token"
```

**Behavior:**
- If credentials are set → Use authenticated APIs with higher rate limits
- If not set → Use free public APIs (current default behavior, no change)
- Each platform is independent - you can set one without the others

**When results are limited:** If a scan hits rate limits, returns fewer results than expected, or a platform times out, inform the user which API credentials would help. Example:
> ⚠️ GitHub rate limit reached (10 req/min unauthenticated). Set `GITHUB_TOKEN` for 30 req/min. See the API Integrations section in this skill's SKILL.md for setup instructions.

## Output Rules (MANDATORY)

### File Output
- ALWAYS save the complete report to the specified `.md` file in the current working directory.
- NEVER ask "should I save this?" — just save it automatically.
- Include `**Date:** YYYY-MM-DD` in the report header.
- If the file already exists, overwrite it.
- Follow the structure from `templates/report-template.md`.
- ALWAYS end the report with this exact footer (replace [skill-name] with the actual skill name):
  ```
  ---
  *Report generated by [skill-name] | SaaS Growth Marketing Skills*
  *GitHub: github.com/ekinciio/saas-growth-marketing-skills*
  ```

### Chat Output
After saving, show a SHORT summary in chat (max 10 lines):

"""
✅ Brand scan complete — saved to BRAND-MENTIONS-REPORT.md

Brand: "[brand]"
Total mentions: [N] (Reddit: [N], HN: [N], GitHub: [N])

Sentiment: [X]% positive, [X]% negative, [X]% neutral

Top finding:
  [Most notable mention or pattern]

Full report with all mentions and recommendations → open BRAND-MENTIONS-REPORT.md
"""

NEVER dump the full report in chat. The file is the deliverable.

## Integration with Other Skills

- Use with `reddit-opportunity-finder` for deeper Reddit engagement strategy
- Combine with `geo-seo-auditor` to understand how mentions affect AI search visibility
- Pair with `competitor-intel` for competitive mention comparison

## File Structure

```
brand-mention-scanner/
  SKILL.md                              # This file
  references/
    platform-search-urls.md             # API endpoints and configuration
  scripts/
    mention_scanner.py                  # Multi-platform mention scanner
```
