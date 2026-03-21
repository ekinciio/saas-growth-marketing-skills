---
name: plg-funnel-analyzer
description: >
  Analyze and optimize Product-Led Growth funnels. Evaluates acquisition,
  activation, retention, revenue, and referral stages. Provides benchmark
  comparisons and identifies funnel leaks. Use when the user mentions PLG,
  product-led growth, funnel analysis, activation rate, user onboarding
  metrics, or growth loops.
---

## First Run

When a user runs `/plg-funnel-analyzer audit`, ALWAYS display this input
summary before asking for any data:

"""
📊 PLG Funnel Analyzer

What I'll ask you (6 numbers):
  1. Signup-to-Active rate (%)       → e.g. 25
  2. Free-to-Paid conversion (%)    → e.g. 5
  3. Monthly churn rate (%)          → e.g. 4
  4. Net Revenue Retention (%)       → e.g. 105
  5. Time-to-Value (days)            → e.g. 3
  6. Payback period (months)         → e.g. 12

  Type "skip" for any you don't have.
  Type "demo" to see a sample report with example data first.

What you'll get:
  → Traffic-light per metric (RED/YELLOW/GREEN)
  → Overall funnel health grade (A through F)
  → Biggest funnel leak identified
  → 5 prioritized fixes with expected impact
  → Saved to PLG-FUNNEL-AUDIT-REPORT.md

Ready? What's your Signup-to-Active rate?
"""

### Demo Mode

If the user types "demo", use this data to generate a full sample report:

```json
{
  "signup_to_active": 18,
  "free_to_paid": 3,
  "monthly_churn": 7,
  "nrr": 98,
  "time_to_value_days": 5,
  "payback_months": 15
}
```

Save the demo report as `PLG-FUNNEL-AUDIT-REPORT-DEMO.md`.
After showing the summary, ask: "Want to run this with your own metrics now?"

### Skip Handling

If the user types "skip" for any metric:
- Mark it as "Not provided" in the report
- Benchmark and score all available metrics
- Note which funnel stages could not be assessed
- Never block the report because one metric is missing

# PLG Funnel Analyzer

Analyze and optimize Product-Led Growth funnels using the AARRR (Pirate Metrics) framework. Compares your metrics against industry benchmarks, identifies the biggest funnel leaks, and generates prioritized recommendations to improve conversion at every stage.

## Commands

| Command | Description |
|---------|-------------|
| `/plg-funnel-analyzer audit` | Full PLG funnel audit (interactive - prompts for your metrics) |
| `/plg-funnel-analyzer benchmark <category>` | Compare your metrics to industry benchmarks by category |
| `/plg-funnel-analyzer loops` | Growth loop identification and optimization suggestions |

## Full Audit Flow

The full audit (`/plg-funnel-analyzer audit`) follows an interactive process:

### Step 1: Metric Collection
Prompt the user for key PLG metrics:
- **Signup-to-Active rate** - Percentage of signups who become active users
- **Free-to-Paid conversion rate** - Percentage of free users who convert to paid
- **Monthly churn rate** - Percentage of customers who cancel per month
- **Net Revenue Retention (NRR)** - Revenue retained from existing customers including expansion
- **Time-to-Value (days)** - Days from signup to the user experiencing core value
- **Payback period (months)** - Months to recover customer acquisition cost

### Step 2: Benchmark Comparison
Compare each metric against PLG SaaS industry benchmarks using a traffic light system:
- **GREEN** - Top 25% performance
- **YELLOW** - Median performance
- **RED** - Bottom 25% performance

### Step 3: Funnel Leak Detection
Identify the stage with the largest drop-off and the greatest potential for improvement. The biggest leak is the metric furthest below median in relative terms.

### Step 4: Recommendations
Generate prioritized, actionable recommendations to address the weakest points in the funnel. Recommendations are ordered by estimated impact.

## Benchmark Categories

Use `/plg-funnel-analyzer benchmark <category>` with one of these categories:

| Category | What It Covers |
|----------|---------------|
| `activation` | Signup-to-active rates, time-to-value, aha moment benchmarks |
| `conversion` | Free-to-paid rates, trial conversion, upgrade triggers |
| `retention` | Monthly/annual churn rates, cohort retention curves |
| `revenue` | NRR, expansion revenue, ARPU, payback period |
| `referral` | Viral coefficient, referral program conversion, NPS benchmarks |
| `all` | Complete benchmark table across all categories |

## PLG SaaS Industry Benchmarks

| Metric | Bottom 25% | Median | Top 25% |
|--------|-----------|--------|---------|
| Signup-to-Active | <15% | 25% | >40% |
| Free-to-Paid | <2% | 5% | >10% |
| Monthly Churn | >8% | 5% | <3% |
| NRR | <95% | 105% | >120% |
| Time-to-Value | >7 days | 3 days | <1 day |
| Payback Period | >18 mo | 12 mo | <6 mo |

## Command Details

### `/plg-funnel-analyzer audit`

Interactive full funnel audit. Prompts the user for their current metrics and returns a comprehensive assessment.

**Output includes:**
- Traffic light assessment for each metric (RED/YELLOW/GREEN)
- Overall funnel health grade (A through F)
- Biggest funnel leak identified with estimated revenue impact
- 5 prioritized recommendations ranked by expected impact
- Suggested experiments for each recommendation

**Report:** Save output to `PLG-FUNNEL-AUDIT-REPORT.md`

**Example interaction:**
```
> /plg-funnel-analyzer audit

Please provide your PLG metrics (enter "skip" for any you do not have):

1. Signup-to-Active rate (%): 18
2. Free-to-Paid conversion (%): 3
3. Monthly churn rate (%): 7
4. Net Revenue Retention (%): 98
5. Time-to-Value (days): 5
6. Payback period (months): 15

Analyzing...
```

### `/plg-funnel-analyzer benchmark <category>`

Returns detailed benchmark data for the specified category with context on what top performers do differently.

**Report:** Save output to `PLG-BENCHMARK-REPORT.md`

**Example:**
```
> /plg-funnel-analyzer benchmark activation

ACTIVATION BENCHMARKS (PLG SaaS)
---------------------------------
Signup-to-Active:  Bottom 25%: <15%  |  Median: 25%  |  Top 25%: >40%
Time-to-Value:     Bottom 25%: >7d   |  Median: 3d   |  Top 25%: <1d

What top performers do differently:
- Progressive onboarding (show value before asking for setup)
- Personalized first-run experience based on use case
- In-app guidance that leads to the aha moment in < 5 minutes
...
```

### `/plg-funnel-analyzer loops`

Identifies potential growth loops in the user's product and suggests optimization strategies.

**Growth loop types analyzed:**
- **Viral loops** - User invites create new users (collaboration, sharing)
- **Content loops** - User-generated content attracts new users via search
- **Data network effects** - Product improves as more users contribute data
- **Marketplace loops** - Supply and demand sides reinforce each other
- **Habit loops** - Retention-driven engagement that reduces churn

**Output includes:**
- Applicable growth loop types based on product description
- Current loop health assessment
- Specific tactics to strengthen each loop
- Metrics to track loop effectiveness

**Report:** Save output to `PLG-GROWTH-LOOPS-REPORT.md`

## AARRR Framework Reference

The audit maps to the AARRR (Pirate Metrics) framework:

| Stage | Key Question | Primary Metric |
|-------|-------------|---------------|
| **Acquisition** | How do users find you? | Signup volume, CAC |
| **Activation** | Do users experience core value? | Signup-to-Active, Time-to-Value |
| **Retention** | Do users come back? | Monthly churn, DAU/MAU |
| **Revenue** | Do users pay? | Free-to-Paid, NRR, ARPU |
| **Referral** | Do users tell others? | Viral coefficient, NPS |

## Health Grading Scale

The overall funnel health grade is calculated from the aggregate benchmark performance:

- **A (Excellent)** - 5-6 metrics in GREEN range
- **B (Good)** - 3-4 metrics in GREEN, rest YELLOW
- **C (Fair)** - Mostly YELLOW with 1-2 GREEN
- **D (Needs Work)** - Mix of YELLOW and RED
- **F (Critical)** - 3+ metrics in RED range

## Important Notes

### Data Requirements
This tool works best when you can provide actual metrics. If some metrics are unavailable, the tool will still provide benchmark data and general recommendations, but the analysis will be less precise.

### Benchmark Context
Benchmarks represent aggregated data across PLG SaaS companies. Your specific vertical, company stage, and pricing model may shift what "good" looks like. Use these as directional guides, not absolute targets.

### Privacy
No metrics or data entered during the audit are stored, cached, or transmitted beyond the current session.

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
✅ Funnel audit complete — saved to PLG-FUNNEL-AUDIT-REPORT.md

Funnel Health: Grade [A-F]
Biggest Leak: [stage] — [metric] is [value] (benchmark: [benchmark])

Assessment:
  🟢 [Best metric]
  🔴 [Worst metric]
  🟡 [Borderline metric]

Full report with benchmarks and 5 prioritized fixes → open PLG-FUNNEL-AUDIT-REPORT.md
"""

NEVER dump the full report in chat. The file is the deliverable.

## References

- `references/plg-metrics.md` - AARRR framework definitions and metric guidance
- `references/funnel-benchmarks.md` - Detailed PLG SaaS benchmark data

## Scripts

### `scripts/funnel_analyzer.py`

Accepts user metrics, runs benchmark comparison with traffic light scoring, detects the biggest funnel leak, and generates prioritized recommendations. Includes standalone demo with example data.
