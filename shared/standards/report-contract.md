# Report Contract

Every report a skill or agent in this toolkit writes follows this contract. Read it before
writing a report. It replaces the old per-skill "Output Rules" blocks and
`templates/report-template.md`; where a SKILL.md disagrees with this file, this file wins.

## Contents

1. Scoring switch
2. File, location and language
3. Report structure
4. Scores in each mode
5. Evidence and confidence
6. Top 3 bets: ICE and traffic-aware test plans
7. Ready-to-ship assets
8. Bans
9. Change since last run
10. JSON sidecar
11. Chat summary
12. Runs inside a subagent or orchestrator
13. Skeleton

---

## 1. Scoring switch

```
scoring_mode: rubric
```

This one line decides how every skill presents scores. Allowed values:

| Value | Meaning |
|---|---|
| `deterministic` | Scores come from the scripts, exactly as they emit them. |
| `rubric` | The model scores each dimension against the skill's written rubric, cites evidence and a confidence level for each score, and a script computes the total. |
| `none` | No 0-100 scores, letter grades or "X of N" counts. The report leads with findings and evidence. |

Status: the default mode is an open maintainer decision. The value above follows the
recommendation of the 1.2 review (`rubric`) until that decision is made. To change it, edit
only this line in `shared/standards/report-contract.md` and run `python3 tools/sync_shared.py`
so every skill's `_shared/` copy picks it up. Scripts and report helpers read the value with
the multiline regex `^scoring_mode: *(deterministic|rubric|none) *$`.

What the switch covers: composite quality scores and grades, such as the CRO score, AI-search
readiness score, citability score, ASO listing score, signup friction score, onboarding score,
local SEO score, PLG funnel grade, SaaS health grade and section completeness ("9/12").

What it never covers: computed metrics. MRR, ARR, churn, NRR, conversion rates, character
counts, sample sizes, Van Westendorp price points and review counts are always shown as
numbers, with unit and period.

Fallbacks:

- `deterministic`, but the skill's scripts emit no score (they are fact extractors): present
  that skill as `none` and say so in the Scoring line of the header.
- `rubric`, but the skill has no written rubric: present it as `none` and say so.

## 2. File, location and language

- Path: `growth-reports/<YYYY-MM-DD>-<skill>-<slug>.md` in the user's project root, plus a JSON
  sidecar with the same name and `.json`. `<slug>` is the subject in lowercase `a-z0-9` and
  hyphens, 60 characters at most; for a URL it is the host without `www.` plus the path (for
  example `https://www.acme.app/pricing` becomes `acme-app-pricing`).
- One report per skill, subject and day: a rerun on the same day replaces that day's report and
  sidecar (it is a correction, not a new data point). Never delete or overwrite a report from
  an earlier day: that history feeds "Change since last run".
- `growth-reports/.gitignore` contains `*`, so reports are never committed. Create it if it is
  missing. Reports about clients or competitors are confidential.
- Use the shared report helper (`report.py` in the growthkit library) when the skill's scripts
  provide it; it applies these rules. Otherwise follow them by hand.
- Save the report without asking. Never paste the full report into chat.
- Language: write the report in the user's language, which is the language of the user's
  request unless `report_language` in `growth-context.md` says otherwise. Translate headings
  (except `## Change since last run`, section 9) and prose. Keep as written: skill names,
  commands, file paths, URLs, code, JSON keys and metric acronyms (MRR, NRR, CAC, LTV, CTA,
  ASO, ICE). Quotes from a source stay in the source
  language, with a translation in brackets when the report language differs. The footer is
  always in English, exactly as in section 13.

## 3. Report structure

Sections in this order. Skill-specific detail goes in `## Details`, never before the bets.

1. Title: `# <Report type>: <subject>`
2. Header block:
   - `**Subject:**` the URL, app, brand, product or data file analyzed
   - `**Date:**` `YYYY-MM-DD`
   - `**Toolkit:**` `saas-growth-marketing-skills <version>, <skill>`
   - `**Sources:**` every source read, each with how and when: static fetch (HTTP status,
     date), rendered HTML (how), screenshots, files the user supplied, APIs, WebSearch
   - `**Context:**` `growth-context.md` (its `updated` date) or "none; see Assumptions"
   - `**Scoring:**` the mode in effect and, for `rubric`, the rubric file and version
   - `**Score:**` only in `deterministic` and `rubric` modes (section 4)
   - `**Coverage:**` Measured: ... | Inferred: ... | Not measured: ...
3. `## Diagnosis`: 3-5 numbered facts. Each is one sentence, evidence-backed, with evidence IDs
   (`[E1]`). Facts, not advice.
4. `## Biggest constraint`: the one thing that most limits the user's current goal
   (`current_goal` in `growth-context.md`), its evidence, and why it outranks the rest.
5. `## Scorecard` (`deterministic`, `rubric`) or `## Findings by area` (`none`), section 4.
6. `## Top 3 bets`, section 6.
7. `## Ready-to-ship assets`, section 7.
8. `## Details`: optional, skill-specific (dimension notes, full tables, other findings ranked
   by ICE, at most 10).
9. `## Not measured and how to get it`: table with columns What | Why not measured | How to get
   it (export, API key, question, browser) | What it would change.
10. `## Assumptions`: every value guessed in this run or marked assumed in `growth-context.md`,
    with what it was inferred from. Write "None" when there are none.
11. `## Change since last run`, section 9.
12. `## Evidence`, section 5.
13. Footer, section 13.

## 4. Scores in each mode

Name a score after what it measures. A score built from what a site exposes is "readiness",
not "visibility" or "performance", unless the outcome itself was measured (for example AI
answers actually sampled, or the user's conversion data).

### `deterministic`

- Header: `**Score:** 72/100 (computed by <script> <version>)`.
- Scorecard table: Dimension | Score | Max | Basis (the JSON field it came from) | Note.
- Copy the script's numbers exactly. Do not adjust them. When your reading of the evidence
  disagrees with a script score, keep the number and add an "Analyst note" with the evidence;
  lower the confidence you state for that dimension.
- Show no score for an input the script could not see (blocked, empty, JS shell), even if a
  buggy script printed one.

### `rubric`

1. Read the skill's rubric (`references/rubric.md` or the file its SKILL.md names).
2. Score every dimension on the rubric's scale, using its written anchors. For each dimension
   record: score, one-line justification, evidence IDs (a quote or a JSON fact path), and
   confidence (section 5). Mark a dimension `na` when it does not apply to this subject (for
   example urgency on a B2B enterprise page) and `not_measured` when it could not be observed.
3. Write the dimension scores to a JSON file and run the skill's scoring command. The script
   drops `na` and `not_measured` dimensions, renormalizes the weights and returns the
   composite and the measured weight. Never add up scores yourself. If the skill has no
   scoring command, show per-dimension scores and no composite.
4. Show a composite only when measured weight is at least 60% of the applicable weight;
   otherwise show per-dimension scores and say why there is no total.
5. Overall confidence: high when at least 80% of the measured weight has high confidence, low
   when more than half has low confidence, medium otherwise.
6. Header: `**Score:** 64/100 (rubric; confidence medium; 85% of weight measured)`, followed
   by: "Model-assigned scores can move a few points between runs; treat differences under 5
   points as noise."
7. Scorecard table: Dimension | Score | Max | Weight | Confidence | Evidence | Justification.

### `none`

- No numeric scores, no letter grades, no "X of N" counts, no Score line in the header.
- `## Findings by area` replaces the Scorecard: Area | Status | Evidence | What to do, where
  Status is one of Strong, Needs work, Critical, Not measured.
- Computed metrics still appear as numbers (section 1).

## 5. Evidence and confidence

- Every claim in Diagnosis, Biggest constraint, Scorecard or Findings, and Bets cites at least
  one evidence ID.
- `## Evidence` table: ID | Claim | Source | Observed | Confidence. Source is a URL, a file
  name, a JSON fact path, a CSS selector or "desktop screenshot, first viewport". Quote the
  page or data directly when the claim is about wording. Observed is the date the source was
  read.
- Confidence levels:
  - high: observed directly on the subject (fetched or rendered page, screenshot, the user's
    data file) or computed by a script from the user's data.
  - medium: observed but incomplete (static HTML only on a JS-rendered page, one page of a
    larger site, fewer than 30 items, numbers the user typed without a source file), or a
    sourced benchmark for a matching segment.
  - low: inferred (from assumptions, indirect signals, or a benchmark for a different
    segment).

## 6. Top 3 bets: ICE and traffic-aware test plans

Exactly three bets, ranked by ICE score. Each bet has:

- Title: the change, in one line.
- Evidence: IDs and one sentence on what they show.
- Hypothesis: "If we <change>, <primary metric> will improve because <reason from the
  evidence>."
- Primary metric, and a guardrail metric when the change could hurt another number.
- ICE: Impact, Confidence and Ease, each 1-10, and the ICE score as their average to one
  decimal.
  - Impact: expected effect on the primary metric given the evidence and the user's goal.
  - Confidence: 8-10 when the subject's own data or direct observation supports it, 4-7 when
    a sourced benchmark or an established pattern does, 1-3 when it is opinion.
  - Ease: 8-10 for a copy or config change done in a day, 4-7 for about a sprint, 1-3 for
    several sprints or a new system.
- Expected effect: a range only when a cited benchmark supports it (source and year in the
  evidence table); otherwise "unknown until measured".
- Test plan, decided by traffic:
  1. Inputs: the baseline rate of the primary metric, weekly traffic that reaches the page or
     step (`monthly_visitors` or `monthly_signups` from `growth-context.md`, divided by 4.33),
     and the minimum detectable effect the user cares about (default 20% relative, stated as an
     assumption).
  2. Run the shared stats helper (`stats.py` in the growthkit library) through the command
     the skill's SKILL.md gives (two proportions, alpha 0.05 two-sided, power 0.8, two
     variants) with a 4-week limit (`max_weeks=4`; the helper's own default is 6, which is
     too long for this contract). Never estimate sample sizes yourself.
  3. Required time 4 weeks or less: plan an A/B test with the sample per variant, the duration
     in whole weeks (`weeks_rounded`, but at least 2), and a fixed stopping point (no early
     stopping on a peek).
  4. More than 4 weeks: no A/B test. Plan "ship and measure": make the change, compare equal
     windows of at least 2 full weeks before and after, and name the confounders to watch
     (launches, campaigns, seasonality). For UX changes, add a qualitative check such as 5
     target-user sessions.
  5. Traffic unknown: say so and state the weekly traffic an A/B test would need.

## 7. Ready-to-ship assets

Things the user can paste or publish after review: rewritten headline, subheadline and CTA
copy, JSON-LD blocks, robots.txt diffs, llms.txt files, store metadata, email copy, reply
drafts, page drafts.

- Label each asset "Draft".
- Validate against hard limits with the skill's scripts when one exists (character limits,
  JSON-LD parses, robots.txt syntax).
- Missing proof gets a bracketed placeholder, never invented content: `[customer logo]`,
  `[testimonial: real quote, name, role, company]`, `[metric: real number and its source]`,
  `[case study link]`.
- Drafts for public posts (Reddit, Hacker News, review replies) open with a disclosure such as
  "I work on <product>." The skill never posts anything itself.
- Claims about a named company appear only with a source URL and date in the evidence table.

## 8. Bans

Never write:

- Unsourced effect sizes. Examples found in earlier versions: "SSO reduces signup friction by
  30-50%", "total activation lift 50-80%", "each additional form field reduces conversion by
  5-10%", an "expected lift" column with no source.
- Invented percentiles or rankings: "top 20% of SaaS companies", "better than most
  competitors", with no benchmark row behind them.
- Invented proof: testimonials, logos, customer counts, ratings, awards, case studies.
- A status or trend the data does not contain: "traffic is declining", "churn is improving",
  "competitor X is growing fast", unless the JSON or a cited source shows it.
- Revenue, ARR, valuation, user counts or other financials about a named company without a
  source URL and date.
- Benchmarks without source, year and segment. Benchmarks come from the shared benchmark file.
- Volatile facts (crawler tokens, store limits, API limits, platform features) older than 6
  months that were not re-checked; see `volatile-facts.md`.
- Advice that breaks platform rules or consumer law: review gating, fake urgency or scarcity,
  fake or incentivized reviews without disclosure, undisclosed promotion.
- A score for something that was not observed.

Always allowed: "unknown", "not measured", ranges from a cited benchmark with source and year,
and numbers computed by scripts from the user's data.

## 9. Change since last run

- Find the latest sidecar for the same skill and subject from an earlier day: the newest
  `growth-reports/<YYYY-MM-DD>-<skill>-<slug>.json` whose name matches exactly (so
  `acme-app` never matches `acme-app-pricing`) and whose `report.skill` and `report.slug`
  match. The report helper's `previous` command does this lookup.
- Write this section yourself, in its place in section 3. The report helper appends a plain
  value table at the end when it does not find the English heading `## Change since last run`,
  so keep that heading in English in every language and add the translation after it, for
  example `## Change since last run (Son çalıştırmadan bu yana değişim)`.
- None found: write "First run for this subject."
- Found: list findings resolved, still open and new, and metric changes as "old -> new
  (date -> date)". Compare scores only when the scoring mode and the rubric or script version
  match; otherwise write "Scores not comparable: <what changed>."
- Never state a trend from one data point or from data that is not in the sidecars.

## 10. JSON sidecar

Written next to the report with the same name and `.json`. It has three top-level keys:

- `report`: written by the report helper (skill, subject, slug, date, toolkit version, report
  file name, date of the previous run).
- `changes_since_last_run`: written by the report helper; changed scalar values compared with
  the previous run's `data`, by dotted path.
- `data`: written by the skill (it is what the skill passes to the helper's `save` command).
  It must contain at least the keys below; skills may add more.

When the helper is not available, write the same layout by hand.

```json
{
  "report": {"skill": "landing-page-cro", "subject": "https://acme.app/pricing",
             "slug": "acme-app-pricing", "date": "2026-10-24", "toolkit_version": "2.0.0",
             "markdown": "2026-10-24-landing-page-cro-acme-app-pricing.md",
             "previous_run": "2026-09-30"},
  "changes_since_last_run": [{"path": "scoring.value", "previous": 58, "current": 64,
                              "delta": 6}],
  "data": {
    "schema_version": 1,
    "language": "en",
    "scoring": {"mode": "rubric", "version": "rubric-v2", "value": 64, "max": 100,
                "confidence": "medium", "measured_weight": 0.85},
    "dimensions": [{"id": "value_prop", "score": 6, "max": 10, "weight": 20,
                    "status": "scored", "confidence": "high", "evidence": ["E1"]}],
    "findings": [{"id": "F1", "area": "CTA", "status": "needs_work", "summary": "...",
                  "evidence": ["E2"]}],
    "constraint": "...",
    "bets": [{"id": "B1", "title": "...", "primary_metric": "...",
              "ice": {"impact": 8, "confidence": 6, "ease": 7, "score": 7.0},
              "test_plan": "ab_test", "evidence": ["E1"]}],
    "coverage": {"measured": [], "inferred": [], "not_measured": []},
    "evidence": [{"id": "E1", "claim": "...", "source": "https://...",
                  "observed": "2026-10-24", "confidence": "high"}],
    "assumptions": [],
    "metrics": {}
  }
}
```

The keys below are inside `data`.

- The helper compares scalar values only (lists are skipped), so anything a later run should
  compare goes in `scoring` or `metrics`, not only in a list.
- `scoring.value`, `scoring.max`, `scoring.confidence` and `scoring.measured_weight` are
  `null` in `none` mode and when no composite is shown. `dimensions` is empty in `none` mode.
- `status` in `dimensions` is `scored`, `na` or `not_measured`. `status` in `findings` is
  `strong`, `needs_work`, `critical` or `not_measured`.
- `test_plan` is `ab_test`, `ship_and_measure` or `qualitative`.
- `metrics` holds computed metrics as `{"name": {"value": 0.042, "unit": "ratio",
  "period": "month"}}` so later runs can compare them.

## 11. Chat summary

After saving, write at most 5 lines in the user's language, with no emojis:

```
Report: growth-reports/2026-10-24-landing-page-cro-acme-app-pricing.md
Biggest constraint: <one sentence>
Top bets: 1) <...> 2) <...> 3) <...>
Score: 64/100 (rubric, medium confidence) | Not measured: <main gaps>
Next: <one next step or the next skill to run>
```

In `none` mode, line 4 is only "Not measured: <main gaps>". When `growth-context.md` was
created or updated in this run, mention it on the Next line.

## 12. Runs inside a subagent or orchestrator

- Write the report and sidecar as usual.
- Return to the parent only: the report path, the sidecar path, the constraint, the three bet
  titles, and any `MISSING_INPUTS: <field>, <field>` line. Do not return the full report.
- Do not ask the user anything; subagents cannot. Missing required inputs go in the
  `MISSING_INPUTS` line.
- An orchestrator merges sidecars, de-duplicates bets across skills, re-ranks them by ICE and
  writes its own report under this same contract.

## 13. Skeleton

```markdown
# <Report type>: <subject>

**Subject:** <url / app / brand / file>
**Date:** YYYY-MM-DD
**Toolkit:** saas-growth-marketing-skills <version>, <skill>
**Sources:** <source, how, date>; <source, how, date>
**Context:** growth-context.md (updated YYYY-MM-DD)
**Scoring:** <deterministic | rubric (references/rubric.md, vN) | none>
**Score:** <only in deterministic and rubric modes>
**Coverage:** Measured: <...> | Inferred: <...> | Not measured: <...>

## Diagnosis
1. <fact> [E1]

## Biggest constraint
<one paragraph> [E2]

## Scorecard
<table; or "## Findings by area" in none mode>

## Top 3 bets
### 1. <change>
- Evidence: [E1] <...>
- Hypothesis: If we <...>, <metric> will improve because <...>.
- Primary metric: <...> (guardrail: <...>)
- ICE: Impact 8, Confidence 6, Ease 7 = 7.0
- Expected effect: unknown until measured
- Test plan: <ab_test with sample and weeks | ship_and_measure with windows | qualitative>

## Ready-to-ship assets
<Draft blocks>

## Details

## Not measured and how to get it
| What | Why not measured | How to get it | What it would change |

## Assumptions

## Change since last run

## Evidence
| ID | Claim | Source | Observed | Confidence |

---
*Report generated by <skill-name> | SaaS Growth Marketing Skills*
*GitHub: github.com/ekinciio/saas-growth-marketing-skills*
```
