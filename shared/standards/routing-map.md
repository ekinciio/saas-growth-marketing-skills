# Routing Map

One owner per intent. This file is the single source for which skill or agent handles a
request and for the "Not for" lines in every description and SKILL.md. When it changes, update
the affected descriptions and run the trigger evals in `evals/triggering.jsonl`.

## Contents

1. Rules
2. Intent ownership
3. Skills: owns, not for, description sentence
4. Agents
5. Third-party skill packs (not ours)
6. Known conflicts and how they resolve
7. Maintaining this map and the eval set

---

## 1. Rules

- Each intent has exactly one owner. When two skills seem to fit, section 2 decides.
- A description claims only the intents its skill owns. Triggers owned by another skill are
  removed (each skill in section 3 lists what to drop).
- Every description ends with one short "Not for ... (owner)" sentence from section 3. The
  SKILL.md `## When to use` section carries the full "Not for" list.
- When a run ends and the user's next question belongs to another skill, the chat summary's
  Next line names that skill.
- A site audit with no area named ("audit https://mysaas.com") goes to `growth-skills`, which
  asks which area and recommends the owner.
- A generic "help" or "what can you do" with no mention of growth work or this toolkit is not
  ours. Claude Code answers it.
- Skills from other packs are never edited or removed by this toolkit. Our skills win routing
  by being specific to SaaS growth, not by claiming generic words.

## 2. Intent ownership

| Intent | Owner | Often misrouted to |
|---|---|---|
| Can AI assistants crawl, understand and cite a SaaS site (AI-crawler rules, llms.txt, citability, JSON-LD) in one report | geo-seo-auditor | geo, geo-audit, geo-check, geo-crawlers, geo-llmstxt, spy-audit, spy-crawlers |
| Conversion audit of an existing landing, home or pricing page | landing-page-cro | saas-landing-builder, pricing-analyzer |
| Plan or write a new page, its copy or an HTML prototype | saas-landing-builder | landing-page-cro |
| Signup page and the steps up to account creation | web-app-growth-engine | landing-page-cro, onboarding-optimizer |
| First-run experience after account creation | onboarding-optimizer | web-app-growth-engine, plg-funnel-analyzer |
| Funnel numbers: activation rate, visitor-to-signup, free-to-paid, growth loops | plg-funnel-analyzer | web-app-growth-engine, onboarding-optimizer |
| Compute or benchmark MRR, ARR, churn, NRR, GRR, CAC, LTV, payback, Rule of 40; month-over-month MRR report; forecast | subscription-metrics | retention-playbook, metrics-analyst, geo-compare |
| Reduce churn: cancel flow, dunning, win-back, health scores | retention-playbook | subscription-metrics |
| The user's own pricing, packaging and willingness to pay | pricing-analyzer | competitor-intel, geo-proposal |
| Business competitors: positioning, messaging, pricing as context, battle cards, "X vs us" pages | competitor-intel | geo-spy, spy-compare, spy-steal, spy-discover, geo-compare |
| Recent conversations mentioning a brand name on Reddit, Hacker News, GitHub | brand-mention-scanner | geo-brand-mentions, spy-brand, geo |
| Reddit threads where people describe the problem the product solves | reddit-opportunity-finder | brand-mention-scanner, geo-prospect |
| Feedback text the user supplies or exports: reviews, NPS, tickets, surveys | review-sentiment | brand-mention-scanner |
| App Store and Google Play listing metadata | aso-optimizer | review-sentiment |
| Google Business Profile, map pack, NAP, local citations | local-seo-optimizer | geo-seo-auditor |
| Which growth skill fits a goal; toolkit listing; site audit with no area named | growth-skills | geo, landing-page-cro |
| Multi-area growth audit ending in a 90-day plan | growth-strategist (agent) | geo-audit |
| Launch plan working back from a launch date | launch-planner (agent) | saas-landing-builder, aso-optimizer |
| Multi-area SaaS health review across revenue, funnel, retention and pricing | metrics-analyst (agent) | subscription-metrics |
| Generic help with no growth context | none (Claude Code) | growth-skills |

## 3. Skills: owns, not for, description sentence

### geo-seo-auditor

- Owns: AI-search readiness of a SaaS website in one report: AI-crawler rules in robots.txt,
  llms.txt (validate or generate), passage citability as one dimension, JSON-LD for entity
  understanding, and fixes per platform (ChatGPT, Claude, Perplexity, Google AI Overviews,
  Copilot).
- Not for:
  - Conversion audits of a page -> landing-page-cro
  - Conversations that mention the brand -> brand-mention-scanner
  - Business competitor analysis -> competitor-intel
  - Rewriting paragraphs on request outside an audit -> not this toolkit
  - General technical SEO, rankings, backlinks, keyword research -> not this toolkit
  - Agency proposals, prospect pipelines, client PDF reports -> not this toolkit
  - Local map-pack visibility -> local-seo-optimizer
- Description sentence: "Not for conversion audits (landing-page-cro), brand-name mention
  scans (brand-mention-scanner) or business competitor analysis (competitor-intel)."
- Drop from the description: bare "robots.txt", bare "audit", "brand authority signals"; drop
  the `brands` command and point to brand-mention-scanner.

### landing-page-cro

- Owns: conversion audit of an existing landing, home or pricing page from a URL or saved
  HTML: value proposition, CTA, proof, objections, form friction, visual hierarchy; copy
  review; test ideas with traffic-aware plans.
- Not for:
  - Planning or writing a new page -> saas-landing-builder
  - The signup form and steps up to account creation -> web-app-growth-engine
  - Price levels, tiers and packaging -> pricing-analyzer (the pricing page's layout and
    conversion stay here)
  - The in-product first run -> onboarding-optimizer
  - AI-search readiness -> geo-seo-auditor
- Description sentence: "Not for writing a new page (saas-landing-builder) or the signup flow
  itself (web-app-growth-engine)."

### saas-landing-builder

- Owns: planning and writing new SaaS pages: page-type blueprints, section-by-section copy
  with frameworks (PAS, AIDA, BAB, 4Ps, StoryBrand), an HTML prototype, and a section
  completeness check of the current page during a rebuild.
- Not for:
  - Scoring a live page's conversion -> landing-page-cro
  - "X vs us" and "X alternatives" pages -> competitor-intel
  - App store listing copy -> aso-optimizer
  - Lifecycle and onboarding emails -> not this toolkit (retention-playbook covers win-back
    and dunning)
  - Building UI components or application code -> not this toolkit
- Description sentence: "Not for scoring an existing page's conversion (landing-page-cro) or
  competitor comparison pages (competitor-intel)."

### web-app-growth-engine

- Owns: the public signup page and the steps up to account creation: a friction ledger of
  steps, required inputs, SSO options, card requirement, CAPTCHA and verification gates, and
  signup conversion.
- Not for:
  - Activation rate, funnel numbers and growth loops -> plg-funnel-analyzer
  - What happens after account creation -> onboarding-optimizer
  - The marketing landing page -> landing-page-cro
  - Fixing signup bugs in code -> not this toolkit
- Description sentence: "Not for activation-rate or funnel numbers (plg-funnel-analyzer),
  post-signup onboarding (onboarding-optimizer) or the landing page (landing-page-cro)."
- Drop from the description: "activation rate", "web activation", "activation metrics",
  "growth loops", "growth engine optimization", "user acquisition for web apps".

### onboarding-optimizer

- Owns: the first-run experience after account creation: setup steps, empty states,
  checklists, tours, time-to-value design, activation milestones as UX.
- Not for:
  - Signup page friction -> web-app-growth-engine
  - Activation rate numbers and funnel benchmarks -> plg-funnel-analyzer
  - Win-back and cancellation flows -> retention-playbook
  - Employee onboarding, developer docs or READMEs -> not this toolkit
- Description sentence: "Not for the signup page (web-app-growth-engine) or activation-rate
  numbers (plg-funnel-analyzer)."
- Drop from the description: "signup friction", bare "user activation".

### plg-funnel-analyzer

- Owns: funnel numbers the user provides or exports: visitor-to-signup, activation rate,
  free-to-paid and trial conversion, benchmarks by motion, the biggest leak, and growth loops.
- Not for:
  - A signup page URL -> web-app-growth-engine
  - Designing the first-run UX -> onboarding-optimizer
  - Computing MRR, churn, NRR, LTV or CAC -> subscription-metrics
  - Churn reduction programs -> retention-playbook
  - Pricing and packaging -> pricing-analyzer
- Description sentence: "Not for a signup page URL (web-app-growth-engine), first-run UX
  (onboarding-optimizer) or revenue KPIs (subscription-metrics)."
- Drop from the description: "user onboarding metrics".

### subscription-metrics

- Owns: computing and benchmarking revenue KPIs: MRR, ARR, logo and revenue churn, NRR, GRR,
  ARPA, CAC, LTV, payback, Rule of 40, burn multiple, quick ratio, magic number; the
  month-over-month MRR and churn report; forecast and runway; billing export import.
- Not for:
  - Reducing churn (cancel flow, dunning, win-back, health scores) -> retention-playbook
  - Funnel conversion and activation -> plg-funnel-analyzer
  - Price changes -> pricing-analyzer
  - A health review across revenue, funnel, retention and pricing -> metrics-analyst
  - Progress reports on GEO or SEO audits -> not this toolkit
- Description sentence: "Not for reducing churn (retention-playbook) or funnel conversion
  (plg-funnel-analyzer)."

### retention-playbook

- Owns: designing interventions that reduce churn: diagnosis from cancellation reasons,
  customer health and risk scoring, cancel flow with save offers, dunning, win-back.
- Not for:
  - Computing churn, NRR or GRR -> subscription-metrics
  - Analyzing review, survey or ticket text -> review-sentiment (then return with the themes)
  - Onboarding new users -> onboarding-optimizer
  - Payment retry code -> not this toolkit
- Description sentence: "Not for computing churn or NRR (subscription-metrics) or mining
  feedback text (review-sentiment)."
- Drop from the description: "NRR".

### pricing-analyzer

- Owns: the user's own SaaS pricing: tiers, packaging, value metric, feature gating,
  freemium versus trial, willingness to pay (Van Westendorp), price increases.
- Not for:
  - Profiling competitors (their prices are context only) -> competitor-intel
  - Pricing page layout and conversion -> landing-page-cro
  - Agency service packages and proposals -> not this toolkit
  - Payment or checkout implementation -> not this toolkit
- Description sentence: "Not for competitor profiles (competitor-intel) or pricing-page
  conversion (landing-page-cro)."
- Drop from the description: bare "pricing page".

### competitor-intel

- Owns: business competitors: positioning, messaging, pricing and packaging as context,
  channels, content, hiring and launch signals, battle cards, landscape maps, "X vs us" and
  "X alternatives" drafts, change monitoring.
- Not for:
  - AI-search visibility comparisons -> not this toolkit (geo-seo-auditor covers the user's
    own site)
  - The user's own pricing decisions -> pricing-analyzer
  - Competitor app listings -> aso-optimizer; competitor reviews -> review-sentiment
  - Brand mention counts -> brand-mention-scanner
- Description sentence: "Not for AI-search visibility comparisons or your own pricing
  decisions (pricing-analyzer)."

### brand-mention-scanner

- Owns: recent conversations that mention a specific brand or product name on Reddit, Hacker
  News and GitHub; filters same-word false positives; flags threads worth a reply; share of
  voice against named competitors.
- Not for:
  - Problem-keyword prospecting -> reddit-opportunity-finder
  - Sentiment of text the user already has -> review-sentiment
  - AI-search authority scores -> not this toolkit
  - Whether AI assistants recommend the brand -> not this toolkit
- Description sentence: "Not for problem-keyword prospecting (reddit-opportunity-finder) or
  text you already have (review-sentiment)."
- Drop from the description: "reputation tracking" without "brand name".

### reddit-opportunity-finder

- Owns: Reddit threads where people describe the problem the product solves (problem and
  category keywords, not the brand name), ranked by intent, with disclosed reply drafts and
  older threads that rank on Google.
- Not for:
  - Mentions of the user's brand name -> brand-mention-scanner
  - Lead lists, CRM or sales pipelines -> not this toolkit
  - Scraping or bulk-downloading Reddit -> not this toolkit
- Description sentence: "Not for brand-name mentions (brand-mention-scanner) or CRM
  pipelines."
- Drop from the description: "Reddit monitoring" without "problem keywords", bare "lead
  generation".

### review-sentiment

- Owns: feedback text the user supplies or exports: app store reviews (plus a free App Store
  review fetch), G2, Capterra and Trustpilot exports, NPS verbatims, support tickets, survey
  and cancellation comments; themes, complaints, feature requests; competitor review
  comparison.
- Not for:
  - Finding mentions online -> brand-mention-scanner
  - App listing metadata and rating prompts -> aso-optimizer
  - Local review counts and replies for map ranking -> local-seo-optimizer
  - Building a sentiment model in code -> not this toolkit
- Description sentence: "Not for finding mentions online (brand-mention-scanner) or app
  listing metadata (aso-optimizer)."

### aso-optimizer

- Owns: App Store and Google Play listings: title, subtitle, keyword field, description,
  screenshots, custom product page and in-app event metadata, policy-safe rating prompts,
  competitor listings.
- Not for:
  - Review text mining -> review-sentiment
  - Web landing pages -> landing-page-cro
  - In-app onboarding -> onboarding-optimizer
  - Build, signing or submission errors -> not this toolkit
- Description sentence: "Not for review text analysis (review-sentiment) or web pages
  (landing-page-cro)."

### local-seo-optimizer

- Owns: Google Business Profile and local search for places with a physical location or
  service area: map pack, NAP consistency, citations, local review counts. Its use as a
  prospect scorecard for SaaS that sells to local businesses is an open maintainer decision.
- Not for:
  - AI-search readiness of a SaaS site -> geo-seo-auditor
  - SEO for an online-only SaaS -> not this toolkit
  - Review text mining -> review-sentiment
  - Translating or localizing a website -> not this toolkit
- Description sentence: "Not for AI-search readiness (geo-seo-auditor) or online-only SaaS
  SEO."

### growth-skills

- Owns: listing this toolkit's skills and agents, recommending the one that fits a growth
  goal, and routing a site audit with no area named (it asks which area).
- Not for:
  - Generic "help" or "what can you do" with no mention of growth work -> Claude Code
  - Running an audit itself -> the owning skill
  - Listing other packs' skills -> not this toolkit
- Description sentence: "Not for generic help requests outside growth work."
- Drop from the description: "help", "what can you do", "list skills".

## 4. Agents

Agents run as subagents: they cannot ask the user, and they return `MISSING_INPUTS` instead
of inventing inputs (`growth-context.md` standard).

### growth-strategist

- Owns: a multi-area growth audit across acquisition, conversion, activation, retention and
  revenue, ending in a 90-day plan.
- Not for: SEO-only or AI-search-only audits (geo-seo-auditor); single-area questions (the
  owning skill).
- Description sentence: "Covers acquisition, conversion, activation, retention and revenue,
  not only SEO; for one area use that area's skill."

### launch-planner

- Owns: a launch plan and checklist that works back from the real launch date.
- Not for: writing the landing page (saas-landing-builder); ASO alone (aso-optimizer);
  competitor research alone (competitor-intel).
- Description sentence: "Not for writing the launch page (saas-landing-builder) or ASO alone
  (aso-optimizer)."

### metrics-analyst

- Owns: a SaaS health review across revenue, funnel, retention and pricing that aggregates
  the statuses the skills report. It has no thresholds or grades of its own.
- Not for: computing one metric or a monthly MRR report (subscription-metrics); churn
  interventions (retention-playbook); funnel diagnosis alone (plg-funnel-analyzer).
- Description sentence: "Not for a single metric or a monthly MRR report
  (subscription-metrics)."

## 5. Third-party skill packs (not ours)

Users often install other packs next to this one. Two GEO packs are common and their
descriptions claim generic words. They are not part of this toolkit:

- geo pack: `geo`, `geo-audit`, `geo-brand-mentions`, `geo-check` (folder `geo-checker`),
  `geo-citability`, `geo-compare`, `geo-content`, `geo-crawlers`, `geo-llmstxt`,
  `geo-platform-optimizer`, `geo-proposal`, `geo-prospect`, `geo-report`, `geo-report-pdf`,
  `geo-schema`, `geo-technical`
- spy pack: `geo-spy` (folder `spy`), `spy-audit`, `spy-brand`, `spy-citability`,
  `spy-compare`, `spy-content`, `spy-crawlers`, `spy-discover`, `spy-report-pdf`,
  `spy-rewrite`, `spy-schema`, `spy-steal`, `spy-watch`

How our descriptions stay distinct:

| Their claimed words | Our boundary |
|---|---|
| "seo", "audit", "optimize", "any URL for analysis" (geo) | No bare generic words in our descriptions; growth-skills routes SaaS site audits with no area named. |
| "compare", "delta", "monthly report", "progress" (geo-compare) | subscription-metrics says "month-over-month MRR and churn report"; competitor-intel says "business competitors". |
| "lead", "pipeline", "client", "crm" (geo-prospect) | reddit-opportunity-finder says "threads where people describe the problem you solve". |
| "proposal", "pricing" of service packages (geo-proposal) | pricing-analyzer says "your own SaaS pricing". |
| "competitor analysis for AI visibility" (geo-spy, spy-compare, spy-steal, spy-discover) | competitor-intel says "business competitors, not AI-search comparisons". |
| "brand mentions", "Brand Authority Score" (geo, geo-brand-mentions, spy-brand) | brand-mention-scanner says "recent conversations mentioning your brand name, to reply to". |
| crawlers, llms.txt, citability, schema, rewrites (geo-crawlers, spy-crawlers, geo-check, geo-llmstxt, geo-citability, spy-citability, spy-rewrite, geo-schema, geo-technical, geo-audit, spy-audit) | geo-seo-auditor says "SaaS AI-search readiness in one report", citability is one dimension and not a rewrite service. |

Local mitigation, never shipped in this repo: a user who keeps both packs can set the
duplicates they do not use to `"name-only"` or `"off"` in `skillOverrides` in their own
settings (the `/skills` menu writes it). `skillOverrides` does not apply to plugin skills.

Open maintainer decisions that affect routing:

- Whether geo-seo-auditor stays as the SaaS-focused GEO check, is renamed, or is slimmed down
  to crawler and llms.txt checks.
- Whether the toolkit ships as a Claude Code plugin, which namespaces every command (for
  example `/growth:geo-seo-auditor`) and ends name collisions.
- Whether local-seo-optimizer stays general, is repositioned for SaaS that sells to local
  businesses, or is replaced.
- Which new skills are added; each new skill needs rows in sections 2 and 3 and 20 eval
  prompts before it ships.

## 6. Known conflicts and how they resolve

The 1.2 review found these collisions. Owners follow sections 2 and 3.

1. "Is GPTBot or ClaudeBot allowed on my site?" -> geo-seo-auditor when the site is the
   user's SaaS; its description leads with "SaaS AI-search readiness".
2. "Generate or validate my llms.txt" -> geo-seo-auditor; generated files never contain
   placeholder links.
3. "Run a GEO or AI visibility audit on <url>" -> geo-seo-auditor, pending the decision on the
   primary GEO tool.
4. "Score my citability" or "rewrite paragraphs so AI cites them" -> geo-seo-auditor only as
   one dimension of a site audit; a rewrite service is not ours.
5. "Where is my brand being mentioned?" -> brand-mention-scanner; geo-seo-auditor loses its
   `brands` command.
6. "Analyze competitor X" or "compare my site with X" -> competitor-intel for business
   analysis; AI-search comparisons are not ours.
7. "Give me a monthly progress report" -> subscription-metrics when it is about MRR or churn;
   a GEO audit delta is not ours.
8. "Find leads or prospects on Reddit" -> reddit-opportunity-finder.
9. "Audit https://mysaas.com" with no area -> growth-skills, which asks which area.
10. "help" or "what can you do" -> not ours.
11. "Our activation rate is 18%, how do we improve it?" -> plg-funnel-analyzer.
12. "Our churn is 4% and NRR 95%" -> subscription-metrics; reducing churn ->
    retention-playbook; a review across several areas -> metrics-analyst.
13. "Analyze the sentiment of these comments" -> review-sentiment when the user supplies the
    text; brand-mention-scanner only when mentions must be found first.
14. "Do a full growth audit" -> growth-strategist (or a main-thread growth-audit skill once it
    exists); geo-audit is SEO-only.
15. "SaaS health check" or "grade my business" -> metrics-analyst for several areas,
    subscription-metrics for revenue KPIs; grades come from the skills only.
16. "Review our pricing" -> pricing-analyzer.
17. "Write my landing page copy" versus "why isn't my landing page converting" ->
    saas-landing-builder versus landing-page-cro; every pair above uses the same
    cross-reference pattern.
18. geo-seo-auditor sorts among the third-party geo-* commands -> open decision on plugin
    namespacing or a rename.

## 7. Maintaining this map and the eval set

- `evals/triggering.jsonl` holds 20 prompts per skill, one JSON object per line:
  `{"skill": "<name>", "prompt": "<text>", "should_trigger": true|false}`.
  - `true`: this skill must be the one chosen for the prompt. No prompt is `true` for two
    skills.
  - `false`: this skill must not be chosen. The right owner is in section 2: another skill,
    an agent, a third-party skill, or nothing.
- Each skill has 10 `true` and 10 `false` prompts. The `false` prompts are near misses:
  sibling skills, third-party geo and spy skills, ordinary coding tasks that share a word, and
  generic help. Every skill's `false` set has at least one third-party geo or spy collision
  and one generic help prompt.
- Prompts are natural requests, never slash commands. `/skill-name ...` invokes the skill
  directly without a Skill tool call, so it tests nothing about the description, and a
  harness that detects triggering from the Skill tool call (skill-creator's `run_eval.py`,
  `claude plugin eval` with a `tool_used: Skill` grader) scores it as a miss every time.
- Adding a skill: add its rows to sections 2 and 3, its 20 prompts, and the "Not for" lines
  that point to it from its neighbours.
- Changing a description: run its 20 prompts before merging. A should-not prompt that
  triggers means the description claims too much; a should prompt that does not trigger means
  the lead use case is missing or buried.
