"""Focused tests for the reproducible recovery-probability model pipeline."""

import joblib

from backend.app.services.ml.features import FEATURE_COLUMNS, extract_features_from_dict
from backend.app.services.ml.model import MLRecoveryModel


def test_feature_extraction_matches_training_schema():
    features = extract_features_from_dict(
        {
            "amount": 2500.0,
            "payment_method": "upi",
            "customer_type": "returning",
            "failure_reason": "timeout",
            "previous_success_count": 8,
            "previous_failure_count": 2,
            "retry_count": 1,
        }
    )

    assert list(features.columns) == FEATURE_COLUMNS
    assert features.loc[0, "transaction_amount"] == 2500.0
    assert features.loc[0, "payment_method"] == "UPI"
    assert features.loc[0, "previous_transaction_count"] == 10


def test_current_artifact_loads_and_predicts_probability():
    model = MLRecoveryModel(model_path="ml/artifacts/recovery_model_v1.0.joblib")
    probability, confidence, version = model.predict(
        {
            "amount": 5000.0,
            "payment_method": "CARD",
            "customer_type": "RETURNING",
            "failure_reason": "TIMEOUT",
            "previous_success_count": 8,
            "previous_failure_count": 2,
            "retry_count": 0,
        }
    )

    assert model.is_fallback is False
    assert 0.0 <= probability <= 1.0
    assert 0.0 <= confidence <= 1.0
    assert version == "v2.0"


def test_artifact_metadata_records_held_out_evaluation():
    artifact = joblib.load("ml/artifacts/recovery_model_v1.0.joblib")
    metrics = artifact["metrics"]

    assert artifact["feature_cols"] == FEATURE_COLUMNS
    assert metrics["target_column"] == "recovered"
    assert metrics["training_rows"] == 40000
    assert metrics["held_out_test_rows"] == 10000
    assert metrics["test_set_used_for_tuning"] is False
    assert set(metrics["held_out_test_metrics"]) >= {
        "roc_auc",
        "pr_auc",
        "precision",
        "recall",
        "f1",
        "brier_score",
        "confusion_matrix",
        "calibration_curve",
    }