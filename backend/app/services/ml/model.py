import os
import joblib
from typing import Dict, Any, Tuple
import numpy as np
from backend.app.core.config import settings
from backend.app.services.ml.features import extract_features_from_dict

class MLRecoveryModel:
    """
    ML Recovery Probability Predictor (13_API_CONTRACTS.md Section 44)
    Provides model prediction with confidence and conservative rule-based fallback.
    """
    
    def __init__(self, model_path: str = None):
        self.model_path = model_path or settings.MODEL_PATH
        self.model = None
        self.model_name = "recovery_probability_model"
        self.model_version = "v1.0"
        self.algorithm = "XGBoost"
        self.is_fallback = False
        self._load_model()
        
    def _load_model(self):
        if os.path.exists(self.model_path):
            try:
                loaded = joblib.load(self.model_path)
                if isinstance(loaded, dict):
                    self.model = loaded.get("pipeline") or loaded.get("model")
                    self.model_version = loaded.get("version", "v1.0")
                    self.algorithm = loaded.get("algorithm", "XGBoost")
                else:
                    self.model = loaded
                self.is_fallback = False
                return
            except Exception as ex:
                print(f"Failed to load ML model artifact from {self.model_path}: {ex}")
        
        self.is_fallback = True

    def predict(self, payment_data: Dict[str, Any]) -> Tuple[float, float, str]:
        """
        Returns (recovery_probability, confidence, model_version)
        """
        # If model is loaded, predict probability
        if self.model and not self.is_fallback:
            try:
                features_df = extract_features_from_dict(payment_data)
                probs = self.model.predict_proba(features_df)
                prob = float(probs[0][1])
                # Calibrated confidence based on prediction certainty distance from 0.5
                confidence = float(min(0.98, max(0.65, 0.70 + abs(prob - 0.5) * 0.5)))
                return round(prob, 4), round(confidence, 2), self.model_version
            except Exception as ex:
                print(f"Inference error, falling back to rule-based predictor: {ex}")
        
        # Rule-Based Conservative Fallback (11_GUARDRAILS_SECURITY.md Section 62)
        prob, conf = self._rule_based_fallback(payment_data)
        return prob, conf, f"{self.model_version}-fallback"

    def _rule_based_fallback(self, payment_data: Dict[str, Any]) -> Tuple[float, float]:
        """
        Intentionally conservative rule-based fallback logic.
        """
        failure_reason = str(payment_data.get("failure_reason", "")).upper()
        payment_method = str(payment_data.get("payment_method", "")).upper()
        customer_type = str(payment_data.get("customer_type") or payment_data.get("customer_segment") or "").upper()
        amount = float(payment_data.get("amount") or payment_data.get("transaction_amount") or 0.0)
        
        base_prob = 0.50
        
        # Adjust for failure reason
        if "TIMEOUT" in failure_reason:
            base_prob += 0.25
        elif "NETWORK" in failure_reason:
            base_prob += 0.18
        elif "INSUFFICIENT_FUNDS" in failure_reason:
            base_prob -= 0.15
        elif "DECLINE" in failure_reason or "BANK" in failure_reason:
            base_prob -= 0.05

        # Adjust for customer segment
        if customer_type in ["LOYAL", "HIGH_VALUE", "RETURNING"]:
            base_prob += 0.10
        elif customer_type == "NEW":
            base_prob -= 0.05
            
        # Adjust for payment method
        if payment_method == "UPI":
            base_prob += 0.08
        elif payment_method == "CARD":
            base_prob += 0.04

        # Large amounts are slightly harder to recover immediately
        if amount > 20000:
            base_prob -= 0.08

        prob = min(0.92, max(0.15, base_prob))
        confidence = 0.85 if "TIMEOUT" in failure_reason else 0.75
        return round(prob, 4), round(confidence, 2)

# Global singleton model service
ml_model_service = MLRecoveryModel()
