# Onboarding Pattern Library

First-run patterns for SaaS products, with when to use each, when to avoid it, how to build it
and what to measure. Use it to pick the pattern fit (a primary pattern plus one or two
supporting ones) and to shape the bets. Product type keys match `references/rubric.md`.

Last verified: 2026-10

Evidence rule for this file: company examples are described only as their own pages describe
them, with the source and the date it was checked. Benchmark numbers are not typed here; get
them with `onboarding_scorer.py benchmarks` (rows from `references/_shared/saas-benchmarks.json`).

## Contents

1. Pattern selection by product type
2. Value before signup
3. AI starter workspace
4. Personalization survey with routing
5. Template gallery
6. Sample data or demo workspace
7. Educational empty states
8. Activation checklist
9. Just-in-time setup wizard
10. Short, user-launched product tour
11. Progressive disclosure
12. Invite-led onboarding
13. Reverse trial
14. Behavior-triggered nudges
15. Combining patterns
16. Sources

---

## 1. Pattern selection by product type

Start from the product type's row, then adjust to the evidence: a pattern the product already
does well stays; the bet goes where the biggest drop or the lowest-scoring dimension is.

| Key | Primary pattern | Supporting patterns | Why |
|---|---|---|---|
| `visual` | Template gallery | Value before signup; short, user-launched tour | The blank canvas is the main obstacle; value can appear in session one. |
| `content` | AI starter workspace | Template gallery; personalization survey | A first draft from the user's own prompt or a template beats an empty page. |
| `data` | Sample data or demo workspace | Educational empty states; just-in-time setup wizard | Real value waits on a connection; sample data shows the payoff while it lands. |
| `developer` | Just-in-time setup wizard | Sample data (test keys, sandbox); educational empty states | The first API call or event is the aha moment; copy-paste setup with the user's own keys. |
| `collaboration` | Activation checklist | Invite-led onboarding; template gallery | Solo value first, then the invite at the moment work is shared. |
| `communication` | Invite-led onboarding | Educational empty states; sample data | A chat or inbox has no value alone; seeded content bridges the wait for teammates. |
| `business_ops` | Just-in-time setup wizard | Sample data; activation checklist | Imports and integrations are unavoidable; ask for each one only when it is needed. |
| `ecommerce` | Activation checklist | Template gallery (store themes); sample data (demo products) | Launch needs several tasks (products, payments, domain); a checklist keeps them in order. |
| `other` | Judge from the description | - | Pick by value horizon: first_session favors templates or AI drafts, after_connection favors sample data, after_team favors invites. |

Cross-cutting patterns that fit any type when the evidence supports them: personalization survey
with routing (several personas or jobs), reverse trial (a freemium product whose paid features
drive retention), behavior-triggered nudges (users who stall between sessions).

## 2. Value before signup

Let visitors use the product, or a real slice of it, before creating an account; ask for the
account when there is something to save or share.

- Best for: first_session products where value appears in minutes (editors, generators, AI
  assistants, calculators).
- Avoid when: value needs the user's data or a connection, or abuse and cost make anonymous
  use unsafe (expensive AI generation without limits).
- Build: keep the anonymous work and carry it into the new account; ask to sign up at the
  moment of saving, sharing or exporting; state what the account adds.
- Measure: share of anonymous sessions that create something, signup rate after creation,
  activation of users who created before signup versus after.
- Example: OpenAI announced on 2024-04-01 that ChatGPT can be used without signing up, with some
  features (saving and sharing chats) reserved for accounts (source 1).

## 3. AI starter workspace

The user describes the goal in plain words and the product builds an editable first version
(workspace, document, app, dashboard).

- Best for: content, collaboration and business tools where a structure (fields, pages,
  workflows) is the blank-page problem.
- Avoid when: output quality on a first prompt is unreliable, or the generated structure is
  hard to edit or undo.
- Build: one prompt box with 3-4 example prompts from the user's job; show the result as
  editable, never final; keep "start blank" and "use a template" visible; cap cost per anonymous
  or free user.
- Measure: prompt submit rate, share of generated workspaces edited within the first session,
  activation of AI-started versus template-started users.
- Example: Airtable's product page says you can build apps with its Omni builder in plain
  language and keep editing the result in Airtable (source 2, checked 2026-10).

## 4. Personalization survey with routing

One to three questions at the start whose answers change what the user sees next: template,
checklist, default view or sample data.

- Best for: products with several personas or jobs (marketing versus engineering, solo versus
  team).
- Avoid when: one path fits most users, or the answers would only feed sales or marketing.
- Build: every question maps to a routing rule (write the table); offer "Not sure" or skip;
  infer what you can from signup data (email domain, invite context); let the user change the
  choice later; avoid long free-text questions.
- Measure: completion and skip rate per question, activation by answer, share of answers that
  actually change the next screen.

## 5. Template gallery

Pre-built starting points organized by use case.

- Best for: visual, content, collaboration and e-commerce products where output varies by use.
- Avoid when: the product has one fixed workflow, or templates with fake data would mislead
  about the user's own results.
- Build: a small set of strong templates grouped by job, matched to the survey answer when there
  is one, with a visible "start blank"; templates should show off the core value, not every
  feature.
- Measure: template pick rate, edits to the template in session one, activation of template
  users versus blank starts.

## 6. Sample data or demo workspace

The product opens with realistic example data so the user sees the payoff before connecting
their own.

- Best for: after_connection products (analytics, CRM, BI, monitoring, developer tools).
- Avoid when: sample data would be confused with real data, or the product is useless until
  the user's data arrives and sample data would only delay the connection.
- Build: label sample data clearly, put "connect your data" next to every sample view, remove
  the sample in one click, and keep the first real data view one step away.
- Measure: share who explore sample data, then connect; time from signup to first real data.
- Example: Metabase's setup guide says it ships with a Sample Database to explore before
  connecting your own data (source 3, checked 2026-10).

## 7. Educational empty states

Each empty screen says what belongs there, why it matters and the one action that fills it.

- Best for: every product, as the minimum layer; especially data-dependent sections that start
  empty.
- Avoid when: the screen can be pre-filled (templates or sample data are better).
- Build: one headline about the outcome, one sentence, one primary CTA, an optional link to a
  short guide; replace the state once the first item exists; never use an empty state to
  advertise an upgrade.
- Measure: CTA click rate per empty state, sections still empty after 7 days.

## 8. Activation checklist

A short, persistent list of the actions that lead to the activation event.

- Best for: products where activation needs several actions across sessions (collaboration,
  e-commerce, business tools).
- Avoid when: there are only one or two actions (just guide them directly), or the list would
  be a tour of features rather than the activation path.
- Build: about 3-5 items, the first already done (account created) or done in one click, each
  item a link to the exact screen; the last item is the activation event; progress persists and
  the list hides when done. Items can launch a short tour (see section 10).
- Measure: item completion by position, checklist completion, activation of checklist users.
  Context row: `checklist_completion.userpilot2025.b2b`.

## 9. Just-in-time setup wizard

Setup that cannot be avoided (connect, import, install), asked at the moment it is needed and
done in the fewest screens.

- Best for: developer, data, business-ops and e-commerce products.
- Avoid when: setup could wait until after a first value moment.
- Build: copy-paste snippets with the user's own keys filled in; a live "waiting for your first
  event" check; "do this later" for anything optional; progress shown when there are 3 or more
  steps; resume where the user left off.
- Measure: completion by step, time per step, share who reach the first real data or call.

## 10. Short, user-launched product tour

A few tooltips that point at the core action, started by the user from a checklist or a help
menu rather than forced on first load.

- Best for: visual interfaces where users must find one key control.
- Avoid when: the product is API-first, or the tour covers features instead of the first
  action, or it plays over an empty screen with nothing to point at.
- Build: few steps (completion falls off after four in Chameleon's 2024 data), each step asks
  the user to do the action, not just read; always dismissible and replayable.
- Measure: start rate, completion, the action rate after the tour. Context rows:
  `tour_completion.chameleon2024.all`, `.self_launched`, `.five_step`.

## 11. Progressive disclosure

A simple first interface that reveals advanced features as usage grows.

- Best for: deep products serving beginners and power users.
- Avoid when: users are experts who expect everything at once, or the core value needs an
  advanced feature on day one.
- Build: tie reveals to usage milestones; keep a "show everything" option; announce new
  capabilities in context, once.
- Measure: feature discovery by cohort, time between milestones.

## 12. Invite-led onboarding

The first user brings in teammates at the moment the work benefits from them; invitees land in
context.

- Best for: collaboration and communication products (after_team value horizon).
- Avoid when: the product is single-player, or the invite is demanded before the user has
  anything to share.
- Build: offer the invite next to a result worth sharing; preview what the invitee sees; send
  invitees straight to the shared item with their own short first run; remind the inviter when
  an invite is pending.
- Measure: invites sent per activated account, invite acceptance, activation of invited users.

## 13. Reverse trial

New users start with the paid features for a limited time, then choose to buy or drop to a
free plan that keeps their work.

- Best for: freemium products whose paid features drive retention and which already have a
  working free plan.
- Avoid when: there is no viable free plan, or paid features need setup that will not happen
  inside the trial window.
- Build: show which features are paid while the user uses them; show days left; at the end,
  keep the work and downgrade rather than lock out.
- Measure: trial-to-paid, free-plan retention after the downgrade, paid-feature usage in the
  trial. Size any change with the `trial` and `plan` commands.
- Source: Kyle Poyar's Growth Unhinged guide defines the model and describes Airtable as an
  early adopter (source 4, 2022).

## 14. Behavior-triggered nudges

Email and in-app messages sent because of what a new user did or did not do, with a link back to
the exact step.

- Best for: every product with a multi-session path to activation.
- Avoid when: messages would fire on time alone, or continue after activation.
- Build: one trigger per stall point on the activation path (set the delay from the user's own
  time-to-activation p75 when the export gives it); one action per message; stop on activation;
  hold out a small control group to measure.
- Measure: return rate within 48 hours of the message, activation of messaged versus held-out
  users.

## 15. Combining patterns

Pick one primary pattern and at most two supporting ones; more creates a disjointed first run.
Common pairs:

- Personalization survey -> template gallery or AI starter workspace (the answer picks the
  starting point).
- Sample data + just-in-time setup wizard (show the payoff, then connect).
- Activation checklist + short, user-launched tours (each item opens its own short tour).
- Value before signup + template gallery (start from a template without an account).
- Invite-led onboarding + educational empty states (explain what teammates will add).

## 16. Sources

1. OpenAI, "Start using ChatGPT instantly", 2024-04-01:
   https://openai.com/index/start-using-chatgpt-instantly/ (checked 2026-10-24)
2. Airtable, "Omni: the expert app builder for every business":
   https://www.airtable.com/platform/app-building (checked 2026-10-24)
3. Metabase documentation, "Setting up Metabase" (Sample Database):
   https://www.metabase.com/docs/latest/configuring-metabase/setting-up-metabase (checked 2026-10-24)
4. Kyle Poyar, "Your guide to reverse trials", Growth Unhinged, 2022:
   https://www.growthunhinged.com/p/your-guide-to-reverse-trials (checked 2026-10-24)
5. Chameleon Benchmark Report 2024 (tour completion; data 2023):
   https://www.chameleon.io/benchmark-report-24 (rows in the shared benchmark file)
6. Userpilot, SaaS Product Metrics Benchmark Report 2025 (checklist completion, activation, time
   to value): https://userpilot.com/saas-product-metrics/ (rows in the shared benchmark file)
