from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy.orm import Session
from backend.app.core.database import get_db
from backend.app.core.security import get_current_auth, verify_merchant_access, AuthContext
from backend.app.schemas.contracts import StandardResponse, AuditResponseData
from backend.app.services.audit_service import AuditService
from backend.app.models.entities import Recovery

router = APIRouter(prefix="/audit", tags=["Audit"])

@router.get("/{recovery_id}", response_model=StandardResponse, status_code=status.HTTP_200_OK)
def get_recovery_audit(
    recovery_id: str,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_current_auth)
):
    """
    Retrieve the complete decision history and audit timeline for a recovery.
    (13_API_CONTRACTS.md Section 42)
    """
    recovery = db.query(Recovery).filter(Recovery.id == recovery_id).first()
    if not recovery:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RECOVERY_NOT_FOUND", "message": f"Recovery {recovery_id} not found"}
        )

    verify_merchant_access(auth, recovery.merchant_id)

    timeline_events = AuditService.get_timeline(db, recovery_id)

    audit_data = AuditResponseData(
        recovery_id=recovery_id,
        events=timeline_events
    )

    return StandardResponse(
        success=True,
        data=audit_data.model_dump(),
        message="Audit timeline retrieved successfully"
    )
