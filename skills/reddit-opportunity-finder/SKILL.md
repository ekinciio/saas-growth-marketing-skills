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

## Report Output

Every command MUST save its output as a markdown report file:

| Command | Output File |
|---------|-------------|
| `search` | `REDDIT-OPPORTUNITIES-REPORT.md` |
| `monitor` | `REDDIT-MONITOR-SETUP-REPORT.md` |
| `analyze` | `REDDIT-SUBREDDIT-REPORT.md` |

The report file should include:
- Date of scan
- Keywords or subreddit analyzed
- Opportunity scores and thread details with URLs
- Engagement recommendations

Always inform the user where the report was saved after completion.

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
