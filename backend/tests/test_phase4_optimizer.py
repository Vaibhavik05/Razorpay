from backend.app.schemas.contracts import RecoveryAction, RiskLevel
from backend.app.services.optimizer import RevenueOptimizer


ALL_ACTIONS = [
    RecoveryAction.NO_ACTION,
    RecoveryAction.RETRY,
    RecoveryAction.PAYMENT_LINK,
    RecoveryAction.CUSTOMER_NOTIFICATION,
    RecoveryAction.HUMAN_ESCALATION,
]


def optimize(probabilities, amount=1000.0, risk_level=RiskLevel.LOW, custom_costs=None):
    return RevenueOptimizer.optimize_action_probabilities(
        amount=amount,
        action_probabilities=probabilities,
        allowed_actions=ALL_ACTIONS,
        risk_level=risk_level,
        custom_costs=custom_costs,
    )


def test_no_action_is_explicit_zero_uplift_baseline():
    action, result = optimize({
        "NO_ACTION": 0.40,
        "RETRY": 0.45,
        "PAYMENT_LINK": 0.50,
        "CUSTOMER_NOTIFICATION": 0.42,
        "HUMAN_ESCALATION": 0.41,
    })

    no_action = next(item for item in result["comparisons"] if item["action"] == "NO_ACTION")
    assert no_action["uplift"] == 0.0
    assert no_action["intervention_cost"] == 0.0
    assert action == RecoveryAction.PAYMENT_LINK


def test_positive_uplift_can_produce_positive_net_value():
    action, result = optimize({
        "NO_ACTION": 0.30,
        "RETRY": 0.35,
        "PAYMENT_LINK": 0.75,
        "CUSTOMER_NOTIFICATION": 0.40,
        "HUMAN_ESCALATION": 0.50,
    })

    assert action == RecoveryAction.PAYMENT_LINK
    selected = next(item for item in result["comparisons"] if item["action"] == action.value)
    assert selected["uplift"] == 0.45
    assert selected["expected_incremental_revenue"] == 450.0
    assert selected["expected_net_value"] == 430.0


def test_negative_uplift_is_preserved_and_not_rewarded():
    action, result = optimize({
        "NO_ACTION": 0.60,
        "RETRY": 0.50,
        "PAYMENT_LINK": 0.55,
        "CUSTOMER_NOTIFICATION": 0.58,
        "HUMAN_ESCALATION": 0.59,
    })

    assert action == RecoveryAction.NO_ACTION
    retry = next(item for item in result["comparisons"] if item["action"] == "RETRY")
    assert retry["uplift"] == -0.1
    assert retry["expected_incremental_revenue"] == -100.0
    assert retry["expected_net_value"] < 0.0


def test_zero_uplift_still_deducts_intervention_cost():
    _, result = optimize({
        "NO_ACTION": 0.50,
        "RETRY": 0.50,
        "PAYMENT_LINK": 0.50,
        "CUSTOMER_NOTIFICATION": 0.50,
        "HUMAN_ESCALATION": 0.50,
    })

    payment_link = next(item for item in result["comparisons"] if item["action"] == "PAYMENT_LINK")
    assert payment_link["expected_incremental_revenue"] == 0.0
    assert payment_link["expected_net_value"] == -20.0


def test_risk_cost_is_transparent_and_deducted():
    _, result = optimize({
        "NO_ACTION": 0.20,
        "RETRY": 0.90,
        "PAYMENT_LINK": 0.21,
        "CUSTOMER_NOTIFICATION": 0.21,
        "HUMAN_ESCALATION": 0.21,
    }, amount=1000.0, risk_level=RiskLevel.HIGH)

    retry = next(item for item in result["comparisons"] if item["action"] == "RETRY")
    assert retry["expected_risk_cost"] == 20.0
    assert retry["expected_net_value"] == 678.0


def test_no_action_wins_when_all_interventions_are_non_positive():
    action, result = optimize({
        "NO_ACTION": 0.80,
        "RETRY": 0.81,
        "PAYMENT_LINK": 0.82,
        "CUSTOMER_NOTIFICATION": 0.81,
        "HUMAN_ESCALATION": 0.83,
    }, amount=100.0)

    assert action == RecoveryAction.NO_ACTION
    assert result["decision_reason"] == "NO_ACTION has the highest expected net value."


def test_highest_recovery_probability_is_not_always_selected():
    action, result = optimize({
        "NO_ACTION": 0.50,
        "RETRY": 0.60,
        "PAYMENT_LINK": 0.65,
        "CUSTOMER_NOTIFICATION": 0.55,
        "HUMAN_ESCALATION": 0.95,
    }, amount=1000.0, custom_costs={RecoveryAction.HUMAN_ESCALATION: 500.0})

    assert action == RecoveryAction.PAYMENT_LINK
    assert result["recommended_action"] == "PAYMENT_LINK"


def test_all_five_actions_are_compared_and_ranked():
    _, result = optimize({action.value: 0.5 for action in ALL_ACTIONS})
    comparisons = result["comparisons"]

    assert {item["action"] for item in comparisons} == {action.value for action in ALL_ACTIONS}
    assert sorted(item["rank"] for item in comparisons) == [1, 2, 3, 4, 5]
    assert result["baseline_action"] == "NO_ACTION"