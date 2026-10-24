# Capturing the First-Run Flow

How to see the user's onboarding and turn it into the flow ledger that
`onboarding_scorer.py flow` validates. Use every mode that is available; better evidence beats
more questions.

Last verified: 2026-10

## Contents

1. Input modes, best first
2. Screenshots and recordings
3. Browser walk
4. Interview fallback (at most 3 questions)
5. Flow ledger format
6. Step kinds
7. Worked example

---

## 1. Input modes, best first

| Mode | What it gives | Confidence |
|---|---|---|
| Analytics export (event log or funnel) | Where users really stop and how long activation takes | high |
| Screenshots or a screen recording of every screen from account creation to first value | What users really see | high |
| Browser walk of the public part (try-without-signup app, first signup step) and rendered HTML the user saves | Screens up to the first data entry; tools loaded | high for what was seen |
| The user's own description (interview) | The flow as the team believes it is | medium |

Data and screens answer different questions: the export says where people stop, the screens
say why. Ask for both when the user can provide them.

## 2. Screenshots and recordings

Ask once, in one message:

- One screenshot per screen from the moment the account exists to the first value moment, in
  order, at desktop width. Include every modal, the first empty screen, the first checklist or
  tour step, and any upgrade prompt.
- The welcome email and any follow-up email the first days bring (screenshots or pasted text).
- Optional: the same first screen at phone width (390 px) if the product is used on mobile.
- A recording (Loom or similar) works too: ask for frames of each screen or the transcript with
  timestamps; the timestamps give seconds per step.

Read each image. Give each screen an evidence ID (E1, E2, ...) in the order seen and record what
it asks (inputs, required marks, choices), offers (templates, sample data, AI prompt, skip,
progress) and shows (empty, value). Quote on-screen text exactly for copy findings.

## 3. Browser walk

The browser fallback's hard limits apply (SKILL.md links that file): no login, no account
creation, no typing personal data, no submitting forms, no CAPTCHAs, reject non-essential
cookies, at most 5 rendered pages per run.

- Public first runs (apps usable without an account, interactive demos): open the app, take the
  desktop and phone screenshots, use controls that only reveal or navigate (open a template
  picker, close a hint, pick a drawing tool), and record each screen. Interacting with a local
  canvas or editor is fine; anything that sends data (start a shared session, upload, submit)
  is not.
- Products behind signup: render the signup page, record the first step's fields and options,
  stop at the first field, and ask the user to complete signup themselves and share
  screenshots or saved HTML of the screens after it. A walk that stopped at signup has not seen
  the first run.
- The user's own logged-in product: when the browser tool uses the user's own profile, the user
  may already be logged in; record only what the screens show and never copy account data into
  the report.
- Run `screen_facts.py` on every saved or rendered HTML file to get controls, progress markers,
  skip controls, starter-content controls and the onboarding and analytics tools the page
  loads. A static fetch of `app.<domain>` often returns a JavaScript shell (exit 5), but it still
  lists the analytics tools, which tells you which export to ask for.

## 4. Interview fallback (at most 3 questions)

Use only when no screens or data are available. Ask in one batch, with "Not sure" allowed:

1. "Walk me through what a new user sees from the moment their account exists until they first
   get value, screen by screen. What does each screen ask for?"
2. "What action tells you a new user is activated, and within how many days?" (skip if
   `activation_event` is in `growth-context.md`)
3. "Roughly how many new accounts do you get per month?" (skip if `monthly_signups` is known)

Fill the ledger from the answers. Everything not said is unknown (`null`), never a default.
Set `source` to `interview`; every dimension scored from it has medium confidence at most.

## 5. Flow ledger format

Write it with the Write tool to `growth-reports/.cache/<date>-onboarding-flow-<slug>.json`.
Every field is optional; `null`, "not sure" and "skip" mean unknown. Unknown keys and negative
numbers are input errors (exit 2) that name the field.

```json
{
  "product": "Acme",
  "product_type": "collaboration",
  "source": "screenshots",
  "captured_on": "2026-10-24",
  "activation_event": "Created a board with 3+ cards and invited 1 teammate within 7 days",
  "value_moment": "Sees their own first board with real tasks",
  "multiplayer": true,
  "first_screen": "blank",
  "time_to_value_minutes": null,
  "trial": {"model": "free_trial", "length_days": 14, "card_required": false},
  "starter_content": {"templates": false, "sample_data": false, "ai_generated": false,
                      "educational_empty_states": true},
  "guidance": {"in_app_guidance": true, "checklist_items": 5, "tour_steps": null,
               "tour_user_launched": null, "contextual_tooltips": false},
  "messages": {"welcome_email": true, "behavior_triggered": null, "in_app_nudges": null},
  "steps": [
    {"name": "Role survey", "kind": "survey", "required_inputs": 2, "optional_inputs": 0,
     "choices": 2, "can_skip": false, "shows_progress": true, "delivers_value": false,
     "personalizes_next": false, "seconds": 40, "evidence": ["E2"]}
  ]
}
```

Enums:

- `product_type`: visual, content, data, developer, collaboration, communication, business_ops,
  ecommerce, other (human labels such as "Developer tool/API" are accepted)
- `source`: screenshots, recording, browser_walk, interview, quiz, data_export, mixed
- `first_screen`: blank, empty_state_cta, template_gallery, sample_data, ai_generated, value_shown
- `trial.model`: free_trial, freemium, reverse_trial, demo_only, paid_only, none

Rules:

- Steps start after account creation (the signup form itself belongs to web-app-growth-engine).
  Email verification, if it blocks the product, is the first step.
- Mark the step where the user first gets value with `"delivers_value": true` or kind `value`.
  If the capture never reached value, say so; the counts before value are then lower bounds.
- `seconds` comes from a recording or a timed walk; leave it null rather than guess.
- `personalizes_next` is true only when you saw the answer change a later screen (or the user
  said so); otherwise null.
- The 1.x quiz keys (`total_steps`, `required_fields`, `has_progress_indicator`,
  `has_skip_option`, `has_template_gallery`, `has_empty_state_education`,
  `time_to_first_value_minutes`, `requires_credit_card_upfront`, `has_welcome_email_sequence`,
  `has_in_app_guidance`) are still read and mapped to the fields above.

## 6. Step kinds

| Kind | Meaning |
|---|---|
| `welcome` | A greeting or intro screen with no input |
| `survey` | Questions about role, team, goal |
| `profile` | Personal or company details |
| `setup` | Naming a workspace, choosing settings |
| `import` | Bringing in existing data |
| `integration` | Connecting another tool or account |
| `install` | Installing an SDK, snippet, extension or app |
| `verification` | Email, phone or identity check that blocks progress |
| `invite` | Inviting teammates |
| `template_picker` | Choosing a template or starting point |
| `tour` | A product tour or walkthrough |
| `checklist` | A getting-started checklist |
| `empty_state` | An empty screen with guidance |
| `content` | A video, article or explanation |
| `paywall` | A plan choice or payment step |
| `upgrade_prompt` | An upsell inside the flow |
| `value` | The user's first value moment |
| `other` | Anything else (describe it in `notes`) |

Kinds `profile`, `import`, `integration`, `install`, `verification`, `invite`, `paywall` and
`upgrade_prompt` before value are reported as chores in `derived.chores_before_value`. A chore
is a fact, not a verdict: an integration may be the value path for a developer tool.

## 7. Worked example

`onboarding_scorer.py flow --demo --json` runs the built-in fictional ledger. Its output shows
the fields the rubric uses: `derived.steps_before_value` 5, `derived.chores_before_value`
(verification, invite), `derived.questions_that_do_not_personalize` (the role survey),
`applicability.progress_and_skip` true and the tour context rows. Use it to check the shape of
your own ledger, never as data about a real product.
