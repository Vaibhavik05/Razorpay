import json
import os
from typing import Any, Dict

import requests


class OptionalLLMExplainer:
    """Optional Ollama explanation layer; never participates in decisioning."""

    def __init__(self, base_url: str | None = None, model: str | None = None, enabled: bool | None = None):
        self.base_url = (base_url or os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")).rstrip("/")
        self.model = model or os.getenv("OLLAMA_MODEL", "qwen2.5:3b")
        self.enabled = enabled if enabled is not None else os.getenv("OLLAMA_ENABLED", "false").lower() == "true"

    @staticmethod
    def fallback(decision: Dict[str, Any]) -> str:
        action = decision.get("recommended_action", "NO_ACTION")
        reason = decision.get("decision_reason", "No deterministic decision reason available.")
        guardrail = decision.get("guardrail_status", "UNKNOWN")
        approval = decision.get("requires_approval", False)
        return (
            f"{action} was selected by the deterministic revenue optimizer. {reason} "
            f"Guardrail status: {guardrail}. Human approval required: {approval}."
        )

    def explain(self, decision: Dict[str, Any]) -> Dict[str, Any]:
        fallback = self.fallback(decision)
        if not self.enabled:
            return {"source": "deterministic_fallback", "text": fallback}
        prompt = (
            "Explain this recovery decision in plain language. Do not calculate or change any values. "
            "Do not recommend a different action. Return JSON with one string field named explanation.\n"
            + json.dumps(decision, sort_keys=True, default=str)
        )
        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json={"model": self.model, "prompt": prompt, "stream": False},
                timeout=float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "10")),
            )
            response.raise_for_status()
            payload = response.json()
            raw = payload.get("response", "")
            parsed = json.loads(raw)
            explanation = parsed.get("explanation")
            if not isinstance(explanation, str) or not explanation.strip():
                raise ValueError("Malformed Ollama explanation")
            return {"source": "ollama", "model": self.model, "text": explanation.strip()}
        except (requests.RequestException, ValueError, TypeError, json.JSONDecodeError):
            return {"source": "deterministic_fallback", "text": fallback}


llm_explainer = OptionalLLMExplainer()
