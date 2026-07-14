# llms.txt Specification Reference

## Overview

`llms.txt` is a proposal (by Jeremy Howard, September 2024, published at [llmstxt.org](https://llmstxt.org)) for a plain-Markdown file placed at the root of a website (`https://example.com/llms.txt`). It gives large language models a concise, curated overview of the site and links to LLM-friendly content, so an AI system can find the right pages without parsing complex HTML.

Unlike `robots.txt` (access control) or `sitemap.xml` (exhaustive page list), llms.txt is a short, human- and LLM-readable Markdown document that highlights only the most useful content, primarily for use at **inference time** (when a user asks an AI about the site), not for training.

**Honest status note:** llms.txt is a community proposal with debated adoption, not an established web standard. Some major AI vendors do not currently fetch or use llms.txt at all, and there is no guarantee that adding one improves AI visibility. It is cheap to add and popular in developer-documentation circles (nbdev, FastHTML, many docs platforms), so it is a reasonable low-effort optimization - but present it as such, never as a compliance requirement.

## File Location

```
https://yourdomain.com/llms.txt
```

The file should be served as Markdown text (typically `Content-Type: text/plain` or `text/markdown`) and be accessible without authentication. A subpath (e.g. `/docs/llms.txt`) is also permitted by the spec.

## Format

The file is **pure Markdown** with a fixed section order. There are no key-value fields. In order:

1. **An H1 with the site or project name** - the only *required* element.
2. **A blockquote** (`> ...`) with a short summary containing the key information needed to understand the rest of the file. Recommended.
3. **Zero or more Markdown sections** (paragraphs, lists, etc. - anything except headings) with more detail about the site and how to interpret the linked files.
4. **Zero or more H2-delimited sections containing "file lists"**: Markdown lists where each entry is a required hyperlink `[name](url)`, optionally followed by `: notes about the file`.

### Skeleton

```markdown
# Title

> Optional description goes here

Optional details go here

## Section name

- [Link title](https://link_url): Optional link details

## Optional

- [Link title](https://link_url)
```

### The `## Optional` section

The H2 section named exactly `Optional` has special semantics: AI systems may **skip** the URLs listed there when a shorter context is needed. Put secondary or supplementary links in it.

## Realistic Example

```markdown
# Acme Analytics

> Acme Analytics is a real-time business intelligence platform for mid-market
> SaaS companies, providing dashboards, KPI tracking, and automated reporting.

Key things to know:

- The product docs are the most authoritative source for feature behavior.
- Pricing and plan limits change periodically; always check the pricing page.

## Docs

- [Product documentation](https://docs.acmeanalytics.com/index.md): Full user guide
- [API reference](https://docs.acmeanalytics.com/api.md): REST API endpoints and auth
- [Quick start](https://docs.acmeanalytics.com/quickstart.md): Set up in 10 minutes

## Company

- [About](https://www.acmeanalytics.com/about): Company background and team
- [Pricing](https://www.acmeanalytics.com/pricing): Current plans and limits

## Optional

- [Blog](https://www.acmeanalytics.com/blog): Product updates and analytics guides
- [Case studies](https://www.acmeanalytics.com/case-studies)
```

## Companion Conventions (not core spec)

- **`.md` page versions:** the proposal also suggests serving a clean Markdown version of each important page at the same URL with `.md` appended (e.g. `/docs/intro.html.md`).
- **`llms-full.txt`:** a common companion convention (not part of the core spec) where the full expanded content of all linked pages is concatenated into one large file for direct ingestion. Related: FastHTML's generated `llms-ctx.txt` / `llms-ctx-full.txt` context files.

## Validation Checklist

When validating an llms.txt file, check:

1. **Required:** File returns HTTP 200 at `/llms.txt` and is Markdown/plain text (an HTML page here usually means a SPA catch-all route, i.e. no real llms.txt).
2. **Required:** Exactly one H1 (`# Name`) appears as the first heading.
3. **Recommended:** A blockquote summary (`> ...`) directly after the H1.
4. **Recommended:** At least one H2 section containing a link list with `- [name](url)` entries.
5. **Recommended:** All link URLs are well-formed (absolute `http(s)://` URLs).
6. **Recommended:** Reasonable length - a curated overview, not a full sitemap dump (roughly a few dozen links, not thousands of lines).
7. **Optional:** An `## Optional` section for skippable secondary links.

## Implementation Tips

- Keep it curated: link the 5-30 pages that best explain your site, not every URL.
- Write the blockquote summary as if it is the only thing an AI will read.
- Prefer linking Markdown versions of pages when available.
- Put nice-to-have links under `## Optional` so they can be dropped for short contexts.
- Review quarterly and after major product or docs changes.
- Set expectations with stakeholders: this is a forward-looking, low-cost addition, not a ranking factor.
