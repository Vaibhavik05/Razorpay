# test_config.py – verifies config loading and mode handling

import os
import pytest
from backend.app.core.config import Settings, get_settings

def test_default_mode(monkeypatch):
    monkeypatch.delenv('RAZORPAY_MODE', raising=False)
    settings = get_settings()
    assert settings.RAZORPAY_MODE == 'MOCK'

def test_real_mode_requires_keys(monkeypatch):
    monkeypatch.setenv('RAZORPAY_MODE', 'REAL')
    with pytest.raises(EnvironmentError):
        get_settings()

def test_mock_mode_allows_missing_keys(monkeypatch):
    monkeypatch.setenv('RAZORPAY_MODE', 'MOCK')
    settings = get_settings()
    assert settings.RAZORPAY_MODE == 'MOCK'
    assert settings.RAZORPAY_KEY_ID is None
    assert settings.RAZORPAY_KEY_SECRET is None
