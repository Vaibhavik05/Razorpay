from typing import Dict, Any, List, Tuple
from backend.app.schemas.contracts import RecoveryAction

# Default unit intervention costs (INR)
DEFAULT_INTERVENTION_COSTS = {
    RecoveryAction.NO_ACTION: 0.0,
    RecoveryAction.RETRY: 2.0,
    RecoveryAction.CUSTOMER_NOTIFICATION: 5.0,
    RecoveryAction.PAYMENT_LINK: 20.0,
    RecoveryAction.HUMAN_ESCALATION: 50.0,
}

class RevenueOptimizer:
    """
    Deterministic Revenue Optimizer (13_API_CONTRACTS.md Sections 13, 14, 15, 46)
    The backend must calculate financial values deterministically.
    The LLM must never determine the final monetary value.
    """
    
    @staticmethod
    def calculate_expected_recovery(probability: float, amount: float) -> float:
        """
        Expected Recovery = Recovery Probability * Transaction Amount
        """
        return round(float(probability * amount), 2)
    
    @staticmethod
    def calculate_incremental_revenue(
        action_probability: float,
        natural_probability: float,
        amount: float
    ) -> float:
        """
        Incremental Revenue = Expected Revenue With Action - Expected Revenue Without Action
        """
        expected_with_action = action_probability * amount
        expected_without_action = natural_probability * amount
        return round(float(max(0.0, expected_with_action - expected_without_action)), 2)
    
    @staticmethod
    def calculate_expected_net_value(
        incremental_revenue: float,
        intervention_cost: float,
        risk_cost: float = 0.0
    ) -> float:
        """
        Expected Net Value = Expected Incremental Revenue - Intervention Cost - Expected Risk Cost
        """
        return round(float(incremental_revenue - intervention_cost - risk_cost), 2)

    @classmethod
    def evaluate_candidate_actions(
        cls,
        amount: float,
        natural_recovery_prob: float,
        action_uplifts: Dict[RecoveryAction, float],
        allowed_actions: List[RecoveryAction] = None,
        custom_costs: Dict[RecoveryAction, float] = None
    ) -> Tuple[RecoveryAction, Dict[RecoveryAction, Dict[str, Any]]]:
        """
        Evaluates candidate actions deterministically and selects the best action
        based on maximum Expected Net Value.
        """
        costs = custom_costs or DEFAULT_INTERVENTION_COSTS
        allowed = allowed_actions or [
            RecoveryAction.NO_ACTION,
            RecoveryAction.RETRY,
            RecoveryAction.PAYMENT_LINK,
            RecoveryAction.CUSTOMER_NOTIFICATION
        ]
        
        evaluation: Dict[RecoveryAction, Dict[str, Any]] = {}
        
        # Base: NO_ACTION
        base_expected_recovery = cls.calculate_expected_recovery(natural_recovery_prob, amount)
        evaluation[RecoveryAction.NO_ACTION] = {
            "action": RecoveryAction.NO_ACTION,
            "recovery_probability": round(natural_recovery_prob, 4),
            "expected_recovery": base_expected_recovery,
            "incremental_revenue": 0.0,
            "intervention_cost": 0.0,
            "expected_net_value": 0.0
        }
        
        best_action = RecoveryAction.NO_ACTION
        best_net_value = 0.0
        
        for action, uplift in action_uplifts.items():
            if action not in allowed or action == RecoveryAction.NO_ACTION:
                continue
            
            # Bound probability between 0.0 and 0.99
            action_prob = min(0.99, max(0.01, natural_recovery_prob + uplift))
            expected_rec = cls.calculate_expected_recovery(action_prob, amount)
            inc_rev = cls.calculate_incremental_revenue(action_prob, natural_recovery_prob, amount)
            cost = costs.get(action, 10.0)
            
            # Risk cost can scale with retry frequency or high amounts
            risk_cost = 0.0
            if action == RecoveryAction.RETRY and amount > 25000:
                risk_cost = 5.0  # slight penalty for retrying large amounts directly
                
            net_val = cls.calculate_expected_net_value(inc_rev, cost, risk_cost)
            
            evaluation[action] = {
                "action": action,
                "recovery_probability": round(action_prob, 4),
                "expected_recovery": expected_rec,
                "incremental_revenue": inc_rev,
                "intervention_cost": cost,
                "expected_net_value": net_val
            }
            
            # Check if this action provides higher net incremental value
            if net_val > best_net_value:
                best_net_value = net_val
                best_action = action
                
        return best_action, evaluation

# Backward-compatible alias
RecoveryOptimizer = RevenueOptimizer

