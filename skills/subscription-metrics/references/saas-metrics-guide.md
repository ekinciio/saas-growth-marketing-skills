# SaaS Metrics Guide

Comprehensive reference for SaaS subscription metrics - definitions, formulas, healthy ranges, and improvement tactics.

---

## 1. Monthly Recurring Revenue (MRR)

**Definition:** The predictable, normalized monthly revenue from all active subscriptions. MRR strips out one-time fees and normalizes annual contracts to a monthly value.

**Formula:**
```
MRR = Sum of monthly revenue from all active subscriptions
```

**MRR Components:**
```
New MRR         = MRR from newly acquired customers
Expansion MRR   = MRR increase from existing customers (upgrades, add-ons, seat expansion)
Contraction MRR = MRR decrease from existing customers (downgrades)
Churned MRR     = MRR lost from cancelled customers
Net New MRR     = New MRR + Expansion MRR - Contraction MRR - Churned MRR
```

**Healthy Range:**
- Positive Net New MRR every month is the baseline expectation
- Month-over-month MRR growth: 10-20% for early stage, 5-10% for growth stage, 2-5% for scale
- Expansion MRR should eventually exceed Churned MRR (negative net churn)

**How to Improve:**
- Increase New MRR: optimize acquisition funnel, expand channels, improve conversion
- Grow Expansion MRR: usage-based pricing tiers, add-on features, seat-based growth
- Reduce Contraction: proactive health scoring, usage alerts before downgrade
- Reduce Churn: better onboarding, customer success engagement, product stickiness

---

## 2. Annual Recurring Revenue (ARR)

**Definition:** The annualized value of recurring subscription revenue. The primary top-line metric for SaaS companies.

**Formula:**
```
ARR = MRR x 12
```

For annual contracts:
```
ARR = Sum of annual contract values for all active subscriptions
```

**Healthy Range:**
- Seed: $100K-$500K ARR
- Series A: $500K-$3M ARR
- Series B: $3M-$15M ARR
- Growth: $15M-$50M ARR
- Scale: $50M+ ARR

**How to Improve:**
- All MRR improvement levers apply (see above)
- Shift customers from monthly to annual contracts (offer 10-20% discount for annual commitment)
- Land-and-expand strategy: start small, grow accounts over time

---

## 3. Churn Rate

### Logo Churn (Customer Churn)

**Definition:** The percentage of customers who cancel their subscription in a given period.

**Formula:**
```
Monthly Logo Churn = Customers lost during month / Customers at start of month x 100
Annual Logo Churn  = 1 - (1 - Monthly Logo Churn)^12
```

**Healthy Range:**
- Monthly: <2% for SMB, <1% for mid-market, <0.5% for enterprise
- Annual: <10% for SMB, <7% for mid-market, <5% for enterprise

### Revenue Churn (Gross Revenue Churn)

**Definition:** The percentage of MRR lost from cancellations and downgrades, not counting expansion.

**Formula:**
```
Gross Revenue Churn = (Churned MRR + Contraction MRR) / MRR at start of month x 100
```

**Healthy Range:**
- Monthly: <2% for SMB, <1.5% for mid-market, <1% for enterprise
- Best-in-class: <0.5% monthly

### Net Revenue Churn

**Definition:** Revenue churn offset by expansion revenue from existing customers. Can be negative (which is good).

**Formula:**
```
Net Revenue Churn = (Churned MRR + Contraction MRR - Expansion MRR) / MRR at start of month x 100
```

**Healthy Range:**
- Negative net revenue churn is the gold standard
- Best-in-class: -2% to -5% monthly (meaning expansion exceeds churn)
- Acceptable: 0% to 1% monthly

**How to Improve Churn:**
- Implement customer health scoring and intervene before churn happens
- Improve onboarding to drive faster time-to-value
- Build product stickiness through integrations, data lock-in, and workflow embedding
- Proactive customer success for high-value accounts
- Win-back campaigns for recently churned customers
- Analyze churn cohorts to identify root causes (pricing, product gaps, support issues)

---

## 4. Customer Acquisition Cost (CAC)

### Blended CAC

**Definition:** The average cost to acquire one new customer across all channels.

**Formula:**
```
Blended CAC = Total Sales & Marketing Spend / Number of New Customers Acquired
```

Include in S&M spend: advertising, content marketing, SDR/AE salaries and commissions, marketing tools, events, partnerships team costs.

### Channel-Specific CAC

**Formula:**
```
Channel CAC = Channel-Specific Spend / New Customers from That Channel
```

Common channels: paid search, paid social, organic/SEO, content marketing, outbound sales, partnerships, referral.

**Healthy Range:**
- Highly dependent on ACV (annual contract value)
- SMB (ACV <$5K): CAC should be <$500
- Mid-market (ACV $5K-$50K): CAC should be <$5,000
- Enterprise (ACV $50K+): CAC up to $50,000 can be acceptable
- General rule: LTV:CAC ratio should be 3:1 or better

**How to Improve:**
- Optimize paid channel targeting and bidding
- Invest in organic channels (SEO, content, community) for lower long-term CAC
- Improve conversion rates at each funnel stage
- Implement referral and partner programs
- Shorten sales cycles to reduce sales team cost per deal
- Focus on ICP (ideal customer profile) to avoid wasted spend on poor-fit leads

---

## 5. Customer Lifetime Value (LTV)

### Simple Method

**Definition:** The total revenue a customer generates over their entire relationship.

**Formula:**
```
LTV = ARPU / Monthly Churn Rate
```
Or equivalently:
```
LTV = ARPU x Average Customer Lifetime (in months)
Average Customer Lifetime = 1 / Monthly Churn Rate
```

### DCF (Discounted Cash Flow) Method

**Definition:** Present value of future customer revenue, accounting for time value of money.

**Formula:**
```
LTV = ARPU x Gross Margin / (Monthly Churn Rate + Monthly Discount Rate)
```

Where monthly discount rate is typically 0.83% (10% annual discount rate / 12).

**Healthy Range:**
- LTV:CAC ratio of 3:1 or higher
- LTV:CAC of 5:1+ may indicate under-investment in growth
- LTV:CAC below 1:1 means you lose money on every customer

**How to Improve:**
- Reduce churn (increases average lifetime)
- Increase ARPU through upsells, cross-sells, and usage growth
- Improve gross margin through operational efficiency
- Drive expansion revenue (larger plans, more seats, add-ons)

---

## 6. LTV:CAC Ratio

**Definition:** How much lifetime value you generate per dollar spent acquiring a customer.

**Formula:**
```
LTV:CAC = Customer Lifetime Value / Customer Acquisition Cost
```

**Healthy Range:**
- Below 1:1 - Unsustainable, losing money on every customer (RED)
- 1:1 to 2:1 - Inefficient, need to improve unit economics (RED)
- 2:1 to 3:1 - Acceptable but room for improvement (YELLOW)
- 3:1 to 5:1 - Healthy, the sweet spot for most SaaS (GREEN)
- Above 5:1 - May be under-investing in growth (YELLOW)

**How to Improve:**
- Increase LTV: reduce churn, increase ARPU, drive expansion
- Decrease CAC: improve conversion rates, invest in organic channels, better targeting

---

## 7. CAC Payback Period

**Definition:** The number of months it takes to recover the cost of acquiring a customer.

**Formula:**
```
Payback Period (months) = CAC / (ARPU x Gross Margin %)
```

**Healthy Range:**
- Under 12 months: excellent (GREEN)
- 12-18 months: good (GREEN)
- 18-24 months: acceptable for enterprise (YELLOW)
- Over 24 months: concerning (RED)
- Over 36 months: unsustainable (RED)

**How to Improve:**
- Reduce CAC (see CAC improvement tactics above)
- Increase ARPU through pricing optimization
- Improve gross margins through automation and efficiency
- Front-load revenue with annual contracts and upfront payments

---

## 8. Rule of 40

**Definition:** A benchmark that states a healthy SaaS company's combined revenue growth rate and profit margin should exceed 40%.

**Formula:**
```
Rule of 40 Score = Revenue Growth Rate (%) + Profit Margin (%)
```

Use YoY revenue growth and EBITDA margin (or free cash flow margin).

**Healthy Range:**
- Above 40%: excellent, best-in-class (GREEN)
- 30-40%: good, on track (YELLOW)
- 20-30%: needs attention, optimize growth or efficiency (YELLOW)
- Below 20%: concerning, fundamental issues to address (RED)

**Interpretation:**
- A company growing 80% YoY with -30% margins scores 50% - healthy
- A company growing 20% YoY with 25% margins scores 45% - healthy
- A company growing 10% YoY with 5% margins scores 15% - needs work

**How to Improve:**
- If growth is strong but margins are poor: focus on operational efficiency, reduce COGS, optimize S&M spend
- If margins are strong but growth is slow: invest more aggressively in growth channels
- Balance: find the right trade-off between growth investment and profitability

---

## 9. Burn Multiple

**Definition:** How much cash a company burns to generate each dollar of net new ARR. Measures capital efficiency.

**Formula:**
```
Burn Multiple = Net Burn / Net New ARR
```

Where Net Burn = Total cash spent - Total cash received in the period.

**Healthy Range:**
- Below 1x: exceptional efficiency (GREEN)
- 1x to 1.5x: great (GREEN)
- 1.5x to 2x: good (YELLOW)
- 2x to 3x: concerning (YELLOW)
- Above 3x: poor capital efficiency (RED)

**How to Improve:**
- Increase net new ARR without proportionally increasing spend
- Reduce burn: cut low-ROI programs, improve operational efficiency
- Accelerate revenue: shorten sales cycles, improve close rates
- Focus on expansion revenue (often lower cost than new acquisition)

---

## 10. SaaS Quick Ratio

**Definition:** Measures growth efficiency by comparing revenue inflows to revenue outflows.

**Formula:**
```
Quick Ratio = (New MRR + Expansion MRR) / (Contraction MRR + Churned MRR)
```

**Healthy Range:**
- Above 4: excellent growth efficiency (GREEN)
- 2 to 4: healthy (GREEN)
- 1 to 2: struggling to grow efficiently (YELLOW)
- Below 1: shrinking, outflows exceed inflows (RED)

**How to Improve:**
- Increase numerator: acquire more customers, drive expansion
- Decrease denominator: reduce churn and contraction
- A ratio of 4 means for every $1 lost, $4 comes in - sustainable growth

---

## 11. Magic Number

**Definition:** Revenue efficiency metric measuring how much ARR is generated per dollar of sales and marketing spend.

**Formula:**
```
Magic Number = Net New ARR (current quarter) / S&M Spend (previous quarter)
```

The one-quarter lag accounts for the delay between spending and revenue realization.

**Healthy Range:**
- Above 1.0: very efficient, consider investing more aggressively (GREEN)
- 0.75 to 1.0: efficient (GREEN)
- 0.5 to 0.75: acceptable (YELLOW)
- Below 0.5: inefficient, need to optimize go-to-market (RED)

**How to Improve:**
- Improve lead quality and conversion rates
- Optimize sales team productivity and quota attainment
- Reduce sales cycle length
- Better alignment between marketing spend and revenue-generating activities

---

## 12. Net Revenue Retention (NRR)

**Definition:** The percentage of revenue retained from existing customers after accounting for expansion, contraction, and churn.

**Formula:**
```
NRR = (Beginning MRR + Expansion MRR - Contraction MRR - Churned MRR) / Beginning MRR x 100
```

Measured over 12 months for annual NRR.

**Healthy Range:**
- Above 130%: exceptional (GREEN) - typical of best PLG companies
- 110-130%: excellent (GREEN)
- 100-110%: good (YELLOW)
- 90-100%: concerning, customers are shrinking (RED)
- Below 90%: critical retention problem (RED)

**How to Improve:**
- Drive product adoption and usage growth
- Implement usage-based or seat-based pricing that grows with customer success
- Proactive expansion selling through customer success
- Build features that serve larger teams and use cases

---

## 13. Gross Revenue Retention (GRR)

**Definition:** The percentage of revenue retained from existing customers excluding expansion - only accounting for contraction and churn.

**Formula:**
```
GRR = (Beginning MRR - Contraction MRR - Churned MRR) / Beginning MRR x 100
```

GRR is always less than or equal to 100% (capped at 100%).

**Healthy Range:**
- Above 95%: exceptional (GREEN)
- 90-95%: good (GREEN)
- 85-90%: acceptable (YELLOW)
- 80-85%: needs improvement (YELLOW)
- Below 80%: serious retention problem (RED)

**How to Improve:**
- Focus on reducing cancellations and downgrades
- Improve product-market fit for core use cases
- Better onboarding and time-to-value
- Proactive churn prevention through health scoring

---

## 14. Average Revenue Per User (ARPU)

**Definition:** The average monthly revenue generated per customer account.

**Formula:**
```
ARPU = MRR / Total Active Customers
```

**Healthy Range:** Varies widely by segment:
- Self-serve SMB: $20-$200/month
- SMB with sales: $200-$1,000/month
- Mid-market: $1,000-$5,000/month
- Enterprise: $5,000-$50,000+/month

**How to Improve:**
- Introduce higher-value pricing tiers
- Add premium features and add-ons
- Usage-based pricing that grows with customer value received
- Move upmarket to serve larger customers
- Bundle complementary products

---

## 15. Expansion MRR Rate

**Definition:** The percentage of MRR growth from existing customers through upgrades, add-ons, and increased usage.

**Formula:**
```
Expansion MRR Rate = Expansion MRR / Beginning MRR x 100
```

**Healthy Range:**
- Above 5% monthly: excellent (GREEN)
- 2-5% monthly: good (YELLOW)
- Below 2% monthly: limited expansion motion (RED)

**How to Improve:**
- Design pricing tiers that encourage natural upgrades
- Build features that serve expanding teams
- Proactive upsell motions through customer success
- Product-led expansion through usage limits and feature gates

---

## Traffic-Light Summary Table

| Metric | GREEN | YELLOW | RED |
|---|---|---|---|
| Monthly Logo Churn | <2% | 2-5% | >5% |
| Monthly Revenue Churn | <2% | 2-4% | >4% |
| Net Revenue Retention | >110% | 100-110% | <100% |
| Gross Revenue Retention | >90% | 80-90% | <80% |
| LTV:CAC Ratio | 3:1-5:1 | 2:1-3:1 or >5:1 | <2:1 |
| CAC Payback | <18 months | 18-24 months | >24 months |
| Rule of 40 | >40% | 30-40% | <30% |
| Burn Multiple | <1.5x | 1.5-3x | >3x |
| Quick Ratio | >4 | 2-4 | <2 |
| Magic Number | >0.75 | 0.5-0.75 | <0.5 |
| Expansion MRR Rate | >5% | 2-5% | <2% |
