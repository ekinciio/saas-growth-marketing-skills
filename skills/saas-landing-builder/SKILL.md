---
name: saas-landing-builder
description: >
  Design and optimize high-converting SaaS landing pages. Provides
  section-by-section page structure, copy frameworks, and conversion
  best practices. Use when the user mentions landing page design,
  SaaS homepage, conversion page, landing page copy, page structure,
  or wants help building a marketing page.
---

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

## SPA Limitation Note

This skill performs static HTML analysis when reviewing existing pages. Single-page applications (SPAs) built with frameworks like React, Angular, or Vue.js render content dynamically via JavaScript. In these cases, the static analysis may not detect all page sections, and results should be verified manually. For SPA-heavy sites, consider using browser automation tools like Playwright or Puppeteer for more complete analysis.

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

### Conversion Benchmarks

| Page Element | Average Impact |
|-------------|---------------|
| Hero with clear value prop | +20-30% conversion |
| Social proof bar | +10-15% trust |
| Testimonials with photos | +15-25% credibility |
| FAQ section | -20-30% support tickets |
| Single CTA focus | +15-20% vs multiple CTAs |

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
