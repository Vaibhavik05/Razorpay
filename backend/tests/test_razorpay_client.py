# test_razorpay_client.py – verifies client factory returns mock or real client

import os
import pytest
from unittest import mock
from backend.app.core.config import Settings, get_settings
from backend.app.services.razorpay_client import RazorpayClientFactory

def test_factory_returns_mock_when_mode_mock(monkeypatch):
    monkeypatch.setenv("RAZORPAY_MODE", "MOCK")
    client = RazorpayClientFactory.create()
    assert client.__class__.__name__ == "MockRazorpayClient"

def test_factory_raises_when_real_and_missing_keys(monkeypatch):
    monkeypatch.setenv("RAZORPAY_MODE", "REAL")
    # Ensure keys are not set
    monkeypatch.delenv("RAZORPAY_KEY_ID", raising=False)
    monkeypatch.delenv("RAZORPAY_KEY_SECRET", raising=False)
    with pytest.raises(EnvironmentError):
        RazorpayClientFactory.create()

def test_factory_returns_real_when_keys_present(monkeypatch):
    monkeypatch.setenv("RAZORPAY_MODE", "REAL")
    monkeypatch.setenv("RAZORPAY_KEY_ID", "test_id")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "test_secret")
    client = RazorpayClientFactory.create()
    # Assuming the real client class is named RazorpayClient
    assert client.__class__.__name__ == "RazorpayClient"
