# Churn Early Warning Signals

A comprehensive catalog of early warning signals that indicate a SaaS customer may be at risk of churning. Signals are organized by category with detection methods, severity levels, and recommended responses.

## Usage Signals

These signals come from product analytics and indicate declining value realization.

### Declining Login Frequency

- **What to track:** Logins per week/month compared to the customer's own baseline
- **Warning threshold:** 50%+ decline in login frequency over a 30-day period
- **Severity:** HIGH
- **Detection method:** Compare current 30-day login count against previous 30-day count
- **Response:** Trigger a check-in email from customer success; review whether the customer completed onboarding

### Feature Abandonment

- **What to track:** Number of distinct features used compared to prior period
- **Warning threshold:** 30%+ reduction in features used over 30 days
- **Severity:** MEDIUM-HIGH
- **Detection method:** Track unique feature touches per user per period
- **Response:** Send targeted feature education content; schedule a training session

### Reduced Session Duration

- **What to track:** Average session length per visit
- **Warning threshold:** Session duration drops below 50% of the customer's historical average
- **Severity:** MEDIUM
- **Detection method:** Average session time over rolling 14-day windows
- **Response:** Investigate whether the product is meeting their use case; send tips for getting more value

### Core Feature Disuse

- **What to track:** Usage of the primary value-driving feature (the one thing the product does best)
- **Warning threshold:** Zero usage of the core feature in 14+ days
- **Severity:** HIGH
- **Detection method:** Feature-specific event tracking
- **Response:** Immediate outreach from customer success to understand blockers

### Single-User Dependency

- **What to track:** How many team members are actively using the product
- **Warning threshold:** Only one active user on a team plan for 30+ days
- **Severity:** MEDIUM
- **Detection method:** Count active users per account
- **Response:** Send team invitation reminders; offer team onboarding session

## Engagement Signals

These signals reflect how the customer interacts with your company outside the product.

### No Response to Emails

- **What to track:** Email open rates and reply rates from customer success and marketing
- **Warning threshold:** Zero email opens for 3+ consecutive campaigns or outreach attempts
- **Severity:** MEDIUM
- **Detection method:** CRM or email tool engagement tracking
- **Response:** Try a different channel (in-app message, phone call); verify contact info is current

### Skipped Onboarding

- **What to track:** Completion rate of onboarding steps or setup wizard
- **Warning threshold:** Customer has not completed onboarding within 14 days of signup
- **Severity:** HIGH
- **Detection method:** Onboarding completion tracking in product analytics
- **Response:** Personal outreach offering guided setup; simplify onboarding flow

### No Support Tickets Filed

- **What to track:** Support ticket count over the customer lifecycle
- **Warning threshold:** Zero support tickets combined with low usage (silence is not always golden)
- **Severity:** LOW-MEDIUM
- **Detection method:** Helpdesk ticket count per account
- **Response:** Proactive check-in to ensure no unvoiced frustrations

### Declining NPS or CSAT Scores

- **What to track:** Changes in NPS or CSAT responses over time
- **Warning threshold:** NPS score below 7 (passive or detractor) or a drop of 3+ points
- **Severity:** HIGH
- **Detection method:** Survey response tracking
- **Response:** Close-the-loop call to address specific feedback; escalate detractors

### No Participation in Community or Events

- **What to track:** Attendance at webinars, community posts, or user group participation
- **Warning threshold:** Zero participation over 6+ months (for customers who previously engaged)
- **Severity:** LOW
- **Detection method:** Event and community platform tracking
- **Response:** Send personalized invitations to relevant upcoming events

## Account Signals

These signals come from billing, CRM, and account management systems.

### Downgrade Inquiry

- **What to track:** Support tickets or conversations mentioning downgrade, reduce plan, or cancel
- **Warning threshold:** Any inquiry about downgrading
- **Severity:** CRITICAL
- **Detection method:** Keyword monitoring in support tickets and chat
- **Response:** Immediate escalation to account manager; prepare a value reinforcement conversation

### Billing Issues

- **What to track:** Failed payments, expired cards, billing disputes
- **Warning threshold:** Any failed payment attempt
- **Severity:** HIGH (involuntary churn risk)
- **Detection method:** Payment processor event monitoring
- **Response:** Automated dunning sequence; personal outreach after second failure

### Contract Renewal Approaching

- **What to track:** Days until contract renewal or subscription anniversary
- **Warning threshold:** 30 days before renewal for at-risk accounts, 60 days for all accounts
- **Severity:** MEDIUM (routine) to HIGH (if combined with other signals)
- **Detection method:** Contract date tracking in CRM
- **Response:** Schedule a renewal conversation; prepare a value summary and ROI report

### Budget or Stakeholder Changes

- **What to track:** Mentions of budget cuts, new leadership, or organizational changes
- **Warning threshold:** Any mention of budget review or change in decision-maker
- **Severity:** HIGH
- **Detection method:** CRM notes, customer success call logs
- **Response:** Re-establish value proposition with new stakeholders; prepare an ROI case

### Invoice Disputes

- **What to track:** Requests for credits, billing explanations, or pricing complaints
- **Warning threshold:** More than one billing-related support ticket in a quarter
- **Severity:** MEDIUM
- **Detection method:** Support ticket categorization
- **Response:** Proactive billing review; consider a pricing conversation

## Behavioral Signals

These signals represent deliberate actions that often precede a cancellation decision.

### Data Export

- **What to track:** Use of bulk export, API data extraction, or backup download features
- **Warning threshold:** Any large-scale data export, especially a first-time export
- **Severity:** CRITICAL
- **Detection method:** Product event tracking on export features
- **Response:** Immediate outreach from customer success to understand intent

### Remove Integrations

- **What to track:** Disconnection of previously active integrations
- **Warning threshold:** Removal of any active integration
- **Severity:** HIGH
- **Detection method:** Integration status change events
- **Response:** Ask whether the integration was causing issues; offer troubleshooting

### Reduce Seat Count

- **What to track:** Changes to the number of licensed seats or team members
- **Warning threshold:** Any reduction in seat count
- **Severity:** HIGH
- **Detection method:** Subscription change events
- **Response:** Understand the context (team restructure vs dissatisfaction); reinforce value for remaining users

### Cancellation Page Visits

- **What to track:** Visits to the cancellation or account closure page without completing the flow
- **Warning threshold:** Any visit to the cancellation page
- **Severity:** CRITICAL
- **Detection method:** Page view tracking on cancel/close account URLs
- **Response:** Trigger an immediate in-app survey or chatbot intervention; route to retention specialist

### Competitor Research Signals

- **What to track:** Mentions of competitors in support tickets, reviews, or feedback
- **Warning threshold:** Any comparison or mention of switching to a competitor
- **Severity:** HIGH
- **Detection method:** Keyword monitoring in support and feedback channels
- **Response:** Prepare a competitive comparison; highlight unique value and switching costs

## Signal Scoring Summary

| Signal | Category | Severity | Score Weight |
|--------|----------|----------|-------------|
| Cancellation page visit | Behavioral | CRITICAL | +30 |
| Data export | Behavioral | CRITICAL | +20 |
| Downgrade inquiry | Account | CRITICAL | +25 |
| Declining logins (>50%) | Usage | HIGH | +25 |
| Skipped onboarding | Engagement | HIGH | +20 |
| Billing issues | Account | HIGH | +15 |
| Seat reduction | Behavioral | HIGH | +15 |
| Integration removal | Behavioral | HIGH | +15 |
| Feature abandonment (>30%) | Usage | MEDIUM-HIGH | +20 |
| NPS detractor (<7) | Engagement | HIGH | +10 to +20 |
| Reduced session duration | Usage | MEDIUM | +10 |
| No email engagement | Engagement | MEDIUM | +10 |
| Contract renewal <30d | Account | MEDIUM | +10 |
| Zero support tickets + low use | Engagement | LOW-MEDIUM | +5 |
| No community participation | Engagement | LOW | +5 |

## Signal Combination Rules

Individual signals are concerning, but combinations are far more predictive:

- **Red alert (immediate action):** Any two CRITICAL signals, or one CRITICAL plus two HIGH signals
- **Orange alert (urgent review):** Any two HIGH signals, or one CRITICAL signal alone
- **Yellow alert (monitor closely):** Any single HIGH signal, or three or more MEDIUM signals
- **Green (routine monitoring):** Individual MEDIUM or LOW signals without combination

## Recommended Monitoring Cadence

- **Real-time:** Cancellation page visits, data exports, downgrade inquiries
- **Daily:** Login frequency changes, billing failures, seat changes
- **Weekly:** Feature usage trends, engagement score changes, NPS responses
- **Monthly:** Overall churn signal distribution, signal-to-churn correlation analysis
