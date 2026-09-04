"""Final held-out buildathon comparison. No tuning or threshold selection occurs here."""
import json
import os
from typing import Callable, Dict, List

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

from backend.app.services.ml.features import FEATURE_COLUMNS, ALLOWED_ACTIONS
from backend.app.services.optimizer import DEFAULT_INTERVENTION_COSTS, RISK_COST_RATES, RevenueOptimizer

TEST_PATH = "data/test.csv"
OUTPUT_JSON = "ml/artifacts/final_buildathon_evaluation.json"
OUTPUT_MD = "ml/artifacts/final_buildathon_evaluation.md"
THRESHOLD = 0.405
OUTCOME_COLUMNS = {
    "NO_ACTION": "outcome_no_action",
    "RETRY": "outcome_retry",
    "PAYMENT_LINK": "outcome_payment_link",
    "CUSTOMER_NOTIFICATION": "outcome_customer_notification",
    "HUMAN_ESCALATION": "outcome_human_escalation",
}


def rule_action(row: pd.Series) -> str:
    reason = str(row["failure_reason"])
    if reason == "UNKNOWN":
        return "NO_ACTION"
    if reason in {"TIMEOUT", "GATEWAY_TIMEOUT", "NETWORK_ERROR"}:
        return "RETRY"
    if reason in {"INSUFFICIENT_FUNDS", "BANK_DECLINE", "LIMIT_EXCEEDED"}:
        return "PAYMENT_LINK"
    return "CUSTOMER_NOTIFICATION"


def evaluate_strategy(name: str, actions: List[str], frame: pd.DataFrame) -> Dict:
    selected_outcomes = np.array([
        frame.iloc[index][OUTCOME_COLUMNS[action]] for index, action in enumerate(actions)
    ], dtype=int)
    baseline = frame[OUTCOME_COLUMNS["NO_ACTION"]].to_numpy(dtype=int)
    amounts = frame["transaction_amount"].to_numpy(dtype=float)
    interventions = np.array([action != "NO_ACTION" for action in actions])
    costs = np.array([DEFAULT_INTERVENTION_COSTS[next(
        item for item in DEFAULT_INTERVENTION_COSTS if item.value == action
    )] for action in actions])
    risk_levels = np.where(amounts > 25000, "HIGH", np.where(amounts > 10000, "MEDIUM", "LOW"))
    risk_costs = np.array([
        0.0 if action == "NO_ACTION" else amount * RISK_COST_RATES[next(
            level for level in RISK_COST_RATES if level.value == risk
        )]
        for action, amount, risk in zip(actions, amounts, risk_levels)
    ])
    recovered_revenue = float(np.sum(selected_outcomes * amounts))
    baseline_revenue = float(np.sum(baseline * amounts))
    incremental_revenue = recovered_revenue - baseline_revenue
    intervention_cost = float(np.sum(costs))
    risk_cost = float(np.sum(risk_costs))
    net_revenue = recovered_revenue - intervention_cost - risk_cost
    observed_intervention = selected_outcomes[interventions]
    return {
        "strategy": name,
        "recovery_rate": round(float(selected_outcomes.mean()), 6),
        "recovered_revenue": round(recovered_revenue, 2),
        "baseline_no_action_revenue": round(baseline_revenue, 2),
        "incremental_revenue": round(incremental_revenue, 2),
        "intervention_cost": round(intervention_cost, 2),
        "expected_risk_cost": round(risk_cost, 2),
        "net_revenue": round(net_revenue, 2),
        "roi": round((incremental_revenue - intervention_cost - risk_cost) / intervention_cost, 6) if intervention_cost else None,
        "intervention_rate": round(float(interventions.mean()), 6),
        "no_action_rate": round(float((~interventions).mean()), 6),
        "unnecessary_intervention_rate": round(float(np.mean((selected_outcomes <= baseline)[interventions])), 6) if interventions.any() else 0.0,
        "action_success_rate": round(float(observed_intervention.mean()), 6) if len(observed_intervention) else 0.0,
        "recommended_action_distribution": pd.Series(actions).value_counts().sort_index().to_dict(),
    }


def main() -> Dict:
    frame = pd.read_csv(TEST_PATH)
    recovery_model = joblib.load("ml/artifacts/recovery_model_v1.0.joblib")["pipeline"]
    action_model = joblib.load("ml/artifacts/action_effectiveness_model_v1.0.joblib")["pipeline"]
    overall_probabilities = recovery_model.predict_proba(frame[FEATURE_COLUMNS])[:, 1]
    long_rows = []
    row_indices = []
    for index, row in frame.iterrows():
        for action in ALLOWED_ACTIONS:
            long_rows.append({**row[FEATURE_COLUMNS].to_dict(), "action": action})
            row_indices.append((index, action))
    action_probabilities = action_model.predict_proba(pd.DataFrame(long_rows))[:, 1]
    probability_map = {(index, action): probability for (index, action), probability in zip(row_indices, action_probabilities)}
    optimizer_actions = []
    optimizer_details = []
    for index, row in frame.iterrows():
        probabilities = {action: probability_map[(index, action)] for action in ALLOWED_ACTIONS}
        selected, details = RevenueOptimizer.optimize_action_probabilities(
            amount=float(row["transaction_amount"]),
            action_probabilities=probabilities,
            risk_level=None if False else __import__("backend.app.schemas.contracts", fromlist=["RiskLevel"]).RiskLevel.HIGH if row["transaction_amount"] > 25000 else __import__("backend.app.schemas.contracts", fromlist=["RiskLevel"]).RiskLevel.MEDIUM if row["transaction_amount"] > 10000 else __import__("backend.app.schemas.contracts", fromlist=["RiskLevel"]).RiskLevel.LOW,
        )
        optimizer_actions.append(selected.value)
        optimizer_details.append(details)
    full_actions = []
    for index, action in enumerate(optimizer_actions):
        amount = float(frame.iloc[index]["transaction_amount"])
        retry_limit = int(frame.iloc[index]["retry_count"]) >= 2
        approval_required = amount > 10000
        full_actions.append("NO_ACTION" if retry_limit or approval_required or action == "HUMAN_ESCALATION" else action)

    strategies = {
        "No Intervention": ["NO_ACTION"] * len(frame),
        "Always Retry": ["RETRY"] * len(frame),
        "Rule-Based Recovery": [rule_action(row) for _, row in frame.iterrows()],
        "ML Recovery": ["RETRY" if probability >= THRESHOLD else "NO_ACTION" for probability in overall_probabilities],
        "ML + Optimization": optimizer_actions,
        "ML + Uplift + Optimization": optimizer_actions,
        "Full NexaRecover AI": full_actions,
    }
    business = [evaluate_strategy(name, actions, frame) for name, actions in strategies.items()]
    result = {
        "evaluation_type": "final held-out test evaluation",
        "test_rows": len(frame),
        "test_set_used_for_tuning": False,
        "frozen_threshold": THRESHOLD,
        "frozen_costs": {action.value: cost for action, cost in DEFAULT_INTERVENTION_COSTS.items()},
        "frozen_risk_cost_rates": {level.value: rate for level, rate in RISK_COST_RATES.items()},
        "business_comparison": business,
        "ml_recovery_model": {
            "roc_auc": round(float(roc_auc_score(frame.recovered, overall_probabilities)), 6),
            "pr_auc": round(float(average_precision_score(frame.recovered, overall_probabilities)), 6),
            "precision": round(float(precision_score(frame.recovered, overall_probabilities >= THRESHOLD)), 6),
            "recall": round(float(recall_score(frame.recovered, overall_probabilities >= THRESHOLD)), 6),
            "f1": round(float(f1_score(frame.recovered, overall_probabilities >= THRESHOLD)), 6),
            "brier": round(float(brier_score_loss(frame.recovered, overall_probabilities)), 6),
        },
        "action_model": {
            "roc_auc": round(float(roc_auc_score(
                np.array([frame.iloc[index][OUTCOME_COLUMNS[action]] for index, action in row_indices]), action_probabilities
            )), 6),
            "pr_auc": round(float(average_precision_score(
                np.array([frame.iloc[index][OUTCOME_COLUMNS[action]] for index, action in row_indices]), action_probabilities
            )), 6),
            "brier": round(float(brier_score_loss(
                np.array([frame.iloc[index][OUTCOME_COLUMNS[action]] for index, action in row_indices]), action_probabilities
            )), 6),
        },
        "limitations": [
            "All business comparisons use synthetic potential outcomes.",
            "The observed action assignment is observational, not randomized.",
            "Action results are not production causal uplift estimates.",
            "ML + Optimization and ML + Uplift + Optimization share the frozen Phase 3 response surface; the latter names the explicit signed uplift calculation.",
            "Full NexaRecover AI applies current guardrail proxy rules for offline comparison.",
        ],
    }
    with open(OUTPUT_JSON, "w", encoding="utf-8") as output:
        json.dump(result, output, indent=2)
    lines = ["# Final Buildathon Evaluation", "", f"Held-out rows: {len(frame)}", "", "| Strategy | Recovery rate | Incremental revenue | Net revenue | ROI | Intervention rate |", "|---|---:|---:|---:|---:|---:|"]
    for item in business:
        lines.append(f"| {item['strategy']} | {item['recovery_rate']:.2%} | ₹{item['incremental_revenue']:,.2f} | ₹{item['net_revenue']:,.2f} | {item['roi'] if item['roi'] is not None else 'n/a'} | {item['intervention_rate']:.2%} |")
    lines += ["", "This is a final held-out evaluation only. No test rows were used for tuning.", "Results are synthetic/counterfactual estimates, not production causal claims."]
    with open(OUTPUT_MD, "w", encoding="utf-8") as output:
        output.write("\n".join(lines))
    print(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    main()
