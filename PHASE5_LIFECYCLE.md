# NexaRecover Phase 5 Lifecycle

```text
FAILED PAYMENT
  -> ANALYZED
  -> ML RECOVERY PROBABILITY
  -> ACTION EFFECTIVENESS
  -> REVENUE OPTIMIZATION
  -> GUARDRAIL CHECK
  -> RECOMMENDED / NO_ACTION / BLOCKED / APPROVAL_REQUIRED
  -> APPROVED (when required)
  -> EXECUTING
  -> EXECUTED
  -> WEBHOOK OUTCOME
  -> RECOVERED or FAILED
  -> AUDIT and METRICS
```

## Decision and execution separation

The optimizer determines the economically best action from modeled probabilities, signed uplift, intervention cost, and expected risk cost. The guardrail engine independently determines whether that recommendation is allowed. A blocked or approval-required recommendation is never silently replaced with another action.

`NO_ACTION` is a valid final decision. It creates no Razorpay request and is recorded as a decision rather than an execution.

## Approval workflow

High-value and policy-sensitive recommendations enter `APPROVAL_REQUIRED`. Authenticated reviewers or administrators approve or reject within the merchant scope. Approval and rejection are idempotent. Approval does not bypass the execution service's state and guardrail checks.

## Execution and idempotency

Execution requires an authorized merchant, matching recovery and action identifiers, a valid lifecycle state, satisfied approval requirements, and an `Idempotency-Key`. Replays return the cached result and do not create duplicate payment links or actions. Razorpay uses the existing mock client by default; no live credentials or real-money behavior was added.

## Webhook and outcomes

Webhook signatures are verified against the exact raw request body. Known recovery IDs or payment-link references are required; unknown events are rejected rather than attached to an arbitrary pending recovery. Duplicate processed webhook events are ignored. Successful events update recovery/payment outcome fields and write audit events.

## Audit and metrics

Analysis, recommendation replay, optimizer comparisons, guardrail results, approvals, rejections, execution, webhook processing, outcomes, and component failures are recorded in the existing audit trail. Metrics continue to aggregate recorded database outcomes and executed recoveries, not recommendations alone.

## Failure handling and isolation

Model failures return a structured unavailable response and do not create a recovery record. Execution failures mark the recovery `FAILED` and are audited. Authentication and merchant isolation are enforced on recommendation, execution, status, approval, rejection, and audit endpoints.

Phase 5 uses the existing synthetic/counterfactual model outputs and does not claim production causal uplift. Datasets, including `data/test.csv`, are not used for lifecycle tuning.
