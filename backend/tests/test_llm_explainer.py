import json

import requests

from backend.app.services.llm_explainer import OptionalLLMExplainer


DECISION = {
    "recommended_action": "PAYMENT_LINK",
    "decision_reason": "PAYMENT_LINK provides the highest positive incremental net value.",
    "guardrail_status": "ALLOW",
    "requires_approval": False,
    "baseline_probability": 0.4,
    "action_comparisons": [],
}


def test_disabled_ollama_uses_deterministic_fallback():
    result = OptionalLLMExplainer(enabled=False).explain(DECISION)
    assert result["source"] == "deterministic_fallback"
    assert "PAYMENT_LINK" in result["text"]


def test_available_ollama_explains_without_changing_decision(monkeypatch):
    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"response": json.dumps({"explanation": "The selected action has the best modeled value."})}

    monkeypatch.setattr(requests, "post", lambda *args, **kwargs: Response())
    result = OptionalLLMExplainer(enabled=True).explain(DECISION)
    assert result["source"] == "ollama"
    assert "best modeled value" in result["text"]
    assert DECISION["recommended_action"] == "PAYMENT_LINK"


def test_malformed_ollama_response_uses_fallback(monkeypatch):
    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"response": "not json"}

    monkeypatch.setattr(requests, "post", lambda *args, **kwargs: Response())
    result = OptionalLLMExplainer(enabled=True).explain(DECISION)
    assert result["source"] == "deterministic_fallback"


def test_ollama_timeout_uses_fallback(monkeypatch):
    def timeout(*args, **kwargs):
        raise requests.Timeout("timed out")

    monkeypatch.setattr(requests, "post", timeout)
    result = OptionalLLMExplainer(enabled=True).explain(DECISION)
    assert result["source"] == "deterministic_fallback"
