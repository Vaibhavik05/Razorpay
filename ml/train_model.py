import os
import json
import pandas as pd
import numpy as np
import joblib
from sklearn.pipeline import Pipeline
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.metrics import roc_auc_score, precision_score, recall_score, f1_score, brier_score_loss
import xgboost as xgb

def train():
    train_path = "data/train.csv"
    test_path = "data/test.csv"
    os.makedirs("ml/artifacts", exist_ok=True)
    
    if not os.path.exists(train_path) or not os.path.exists(test_path):
        print(f"Data files {train_path} or {test_path} not found. Ensure synthetic data is present.")
        return

    print("Loading train and test datasets...")
    train_df = pd.read_csv(train_path)
    test_df = pd.read_csv(test_path)

    feature_cols = [
        "transaction_amount",
        "payment_method",
        "customer_segment",
        "failure_reason",
        "previous_transaction_count",
        "historical_success_rate",
        "retry_count"
    ]
    target_col = "recovered"

    X_train = train_df[feature_cols].copy()
    y_train = train_df[target_col].copy()
    X_test = test_df[feature_cols].copy()
    y_test = test_df[target_col].copy()

    # Preprocessing
    categorical_cols = ["payment_method", "customer_segment", "failure_reason"]
    numerical_cols = ["transaction_amount", "previous_transaction_count", "historical_success_rate", "retry_count"]

    preprocessor = ColumnTransformer(
        transformers=[
            ("num", StandardScaler(), numerical_cols),
            ("cat", OneHotEncoder(handle_unknown="ignore"), categorical_cols)
        ]
    )

    classifier = xgb.XGBClassifier(
        n_estimators=100,
        max_depth=4,
        learning_rate=0.08,
        random_state=42,
        eval_metric="logloss"
    )

    pipeline = Pipeline(steps=[
        ("preprocessor", preprocessor),
        ("classifier", classifier)
    ])

    print("Training XGBoost recovery model...")
    pipeline.fit(X_train, y_train)

    print("Evaluating model on held-out test set...")
    test_preds_proba = pipeline.predict_proba(X_test)[:, 1]
    test_preds = (test_preds_proba >= 0.5).astype(int)

    roc_auc = float(roc_auc_score(y_test, test_preds_proba))
    precision = float(precision_score(y_test, test_preds, zero_division=0))
    recall = float(recall_score(y_test, test_preds, zero_division=0))
    f1 = float(f1_score(y_test, test_preds, zero_division=0))
    brier = float(brier_score_loss(y_test, test_preds_proba))

    metrics = {
        "model_name": "recovery_probability_model",
        "version": "v1.0",
        "algorithm": "XGBoost",
        "roc_auc": round(roc_auc, 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "brier_score": round(brier, 4),
        "dataset": "Synthetic (Buildathon Simulation)",
        "train_samples": len(X_train),
        "test_samples": len(X_test)
    }

    print("Evaluation Results:", json.dumps(metrics, indent=2))

    artifact_package = {
        "pipeline": pipeline,
        "version": "v1.0",
        "algorithm": "XGBoost",
        "metrics": metrics,
        "feature_cols": feature_cols
    }

    model_path = "ml/artifacts/recovery_model_v1.0.joblib"
    joblib.dump(artifact_package, model_path)
    print(f"Saved model artifact to {model_path}")

    with open("ml/artifacts/model_metrics.json", "w") as f:
        json.dump(metrics, f, indent=2)
    print("Saved model metrics to ml/artifacts/model_metrics.json")

if __name__ == "__main__":
    train()
