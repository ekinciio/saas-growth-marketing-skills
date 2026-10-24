# Proof Rules, Placeholders and the Proof Checklist

Last verified: 2026-10

Read this before you write any copy that mentions customers, numbers, ratings, quotes,
guarantees, trial terms or urgency, and before you write the "Proof to collect before
launch" checklist. This is product guidance, not legal advice; when a claim is borderline,
tell the user to check it with counsel.

## Contents

1. The rule
2. Placeholder syntax
3. The proof inventory question
4. What counts as usable proof
5. Claims that need extra care
6. Legal background (sources)
7. Proof to collect before launch: template

---

## 1. The rule

Use only proof the user supplied in this conversation, proof published on the user's own
live site (cite the URL and the date you saw it, and ask the user to confirm it is current),
or public third-party proof with a link and date (a review profile, a press article). For
everything else write a bracketed placeholder. Never invent, estimate, round up or "make
illustrative" a customer name, logo, quote, metric, rating, award, user count, case study,
guarantee, deadline or scarcity limit. This holds for every command, every draft and the
HTML prototype.

Before you hand over any draft, run `blueprint_tools.py lint` on it. Every claim and quote it
lists must either trace to a proof item in the evidence table or become a placeholder.

## 2. Placeholder syntax

Upper-case kind, a colon, and what is needed. Placeholders must be visible in the draft
(the HTML prototype styles them as red dashed boxes) so nobody ships them by accident.

| Need | Placeholder |
|---|---|
| Customer logos | `[LOGO: 4-6 customer logos, written permission]` |
| A named quote | `[TESTIMONIAL: real quote with a specific result; name, role, company]` |
| A metric | `[METRIC: % of time saved; needs source and date]` |
| Customer count | `[METRIC: active teams; from the billing or product database]` |
| Rating | `[RATING: platform, score, number of reviews, date]` |
| Case study | `[CASE STUDY: customer, before and after, link]` |
| Award or press | `[PRESS: outlet and article link]` |
| Compliance | `[COMPLIANCE: report or certificate name, date]` |
| Screenshot or video | `[SCREENSHOT: view that shows the headline's outcome]` |
| Price | `[PRICE: from the current price list]` |
| A fact you could not confirm | `[CONFIRM: setup time; ask the product team]` |

Keep placeholders specific: the note says what would make the slot true, so the checklist
can turn it into a task.

## 3. The proof inventory question

Ask it during intake unless the user already listed their proof. One multiple-choice
question, "Not sure" allowed:

> Which proof can the page use today? (choose all that apply) Customer logos you have
> permission to show; named customer quotes; metrics you can source (from your product,
> billing or a customer); review-site ratings (G2, Capterra, App Store); case studies;
> security or compliance reports; press or awards; none yet.

If they choose "none yet" or skip, every proof slot becomes a placeholder and the
checklist (section 7) becomes the main deliverable next to the copy.

## 4. What counts as usable proof

| Proof | Usable when | Cite as |
|---|---|---|
| Customer logo | The user confirms permission (contract clause or written OK) | "user confirmed permission, YYYY-MM-DD" |
| Named quote | Real words from a real customer, used with permission, not edited to change meaning | The source (email, interview, review URL) and date |
| Review-site quote or rating | Public, linkable, with the platform, score, review count and date; not cherry-picked to mislead | URL and date |
| Metric about customers | Measured (product analytics, billing, a customer's own report) with a date and a definition | Source and date; the definition in the footnote |
| Metric about the product | Reproducible (benchmark method stated) | Method and date |
| Customer count | From the user's own database, current, with a definition ("active teams in the last 30 days") | Source and date |
| Security or compliance | The report or certificate exists and is current | Report name and date |
| Proof on the user's own live site | Already published by them; still confirm it is current | URL and date seen |

Material connections: if a quoted person got something (free plan, payment, discount,
equity) or works for the company, the quote needs a clear disclosure next to it.

## 5. Claims that need extra care

- **Performance claims** ("cut close from 11 days to 3", "set up in 5 minutes", "3x faster"):
  need substantiation for typical users, not the best case. Without it, rewrite as a
  capability ("reconciles payouts automatically") or use a placeholder.
- **Superlatives and rankings** ("#1", "the leading", "award-winning"): only with a named,
  current source.
- **Urgency and scarcity** ("only 3 spots left", countdown timers, "price goes up Friday"):
  only when real and enforced. Fake urgency is a dark pattern the FTC has called out.
- **Trial, renewal and cancellation terms** next to a CTA ("free for 14 days", "cancel
  anytime", "no credit card required"): must match the real product terms. In the US,
  ROSCA requires clear disclosure of material terms before billing, and several states
  (for example California, whose automatic renewal law was updated in July 2025) add
  rules.
- **Guarantees** ("money back in 30 days"): only if the policy exists and is linked.
- **Comparisons with named competitors**: sourced, dated and fair; comparison pages belong
  to competitor-intel.
- **AI-generated content**: never generate a testimonial, a reviewer, a headshot or a
  customer logo. A model-written quote attributed to a person is a fake testimonial.

## 6. Legal background (sources)

| Rule | What it says for landing pages | Source | Checked |
|---|---|---|---|
| FTC Trade Regulation Rule on the Use of Consumer Reviews and Testimonials, 16 CFR Part 465 (in force since October 2024) | Bans fake reviews and testimonials (including AI-generated ones and ones from people who did not use the product), undisclosed insider reviews, company-controlled "independent" review sites, review suppression and fake social-media indicators; civil penalties per violation | Final rule: https://www.ftc.gov/system/files/ftc_gov/pdf/r311003consumerreviewstestimonialsfinalrulefrn.pdf | 2026-10 |
| FTC warning letters under Part 465 | On 2025-12-22 the FTC sent warning letters to 10 companies, its first public use of the rule | https://www.arnoldporter.com/en/perspectives/blogs/consumer-products-and-retail-navigator/2026/01/ftc-warning-letters-over-consumer-review-rule (secondary) | 2026-10 |
| FTC Guides Concerning the Use of Endorsements and Testimonials in Advertising, 16 CFR Part 255 (revised 2023) | Endorsements must reflect honest opinions of real users; material connections must be disclosed clearly; results must be typical or the typical result stated | https://www.ftc.gov/legal-library/browse/federal-register-notices/16-cfr-part-255-guides-concerning-use-endorsements-testimonials-advertising | 2026-10 |
| UK Digital Markets, Competition and Consumers Act 2024 | Fake reviews and concealed incentivised reviews are banned from 2025-04-06; the CMA can fine up to 10% of global turnover | https://cms.law/en/gbr/legal-updates/the-dmcc-act-consumer-elements-come-into-force-from-6-april-2025 (secondary) | 2026-10 |
| EU Unfair Commercial Practices Directive, Annex I points 23b and 23c (added by Directive (EU) 2019/2161, applied from 2022-05-28) | Banned: claiming reviews come from real users without reasonable checks, and submitting or commissioning fake reviews or endorsements | https://eur-lex.europa.eu/eli/dir/2019/2161/oj | 2026-10 |

When a fact in this table is more than 6 months older than the run date, re-check it with
WebSearch before stating it.

## 7. Proof to collect before launch: template

End every blueprint and every copy deliverable with this checklist, built from the
placeholders actually used (count them with `lint`). Order by impact on the page's main
claim.

```markdown
### Proof to collect before launch
- [ ] [LOGO] Ask 4-6 customers for written permission to show their logo (owner: [name], due: [date])
- [ ] [TESTIMONIAL] Interview 3 customers from the ICP; ask for the result in their words and permission to quote name, role and company
- [ ] [METRIC] Pull "[metric]" from [product analytics / billing] with its definition and date
- [ ] [RATING] Link the review profile with score, review count and date, or remove the slot
- [ ] [CONFIRM] Check "[claim]" with the product team; rewrite as a capability if it cannot be sourced
- [ ] Remove every remaining [PLACEHOLDER] or its section before publishing
```
