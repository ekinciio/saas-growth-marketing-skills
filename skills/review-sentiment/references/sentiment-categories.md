# Sentiment Categories and Theme Definitions

Reference document for review sentiment classification, theme categories, and scoring methodology.

## Sentiment Score Definitions

### Star Rating to Sentiment Mapping

| Stars | Sentiment | Score Range | Description |
|-------|-----------|-------------|-------------|
| 5 | Positive | 0.8 - 1.0 | Highly satisfied, enthusiastic praise |
| 4 | Positive | 0.6 - 0.8 | Satisfied with minor reservations |
| 3 | Neutral | 0.4 - 0.6 | Mixed feelings, balanced pros and cons |
| 2 | Negative | 0.2 - 0.4 | Dissatisfied, notable complaints |
| 1 | Negative | 0.0 - 0.2 | Very dissatisfied, strong criticism |

### Text-Based Sentiment Classification

When no star rating is available, sentiment is determined from text signals:

**Positive indicators:**
- Praise words: love, great, excellent, amazing, fantastic, perfect, awesome, wonderful, brilliant, outstanding, impressive, smooth, intuitive, easy, fast, reliable, helpful, beautiful, clean, powerful
- Positive phrases: "works great", "highly recommend", "best app", "game changer", "well designed", "exactly what I needed", "easy to use", "saved me time", "worth every penny"
- Exclamation with positive context
- Comparative praise: "better than", "best I've used", "nothing else compares"

**Negative indicators:**
- Complaint words: terrible, awful, horrible, worst, broken, slow, frustrating, annoying, useless, buggy, confusing, complicated, expensive, overpriced, unreliable, disappointed, unresponsive, clunky, laggy, outdated
- Negative phrases: "waste of money", "doesn't work", "total disaster", "can't believe", "give up", "looking for alternatives", "not worth", "going to cancel", "asked for refund"
- Mentions of crashes, errors, bugs, or failures
- Expressions of frustration or anger

**Neutral indicators:**
- Balanced language with both pros and cons
- Hedging words: okay, decent, average, fair, acceptable, not bad
- Feature descriptions without strong emotion
- Questions or suggestions without complaint
- "It's fine" or "does the job" type phrases

### Negation Handling

Negation words flip the sentiment of the following phrase:
- "not", "no", "never", "don't", "doesn't", "won't", "can't", "couldn't", "shouldn't", "hardly", "barely"
- Example: "not bad" becomes mildly positive
- Example: "not good" becomes negative
- Example: "never crashes" becomes positive

### Intensity Modifiers

Modifiers adjust the confidence score:
- **Amplifiers (increase confidence):** very, extremely, incredibly, absolutely, totally, completely, so, really, truly, remarkably
- **Downtoners (decrease confidence):** slightly, somewhat, a bit, a little, kind of, sort of, fairly, rather, quite

## Theme Categories

### UX/UI
Reviews about design, visual appearance, navigation, and ease of use.

**Keywords:** design, UI, UX, interface, layout, navigation, menu, button, screen, dashboard, visual, clean, modern, intuitive, confusing, cluttered, ugly, beautiful, sleek, user-friendly, hard to find, easy to navigate, looks great, redesign, dark mode, theme, color

**Example positive review:**
> "The new interface is so clean and intuitive. Love the dashboard layout and how easy it is to find everything."
> - Sentiment: Positive (0.91)
> - Theme: UX/UI

**Example negative review:**
> "Navigation is a nightmare. I can never find what I'm looking for and the menu structure makes no sense."
> - Sentiment: Negative (0.87)
> - Theme: UX/UI

### Performance
Reviews about speed, loading times, crashes, and reliability.

**Keywords:** fast, slow, speed, loading, crash, freeze, lag, performance, responsive, quick, instant, hang, timeout, down, outage, uptime, reliable, unreliable, stable, unstable, memory, battery, resource

**Example positive review:**
> "Pages load instantly and I've never experienced a single crash in 6 months of daily use."
> - Sentiment: Positive (0.89)
> - Theme: Performance

**Example negative review:**
> "The app is incredibly slow. Takes 10+ seconds to load any page and crashes at least once a day."
> - Sentiment: Negative (0.93)
> - Theme: Performance

### Pricing
Reviews about cost, value, subscription plans, and billing.

**Keywords:** price, pricing, cost, expensive, cheap, affordable, value, money, subscription, plan, tier, billing, invoice, refund, trial, free, premium, upgrade, downgrade, worth, overpriced, underpriced, budget, ROI

**Example positive review:**
> "Great value for the price. The starter plan has everything a small business needs."
> - Sentiment: Positive (0.78)
> - Theme: Pricing

**Example negative review:**
> "Way too expensive for what you get. Competitors offer the same features at half the price."
> - Sentiment: Negative (0.85)
> - Theme: Pricing

### Support
Reviews about customer service, response times, and helpfulness.

**Keywords:** support, help, customer service, response, reply, ticket, chat, email, phone, wait, agent, representative, resolve, solution, helpful, unhelpful, rude, friendly, knowledgeable, documentation, FAQ, community

**Example positive review:**
> "Support team is fantastic. Got a reply within an hour and they walked me through the solution step by step."
> - Sentiment: Positive (0.92)
> - Theme: Support

**Example negative review:**
> "Submitted a support ticket 5 days ago and still no response. This is unacceptable for a paid product."
> - Sentiment: Negative (0.91)
> - Theme: Support

### Features
Reviews about functionality, capabilities, and feature requests.

**Keywords:** feature, functionality, capability, tool, option, setting, integration, API, export, import, automation, workflow, customization, template, report, analytics, notification, search, filter, sort, missing, wish, need, request, add, want

**Example positive review:**
> "The automation features are incredible. Saved us hours every week with the workflow builder."
> - Sentiment: Positive (0.88)
> - Theme: Features

**Example negative review (feature request):**
> "Really wish it had a Slack integration. Also missing basic export to CSV which is a dealbreaker for us."
> - Sentiment: Negative (0.65)
> - Theme: Features

### Bugs
Reviews about errors, glitches, and broken functionality.

**Keywords:** bug, error, glitch, broken, fix, issue, problem, doesn't work, not working, fail, failure, crash, unexpected, wrong, incorrect, stuck, loop, blank, missing data, lost data, corrupt, regression

**Example negative review:**
> "The export feature has been broken for two weeks. Getting a blank file every time. This is a critical bug."
> - Sentiment: Negative (0.94)
> - Theme: Bugs

**Example mixed review:**
> "Love the product overall but there's a persistent bug where notifications don't appear on mobile."
> - Sentiment: Neutral (0.50)
> - Themes: Bugs, Features

### Onboarding
Reviews about the initial setup experience, documentation, and learning curve.

**Keywords:** onboarding, setup, getting started, first time, new user, tutorial, guide, documentation, docs, walkthrough, learning curve, easy to start, complicated setup, configuration, install, registration, sign up, welcome, intro, training

**Example positive review:**
> "Had everything set up in under 10 minutes. The onboarding wizard and documentation are top-notch."
> - Sentiment: Positive (0.90)
> - Theme: Onboarding

**Example negative review:**
> "Took me three days to figure out the basic setup. Documentation is outdated and the UI gives no guidance."
> - Sentiment: Negative (0.86)
> - Themes: Onboarding, UX/UI

## Multi-Theme Reviews

Many reviews touch on multiple themes. Each review should be tagged with all relevant themes.

**Example:**
> "The design is beautiful and onboarding was smooth, but the app is way too slow and their pricing doesn't match the value."
> - Sentiment: Neutral (0.45)
> - Themes: UX/UI, Onboarding, Performance, Pricing

**Example:**
> "Support helped me fix a bug quickly, and they were very friendly. But I wish the feature set was more complete."
> - Sentiment: Neutral (0.55)
> - Themes: Support, Bugs, Features

## Aggregate Metrics

When analyzing a batch of reviews, calculate:

| Metric | Formula |
|--------|---------|
| Positive % | (positive reviews / total reviews) x 100 |
| Negative % | (negative reviews / total reviews) x 100 |
| Neutral % | (neutral reviews / total reviews) x 100 |
| Average sentiment score | Mean of all individual sentiment scores |
| Theme frequency | Count of reviews mentioning each theme |
| Top positive theme | Most common theme in positive reviews |
| Top negative theme | Most common theme in negative reviews |
| Feature request count | Reviews classified as feature requests |
| Complaint frequency | Top repeated complaints ranked by count |
