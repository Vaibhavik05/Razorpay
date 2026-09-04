import json
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Header, Request, Depends, status, HTTPException
from sqlalchemy.orm import Session
from backend.app.core.database import get_db
from backend.app.schemas.contracts import StandardResponse, ErrorDetail
from backend.app.services.razorpay_client import get_razorpay_client
from backend.app.services.audit_service import AuditService
from backend.app.models.entities import Payment, Recovery, AuditEvent

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])

@router.post("/razorpay", response_model=StandardResponse, status_code=status.HTTP_200_OK)
async def process_razorpay_webhook(
    request: Request,
    x_razorpay_signature: Optional[str] = Header(None, alias="X-Razorpay-Signature"),
    db: Session = Depends(get_db)
):
    """
    Receive payment and recovery-related events from Razorpay.
    (13_API_CONTRACTS.md Sections 30-33)
    """
    body_bytes = await request.body()
    razorpay_client = get_razorpay_client()
    
    # 1. Verify Signature (11_GUARDRAILS_SECURITY.md Section 50 & 13_API_CONTRACTS.md Section 32)
    is_valid = razorpay_client.verify_webhook_signature(
        body_bytes=body_bytes,
        signature=x_razorpay_signature or ""
    )
    
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_SIGNATURE", "message": "Webhook signature verification failed"}
        )

    # 2. Parse Payload
    try:
        payload = json.loads(body_bytes.decode("utf-8"))
    except Exception:
        return StandardResponse(
            success=False,
            error=ErrorDetail(
                code="INVALID_REQUEST",
                message="Failed to parse webhook JSON payload"
            )
        )

    event_name = payload.get("event", "payment.captured")
    payload_data = payload.get("payload", {})
    payment_obj = payload_data.get("payment", {}).get("entity") or payload_data.get("payment", {})
    payment_link_obj = payload_data.get("payment_link", {}).get("entity") or payload_data.get("payment_link", {})
    if not payment_obj and payment_link_obj:
        payment_obj = payment_link_obj
    
    rzp_payment_id = payment_obj.get("id")
    reference_id = payment_obj.get("reference_id")
    amount_paise = payment_obj.get("amount", 0)
    amount_inr = float(amount_paise) / 100.0 if amount_paise else 0.0
    status_str = payment_obj.get("status", "captured")

    # 3. Deduplication check via Audit Log
    existing_webhook_audit = db.query(AuditEvent).filter(
        AuditEvent.event_type == "WEBHOOK_PROCESSED",
        AuditEvent.action == rzp_payment_id
    ).first()
    if rzp_payment_id and existing_webhook_audit:
        return StandardResponse(
            success=True,
            message="Webhook event already processed (idempotent duplicate)"
        )

    # 4. Find associated recovery or payment
    recovery = None
    # Check notes or reference_id if present
    notes = payment_obj.get("notes", {})
    rec_id = notes.get("recovery_id")
    if rec_id:
        recovery = db.query(Recovery).filter(Recovery.id == rec_id).first()

    if not recovery and reference_id:
        recovery = db.query(Recovery).filter(Recovery.id == reference_id).first()
        
    if not recovery and rzp_payment_id:
        recovery = db.query(Recovery).filter(Recovery.payment_link_id == rzp_payment_id).first()
        
    if not recovery:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RECOVERY_NOT_FOUND", "message": "Webhook does not identify a known recovery"}
        )

    merchant_id = recovery.merchant_id
    transaction_id = recovery.transaction_id

    # 5. Update Status
    if event_name in ["payment.captured", "payment.successful", "order.paid"] or status_str in ["captured", "paid"]:
        if recovery:
            recovery.outcome = "RECOVERED"
            recovery.status = "RECOVERED"
            recovery.recovered_amount = amount_inr or recovery.expected_recovery
            db.commit()
            
        payment = db.query(Payment).filter(Payment.id == transaction_id).first()
        if payment:
            payment.payment_status = "SUCCESS"
            db.commit()

        AuditService.log_event(
            db=db,
            event_type="PAYMENT_RECOVERED",
            merchant_id=merchant_id,
            payment_id=transaction_id,
            recovery_id=recovery.id if recovery else None,
            action=rzp_payment_id,
            details={"amount": amount_inr, "status": "RECOVERED"}
        )
    elif event_name == "payment.failed" or status_str == "failed":
        if recovery:
            recovery.outcome = "FAILED"
            recovery.recovered_amount = 0.0
            db.commit()

    # Log webhook processing event
    AuditService.log_event(
        db=db,
        event_type="WEBHOOK_PROCESSED",
        merchant_id=merchant_id,
        payment_id=transaction_id,
        recovery_id=recovery.id if recovery else None,
        action=rzp_payment_id,
        details={"event": event_name, "status": status_str}
    )

    return StandardResponse(
        success=True,
        message="Webhook processed successfully"
    )
