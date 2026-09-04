import hashlib
import hmac
import json
from datetime import datetime, timezone

from backend.app.core.config import settings
from backend.app.models.entities import (
    Customer,
    Merchant,
    MerchantPolicy,
    Payment,
    Recovery,
    AuditEvent,
)
from backend.app.services.ml.action_effectiveness import action_effectiveness_model_service
from backend.app.services import execution_service


AUTH = {"Authorization": "Bearer merchant_token_acme"}
REVIEWER = {"Authorization": "Bearer reviewer_token"}
BASE_PROBABILITIES = {
    "NO_ACTION": 0.30,
    "RETRY": 0.60,
    "PAYMENT_LINK": 0.75,
    "CUSTOMER_NOTIFICATION": 0.40,
    "HUMAN_ESCALATION": 0.50,
}


def seed_context(db_session, amount=1000.0, opted_out=False):
    now = datetime.now(timezone.utc)
    db_session.add(Merchant(id="MERCHANT001", name="Demo Merchant"))
    db_session.add(MerchantPolicy(
        merchant_id="MERCHANT001",
        max_retries=2,
        auto_recovery_limit=10000.0,
        approval_threshold=25000.0,
        allowed_actions=[
            "NO_ACTION", "RETRY", "PAYMENT_LINK", "CUSTOMER_NOTIFICATION", "HUMAN_ESCALATION"
        ],
    ))
    db_session.add(Customer(
        id="CUST001", segment="RETURNING", historical_success_rate=0.8,
        opted_out=opted_out, notification_count_24h=0,
    ))
    db_session.add(Payment(
        id="PAY001", merchant_id="MERCHANT001", customer_id="CUST001",
        amount=amount, payment_method="UPI", failure_reason="TIMEOUT",
        payment_status="FAILED", retry_count=0, created_at=now,
    ))
    db_session.commit()


def patch_probabilities(monkeypatch, probabilities):
    monkeypatch.setattr(
        action_effectiveness_model_service,
        "predict_action_probabilities",
        lambda payment_data: probabilities.copy(),
    )


def recommend(client):
    return client.post(
        "/api/v1/recovery/recommend",
        json={
            "transaction_id": "PAY001",
            "merchant_id": "MERCHANT001",
            "customer_id": "CUST001",
            "amount": 1000.0,
            "failure_reason": "TIMEOUT",
            "customer_type": "RETURNING",
        },
        headers=AUTH,
    )


def execute(client, recovery_id, action, key):
    return client.post(
        "/api/v1/recovery/execute",
        json={
            "recovery_id": recovery_id,
            "transaction_id": "PAY001",
            "action": action,
            "merchant_id": "MERCHANT001",
        },
        headers={**AUTH, "Idempotency-Key": key},
    )


def test_happy_path_recommend_execute_webhook_and_audit(client, db_session, monkeypatch):
    seed_context(db_session)
    patch_probabilities(monkeypatch, BASE_PROBABILITIES)

    recommendation = recommend(client).json()
    assert recommendation["success"] is True
    data = recommendation["data"]
    assert data["recommended_action"] == "PAYMENT_LINK"
    assert data["decision_state"] == "READY_FOR_EXECUTION"
    assert len(data["action_comparisons"]) == 5

    execution = execute(client, data["recovery_id"], "PAYMENT_LINK", "phase5-happy")
    assert execution.status_code == 200
    assert execution.json()["data"]["execution_status"] == "SUCCESS"

    webhook = {
        "event": "payment_link.paid",
        "payload": {"payment_link": {"entity": {
            "id": execution.json()["data"]["payment_link_id"],
            "reference_id": "PAY001",
            "amount": 100000,
            "status": "paid",
        }}},
    }
    body = json.dumps(webhook, separators=(",", ":")).encode()
    secret = (settings.RAZORPAY_WEBHOOK_SECRET or "mock_secret").encode()
    signature = hmac.new(secret, body, hashlib.sha256).hexdigest()
    outcome = client.post(
        "/api/v1/webhooks/razorpay", content=body,
        headers={"X-Razorpay-Signature": signature, "Content-Type": "application/json"},
    )
    assert outcome.status_code == 200
    recovery = db_session.query(Recovery).filter_by(id=data["recovery_id"]).one()
    assert recovery.status == "RECOVERED"
    assert recovery.outcome == "RECOVERED"
    assert db_session.query(AuditEvent).filter_by(recovery_id=recovery.id).count() >= 3


def test_no_action_does_not_execute(client, db_session, monkeypatch):
    probabilities = {action: 0.50 for action in BASE_PROBABILITIES}
    seed_context(db_session)
    patch_probabilities(monkeypatch, probabilities)

    recommendation = recommend(client).json()["data"]
    assert recommendation["recommended_action"] == "NO_ACTION"
    assert recommendation["decision_state"] == "NO_ACTION"
    response = execute(client, recommendation["recovery_id"], "NO_ACTION", "phase5-no-action")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "NO_ACTION_NOT_EXECUTABLE"


def test_guardrail_block_preserves_optimizer_recommendation(client, db_session, monkeypatch):
    seed_context(db_session, opted_out=True)
    patch_probabilities(monkeypatch, BASE_PROBABILITIES)

    data = recommend(client).json()["data"]
    assert data["optimizer_recommendation"] == "PAYMENT_LINK"
    assert data["decision_state"] == "BLOCKED_BY_GUARDRAIL"
    assert data["guardrail_status"] == "BLOCK"
    assert "opted out" in data["guardrail_reason"]


def test_approval_required_then_approve_and_execute(client, db_session, monkeypatch):
    seed_context(db_session, amount=30000.0)
    patch_probabilities(monkeypatch, BASE_PROBABILITIES)
    response = client.post(
        "/api/v1/recovery/recommend",
        json={
            "transaction_id": "PAY001", "merchant_id": "MERCHANT001", "customer_id": "CUST001",
            "amount": 30000.0, "failure_reason": "TIMEOUT", "customer_type": "RETURNING",
        }, headers=AUTH,
    )
    data = response.json()["data"]
    assert data["decision_state"] == "APPROVAL_REQUIRED"
    approved = client.post(
        f"/api/v1/recovery/{data['recovery_id']}/approve",
        json={"reviewer_id": "USER_REVIEWER_1", "comment": "Reviewed"}, headers=REVIEWER,
    )
    assert approved.status_code == 200
    execution = client.post(
        "/api/v1/recovery/execute",
        json={"recovery_id": data["recovery_id"], "transaction_id": "PAY001", "action": "PAYMENT_LINK", "merchant_id": "MERCHANT001"},
        headers={**AUTH, "Idempotency-Key": "phase5-approval"},
    )
    assert execution.status_code == 200
    assert execution.json()["data"]["execution_status"] == "SUCCESS"


def test_rejection_is_idempotent_and_not_executable(client, db_session, monkeypatch):
    seed_context(db_session, amount=30000.0)
    patch_probabilities(monkeypatch, BASE_PROBABILITIES)
    data = client.post(
        "/api/v1/recovery/recommend",
        json={"transaction_id": "PAY001", "merchant_id": "MERCHANT001", "customer_id": "CUST001", "amount": 30000.0, "failure_reason": "TIMEOUT"},
        headers=AUTH,
    ).json()["data"]
    rejected = client.post(
        f"/api/v1/recovery/{data['recovery_id']}/reject",
        json={"reviewer_id": "USER_REVIEWER_1", "reason": "Not approved"}, headers=REVIEWER,
    )
    assert rejected.status_code == 200
    repeated = client.post(
        f"/api/v1/recovery/{data['recovery_id']}/reject",
        json={"reviewer_id": "USER_REVIEWER_1", "reason": "Not approved"}, headers=REVIEWER,
    )
    assert repeated.status_code == 200
    blocked_execution = execute(client, data["recovery_id"], "PAYMENT_LINK", "phase5-rejected")
    assert blocked_execution.status_code == 400


def test_duplicate_recommendation_and_execution_are_idempotent(client, db_session, monkeypatch):
    seed_context(db_session)
    patch_probabilities(monkeypatch, BASE_PROBABILITIES)
    first = recommend(client).json()["data"]
    second = recommend(client).json()["data"]
    assert second["recovery_id"] == first["recovery_id"]
    assert db_session.query(Recovery).filter_by(transaction_id="PAY001").count() == 1

    first_execution = execute(client, first["recovery_id"], "PAYMENT_LINK", "phase5-duplicate")
    second_execution = execute(client, first["recovery_id"], "PAYMENT_LINK", "phase5-duplicate")
    assert first_execution.status_code == second_execution.status_code == 200
    assert first_execution.json()["data"]["payment_link_id"] == second_execution.json()["data"]["payment_link_id"]


def test_invalid_webhook_and_cross_merchant_access_are_rejected(client, db_session, monkeypatch):
    seed_context(db_session)
    patch_probabilities(monkeypatch, BASE_PROBABILITIES)
    data = recommend(client).json()["data"]
    invalid = client.post(
        "/api/v1/webhooks/razorpay", content=b'{"event":"payment.captured"}',
        headers={"X-Razorpay-Signature": "invalid"},
    )
    assert invalid.status_code == 401

    cross = client.get(
        f"/api/v1/recovery/{data['recovery_id']}",
        headers={"Authorization": "Bearer merchant_token_beta"},
    )
    assert cross.status_code == 403


def test_model_failure_fails_closed(client, db_session, monkeypatch):
    seed_context(db_session)
    monkeypatch.setattr(
        action_effectiveness_model_service,
        "predict_action_probabilities",
        lambda payment_data: (_ for _ in ()).throw(RuntimeError("model unavailable")),
    )
    response = recommend(client)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "DECISION_ENGINE_UNAVAILABLE"
    assert db_session.query(Recovery).count() == 0


def test_execution_failure_marks_recovery_failed(client, db_session, monkeypatch):
    seed_context(db_session)
    patch_probabilities(monkeypatch, BASE_PROBABILITIES)
    data = recommend(client).json()["data"]
    monkeypatch.setattr(
        execution_service,
        "get_razorpay_client",
        lambda: (_ for _ in ()).throw(RuntimeError("mock execution failure")),
    )

    response = execute(client, data["recovery_id"], "PAYMENT_LINK", "phase5-execution-failure")
    assert response.status_code == 500
    recovery = db_session.query(Recovery).filter_by(id=data["recovery_id"]).one()
    assert recovery.status == "FAILED"
    assert recovery.execution_status == "FAILED"