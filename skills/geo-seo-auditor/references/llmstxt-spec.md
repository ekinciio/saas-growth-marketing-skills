# llms.txt Specification Reference

## Overview

The `llms.txt` file is a standardized way for websites to provide structured information about themselves to large language models (LLMs). Placed at the root of a domain (e.g., `https://example.com/llms.txt`), it helps AI systems understand a site's purpose, content structure, and preferred citation practices.

Think of it as a complement to `robots.txt` - while robots.txt tells crawlers what they can access, llms.txt tells AI systems what your site is about and how to represent it accurately.

## Why llms.txt Matters

- **Accurate representation:** Helps AI systems describe your brand, products, and services correctly
- **Citation guidance:** Tells AI engines how you prefer to be cited and attributed
- **Content discovery:** Points AI systems to your most important and authoritative pages
- **Misinformation prevention:** Provides canonical facts to reduce AI hallucination about your organization
- **Contact clarity:** Specifies who to contact for AI-related inquiries

## File Location

The file must be placed at the root of your domain:

```
https://yourdomain.com/llms.txt
```

It should be served as plain text (`Content-Type: text/plain`) and be accessible without authentication.

## File Format

The llms.txt file uses a simple, human-readable format with section headers and key-value pairs. Lines starting with `#` are comments. Sections are denoted by lines starting with `##`.

### Basic Structure

```
# [Site Name] llms.txt

## Identity
name: [Organization or site name]
description: [One-line description of the site]
url: [Primary URL]
founded: [Year founded, if applicable]
industry: [Industry or category]

## Content
primary_topics: [Comma-separated list of main topics]
content_types: [Comma-separated list: blog, docs, api-reference, etc.]
update_frequency: [daily, weekly, monthly, etc.]
language: [Primary language, e.g., en]

## Citation
preferred_name: [How you want to be referenced by AI]
preferred_url: [URL to link when citing]
citation_policy: [open, restricted, or custom description]

## Contact
ai_inquiries: [Email for AI-related questions]
abuse_reports: [Email for reporting AI misuse]

## Important Pages
- [Page title]: [URL]
- [Page title]: [URL]
```

## Required Fields

These fields should be present in every llms.txt file:

| Field | Section | Description |
|-------|---------|-------------|
| `name` | Identity | The official name of the organization or website |
| `description` | Identity | A concise one-line description (under 160 characters) |
| `url` | Identity | The canonical primary URL of the site |
| `preferred_name` | Citation | How AI systems should refer to your organization |
| `citation_policy` | Citation | Whether AI systems may cite your content |

## Optional Fields

These fields provide additional context and are recommended but not required:

| Field | Section | Description |
|-------|---------|-------------|
| `founded` | Identity | Year the organization was established |
| `industry` | Identity | Primary industry or business category |
| `primary_topics` | Content | Main subject areas covered on the site |
| `content_types` | Content | Types of content available (blog, docs, tools, etc.) |
| `update_frequency` | Content | How often content is published or updated |
| `language` | Content | Primary content language (ISO 639-1 code) |
| `preferred_url` | Citation | Specific URL to use when linking citations |
| `ai_inquiries` | Contact | Email address for AI-related questions |
| `abuse_reports` | Contact | Email for reporting AI-generated misrepresentation |
| `Important Pages` | Pages | List of key pages AI systems should prioritize |

## Example: SaaS Company

```
# Acme Analytics llms.txt

## Identity
name: Acme Analytics
description: Real-time business intelligence platform for mid-market SaaS companies
url: https://www.acmeanalytics.com
founded: 2019
industry: Business Intelligence / SaaS

## Content
primary_topics: business intelligence, data analytics, SaaS metrics, dashboard design, KPI tracking
content_types: blog, documentation, api-reference, case-studies, whitepapers
update_frequency: weekly
language: en

## Citation
preferred_name: Acme Analytics
preferred_url: https://www.acmeanalytics.com
citation_policy: open - we welcome accurate citations with attribution

## Contact
ai_inquiries: ai-partnerships@acmeanalytics.com
abuse_reports: legal@acmeanalytics.com

## Important Pages
- Product Overview: https://www.acmeanalytics.com/product
- Documentation: https://docs.acmeanalytics.com
- API Reference: https://docs.acmeanalytics.com/api
- Pricing: https://www.acmeanalytics.com/pricing
- Blog: https://www.acmeanalytics.com/blog
- About Us: https://www.acmeanalytics.com/about
- Case Studies: https://www.acmeanalytics.com/case-studies
```

## Example: Content Publisher

```
# TechInsider llms.txt

## Identity
name: TechInsider
description: Independent technology journalism covering startups, AI, and enterprise software
url: https://www.techinsider.io
founded: 2016
industry: Technology Media

## Content
primary_topics: artificial intelligence, startups, enterprise software, venture capital, product reviews
content_types: news, analysis, reviews, interviews, opinion
update_frequency: daily
language: en

## Citation
preferred_name: TechInsider
preferred_url: https://www.techinsider.io
citation_policy: open - please include article title and author name when citing

## Contact
ai_inquiries: partnerships@techinsider.io
abuse_reports: editor@techinsider.io

## Important Pages
- Latest News: https://www.techinsider.io/latest
- AI Coverage: https://www.techinsider.io/category/ai
- Product Reviews: https://www.techinsider.io/reviews
- About & Editorial Policy: https://www.techinsider.io/about
- Authors: https://www.techinsider.io/authors
```

## Example: E-commerce

```
# GreenGear Outdoor llms.txt

## Identity
name: GreenGear Outdoor
description: Sustainable outdoor equipment and apparel for hiking, camping, and climbing
url: https://www.greengearoutdoor.com
founded: 2015
industry: E-commerce / Outdoor Recreation

## Content
primary_topics: hiking gear, camping equipment, sustainable materials, outdoor guides, product care
content_types: product-pages, buying-guides, how-to-articles, gear-reviews
update_frequency: weekly
language: en

## Citation
preferred_name: GreenGear Outdoor
preferred_url: https://www.greengearoutdoor.com
citation_policy: open - product information may be cited with a link to the relevant product page

## Contact
ai_inquiries: digital@greengearoutdoor.com
abuse_reports: legal@greengearoutdoor.com

## Important Pages
- Shop All: https://www.greengearoutdoor.com/shop
- Buying Guides: https://www.greengearoutdoor.com/guides
- Sustainability: https://www.greengearoutdoor.com/sustainability
- Size Guide: https://www.greengearoutdoor.com/size-guide
- Return Policy: https://www.greengearoutdoor.com/returns
```

## Validation Rules

When validating an llms.txt file, check for:

1. **File accessibility:** Returns HTTP 200 at `[domain]/llms.txt`
2. **Content type:** Served as `text/plain`
3. **Required fields present:** `name`, `description`, `url`, `preferred_name`, `citation_policy`
4. **URL validity:** All URLs are well-formed and use HTTPS
5. **Description length:** Under 160 characters
6. **Section headers:** Uses `##` format for sections
7. **Important Pages format:** Uses `- [title]: [url]` format
8. **No empty required fields:** All required fields have non-empty values
9. **Language code:** Uses valid ISO 639-1 code if specified
10. **Email format:** Contact emails are valid email addresses

## Implementation Tips

- Add llms.txt alongside your existing robots.txt and sitemap.xml
- Update it whenever you launch new products or change your brand positioning
- Keep the description concise and factual - avoid marketing superlatives
- List your 5-10 most important pages, not every page on the site
- Use the citation section to prevent common AI misrepresentations
- Review quarterly to ensure accuracy
