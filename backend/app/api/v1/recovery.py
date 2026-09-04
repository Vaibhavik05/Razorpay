from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.core.database import get_db
from backend.app.core.security import get_current_auth, verify_merchant_access, AuthContext, UserRole
from backend.app.schemas.contracts import (
    StandardResponse, RecoveryRecommendRequest, RecoveryExecuteRequest,
    ApprovalRequestPayload, RejectRequestPayload, ApprovalDecisionData,
    RecoveryLifecycleStatus
)
from backend.app.models.entities import Recovery, ApprovalRequest
from backend.app.services.recovery_service import RecoveryService
from backend.app.services.execution_service import ExecutionService
from backend.app.services.audit_service import AuditService

router = APIRouter(prefix="/recovery", tags=["Recovery"])

@router.post("/recommend", response_model=StandardResponse, status_code=status.HTTP_200_OK)
def recommend_recovery(
    request: RecoveryRecommendRequest,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_current_auth)
):
    """
    Determine the best recovery action based on recovery probability,
    expected incremental revenue, costs, and guardrails.
    (13_API_CONTRACTS.md Section 9)
    """
    verify_merchant_access(auth, request.merchant_id)
    rec_data = RecoveryService.recommend_recovery(db, request)
    return StandardResponse(
        success=True,
        data=rec_data.model_dump(),
        message="Recovery recommendation generated successfully"
    )

@router.post("/execute", response_model=StandardResponse, status_code=status.HTTP_200_OK)
def execute_recovery(
    request: RecoveryExecuteRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_current_auth)
):
    """
    Execute a previously validated recovery action.
    Idempotency is mandatory for financial execution.
    (13_API_CONTRACTS.md Section 16 & 53)
    """
    verify_merchant_access(auth, request.merchant_id)
    
    exec_data = ExecutionService.execute_recovery(
        db=db,
        request=request,
        idempotency_key=idempotency_key,
        user_id=auth.user_id
    )

    if exec_data.execution_status.value == "APPROVAL_REQUIRED":
        return StandardResponse(
            success=True,
            data=exec_data.model_dump(),
            message="Human approval is required"
        )
    elif exec_data.execution_status.value == "BLOCKED":
        return StandardResponse(
            success=False,
            data=exec_data.model_dump(),
            message="Recovery action blocked by guardrails"
        )
        
    return StandardResponse(
        success=True,
        data=exec_data.model_dump(),
        message="Recovery action executed successfully"
    )

@router.get("/{recovery_id}", response_model=StandardResponse, status_code=status.HTTP_200_OK)
def get_recovery_status(
    recovery_id: str,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_current_auth)
):
    """
    Retrieve the current state of a recovery operation.
    (13_API_CONTRACTS.md Section 21)
    """
    recovery = db.query(Recovery).filter(Recovery.id == recovery_id).first()
    if not recovery:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RECOVERY_NOT_FOUND", "message": f"Recovery record {recovery_id} not found"}
        )
    verify_merchant_access(auth, recovery.merchant_id)
    rec_data = RecoveryService.get_recovery_status(db, recovery_id)
    return StandardResponse(
        success=True,
        data=rec_data.model_dump(),
        message="Recovery status retrieved successfully"
    )

@router.post("/{recovery_id}/approve", response_model=StandardResponse, status_code=status.HTTP_200_OK)
def approve_recovery(
    recovery_id: str,
    payload: ApprovalRequestPayload,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_current_auth)
):
    """
    Approve a recovery action requiring human approval.
    (13_API_CONTRACTS.md Section 36-38)
    """
    # Authorization rule (Section 55): Reviewer or Admin can approve
    if auth.role not in [UserRole.REVIEWER, UserRole.ADMIN]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "AUTHORIZATION_FAILED", "message": "Only Reviewers and Admins can approve recovery actions"}
        )

    recovery = db.query(Recovery).filter(Recovery.id == recovery_id).first()
    if not recovery:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RECOVERY_NOT_FOUND", "message": f"Recovery {recovery_id} not found"}
        )

    verify_merchant_access(auth, recovery.merchant_id)

    if payload.reviewer_id != auth.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "AUTHORIZATION_FAILED", "message": "Reviewer identity does not match authenticated user"}
        )
    if recovery.status == RecoveryLifecycleStatus.APPROVED.value:
        return StandardResponse(
            success=True,
            data=ApprovalDecisionData(
                recovery_id=recovery.id,
                approval_status="APPROVED",
                approved_by=payload.reviewer_id,
            ).model_dump(),
            message="Recovery approval already recorded"
        )
    if recovery.status in [RecoveryLifecycleStatus.REJECTED.value, RecoveryLifecycleStatus.BLOCKED.value]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "INVALID_STATE", "message": f"Recovery cannot be approved from status '{recovery.status}'"}
        )
    if recovery.status != RecoveryLifecycleStatus.APPROVAL_REQUIRED.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "INVALID_STATE", "message": f"Recovery is not awaiting approval (status '{recovery.status}')"}
        )

    recovery.status = RecoveryLifecycleStatus.APPROVED.value
    recovery.requires_approval = False
    
    # Record Approval Request
    approval = ApprovalRequest(
        id=f"APP_{recovery.id}",
        recovery_id=recovery.id,
        reviewer_id=payload.reviewer_id,
        approval_status="APPROVED",
        comment=payload.comment,
        reviewed_at=datetime.utcnow()
    )
    db.add(approval)
    db.commit()

    # Log audit event
    AuditService.log_event(
        db=db,
        event_type="RECOVERY_APPROVED",
        merchant_id=recovery.merchant_id,
        payment_id=recovery.transaction_id,
        recovery_id=recovery.id,
        user_id=payload.reviewer_id,
        action=recovery.recommended_action,
        details={"comment": payload.comment}
    )

    decision_data = ApprovalDecisionData(
        recovery_id=recovery.id,
        approval_status="APPROVED",
        approved_by=payload.reviewer_id,
        approved_at=datetime.utcnow().isoformat() + "Z"
    )

    return StandardResponse(
        success=True,
        data=decision_data.model_dump(),
        message="Recovery approved successfully"
    )

@router.post("/{recovery_id}/reject", response_model=StandardResponse, status_code=status.HTTP_200_OK)
def reject_recovery(
    recovery_id: str,
    payload: RejectRequestPayload,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_current_auth)
):
    """
    Reject a recovery action requiring human approval.
    (13_API_CONTRACTS.md Section 39-41)
    """
    if auth.role not in [UserRole.REVIEWER, UserRole.ADMIN]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "AUTHORIZATION_FAILED", "message": "Only Reviewers and Admins can reject recovery actions"}
        )

    recovery = db.query(Recovery).filter(Recovery.id == recovery_id).first()
    if not recovery:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RECOVERY_NOT_FOUND", "message": f"Recovery {recovery_id} not found"}
        )

    verify_merchant_access(auth, recovery.merchant_id)

    if payload.reviewer_id != auth.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "AUTHORIZATION_FAILED", "message": "Reviewer identity does not match authenticated user"}
        )
    if recovery.status == RecoveryLifecycleStatus.REJECTED.value:
        return StandardResponse(
            success=True,
            data=ApprovalDecisionData(
                recovery_id=recovery.id,
                approval_status="REJECTED",
                rejected_by=payload.reviewer_id,
                rejection_reason=recovery.block_reason,
            ).model_dump(),
            message="Recovery rejection already recorded"
        )
    if recovery.status in [RecoveryLifecycleStatus.APPROVED.value, RecoveryLifecycleStatus.EXECUTED.value, RecoveryLifecycleStatus.RECOVERED.value]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "INVALID_STATE", "message": f"Recovery cannot be rejected from status '{recovery.status}'"}
        )
    if recovery.status != RecoveryLifecycleStatus.APPROVAL_REQUIRED.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "INVALID_STATE", "message": f"Recovery is not awaiting approval (status '{recovery.status}')"}
        )

    recovery.status = RecoveryLifecycleStatus.REJECTED.value
    recovery.block_reason = payload.reason
    
    rejection = ApprovalRequest(
        id=f"REJ_{recovery.id}",
        recovery_id=recovery.id,
        reviewer_id=payload.reviewer_id,
        approval_status="REJECTED",
        reason=payload.reason,
        reviewed_at=datetime.utcnow()
    )
    db.add(rejection)
    db.commit()

    AuditService.log_event(
        db=db,
        event_type="RECOVERY_REJECTED",
        merchant_id=recovery.merchant_id,
        payment_id=recovery.transaction_id,
        recovery_id=recovery.id,
        user_id=payload.reviewer_id,
        details={"reason": payload.reason}
    )

    decision_data = ApprovalDecisionData(
        recovery_id=recovery.id,
        approval_status="REJECTED",
        rejected_by=payload.reviewer_id,
        rejection_reason=payload.reason
    )

    return StandardResponse(
        success=True,
        data=decision_data.model_dump(),
        message="Recovery rejected successfully"
    )
