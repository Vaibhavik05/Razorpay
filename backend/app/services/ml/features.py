from typing import Dict, Any
import pandas as pd
import numpy as np

CATEGORICAL_COLUMNS = [
    "payment_method",
    "customer_segment",
    "failure_reason"
]

NUMERICAL_COLUMNS = [
    "transaction_amount",
    "previous_transaction_count",
    "historical_success_rate",
    "retry_count"
]

def extract_features_from_dict(data: Dict[str, Any]) -> pd.DataFrame:
    """
    Extracts and standardizes raw feature inputs into a DataFrame for model inference.
    """
    # Map common aliases
    amount = float(data.get("amount") or data.get("transaction_amount") or 0.0)
    prev_success = int(data.get("previous_successful_payments") or data.get("previous_success_count") or 0)
    prev_failed = int(data.get("previous_failed_payments") or data.get("previous_failure_count") or 0)
    total_txns = prev_success + prev_failed
    
    historical_rate = float(data.get("historical_success_rate") or (prev_success / total_txns if total_txns > 0 else 0.8))
    
    feature_row = {
        "transaction_amount": amount,
        "payment_method": str(data.get("payment_method", "CARD")).upper(),
        "customer_segment": str(data.get("customer_type") or data.get("customer_segment") or "RETURNING").upper(),
        "failure_reason": str(data.get("failure_reason", "TIMEOUT")).upper(),
        "previous_transaction_count": total_txns,
        "historical_success_rate": historical_rate,
        "retry_count": int(data.get("retry_count", 0))
    }
    
    return pd.DataFrame([feature_row])
