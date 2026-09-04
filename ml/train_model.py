import json
import os
import platform
from datetime import datetime, timezone
from typing import Any, Dict, Tuple

import joblib
import numpy as np
import pandas as pd
import sklearn
import xgboost as xgb
from sklearn.calibration import CalibratedClassifierCV, calibration_curve
from sklearn.compose import ColumnTransformer
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from backend.app.services.ml.features import (
    CATEGORICAL_COLUMNS,
    FEATURE_COLUMNS,
    NUMERICAL_COLUMNS,
)

RANDOM_SEED = 42
TARGET_COLUMN = "recovered"
MODEL_VERSION = "v2.0"
MODEL_PATH = "ml/artifacts/recovery_model_v1.0.joblib"
METRICS_PATH = "ml/artifacts/model_metrics.json"


def build_pipeline() -> Pipeline:
    preprocessor = ColumnTransformer(
        transformers=[
            ("num", StandardScaler(), NUMERICAL_COLUMNS),
            ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL_COLUMNS),
        ]
    )
    classifier = xgb.XGBClassifier(
        n_estimators=100,
        max_depth=4,
        learning_rate=0.08,
        random_state=RANDOM_SEED,
        eval_metric="logloss",
        n_jobs=1,
    )
    return Pipeline([("preprocessor", preprocessor), ("classifier", classifier)])


def select_threshold(y_true: pd.Series, probabilities: np.ndarray) -> Tuple[float, float]:
    thresholds = np.linspace(0.05, 0.95, 181)
    scores = [f1_score(y_true, probabilities >= threshold, zero_division=0) for threshold in thresholds]
    best_index = int(np.argmax(scores))
    return float(thresholds[best_index]), float(scores[best_index])


def _fit_validation_models(X_dev: pd.DataFrame, y_dev: pd.Series) -> Tuple[Pipeline, CalibratedClassifierCV]:
    base_model = build_pipeline().fit(X_dev, y_dev)
    calibrated_model = CalibratedClassifierCV(
        estimator=build_pipeline(), method="sigmoid", cv=5, n_jobs=1
    ).fit(X_dev, y_dev)
    return base_model, calibrated_model


def _feature_importance(model: Any) -> Dict[str, float]:
    fitted_pipeline = model
    if isinstance(model, CalibratedClassifierCV):
        fitted_pipeline = model.calibrated_classifiers_[0].estimator
    preprocessor = fitted_pipeline.named_steps["preprocessor"]
    classifier = fitted_pipeline.named_steps["classifier"]
    names = preprocessor.get_feature_names_out()
    return {
        str(name): round(float(value), 8)
        for name, value in sorted(
            zip(names, classifier.feature_importances_), key=lambda pair: pair[1], reverse=True
        )
    }


def _distribution(probabilities: np.ndarray) -> Dict[str, float]:
    percentiles = np.percentile(probabilities, [0, 25, 50, 75, 100])
    return {
        "min": round(float(percentiles[0]), 6),
        "p25": round(float(percentiles[1]), 6),
        "median": round(float(percentiles[2]), 6),
        "p75": round(float(percentiles[3]), 6),
        "max": round(float(percentiles[4]), 6),
        "mean": round(float(np.mean(probabilities)), 6),
    }


def _evaluate(
    y_true: pd.Series,
    probabilities: np.ndarray,
    threshold: float,
    split_name: str,
) -> Dict[str, Any]:
    predictions = (probabilities >= threshold).astype(int)
    calibration_fraction, calibration_mean = calibration_curve(
        y_true, probabilities, n_bins=10, strategy="quantile"
    )
    return {
        "split": split_name,
        "roc_auc": round(float(roc_auc_score(y_true, probabilities)), 6),
        "pr_auc": round(float(average_precision_score(y_true, probabilities)), 6),
        "precision": round(float(precision_score(y_true, predictions, zero_division=0)), 6),
        "recall": round(float(recall_score(y_true, predictions, zero_division=0)), 6),
        "f1": round(float(f1_score(y_true, predictions, zero_division=0)), 6),
        "brier_score": round(float(brier_score_loss(y_true, probabilities)), 6),
        "confusion_matrix": confusion_matrix(y_true, predictions, labels=[0, 1]).tolist(),
        "observed_recovery_rate": round(float(np.mean(y_true)), 6),
        "predicted_positive_rate": round(float(np.mean(predictions)), 6),
        "probability_distribution": _distribution(probabilities),
        "calibration_curve": {
            "mean_predicted_probability": [round(float(value), 6) for value in calibration_mean],
            "observed_fraction_positive": [round(float(value), 6) for value in calibration_fraction],
        },
    }


def train() -> Dict[str, Any]:
    os.makedirs("ml/artifacts", exist_ok=True)
    train_df = pd.read_csv("data/train.csv")
    X = train_df[FEATURE_COLUMNS].copy()
    y = train_df[TARGET_COLUMN].astype(int).copy()
    X_dev, X_validation, y_dev, y_validation = train_test_split(
        X, y, test_size=0.2, random_state=RANDOM_SEED, stratify=y
    )

    base_validation, calibrated_validation = _fit_validation_models(X_dev, y_dev)
    base_validation_probabilities = base_validation.predict_proba(X_validation)[:, 1]
    calibrated_validation_probabilities = calibrated_validation.predict_proba(X_validation)[:, 1]
    calibration_used = brier_score_loss(y_validation, calibrated_validation_probabilities) < brier_score_loss(
        y_validation, base_validation_probabilities
    )
    validation_probabilities = calibrated_validation_probabilities if calibration_used else base_validation_probabilities
    threshold, validation_f1 = select_threshold(y_validation, validation_probabilities)

    final_model: Any
    if calibration_used:
        final_model = CalibratedClassifierCV(
            estimator=build_pipeline(), method="sigmoid", cv=5, n_jobs=1
        ).fit(X, y)
    else:
        final_model = build_pipeline().fit(X, y)

    # The held-out test set is loaded only after model and threshold selection are complete.
    test_df = pd.read_csv("data/test.csv")
    X_test = test_df[FEATURE_COLUMNS].copy()
    y_test = test_df[TARGET_COLUMN].astype(int).copy()
    test_probabilities = final_model.predict_proba(X_test)[:, 1]
    test_metrics = _evaluate(y_test, test_probabilities, threshold, "held_out_test")
    validation_metrics = _evaluate(y_validation, validation_probabilities, threshold, "train_validation")

    metadata = {
        "model_name": "recovery_probability_model",
        "model_version": MODEL_VERSION,
        "algorithm": "XGBoost with sigmoid calibration" if calibration_used else "XGBoost",
        "target_column": TARGET_COLUMN,
        "feature_columns": FEATURE_COLUMNS,
        "categorical_features": CATEGORICAL_COLUMNS,
        "numerical_features": NUMERICAL_COLUMNS,
        "preprocessing": "StandardScaler for numerical features; OneHotEncoder(handle_unknown=ignore) for categorical features",
        "random_seed": RANDOM_SEED,
        "threshold": round(threshold, 6),
        "threshold_selection": "maximum F1 on train-only validation split",
        "calibration_used": calibration_used,
        "calibration_method": "sigmoid, 5-fold cross-validation on training data" if calibration_used else None,
        "training_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "dataset": "Synthetic (Buildathon Simulation)",
        "training_rows": int(len(train_df)),
        "training_positive_count": int(y.sum()),
        "training_negative_count": int((1 - y).sum()),
        "validation_rows": int(len(y_validation)),
        "held_out_test_rows": int(len(test_df)),
        "held_out_test_positive_count": int(y_test.sum()),
        "held_out_test_negative_count": int((1 - y_test).sum()),
        "feature_count": len(FEATURE_COLUMNS),
        "validation_f1": round(validation_f1, 6),
        "validation_metrics": validation_metrics,
        "held_out_test_metrics": test_metrics,
        "feature_importance": _feature_importance(final_model),
        "software_versions": {
            "python": platform.python_version(),
            "scikit_learn": sklearn.__version__,
            "xgboost": xgb.__version__,
            "pandas": pd.__version__,
        },
        "test_set_used_for_tuning": False,
    }

    artifact = {
        "pipeline": final_model,
        "version": MODEL_VERSION,
        "algorithm": metadata["algorithm"],
        "metrics": metadata,
        "feature_cols": FEATURE_COLUMNS,
    }
    joblib.dump(artifact, MODEL_PATH)
    with open(METRICS_PATH, "w", encoding="utf-8") as metrics_file:
        json.dump(metadata, metrics_file, indent=2)
    print(json.dumps(metadata, indent=2))
    return metadata


if __name__ == "__main__":
    train()
