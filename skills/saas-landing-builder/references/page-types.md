# Page Types, Section Sets and Message Match

Last verified: 2026-10

Read this before you pick a section set. The machine-readable sets live in
`scripts/section_sets.json`; `blueprint_tools.py sections --page-type <id>` prints the one
in use. This file explains why each set looks the way it does. The sets are house guidance
written for this toolkit from common practice on SaaS sites, not a benchmark: no section is
proven to add a fixed amount of conversion.

## Contents

1. How to pick the page type
2. Slots: what "complete" means
3. The seven page types
4. Section order as a narrative
5. Awareness stages
6. Message match for several traffic sources
7. What to leave out

---

## 1. How to pick the page type

| Situation | Page type id |
|---|---|
| Main site homepage, visitors can sign up or start free on their own | `plg-homepage` |
| Main site homepage, the main path is a demo or a sales conversation | `sales-led-homepage` |
| Hybrid motion (self-serve plus sales) | `plg-homepage` with a secondary "Talk to sales" CTA, or `sales-led-homepage` when most revenue comes from sales-assisted deals |
| Paid ads (search, social) that send visitors to a self-serve signup | `paid-signup-lp` |
| Paid, outbound, partner or event traffic that should book a demo | `demo-lp` |
| One feature, use case, role, industry or integration | `feature-page` |
| Product not live yet; the goal is a waitlist or early-access list | `waitlist` |
| A new pricing page (layout and copy only) | `pricing-page` |

`gtm_motion` in `growth-context.md` gives the default: `plg` to `plg-homepage`, `sales-led`
to `sales-led-homepage`, `hybrid` to `plg-homepage` with a sales CTA. Price levels, tiers and
packaging belong to pricing-analyzer; this skill only lays out and writes the page.

## 2. Slots: what "complete" means

A slot is a job the page must do. Each slot lists the block labels that can fill it, so a
lean page is not punished for using one strong block instead of three weak ones. Example:
the `proof` slot of a PLG homepage is filled by a logo bar (`social_proof`) or by named
quotes (`testimonials`).

- **Required**: without it the page cannot do its job for this page type.
- **Recommended**: most pages of this type are stronger with it; leaving it out is a
  decision to state, not a defect.
- **Optional**: add it only when the intake gives a reason (an objection, a traffic source,
  a buyer role).

Completeness is reported as "required X of Y; recommended X of Y" for the chosen page type,
never against a fixed list of 12 sections, and never as a percentage.

## 3. The seven page types

### plg-homepage

- Goal: self-serve signup (free trial or freemium). Full navigation.
- Required: hero, proof (logos or named quotes), product (what it does), final CTA.
- Recommended: named proof, see it work (steps or a product demo), objections (FAQ,
  security or comparison), integrations, footer.
- Optional: problem, use cases, pricing teaser.
- Emphasis: show the product early; self-serve buyers judge by what they can see.
  Interactive demos or short product clips often replace long feature lists.

### sales-led-homepage

- Goal: demo request or contact sales. Full navigation.
- Required: hero, proof, product, next step (final CTA or inline form).
- Recommended: named proof (case studies with outcomes), use cases by role or industry,
  security and compliance, integrations, see it work, footer.
- Optional: problem, objections (FAQ or comparison), pricing anchor.
- Emphasis: several people buy. Give each role a reason (use cases) and give the security
  reviewer what they need.

### paid-signup-lp

- Goal: self-serve signup from paid traffic. Minimal navigation (logo plus one CTA): every
  extra link is an exit the ad budget paid for.
- Required: hero that matches the ad, proof, product, final CTA (the same ask as the hero).
- Recommended: problem, named proof, objections, see it work.
- Optional: pricing, integrations, footer with legal links only.
- Emphasis: one audience, one promise, one CTA. Build one variant per ad group theme
  (section 6).

### demo-lp

- Goal: demo request. Minimal navigation.
- Required: hero, proof, product, next step (the form or booking step).
- Recommended: named proof from the visitor's segment, what happens next (who calls, how
  long, what they get), objections (FAQ, security), problem.
- Optional: integrations, use cases, footer with legal links.
- Emphasis: the form is a cost. Say what the demo gives, ask only for fields sales uses, and
  say what happens after submit.

### feature-page

- Goal: the site's main conversion. Full navigation.
- Required: hero (the feature and its outcome), product (how it works), final CTA.
- Recommended: proof, use cases, see it work, FAQ, footer.
- Optional: problem, integrations (required in practice on an integration page), pricing
  (when the feature is a paid add-on or plan-gated).
- Emphasis: these pages often catch search traffic for a job ("schedule shifts by
  availability"); answer that job in the first screen.

### waitlist

- Goal: waitlist signup. Minimal navigation.
- Required: hero, product, signup (form or CTA).
- Recommended: problem, credibility (only real: founder track record, design partners or
  beta users who agreed to be named), FAQ (launch timing, price expectations, data), final
  CTA.
- Optional: see it work, use cases, pricing (only when decided), footer with a privacy link.
- Emphasis: no invented user counts, no fake scarcity ("only 100 spots") unless the limit is
  real and enforced.

### pricing-page

- Goal: plan selection, signup or contact sales. Full navigation.
- Required: plans (prices and what each plan includes), objections (billing, limits,
  cancellation, plan choice).
- Recommended: proof, a short hero, security, next step, footer.
- Optional: comparison with a named alternative, integrations when plan-gated.
- Emphasis: price points come from the user or pricing-analyzer, never from you. For usage
  or credit pricing, show worked examples or a calculator the user can verify.

## 4. Section order as a narrative

There is no single correct order. Judge order by whether the page answers the visitor's
questions in the order they ask them:

1. What is this, is it for me, and what do I do next? (hero)
2. Can I believe it? (proof close to the first ask)
3. How does it work for someone like me? (product, steps, demo, use cases)
4. What could go wrong? (objections, security, pricing questions) before the final ask
5. What now? (final CTA that repeats the main ask)

Guidelines, not rules:

- Put some proof before or right after the first big ask.
- Handle the main objections before the final CTA.
- Problem-first pages (cold or problem-aware traffic) put the problem right after the hero;
  product-aware pages (branded search, retargeting) can skip it.
- Keep one primary CTA text for the whole page; a secondary CTA is for a different
  readiness level ("Watch the demo"), not a competing goal.

## 5. Awareness stages

From Eugene Schwartz, *Breakthrough Advertising* (1966); still the most useful way to decide
how much the page must explain before it asks.

| Stage | Visitor knows | Typical traffic | Page starts with |
|---|---|---|---|
| Unaware | Nothing about the problem | Broad social, display | A recognizable situation or cost |
| Problem-aware | The pain, not the solutions | Problem keywords, communities, many paid social ads | The problem in their words, then the new way |
| Solution-aware | Solutions exist, not yours | Category keywords ("scheduling software"), comparison research | What makes yours different from the main alternative |
| Product-aware | Your product, not convinced | Branded search, retargeting, referrals | Proof and the offer |
| Most aware | Ready, needs a reason now | Existing leads, trial users, pricing page | The offer, terms and next step |

When the stage is unknown, assume solution-aware for organic homepages and problem-aware for
paid social, and list it under Assumptions.

## 6. Message match for several traffic sources

Message match means the first screen repeats the promise that made the visitor click.
Build the table when the intake names two or more traffic sources, and always for paid
landing pages (one row per ad group or campaign theme).

| Source | What they searched or clicked | Awareness | Hero headline variant | CTA | Proof shown first |
|---|---|---|---|---|---|
| Google Ads: category keywords | "[keyword theme]" | Solution-aware | [variant that names the category and the difference] | [same CTA everywhere] | [proof from that segment] |
| LinkedIn: role targeting | "[ad promise]" | Problem-aware | [variant that names the role's pain] | [CTA] | [named quote from that role] |
| Branded search | "[product name]" | Product-aware | [offer-led variant] | [CTA] | [rating or logos] |

Rules: one variant per row, the same CTA text across rows unless the offer differs, and no
claim in a variant that the main page cannot back up.

## 7. What to leave out

- Sections with nothing true to say yet (a testimonials block with no testimonials becomes a
  placeholder in the draft and an item in "Proof to collect before launch", not invented
  quotes).
- Feature lists longer than the visitor can scan; link to feature pages instead.
- Pricing on a homepage when the pricing page does the job better.
- A second goal (newsletter, careers, blog) competing with the main ask on a landing page.
