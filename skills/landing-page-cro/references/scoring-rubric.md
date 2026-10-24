# CRO scoring rubric (cro-rubric-v2)

Rubric version: `cro-rubric-v2`. Last verified: 2026-10.

The model scores each dimension 0-10 against the written anchors below, quoting evidence
for every score. `cro_auditor.py --score` applies the weights, drops `na` and
`not_measured` dimensions, renormalizes and returns the total. Never add scores up by hand.

## Contents

1. Rules that apply to every dimension
2. Page type and sales motion
3. The ten dimensions (weights, evidence, anchors, traps)
4. Scores file format
5. Bands and how to talk about the total
6. Sources

---

## 1. Rules that apply to every dimension

- **Evidence first.** Before writing a score, write the evidence IDs it rests on: a quote
  from the page (copied from the extractor JSON, for example `page.hero.headline`) or a
  screenshot observation ("desktop screenshot, first viewport"). A score without evidence is
  not allowed.
- **Judge meaning, not keywords.** The extractor already removed hidden text (display:none,
  the hidden attribute, aria-hidden, screen-reader-only text). A page does not earn points for
  containing words such as "secure" or "customers"; it earns them for saying something
  specific and believable to its buyer.
- **Score for a first-time visitor from the ICP**, not for someone who already knows the
  brand. A famous brand can afford an abstract headline; say so as context, but score what
  the page communicates on its own.
- **Use the anchors.** Pick the band whose description fits best, then the number inside the
  band. When two bands fit equally, take the lower one and say what would lift it.
- **`na`** means the dimension does not apply to this page (no form because the CTA links to a
  signup page; no time-bound offer on a B2B subscription page). **`not_measured`** means it
  applies but could not be observed (no screenshots, no PageSpeed field data, a form that
  JavaScript renders and you could not render). Neither is ever scored 0.
- **Confidence** per dimension:
  - high: observed directly (the text is in the extracted facts, or the visual is in a
    screenshot you looked at);
  - medium: observed but incomplete (static HTML of a page that renders more with
    JavaScript; a visual dimension judged from the outline because no screenshot was taken);
  - low: inferred (from indirect signals, or a dimension judged mostly from assumptions).
- **Never invent.** No numbers, testimonials, logos or ratings that are not on the page. Missing
  proof is a finding, not something to fill in.
- **Compliance overrides persuasion.** Fake urgency, unverifiable or fabricated reviews and
  misleading badges are scored low and named as a compliance risk in the Diagnosis: the US
  FTC rule on reviews and testimonials (16 CFR Part 465, in force since 2024-10-21), the EU
  Unfair Commercial Practices Directive (Annex I point 7, false "very limited time" claims)
  and the UK DMCC Act 2024 (Schedule 20, paragraph 7 on false limited-time claims and
  paragraph 13 on fake reviews) all reach these practices.

## 2. Page type and sales motion

Decide these first (intake step in SKILL.md). They change what "good" looks like inside each
anchor, not the weights.

| Page type | What matters most | Defaults |
|---|---|---|
| Homepage (mixed traffic) | Value proposition for the main segment, clear routing for the others, proof | Nav links are normal; urgency `na` |
| Paid or campaign landing page | Message match with the ad or email, one CTA, no exits | Every nav exit (`page.navigation.nav_exits`) counts against the CTA dimension |
| Demo-request page (sales-led) | What happens after the form, form friction, proof from similar companies | Prices on the page are not required; a price range or "from" price is a plus |
| Pricing page | Plan clarity, the recommended plan, what is included, billing FAQ, risk reversal, enterprise path | Proof near the plan cards; urgency `na` unless a real offer is running |
| Product or feature page | One job explained with the product shown doing it, path to trial or demo | Same anchors, judged for that feature's buyer |

Sales motion (`gtm_motion` in growth-context.md): `plg` pages should make the free start the
primary action; `sales-led` pages should make the meeting easy and say what it gives the
visitor; `hybrid` pages need one primary action and a clearly secondary second path.

## 3. The ten dimensions

Weights are relative impact on conversion. They are fixed so totals stay comparable across
runs; `cro_auditor.py` renormalizes them over the dimensions that were scored.

### 3.1 Value proposition and first screen (`value_prop`, weight 20)

Evidence: `page.hero.headline`, `headline_source`, `subheadline`, `hero.text`, `hero.media`,
the desktop and 390 px first-viewport screenshots, and for paid traffic the ad or email copy.

| Score | Anchor |
|---|---|
| 9-10 | The first screen says what the product does, for whom, and the outcome or change it brings, in the buyer's words; the subheadline adds how it works or why it beats the current way; the visual shows the product doing the job; for paid traffic the headline repeats the promise of the ad. |
| 7-8 | Product, audience and outcome are clear, but one piece is weak: the mechanism is vague, there is no differentiation from the obvious alternative, or the visual is decorative. |
| 5-6 | The category is clear ("CRM for small teams") but the outcome is missing, or the outcome is clear but the audience is not; or the visitor must scroll to understand. |
| 3-4 | A clever or abstract line that needs the subheadline or more to know what the product is, or company-centric copy ("We are the leading platform"). |
| 0-2 | No identifiable headline, or the first screen does not say what the product does. |

Traps: a long headline is not a clear one; an h1 that is only the brand name counts as
missing; `headline_source` other than `h1` is an accessibility and SEO note, not a
conversion score change.

### 3.2 Primary CTA and next step (`cta`, weight 15)

Evidence: `page.ctas.primary_guess`, `hero.ctas`, `ctas.hero_conversion_intents`,
`ctas.primary_repeats_in_body`, `ctas.non_semantic_buttons`, `hero.risk_reducers`,
`page.navigation.nav_exits` (paid pages), screenshots for prominence and contrast.

| Score | Anchor |
|---|---|
| 9-10 | One primary action, visible in the first screen on desktop and at 390 px, with text that names the value or the next step ("Start my free trial", "Book a 20-minute demo"); risk-reducing microcopy next to it; repeated after the main proof and pricing sections; any second action is visibly secondary; the action fits the motion. |
| 7-8 | A clear primary CTA, but generic text ("Get started"), no microcopy, or no repeat further down. |
| 5-6 | Two equal-weight actions compete in the hero, or the main action is vague ("Learn more", "Submit"), or the primary action lives only in the navigation bar. On a paid landing page, several nav exits also land here. |
| 3-4 | No conversion action in the first screen, or the main CTA is a non-semantic element (`non_semantic_buttons`) that keyboard users cannot reach. |
| 0-2 | No way to convert on the page. |

Traps: `primary_guess` is a guess from the static HTML; confirm it in the screenshot. A CTA
count is not a score: three repeats of a weak CTA are still weak.

### 3.3 Social proof specificity (`proof`, weight 15)

Evidence: `page.proof.logo_walls` (names, signals), `proof.quotes` (attribution),
`proof.ratings` (mentions with platform, badges, JSON-LD aggregate), `proof.numeric_claims`,
`proof.case_study_links`, block positions in `page.outline`.

| Score | Anchor |
|---|---|
| 9-10 | Proof the ICP recognizes and believes: named quotes with role and company that state a concrete outcome, logos from the buyer's own world, a third-party rating with platform and review count, linked case studies; placed in or near the first screen and next to CTAs. |
| 7-8 | Logos and attributed quotes, but outcomes are vague ("great tool") or the proof sits far from the decision points. |
| 5-6 | Logos only, or quotes without names, or round numbers with no source ("thousands of teams"). |
| 3-4 | One weak element (an unnamed quote, a single badge). |
| 0-2 | No social proof. |

Traps: logo walls with `unnamed` items could not be named from the HTML; say so instead of
guessing brands. A numeric claim is proof only if the page says where it comes from; an
unsourced claim is a credibility and compliance risk, not a plus.

### 3.4 Objection handling and risk reversal (`objections`, weight 10)

Evidence: `page.objections.faq`, `objections.pricing`, `objections.comparison_links`,
`objections.risk_reducers`, `page.trust.guarantee_sentences`, outline headings (how it
works, integrations, migration, security, onboarding).

| Score | Anchor |
|---|---|
| 9-10 | The top objections for this buyer are answered on the page, close to the CTA: price (or a clear path to it), switching and setup effort, integrations, security, time to value, team adoption; risk reversal is explicit (trial terms, cancel any time, guarantee, free migration); evaluators get comparison help. |
| 7-8 | Most objections answered; one important one (often price or migration) is missing or buried. |
| 5-6 | A short FAQ or a pricing link, but the main fears of this ICP are not addressed. |
| 3-4 | Almost nothing; the visitor must contact sales to learn basics. |
| 0-2 | No objection handling at all. |

Sales-led enterprise pages are not penalized for hiding prices if they say what the demo
covers and how fast someone replies.

### 3.5 Copy clarity and customer language (`copy`, weight 10)

Evidence: `hero.text`, `page.outline[].heading` and `text`, quotes (the customer's own words
versus the page's words).

| Score | Anchor |
|---|---|
| 9-10 | Plain, specific language the buyer uses for the problem; short sentences; every feature tied to a result; one consistent name for each concept; headings alone tell the story. |
| 7-8 | Mostly clear and benefit-led, with some jargon or feature lists without a "so you can". |
| 5-6 | A mix: buzzwords ("seamless", "AI-powered", "all-in-one"), vague claims, or long paragraphs. |
| 3-4 | Feature-heavy, internal or company-centric language; the visitor has to translate. |
| 0-2 | Jargon throughout, contradictory or unreadable. |

Context: Unbounce's 2024 SaaS benchmark found pages written at a 5th-7th grade reading level
converted at 12.9% versus 2.1% for professional-level copy
(`landing_page_conversion.unbounce2024.saas` value note in `saas-benchmarks.json`). It is a
correlation across pages, not a promised lift; cite it as such.

### 3.6 Trust and security signals (`trust`, weight 10)

Evidence: `page.trust.compliance` (with zones), `trust.badge_images`, `trust.legal_links`,
`page.measurement.consent`, company identity in the footer, screenshots for badge placement.

| Score | Anchor |
|---|---|
| 9-10 | Security and compliance evidence that fits the buyer (SOC 2 or ISO 27001 for mid-market and enterprise, HIPAA for health data, GDPR for EU data) linked to a security page or trust center, shown near forms or the CTA; privacy and terms present; the company is identifiable. |
| 7-8 | The right signals exist but sit only in the footer or on a separate page with no link near the decision. |
| 5-6 | Only legal links; nothing on security although the buyer handles sensitive data. |
| 3-4 | Missing basics (no privacy policy link) or vague claims ("bank-level security") with nothing behind them. |
| 0-2 | Signals that look misleading (badges for certifications the company does not cite elsewhere) or none at all. |

Self-serve tools for individuals need less: privacy, terms and a real company identity can
reach 7-8.

### 3.7 Form friction (`form`, weight 10)

Evidence: `page.forms.primary` (visible_fields, required_fields, field labels and
label_source, submit_text), `forms.embedded_by_javascript`, screenshots.

`na` when the page has no conversion form (the CTA links to a signup page; that flow belongs to
web-app-growth-engine) or only a newsletter form. `not_measured` when the primary form is
rendered by JavaScript (`embedded_by_javascript`) and you could not render it.

| Score | Anchor |
|---|---|
| 9-10 | Only the fields the next step needs (email or SSO for a trial; a short qualification set for a demo, each field earning its place); visible labels (not placeholder-only); submit text that repeats the value; a privacy line near the button. |
| 7-8 | One or two fields that could wait until later, or labels that rely on placeholders. |
| 5-6 | Several optional-looking fields marked required, or a phone number required for a trial. |
| 3-4 | Long forms (8 or more questions for a trial or newsletter-level offer), unclear errors or a CAPTCHA up front. |
| 0-2 | The form cannot be completed, or asks for payment or a password before showing any value. |

Context: Zuko's form benchmarks give average view-to-completion rates of 46.6% for
registration forms and 18.0% for enquiry forms (`form_view_to_completion.zuko.*`). Use them as
context for the user's own form analytics, never as a predicted effect of removing a field.

### 3.8 Visual hierarchy and scannability (`hierarchy`, weight 5)

Evidence: desktop and 390 px screenshots; `page.outline` (order and length of sections);
`page.headings`.

| Score | Anchor |
|---|---|
| 9-10 | The eye goes headline, then subheadline, then CTA; sections alternate clearly; the page reads from headings alone; on mobile nothing is cut off and the CTA stays in the first screen. |
| 7-8 | Clear overall, with one crowded section or a weak contrast between primary and secondary actions. |
| 5-6 | Several competing focal points, walls of text, or a cookie banner covering the hero. |
| 3-4 | Hard to scan; on mobile the CTA falls far below the first screen or text overflows. |
| 0-2 | No visible structure. |

Without screenshots: score from the outline only, confidence low, and never above 7; or
mark `not_measured` if the outline is thin.

### 3.9 Speed and mobile experience (`speed`, weight 5)

Evidence: `speed.psi.<strategy>.cwv_assessment`, `lcp`, `inp`, `cls` (75th percentile field
data from PageSpeed Insights), or field data the user supplies. Thresholds come from
`references/_shared/volatile-facts.md` section 7. `page.speed_diagnostics` and Lighthouse lab
numbers explain causes; they never decide the score.

`not_measured` when there is no field data (no key, rate limited, or `no_field_data`).

| Score | Anchor |
|---|---|
| 9-10 | Mobile field data passes Core Web Vitals (LCP, INP and CLS all good) at URL level. |
| 7-8 | Passes at origin level only, or passes with a diagnostic risk (a lazy-loaded hero image, many render-blocking scripts). |
| 5-6 | One metric needs improvement. |
| 3-4 | One metric is poor. |
| 0-2 | Two or more metrics are poor. |

### 3.10 Offer timing and urgency (`urgency`, weight 5)

Evidence: `page.urgency.candidates` (phrase and context), `urgency.countdown_elements`,
screenshots on two visits when a timer is present.

`na` by default for B2B and subscription pages with no time-bound offer: the absence of
urgency is correct, not a gap. Score it only when the page presents a deadline, a cohort, an
event or limited capacity.

| Score | Anchor |
|---|---|
| 9-10 | A real, dated deadline or capacity limit with a stated reason (launch pricing until a date, an event, a cohort start), consistent across visits. |
| 7-8 | Real but vague timing ("launch pricing for a limited time" with no date). |
| 5-6 | Generic pressure ("Act now", "Don't miss out") without an actual offer. |
| 0-4 | Fake or unverifiable scarcity: a countdown that resets, "only 3 spots left" for software, a deadline that never passes. Name it as a compliance risk. |

## 4. Scores file format

Write the file with the Write tool (for example
`growth-reports/.cache/<date>-<slug>-scores.json`) and pass its path to `--score`:

```json
{
  "rubric_version": "cro-rubric-v2",
  "page_type": "homepage",
  "dimensions": {
    "value_prop": {"score": 6, "confidence": "high", "evidence": ["E1", "E2"],
                   "justification": "Category clear, outcome missing for the ICP"},
    "cta": {"score": 7, "confidence": "high", "evidence": ["E3"], "justification": "..."},
    "form": {"status": "na", "reason": "No form; the CTA links to /signup"},
    "speed": {"status": "not_measured", "reason": "No PageSpeed key; no field data"}
  }
}
```

Every dimension id must be one of `value_prop`, `cta`, `proof`, `objections`, `copy`, `trust`,
`form`, `hierarchy`, `speed`, `urgency`. A missing id is treated as `not_measured`.
Half points (6.5) are allowed. The script returns `scoring.value` (shown only when at least
60% of the applicable weight was scored), `scoring.confidence`, `scoring.header_line`,
per-dimension `points` and `points_lost`, and `biggest_gaps` (the three dimensions that
cost the most points).

## 5. Bands and how to talk about the total

| Total | Band |
|---|---|
| 90-100 | Excellent |
| 70-89 | Good |
| 50-69 | Fair |
| 30-49 | Poor |
| 0-29 | Critical |

- The total is a rubric score of what the page shows, not a conversion rate and not a
  percentile. Never write "better than most SaaS pages" or "top 20%".
- Model-assigned scores move a few points between runs; differences under 5 points are noise.
- Lead the report with the biggest constraint and the bets, not the number.

## 6. Sources

- Report contract scoring rules: `references/_shared/report-contract.md` sections 4 and 5.
- Core Web Vitals thresholds and the field-data rule: `references/_shared/volatile-facts.md`
  sections 5 and 7 (web.dev, PageSpeed Insights v5 docs; verified 2026-10-24).
- Unbounce Conversion Benchmark Report 2024 (SaaS), reading-level finding:
  https://unbounce.com/conversion-benchmark-report/saas-conversion-rate/ (row
  `landing_page_conversion.unbounce2024.saas`).
- Zuko form benchmarks: https://zuko.io/blog/zuko-benchmarking-data-how-does-your-form-compare
  (rows `form_view_to_completion.zuko.*`).
- FTC Trade Regulation Rule on the Use of Consumer Reviews and Testimonials, 16 CFR Part 465
  (Federal Register, 2024-08-22; effective 2024-10-21):
  https://www.govinfo.gov/content/pkg/FR-2024-08-22/html/2024-18519.htm
- EU Directive 2005/29/EC, Annex I point 7: https://www.legislation.gov.uk/eudr/2005/29/annex/I
- UK Digital Markets, Competition and Consumers Act 2024, Schedule 20:
  https://www.legislation.gov.uk/ukpga/2024/13/schedule/20
