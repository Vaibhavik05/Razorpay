from sqlalchemy import Column, String, Float, Integer, Boolean, DateTime, Text, ForeignKey, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from backend.app.core.database import Base

class Merchant(Base):
    __tablename__ = "merchants"
    
    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    category = Column(String, default="GENERAL")
    size = Column(String, default="MEDIUM")
    monthly_volume = Column(Float, default=1000000.0)
    recovery_preference = Column(String, default="BALANCED")
    api_key_hash = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    policy = relationship("MerchantPolicy", back_populates="merchant", uselist=False)
    payments = relationship("Payment", back_populates="merchant")

class MerchantPolicy(Base):
    __tablename__ = "merchant_policies"
    
    merchant_id = Column(String, ForeignKey("merchants.id"), primary_key=True)
    max_retries = Column(Integer, default=2)
    auto_recovery_limit = Column(Float, default=10000.0)
    approval_threshold = Column(Float, default=25000.0)
    notifications_enabled = Column(Boolean, default=True)
    allowed_actions = Column(JSON, default=lambda: ["NO_ACTION", "RETRY", "PAYMENT_LINK", "CUSTOMER_NOTIFICATION", "HUMAN_ESCALATION"])
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    merchant = relationship("Merchant", back_populates="policy")

class Customer(Base):
    __tablename__ = "customers"
    
    id = Column(String, primary_key=True, index=True)
    segment = Column(String, default="REGULAR")
    customer_tenure_days = Column(Integer, default=30)
    previous_transaction_count = Column(Integer, default=0)
    previous_success_count = Column(Integer, default=0)
    previous_failure_count = Column(Integer, default=0)
    previous_recovery_count = Column(Integer, default=0)
    historical_success_rate = Column(Float, default=0.8)
    opted_out = Column(Boolean, default=False)
    notification_count_24h = Column(Integer, default=0)
    
    payments = relationship("Payment", back_populates="customer")

class Payment(Base):
    __tablename__ = "payments"
    
    id = Column(String, primary_key=True, index=True)
    merchant_id = Column(String, ForeignKey("merchants.id"), index=True, nullable=False)
    customer_id = Column(String, ForeignKey("customers.id"), index=True, nullable=False)
    amount = Column(Float, nullable=False)
    currency = Column(String, default="INR")
    payment_method = Column(String, default="CARD")
    card_type = Column(String, nullable=True)
    issuer_type = Column(String, nullable=True)
    payment_status = Column(String, default="FAILED")  # FAILED, SUCCESS, PENDING
    failure_category = Column(String, nullable=True)
    failure_reason = Column(String, default="TIMEOUT")
    gateway_response_code = Column(String, nullable=True)
    retry_count = Column(Integer, default=0)
    revenue_at_risk = Column(Float, default=0.0)
    natural_recovery_probability = Column(Float, default=0.3)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    merchant = relationship("Merchant", back_populates="payments")
    customer = relationship("Customer", back_populates="payments")
    recovery = relationship("Recovery", back_populates="payment", uselist=False)

class Recovery(Base):
    __tablename__ = "recoveries"
    
    id = Column(String, primary_key=True, index=True)  # e.g. REC789 or REC_pay_000001
    transaction_id = Column(String, ForeignKey("payments.id"), index=True, nullable=False)
    merchant_id = Column(String, ForeignKey("merchants.id"), index=True, nullable=False)
    
    # Lifecycle status: IDENTIFIED, ANALYZED, RECOMMENDED, VALIDATED, APPROVAL_REQUIRED, APPROVED, REJECTED, EXECUTING, EXECUTED, RECOVERED, FAILED, BLOCKED, EXPIRED, CANCELLED
    status = Column(String, default="IDENTIFIED", index=True)
    
    # Intelligence / Decision values
    recommended_action = Column(String, default="NO_ACTION")
    recovery_probability = Column(Float, default=0.0)
    expected_recovery = Column(Float, default=0.0)
    expected_incremental_revenue = Column(Float, default=0.0)
    intervention_cost = Column(Float, default=0.0)
    expected_net_value = Column(Float, default=0.0)
    confidence = Column(Float, default=0.0)
    risk_level = Column(String, default="LOW")  # LOW, MEDIUM, HIGH
    requires_approval = Column(Boolean, default=False)
    approval_reason = Column(String, nullable=True)
    block_reason = Column(String, nullable=True)
    reason = Column(Text, nullable=True)
    
    # Execution values
    executed_action = Column(String, nullable=True)
    execution_status = Column(String, nullable=True)  # SUCCESS, FAILED, APPROVAL_REQUIRED, BLOCKED
    payment_link_id = Column(String, nullable=True)
    payment_link_url = Column(String, nullable=True)
    executed_at = Column(DateTime, nullable=True)
    
    # Outcome values
    outcome = Column(String, default="PENDING")  # PENDING, RECOVERED, NOT_RECOVERED, FAILED
    recovered_amount = Column(Float, default=0.0)
    recovery_time_minutes = Column(Float, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    payment = relationship("Payment", back_populates="recovery")
    approvals = relationship("ApprovalRequest", back_populates="recovery")

class ApprovalRequest(Base):
    __tablename__ = "approval_requests"
    
    id = Column(String, primary_key=True, index=True)
    recovery_id = Column(String, ForeignKey("recoveries.id"), index=True, nullable=False)
    reviewer_id = Column(String, nullable=True)
    approval_status = Column(String, default="PENDING")  # PENDING, APPROVED, REJECTED, EXPIRED
    reason = Column(String, nullable=True)
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    reviewed_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)
    
    recovery = relationship("Recovery", back_populates="approvals")

class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    
    idempotency_key = Column(String, primary_key=True, index=True)
    recovery_id = Column(String, index=True, nullable=False)
    action = Column(String, nullable=False)
    status_code = Column(Integer, default=200)
    response_json = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class AuditEvent(Base):
    __tablename__ = "audit_events"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    event_type = Column(String, index=True, nullable=False)  # PAYMENT_ANALYZED, RECOMMENDATION_GENERATED, GUARDRAIL_PASSED, GUARDRAIL_BLOCKED, ACTION_EXECUTED, PAYMENT_RECOVERED
    recovery_id = Column(String, index=True, nullable=True)
    payment_id = Column(String, index=True, nullable=True)
    merchant_id = Column(String, index=True, nullable=False)
    user_id = Column(String, nullable=True)
    action = Column(String, nullable=True)
    details = Column(JSON, nullable=True)
