import os
import joblib
import pandas as pd
from typing import Dict, Any, Optional, List

from backend.app.services.ml.features import (
    ACTION_COLUMN,
    ALLOWED_ACTIONS,
    FEATURE_COLUMNS,
    extract_features_from_dict,
)


class ActionEffectivenessModel:
    """Predict synthetic recovery response for each context/action pair."""

    def __init__(self, model_path: Optional[str] = None):
        self.model_path = model_path or "ml/artifacts/action_effectiveness_model_v1.0.joblib"
        self.model = None
        self.model_version = "v1.0"
        self.is_fallback = True
        self._load_model()

    def _load_model(self) -> None:
        if not os.path.exists(self.model_path):
            return
        try:
            loaded = joblib.load(self.model_path)
            self.model = loaded.get("pipeline") if isinstance(loaded, dict) else loaded
            self.model_version = loaded.get("model_version", "v1.0") if isinstance(loaded, dict) else "v1.0"
            self.is_fallback = self.model is None
        except Exception as ex:
            print(f"Failed to load action-effectiveness artifact from {self.model_path}: {ex}")

    def predict_action_probabilities(
        self, payment_data: Dict[str, Any], actions: Optional[List[str]] = None
    ) -> Dict[str, float]:
        requested_actions = actions or ALLOWED_ACTIONS
        invalid_actions = sorted(set(requested_actions) - set(ALLOWED_ACTIONS))
        if invalid_actions:
            raise ValueError(f"Unsupported recovery action(s): {', '.join(invalid_actions)}")

        if self.is_fallback or self.model is None:
            raise RuntimeError("Action-effectiveness model artifact is unavailable")

        base_features = extract_features_from_dict(payment_data)
        rows = []
        for action in requested_actions:
            row = base_features.iloc[0].to_dict()
            row[ACTION_COLUMN] = action
            rows.append(row)
        features = pd.DataFrame(rows, columns=FEATURE_COLUMNS + [ACTION_COLUMN])
        probabilities = self.model.predict_proba(features)[:, 1]
        return {action: round(float(probability), 6) for action, probability in zip(requested_actions, probabilities)}


action_effectiveness_model_service = ActionEffectivenessModel()