# AI Search Engine Crawlers Reference

This document lists known AI crawler and control tokens, their operators, and how to manage them through robots.txt.

Categories used below:

- **training** - collects content for AI model training
- **search** - indexes content for AI search/answer products (blocking removes you from those answers)
- **user-fetch** - fetches a page only when a user explicitly asks an AI assistant to open it
- **training-control** - a robots.txt opt-out *token*, not a crawler; honored by another bot
- **other** - miscellaneous (R&D, etc.)

## Crawler Directory

### 1. GPTBot (OpenAI)

- **User-Agent token:** `GPTBot`
- **Full User-Agent String:** `Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; GPTBot/1.4; +https://openai.com/gptbot)`
- **Category:** training
- **Purpose:** Crawls web pages for training OpenAI's models

```
User-agent: GPTBot
Allow: /
# or: Disallow: /
```

---

### 2. OAI-SearchBot (OpenAI)

- **User-Agent token:** `OAI-SearchBot`
- **Full User-Agent String:** `Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36; compatible; OAI-SearchBot/1.4; +https://openai.com/searchbot` (Chrome-like full UA)
- **Category:** search
- **Purpose:** Indexes pages for ChatGPT search. Blocking it removes your site from ChatGPT search results, but does not affect model training (that is GPTBot).

```
User-agent: OAI-SearchBot
Allow: /
```

---

### 3. ChatGPT-User (OpenAI)

- **User-Agent token:** `ChatGPT-User`
- **Category:** user-fetch
- **Purpose:** Fetches a page when a ChatGPT user explicitly asks for it (browsing, GPT Actions). Blocking it breaks link opening for users who already know your site.

```
User-agent: ChatGPT-User
Allow: /
```

---

### 4. ClaudeBot (Anthropic)

- **User-Agent token:** `ClaudeBot`
- **Full User-Agent String:** `Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; ClaudeBot/1.0; +claudebot@anthropic.com)`
- **Category:** training
- **Purpose:** Crawls publicly available web content for training Anthropic's models
- **Verification:** Anthropic publishes crawler IP ranges at https://claude.com/crawling/bots.json

```
User-agent: ClaudeBot
Allow: /
```

---

### 5. Claude-SearchBot (Anthropic)

- **User-Agent token:** `Claude-SearchBot`
- **Category:** search
- **Purpose:** Indexes pages to improve Claude's search results. Blocking it reduces your visibility in Claude's web search answers.

```
User-agent: Claude-SearchBot
Allow: /
```

---

### 6. Claude-User (Anthropic)

- **User-Agent token:** `Claude-User`
- **Category:** user-fetch
- **Purpose:** Fetches a page when a Claude user explicitly asks for it.

```
User-agent: Claude-User
Allow: /
```

---

### 7. PerplexityBot (Perplexity)

- **User-Agent token:** `PerplexityBot`
- **Full User-Agent String:** `Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; PerplexityBot/1.0; +https://perplexity.ai/perplexitybot)`
- **Category:** search
- **Purpose:** Indexes content for Perplexity's answer engine. Perplexity states this crawler is used for search indexing, not model training.

```
User-agent: PerplexityBot
Allow: /
```

---

### 8. Perplexity-User (Perplexity)

- **User-Agent token:** `Perplexity-User`
- **Category:** user-fetch
- **Purpose:** Fetches a page when a Perplexity user explicitly opens or cites it.

```
User-agent: Perplexity-User
Allow: /
```

---

### 9. Google-Extended (Google)

- **User-Agent token:** `Google-Extended`
- **Category:** training-control
- **Purpose:** A robots.txt opt-out *token*, not a separate crawler - it is honored by Googlebot. Blocking it opts your content out of Gemini model **training and grounding**.
- **What it does NOT do:** Google-Extended does **not** affect Google Search inclusion, AI Overviews, or AI Mode. Inclusion in AI Overviews/AI Mode is governed by normal Googlebot access plus snippet controls (`nosnippet`, `data-nosnippet`, `max-snippet`, `noindex`).

```
# Opt out of Gemini training/grounding only:
User-agent: Google-Extended
Disallow: /
```

**Note:** To appear in AI Overviews, keep Googlebot allowed and avoid restrictive snippet controls. Blocking Google-Extended neither removes you from nor adds you to AI Overviews.

---

### 10. GoogleOther (Google)

- **User-Agent token:** `GoogleOther`
- **Category:** other
- **Purpose:** Google's generic token for R&D and internal one-off crawls.

```
User-agent: GoogleOther
Allow: /
```

---

### 11. Google-CloudVertexBot (Google)

- **User-Agent token:** `Google-CloudVertexBot`
- **Category:** training
- **Purpose:** Crawls sites on request of Google Cloud Vertex AI customers building AI agents (site ingestion).

```
User-agent: Google-CloudVertexBot
Allow: /
```

---

### 12. bingbot (Microsoft)

- **User-Agent token:** `bingbot`
- **Category:** search
- **Purpose:** Bing's main search crawler, which also powers Microsoft Copilot answers. **Blocking bingbot removes you from both Bing Search and Copilot visibility** - there is no separate Copilot-only crawler to allow.

```
User-agent: bingbot
Allow: /
```

---

### 13. meta-externalagent (Meta)

- **User-Agent token:** `meta-externalagent`
- **Category:** training
- **Purpose:** AI training and content indexing for Meta AI. Replaces the legacy FacebookBot token.

```
User-agent: meta-externalagent
Allow: /
```

---

### 14. meta-externalfetcher (Meta)

- **User-Agent token:** `meta-externalfetcher`
- **Category:** user-fetch
- **Purpose:** User-initiated link fetches from Meta AI products.

```
User-agent: meta-externalfetcher
Allow: /
```

---

### 15. Applebot-Extended (Apple)

- **User-Agent token:** `Applebot-Extended`
- **Category:** training-control
- **Purpose:** An opt-out *token*, not a crawler - it does not crawl; the standard `Applebot` does. Blocking Applebot-Extended opts your content out of Apple Intelligence / foundation model training while keeping Applebot crawling for Siri and Spotlight.

```
# Opt out of Apple AI training only:
User-agent: Applebot-Extended
Disallow: /
```

---

### 16. Amazonbot (Amazon)

- **User-Agent token:** `Amazonbot`
- **Full User-Agent String:** `Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) AppleWebKit/600.2.5 (KHTML, like Gecko) Version/8.0.2 Safari/600.2.5 (Amazonbot/0.1; +https://developer.amazon.com/support/amazonbot)`
- **Category:** search
- **Purpose:** Indexes web content for Alexa and Amazon AI answers.

```
User-agent: Amazonbot
Allow: /
```

---

### 17. Bytespider (ByteDance)

- **User-Agent token:** `Bytespider`
- **Full User-Agent String:** `Mozilla/5.0 (Linux; Android 5.0) AppleWebKit/537.36 (KHTML, like Gecko; compatible; Bytespider; spider-feedback@bytedance.com)`
- **Category:** training
- **Purpose:** Model training for ByteDance AI products. Widely reported to have **poor robots.txt compliance** - robots.txt alone may not stop it; consider server-level blocking if you need to exclude it.

```
User-agent: Bytespider
Disallow: /
```

---

### 18. CCBot (Common Crawl)

- **User-Agent token:** `CCBot`
- **Full User-Agent String:** `CCBot/2.0 (https://commoncrawl.org/faq/)`
- **Category:** training
- **Purpose:** Builds the open Common Crawl corpus, which is widely used as AI training data. Blocking CCBot reduces your content's presence across many AI systems at once.

```
User-agent: CCBot
Allow: /
```

---

### 19. DuckAssistBot (DuckDuckGo)

- **User-Agent token:** `DuckAssistBot`
- **Category:** search
- **Purpose:** Fetches content for DuckAssist AI-generated answers on DuckDuckGo.

```
User-agent: DuckAssistBot
Allow: /
```

---

### 20. MistralAI-User (Mistral)

- **User-Agent token:** `MistralAI-User`
- **Category:** user-fetch
- **Purpose:** Fetches pages for citations when Le Chat users ask about web content.

```
User-agent: MistralAI-User
Allow: /
```

---

### 21. cohere-training-data-crawler (Cohere)

- **User-Agent token:** `cohere-training-data-crawler`
- **Category:** training
- **Purpose:** Crawls web content for training Cohere's enterprise models. (Note: `cohere-ai` was never an official Cohere token.)

```
User-agent: cohere-training-data-crawler
Allow: /
```

---

### Long-tail bots

A number of niche data-platform bots also crawl for AI-adjacent purposes: `Timpibot` (Timpi decentralized search), `webzio-extended` (Webz.io data platform), and `Diffbot` (knowledge-graph extraction). They have negligible impact on AI search visibility; set a policy for them only if you have a specific reason.

## Quick Reference Table

| Token | Operator | Purpose | Category |
|---|---|---|---|
| GPTBot | OpenAI | Model training | training |
| OAI-SearchBot | OpenAI | ChatGPT search indexing | search |
| ChatGPT-User | OpenAI | User-initiated fetches / GPT Actions | user-fetch |
| ClaudeBot | Anthropic | Model training | training |
| Claude-SearchBot | Anthropic | Claude search indexing | search |
| Claude-User | Anthropic | User-initiated fetches | user-fetch |
| PerplexityBot | Perplexity | Search indexing (not training) | search |
| Perplexity-User | Perplexity | User-initiated fetches | user-fetch |
| Google-Extended | Google | Gemini training + grounding opt-out token (not a crawler; does NOT govern AI Overviews) | training-control |
| GoogleOther | Google | R&D crawls | other |
| Google-CloudVertexBot | Google | Vertex AI site ingestion | training |
| bingbot | Microsoft | Bing Search + Copilot answers (blocking removes Copilot visibility) | search |
| meta-externalagent | Meta | AI training + indexing (replaces FacebookBot) | training |
| meta-externalfetcher | Meta | User-initiated link fetches | user-fetch |
| Applebot-Extended | Apple | Apple Intelligence training opt-out token (doesn't crawl; Applebot does) | training-control |
| Amazonbot | Amazon | Alexa/AI answers | search |
| Bytespider | ByteDance | Model training (poor robots.txt compliance) | training |
| CCBot | Common Crawl | Open corpus widely used for AI training | training |
| DuckAssistBot | DuckDuckGo | DuckAssist AI answers | search |
| MistralAI-User | Mistral | Le Chat citation fetches | user-fetch |
| cohere-training-data-crawler | Cohere | Model training | training |

## Recommended robots.txt Strategy

For maximum AI search visibility, allow the search-facing and user-fetch crawlers:

```
# AI search and answer engines
User-agent: OAI-SearchBot
Allow: /

User-agent: Claude-SearchBot
Allow: /

User-agent: PerplexityBot
Allow: /

User-agent: bingbot
Allow: /

User-agent: DuckAssistBot
Allow: /

User-agent: Amazonbot
Allow: /

# User-initiated fetchers
User-agent: ChatGPT-User
Allow: /

User-agent: Claude-User
Allow: /

User-agent: Perplexity-User
Allow: /

User-agent: MistralAI-User
Allow: /
```

For selective access, allow search-facing crawlers and block training-only crawlers:

```
# Allow search-facing crawlers
User-agent: OAI-SearchBot
Allow: /

User-agent: Claude-SearchBot
Allow: /

User-agent: PerplexityBot
Allow: /

User-agent: bingbot
Allow: /

# Block training-only crawlers
User-agent: GPTBot
Disallow: /

User-agent: ClaudeBot
Disallow: /

User-agent: CCBot
Disallow: /

User-agent: Bytespider
Disallow: /

User-agent: meta-externalagent
Disallow: /

# Opt-out tokens for Gemini and Apple Intelligence training
User-agent: Google-Extended
Disallow: /

User-agent: Applebot-Extended
Disallow: /
```

**Important:** none of the above affects Google AI Overviews. AI Overviews inclusion is controlled by regular Googlebot access and snippet controls (`nosnippet`, `data-nosnippet`, `max-snippet`, `noindex`), not by any AI-specific token.
