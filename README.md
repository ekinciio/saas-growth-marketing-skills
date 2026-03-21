<p align="center">
  <img src="https://img.shields.io/badge/Skills-15-blue?style=for-the-badge" alt="15 Skills" />
  <img src="https://img.shields.io/badge/Templates-4-yellow?style=for-the-badge" alt="4 Templates" />
  <img src="https://img.shields.io/badge/Scripts-19-green?style=for-the-badge" alt="19 Scripts" />
  <img src="https://img.shields.io/badge/Built_for-Claude_Code-blueviolet?style=for-the-badge" alt="Built for Claude Code" />
  <img src="https://img.shields.io/badge/License-MIT-orange?style=for-the-badge" alt="MIT License" />
</p>

<h1 align="center">SaaS Growth Marketing Skills</h1>

<p align="center">
  <strong>Growth marketing skills for AI coding agents. Built for Claude Code.</strong>
</p>

---

15 specialized skills that turn your AI coding agent into a growth marketing expert. Built for Claude Code, compatible with any tool supporting the [Agent Skills](https://github.com/anthropics/agent-skills) standard.

Every skill produces **actionable output** saved as a `.md` report file - scores, audits, and data-driven recommendations. Not just knowledge dumps. Give it a URL, your metrics, or your app name and get back a scored audit with prioritized fixes, saved to a file you can share.

**No API keys required** - everything works with public endpoints and your own data.

## Quick Stats

| | |
|---|---|
| **Skills** | 15 specialized growth skills |
| **Scripts** | 19 Python automation scripts |
| **Agents** | 3 orchestration agents |
| **Templates** | 4 strategy templates |
| **License** | MIT - free forever |

---

## What You Get

| Skill | Input | Output | Report File |
|-------|-------|--------|-------------|
| **geo-seo-auditor** | URL | AI search visibility score (0-100), crawler status, llms.txt | `GEO-AUDIT-REPORT.md` |
| **aso-optimizer** | App name | Optimized metadata, ASO health score, keyword strategy | `ASO-REPORT.md` |
| **landing-page-cro** | URL | CRO score (0-100), 10-point audit, A/B test ideas | `CRO-AUDIT-REPORT.md` |
| **subscription-metrics** | Your numbers | MRR, ARR, CAC, LTV, Rule of 40 + health assessment | `SAAS-METRICS-REPORT.md` |
| **local-seo-optimizer** | Business info | Local SEO score, GBP completeness, citation gaps | `LOCAL-SEO-AUDIT-REPORT.md` |
| **review-sentiment** | Reviews text | Sentiment breakdown, theme extraction, insights | `REVIEW-SENTIMENT-REPORT.md` |
| **plg-funnel-analyzer** | Your metrics | Funnel leak detection, benchmark comparison, fix priorities | `PLG-FUNNEL-AUDIT-REPORT.md` |
| **onboarding-optimizer** | Flow details | Onboarding score, pattern recommendation, activation lift | `ONBOARDING-AUDIT-REPORT.md` |
| **retention-playbook** | Customer data | Churn risk score, early warning signals, interventions | `RETENTION-DIAGNOSIS-REPORT.md` |
| **pricing-analyzer** | Pricing data | Van Westendorp analysis, tier recommendations, positioning | `PRICING-AUDIT-REPORT.md` |
| **competitor-intel** | Competitor URL | Auto-extracted profile, positioning analysis, battle card | `COMPETITOR-ANALYSIS-REPORT.md` |
| **web-app-growth-engine** | Signup URL | Friction score, field analysis, SSO/trust audit | `WEB-GROWTH-AUDIT-REPORT.md` |
| **saas-landing-builder** | Landing URL | Section completeness (X/12), missing elements, structure score | `LANDING-PAGE-BLUEPRINT-REPORT.md` |
| **reddit-opportunity-finder** | Keywords | Scored Reddit threads, opportunity ranking, best subreddits | `REDDIT-OPPORTUNITIES-REPORT.md` |
| **brand-mention-scanner** | Brand name | Cross-platform mentions (Reddit/HN/GitHub), sentiment, opportunities | `BRAND-MENTIONS-REPORT.md` |

---

## One-Command Install

```bash
curl -fsSL https://raw.githubusercontent.com/ekinciio/saas-growth-marketing-skills/main/install.sh | bash
```

Or clone manually:

```bash
git clone https://github.com/ekinciio/saas-growth-marketing-skills.git
cd saas-growth-marketing-skills
pip install -r requirements.txt
```

---

## Skills

| # | Skill | Command | Description |
|---|-------|---------|-------------|
| 1 | geo-seo-auditor | `/geo-seo-auditor audit <url>` | Audit websites for AI search engine visibility (GEO) |
| 2 | aso-optimizer | `/aso-optimizer analyze <app>` | App Store Optimization - metadata scoring and competitor comparison |
| 3 | local-seo-optimizer | `/local-seo-optimizer audit <biz>` | Google Business Profile and local search audit |
| 4 | review-sentiment | `/review-sentiment analyze` | Customer review sentiment analysis and theme extraction |
| 5 | landing-page-cro | `/landing-page-cro audit <url>` | Landing page conversion rate optimization audit |
| 6 | plg-funnel-analyzer | `/plg-funnel-analyzer audit` | Product-Led Growth funnel analysis with benchmarks |
| 7 | subscription-metrics | `/subscription-metrics calculate` | SaaS metrics calculator (MRR, ARR, CAC, LTV, Rule of 40) |
| 8 | onboarding-optimizer | `/onboarding-optimizer audit` | User onboarding flow evaluation and pattern matching |
| 9 | retention-playbook | `/retention-playbook diagnose` | Churn risk scoring and retention strategy |
| 10 | pricing-analyzer | `/pricing-analyzer audit` | Pricing strategy analysis with Van Westendorp |
| 11 | competitor-intel | `/competitor-intel analyze <url>` | Competitive analysis and battle card generation |
| 12 | web-app-growth-engine | `/web-app-growth-engine audit <url>` | Web app signup funnel and growth loop analysis |
| 13 | saas-landing-builder | `/saas-landing-builder create` | Landing page structure design and copy frameworks |
| 14 | reddit-opportunity-finder | `/reddit-opportunity-finder search <kw>` | Find high-intent Reddit threads for your product |
| 15 | brand-mention-scanner | `/brand-mention-scanner scan <brand>` | Brand mention tracking across Reddit, HN, and GitHub |
| — | growth-skills | `/growth-skills` | Index of all available skills and commands |

---

## Architecture

```
saas-growth-marketing-skills/
  skills/
    geo-seo-auditor/          # AI search visibility auditing
    aso-optimizer/             # App store optimization
    local-seo-optimizer/      # Local SEO and GBP audit
    review-sentiment/         # Review sentiment analysis
    landing-page-cro/         # Conversion rate optimization
    plg-funnel-analyzer/      # PLG funnel benchmarking
    subscription-metrics/     # SaaS KPI calculator
    onboarding-optimizer/     # Onboarding flow scoring
    retention-playbook/       # Churn risk and retention
    pricing-analyzer/         # Pricing strategy analysis
    competitor-intel/         # Competitive intelligence
    web-app-growth-engine/    # Web app growth analysis
    saas-landing-builder/     # Landing page design
    reddit-opportunity-finder/ # Reddit thread discovery
    brand-mention-scanner/    # Brand monitoring
  agents/
    growth-strategist.md      # Orchestrates growth audits
    launch-planner.md         # Product launch planning
    metrics-analyst.md        # SaaS metrics analysis
  templates/
    gtm-strategy.md           # Go-to-market template
    pricing-analysis.md       # Pricing analysis template
    launch-checklist.md       # 60+ item launch checklist
    report-template.md        # Report structure template
```

Each skill contains:
- `SKILL.md` - Skill definition with commands and instructions
- `references/` - Domain knowledge and best practices
- `scripts/` - Python scripts for data processing and scoring

Every skill saves its output as a `.md` report file in the current working directory. Report files include the date of analysis, full results, and prioritized recommendations.

---

## How It Works

- **Skills auto-activate** when Claude detects relevant context in your conversation
- **Or invoke directly** with `/skill-name` commands
- **Python scripts** handle data processing, scoring, and analysis
- **Agents** orchestrate multiple skills for comprehensive analysis
- **Templates** provide ready-to-fill strategy documents

---

## No API Keys Required (But Supported)

Zero configuration out of the box. No API keys, no accounts, no subscriptions.

- **URL-based skills** fetch public web pages (requests + BeautifulSoup)
- **Community skills** use public APIs (Reddit JSON, HN Algolia, GitHub Search, iTunes Search)
- **Metric skills** use your own data - you input numbers, the skill calculates and benchmarks

Install and start auditing in under 60 seconds.

### Optional API Integrations

7 skills support optional API keys for higher rate limits and richer data. If no keys are set, the free flow works exactly as before.

| Skill | Environment Variable | Service | What It Adds |
|-------|---------------------|---------|-------------|
| reddit-opportunity-finder | `REDDIT_CLIENT_ID` | Reddit OAuth | 60 req/min vs 1/2s |
| brand-mention-scanner | `REDDIT_CLIENT_ID`, `GITHUB_TOKEN` | Reddit OAuth, GitHub | Higher rate limits |
| geo-seo-auditor | `GOOGLE_API_KEY`, `AHREFS_API_KEY` | PageSpeed, Ahrefs | Real Core Web Vitals, backlink data |
| landing-page-cro | `GOOGLE_API_KEY` | PageSpeed Insights | Real performance scores |
| web-app-growth-engine | `GOOGLE_API_KEY`, `GOOGLE_ANALYTICS_JSON` | PageSpeed, GA4 | Performance + analytics data |
| aso-optimizer | `SENSOR_TOWER_API_KEY`, `APPSTORE_CONNECT_KEY_ID` | Sensor Tower, ASC | Keyword volume, downloads |
| competitor-intel | `SEMRUSH_API_KEY`, `SIMILARWEB_API_KEY` | SEMrush, SimilarWeb | Traffic, keywords, tech stack |

See each skill's `SKILL.md` for full setup instructions.

---

## Data Quality & Accuracy

> The more data you feed, the better results you get.

These skills are designed to work at two levels:

### Quick Mode (URL only)
Just pass a URL and get instant insights. Skills will scrape publicly available data - HTML, meta tags, structured data, App Store listings, Reddit threads - and generate a scored report with recommendations.

**This is great for a fast overview**, but the analysis is limited to what's publicly visible.

### Full Mode (connect your data)
For the most accurate results, feed your real business data:

| Skill | What to connect for best results |
|-------|----------------------------------|
| **Subscription Metrics** | RevenueCat, Stripe, or Baremetrics export (MRR, churn, ARPU, LTV) |
| **Pricing Analyzer** | Your actual pricing tiers, competitor pricing data, conversion rates per tier |
| **PLG Funnel Analyzer** | Real funnel metrics (signup-to-active %, free-to-paid %, NRR, churn rate) |
| **Retention Playbook** | Cohort data, churn reasons, customer segment breakdown |
| **Onboarding Optimizer** | Onboarding flow screenshots, activation funnel data, drop-off rates |
| **Review Sentiment** | Full review exports from App Store Connect, Google Play Console, G2, or Capterra |
| **ASO Optimizer** | App Store Connect keyword data, impression/conversion metrics |
| **Competitor Intel** | Internal competitive research, win/loss data, sales objections |

### Pro Tip: Connect Your APIs

For real-time, always-accurate data, you can extend these skills by connecting your own APIs:

- **App Store Connect API** - real keyword rankings, impression data, conversion rates
- **Google Search Console API** - actual search performance, click-through rates
- **RevenueCat / Stripe API** - live revenue metrics, churn data, subscription analytics
- **Google Business Profile API** - real review data, local SEO metrics
- **Reddit API (with auth)** - deeper thread analysis, comment sentiment

> **Bottom line:** These skills work out of the box with just a URL. But if you want results you can actually make business decisions on, connect your real data. The difference between a "good enough" audit and a "boardroom-ready" audit is the data you feed it.

---

## Case Study: Notion.com Full Audit

See the [Notion full audit](examples/notion-full-audit/) — 12 reports generated by running skills and agents on Notion.com, demonstrating what a complete SaaS growth audit looks like.

---

## Use Cases

- **SaaS Founders** - Audit your product's growth health across all dimensions
- **Growth Marketers** - Optimize funnels, pricing, and retention with data
- **Marketing Agencies** - Run client audits and generate scored reports
- **Indie Developers** - Launch apps with professional-grade ASO and landing pages
- **Content Teams** - Optimize for AI search engines (GEO)

---

## Requirements

- Python 3.8+
- Claude Code CLI (primary) or any Agent Skills-compatible tool
- Git
- Internet connection (for page fetching and public API scripts)

---

## Limitations

- **URL-based skills work best with server-rendered pages.** Client-side-only SPAs (pure React/Vue without SSR) may return incomplete results because content is loaded via JavaScript, not present in initial HTML.

- **ASO skill uses the free iTunes Search API by default.** It provides metadata quality analysis and competitor comparison, but does NOT provide keyword search volume, difficulty scores, or download estimates. Set `SENSOR_TOWER_API_KEY` or `APPSTORE_CONNECT_KEY_ID` to unlock these features.

- **Reddit and GitHub APIs have rate limits by default.** Reddit: 2-second delays between requests. GitHub: 10 requests per minute without auth. Set `REDDIT_CLIENT_ID` for 60 req/min or `GITHUB_TOKEN` for 30 req/min to remove these bottlenecks.

- **Sentiment analysis is keyword-based, not ML-based.** The review-sentiment and brand-mention-scanner use keyword matching for sentiment (not machine learning models). Results are directional, not precise.

- **Pricing analyzer requires manual input.** Competitor pricing cannot be auto-scraped reliably due to varied page formats. Users input competitor pricing data manually.

- **These skills are analysis tools, not monitoring services.** They run on-demand audits. For continuous monitoring, use dedicated SaaS tools.

---

## Compatible Tools

These skills follow the open [Agent Skills](https://github.com/anthropics/agent-skills) standard. While built and tested for **Claude Code**, they are also compatible with:

- Codex
- Gemini CLI
- Cursor
- Windsurf
- OpenCode
- Antigravity

---

## Contributing

Contributions are welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

All contributions must be relevant to SaaS growth, marketing, or business optimization.

---

## Author

**Mustafa Ekinci** - Growth marketer, builder, CMO. Building tools at the intersection of AI and growth marketing.

- X: [@ekinciio](https://x.com/ekinciio)
- GitHub: [ekinciio](https://github.com/ekinciio)

---

## License

MIT License - use freely, contribute back.

See [LICENSE](LICENSE) for details.
