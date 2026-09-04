from typing import Optional, List, Dict, Any
from backend.app.schemas.contracts import GuardrailStatus, RecoveryAction, RiskLevel
from backend.app.models.entities import Payment, Customer, MerchantPolicy, Recovery

class GuardrailDecision:
    def __init__(
        self,
        status: GuardrailStatus,
        requires_approval: bool,
        reason: str,
        risk_level: RiskLevel = RiskLevel.LOW
    ):
        self.status = status
        self.requires_approval = requires_approval
        self.reason = reason
        self.risk_level = risk_level

    def to_dict(self) -> Dict[str, Any]:
        return {
            "guardrail_status": self.status.value,
            "requires_approval": self.requires_approval,
            "reason": self.reason,
            "risk_level": self.risk_level.value
        }

class GuardrailEngine:
    """
    Deterministic Safety & Guardrail Engine (11_GUARDRAILS_SECURITY.md)
    Enforces transaction limits, retry limits, duplicate prevention, customer safety,
    and fail-closed behavior.
    """
    
    @staticmethod
    def evaluate(
        action: RecoveryAction,
        amount: float,
        confidence: float,
        policy: Optional[MerchantPolicy] = None,
        payment: Optional[Payment] = None,
        customer: Optional[Customer] = None,
        existing_recoveries: Optional[List[Recovery]] = None
    ) -> GuardrailDecision:
        try:
            # Sane defaults if policy not configured
            max_retries = policy.max_retries if policy else 2
            auto_recovery_limit = policy.auto_recovery_limit if policy else 10000.0
            approval_threshold = policy.approval_threshold if policy else 25000.0
            notifications_enabled = policy.notifications_enabled if policy else True
            allowed_actions = policy.allowed_actions if policy and policy.allowed_actions else [
                "NO_ACTION", "RETRY", "PAYMENT_LINK", "CUSTOMER_NOTIFICATION", "HUMAN_ESCALATION"
            ]
            
            # Rule 0: NO_ACTION is always allowed without execution
            if action == RecoveryAction.NO_ACTION:
                return GuardrailDecision(
                    status=GuardrailStatus.ALLOW,
                    requires_approval=False,
                    reason="No-action baseline approved. No intervention needed.",
                    risk_level=RiskLevel.LOW
                )

            # Rule 1: Action allowlist check
            if action.value not in allowed_actions:
                return GuardrailDecision(
                    status=GuardrailStatus.BLOCK,
                    requires_approval=False,
                    reason=f"Action '{action.value}' is not permitted by merchant policy.",
                    risk_level=RiskLevel.HIGH
                )

            # Rule 2: Duplicate Action Check
            if existing_recoveries:
                for rec in existing_recoveries:
                    if rec.executed_action == action.value and rec.execution_status in ["SUCCESS", "EXECUTED", "PENDING"]:
                        return GuardrailDecision(
                            status=GuardrailStatus.BLOCK,
                            requires_approval=False,
                            reason=f"Duplicate action prevented: '{action.value}' was already executed on this transaction.",
                            risk_level=RiskLevel.HIGH
                        )

            # Rule 3: Retry Limit Check
            if action == RecoveryAction.RETRY:
                current_retries = payment.retry_count if payment else 0
                if current_retries >= max_retries:
                    return GuardrailDecision(
                        status=GuardrailStatus.BLOCK,
                        requires_approval=False,
                        reason=f"Maximum retry limit reached ({current_retries}/{max_retries}).",
                        risk_level=RiskLevel.HIGH
                    )

            # Rule 4: Customer Communication & Opt-Out Check
            if action in [RecoveryAction.CUSTOMER_NOTIFICATION, RecoveryAction.PAYMENT_LINK]:
                if customer:
                    if customer.opted_out:
                        return GuardrailDecision(
                            status=GuardrailStatus.BLOCK,
                            requires_approval=False,
                            reason="Customer has opted out of communication.",
                            risk_level=RiskLevel.HIGH
                        )
                    if customer.notification_count_24h >= 3:
                        return GuardrailDecision(
                            status=GuardrailStatus.BLOCK,
                            requires_approval=False,
                            reason="Customer notification frequency limit exceeded (max 3 per 24 hours).",
                            risk_level=RiskLevel.MEDIUM
                        )
                if not notifications_enabled and action == RecoveryAction.CUSTOMER_NOTIFICATION:
                    return GuardrailDecision(
                        status=GuardrailStatus.BLOCK,
                        requires_approval=False,
                        reason="Merchant policy has disabled automated customer notifications.",
                        risk_level=RiskLevel.MEDIUM
                    )

            # Rule 5: Transaction Limit & Human-In-The-Loop Approval Check
            if amount > approval_threshold:
                return GuardrailDecision(
                    status=GuardrailStatus.REQUIRE_APPROVAL,
                    requires_approval=True,
                    reason=f"High-value transaction (₹{amount:,.2f}) exceeds approval threshold (₹{approval_threshold:,.2f}).",
                    risk_level=RiskLevel.HIGH
                )
            elif amount > auto_recovery_limit:
                return GuardrailDecision(
                    status=GuardrailStatus.REQUIRE_APPROVAL,
                    requires_approval=True,
                    reason=f"Transaction value (₹{amount:,.2f}) exceeds auto-recovery limit (₹{auto_recovery_limit:,.2f}). Human review required.",
                    risk_level=RiskLevel.MEDIUM
                )

            # Rule 6: Low Confidence Threshold Check
            if confidence < 0.60:
                return GuardrailDecision(
                    status=GuardrailStatus.REQUIRE_APPROVAL,
                    requires_approval=True,
                    reason=f"Model confidence ({confidence:.0%}) is below automatic execution threshold (60%).",
                    risk_level=RiskLevel.MEDIUM
                )

            # High Risk actions (Manual escalation)
            if action == RecoveryAction.HUMAN_ESCALATION:
                return GuardrailDecision(
                    status=GuardrailStatus.REQUIRE_APPROVAL,
                    requires_approval=True,
                    reason="Manual escalation requires human reviewer action.",
                    risk_level=RiskLevel.MEDIUM
                )

            # All guardrails passed
            return GuardrailDecision(
                status=GuardrailStatus.ALLOW,
                requires_approval=False,
                reason="Action is within merchant policy and safety limits.",
                risk_level=RiskLevel.LOW
            )

        except Exception as ex:
            # 11_GUARDRAILS_SECURITY.md Section 61: FAIL CLOSED
            return GuardrailDecision(
                status=GuardrailStatus.BLOCK,
                requires_approval=False,
                reason=f"Guardrail safety failure (Fail-Closed): {str(ex)}",
                risk_level=RiskLevel.HIGH
            )

# Backward-compatible alias
GuardrailService = GuardrailEngine

