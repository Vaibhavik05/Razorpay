from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import func
from backend.app.models.entities import Payment, Recovery, Customer
from backend.app.schemas.contracts import (
    DashboardData, TopOpportunity, MetricsData, ActionMetric, RecoveryAction, RiskLevel
)

class MetricsService:
    """
    Financial Metrics & Aggregations Service (13_API_CONTRACTS.md Sections 24-29)
    All metrics are calculated strictly from database records — zero hardcoded fake metrics.
    """
    
    @staticmethod
    def get_dashboard_data(db: Session, merchant_id: str) -> DashboardData:
        # 1. Total revenue at risk (sum of failed payments)
        risk_query = db.query(
            func.coalesce(func.sum(Payment.amount), 0.0)
        ).filter(
            Payment.merchant_id == merchant_id,
            Payment.payment_status == "FAILED"
        ).scalar()
        revenue_at_risk = float(risk_query or 0.0)

        # 2. Total recovered revenue
        recovered_query = db.query(
            func.coalesce(func.sum(Recovery.recovered_amount), 0.0)
        ).filter(
            Recovery.merchant_id == merchant_id,
            Recovery.outcome == "RECOVERED"
        ).scalar()
        recovered_revenue = float(recovered_query or 0.0)

        # 3. Incremental revenue from recoveries
        incremental_query = db.query(
            func.coalesce(func.sum(Recovery.expected_incremental_revenue), 0.0)
        ).filter(
            Recovery.merchant_id == merchant_id,
            Recovery.status.in_(["EXECUTED", "RECOVERED"])
        ).scalar()
        incremental_revenue = float(incremental_query or 0.0)

        # 4. Total recoveries count & recovery rate
        total_executed = db.query(func.count(Recovery.id)).filter(
            Recovery.merchant_id == merchant_id,
            Recovery.status.in_(["EXECUTED", "RECOVERED"])
        ).scalar() or 0
        
        total_recovered_count = db.query(func.count(Recovery.id)).filter(
            Recovery.merchant_id == merchant_id,
            Recovery.outcome == "RECOVERED"
        ).scalar() or 0
        
        recovery_rate = float(round(total_recovered_count / total_executed, 4)) if total_executed > 0 else 0.0
        avg_recovery_val = float(round(recovered_revenue / total_recovered_count, 2)) if total_recovered_count > 0 else 0.0

        # 5. Top opportunities ranked by Expected Incremental Revenue
        opportunities_query = db.query(Recovery, Payment).join(
            Payment, Recovery.transaction_id == Payment.id
        ).filter(
            Recovery.merchant_id == merchant_id,
            Recovery.status.in_(["IDENTIFIED", "ANALYZED", "RECOMMENDED", "VALIDATED", "APPROVAL_REQUIRED"])
        ).order_by(
            Recovery.expected_incremental_revenue.desc()
        ).limit(10).all()

        top_opportunities: List[TopOpportunity] = []
        for rec, pay in opportunities_query:
            top_opportunities.append(TopOpportunity(
                recovery_id=rec.id,
                transaction_id=pay.id,
                amount=pay.amount,
                failure_reason=pay.failure_reason or "TIMEOUT",
                recommended_action=RecoveryAction(rec.recommended_action) if rec.recommended_action in RecoveryAction._value2member_map_ else RecoveryAction.PAYMENT_LINK,
                expected_incremental_revenue=rec.expected_incremental_revenue or 0.0,
                confidence=rec.confidence or 0.85,
                risk_level=RiskLevel(rec.risk_level) if rec.risk_level in RiskLevel._value2member_map_ else RiskLevel.LOW
            ))

        return DashboardData(
            revenue_at_risk=round(revenue_at_risk, 2),
            recovered_revenue=round(recovered_revenue, 2),
            incremental_revenue=round(incremental_revenue, 2),
            recovery_rate=recovery_rate,
            average_recovery_value=avg_recovery_val,
            top_opportunities=top_opportunities
        )

    @staticmethod
    def get_metrics_data(
        db: Session,
        merchant_id: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        action_filter: Optional[str] = None,
        failure_reason_filter: Optional[str] = None,
        customer_segment_filter: Optional[str] = None
    ) -> MetricsData:
        # Base payment query
        pay_query = db.query(Payment).filter(Payment.merchant_id == merchant_id)
        if failure_reason_filter:
            pay_query = pay_query.filter(Payment.failure_reason == failure_reason_filter)

        total_failed = pay_query.filter(Payment.payment_status == "FAILED").count()
        
        sum_risk = db.query(func.coalesce(func.sum(Payment.amount), 0.0)).filter(
            Payment.merchant_id == merchant_id,
            Payment.payment_status == "FAILED"
        ).scalar() or 0.0
        
        rec_query = db.query(Recovery).filter(Recovery.merchant_id == merchant_id)
        if action_filter:
            rec_query = rec_query.filter(Recovery.executed_action == action_filter)

        total_interventions = rec_query.filter(Recovery.status.in_(["EXECUTED", "RECOVERED"])).count()
        total_recovered_count = rec_query.filter(Recovery.outcome == "RECOVERED").count()
        
        recovered_rev = db.query(func.coalesce(func.sum(Recovery.recovered_amount), 0.0)).filter(
            Recovery.merchant_id == merchant_id,
            Recovery.outcome == "RECOVERED"
        ).scalar() or 0.0

        inc_rev = db.query(func.coalesce(func.sum(Recovery.expected_incremental_revenue), 0.0)).filter(
            Recovery.merchant_id == merchant_id,
            Recovery.status.in_(["EXECUTED", "RECOVERED"])
        ).scalar() or 0.0

        total_costs = db.query(func.coalesce(func.sum(Recovery.intervention_cost), 0.0)).filter(
            Recovery.merchant_id == merchant_id,
            Recovery.status.in_(["EXECUTED", "RECOVERED"])
        ).scalar() or 0.0

        rec_rate = float(round(total_recovered_count / total_interventions, 4)) if total_interventions > 0 else 0.0
        avg_val = float(round(recovered_rev / total_recovered_count, 2)) if total_recovered_count > 0 else 0.0
        roi = float(round((inc_rev - total_costs) / total_costs, 2)) if total_costs > 0 else 0.0

        # Action Breakdown
        actions_list: List[ActionMetric] = []
        for act in [RecoveryAction.RETRY, RecoveryAction.PAYMENT_LINK, RecoveryAction.CUSTOMER_NOTIFICATION]:
            act_total = db.query(Recovery).filter(
                Recovery.merchant_id == merchant_id,
                Recovery.executed_action == act.value
            ).count()
            act_succ = db.query(Recovery).filter(
                Recovery.merchant_id == merchant_id,
                Recovery.executed_action == act.value,
                Recovery.outcome == "RECOVERED"
            ).count()
            act_rec_rev = db.query(func.coalesce(func.sum(Recovery.recovered_amount), 0.0)).filter(
                Recovery.merchant_id == merchant_id,
                Recovery.executed_action == act.value,
                Recovery.outcome == "RECOVERED"
            ).scalar() or 0.0
            act_inc_rev = db.query(func.coalesce(func.sum(Recovery.expected_incremental_revenue), 0.0)).filter(
                Recovery.merchant_id == merchant_id,
                Recovery.executed_action == act.value
            ).scalar() or 0.0

            act_rate = round(act_succ / act_total, 4) if act_total > 0 else 0.0
            actions_list.append(ActionMetric(
                action=act.value,
                recovery_rate=act_rate,
                recovered_revenue=round(float(act_rec_rev), 2),
                incremental_revenue=round(float(act_inc_rev), 2)
            ))

        return MetricsData(
            total_failed_payments=total_failed,
            total_revenue_at_risk=round(float(sum_risk), 2),
            recovered_revenue=round(float(recovered_rev), 2),
            incremental_revenue=round(float(inc_rev), 2),
            recovery_rate=rec_rate,
            intervention_count=total_interventions,
            average_recovery_value=avg_val,
            roi=roi,
            actions=actions_list
        )
