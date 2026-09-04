from typing import Dict, Any, List, Tuple, Union
from backend.app.schemas.contracts import RecoveryAction, RiskLevel

# Default unit intervention costs (INR)
DEFAULT_INTERVENTION_COSTS = {
    RecoveryAction.NO_ACTION: 0.0,
    RecoveryAction.RETRY: 2.0,
    RecoveryAction.CUSTOMER_NOTIFICATION: 5.0,
    RecoveryAction.PAYMENT_LINK: 20.0,
    RecoveryAction.HUMAN_ESCALATION: 50.0,
}

# Buildathon simulation assumptions for risk exposure as a share of payment value.
RISK_COST_RATES = {
    RiskLevel.LOW: 0.0,
    RiskLevel.MEDIUM: 0.01,
    RiskLevel.HIGH: 0.02,
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
        return round(float(expected_with_action - expected_without_action), 2)

    @staticmethod
    def calculate_uplift(action_probability: float, natural_probability: float) -> float:
        """Return signed action uplift relative to the NO_ACTION baseline."""
        return round(float(action_probability - natural_probability), 6)

    @staticmethod
    def calculate_expected_risk_cost(
        amount: float, action: RecoveryAction, risk_level: RiskLevel
    ) -> float:
        """Apply the transparent simulation risk rate to interventions only."""
        if action == RecoveryAction.NO_ACTION:
            return 0.0
        return round(float(amount * RISK_COST_RATES[risk_level]), 2)
    
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
        """Backward-compatible adapter for callers that provide explicit probabilities."""
        probabilities = {RecoveryAction.NO_ACTION: natural_recovery_prob}
        for action, uplift in action_uplifts.items():
            probabilities[action] = natural_recovery_prob + uplift
        legacy_allowed = allowed_actions or [
            RecoveryAction.NO_ACTION,
            RecoveryAction.RETRY,
            RecoveryAction.PAYMENT_LINK,
            RecoveryAction.CUSTOMER_NOTIFICATION,
        ]
        legacy_allowed = [action for action in legacy_allowed if action.value in {
            item.value if isinstance(item, RecoveryAction) else item for item in probabilities
        }]
        best_action, comparison = cls.optimize_action_probabilities(
            amount=amount,
            action_probabilities=probabilities,
            allowed_actions=legacy_allowed,
            custom_costs=custom_costs,
        )
        return best_action, {
            RecoveryAction(item["action"]): {
                "action": RecoveryAction(item["action"]),
                "recovery_probability": item["recovery_probability"],
                "expected_recovery": item["expected_recovered_revenue"],
                "incremental_revenue": item["expected_incremental_revenue"],
                "intervention_cost": item["intervention_cost"],
                "expected_net_value": item["expected_net_value"],
            }
            for item in comparison["comparisons"]
        }

    @classmethod
    def optimize_action_probabilities(
        cls,
        amount: float,
        action_probabilities: Dict[Union[RecoveryAction, str], float],
        allowed_actions: List[RecoveryAction] = None,
        custom_costs: Dict[RecoveryAction, float] = None,
        risk_level: RiskLevel = RiskLevel.LOW,
    ) -> Tuple[RecoveryAction, Dict[str, Any]]:
        """Compare modeled action probabilities and select the highest net value."""
        costs = custom_costs or DEFAULT_INTERVENTION_COSTS
        allowed = allowed_actions or list(RecoveryAction)
        normalized = {
            (action.value if isinstance(action, RecoveryAction) else action): float(probability)
            for action, probability in action_probabilities.items()
        }
        if RecoveryAction.NO_ACTION.value not in normalized:
            raise ValueError("NO_ACTION probability is required as the baseline")

        baseline_probability = normalized[RecoveryAction.NO_ACTION.value]
        comparisons = []
        for action in allowed:
            probability = min(1.0, max(0.0, normalized[action.value]))
            uplift = cls.calculate_uplift(probability, baseline_probability)
            incremental_revenue = round(uplift * amount, 2)
            intervention_cost = round(float(costs.get(action, 0.0)), 2)
            risk_cost = cls.calculate_expected_risk_cost(amount, action, risk_level)
            net_value = cls.calculate_expected_net_value(incremental_revenue, intervention_cost, risk_cost)
            comparisons.append({
                "action": action.value,
                "recovery_probability": round(probability, 6),
                "uplift": uplift,
                "transaction_amount": round(float(amount), 2),
                "expected_recovered_revenue": cls.calculate_expected_recovery(probability, amount),
                "expected_incremental_revenue": incremental_revenue,
                "intervention_cost": intervention_cost,
                "expected_risk_cost": risk_cost,
                "expected_net_value": net_value,
            })

        ranked = sorted(comparisons, key=lambda item: (-item["expected_net_value"], item["action"]))
        for rank, item in enumerate(ranked, start=1):
            item["rank"] = rank
        recommended = next(item for item in ranked if item["action"] == RecoveryAction.NO_ACTION.value)
        for item in ranked:
            if item["action"] != RecoveryAction.NO_ACTION.value and item["expected_net_value"] > recommended["expected_net_value"]:
                recommended = item

        if recommended["action"] == RecoveryAction.NO_ACTION.value:
            decision_reason = "NO_ACTION has the highest expected net value."
        else:
            decision_reason = f"{recommended['action']} provides the highest positive incremental net value."
        return RecoveryAction(recommended["action"]), {
            "baseline_action": RecoveryAction.NO_ACTION.value,
            "baseline_probability": round(baseline_probability, 6),
            "recommended_action": recommended["action"],
            "recommended_net_value": recommended["expected_net_value"],
            "recommended_uplift": recommended["uplift"],
            "decision_reason": decision_reason,
            "comparisons": ranked,
        }

# Backward-compatible alias
RecoveryOptimizer = RevenueOptimizer

