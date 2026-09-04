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
from backend.app.services.ml.action_effectiveness import action_effectiveness_model_service
from backend.app.services.optimizer import RevenueOptimizer
from backend.app.services.guardrails import GuardrailEngine, GuardrailDecision
from backend.app.services.ai_explainer import StructuredAIExplainer
from backend.app.services.llm_explainer import llm_explainer
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

        existing_recommendation = next(
            (item for item in existing_recs if item.status in [
                RecoveryLifecycleStatus.RECOMMENDED.value,
                RecoveryLifecycleStatus.APPROVAL_REQUIRED.value,
                RecoveryLifecycleStatus.APPROVED.value,
                RecoveryLifecycleStatus.BLOCKED.value,
            ]),
            None,
        )

        # Determine recovery probability if not provided
        rec_prob = request.recovery_probability
        confidence = request.confidence
        if rec_prob is None or confidence is None:
            p_prob, p_conf, _ = ml_model_service.predict(request.model_dump())
            rec_prob = rec_prob or p_prob
            confidence = confidence or p_conf

        try:
            action_probabilities = action_effectiveness_model_service.predict_action_probabilities(
                request.model_dump()
            )
        except Exception as ex:
            AuditService.log_event(
                db=db,
                event_type="DECISION_FAILED",
                merchant_id=request.merchant_id,
                payment_id=request.transaction_id,
                details={"component": "action_effectiveness_model", "error": str(ex)},
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"code": "DECISION_ENGINE_UNAVAILABLE", "message": "Action-effectiveness model unavailable"},
            ) from ex
        allowed_actions = [RecoveryAction(action) for action in (
            policy.allowed_actions if policy and policy.allowed_actions else action_probabilities.keys()
        ) if action in action_probabilities]
        if RecoveryAction.NO_ACTION not in allowed_actions:
            allowed_actions.insert(0, RecoveryAction.NO_ACTION)

        risk_level = RiskLevel.LOW
        if request.amount > 25000:
            risk_level = RiskLevel.HIGH
        elif request.amount > 10000 or confidence < 0.65:
            risk_level = RiskLevel.MEDIUM

        try:
            best_action, optimization = RevenueOptimizer.optimize_action_probabilities(
                amount=request.amount,
                action_probabilities=action_probabilities,
                allowed_actions=allowed_actions,
                risk_level=risk_level,
            )
        except Exception as ex:
            AuditService.log_event(
                db=db,
                event_type="DECISION_FAILED",
                merchant_id=request.merchant_id,
                payment_id=request.transaction_id,
                details={"component": "revenue_optimizer", "failure_type": type(ex).__name__},
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"code": "DECISION_ENGINE_UNAVAILABLE", "message": "Recovery decision unavailable"},
            ) from ex
        chosen_comparison = next(
            item for item in optimization["comparisons"] if item["action"] == best_action.value
        )
        expected_rec = chosen_comparison["expected_recovered_revenue"]
        rec_prob = chosen_comparison["recovery_probability"]
        inc_rev = chosen_comparison["expected_incremental_revenue"]
        cost = chosen_comparison["intervention_cost"]
        risk_cost = chosen_comparison["expected_risk_cost"]
        net_val = chosen_comparison["expected_net_value"]

        # Deterministic Guardrail Check
        guardrail_decision: GuardrailDecision = GuardrailEngine.evaluate(
            action=best_action,
            amount=request.amount,
            confidence=confidence,
            policy=policy,
            payment=payment,
            customer=customer,
            existing_recoveries=[] if existing_recommendation else existing_recs
        )

        if existing_recommendation:
            recovery_id = existing_recommendation.id
            AuditService.log_event(
                db=db,
                event_type="RECOMMENDATION_REPLAYED",
                merchant_id=request.merchant_id,
                payment_id=request.transaction_id,
                recovery_id=recovery_id,
                action=existing_recommendation.recommended_action,
                details={"idempotent": True},
            )
            return RecoveryRecommendationData(
                recovery_id=recovery_id,
                transaction_id=request.transaction_id,
                recommended_action=RecoveryAction(existing_recommendation.recommended_action),
                recovery_probability=existing_recommendation.recovery_probability,
                expected_recovery=existing_recommendation.expected_recovery,
                expected_incremental_revenue=existing_recommendation.expected_incremental_revenue,
                intervention_cost=existing_recommendation.intervention_cost,
                expected_net_value=existing_recommendation.expected_net_value,
                confidence=existing_recommendation.confidence,
                risk_level=RiskLevel(existing_recommendation.risk_level),
                requires_approval=existing_recommendation.requires_approval,
                reason=existing_recommendation.reason or "Existing recommendation replayed.",
                action_probabilities=action_probabilities,
                baseline_probability=optimization["baseline_probability"],
                action_comparisons=optimization["comparisons"],
                uplift=chosen_comparison["uplift"],
                expected_risk_cost=risk_cost,
                recommended_net_value=optimization["recommended_net_value"],
                decision_reason=optimization["decision_reason"],
                optimizer_recommendation=best_action,
                guardrail_status=guardrail_decision.status,
                guardrail_reason=guardrail_decision.reason,
                decision_state=(
                    "BLOCKED_BY_GUARDRAIL" if existing_recommendation.status == RecoveryLifecycleStatus.BLOCKED.value
                    else "APPROVAL_REQUIRED" if existing_recommendation.status == RecoveryLifecycleStatus.APPROVAL_REQUIRED.value
                    else "NO_ACTION" if existing_recommendation.recommended_action == RecoveryAction.NO_ACTION.value
                    else "READY_FOR_EXECUTION"
                ),
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

        decision_state = "READY_FOR_EXECUTION"
        if best_action == RecoveryAction.NO_ACTION:
            decision_state = "NO_ACTION"
        elif guardrail_decision.status == GuardrailStatus.REQUIRE_APPROVAL:
            decision_state = "APPROVAL_REQUIRED"
        elif guardrail_decision.status == GuardrailStatus.BLOCK:
            decision_state = "BLOCKED_BY_GUARDRAIL"

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

        AuditService.log_event(
            db=db,
            event_type="OPTIMIZER_RECOMMENDATION",
            merchant_id=request.merchant_id,
            payment_id=request.transaction_id,
            recovery_id=recovery_id,
            action=best_action.value,
            details={
                "action_probabilities": action_probabilities,
                "comparisons": optimization["comparisons"],
                "decision_state": decision_state,
            },
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

        llm_explanation = llm_explainer.explain({
            "recommended_action": best_action.value,
            "decision_reason": optimization["decision_reason"],
            "guardrail_status": guardrail_decision.status.value,
            "requires_approval": guardrail_decision.requires_approval,
            "baseline_probability": optimization["baseline_probability"],
            "action_comparisons": optimization["comparisons"],
        })

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
            reason=ai_exp["reason"],
            action_probabilities=action_probabilities,
            baseline_probability=optimization["baseline_probability"],
            action_comparisons=optimization["comparisons"],
            uplift=chosen_comparison["uplift"],
            expected_risk_cost=risk_cost,
            recommended_net_value=optimization["recommended_net_value"],
            decision_reason=optimization["decision_reason"],
            optimizer_recommendation=best_action,
            guardrail_status=guardrail_decision.status,
            guardrail_reason=guardrail_decision.reason,
            decision_state=decision_state,
            llm_explanation=llm_explanation
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
