import hashlib
import hmac
import json

import pytest

from backend.app.core.config import settings
from backend.app.models.entities import AuditEvent, Recovery
from backend.app.services.guardrails import GuardrailEngine
from backend.app.schemas.contracts import RecoveryAction, RiskLevel, GuardrailStatus
from backend.app.services import recovery_service
from backend.app.services.ml.action_effectiveness import action_effectiveness_model_service
from backend.tests.test_phase5_lifecycle import AUTH, REVIEWER, BASE_PROBABILITIES, patch_probabilities, recommend, seed_context, execute


def test_guardrail_action_allowlist_retry_limit_opt_out_and_frequency(db_session):
    seed_context(db_session)
    from backend.app.models.entities import Customer, MerchantPolicy, Payment
    customer = db_session.query(Customer).filter_by(id="CUST001").one()
    policy = db_session.query(MerchantPolicy).filter_by(merchant_id="MERCHANT001").one()
    payment = db_session.query(Payment).filter_by(id="PAY001").one()

    policy.allowed_actions = ["NO_ACTION", "RETRY"]
    denied = GuardrailEngine.evaluate(RecoveryAction.PAYMENT_LINK, 1000, 0.9, policy, payment, customer, [])
    assert denied.status == GuardrailStatus.BLOCK
    assert "not permitted" in denied.reason

    payment.retry_count = policy.max_retries
    retry = GuardrailEngine.evaluate(RecoveryAction.RETRY, 1000, 0.9, policy, payment, customer, [])
    assert retry.status == GuardrailStatus.BLOCK
    assert "Maximum retry limit" in retry.reason

    policy.allowed_actions = [
        "NO_ACTION", "RETRY", "PAYMENT_LINK", "CUSTOMER_NOTIFICATION", "HUMAN_ESCALATION"
    ]
    customer.opted_out = True
    opted_out = GuardrailEngine.evaluate(RecoveryAction.CUSTOMER_NOTIFICATION, 1000, 0.9, policy, payment, customer, [])
    assert opted_out.status == GuardrailStatus.BLOCK
    assert "opted out" in opted_out.reason

    customer.opted_out = False
    customer.notification_count_24h = 3
    frequency = GuardrailEngine.evaluate(RecoveryAction.PAYMENT_LINK, 1000, 0.9, policy, payment, customer, [])
    assert frequency.status == GuardrailStatus.BLOCK
    assert "frequency limit" in frequency.reason


def test_guardrail_high_value_low_confidence_and_human_escalation(db_session):
    seed_context(db_session)
    from backend.app.models.entities import MerchantPolicy, Payment
    policy = db_session.query(MerchantPolicy).filter_by(merchant_id="MERCHANT001").one()
    payment = db_session.query(Payment).filter_by(id="PAY001").one()

    high_value = GuardrailEngine.evaluate(RecoveryAction.PAYMENT_LINK, 30000, 0.9, policy, payment, None, [])
    assert high_value.status == GuardrailStatus.REQUIRE_APPROVAL
    assert high_value.requires_approval is True

    low_confidence = GuardrailEngine.evaluate(RecoveryAction.RETRY, 1000, 0.5, policy, payment, None, [])
    assert low_confidence.status == GuardrailStatus.REQUIRE_APPROVAL

    escalation = GuardrailEngine.evaluate(RecoveryAction.HUMAN_ESCALATION, 1000, 0.9, policy, payment, None, [])
    assert escalation.status == GuardrailStatus.REQUIRE_APPROVAL


def test_guardrail_exception_fails_closed():
    class BrokenPolicy:
        @property
        def max_retries(self):
            raise RuntimeError("secret-internal-value")

    decision = GuardrailEngine.evaluate(RecoveryAction.RETRY, 1000, 0.9, BrokenPolicy())
    assert decision.status == GuardrailStatus.BLOCK
    assert "secret-internal-value" not in decision.reason


def test_authentication_rejects_missing_invalid_and_fabricated_tokens(client):
    assert client.get("/api/v1/merchant/dashboard").status_code == 401
    assert client.get("/api/v1/merchant/dashboard", headers={"Authorization": "Bearer invalid"}).status_code == 401
    assert client.get("/api/v1/merchant/dashboard", headers={"Authorization": "Bearer user:MERCHANT:MERCHANT002"}).status_code == 401
    assert client.get("/api/v1/merchant/dashboard", headers={"Authorization": "Basic token"}).status_code == 401


def test_idempotency_key_conflict_is_rejected(client, db_session, monkeypatch):
    seed_context(db_session)
    patch_probabilities(monkeypatch, BASE_PROBABILITIES)
    data = recommend(client).json()["data"]
    first = execute(client, data["recovery_id"], "PAYMENT_LINK", "phase6-key")
    assert first.status_code == 200
    conflict = client.post(
        "/api/v1/recovery/execute",
        json={"recovery_id": data["recovery_id"], "transaction_id": "PAY001", "action": "RETRY", "merchant_id": "MERCHANT001"},
        headers={**AUTH, "Idempotency-Key": "phase6-key"},
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_KEY_CONFLICT"


def test_webhook_missing_modified_and_duplicate_signature_handling(client, db_session, monkeypatch):
    seed_context(db_session)
    patch_probabilities(monkeypatch, BASE_PROBABILITIES)
    data = recommend(client).json()["data"]
    execution = execute(client, data["recovery_id"], "PAYMENT_LINK", "phase6-webhook")
    payment_link_id = execution.json()["data"]["payment_link_id"]
    payload = {"event": "payment_link.paid", "payload": {"payment_link": {"entity": {"id": payment_link_id, "reference_id": "PAY001", "amount": 100000, "status": "paid"}}}}
    body = json.dumps(payload, separators=(",", ":")).encode()
    secret = (settings.RAZORPAY_WEBHOOK_SECRET or "mock_secret").encode()
    signature = hmac.new(secret, body, hashlib.sha256).hexdigest()
    assert client.post("/api/v1/webhooks/razorpay", content=body).status_code == 401
    modified = body.replace(b"100000", b"99999")
    assert client.post("/api/v1/webhooks/razorpay", content=modified, headers={"X-Razorpay-Signature": signature}).status_code == 401
    valid = client.post("/api/v1/webhooks/razorpay", content=body, headers={"X-Razorpay-Signature": signature})
    duplicate = client.post("/api/v1/webhooks/razorpay", content=body, headers={"X-Razorpay-Signature": signature})
    assert valid.status_code == 200
    assert duplicate.status_code == 200
    assert "already processed" in duplicate.json()["message"]


def test_error_response_does_not_leak_internal_details(client, db_session, monkeypatch):
    seed_context(db_session)
    monkeypatch.setattr(
        action_effectiveness_model_service,
        "predict_action_probabilities",
        lambda payment_data: (_ for _ in ()).throw(RuntimeError("secret-api-key-value")),
    )
    response = recommend(client)
    assert response.status_code == 503
    assert "secret-api-key-value" not in response.text
    assert "C:\\" not in response.text
    assert db_session.query(AuditEvent).filter_by(event_type="DECISION_FAILED").count() == 1


def test_cross_merchant_lifecycle_access_is_denied(client, db_session, monkeypatch):
    seed_context(db_session)
    patch_probabilities(monkeypatch, BASE_PROBABILITIES)
    data = recommend(client).json()["data"]
    beta = {"Authorization": "Bearer merchant_token_beta"}
    assert client.get(f"/api/v1/recovery/{data['recovery_id']}", headers=beta).status_code == 403
    assert client.get(f"/api/v1/audit/{data['recovery_id']}", headers=beta).status_code == 403
    assert client.post(f"/api/v1/recovery/{data['recovery_id']}/approve", json={"reviewer_id": "USER_REVIEWER_1"}, headers=beta).status_code == 403
    assert client.post(f"/api/v1/recovery/{data['recovery_id']}/reject", json={"reviewer_id": "USER_REVIEWER_1", "reason": "x"}, headers=beta).status_code == 403


def test_invalid_state_transitions_are_rejected(client, db_session, monkeypatch):
    seed_context(db_session)
    patch_probabilities(monkeypatch, BASE_PROBABILITIES)
    data = recommend(client).json()["data"]
    recovery = db_session.query(Recovery).filter_by(id=data["recovery_id"]).one()
    recovery.status = "REJECTED"
    db_session.commit()
    response = execute(client, recovery.id, "PAYMENT_LINK", "phase6-invalid-state")
    assert response.status_code == 400
    assert db_session.query(Recovery).filter_by(id=recovery.id).one().status == "REJECTED"
