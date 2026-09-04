# Phase 6 Security, Guardrails, and Failure Testing

## Security boundaries

- Authentication accepts only the predefined demo tokens; fabricated `user:role:merchant` strings and fallback tokens are rejected.
- Merchant isolation is enforced for analysis, recommendation, dashboard, metrics, recovery status, execution, approval, rejection, and audit access.
- Guardrails enforce action allowlists, retry limits, communication opt-out/frequency limits, transaction approval thresholds, confidence thresholds, and human escalation approval.
- The optimizer recommendation remains separate from guardrail authorization.
- Execution requires an authorized merchant, matching recovery/action identifiers, an allowed lifecycle state, satisfied approval requirements, and an idempotency key.
- `NO_ACTION` is recorded as a decision and never invokes Razorpay execution.
- Webhooks verify HMAC signatures against the exact raw request body and require a known recovery/payment-link identity.

## Idempotency

Execution idempotency keys are globally checked. Reusing a key for the same recovery and action returns the cached result. Reusing it for another recovery or action returns a conflict and cannot execute a different request. Recommendation replay returns the existing active recovery record for the same transaction. Webhook replay is ignored after the processing audit event exists.

## Failure handling

Model and optimizer failures return structured unavailable responses and do not create executable recoveries. Guardrail errors fail closed. Razorpay client initialization or execution errors mark the recovery `FAILED` and write an audit event. API error responses do not include exception text, credentials, tokens, connection strings, or stack traces.

## Approval and state security

Approval and rejection require reviewer/admin roles, matching authenticated reviewer identity, merchant scope, and `APPROVAL_REQUIRED` state. Duplicate approvals/rejections are idempotent. Rejected, blocked, executed, and recovered records cannot be transitioned through approval incorrectly.

## Audit integrity

The existing audit trail records analysis, recommendation, optimizer output, guardrail results, approval/rejection, execution, webhook processing, outcomes, and component failures. Audit details contain merchant, recovery, action, decision, reason/type, and timestamp context without secret values.

## Test matrix

| Test | Expected | Actual | Status |
|---|---|---|---|
| Invalid/fabricated token | 401 | 401 | PASS |
| Missing/malformed auth | 401 | 401 | PASS |
| Action allowlist | Block | Block | PASS |
| Retry limit | Block with exact reason | Block | PASS |
| Customer opt-out | Block | Block | PASS |
| Notification frequency | Block | Block | PASS |
| High-value payment | Approval required | Approval required | PASS |
| Low confidence | Approval required | Approval required | PASS |
| Human escalation | Approval required | Approval required | PASS |
| Guardrail exception | Fail closed | Block | PASS |
| Duplicate recommendation | Same record | Same record | PASS |
| Duplicate execution | Cached response | Cached response | PASS |
| Idempotency key conflict | 409, no execution | 409 | PASS |
| Invalid/missing webhook signature | 401 | 401 | PASS |
| Modified webhook payload | 401 | 401 | PASS |
| Unknown recovery webhook | 404 | Rejected | PASS |
| Duplicate webhook | No second update | Ignored | PASS |
| Model failure | Structured failure, no record | 503, no record | PASS |
| Optimizer failure | Structured failure, no record | 503, no record | PASS |
| Execution failure | FAILED and audited | FAILED and audited | PASS |
| Cross-merchant status/audit/approval/rejection | 403 | 403 | PASS |
| Invalid lifecycle transition | Rejected, state preserved | Rejected | PASS |
| NO_ACTION execution | No Razorpay call | 400, audited | PASS |
| Error leakage | No internal details | Sanitized | PASS |
| Audit integrity | Security event recorded | Verified | PASS |

## Known limitations

The project uses predefined demo tokens and synthetic data. Production deployment requires a real identity provider, secret-managed credentials, rate limiting, durable event IDs, and operational monitoring. Those are outside Phase 6 and were not introduced here.

No real Razorpay execution was introduced. Datasets were not modified, and `data/test.csv` was not used for tuning.
