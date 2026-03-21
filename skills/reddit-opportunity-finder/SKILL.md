---
name: reddit-opportunity-finder
description: >
  Find high-intent Reddit threads where your product or service is relevant.
  Searches Reddit for keyword-matching posts and comments, scores them by
  engagement and recency, and identifies opportunities to provide value.
  Use when the user mentions Reddit marketing, Reddit opportunities,
  Reddit lead generation, Reddit monitoring, finding Reddit threads,
  or community-driven growth.
---

## First Run

When a user runs `/reddit-opportunity-finder search <keywords>` for the
first time, display this intro before starting:

"""
🔍 Reddit Opportunity Finder

What I'll do:
  Search Reddit for threads matching "[keywords]" and score each
  by opportunity value (recency, engagement, intent signals).

What you'll get:
  → Matching threads sorted by opportunity score (0-100)
  → Thread details (title, subreddit, score, comments, URL)
  → Top subreddits for your keywords
  → Engagement recommendations

Note: Reddit rate limit is 1 request per 2 seconds (unauthenticated).
      Set REDDIT_CLIENT_ID for 60 req/min. Results may take 30-60s.

Output: Saved to REDDIT-OPPORTUNITIES-REPORT.md

Searching...
"""

Then proceed immediately.

# Reddit Opportunity Finder

A skill for discovering high-intent Reddit threads where your product or service can provide genuine value. Searches Reddit's public API for keyword-matching posts, scores them by engagement and recency, and surfaces the best opportunities for authentic participation.

## Commands

### `/reddit-opportunity-finder search <keywords>`

Searches Reddit for threads matching your keywords and scores each by opportunity value.

**Usage:**
```
/reddit-opportunity-finder search "best project management tool"
/reddit-opportunity-finder search "code review automation, AI code review"
```

**Output includes:**
- Matching threads sorted by opportunity score (0-100)
- Thread title, subreddit, score, comment count, and age
- Direct URL to each thread
- Question/recommendation format detection
- Top subreddits where opportunities exist

**Opportunity scoring factors:**
- Recency: Newer threads score higher (24h: +30, 72h: +20, 1 week: +10)
- Engagement: Higher upvotes and comments indicate active discussions
- Intent signals: Question marks, "best", "recommend", "looking for"
- Subreddit relevance: Known SaaS-friendly subreddits score higher

**Report:** Save output to `REDDIT-OPPORTUNITIES-REPORT.md`

### `/reddit-opportunity-finder monitor <keywords>`

Generates a monitoring setup guide for ongoing keyword tracking on Reddit.

**Usage:**
```
/reddit-opportunity-finder monitor "review management, reputation management"
```

**Output includes:**
- Recommended monitoring frequency
- Subreddit watchlist based on keyword analysis
- Alert configuration guidance
- RSS feed setup instructions
- Automation suggestions using Reddit's JSON API

**Report:** Save output to `REDDIT-MONITOR-SETUP-REPORT.md`

### `/reddit-opportunity-finder analyze <subreddit>`

Analyzes a specific subreddit for opportunity fit and engagement patterns.

**Usage:**
```
/reddit-opportunity-finder analyze r/SaaS
```

**Output includes:**
- Subreddit activity metrics (posts per day, average engagement)
- Common thread types and formats
- Self-promotion rules and limits
- Best posting times and days
- Competitor presence analysis
- Opportunity assessment score

**Report:** Save output to `REDDIT-SUBREDDIT-REPORT.md`

## Technical Details

This skill uses Reddit's public JSON API, which requires no authentication. All endpoints return JSON when `.json` is appended to the URL.

**API endpoint:**
```
https://www.reddit.com/search.json?q={keyword}&sort=new&limit=25&t={time_filter}
```

**Important:**
- A User-Agent header is required for all requests
- Rate limiting: Maximum one request every 2 seconds
- Results are limited to 25 per request by default
- Time filters: hour, day, week, month, year, all

## Engagement Guidelines

Reddit values authentic participation over marketing. When responding to opportunities found by this skill:

1. **Provide genuine value first** - Answer the question fully before mentioning your product
2. **Disclose affiliations** - Be transparent about your connection to any product
3. **Respect subreddit rules** - Each subreddit has its own self-promotion policies
4. **Follow the 10% rule** - No more than 10% of your activity should be self-promotional
5. **Build karma first** - Establish credibility through helpful contributions

## Best Subreddits for SaaS

| Subreddit | Focus | Self-Promo Rules |
|-----------|-------|-----------------|
| r/SaaS | SaaS discussion | Allowed with value |
| r/startups | Startup community | Limited, must add context |
| r/Entrepreneur | Business building | Moderate |
| r/smallbusiness | Small business | Moderate |
| r/marketing | Marketing strategy | Strict |
| r/SEO | Search optimization | Moderate |
| r/webdev | Web development | Tool recommendations OK |
| r/artificial | AI discussion | Tool sharing OK |
| r/ChatGPT | AI tools | Recommendations welcome |

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
✅ Reddit scan complete — saved to REDDIT-OPPORTUNITIES-REPORT.md

Found: [N] threads across [N] subreddits

Top 3 opportunities:
  1. [Thread title] (r/[sub], [score] upvotes) — Score: [X]/100
  2. [Thread title] (r/[sub], [score] upvotes) — Score: [X]/100
  3. [Thread title] (r/[sub], [score] upvotes) — Score: [X]/100

Full report with all threads and engagement tips → open REDDIT-OPPORTUNITIES-REPORT.md
"""

NEVER dump the full report in chat. The file is the deliverable.

## API Integrations (Optional)

This skill works out of the box with Reddit's free public JSON API. However, the free API has strict rate limits (1 request per 2 seconds) which can cause timeouts or incomplete results for broad searches.

If the user provides their own API credentials, use them for higher rate limits and richer data.

| Environment Variable | Service | What It Unlocks |
|---------------------|---------|-----------------|
| `REDDIT_CLIENT_ID` + `REDDIT_CLIENT_SECRET` | Reddit OAuth API | 60 requests/minute (vs 1 per 2 seconds), access to more results per query, comment-level search |

**How to set up:**
1. Create a Reddit app at `https://www.reddit.com/prefs/apps`
2. Select "script" as the app type
3. Set the environment variables:
   ```bash
   export REDDIT_CLIENT_ID="your_client_id"
   export REDDIT_CLIENT_SECRET="your_client_secret"
   ```

**Behavior:**
- If `REDDIT_CLIENT_ID` is set → Use OAuth API with higher rate limits
- If not set → Use free public JSON API (current default behavior, no change)

**When results are limited:** If a search returns fewer results than expected, hits a rate limit, or times out, inform the user that optional API credentials can improve results. Example:
> ⚠️ Reddit rate limit reached - retrieved 12 of ~50 potential results. For higher limits (60 req/min), set `REDDIT_CLIENT_ID` and `REDDIT_CLIENT_SECRET`. See the API Integrations section in this skill's SKILL.md for setup instructions.

## Integration with Other Skills

- Use with `brand-mention-scanner` for comprehensive mention monitoring
- Combine with `geo-seo-auditor` for Reddit's impact on AI search (GEO)
- Pair with `saas-landing-builder` to optimize pages Reddit traffic lands on

## File Structure

```
reddit-opportunity-finder/
  SKILL.md                              # This file
  references/
    reddit-engagement-guide.md          # Engagement rules and best practices
  scripts/
    reddit_scanner.py                   # Automated Reddit opportunity scanner
```
