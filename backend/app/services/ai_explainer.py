import re
from typing import Dict, Any, List
from backend.app.schemas.contracts import RecoveryAction

class StructuredAIExplainer:
    """
    Structured AI Explanation Engine (11_GUARDRAILS_SECURITY.md Sections 18-24, 63)
    Generates explainable, audited, structured reasoning grounded exclusively
    in backend facts and deterministic calculations.
    """
    
    @staticmethod
    def sanitize_untrusted_input(text: str) -> str:
        """
        Prompt Injection Defense (11_GUARDRAILS_SECURITY.md Section 23-24):
        Treats external user-controlled text as untrusted data.
        Removes control instructions and dangerous prompt sequences.
        """
        if not text:
            return ""
        sanitized = re.sub(r"(?i)(ignore|disregard|system\s+prompt|admin|password|api[_\s]*key|secret)", "[FILTERED]", str(text))
        return sanitized.strip()

    @classmethod
    def generate_explanation(
        cls,
        transaction_id: str,
        recommended_action: RecoveryAction,
        amount: float,
        failure_reason: str,
        customer_type: str,
        recovery_prob: float,
        incremental_revenue: float,
        confidence: float,
        requires_approval: bool,
        candidate_evaluations: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Generates structured reasoning bullets explaining:
        - What action was chosen
        - Why it outperforms other actions
        - Expected monetary value
        - Safety & risk context
        """
        safe_failure = cls.sanitize_untrusted_input(failure_reason)
        safe_cust = cls.sanitize_untrusted_input(customer_type)
        
        reasons: List[str] = []
        
        if safe_cust in ["RETURNING", "LOYAL", "HIGH_VALUE"]:
            reasons.append(f"{safe_cust.capitalize()} customer with strong historical payment loyalty.")
        else:
            reasons.append(f"Customer segment '{safe_cust}' evaluated.")
            
        if "TIMEOUT" in safe_failure.upper():
            reasons.append("Temporary network/gateway timeout indicates transient failure rather than insolvency.")
        elif "INSUFFICIENT" in safe_failure.upper():
            reasons.append("Account fund insufficiency requires non-intrusive payment link or notification.")
        else:
            reasons.append(f"Failure diagnosed as '{safe_failure}'.")
            
        if recommended_action == RecoveryAction.PAYMENT_LINK:
            reasons.append(f"Payment Link offers the highest expected recovery ({recovery_prob:.0%}) and net incremental uplift (₹{incremental_revenue:,.2f}).")
        elif recommended_action == RecoveryAction.RETRY:
            reasons.append(f"Smart Retry has minimal cost (₹2.00) with positive expected incremental return.")
        elif recommended_action == RecoveryAction.CUSTOMER_NOTIFICATION:
            reasons.append(f"Notification prompts customer completion without initiating direct charge attempts.")
        elif recommended_action == RecoveryAction.NO_ACTION:
            reasons.append("Intervention cost and customer friction exceed expected incremental recovery; natural recovery is preferred.")
            
        if requires_approval:
            reasons.append("Action flagged for human verification per merchant risk policy threshold.")

        summary_reason = " ".join(reasons)
        
        return {
            "intent": "RECOVERY_RECOMMENDATION",
            "transaction_id": transaction_id,
            "recommended_action": recommended_action.value,
            "reason": summary_reason,
            "reasons_list": reasons,
            "confidence": confidence,
            "expected_incremental_revenue": incremental_revenue
        }
