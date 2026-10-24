---
name: subscription-metrics
description: >
  Calculate and analyze SaaS subscription metrics. Computes MRR, ARR, CAC,
  LTV, churn rate, Rule of 40, burn multiple, and other critical SaaS KPIs.
  Provides health assessment and benchmarks. Use when the user mentions
  SaaS metrics, MRR, ARR, churn, CAC, LTV, Rule of 40, unit economics,
  subscription analytics, burn multiple, NRR, net revenue retention,
  or magic number.
---

# Subscription Metrics

Calculate, analyze, and benchmark SaaS subscription metrics to understand business health and growth trajectory.

## First Run

When a user runs `/subscription-metrics calculate`, ALWAYS display this
input summary before asking for any data:

"""
📊 SaaS Metrics Calculator

What I'll ask you (5 data groups, ~14 numbers, all for ONE month
unless marked yearly):

  Revenue data (this month):
    1. MRR at start of month ($)        → e.g. 100000
    2. New MRR this month ($)           → e.g. 15000
    3. Expansion MRR ($)                → e.g. 3000
    4. Contraction MRR ($)              → e.g. 1000
    5. Churned MRR ($)                  → e.g. 2000

  Customer counts (this month):
    6. Customers at start of month      → e.g. 200
    7. New customers this month         → e.g. 25
    8. Churned customers this month     → e.g. 8

  Costs (this month):
    9. Total S&M spend this month ($)   → e.g. 30000
   10. Gross margin (%)                 → e.g. 75 (70% is assumed if you skip)
   11. Monthly net burn ($) - optional (needed for burn multiple) → e.g. 40000
   12. Total operating costs this month ($) - optional (used to estimate
       net burn as operating costs - MRR when net burn is not provided) → e.g. 150000

  Growth (yearly):
   13. YoY revenue growth rate (%)      → e.g. 80
   14. EBITDA or profit margin (%)      → e.g. -20

  Optional, if you track them (12-month cohort figures):
   15. Trailing 12-month NRR (%)        → e.g. 104
   16. Trailing 12-month GRR (%)        → e.g. 88

  Type "skip" for any you don't know. Type 0 only if it really was zero
  (e.g. no downgrades this month).
  Type "demo" to see a sample report with example data first.

What you'll get:
  → MRR, ARR, churn rates, CAC, LTV, LTV:CAC ratio
  → Monthly NRR/GRR with a yearly estimate (or your 12-month figures)
  → Rule of 40, burn multiple, SaaS Quick Ratio
  → Traffic-light health assessment (GREEN/YELLOW/RED)
  → Saved to SAAS-METRICS-REPORT.md

Ready? Let's start - what was your MRR at the start of the month?
"""

### Demo Mode

If the user types "demo", use this data to generate a full sample report:

```json
{
  "beginning_mrr": 100000,
  "new_mrr": 15000,
  "expansion_mrr": 3000,
  "contraction_mrr": 1000,
  "churned_mrr": 2000,
  "customers_start": 200,
  "customers_new": 25,
  "customers_churned": 8,
  "total_sales_marketing_spend": 30000,
  "net_burn": 40000,
  "yoy_revenue_growth_pct": 80,
  "profit_margin_pct": -20
}
```

Write this JSON to a file and run the script on it (as in `calculate` step 5;
the script's own `--demo` uses different sample data). Save the demo report as
`SAAS-METRICS-REPORT-DEMO.md`.
After showing the summary, ask: "Want to run this with your own numbers now?"

### Skip Handling

If the user types "skip" for any input:
- Leave the field out of the JSON (or set it to `null` or `"skip"`). Never
  write 0 for a skipped value: 0 means "it was zero" and gets graded.
- The script shows every metric that needs the missing input as N/A,
  excludes it from the grade, and lists the input under "Not provided".
  Copy that list into the report.
- Metrics with a zero denominator (no customers at start, no churn or
  contraction for the Quick Ratio, no prior-quarter S&M for the Magic
  Number) are also N/A, never "Infinite" or 0.
- A letter grade needs at least 3 graded metrics; with fewer the grade is N/A.
- If gross margin is skipped, the script assumes 70% and says so under
  "Assumptions". Repeat that assumption in the report next to LTV and payback.
- Never block the entire report because one input is missing.

### Monthly vs Annual (MANDATORY)

NRR, GRR and revenue churn computed from one month of MRR movements are
MONTHLY rates. The script labels them "Monthly NRR" / "Monthly GRR" and
grades them on monthly-equivalent thresholds (monthly = annual^(1/12)):
annual GRR 90% = 99.13% a month, 80% = 98.16%; annual NRR 110% = 100.80%
a month, 100% = 100%. It also prints an annualized approximation
(monthly^12, e.g. 95% a month is about 54% a year).
- Always present these rows as monthly, and quote the annualized
  approximation with its caveat: it assumes the month repeats for 12 months.
- Never compare a monthly NRR/GRR with an annual benchmark yourself.
- If the user has real 12-month cohort NRR/GRR, pass them as `ttm_nrr_pct`
  / `ttm_grr_pct`; they replace the monthly rows and use annual thresholds.
- Monthly Revenue Churn and Monthly Net Revenue Churn are 100 minus monthly
  GRR / NRR. They share the same thresholds (so they always agree) and are
  counted once in the grade, through GRR and NRR.

## Commands

### `/subscription-metrics calculate`
Interactive metric calculator. Walk the user through providing their raw business data, then compute all relevant SaaS metrics.

**Steps:**
1. Ask for monthly revenue data (beginning MRR, new MRR, expansion MRR, contraction MRR, churned MRR)
2. Ask for customer counts (beginning of period, new, churned)
3. Ask for cost data (total S&M spend, gross margin, optional monthly net burn; total operating costs may be provided as a fallback - net burn is then estimated as operating costs - MRR)
4. Ask for growth data (YoY revenue growth rate, profit margin or EBITDA margin) and, if available, trailing 12-month NRR and GRR
5. Write the inputs to a JSON file and run `python3 <skill dir>/scripts/metrics_calculator.py input.json`. Never compute the metrics by hand. If the script exits with code 2, show the user the listed input errors and ask for corrected numbers
6. Present results in a structured table with traffic-light indicators, including the script's "Not provided", "Assumptions" and "Warnings" sections
7. Provide a short interpretation of each metric

**Output format:**
```
Metric                 | Value      | Status  | Benchmark
-----------------------|------------|---------|----------
MRR                    | $125,000   | GREEN   | -
ARR                    | $1,500,000 | GREEN   | -
Monthly Logo Churn     | 2.1%       | YELLOW  | <2%
Monthly Revenue Churn  | 0.80%      | GREEN   | <=0.87%/mo (= GRR 90%/yr)
Monthly NRR            | 101.20%    | GREEN   | >=100.80%/mo (= 110%/yr); ~115.4%/yr annualized
Monthly GRR            | 99.20%     | GREEN   | >=99.13%/mo (= 90%/yr); ~90.8%/yr annualized
Rule of 40             | N/A        | N/A     | Not provided: profit margin
...
```

**Report:** Save output to `SAAS-METRICS-REPORT.md`

### `/subscription-metrics health`
SaaS health scorecard. Generate a comprehensive health assessment based on provided metrics.

**Steps:**
1. Collect the same inputs as `calculate` (or reuse if already provided)
2. Run the script exactly as in `calculate` step 5. Never compute the metrics or the grade by hand
3. Use the script's GREEN / YELLOW / RED status for each metric
4. Report the script's overall health grade (A through F, or N/A when fewer than 3 metrics could be graded)
5. List the top 3 strengths and top 3 areas for improvement
6. Provide specific, actionable recommendations for each RED or YELLOW metric

**Report:** Save output to `SAAS-HEALTH-REPORT.md`

**Health grade scale** (computed over assessed metrics only - ARPU, CAC, LTV, MRR, and ARR are informational and excluded from the grade; N/A metrics are excluded; Monthly Revenue Churn and Monthly Net Revenue Churn mirror GRR and NRR and are counted once through them; fewer than 3 graded metrics gives grade N/A):
- A: ≥80% GREEN and 0 RED
- B: ≥60% GREEN and ≤1 RED
- C: ≥40% GREEN and ≤1 RED
- D: 2 RED, or 20-39% GREEN
- F: ≥3 RED, or <20% GREEN

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
✅ Metrics calculated - saved to SAAS-METRICS-REPORT.md

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
- `scripts/metrics_calculator.py` - Python calculator for all metrics with traffic-light assessment.
  Run it directly: `python3 <skill dir>/scripts/metrics_calculator.py data.json` (a JSON file using the
  BusinessData field names: `beginning_mrr`, `new_mrr`, `expansion_mrr`, `contraction_mrr`,
  `churned_mrr`, `customers_start`, `customers_new`, `customers_churned`,
  `total_sales_marketing_spend`, `gross_margin_pct`, `net_burn`, `total_operating_costs`,
  `yoy_revenue_growth_pct`, `profit_margin_pct`, and optional `ttm_nrr_pct`, `ttm_grr_pct`,
  `prev_quarter_sm_spend`, `current_quarter_net_new_arr`), pipe JSON via stdin, or use `--demo`
  for sample data. Every field is optional. Numbers may be strings ("15,000", "$15K");
  `gross_margin_pct` accepts 75 or 0.75. Impossible values (negative MRR, more churned customers
  than existed, a margin above 100%) stop the run with exit code 2 and a list of what to fix

## Guidelines

- Always clarify whether numbers are monthly or annual before calculating. If the script prints a warning that a value looks annual or quarterly, ask the user before reporting
- Use monthly figures as the base and annualize where needed (ARR = MRR x 12; retention rates compound: annual = monthly^12)
- When churn is discussed, always distinguish between logo churn and revenue churn
- For CAC, prefer blended CAC but note channel-specific if provided
- LTV calculations should default to the simple method unless the user has detailed cohort data
- Present metrics with proper formatting: percentages to one decimal, currency with appropriate scale ($K, $M)
- Traffic-light thresholds come from `references/saas-metrics-guide.md`
- Never present a single metric in isolation - always show related metrics for context (e.g., CAC with LTV and payback period)
- When recommending improvements, prioritize by impact and feasibility
