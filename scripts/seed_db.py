import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import pandas as pd
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from backend.app.core.database import Base, engine, SessionLocal
from backend.app.models.entities import (
    Merchant, MerchantPolicy, Customer, Payment, Recovery, AuditEvent
)

def seed():
    print("Creating database tables...")
    Base.metadata.create_all(bind=engine)
    db: Session = SessionLocal()

    try:
        # 1. Seed Primary Demo Merchant (Acme Store / MERCHANT001)
        demo_merchant = db.query(Merchant).filter(Merchant.id == "MERCHANT001").first()
        if not demo_merchant:
            demo_merchant = Merchant(
                id="MERCHANT001",
                name="Acme Store",
                category="ECOMMERCE",
                size="GROWTH",
                monthly_volume=8500000.0,
                recovery_preference="BALANCED"
            )
            db.add(demo_merchant)
            db.commit()

        # Seed Merchant Policy
        policy = db.query(MerchantPolicy).filter(MerchantPolicy.merchant_id == "MERCHANT001").first()
        if not policy:
            policy = MerchantPolicy(
                merchant_id="MERCHANT001",
                max_retries=2,
                auto_recovery_limit=10000.0,
                approval_threshold=25000.0,
                notifications_enabled=True,
                allowed_actions=["NO_ACTION", "RETRY", "PAYMENT_LINK", "CUSTOMER_NOTIFICATION", "HUMAN_ESCALATION"]
            )
            db.add(policy)
            db.commit()

        # 2. Seed customers from data/customers.csv (first 500)
        cust_csv_path = "data/customers.csv"
        if os.path.exists(cust_csv_path):
            print("Seeding customers from data/customers.csv...")
            cust_df = pd.read_csv(cust_csv_path).head(500)
            for _, row in cust_df.iterrows():
                cid = str(row["customer_id"])
                if not db.query(Customer).filter(Customer.id == cid).first():
                    cust = Customer(
                        id=cid,
                        segment=str(row.get("customer_segment", "REGULAR")),
                        customer_tenure_days=int(row.get("customer_tenure_days", 30)),
                        previous_transaction_count=int(row.get("total_transactions", 0)),
                        previous_success_count=int(row.get("successful_transactions", 0)),
                        previous_failure_count=int(row.get("failed_transactions", 0)),
                        previous_recovery_count=int(row.get("recovered_transactions", 0)),
                        historical_success_rate=float(row.get("historical_success_rate", 0.8)),
                        opted_out=bool(row.get("opted_out", False)),
                        notification_count_24h=0
                    )
                    db.add(cust)
            db.commit()

        # Ensure demo customer CUST456 exists
        if not db.query(Customer).filter(Customer.id == "CUST456").first():
            db.add(Customer(
                id="CUST456",
                segment="LOYAL",
                customer_tenure_days=180,
                previous_transaction_count=10,
                previous_success_count=8,
                previous_failure_count=2,
                previous_recovery_count=2,
                historical_success_rate=0.80,
                opted_out=False
            ))
            db.commit()

        # 3. Seed Payments and Recoveries from data/payments.csv (first 1000 records)
        pay_csv_path = "data/payments.csv"
        if os.path.exists(pay_csv_path):
            print("Seeding payments and recoveries from data/payments.csv...")
            pay_df = pd.read_csv(pay_csv_path).head(1000)
            
            for idx, row in pay_df.iterrows():
                pid = str(row["payment_id"])
                if not db.query(Payment).filter(Payment.id == pid).first():
                    amount = float(row["transaction_amount"])
                    cust_id = str(row["customer_id"])
                    
                    # Ensure customer exists
                    if not db.query(Customer).filter(Customer.id == cust_id).first():
                        db.add(Customer(id=cust_id, segment=str(row.get("customer_segment", "REGULAR"))))
                        db.commit()
                        
                    # Map to demo merchant MERCHANT001 for easy inspection
                    m_id = "MERCHANT001"
                    
                    # Parse timestamp if available
                    t_str = str(row.get("transaction_timestamp", ""))
                    try:
                        t_time = datetime.strptime(t_str, "%Y-%m-%d %H:%M:%S")
                    except Exception:
                        t_time = datetime.utcnow() - timedelta(days=int(idx % 30), hours=int(idx % 24))

                    payment = Payment(
                        id=pid,
                        merchant_id=m_id,
                        customer_id=cust_id,
                        amount=amount,
                        currency="INR",
                        payment_method=str(row.get("payment_method", "CARD")),
                        card_type=str(row.get("card_type", "CREDIT")),
                        issuer_type=str(row.get("issuer_type", "OTHER")),
                        payment_status=str(row.get("payment_status", "FAILED")),
                        failure_category=str(row.get("failure_category", "TECHNICAL")),
                        failure_reason=str(row.get("failure_reason", "TIMEOUT")),
                        gateway_response_code=str(row.get("gateway_response_code", "GW_001")),
                        retry_count=int(row.get("retry_count", 0)),
                        revenue_at_risk=amount,
                        natural_recovery_probability=float(row.get("natural_recovery_probability", 0.3)),
                        created_at=t_time
                    )
                    db.add(payment)
                    
                    # Seed Recovery Record
                    action_taken = str(row.get("action_taken", "PAYMENT_LINK"))
                    rec_status = str(row.get("recovery_status", "NOT_RECOVERED"))
                    outcome = "RECOVERED" if rec_status == "RECOVERED" else "PENDING"
                    
                    # For demo opportunities, keep some in RECOMMENDED/ANALYZED state
                    lifecycle_status = "RECOVERED" if outcome == "RECOVERED" else (
                        "RECOMMENDED" if idx < 100 else "EXECUTED"
                    )
                    
                    inc_rev = float(row.get("incremental_revenue", 0.0))
                    if inc_rev <= 0:
                        inc_rev = round(amount * 0.25, 2)
                        
                    rec_prob = float(row.get("natural_recovery_probability", 0.5)) + 0.25
                    rec_prob = min(0.95, max(0.1, rec_prob))

                    requires_approval = amount > 25000.0
                    risk_lvl = "HIGH" if amount > 25000.0 else ("MEDIUM" if amount > 10000.0 else "LOW")

                    recovery = Recovery(
                        id=f"REC_{pid}",
                        transaction_id=pid,
                        merchant_id=m_id,
                        status=lifecycle_status,
                        recommended_action=action_taken,
                        recovery_probability=rec_prob,
                        expected_recovery=round(rec_prob * amount, 2),
                        expected_incremental_revenue=inc_rev,
                        intervention_cost=float(row.get("intervention_cost", 20.0)),
                        expected_net_value=round(inc_rev - 20.0, 2),
                        confidence=0.88,
                        risk_level=risk_lvl,
                        requires_approval=requires_approval,
                        approval_reason="Transaction exceeds automatic execution threshold." if requires_approval else None,
                        executed_action=action_taken if lifecycle_status in ["EXECUTED", "RECOVERED"] else None,
                        execution_status="SUCCESS" if lifecycle_status in ["EXECUTED", "RECOVERED"] else None,
                        outcome=outcome,
                        recovered_amount=float(row.get("recovered_amount", 0.0)),
                        reason=f"Optimal recovery action '{action_taken}' determined with expected net incremental gain.",
                        created_at=t_time,
                        updated_at=t_time
                    )
                    db.add(recovery)

            db.commit()

        # 4. Seed Canonical Demo Opportunities (matching specs in 09_UI_UX_DESIGN_SPEC.md & 13_API_CONTRACTS.md)
        demo_txns = [
            {
                "tx_id": "TXN123",
                "cust_id": "CUST456",
                "amount": 12500.0,
                "reason": "TIMEOUT",
                "action": "PAYMENT_LINK",
                "rec_id": "REC789",
                "rec_prob": 0.82,
                "inc_rev": 2150.0,
                "net_val": 2130.0,
                "conf": 0.91,
                "risk": "LOW",
                "status": "RECOMMENDED"
            },
            {
                "tx_id": "PAY_DEMO_001",
                "cust_id": "CUST456",
                "amount": 5000.0,
                "reason": "TIMEOUT",
                "action": "PAYMENT_LINK",
                "rec_id": "REC_DEMO_001",
                "rec_prob": 0.76,
                "inc_rev": 2250.0,
                "net_val": 2230.0,
                "conf": 0.89,
                "risk": "LOW",
                "status": "RECOMMENDED"
            },
            {
                "tx_id": "PAY_10293",
                "cust_id": "CUST456",
                "amount": 25000.0,
                "reason": "TIMEOUT",
                "action": "HUMAN_ESCALATION",
                "rec_id": "REC_PAY_10293",
                "rec_prob": 0.75,
                "inc_rev": 4500.0,
                "net_val": 4450.0,
                "conf": 0.85,
                "risk": "HIGH",
                "status": "APPROVAL_REQUIRED"
            }
        ]

        for d in demo_txns:
            if not db.query(Payment).filter(Payment.id == d["tx_id"]).first():
                p = Payment(
                    id=d["tx_id"],
                    merchant_id="MERCHANT001",
                    customer_id=d["cust_id"],
                    amount=d["amount"],
                    currency="INR",
                    payment_method="UPI",
                    failure_reason=d["reason"],
                    payment_status="FAILED",
                    revenue_at_risk=d["amount"],
                    retry_count=1,
                    natural_recovery_probability=0.35,
                    created_at=datetime.utcnow() - timedelta(hours=2)
                )
                db.add(p)
                db.commit()

            if not db.query(Recovery).filter(Recovery.id == d["rec_id"]).first():
                r = Recovery(
                    id=d["rec_id"],
                    transaction_id=d["tx_id"],
                    merchant_id="MERCHANT001",
                    status=d["status"],
                    recommended_action=d["action"],
                    recovery_probability=d["rec_prob"],
                    expected_recovery=round(d["rec_prob"] * d["amount"], 2),
                    expected_incremental_revenue=d["inc_rev"],
                    intervention_cost=20.0,
                    expected_net_value=d["net_val"],
                    confidence=d["conf"],
                    risk_level=d["risk"],
                    requires_approval=(d["status"] == "APPROVAL_REQUIRED"),
                    approval_reason="High-value transaction exceeds approval threshold." if d["status"] == "APPROVAL_REQUIRED" else None,
                    reason=f"Strong recovery probability ({d['rec_prob']:.0%}) for returning customer segment with timeout failure.",
                    outcome="PENDING",
                    created_at=datetime.utcnow() - timedelta(hours=2)
                )
                db.add(r)
                db.commit()

                # Add initial audit events for demo recovery
                AuditEvent_obj = AuditEvent(
                    timestamp=datetime.utcnow() - timedelta(hours=2),
                    event_type="PAYMENT_ANALYZED",
                    merchant_id="MERCHANT001",
                    payment_id=d["tx_id"],
                    recovery_id=d["rec_id"],
                    action=d["action"],
                    details={"amount": d["amount"], "recovery_probability": d["rec_prob"]}
                )
                db.add(AuditEvent_obj)
                db.commit()

        print("Database seeding completed successfully!")

    finally:
        db.close()

if __name__ == "__main__":
    seed()
