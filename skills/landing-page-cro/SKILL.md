---
name: landing-page-cro
description: >
  Audit and optimize landing pages for conversion rate optimization.
  Analyzes page structure, copy effectiveness, CTA placement, social proof,
  form friction, and trust signals. Provides a CRO score and actionable
  recommendations. Use when the user mentions CRO, conversion optimization,
  landing page audit, conversion rate, A/B testing ideas, or page optimization.
---

# Landing Page CRO

Comprehensive conversion rate optimization audit tool for landing pages. Evaluates 10 key dimensions of page effectiveness, scores each on a 0-10 scale, and delivers prioritized recommendations to improve conversion rates.

## Commands

| Command | Description |
|---------|-------------|
| `/landing-page-cro audit <url>` | Full CRO audit with scores and recommendations |
| `/landing-page-cro score <url>` | Quick CRO score (0-100) with dimension breakdown |
| `/landing-page-cro copy-review` | Landing page copy review and improvement suggestions |
| `/landing-page-cro ab-ideas <url>` | A/B test ideas generator based on page analysis |

## Full Audit Flow

The full audit (`/landing-page-cro audit <url>`) follows a structured process:

### Step 1: Page Fetch and Parse
- Fetch the target URL HTML content
- Extract page structure, headings, CTAs, forms, and media
- Identify above-the-fold content boundaries
- Detect social proof elements, trust badges, and testimonials

### Step 2: Score Each Dimension (0-10 each)
Evaluate the page across 10 CRO dimensions, each scored from 0 to 10 for a maximum total of 100.

### Step 3: Generate Recommendations
- Identify the weakest scoring dimensions
- Produce the top 5 prioritized, actionable recommendations
- Suggest specific A/B test hypotheses for each recommendation

### Step 4: Report
- Compile a structured report with overall score, dimension breakdown, and recommendations
- Rank recommendations by estimated impact

## CRO Scoring Criteria

Each dimension is scored from 0 to 10. The total CRO score is the sum of all 10 dimensions (0-100).

| # | Dimension | What It Measures |
|---|-----------|------------------|
| 1 | Above-the-fold clarity | Headline communicates value prop clearly; visitor understands what this is within 5 seconds |
| 2 | CTA visibility and copy strength | Primary CTA is prominent, uses action-oriented language, and stands out visually |
| 3 | Social proof presence and quality | Customer logos, testimonials, case studies, review counts, or user statistics are present and credible |
| 4 | Trust signals | Security badges, partner logos, certifications, privacy mentions, or money-back guarantees are visible |
| 5 | Form simplicity | Low field count, clear labels, minimal friction; fewer fields means less drop-off |
| 6 | Page speed and mobile responsiveness | Fast load time, mobile-friendly layout, responsive images, no layout shifts |
| 7 | Visual hierarchy and scan-ability | Clear heading structure, whitespace usage, content sections are easy to scan without reading everything |
| 8 | Objection handling | Common buyer concerns are addressed - pricing clarity, FAQs, comparison tables, risk reversal |
| 9 | Urgency and scarcity | Authentic time-based or quantity-based motivators that encourage action without feeling manipulative |
| 10 | Copy clarity and benefit-driven language | Copy focuses on customer outcomes rather than feature lists; uses plain language, avoids jargon |

### Score Ranges

- **90-100**: Excellent - Highly optimized landing page
- **70-89**: Good - Strong foundation with room for improvement
- **50-69**: Fair - Several conversion barriers need attention
- **30-49**: Poor - Significant optimization required
- **0-29**: Critical - Major overhaul needed

## Command Details

### `/landing-page-cro audit <url>`

Runs the complete CRO audit across all 10 dimensions. Returns a detailed report with scores, evidence, and prioritized recommendations.

**Output includes:**
- Overall CRO score (0-100)
- Per-dimension scores (0-10 each) with evidence
- Top 5 prioritized recommendations
- Suggested A/B test hypotheses
- Quick wins vs. long-term improvements

**Report:** Save output to `CRO-AUDIT-REPORT.md`

### `/landing-page-cro score <url>`

A rapid scoring pass that returns the overall CRO score and dimension breakdown without detailed recommendations. Use this for a quick health check.

**Output includes:**
- Overall CRO score (0-100)
- Per-dimension scores (0-10)
- Traffic light indicators (red/yellow/green per dimension)
- Top 3 weakest dimensions flagged

**Report:** Save output to `CRO-SCORE-REPORT.md`

### `/landing-page-cro copy-review`

Interactive copy review mode. Provide landing page copy (headline, subheadline, body, CTA text) and receive:
- Clarity score
- Benefit-vs-feature ratio analysis
- Emotional trigger assessment
- Suggested rewrites for weak sections
- CTA copy alternatives ranked by strength

**Report:** Save output to `CRO-COPY-REPORT.md`

### `/landing-page-cro ab-ideas <url>`

Analyzes the page and generates a prioritized list of A/B test ideas.

**Output includes:**
- 5-10 test hypotheses ranked by expected impact
- For each test: hypothesis statement, control vs. variant description, expected lift range, implementation difficulty (easy/medium/hard)
- Quick-win tests that can be implemented in under an hour
- High-impact tests that require more development effort

**Report:** Save output to `CRO-AB-IDEAS-REPORT.md`

## Scoring Methodology Details

### 1. Above-the-fold Clarity (0-10)
- **10**: Clear headline + subheadline + supporting visual that communicates the value prop instantly
- **7-9**: Headline is clear but subheadline or visual could be stronger
- **4-6**: Value prop requires reading below the fold to understand
- **1-3**: Headline is vague, generic, or focused on the company instead of the visitor
- **0**: No identifiable headline or value proposition

### 2. CTA Visibility and Copy Strength (0-10)
- **10**: Primary CTA is above the fold, high contrast, action-oriented text (e.g., "Start Free Trial"), repeated at logical intervals
- **7-9**: CTA is visible but copy could be more specific or compelling
- **4-6**: CTA exists but blends into the page or uses weak text like "Submit"
- **1-3**: CTA is hard to find or buried below extensive content
- **0**: No identifiable call to action

### 3. Social Proof Presence and Quality (0-10)
- **10**: Multiple forms of social proof - named testimonials with photos, recognizable logos, specific metrics, case study links
- **7-9**: Good social proof but missing specificity (e.g., no names on testimonials)
- **4-6**: Minimal social proof - generic "trusted by thousands" without evidence
- **1-3**: A single weak social proof element
- **0**: No social proof elements detected

### 4. Trust Signals (0-10)
- **10**: Security badges, partner logos, certifications, privacy policy link, money-back guarantee, and recognizable brand associations
- **7-9**: Several trust signals present but not comprehensive
- **4-6**: One or two basic trust elements (e.g., only a privacy link)
- **1-3**: Minimal trust indicators
- **0**: No trust signals detected

### 5. Form Simplicity (0-10)
- **10**: 1-3 fields, clear labels, single-step submission, no unnecessary required fields
- **7-9**: 4-5 fields with clear purpose for each
- **4-6**: 6-8 fields or multi-step without progress indicators
- **1-3**: 9+ fields or confusing layout
- **0**: Form is broken, excessively long, or requires account creation before showing value

### 6. Page Speed and Mobile Responsiveness (0-10)
- **10**: Sub-2-second load, fully responsive, no layout shifts, optimized images
- **7-9**: Loads in 2-4 seconds, mostly responsive
- **4-6**: Loads in 4-6 seconds or has minor mobile issues
- **1-3**: Slow load (6+ seconds) or significant mobile rendering problems
- **0**: Page fails to load or is completely broken on mobile

### 7. Visual Hierarchy and Scan-ability (0-10)
- **10**: Clear H1-H2-H3 structure, ample whitespace, logical content flow, scannable sections
- **7-9**: Good structure with minor hierarchy issues
- **4-6**: Walls of text, weak heading usage, or cluttered layout
- **1-3**: Disorganized layout that is difficult to scan
- **0**: No discernible visual hierarchy

### 8. Objection Handling (0-10)
- **10**: FAQ section, pricing transparency, comparison table, risk reversal (guarantee), and proactive answers to common concerns
- **7-9**: Addresses most objections but misses one key area
- **4-6**: Some objection handling but leaves important questions unanswered
- **1-3**: Minimal attempt to address buyer concerns
- **0**: No objection handling detected

### 9. Urgency and Scarcity (0-10)
- **10**: Authentic, specific urgency (limited offer with real deadline, limited spots with actual count) that feels genuine
- **7-9**: Some urgency elements that are credible
- **4-6**: Generic urgency ("Act now!") without specifics
- **1-3**: Fake or manipulative scarcity tactics
- **0**: No urgency elements (not always a negative - score contextually)

### 10. Copy Clarity and Benefit-driven Language (0-10)
- **10**: Every section leads with customer outcomes, plain language, specific benefits with evidence
- **7-9**: Mostly benefit-driven with occasional feature-only mentions
- **4-6**: Mix of benefits and features, some jargon
- **1-3**: Feature-heavy copy with little connection to customer outcomes
- **0**: Technical jargon, no identifiable benefits, or copy that focuses entirely on the company

## Report Output

Every command MUST save its output as a markdown report file:

| Command | Output File |
|---------|-------------|
| `audit` | `CRO-AUDIT-REPORT.md` |
| `score` | `CRO-SCORE-REPORT.md` |
| `copy-review` | `CRO-COPY-REPORT.md` |
| `ab-ideas` | `CRO-AB-IDEAS-REPORT.md` |

The report file should include:
- Date of analysis
- URL analyzed
- Overall CRO score with per-dimension breakdown
- Prioritized recommendations with A/B test hypotheses
- Quick wins vs long-term improvements

Always inform the user where the report was saved after completion.

## Important Notes

### SPA Limitation
This tool works best with server-rendered pages. Single-page applications (SPAs) that rely heavily on client-side JavaScript rendering may return incomplete results because the fetched HTML may not contain the full rendered content. If auditing an SPA, consider providing a pre-rendered version or a URL that serves server-side rendered HTML.

### Prerequisites
The Python scripts in the `scripts/` directory require the following packages:
- `requests` - HTTP requests
- `beautifulsoup4` - HTML parsing

Install with: `pip install requests beautifulsoup4`

### Rate Limiting
When auditing multiple pages, allow at least 2 seconds between requests to avoid being rate-limited by the target server.

### Data Privacy
This tool only reads publicly available information. It does not store, cache, or transmit any data from audited pages beyond the current session.

## References

- `references/cro-checklist.md` - Comprehensive CRO audit checklist with specific items for each dimension
- `references/psychological-triggers.md` - Psychological triggers for conversion with SaaS examples

## Scripts

### `scripts/cro_auditor.py`

Fetches a landing page and auto-scores it across all 10 CRO dimensions. Detects CTAs, forms, social proof elements, trust signals, and heading structure. Returns a score breakdown and top 5 recommendations.
