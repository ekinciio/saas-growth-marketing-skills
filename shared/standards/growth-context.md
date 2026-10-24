# Growth Context Standard

Defines `growth-context.md`, the one file that tells every skill who the product is for, how it
sells and what the team is trying to achieve. It lives in the user's project root, is created
on the first run, and is read first by every skill and agent in this toolkit.

Do not confuse the two files: this standard (`shared/standards/growth-context.md`, synced into
skills as `_shared/growth-context.md`) describes the format; the user's file
(`<project root>/growth-context.md`) holds their answers.

## Contents

1. Why it exists
2. File location and format
3. Schema
4. Which fields each skill needs most
5. Reading the file
6. When fields are missing: infer, then ask (at most 3 questions)
7. Writing and updating the file
8. Agents and orchestrators
9. Privacy
10. Example

---

## 1. Why it exists

A URL audit that does not know the buyer, the sales motion or the traffic gives generic
advice: benchmarks from the wrong segment, A/B tests for a site that can never reach
significance, enterprise advice for a self-serve tool. Collecting this context once and reusing
it in every skill fixes that.

## 2. File location and format

- Path: `${CLAUDE_PROJECT_DIR}/growth-context.md`. In SKILL.md text Claude Code replaces
  `${CLAUDE_PROJECT_DIR}` with the project root. If it is not replaced, use the current
  working directory. If the user points to another file, use that file.
- Format: YAML frontmatter followed by free Markdown notes. Keep the frontmatter flat: each key
  holds a single value or a one-line list in brackets. No nesting, so humans can edit it and a
  small standard-library parser could read it. Quote values that YAML could read as a boolean
  or a date, such as the Norway country code and the Norwegian language code
  (`markets: [US, "NO"]`, `languages: [en, "no"]`). Write yes-or-no fields as `true` or
  `false`, never `yes` or `no`.
- Scripts do not parse this file. SKILL.md workflows read it and pass the values a script
  needs as command-line arguments.
- Units are fixed: `monthly_*` fields are per calendar month; `acv` is per year; money is in
  `currency`; counts are plain numbers without separators.

## 3. Schema

Core fields (the ones every skill benefits from) are marked with *.

| Key | Type and allowed values | Meaning |
|---|---|---|
| `schema_version` | `1` | Format version. |
| `updated` | `YYYY-MM-DD` | Last date any value was confirmed or changed. |
| `product` * | text | Product or brand name as customers write it. |
| `website` * | URL | Main marketing site. |
| `one_liner` * | text | What the product does and for whom, in one sentence. |
| `category` | text | The category buyers search for ("employee scheduling software"). |
| `icp` * | text | Ideal customer: company type, size and the user role that gets the value. |
| `buyer` * | text | The role that decides and pays, if different from the user. |
| `gtm_motion` * | `plg`, `sales-led`, `hybrid` | How new customers mostly start. |
| `stage` * | `pre-launch`, `pre-pmf`, `early`, `growth`, `scale` | Company stage. |
| `arr_band` | `none`, `<100k`, `100k-1m`, `1m-10m`, `10m+` | Annual recurring revenue band, in `currency`. |
| `pricing_model` | `flat`, `tiered`, `per-seat`, `usage`, `hybrid`, `free` | How price scales. |
| `free_offer` | `free-trial`, `freemium`, `demo-only`, `none` | How people try it. |
| `card_required` | `true`, `false` | Card needed to start the trial or free plan. |
| `acv` * | number | Average annual contract value per customer. |
| `currency` | ISO 4217 code, default `USD` | Currency for `acv`, `arr_band` and prices. |
| `price_points` * | list | Public plans, for example `[Starter 19/mo, Team 49/mo, Enterprise contact sales]`. |
| `monthly_visitors` * | number | Website visitors per month, all pages. |
| `monthly_signups` * | number | New accounts or trials per month. |
| `activation_event` * | text | The first action that predicts retention, with its time window ("ran first report within 7 days"). |
| `platforms` | list of `web`, `ios`, `android`, `desktop`, `api` | Where the product runs. |
| `app_ids` | list | App Store IDs and Google Play package names. |
| `competitors` * | list, up to 5 | Main alternatives buyers compare, as `Name (url)`. Top 3 first. |
| `current_goal` * | text | The goal this quarter: metric, target and date ("trial-to-paid 8% to 12% by 2027-01-31"). |
| `markets` * | list of ISO 3166 codes or regions | Where customers are. |
| `languages` * | list of ISO 639-1 codes | Languages of the product and site. |
| `report_language` | ISO 639-1 code | Language for reports. Default: the language of the user's request. |
| `locations` | list | Physical locations or service areas (local-seo-optimizer only). |
| `constraints` | text | Limits that shape advice: team size, budget, no paid ads, regulated industry. |
| `assumed` | list of keys | Keys whose values were inferred, not confirmed by the user. |

Below the frontmatter, two Markdown sections:

- `## Notes`: anything else the user wants every skill to know.
- `## Sources`: one dated line per value that came from somewhere specific
  ("2026-10-24 icp: inferred from the homepage hero on https://acme.app").

## 4. Which fields each skill needs most

Ask only for fields in this table that are still empty and cannot be inferred. Order shows
priority.

| Skill or agent | Fields that change the advice most |
|---|---|
| geo-seo-auditor | `website`, `category`, `competitors`, `markets`, `languages` |
| landing-page-cro | `icp`, `gtm_motion`, `current_goal`, `monthly_visitors`, `free_offer` |
| saas-landing-builder | `one_liner`, `icp`, `buyer`, `gtm_motion`, `competitors`, `price_points` |
| web-app-growth-engine | `gtm_motion`, `free_offer`, `card_required`, `monthly_signups`, `monthly_visitors` |
| onboarding-optimizer | `activation_event`, `icp`, `gtm_motion`, `platforms` |
| plg-funnel-analyzer | `gtm_motion`, `free_offer`, `monthly_visitors`, `monthly_signups`, `activation_event`, `acv` |
| subscription-metrics | `stage`, `arr_band`, `acv`, `pricing_model`, `currency`, `icp` |
| retention-playbook | `icp`, `acv`, `pricing_model`, `activation_event`, `current_goal` |
| pricing-analyzer | `price_points`, `pricing_model`, `acv`, `buyer`, `competitors`, `gtm_motion` |
| competitor-intel | `competitors`, `one_liner`, `icp`, `markets` |
| brand-mention-scanner | `product`, `website`, `category`, `competitors` |
| reddit-opportunity-finder | `one_liner`, `category`, `icp`, `competitors` |
| review-sentiment | `product`, `platforms`, `app_ids`, `languages`, `competitors` |
| aso-optimizer | `app_ids`, `platforms`, `category`, `markets`, `languages`, `competitors` |
| local-seo-optimizer | `product`, `website`, `locations`, `category`, `markets` |
| growth-skills | `current_goal`, `stage`, `gtm_motion` |
| growth-strategist, launch-planner, metrics-analyst | all core fields; they pass the file to each skill they run |

## 5. Reading the file

1. Read the file before asking anything and before running any script.
2. Precedence when values disagree: what the user said in this conversation, then file values
   not listed in `assumed`, then values inferred in this run, then file values listed in
   `assumed`.
3. If `updated` is more than 90 days old, treat `monthly_visitors`, `monthly_signups` and
   `current_goal` as possibly stale. Say so under Assumptions in the report, and confirm them
   only when the main recommendation depends on them (this counts toward the 3 questions).
4. Use the values: pick benchmarks for the matching segment (`gtm_motion`, `acv`, `stage`,
   `pricing_model`), size test plans from `monthly_visitors` and `monthly_signups`
   (`report-contract.md` section 6), write copy for `icp` and `buyer`, compare against
   `competitors`, and rank bets by their effect on `current_goal`.

## 6. When fields are missing: infer, then ask (at most 3 questions)

1. List the missing fields that matter for this skill (section 4).
2. Infer what you can from cheap sources: the URL the user gave (homepage hero, pricing page,
   signup page, footer), the app store listing, and the user's own messages. Record each
   inferred value with its source and add its key to `assumed`.
3. Never infer numbers. `monthly_visitors`, `monthly_signups`, `acv` and revenue are never
   guessed from a website; if the user does not give them, they stay empty and the report
   lists them under "Not measured and how to get it".
4. Ask only for what is still missing and would change the advice, at most 3 questions per
   run, in one batch, in the main conversation only. Use AskUserQuestion when available, with
   short options and a "Not sure" option. Typical high-value questions: monthly visitors and
   signups (they decide whether A/B tests are possible), the current goal, and the sales
   motion.
5. If the user skips a question, continue: use the inferred value marked as assumed, or leave
   the field empty, and list it under Assumptions in the report.
6. In a subagent, never ask (subagents cannot). Return `MISSING_INPUTS: <field>, <field>` for
   required inputs that cannot be read or inferred, and do not invent them.

## 7. Writing and updating the file

- Create the file at the end of the first run that collected or inferred any value. Say so in
  the chat summary ("Saved what I learned to growth-context.md; edit it any time").
- Update only what changed in this run. Never overwrite a value the user gave with an inferred
  value. When the user confirms an assumed value, remove its key from `assumed`.
- Set `updated` to today whenever a value changes, and add a dated line to `## Sources`.
- Keep the frontmatter flat and the keys in the schema order.
- Inside an orchestrated run only the orchestrator writes the file; subagents treat it as
  read-only, so parallel runs do not overwrite each other.

## 8. Agents and orchestrators

- An orchestrator (a main-thread skill such as a growth audit) does the intake once: it reads
  the file, infers what it can, asks at most 3 questions, and writes the file before it starts
  any sub-skill.
- It passes the file's path and full contents in every subagent prompt, with the instruction:
  "Use this growth context; do not ask the user; return MISSING_INPUTS for anything required
  that is missing."
- The agents in `agents/` (growth-strategist, launch-planner, metrics-analyst) run as
  subagents. They read the file, never ask the user, return `MISSING_INPUTS` when a required
  value is missing, and never invent URLs or numbers.
- Sub-skills run in the main conversation read the file themselves.

## 9. Privacy

- Store aggregates only: no customer names or emails, no raw billing or analytics exports, no
  API keys, passwords or tokens.
- The file sits in the project root and is not git-ignored by default, because teams may want
  to share it. If the project is a public repository, tell the user once that the file
  becomes public if committed.

## 10. Example

```markdown
---
schema_version: 1
updated: 2026-10-24
product: Shiftly
website: https://shiftly.example
one_liner: Shiftly helps restaurant managers build staff schedules in minutes.
category: employee scheduling software
icp: Independent restaurants and small chains with 10-80 hourly staff
buyer: Owner or general manager
gtm_motion: plg
stage: early
arr_band: 100k-1m
pricing_model: per-seat
free_offer: free-trial
card_required: false
acv: 1200
currency: USD
price_points: [Starter 3/user/mo, Pro 5/user/mo, Enterprise contact sales]
monthly_visitors: 18000
monthly_signups: 420
activation_event: Published the first weekly schedule within 7 days of signup
platforms: [web, ios, android]
app_ids: [1234567890, com.shiftly.app]
competitors: [7shifts (https://www.7shifts.com), Homebase (https://joinhomebase.com), When I Work (https://wheniwork.com)]
current_goal: Raise trial-to-paid from 9% to 12% by 2027-01-31
markets: [US, CA]
languages: [en]
report_language: en
constraints: Two engineers, no paid ads budget
assumed: [icp, stage]
---

## Notes
Most signups come from the app stores, not the website.

## Sources
- 2026-10-24 icp: inferred from the homepage hero on https://shiftly.example
- 2026-10-24 stage: inferred from team size on the About page
- 2026-10-20 monthly_visitors, monthly_signups: given by the user
```
