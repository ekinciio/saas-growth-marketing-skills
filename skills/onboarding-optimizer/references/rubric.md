# Onboarding Rubric

Rubric version: `onboarding-rubric-v2` (the `score` command refuses any other version).
Last verified: 2026-10

The model scores the first-run experience with this file. The scripts only count facts and do
the arithmetic. The score measures the design of the first run as observed, so call it the
"first-run design score". It is not an activation rate; when the user's data is available, the
measured activation rate is reported next to it as a metric.

## Contents

1. Scale, statuses and evidence
2. Product types and value horizon
3. Dimensions and weights
4. Anchors per dimension
5. Applicability rules
6. Scoring mistakes to avoid
7. Using the user's data
8. Composite, grade and confidence
9. Scores file format

---

## 1. Scale, statuses and evidence

- Score each dimension from 0 to 10 using the anchors in section 4. Pick the anchor band whose
  description fits best, then the number inside the band.
- Every scored dimension cites at least one evidence ID from the report's Evidence table: a
  screenshot ("desktop screenshot, screen 3"), a quote from a screen, a `screen_facts.py` or
  `onboarding_scorer.py flow` fact path (`derived.chores_before_value`), or a number from
  `onboarding_funnel.py`. No evidence, no score.
- Give each score a confidence:
  - high: seen on screenshots or rendered screens of this flow, or computed from the user's export
  - medium: described by the user without screens, static HTML only, one screen of several
  - low: inferred from indirect signals
- Status `na`: the dimension does not apply to this product (rules in section 5). Write why.
- Status `not_measured`: the dimension applies but nothing about it was observed (for example
  follow-up emails when only the first session was captured). Never score it 0.

## 2. Product types and value horizon

One enum, shared with `scripts/onboarding_scorer.py` and `references/onboarding-patterns.md`.
The value horizon is a property of the product (what must exist before value can appear), not a
benchmark.

| Key | Product type | Value horizon |
|---|---|---|
| `visual` | Visual and design tools (design, whiteboards, video, diagrams) | first_session |
| `content` | Content and creation tools (docs, writing, forms, site builders) | first_session |
| `data` | Data and analytics (BI, product analytics, monitoring) | after_connection |
| `developer` | Developer tools and APIs (SDKs, infrastructure, CI) | after_connection |
| `collaboration` | Collaboration and project management (team workspaces, tasks) | after_team |
| `communication` | Communication (chat, meetings, shared inbox, support desk) | after_team |
| `business_ops` | Business operations (CRM, HR, finance, scheduling, ERP) | after_connection |
| `ecommerce` | E-commerce and store builders | after_connection |
| `other` | None of the above; judge from the product description | none |

- first_session: value can appear in the first session with no outside data. Hold the flow to
  "the user's own first result in session one".
- after_connection: real value needs the user's data, code, store or an integration. Hold the
  flow to "a first value proxy in session one (sample data, a test event, a preview built from
  public data) and real value as soon as the connection lands".
- after_team: full value needs other people. Hold the flow to "solo value in session one, team
  value after the first accepted invite".

## 3. Dimensions and weights

| Id | Weight | What it measures |
|---|---|---|
| `value_path` | 25 | How directly a new user reaches the first value moment that matches the activation event |
| `setup_friction` | 15 | Work asked before value: required inputs, chores, decisions, and help with them |
| `first_screen` | 15 | What the product shows when it first opens: blank, empty state, templates, sample data, AI draft |
| `guidance` | 15 | In-product help that moves the user to activation: checklist, tour, tooltips |
| `personalization` | 10 | Whether onboarding questions change what the user sees next |
| `reengagement` | 10 | What brings back users who stall before activation |
| `team_activation` | 5 | For multi-player products: bringing in the people needed for value |
| `trial_fit` | 5 | Whether the trial or free plan lets the user reach value before a paywall |

Weights sum to 100. The composite renormalizes over the dimensions that were scored.

## 4. Anchors per dimension

### value_path (25)

| Band | Anchor |
|---|---|
| 0-2 | No value moment is reachable in the captured flow for a first_session product, or the flow ends in setup; the activation event is undefined and no screen points to one outcome. |
| 3-4 | Value is reachable but behind several chores that could wait (verification, profile, invites, integrations), or the first screen offers many equal options and no single next action. |
| 5-6 | One clear path to value, but one or two avoidable steps come first, or the value moment is generic (an empty dashboard) rather than the user's own result. |
| 7-8 | The first screen leads to the user's own first result with at most one non-essential step before it; after_connection products give a value proxy while the connection is pending. |
| 9-10 | The user produces their own meaningful result in session one (or a convincing proxy for after_connection products); every step before it is essential or personalizes the path; the activation event is visibly the goal of the first session. |

Facts to use: `derived.steps_before_value`, `derived.time_to_value_minutes`,
`derived.chores_before_value`, `value_moment`, `activation_event`, the product type's value
horizon, and from data `funnel.biggest_drop` and `time_to_activation`.

### setup_friction (15)

| Band | Anchor |
|---|---|
| 0-2 | Several required inputs or chores before value that the product could infer, default or defer (phone number, company size, payment details for a free plan, a mandatory integration before any preview), with no way to defer them. |
| 3-4 | Many required inputs or two or more chores before value; with 3 or more steps, no progress indicator and no way to defer optional steps. |
| 5-6 | Inputs are mostly needed, but at least one chore could move after value; defaults or prefill are partial. |
| 7-8 | Only inputs that change the next screen are required; defaults and prefill from signup or SSO; with 3 or more steps, progress is shown and optional steps can be deferred. |
| 9-10 | Close to zero required input before value; everything else is asked at the moment it is needed (just-in-time setup). |

Progress and skip criteria apply only when `applicability.progress_and_skip` is true (3 or more
steps before value). A one- or two-step flow loses nothing for lacking them.

### first_screen (15)

| Band | Anchor |
|---|---|
| 0-2 | A blank or broken first screen with no hint of what to do, or a wall of equal options. |
| 3-4 | An empty state with generic copy ("No projects yet") and a CTA that does not lead toward value, or a first message about something other than value (warnings, legal, upsell). |
| 5-6 | An educational empty state with one primary CTA, or a template gallery that is generic and not matched to the user's job. |
| 7-8 | Starter content matched to the user's job (templates by use case, sample data that resembles theirs, an AI draft from a prompt) with an obvious way to start blank. |
| 9-10 | The first screen already shows the user's own value or a personalized starter they can edit at once; empty states elsewhere teach the next step with one CTA. |

### guidance (15)

| Band | Anchor |
|---|---|
| 0-2 | No guidance in a product that needs it, or guidance that blocks the interface (a forced tour) before value. |
| 3-4 | A long auto-launched tour (five or more steps), or a checklist of chores unrelated to the activation event. |
| 5-6 | Some guidance tied to core actions, but generic or badly timed. |
| 7-8 | Short guidance triggered by what the user does; a checklist of about 3-5 items that ends at the activation event; tours the user chooses to launch. |
| 9-10 | Contextual, short and user-controlled guidance where each item is a step on the activation path, and progress persists across sessions. |

Context rows (cite with `onboarding_scorer.py benchmarks --metric tour_completion` or
`--metric checklist_completion`): `tour_completion.chameleon2024.all`,
`tour_completion.chameleon2024.self_launched`, `tour_completion.chameleon2024.five_step`,
`checklist_completion.userpilot2025.b2b`. They describe other companies' tours and checklists;
use them as context for the user's own completion data, never as the score.

### personalization (10)

| Band | Anchor |
|---|---|
| 0-2 | Required survey questions whose answers change nothing the user sees (data collection before value). |
| 3-4 | Questions that change only cosmetics, or more than three questions before value. |
| 5-6 | No survey and one path fits most users, or a survey that routes to a relevant template or checklist but also asks questions that do not route. |
| 7-8 | One to three skippable questions, each changing the template, checklist or default view. |
| 9-10 | The path adapts to role and job with few or no questions (inferred from signup data, the invite context or the first prompt), and the user can change it later. |

Facts: `derived.questions_that_do_not_personalize`, `derived.questions_personalization_unknown`.

### reengagement (10)

| Band | Anchor |
|---|---|
| 0-2 | Nothing, or only newsletters and time-based blasts unrelated to the user's progress. |
| 3-4 | A generic time-based welcome sequence. |
| 5-6 | Welcome messages point to the activation action but ignore what the user already did. |
| 7-8 | Messages triggered by what the user did or did not do, with a deep link back to the exact step; setup progress is saved. |
| 9-10 | As 7-8, across in-app and email, stopped once the user activates, and measured against activation. |

Usually `not_measured` when only the first session was captured and the user did not describe
the messages.

### team_activation (5)

| Band | Anchor |
|---|---|
| 0-2 | An invite is required before any solo value, or there is no way to invite. |
| 3-4 | The invite is buried, or demanded before the user has anything worth sharing. |
| 5-6 | An invite prompt appears at a generic moment. |
| 7-8 | The invite is offered when the work benefits from another person (sharing a result), with a preview of what the invitee will see. |
| 9-10 | Invitees land on the shared item, which already has value, with their own short onboarding. |

### trial_fit (5)

| Band | Anchor |
|---|---|
| 0-2 | A paywall before any value in a self-serve product, or a trial shorter than the product's time to value. |
| 3-4 | The trial clock runs while setup is still impossible (waiting on an integration or approval), or upgrade prompts interrupt the path to value. |
| 5-6 | The trial length covers the time to value; upgrade prompts are neutral. |
| 7-8 | Paid features are experienced during the trial (or a reverse trial), limits and the clock are visible, and the end of the trial keeps the user's work (downgrade, not lock-out). |
| 9-10 | As 7-8, and the trial model was chosen with the user's own conversion numbers; the upgrade ask comes right after value. |

A card at signup is a trade-off, not a defect: it usually lowers trial starts and raises
trial-to-paid. Never lower this score for the card alone. When visitor-to-trial and
trial-to-paid rates are known, run the `trial` command and judge with its result; otherwise note
the trade-off and the rates needed.

## 5. Applicability rules

The `flow` command returns `applicability.dimensions.<id>.suggested_status`. Follow it unless
you have evidence the facts missed, and say so in the justification.

| Dimension | `na` when | `not_measured` when |
|---|---|---|
| `team_activation` | `multiplayer` is false (single-player product) | multiplayer is unknown and no invite step was seen |
| `trial_fit` | `trial.model` is `demo_only`, `paid_only` or `none` | the trial model is unknown |
| `personalization` | one persona and one job, with a stated reason | never: no survey is itself a fact to judge |
| `guidance` | almost never; only when value needs no explanation at all | no in-app screen was seen |
| `reengagement` | never | no message and no return visit was observed or described |
| the rest | never | no screen and no description of that part was captured |

## 6. Scoring mistakes to avoid

- Never reward adding steps. A one-step flow with no progress bar beats a four-step flow with
  one. Progress and skip only matter at 3 or more steps.
- Never turn "unknown" into a low score. Unknown is `not_measured`.
- Never penalize a card at signup on its own (section 4, trial_fit).
- Never score a step you did not see. A browser walk that stopped at the signup form has not
  seen the first run; the first-run dimensions are `not_measured` until the user shares screens.
- Never use another company's completion rate as the user's score. Benchmarks are context.
- Do not reward tooling. A detected tour tool (Appcues, Pendo, Userpilot, ...) is a fact about
  the stack, not evidence of good guidance.
- Do not mark a high score on a dimension the biggest data drop points to. If the export shows
  most users stop at a step, the dimension that covers that step cannot be 9-10.

## 7. Using the user's data

- `onboarding_funnel.py` results are evidence with high confidence: cite step conversion, the
  biggest drop, time to activation (median and p75) and cohort activation with its interval.
- Data does not replace the design score. It sets the biggest constraint (the step with the
  largest drop on the activation path), raises the confidence of the dimension that covers that
  step, and gives the baseline and weekly traffic for test plans.
- Compare activation with benchmarks only when the user's definition matches the row's
  definition (`onboarding_scorer.py benchmarks --metric activation_rate`); otherwise say the
  definitions differ and mark the comparison low confidence.

## 8. Composite, grade and confidence

The `score` command computes, never the model:

- composite = sum(score / 10 x weight) over scored dimensions / scored weight x 100
- shown only when scored weight is at least 60% of the applicable (non-`na`) weight
- grade: A 90-100, B 80-89, C 70-79, D 60-69, F below 60
- overall confidence: high when at least 80% of scored weight is high confidence, low when more
  than half is low, medium otherwise

Model-assigned scores move a few points between runs; treat differences under 5 points as noise.

## 9. Scores file format

```json
{
  "rubric_version": "onboarding-rubric-v2",
  "dimensions": [
    {"id": "value_path", "score": 6, "confidence": "high", "evidence": ["E2", "E5"],
     "justification": "Own first board after 5 steps; 2 of them could wait"},
    {"id": "reengagement", "status": "not_measured", "justification": "No emails captured"},
    {"id": "team_activation", "status": "na", "justification": "Single-player product"}
  ]
}
```

Every id from section 3 appears once. A missing id is counted as `not_measured` with a note.
