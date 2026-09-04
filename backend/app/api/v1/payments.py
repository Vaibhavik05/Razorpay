from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from backend.app.core.database import get_db
from backend.app.core.security import get_current_auth, verify_merchant_access, AuthContext
from backend.app.schemas.contracts import (
    StandardResponse, PaymentAnalyzeRequest, PaymentAnalyzeData
)
from backend.app.services.recovery_service import RecoveryService

router = APIRouter(prefix="/payments", tags=["Payments"])

@router.post("/analyze", response_model=StandardResponse, status_code=status.HTTP_200_OK)
def analyze_payment(
    request: PaymentAnalyzeRequest,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_current_auth)
):
    """
    Analyze a failed payment and generate information required for recovery decision-making.
    (13_API_CONTRACTS.md Section 8)
    """
    verify_merchant_access(auth, request.merchant_id)
    
    analysis_data: PaymentAnalyzeData = RecoveryService.analyze_payment(db, request)
    
    return StandardResponse(
        success=True,
        data=analysis_data.model_dump(),
        message="Payment analyzed successfully"
    )
