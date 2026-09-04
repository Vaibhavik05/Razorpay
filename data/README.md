# NexaRecover AI — Synthetic Dataset v1.0

This dataset is **100% synthetic** and does not represent real Razorpay, merchant, customer, gateway, or payment data.

## Files
- `payments.csv` — 50,000 payment/recovery opportunity records.
- `train.csv` — 40,000 records (80%).
- `test.csv` — 10,000 held-out records (20%).
- `merchants.csv` — synthetic merchant reference table.
- `customers.csv` — synthetic customer reference table.
- `validation_report.json` — automated schema/data-quality checks.

## Reproducibility
Random seed: `42`

## Synthetic causal evaluation
`outcome_*` columns are synthetic potential outcomes. They are included for evaluating action-selection/incremental-recovery logic and must not be presented as observed production outcomes.

## Cost assumptions
Synthetic intervention costs:
- NO_ACTION: ₹0
- RETRY: approximately ₹1.50
- PAYMENT_LINK: approximately ₹2.50
- CUSTOMER_NOTIFICATION: approximately ₹1.00
- HUMAN_ESCALATION: approximately ₹18.00

These are project assumptions only and are **not** Razorpay internal costs.

## Important leakage note
For a real-time prediction model, do not use post-decision fields such as `recovered`, `recovery_time_minutes`, `recovered_amount`, recovery status, or future action outcomes as model inputs.


## Incremental-revenue definitions (v1.1 correction)

For each row, the synthetic potential outcome for the selected action is compared with `outcome_no_action`.

`incremental_recovery = selected_action_outcome - outcome_no_action`

Possible values:
- `+1` — selected action creates additional recovery relative to no action.
- `0` — no incremental recovery difference.
- `-1` — selected action performs worse than no action in the synthetic potential-outcome world.

`incremental_revenue = incremental_recovery * transaction_amount - intervention_cost`

This is a synthetic evaluation metric. It must not be presented as observed production revenue impact.
