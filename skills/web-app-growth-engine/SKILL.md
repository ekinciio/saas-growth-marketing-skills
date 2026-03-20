---
name: web-app-growth-engine
description: >
  Analyze and optimize SaaS web application growth funnels. Evaluates signup
  flows, activation metrics, conversion points, and growth loops for
  web-based SaaS products. Use when the user mentions web app growth,
  signup funnel, SaaS conversion, web activation, user acquisition for
  web apps, or growth engine optimization.
---

# Web App Growth Engine

A comprehensive skill for analyzing and optimizing SaaS web application growth funnels. This skill helps you evaluate signup flows, measure activation metrics, identify conversion bottlenecks, and design sustainable growth loops.

## Commands

### `/web-app-growth-engine audit <url>`

Performs a full web growth audit on the specified URL. This includes:

1. **Signup Flow Analysis** - Evaluates the friction in your signup process
2. **Activation Metrics** - Assesses how quickly users reach value
3. **Conversion Points** - Identifies where users drop off
4. **Growth Loop Assessment** - Checks for viral and retention loops

**Usage:**
```
/web-app-growth-engine audit https://example.com
```

**Output includes:**
- Signup friction score (0-100)
- Field-by-field analysis of the signup form
- SSO and social login availability
- Trust signal evaluation
- CTA effectiveness assessment
- Activation metric recommendations
- Growth loop opportunities

**Report:** Save output to `WEB-GROWTH-AUDIT-REPORT.md`

### `/web-app-growth-engine signup-flow <url>`

Performs a focused signup flow friction analysis on the specified URL.

**Usage:**
```
/web-app-growth-engine signup-flow https://example.com/signup
```

**What it analyzes:**
- Number of form fields and required fields
- SSO options (Google, GitHub, Microsoft, etc.)
- Password requirements and complexity
- CAPTCHA presence
- Credit card requirements
- Trust signals (badges, testimonials, security icons)
- CTA button text and placement
- Progressive profiling implementation

**Report:** Save output to `WEB-GROWTH-SIGNUP-REPORT.md`

**Friction scoring breakdown:**
- Each required field: +8 points
- No SSO option: +15 points
- Password requirement: +10 points
- CAPTCHA present: +10 points
- Credit card required: +25 points
- More than 5 fields: +15 points
- No trust signals: +10 points

### `/web-app-growth-engine activation`

Generates an activation metric framework tailored to your product type.

**Usage:**
```
/web-app-growth-engine activation
```

**Framework includes:**
- Defining your product's "aha moment"
- Time-to-value measurement strategy
- Activation rate calculation methods
- Setup completion tracking
- Feature adoption milestones
- Value realization indicators
- Cohort analysis recommendations

**Product type categories:**
- Productivity tools (e.g., project management, note-taking)
- Developer tools (e.g., APIs, CI/CD, hosting)
- Analytics platforms (e.g., dashboards, reporting)
- Communication tools (e.g., chat, email, video)
- E-commerce enablers (e.g., payment, shipping, storefront)
- Design tools (e.g., editors, prototyping)

**Report:** Save output to `WEB-GROWTH-ACTIVATION-REPORT.md`

### `/web-app-growth-engine loops`

Designs growth loops specific to your SaaS product.

**Usage:**
```
/web-app-growth-engine loops
```

**Growth loop types covered:**

1. **Viral Loops**
   - User-invite loops (referral programs)
   - Content-sharing loops (user-generated content)
   - Collaborative loops (team invitations)
   - Embed/badge loops (powered-by attribution)

2. **Content Loops**
   - SEO-driven content loops
   - User-generated content indexing
   - Template/resource sharing
   - Community-driven content

3. **Paid Loops**
   - Acquisition cost optimization
   - Revenue reinvestment models
   - Channel diversification strategy

4. **Product-Led Loops**
   - Freemium conversion paths
   - Usage-based expansion
   - Feature gating strategy
   - Self-serve upgrade flows

**Report:** Save output to `WEB-GROWTH-LOOPS-REPORT.md`

## API Integrations (Optional)

This skill works out of the box by fetching public web pages. However, real page performance data and analytics cannot be measured from a simple HTML fetch alone.

If the user provides their own API keys, use them to enrich the growth audit with real data.

| Environment Variable | Service | What It Unlocks |
|---------------------|---------|-----------------|
| `GOOGLE_API_KEY` | Google PageSpeed Insights API | Real Core Web Vitals scores, mobile performance data, Lighthouse audit |
| `GOOGLE_ANALYTICS_JSON` | Google Analytics Data API | Actual signup conversion rates, traffic sources, bounce rates, session data |

**How to set up:**
```bash
# Google PageSpeed (optional)
export GOOGLE_API_KEY="your_google_api_key"

# Google Analytics (optional) - path to service account JSON
export GOOGLE_ANALYTICS_JSON="/path/to/service-account.json"
```

**Behavior:**
- If API keys are set → Enrich the audit with real performance and analytics data
- If not set → Use HTML-only analysis (current default behavior, no change)
- Each integration is independent - you can set one without the others

## SPA Limitation Note

This skill performs static HTML analysis using HTTP requests. Single-page applications (SPAs) built with frameworks like React, Angular, or Vue.js may render signup forms dynamically via JavaScript. In these cases, the static analysis may not capture all form elements, and results should be verified manually. For SPA-heavy sites, consider using browser automation tools like Playwright or Puppeteer for a more complete analysis.

## Growth Audit Methodology

The audit follows a structured approach based on the pirate metrics framework (AARRR):

### 1. Acquisition Analysis
- Traffic source diversity
- Landing page effectiveness
- Ad-to-page message match
- SEO visibility for product keywords

### 2. Activation Assessment
- Signup completion rate indicators
- Onboarding flow completeness
- Time-to-first-value estimation
- Setup wizard presence and quality

### 3. Retention Signals
- Email capture for re-engagement
- Notification permission requests
- Habit-forming feature identification
- Session depth indicators

### 4. Revenue Path
- Pricing page clarity
- Free-to-paid conversion path
- Upgrade prompts and positioning
- Payment friction assessment

### 5. Referral Mechanisms
- Share functionality presence
- Referral program visibility
- Social proof generation
- Network effects potential

## Benchmark Data

### Signup Conversion Benchmarks by Industry
| Industry | Average | Good | Excellent |
|----------|---------|------|-----------|
| B2B SaaS | 2-5% | 5-8% | 8-12% |
| Developer Tools | 3-7% | 7-12% | 12-20% |
| E-commerce SaaS | 1-3% | 3-6% | 6-10% |
| Marketing Tools | 2-4% | 4-7% | 7-11% |
| Productivity Apps | 3-6% | 6-10% | 10-15% |

### Activation Rate Benchmarks
| Product Type | Average | Good | Excellent |
|-------------|---------|------|-----------|
| Freemium SaaS | 20-30% | 30-45% | 45-60% |
| Free Trial | 15-25% | 25-40% | 40-55% |
| PLG Products | 25-35% | 35-50% | 50-65% |

## Report Output

Every command MUST save its output as a markdown report file:

| Command | Output File |
|---------|-------------|
| `audit` | `WEB-GROWTH-AUDIT-REPORT.md` |
| `signup-flow` | `WEB-GROWTH-SIGNUP-REPORT.md` |
| `activation` | `WEB-GROWTH-ACTIVATION-REPORT.md` |
| `loops` | `WEB-GROWTH-LOOPS-REPORT.md` |

The report file should include:
- Date of analysis
- URL analyzed
- Full scores with dimension breakdowns
- Benchmark comparisons
- Prioritized recommendations

Always inform the user where the report was saved after completion.

## Integration with Other Skills

- Use with `saas-landing-builder` for landing page optimization
- Combine with `onboarding-optimizer` for post-signup flow improvement
- Pair with `plg-funnel-analyzer` for deeper product-led growth analysis
- Connect with `subscription-metrics` for revenue impact measurement

## File Structure

```
web-app-growth-engine/
  SKILL.md                              # This file
  references/
    signup-funnel-patterns.md           # Signup optimization patterns
    activation-metrics.md               # Activation measurement frameworks
  scripts/
    signup_auditor.py                   # Automated signup flow analyzer
```
