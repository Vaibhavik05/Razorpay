import os
import requests
import streamlit as st
from typing import Dict, Any, Optional

DEFAULT_API_BASE_URL = "https://nexarecover-backend.onrender.com/api/v1"
API_TIMEOUT_SECONDS = int(os.getenv("API_TIMEOUT_SECONDS", "30"))


def get_api_base_url() -> str:
    """Resolve the backend URL from deployment config with a cloud default."""
    configured_url = os.getenv("API_BASE_URL")
    if configured_url:
        return configured_url.rstrip("/")

    try:
        configured_url = st.secrets.get("API_BASE_URL")
    except (FileNotFoundError, KeyError):
        configured_url = None

    return (configured_url or DEFAULT_API_BASE_URL).rstrip("/")

class APIClient:
    """
    HTTP client for Streamlit frontend.
    The frontend NEVER performs business logic or financial calculations directly;
    all data and actions are brokered via FastAPI (13_API_CONTRACTS.md Section 65).
    """
    def __init__(self, token: str = "merchant_token_acme"):
        self.token = token
        self.base_url = get_api_base_url()

    def _headers(self, idempotency_key: Optional[str] = None) -> Dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        return headers

    def get_dashboard(self) -> Dict[str, Any]:
        resp = requests.get(f"{self.base_url}/merchant/dashboard", headers=self._headers(), timeout=API_TIMEOUT_SECONDS)
        return resp.json()

    def get_metrics(self, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        resp = requests.get(f"{self.base_url}/metrics", headers=self._headers(), params=params or {}, timeout=API_TIMEOUT_SECONDS)
        return resp.json()

    def analyze_payment(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        resp = requests.post(f"{self.base_url}/payments/analyze", headers=self._headers(), json=payload, timeout=API_TIMEOUT_SECONDS)
        return resp.json()

    def recommend_recovery(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        resp = requests.post(f"{self.base_url}/recovery/recommend", headers=self._headers(), json=payload, timeout=API_TIMEOUT_SECONDS)
        return resp.json()

    def execute_recovery(self, payload: Dict[str, Any], idempotency_key: str) -> Dict[str, Any]:
        resp = requests.post(
            f"{self.base_url}/recovery/execute",
            headers=self._headers(idempotency_key=idempotency_key),
            json=payload,
            timeout=API_TIMEOUT_SECONDS
        )
        return resp.json()

    def get_recovery_status(self, recovery_id: str) -> Dict[str, Any]:
        resp = requests.get(f"{self.base_url}/recovery/{recovery_id}", headers=self._headers(), timeout=API_TIMEOUT_SECONDS)
        return resp.json()

    def approve_recovery(self, recovery_id: str, reviewer_id: str, comment: str = "") -> Dict[str, Any]:
        payload = {"reviewer_id": reviewer_id, "comment": comment}
        resp = requests.post(f"{self.base_url}/recovery/{recovery_id}/approve", headers=self._headers(), json=payload, timeout=API_TIMEOUT_SECONDS)
        return resp.json()

    def reject_recovery(self, recovery_id: str, reviewer_id: str, reason: str) -> Dict[str, Any]:
        payload = {"reviewer_id": reviewer_id, "reason": reason}
        resp = requests.post(f"{self.base_url}/recovery/{recovery_id}/reject", headers=self._headers(), json=payload, timeout=API_TIMEOUT_SECONDS)
        return resp.json()

    def get_audit(self, recovery_id: str) -> Dict[str, Any]:
        resp = requests.get(f"{self.base_url}/audit/{recovery_id}", headers=self._headers(), timeout=API_TIMEOUT_SECONDS)
        return resp.json()

    def get_health(self) -> Dict[str, Any]:
        resp = requests.get(f"{self.base_url}/health", timeout=API_TIMEOUT_SECONDS)
        return resp.json()

    def get_readiness(self) -> Dict[str, Any]:
        resp = requests.get(f"{self.base_url}/ready", timeout=API_TIMEOUT_SECONDS)
        return resp.json()

    def send_webhook(self, event_name: str, payment_id: str, amount_inr: float) -> Dict[str, Any]:
        """Trigger a realistic payment capture webhook event"""
        payload = {
            "event": event_name,
            "payload": {
                "payment": {
                    "entity": {
                        "id": payment_id,
                        "amount": int(round(amount_inr * 100)),
                        "currency": "INR",
                        "status": "captured"
                    }
                }
            }
        }
        headers = {
            "X-Razorpay-Signature": "valid_mock_signature",
            "Content-Type": "application/json"
        }
        resp = requests.post(f"{self.base_url}/webhooks/razorpay", headers=headers, json=payload, timeout=API_TIMEOUT_SECONDS)
        return resp.json()
