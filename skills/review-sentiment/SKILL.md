---
name: review-sentiment
description: >
  Analyze customer review sentiment for apps and businesses. Categorizes
  reviews by sentiment (positive, negative, neutral), identifies common
  themes, extracts feature requests and complaints, and provides
  actionable insights. Use when the user mentions review analysis,
  customer feedback analysis, sentiment analysis, review mining,
  or wants to understand customer sentiment from reviews.
---

## First Run

When a user runs `/review-sentiment analyze`, ALWAYS display this
guidance before asking for input:

"""
📝 Review Sentiment Analyzer

What I'll need:
  Paste your customer reviews below — one per line or separated
  by blank lines. Works with any source: app stores, G2, Capterra,
  Yelp, Google, support tickets, survey responses.

  Minimum: 5 reviews for meaningful patterns
  Ideal: 20-50 reviews for strong analysis
  Format: Plain text. Star ratings optional but helpful.

  Type "demo" to see analysis on 10 sample reviews first.

What you'll get:
  → Sentiment breakdown (positive/negative/neutral %)
  → Theme extraction (UX, pricing, support, bugs, etc.)
  → Top complaints and praise patterns
  → Feature requests ranked by frequency
  → Saved to REVIEW-SENTIMENT-REPORT.md

Paste your reviews below:
"""

### Demo Mode

If the user types "demo", use these 10 sample reviews:

```
"Love the new dashboard! So much easier to navigate now."
"Terrible customer support. Waited 3 days for a response."
"It's okay. Does what I need but pricing feels high."
"App crashes every time I try to export a PDF. Very frustrating."
"Onboarding was smooth and the docs are great."
"The automation features saved us hours every week."
"Can't believe there's still no dark mode in 2026."
"Best tool I've found for small team project management."
"Billing is confusing. Got charged twice last month."
"Fast, reliable, and the API is well documented."
```

Save the demo report as `REVIEW-SENTIMENT-REPORT-DEMO.md`.
After showing the summary, ask: "Want to analyze your own reviews now?"

# Review Sentiment Analyzer

Analyze customer reviews to extract sentiment, identify themes, surface feature requests and complaints, and generate actionable summaries. Works with reviews from any source - app stores, Google, Yelp, G2, Capterra, or any text-based feedback.

## Commands

### `/review-sentiment analyze` - Analyze Provided Reviews

Performs sentiment analysis on a set of review texts. Each review is classified by sentiment and tagged with detected themes.

**Analyze Flow:**
1. Accept review texts (paste reviews or provide structured data)
2. Classify each review: positive, negative, or neutral
3. Assign a confidence score (0-1) per review
4. Detect themes in each review (UX/UI, Performance, Pricing, etc.)
5. Calculate aggregate sentiment distribution
6. Build keyword frequency table
7. Generate executive summary

**Input format:**
- Plain text reviews (one per line or separated by blank lines)
- Structured data with optional star ratings

**Output per review:**
- Sentiment label: positive, negative, or neutral
- Confidence score: 0.0 to 1.0
- Detected themes: list of matched theme categories
- Key phrases: notable words or phrases extracted

**Aggregate output:**
- Positive / negative / neutral percentages
- Top themes by frequency
- Keyword frequency table (top 20)
- Sentiment trend (if timestamps provided)

**Report:** Save output to `REVIEW-SENTIMENT-REPORT.md`

### `/review-sentiment themes` - Extract Common Themes

Focused analysis that groups reviews by theme and highlights patterns.

**Theme categories:**
- UX/UI - design, navigation, layout, ease of use
- Performance - speed, loading, crashes, reliability
- Pricing - cost, value, plans, billing
- Support - customer service, response time, helpfulness
- Features - functionality, capabilities, missing features
- Bugs - errors, glitches, broken functionality
- Onboarding - setup, getting started, documentation, learning curve

**Output includes:**
- Theme distribution chart (percentage of reviews mentioning each theme)
- Top positive themes (what users love)
- Top negative themes (what users complain about)
- Feature requests extracted from reviews
- Complaint patterns with frequency

**Report:** Save output to `REVIEW-THEMES-REPORT.md`

### `/review-sentiment summary` - Executive Summary

Generates a concise executive summary suitable for stakeholders.

**Summary includes:**
- Overall sentiment score (1-5 scale)
- One-paragraph sentiment overview
- Top 3 strengths (most praised aspects)
- Top 3 weaknesses (most criticized aspects)
- Feature requests ranked by mention frequency
- Recommended actions based on review patterns
- Comparison benchmarks (if industry data available)

**Report:** Save output to `REVIEW-SUMMARY-REPORT.md`

## How It Works

This skill uses keyword matching and pattern-based heuristics to classify review sentiment. It does not require external APIs or machine learning services.

**Sentiment classification approach:**
- Analyzes positive and negative indicator words and phrases
- Considers negation patterns (e.g., "not good" flips positive to negative)
- Weighs intensity modifiers (e.g., "very", "extremely", "slightly")
- Uses star ratings as a signal when available
- Assigns confidence based on clarity of sentiment signals

**Theme detection approach:**
- Matches reviews against curated keyword lists per theme category
- Supports multi-theme tagging (a single review can match multiple themes)
- Extracts specific feature mentions and complaint patterns

## Example Usage

```
User: /review-sentiment analyze

Here are our latest app reviews:

"Love the new dashboard! So much easier to navigate now. The charts
are beautiful and load instantly."

"Terrible customer support. Waited 3 days for a response and they
didn't even solve my problem."

"It's okay. Does what I need but the pricing feels high for what
you get. Would be nice to have a cheaper plan."

"App crashes every time I try to export a PDF. Very frustrating.
This has been broken for weeks."

"Onboarding was smooth and the docs are great. Had everything
set up in under 10 minutes."

Output:
- Review 1: Positive (0.92) - Themes: UX/UI, Performance
- Review 2: Negative (0.95) - Themes: Support
- Review 3: Neutral (0.55) - Themes: Pricing, Features
- Review 4: Negative (0.90) - Themes: Bugs, Performance
- Review 5: Positive (0.88) - Themes: Onboarding

Aggregate: 40% Positive, 40% Negative, 20% Neutral
Top Themes: Support, Pricing, UX/UI, Bugs, Onboarding
```

## Limitations

- Sentiment classification is heuristic-based (keyword and pattern matching), not ML-based. Sarcasm, irony, and nuanced language may be misclassified.
- Works best with English-language reviews.
- Theme detection relies on curated keyword lists; highly domain-specific terminology may not be captured without customization.
- For best results, provide at least 10-20 reviews to get meaningful aggregate statistics.

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
✅ Sentiment analysis complete — saved to REVIEW-SENTIMENT-REPORT.md

Reviews analyzed: [N]
Sentiment: [X]% positive, [X]% negative, [X]% neutral

Top themes:
  👍 Most praised: [theme]
  👎 Most criticized: [theme]
  💡 Top feature request: [request]

Full report with per-review breakdown → open REVIEW-SENTIMENT-REPORT.md
"""

NEVER dump the full report in chat. The file is the deliverable.

## References

- `references/sentiment-categories.md` - Sentiment scoring definitions, theme categories, and example classifications

## Scripts

- `scripts/sentiment_analyzer.py` - Sentiment analysis engine with keyword-based classification
