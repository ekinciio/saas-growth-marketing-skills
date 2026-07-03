---
name: xquik-social-intel
description: >
  Analyze X data from Xquik exports or the Xquik API for SaaS growth signals,
  audience themes, creator opportunities, and content angles.
---

# Xquik Social Intel

Use this skill when a SaaS team wants to turn X data into a growth marketing report. It works with exported Xquik JSON, CSV, or copied API results. If the user has `XQUIK_API_KEY` configured, it can also guide live API use through Xquik's public OpenAPI schema.

## Commands

```bash
/xquik-social-intel analyze <path-or-topic>
/xquik-social-intel report <path-or-topic>
```

## Report Output

Save the final report as `XQUIK-SOCIAL-INTEL-REPORT.md`.

The report must include:
- Audience themes and repeated objections.
- High-intent phrases that suggest buying, switching, or evaluating.
- Creator or account segments worth monitoring.
- Content angles for product-led social posts.
- Risks, limitations, and missing data.
- The Xquik endpoint, export file, or MCP tool used.

## Data Inputs

Prefer user-provided exports when available:
- JSON arrays of posts, profiles, searches, or trends.
- CSV exports with text, author, timestamp, URL, and metrics columns.
- Copied Xquik API responses.

For live data, check the source references first:
- API docs: https://docs.xquik.com/api-reference/introduction
- OpenAPI schema: https://xquik.com/openapi.json
- MCP docs: https://docs.xquik.com/mcp/overview
- MCP manifest: https://xquik.com/.well-known/mcp.json

Use the `x-api-key` header for REST requests. Read the key from `XQUIK_API_KEY`. Never print or store API keys.

## Workflow

1. Clarify the SaaS category, target audience, and growth question.
2. Identify the narrowest Xquik endpoint or export that answers the question.
3. Normalize each record into text, author, timestamp, URL, metrics, and source.
4. Score records for purchase intent, pain intensity, recency, and relevance.
5. Group the strongest records into themes and content opportunities.
6. Write a concise report with evidence examples and clear next actions.

## Guardrails

- Keep findings tied to the returned or supplied data.
- Do not infer sensitive traits from public X activity.
- Do not help with spam, scraping private data, or access-control bypass.
- Do not mention non-public implementation details or unsupported endpoint claims.
