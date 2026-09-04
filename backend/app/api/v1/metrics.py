from typing import Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session
from backend.app.core.database import get_db
from backend.app.core.security import get_current_auth, AuthContext
from backend.app.schemas.contracts import StandardResponse
from backend.app.services.metrics_service import MetricsService

router = APIRouter(prefix="/metrics", tags=["Metrics"])

@router.get("", response_model=StandardResponse, status_code=status.HTTP_200_OK)
def get_metrics(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    failure_reason: Optional[str] = Query(None),
    customer_segment: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_current_auth)
):
    """
    Retrieve aggregated revenue recovery performance metrics.
    (13_API_CONTRACTS.md Section 27-29)
    """
    metrics_data = MetricsService.get_metrics_data(
        db=db,
        merchant_id=auth.merchant_id,
        start_date=start_date,
        end_date=end_date,
        action_filter=action,
        failure_reason_filter=failure_reason,
        customer_segment_filter=customer_segment
    )
    return StandardResponse(
        success=True,
        data=metrics_data.model_dump(),
        message="Metrics retrieved successfully"
    )
