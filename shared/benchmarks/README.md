# Shared SaaS benchmarks

`saas-benchmarks.json` is the single, sourced benchmark file for every skill and agent in this repo. Each row holds one number (or one set of percentiles) for one metric in one segment, plus the source, year, sample and how it was verified.

Last verified: **2026-10-24**. Freshness rule: a row whose `verified_on` is more than 6 months old must be re-checked with WebSearch/WebFetch before it is quoted. Volatile platform facts (crawler tokens, store limits, API policies, Core Web Vitals, browser versions) live in `../standards/volatile-facts.md`.

## Rules for using a benchmark

1. **Match the definition and the period.** Compare a 12-month cohort NRR with an `annual` row. A single month of MRR movement is graded with `monthly_equivalent`, never against the annual number.
2. **Pick the closest segment** (see "Choosing a row"). If nothing matches, say so and show the nearest row with its segment.
3. **Cite every number in the report**: value, source name, year and segment, for example "median NRR 102% (Aleph x Benchmarkit 2026, FY2025 data, n=230)".
4. **Never grade against a row with `"verified": false`.** It can be mentioned as context with its caveat.
5. **`thresholds` rows are rules of thumb**, not distributions. Say "rule of thumb from <name>", not "top quartile".
6. **When two sources disagree, show both.** Example: B2B median NRR is 102% in the Aleph x Benchmarkit survey but 82% in ChartMogul's billing-data panel. The panels differ (survey respondents vs every ChartMogul customer above $250K ARR, likely with more small self-serve companies), so say which one you used. The same metric can also have different formulas: Aleph's magic number (annual new ARR / prior-period S&M) is not Scale's quarterly one.
7. **Activation and time-to-value depend on the user's own definition.** Ask what event counts as "activated" and in what window before comparing. Mark the comparison low-confidence if the definition differs.

## Reading the file

The file is about 200 KB. Do not read it whole into context. Each row is on one line, so grep or filter it:

```bash
grep '"metric": "nrr"' shared/benchmarks/saas-benchmarks.json
python3 -c "import json;d=json.load(open('shared/benchmarks/saas-benchmarks.json'));[print(r['id'],r['segment'],r['p25'],r['median'],r['p75']) for r in d['rows'] if r['metric']=='grr']"
```

## Schema

Top-level keys:

| Key | Meaning |
|---|---|
| `schema_version` | `"1.0"`. Bump the major version if a row field is renamed or removed. |
| `last_verified` | Date of the last full verification pass. |
| `freshness_rule` | The 6-month re-check rule. |
| `conventions` | Machine-readable notes on percentiles, units, periods and segments (same as this README). |
| `sources` | One entry per source id: name, url, publisher, year, published date, data period, sample note, method. |
| `rows` | The benchmark rows (below). |
| `retention_conversions` | Monthly/annual conversion formulas plus anchor values for GRR, NRR and logo churn. |

Row fields:

| Field | Type | Meaning |
|---|---|---|
| `id` | string | Stable id: `<metric>.<source+year>.<segment>`. Never reuse or rename an id; skills will reference them. |
| `metric` | string | Metric key (see the coverage table). |
| `metric_label` | string | Human label. |
| `definition` | string | How the metric is calculated in this row's source. |
| `unit` | string | `percent` (0-100 scale, 102 means 102%), `months`, `hours`, `ratio` (x:1), `multiple` (x), `percentage_points` (sum of two percentages), `usd`. |
| `period` | string | `annual` (12-month measure), `monthly` (one month), `quarterly`, `cohort` (share of a signup cohort within `window`), `point_in_time` (rate or snapshot without a retention period). |
| `window` | string or null | Measurement window when it matters, for example "within 6 months of signup". |
| `direction` | string | `higher_is_better`, `lower_is_better` or `context` (no good/bad direction, for example ARR at Series A). |
| `segment` | object | See "Segment vocabulary". |
| `p25`, `median`, `p75`, `p90` | number or null | Percentiles of the metric's own distribution. `null` when the source gives none. For `lower_is_better` metrics the best quartile is at or below `p25`. |
| `mean` | number or null | Average, when the source reports one. |
| `value` | number or null | A single figure whose statistic the source does not name (or a value from a segment table). Do not present it as a median. |
| `thresholds` | list or null | Rule-of-thumb bands: `{"label", "min", "max", "note"}`; `min` inclusive, `max` exclusive, either may be missing. |
| `value_note` | string | Caveats, context, prior-year values, internal conflicts in the source. |
| `source_id` | string | Key into `sources`. |
| `source_name`, `source_url` | string | Where the number comes from (the URL is the exact page that was checked). |
| `year` | integer | Publication year of the source. |
| `data_period` | string or null | Period the data describes (often the year before publication). |
| `sample_size` | integer or null | Respondents for this metric, when the source gives it. |
| `sample_note` | string or null | Only set when the row narrows the source's sample; otherwise read `sources[source_id].sample_note`. |
| `verified` | boolean | `true` = the number was read from the source on `verified_on`. `false` = could not be confirmed; `verification_note` says why. |
| `verified_on` | date | Date of the check. |
| `verification_note` | string | How it was checked (page text, PDF chart labels, table image) or why it failed. |
| `confidence` | string | `high` (primary source, explicit number), `medium` (vendor first-party data, statistic not named, chart-read or internally inconsistent source), `low` (unverified or ambiguous). |
| `monthly_equivalent` | object | Only on annual NRR/GRR rows: each statistic converted with `monthly = (annual / 100) ** (1/12) * 100`. |
| `annual_equivalent` | object | Only on monthly logo churn rows: `annual = (1 - (1 - monthly / 100) ** 12) * 100`. |

### Segment vocabulary

| Field | Values used today |
|---|---|
| `motion` | `all`, `plg`, `sales_led`, `hybrid`, `freemium`, `freemium_self_serve`, `freemium_sales_assist`, `free_trial` (card requirement not split), `trial_opt_in` (no credit card), `trial_opt_out` (credit card required) |
| `arr_band` | `all`, `<$300K`, `>=$250K`, `>=$1M`, `$1M-$3M`, `$3M-$5M`, `<$5M`, `$5M-$10M`, `$10M-$20M`, `$3M-$20M`, `$20M-$50M`, `$20M-$100M`, `>$100M` |
| `acv_band` | `all`, `<$5K`, `<$12K`, `$12K-$25K`, `$25K-$50K`, `$50K-$100K`, `$100K-$250K`, `>$250K` |
| `pricing_model` | `all`, `seat`, `usage`, `hybrid` (subscription + usage), `non_seat_subscription` |
| `ai_native` | `true`, `false`, `"mixed"` (sample blends SaaS and AI-native), `null` (not reported) |
| `extra` | Any other cut: `funding` (`bootstrapped`, `equity_backed`), `growth_band`, `contract_term`, `price_point`, `arpa_band`, `company_type` (`b2b_saas`, `b2c_saas`, `public_cloud`), `cohort` (`top_decile`: the figure describes the top 10% of the sample, not a percentile cut-off), `industry`, `traffic_source` (`organic`, `paid`), `form_type`, `tour_type`, `auth_method`, `vertical` |

Add new values only when a source uses them, and document them here.

### Choosing a row

1. Filter by `metric`, a matching `period` and `verified: true`.
2. Prefer the row whose segment matches the user on the most dimensions, in this order: ARR band or ACV band, pricing model (seat vs usage), motion, AI-native, then `extra`.
3. Among equal matches prefer the newer `year`, then higher `confidence`.
4. Fall back to the `all` row and say which segment was used.

## Coverage (155 rows)

| Metric | Sources | Notes |
|---|---|---|
| NRR | Aleph x Benchmarkit 2026, ChartMogul Dec 2025, SaaS Capital 2025 and 2026 | Overall, ARR band, ACV band (with quartiles), seat vs usage, AI-native and price point, funding, contract term |
| GRR | Same as NRR | Overall quartiles, GTM motion (sales-led 88, hybrid 80, PLG 79), ACV, AI-native |
| Logo churn (monthly) | ChartMogul 2022 | By ARPA and ARR band; older data, `confidence` medium/low |
| CAC payback | Aleph x Benchmarkit 2026, David Skok | Quartiles, ACV, growth band, horizontal vs vertical |
| LTV:CAC | Aleph x Benchmarkit 2026, David Skok | Quartiles (1.1x / 4.1x / 7.8x), vertical vs horizontal, ARR band, growth band; Skok's >3 rule of thumb |
| Rule of 40 / Rule of X | Aleph x Benchmarkit 2026, SaaS Capital 2025, Bessemer 2024 | All-company quartiles (7 / 25 / 43), growth band, pricing model; private medians by ARR band and funding; public index average and top decile |
| Burn multiple | David Sacks 2020 | Rule-of-thumb bands (no verified distribution) |
| Magic number | Aleph x Benchmarkit 2026, Scale Venture Partners 2020 | Quartiles (0.68 / 1.37 / 2.14) on Aleph's annual new-ARR formula; Scale's 0.7 baseline on the quarterly formula |
| Quick ratio | Mamoon Hamid (SaaStr) | 4+ desirable |
| Free-to-paid / trial-to-paid | Lenny Rachitsky and Kyle Poyar 2023, First Page Sage 2025 | By motion; opt-in (no card) vs opt-out (card required); organic vs paid traffic (First Page Sage figures are averages, stored in `mean`) |
| Visitor-to-signup | First Page Sage 2025, Lenny/Poyar 2023 | By motion |
| SaaS landing page conversion | Unbounce 2024 | SaaS median 3.8% vs 6.6% all industries |
| Signup form conversion | Zuko (2022-2025 data) | Registration forms: 46.6% view-to-completion, 60.7% starter-to-completion (table averages, stored in `mean`) |
| Passkeys | FIDO Passkey Index 2026 | 36% of sign-ins; 93% vs 78% success |
| Activation rate | Lenny/Timen 2022, Userpilot 2024 and 2025 | Overall, SaaS-only, PLG vs sales-led |
| Time to value | Userpilot 2024 and 2025 | Hours |
| Onboarding tour and checklist completion | Chameleon 2024, Userpilot 2025 | Tour 33.5% average; 64% when user-launched; 21.6% at five steps |
| Month-1 user retention | Userpilot 2025 | Product usage retention |
| ARR growth by stage | SaaS Capital 2025 and 2026 | By ARR band and funding |
| ARR at Series A | Carta citing SVB | `verified: false` |

### Headline numbers (quick reference)

| Metric | p25 | Median | p75 | Monthly equivalent of median | Row id |
|---|---|---|---|---|---|
| NRR, all B2B SaaS | 92% | 102% | 108% | 100.17% | `nrr.aleph2026.all` |
| NRR, <$5M ARR | - | 94% | - | 99.49% | `nrr.aleph2026.arr_lt5m` |
| NRR, seat / usage pricing | - | 98% / 108% | - / 155% | 99.83% / 100.64% | `nrr.aleph2026.seat`, `nrr.aleph2026.usage` |
| NRR, B2B SaaS (ChartMogul billing panel, >=$250K ARR) | - | 82% | 97% | 98.36% | `nrr.chartmogul2025.b2b` |
| NRR, AI-native | - | 48% | - | - | `nrr.chartmogul2025.ai_native` |
| GRR, all B2B SaaS | 76% | 84% | 91% | 98.56% | `grr.aleph2026.all` |
| CAC payback (months, lower is better) | 10 | 16 | 24 | - | `cac_payback.aleph2026.all` |
| LTV:CAC | 1.1x | 4.1x | 7.8x | - | `ltv_to_cac.aleph2026.all` |
| Magic number (Aleph formula) | 0.68 | 1.37 | 2.14 | - | `magic_number.aleph2026.all` |
| Rule of 40 (points) | 7 | 25 | 43 | - | `rule_of_40.aleph2026.all` |

## Monthly-equivalent thresholds

Annual retention converts to a constant monthly rate with `monthly = annual ** (1/12)`. Monthly logo churn converts to annual with `annual = 1 - (1 - monthly) ** 12`. These assume a constant rate on a closed cohort, so cohort-based 12-month NRR/GRR stays the primary measure; the conversions are for grading one month of movement and for sanity checks.

| Annual GRR | Monthly GRR | Monthly gross revenue churn |
|---|---|---|
| 95% | 99.57% | 0.43% |
| 91% | 99.22% | 0.78% |
| 90% | 99.13% | 0.87% |
| 85% | 98.65% | 1.35% |
| 84% (median) | 98.56% | 1.44% |
| 80% | 98.16% | 1.84% |
| 76% (p25) | 97.74% | 2.26% |

| Annual NRR | Monthly NRR | Monthly net revenue churn |
|---|---|---|
| 120% | 101.53% | -1.53% |
| 110% | 100.80% | -0.80% |
| 108% (p75) | 100.64% | -0.64% |
| 102% (median) | 100.17% | -0.17% |
| 100% | 100.00% | 0.00% |
| 92% (p25) | 99.31% | 0.69% |

| Monthly logo churn | Annual logo churn |
|---|---|
| 1% | 11.4% |
| 2% | 21.5% |
| 3% | 30.6% |
| 5% | 46.0% |
| 8% | 63.2% |

The full anchor lists are in `retention_conversions` in the JSON.

## Updating the file

- Verify every new number against its source the same day and set `verified_on`. If a number cannot be verified, either leave it out or add it with `"verified": false`, `"confidence": "low"` and the reason in `verification_note`. Never invent a percentile the source does not give; use `null`.
- Keep one row per line, keep `id`s stable, and add a new row (new id) for a new source year instead of overwriting the old row, so reports stay reproducible. Mark superseded rows in `value_note`.
- When a value changes, recompute `monthly_equivalent` / `annual_equivalent` with the formulas above (two decimals for retention, one for churn).
- No em dashes or en dashes anywhere; use a plain hyphen.

## Numbers checked and left out

| Claim | Why it is not in the file |
|---|---|
| Recurly churn benchmarks (SaaS 3.22%, all industries 3.60%, July 2026 data) | The page does not say whether the rates are monthly or annual and gives two different SaaS figures (3.04% and 3.22%). |
| Median burn multiple from KeyBanc 2024-2025 or any other survey (for example "median 1.8x, top quartile 1.1x") | Only secondary blog summaries were found; the KeyBanc report is gated and Aleph publishes no burn-multiple page. (Aleph's Rule of 40, magic number and LTV:CAC pages are public and are in the file.) |
| Aleph Rule of 40 margin basis | The page does not say whether the 25% median uses EBITDA, operating or free-cash-flow margin; the row says so. |
| Aleph LTV:CAC for "low-growth companies" (3.2x) | The page does not name the growth band. |
| ARR growth by ARR band from Benchmarkit (for example "<$1M ARR grows 85%") | Secondary source only. |
| Userpilot 2025 PLG vs sales-led splits for activation and TTV | Shown only in charts on the page; the 2024 report's text values are used instead. |
| Chameleon completion for 3- and 4-step tours | Not stated in the 2024 report text (only the five-step 21.6%). |
| Lenny/Timen "good" and "great" activation thresholds as numbers | Given only as percentiles (60th and 80th) with values in a chart image. |

## Known conflicts to migrate

These thresholds are hard-coded in skills today and disagree with each other or with this file. Line numbers are against commit `c6eb6b2`. The next commit, `7340be2`, already changed several of these files (subscription-metrics B02/B19, plg-funnel-analyzer B20, pricing-analyzer B18, landing-page-cro B01; for example `saas-metrics-guide.md` now grades monthly NRR/GRR on 100.80% / 99.13%), and other batches keep editing them, so re-grep the quoted text before editing. Migration means: read the row from this file, cite it, and delete the local copy of the number.

### Retention and churn

| File:line (c6eb6b2) | Hard-coded today | Benchmark file says | Rows |
|---|---|---|---|
| `skills/subscription-metrics/scripts/metrics_calculator.py:90` | Monthly logo churn GREEN <2%, YELLOW <5% | Depends on ARPA: median 6.1%/mo under $25 ARPA, 2.2%/mo above $500 ARPA. The same 5% is "median" (YELLOW) in plg-funnel-analyzer. | `logo_churn.chartmogul2022.*` |
| `skills/subscription-metrics/scripts/metrics_calculator.py:91` | Monthly revenue churn GREEN <2%, YELLOW <4% | 2%/mo = 78.5% annual GRR, below the 84% median; median GRR 84% = 1.44%/mo; 90% GRR = 0.87%/mo; 80% = 1.84%/mo | `grr.aleph2026.all`, `retention_conversions.grr` |
| `skills/subscription-metrics/scripts/metrics_calculator.py:92` | NRR GREEN >=110, YELLOW >=100, applied to one month of movement | Annual: p25 92 / median 102 / p75 108. One month: median 100.17%, 110% annual = 100.80%/mo | `nrr.aleph2026.all` |
| `skills/subscription-metrics/scripts/metrics_calculator.py:93` | GRR GREEN >=90, YELLOW >=80, applied to one month | Annual: p25 76 / median 84 / p75 91 (Aleph), median 91 (SaaS Capital). 90% annual = 99.13%/mo | `grr.aleph2026.all`, `grr.saascap2025.all` |
| `skills/subscription-metrics/scripts/metrics_calculator.py:100` | Expansion MRR rate GREEN >5%/mo, YELLOW >2%/mo | No verified source; 5%/mo expansion alone compounds to about 80% a year | none |
| `skills/subscription-metrics/scripts/metrics_calculator.py:290` | Net revenue churn GREEN <0, YELLOW <=1%/mo | 110% annual NRR = -0.80%/mo; 100% = 0%; median 102% = -0.17%/mo | `retention_conversions.nrr` |
| `skills/subscription-metrics/references/saas-metrics-guide.md:79-80` | Logo churn "<2% monthly SMB" next to "<10% annual SMB" | 2% monthly = 21.5% annual; the two lines contradict each other | `retention_conversions.logo_churn` |
| `skills/subscription-metrics/references/saas-metrics-guide.md:92-93` | Revenue churn "<2% monthly SMB", best-in-class <0.5% | See line 91 above | `grr.*` |
| `skills/subscription-metrics/references/saas-metrics-guide.md:106-107` | Net revenue churn best-in-class -2% to -5% monthly | -2%/mo = 126.8% annual NRR and -5%/mo = 179.6%; the p75 is 108% (-0.64%/mo) | `nrr.aleph2026.all` |
| `skills/subscription-metrics/references/saas-metrics-guide.md:362-367` | NRR bands (>120 best, 110-120 excellent, 100-110 solid, "~101-106% 2025 median", <90 critical) | Median 102, p25 92 (so a bottom-quartile company is not "critical"); <$5M ARR median 94; seat 98 vs usage 108 | `nrr.aleph2026.*` |
| `skills/subscription-metrics/references/saas-metrics-guide.md:389-393` | GRR bands (>95 exceptional ... <80 serious) | p25 76 / median 84 / p75 91; ACV >$250K median 95 | `grr.aleph2026.all`, `grr.saascap2025.acv_*` |
| `skills/subscription-metrics/references/saas-metrics-guide.md:437-439` | Expansion MRR rate bands | No verified source | none |
| `skills/subscription-metrics/references/saas-metrics-guide.md:453-456` | Summary table: logo churn, revenue churn, NRR, GRR | As above | as above |
| `skills/subscription-metrics/SKILL.md:112-114` | Example benchmarks: logo churn <2%, revenue churn <2%, NRR ">100%" (script says >=110 for GREEN) | Internal conflict with the script; see rows above | `nrr.*`, `grr.*` |
| `skills/plg-funnel-analyzer/scripts/funnel_analyzer.py:58-64` | Monthly churn bottom 25% 8%, median 5%, top 25% 3% | No verified percentile source; ChartMogul ARPA medians 2.2%-6.1%; conflicts with metrics_calculator (5% is RED there) | `logo_churn.chartmogul2022.*` |
| `skills/plg-funnel-analyzer/scripts/funnel_analyzer.py:67-73` | NRR bottom 25% 95, median 105, top 25% 120 | p25 92 / median 102 / p75 108; 120%+ is "best-in-class", not top quartile | `nrr.aleph2026.all` |
| `skills/plg-funnel-analyzer/SKILL.md:122-123` | Same churn and NRR table | As above | as above |
| `skills/plg-funnel-analyzer/references/funnel-benchmarks.md:11-12, 49-51, 71, 111-112` | Monthly churn SMB 8/5/3, mid-market 5/3/1.5, annual churn 40/25/15, NRR 95/105/120, NRR by stage 90-130 | As above; no verified source for the churn or stage tables | as above |
| `skills/plg-funnel-analyzer/references/plg-metrics.md:181` | "NRR above 120% ... best-in-class (not merely top-quartile)" | Consistent with Aleph (120%+ best-in-class); keep but cite | `nrr.aleph2026.all` |
| `skills/retention-playbook/SKILL.md:59-61` | Demo: monthly logo churn 6.5%, monthly revenue churn 4.2%, NRR 97 | 4.2%/mo revenue churn = 59.8% annual GRR, so a 97% annual NRR would need about 37 points of expansion a year; implausible for a demo and teaches the wrong relationship | `retention_conversions` |
| `skills/retention-playbook/SKILL.md:241-243` | NRR >100% "gold standard"; 3% monthly = about 31% annual; involuntary churn 20-40% of churn | 3% = 30.6% (correct). Median NRR is 102%, so >100% is roughly median, not gold standard. No verified source for 20-40% involuntary | `nrr.aleph2026.all` |
| `agents/metrics-analyst.md:80` | Monthly churn benchmark "<5%" | Conflicts with metrics_calculator (<2% GREEN) and plg-funnel-analyzer (5% = median) | `logo_churn.*` |

### Unit economics and efficiency

| File:line (c6eb6b2) | Hard-coded today | Benchmark file says | Rows |
|---|---|---|---|
| `skills/subscription-metrics/scripts/metrics_calculator.py:94` | LTV:CAC GREEN >=3, YELLOW >=2, >5 "over-invest" | Aleph 2026: p25 1.1x / median 4.1x / p75 7.8x; 3x minimum, 4-5x healthy, 7x+ top-tier, only "far above 8x" may signal under-investment. Skok: >3 is good, the best reach 7-8. No source treats >5 as a penalty | `ltv_to_cac.aleph2026.all`, `ltv_to_cac.skok.rule` |
| `skills/subscription-metrics/scripts/metrics_calculator.py:95` | Payback GREEN <18 months, YELLOW <24 | p25 10 / median 16 / p75 24 months; plg-funnel-analyzer calls <6 "top 25%" | `cac_payback.aleph2026.all` |
| `skills/subscription-metrics/scripts/metrics_calculator.py:96` | Rule of 40 GREEN >=40, YELLOW >=30 | Aleph 2026 (all companies): p25 7 / median 25 / p75 43, and the page says it only becomes meaningful from about $20M ARR. SaaS Capital private medians 7-45.5 by ARR band and funding (equity-backed all: 15; bootstrapped all: 34.5); public index average about 31 | `rule_of_40.aleph2026.all`, `rule_of_40.saascap2025.*` |
| `skills/subscription-metrics/scripts/metrics_calculator.py:97` | Burn multiple GREEN <1.5, YELLOW <3 | Sacks: <1 amazing, 1-1.5 great, 1.5-2 good, 2-3 suspect, >3 bad | `burn_multiple.sacks.rule` |
| `skills/subscription-metrics/scripts/metrics_calculator.py:98` | Quick ratio GREEN >=4, YELLOW >=2 | Hamid: 4+ desirable, near 2 warning, 1 critical (consistent) | `quick_ratio.hamid.rule` |
| `skills/subscription-metrics/scripts/metrics_calculator.py:99` | Magic number GREEN >=0.75, YELLOW >=0.5 | Aleph 2026: <0.75 audit GTM, 0.75-1.0 acceptable, >1.0 strong; p25 0.68 / median 1.37 / p75 2.14 (annual new-ARR formula). Scale: 0.7 is a healthy baseline (quarterly formula). No source found for 0.5. The script's formula must match the row it grades against | `magic_number.aleph2026.all`, `magic_number.scale.rule` |
| `skills/subscription-metrics/references/saas-metrics-guide.md:146, 191, 212-216` | LTV:CAC bands (5:1+ YELLOW) | See line 94 above | `ltv_to_cac.aleph2026.all`, `ltv_to_cac.skok.rule` |
| `skills/subscription-metrics/references/saas-metrics-guide.md:234-238` | Payback bands (<12 excellent, 12-18 good, 18-24 YELLOW) | See line 95 above | `cac_payback.*` |
| `skills/subscription-metrics/references/saas-metrics-guide.md:260-263` | Rule of 40: 20-30% YELLOW (script says <30 RED) | Internal conflict; see line 96 above | `rule_of_40.*` |
| `skills/subscription-metrics/references/saas-metrics-guide.md:289-293` | Burn multiple: 1.5-2x YELLOW | Sacks calls 1.5-2x "good" | `burn_multiple.sacks.rule` |
| `skills/subscription-metrics/references/saas-metrics-guide.md:313-316` | Quick ratio 2-4 "healthy (GREEN)" (script and summary table: YELLOW) | Internal conflict | `quick_ratio.hamid.rule` |
| `skills/subscription-metrics/references/saas-metrics-guide.md:337-340` | Magic number bands 1.0 / 0.75 / 0.5 | 1.0 and 0.75 match Aleph 2026; 0.5 has no source. See line 99 above | `magic_number.aleph2026.all` |
| `skills/subscription-metrics/references/saas-metrics-guide.md:457-463` | Summary table for LTV:CAC, payback, Rule of 40, burn, quick ratio, magic number, expansion | As above | as above |
| `skills/plg-funnel-analyzer/scripts/funnel_analyzer.py:85-91` | Payback 24 / 16 / 6, comment "Benchmarkit 2025" | Figure is from the 2026 Aleph x Benchmarkit report (FY2025 data); explicit p25 is 10, the "<=6 top quartile" line conflicts with the same page | `cac_payback.aleph2026.all` |
| `skills/plg-funnel-analyzer/SKILL.md:125` and `references/funnel-benchmarks.md:14, 16, 74-75` | Payback table, "Benchmarkit 2025" citation, LTV/CAC 2 / 3-4 / 6 | As above; LTV:CAC quartiles are 1.1x / 4.1x / 7.8x (Aleph 2026) | `cac_payback.*`, `ltv_to_cac.aleph2026.all` |
| `skills/plg-funnel-analyzer/references/funnel-benchmarks.md:22-23` | CAC (SMB) $200-300 median, mid-market $2,000-3,000 | No verified source | none |
| `agents/metrics-analyst.md:83-84` | LTV:CAC ">3:1", Rule of 40 ">40%" | Both are rules of thumb: median LTV:CAC is 4.1x and median Rule of 40 is 25 (Aleph 2026); cite the rows | `ltv_to_cac.aleph2026.all`, `rule_of_40.aleph2026.all` |

### Conversion, activation and onboarding

| File:line (c6eb6b2) | Hard-coded today | Benchmark file says | Rows |
|---|---|---|---|
| `skills/plg-funnel-analyzer/scripts/funnel_analyzer.py:40-46` | Signup-to-active 15 / 25 / 40 | Median 25% (all products) or 30% (SaaS only); Userpilot B2B median 37% | `activation_rate.*` |
| `skills/plg-funnel-analyzer/scripts/funnel_analyzer.py:49-55` | Free-to-paid 2 / 5 / 10 for every motion | Depends on motion: freemium self-serve good 3-5%, freemium sales-assist 5-7%, free trial 8-12%; opt-out (card) trial-to-paid 48.8% | `free_to_paid.*`, `trial_to_paid.*` |
| `skills/plg-funnel-analyzer/scripts/funnel_analyzer.py:76-82` | Time-to-value 7 / 3 / 1 days | Userpilot B2B median 25.9 hours (about 1.1 days), mean 36.4 hours | `time_to_value.userpilot2025.b2b` |
| `skills/plg-funnel-analyzer/SKILL.md:120-121, 124, 170-171` | Same activation, free-to-paid and TTV values | As above | as above |
| `skills/plg-funnel-analyzer/references/funnel-benchmarks.md:9-10, 13, 24, 26, 32-36, 68-70, 77, 109-110` | Activation 15/25/40, free-to-paid 2/5/10, TTV, signup completion 50/70/85, website-to-signup 1/2-3/5, onboarding completion, trial-to-paid no card 8-12% and card 45-50%, stage tables | As above; visitor-to-signup by motion: opt-in trial 8.5%, opt-out 2.5%, freemium 13.3% (organic); SaaS landing page median 3.8% | `visitor_to_signup.*`, `landing_page_conversion.*` |
| `skills/plg-funnel-analyzer/references/plg-metrics.md:111-114` | TTV bands (<5 min best, <1 day good, 1-3 days average, >7 days poor) | Userpilot median about 1.1 days | `time_to_value.*` |
| `skills/plg-funnel-analyzer/references/plg-metrics.md:142-147` | Activation by product type (collaboration 30%, dev tools 20% ...) | No verified source (Userpilot gives different industry cuts) | `activation_rate.userpilot2025.b2b` |
| `skills/plg-funnel-analyzer/references/plg-metrics.md:153-157, 159` | Conversion by model: freemium 2-3%, trial no card 8-12%, card 45-50%, reverse trial 15-20%, usage free tier 4-6% | Freemium 2.6-2.8% and opt-out 48.8-51% match First Page Sage; reverse trial and usage-based rows have no verified source | `trial_to_paid.fps2025.*`, `free_to_paid.*` |
| `skills/plg-funnel-analyzer/references/plg-metrics.md:177-179` | Expansion as % of new ARR by stage | No verified source | none |
| `skills/pricing-analyzer/references/pricing-models.md:148` | "typical conversion rates are 2-5%" for free users | Freemium-to-paid 2.6% (organic); freemium self-serve good 3-5% | `trial_to_paid.fps2025.freemium.*`, `free_to_paid.lenny2023.freemium_self_serve` |
| `skills/web-app-growth-engine/SKILL.md:240-244` | Signup conversion by industry (B2B SaaS 2-5% average, 8-12% excellent ...) | No verified source for the industry split; use visitor-to-signup by motion and the Unbounce SaaS median | `visitor_to_signup.*`, `landing_page_conversion.*` |
| `skills/web-app-growth-engine/SKILL.md:249-251` | Activation by product type (freemium 20-30%, trial 15-25%, PLG 25-35% average) | Lenny SaaS median 30%; Userpilot PLG 34.6% vs sales-led 41.6% | `activation_rate.*` |
| `skills/web-app-growth-engine/references/activation-metrics.md:132-138, 144-148, 171, 188, 205, 210-222` | Funnel step rates and activation by business model | No verified source for these tables | `activation_rate.*` |
| `skills/web-app-growth-engine/references/signup-funnel-patterns.md:18-28, 60-61, 99-101, 107-117, 143-167` | SSO adoption shares, SSO and field-count lift percentages, per-vertical card and verification rates | No verified source; passkeys are 36% of sign-ins with 93% vs 78% success (FIDO 2026) | `passkey_signin_share.fido2026`, `signin_success_rate.*` |
| `skills/web-app-growth-engine/references/signup-funnel-patterns.md:172-175, 180` | Landing-to-signup-start 2-5% average, signup start-to-complete 30-50% average, "card reduces signups 60-80%" | Registration form starter-to-completion 60.7%, view-to-completion 46.6%; visitor-to-trial opt-in 8.5% vs opt-out 2.5% | `form_*.zuko.*`, `visitor_to_signup.fps2025.*` |
| `skills/web-app-growth-engine/scripts/signup_auditor.py:520, 527, 553, 561` | Lift claims in recommendations (field count 5-10%, SSO 30-50% and 85-95%, card 60-80%, trust signals 10-20%) | No verified source; remove or cite | none |
| `skills/web-app-growth-engine/scripts/signup_auditor.py:591-599` | "Top 10% / Top 25% of SaaS signup flows", "losing 30-50% / 50-70% of signups" | No dataset behind these percentiles | none |
| `skills/onboarding-optimizer/references/onboarding-patterns.md:37` | Tour completion target >60% | Chameleon 2024 average 33.5%; 64% when user-launched; 21.6% for five-step tours (61% was the 2019 figure) | `tour_completion.chameleon2024.*` |
| `skills/onboarding-optimizer/references/onboarding-patterns.md:114, 192` | Wizard completion >70%, empty-state CTA >30% | No verified source; Userpilot checklist completion mean 19.2%, median 10.1% | `checklist_completion.userpilot2025.b2b` |
| `skills/onboarding-optimizer/scripts/onboarding_scorer.py:236-244` | Time to first value <5 min excellent, <=15 acceptable | No verified minute-level source; Userpilot median TTV is about 26 hours (activation-event based) | `time_to_value.*` |
| `skills/onboarding-optimizer/scripts/onboarding_scorer.py:349-482` | Hard-coded activation-lift ranges per recommendation (for example 15-30%, 10-25%) and claims at :381, :403, :448, :459 | No verified source; do not present lift estimates as data | none |

### Growth and stage

| File:line (c6eb6b2) | Hard-coded today | Benchmark file says | Rows |
|---|---|---|---|
| `skills/subscription-metrics/references/saas-metrics-guide.md:27` | MoM MRR growth 10-20% early, 5-10% growth, 2-5% scale | Annual growth medians: 22% overall (2025); by ARR band 12-39% depending on funding | `arr_growth.*` |
| `skills/subscription-metrics/references/saas-metrics-guide.md:53-57` | ARR by stage: Seed $100K-$500K, Series A $500K-$3M, Series B $3M-$15M | Series A median about $2.8M in 2025 is reported by Carta/SVB but unverified | `arr_at_series_a.carta_svb.2025` |
| `skills/subscription-metrics/SKILL.md:154-158` | MRR by stage: Series A $50K-$250K MRR ($0.6M-$3M ARR) | Conflicts with guide lines 53-57; see above | as above |
| `skills/plg-funnel-analyzer/references/funnel-benchmarks.md:107-113` | Stage table (MRR, MoM growth, activation, free-to-paid, churn, NRR, team size per $1M ARR) | No verified source for the stage splits | `arr_growth.*`, `nrr.aleph2026.arr_*` |
