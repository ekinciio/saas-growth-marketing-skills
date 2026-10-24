# PLG Metric Definitions

Last verified: 2026-10

How each funnel number is defined and measured, so the user's figure and the benchmark
describe the same thing. No benchmark values here: they come from
`references/_shared/saas-benchmarks.json` through the scripts.

## Contents

1. The funnel the skill models
2. Definitions and the questions to ask
3. Cohort rates versus period ratios
4. Activation and the aha moment
5. Retention curves and the flattening signal
6. Trial and free-offer motions
7. Sources

---

## 1. The funnel the skill models

```
visitors --visitor-to-signup--> signups --activation--> activated --free-to-paid--> paying
paying customers --monthly logo churn / NRR--> revenue kept and expanded
```

AARRR (acquisition, activation, retention, revenue, referral) is still a useful checklist, but
the skill ranks stages by money: the impact model asks what each stage is worth if it reached
its segment's benchmark. Referral is treated as a loop (`references/growth-loops.md`), not as
a funnel stage.

## 2. Definitions and the questions to ask

| Metric | Definition | Ask before comparing |
|---|---|---|
| Visitor-to-signup | New accounts / unique visitors in the same period | Which visitors (all pages or the marketing site), which period, bots filtered? |
| Activation rate | Signups who reach the activation event within N days / signups of that cohort | What event, within how many days? Cohorts younger than N days excluded? |
| Time to value | Time from signup to the activation event (median, plus the spread) | Same event as activation? Median or average? |
| Free-to-paid | Signups (or trial starts) that start paying within a window / that cohort | Freemium or trial? Card required? Window (Lenny/Poyar use 6 months)? |
| Monthly logo churn | Customers lost in the month / paying customers at the start of the month | Customers or revenue? Monthly or annual? Excludes customers who joined that month? |
| GRR (12 months) | Revenue kept from a cohort after 12 months, without expansion | Cohort-based or one month annualized? |
| NRR (12 months) | Revenue from the same cohort after 12 months, including expansion | Same as GRR; NRR can never be below GRR for the same cohort |
| Month-1 / week-N user retention | Share of a signup cohort active in month 1 or week N | What counts as active? |
| CAC payback | Months of gross-margin-adjusted revenue to recover the cost of acquiring a customer | Blended or paid only? Gross margin included? |

Units the script expects: rates in percent, time to value with a unit ("36 hours"), payback in
months, NRR and GRR as 12-month percentages (a ratio such as 1.12 is accepted with a warning).

## 3. Cohort rates versus period ratios

"95 paid this month / 2,100 signups this month" is a period ratio, not a conversion rate: this
month's payers signed up in earlier months. It is close to the cohort rate only when signups
are steady and the window is short. The facts mark rates computed from `funnel_counts` this
way and the report should too. A cohort rate (signups of March, converted within 6 months)
needs an export with dates; the `import` command computes it and excludes cohorts younger than
the window (`excluded_too_recent`), which a dashboard often does not.

## 4. Activation and the aha moment

- The activation event should be the earliest action that predicts retention, not the end of
  the onboarding checklist. Find it by comparing what retained and churned users did in their
  first days (an event-log export with `import` gives the counts; the choice is a judgment).
- One product's activation rate is only comparable with another's when both use a similar
  event and window. That is why the facts lower confidence when the definition is missing.
- Time to value is a distribution. A median of one day with a long tail of users who take two
  weeks is a different problem (a segment that cannot get set up) from a uniform two days.
  The import reports p25, median, p75, p90 and the share activated within one hour, one day
  and seven days.
- Designing the steps that lead to the event is onboarding-optimizer's job; this skill sizes
  the gap and the value of closing it.

## 5. Retention curves and the flattening signal

- Plot the share of each signup cohort still active in week 1, 2, 3 ... A curve that levels
  off at a non-zero share means a core group keeps getting value; a curve that keeps sliding
  toward zero means the product has not found its retained use case yet, and more acquisition
  mostly buys churn.
- The `import` command averages cohorts (weighted by size), reports weeks 1, 4 and 12, and
  runs a flattening check: the last observed week against the week four periods earlier,
  "flattening" when the curve lost 10% or less of the users still active (a tool convention,
  stated in the output, not an industry threshold). Few cohorts reaching the tail lowers
  confidence; the output says so.
- Compare newer cohorts with older ones before calling a trend: a better curve for recent
  cohorts is the clearest sign that product changes work.
- Revenue retention (GRR, NRR) and usage retention answer different questions: a team can
  keep paying for a product few people use, until renewal.

## 6. Trial and free-offer motions

| Motion | What the user gets | Typical trade-off |
|---|---|---|
| Freemium (self-serve or sales-assisted) | A free plan with limits, no time limit | Many signups, low conversion; upgrade triggers are usage limits and team features |
| Trial without card (opt-in) | Paid features for a fixed time, no payment details | More trial starts than with a card, lower trial-to-paid |
| Trial with card (opt-out) | Paid features for a fixed time, payment details at signup | Fewer trial starts, much higher trial-to-paid; compare paying customers per 1,000 visitors, not the conversion rate alone |
| Reverse trial | Paid features for a time, then a free plan instead of a lockout | Elena Verna describes it as a way to keep trial-style conversion while users stay in the product on the free plan |

Because these motions convert so differently, the skill refuses to compare a rate with a
benchmark of another motion. The card decision itself is best judged on paying customers per
1,000 visitors from the user's own rates, before and after.

## 7. Sources

- Lenny Rachitsky and Yuriy Timen, "What is a good activation rate?" (2022):
  https://www.lennysnewsletter.com/p/what-is-a-good-activation-rate
- Lenny Rachitsky and Kyle Poyar, "What is a good free-to-paid conversion rate?" (2023):
  https://www.lennysnewsletter.com/p/what-is-a-good-free-to-paid-conversion
- Lenny Rachitsky, "What is good retention?" (2020-06-09; denominators by business type, a
  flat curve that supports scalable acquisition can carry a business):
  https://www.lennysnewsletter.com/p/what-is-good-retention-issue-29
- Elena Verna, "Trial or freemium? Get the best of both with a reverse trial", Amplitude
  (first published 2022-09-07, updated 2025-06-03): https://amplitude.com/blog/reverse-trial
- Benchmark definitions and windows: `references/_shared/saas-benchmarks.json`
