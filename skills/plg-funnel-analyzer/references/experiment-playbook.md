# Experiment Playbook by Funnel Leak

Last verified: 2026-10

Candidate changes for each leak the facts can surface, with the metric each one moves, a
guardrail, and the skill that owns the detailed design. Pick from here, then adapt to the
product's motion, ICP and activation event. Effects are unknown until measured: no lift
numbers appear here and none may appear in a report unless a sourced benchmark supports them.

## Contents

1. Rules for every bet
2. Acquisition: visitor-to-signup
3. Activation and time to value
4. Monetization: free-to-paid and trial-to-paid
5. Retention: logo churn, GRR, usage retention
6. Expansion: NRR
7. Efficiency: CAC payback

---

## 1. Rules for every bet

- Change one thing the primary metric responds to directly; a homepage test cannot be read in
  free-to-paid six months later.
- Primary metric plus a guardrail from the next funnel stage, so a gain that only moves the
  problem downstream shows up (more signups that never activate, more upgrades that refund).
- Size it with the `size` command or `test_sizing` from the facts. Over 4 weeks: ship and
  measure with equal before/after windows and the confounders named; add five target-user
  sessions for UX changes.
- Conversion tests wait the conversion window after the last user enters; say so in the plan.
- When the change belongs to another skill's area, the bet names that skill as the next step.

## 2. Acquisition: visitor-to-signup

Signals: `visitor_to_signup` below its reference (confidence is always capped at low, so
confirm which visitors are counted first); `derived.visitor_to_signup_from_volumes` disagreeing
with the typed rate.

| Change | Primary metric | Guardrail | Owner of the details |
|---|---|---|---|
| State the free offer in the hero and primary CTA in the motion's words ("Free plan", "Start a 14-day trial, no card") | Visitor-to-signup on the page | Activation rate of the new signups | landing-page-cro |
| Cut signup steps: SSO, fewer required fields, verification after first value | Signup start-to-complete | Activation rate, spam signups | web-app-growth-engine |
| Pricing page: make the free plan and its limits visible next to paid plans | Pricing-page visitor-to-signup | Paid plan share of signups | landing-page-cro (layout), pricing-analyzer (limits) |
| Send high-intent traffic to a use-case page with a template instead of the generic homepage | Visitor-to-signup by landing page | Activation rate by landing page | saas-landing-builder |

## 3. Activation and time to value

Signals: `activation_rate` below its reference; `time_to_value_hours` above it; an imported
TTV distribution with a long tail (p90 far above the median); a funnel export whose
`biggest_drop` sits before the activation step.

| Change | Primary metric | Guardrail | Owner |
|---|---|---|---|
| Start users in a template, sample data or an import from the tool they use now, so the first session ends at the activation event | Activation within the window | Week-4 retention (guards against shallow activation) | onboarding-optimizer |
| Ask role or use case at signup and route to the matching first project | Activation by segment | Signup completion | onboarding-optimizer, web-app-growth-engine |
| Move setup that does not create value (profile, settings, team details) after the activation event | Median and p75 time to value | Activation | onboarding-optimizer |
| Put the invite where shared work happens (share a project, assign a task), when activation needs a teammate | Invites per activated account, activation | Invite acceptance | onboarding-optimizer |
| Human help for high-value signups that stall (accounts that match the ICP but have not activated by day 2) | Activation of that segment | Sales or CS hours per activation | sales-assist motion |
| Next-step emails or in-app prompts tied to the step not yet done (not a fixed drip) | Activation within the window | Unsubscribe and complaint rate | onboarding-optimizer |

A trial shorter than the time most users need to reach value cannot convert them: compare
the trial length with the TTV p75 and p90 from the import before testing anything else.

## 4. Monetization: free-to-paid and trial-to-paid

Signals: `free_to_paid` below the row for the same motion; a high activation rate with low
conversion (users get value but have no reason to pay); a trial length shorter than the TTV
p75.

| Change | Primary metric | Guardrail | Owner |
|---|---|---|---|
| Upgrade prompt at the moment a free limit is hit, naming the paid feature that removes it | Free-to-paid within the window | Week-4 retention of free users | pricing-analyzer (which limits), onboarding-optimizer (the moment) |
| Reverse trial: new signups start with paid features for a fixed time, then drop to the free plan instead of losing access | Free-to-paid within the window | Free-plan retention after the trial | pricing-analyzer |
| Card at trial start, or the reverse: decide on paying customers per 1,000 visitors (visitor-to-trial x trial-to-paid), never on trial-to-paid alone | Paying customers per 1,000 visitors | Refunds and month-2 churn of new payers | web-app-growth-engine |
| Trial length matched to time to value (extend when p75 TTV is near the end; shorten when users activate in hours and stall) | Trial-to-paid | Activation | pricing-analyzer |
| Sales touch for product-qualified accounts (several active users, a paid-feature limit hit) | PQL-to-paid | Sales cost per new customer | sales-assist motion |

## 5. Retention: logo churn, GRR, usage retention

Signals: churn or GRR in the bottom quartile of the matching row; `still_declining` or
`falls_to_zero` in the flattening check; the churn row topping the sensitivity table.

| Change | Primary metric | Guardrail | Owner |
|---|---|---|---|
| Find the retained use case: compare first-week actions of retained and churned cohorts, then point onboarding at that use case | Week-4 and week-12 retention of new cohorts | Activation | onboarding-optimizer |
| Recover failed payments before they count as churn (retries, card updater, dunning emails) | Involuntary churn | Payment-failure complaints | retention-playbook |
| Cancel flow with pause and downgrade options, and reasons collected | Monthly logo churn | Net MRR (downgrades) | retention-playbook |
| Annual plan offer at the moment of demonstrated value | Share of new MRR on annual plans, then logo churn | ARPA | pricing-analyzer |
| Activity-based notifications (someone commented, a report is ready) instead of generic reminders | Weekly returning users | Notification opt-outs | retention-playbook |

## 6. Expansion: NRR

Signals: `nrr` below the primary row while GRR is healthy (expansion is the gap), or seat
pricing with a product used by one person per account.

| Change | Primary metric | Guardrail | Owner |
|---|---|---|---|
| Price on the value metric that grows with the customer's use (seats, usage, projects) | Expansion MRR per cohort | New-customer conversion | pricing-analyzer |
| Prompts at seat or usage thresholds, plus a sales touch for accounts growing inside the free plan | Expansion MRR | Contraction | pricing-analyzer, sales-assist |
| Collaboration loop that brings more teammates into paid accounts | Seats per account at month 6 | Inactive seats | this skill's `loops` command |

## 7. Efficiency: CAC payback

Signals: `cac_payback_months` worse than the matching row. Payback is computed by
subscription-metrics; this skill only shows where the funnel lengthens it. Shorter payback
comes from the stages above (more payers per acquired signup) or from ARPA, not from cutting
the measurement. Hand the channel-level analysis to subscription-metrics.
