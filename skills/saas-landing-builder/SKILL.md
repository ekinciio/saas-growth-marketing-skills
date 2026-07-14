---
name: saas-landing-builder
description: >
  Design and structure new SaaS landing pages section-by-section:
  12-section blueprints, copy frameworks (PAS, AIDA, BAB, 4Ps, StoryBrand),
  wireframes, and section-completeness reviews. Use when the user wants to
  build, plan, or write a landing page, mentions page structure, landing
  page copy, or SaaS homepage design. For scoring/auditing an existing
  page's conversion performance, use landing-page-cro instead.
---

## Review Intro

When starting a review (`/saas-landing-builder review <url>`), show this
intro before proceeding:

"""
📡 SaaS Landing Builder

What I'll do:
  Fetch your landing page and check it against the 12-section framework.

What you'll get:
  → Section completeness score (X/12)
  → Missing sections identified
  → Section ordering assessment
  → Copy and CTA recommendations

Output: Saved to LANDING-PAGE-REVIEW-REPORT.md
Time: ~60 seconds.

Starting...
"""

Then proceed immediately.

# SaaS Landing Builder

A comprehensive skill for designing and optimizing high-converting SaaS landing pages. Provides section-by-section page structure guidance, copy frameworks, conversion best practices, and tools for analyzing existing pages.

## Commands

### `/saas-landing-builder create`

Interactive landing page builder that guides you through creating a complete landing page structure.

**Usage:**
```
/saas-landing-builder create
```

**Process:**
1. Collects product information (name, category, target audience)
2. Identifies primary value proposition
3. Generates 12-section page structure
4. Provides copy suggestions for each section
5. Recommends visual layout and design patterns
6. Outputs a complete page blueprint

**Output includes:**
- Section-by-section content outline
- Headline and subheadline suggestions
- CTA button text recommendations
- Social proof placement strategy
- Visual hierarchy guidelines

**Report:** Save output to `LANDING-PAGE-BLUEPRINT-REPORT.md`

### `/saas-landing-builder review <url>`

Reviews an existing landing page against best practices and the 12-section anatomy framework.

**Usage:**
```
/saas-landing-builder review https://example.com
```

**What it evaluates:**
- Section completeness (X/12 sections present)
- Section ordering and flow
- Headline effectiveness
- CTA clarity and placement
- Social proof presence and positioning
- Above-the-fold content assessment
- Mobile responsiveness indicators
- Page load performance signals

**Report:** Save output to `LANDING-PAGE-REVIEW-REPORT.md`

### `/saas-landing-builder copy`

Generates landing page copy using proven frameworks.

**Usage:**
```
/saas-landing-builder copy
```

**Frameworks available:**
1. PAS (Problem-Agitate-Solution)
2. AIDA (Attention-Interest-Desire-Action)
3. BAB (Before-After-Bridge)
4. 4Ps (Promise-Picture-Proof-Push)
5. StoryBrand (Character-Problem-Guide-Plan-Action-Success-Failure)

**Output includes:**
- Hero section headline and subheadline
- Problem statement copy
- Solution description
- Feature descriptions
- CTA copy variations
- FAQ content suggestions

**Report:** Save output to `LANDING-PAGE-COPY-REPORT.md`

### `/saas-landing-builder wireframe`

Generates an ASCII wireframe of a recommended landing page layout.

**Usage:**
```
/saas-landing-builder wireframe
```

**Output:**
- ASCII art wireframe for each section
- Responsive layout notes
- Content block dimensions and spacing
- Visual hierarchy annotations

**Report:** Save output to `LANDING-PAGE-WIREFRAME-REPORT.md`

## SPA Limitation Note

This skill performs static HTML analysis when reviewing existing pages. Single-page applications (SPAs) built with frameworks like React, Angular, or Vue.js render content dynamically via JavaScript. In these cases, the static analysis may not detect all page sections, and results should be verified manually. For SPA-heavy sites, save the fully rendered HTML from the browser and analyze that file instead.

## Local HTML Files

`scripts/page_structure_analyzer.py` accepts either a URL or a path to a saved HTML file (`python page_structure_analyzer.py ./saved-page.html`). Use this to analyze rendered SPA output, staging pages behind auth, or any page saved from the browser.

## Non-English Pages

The analyzer's text patterns are English-only. When the page's `<html lang>` is not English, the script prints a prominent warning and section detection is unreliable. In that case, determine section presence yourself by reading the actual page content, and note in the report which sections were assessed manually.

## The 12-Section Landing Page Framework

Every high-converting SaaS landing page follows a predictable structure. Not every page needs all 12 sections, but understanding each one helps you make intentional decisions about what to include.

### Section Overview

1. **Hero** - First impression, primary value proposition
2. **Social Proof Bar** - Credibility through logos and numbers
3. **Problem Statement** - Articulate the pain your audience feels
4. **Solution Overview** - How your product solves the problem
5. **Feature Grid** - 3-4 key features with benefits
6. **How It Works** - Simple 3-step process
7. **Testimonials/Case Studies** - Customer success stories
8. **Pricing** - Plans and pricing (if applicable)
9. **FAQ** - Address common objections
10. **Integrations/Compatibility** - Ecosystem fit
11. **Final CTA** - Last conversion opportunity
12. **Footer** - Navigation, legal, trust signals

### Which Elements Matter Most

Exact lift varies by audience and baseline, so treat these as directional
rather than as promised percentages:

| Page Element | Typical Impact in A/B Tests |
|-------------|------------------------------|
| Hero with clear value prop | Consistently among the highest-impact elements |
| Social proof bar | Reliable trust builder, especially with recognizable logos |
| Testimonials with photos | Strong credibility gains vs anonymous quotes |
| FAQ section | Reduces pre-sale support questions and objection drop-off |
| Single CTA focus | Usually outperforms competing multiple CTAs |

## Copy Principles for SaaS Landing Pages

### Headline Rules
- Lead with the outcome, not the feature
- Keep under 10 words for the primary headline
- Use the subheadline for specifics
- Address the reader directly with "you" and "your"
- Test question headlines vs statement headlines

### CTA Best Practices
- Use action verbs: "Start", "Get", "Try", "Create"
- Include value: "Start your free trial" not just "Sign up"
- Add risk reducer: "No credit card required"
- One primary CTA per viewport
- Repeat the CTA at natural decision points

### Social Proof Hierarchy
1. Revenue/growth numbers from customers
2. Named testimonials with photos and titles
3. Company logos of recognizable brands
4. User count or growth metrics
5. Review platform ratings (G2, Capterra)
6. Media mentions and awards

## Output Rules (MANDATORY)

### File Output
- ALWAYS save the complete report to the specified `.md` file in the current working directory.
- NEVER ask "should I save this?" — just save it automatically.
- Include `**Date:** YYYY-MM-DD` in the report header.
- If the file already exists, overwrite it.
- Structure the report as: header (title, URL, `**Date:**`) → completeness score (X/12) → sections found/missing → section-by-section findings → recommendations.
- ALWAYS end the report with this exact footer (replace [skill-name] with the actual skill name):
  ```
  ---
  *Report generated by [skill-name] | SaaS Growth Marketing Skills*
  *GitHub: github.com/ekinciio/saas-growth-marketing-skills*
  ```

### Chat Output
After saving, show a SHORT summary in chat (max 10 lines):

"""
✅ Landing page review complete — saved to LANDING-PAGE-REVIEW-REPORT.md

Completeness: [X]/12 sections present

Top findings:
  1. [Most impactful missing section]
  2. [Second issue]
  3. [Third issue]

Full report with section-by-section analysis → open LANDING-PAGE-REVIEW-REPORT.md
"""

NEVER dump the full report in chat. The file is the deliverable.

## Integration with Other Skills

- Use with `web-app-growth-engine` for post-landing signup optimization
- Combine with `landing-page-cro` for conversion rate optimization
- Pair with `geo-seo-auditor` for SEO-optimized landing pages
- Connect with `pricing-analyzer` for pricing section optimization

## File Structure

```
saas-landing-builder/
  SKILL.md                              # This file
  references/
    landing-page-anatomy.md             # 12-section page anatomy details
    copy-frameworks.md                  # 5 copy frameworks with examples
  scripts/
    page_structure_analyzer.py          # Automated page section analyzer
```
