---
name: competitor-intel
description: >
  Conduct competitive analysis for SaaS products. Analyzes competitor
  positioning, pricing, features, marketing channels, and content strategy.
  Generates battle cards and competitive positioning frameworks.
  Use when the user mentions competitive analysis, competitor research,
  battle cards, competitive positioning, or market landscape.
---

# Competitor Intel

Conduct structured competitive analysis for SaaS products, generate sales battle cards, map market landscapes, and build competitive positioning strategies.

## Commands

### `/competitor-intel analyze <competitor-url>`

Run a full competitor analysis by scanning the provided URL and combining it with the user's knowledge.

**Steps:**
1. Accept the competitor URL from the user
2. Run `scripts/competitor_scanner.py` to extract publicly available page data (title, meta description, headers, CTAs, social links, tech signals)
3. Ask the user to supplement with any known information about pricing, funding, team size, and market positioning
4. Analyze the extracted data against the framework in `references/analysis-framework.md`
5. Generate a structured competitor profile

**Output format:**
```
Competitor Analysis: [Company Name]
====================================

Overview:
  URL:              [url]
  Value Proposition: [extracted from meta/headers]
  Target Audience:   [inferred from messaging]

Product:
  Key Features:     [from page analysis]
  Platform:         [web, mobile, desktop]
  Integrations:     [detected integration page: yes/no]

Marketing:
  Social Channels:  [detected links]
  Blog/Content:     [detected: yes/no]
  Trust Signals:    [count of testimonials, logos, badges]
  Primary CTA:      [extracted CTA text]

Strengths:
  - [Strength 1]
  - [Strength 2]

Weaknesses:
  - [Weakness 1]
  - [Weakness 2]

Opportunities Against:
  - [Opportunity 1]
  - [Opportunity 2]
```

**Report:** Save output to `COMPETITOR-ANALYSIS-REPORT.md`

**Single-page limitation:** The scanner fetches only the provided URL. It does not crawl additional pages or subdomains. For deeper analysis, the user should provide specific page URLs (pricing page, features page, about page) as separate analysis runs.

### `/competitor-intel battlecard <competitor-name>`

Generate a sales battle card for use by the sales team when competing against a specific competitor.

**Steps:**
1. Ask for the competitor name and any existing knowledge (or run `/competitor-intel analyze` first)
2. Ask for the user's own product strengths, differentiators, and pricing
3. Ask for common objections the sales team hears about the competitor
4. Generate a structured battle card using the framework from `references/analysis-framework.md`
5. Include talk tracks and objection handling scripts

**Battle card sections:**
- Quick overview (one-line positioning for each product)
- Feature comparison table (your product vs competitor)
- Pricing comparison
- Where you win (your strengths vs their weaknesses)
- Where they win (acknowledge honestly)
- Common objections and responses
- Killer questions to ask the prospect
- Competitive landmines (things to establish early that favor your product)
- Customer proof points (case studies or quotes that counter the competitor)

**Report:** Save output to `COMPETITOR-BATTLECARD-REPORT.md`

### `/competitor-intel landscape`

Map the competitive landscape for the user's market.

**Steps:**
1. Ask for the user's product category and target market
2. Ask the user to list known competitors (3-10 recommended)
3. For each competitor, collect key attributes: positioning, pricing tier, target segment, primary differentiator
4. Create a market landscape map organized by axes chosen with the user (e.g., price vs feature breadth, SMB vs enterprise, vertical vs horizontal)
5. Identify white space opportunities and crowded segments
6. Recommend positioning strategy based on the landscape

**Output includes:**
- Text-based 2x2 landscape map
- Competitor clustering by segment
- White space identification
- Crowded segment warnings
- Recommended positioning quadrant

**Report:** Save output to `COMPETITOR-LANDSCAPE-REPORT.md`

### `/competitor-intel positioning`

Develop a competitive positioning strategy.

**Steps:**
1. Ask for the user's current positioning statement (or help craft one)
2. Collect competitor positioning statements (or derive from `/competitor-intel analyze` results)
3. Apply the positioning framework from `references/analysis-framework.md`
4. Identify differentiation opportunities across five dimensions: product, price, experience, brand, and audience
5. Generate a positioning recommendation

**Output includes:**
- Current positioning assessment
- Competitor positioning map
- Differentiation opportunity matrix
- Recommended positioning statement
- Messaging pillars (3-5 key messages that reinforce the positioning)
- Proof points for each pillar

**Report:** Save output to `COMPETITOR-POSITIONING-REPORT.md`

## Report Output

Every command MUST save its output as a markdown report file:

| Command | Output File |
|---------|-------------|
| `analyze` | `COMPETITOR-ANALYSIS-REPORT.md` |
| `battlecard` | `COMPETITOR-BATTLECARD-REPORT.md` |
| `landscape` | `COMPETITOR-LANDSCAPE-REPORT.md` |
| `positioning` | `COMPETITOR-POSITIONING-REPORT.md` |

The report file should include:
- Date of analysis
- Competitor name(s) and URL(s)
- Full analysis with strengths, weaknesses, and opportunities
- Actionable recommendations

Always inform the user where the report was saved after completion.

## API Integrations (Optional)

This skill works out of the box by fetching a single public web page. However, deeper competitive data (traffic estimates, keyword rankings, tech stack) cannot be extracted from a single page fetch alone.

If the user provides their own API keys, use them for richer competitive intelligence.

| Environment Variable | Service | What It Unlocks |
|---------------------|---------|-----------------|
| `SEMRUSH_API_KEY` | SEMrush API | Organic traffic estimates, top keywords, backlink data, ad spend estimates |
| `SIMILARWEB_API_KEY` | SimilarWeb API | Monthly visit estimates, traffic sources, geographic distribution, engagement metrics |
| `BUILTWITH_API_KEY` | BuiltWith API | Full technology stack detection (frameworks, analytics, CDN, hosting) |

**How to set up:**
```bash
# SEMrush (optional)
export SEMRUSH_API_KEY="your_api_key"

# SimilarWeb (optional)
export SIMILARWEB_API_KEY="your_api_key"

# BuiltWith (optional)
export BUILTWITH_API_KEY="your_api_key"
```

**Behavior:**
- If API keys are set → Enrich the competitor profile with traffic, keyword, and tech stack data
- If not set → Use single-page HTML analysis (current default behavior, no change)
- Each integration is independent - you can set one without the others

**When data is limited:** If the analysis lacks traffic estimates, keyword data, or tech stack details, inform the user which API keys would enrich the profile. Example:
> ℹ️ Traffic and keyword data unavailable - analysis is based on public page content only. For traffic estimates, set `SIMILARWEB_API_KEY`. For keyword rankings, set `SEMRUSH_API_KEY`. See the API Integrations section in this skill's SKILL.md for setup instructions.

## Key Reference Files

- `references/analysis-framework.md` - Structured competitive analysis framework covering product, pricing, marketing, brand, and traction dimensions
- `scripts/competitor_scanner.py` - Python scanner that extracts publicly available data from a competitor's webpage

## Guidelines

- Always be transparent that web scanning captures only publicly visible information from a single page
- Supplement automated scanning with the user's first-hand market knowledge
- Battle cards should be honest - acknowledging competitor strengths builds credibility with the sales team
- Update competitive intel at least quarterly as competitors evolve
- Focus on positioning differences that matter to the buyer, not technical minutiae
- When mapping landscapes, choose axes that reveal meaningful strategic differences
- Competitive intelligence should inform strategy, not drive reactive feature copying
- Always ask whether the user has direct customer feedback about competitors, as this is the most valuable intel source
- Do not make claims about competitors that cannot be verified from public sources
