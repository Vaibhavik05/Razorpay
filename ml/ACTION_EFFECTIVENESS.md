# Action Effectiveness Model

## What it predicts

The action-effectiveness model estimates `P(recovery | pre-decision payment context, action)` for:

- `NO_ACTION`
- `RETRY`
- `PAYMENT_LINK`
- `CUSTOMER_NOTIFICATION`
- `HUMAN_ESCALATION`

It is a response-surface model. It produces one probability for every allowed action in a payment context so a later decision layer can compare them.

## Data and methodology

The model uses the seven pre-decision features shared with the recovery-probability model, plus the candidate action as an encoded categorical feature. Training uses `data/train.csv` only. Each training payment is expanded into five context/action rows, with the corresponding synthetic potential-outcome column as the target.

The dataset contains `outcome_no_action`, `outcome_retry`, `outcome_payment_link`, `outcome_customer_notification`, and `outcome_human_escalation` for every row. Dataset validation confirms that `recovered` matches the potential outcome for the observed `action_taken`.

Observed action assignment is imbalanced and context-dependent, not randomized. Because the synthetic dataset provides all five potential outcomes, the model can be evaluated against synthetic counterfactual outcomes. These results are not a causal uplift estimate for production traffic.

## Limitations

The action probabilities describe estimated synthetic response associations. They do not prove that an intervention causes an incremental recovery in a live system. Production use requires randomized experimentation or another causal design, stable pre-decision history, and monitoring for policy and selection bias.

No hardcoded action uplift constants are used. Action probabilities come from the trained model artifact. Guardrails and Razorpay execution behavior remain separate.

## Phase 4 handoff

The recommendation layer exposes the full action-probability map. Phase 4 may combine those probabilities with intervention cost, risk, merchant policy, and constraints to select an action. Phase 3 does not perform ROI calculation or action selection by expected net value.

## Artifacts

- Model: `ml/artifacts/action_effectiveness_model_v1.0.joblib`
- Metrics: `ml/artifacts/action_effectiveness_metrics.json`
