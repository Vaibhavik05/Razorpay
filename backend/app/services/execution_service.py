from datetime import datetime
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from backend.app.models.entities import (
    Recovery, Payment, Customer, MerchantPolicy, ApprovalRequest, IdempotencyRecord
)
from backend.app.schemas.contracts import (
    RecoveryAction, ExecutionStatus, GuardrailStatus, RecoveryLifecycleStatus,
    RecoveryExecuteRequest, RecoveryExecuteData
)
from backend.app.services.guardrails import GuardrailEngine, GuardrailDecision
from backend.app.services.razorpay_client import get_razorpay_client
from backend.app.services.audit_service import AuditService

class ExecutionService:
    """
    Recovery Execution Service (11_GUARDRAILS_SECURITY.md & 13_API_CONTRACTS.md Sections 16-20, 53)
    Enforces idempotency, state transitions, guardrails, and Razorpay API execution.
    """
    
    @staticmethod
    def execute_recovery(
        db: Session,
        request: RecoveryExecuteRequest,
        idempotency_key: str,
        user_id: Optional[str] = None
    ) -> RecoveryExecuteData:
        if not idempotency_key:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "INVALID_REQUEST", "message": "Missing required Idempotency-Key header"}
            )
            
        # 1. Check Idempotency (Section 53)
        existing_idempotency = db.query(IdempotencyRecord).filter(
            IdempotencyRecord.idempotency_key == idempotency_key
        ).first()
        
        if existing_idempotency:
            if (
                existing_idempotency.recovery_id != request.recovery_id
                or existing_idempotency.action != request.action.value
            ):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={"code": "IDEMPOTENCY_KEY_CONFLICT", "message": "Idempotency-Key was already used for a different request"}
                )
            cached_data = existing_idempotency.response_json
            return RecoveryExecuteData(**cached_data)

        # 2. Retrieve Recovery Record
        recovery = db.query(Recovery).filter(Recovery.id == request.recovery_id).first()
        if not recovery:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "RECOVERY_NOT_FOUND", "message": f"Recovery {request.recovery_id} not found"}
            )

        if recovery.merchant_id != request.merchant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "AUTHORIZATION_FAILED", "message": "Recovery belongs to a different merchant"}
            )
        if recovery.recommended_action != request.action.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "ACTION_MISMATCH", "message": "Requested action does not match optimizer recommendation"}
            )
        if request.action == RecoveryAction.NO_ACTION:
            AuditService.log_event(
                db=db,
                event_type="NO_ACTION_RECORDED",
                merchant_id=request.merchant_id,
                payment_id=request.transaction_id,
                recovery_id=recovery.id,
                action=request.action.value,
                details={"decision_state": "NO_ACTION"},
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "NO_ACTION_NOT_EXECUTABLE", "message": "NO_ACTION does not invoke execution"}
            )

        # 3. Retrieve Context
        payment = db.query(Payment).filter(Payment.id == request.transaction_id).first()
        if not payment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "PAYMENT_NOT_FOUND", "message": f"Payment {request.transaction_id} not found"}
            )
            
        customer = db.query(Customer).filter(Customer.id == payment.customer_id).first()
        policy = db.query(MerchantPolicy).filter(MerchantPolicy.merchant_id == request.merchant_id).first()
        existing_recs = db.query(Recovery).filter(
            Recovery.transaction_id == request.transaction_id,
            Recovery.id != request.recovery_id
        ).all()

        # 4. State Transition Verification (11_GUARDRAILS_SECURITY.md Section 66-67)
        allowed_pre_states = [
            RecoveryLifecycleStatus.RECOMMENDED.value,
            RecoveryLifecycleStatus.VALIDATED.value,
            RecoveryLifecycleStatus.APPROVED.value,
            RecoveryLifecycleStatus.APPROVAL_REQUIRED.value
        ]
        if recovery.status not in allowed_pre_states:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "INVALID_REQUEST",
                    "message": f"Invalid state transition: Cannot execute recovery in status '{recovery.status}'"
                }
            )

        # 5. Check Approval requirement if currently APPROVAL_REQUIRED
        if recovery.status == RecoveryLifecycleStatus.APPROVAL_REQUIRED.value:
            approval = db.query(ApprovalRequest).filter(
                ApprovalRequest.recovery_id == recovery.id,
                ApprovalRequest.approval_status == "APPROVED"
            ).first()
            if not approval:
                resp_data = RecoveryExecuteData(
                    recovery_id=recovery.id,
                    transaction_id=payment.id,
                    action=request.action,
                    execution_status=ExecutionStatus.APPROVAL_REQUIRED,
                    requires_approval=True,
                    approval_reason=recovery.approval_reason or "Transaction requires human review before execution."
                )
                return resp_data

        # 6. Re-validate Guardrails (Section 5, 6, 47)
        guardrail_decision: GuardrailDecision = GuardrailEngine.evaluate(
            action=request.action,
            amount=payment.amount,
            confidence=recovery.confidence,
            policy=policy,
            payment=payment,
            customer=customer,
            existing_recoveries=existing_recs
        )

        if guardrail_decision.status == GuardrailStatus.BLOCK:
            recovery.status = RecoveryLifecycleStatus.BLOCKED.value
            recovery.block_reason = guardrail_decision.reason
            recovery.execution_status = ExecutionStatus.BLOCKED.value
            db.commit()
            
            AuditService.log_event(
                db=db,
                event_type="GUARDRAIL_BLOCKED",
                merchant_id=request.merchant_id,
                payment_id=payment.id,
                recovery_id=recovery.id,
                action=request.action.value,
                details={"block_reason": guardrail_decision.reason}
            )
            
            resp_data = RecoveryExecuteData(
                recovery_id=recovery.id,
                transaction_id=payment.id,
                action=request.action,
                execution_status=ExecutionStatus.BLOCKED,
                guardrail_status=GuardrailStatus.BLOCK,
                block_reason=guardrail_decision.reason
            )
            # Record idempotency
            idemp = IdempotencyRecord(
                idempotency_key=idempotency_key,
                recovery_id=recovery.id,
                action=request.action.value,
                response_json=resp_data.model_dump()
            )
            db.add(idemp)
            db.commit()
            return resp_data

        if guardrail_decision.status == GuardrailStatus.REQUIRE_APPROVAL and recovery.status != RecoveryLifecycleStatus.APPROVED.value:
            recovery.status = RecoveryLifecycleStatus.APPROVAL_REQUIRED.value
            recovery.requires_approval = True
            recovery.approval_reason = guardrail_decision.reason
            recovery.execution_status = ExecutionStatus.APPROVAL_REQUIRED.value
            db.commit()
            
            resp_data = RecoveryExecuteData(
                recovery_id=recovery.id,
                transaction_id=payment.id,
                action=request.action,
                execution_status=ExecutionStatus.APPROVAL_REQUIRED,
                requires_approval=True,
                approval_reason=guardrail_decision.reason
            )
            return resp_data

        # 7. Execute Controlled Action via Razorpay Adapter
        recovery.status = RecoveryLifecycleStatus.EXECUTING.value
        db.commit()
        
        payment_link_id = None
        payment_link_url = None
        executed_time = datetime.utcnow()
        
        try:
            razorpay_client = get_razorpay_client()
            if request.action == RecoveryAction.PAYMENT_LINK:
                cust_details = {"name": f"Customer {customer.id}", "contact": "+919876543210"} if customer else None
                link_resp = razorpay_client.create_payment_link(
                    amount_inr=payment.amount,
                    currency=payment.currency,
                    description=f"Recovery for payment {payment.id}",
                    customer_details=cust_details,
                    reference_id=recovery.id
                )
                payment_link_id = link_resp.get("payment_link_id")
                payment_link_url = link_resp.get("short_url")
                
            elif request.action == RecoveryAction.RETRY:
                payment.retry_count = (payment.retry_count or 0) + 1
                
            elif request.action == RecoveryAction.CUSTOMER_NOTIFICATION:
                if customer:
                    customer.notification_count_24h = (customer.notification_count_24h or 0) + 1

            # Update recovery state to EXECUTED
            recovery.status = RecoveryLifecycleStatus.EXECUTED.value
            recovery.executed_action = request.action.value
            recovery.execution_status = ExecutionStatus.SUCCESS.value
            recovery.payment_link_id = payment_link_id
            recovery.payment_link_url = payment_link_url
            recovery.executed_at = executed_time
            db.commit()
            
            # Log Audit Event
            AuditService.log_event(
                db=db,
                event_type="ACTION_EXECUTED",
                merchant_id=request.merchant_id,
                payment_id=payment.id,
                recovery_id=recovery.id,
                user_id=user_id,
                action=request.action.value,
                details={
                    "payment_link_id": payment_link_id,
                    "payment_link_url": payment_link_url,
                    "amount": payment.amount
                }
            )

            resp_data = RecoveryExecuteData(
                recovery_id=recovery.id,
                transaction_id=payment.id,
                action=request.action,
                execution_status=ExecutionStatus.SUCCESS,
                payment_link_id=payment_link_id,
                payment_link_url=payment_link_url,
                executed_at=executed_time.isoformat() + "Z"
            )

            # Store in idempotency table
            idemp = IdempotencyRecord(
                idempotency_key=idempotency_key,
                recovery_id=recovery.id,
                action=request.action.value,
                response_json=resp_data.model_dump()
            )
            db.add(idemp)
            db.commit()
            return resp_data

        except Exception as ex:
            recovery.status = RecoveryLifecycleStatus.FAILED.value
            recovery.execution_status = ExecutionStatus.FAILED.value
            db.commit()
            
            AuditService.log_event(
                db=db,
                event_type="ACTION_FAILED",
                merchant_id=request.merchant_id,
                payment_id=payment.id,
                recovery_id=recovery.id,
                details={"failure_type": type(ex).__name__}
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={"code": "RAZORPAY_API_ERROR", "message": "Execution failed safely"}
            )
