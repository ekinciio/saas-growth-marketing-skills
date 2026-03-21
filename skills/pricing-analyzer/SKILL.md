---
name: pricing-analyzer
description: >
  Analyze and optimize SaaS pricing strategy. Evaluates pricing tiers,
  feature gating, willingness-to-pay, and competitive pricing positioning.
  Use when the user mentions pricing strategy, pricing tiers, pricing page,
  willingness to pay, freemium vs paid, feature gating, or pricing optimization.
---

## First Run

When a user runs `/pricing-analyzer audit`, ALWAYS display this input
summary before asking for any data:

"""
📊 Pricing Analyzer

What I'll ask you:

  Your pricing:
    1. Number of tiers              → e.g. 3
    2. Price per tier ($/mo)        → e.g. 0, 29, 99
    3. Key features per tier        → brief list each

  Business context:
    4. Average deal size ($/mo)     → e.g. 45
    5. Most popular tier            → e.g. "Pro"
    6. Free-to-paid conversion (%)  → e.g. 4

  Competitor pricing (optional):
    7. Competitor names + prices    → entered manually

  Type "skip" for any you don't have.
  Type "demo" to see a sample report first.

What you'll get:
  → Pricing model identification and assessment
  → Feature gating analysis
  → Competitive positioning map
  → Tier optimization recommendations
  → Saved to PRICING-AUDIT-REPORT.md

Ready? How many pricing tiers do you have?
"""

### Demo Mode

If the user types "demo", use this data to generate a full sample report:

```json
{
  "tiers": [
    {"name": "Free", "price": 0, "features": ["3 projects", "1 user", "basic reports"]},
    {"name": "Pro", "price": 29, "features": ["unlimited projects", "5 users", "advanced reports", "integrations"]},
    {"name": "Business", "price": 99, "features": ["everything in Pro", "unlimited users", "SSO", "priority support"]}
  ],
  "avg_deal_size": 45,
  "most_popular_tier": "Pro",
  "free_to_paid_pct": 4,
  "competitors": [
    {"name": "Competitor A", "prices": [0, 19, 79]},
    {"name": "Competitor B", "prices": [15, 49, 149]}
  ]
}
```

Save the demo report as `PRICING-AUDIT-REPORT-DEMO.md`.
After showing the summary, ask: "Want to run this with your own pricing data now?"

### Skip Handling

If the user types "skip" for any input:
- Proceed with available data
- Note which analyses were limited by missing data
- Never block the report because competitor data is missing

# Pricing Analyzer

Evaluate and optimize SaaS pricing strategy through tier analysis, competitive positioning, willingness-to-pay research, and feature gating recommendations.

## Commands

### `/pricing-analyzer audit`

Interactive pricing strategy audit. Walk the user through a comprehensive evaluation of their current pricing.

**Steps:**
1. Ask for current pricing structure (number of tiers, prices, billing options)
2. Ask for features included in each tier
3. Ask for key business metrics (average deal size, conversion rate from free to paid, most popular tier)
4. Ask for target customer segments and their approximate budgets
5. Evaluate pricing against the six models in `references/pricing-models.md`
6. Identify gaps, misalignments, and optimization opportunities
7. Generate a pricing audit report with specific recommendations

**Output format:**
```
Pricing Audit Report
====================

Current Structure:
  Model:        [Identified pricing model]
  Tiers:        [Number of tiers]
  Price Range:  $X - $Y/mo

Strengths:
  - [Strength 1]
  - [Strength 2]

Issues Found:
  1. [Issue] - Impact: HIGH - Recommendation: [Fix]
  2. [Issue] - Impact: MEDIUM - Recommendation: [Fix]

Feature Gating Assessment:
  [Analysis of which features are in which tiers]

Recommended Changes:
  [Prioritized list of pricing changes with expected impact]
```

**Report:** Save output to `PRICING-AUDIT-REPORT.md`

### `/pricing-analyzer compare`

Competitive pricing comparison based on manually entered data.

**Steps:**
1. Ask the user to provide their own pricing tiers and features
2. Ask the user to enter competitor pricing data (names, tiers, prices, key features)
3. Run comparison analysis using `scripts/pricing_analyzer.py`
4. Generate a positioning map showing where each product sits on the price-to-value spectrum
5. Identify pricing gaps and opportunities in the competitive landscape
6. Recommend positioning adjustments

**Important:** All competitor pricing data is entered manually by the user. This skill does not automatically fetch competitor prices from external sources.

**Output includes:**
- Side-by-side pricing comparison table
- Price-per-feature analysis
- Positioning map (text-based)
- Gap analysis highlighting underserved price points
- Recommended positioning strategy

**Report:** Save output to `PRICING-COMPARE-REPORT.md`

### `/pricing-analyzer tiers`

Generate tier structure recommendations based on the user's product and market.

**Steps:**
1. Ask for the full feature list of the product
2. Ask which features drive the most value and which are table stakes
3. Ask about target customer segments (startup, SMB, mid-market, enterprise)
4. Ask about current conversion and upgrade patterns (if available)
5. Recommend optimal number of tiers (typically 3-4)
6. Assign features to tiers based on value and segment alignment
7. Suggest price anchoring strategy and tier naming

**Tier design principles applied:**
- Each tier should have a clear target persona
- The gap between tiers should feel justified by the features added
- One tier should serve as the obvious "best value" anchor (typically the middle tier)
- Enterprise tier should include human-touch elements (support, onboarding, SLA)
- Free or lowest tier should deliver enough value to demonstrate the product but create natural upgrade triggers

**Output includes:**
- Recommended tier structure with features per tier
- Pricing guidance (ranges, not exact numbers unless data supports it)
- Upgrade trigger identification (features that motivate tier upgrades)
- Tier naming suggestions

**Report:** Save output to `PRICING-TIERS-REPORT.md`

### `/pricing-analyzer sensitivity`

Guide the user through a Van Westendorp Price Sensitivity analysis.

**Steps:**
1. Explain the Van Westendorp methodology and the four questions
2. Help the user design the survey (target audience, sample size, distribution)
3. If the user has survey results, input the data into `scripts/pricing_analyzer.py`
4. Calculate the four price intersection points:
   - OPP (Optimal Price Point): Intersection of "too cheap" and "too expensive"
   - IDP (Indifference Price Point): Intersection of "not a bargain" and "not expensive"
   - PME (Point of Marginal Expensiveness): Intersection of "not a bargain" and "too expensive"
   - PMC (Point of Marginal Cheapness): Intersection of "too cheap" and "not expensive"
5. Define the acceptable price range (PMC to PME)
6. Recommend a price point within the optimal range

**Van Westendorp four questions:**
1. At what price would this product be so cheap you would question its quality?
2. At what price would this product be a bargain - a great buy for the money?
3. At what price would this product start to seem expensive but you would still consider it?
4. At what price would this product be too expensive to consider?

**Output includes:**
- Price sensitivity chart description (text-based)
- Four intersection points with values
- Acceptable price range
- Optimal price recommendation with rationale

**Report:** Save output to `PRICING-SENSITIVITY-REPORT.md`

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
✅ Pricing audit complete — saved to PRICING-AUDIT-REPORT.md

Model: [identified pricing model]
Tiers: [N] tiers ($[low] - $[high]/mo)

Key findings:
  1. [Top pricing issue or strength]
  2. [Second finding]
  3. [Third finding]

Full report with tier recommendations and positioning → open PRICING-AUDIT-REPORT.md
"""

NEVER dump the full report in chat. The file is the deliverable.

## Key Reference Files

- `references/pricing-models.md` - Six SaaS pricing models with pros, cons, examples, and implementation guidance
- `scripts/pricing_analyzer.py` - Python analyzer for tier gaps, competitive positioning, and Van Westendorp calculations

## Guidelines

- Never recommend a specific price without data to support it - provide ranges and frameworks instead
- Pricing changes are high-impact decisions; always recommend A/B testing or gradual rollouts
- Consider the psychological aspects of pricing: charm pricing ($49 vs $50), anchoring, and decoy effects
- Annual billing discounts of 15-20% are standard in SaaS; recommend this if not already offered
- Feature gating should align with customer segments, not arbitrarily restrict value
- Always ask about billing frequency (monthly vs annual) and its impact on cash flow
- When comparing competitors, note that public pricing pages may not reflect actual negotiated prices for enterprise deals
- Pricing should be revisited at least annually, or when there are significant changes in the product, market, or competitive landscape
- Per-seat pricing works well when each seat gets clear individual value; usage-based works when consumption varies significantly between customers
