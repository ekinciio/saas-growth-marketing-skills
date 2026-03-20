---
name: onboarding-optimizer
description: >
  Evaluate and optimize user onboarding flows for SaaS products. Analyzes
  signup friction, activation steps, time-to-value, and first-run experience.
  Provides pattern recommendations based on product type. Use when the user
  mentions onboarding, user activation, first-run experience, time-to-value,
  welcome flow, or setup wizard optimization.
---

## First Run

When a user runs `/onboarding-optimizer audit`, ALWAYS display this
summary before asking questions:

"""
📝 Onboarding Optimizer

What I'll ask you (10 questions about your current onboarding):
  1.  Product type and primary use case
  2.  Steps from signup to first value moment    → a number
  3.  Required fields at signup                  → a number
  4.  Progress indicator?                        → yes/no
  5.  Can users skip optional steps?             → yes/no
  6.  Template gallery or starter content?       → yes/no
  7.  Time to first value moment                 → minutes
  8.  Credit card required before trial?         → yes/no
  9.  Welcome email sequence?                    → yes/no
  10. In-app guidance (tooltips, checklists)?    → yes/no

  Most answers are yes/no or a number. Takes ~3 minutes.
  Type "demo" to see a sample audit first.

What you'll get:
  → Onboarding score (0-100) with letter grade
  → Scoring breakdown (what helped, what hurt)
  → Recommended onboarding pattern for your product type
  → Prioritized improvements with estimated activation lift
  → Saved to ONBOARDING-AUDIT-REPORT.md

Let's start — what's your product type?
"""

### Demo Mode

If the user types "demo", use this data to generate a full sample report:

```json
{
  "product_type": "project management tool",
  "steps_to_value": 4,
  "required_fields": 2,
  "has_progress_indicator": true,
  "can_skip_steps": true,
  "has_template_gallery": true,
  "time_to_value_minutes": 8,
  "credit_card_required": false,
  "has_welcome_email": true,
  "has_in_app_guidance": false,
  "has_empty_state_education": false
}
```

Save the demo report as `ONBOARDING-AUDIT-REPORT-DEMO.md`.
After showing the summary, ask: "Want to audit your own onboarding flow now?"

### Skip Handling

If the user doesn't know an answer:
- Accept "not sure" or "skip" and score that factor as neutral (0 points)
- Continue with remaining questions
- Note which factors were unknown in the report

# Onboarding Optimizer

Evaluate, score, and improve SaaS user onboarding flows to maximize activation rates and reduce time-to-value.

## Commands

### `/onboarding-optimizer audit`
Interactive onboarding flow audit. Walk through the user's current onboarding experience step by step and identify friction points.

**Steps:**
1. Ask the user to describe their product type and primary use case
2. Gather onboarding flow details:
   - How many steps from signup to first value moment?
   - How many required fields at signup?
   - Is there a progress indicator?
   - Can users skip optional steps?
   - Is there a template gallery or starter content?
   - Are empty states educational (guiding next action)?
   - How long until a new user reaches their first value moment?
   - Is a credit card required before trial?
   - Is there a welcome email sequence?
   - Is there in-app guidance (tooltips, checklists, walkthroughs)?
3. Run the scoring algorithm from `scripts/onboarding_scorer.py`
4. Present the score, grade, and detailed breakdown
5. Show which factors helped and which hurt the score
6. Recommend a specific onboarding pattern from the pattern library
7. Provide a prioritized list of improvements with estimated activation lift

**Output format:**
```
Onboarding Score: 72/100 (Grade: B)

Scoring Breakdown:
  Base score:              50
  Steps (4 steps):         +0  (under 5 is optimal)
  Required fields (2):     +0  (under 3 is optimal)
  Progress indicator:      +10
  Skip option:             +10
  Template gallery:        +5
  Time-to-value (8 min):   +5  (5-15 min range)
  Welcome email sequence:  +10
  In-app guidance:         -0  (not present)
  Credit card upfront:     -15
  Empty state education:   -0  (not present)

Recommended Pattern: Progressive Disclosure
Top Improvements: [...]
```

**Report:** Save output to `ONBOARDING-AUDIT-REPORT.md`

### `/onboarding-optimizer patterns`
Display the onboarding pattern library with guidance on when to use each pattern.

**Steps:**
1. Ask the user about their product type (or skip if already known):
   - Visual/design tool
   - Data/analytics platform
   - Collaboration/productivity tool
   - Developer tool/API
   - Business operations (CRM, ERP, etc.)
   - Other (describe)
2. Show all 5 onboarding patterns from `references/onboarding-patterns.md`
3. Highlight which pattern is the best fit for their product type
4. Explain why that pattern works for their context
5. Provide implementation tips specific to their product

**Report:** Save output to `ONBOARDING-PATTERNS-REPORT.md`

### `/onboarding-optimizer checklist`
Generate a customized onboarding improvement checklist based on the current flow.

**Steps:**
1. If an audit has already been performed, use those results; otherwise run a quick audit
2. Generate a prioritized checklist of improvements grouped by:
   - Quick wins (can implement in 1-2 days)
   - Medium effort (1-2 weeks)
   - Strategic improvements (1+ months)
3. For each item, include:
   - What to do
   - Why it matters
   - Expected impact on activation rate
   - Implementation difficulty (low, medium, high)

**Quick win examples:**
- Add a progress indicator to multi-step signup
- Remove optional fields from the signup form
- Add skip buttons to non-critical setup steps
- Create educational empty states with clear CTAs

**Medium effort examples:**
- Build a welcome email sequence (3-5 emails over first 14 days)
- Add in-app tooltips for key features
- Create a getting-started checklist in the dashboard
- Implement a template gallery for new users

**Strategic improvement examples:**
- Redesign signup to reduce steps to under 5
- Build an interactive product tour
- Implement progressive disclosure for complex features
- Remove credit card requirement from trial signup
- Create personalized onboarding paths based on user role or use case

**Report:** Save output to `ONBOARDING-CHECKLIST-REPORT.md`

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
✅ Onboarding audit complete — saved to ONBOARDING-AUDIT-REPORT.md

Score: [X]/100 (Grade: [A-F])
Recommended Pattern: [pattern name]

What helped:
  + [factor] (+[X] points)
  + [factor] (+[X] points)

What hurt:
  - [factor] (-[X] points)
  - [factor] (-[X] points)

Full report with improvement roadmap → open ONBOARDING-AUDIT-REPORT.md
"""

NEVER dump the full report in chat. The file is the deliverable.

## Key Reference Files

- `references/onboarding-patterns.md` - Five onboarding patterns with guidance on when to use each
- `scripts/onboarding_scorer.py` - Scoring algorithm that evaluates onboarding flows on a 0-100 scale

## Guidelines

- Always consider the product type and target user when making recommendations
- Not every product needs every onboarding element - context matters
- Prioritize time-to-value above all else; every step that delays value delivery needs strong justification
- Credit card upfront is not always wrong (it filters for serious users) but the trade-off should be explicit
- Email sequences and in-app guidance are complementary, not alternatives
- Progress indicators matter more as the number of steps increases
- Template galleries are high-impact for creative and content tools but less relevant for data tools
- When suggesting improvements, always estimate the expected activation lift range
- Frame recommendations around the user's specific product context, not generic best practices
