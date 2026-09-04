import hmac
import hashlib
import uuid
from typing import Dict, Any, Optional
from abc import ABC, abstractmethod
from backend.app.core.config import settings, get_settings

class RazorpayClientInterface(ABC):
    """
    Abstract Razorpay Client Interface (13_API_CONTRACTS.md Section 72-73)
    Decouples business logic from external SDKs and enables deterministic testing.
    """
    
    @abstractmethod
    def create_payment_link(
        self,
        amount_inr: float,
        currency: str,
        description: str,
        customer_details: Optional[Dict[str, Any]] = None,
        reference_id: Optional[str] = None
    ) -> Dict[str, Any]:
        pass

    @abstractmethod
    def fetch_payment(self, payment_id: str) -> Dict[str, Any]:
        pass

    @abstractmethod
    def verify_webhook_signature(self, body_bytes: bytes, signature: str, secret: Optional[str] = None) -> bool:
        pass

class MockRazorpayClient(RazorpayClientInterface):
    """
    Mock Razorpay Client for Offline / Buildathon Deterministic Testing
    """
    
    def __init__(self):
        self.created_links: Dict[str, Dict[str, Any]] = {}

    def create_payment_link(
        self,
        amount_inr: float,
        currency: str,
        description: str,
        customer_details: Optional[Dict[str, Any]] = None,
        reference_id: Optional[str] = None
    ) -> Dict[str, Any]:
        # Currency conversion: INR to paise
        amount_paise = int(round(amount_inr * 100))
        link_id = f"plink_{reference_id or uuid.uuid4().hex[:8]}"
        
        result = {
            "status": "success",
            "payment_link_id": link_id,
            "short_url": f"https://rzp.io/i/{link_id}",
            "amount": amount_paise,
            "currency": currency,
            "description": description,
            "reference_id": reference_id
        }
        self.created_links[link_id] = result
        return result

    def fetch_payment(self, payment_id: str) -> Dict[str, Any]:
        return {
            "id": payment_id,
            "status": "captured",
            "amount": 1250000,
            "currency": "INR",
            "method": "card"
        }

    def verify_webhook_signature(self, body_bytes: bytes, signature: str, secret: Optional[str] = None) -> bool:
        if not signature:
            return False
        if signature == "valid_mock_signature":
            return True
        sec = secret or settings.RAZORPAY_WEBHOOK_SECRET or "mock_secret"
        # Calculate expected HMAC SHA256
        expected_sig = hmac.new(
            sec.encode("utf-8"),
            body_bytes,
            hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected_sig, signature)


class RazorpayClient(RazorpayClientInterface):
    """
    Real Razorpay Client using official razorpay SDK
    """
    def __init__(self, key_id: str, key_secret: str):
        import razorpay
        self.client = razorpay.Client(auth=(key_id, key_secret))
        self.key_secret = key_secret

    def create_payment_link(
        self,
        amount_inr: float,
        currency: str,
        description: str,
        customer_details: Optional[Dict[str, Any]] = None,
        reference_id: Optional[str] = None
    ) -> Dict[str, Any]:
        amount_paise = int(round(amount_inr * 100))
        payload = {
            "amount": amount_paise,
            "currency": currency,
            "description": description,
            "reference_id": reference_id or str(uuid.uuid4()),
        }
        if customer_details:
            payload["customer"] = customer_details
            
        resp = self.client.payment_link.create(payload)
        return {
            "status": "success",
            "payment_link_id": resp.get("id"),
            "short_url": resp.get("short_url"),
            "amount": resp.get("amount"),
            "currency": resp.get("currency")
        }

    def fetch_payment(self, payment_id: str) -> Dict[str, Any]:
        return self.client.payment.fetch(payment_id)

    def verify_webhook_signature(self, body_bytes: bytes, signature: str, secret: Optional[str] = None) -> bool:
        sec = secret or settings.RAZORPAY_WEBHOOK_SECRET
        try:
            self.client.utility.verify_webhook_signature(body_bytes.decode("utf-8"), signature, sec)
            return True
        except Exception:
            return False

# Backward-compatible alias
RealRazorpayClient = RazorpayClient

def get_razorpay_client() -> RazorpayClientInterface:
    """Factory that returns the appropriate Razorpay client.

    - If ``RAZORPAY_MODE`` is set to ``MOCK`` (default) we always return the deterministic
      ``MockRazorpayClient`` which does not require any credentials.
    - If ``RAZORPAY_MODE`` is ``REAL`` we attempt to instantiate ``RazorpayClient``.
      Missing credentials or any initialization error raise a clear ``EnvironmentError``
      so the application fails fast rather than silently falling back to the mock client.
    """
    curr_settings = get_settings()
    mode = getattr(curr_settings, "RAZORPAY_MODE", "MOCK").upper()
    if mode == "MOCK":
        return MockRazorpayClient()
    # REAL mode - require credentials
    if not curr_settings.RAZORPAY_KEY_ID or not curr_settings.RAZORPAY_KEY_SECRET:
        raise EnvironmentError(
            "RAZORPAY_MODE=REAL requires RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET to be set in the environment."
        )
    try:
        return RazorpayClient(curr_settings.RAZORPAY_KEY_ID, curr_settings.RAZORPAY_KEY_SECRET)
    except Exception as exc:
        raise RuntimeError("Failed to initialise RazorpayClient") from exc

class RazorpayClientFactory:
    """Factory class providing static create() method matching test interface."""
    @staticmethod
    def create() -> RazorpayClientInterface:
        return get_razorpay_client()

