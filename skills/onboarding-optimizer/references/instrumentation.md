# Activation Definition, Exports and Instrumentation Plan

Read this when the user has (or should get) analytics data: to define activation, to get an
export the funnel script can read, and to write the instrumentation plan in the report.

Last verified: 2026-10

## Contents

1. Define activation before measuring it
2. Getting an export the script can read
3. Choosing the funnel steps
4. Reading the funnel output
5. Instrumentation plan (report asset)
6. Privacy

---

## 1. Define activation before measuring it

- Activation is the first action that predicts retention, with a time window: "ran the first
  report within 7 days", not "logged in". Take it from `activation_event` in
  `growth-context.md`; otherwise ask (it counts toward the 3 questions).
- Distinguish three moments and name each in the report:
  - setup: the product can work for this user (data connected, workspace exists)
  - first value (aha): the user sees the outcome they came for, on their own data or work
  - habit: the action repeats (for example weekly), which is where retention shows
- The activation event should sit at the first value moment or just after it. If the team's
  definition is a setup step ("connected an integration"), say so: it measures setup, not value.
- Benchmarks for activation and time to value depend on each source's definition (each row's
  `definition` and `note`). Compare only when the definitions match; otherwise label the
  comparison low confidence.

## 2. Getting an export the script can read

`onboarding_funnel.py` reads three shapes. Ask for the first one when possible.

| Shape | Columns it needs | Gives |
|---|---|---|
| Raw event log (one row per event) | a user id, an event name, a timestamp | step conversion, biggest drop, time to each step and to activation (median, p75, p90), activation by weekly or monthly cohort |
| Funnel export (one row per step, optional breakdown) | a step name and a count; optional time to convert | step conversion and the biggest drop per segment |
| Step counts typed by the user | written by you as JSON: `{"steps": [{"name": ..., "count": ...}]}` | the same as a funnel export, medium confidence |

How users usually get them (menu names change; if the user cannot find the menu, ask for any
CSV with user id, event and time for the onboarding events of the last 60-90 days):

- PostHog: insights and data tables can be exported to CSV; a SQL insight that selects
  `event, distinct_id, timestamp` for the onboarding events gives the raw log.
- Mixpanel: reports export to CSV; a raw event export has `event`, `distinct_id` and `time`.
- Amplitude: charts export to CSV; the export API gives `event_type`, `user_id`, `event_time`.
- GA4: a funnel exploration can be exported (CSV or Sheets); the BigQuery export has
  `event_name`, `user_pseudo_id`, `event_timestamp`.
- Any warehouse: one query that returns `user_id, event, timestamp` for the step events.

If an analytics connector (an MCP server for PostHog, Mixpanel or Amplitude) is already
connected in this session, ask once before using it, pull only aggregated step counts or the
three columns above for the onboarding events, save them as a file and run the script on the
file. Say in the report Sources that the connector was used. Never ask the user to paste API keys
into the chat.

## 3. Choosing the funnel steps

- First step: the account-created or signup-completed event (the cohort entry).
- Middle steps: the 2-5 actions on the path to value, in order (workspace created, data source
  connected, first item created, teammate invited).
- Last step: the activation event.
- Window: the window in the activation definition (`--window-days 7` for "within 7 days").
  Default 14.
- Run once without `--step` when you do not know the event names: the output lists the most
  frequent events.

## 4. Reading the funnel output

- `funnel.biggest_drop`: the step with the largest share lost from the previous step. It is the
  first candidate for the biggest constraint, if that step is on the path to value.
- `activation.rate_complete_cohorts` and its `ci95`: the activation rate among cohorts whose
  whole window has passed. `rate_so_far` includes users still inside their window and is biased
  low; do not report it as the activation rate.
- `time_to_activation` median and p75 (hours): the p75 sets the delay for a stalled-user nudge
  (send it before most activators would have finished).
- `cohorts`: look for a change in activation between cohorts only when the intervals do not
  overlap; overlapping intervals are noise. Cohorts flagged `small` (under 30 users) are not
  evidence of a trend.
- Use the measured baseline and the weekly entries (`activation.users_entered` over the weeks
  in the file, or `monthly_signups`) for `onboarding_scorer.py plan`.

## 5. Instrumentation plan (report asset)

Write it when the export is missing, the steps are not tracked, or the activation event is not
defined. Event names in `object_action` form, past tense, snake_case; one event per user
action, properties for detail.

| Event | When | Properties |
|---|---|---|
| `account_created` | Account exists | `signup_method`, `invited` (true/false), `plan` |
| `onboarding_step_viewed` | Each first-run screen is shown | `step`, `step_index` |
| `onboarding_step_completed` | A step is finished or skipped | `step`, `skipped` |
| `survey_answered` | A routing question is answered | `question`, `answer` |
| `template_selected` / `sample_data_opened` / `ai_starter_generated` | A starting point is chosen | `template_id` or `prompt_length` |
| `integration_connected` / `data_source_connected` / `sdk_first_event_received` | Setup that unlocks value | `type` |
| `<core_object>_created` | The first unit of value (report, board, project) | `source` (template, blank, ai) |
| `teammate_invited` / `invite_accepted` | Team activation | `invite_count` |
| `checklist_item_completed` | A checklist item is done | `item`, `position` |
| `tour_started` / `tour_completed` / `tour_dismissed` | Tour engagement | `tour_id`, `step` |
| `paywall_viewed` / `trial_started` / `subscription_started` | Monetization touchpoints | `plan`, `trigger` |

Add `workspace_id` (or account id) to every event so team products can be analyzed by account.
Define `activated` as a derived cohort in the analytics tool rather than a client event, so the
definition can change without a release.

## 6. Privacy

- Exports need only user id, event name and timestamp for the onboarding events. The script
  hashes user ids in memory, ignores contact columns (email, name, phone) and refuses files that
  are lists of people.
- The report shows aggregates only: counts, rates, times. Never paste rows, ids or emails.
- Exports stay where the user saved them; do not copy them into `growth-reports/`.
