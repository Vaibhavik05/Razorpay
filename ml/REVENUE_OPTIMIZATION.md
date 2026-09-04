# Uplift and Revenue Optimization

## Methodology

For each failed payment and allowed action, the Phase 3 response-surface model provides:

`P(recovery | pre-decision context, action)`

`NO_ACTION` is always included as the natural-recovery baseline.

```text
uplift = action_recovery_probability - natural_recovery_probability
expected_recovered_revenue = action_recovery_probability * transaction_amount
expected_incremental_revenue = uplift * transaction_amount
expected_net_value = expected_incremental_revenue - intervention_cost - expected_risk_cost
```

Uplift and incremental revenue remain signed. An intervention that lowers recovery probability is not silently converted to zero.

## Costs and risk

The intervention costs are centralized in `backend/app/services/optimizer.py` and are Buildathon simulation assumptions:

- `NO_ACTION`: INR 0
- `RETRY`: INR 2
- `CUSTOMER_NOTIFICATION`: INR 5
- `PAYMENT_LINK`: INR 20
- `HUMAN_ESCALATION`: INR 50

The project did not previously define an expected monetary risk cost. Phase 4 uses a transparent risk-level rate based on existing guardrail risk information:

- `LOW`: 0% of transaction amount
- `MEDIUM`: 1% of transaction amount
- `HIGH`: 2% of transaction amount

NO_ACTION always has zero risk cost. These rates are Buildathon simulation assumptions, not production loss estimates.

## Selection and guardrails

The optimizer compares every action allowed by merchant policy, ranks them by expected net value, and recommends NO_ACTION when no intervention has a strictly positive net value. A high recovery probability alone does not win if costs and risk make its net value lower.

The optimizer answers: "What is economically best?" Guardrails separately answer: "Is that action allowed?" The original optimizer recommendation and guardrail decision remain distinct; Phase 4 does not change guardrail policy or execution behavior.

## Metrics distinction and limitations

Expected recovered revenue is the modeled total recovery amount for an action. Expected incremental revenue is only the modeled difference from NO_ACTION. Neither is observed revenue, and neither is proven causal uplift in production.

The action model uses synthetic potential outcomes and observational, context-dependent action assignment. Its comparisons are synthetic counterfactual estimates. Production causal claims require randomized experimentation or another defensible causal design.

The recommendation API exposes action probabilities, baseline probability, full action comparisons, uplift, costs, risk cost, net value, rank, and deterministic decision reason for the next orchestration phase.