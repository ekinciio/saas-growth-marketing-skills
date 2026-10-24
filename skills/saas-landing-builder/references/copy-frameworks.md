# Copy Frameworks and Voice-of-Customer Copy

Last verified: 2026-10

Read this before you choose a framework or write any section copy. All examples are
illustrative: "Acme" is fictional, and every number, name or quote in an example is a
bracketed placeholder on purpose. Never copy an example's claims into a user's page.

## Contents

1. Choose the framework from awareness and proof
2. PAS: Problem, Agitate, Solution
3. AIDA: Attention, Interest, Desire, Action
4. BAB: Before, After, Bridge
5. 4Ps: Promise, Picture, Proof, Push
6. StoryBrand
7. Voice of customer: write in the buyer's words
8. Headlines, subheadlines and CTAs
9. Plain-language rules
10. Notes for 2026

---

## 1. Choose the framework from awareness and proof

Pick from the awareness stage of the main traffic source and the proof inventory, then say
why in the report's Details section. A framework is a sequence of jobs, not a template to
fill line by line.

| Awareness (main traffic) | Proof inventory | Framework | Why |
|---|---|---|---|
| Unaware or problem-aware | Any | PAS | Visitors must recognize the problem before a product matters |
| Problem-aware, the change is easy to picture | Any | BAB | A clear before and after carries the page |
| Solution-aware (comparing options) | Any | AIDA, with a "why us over [main alternative]" Interest step | They know the category; difference and desire do the work |
| Product-aware | Real, sourced results | 4Ps | The Proof step needs real evidence; without it this framework produces invented claims |
| Product-aware | Thin or none | AIDA with an offer-led hero and a risk reducer that is true | Lean on the offer and the product itself, not on proof you do not have |
| Brand homepage for several audiences, sales-led | Any | StoryBrand for the narrative, PAS or AIDA inside sections | The customer is the hero; the brand is the guide |

Never pick 4Ps when the proof inventory is empty: its Proof step would be all placeholders,
and the page would make a promise it cannot back.

## 2. PAS: Problem, Agitate, Solution

- **Problem**: the situation in the buyer's words (from voice-of-customer phrases).
- **Agitate**: the cost of leaving it as is (time, money, risk, stress), stated concretely
  and honestly; no scare tactics.
- **Solution**: the product as the way out, tied point by point to the problem.

Section mapping: hero states the problem or the outcome; the block after the hero agitates;
solution and features answer it.

Illustrative example:

- Problem: "Month-end close still means copying CSVs between [number of tools] tools."
- Agitate: "Every manual match is a chance to miss a payout, and the close slips into the
  next month."
- Solution: "Acme matches every payout to every bank line and posts the journal entry for
  you."

## 3. AIDA: Attention, Interest, Desire, Action

- **Attention**: a headline that names the outcome or the difference.
- **Interest**: how it works and why it is different from [main alternative].
- **Desire**: what changes for the buyer, shown with real proof or the product itself.
- **Action**: one clear next step with a true risk reducer.

Section mapping: hero (Attention), solution, features and how it works (Interest),
testimonials and demo (Desire), final CTA (Action).

## 4. BAB: Before, After, Bridge

- **Before**: today, in the buyer's words.
- **After**: the same day once the problem is gone, concrete and believable.
- **Bridge**: the product and the few steps that get them there.

Section mapping: problem (Before), solution (After), how it works and features (Bridge),
testimonials (real before-and-after stories, when the user has them).

## 5. 4Ps: Promise, Picture, Proof, Push

- **Promise**: a specific outcome the user can substantiate.
- **Picture**: what life looks like with the promise kept.
- **Proof**: sourced results, named testimonials, case studies (only real ones).
- **Push**: the offer and a true risk reducer.

Illustrative example: "Promise: [METRIC: close time reduced, from customer data]. Proof:
[CASE STUDY: named customer, before and after]." If those placeholders cannot be filled
before launch, switch frameworks.

## 6. StoryBrand

From Donald Miller, *Building a StoryBrand* (2017). The customer is the hero, the brand is
the guide.

- Character: who the buyer is and what they want.
- Problem: external (the task), internal (how it feels), philosophical (why it is wrong).
- Guide: empathy plus authority (authority = real proof only).
- Plan: three simple steps.
- Call to action: direct ("Book a demo") plus transitional ("Watch the product tour" only if
  it exists).
- Success and failure: what changes, and what it costs to do nothing (honest, no fear
  tactics).

Use it for brand homepages and sales-led homepages; it is too long for most paid LPs.

## 7. Voice of customer: write in the buyer's words

Copy built from customer language beats copy built from the team's vocabulary. This is the
step that separates a consultant's draft from generic AI copy.

Sources, best first:

1. What the user pastes or points to: interview notes, sales-call notes, support tickets,
   survey answers, churn reasons, their own review exports. Remove names, emails and company
   names before quoting.
2. Reports already in `growth-reports/` from review-sentiment (themes and quotes from
   reviews) or reddit-opportunity-finder (threads where people describe the problem).
3. Public sources found with web search: reviews of the main alternative on G2, Capterra or
   app stores, and community threads about the problem. At most 5 sources per run. Quote
   short phrases (under 15 words), never usernames, always with the URL and date.

Build a phrase bank before writing:

| Bucket | What to collect | Used in |
|---|---|---|
| Pains | How they describe the problem and its cost | Problem, hero, agitate |
| Desired outcomes | What "done" looks like to them | Hero, solution, after |
| Triggers | What made them look for a tool now | Hero variants, message match |
| Objections | Why they hesitated or chose something else | FAQ, security, comparison |
| Category words | What they call the product type | Eyebrow, subheadline, SEO title |

Every phrase used in copy gets an evidence ID with its source. If no voice-of-customer data
exists, say so under "Not measured" and recommend 5 customer conversations to validate the
wording before launch.

## 8. Headlines, subheadlines and CTAs

Headlines:

- Say the outcome for the ICP, or the problem in their words. The subheadline says what the
  product is, for whom, and how it differs from the main alternative.
- The hero should pass a five-second test: a stranger can say what it is, who it is for and
  what to do next.
- Write 3 to 5 variants with different angles (outcome, problem, difference, audience,
  proof-led only with real proof) and say which awareness stage each fits.
- Clever is fine only when it is also clear.

CTAs:

- Start with a verb and name what they get ("Start free", "Get a demo", "Join the
  waitlist"); avoid "Submit" and "Learn more" as the primary CTA.
- One primary CTA text across the page. A secondary CTA serves a less ready visitor
  ("See how it works"), not a different goal.
- Risk reducers next to the CTA must be true today (real trial length, card requirement,
  cancellation terms).

Microcopy that often matters: what happens after the click, form field hints, privacy note
next to email fields, and the plan or trial terms.

## 9. Plain-language rules

- Short sentences, concrete nouns, active verbs. Prefer the buyer's words to the team's.
- Replace adjectives with specifics the user can source; otherwise drop the adjective.
- "You" and "your" more than "we" and "our".
- Reading level matters on SaaS pages: run `blueprint_tools.py benchmarks` and cite the
  `value_note` of the Unbounce SaaS row when you mention it, with source and year.
- Write in the page's language from the start; do not translate English copy line by line.
  Keep product and category terms the market actually uses.

## 10. Notes for 2026

- AI features: "AI-powered" is not a value proposition. Say what the AI does for the user and
  what they no longer have to do.
- Answer-ready copy: a plain one-sentence definition ("Acme is [category] for [ICP] that
  [outcome]") near the top helps people and AI assistants describe the product correctly.
  For AI-search readiness of the whole site, use geo-seo-auditor.
- Interactive demos and short product clips can replace long feature sections; only
  reference ones that exist.
- Accessibility is part of copy: descriptive link text, real button labels and alt text for
  product images.
