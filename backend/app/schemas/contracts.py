from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field, field_validator
from enum import Enum

class RecoveryAction(str, Enum):
    NO_ACTION = "NO_ACTION"
    RETRY = "RETRY"
    PAYMENT_LINK = "PAYMENT_LINK"
    CUSTOMER_NOTIFICATION = "CUSTOMER_NOTIFICATION"
    HUMAN_ESCALATION = "HUMAN_ESCALATION"

class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"

class GuardrailStatus(str, Enum):
    ALLOW = "ALLOW"
    BLOCK = "BLOCK"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"

class ExecutionStatus(str, Enum):
    SUCCESS = "SUCCESS"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"

class RecoveryLifecycleStatus(str, Enum):
    IDENTIFIED = "IDENTIFIED"
    ANALYZED = "ANALYZED"
    RECOMMENDED = "RECOMMENDED"
    VALIDATED = "VALIDATED"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXECUTING = "EXECUTING"
    EXECUTED = "EXECUTED"
    RECOVERED = "RECOVERED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"

# Standard Response Envelopes
class ErrorDetail(BaseModel):
    code: str
    message: str
    details: Optional[Dict[str, Any]] = None

class StandardResponse(BaseModel):
    success: bool
    data: Optional[Any] = None
    message: Optional[str] = None
    error: Optional[ErrorDetail] = None

# Payment Analysis Contracts
class PaymentAnalyzeRequest(BaseModel):
    transaction_id: str
    merchant_id: str
    customer_id: str
    amount: float = Field(..., gt=0, description="Amount in INR")
    currency: str = "INR"
    payment_method: str
    failure_reason: str
    customer_type: str = "RETURNING"
    previous_successful_payments: int = 0
    previous_failed_payments: int = 0

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, v: str) -> str:
        if v.upper() != "INR":
            raise ValueError("Only INR is supported for MVP")
        return v.upper()

class PaymentAnalyzeData(BaseModel):
    transaction_id: str
    amount: float
    revenue_at_risk: float
    recovery_probability: float
    confidence: float
    risk_level: RiskLevel
    eligible_actions: List[RecoveryAction]

# Recovery Recommendation Contracts
class RecoveryRecommendRequest(BaseModel):
    transaction_id: str
    merchant_id: str
    customer_id: str
    amount: float = Field(..., gt=0)
    failure_reason: str
    customer_type: str = "RETURNING"
    recovery_probability: Optional[float] = None
    confidence: Optional[float] = None

class RecoveryRecommendationData(BaseModel):
    recovery_id: str
    transaction_id: str
    recommended_action: RecoveryAction
    recovery_probability: float
    expected_recovery: float
    expected_incremental_revenue: float
    intervention_cost: float
    expected_net_value: float
    confidence: float
    risk_level: RiskLevel
    requires_approval: bool
    reason: str
    action_probabilities: Dict[str, float] = Field(default_factory=dict)
    baseline_probability: float = 0.0
    action_comparisons: List[Dict[str, Any]] = Field(default_factory=list)
    uplift: float = 0.0
    expected_risk_cost: float = 0.0
    recommended_net_value: float = 0.0
    decision_reason: str = ""
    optimizer_recommendation: RecoveryAction = RecoveryAction.NO_ACTION
    guardrail_status: Optional[GuardrailStatus] = None
    guardrail_reason: Optional[str] = None
    decision_state: str = "RECOMMENDED"
    llm_explanation: Optional[Dict[str, Any]] = None

# Recovery Execution Contracts
class RecoveryExecuteRequest(BaseModel):
    recovery_id: str
    transaction_id: str
    action: RecoveryAction
    merchant_id: str

class RecoveryExecuteData(BaseModel):
    recovery_id: str
    transaction_id: Optional[str] = None
    action: Optional[RecoveryAction] = None
    execution_status: ExecutionStatus
    payment_link_id: Optional[str] = None
    payment_link_url: Optional[str] = None
    executed_at: Optional[str] = None
    requires_approval: Optional[bool] = None
    approval_reason: Optional[str] = None
    guardrail_status: Optional[GuardrailStatus] = None
    block_reason: Optional[str] = None
    decision_state: Optional[str] = None

# Recovery Status Contract
class RecoveryStatusData(BaseModel):
    recovery_id: str
    transaction_id: str
    status: RecoveryLifecycleStatus
    recommended_action: RecoveryAction
    execution_status: Optional[str] = None
    outcome: str = "PENDING"
    amount: float
    expected_incremental_revenue: float
    created_at: str
    updated_at: str

# Dashboard & Metrics Contracts
class TopOpportunity(BaseModel):
    recovery_id: str
    transaction_id: str
    amount: float
    failure_reason: str
    recommended_action: RecoveryAction
    expected_incremental_revenue: float
    confidence: float
    risk_level: RiskLevel

class DashboardData(BaseModel):
    revenue_at_risk: float
    recovered_revenue: float
    incremental_revenue: float
    recovery_rate: float
    average_recovery_value: float
    top_opportunities: List[TopOpportunity]

class ActionMetric(BaseModel):
    action: str
    recovery_rate: float
    recovered_revenue: float
    incremental_revenue: float

class MetricsData(BaseModel):
    total_failed_payments: int
    total_revenue_at_risk: float
    recovered_revenue: float
    incremental_revenue: float
    recovery_rate: float
    intervention_count: int
    average_recovery_value: float
    roi: float
    actions: Optional[List[ActionMetric]] = None

# Human Approval Contracts
class ApprovalRequestPayload(BaseModel):
    reviewer_id: str
    comment: Optional[str] = None

class RejectRequestPayload(BaseModel):
    reviewer_id: str
    reason: str

class ApprovalDecisionData(BaseModel):
    recovery_id: str
    approval_status: str
    approved_by: Optional[str] = None
    rejected_by: Optional[str] = None
    approved_at: Optional[str] = None
    rejection_reason: Optional[str] = None

# Audit Contracts
class AuditTimelineEvent(BaseModel):
    timestamp: str
    event: str
    action: Optional[str] = None
    details: Optional[Dict[str, Any]] = None

class AuditResponseData(BaseModel):
    recovery_id: str
    events: List[AuditTimelineEvent]

# Health Contracts
class HealthData(BaseModel):
    status: str = "healthy"
    service: str = "nexarecover-api"
    version: str = "1.0.0"

class ReadyData(BaseModel):
    api: str = "healthy"
    database: str = "healthy"
    ml_model: str = "healthy"
    guardrails: str = "healthy"
    razorpay_client: str = "healthy"
