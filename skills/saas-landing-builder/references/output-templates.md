# Output Templates per Command

Last verified: 2026-10

Read this before you write the report. Each command fills the shared report contract
(`references/_shared/report-contract.md`, section 13) with its own content. Headings are
translated into the report language, except `## Change since last run`, which stays in
English with the translation after it. The footer is always English and is added by the
report helper.

## Contents

1. Header lines per command
2. create: blueprint report
3. copy: copy deck report
4. wireframe: prototype report
5. review: rebuild plan report
6. Sidecar data for this skill
7. Chat summaries

---

## 1. Header lines per command

| Command | Title | Subject | Scoring line | Score line |
|---|---|---|---|---|
| create | `# Landing page blueprint: <Product> (<page type label>)` | `<Product> <page-type-id>` | `none (a blueprint; nothing on a live page is scored)` | none |
| copy | `# Landing page copy: <Product> (<page type label>)` | `<Product> <page-type-id>` | `none (copy deck)` | none |
| wireframe | `# Landing page prototype: <Product> (<page type label>)` | `<Product> <page-type-id>` | `none (HTML draft)` | none |
| review | `# Rebuild plan: <url>` | the URL | `rubric (references/section-labels.md v1, section sets <version>)` | the completeness `summary`, for example `Required 3 of 4; recommended 2 of 6 (PLG homepage set; rubric; confidence medium)` |

Create, copy and wireframe for the same product and page type share one subject, so a
later run on the same day replaces the earlier one. When the user wants to keep both, add
the command to the subject (`<Product> <page-type-id> copy`).

Sources line: the user's brief and answers (date), `growth-context.md`, every URL fetched
(static fetch with HTTP status, or rendered), voice-of-customer sources, WebSearch queries.

## 2. create: blueprint report

1. `## Diagnosis`: 3-5 facts about the starting point, each with an evidence ID: the ICP and
   buyer, the awareness stage of the main traffic, the proof inventory (what exists, what
   does not), the main alternative, what the current site says (when pre-filled from a URL).
2. `## Biggest constraint`: the one input gap or fact that most limits the page (often: no
   usable proof, an unclear category, or traffic that is colder than the planned page).
3. `## Findings by area`: Area | Status | Evidence | What to do, with these areas:
   Positioning and one-liner; Audience and awareness; Proof inventory; Objections; Offer and
   CTA; Traffic and message match; Measurement readiness.
4. `## Top 3 bets`: the three highest-ICE decisions to make or test at launch (for example a
   hero angle test, a proof-collection sprint, a message-matched variant for paid traffic),
   each with a test plan from `blueprint_tools.py test-plan`.
5. `## Ready-to-ship assets`, in this order, each labelled Draft:
   - Page blueprint table: # | Section (label) | Job on this page | Draft copy (headline and
     body) | Proof slot | CTA | Objection handled
   - Hero variants: 3-5 headlines with angle and the awareness stage each fits; the
     recommended one first
   - Section copy: every section's final draft copy, in page order
   - Message-match table (when two or more traffic sources, and always for paid pages)
   - FAQ drafts from the top objections; facts not confirmed are `[CONFIRM: ...]`
   - SEO title and meta description drafts for the page
   - `### Proof to collect before launch` checklist (always last)
6. `## Details`: framework choice and why; section order and why; sections left out and why;
   the voice-of-customer phrase bank with sources.
7. `## Not measured and how to get it`, `## Assumptions`, `## Change since last run`,
   `## Evidence`.

## 3. copy: copy deck report

Same structure as create, with these differences:

- Diagnosis and constraint focus on the message: what the buyer must believe, which
  objection blocks them, which phrases the buyer uses.
- Findings by area: Clarity of the one-liner; Voice of customer; Proof; Objections; CTA and
  risk reducers; Message match.
- Ready-to-ship assets: the copy deck per section (headline, subheadline or body, CTA,
  microcopy), 3-5 hero variants, CTA variants, FAQ drafts, meta title and description, and
  the proof checklist last.

## 4. wireframe: prototype report

- Diagnosis: what the prototype covers (page type, sections, copy source), what it does not.
- Biggest constraint: usually the open proof placeholders or missing brand inputs.
- Findings by area: Structure (sections and order versus the blueprint); Copy fidelity;
  Proof placeholders; Accessibility and mobile (from `lint` html checks and screenshots);
  Hand-off readiness.
- Ready-to-ship assets: the file path of the HTML draft, how to open it, the section list,
  the `lint` result (must-fix items left: 0), the developer hand-off list, and the proof
  checklist last.

## 5. review: rebuild plan report

1. Header with the Score line from `completeness`, and in Coverage: how the page was seen
   (static fetch, rendered, saved file) and any slots marked not measured.
2. `## Diagnosis`: facts from the outline (block count, what the hero says, where proof
   first appears, missing required slots), each with evidence IDs pointing at block
   indices.
3. `## Biggest constraint`: the missing or weak job that most limits the page for its type
   and the user's goal.
4. `## Scorecard`: Slot | Level | Status | Blocks | Evidence | Confidence | Note, then the
   line "Labels are model-assigned from the extracted outline; a borderline block can change
   label between runs."
5. `## Top 3 bets`: the rebuild moves with the most impact (add a missing required slot,
   rewrite the hero, move proof next to the first ask), with ICE and test plans.
6. `## Ready-to-ship assets`: the rebuild table (Block | What it is now | Label | Decision:
   Keep, Rewrite, Move, Merge, Cut or Add | Why, with evidence), the new section order, draft
   copy for every Rewrite and Add, and the proof checklist last.
7. `## Details`: the full block outline with labels; claims found on the current page that
   need a source (from the analyzer's `claims`), as questions for the user.
8. A line in Details or Next: "For a conversion score of the current page, run
   landing-page-cro."

## 6. Sidecar data for this skill

Pass these keys in the `--data` file of the report helper, besides the contract's required
keys (`schema_version`, `language`, `scoring`, `dimensions`, `findings`, `constraint`, `bets`,
`coverage`, `evidence`, `assumptions`, `metrics`):

```json
{
  "command": "create",
  "page_type": "plg-homepage",
  "framework": "PAS",
  "awareness": "problem-aware",
  "sections": ["hero", "problem", "solution", "how_it_works", "testimonials", "faq", "final_cta"],
  "voc_sources": 2,
  "prototype": "growth-reports/2026-10-24-saas-landing-builder-acme-plg-homepage.html",
  "metrics": {
    "proof_placeholders_open": {"value": 7, "unit": "count", "period": "point_in_time"},
    "unsourced_claims_open": {"value": 0, "unit": "count", "period": "point_in_time"}
  }
}
```

- `proof_placeholders_open` and `unsourced_claims_open` come from `lint` on the final draft,
  so the next run shows how many proof gaps were closed.
- For review, copy `sidecar.scoring`, `sidecar.dimensions` and `sidecar.metrics` from the
  `completeness` output and add the confidence you assigned.
- In `none` mode `scoring.value`, `scoring.max`, `scoring.confidence` and
  `scoring.measured_weight` are null and `dimensions` is empty.

## 7. Chat summaries

At most 5 lines, in the user's language, no emojis.

create, copy, wireframe:

```
Report: growth-reports/<date>-saas-landing-builder-<slug>.md (prototype: <slug>.html)
Biggest constraint: <one sentence>
Top bets: 1) <...> 2) <...> 3) <...>
Not measured: <main gaps>; proof placeholders open: <n>
Next: <collect the proof on the checklist | run wireframe for an HTML draft | after launch, landing-page-cro>
```

review:

```
Report: growth-reports/<date>-saas-landing-builder-<slug>.md
Biggest constraint: <one sentence>
Top bets: 1) <...> 2) <...> 3) <...>
Score: <completeness summary> (rubric, <confidence> confidence) | Not measured: <gaps>
Next: <create the new blueprint | landing-page-cro for a conversion score of the current page>
```

When `growth-context.md` was created or updated in this run, say so on the Next line.
