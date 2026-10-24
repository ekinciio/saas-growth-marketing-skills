# Section Labels and Rebuild Rubric (rubric v1)

Last verified: 2026-10

Read this before you label the blocks of an existing page (the `review` command) and before
you write a rebuild plan. The labels are the rubric: the model assigns them from the
extracted facts, quotes evidence for each, and `blueprint_tools.py completeness` counts them
against the page type's section set. There is no automatic order verdict and no score for
copy quality here; conversion scoring belongs to landing-page-cro.

## Contents

1. Labelling rules
2. Label definitions
3. Hard cases
4. Confidence
5. Rebuild decisions per block
6. How to report completeness

---

## 1. Labelling rules

- Label every block in the outline, in order. Use `other` when no label fits.
- A block may carry two labels when it really does two jobs: a hero with an inline waitlist
  form is `["hero", "lead_form"]`; a features block with one named quote is
  `["features", "testimonials"]`. Do not add a second label for a passing mention.
- Label from what the block does for the visitor, not from class names or ids. A block with
  id `testimonials` that holds only logos is `social_proof`.
- Use the excerpt, heading, subheadings, CTAs, image count and markers (`has_blockquote`,
  `has_accordion`, `has_form`, `has_table`). When the excerpt is cut off and the label is
  unclear, say so and lower the confidence; do not guess.
- Blocks with `similar_to` set are usually the mobile or desktop twin of an earlier block.
  Give them the same label as the twin and mention the duplicate once.
- Label the page footer from `chrome.footer` with `{"block": "footer", "labels": ["footer"]}`
  when it is present.
- Every label gets an evidence line: the block index plus a short quote from the heading or
  excerpt (for example `block 4: "Live in an afternoon" + 3 numbered steps`).

## 2. Label definitions

| Label | Label it when the block | Not this label when |
|---|---|---|
| `hero` | Is the first content block and carries the main headline (usually the H1), with a subheadline or CTA | A later block repeats the H1 style (that is `final_cta` or `other`) |
| `social_proof` | Shows customer logos, counts, ratings, awards or press without a named person's words | It quotes a named person (`testimonials`) |
| `problem` | Describes the pain, cost or status quo before the product appears | It only lists features with negative wording |
| `solution` | Says in a few sentences what the product is and what changes for the user | It is a grid of separate capabilities (`features`) |
| `features` | Presents capabilities as cards, tabs or rows | It is numbered steps (`how_it_works`) |
| `how_it_works` | Gives ordered steps from start to outcome, or what happens after the CTA | The numbers are feature labels ("Fig 0.1") rather than a sequence |
| `product_demo` | Embeds an interactive demo, a video walkthrough or a click-through tour | It is a static screenshot inside another block |
| `testimonials` | Quotes a person or names a customer story (name, role or company attached) | Quotes have no attribution at all (label `social_proof` and note the gap) |
| `pricing` | Shows prices or plans, or a pricing teaser with a link to the pricing page | Only the nav links to pricing |
| `faq` | Lists questions with answers (accordion or plain) | It is a single "Questions? Contact us" line (`other` or `final_cta`) |
| `integrations` | Names or shows the tools it connects with, or the API | One logo appears inside a feature card |
| `security` | Covers security, compliance, privacy or reliability (SOC 2, GDPR, uptime, data residency) | A footer link says "Security" (that is chrome) |
| `comparison` | Compares with alternatives or the old way, side by side | It is a plan comparison table (`pricing`) |
| `use_cases` | Is organized by role, team, industry or job to be done | It lists features with role names in passing |
| `final_cta` | Is near the end and its main job is the conversion ask | It is a mid-page CTA band after the hero (`other`, or the section it belongs to) |
| `lead_form` | Contains a form the visitor fills on the page (demo, waitlist, contact) | The only form is a newsletter in the footer |
| `footer` | Is the page footer from `chrome.footer` | Never for a main-content block |
| `other` | Does anything else: changelog, blog or event teasers, careers, announcements, newsletter | Use it rather than forcing a wrong label |

## 3. Hard cases

- **Logo images counted as images**: `images` includes inline SVGs, so an icon-heavy block can
  show a high count. Judge logos from the heading ("Trusted by", "Powering") and the excerpt.
- **Thin static HTML**: when the analyzer's `render.render_recommended` is true, render the
  page first (Failure handling in SKILL.md). If you cannot, label what you have,
  mark slots you could not observe as `not_measured` in the labels file, and say so in the
  coverage note. A section you did not see is not missing.
- **Tabs and carousels**: hidden panels are removed as hidden content. If the visible tab
  suggests more panels, note "other tabs not seen" instead of marking them missing.
- **Non-English pages**: label from meaning; the labels do not depend on language. Quote the
  original text in evidence with a translation in brackets.

## 4. Confidence

| Level | When |
|---|---|
| high | The block's excerpt and markers make the job clear, and the page was fully seen (static HTML was complete or a render was used) |
| medium | The label fits but the excerpt is cut off, or the page is static HTML with a render recommendation you could not follow |
| low | The block is ambiguous (decorative, mostly images, or a mixed block) |

## 5. Rebuild decisions per block

For each block of the current page, decide one of:

| Decision | When | Write |
|---|---|---|
| Keep | It does its job for the target page type and its claims are sourced | Why it works, in one line |
| Rewrite | The job is right but the copy is vague, feature-led, off-audience or claims are unsourced | The new draft copy (or the brief for it) |
| Move | The job is right but it answers a question too early or too late in the narrative order | Where it goes and why |
| Merge | Two blocks do the same job (often responsive twins or two logo bars) | Which block absorbs which |
| Cut | It does not serve this page type's goal (a second goal, a changelog on a paid LP) | Where the content can live instead |
| Add | A required or recommended slot is missing | The new section's job, draft copy and proof slot |

Every decision cites the block's evidence ID. Copy you rewrite follows the proof rules in SKILL.md: unsourced numbers on the current page become questions for
the user ("confirm the source of '10,000+ teams'"), not facts in the new draft.

## 6. How to report completeness

- Run `completeness` and copy its `summary`, `slots` and `sidecar` into the report and
  sidecar. Never count slots yourself.
- When `show_counts` is false (scoring mode `none`, or less than 60% of slots measured),
  show the slot table with statuses and no counts.
- Scorecard columns: Slot | Level | Status | Blocks | Evidence | Confidence | Note.
- After the table, one line: "Labels are model-assigned from the extracted outline; a
  borderline block can change label between runs."
- A missing recommended slot is a decision to discuss, not a defect. A missing required
  slot is a finding with an Add decision in the rebuild plan.
