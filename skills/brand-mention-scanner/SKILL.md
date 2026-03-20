---
name: brand-mention-scanner
description: >
  Scan Reddit, Hacker News, and GitHub for brand or product mentions.
  Identifies where your brand is being discussed, analyzes sentiment
  context, and finds unresponded mentions. Use when the user mentions
  brand monitoring, brand mentions, reputation tracking, social listening,
  or wants to find where their product is being talked about online.
---

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

## Report Output

Every command MUST save its output as a markdown report file:

| Command | Output File |
|---------|-------------|
| `scan` | `BRAND-MENTIONS-REPORT.md` |
| `reddit` | `BRAND-MENTIONS-REDDIT-REPORT.md` |
| `hn` | `BRAND-MENTIONS-HN-REPORT.md` |
| `github` | `BRAND-MENTIONS-GITHUB-REPORT.md` |
| `report` | `BRAND-MENTIONS-FULL-REPORT.md` |

The report file should include:
- Date of scan
- Brand name searched
- Platform-by-platform results with sentiment breakdown
- Top mentions by engagement
- Action items and recommendations

Always inform the user where the report was saved after completion.

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
