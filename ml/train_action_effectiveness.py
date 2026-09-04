import json
import os
import platform
from datetime import datetime, timezone
from typing import Any, Dict, List

import joblib
import numpy as np
import pandas as pd
import sklearn
import xgboost as xgb
from sklearn.calibration import calibration_curve
from sklearn.compose import ColumnTransformer
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from backend.app.services.ml.features import (
    ACTION_COLUMN,
    ALLOWED_ACTIONS,
    CATEGORICAL_COLUMNS,
    FEATURE_COLUMNS,
    NUMERICAL_COLUMNS,
)

RANDOM_SEED = 42
MODEL_VERSION = "v1.0"
MODEL_PATH = "ml/artifacts/action_effectiveness_model_v1.0.joblib"
METRICS_PATH = "ml/artifacts/action_effectiveness_metrics.json"
OUTCOME_COLUMNS = {
    "NO_ACTION": "outcome_no_action",
    "RETRY": "outcome_retry",
    "PAYMENT_LINK": "outcome_payment_link",
    "CUSTOMER_NOTIFICATION": "outcome_customer_notification",
    "HUMAN_ESCALATION": "outcome_human_escalation",
}


def build_action_pipeline() -> Pipeline:
    preprocessor = ColumnTransformer(
        transformers=[
            ("num", StandardScaler(), NUMERICAL_COLUMNS),
            ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL_COLUMNS + [ACTION_COLUMN]),
        ]
    )
    classifier = xgb.XGBClassifier(
        n_estimators=120,
        max_depth=4,
        learning_rate=0.08,
        random_state=RANDOM_SEED,
        eval_metric="logloss",
        n_jobs=1,
    )
    return Pipeline([("preprocessor", preprocessor), ("classifier", classifier)])


def expand_potential_outcomes(frame: pd.DataFrame) -> pd.DataFrame:
    rows: List[pd.DataFrame] = []
    base_columns = FEATURE_COLUMNS + ["recovered"]
    for action, outcome_column in OUTCOME_COLUMNS.items():
        action_rows = frame[base_columns].copy()
        action_rows[ACTION_COLUMN] = action
        action_rows["recovered"] = frame[outcome_column].astype(int).to_numpy()
        rows.append(action_rows)
    return pd.concat(rows, ignore_index=True)


def evaluate_predictions(
    frame: pd.DataFrame, probabilities: np.ndarray, split_name: str
) -> Dict[str, Any]:
    y_true = frame["recovered"].to_numpy()
    calibration_true, calibration_predicted = calibration_curve(
        y_true, probabilities, n_bins=10, strategy="quantile"
    )
    by_action: Dict[str, Any] = {}
    for action in ALLOWED_ACTIONS:
        mask = frame[ACTION_COLUMN].to_numpy() == action
        action_true = y_true[mask]
        action_probabilities = probabilities[mask]
        by_action[action] = {
            "sample_count": int(mask.sum()),
            "potential_outcome_recovery_rate": round(float(action_true.mean()), 6),
            "mean_predicted_probability": round(float(action_probabilities.mean()), 6),
            "roc_auc": round(float(roc_auc_score(action_true, action_probabilities)), 6),
            "pr_auc": round(float(average_precision_score(action_true, action_probabilities)), 6),
            "brier_score": round(float(brier_score_loss(action_true, action_probabilities)), 6),
        }
    return {
        "split": split_name,
        "sample_count": int(len(frame)),
        "roc_auc": round(float(roc_auc_score(y_true, probabilities)), 6),
        "pr_auc": round(float(average_precision_score(y_true, probabilities)), 6),
        "brier_score": round(float(brier_score_loss(y_true, probabilities)), 6),
        "probability_distribution": {
            "min": round(float(np.min(probabilities)), 6),
            "p25": round(float(np.percentile(probabilities, 25)), 6),
            "median": round(float(np.median(probabilities)), 6),
            "p75": round(float(np.percentile(probabilities, 75)), 6),
            "max": round(float(np.max(probabilities)), 6),
            "mean": round(float(np.mean(probabilities)), 6),
        },
        "calibration_curve": {
            "mean_predicted_probability": [round(float(value), 6) for value in calibration_predicted],
            "observed_fraction_positive": [round(float(value), 6) for value in calibration_true],
        },
        "by_action": by_action,
    }


def representative_context(frame: pd.DataFrame, model: Pipeline) -> Dict[str, float]:
    context = {
        "transaction_amount": float(frame.transaction_amount.median()),
        "payment_method": str(frame.payment_method.mode().iloc[0]),
        "customer_segment": str(frame.customer_segment.mode().iloc[0]),
        "failure_reason": str(frame.failure_reason.mode().iloc[0]),
        "previous_transaction_count": int(frame.previous_transaction_count.median()),
        "historical_success_rate": float(frame.historical_success_rate.median()),
        "retry_count": int(frame.retry_count.median()),
    }
    rows = [{**context, ACTION_COLUMN: action} for action in ALLOWED_ACTIONS]
    probabilities = model.predict_proba(pd.DataFrame(rows))[:, 1]
    return {action: round(float(probability), 6) for action, probability in zip(ALLOWED_ACTIONS, probabilities)}


def train() -> Dict[str, Any]:
    os.makedirs("ml/artifacts", exist_ok=True)
    source = pd.read_csv("data/train.csv")
    train_indices, validation_indices = train_test_split(
        np.arange(len(source)), test_size=0.2, random_state=RANDOM_SEED, stratify=source["recovered"]
    )
    train_long = expand_potential_outcomes(source.iloc[train_indices])
    validation_long = expand_potential_outcomes(source.iloc[validation_indices])
    model = build_action_pipeline().fit(train_long[FEATURE_COLUMNS + [ACTION_COLUMN]], train_long["recovered"])
    validation_probabilities = model.predict_proba(validation_long[FEATURE_COLUMNS + [ACTION_COLUMN]])[:, 1]
    validation_metrics = evaluate_predictions(validation_long, validation_probabilities, "train_validation")

    final_train_long = expand_potential_outcomes(source)
    final_model = build_action_pipeline().fit(
        final_train_long[FEATURE_COLUMNS + [ACTION_COLUMN]], final_train_long["recovered"]
    )

    # Test rows are loaded only after the model has been finalized on train data.
    test_source = pd.read_csv("data/test.csv")
    test_long = expand_potential_outcomes(test_source)
    test_probabilities = final_model.predict_proba(test_long[FEATURE_COLUMNS + [ACTION_COLUMN]])[:, 1]
    test_metrics = evaluate_predictions(test_long, test_probabilities, "held_out_test")

    observed_action_metrics = {}
    for action in ALLOWED_ACTIONS:
        action_rows = source[source.action_taken == action]
        observed_action_metrics[action] = {
            "sample_count": int(len(action_rows)),
            "observed_recovery_rate": round(float(action_rows.recovered.mean()), 6),
        }

    metadata = {
        "model_name": "action_effectiveness_response_surface",
        "model_version": MODEL_VERSION,
        "algorithm": "XGBoost",
        "prediction": "P(recovery | pre-decision context, action)",
        "feature_columns": FEATURE_COLUMNS,
        "action_column": ACTION_COLUMN,
        "allowed_actions": ALLOWED_ACTIONS,
        "categorical_features": CATEGORICAL_COLUMNS + [ACTION_COLUMN],
        "numerical_features": NUMERICAL_COLUMNS,
        "target_columns_by_action": OUTCOME_COLUMNS,
        "training_target": "synthetic potential outcome for each action",
        "action_assignment": "observational and context-dependent; not randomized",
        "causal_interpretation": "not a production causal uplift estimate",
        "random_seed": RANDOM_SEED,
        "training_rows": int(len(source)),
        "validation_rows": int(len(validation_indices)),
        "held_out_test_rows": int(len(test_source)),
        "training_long_rows": int(len(final_train_long)),
        "validation_long_rows": int(len(validation_long)),
        "held_out_test_long_rows": int(len(test_long)),
        "observed_action_metrics_train": observed_action_metrics,
        "validation_metrics": validation_metrics,
        "held_out_test_metrics": test_metrics,
        "representative_context_probabilities": representative_context(source, final_model),
        "training_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "software_versions": {
            "python": platform.python_version(),
            "scikit_learn": sklearn.__version__,
            "xgboost": xgb.__version__,
            "pandas": pd.__version__,
        },
        "test_set_used_for_tuning": False,
    }
    joblib.dump(
        {
            "pipeline": final_model,
            "model_version": MODEL_VERSION,
            "feature_cols": FEATURE_COLUMNS,
            "action_column": ACTION_COLUMN,
            "allowed_actions": ALLOWED_ACTIONS,
            "metrics": metadata,
        },
        MODEL_PATH,
    )
    with open(METRICS_PATH, "w", encoding="utf-8") as metrics_file:
        json.dump(metadata, metrics_file, indent=2)
    print(json.dumps(metadata, indent=2))
    return metadata


if __name__ == "__main__":
    train()