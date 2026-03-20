# PLG Metrics Reference

Definitions, measurement guidance, and optimization strategies for Product-Led Growth metrics using the AARRR framework.

## AARRR Framework (Pirate Metrics)

The AARRR framework organizes growth metrics into five sequential stages. Each stage feeds into the next, and a leak at any stage limits overall growth.

### 1. Acquisition

**Definition:** How users discover and sign up for your product.

**Key Metrics:**
- **Signup volume** - Total new signups per period
- **Customer Acquisition Cost (CAC)** - Total spend to acquire one customer
- **Channel breakdown** - Signups by source (organic, paid, referral, direct)
- **Signup completion rate** - Percentage of users who start and finish registration

**Measurement Notes:**
- Track CAC per channel to identify the most efficient acquisition sources
- Separate organic vs. paid acquisition to understand true unit economics
- Monitor signup abandonment at each step of the registration flow

### 2. Activation

**Definition:** The moment a new user experiences the core value of your product for the first time.

**Key Metrics:**
- **Signup-to-Active rate** - Percentage of signups who reach "activated" status
- **Time-to-Value (TTV)** - Duration from signup to first value experience
- **Aha moment completion** - Percentage of users who reach the key activation event
- **Onboarding completion rate** - Percentage of users who finish the setup flow

**Measurement Notes:**
- Define your "aha moment" precisely (e.g., "created first project and invited a teammate")
- Track TTV in hours, not just days - the faster, the better
- Segment activation rates by signup source to identify quality differences

### 3. Retention

**Definition:** Whether users continue to come back and use the product over time.

**Key Metrics:**
- **Monthly churn rate** - Percentage of customers who cancel per month
- **DAU/MAU ratio** - Daily active users divided by monthly active users (stickiness)
- **Week 1 / Week 4 / Week 12 retention** - Cohort retention at key milestones
- **Feature retention** - Which features keep users engaged long-term

**Measurement Notes:**
- Churn is the silent killer of PLG businesses - even small improvements compound
- Track retention curves by cohort to see if product improvements help newer users
- A DAU/MAU ratio above 25% indicates strong daily engagement
- Feature-level retention reveals what drives long-term stickiness

### 4. Revenue

**Definition:** How effectively the product converts free users to paid and expands revenue from existing customers.

**Key Metrics:**
- **Free-to-Paid conversion rate** - Percentage of free users who become paying customers
- **Net Revenue Retention (NRR)** - Revenue retained from existing customers including expansion and contraction
- **Average Revenue Per User (ARPU)** - Total revenue divided by total customers
- **Payback period** - Months to recover the cost of acquiring a customer
- **Expansion revenue percentage** - Revenue from upsells, cross-sells, and seat additions

**Measurement Notes:**
- NRR above 100% means you grow even without new customers
- Track conversion triggers - what actions correlate with upgrade decisions
- Monitor payback period by cohort and channel
- Expansion revenue is the hallmark of great PLG companies

### 5. Referral

**Definition:** Whether existing users bring in new users through word-of-mouth, sharing, or built-in viral mechanics.

**Key Metrics:**
- **Viral coefficient (K-factor)** - Average number of new users each existing user brings in
- **Referral program conversion rate** - Percentage of referred visitors who sign up
- **Net Promoter Score (NPS)** - Likelihood of users recommending the product (-100 to 100)
- **Organic vs. paid ratio** - Proportion of growth from organic channels

**Measurement Notes:**
- A viral coefficient above 1.0 means exponential growth (rare but powerful)
- Track referral quality - do referred users activate and retain better?
- NPS above 50 is considered excellent for SaaS
- Built-in virality (collaboration, sharing) is more sustainable than referral programs

## Time-to-Value (TTV) Deep Dive

Time-to-Value is one of the most critical PLG metrics. It measures how quickly a new user goes from signup to experiencing the product's core benefit.

### Types of TTV

| Type | Definition | Example |
|------|-----------|---------|
| **Time to Basic Value** | First useful interaction | User creates first document |
| **Time to Aha Moment** | User understands the product's unique advantage | User sees the collaboration feature working in real-time |
| **Time to Habit** | Product becomes part of the user's workflow | User logs in daily for a week |

### TTV Optimization Strategies

1. **Reduce signup friction** - Minimize required fields, offer social login, delay email verification
2. **Progressive onboarding** - Show value first, ask for setup details later
3. **Pre-populated templates** - Give users something to work with immediately
4. **Guided first-run experience** - Walk users to the aha moment step by step
5. **Skip optional setup** - Let users explore before completing their profile
6. **Contextual help** - Provide in-app guidance at decision points, not upfront tutorials

### TTV Benchmarks

- **Best in class:** Under 5 minutes to basic value
- **Good:** Under 1 day to aha moment
- **Average:** 1-3 days to aha moment
- **Needs improvement:** More than 7 days to aha moment

## Aha Moment Identification

The aha moment is the specific action or experience that makes a user understand the product's value. Identifying it is critical for PLG optimization.

### How to Find Your Aha Moment

1. **Cohort analysis** - Compare actions taken by retained users vs. churned users in their first week
2. **Correlation analysis** - Find which early actions correlate most strongly with long-term retention
3. **User interviews** - Ask retained users "When did you realize this product was valuable?"
4. **Event sequence analysis** - Map the most common paths of users who convert to paid

### Examples of Aha Moments in SaaS

| Product Type | Likely Aha Moment |
|-------------|-------------------|
| Project management | Created a project and moved the first task to done |
| Communication tool | Had a real-time conversation with a teammate |
| Analytics platform | Saw the first dashboard with their own data |
| Design tool | Created and shared a design with a collaborator |
| CRM | Imported contacts and logged the first deal |
| Developer tool | Deployed code using the platform for the first time |

## Activation Rate Benchmarks by Product Type

| Product Type | Median Activation Rate | Top Quartile |
|-------------|----------------------|-------------|
| Collaboration/productivity | 30% | 45%+ |
| Developer tools | 20% | 35%+ |
| Marketing/analytics | 25% | 40%+ |
| Design tools | 22% | 38%+ |
| Communication platforms | 35% | 50%+ |
| CRM/sales tools | 18% | 30%+ |

## Free-to-Paid Conversion Benchmarks

| Model | Median Conversion | Top Quartile |
|-------|------------------|-------------|
| Freemium (unlimited free tier) | 2-3% | 5%+ |
| Free trial (14-day, no card) | 8-12% | 18%+ |
| Free trial (14-day, card required) | 25-40% | 50%+ |
| Reverse trial (start paid, downgrade to free) | 15-20% | 30%+ |
| Usage-based free tier | 4-6% | 10%+ |

## Expansion Revenue Patterns

Expansion revenue comes from existing customers paying more over time. Strong PLG companies derive 30-50% of new ARR from expansion.

### Expansion Levers

1. **Seat-based expansion** - More team members adopt the product
2. **Usage-based expansion** - Customers use more of a metered resource
3. **Feature-based upsell** - Customers upgrade to access advanced features
4. **Cross-sell** - Customers adopt additional product modules
5. **Plan upgrade** - Customers move from a lower tier to a higher tier

### Expansion Revenue Benchmarks

| Stage | Expansion as % of New ARR |
|-------|--------------------------|
| Early stage (pre-$5M ARR) | 10-20% |
| Growth stage ($5M-$50M ARR) | 25-35% |
| Scale stage ($50M+ ARR) | 35-50% |

Companies with NRR above 120% are typically in the top quartile of PLG performance and can sustain growth even with moderate new customer acquisition.
