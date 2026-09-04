"""
Unit tests for Deterministic Revenue Optimizer
Verifies financial math, cost deductions, and optimal recovery action selection.
"""
import pytest
from backend.app.schemas.contracts import RecoveryAction
from backend.app.services.optimizer import RevenueOptimizer, RecoveryOptimizer, DEFAULT_INTERVENTION_COSTS

def test_expected_recovery_calculation():
    amount = 5000.0
    prob = 0.65
    expected = RevenueOptimizer.calculate_expected_recovery(prob, amount)
    assert expected == round(5000.0 * 0.65, 2)
    assert expected == 3250.0

def test_incremental_revenue_calculation():
    amount = 10000.0
    natural_prob = 0.20
    action_prob = 0.75
    # (0.75 - 0.20) * 10000 = 5500.0
    incremental = RevenueOptimizer.calculate_incremental_revenue(action_prob, natural_prob, amount)
    assert incremental == 5500.0

def test_incremental_revenue_floor_at_zero():
    amount = 1000.0
    natural_prob = 0.50
    action_prob = 0.40  # lower than baseline
    incremental = RevenueOptimizer.calculate_incremental_revenue(action_prob, natural_prob, amount)
    assert incremental == 0.0

def test_expected_net_value():
    inc_rev = 500.0
    cost = 20.0
    risk = 5.0
    net = RevenueOptimizer.calculate_expected_net_value(inc_rev, cost, risk)
    assert net == 475.0

def test_evaluate_candidate_actions_picks_highest_net():
    amount = 2000.0
    natural_prob = 0.15
    action_uplifts = {
        RecoveryAction.RETRY: 0.20,             # prob 0.35 -> inc: 400 - 2 = 398
        RecoveryAction.PAYMENT_LINK: 0.50,      # prob 0.65 -> inc: 1000 - 20 = 980
        RecoveryAction.CUSTOMER_NOTIFICATION: 0.10 # prob 0.25 -> inc: 200 - 5 = 195
    }
    
    best_action, eval_dict = RevenueOptimizer.evaluate_candidate_actions(
        amount=amount,
        natural_recovery_prob=natural_prob,
        action_uplifts=action_uplifts
    )
    
    assert best_action == RecoveryAction.PAYMENT_LINK
    assert eval_dict[RecoveryAction.PAYMENT_LINK]["expected_net_value"] > eval_dict[RecoveryAction.RETRY]["expected_net_value"]
    assert eval_dict[RecoveryAction.NO_ACTION]["expected_net_value"] == 0.0

def test_evaluate_candidate_actions_falls_back_to_no_action():
    # Very low transaction amount where costs exceed potential recovery
    amount = 10.0
    natural_prob = 0.10
    action_uplifts = {
        RecoveryAction.PAYMENT_LINK: 0.05 # inc rev: 0.05 * 10 = 0.50, cost = 20 -> net -19.50
    }
    best_action, eval_dict = RevenueOptimizer.evaluate_candidate_actions(
        amount=amount,
        natural_recovery_prob=natural_prob,
        action_uplifts=action_uplifts
    )
    assert best_action == RecoveryAction.NO_ACTION

def test_evaluate_respects_allowed_actions():
    amount = 5000.0
    natural_prob = 0.10
    action_uplifts = {
        RecoveryAction.PAYMENT_LINK: 0.60,
        RecoveryAction.RETRY: 0.30
    }
    # Exclude PAYMENT_LINK
    best_action, eval_dict = RevenueOptimizer.evaluate_candidate_actions(
        amount=amount,
        natural_recovery_prob=natural_prob,
        action_uplifts=action_uplifts,
        allowed_actions=[RecoveryAction.NO_ACTION, RecoveryAction.RETRY]
    )
    assert best_action == RecoveryAction.RETRY
    assert RecoveryAction.PAYMENT_LINK not in eval_dict

def test_recovery_optimizer_alias():
    assert RecoveryOptimizer is RevenueOptimizer
