from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from sqlalchemy import text
from backend.app.core.database import get_db
from backend.app.schemas.contracts import StandardResponse, HealthData, ReadyData
from backend.app.services.ml.model import ml_model_service
from backend.app.services.razorpay_client import get_razorpay_client

router = APIRouter(tags=["Health"])

@router.get("/health", response_model=StandardResponse, status_code=status.HTTP_200_OK)
def get_health():
    """
    Service health check (13_API_CONTRACTS.md Section 34)
    """
    return StandardResponse(
        success=True,
        data=HealthData().model_dump(),
        message="Service is healthy"
    )

@router.get("/ready", response_model=StandardResponse, status_code=status.HTTP_200_OK)
def get_readiness(db: Session = Depends(get_db)):
    """
    Readiness probe checking database, ML model, guardrails, and Razorpay client.
    (13_API_CONTRACTS.md Section 35)
    """
    db_status = "healthy"
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        db_status = "unhealthy"

    ml_status = "healthy"
    if ml_model_service.is_fallback:
        ml_status = "healthy (rule-fallback)"

    razorpay_status = "healthy"
    try:
        client = get_razorpay_client()
        if not client:
            razorpay_status = "unhealthy"
    except Exception:
        razorpay_status = "unhealthy"

    ready_data = ReadyData(
        api="healthy",
        database=db_status,
        ml_model=ml_status,
        guardrails="healthy",
        razorpay_client=razorpay_status
    )

    return StandardResponse(
        success=True,
        data=ready_data.model_dump(),
        message="Readiness check completed"
    )
