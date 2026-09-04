from typing import Optional
import os
from pydantic_settings import BaseSettings
from pydantic import ConfigDict

class Settings(BaseSettings):
    PROJECT_NAME: str = "NexaRecover AI"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: str = "TEST"
    
    # Secret Key for JWT / Demo tokens
    SECRET_KEY: str = "nexarecover-secret-key-buildathon-demo-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440
    
    # Database
    DATABASE_URL: str = "sqlite:///./nexarecover.db"
    
    # Razorpay Integration
    # Use RAZORPAY_MODE=MOCK (default) for safe development.
    # In REAL mode, RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET must be provided via environment.
    RAZORPAY_MODE: str = "MOCK"
    RAZORPAY_KEY_ID: Optional[str] = None
    RAZORPAY_KEY_SECRET: Optional[str] = None
    RAZORPAY_WEBHOOK_SECRET: Optional[str] = None
    
    # ML & Explanations
    MODEL_PATH: str = "ml/artifacts/recovery_model_v1.0.joblib"
    DATASET_LABEL: str = "Synthetic (Buildathon Simulation)"
    
    model_config = ConfigDict(extra="ignore")


def get_settings() -> Settings:
    mode = os.environ.get("RAZORPAY_MODE", "MOCK").upper()
    key_id = os.environ.get("RAZORPAY_KEY_ID")
    key_secret = os.environ.get("RAZORPAY_KEY_SECRET")
    webhook_secret = os.environ.get("RAZORPAY_WEBHOOK_SECRET")
    
    if mode == "REAL" and (not key_id or not key_secret):
        raise EnvironmentError(
            "RAZORPAY_MODE=REAL requires RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET to be set in the environment."
        )
    
    return Settings(
        RAZORPAY_MODE=mode,
        RAZORPAY_KEY_ID=key_id,
        RAZORPAY_KEY_SECRET=key_secret,
        RAZORPAY_WEBHOOK_SECRET=webhook_secret,
    )

settings = Settings()

