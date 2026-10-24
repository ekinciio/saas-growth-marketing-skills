# HTML Prototype (the wireframe command)

Last verified: 2026-10

Read this before you build the HTML draft. The prototype is a single responsive HTML file
that shows the blueprint's sections, in order, with the real draft copy and visible proof
placeholders. A founder can open it, share it, or hand it to a designer or developer. It is
a draft for review, not a production page.

## Contents

1. Inputs
2. Build rules
3. Accessibility and mobile
4. Check before handover
5. Save, share, hand off

---

## 1. Inputs

- The blueprint from this run or an earlier report (`growth-reports/*-saas-landing-builder-*.md`).
  Without a blueprint, run the create workflow first; do not invent sections or copy.
- Brand basics if the user gives them: product name, one brand color (hex), logo text.
  Otherwise keep the skeleton's neutral palette and say so.
- The page language (the `lang` attribute and all copy).

## 2. Build rules

- Start from the skeleton file `assets/prototype-skeleton.html`. Keep only the blueprint's
  sections, in the blueprint's order, each with `data-section="<label>"` using the labels of
  the section set. Add a section by copying the closest existing pattern.
- Copy comes from the blueprint word for word. Replace every `{{...}}` token; none may
  remain.
- Proof the user did not supply stays a visible placeholder (`.ph` inline, `.ph-box` for
  logos, screenshots and video). Never draw a fake logo, invent a person, or use a stock
  headshot.
- One file, no external requests: no web fonts, CDNs, remote images, analytics, chat
  widgets or embeds. Use the system font stack and inline CSS.
- No JavaScript is needed. Use `<details>` for the FAQ. Links point to in-page anchors
  (`#get-started`); forms have no live `action` (omit it or use `#`).
- Keep the DRAFT banner, `DRAFT` in the `<title>`, and `<meta name="robots"
  content="noindex, nofollow">`.
- Navigation follows the page type: full nav for homepages, feature and pricing pages; logo
  plus one CTA for paid, demo and waitlist pages.
- Exactly one `<h1>` (the hero headline); headings do not skip levels.
- Keep it light: the skeleton plus copy is usually well under 100 KB.

## 3. Accessibility and mobile

Aim for WCAG 2.2 level AA (W3C Recommendation, https://www.w3.org/TR/WCAG22/), which is also
the usual reference for the European Accessibility Act (Directive (EU) 2019/882, applied
from 2025-06-28 to many consumer-facing digital services; B2B-only products may be out of
its scope, so state it as good practice, not as a legal finding).

- Text contrast at least 4.5:1 (1.4.3); keep the skeleton's colors or check new ones.
- Visible keyboard focus (2.4.7); the skeleton's `:focus-visible` style stays.
- Targets at least 24 by 24 CSS pixels (2.5.8); the skeleton's buttons are 48 px tall.
- Every form control has a label; every image or placeholder box has a text alternative.
- Respect `prefers-reduced-motion` if you add any motion.
- Mobile first: no horizontal scroll at 390 px width, the hero headline and primary CTA
  inside the first mobile screen, tap targets not crowded.

## 4. Check before handover

1. Run `blueprint_tools.py lint` on the file (the command is in SKILL.md).
2. Fix every item in `html.must_fix`. Fix `html.should_fix` items unless there is a reason
   (state it).
3. Every claim and quote it lists must trace to user-supplied proof in the evidence table or
   become a placeholder.
4. `html.data_sections` must match the blueprint's section order.
5. If a browser is available, take a desktop (1440 x 900) and a mobile-width (390 x 844)
   screenshot and look at them before you hand the file over; fix what looks broken.

## 5. Save, share, hand off

- Save next to the report with the same name and `.html`:
  `growth-reports/<YYYY-MM-DD>-saas-landing-builder-<slug>.html`.
- Tell the user how to open it (double-click the file, or open it in a browser).
- If the session has a tool that publishes private pages (for example a claude.ai artifact
  tool), offer to publish it privately; publish only after the user says yes, and never to a
  public host.
- In the report, list for a developer: the section order, where the copy came from, every
  placeholder still open, and what the draft does not include (real forms, analytics,
  SEO tags beyond noindex, responsive images, the final design system).
