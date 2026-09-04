"""Run the complete NexaRecover lifecycle against an isolated mock database."""
import hashlib
import hmac
import json
from datetime import datetime, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.main import app
from backend.app.core.database import Base, get_db
from backend.app.core.config import settings
from backend.app.models.entities import Customer, Merchant, MerchantPolicy, Payment
from backend.app.services.ml.action_effectiveness import action_effectiveness_model_service

ENGINE = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
SESSION = sessionmaker(autocommit=False, autoflush=False, bind=ENGINE)
AUTH = {"Authorization": "Bearer merchant_token_acme"}


def make_db():
    Base.metadata.create_all(bind=ENGINE)
    db = SESSION()
    db.add(Merchant(id="MERCHANT001", name="NexaRecover Demo"))
    db.add(MerchantPolicy(merchant_id="MERCHANT001", approval_threshold=25000.0, auto_recovery_limit=10000.0))
    db.add(Customer(id="CUST001", segment="RETURNING", historical_success_rate=0.8, notification_count_24h=0))
    db.commit()
    return db


def add_payment(db, payment_id, amount=1000.0, opted_out=False):
    customer = db.query(Customer).filter_by(id="CUST001").one()
    customer.opted_out = opted_out
    db.add(Payment(id=payment_id, merchant_id="MERCHANT001", customer_id=customer.id, amount=amount,
                   payment_method="UPI", failure_reason="TIMEOUT", payment_status="FAILED",
                   retry_count=0, created_at=datetime.now(timezone.utc)))
    db.commit()


def recommend(client, payment_id, amount):
    return client.post("/api/v1/recovery/recommend", json={
        "transaction_id": payment_id, "merchant_id": "MERCHANT001", "customer_id": "CUST001",
        "amount": amount, "failure_reason": "TIMEOUT", "customer_type": "RETURNING",
    }, headers=AUTH)


def main():
    db = make_db()
    app.dependency_overrides[get_db] = lambda: db
    try:
        with TestClient(app) as client:
            payment_probs = {"NO_ACTION": 0.30, "RETRY": 0.60, "PAYMENT_LINK": 0.75,
                             "CUSTOMER_NOTIFICATION": 0.40, "HUMAN_ESCALATION": 0.50}
            add_payment(db, "DEMO_SUCCESS")
            with patch.object(action_effectiveness_model_service, "predict_action_probabilities", return_value=payment_probs):
                recommendation = recommend(client, "DEMO_SUCCESS", 1000.0).json()["data"]
            execution = client.post("/api/v1/recovery/execute", json={
                "recovery_id": recommendation["recovery_id"], "transaction_id": "DEMO_SUCCESS",
                "action": "PAYMENT_LINK", "merchant_id": "MERCHANT001",
            }, headers={**AUTH, "Idempotency-Key": "demo-success"}).json()["data"]
            payload = {"event": "payment_link.paid", "payload": {"payment_link": {"entity": {
                "id": execution["payment_link_id"], "reference_id": "DEMO_SUCCESS", "amount": 100000, "status": "paid"}}}}
            body = json.dumps(payload, separators=(",", ":")).encode()
            signature = hmac.new((settings.RAZORPAY_WEBHOOK_SECRET or "mock_secret").encode(), body, hashlib.sha256).hexdigest()
            webhook = client.post("/api/v1/webhooks/razorpay", content=body, headers={"X-Razorpay-Signature": signature}).json()

            add_payment(db, "DEMO_NO_ACTION")
            with patch.object(action_effectiveness_model_service, "predict_action_probabilities", return_value={a: 0.5 for a in payment_probs}):
                no_action = recommend(client, "DEMO_NO_ACTION", 1000.0).json()["data"]

            add_payment(db, "DEMO_BLOCKED", opted_out=True)
            with patch.object(action_effectiveness_model_service, "predict_action_probabilities", return_value=payment_probs):
                blocked = recommend(client, "DEMO_BLOCKED", 1000.0).json()["data"]

            add_payment(db, "DEMO_APPROVAL", amount=30000.0)
            with patch.object(action_effectiveness_model_service, "predict_action_probabilities", return_value=payment_probs):
                approval = recommend(client, "DEMO_APPROVAL", 30000.0).json()["data"]

            add_payment(db, "DEMO_DUPLICATE")
            with patch.object(action_effectiveness_model_service, "predict_action_probabilities", return_value=payment_probs):
                first = recommend(client, "DEMO_DUPLICATE", 1000.0).json()["data"]
                second = recommend(client, "DEMO_DUPLICATE", 1000.0).json()["data"]
            duplicate = {"same_recovery_id": first["recovery_id"] == second["recovery_id"]}

            print(json.dumps({
                "successful_recovery": {"action": recommendation["recommended_action"], "execution": execution["execution_status"], "webhook": webhook["success"]},
                "no_action": {"decision_state": no_action["decision_state"], "action": no_action["recommended_action"]},
                "guardrail_block": {"decision_state": blocked["decision_state"], "guardrail_status": blocked["guardrail_status"]},
                "approval_required": {"decision_state": approval["decision_state"], "requires_approval": approval["requires_approval"]},
                "duplicate_recommendation": duplicate,
            }, indent=2))
    finally:
        app.dependency_overrides.clear()
        db.close()
        Base.metadata.drop_all(bind=ENGINE)


if __name__ == "__main__":
    main()
