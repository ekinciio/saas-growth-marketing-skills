# AI Search Engine Crawlers Reference

This document lists known AI crawlers, their associated platforms, and how to manage their access through robots.txt.

## Crawler Directory

### 1. GPTBot (OpenAI)

- **User-Agent:** `GPTBot`
- **Full User-Agent String:** `Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; GPTBot/1.2; +https://openai.com/gptbot)`
- **Platform:** OpenAI - Used for training data collection for GPT models
- **Purpose:** Crawls web pages to improve AI model accuracy and capabilities

**robots.txt configuration:**
```
# Allow GPTBot
User-agent: GPTBot
Allow: /

# Block GPTBot
User-agent: GPTBot
Disallow: /
```

---

### 2. OAI-SearchBot (OpenAI)

- **User-Agent:** `OAI-SearchBot`
- **Full User-Agent String:** `Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; OAI-SearchBot/1.0; +https://openai.com/searchbot)`
- **Platform:** OpenAI - Used for ChatGPT's real-time web search feature
- **Purpose:** Fetches pages in real time when users ask ChatGPT to search the web

**robots.txt configuration:**
```
# Allow OAI-SearchBot
User-agent: OAI-SearchBot
Allow: /

# Block OAI-SearchBot
User-agent: OAI-SearchBot
Disallow: /
```

**Note:** Blocking OAI-SearchBot prevents your site from appearing in ChatGPT search results, but does not affect GPT model training (that is GPTBot).

---

### 3. ClaudeBot (Anthropic)

- **User-Agent:** `ClaudeBot`
- **Full User-Agent String:** `Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; ClaudeBot/1.0; +https://www.anthropic.com/claud-bot)`
- **Platform:** Anthropic - Used for Claude AI training and web features
- **Purpose:** Crawls publicly available web content for AI model improvement

**robots.txt configuration:**
```
# Allow ClaudeBot
User-agent: ClaudeBot
Allow: /

# Block ClaudeBot
User-agent: ClaudeBot
Disallow: /
```

---

### 4. PerplexityBot (Perplexity AI)

- **User-Agent:** `PerplexityBot`
- **Full User-Agent String:** `Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; PerplexityBot/1.0; +https://perplexity.ai/perplexitybot)`
- **Platform:** Perplexity AI - Used for real-time search and answer generation
- **Purpose:** Fetches and indexes web content for Perplexity's AI search engine

**robots.txt configuration:**
```
# Allow PerplexityBot
User-agent: PerplexityBot
Allow: /

# Block PerplexityBot
User-agent: PerplexityBot
Disallow: /
```

---

### 5. Google-Extended (Google)

- **User-Agent:** `Google-Extended`
- **Platform:** Google - Controls whether content is used for Gemini and AI Overviews
- **Purpose:** Separate from Googlebot; specifically governs AI training and generative features

**robots.txt configuration:**
```
# Allow Google-Extended
User-agent: Google-Extended
Allow: /

# Block Google-Extended (blocks AI use but keeps regular search indexing)
User-agent: Google-Extended
Disallow: /
```

**Note:** Blocking Google-Extended does NOT affect your regular Google Search rankings. It only prevents content from being used in Gemini models and AI Overviews.

---

### 6. Bytespider (TikTok/ByteDance)

- **User-Agent:** `Bytespider`
- **Full User-Agent String:** `Mozilla/5.0 (Linux; Android 5.0) AppleWebKit/537.36 (KHTML, like Gecko; compatible; Bytespider; spider-feedback@bytedance.com)`
- **Platform:** ByteDance/TikTok - Used for AI model training and content indexing
- **Purpose:** Crawls web content for ByteDance's various AI products

**robots.txt configuration:**
```
# Allow Bytespider
User-agent: Bytespider
Allow: /

# Block Bytespider
User-agent: Bytespider
Disallow: /
```

---

### 7. CCBot (Common Crawl)

- **User-Agent:** `CCBot`
- **Full User-Agent String:** `CCBot/2.0 (https://commoncrawl.org/faq/)`
- **Platform:** Common Crawl - Open dataset used by many AI companies for training
- **Purpose:** Builds an open web archive used as training data by numerous AI models

**robots.txt configuration:**
```
# Allow CCBot
User-agent: CCBot
Allow: /

# Block CCBot
User-agent: CCBot
Disallow: /
```

**Note:** Common Crawl data is used by many AI projects. Blocking CCBot may reduce your content's presence across multiple AI systems.

---

### 8. Amazonbot (Amazon)

- **User-Agent:** `Amazonbot`
- **Full User-Agent String:** `Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) AppleWebKit/537.36 (KHTML, like Gecko; compatible; Amazonbot/0.1; +https://developer.amazon.com/amazonbot)`
- **Platform:** Amazon - Used for Alexa AI answers and Amazon search
- **Purpose:** Indexes web content for Alexa voice responses and Amazon product search

**robots.txt configuration:**
```
# Allow Amazonbot
User-agent: Amazonbot
Allow: /

# Block Amazonbot
User-agent: Amazonbot
Disallow: /
```

---

### 9. FacebookBot (Meta)

- **User-Agent:** `FacebookBot`
- **Full User-Agent String:** `Mozilla/5.0 (compatible; FacebookBot/1.0; +https://www.facebook.com/externalhit_uatext.php)`
- **Platform:** Meta - Used for AI features across Facebook, Instagram, and WhatsApp
- **Purpose:** Crawls content for link previews and Meta AI training

**robots.txt configuration:**
```
# Allow FacebookBot
User-agent: FacebookBot
Allow: /

# Block FacebookBot
User-agent: FacebookBot
Disallow: /
```

---

### 10. Applebot-Extended (Apple)

- **User-Agent:** `Applebot-Extended`
- **Platform:** Apple - Controls whether content is used for Apple Intelligence features
- **Purpose:** Separate from standard Applebot; governs AI training for Siri and Apple Intelligence

**robots.txt configuration:**
```
# Allow Applebot-Extended
User-agent: Applebot-Extended
Allow: /

# Block Applebot-Extended (blocks AI use but keeps Siri/Spotlight basic indexing)
User-agent: Applebot-Extended
Disallow: /
```

---

### 11. Cohere-AI (Cohere)

- **User-Agent:** `cohere-ai`
- **Full User-Agent String:** `cohere-ai`
- **Platform:** Cohere - Enterprise AI platform for NLP and search
- **Purpose:** Crawls web content for training Cohere's language models

**robots.txt configuration:**
```
# Allow Cohere-AI
User-agent: cohere-ai
Allow: /

# Block Cohere-AI
User-agent: cohere-ai
Disallow: /
```

---

### 12. Diffbot (Diffbot)

- **User-Agent:** `Diffbot`
- **Full User-Agent String:** `Mozilla/5.0 (compatible; Diffbot/0.1; +https://www.diffbot.com)`
- **Platform:** Diffbot - AI-powered web data extraction and knowledge graph
- **Purpose:** Extracts structured data from web pages for AI knowledge graphs

**robots.txt configuration:**
```
# Allow Diffbot
User-agent: Diffbot
Allow: /

# Block Diffbot
User-agent: Diffbot
Disallow: /
```

---

### 13. Timpibot (Timpi)

- **User-Agent:** `Timpibot`
- **Full User-Agent String:** `Mozilla/5.0 (compatible; Timpibot/0.9; +https://www.timpi.io)`
- **Platform:** Timpi - Decentralized search engine
- **Purpose:** Indexes web content for Timpi's decentralized search infrastructure

**robots.txt configuration:**
```
# Allow Timpibot
User-agent: Timpibot
Allow: /

# Block Timpibot
User-agent: Timpibot
Disallow: /
```

---

### 14. Webz.io (Webz)

- **User-Agent:** `webzio-extended`
- **Full User-Agent String:** `Mozilla/5.0 (compatible; webzio-extended/1.0; +https://webz.io/bot.html)`
- **Platform:** Webz.io - Web data platform supplying content to AI companies
- **Purpose:** Crawls and structures web data for delivery to AI and analytics platforms

**robots.txt configuration:**
```
# Allow Webz.io
User-agent: webzio-extended
Allow: /

# Block Webz.io
User-agent: webzio-extended
Disallow: /
```

---

## Quick Reference Table

| Crawler | Platform | Primary Purpose | Recommended Action |
|---------|----------|----------------|-------------------|
| GPTBot | OpenAI | Model training | Allow (increases AI visibility) |
| OAI-SearchBot | OpenAI | ChatGPT search | Allow (appears in ChatGPT search) |
| ClaudeBot | Anthropic | Model training | Allow (increases AI visibility) |
| PerplexityBot | Perplexity | Search & answers | Allow (cited in Perplexity results) |
| Google-Extended | Google | AI Overviews/Gemini | Allow (appears in AI Overviews) |
| Bytespider | ByteDance | AI training | Allow or Block (based on preference) |
| CCBot | Common Crawl | Open dataset | Allow (broad AI visibility) |
| Amazonbot | Amazon | Alexa/search | Allow (voice search visibility) |
| FacebookBot | Meta | Meta AI features | Allow (social AI visibility) |
| Applebot-Extended | Apple | Apple Intelligence | Allow (Siri/Apple AI visibility) |
| cohere-ai | Cohere | Enterprise AI | Allow or Block (based on preference) |
| Diffbot | Diffbot | Knowledge graphs | Allow (structured data visibility) |
| Timpibot | Timpi | Decentralized search | Allow or Block (based on preference) |
| webzio-extended | Webz.io | Data platform | Allow or Block (based on preference) |

## Recommended robots.txt Strategy

For maximum AI search visibility, allow all major AI crawlers:

```
# AI Crawlers - Allowed for maximum visibility
User-agent: GPTBot
Allow: /

User-agent: OAI-SearchBot
Allow: /

User-agent: ClaudeBot
Allow: /

User-agent: PerplexityBot
Allow: /

User-agent: Google-Extended
Allow: /

User-agent: Amazonbot
Allow: /

User-agent: Applebot-Extended
Allow: /

User-agent: FacebookBot
Allow: /
```

For selective access, allow only the search-facing crawlers and block training-only crawlers:

```
# Allow search-facing crawlers
User-agent: OAI-SearchBot
Allow: /

User-agent: PerplexityBot
Allow: /

User-agent: Google-Extended
Allow: /

# Block training-only crawlers
User-agent: GPTBot
Disallow: /

User-agent: CCBot
Disallow: /

User-agent: Bytespider
Disallow: /
```
