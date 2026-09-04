import pytest

from backend.app.services.ml.action_effectiveness import ActionEffectivenessModel
from backend.app.services.ml.features import ALLOWED_ACTIONS


PAYMENT_CONTEXT = {
    "amount": 5000.0,
    "payment_method": "UPI",
    "customer_type": "RETURNING",
    "failure_reason": "TIMEOUT",
    "previous_successful_payments": 8,
    "previous_failed_payments": 2,
    "retry_count": 0,
}


def test_action_effectiveness_predicts_each_allowed_action():
    model = ActionEffectivenessModel(
        model_path="ml/artifacts/action_effectiveness_model_v1.0.joblib"
    )
    probabilities = model.predict_action_probabilities(PAYMENT_CONTEXT)

    assert model.is_fallback is False
    assert list(probabilities) == ALLOWED_ACTIONS
    assert all(0.0 <= probability <= 1.0 for probability in probabilities.values())


def test_action_effectiveness_rejects_unknown_action():
    model = ActionEffectivenessModel(
        model_path="ml/artifacts/action_effectiveness_model_v1.0.joblib"
    )

    with pytest.raises(ValueError, match="Unsupported recovery action"):
        model.predict_action_probabilities(PAYMENT_CONTEXT, ["UNKNOWN_ACTION"])


def test_action_effectiveness_model_metadata_loads():
    model = ActionEffectivenessModel(
        model_path="ml/artifacts/action_effectiveness_model_v1.0.joblib"
    )

    assert model.model is not None
    assert model.model_version == "v1.0"