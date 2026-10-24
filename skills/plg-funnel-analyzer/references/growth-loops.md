# Growth Loops

Last verified: 2026-10

How to find, judge and measure the loops that bring a SaaS product its next users. Read this
for the `loops` command, or when the biggest constraint is acquisition and the product has a
loop it does not use. No benchmark numbers exist for loops in `saas-benchmarks.json`; measure
the user's own loop and never quote an industry viral coefficient.

## Contents

1. Loops versus the funnel
2. Loop types for SaaS
3. Choosing the loops that fit
4. Measuring a loop
5. The loops report
6. Sources

---

## 1. Loops versus the funnel

A growth loop is a closed system: an input (a new user) goes through a process (using the
product) and produces an output (an invite, a shared artifact, a public page, revenue) that is
reinvested as the next input. Brian Balfour, Casey Winters, Kevin Kwok and Andrew Chen argued
in 2018 that funnels describe where users are lost but not how the fastest-growing products
grow, because each turn of a loop feeds the next. They group loops into new-user loops,
returning-user loops, defensibility loops and efficiency loops.

Use both views: the funnel facts show where the bucket leaks; the loop view shows where the
next users come from. A loop on top of a leaking retention curve still compounds churn.

## 2. Loop types for SaaS

| Loop | How it turns | Product traits it needs | Data that shows it works | Owner of the details |
|---|---|---|---|---|
| Collaboration invite | A user invites teammates because the work is shared; teammates sign up and invite others | Multiplayer value: shared docs, projects, boards, approvals | Invites per activated account, invite acceptance, time from signup to first invite, share of signups from invites | onboarding-optimizer (where the invite sits in setup) |
| Output sharing | Users send or publish things made in the product (links, embeds, reports, forms, booking pages, AI-generated outputs); viewers see the product and sign up | Artifacts that people outside the account see, with the product visible | Shared artifacts per user, views per artifact, viewer-to-signup | saas-landing-builder (the page viewers land on) |
| Public content (SEO) | Users or the company create pages that search engines and AI assistants index (templates, galleries, community answers, public profiles); searchers sign up | Content that is useful outside the account and can be public | Indexed pages, organic signups per page, signups by landing page | geo-seo-auditor (AI-search readiness of those pages) |
| Integration and marketplace | Listings in partners' marketplaces and "works with" pages bring the partners' users | Integrations with popular platforms | Installs and signups by listing | not this toolkit |
| Developer and API | Developers build the product into their apps; each app or its docs exposes it to new developers | An API or SDK that ships inside other products | Signups by referrer domain, active API keys | not this toolkit |
| Product-qualified sales | Free usage creates product-qualified accounts; sales converts them; revenue funds more free users | Accounts that grow inside the free plan; ARPA that pays for sales time | PQL rate, PQL-to-paid, time to PQL | pricing-analyzer (limits that trigger the upgrade) |
| Paid acquisition | Revenue from new customers is reinvested in ads | CAC payback shorter than the cash the company can wait for | CAC payback by channel (subscription-metrics computes it) | subscription-metrics |
| Returning-user | Activity by others (comments, mentions, digests) brings existing users back | Notifications tied to real activity, not reminders | Share of weekly actives who return through a notification | retention-playbook (lifecycle side) |

## 3. Choosing the loops that fit

Answer from growth-context.md, the user's description and the website (homepage, pricing page,
templates or community pages):

1. Is the value multiplayer? If no, a collaboration loop is weak however good the invite UI.
2. Does the product create artifacts outsiders see? Is the product visible on them?
3. Can usage create public, indexable pages without exposing private data?
4. Do the buyers already live in a platform with a marketplace?
5. Is ARPA high enough to pay for paid acquisition or a sales touch (CAC payback)?
6. What share of signups comes from each source today? (Ask for signups by source if no export.)

For each candidate loop record: fit (which trait is present, with evidence), current state
(observed in data, observed on the site, or not observed), the break point (the step where the
loop loses the most), the metric to track, and the first experiment. Do not invent a loop the
product cannot support to fill the table.

## 4. Measuring a loop

- Viral coefficient: K = invitations (or shares) per user x the share of those that become new
  users (David Skok). K above 1 grows on its own; K below 1 still multiplies every user you
  acquire: the total users per acquired user is 1 / (1 - K) (a geometric series), so K = 0.2
  means 1.25 users per acquired user.
- Cycle time: the time from a user joining to the users they bring joining. Skok shows that a
  shorter cycle changes growth more than a higher K, so measure it and test ways to shorten it
  (prompt the invite at the moment of shared work, not at signup).
- Measure per cohort: invites per activated account in the first 7 or 14 days, acceptance
  within 7 days, and the activation rate of invited users compared with other signups (an
  invited user arrives with a teammate already inside, so check whether that shows in the
  data before relying on it).
- The `import` command can count loop events when the export has them: pass the invite event
  as `--activation-event` with the signup event as `--signup-event` to get the share of
  signups that invite within N days and the time to first invite.
- Compute these yourself only from the user's numbers. With no data, the loop's state is
  "not measured" and the first step is instrumentation.

## 5. The loops report

- Title: `# Growth loops: <product>`. Scoring mode for this command: `none` (no composite
  score), so `## Findings by area` replaces the Scorecard, with one row per candidate loop:
  Area (loop) | Status (Strong, Needs work, Critical, Not measured) | Evidence | What to do.
- Diagnosis: which loops run today and what share of signups they bring, from data or labelled
  "not measured".
- Biggest constraint: the loop with the best fit whose break point blocks it, or the leaking
  funnel stage that would waste any loop (link to the funnel audit when one exists).
- Top 3 bets: loop experiments, each with a measurable loop metric (invites per activated
  account, artifact view-to-signup, PQL rate) and a test plan from the `size` command when
  the traffic is known.
- Ready-to-ship assets: drafts only, for example invite email copy or the "made with" footer
  text, with bracketed placeholders for proof.

## 6. Sources

- Brian Balfour, Casey Winters, Kevin Kwok and Andrew Chen, "Growth Loops are the New
  Funnels", Reforge (2018-07-31): https://www.reforge.com/blog/growth-loops
- David Skok, "Lessons Learned - Viral Marketing", For Entrepreneurs (viral coefficient and
  cycle time): https://www.forentrepreneurs.com/lessons-learnt-viral-marketing/
- Andrew Chen, "The Cold Start Problem" (Harper Business, 2021), on network effects in
  collaboration products.
