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

A skill for discovering high-intent Reddit threads where your product or service can provide genuine value. Searches Reddit for keyword-matching posts (OAuth API when credentials are set, public RSS feed otherwise), scores them by engagement and recency, and surfaces the best opportunities for authentic participation.

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

Note: Full data needs Reddit OAuth credentials (REDDIT_CLIENT_ID +
      REDDIT_CLIENT_SECRET, 100 queries/min). Without them I use
      Reddit's public RSS feed - no upvote/comment counts.
      Results may take 30-60s.

Output: Saved to REDDIT-OPPORTUNITIES-REPORT.md

Searching...
"""

Then proceed immediately.

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
- Automation suggestions using Reddit's RSS feeds (the JSON API now requires approved OAuth credentials)

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

## Workflow

When executing the `search` command:

1. **Run the scanner script** (paths relative to this skill's directory):
   ```bash
   python3 scripts/reddit_scanner.py "<keywords>" --time week
   ```
   Use comma-separated keywords for multiple searches; add `--subreddit <name>` or `--min-upvotes <N>` when the user asks for them.

2. **Check the script output for errors before reporting.** The report includes a `Data source:` line and an `Errors` section:
   - If the RSS fallback was used, upvote/comment counts are unknown (shown as 0) and opportunity scores omit engagement components. Say so in the report and mention that setting `REDDIT_CLIENT_ID`/`REDDIT_CLIENT_SECRET` restores full data.
   - If the script reports 403 errors or returns no results at all, fall back to WebSearch for thread discovery (e.g. `site:reddit.com "<keywords>"`) and note the degraded method in the report. Never present a failed scan as "0 opportunities found".

3. **Read `references/reddit-engagement-guide.md` before writing engagement recommendations** - it defines the rules (10% rule, disclosure, subreddit compliance, response templates) that recommendations must follow.

## Technical Details

Reddit no longer allows unauthenticated API access: `https://www.reddit.com/search.json` returns **403 Blocked** for all user agents. The scanner script tries three access methods in order:

1. **OAuth API (primary, full data).** With `REDDIT_CLIENT_ID` and `REDDIT_CLIENT_SECRET` set, the script fetches an app-only token from `https://www.reddit.com/api/v1/access_token` (grant type `client_credentials`, HTTP basic auth) and searches via `https://oauth.reddit.com/search`. Free tier: 100 queries per minute per client ID, averaged over a 10-minute window.
2. **Public JSON API (tried once).** Kept for the rare environment where it still responds; expect 403.
3. **RSS fallback (no auth).** `https://www.reddit.com/search.rss?q={keyword}&sort=new&t={time_filter}&type=link` still returns 200. The Atom feed keeps title, URL, date, and subreddit but has no upvote or comment counts, so those score components are 0 and results are marked "limited data - RSS fallback".

**Important:**
- A descriptive User-Agent header is required (Reddit's format: `script:app-name:version (by /u/username)`)
- Time filters: hour, day, week, month, year, all
- The script never silently returns 0 results on failure - every error is recorded in the result's `errors` list and printed in the report
- If all methods fail, use WebSearch for thread discovery instead

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

## API Integrations (Recommended)

Without credentials this skill falls back to Reddit's public RSS search feed, which still works but returns no upvote or comment data. OAuth credentials restore full data.

| Environment Variable | Service | What It Unlocks |
|---------------------|---------|-----------------|
| `REDDIT_CLIENT_ID` + `REDDIT_CLIENT_SECRET` | Reddit OAuth API | Full post data (upvotes, comment counts, selftext); 100 queries/min per client ID (averaged over a 10-minute window) |

**How to set up:**
1. New Reddit API access requires approval: submit Reddit's developer request form (Responsible Builder Policy) via `support.reddithelp.com`. Approval is not instant.
2. Apps created earlier at `https://www.reddit.com/prefs/apps` keep working - use their existing client ID and secret.
3. Set the environment variables:
   ```bash
   export REDDIT_CLIENT_ID="your_client_id"
   export REDDIT_CLIENT_SECRET="your_client_secret"
   ```

**Behavior:**
- If credentials are set → OAuth API with full data (100 queries/min free tier)
- If not set → RSS fallback: title/URL/date/subreddit only; engagement data missing and scores reflect that

**When results are limited:** If the scan used the RSS fallback or hit errors, tell the user plainly. Example:
> ⚠️ Reddit blocks unauthenticated API access (403), so this scan used the RSS fallback - upvote and comment counts are unavailable and opportunity scores omit engagement. For full data, set `REDDIT_CLIENT_ID` and `REDDIT_CLIENT_SECRET` (see API Integrations in this skill's SKILL.md).

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
