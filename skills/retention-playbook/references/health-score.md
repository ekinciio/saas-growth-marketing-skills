# Account Health and Engagement Scores

Last verified: 2026-10 (field names and components match `scripts/churn_risk_scorer.py`,
scorer version `risk-v2`).

Read this file when you prepare an accounts file for the scorer, when a run exits 5 because no
field was recognized, or when you design a health score for a user who has no data yet.

## Contents

1. Two scores, not one
2. Input file: one row per account
3. Building the file from common tools
4. Engagement score components
5. Tiers and what to do in each
6. Designing a health score without data
7. Pitfalls

---

## 1. Two scores, not one

- **Risk** counts warning signals (`references/churn-signals.md`). Missing data never lowers it and
  never makes an account "LOW": too little data gives `UNKNOWN`.
- **Engagement** measures positive use: how often, how recently, how broadly, how many seats, and
  the trend. It is computed only when at least 60% of its weight was measured; otherwise the tier
  is `insufficient_data`.
- Engagement is not "100 minus risk". A champion-level user who just exported all data and asked
  to downgrade is high engagement and red risk at once, and that combination is the story.

## 2. Input file: one row per account

CSV, TSV, JSON list, JSONL, or `{"customers": [...]}`. Column names are matched after lower-casing
and replacing spaces and punctuation with `_`. Any unlisted column can be mapped with the scorer's
map option (`FIELD=COLUMN`). Values like "yes", "no", "TRUE", "1", "12%", "$1,200" and "n/a" are
read correctly; unreadable values are dropped with a warning, never guessed.

| Field | Also accepted | Type |
|---|---|---|
| `account_id` | customer_id, account, customer, id, company_id, org_id, workspace_id, user_id | text (emails are masked) |
| `mrr` | monthly_recurring_revenue, monthly_revenue, monthly_charge(s) | money; `arr` / 12 when only ARR is given |
| `arr` | annual_recurring_revenue, acv | money |
| `segment` | plan, tier, contract | label for summaries |
| `churned` | churn, is_churned, churn_label | yes/no, only for calibration |
| `login_frequency_last_30d` | logins_last_30d, sessions_last_30d | count (all users of the account) |
| `login_frequency_prev_30d` | logins_prev_30d, sessions_prev_30d | count |
| `active_days_last_30d` | active_days_30d | count |
| `last_login_days_ago` | days_since_last_login, days_since_last_seen, days_inactive | days |
| `expected_cadence_days` | cadence_days | days between uses for a healthy account; overrides the run default |
| `features_used_last_30d`, `features_used_prev_30d` | distinct_features_30d | count |
| `features_total` | features_available | count (breadth denominator) |
| `key_actions_used_30d` | key_actions_30d, value_actions_30d | count of the user's key value actions done |
| `key_actions_total` | key_actions_defined | count |
| `core_action_days_ago` | days_since_core_action | days |
| `seats` | licensed_seats, seat_count, quantity | count |
| `active_users_30d` | active_users, active_seats, mau | count |
| `seat_count_change` | seat_change, seat_delta | signed number (negative = cut) |
| `nps_score`, `prev_nps_score` | nps, previous_nps | 0-10 |
| `onboarding_completed` | onboarded | yes/no |
| `account_age_days` | tenure_days, days_since_signup | days |
| `emails_unopened_streak` | unopened_emails_streak | count |
| `support_tickets_last_90d` | tickets_90d, support_tickets | count (neutral) |
| `billing_tickets_last_90d` | billing_tickets_90d | count |
| `ticket_subjects` | recent_ticket_subjects | text list, `;`-separated (masked, max 5) |
| `has_billing_issues` | payment_failed, past_due, billing_issue | yes/no |
| `has_downgrade_inquiry` | downgrade_inquiry | yes/no |
| `contract_renewal_days` | days_to_renewal, renewal_days | days; negative = renewal date passed |
| `champion_left` | stakeholder_change | yes/no |
| `has_exported_data` | data_export, bulk_export | yes/no |
| `has_visited_cancellation_page` | cancel_page_visit | yes/no |
| `has_removed_integration` | integration_removed | yes/no |
| `has_competitor_mention` | competitor_mention | yes/no |

Personal-data columns (email, name, phone, address and similar) are never read; the output lists
their names so the user knows they were skipped.

## 3. Building the file from common tools

Ask the user for an export, never for per-account numbers typed in chat.

- **Billing (Stripe, Paddle, Chargebee):** customer id, MRR, seats (quantity), past-due status,
  renewal date. Past due or a failed invoice in the last 30 days sets `has_billing_issues`.
- **Product analytics (PostHog, Amplitude, Mixpanel, GA4):** per-account active days, logins or
  sessions for the last and previous 30 days, last seen, and counts of the key value actions. Group
  by the account or organization property, not by user, for B2B products.
- **CRM or helpdesk (HubSpot, Salesforce, Intercom, Zendesk):** NPS, ticket counts and subjects,
  downgrade or cancel requests, champion changes, competitor mentions.
- Join on the customer id in a spreadsheet and save as CSV. If the user cannot join files, score
  each export alone: the output says which signal families are missing.

## 4. Engagement score components

Defaults (override with the scorer's engagement-weights option):

| Component | Weight | Value (0 to 1) |
|---|---|---|
| frequency | 30 | active days / expected uses in 30 days (30 / cadence); logins when active days are absent; capped at 1 |
| recency | 20 | 1 when the last login is within the cadence, 0 at 4x the cadence or more, linear in between |
| breadth | 25 | key actions used / key actions defined, or features used / features total |
| seat_utilization | 15 | active users / seats |
| trend | 10 | logins this period / previous period, capped at 1, only when the previous period has 5 or more |

Score = measured components weighted and renormalized, times 100. Coverage = measured weight / total
weight. Below 60% coverage there is no score.

Set the cadence from the product, not from habit: a daily tool (chat, scheduling) is 1-2 days, a
weekly reporting tool 7, a monthly invoicing or payroll tool 30. Ask the user when unsure; the
cadence changes which accounts look dormant.

## 5. Tiers and what to do in each

| Tier | Score | Default play |
|---|---|---|
| champion | 80-100 | Ask for referrals, reviews and case studies (real ones); expansion conversations |
| healthy | 60-79 | Keep value visible: usage summaries, new features that match their key actions |
| at_risk | 40-59 | Find the missing key action; targeted education; CSM touch for accounts above the MRR cut-off |
| disengaging | 20-39 | Re-activation sequence tied to the activation event; ask what changed |
| ghost | 0-19 | Treat as likely churn at renewal; a direct "is this still useful?" conversation beats more nudges |
| insufficient_data | - | Fix the data first: list the fields to add |

Review weekly for at_risk and below, monthly for healthy and above. Read engagement together with
risk: high engagement plus red risk means intent to leave despite use (price, a competitor, a
consolidation); low engagement plus green risk means silent decay.

## 6. Designing a health score without data

When the user has no account data yet, the deliverable is a spec, not scores:

1. Define the key value actions (3-5) and the activation event from `growth-context.md`.
2. Set the cadence per plan or segment.
3. Pick the signals the team can track now (section 2 of `references/churn-signals.md`), mark the
   ones they cannot, and name the tool and event for each.
4. Define owners and response windows per tier.
5. Plan the calibration: label churned accounts for one quarter, then run the calibrate option and
   re-weight.

## 7. Pitfalls

- Logins measure presence, not value. Prefer key actions and active days when available.
- Per-user data in a B2B product must be rolled up to the account before scoring.
- A score nobody acts on is a dashboard. Every tier needs an owner and a play.
- Never present default weights as predictive; only the user's calibration shows that.
