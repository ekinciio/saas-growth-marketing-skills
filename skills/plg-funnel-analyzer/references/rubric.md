# PLG Funnel Rubric (plg-rubric-v1)

Last verified: 2026-10

How the model turns the `facts` JSON into dimension scores, the biggest constraint and the
three bets. The script never scores; it reports positions against sourced benchmark rows. The
weights below are the ones `funnel_analyzer.py score` uses (a test keeps them in sync).

## Contents

1. Scoring procedure
2. Dimensions and weights
3. Score anchors
4. Dimension notes
5. Confidence
6. Biggest constraint
7. Bets, experiments and test plans
8. What the report's Details section holds
9. Sources

---

## 1. Scoring procedure

1. Run `facts` and read, for each metric, `comparable`, `benchmark` (source, year, segment),
   `position` (`band`, `performance`, `performance_quartile`, `ratio_to_reference`),
   `confidence` and `caveats`.
2. Group the metrics by `dimension` (the `dimensions` block of the facts lists them).
3. Score each dimension 0-10 with the anchors in section 3. Write one line of justification
   that quotes the number, the reference value and the source, and cite evidence IDs whose
   source is a JSON path such as `facts.metrics.activation_rate.position`.
4. Status:
   - `scored`: at least one metric of the dimension has `comparable: true`, or the retention
     dimension has a flattening check from the user's own export (section 4).
   - `not_measured`: no metric for the dimension, or only metrics with `comparable: false`
     (motion unknown, no row for the segment). Show the number in the report, but never
     invent a score for it. This is how "report the rate without a color" works.
   - `na`: the dimension cannot apply: monetization with no free plan or trial (demo-only
     sales), expansion before the first paying customer, efficiency when the user confirms
     there is no paid acquisition at all.
5. Write `{"dimensions": [{"id", "score", "status", "confidence", "evidence", "justification"}]}`
   and run `score`. Copy `value`, `grade`, `confidence` and `measured_weight` from its output.
   When `composite_shown` is false, show per-dimension scores and the `reason`, no total.
6. Mention `range_if_not_measured_scored_0_to_10` in Details when a dimension is not measured,
   so the reader sees how much the missing data could move the total.

## 2. Dimensions and weights

| id | Dimension | Weight | Metrics in the facts JSON |
|---|---|---|---|
| acquisition | Visitor-to-signup | 10 | `visitor_to_signup` |
| activation | Activation | 20 | `activation_rate` |
| time_to_value | Time to value | 10 | `time_to_value_hours` |
| monetization | Free-to-paid or trial-to-paid | 20 | `free_to_paid` |
| retention | Logo, revenue and usage retention | 25 | `monthly_logo_churn`, `grr`, `month_1_retention`, `week_*_retention`, import `retention.flattening` |
| expansion | Net revenue retention | 10 | `nrr` |
| efficiency | CAC payback | 5 | `cac_payback_months` |

Retention carries the most weight because acquisition and activation gains leak out of a
product that does not keep users. Grades from the total: A 70 or more, B 57-69.9, C 43-56.9,
D 30-42.9, F under 30. A product at its segment's reference on every measured dimension scores
50 (grade C).

## 3. Score anchors

Read `position` in the facts. "Better" means higher for higher-is-better metrics and lower for
churn, time to value and payback. For a lower-is-better metric read the ratio column as
reference / value instead of value / reference.

| Score | Percentile rows (`basis: percentiles`) | Threshold rows (good / great bands) | Mean or single-value rows (`ratio_to_reference`) |
|---|---|---|---|
| 10 | Better than p90, or better than p75 by 25% or more when there is no p90 | Above the top of "great" | 1.75 or more |
| 8-9 | Top quartile | Inside "great" | 1.35 to 1.75 |
| 6-7 | Second quartile (median to p75) | Between "good" and "great", or upper half of "good" | 1.10 to 1.35 |
| 5 | Within 5% of the median | Lower half of "good" | 0.95 to 1.10 |
| 3-4 | Third quartile (p25 to median) | Below "good" by less than 25% | 0.75 to 0.95 |
| 1-2 | Bottom quartile | 50% to 75% of the "good" lower bound | 0.50 to 0.75 |
| 0 | Worse than half of p25 (or double p75 for lower-is-better) | Under half of the "good" lower bound | Under 0.50 |

When a row has only a median, use the mean column with the median as the reference. The ratio
cut-offs are this rubric's conventions for turning a position into a score, not benchmarks;
never quote them as industry data.

Inside a band, pick the higher score when the user's own trend is improving (two or more
periods of data) and the lower one when it is worsening; with one data point use the lower
score of a two-score band.

## 4. Dimension notes

- **Activation.** Benchmark products define "activated" their own way. With no activation
  definition the facts mark confidence low; keep the score but say the comparison is
  indicative. If `ci95` (counts or export) spans more than one anchor band, lower the
  confidence one level.
- **Time to value.** Measured to the activation event. Score it only with the activation
  definition known; otherwise `not_measured` is honest when the user typed a guess.
- **Monetization.** Only score against a row for the same motion (the script enforces this).
  A card-required trial is never compared with freemium or no-card rows. When the user's
  conversion window differs from the row's window the facts set confidence low; say which
  window each number uses.
- **Retention.** Score each comparable metric, weight GRR or logo churn twice as much as
  month-1 usage retention, and average. Then adjust with the flattening check when an export
  was imported: +1 for `flattening`, -1 for `still_declining`, -2 for `falls_to_zero` (stay
  within 0-10). With only a flattening check and no comparable metric: 6 for `flattening`,
  3 for `still_declining`, 1 for `falls_to_zero`; a `too_short` check alone means
  `not_measured`. Week-1/4/12 retention has no verified benchmark; use it for the curve shape,
  never for a percentile claim.
- **Expansion.** NRR from a billing export beats a typed NRR (confidence). When the segment
  row and the ChartMogul billing-panel row disagree, name both and score on the primary row.
- **Efficiency.** CAC payback is computed by subscription-metrics; here it is an input.
  `na` only when there is no paid acquisition at all.

Cross-checks the facts already run (`notes` in the envelope): NRR far above the logo
retention implied by monthly churn, NRR below GRR, visitor-to-signup that does not match the
volumes. Mention any that fired in Diagnosis or Assumptions; do not score around them silently.

## 5. Confidence

- Use the `confidence` the facts give each metric. A comparison with a benchmark is at most
  medium (report contract); high is for facts computed from the user's own export with no
  benchmark (the flattening check, an activation rate from an event log).
- A dimension's confidence is the lowest confidence among the metrics that set its score.
- Typed numbers without a source file are medium at best; numbers the user marked as rough
  guesses are low.

## 6. Biggest constraint

Pick one, in this order:

1. If `impact_model.leaks_ranked` exists, take the highest-ranked leak with medium or high
   confidence. If a low-confidence leak ranks above it (visitor-to-signup often does, because
   its benchmark rows are weak), name it in one sentence as "possibly larger, verify first"
   with the caveat from the facts.
2. If no leak is ranked but `impact_model.sensitivity` exists, use the top sensitivity row and
   say it is "per unit of improvement", because no benchmark target was available.
3. Without an impact model, use `gap_ranking` (largest shortfall with medium or high
   confidence). If the retention dimension scored 3 or lower, or the flattening check says
   `still_declining` or `falls_to_zero`, retention is the constraint even when another gap is
   larger: new users poured into a product that does not keep them do not compound.
4. Tie it to `current_goal` from growth-context.md: say how the constraint limits that goal.

Quote the money: "moving activation from <value> to <reference> (<source>, <year>, <segment>)
is worth about <gain> MRR by month 12 in this model", with the model's assumptions named once. The model
gain is the value of closing the gap, not a forecast of what one experiment will do.

## 7. Bets, experiments and test plans

- Exactly 3 bets in `## Top 3 bets` (report contract section 6), ranked by ICE. The first bet
  attacks the biggest constraint. Add one or two more experiments in Details when the
  constraint needs several, so the user has 3-5 experiments in total.
- Draw each change from `references/experiment-playbook.md`, adapted to this product's motion,
  ICP and activation event. Name the skill that owns the detailed design (onboarding-optimizer,
  web-app-growth-engine, retention-playbook, pricing-analyzer) when the bet needs it.
- Test plan: use `test_sizing.<metric>` from the facts when the bet moves that metric with that
  traffic. Otherwise run the `size` command with the bet's baseline, weekly traffic and the
  minimum effect the user cares about (default 20% relative, stated as an assumption).
  - `feasible: true`: A/B test with `n_per_arm`, `weeks_rounded` (at least 2) and a fixed stop.
  - `feasible: false`: ship and measure, with equal before/after windows of at least 2 full
    weeks, the confounders to watch, and `detectable_relative_change_in_max_weeks_percent` as
    the reason.
  - Conversion and activation tests also wait `readout_delay_days` after the last user enters.
- Expected effect: "unknown until measured" unless a row in `saas-benchmarks.json` supports a
  range. Never reuse the impact model gain as an expected lift.

## 8. What the report's Details section holds

1. Metric table: Metric | Value (unit, period, source) | Benchmark (value, statistic, source,
   year, segment) | Position | Confidence. Metrics with `comparable: false` show the reason.
2. Alternatives when sources disagree (for example Aleph x Benchmarkit vs ChartMogul NRR).
3. Impact model: inputs, assumptions (copy the list), baseline month-12 MRR, leaks ranked with
   both targets, sensitivity table.
4. Test sizing table for the metrics with traffic.
5. Imported data: activation definition and window, eligible signups, time-to-value
   percentiles, the retention checkpoints and the flattening verdict with its rule.
6. Up to two extra experiments (section 7).

## 9. Sources

- Score anchors and the 60% measured-weight rule: `references/_shared/report-contract.md`
  (section 4).
- Benchmark rows and their caveats: `references/_shared/saas-benchmarks.json` (verified
  2026-10-24).
- Retention curve shape as the signal (a flat curve that supports scalable acquisition can
  carry a business): Lenny Rachitsky, "What is good retention?" (2020-06-09),
  https://www.lennysnewsletter.com/p/what-is-good-retention-issue-29
