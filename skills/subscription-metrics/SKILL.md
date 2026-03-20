---
name: subscription-metrics
description: >
  Calculate and analyze SaaS subscription metrics. Computes MRR, ARR, CAC,
  LTV, churn rate, Rule of 40, burn multiple, and other critical SaaS KPIs.
  Provides health assessment and benchmarks. Use when the user mentions
  SaaS metrics, MRR, ARR, churn, CAC, LTV, Rule of 40, unit economics,
  or subscription analytics.
---

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

### `/subscription-metrics health`
SaaS health scorecard. Generate a comprehensive health assessment based on provided metrics.

**Steps:**
1. Collect the same inputs as `calculate` (or reuse if already provided)
2. Compute all metrics
3. Score each metric as GREEN / YELLOW / RED against industry benchmarks
4. Produce an overall health grade (A through F)
5. List the top 3 strengths and top 3 areas for improvement
6. Provide specific, actionable recommendations for each RED or YELLOW metric

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

## Report Output

Every command MUST save its output as a markdown report file:

| Command | Output File |
|---------|-------------|
| `calculate` | `SAAS-METRICS-REPORT.md` |
| `health` | `SAAS-HEALTH-REPORT.md` |
| `benchmark` | `SAAS-BENCHMARK-REPORT.md` |
| `forecast` | `SAAS-FORECAST-REPORT.md` |

The report file should include:
- Date of analysis
- Company name and stage
- Full metric calculations with traffic-light indicators
- Benchmark comparisons
- Health grade and recommendations

Always inform the user where the report was saved after completion.

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
