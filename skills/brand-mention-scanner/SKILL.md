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

## Intro Banner

When starting a scan, display this intro before fetching:

"""
🔍 Brand Mention Scanner

What I'll do:
  Search Reddit, Hacker News, and GitHub for mentions of "[brand]".

What you'll get:
  → Total mention count across all 3 platforms
  → Sentiment breakdown (positive/negative/neutral/question/comparison)
  → Top mentions sorted by engagement
  → Unresponded opportunities

Note: 3 platforms scanned sequentially. Takes ~15-30 seconds total.
      Rate limits apply (see SKILL.md for optional API keys).

Output: Saved to BRAND-MENTIONS-REPORT.md

Scanning...
"""

Then proceed immediately.

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

## Workflow

When executing any scan command:

1. **Run the scanner script** (paths relative to this skill's directory):
   ```bash
   python3 scripts/mention_scanner.py "<brand>" --platforms reddit,hn,github --time month
   ```
   Adjust `--platforms` for single-platform commands and `--time` for the requested window.

2. **Check the report's `Errors` section before summarizing.** Platform failures are printed as `FAILED` lines in the platform breakdown and listed under Errors - never present a failed platform as "0 mentions". If Reddit ran in RSS-fallback mode, say that upvote/comment counts are unavailable and that `REDDIT_CLIENT_ID`/`REDDIT_CLIENT_SECRET` restore full data. If Reddit failed entirely, fall back to WebSearch (e.g. `site:reddit.com "<brand>"`) for that platform.

3. **Consult `references/platform-search-urls.md`** when adding new platforms, debugging API errors, or answering questions about endpoints and rate limits.

## Platform APIs

Hacker News and GitHub are public and need no authentication. Reddit no longer allows unauthenticated API access - the scanner uses OAuth when credentials are set and falls back to Reddit's public RSS feed otherwise.

### 1. Reddit
- **Primary endpoint (OAuth):** `https://oauth.reddit.com/search?q="BRAND"&sort=new&limit=50` with a bearer token from `https://www.reddit.com/api/v1/access_token` (client_credentials grant)
- **Fallback endpoint:** `https://www.reddit.com/search.rss?q="BRAND"&sort=new` (Atom feed; no upvote/comment counts)
- **Rate limit:** OAuth free tier: 100 queries/min per client ID (averaged over a 10-minute window). Unauthenticated JSON: blocked (403)
- **Auth:** `REDDIT_CLIENT_ID` + `REDDIT_CLIENT_SECRET` for OAuth; none for RSS (User-Agent header always required)
- **Returns:** Posts matching the brand name (RSS: title/URL/date/subreddit only)

### 2. Hacker News (Algolia API)
- **Endpoint:** `https://hn.algolia.com/api/v1/search_by_date?query="BRAND"&tags=story&numericFilters=created_at_i>CUTOFF`
- **Rate limit:** Generous (10,000 requests/hour)
- **Auth:** None required
- **Returns:** Stories and comments matching the brand name within the time window

### 3. GitHub
- **Endpoint:** `https://api.github.com/search/repositories?q=BRAND+pushed:>YYYY-MM-DD`
- **Rate limit:** 10 requests/minute unauthenticated; 30 requests/minute with `GITHUB_TOKEN`
- **Auth:** Optional `GITHUB_TOKEN` (`Accept: application/vnd.github+json` and `X-GitHub-Api-Version: 2022-11-28` headers recommended)
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

Hacker News and GitHub work out of the box with no credentials. Reddit works without credentials only in degraded RSS mode (no upvote/comment data), so Reddit credentials are strongly recommended.

| Environment Variable | Service | What It Unlocks |
|---------------------|---------|-----------------|
| `REDDIT_CLIENT_ID` + `REDDIT_CLIENT_SECRET` | Reddit OAuth API | Full post data (upvotes, comment counts); 100 queries/min per client ID (averaged over a 10-minute window). Without them: RSS fallback with limited data |
| `GITHUB_TOKEN` | GitHub Personal Access Token | Higher search rate limit (30 requests/minute vs 10 unauthenticated) |

**How to set up:**
```bash
# Reddit (recommended). New API access requires approval via Reddit's
# developer request form (Responsible Builder Policy) at
# support.reddithelp.com; apps created earlier at
# https://www.reddit.com/prefs/apps keep working.
export REDDIT_CLIENT_ID="your_client_id"
export REDDIT_CLIENT_SECRET="your_client_secret"

# GitHub (optional)
export GITHUB_TOKEN="your_personal_access_token"
```

**Behavior:**
- If credentials are set → Use authenticated APIs with full data and higher rate limits
- If not set → HN and GitHub still work fully; Reddit degrades to the RSS fallback (errors and limitations are recorded in the report)
- Each platform is independent - you can set one without the others

**When results are limited:** If a scan hits rate limits, returns fewer results than expected, or a platform times out, inform the user which API credentials would help. Example:
> ⚠️ GitHub rate limit reached (10 req/min unauthenticated). Set `GITHUB_TOKEN` for 30 req/min. See the API Integrations section in this skill's SKILL.md for setup instructions.

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
✅ Brand scan complete - saved to BRAND-MENTIONS-REPORT.md

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
