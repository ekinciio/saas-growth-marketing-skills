# Funnel Benchmarks: How They Are Chosen

Last verified: 2026-10

This file explains which benchmark the skill compares each funnel number with, and why. The
numbers themselves live only in `references/_shared/saas-benchmarks.json` (synced from
`shared/benchmarks/`); the `facts` and `benchmarks` commands print them with source, year,
segment and confidence. Never type a benchmark number into a report from memory or from this
file.

## Contents

1. Choosing a row
2. Motion: why free-to-paid has no single benchmark
3. Metric by metric
4. Known gaps (no verified benchmark)
5. When sources disagree
6. Sources

---

## 1. Choosing a row

The script filters rows by metric and period, keeps only `verified: true` rows, and drops any
row whose segment the user is not in. Among the rest it prefers, in this order (the order of
the benchmark README):

1. ARR band or ACV band (inside the band beats partly overlapping). ARR comes from
   `context.arr`, `context.arr_band` or MRR x 12; ACV from `context.acv` or ARPA x 12.
2. Pricing model (seat or usage).
3. Motion (freemium, trial with or without card, or plg / sales-led / hybrid).
4. AI-native.
5. Other cuts (B2B or B2C, traffic source, ARPA band, funding, contract term).
6. Then the newer year, the higher row confidence, and rows with percentiles over single
   values. Equal rows are taken in id order, so the choice is repeatable.

A row cut by something the user did not give (for example an ARPA band when ARPA is unknown)
is not used. Panels that only set a floor (ChartMogul's "companies above $250K ARR") still
apply when ARR is unknown. When nothing matches, the facts say why and list the nearest rows
for context; that metric is not scored.

The primary row sets the position and the target. Up to three alternatives follow, one per
other source first, so a report can show both sides when sources disagree.

## 2. Motion: why free-to-paid has no single benchmark

A card-required trial, a no-card trial and a freemium plan convert at rates several times
apart, so comparing them with one number is the classic error (a card-required trial looks
elite, a good freemium product looks average). The script only compares a free-to-paid or
visitor-to-signup rate with rows for the same motion:

| context.motion | Free-to-paid rows used | Visitor-to-signup rows used |
|---|---|---|
| `freemium_self_serve` | Lenny/Poyar freemium self-serve, then First Page Sage freemium | First Page Sage and Lenny/Poyar freemium |
| `freemium_sales_assist` | Lenny/Poyar freemium sales-assist, then First Page Sage freemium | as above |
| `freemium` (sales assist unknown) | First Page Sage freemium, then both Lenny/Poyar freemium rows | as above |
| `trial_no_card` | First Page Sage opt-in trial, then Lenny/Poyar free trial (card not split) | First Page Sage opt-in, Lenny/Poyar free trial |
| `trial_card_required` | First Page Sage opt-out trial only | First Page Sage opt-out |
| `trial` (card unknown), `reverse_trial`, `no_free_offer`, unknown | none: the rate is shown, not compared | none |

Motion comes from `context.motion`, or from growth-context.md (`free_offer` plus
`card_required`, and `gtm_motion` for freemium). The `pricing` command quotes the pricing page
wording (free plan, trial length, "no credit card required", per-seat or usage pricing,
contact sales) so the model can infer it; an inferred motion is an assumption in the report.

Windows matter too. Lenny/Poyar count conversions within 6 months of signup. First Page Sage
does not state a window and counts a single paid month as a conversion, which overstates
retained paying customers. Ask the user for their window and say which window each number
uses.

## 3. Metric by metric

| Metric | Row family | Notes |
|---|---|---|
| Visitor-to-signup | `visitor_to_signup.fps2025.*`, `visitor_to_signup.lenny2023.*` | Averages and an unnamed statistic; depends on which visitors are counted. Confidence is capped at low. |
| Activation rate | `activation_rate.lenny2022.*`, `activation_rate.userpilot2025.b2b`, `activation_rate.userpilot2024.*` | Every product defines activation its own way; ask for the event and window. |
| Time to value | `time_to_value.userpilot2025.b2b`, `time_to_value.userpilot2024.*` | Hours from signup to the activation event. The 2025 median label is inferred by the benchmark file (see its note). |
| Free-to-paid | `free_to_paid.lenny2023.*` (rules of thumb: good and great bands), `trial_to_paid.fps2025.*` (averages) | Section 2. "Good" and "great" are rules of thumb, not percentiles. |
| Monthly logo churn | `logo_churn.chartmogul2022.*` | Cut by ARPA (under $25 or over $500 a month) and ARR (under $300K, $1M-$3M); 2021-22 data, so confidence is low. No row for mid ARPA: the facts list the nearest rows. |
| GRR | `grr.aleph2026.*`, `grr.saascap2025.*`, `grr.chartmogul2025.ai_native*` | 12-month. Aleph splits by GTM motion (PLG, hybrid, sales-led) and ACV. |
| NRR | `nrr.aleph2026.*`, `nrr.saascap2025.*`, `nrr.chartmogul2025.*` | 12-month. Split by ARR, ACV, seat vs usage pricing, AI-native, funding and contract term. |
| Month-1 user retention | `month_1_retention.userpilot2025.b2b` | Product usage retention, not revenue. |
| CAC payback | `cac_payback.aleph2026.*`, `cac_payback.skok.rule` | Lower is better. Computed by subscription-metrics; here it is an input. |

Monthly churn and annual retention are different periods. The facts convert monthly logo churn
to its annual equivalent (`1 - (1 - c)^12`) and NRR or GRR to a monthly equivalent
(`annual^(1/12)`) so they can be read side by side; the benchmark README holds the formulas.

## 4. Known gaps (no verified benchmark)

Say "no verified benchmark" for these, and judge them from the user's own data and trend:

- Week-1, week-4 and week-12 user retention. Use the flattening check of the imported curve.
- Reverse-trial conversion.
- Viral coefficient, invite acceptance, referral conversion, NPS.
- DAU/MAU, onboarding completion, day-1 return, signup completion by stage.
- Benchmarks by company stage (activation or churn "for a Series A company").
- Monthly churn for ARPA between $25 and $500 a month.

Older versions of this skill printed numbers for several of these. They had no verifiable
source and were removed.

## 5. When sources disagree

- NRR: survey-based Aleph x Benchmarkit medians sit well above ChartMogul's billing-data panel,
  which includes more small self-serve companies. Name both, say which one is primary for the
  user's segment, and score on the primary.
- Free-to-paid for freemium: Lenny/Poyar give rule-of-thumb bands with a 6-month window;
  First Page Sage gives agency-sample averages. The impact model ranks leaks on the more
  conservative of the two targets (the one closer to the user's current value).
- Activation: Lenny/Timen (all SaaS, survey) and Userpilot (B2B SaaS, product data) differ;
  activation definitions differ more than the samples do.

## 6. Sources

All rows, with exact URLs, sample notes and verification dates:
`references/_shared/saas-benchmarks.json` (last verified 2026-10-24). Headline sources:

- Aleph x Benchmarkit, 2026 SaaS & AI Performance Benchmarks (FY2025 data)
- ChartMogul, "The AI churn wave" (December 2025) and "What is a good customer churn rate?"
  (2022 data)
- SaaS Capital retention benchmarks (2025, 2026)
- Lenny Rachitsky and Kyle Poyar, "What is a good free-to-paid conversion rate?" (2023)
- Lenny Rachitsky and Yuriy Timen, "What is a good activation rate?" (2022)
- First Page Sage, SaaS free trial conversion rate benchmarks (2025)
- Userpilot, SaaS Product Metrics Benchmark Report (2024, 2025)
