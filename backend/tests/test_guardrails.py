"""
Unit tests for Guardrail Engine and Deterministic Safety Policies
Verifies retry limits, idempotency/duplicate protection, customer opt-out,
approval thresholds, and fail-closed safety posture.
"""
import pytest
from backend.app.schemas.contracts import GuardrailStatus, RecoveryAction, RiskLevel
from backend.app.services.guardrails import GuardrailEngine, GuardrailDecision, GuardrailService
from backend.app.models.entities import MerchantPolicy, Payment, Customer, Recovery

def test_no_action_always_allowed():
    decision = GuardrailEngine.evaluate(
        action=RecoveryAction.NO_ACTION,
        amount=5000.0,
        confidence=0.85
    )
    assert decision.status == GuardrailStatus.ALLOW
    assert decision.requires_approval is False
    assert decision.risk_level == RiskLevel.LOW

def test_disallowed_action_blocked():
    policy = MerchantPolicy(
        merchant_id="merch_1",
        allowed_actions=["NO_ACTION", "CUSTOMER_NOTIFICATION"]
    )
    decision = GuardrailEngine.evaluate(
        action=RecoveryAction.PAYMENT_LINK,
        amount=1500.0,
        confidence=0.90,
        policy=policy
    )
    assert decision.status == GuardrailStatus.BLOCK
    assert decision.requires_approval is False
    assert "not permitted by merchant policy" in decision.reason

def test_duplicate_action_blocked():
    existing = [
        Recovery(
            id="rec_test_123",
            merchant_id="merch_1",
            transaction_id="pay_123",
            executed_action="PAYMENT_LINK",
            execution_status="SUCCESS"
        )
    ]
    decision = GuardrailEngine.evaluate(

        action=RecoveryAction.PAYMENT_LINK,
        amount=2500.0,
        confidence=0.88,
        existing_recoveries=existing
    )
    assert decision.status == GuardrailStatus.BLOCK
    assert "Duplicate action prevented" in decision.reason

def test_max_retries_exceeded_blocked():
    policy = MerchantPolicy(max_retries=2)
    payment = Payment(retry_count=2)
    decision = GuardrailEngine.evaluate(
        action=RecoveryAction.RETRY,
        amount=1000.0,
        confidence=0.85,
        policy=policy,
        payment=payment
    )
    assert decision.status == GuardrailStatus.BLOCK
    assert "Maximum retry limit reached" in decision.reason

def test_customer_opted_out_blocked():
    customer = Customer(opted_out=True)
    decision = GuardrailEngine.evaluate(
        action=RecoveryAction.CUSTOMER_NOTIFICATION,
        amount=500.0,
        confidence=0.80,
        customer=customer
    )
    assert decision.status == GuardrailStatus.BLOCK
    assert "opted out" in decision.reason

def test_customer_notification_rate_limit_blocked():
    customer = Customer(opted_out=False, notification_count_24h=3)
    decision = GuardrailEngine.evaluate(
        action=RecoveryAction.CUSTOMER_NOTIFICATION,
        amount=500.0,
        confidence=0.80,
        customer=customer
    )
    assert decision.status == GuardrailStatus.BLOCK
    assert "frequency limit exceeded" in decision.reason

def test_high_value_transaction_requires_approval():
    policy = MerchantPolicy(approval_threshold=25000.0, auto_recovery_limit=10000.0)
    decision = GuardrailEngine.evaluate(
        action=RecoveryAction.PAYMENT_LINK,
        amount=30000.0,
        confidence=0.95,
        policy=policy
    )
    assert decision.status == GuardrailStatus.REQUIRE_APPROVAL
    assert decision.requires_approval is True
    assert decision.risk_level == RiskLevel.HIGH

def test_auto_recovery_limit_requires_approval():
    policy = MerchantPolicy(approval_threshold=50000.0, auto_recovery_limit=10000.0)
    decision = GuardrailEngine.evaluate(
        action=RecoveryAction.PAYMENT_LINK,
        amount=15000.0,
        confidence=0.90,
        policy=policy
    )
    assert decision.status == GuardrailStatus.REQUIRE_APPROVAL
    assert decision.requires_approval is True

def test_low_confidence_requires_approval():
    decision = GuardrailEngine.evaluate(
        action=RecoveryAction.PAYMENT_LINK,
        amount=1000.0,
        confidence=0.45  # below 60% threshold
    )
    assert decision.status == GuardrailStatus.REQUIRE_APPROVAL
    assert decision.requires_approval is True
    assert "below automatic execution threshold" in decision.reason

def test_human_escalation_requires_approval():
    decision = GuardrailEngine.evaluate(
        action=RecoveryAction.HUMAN_ESCALATION,
        amount=1000.0,
        confidence=0.90
    )
    assert decision.status == GuardrailStatus.REQUIRE_APPROVAL
    assert decision.requires_approval is True

def test_guardrail_service_alias():
    assert GuardrailService is GuardrailEngine
