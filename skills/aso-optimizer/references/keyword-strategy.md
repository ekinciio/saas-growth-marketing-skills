# ASO Keyword Strategy

Guide to keyword research, placement, and optimization for app store listings.

## Keyword Placement Priority

Keywords carry different weight depending on where they appear. Prioritize
placement in this order:

### 1. App Title (Highest Weight)
- Both Apple and Google give the strongest ranking signal to title keywords
- Place your single most important keyword here
- Format: `Brand - Primary Keyword` or `Brand: Primary Keyword`
- Example: `Todoist: To-Do List & Planner`
- Limit: 30 characters on both platforms

### 2. Subtitle (iOS Only)
- Second-strongest ranking signal on the App Store
- Use secondary keywords that complement the title
- Do not repeat words already in the title
- Example: If title is `Calm - Sleep & Meditation`, subtitle could be `Relax, Focus & Breathe`
- Limit: 30 characters

### 3. Keyword Field (iOS Only)
- Hidden from users but indexed by Apple search
- Use all 100 characters - every unused character is wasted opportunity
- Separate terms with commas and no spaces: `budget,tracker,expense,money,finance`
- Do not repeat any word from the title or subtitle (already indexed)
- Use singular forms only (Apple indexes both singular and plural automatically)
- Avoid prepositions, articles, and the app name itself
- Include common misspellings of your core terms

### 4. Short Description (Google Play Only)
- Shown below the title on the Play Store listing
- Indexed by Google for search ranking
- Limit: 80 characters
- Focus on a concise value proposition with 2-3 keywords

### 5. Full Description
- Apple does NOT index the description for search (but it affects browse ranking)
- Google DOES index the description for Play Store search
- For Google Play: include target keywords naturally 3-5 times in the description
- For Apple: optimize for readability and conversion rather than keyword stuffing
- Limit: 4,000 characters on both platforms

## Long-Tail vs Short-Tail Keywords

### Short-Tail Keywords
- 1-2 words: `todo`, `calendar`, `fitness`
- Very high search volume but extreme competition
- Difficult for new or small apps to rank
- Best used in the title if your app has strong authority

### Long-Tail Keywords
- 3+ words: `habit tracker with reminders`, `budget planner for couples`
- Lower search volume but much less competition
- Higher conversion rate (users searching specific terms have clearer intent)
- Ideal for new apps building initial ranking momentum

### Recommended Approach by App Maturity

| App Stage | Short-Tail | Long-Tail | Strategy |
|-----------|-----------|-----------|----------|
| New (0-1K ratings) | 20% | 80% | Focus almost entirely on long-tail to build initial rankings |
| Growing (1K-10K ratings) | 40% | 60% | Start targeting moderate competition short-tail terms |
| Established (10K+ ratings) | 60% | 40% | Compete for high-volume short-tail while maintaining long-tail coverage |

### Building a Keyword List

1. Brainstorm 50+ keywords related to your app's functionality
2. Add synonyms and related terms for each
3. Research competitor titles, subtitles, and descriptions for additional ideas
4. Categorize by estimated difficulty (low, medium, high)
5. Map keywords to metadata fields based on the placement priority above
6. Track ranking positions weekly and rotate underperformers

## Competitor Metadata Reverse Engineering

Analyzing competitor listings reveals keyword opportunities and best practices.

### What to Analyze

- **Title structure**: How do top competitors balance brand and keywords?
- **Subtitle/short description**: What secondary keywords are they targeting?
- **Description format**: How do they structure content? What CTAs do they use?
- **Rating and review volume**: What is the competitive benchmark for credibility?
- **Visual strategy**: What do the first 2 screenshots communicate?
- **Update frequency**: How often do they refresh metadata?

### Step-by-Step Competitor Analysis

1. Identify your top 5-10 competitors by searching your primary keywords
2. Record each competitor's title, subtitle, and first description paragraph
3. Extract unique keywords from each competitor that you are not currently using
4. Note which keywords appear across multiple competitor titles (high-value terms)
5. Identify gaps - keywords relevant to your features that competitors do not use
6. Score each competitor listing using the ASO health score framework
7. Use findings to refine your own keyword list and metadata

### Tools for Competitor Research (Free Methods)

- Search the app store for your target keywords and note the top 10 results
- Use the iTunes Search API to pull competitor metadata programmatically
- Read competitor reviews to discover the language users naturally use
- Check competitor "What's New" sections for feature-related keywords
- Monitor competitor title/subtitle changes over time for strategy signals

## Localization Strategy Overview

Localizing metadata expands reach into new markets without building new features.

### Priority Markets by App Store Revenue

1. United States
2. Japan
3. United Kingdom
4. South Korea
5. Germany
6. China (iOS only - Google Play not available)
7. France
8. Canada
9. Australia
10. Brazil

### Localization Best Practices

- Never rely on direct translation alone - keyword search behavior varies by locale
- Research local keyword volume and competition for each market
- Adapt screenshots and visual assets for cultural relevance
- Consider right-to-left layout for Arabic and Hebrew markets
- Use native speakers or professional localization services for quality
- Localize the "What's New" section with each update

### iOS Localization Bonus

Apple allows you to set metadata for specific locale variants. Some locales
share rankings:

- US English metadata also indexes for UK, Australia, and Canada if those
  locales have no custom metadata
- Spanish (Mexico) metadata is shared across Latin American Spanish locales
- Use this to your advantage by filling in metadata for strategic "bridge" locales

### Google Play Localization

- Google Play supports localization for 77+ languages
- The description is indexed for search in each locale
- Localized screenshots significantly improve conversion in non-English markets
- Google auto-translates your listing if you do not provide a translation (but
  quality is often poor, making manual localization worthwhile)

## Keyword Optimization Cycle

Keyword strategy is not a one-time setup. Follow this ongoing process:

1. **Research** (Week 1): Build and prioritize your keyword list
2. **Implement** (Week 2): Place keywords across metadata fields
3. **Monitor** (Weeks 3-6): Track ranking positions for each target keyword
4. **Analyze** (Week 6): Identify winners (ranking well) and losers (not moving)
5. **Iterate** (Week 7): Replace underperforming keywords with new candidates
6. **Repeat**: Run this cycle continuously, testing 3-5 new keywords per cycle

## Disclaimer

This guide covers keyword strategy using freely available methods - competitor
metadata analysis, iTunes Search API data, and manual research techniques.
Accurate keyword search volume data, keyword difficulty scores, and download
estimates require paid ASO tools such as Sensor Tower, data.ai (formerly App
Annie), AppTweak, or Apple Search Ads keyword insights. The strategies described
here are effective without paid tools but can be enhanced significantly when
combined with volume data from those platforms.
