# CRO audit checklist

Last verified: 2026-10.

What to look at before scoring, per dimension, and where each item comes from: an extractor
fact (`page.*` in the JSON of `cro_auditor.py`), a screenshot, or the user. Each item is a
check, not a point: a page can tick every box and still score low if the content is weak.
The anchors that turn these observations into scores are in `scoring-rubric.md`.

## Contents

1. Before you start
2. Value proposition and first screen
3. Primary CTA and next step
4. Social proof
5. Objections and risk reversal
6. Copy
7. Trust and security
8. Form
9. Visual hierarchy and mobile
10. Speed
11. Urgency and offer timing
12. Measurement readiness ("before you test")
13. Quick wins that are safe to ship without a test
14. Sources

---

## 1. Before you start

- [ ] Page type and primary conversion are known (homepage, paid landing page, demo page,
      pricing page; trial, demo, purchase, waitlist).
- [ ] For paid or email traffic: you have the ad or email text, so you can check message
      match.
- [ ] The extractor ran on the page you meant (`fetch.final_url`; a redirect to a locale or a
      login page changes everything).
- [ ] `page.notes` read: thin page, JS-rendered forms, non-English page, missing h1.
- [ ] Desktop (1440 x 900) and mobile-width (390 x 844) first-viewport screenshots taken, or
      the visual items below marked "not measured".

## 2. Value proposition and first screen

- [ ] Headline (`page.hero.headline`) says what the product does and for whom, or the
      outcome the buyer gets, without needing the subheadline.
- [ ] Subheadline (`hero.subheadline`) adds how it works or why it beats the current way.
- [ ] The visual (`hero.media`, screenshot) shows the product doing the job; an interactive
      demo or a short product video in the hero is a plus when it loads fast.
- [ ] One message: no rotating headlines or several competing promises above the fold.
- [ ] Message match: the promise and wording of the ad, email or search query appear in the
      headline.
- [ ] The first screen works without the brand: a stranger from the ICP understands it.
- NN/g's eye-tracking study found that people spent about 57% of page-viewing time above the
  fold and 74% in the first two screenfuls (desktop, 2018). The first screen deserves the
  most care, but the page does not have to fit into it.

## 3. Primary CTA and next step

- [ ] One primary action (`page.ctas.primary_guess`), visible in the first screen on desktop
      and on mobile (screenshot).
- [ ] CTA text names the value or the next step ("Start my free trial", "See a 2-minute
      demo"), not "Submit" or "Learn more".
- [ ] Risk-reducing microcopy right under or next to it (`hero.risk_reducers`): trial
      length, "no credit card required", "cancel any time", or what happens in the demo.
- [ ] Secondary action (demo next to trial, or the reverse) is visibly secondary
      (`ctas.hero_conversion_intents` lists both).
- [ ] The primary CTA repeats after proof and pricing sections
      (`ctas.primary_repeats_in_body`).
- [ ] Buttons are real links or buttons (`ctas.non_semantic_buttons` is empty), so keyboard
      and assistive-technology users can reach them.
- [ ] Paid landing pages: navigation exits (`page.navigation.nav_exits`) removed or reduced.
- [ ] Tap targets on mobile are at least 24 x 24 CSS px or well spaced (WCAG 2.2 success
      criterion 2.5.8, level AA).

## 4. Social proof

- [ ] Logos (`page.proof.logo_walls`) come from the buyer's world (same size, industry or
      region), with a caption that says who they are.
- [ ] Quotes (`proof.quotes`) carry a real name, role and company, and state an outcome.
- [ ] Ratings (`proof.ratings`) name the platform and ideally the review count; badges link to
      the listing.
- [ ] Numbers (`proof.numeric_claims`) have a source or a date; round, unsourced numbers are
      flagged, not counted.
- [ ] Case studies are linked (`proof.case_study_links`) for buyers who need depth.
- [ ] Proof sits near the decision points: under the hero, next to pricing and the form.

## 5. Objections and risk reversal

- [ ] The buyer's top questions are answered (`page.objections.faq`): price, setup effort,
      migration, integrations, security, data ownership, cancellation, support.
- [ ] Pricing is on the page or one click away (`objections.pricing`); sales-led pages say
      what the demo covers and how fast someone replies.
- [ ] Risk reversal is explicit (`objections.risk_reducers`,
      `trust.guarantee_sentences`): trial terms, refund or guarantee, free migration.
- [ ] Evaluators get comparison help (`objections.comparison_links`): "X vs us" or
      alternatives pages, a comparison table.
- [ ] A "how it works" section shows the first steps after signing up.

## 6. Copy

- [ ] Headings alone tell the story in order (`page.outline[].heading`).
- [ ] Customer language: words the buyer uses for the problem (from reviews, sales calls,
      support tickets), not internal product names.
- [ ] Each feature is tied to a result ("so you can ...").
- [ ] Short sentences, few buzzwords ("seamless", "all-in-one", "next-generation").
- [ ] Unbounce's 2024 SaaS benchmark saw much higher conversion for pages written at a 5th-7th
      grade reading level than for professional-level copy (correlation, see
      `landing_page_conversion.unbounce2024.saas` in the benchmark file).

## 7. Trust and security

- [ ] Compliance evidence fits the buyer (`page.trust.compliance` and its zones): SOC 2 or
      ISO 27001 for mid-market and enterprise, HIPAA for health data, GDPR for EU personal
      data.
- [ ] A security page or trust center is linked (`trust.legal_links.security`), ideally near
      the form or pricing, not only in the footer.
- [ ] Privacy policy and terms are linked (`trust.legal_links`).
- [ ] Badges match certifications the company actually cites (no decorative "secure" seals).
- [ ] The company is identifiable (name, address or legal entity in the footer).

## 8. Form

- [ ] Primary form (`page.forms.primary`): number of visible and required fields; every field
      earns its place for this step.
- [ ] Labels are visible (`fields[].label_source` is `label`, not `placeholder`).
- [ ] Submit text repeats the value ("Get my demo"), not "Submit".
- [ ] Forms rendered by JavaScript (`forms.embedded_by_javascript`: HubSpot, Marketo, Chili
      Piper, Typeform, Calendly) are checked in the rendered page or screenshot.
- [ ] Trials ask for as little as possible (email or SSO); demo forms ask only what routing
      needs.
- [ ] A privacy line near the button says how the data is used.

## 9. Visual hierarchy and mobile

- [ ] Desktop screenshot: headline, subheadline and CTA read in that order; the CTA has the
      strongest contrast.
- [ ] Mobile screenshot (390 px): no cut-off text, no horizontal scroll, the CTA visible in
      the first screen or reachable without hunting.
- [ ] Cookie or consent banner does not cover the hero or the CTA.
- [ ] Sections alternate clearly; no wall of text; images support the copy.
- [ ] One h1 (`page.accessibility_hints.h1_count`); images have alt text
      (`images_missing_alt`).

## 10. Speed

- [ ] Field data from PageSpeed Insights (`speed.psi`): Core Web Vitals pass or fail at the
      75th percentile on mobile, thresholds in `references/_shared/volatile-facts.md`
      section 7. Lab numbers explain causes; they never decide pass or fail.
- [ ] Diagnostics (`page.speed_diagnostics`): render-blocking scripts in the head, a
      lazy-loaded hero image (`hero_first_image_lazy` true delays LCP), image formats (AVIF or
      WebP versus large PNG and JPG), third-party script count.
- [ ] No field data: say "not measured" and give the way to get it (a free PageSpeed API key in
      `PAGESPEED_API_KEY`, or the user's own RUM data).

## 11. Urgency and offer timing

- [ ] Is there a real, time-bound offer? If not, urgency is `na`: the absence is correct.
- [ ] Deadlines are dated and true; countdowns do not reset (check two visits or two
      screenshots a few minutes apart).
- [ ] Scarcity claims ("only N spots") are real and explainable; software is rarely scarce.
- [ ] No pressure copy without an offer ("Act now!").

## 12. Measurement readiness ("before you test")

- [ ] Analytics present (`page.measurement.analytics`, or a tag manager that may load it).
- [ ] Session replay or heatmaps (`measurement.session_replay`) for qualitative checks.
- [ ] Experimentation tool (`measurement.experimentation`) if A/B tests are planned;
      Google Optimize ended in 2023, so its tags mean nothing runs.
- [ ] Consent manager (`measurement.consent`): in consent-first regions, analytics and test
      data cover only visitors who accept, which shrinks sample sizes.
- [ ] The conversion event is tracked end to end (CTA click, form submit, account created),
      and the user knows the baseline rate. If not, the first bet is often "measure it".

## 13. Quick wins that are safe to ship without a test

Low-risk fixes that remove friction or confusion; ship them and watch the conversion rate
before and after:

1. Replace "Submit" or "Learn more" on the primary action with a specific verb and value.
2. Put the risk reducer the business already offers (trial length, no card, cancel any time)
   under the CTA.
3. Move existing, attributed proof (logos, a named quote) next to the first CTA.
4. Turn a button-looking `div` into a real `button` or `a`.
5. Remove the `loading="lazy"` attribute from the hero image.
6. Add visible labels to form fields that only have placeholders.
7. Link the security page or trust center next to forms and pricing.

## 14. Sources

- NN/g, "Scrolling and Attention" (2018 eye-tracking update):
  https://www.nngroup.com/articles/scrolling-and-attention/
- W3C WCAG 2.2, success criterion 2.5.8 Target Size (Minimum), level AA:
  https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html
- Core Web Vitals thresholds and field data: `references/_shared/volatile-facts.md`
  sections 5 and 7 (web.dev and PageSpeed Insights documentation, verified 2026-10-24).
- Unbounce Conversion Benchmark Report 2024 (SaaS):
  https://unbounce.com/conversion-benchmark-report/saas-conversion-rate/
- Google Optimize sunset (September 2023): https://support.google.com/analytics/answer/12979939
