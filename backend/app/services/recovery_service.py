import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from backend.app.models.entities import Payment, Customer, MerchantPolicy, Recovery, AuditEvent
from backend.app.schemas.contracts import (
    RecoveryAction, RiskLevel, GuardrailStatus, RecoveryLifecycleStatus,
    PaymentAnalyzeRequest, PaymentAnalyzeData,
    RecoveryRecommendRequest, RecoveryRecommendationData,
    RecoveryStatusData
)
from backend.app.services.ml.model import ml_model_service
from backend.app.services.optimizer import RevenueOptimizer
from backend.app.services.guardrails import GuardrailEngine, GuardrailDecision
from backend.app.services.ai_explainer import StructuredAIExplainer
from backend.app.services.audit_service import AuditService

class RecoveryService:
    """
    Core Recovery Service coordinating ML, Optimization, Guardrails, and Auditing.
    """
    
    @staticmethod
    def analyze_payment(db: Session, request: PaymentAnalyzeRequest) -> PaymentAnalyzeData:
        # Check or create payment record in DB
        payment = db.query(Payment).filter(Payment.id == request.transaction_id).first()
        if not payment:
            payment = Payment(
                id=request.transaction_id,
                merchant_id=request.merchant_id,
                customer_id=request.customer_id,
                amount=request.amount,
                currency=request.currency,
                payment_method=request.payment_method,
                failure_reason=request.failure_reason,
                payment_status="FAILED",
                revenue_at_risk=request.amount,
                retry_count=0
            )
            db.add(payment)
            db.commit()
            db.refresh(payment)

        # ML Prediction
        req_dict = request.model_dump()
        rec_prob, confidence, model_ver = ml_model_service.predict(req_dict)
        
        # Determine initial risk level
        risk_level = RiskLevel.LOW
        if request.amount > 25000:
            risk_level = RiskLevel.HIGH
        elif request.amount > 10000 or confidence < 0.65:
            risk_level = RiskLevel.MEDIUM

        # Log audit event
        AuditService.log_event(
            db=db,
            event_type="PAYMENT_ANALYZED",
            merchant_id=request.merchant_id,
            payment_id=request.transaction_id,
            details={
                "amount": request.amount,
                "recovery_probability": rec_prob,
                "confidence": confidence,
                "model_version": model_ver
            }
        )

        return PaymentAnalyzeData(
            transaction_id=request.transaction_id,
            amount=request.amount,
            revenue_at_risk=request.amount,
            recovery_probability=rec_prob,
            confidence=confidence,
            risk_level=risk_level,
            eligible_actions=[
                RecoveryAction.NO_ACTION,
                RecoveryAction.RETRY,
                RecoveryAction.PAYMENT_LINK,
                RecoveryAction.CUSTOMER_NOTIFICATION
            ]
        )

    @staticmethod
    def recommend_recovery(db: Session, request: RecoveryRecommendRequest) -> RecoveryRecommendationData:
        # Load context
        payment = db.query(Payment).filter(Payment.id == request.transaction_id).first()
        customer = db.query(Customer).filter(Customer.id == request.customer_id).first()
        policy = db.query(MerchantPolicy).filter(MerchantPolicy.merchant_id == request.merchant_id).first()
        existing_recs = db.query(Recovery).filter(Recovery.transaction_id == request.transaction_id).all()

        # Determine recovery probability if not provided
        rec_prob = request.recovery_probability
        confidence = request.confidence
        if rec_prob is None or confidence is None:
            p_prob, p_conf, _ = ml_model_service.predict(request.model_dump())
            rec_prob = rec_prob or p_prob
            confidence = confidence or p_conf

        # Uplifts for candidate actions relative to baseline
        natural_prob = payment.natural_recovery_probability if payment else max(0.1, rec_prob - 0.25)
        action_uplifts = {
            RecoveryAction.RETRY: 0.15,
            RecoveryAction.PAYMENT_LINK: 0.26,
            RecoveryAction.CUSTOMER_NOTIFICATION: 0.18,
            RecoveryAction.HUMAN_ESCALATION: 0.20
        }

        allowed_actions_enum = [RecoveryAction.NO_ACTION, RecoveryAction.RETRY, RecoveryAction.PAYMENT_LINK, RecoveryAction.CUSTOMER_NOTIFICATION]
        if policy and policy.allowed_actions:
            allowed_actions_enum = [RecoveryAction(a) for a in policy.allowed_actions if a in RecoveryAction._value2member_map_]

        # Deterministic Revenue Optimizer
        best_action, evaluations = RevenueOptimizer.evaluate_candidate_actions(
            amount=request.amount,
            natural_recovery_prob=natural_prob,
            action_uplifts=action_uplifts,
            allowed_actions=allowed_actions_enum
        )

        chosen_eval = evaluations.get(best_action, evaluations[RecoveryAction.NO_ACTION])
        expected_rec = chosen_eval["expected_recovery"]
        inc_rev = chosen_eval["incremental_revenue"]
        cost = chosen_eval["intervention_cost"]
        net_val = chosen_eval["expected_net_value"]

        # Deterministic Guardrail Check
        guardrail_decision: GuardrailDecision = GuardrailEngine.evaluate(
            action=best_action,
            amount=request.amount,
            confidence=confidence,
            policy=policy,
            payment=payment,
            customer=customer,
            existing_recoveries=existing_recs
        )

        # Structured AI Explanation
        ai_exp = StructuredAIExplainer.generate_explanation(
            transaction_id=request.transaction_id,
            recommended_action=best_action,
            amount=request.amount,
            failure_reason=request.failure_reason,
            customer_type=request.customer_type,
            recovery_prob=rec_prob,
            incremental_revenue=inc_rev,
            confidence=confidence,
            requires_approval=guardrail_decision.requires_approval
        )

        # Create or update recovery record
        recovery_id = f"REC_{uuid.uuid4().hex[:6].upper()}"
        initial_status = RecoveryLifecycleStatus.RECOMMENDED.value
        if guardrail_decision.status == GuardrailStatus.REQUIRE_APPROVAL:
            initial_status = RecoveryLifecycleStatus.APPROVAL_REQUIRED.value
        elif guardrail_decision.status == GuardrailStatus.BLOCK:
            initial_status = RecoveryLifecycleStatus.BLOCKED.value

        recovery = Recovery(
            id=recovery_id,
            transaction_id=request.transaction_id,
            merchant_id=request.merchant_id,
            status=initial_status,
            recommended_action=best_action.value,
            recovery_probability=rec_prob,
            expected_recovery=expected_rec,
            expected_incremental_revenue=inc_rev,
            intervention_cost=cost,
            expected_net_value=net_val,
            confidence=confidence,
            risk_level=guardrail_decision.risk_level.value,
            requires_approval=guardrail_decision.requires_approval,
            approval_reason=guardrail_decision.reason if guardrail_decision.requires_approval else None,
            block_reason=guardrail_decision.reason if guardrail_decision.status == GuardrailStatus.BLOCK else None,
            reason=ai_exp["reason"]
        )
        db.add(recovery)
        db.commit()
        db.refresh(recovery)

        # Log audit events
        AuditService.log_event(
            db=db,
            event_type="RECOMMENDATION_GENERATED",
            merchant_id=request.merchant_id,
            payment_id=request.transaction_id,
            recovery_id=recovery_id,
            action=best_action.value,
            details={"expected_net_value": net_val, "expected_incremental_revenue": inc_rev}
        )

        guardrail_event_type = "GUARDRAIL_PASSED" if guardrail_decision.status == GuardrailStatus.ALLOW else (
            "GUARDRAIL_APPROVAL_REQUIRED" if guardrail_decision.status == GuardrailStatus.REQUIRE_APPROVAL else "GUARDRAIL_BLOCKED"
        )
        AuditService.log_event(
            db=db,
            event_type=guardrail_event_type,
            merchant_id=request.merchant_id,
            payment_id=request.transaction_id,
            recovery_id=recovery_id,
            action=best_action.value,
            details={"reason": guardrail_decision.reason, "status": guardrail_decision.status.value}
        )

        return RecoveryRecommendationData(
            recovery_id=recovery_id,
            transaction_id=request.transaction_id,
            recommended_action=best_action,
            recovery_probability=rec_prob,
            expected_recovery=expected_rec,
            expected_incremental_revenue=inc_rev,
            intervention_cost=cost,
            expected_net_value=net_val,
            confidence=confidence,
            risk_level=guardrail_decision.risk_level,
            requires_approval=guardrail_decision.requires_approval,
            reason=ai_exp["reason"]
        )

    @staticmethod
    def get_recovery_status(db: Session, recovery_id: str) -> RecoveryStatusData:
        rec = db.query(Recovery).filter(Recovery.id == recovery_id).first()
        if not rec:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "RECOVERY_NOT_FOUND", "message": f"Recovery record {recovery_id} not found"}
            )
            
        return RecoveryStatusData(
            recovery_id=rec.id,
            transaction_id=rec.transaction_id,
            status=RecoveryLifecycleStatus(rec.status),
            recommended_action=RecoveryAction(rec.recommended_action),
            execution_status=rec.execution_status,
            outcome=rec.outcome or "PENDING",
            amount=rec.expected_recovery,
            expected_incremental_revenue=rec.expected_incremental_revenue,
            created_at=rec.created_at.isoformat() + "Z",
            updated_at=rec.updated_at.isoformat() + "Z"
        )
