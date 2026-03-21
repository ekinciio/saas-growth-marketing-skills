---
name: subscription-metrics
description: >
  Calculate and analyze SaaS subscription metrics. Computes MRR, ARR, CAC,
  LTV, churn rate, Rule of 40, burn multiple, and other critical SaaS KPIs.
  Provides health assessment and benchmarks. Use when the user mentions
  SaaS metrics, MRR, ARR, churn, CAC, LTV, Rule of 40, unit economics,
  or subscription analytics.
---

## First Run

When a user runs `/subscription-metrics calculate`, ALWAYS display this
input summary before asking for any data:

"""
📊 SaaS Metrics Calculator

What I'll ask you (4 data groups, ~10 numbers):

  Revenue data:
    1. New MRR this month ($)           → e.g. 15000
    2. Expansion MRR ($)                → e.g. 3000
    3. Contraction MRR ($)              → e.g. 1000
    4. Churned MRR ($)                  → e.g. 2000

  Customer counts:
    5. Customers at start of month      → e.g. 200
    6. New customers this month         → e.g. 25
    7. Churned customers this month     → e.g. 8

  Costs:
    8. Total S&M spend this month ($)   → e.g. 30000

  Growth:
    9. YoY revenue growth rate (%)      → e.g. 80
   10. EBITDA or profit margin (%)      → e.g. -20

  Type "skip" for any you don't have.
  Type "demo" to see a sample report with example data first.

What you'll get:
  → MRR, ARR, churn rates, CAC, LTV, LTV:CAC ratio
  → Rule of 40, burn multiple, SaaS Quick Ratio
  → Traffic-light health assessment (GREEN/YELLOW/RED)
  → Saved to SAAS-METRICS-REPORT.md

Ready? Let's start — what's your New MRR this month?
"""

### Demo Mode

If the user types "demo", use this data to generate a full sample report:

```json
{
  "new_mrr": 15000,
  "expansion_mrr": 3000,
  "contraction_mrr": 1000,
  "churned_mrr": 2000,
  "customers_start": 200,
  "new_customers": 25,
  "churned_customers": 8,
  "total_sm_spend": 30000,
  "yoy_growth_rate": 80,
  "profit_margin": -20
}
```

Save the demo report as `SAAS-METRICS-REPORT-DEMO.md`.
After showing the summary, ask: "Want to run this with your own numbers now?"

### Skip Handling

If the user types "skip" for any metric:
- Mark it as "Not provided" in the report
- Calculate all metrics that are possible with available data
- Note which metrics could not be calculated and why
- Never block the entire report because one input is missing

# Subscription Metrics

Calculate, analyze, and benchmark SaaS subscription metrics to understand business health and growth trajectory.

## Commands

### `/subscription-metrics calculate`
Interactive metric calculator. Walk the user through providing their raw business data, then compute all relevant SaaS metrics.

**Steps:**
1. Ask for monthly revenue data (new MRR, expansion MRR, contraction MRR, churned MRR)
2. Ask for customer counts (beginning of period, new, churned, end of period)
3. Ask for cost data (total S&M spend, total operating costs, optional: CAC by channel)
4. Ask for growth data (YoY revenue growth rate, profit margin or EBITDA margin)
5. Run `scripts/metrics_calculator.py` logic to compute all metrics
6. Present results in a structured table with traffic-light indicators
7. Provide a short interpretation of each metric

**Output format:**
```
Metric                 | Value      | Status  | Benchmark
-----------------------|------------|---------|----------
MRR                    | $125,000   | GREEN   | -
ARR                    | $1,500,000 | GREEN   | -
Monthly Logo Churn     | 2.1%       | YELLOW  | <2%
Monthly Revenue Churn  | 1.8%       | GREEN   | <2%
Net Revenue Retention   | 108%       | GREEN   | >100%
...
```

**Report:** Save output to `SAAS-METRICS-REPORT.md`

### `/subscription-metrics health`
SaaS health scorecard. Generate a comprehensive health assessment based on provided metrics.

**Steps:**
1. Collect the same inputs as `calculate` (or reuse if already provided)
2. Compute all metrics
3. Score each metric as GREEN / YELLOW / RED against industry benchmarks
4. Produce an overall health grade (A through F)
5. List the top 3 strengths and top 3 areas for improvement
6. Provide specific, actionable recommendations for each RED or YELLOW metric

**Report:** Save output to `SAAS-HEALTH-REPORT.md`

**Health grade scale:**
- A: 80-100% of metrics GREEN
- B: 60-79% GREEN, no RED
- C: 40-59% GREEN or 1 RED
- D: 20-39% GREEN or 2+ RED
- F: <20% GREEN or critical metrics RED

### `/subscription-metrics benchmark`
Compare metrics to industry benchmarks segmented by stage and vertical.

**Steps:**
1. Ask for company stage: Seed, Series A, Series B, Growth, Scale
2. Ask for vertical: horizontal SaaS, vertical SaaS, infrastructure, dev tools, fintech, healthtech
3. Collect current metrics or reuse from prior calculation
4. Compare each metric against stage-appropriate and vertical-appropriate benchmarks
5. Show percentile ranking where possible (top 10%, top 25%, median, below median)
6. Highlight where the company over-performs or under-performs relative to peers

**Report:** Save output to `SAAS-BENCHMARK-REPORT.md`

**Benchmark ranges by stage (MRR example):**
- Seed: $5K-$50K MRR typical
- Series A: $50K-$250K MRR typical
- Series B: $250K-$1M MRR typical
- Growth: $1M-$5M MRR typical
- Scale: $5M+ MRR typical

### `/subscription-metrics forecast`
Simple MRR/ARR forecast based on current trajectory and assumptions.

**Steps:**
1. Collect current MRR and growth rate (or derive from historical data)
2. Ask for assumptions: expected monthly growth rate, expected churn rate changes, planned expansion revenue
3. Project MRR and ARR for 6, 12, 18, and 24 months
4. Show optimistic (1.5x growth assumption), base, and pessimistic (0.5x growth assumption) scenarios
5. Calculate months to key milestones ($100K MRR, $1M ARR, etc.)
6. Flag if current burn rate is unsustainable given the forecast

**Output includes:**
- Monthly MRR projection table (3 scenarios)
- ARR milestones timeline
- Revenue growth chart description (text-based)
- Cash runway estimate if burn data is provided

**Report:** Save output to `SAAS-FORECAST-REPORT.md`

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
✅ Metrics calculated — saved to SAAS-METRICS-REPORT.md

Health Grade: [A-F]
MRR: $[X] | ARR: $[X] | Monthly Churn: [X]%

Highlights:
  🟢 [Strongest metric + value]
  🔴 [Weakest metric + value]
  🔴 [Second weakest + value]

Full dashboard with all metrics and benchmarks → open SAAS-METRICS-REPORT.md
"""

NEVER dump the full report in chat. The file is the deliverable.

## Key Reference Files

- `references/saas-metrics-guide.md` - Detailed definitions, formulas, benchmarks, and improvement tactics for every SaaS metric
- `scripts/metrics_calculator.py` - Python calculator for all metrics with traffic-light assessment

## Guidelines

- Always clarify whether numbers are monthly or annual before calculating
- Use monthly figures as the base and annualize where needed (ARR = MRR x 12)
- When churn is discussed, always distinguish between logo churn and revenue churn
- For CAC, prefer blended CAC but note channel-specific if provided
- LTV calculations should default to the simple method unless the user has detailed cohort data
- Present metrics with proper formatting: percentages to one decimal, currency with appropriate scale ($K, $M)
- Traffic-light thresholds come from `references/saas-metrics-guide.md`
- Never present a single metric in isolation - always show related metrics for context (e.g., CAC with LTV and payback period)
- When recommending improvements, prioritize by impact and feasibility
