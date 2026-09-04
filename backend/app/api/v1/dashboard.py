from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from backend.app.core.database import get_db
from backend.app.core.security import get_current_auth, AuthContext
from backend.app.schemas.contracts import StandardResponse
from backend.app.services.metrics_service import MetricsService

router = APIRouter(prefix="/merchant", tags=["Merchant"])

@router.get("/dashboard", response_model=StandardResponse, status_code=status.HTTP_200_OK)
def get_merchant_dashboard(
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_current_auth)
):
    """
    Provide main dashboard data for the authenticated merchant.
    (13_API_CONTRACTS.md Section 24)
    """
    dashboard_data = MetricsService.get_dashboard_data(db, auth.merchant_id)
    return StandardResponse(
        success=True,
        data=dashboard_data.model_dump(),
        message="Merchant dashboard data retrieved successfully"
    )
