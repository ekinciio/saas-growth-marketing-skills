# Volatile facts registry

Facts in this file change often: AI crawler tokens, store metadata limits, API access policies, Google Business Profile features, Core Web Vitals and the current Chrome version. Skills and agents must take these facts from here instead of hard-coding them, and must keep this file current.

Benchmarks (NRR, churn, conversion rates and so on) live in `saas-benchmarks.json` (`shared/benchmarks/` in this repo, `references/_shared/` in an installed skill).

## Rules

1. **Verify before stating.** If a row's `Last verified` date is more than 6 months old and WebSearch or WebFetch is available, check the source again before stating the fact, then update the row and its date. If the tools are not available, state the fact with its `Last verified` date ("as of 2026-10") so the reader can judge freshness.
2. **Cite the year** in reports, for example "OpenAI documents OAI-SearchBot as its search crawler (OpenAI bots page, checked 2026-10)".
3. **Only state facts marked `verified` as fact.** `secondary` means a reputable secondary source confirmed it but the primary page could not be read; say so. `unverified` means do not state it as fact.
4. **Only cite crawler tokens listed here.** If a user or a page mentions another token, verify it before repeating it, then add it here.
5. **Chrome moves every two weeks.** Re-check the Chrome row whenever it is more than 8 weeks (four major versions) old.
6. No em dashes or en dashes in this file; use a plain hyphen.

Status values: `verified` (primary source read on the date shown), `secondary` (only a secondary source could be read), `unverified` (could not be confirmed; listed so nobody re-adds it as fact).

## 1. AI crawler and user-agent tokens

Robots.txt matching of the user-agent token is case-insensitive (RFC 9309, section 2.2.1), so `meta-externalagent` and `Meta-ExternalAgent` name the same group. Under RFC 9309 a robots.txt that returns 4xx means "no rules, crawling allowed", while 5xx or a network failure means compliant crawlers "MUST assume complete disallow" (sections 2.3.1.3 and 2.3.1.4, https://www.rfc-editor.org/rfc/rfc9309.html, verified 2026-10-24). User-agent strings carry version numbers that change; match on the token, not the full string.

Type: `training` = collects data for model training; `search` = builds an index used to show and cite pages in AI answers; `user-fetch` = fetches a page because a user asked; `control` = a robots.txt token that changes how another crawler's data is used and does not crawl itself.

| Operator | Token | Type | What it controls | Honors robots.txt | IP list | Source | Last verified | Status |
|---|---|---|---|---|---|---|---|---|
| OpenAI | `GPTBot` | training | Content that may be used to train OpenAI foundation models; disallow = training opt-out | Yes (disallow is the documented opt-out) | https://openai.com/gptbot.json | https://developers.openai.com/api/docs/bots | 2026-10-24 | verified |
| OpenAI | `OAI-SearchBot` | search | Appearing in ChatGPT search answers; opted-out sites can still appear as navigational links; changes take about 24 hours | Yes | https://openai.com/searchbot.json | https://developers.openai.com/api/docs/bots | 2026-10-24 | verified |
| OpenAI | `ChatGPT-User` | user-fetch | Page visits for user actions in ChatGPT and Custom GPTs (GPT Actions); not automatic crawling | Robots.txt rules may not apply | https://openai.com/chatgpt-user.json | https://developers.openai.com/api/docs/bots | 2026-10-24 | verified |
| OpenAI | `OAI-AdsBot` | other | Checks landing pages submitted as ChatGPT ads for policy and relevance; only visits submitted ad pages; not used for training | Not stated | https://openai.com/adsbot.json | https://developers.openai.com/api/docs/bots | 2026-10-24 | verified |
| Anthropic | `ClaudeBot` | training | Public web content that could contribute to model training | Yes (Anthropic says its bots honor robots.txt) | https://claude.com/crawling/bots.json | https://support.claude.com/en/articles/8896518-does-anthropic-crawl-data-from-the-web-and-how-can-site-owners-block-the-crawler | 2026-10-24 | verified |
| Anthropic | `Claude-SearchBot` | search | Indexing to improve Claude's search results | Yes | https://claude.com/crawling/bots.json | same as above | 2026-10-24 | verified |
| Anthropic | `Claude-User` | user-fetch | Fetching a page when a Claude user's question needs it | Yes | https://claude.com/crawling/bots.json | same as above | 2026-10-24 | verified |
| Google | `Googlebot` | search | Google Search (including Discover, Images, Video, News). A page can be a supporting link in AI Overviews or AI Mode only if it is "indexed and eligible to be shown in Google Search with a snippet", with no extra requirements, so blocking Googlebot also removes it from those features | Yes | Not checked | https://developers.google.com/crawling/docs/crawlers-fetchers/google-common-crawlers and https://developers.google.com/search/docs/appearance/ai-features | 2026-10-24 | verified |
| Google | `Google-Extended` | control | Whether crawled content may be used to train Gemini models and for grounding. No separate user agent (uses Googlebot). Does not affect Search inclusion or ranking and does not remove a site from AI Overviews or AI Mode (use the Search Console control in section 2) | Yes (robots token) | n/a | same as above (page updated 2026-10-15) | 2026-10-24 | verified |
| Google | `Google-CloudVertexBot` | other | Crawls that site owners request to build Vertex AI Agents; no effect on Search | Yes | Not checked | same as above | 2026-10-24 | verified |
| Google | `GoogleOther` | other | Generic crawler for internal research; no product effect | Yes | Not checked | same as above | 2026-10-24 | verified |
| Google | `Google-Agent` | user-fetch | Agents hosted on Google infrastructure that browse and act on a user's request | Generally ignores robots.txt | https://developers.google.com/static/crawling/ipranges/user-triggered-agents.json | https://developers.google.com/crawling/docs/crawlers-fetchers/google-user-triggered-fetchers | 2026-10-24 | verified |
| Google | `Google-GeminiNotebook` | user-fetch | URLs that Gemini Notebook users add as sources. Former token `Google-NotebookLM` was supported until August 2026 | Generally ignores robots.txt | Not checked | same as above (page updated 2026-08-19) | 2026-10-24 | verified |
| Google | `Google-Read-Aloud` | user-fetch | Reads pages aloud on user request (former token `google-speakr` is deprecated) | Generally ignores robots.txt | Not checked | same as above | 2026-10-24 | verified |
| Perplexity | `PerplexityBot` | search | Surfacing and linking sites in Perplexity results; not used to train foundation models | Yes | https://www.perplexity.com/perplexitybot.json | https://docs.perplexity.ai/docs/resources/perplexity-crawlers | 2026-10-24 | verified |
| Perplexity | `Perplexity-User` | user-fetch | Visiting pages to answer a user's question; not crawling or training | Generally ignores robots.txt | https://www.perplexity.com/perplexity-user.json | https://docs.perplexity.ai/docs/resources/perplexity-crawlers | 2026-10-24 | verified |
| Apple | `Applebot` | search | Spotlight, Siri and Safari search features; Apple says the data may also be used to train Apple foundation models | Yes | Not checked | https://support.apple.com/en-us/119829 (published 2026-09-04) | 2026-10-24 | verified |
| Apple | `Applebot-Extended` | control | Disallow to opt out of Applebot data being used to train Apple's generative foundation models; does not crawl; no effect on search inclusion or ranking | Yes (robots token) | n/a | https://support.apple.com/en-us/119829 | 2026-10-24 | verified |
| Meta | `Meta-ExternalAgent` | training | Training foundation AI models and improving products by indexing content | Yes (block with a disallow rule) | Not checked | https://developers.facebook.com/docs/sharing/webmasters/web-crawlers | 2026-10-24 | verified |
| Meta | `Meta-WebIndexer` | search | Improving Meta AI search results; allowing it helps Meta cite and link the site | Not stated | Not checked | same as above | 2026-10-24 | verified |
| Meta | `Meta-ExternalFetcher` | user-fetch | Fetches individual links at a user's request for agentic AI features | May bypass robots.txt | Not checked | same as above | 2026-10-24 | verified |
| Meta | `facebookexternalhit` | other | Link previews (title, description, thumbnail) for shared links | Generally yes; may bypass for security or integrity checks | Not checked | same as above | 2026-10-24 | verified |
| Meta | `Meta-ExternalAds` | other | Advertising and other business products | Yes (robots rules documented) | Not checked | same as above | 2026-10-24 | verified |
| Amazon | `Amazonbot` | training | Improving Amazon products and services; "may be used to train Amazon AI models" | Yes | https://developer.amazon.com/amazonbot/ip-addresses/ | https://developer.amazon.com/amazonbot | 2026-10-24 | verified |
| Amazon | `Amzn-SearchBot` | search | Search experiences in Amazon products; not used for generative AI training. If not named, it follows the rules for other search bots | Yes | https://developer.amazon.com/amazonbot/searchbot-ip-addresses/ | https://developer.amazon.com/amazonbot | 2026-10-24 | verified |
| Amazon | `Amzn-User` | user-fetch | User actions such as Alexa queries that need fresh information; not for training | May not follow all directives | https://developer.amazon.com/amazonbot/live-ip-addresses/ | https://developer.amazon.com/amazonbot | 2026-10-24 | verified |
| Common Crawl | `CCBot` | training | Builds the open Common Crawl web repository; whoever reuses that data is outside the site's control. Robots.txt disallow (or the Opt-Out Registry) is the documented opt-out | Robots.txt is the documented opt-out | https://index.commoncrawl.org/ccbot.json (reverse DNS `*.crawl.commoncrawl.org`) | https://commoncrawl.org/ccbot | 2026-10-24 | verified |
| DuckDuckGo | `DuckAssistBot` | search | Real-time crawling for DuckDuckGo's AI-assisted answers; "not used in any way to train AI models"; robots.txt changes take effect after 72 hours | Robots.txt is the documented opt-out | Not checked | https://duckduckgo.com/duckduckgo-help-pages/results/duckassistbot | 2026-10-24 | verified |
| Mistral | `MistralAI-User` | user-fetch | Pages visited when a user asks Mistral's assistant a question; not for training | Not stated | https://mistral.ai/mistralai-user-ips.json | https://docs.mistral.ai/robots/ | 2026-10-24 | verified |
| Mistral | `MistralAI-Index` | search | Automatic crawling to index for Mistral search; not for training | Not stated | https://mistral.ai/mistralai-index-ips.json | https://docs.mistral.ai/robots/ | 2026-10-24 | verified |
| Mistral | `MistralAI-Training` | training | Crawls content to build Mistral training datasets | Yes (disallow documented) | Not published | https://docs.mistral.ai/robots/ | 2026-10-24 | verified |
| Microsoft | `bingbot` | search | Bing has no separate AI token. Copilot and grounding use is controlled with meta robots: `NOARCHIVE` keeps content out of Copilot responses and grounding results; `NOCACHE` limits Copilot to URL, title and snippet | Yes | Not checked | https://www.searchenginejournal.com/bing-adds-geo-to-official-guidelines-expands-ai-abuse-definitions/568442 (summary of Bing Webmaster Guidelines, 2026-02-27; Bing's own page is JavaScript-rendered and could not be read) | 2026-10-24 | secondary |
| ByteDance | `Bytespider` | training (reported) | Reported by third parties as ByteDance's data crawler; robots.txt compliance is disputed | Disputed | Not found | No official ByteDance page found | 2026-10-24 | unverified |

Not on the operators' current pages (do not recommend rules for them without a new check): `anthropic-ai` and `Claude-Web` (Anthropic lists only the three tokens above), `cohere-ai` and `cohere-training-data-crawler` (not checked).

## 2. Google and Bing AI search controls

| Fact | Value | Source | Last verified | Status |
|---|---|---|---|---|
| Search Console "Search generative AI" control | Settings > Search generative AI. Include (default) or Exclude for AI Overviews, AI Mode and generative AI features in Discover. Exclude withholds links and content and gives no traffic or impressions from those features. It does not affect AI training (that is `Google-Extended`); `noindex` is the way to leave Search completely. Rolled out to all websites worldwide as of 2026-08-31; exclusion takes effect within 1-2 days | https://support.google.com/webmasters/answer/16908024 | 2026-10-24 | verified |
| Search generative AI performance reports | Launched 2026-06-03 for a subset of sites; all websites worldwide as of 2026-08-31. Shows impressions in AI features for Search and Discover, by page, country, device and date (no clicks listed in the launch post) | https://developers.google.com/search/blog/2026/06/gen-ai-performance-reports | 2026-10-24 | verified |
| Preview controls | `nosnippet`, `data-nosnippet`, `max-snippet` and `noindex` limit what Google Search shows from a page, including in AI features; Google-Extended limits training and grounding in other Google systems | https://developers.google.com/search/docs/appearance/ai-features (updated 2025-12-10) | 2026-10-24 | verified |
| Bing / Copilot | `NOARCHIVE` keeps content out of Copilot responses and grounding; `NOCACHE` limits Copilot to URL, title and snippet; Bing advises against `NOCACHE` on pages you want cited richly | https://www.searchenginejournal.com/bing-adds-geo-to-official-guidelines-expands-ai-abuse-definitions/568442 | 2026-10-24 | secondary |

## 3. App Store and Google Play metadata limits

| Store | Field | Limit | Source | Last verified | Status |
|---|---|---|---|---|---|
| App Store | App name | 2-30 characters | https://developer.apple.com/help/app-store-connect/reference/app-information/app-information | 2026-10-24 | verified |
| App Store | Subtitle | 30 characters | same as above | 2026-10-24 | verified |
| App Store | Keywords | 100 bytes (not characters: multi-byte scripts fit fewer keywords); each keyword longer than two characters | https://developer.apple.com/help/app-store-connect/reference/app-information/platform-version-information | 2026-10-24 | verified |
| App Store | Promotional text | 170 characters; can be changed without a new app submission | same as above | 2026-10-24 | verified |
| App Store | Description | 4,000 characters | same as above | 2026-10-24 | verified |
| App Store | What's New | 4,000 characters | same as above | 2026-10-24 | verified |
| App Store | In-app purchase display name / description / reference name | 2-30 / 45 / 64 characters | https://developer.apple.com/help/app-store-connect/reference/in-app-purchases-and-subscriptions/in-app-purchase-information | 2026-10-24 | verified |
| App Store | Custom product pages | Up to 70 per app; keywords can be assigned so a custom page appears in search results for those keywords; deep links need iOS/iPadOS 18+ | https://developer.apple.com/app-store/custom-product-pages/ | 2026-10-24 | verified |
| App Store | Developer (seller) name length | No limit found in the App Store Connect references checked; do not validate a 50-character limit | references above | 2026-10-24 | unverified |
| Google Play | App name | 30 characters (full- and half-width count the same) | https://support.google.com/googleplay/android-developer/answer/9859152 | 2026-10-24 | verified |
| Google Play | Short description | 80 characters | same as above | 2026-10-24 | verified |
| Google Play | Full description | 4,000 characters | same as above | 2026-10-24 | verified |
| Google Play | Release notes | 500 Unicode characters per language | https://support.google.com/googleplay/android-developer/answer/9859348 | 2026-10-24 | verified |
| Google Play | Metadata policy (title, icon, developer name) | Title 30 characters or less. No emoji, emoticons or repeated special characters; no ALL CAPS unless part of the brand; no store performance or ranking claims ("App of the year", "#1", "Best of Play 20XX", "Popular", award icons); no price or promotion text ("10% off", "free for limited time only"); nothing suggesting a Google Play program; no download/install symbols unless the app is about downloading | https://support.google.com/googleplay/android-developer/answer/9898842 | 2026-10-24 | verified |
| Google Play | Custom store listings | Up to 50, targeted by country, user or buyer state, or search keyword; Play Console can deploy Gemini-generated listings for recommended keywords | https://google.play/business/storelistings/ | 2026-10-24 | verified |

## 4. Reddit API access

| Fact | Value | Source | Last verified | Status |
|---|---|---|---|---|
| Self-service API access | Closed on 2025-11-11 with the Responsible Builder Policy. New OAuth credentials need Reddit's approval; existing access was not affected. Developers are pointed to Devvit first; researchers and moderators have request forms | r/redditdev, "Introducing the Responsible Builder Policy" (2025-11-11), read through search-engine excerpts; reddit.com, redditinc.com and the Reddit help center block automated fetches | 2026-10-24 | secondary |
| Unauthenticated JSON endpoints | `www.reddit.com/...json` returned HTTP 403 to a scripted request on 2026-10-24 | Direct request from this machine | 2026-10-24 | verified (observed) |
| OAuth rate limit | 100 queries per minute per OAuth client id, averaged over 10 minutes; 10 QPM without OAuth | Reddit's 2023 API update (r/modnews, 2023-05-31) seen through search excerpts; current Data API wiki could not be read | 2026-10-24 | unverified |
| Commercial use | Requires a separate agreement with Reddit; pricing (often quoted as $0.24 per 1,000 calls) is at Reddit's discretion | Secondary summaries of the Data API Terms only | 2026-10-24 | unverified |
| Model training on Reddit content | Data API Terms bar training ML/AI models on user content without permission | Secondary summaries only | 2026-10-24 | unverified |

Practical default: assume most users cannot get Reddit API keys. Treat WebSearch (`site:reddit.com`) and the public RSS search as the normal path and the OAuth API as optional.

## 5. Other API limits

| Fact | Value | Source | Last verified | Status |
|---|---|---|---|---|
| GitHub search API | 30 requests/minute authenticated (code search: 10/minute, authentication required); 10 requests/minute unauthenticated; at most 1,000 results per search | https://docs.github.com/en/rest/search/search | 2026-10-24 | verified |
| Hacker News (Algolia) API rate limit | Often quoted as 10,000 requests/hour per IP | https://hn.algolia.com/api renders client-side and could not be read | 2026-10-24 | unverified |
| PageSpeed Insights API | INP is field data only (`loadingExperience.metrics.INTERACTION_TO_NEXT_PAINT`, 28-day CrUX window, 75th percentile). Lighthouse lab metrics are FCP, LCP, Speed Index, CLS, TTI and TBT, so a lab run has no INP. `EXPERIMENTAL_INTERACTION_TO_NEXT_PAINT` was removed from the API on 2023-08-08 | https://developers.google.com/speed/docs/insights/v5/about and https://developers.google.com/speed/docs/insights/release_notes | 2026-10-24 | verified |

## 6. Google Business Profile and other local listings

| Fact | Value | Source | Last verified | Status |
|---|---|---|---|---|
| GBP chat and call history | Removed from Business Profiles on 2024-07-31 (Google Business Messages was wound down the same day). Calls from the profile still work | https://support.google.com/business/answer/14919056 | 2026-10-24 | verified |
| GBP chat replacement | Optional WhatsApp or text-message chat link, available only in select regions; if both are added only text message shows; no response-time requirement is stated | https://support.google.com/business/answer/15013580 | 2026-10-24 | verified |
| GBP Questions and answers | The My Business Q&A API was discontinued on 2025-11-03 "as we are in the process of updating the Q&A functionality and user experience" | https://developers.google.com/my-business/content/qanda/change-log | 2026-10-24 | verified |
| GBP Q&A on Maps | Public Q&A replaced by a Gemini-powered "Ask" experience that answers from the profile, website and reviews; owners can no longer post answers. Rollout dates and coverage differ between reports | Trade press (PPC Land, Whitespark, BrightLocal); no Google announcement found | 2026-10-24 | secondary |
| Apple Business | Apple's support guide says "Apple Business Connect is now Apple Business"; it combines Apple Business Manager, Apple Business Essentials and Apple Business Connect. Trade press dates the launch to late March 2026 | https://support.apple.com/guide/apple-business-connect/welcome/web; IT Brief (2026-03-29) for the date | 2026-10-24 | verified (rename) / secondary (date) |

## 7. Core Web Vitals

| Metric | Good | Poor | Notes | Source | Last verified | Status |
|---|---|---|---|---|---|---|
| LCP (Largest Contentful Paint) | <= 2.5 s | > 4.0 s | Assessed at the 75th percentile of page loads, mobile and desktop separately | https://web.dev/articles/defining-core-web-vitals-thresholds (updated 2025-05-07) | 2026-10-24 | verified |
| INP (Interaction to Next Paint) | <= 200 ms | > 500 ms | Replaced FID as a Core Web Vital on 2024-03-12 (https://web.dev/blog/inp-cwv-march-12). Field data only | same as above | 2026-10-24 | verified |
| CLS (Cumulative Layout Shift) | <= 0.1 | > 0.25 | | same as above | 2026-10-24 | verified |

Values between Good and Poor are "needs improvement". A page passes only when all three are Good at the 75th percentile of real-user (CrUX) data; lab scores cannot decide pass or fail.

## 8. Chrome stable version (for browser-like User-Agent strings)

| Fact | Value | Source | Last verified | Status |
|---|---|---|---|---|
| Current Chrome stable major | **156** (early-stable rollout from 2026-10-07; 156.0.8078.48 at fraction 1.0 in one Windows/Mac rollout group since 2026-10-20, while another group still served 155 to about 74% on 2026-10-24). Chrome 157 (157.0.8103.15) started an early-stable rollout to 0.5% on 2026-10-22. Use the newest major that is broadly serving, not the 0.5% early-stable one | https://versionhistory.googleapis.com/v1/chrome/platforms/win/channels/stable/versions/all/releases?filter=endtime=none | 2026-10-24 | verified |
| Release cadence | A new major every two weeks since Chrome 153 (stable 2026-09-08); Extended Stable stays on an eight-week cycle | https://developer.chrome.com/blog/chrome-two-week-release (2026-03-03) | 2026-10-24 | verified |
| Reduced UA format | `Mozilla/5.0 (<platform>) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/<major>.0.0.0 Safari/537.36`, platform `Windows NT 10.0; Win64; x64` or `Macintosh; Intel Mac OS X 10_15_7` | https://www.chromium.org/updates/ua-reduction/ | 2026-10-24 | verified |

Current desktop string to use in one shared constant:

```
Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/156.0.0.0 Safari/537.36
```

To re-check the major version, list the stable releases that are serving now to at least half of a rollout group:

```bash
curl -s "https://versionhistory.googleapis.com/v1/chrome/platforms/win/channels/stable/versions/all/releases?filter=endtime=none,fraction%3E=0.5"
```

On 2026-10-24 this returned only `156.0.8078.48` (fraction 1). Do not use `.../stable/versions?pageSize=1`: it returns the newest stable version even while it is a 0.5% early-stable rollout (it returned `157.0.8103.15` the same day).

A current UA string is hygiene, not a way past bot protection: in the 2026-10 audit, sites that returned 403 (for example GitHub and Canva) blocked every UA tested. Report a 403 as "blocked by bot protection", not as a rendering problem.

## 9. Where these facts are hard-coded today

Line numbers are against commit `c6eb6b2`; commit `7340be2` and later batches change some of these files (for example `cro_auditor.py`), so re-grep before changing them. Each of these should read from this registry (or from the shared library constant built from it).

| Fact | File:line (c6eb6b2) | Problem |
|---|---|---|
| Chrome UA | `skills/competitor-intel/scripts/competitor_scanner.py:79`, `skills/landing-page-cro/scripts/cro_auditor.py:61`, `skills/saas-landing-builder/scripts/page_structure_analyzer.py:264`, `skills/web-app-growth-engine/scripts/signup_auditor.py:179` | Chrome/138 (June 2025), 18 majors behind 156 |
| Crawler roster | `skills/geo-seo-auditor/scripts/crawler_checker.py:30-169`, `:470-472`, `:492`, `:511-512`, `:524`; `skills/geo-seo-auditor/references/ai-crawlers.md` (for example `:33`, `:325`) | Amazonbot labelled `search` (Amazon now says it may train models); missing `Amzn-SearchBot`, `Amzn-User`, `Meta-WebIndexer`, `Meta-ExternalFetcher`, `Google-Agent`, `Google-GeminiNotebook`, `OAI-AdsBot`, `MistralAI-Index`, `MistralAI-Training`, `Googlebot`, `Applebot`; user-fetch tokens treated as robots-controlled |
| App Store / Play limits | `skills/aso-optimizer/scripts/metadata_validator.py:34-40` (iOS), `:44-47` (Play) | iOS limits match, except `developer_name: 50` (no documented limit); Play `whats_new: 500` matches |
| Core Web Vitals | `skills/landing-page-cro/SKILL.md:280`, `skills/web-app-growth-engine/SKILL.md:178-180` | Read INP from Lighthouse lab audits; INP exists only in field data. Thresholds in `skills/landing-page-cro/references/cro-checklist.md:63-65` and `skills/landing-page-cro/SKILL.md:284` are correct |
| GBP chat | `skills/local-seo-optimizer/scripts/local_seo_scorer.py:78-79`, `skills/local-seo-optimizer/references/gbp-audit-checklist.md:78-79` and `:111`, `skills/local-seo-optimizer/references/local-ranking-factors.md:182`, `skills/local-seo-optimizer/SKILL.md:73`, `:155`, `:234` | Score and recommend the GBP chat feature removed on 2024-07-31 and a 24-hour response rule that no longer exists |
| Reddit access | `README.md:21` and `:151-163` ("No API keys required") vs `README.md:249`; `skills/brand-mention-scanner/SKILL.md:156`, `:209`, `:215-217`; `skills/brand-mention-scanner/references/platform-search-urls.md:44` | 100 QPM is unverified for 2026; new credentials need approval, so the keyless claim misleads |
