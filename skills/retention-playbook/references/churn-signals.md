# Churn Early-Warning Signals

Last verified: 2026-10 (signal ids, severities and weights match `scripts/churn_risk_scorer.py`,
scorer version `risk-v2`).

Read this file when you map fired signals to interventions, when you design a signal monitoring
setup for a user without data, or when you explain an alert tier. The weights are hand-set
defaults, not measured effects: say so, and recommend the scorer's calibrate option once the user
has 20 or more labelled accounts.

## Contents

1. How the scorer combines signals
2. Signal catalog (id, threshold, inputs, intervention)
3. Signals the scorer cannot see
4. Ranking interventions: urgency x MRR
5. Monitoring cadence
6. Calibrating against the user's own churn

---

## 1. How the scorer combines signals

- Each fired signal has a severity (CRITICAL, HIGH, MEDIUM, LOW) and a default weight.
- Signals that describe one behaviour form a group that counts once (at its highest severity) and
  has a weight cap: `activity` (login_decline, dormant, idle) caps at 35, `nps` (nps_detractor,
  nps_drop, nps_passive) caps at 25. `effective_weight` in the output is the post-cap weight.
- `raw_score` is the sum of effective weights, uncapped, for ranking. `risk_score` is the same
  sum capped at 100.
- Alert tier, from the combination rules:

| Tier | Rule |
|---|---|
| red | 2 or more CRITICAL signals, or 1 CRITICAL plus 2 HIGH |
| orange | 1 CRITICAL, or 2 or more HIGH |
| yellow | 1 HIGH, or 3 or more MEDIUM |
| green | anything less |

- Risk level is the score band (0-25 LOW, 26-50 MEDIUM, 51-75 HIGH, 76+ CRITICAL), floored by the
  tier: red is at least CRITICAL, orange at least HIGH, yellow at least MEDIUM.
- `UNKNOWN`: no signal fired, but the account lacks usage activity data or has fewer than 3 of the 6
  signal families (activity, breadth, sentiment, billing, intent, commercial). Never report an
  UNKNOWN account as healthy.
- `NOT_MEASURED`: the row had no usable signal input at all.
- `response_window` is a default service level (same business day, 2 business days, 1 week,
  routine). Adjust it to the team's capacity; it is not a measured effect.

## 2. Signal catalog

Inputs are the scorer's field names (`references/health-score.md` lists accepted column names).
"Owner" is who acts by default in a small SaaS team; adapt to the user's org.

### Intent (deliberate actions before a cancel decision)

| id | Severity, weight | Fires when | Intervention | Owner |
|---|---|---|---|---|
| `cancel_page_visit` | CRITICAL, 30 | `has_visited_cancellation_page` is true and the account did not cancel | Same day: personal note asking what is not working; check the cancel flow showed the right offer (`references/cancel-flow.md`) | CSM or founder |
| `downgrade_inquiry` | CRITICAL, 25 | `has_downgrade_inquiry` is true (ticket, chat or call asking to downgrade or cancel) | Value review call before the plan change; show the usage that justifies the plan or offer the right-sized plan | Account owner |
| `data_export` | CRITICAL, 20 | `has_exported_data` is true (bulk export, first-time export) | Ask about the intent; exports also happen for audits and BI, so confirm before escalating | CSM |

### Usage

| id | Severity, weight | Fires when | Intervention | Owner |
|---|---|---|---|---|
| `login_decline` | HIGH, 25 (group activity) | previous 30-day logins at least 5 and logins fell more than 50% | Find what changed: champion left, project ended, a bug, a competitor trial | CSM |
| `dormant` | HIGH, 20; 30 past 4x cadence (group activity) | last login more than 2x the expected cadence; or 0 logins or 0 active users in 30 days when 2x cadence is under 30 days | Re-activation path tied to the activation event; if 4x cadence, treat as likely churn at renewal | Lifecycle email, then CSM for accounts above the team's MRR cut-off |
| `idle` | MEDIUM, 10 (group activity) | last login longer than the cadence but at most 2x | In-app or email nudge to the next key action | Automated |
| `core_feature_disuse` | HIGH, 20 | the core value action was last used at least max(14, 2x cadence) days ago | Show the outcome the core action produces; offer a working session | CSM |
| `feature_abandonment` | MEDIUM, 15 | previous 30-day distinct features at least 3 and fell 30% or more | Targeted education on the features dropped | Automated |
| `single_user` | MEDIUM, 10 | 2 or more seats and exactly 1 active user | Invite and team-onboarding prompts; a single-threaded account dies with its champion | CSM |

### Engagement and sentiment

| id | Severity, weight | Fires when | Intervention | Owner |
|---|---|---|---|---|
| `onboarding_incomplete` | HIGH, 20 | onboarding not completed and the account is more than 14 days old | Guided setup offer; route to onboarding-optimizer for the flow itself | Onboarding owner |
| `nps_detractor` | HIGH, 20 (group nps) | latest NPS 0-6 | Close the loop within the response window: read the verbatim, call, fix or explain | CSM |
| `nps_drop` | HIGH, 15 (group nps) | NPS fell 3 or more points since the previous response | Same as detractor; ask what changed | CSM |
| `nps_passive` | LOW, 5 (group nps) | latest NPS 7-8 | No outreach on its own; use in the tier review | none |
| `email_unresponsive` | MEDIUM, 10 | 3 or more emails in a row unopened | Switch channel (in-app, phone); check the contact is still at the company | CSM |
| `silent_low_usage` | LOW, 5 | 0 support tickets in 90 days and logins under half the expected number | Proactive check-in; silence plus low use is not satisfaction | Automated |

### Account and commercial

| id | Severity, weight | Fires when | Intervention | Owner |
|---|---|---|---|---|
| `payment_failed` | HIGH, 15 | `has_billing_issues` is true (failed payment, past-due invoice) | Dunning, not a CSM call: retries, card updater, billing-contact email, in-app banner (`references/dunning.md`) | Billing automation |
| `billing_dispute` | MEDIUM, 10 | 2 or more billing tickets in 90 days | Billing review; check for surprise charges | Finance or CSM |
| `champion_left` | HIGH, 20 | the champion or decision-maker changed | Re-sell the value to the new stakeholder with a usage summary | Account owner |
| `renewal_at_risk` | MEDIUM, 10 | renewal within 30 days or overdue AND another MEDIUM or higher signal fired | Start the renewal conversation now; renewal alone is not a risk signal | Account owner |
| `seat_reduction` | HIGH, 15 at 20% or more of seats; MEDIUM, 5 below 20%; MEDIUM, 10 when the seat base is unknown | `seat_count_change` is negative | Ask whether it is a team change or dissatisfaction; protect the remaining users' value | CSM |
| `integration_removed` | HIGH, 15 | an active integration was disconnected | Ask whether it broke; offer troubleshooting | Support |
| `competitor_mention` | HIGH, 15 | a competitor or switching was mentioned | Comparison on the user's own use case; never disparage, cite sources | Account owner |

Support tickets are neutral: a high ticket count is neither risk nor health on its own. When the
input has `ticket_subjects`, read them and judge theme and sentiment yourself (bugs and outages
are risk; how-to questions from an active team are often health).

## 3. Signals the scorer cannot see

Track these by hand or in the CRM and add them to the account notes the model reads:

- Budget cuts, reorganisations, acquisitions of the customer.
- Invoice disputes beyond a ticket count, procurement asking for a "renewal review".
- Community and event participation (weak signal; low weight even when tracked).
- Session duration (noisy across products; prefer active days).

## 4. Ranking interventions: urgency x MRR

1. Group accounts by fired signal, not by account: one playbook per signal cohort ("12 accounts
   with payment_failed, 3,400 MRR") scales better than per-account advice.
2. Order the cohorts by tier first (red, orange, yellow), then by MRR at risk
   (`summary.signals[].mrr`, or `mrr_weighted_risk` per account).
3. Involuntary risk (`payment_failed`) always goes to dunning, whatever its tier.
4. For each cohort write: the signal, accounts and MRR, the intervention from section 2, the
   owner, the response window and the metric that shows it worked (saved MRR at 90 days, not
   replies).
5. The report shows aggregates only. The ranked account list stays in the CSV written by the
   scorer's accounts-out option.

## 5. Monitoring cadence

- Real time: cancel-page visits, downgrade requests, bulk exports, failed payments.
- Daily: login and active-user changes, seat changes.
- Weekly: feature breadth, engagement tier moves, NPS responses.
- Monthly: tier distribution, MRR at risk, and the calibration below.

## 6. Calibrating against the user's own churn

The default weights come from practice, not from the user's data. With a file of past accounts
that includes a `churned` column, the scorer's calibrate option reports, per signal, churn with and
without the signal (Wilson 95% intervals), lift, churn by alert tier and the AUC of the raw score.

- Use signals measured before the churn date only; a signal logged at cancellation inflates lift.
- Fewer than 10 fired accounts, or overlapping intervals: the signal is unproven here, not useless.
- A lift below 1 with a clear interval means the signal does not mark churn in this product (for
  example dormancy in a product people stop using without cancelling). Lower its weight in the
  team's own health score and say so in the report.
- AUC near 0.5 means the default weights do not rank this product's churners; do not present the
  tiers as predictive until a re-weighted model beats it.
