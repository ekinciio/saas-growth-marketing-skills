# Platform Search URLs and API Reference

Complete API reference for all platforms supported by the brand mention scanner, plus future platform candidates.

## Currently Supported Platforms

### 1. Reddit

**API Endpoints:**

OAuth search (primary; requires credentials):
```
https://oauth.reddit.com/search?q="BRAND"&sort=new&limit=50
Authorization: bearer <token>
```
Token exchange (client_credentials grant, HTTP basic auth with client ID/secret):
```
POST https://www.reddit.com/api/v1/access_token
grant_type=client_credentials
```

Public JSON search (blocked - returns 403 for all user agents; kept for reference):
```
https://www.reddit.com/search.json?q="BRAND"&sort=new&limit=50
```

RSS/Atom search (no auth; works, but no upvote/comment counts):
```
https://www.reddit.com/search.rss?q="BRAND"&sort=new&type=link
```

**Parameters** (shared by all three endpoints):
| Parameter | Type | Description | Default |
|-----------|------|-------------|---------|
| q | string | Search query (wrap in quotes for exact match) | Required |
| sort | string | Sort order: relevance, hot, top, new, comments | relevance |
| t | string | Time filter: hour, day, week, month, year, all | all |
| limit | int | Results per page (max 100) | 25 |
| after | string | Pagination token for next page | None |
| type | string | Result type: link, comment, sr | link |

**Rate Limits:**
- Unauthenticated JSON API: blocked (403) - Reddit closed unauthenticated API access
- OAuth (free tier): 100 queries per minute per client ID, averaged over a 10-minute window
- RSS feed: unauthenticated but aggressively rate limited - expect 429 on rapid successive requests
- User-Agent header is required (format: `script:app-name:version (by /u/username)`)

**Response Format Example:**
```json
{
  "data": {
    "children": [
      {
        "data": {
          "title": "Post title",
          "subreddit": "SaaS",
          "author": "username",
          "score": 42,
          "num_comments": 15,
          "permalink": "/r/SaaS/comments/abc123/post_title/",
          "selftext": "Post body text...",
          "created_utc": 1700000000,
          "url": "https://example.com"
        }
      }
    ]
  }
}
```

**Auth Requirements:** OAuth credentials (`REDDIT_CLIENT_ID` + `REDDIT_CLIENT_SECRET`) for the API. New API access requires approval via Reddit's developer request form (Responsible Builder Policy, support.reddithelp.com); apps created earlier at reddit.com/prefs/apps keep working. The RSS feed needs no auth but returns limited data.

---

### 2. Hacker News (Algolia API)

**API Endpoints:**

Stories search:
```
https://hn.algolia.com/api/v1/search?query="BRAND"&tags=story
```

Comments search:
```
https://hn.algolia.com/api/v1/search?query="BRAND"&tags=comment
```

Recent items:
```
https://hn.algolia.com/api/v1/search_by_date?query="BRAND"&tags=story
```

**Parameters:**
| Parameter | Type | Description | Default |
|-----------|------|-------------|---------|
| query | string | Search query | Required |
| tags | string | Filter: story, comment, poll, show_hn, ask_hn | None |
| numericFilters | string | Numeric filters (e.g., points>10) | None |
| page | int | Page number (0-indexed) | 0 |
| hitsPerPage | int | Results per page (max 1000) | 20 |

**Rate Limits:**
- 10,000 requests per hour
- No authentication required
- Very generous for monitoring use cases

**Response Format Example:**
```json
{
  "hits": [
    {
      "title": "Story title",
      "url": "https://example.com",
      "author": "username",
      "points": 150,
      "num_comments": 45,
      "created_at": "2024-01-15T10:30:00.000Z",
      "objectID": "12345678",
      "story_text": "Optional self-post text..."
    }
  ],
  "nbHits": 100,
  "page": 0,
  "nbPages": 5
}
```

**Auth Requirements:** None.

---

### 3. GitHub

**API Endpoint:**
```
https://api.github.com/search/repositories?q=BRAND
```

**Parameters:**
| Parameter | Type | Description | Default |
|-----------|------|-------------|---------|
| q | string | Search query (supports qualifiers) | Required |
| sort | string | Sort: stars, forks, help-wanted-issues, updated | best match |
| order | string | Order: asc, desc | desc |
| per_page | int | Results per page (max 100) | 30 |
| page | int | Page number | 1 |

**Search Qualifiers:**
- `in:name` - Search in repository name
- `in:description` - Search in description
- `in:readme` - Search in README
- `language:python` - Filter by language
- `stars:>100` - Filter by star count
- `pushed:>2024-01-01` - Filter by last push date

**Rate Limits:**
- Unauthenticated: 10 requests per minute
- Authenticated: 30 requests per minute
- Search API has a special rate limit separate from the REST API

**Required Headers:**
```
Accept: application/vnd.github+json
X-GitHub-Api-Version: 2022-11-28
User-Agent: saas-growth-skills/1.0
```
Add `Authorization: Bearer <GITHUB_TOKEN>` for the higher authenticated rate limit.

**Response Format Example:**
```json
{
  "total_count": 150,
  "items": [
    {
      "full_name": "org/repo-name",
      "description": "Repository description",
      "html_url": "https://github.com/org/repo-name",
      "stargazers_count": 1500,
      "forks_count": 200,
      "open_issues_count": 25,
      "language": "TypeScript",
      "updated_at": "2024-01-15T10:30:00Z",
      "topics": ["saas", "tool"]
    }
  ]
}
```

**Auth Requirements:** None for basic search, but authenticated requests get higher rate limits.

---

## Future Platform Candidates

### ProductHunt

**API Endpoint:**
```
https://api.producthunt.com/v2/api/graphql
```

**Notes:**
- GraphQL API
- Requires OAuth2 authentication (developer token)
- Rate limit: complexity-based - each query costs points depending on how much data it requests, against a per-window budget (check current limits in the ProductHunt API docs)
- Good for tracking product launches and competitor activity
- Useful for identifying early-stage competitors

### Stack Overflow

**API Endpoint:**
```
https://api.stackexchange.com/2.3/search?intitle=BRAND&site=stackoverflow
```

**Notes:**
- REST API with JSON responses
- Rate limit: 300 requests per day without a key; 10,000 per day with a free registered API key (no user OAuth needed)
- Good for developer tools and technical products
- Questions and answers format provides rich context

### Dev.to

**API Endpoint:**
```
https://dev.to/api/articles?tag=BRAND
```

**Notes:**
- Simple REST API
- Rate limit: 30 requests per 30 seconds
- Good for developer community content
- Articles and discussions about tools and technologies

### Medium

**Notes:**
- No official public API for search
- RSS feeds available per publication and tag
- Consider using web scraping with appropriate rate limiting
- Good for thought leadership and industry content monitoring

### Twitter/X

**API Endpoint:**
```
https://api.x.com/2/tweets/search/recent?query=BRAND
```

**Notes:**
- Requires authentication (Bearer token); no free tier
- The free and legacy subscription tiers have been discontinued; as of 2026, new developers are on pay-per-use pricing
- Full-archive search and streaming are restricted to higher-priced access
- Expect significant, usage-based cost for any brand monitoring volume - budget before committing to this platform

## Platform Selection Guide

| Platform | Best For | Cost | Effort |
|----------|----------|------|--------|
| Reddit | Community sentiment, product recommendations | Free | Low |
| Hacker News | Developer audience, tech product buzz | Free | Low |
| GitHub | Open source ecosystem, developer tools | Free | Low |
| ProductHunt | Product launches, competitor tracking | Free (with auth) | Medium |
| Stack Overflow | Technical support mentions, developer tools | Free | Low |
| Dev.to | Developer content, thought leadership | Free | Low |
| Medium | Industry articles, brand awareness | N/A | Medium |
| Twitter/X | Real-time mentions, customer support | Paid | High |

## Rate Limiting Best Practices

1. **Always include a 2-second delay** between requests to any platform
2. **Cache results** to avoid redundant API calls
3. **Use conditional requests** (If-Modified-Since, ETag) where supported
4. **Implement exponential backoff** on rate limit errors (429 responses)
5. **Rotate request timing** to spread load across monitoring cycles
6. **Track usage** against limits to avoid hitting caps
