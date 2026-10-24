---
name: onboarding-optimizer
description: >
  Audits and redesigns a SaaS product's first-run experience after account
  creation: path to first value, setup steps, empty states, checklists, tours,
  welcome surveys and stalled-user nudges, scored against a written rubric
  with evidence. Works from screenshots, a browser walk, an analytics export
  or a short interview. Not for the signup page (web-app-growth-engine) or
  activation-rate numbers (plg-funnel-analyzer).
when_to_use: >
  "users sign up but never finish setup", "review our onboarding flow",
  "shorten time-to-value in the first session", "design a setup wizard or
  getting-started checklist", "our product tour completion is low", "what
  should our empty states say", "here are screenshots of our first-run
  experience", "where do new users drop off before activation (here is our
  PostHog export)".
argument-hint: "[audit|design] <screenshots, app URL, export file or product description>"
allowed-tools:
  - Bash(python3 "${CLAUDE_SKILL_DIR}/scripts/onboarding_scorer.py" *)
  - Bash(python3 "${CLAUDE_SKILL_DIR}/scripts/onboarding_funnel.py" *)
  - Bash(python3 "${CLAUDE_SKILL_DIR}/scripts/screen_facts.py" *)
  - Bash(python3 "${CLAUDE_SKILL_DIR}/scripts/_growthkit/report.py" *)
metadata:
  version: "2.0.0"
  last_verified: "2026-10"
---

# Onboarding Optimizer

Finds where new users stall between account creation and first value, scores the first-run
design against a written rubric with quoted evidence, and ships the fixes as test-sized bets and
ready-to-paste copy.

## When to use

- New users create an account but do not reach the first value moment or the activation event.
- The team wants a review of its first-run screens, setup wizard, checklist, tour, empty states
  or welcome survey (from screenshots, a recording, a browser walk or a description).
- The user has an analytics export and wants the onboarding funnel: step drop-off, time to
  activation, activation by signup cohort.
- A new product needs a first-run design (`design`: pattern fit and drafts, no score).

Not for:

- Signup page friction and the steps up to account creation -> web-app-growth-engine
- Activation-rate numbers and funnel benchmarks across the whole funnel -> plg-funnel-analyzer
- Win-back and cancellation flows -> retention-playbook
- Employee onboarding, developer docs or READMEs -> not this toolkit

## Output contract

- Report: `growth-reports/<YYYY-MM-DD>-onboarding-optimizer-<slug>.md` in the user's project,
  plus the JSON sidecar, saved with the report helper (step 10). Never paste the report in chat.
- Read `${CLAUDE_SKILL_DIR}/references/_shared/report-contract.md` before writing. Scores follow
  its `rubric` mode: the model scores each dimension with `references/rubric.md`, the `score`
  command computes the composite. The score is the "first-run design score", never an
  activation rate.
- `design` mode and runs where no screen was seen use `none` mode (findings, no score).
- Language: the user's language (or `report_language`); footer in English, as in the contract.
- Chat: the 5-line summary from the contract, nothing more.

## Inputs

Read `${CLAUDE_PROJECT_DIR}/growth-context.md` first (format:
`${CLAUDE_SKILL_DIR}/references/_shared/growth-context.md`). Fields that matter most here:
`activation_event`, `icp`, `gtm_motion`, `platforms`, then `free_offer`, `card_required`,
`monthly_signups` (test sizing) and `current_goal` (ranking).

Evidence, best first (use every one available):

1. Analytics export: raw event log or funnel export (PostHog, Mixpanel, Amplitude, GA4, any CSV
   with user id, event, timestamp).
2. Screenshots or a recording of every screen from account creation to first value, plus the
   welcome and follow-up emails.
3. Browser walk: a public first run (app usable without an account) or rendered HTML the user
   saves from their own product. Never create accounts or log in.
4. Interview: the user's description, when nothing else exists.

Ask at most 3 questions, in one batch (AskUserQuestion when available, with a "Not sure"
option): typically the evidence request, the activation event, and monthly signups. Never infer
numbers. Inside a subagent ask nothing; return `MISSING_INPUTS: <field>, <field>`.

## Workflow

If `${CLAUDE_SKILL_DIR}` appears literally in the commands below, replace it with the directory
that contains this SKILL.md.

Run every command as its own Bash call from the user's project folder: no `cd`, pipes or `>`.
Write JSON inputs with the Write tool under `growth-reports/.cache/` (create
`growth-reports/.gitignore` containing `*` first if it is missing).

1. **Context and scope.** Read `growth-context.md`. Confirm the request is about the first run
   after account creation; route signup-page or funnel-benchmark questions per "Not for".
   Read `references/flow-capture.md` before collecting evidence.

2. **Data (when an export exists).** Read `references/instrumentation.md`. Run once without
   steps if you do not know the event names, then with the onboarding steps in order (first:
   account created, last: the activation event; window from the activation definition):

   ```bash
   python3 "${CLAUDE_SKILL_DIR}/scripts/onboarding_funnel.py" "<export.csv>" --json
   python3 "${CLAUDE_SKILL_DIR}/scripts/onboarding_funnel.py" "<export.csv>" --step "<signup event>" --step "<step event>" --step "<activation event>" --window-days 14 --json
   ```

   For numbers the user typed, write `{"steps": [{"name": ..., "count": ...}]}` to
   `growth-reports/.cache/<date>-onboarding-steps-<slug>.json` and pass that file instead.

3. **Screens.** Read every screenshot the user shares. For saved or rendered HTML, and for
   public first-run URLs, run (screens in flow order):

   ```bash
   python3 "${CLAUDE_SKILL_DIR}/scripts/screen_facts.py" "<url-or-saved.html>" "<next screen>" --json
   ```

   For a browser walk, or when a fetch is blocked or a JavaScript shell, follow
   `${CLAUDE_SKILL_DIR}/references/_shared/browser-fallback.md` (sections 5 and 6) and re-run
   `screen_facts.py` on the rendered file. Take the desktop and 390 px screenshots of the first
   screen.

4. **Flow ledger.** Write the ledger (format in `references/flow-capture.md`) to
   `growth-reports/.cache/<date>-onboarding-flow-<slug>.json`, one step per screen with its
   evidence ID, unknowns as `null`. Then:

   ```bash
   python3 "${CLAUDE_SKILL_DIR}/scripts/onboarding_scorer.py" flow "growth-reports/.cache/<date>-onboarding-flow-<slug>.json" --json
   ```

   Use `derived` (steps, inputs, chores and time before value), `applicability` (which
   dimensions apply, progress and skip only at 3+ steps) and `benchmarks` (context rows).

5. **Score.** Read `references/rubric.md`. Score every dimension with evidence IDs and a
   confidence, or mark it `na` / `not_measured` per the rubric. Write the scores file and run:

   ```bash
   python3 "${CLAUDE_SKILL_DIR}/scripts/onboarding_scorer.py" score "growth-reports/.cache/<date>-onboarding-scores-<slug>.json" --json
   ```

   Copy `scoring.value`, `grade`, `confidence` and `measured_weight` exactly. If
   `composite_shown` is false, show dimension scores only, with `reason_no_composite`.

6. **Biggest constraint.** With data: the step with the largest drop on the path to value
   (`funnel.biggest_drop`), explained by what the screens show at that step. Without data: the
   lowest-scoring dimension weighted by its effect on `current_goal`, with its evidence.

7. **Pattern fit.** Read `references/onboarding-patterns.md`. Name the current primary pattern,
   the recommended primary and supporting patterns for the product type, and what changes.

8. **Top 3 bets, sized.** For each bet, run the plan with the baseline of its primary metric
   (the measured rate, or a benchmark row marked as an assumption) and the traffic reaching that
   step (`--weekly`, or `--monthly` from `monthly_signups`; omit when unknown):

   ```bash
   python3 "${CLAUDE_SKILL_DIR}/scripts/onboarding_scorer.py" plan --baseline 0.31 --monthly 420 --mde 0.2 --label "<bet>" --json
   ```

   Use its `test_plan` (`ab_test` with `n_per_arm` and `weeks`, `ship_and_measure`, or
   `traffic_unknown` with `weekly_needed_for_max_weeks`). When a bet touches the card or trial
   model and the four rates are known, also run:

   ```bash
   python3 "${CLAUDE_SKILL_DIR}/scripts/onboarding_scorer.py" trial --no-card-v2t 8% --no-card-t2p 15% --card-v2t 3% --card-t2p 45% --json
   ```

   Benchmark context (metrics: activation_rate, time_to_value, tour_completion,
   checklist_completion, month_1_retention, trial_to_paid, free_to_paid, visitor_to_signup);
   cite each row's id, source, year and segment:

   ```bash
   python3 "${CLAUDE_SKILL_DIR}/scripts/onboarding_scorer.py" benchmarks --metric activation_rate --json
   ```

9. **Assets (Draft).** Write the ones the bets need, with bracketed placeholders for anything
   unknown: first-screen empty-state copy (headline, one sentence, one CTA); an activation
   checklist (3-5 items ending at the activation event); a welcome survey (at most 3 questions,
   each with its routing rule); a stalled-user nudge (trigger event and delay, subject, body,
   deep link); the instrumentation plan when steps are not tracked
   (`references/instrumentation.md` section 5).

10. **Save.** Look up the previous run for "Change since last run":

    ```bash
    python3 "${CLAUDE_SKILL_DIR}/scripts/_growthkit/report.py" previous --skill onboarding-optimizer --subject "<product name or app URL>"
    ```

    Write the report (structure below) to
    `growth-reports/.cache/<date>-onboarding-report-<slug>.md` and the sidecar data
    (`report-contract.md` section 10, with `scoring` from step 5 and `metrics` such as
    `activation_rate`, `time_to_activation_p75_hours`, `steps_before_value`) to
    `growth-reports/.cache/<date>-onboarding-data-<slug>.json`, then:

    ```bash
    python3 "${CLAUDE_SKILL_DIR}/scripts/_growthkit/report.py" save --skill onboarding-optimizer --subject "<product name or app URL>" --markdown "growth-reports/.cache/<date>-onboarding-report-<slug>.md" --data "growth-reports/.cache/<date>-onboarding-data-<slug>.json"
    ```

    Then update `growth-context.md` (growth-context standard section 7) and post the 5-line
    chat summary.

Report title: `# Onboarding audit: <product>`. Follow the contract's section order. In
`## Details`, in this order: flow map (table: step, kind, asks, offers, seconds, evidence),
activation definition and the setup, first-value and habit moments, the leak (data), pattern
fit, more bets ranked by ICE (at most 10), instrumentation plan. Coverage names every mode used
and every mode missing.

`design` (new product, no flow yet): steps 1, 7, 8 and 9 only. Design the first run from the
product type's value horizon and patterns, size the first test, write the drafts; scoring mode
`none`.

## Failure handling

| Exit | Meaning | What to do |
|---|---|---|
| 0 | ok | Use the result; read `notes` (small cohorts, incomplete windows, sparse screens). |
| 2 | usage or input error | Read `errors` (it names the field, the bad value, or the valid event names and keys), fix the file or arguments, retry once. Unknown product type: use a listed key. |
| 3 | `screen_facts.py`: blocked or unreachable | Blocked: follow `browser-fallback.md`. 404, DNS or TLS: check the URL with the user. Never score an unseen screen. |
| 4 | partial | Use what succeeded; list failed screens or unreadable rows under "Not measured". |
| 5 | nothing to analyze | Empty ledger, JavaScript shell, or no usable rows: render the screen or ask for screenshots or the export. No score. A shell still returns detected tools. |
| 1 or traceback | script bug | Retry once; then continue with other evidence, mark the section "Not measured (tool error)" and quote the last error line. |

Skill-specific cases:

- The walk stopped at the signup form: the first run was not seen. Ask for screenshots; until
  then the design dimensions are `not_measured` and the report runs in `none` mode.
- `activation.rate_complete_cohorts` is null: no cohort finished its window; say so and do not
  report `rate_so_far` as the activation rate.
- The export is billing or retention data: the script says which skill reads it; offer that.

## Judgment

- Score only with `references/rubric.md`; every score cites evidence IDs and a confidence.
  Unknown is `not_measured`, never 0. Never reward added steps; never penalize a card at signup
  by itself; never score a screen nobody saw.
- No invented numbers: no lift estimates, percentiles or "top X%". Effects are "unknown until
  measured" unless a cited benchmark supports a range. Benchmarks are context, not grades, and
  only when the user's activation definition matches the row's.
- Company examples carry a source URL and date. No invented testimonials, logos, metrics or
  urgency in drafts.

## References

- Read `references/flow-capture.md` before collecting evidence and writing the flow ledger.
- Read `references/rubric.md` before scoring.
- Read `references/onboarding-patterns.md` for pattern fit, bets and `design` mode.
- Read `references/instrumentation.md` when an export exists or the steps are not tracked.
- Read `references/_shared/report-contract.md` before writing the report.
- Read `references/_shared/browser-fallback.md` for a browser walk, a blocked page or screenshots.
- Read `references/_shared/growth-context.md` when creating or updating `growth-context.md`.

## Notes

- Exports stay local; the funnel script hashes user ids and reports aggregates only. Never paste
  rows, ids or emails into the report.
- Never log in, create an account, type into fields or submit forms during a walk; ask the user
  to do those steps and share screenshots.
- Client and competitor reports are confidential; `growth-reports/` is git-ignored.
