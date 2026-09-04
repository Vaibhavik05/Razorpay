from typing import Dict, Any, Optional, List
from datetime import datetime
from sqlalchemy.orm import Session
from backend.app.models.entities import AuditEvent
from backend.app.schemas.contracts import AuditTimelineEvent

class AuditService:
    """
    Audit Trail Service (11_GUARDRAILS_SECURITY.md Section 45 & 13_API_CONTRACTS.md Section 42)
    Every financial decision, guardrail check, and execution must be logged.
    """
    
    @staticmethod
    def log_event(
        db: Session,
        event_type: str,
        merchant_id: str,
        payment_id: Optional[str] = None,
        recovery_id: Optional[str] = None,
        user_id: Optional[str] = None,
        action: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> AuditEvent:
        event = AuditEvent(
            timestamp=datetime.utcnow(),
            event_type=event_type,
            merchant_id=merchant_id,
            payment_id=payment_id,
            recovery_id=recovery_id,
            user_id=user_id,
            action=action,
            details=details or {}
        )
        db.add(event)
        db.commit()
        db.refresh(event)
        return event

    @staticmethod
    def get_timeline(db: Session, recovery_id: str) -> List[AuditTimelineEvent]:
        events = db.query(AuditEvent).filter(
            AuditEvent.recovery_id == recovery_id
        ).order_by(AuditEvent.timestamp.asc()).all()
        
        timeline: List[AuditTimelineEvent] = []
        for e in events:
            timeline.append(AuditTimelineEvent(
                timestamp=e.timestamp.isoformat() + "Z",
                event=e.event_type,
                action=e.action,
                details=e.details
            ))
        return timeline
