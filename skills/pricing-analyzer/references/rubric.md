# Pricing Rubric (pricing-rubric-v1)

How the model judges a SaaS company's own pricing and packaging in the `audit` command. The
script (`pricing_analyzer.py facts`) only normalizes tiers and does math; every score and label
below is a judgment that must quote evidence from that JSON, the pricing page or the user's data.

Last verified: 2026-10

## Contents

1. Rules for every score
2. Dimensions and weights
3. Dimension anchors
4. Findings: data-backed or judgment
5. Ranking findings and choosing the biggest constraint
6. Flags from the script
7. What not to conclude

---

## 1. Rules for every score

- Scale: 0-10 per dimension. Use the anchors in section 3; pick the anchor band first, then the
  number inside it.
- Evidence: every score cites at least one evidence ID that points to a JSON fact path (for
  example `own.tiers[2].added`, `cost_matrix.by_scenario[2].own_vs[0]`,
  `business.paid_tier_mix`), a quote from the pricing page, or a number the user gave.
- Status: `scored`, `na` (does not apply: for example `cost_to_serve` when the product has no
  variable cost per use) or `not_measured` (applies, but the input to judge it is missing). Never
  score a dimension you could not observe, and never give 0 for "not measured".
- Confidence per dimension:
  - high: the user's own data (tier mix, MRR by tier, survey, cost per unit) or a confirmed
    pricing table supports it.
  - medium: a pricing page read by the script and confirmed by the user, but no customer data;
    or a sourced benchmark for the same segment.
  - low: inferred from an unconfirmed page read, from a benchmark for another segment, or from
    general practice only.
- Composite: write the dimension scores to a JSON file and run `pricing_analyzer.py score`. The
  script drops `na` and `not_measured`, renormalizes, and returns the total only when at least
  60% of the applicable weight was measured. Never add the numbers yourself.

## 2. Dimensions and weights

| id | Dimension | Weight | Question it answers |
|---|---|---|---|
| value_metric | Value metric fit | 20 | Does the thing you charge for grow with the value the customer gets? |
| packaging_fences | Packaging and fences | 20 | Does each tier add what a different buyer will pay more for? |
| ladder_anchoring | Tier ladder and anchoring | 15 | Do the tiers form a clear good-better-best path with a sensible anchor? |
| price_level | Price level vs alternatives and evidence | 10 | At the customer's real size, is the price defensible against alternatives and willingness-to-pay evidence? |
| entry_offer | Entry offer (free plan, trial, reverse trial) | 10 | Does the way people try the product fit the motion and lead to paid? |
| enterprise_threshold | Enterprise threshold | 10 | Is the line between self-serve and "Contact sales" in the right place? |
| cost_to_serve | Cost to serve and margin floor | 10 | Do usage allowances (AI credits, outcomes, API calls) keep a margin floor? |
| annual_discounting | Annual billing and discounting | 5 | Is annual billing offered and is discounting controlled? |

The ids and weights are also in `RUBRIC_WEIGHTS` in `scripts/pricing_analyzer.py`; a test keeps
the two in sync.

## 3. Dimension anchors

### value_metric (20)

Evidence: `own.structure.billing_units`, each tier's `billing_unit`, `usage_unit`,
`included_usage`, `business.expansion_source_share`, `business.implied_seats_per_account`, what
the product does (`growth-context.md` `one_liner`).

- 0-2: The charge metric moves against value (for example per-seat pricing for a product whose
  value comes from automation that replaces seats), or it punishes the behavior that creates
  value (charging per collaborator for a product that needs wide sharing to work).
- 3-4: A generic metric (flat fee or seats) with no link to the value driver, and the evidence
  shows a problem: expansion comes almost only from upgrades, or ARPA sits far below the list
  price at the typical account size.
- 5-6: A reasonable proxy (seats for a collaboration tool) with known leaks: free viewers,
  shared logins, or AI features whose cost scales with use but are priced per seat.
- 7-8: The metric tracks value for most customers, and a second metric (credits, usage, add-on)
  captures heavy use. Expansion has more than one source.
- 9-10: The metric is the outcome or the unit of work the customer already counts (resolved
  conversations, processed documents, active locations), buyers can predict the bill, and
  expansion data confirms it grows with value.

Judgment calls: hybrid seats plus credits is now the most common primary model in survey data
(see `pricing-models.md`, section 9), but it is not automatically right; judge fit, not
fashion. Outcome pricing scores high only if the outcome is measurable without disputes.

### packaging_fences (20)

Evidence: each tier's `added`, `removed`, `limit_changes`, `inherits_from`; `feature_gates`;
`business.paid_tier_mix`; competitor tiers.

- 0-2: Tiers differ only by arbitrary caps, or the features that make the product work are
  missing from the plan most people buy.
- 3-4: Fences exist but do not map to different buyers (for example the jump to the next tier
  adds only cosmetic items), or a must-have for the core buyer sits behind sales.
- 5-6: Most fences map to a buyer difference (team vs company: admin, permissions, SSO), but
  one tier is crowded or empty, or one fence blocks adoption.
- 7-8: Each paid tier adds a coherent set for one persona (individual, team, company), limits
  rise in step, and nothing essential to the entry buyer is withheld.
- 9-10: As 7-8, and the tier mix or upgrade data shows customers self-select as designed.

How to judge a fence: name the persona each `added` list serves and what they would pay more
for. Security, compliance, admin, audit, data residency and integrations with company
systems are classic company-buyer fences; core workflow features usually are not. Feature
counts are never evidence: 3 features can be a strong fence and 15 a weak one.

### ladder_anchoring (15)

Evidence: `own.structure.price_ratios_between_paid_tiers`, `badged_tiers`, `tier_count`,
`business.paid_tier_mix`, `business.top_self_serve_tier_share`, the same ratios for competitors.

- 0-2: One paid tier only, or tiers so close in price and content that buyers cannot tell them
  apart.
- 3-4: A tier is skipped by almost everyone, or the recommended tier is not the one the target
  buyer should pick.
- 5-6: Clear good-better-best, but the anchor (top self-serve or enterprise tier) does little:
  no visible reason to look up, or a large gap with nothing in between for a common segment.
- 7-8: Three or four options, a highlighted tier that matches the target buyer, steps that
  match visible value steps, and a top tier that frames the middle one.
- 9-10: As 7-8, and the tier mix or tests show the ladder works (the highlighted tier is the
  most chosen among the target segment).

Compare step sizes with the competitors' ratios in the same JSON rather than with a generic
rule. A small share on the top self-serve tier is normal for an anchor; it is a problem only
if that tier is meant to be bought.

### price_level (10)

Evidence: `cost_matrix.by_scenario`, `cost_matrix.tier_map`, `cost_matrix.feature_gate_costs`,
`business.arpa_monthly`, Van Westendorp results if run, win/loss notes the user gives.

- 0-2: At the customer's real team sizes the product costs several times the closest
  alternatives for the same job with no visible reason, or so little that it signals a toy.
- 3-4: The price diverges from alternatives at the sizes that matter and the differentiation is
  not on the page.
- 5-6: Within the range of alternatives at the main segment size, but out of line at another
  important size (for example cheap at 5 seats, expensive at 100).
- 7-8: Defensible at every segment size the user cares about, with differentiation visible.
- 9-10: As 7-8, backed by willingness-to-pay evidence (survey, sales data, low price
  objections) for the main segment.

Always judge at the scenario that matches the user's typical account (`avg_seats_per_account`
or `icp`), never by an average across tiers. Public list prices hide negotiated enterprise
prices; say so when an enterprise tier is involved.

### entry_offer (10)

Evidence: `own.structure.has_free_tier`, free tier limits (`added`, `seat_max`), page signals
(`free_trial_days`, `no_card_required_mentioned`), `business.free_to_paid_pct` and the
`free_to_paid_benchmark` row, `gtm_motion`, `free_offer`, `card_required`.

- 0-2: The way to try the product contradicts the motion (no way to try a self-serve product,
  or a free plan that delivers the full job so nobody upgrades).
- 3-4: The offer fits the motion but leaks: the free plan has no upgrade trigger tied to value,
  or the trial ends before most users reach the activation event.
- 5-6: Reasonable offer; conversion unknown or below the benchmark band for the same offer type.
- 7-8: The offer fits the motion and the upgrade trigger appears when value appears; conversion
  is in the benchmark band.
- 9-10: As 7-8, with conversion at or above the benchmark's upper band and a deliberate design
  (for example a reverse trial that lets users feel the paid features first).

Use only the `free_to_paid.*` and `trial_to_paid.*` rows from the shared benchmark file, with
source, year and segment, and check that the conversion window matches.

### enterprise_threshold (10)

Evidence: `own.structure.has_custom_tier`, `self_serve_seat_ceiling`, the custom tier's `added`
list, `feature_gates` for SSO, SCIM and audit logs, `business.avg_discount_pct`, `acv` from the
context file.

- 0-2: Buyers who want to self-serve are forced into sales below a size where a sales call pays
  for itself, or large accounts can buy unlimited usage self-serve at a small-team price.
- 3-4: The threshold is unclear: no seat or usage line, or a security baseline (SSO) the
  target buyer requires is only available through sales.
- 5-6: A clear line, but the custom tier adds little beyond support, or sales-led discounts are
  large and unexplained.
- 7-8: The custom tier holds what large companies need (security, compliance, admin at scale,
  procurement terms), the self-serve ceiling sits where deal size justifies sales, and
  discounting is controlled.
- 9-10: As 7-8, with evidence that sales-led deals close above self-serve prices.

### cost_to_serve (10)

Evidence: `business.cost_to_serve` (margin at full allowance, overage margin), flags
`negative_margin_at_full_allowance`, `margin_below_target`, `overage_below_cost`; included
credits or usage per tier.

- `na` when the product has no meaningful variable cost per use.
- `not_measured` when allowances exist but the user did not give a cost per unit.
- 0-2: A heavy user on an included allowance costs more than they pay, or overage is priced
  below cost.
- 3-4: Positive margin, but below the user's own target at full allowance, with no cap, rollover
  limit or fair-use rule.
- 5-6: Margin holds for typical users; heavy users are protected by limits only.
- 7-8: Allowances are sized so full use keeps the target margin; overage is priced above cost;
  the buyer can predict the bill.
- 9-10: As 7-8, with usage data showing the allowance matches real use and credits expire or
  roll over by design.

Context, not a grade: the 2026 State of B2B Monetization survey reports a median target AI
margin of "about 50%" (see `pricing-models.md`, section 9). Grade against the user's own target
when they have one.

### annual_discounting (5)

Evidence: `business.annual_discount_pct_by_tier`, `own.structure.annual_billing_offered`,
`business.annual_share_pct`, `business.implied_discount_vs_list_pct`, flag
`discount_beyond_annual`, competitors' annual discounts in the same JSON.

- 0-2: No annual option for a product sold to businesses, or revenue per account is far below
  list with no explanation.
- 3-4: Annual exists but is hard to find or barely discounted relative to competitors, or
  sales discounts are uncontrolled.
- 5-6: Annual offered at a discount in line with the competitors in this run; mix unknown.
- 7-8: Annual offered and chosen by a meaningful share of customers; discounting explained.
- 9-10: As 7-8, with a deliberate policy (annual-only for some tiers, discount approval rules).

No sourced benchmark for annual discount size or annual mix is in the shared benchmark file.
Compare with the competitors' annual discounts that the script computed, and say so.

## 4. Findings: data-backed or judgment

Every finding in Diagnosis, Findings or Details carries one label:

- **Data-backed**: the claim is a computed number or a direct observation (a cost at a
  scenario, a tier mix share, a margin, a feature that appears only in the custom tier, a
  break-even churn). Cite the JSON path or the quote.
- **Judgment**: the claim interprets evidence (this fence does not match a buyer, this metric
  does not track value). Cite the evidence it rests on and say what would confirm it (a test,
  a survey, sales notes).

Each finding names the specific tier, feature or number it is about. "Pricing is confusing" is
not a finding; "Business adds SAML SSO and admin roles, which are company-buyer needs, but the
20-seat team in the ICP pays 2x for them" is.

## 5. Ranking findings and choosing the biggest constraint

1. Rank by expected revenue effect for the user's goal (`current_goal`): use the tier mix,
   MRR by tier and segment sizes to say how much revenue each finding touches. A fence problem
   on the tier with most of the MRR outranks a cosmetic issue on the anchor tier.
2. Then by confidence (data-backed before judgment).
3. Then by ease (a page or packaging change before a new billing system).
4. The biggest constraint is the top-ranked finding that limits the goal. Explain why it
   outranks the second one in one sentence.

## 6. Flags from the script

The `flags` list in the facts JSON is deterministic: each flag states the fact, the rule and the
basis (arithmetic on the user's data, a benchmark row id, or input completeness). Treat a flag
as a prompt to look, not a conclusion. Severity `high` means the arithmetic shows money lost
per customer (for example overage below cost); everything else needs judgment before it
becomes a finding.

## 7. What not to conclude

- No "premium" or "value" label from an average of list prices: averages ignore billing units
  and anchor tiers. Use the cost-at-scenario matrix.
- No "underpriced by X%" without willingness-to-pay evidence from this customer base.
- No expected lift from a price or packaging change; write "unknown until measured" and give a
  test or measurement plan.
- No claim about a competitor's revenue, customers or growth without a dated source URL.
- No price A/B test that shows different prices to similar visitors at the same time without
  saying it can create fairness and legal issues; prefer testing packaging, testing on new
  segments or regions, or a dated before/after change.
