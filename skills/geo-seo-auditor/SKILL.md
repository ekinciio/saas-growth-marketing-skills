---
name: geo-seo-auditor
description: >
  Audit websites for AI search engine visibility (GEO - Generative Engine Optimization).
  Analyzes citability score, AI crawler access, llms.txt compliance, brand authority signals,
  and platform-specific optimization for ChatGPT, Claude, Perplexity, and Google AI Overviews.
  Use when the user mentions GEO, AI SEO, AI search visibility, citability, llms.txt,
  AI crawler, or wants to optimize content for AI-powered search engines.
---

## First Run

When a user runs any geo-seo-auditor command for the first time, display
this intro before starting execution:

"""
📡 GEO SEO Auditor

What I'll do:
  Fetch your URL and evaluate AI search readiness across 6 dimensions.

What you'll get:
  → AI visibility score (0-100)
  → AI crawler access status (14 crawlers checked)
  → Citability analysis of key content blocks
  → Top 5 prioritized fixes

Output: Saved to GEO-AUDIT-REPORT.md
Time: ~90 seconds.

Starting...
"""

Then proceed immediately. Do not wait for user confirmation.

# GEO SEO Auditor

Comprehensive audit tool for Generative Engine Optimization (GEO) and traditional SEO. Evaluates how well a website is positioned to be cited by AI-powered search engines including ChatGPT, Claude, Perplexity, and Google AI Overviews.

## Commands

| Command | Description |
|---------|-------------|
| `/geo-seo-auditor audit <url>` | Full GEO + traditional SEO audit |
| `/geo-seo-auditor quick <url>` | 60-second GEO visibility snapshot |
| `/geo-seo-auditor citability <url>` | Score content for AI citation readiness |
| `/geo-seo-auditor crawlers <url>` | Check AI crawler access via robots.txt |
| `/geo-seo-auditor llmstxt <url>` | Analyze or generate llms.txt file |
| `/geo-seo-auditor brands <url>` | Scan brand mentions across AI-cited platforms |
| `/geo-seo-auditor platforms <url>` | Platform-specific optimization recommendations |

## Full Audit Flow

The full audit (`/geo-seo-auditor audit <url>`) follows a 6-step process:

### Step 1: Discovery
- Fetch the target URL HTML content
- Extract metadata (title, description, OG tags, canonical)
- Retrieve robots.txt and check sitemap.xml
- Detect structured data (JSON-LD, microdata)
- Check for llms.txt file

### Step 2: AI Visibility Analysis
- Score content blocks for AI citability (0-100)
- Identify the most citable passages on the page
- Evaluate content structure for AI comprehension
- Check factual density, self-containment, and Q&A format
- Flag anti-patterns (vague language, opinion without data, jargon)

### Step 3: Brand Authority
- Scan for brand mentions across AI-cited platforms
- Check presence on Wikipedia, Crunchbase, LinkedIn, GitHub
- Evaluate E-E-A-T signals (Experience, Expertise, Authoritativeness, Trustworthiness)
- Identify author credentials and organizational trust markers
- Assess backlink profile strength indicators

### Step 4: Platform Analysis
- ChatGPT: GPTBot access, content structure for citation
- Claude: ClaudeBot access, passage clarity and factual density
- Perplexity: PerplexityBot access, source attribution readiness
- Google AI Overviews: Google-Extended status, featured snippet optimization
- Generate platform-specific optimization recommendations

### Step 5: Scoring
- Calculate weighted scores across all audit dimensions
- Generate an overall GEO Readiness Score (0-100)
- Benchmark against best practices
- Identify top priorities for improvement

### Step 6: Report
- Compile findings into a structured audit report
- Include actionable recommendations ranked by impact
- Provide implementation difficulty ratings (easy, medium, hard)
- Deliver quick wins and long-term strategy items

## Scoring Methodology

| Dimension | Weight | What It Measures |
|-----------|--------|------------------|
| AI Citability & Visibility | 25% | How likely AI engines are to cite your content |
| Brand Authority Signals | 20% | Presence and reputation across AI-indexed sources |
| Content Quality & E-E-A-T | 20% | Expertise, experience, authority, and trust signals |
| Technical Foundations | 15% | Crawlability, page speed, mobile-friendliness, HTTPS |
| Structured Data | 10% | Schema markup, JSON-LD, rich snippet eligibility |
| Platform Optimization | 10% | Readiness for each major AI search platform |

### Score Ranges

- **90-100**: Excellent - Well-optimized for AI search visibility
- **70-89**: Good - Strong foundation with room for improvement
- **50-69**: Fair - Several areas need attention
- **30-49**: Poor - Significant optimization required
- **0-29**: Critical - Major overhaul needed for AI visibility

## Command Details

### `/geo-seo-auditor audit <url>`

Runs the complete 6-step audit. This is the most thorough analysis and covers every dimension in the scoring methodology. Typical runtime is 2-4 minutes depending on page complexity.

**Output includes:**
- Overall GEO Readiness Score
- Dimension-by-dimension breakdown
- Top 10 prioritized recommendations
- AI crawler access summary
- Citability analysis of key content blocks
- llms.txt compliance check
- Platform-specific readiness scores

**Report:** Save output to `GEO-AUDIT-REPORT.md`

### `/geo-seo-auditor quick <url>`

A rapid 60-second snapshot that covers the essentials:
- Overall GEO Readiness Score (estimated)
- AI crawler access status (top 5 crawlers)
- Page citability score (top 3 blocks)
- llms.txt existence check
- Top 3 quick-win recommendations

**Report:** Save output to `GEO-QUICK-REPORT.md`

Use this when you need a fast overview before diving deeper.

### `/geo-seo-auditor citability <url>`

Deep-dive into content citability. Analyzes every content block on the page and scores each one for AI citation readiness.

**Scoring criteria per block (0-100):**
- Structure clarity (headers, lists, definitions): 25 points
- Factual density (statistics, dates, specifics): 25 points
- Self-containment (passage stands alone without context): 25 points
- Question-answer format (directly answers a query): 25 points

**Output includes:**
- Overall page citability score
- Per-block scores with excerpts
- Top 5 most citable passages
- Bottom 5 least citable passages
- Specific rewrite suggestions for low-scoring blocks

**Report:** Save output to `GEO-CITABILITY-REPORT.md`

### `/geo-seo-auditor crawlers <url>`

Checks the site's robots.txt against 14+ known AI crawlers.

**Crawlers checked:**
- GPTBot (OpenAI - ChatGPT training)
- OAI-SearchBot (OpenAI - ChatGPT search)
- ClaudeBot (Anthropic - Claude)
- PerplexityBot (Perplexity AI)
- Google-Extended (Google AI/Gemini)
- Bytespider (TikTok/ByteDance)
- CCBot (Common Crawl)
- Amazonbot (Amazon/Alexa)
- FacebookBot (Meta)
- Applebot-Extended (Apple Intelligence)
- Cohere-AI (Cohere)
- Diffbot (Diffbot)
- Timpibot (Timpi search)
- Webz.io (Webz data platform)

**Status per crawler:** allowed, blocked, or not_mentioned

**Output includes:**
- Status table for all crawlers
- Recommendations for which crawlers to allow/block
- Sample robots.txt directives

**Report:** Save output to `GEO-CRAWLERS-REPORT.md`

### `/geo-seo-auditor llmstxt <url>`

Checks for the presence and validity of an llms.txt file at the site root.

**If llms.txt exists:**
- Validates format against the specification
- Checks required and optional fields
- Identifies missing or malformed entries
- Suggests improvements

**If llms.txt is missing:**
- Generates a recommended llms.txt based on site structure
- Explains the benefits of adding one
- Provides implementation instructions

**Report:** Save output to `GEO-LLMSTXT-REPORT.md`

### `/geo-seo-auditor brands <url>`

Scans for brand authority signals across platforms commonly indexed by AI engines.

**Platforms checked:**
- Wikipedia presence and article quality
- Crunchbase profile completeness
- LinkedIn company page signals
- GitHub organization activity
- Industry directories and review sites
- News mentions and press coverage indicators

**Output includes:**
- Brand mention inventory
- Authority score per platform
- Gaps in brand presence
- Recommendations for strengthening authority signals

**Report:** Save output to `GEO-BRANDS-REPORT.md`

### `/geo-seo-auditor platforms <url>`

Generates platform-specific optimization recommendations for each major AI search engine.

**Platforms covered:**

**ChatGPT:**
- GPTBot and OAI-SearchBot crawler access
- Content structure preferences
- Citation format optimization

**Claude:**
- ClaudeBot crawler access
- Passage clarity and factual density
- Source attribution readiness

**Perplexity:**
- PerplexityBot crawler access
- Inline citation optimization
- Source snippet formatting

**Google AI Overviews:**
- Google-Extended crawler status
- Featured snippet optimization
- Structured data for AI extraction

**Report:** Save output to `GEO-PLATFORMS-REPORT.md`

## API Integrations (Optional)

This skill works out of the box by fetching public web pages. However, some analysis dimensions (page speed, backlinks, search performance) cannot be measured from a simple HTML fetch alone.

If the user provides their own API keys, use them to enrich the audit with real performance and search data.

| Environment Variable | Service | What It Unlocks |
|---------------------|---------|-----------------|
| `GOOGLE_API_KEY` | Google PageSpeed Insights API | Real Core Web Vitals scores (LCP, FID, CLS), mobile/desktop performance data |
| `GOOGLE_SEARCH_CONSOLE_JSON` | Google Search Console API | Actual search impressions, clicks, CTR, average position for the audited URL |
| `AHREFS_API_KEY` | Ahrefs API | Backlink count, referring domains, Domain Rating, organic keyword data |

**How to set up:**
```bash
# Google PageSpeed (optional)
export GOOGLE_API_KEY="your_google_api_key"

# Google Search Console (optional) - path to service account JSON
export GOOGLE_SEARCH_CONSOLE_JSON="/path/to/service-account.json"

# Ahrefs (optional)
export AHREFS_API_KEY="your_ahrefs_api_key"
```

**Behavior:**
- If API keys are set → Enrich the audit with real performance and search data
- If not set → Use HTML-only analysis (current default behavior, no change)
- Each integration is independent - you can set one without the others

**When data is limited:** If the audit cannot measure page speed accurately or lacks backlink data, inform the user which API keys would enrich the results. Example:
> ℹ️ Page speed score is estimated from HTML signals only. For real Core Web Vitals (LCP, CLS, INP), set `GOOGLE_API_KEY`. See the API Integrations section in this skill's SKILL.md for setup instructions.

## Output Rules (MANDATORY)

### File Output
- ALWAYS save the complete report to the specified `.md` file in the current working directory.
- NEVER ask "should I save this?" — just save it automatically.
- Include `**Date:** YYYY-MM-DD` in the report header.
- If the file already exists, overwrite it (latest analysis wins).
- Follow the structure from `templates/report-template.md`.

### Chat Output
After saving, show a SHORT summary in chat (max 10 lines):

"""
✅ GEO audit complete — saved to GEO-AUDIT-REPORT.md

Score: [X]/100 ([interpretation])

Top findings:
  1. [Most important finding]
  2. [Second finding]
  3. [Third finding]

Full report with all 6 dimensions and fixes → open GEO-AUDIT-REPORT.md
"""

NEVER dump the full report in chat. The file is the deliverable.

## Important Notes

### SPA Limitation
Works best with server-rendered pages. Client-side-only SPAs may return incomplete results. If the target site relies heavily on JavaScript rendering, the fetched HTML may not contain the full page content. Consider using a server-side rendered version of the page or providing pre-rendered HTML when possible.

### Prerequisites
The Python scripts in the `scripts/` directory require the following packages:
- `requests` - HTTP requests
- `beautifulsoup4` - HTML parsing
- `lxml` (optional) - Faster HTML/XML parsing

Install with: `pip install requests beautifulsoup4 lxml`

### Rate Limiting
When auditing multiple pages, allow at least 2 seconds between requests to avoid being rate-limited by the target server. The scripts include built-in delays for multi-page operations.

### Data Privacy
This tool only reads publicly available information. It does not store, cache, or transmit any data from audited websites beyond the current session.
