---
name: retention-playbook
description: >
  Identify churn risks and implement retention strategies for SaaS products.
  Provides churn signal detection, win-back campaign frameworks, and engagement
  scoring models. Use when the user mentions churn, retention, win-back,
  engagement scoring, customer health, or reducing cancellations.
---

## First Run

When a user runs `/retention-playbook diagnose`, ALWAYS display this input
summary before asking for any data:

"""
📊 Retention Playbook

What I'll ask you:

  Product context:
    1. SaaS vertical                → e.g. "project management"
    2. Pricing model                → e.g. "per-seat"
    3. Avg contract length          → e.g. "monthly"

  Churn metrics:
    4. Monthly logo churn (%)       → e.g. 5
    5. Monthly revenue churn (%)    → e.g. 3
    6. Net Revenue Retention (%)    → e.g. 102

  Current tracking:
    7. Which churn signals do you track? → e.g. "login frequency, support tickets"

  Type "skip" for any you don't have.
  Type "demo" to see a sample diagnosis first.

What you'll get:
  → Churn categorization (preventable vs structural vs competitive)
  → Top 3 churn drivers identified
  → Prioritized retention action plan with timeline
  → Saved to RETENTION-DIAGNOSIS-REPORT.md

Ready? What's your SaaS vertical?
"""

### Demo Mode

If the user types "demo", use this data to generate a full sample report:

```json
{
  "vertical": "project management SaaS",
  "pricing_model": "per-seat",
  "avg_contract": "monthly",
  "monthly_logo_churn": 6.5,
  "monthly_revenue_churn": 4.2,
  "nrr": 97,
  "signals_tracked": ["login frequency", "support tickets"]
}
```

Save the demo report as `RETENTION-DIAGNOSIS-REPORT-DEMO.md`.
After showing the summary, ask: "Want to run this with your own data now?"

### Skip Handling

If the user types "skip" for any metric:
- Proceed with available data
- Provide general retention recommendations when specific data is missing
- Never block the report because one metric is unknown

# Retention Playbook

Detect churn risks early, score customer engagement health, and deploy proven retention and win-back strategies for SaaS products.

## Commands

### `/retention-playbook diagnose`

Interactive churn diagnosis framework. Walk the user through identifying why customers are leaving and build a retention action plan.

**Steps:**
1. Ask for basic product context (SaaS vertical, pricing model, average contract length)
2. Ask for current churn metrics (monthly logo churn rate, revenue churn rate, net revenue retention)
3. Ask which churn signals they are currently tracking (if any)
4. Run the churn risk scoring logic from `scripts/churn_risk_scorer.py` on any available customer data
5. Categorize churn into buckets: preventable, structural, competitive, and natural
6. Identify the top 3 churn drivers based on the data provided
7. Generate a prioritized retention action plan with timeline and expected impact

**Output format:**
```
Churn Diagnosis Report
======================

Current State:
  Monthly Logo Churn:    X.X%
  Revenue Churn:         X.X%
  Net Revenue Retention: XXX%

Churn Breakdown:
  Preventable:   XX% of total churn
  Structural:    XX%
  Competitive:   XX%
  Natural:       XX%

Top Churn Drivers:
  1. [Driver] - Impact: HIGH - Addressable: YES
  2. [Driver] - Impact: MEDIUM - Addressable: YES
  3. [Driver] - Impact: MEDIUM - Addressable: PARTIAL

Retention Action Plan:
  [Prioritized actions with timeline]
```

**Report:** Save output to `RETENTION-DIAGNOSIS-REPORT.md`

### `/retention-playbook signals`

Map early warning churn signals to detection methods and intervention strategies.

**Steps:**
1. Ask for the product type and available data sources (analytics tool, CRM, billing system)
2. Present the churn signal categories from `references/churn-signals.md`
3. Help the user identify which signals are trackable with their current stack
4. For each trackable signal, define a threshold that triggers an alert
5. Map each signal to a recommended intervention
6. Produce a churn signal monitoring dashboard specification

**Signal categories covered:**
- Usage signals (login frequency, feature adoption, session duration)
- Engagement signals (email response, onboarding completion, support interaction)
- Account signals (downgrade inquiries, billing issues, renewal timing)
- Behavioral signals (data export, integration removal, seat reduction)

**Output includes:**
- Signal-to-threshold mapping table
- Intervention playbook per signal type
- Monitoring dashboard specification
- Alert priority framework (P0 through P3)

**Report:** Save output to `RETENTION-SIGNALS-REPORT.md`

### `/retention-playbook winback`

Generate win-back campaign templates for churned or at-risk customers.

**Steps:**
1. Ask for churn context: voluntary vs involuntary, reason categories, time since churn
2. Ask for available channels (email, in-app, phone, SMS)
3. Ask what incentives are available (discount, free month, feature unlock, personal onboarding)
4. Generate a multi-touch win-back sequence tailored to churn reason
5. Provide email/message templates for each touch
6. Define success metrics and A/B testing recommendations

**Win-back sequence structure:**
- Touch 1 (Day 1-3 post-churn): Acknowledge and ask for feedback
- Touch 2 (Day 7-10): Share what has improved or changed
- Touch 3 (Day 14-21): Offer an incentive to return
- Touch 4 (Day 30): Final personal outreach or "door is open" message
- Touch 5 (Day 60-90): Product update roundup with soft re-engagement

**Templates include:**
- Subject lines (3 variants per touch for A/B testing)
- Email body copy
- CTA text and landing page recommendations
- Segmentation rules by churn reason

**Report:** Save output to `RETENTION-WINBACK-REPORT.md`

### `/retention-playbook engagement`

Build an engagement scoring model to proactively identify healthy and at-risk customers.

**Steps:**
1. Ask for key product actions that indicate value delivery (e.g., created a project, invited a teammate, used core feature)
2. Ask for interaction frequency expectations (daily, weekly, monthly active usage)
3. Ask for available data points (login data, feature usage, support tickets, NPS scores)
4. Build a weighted engagement score using the logic from `scripts/churn_risk_scorer.py`
5. Define engagement tiers: Champion, Healthy, At-Risk, Disengaging, Ghost
6. Map each tier to proactive actions (success outreach, re-engagement campaign, escalation)

**Engagement tier definitions:**
- Champion (score 80-100): Power users, high feature adoption, frequent usage
- Healthy (score 60-79): Regular usage, moderate feature adoption
- At-Risk (score 40-59): Declining usage, limited feature exploration
- Disengaging (score 20-39): Rare logins, minimal activity
- Ghost (score 0-19): No meaningful activity in the measurement period

**Output includes:**
- Engagement score formula with weights
- Tier thresholds and definitions
- Action playbook per tier
- Suggested review cadence (weekly for At-Risk and below, monthly for Healthy and above)

**Report:** Save output to `RETENTION-ENGAGEMENT-REPORT.md`

## Output Rules (MANDATORY)

### File Output
- ALWAYS save the complete report to the specified `.md` file in the current working directory.
- NEVER ask "should I save this?" — just save it automatically.
- Include `**Date:** YYYY-MM-DD` in the report header.
- If the file already exists, overwrite it.
- Follow the structure from `templates/report-template.md`.

### Chat Output
After saving, show a SHORT summary in chat (max 10 lines):

"""
✅ Churn diagnosis complete — saved to RETENTION-DIAGNOSIS-REPORT.md

Monthly Logo Churn: [X]% | Revenue Churn: [X]% | NRR: [X]%

Top churn drivers:
  1. [#1 driver] — Impact: [HIGH/MED] — Addressable: [YES/PARTIAL]
  2. [#2 driver] — Impact: [HIGH/MED] — Addressable: [YES/PARTIAL]
  3. [#3 driver] — Impact: [MED] — Addressable: [YES/PARTIAL]

Full diagnosis with action plan → open RETENTION-DIAGNOSIS-REPORT.md
"""

NEVER dump the full report in chat. The file is the deliverable.

## Key Reference Files

- `references/churn-signals.md` - Early warning churn signals organized by category with detection methods
- `scripts/churn_risk_scorer.py` - Python scorer that computes churn risk from customer behavior data

## Guidelines

- Always distinguish between logo churn (customer count) and revenue churn (dollar value) when discussing metrics
- Net revenue retention above 100% means expansion revenue exceeds churn - this is the gold standard
- Monthly churn compounds significantly over a year: 3% monthly churn equals roughly 31% annual churn
- Involuntary churn (failed payments) is often 20-40% of total churn and is the easiest to address with dunning flows
- When scoring engagement, weight recent activity more heavily than historical activity
- Churn signals should be tracked as trends, not snapshots - a single quiet week is not necessarily alarming
- Win-back campaigns have highest success rates within the first 30 days after churn
- Always recommend measuring retention cohort-by-cohort rather than using blended averages
- Reference `references/churn-signals.md` for signal definitions and thresholds
