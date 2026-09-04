"""
Integration tests for FastAPI REST API endpoints
Tests root, health, payments, recovery, merchant dashboard, and webhook flows.
"""
import pytest
from datetime import datetime, timezone
from backend.app.models.entities import Merchant, Payment, Customer, MerchantPolicy, Recovery

AUTH_HEADERS = {"Authorization": "Bearer merchant_token_acme"}

def _seed_base_data(db_session):
    now = datetime.now(timezone.utc)
    merchant = db_session.query(Merchant).filter_by(id="MERCHANT001").first()
    if not merchant:
        merchant = Merchant(
            id="MERCHANT001",
            name="Acme Payments Demo",
            category="E-commerce",
            created_at=now
        )
        policy = MerchantPolicy(
            merchant_id="MERCHANT001",
            max_retries=2,
            auto_recovery_limit=10000.0,
            approval_threshold=25000.0,
            notifications_enabled=True,
            allowed_actions=["NO_ACTION", "RETRY", "PAYMENT_LINK", "CUSTOMER_NOTIFICATION", "HUMAN_ESCALATION"]
        )
        customer = Customer(
            id="CUST001",
            segment="REGULAR",
            customer_tenure_days=45,
            previous_transaction_count=5,
            previous_success_count=4,
            historical_success_rate=0.8,
            opted_out=False,
            notification_count_24h=0
        )
        db_session.add(merchant)
        db_session.add(policy)
        db_session.add(customer)
        db_session.commit()

def test_root_endpoint(client):
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "NexaRecover AI"
    assert "version" in data

def test_health_endpoint(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    res = response.json()
    assert res["success"] is True
    assert res["data"]["status"] == "healthy"

def test_readiness_endpoint(client):
    response = client.get("/api/v1/ready")
    assert response.status_code == 200
    res = response.json()
    assert res["success"] is True
    assert res["data"]["api"] == "healthy"
    assert res["data"]["database"] == "healthy"

def test_unauthenticated_request_fails(client):
    response = client.get("/api/v1/merchant/dashboard")
    assert response.status_code == 401

def test_merchant_dashboard_authenticated(client, db_session):
    _seed_base_data(db_session)
    response = client.get("/api/v1/merchant/dashboard", headers=AUTH_HEADERS)
    assert response.status_code == 200
    res = response.json()
    assert res["success"] is True
    assert "recovered_revenue" in res["data"]
    assert "recovery_rate" in res["data"]

def test_payment_analyze_endpoint(client, db_session):
    _seed_base_data(db_session)
    now = datetime.now(timezone.utc)
    payment = Payment(
        id="pay_test_100",
        merchant_id="MERCHANT001",
        customer_id="CUST001",
        amount=3500.0,
        currency="INR",
        payment_method="UPI",
        failure_reason="GATEWAY_TIMEOUT",
        payment_status="FAILED",
        created_at=now
    )
    db_session.add(payment)
    db_session.commit()

    payload = {
        "transaction_id": "pay_test_100",
        "merchant_id": "MERCHANT001",
        "customer_id": "CUST001",
        "amount": 3500.0,
        "currency": "INR",
        "payment_method": "UPI",
        "failure_reason": "GATEWAY_TIMEOUT"
    }
    response = client.post("/api/v1/payments/analyze", json=payload, headers=AUTH_HEADERS)
    assert response.status_code == 200
    res = response.json()
    assert res["success"] is True
    assert "recovery_probability" in res["data"]
    assert "eligible_actions" in res["data"]

def test_recovery_recommend_endpoint(client, db_session):
    _seed_base_data(db_session)
    now = datetime.now(timezone.utc)
    payment = Payment(
        id="pay_test_200",
        merchant_id="MERCHANT001",
        customer_id="CUST001",
        amount=4500.0,
        currency="INR",
        payment_method="CARD",
        failure_reason="INSUFFICIENT_FUNDS",
        payment_status="FAILED",
        created_at=now
    )
    db_session.add(payment)
    db_session.commit()

    payload = {
        "transaction_id": "pay_test_200",
        "merchant_id": "MERCHANT001",
        "customer_id": "CUST001",
        "amount": 4500.0,
        "failure_reason": "INSUFFICIENT_FUNDS"
    }
    response = client.post("/api/v1/recovery/recommend", json=payload, headers=AUTH_HEADERS)
    assert response.status_code == 200
    res = response.json()
    assert res["success"] is True
    assert res["data"]["transaction_id"] == "pay_test_200"
    assert "recommended_action" in res["data"]
    assert "expected_net_value" in res["data"]
    assert "expected_recovery" in res["data"]

def test_recovery_execute_idempotent(client, db_session):
    _seed_base_data(db_session)
    now = datetime.now(timezone.utc)
    payment = Payment(
        id="pay_test_300",
        merchant_id="MERCHANT001",
        customer_id="CUST001",
        amount=2000.0,
        currency="INR",
        payment_method="UPI",
        failure_reason="NETWORK_ERROR",
        payment_status="FAILED",
        created_at=now
    )
    recovery = Recovery(
        id="rec_test_300",
        transaction_id="pay_test_300",
        merchant_id="MERCHANT001",
        status="RECOMMENDED",
        recommended_action="PAYMENT_LINK",
        expected_net_value=1200.0,
        confidence=0.85
    )
    db_session.add(payment)
    db_session.add(recovery)
    db_session.commit()

    headers = {**AUTH_HEADERS, "Idempotency-Key": "idem_test_key_001"}
    payload = {
        "recovery_id": "rec_test_300",
        "transaction_id": "pay_test_300",
        "merchant_id": "MERCHANT001",
        "action": "PAYMENT_LINK"
    }
    
    # First execution
    response1 = client.post("/api/v1/recovery/execute", json=payload, headers=headers)
    assert response1.status_code == 200
    res1 = response1.json()
    assert res1["success"] is True
    assert res1["data"]["execution_status"] in ["SUCCESS", "PENDING", "APPROVAL_REQUIRED"]

    # Replay with same idempotency key
    response2 = client.post("/api/v1/recovery/execute", json=payload, headers=headers)
    assert response2.status_code == 200
    res2 = response2.json()
    assert res2["success"] is True
    assert res2["data"]["recovery_id"] == res1["data"]["recovery_id"]


def test_webhook_processing(client, db_session):
    _seed_base_data(db_session)
    now = datetime.now(timezone.utc)
    payment = Payment(
        id="pay_test_wb",
        merchant_id="MERCHANT001",
        customer_id="CUST001",
        amount=2000.0,
        currency="INR",
        payment_method="UPI",
        failure_reason="NETWORK_ERROR",
        payment_status="FAILED",
        created_at=now
    )
    recovery = Recovery(
        id="rec_test_wb",
        transaction_id="pay_test_wb",
        merchant_id="MERCHANT001",
        status="EXECUTED",
        payment_link_id="plink_webhook_test"
    )
    db_session.add(payment)
    db_session.add(recovery)
    db_session.commit()

    webhook_payload = {
        "entity": "event",
        "event": "payment_link.paid",
        "payload": {
            "payment_link": {
                "entity": {
                    "id": "plink_webhook_test",
                    "reference_id": "pay_test_wb",
                    "amount": 200000,
                    "status": "paid"
                }
            }
        }
    }
    headers = {"X-Razorpay-Signature": "valid_mock_signature"}
    response = client.post("/api/v1/webhooks/razorpay", json=webhook_payload, headers=headers)
    assert response.status_code == 200
    res = response.json()
    assert res["success"] is True
