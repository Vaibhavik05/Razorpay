# ⚡ NexaRecover AI — Razorpay Payment Recovery & Revenue Intelligence Platform

> **Deterministic AI-powered failed-payment recovery engine built on FastAPI + Streamlit, with Razorpay integration.**  
> Recovers lost revenue through intelligent retry sequencing, payment links, customer notifications, and human-in-the-loop approvals — all backed by an XGBoost ML classifier and a transparent revenue optimizer.

---

## Table of Contents

1. [System Overview](#system-overview)
2. [Architecture & Data Flow](#architecture--data-flow)
3. [Key Modules](#key-modules)
4. [Project Structure](#project-structure)
5. [Quick-Start Setup](#quick-start-setup)
6. [Environment Variables](#environment-variables)
7. [Running the Application](#running-the-application)
8. [API Reference](#api-reference)
9. [Webhook Simulation](#webhook-simulation)
10. [Running Automated Tests](#running-automated-tests)
11. [Safety Guardrails](#safety-guardrails)
12. [Razorpay Integration Modes](#razorpay-integration-modes)

---

## System Overview

NexaRecover AI monitors Razorpay payment events in real time and automatically identifies failed transactions that are worth recovering. For each failure it:

1. **Classifies** the root cause (timeout, network error, bank decline, insufficient funds) using an XGBoost model.
2. **Optimises** the recovery action selection (retry / payment link / notification / human escalation) using a deterministic Expected Incremental Revenue formula.
3. **Enforces** safety guardrails (retry limits, idempotency, opt-out respect, high-value human approvals).
4. **Executes** the action via Razorpay in `MOCK` (deterministic, zero cost) or `REAL` (live API) mode.
5. **Presents** all intelligence and controls through a Streamlit revenue intelligence dashboard.

---

## Architecture & Data Flow

```
Razorpay Webhook
      │
      ▼
┌─────────────────────────────────────────────────────────────┐
│  FastAPI Backend  (backend/app)                             │
│                                                             │
│  POST /webhooks/razorpay                                    │
│    └─► verify_webhook_signature (HMAC-SHA256 guardrail)     │
│    └─► PaymentAnalysisService                               │
│          └─► XGBoost ML Classifier (ml/)                   │
│          └─► RevenueOptimizer (deterministic math)          │
│          └─► GuardrailService  (safety constraints)         │
│          └─► RazorpayClientFactory → MOCK | REAL client     │
│          └─► SQLAlchemy → SQLite / PostgreSQL               │
│                                                             │
│  REST API Endpoints:                                        │
│    GET  /api/v1/merchant/dashboard                          │
│    POST /api/v1/payments/analyze                            │
│    POST /api/v1/recovery/recommend                          │
│    POST /api/v1/recovery/execute    (idempotency key)       │
│    POST /api/v1/recovery/{id}/approve                       │
│    POST /api/v1/recovery/{id}/reject                        │
│    GET  /api/v1/health | /ready                             │
└─────────────────────────────────────────────────────────────┘
      │  HTTP (JSON)
      ▼
┌──────────────────────────────────────┐
│  Streamlit Frontend  (frontend/)     │
│                                      │
│  frontend/app.py  (entrypoint)       │
│    ├─ Dashboard          (KPIs, trend chart)              │
│    ├─ Recovery Opportunities  (ranked list)               │
│    ├─ Opportunity Details     (AI explainer + execution)  │
│    ├─ Approvals Queue         (human-in-the-loop)         │
│    ├─ Analytics               (channel & segment perf.)  │
│    ├─ Strategy Experiments    (A/B test monitor)          │
│    └─ System Health & Config  (health probes)             │
└──────────────────────────────────────┘
```

> **Architecture Constraint:** The frontend **NEVER** performs business logic or financial calculations directly. All computation is done in FastAPI and consumed via the `APIClient`.

---

## Key Modules

### 1. ML XGBoost Classifier — `ml/`
- Pre-trained gradient-boosted classifier that predicts the probability of successfully recovering a failed payment given: failure reason, amount tier, customer segment, payment method, time-of-day, and historical retry outcomes.
- Outputs a `recovery_probability` score (0–1) used downstream in the optimizer.

### 2. Deterministic Revenue Optimizer — `backend/app/services/revenue_optimizer.py`
- **No randomness.** Given a list of candidate recovery actions for a payment, the optimizer selects the action with the highest **Expected Incremental Revenue (EIR)**:

  ```
  EIR(action) = recovery_probability(action) × payment_amount × (1 - commission_rate)
              − intervention_cost(action)
  ```
- Tie-breaking is deterministic (alphabetical action name sort).
- Exposed via `RevenueOptimizer.optimize()` and `RecoveryOptimizer` alias.

### 3. Safety Guardrail Engine — `backend/app/services/guardrails.py`
- **Fail-closed**: blocks execution if any guardrail fires.
- Rules enforced before every recovery execution:
  | Guardrail | Policy |
  |-----------|--------|
  | Retry limit | Maximum 3 automated retries per payment |
  | Idempotency | Same `Idempotency-Key` header → returns cached result, not a new action |
  | Opt-out | Customer marked `do_not_contact=True` → blocks all outreach |
  | High-value threshold | Transactions > ₹10,000 require human approval before execution |
  | Signature verification | Webhook signature must match HMAC-SHA256; `valid_mock_signature` accepted in MOCK mode |

### 4. Razorpay Integration Adapter — `backend/app/services/razorpay_client.py`
- `RazorpayClientInterface` — abstract base class.
- `MockRazorpayClient` — deterministic, no network calls. Returns pre-defined success responses.
- `RealRazorpayClient` (`RazorpayClient`) — thin wrapper around the official Razorpay Python SDK.
- `RazorpayClientFactory.create(settings)` — instantiates the correct client based on `RAZORPAY_MODE`.

---

## Project Structure

```
Razorpay-1/
├── backend/
│   ├── app/
│   │   ├── api/v1/              # FastAPI routers
│   │   │   ├── payments.py      # POST /payments/analyze
│   │   │   ├── recovery.py      # POST /recovery/recommend|execute, approve, reject
│   │   │   ├── dashboard.py     # GET  /merchant/dashboard
│   │   │   └── webhooks.py      # POST /webhooks/razorpay
│   │   ├── core/
│   │   │   ├── config.py        # Settings (pydantic-settings), get_settings()
│   │   │   └── database.py      # SQLAlchemy engine + session factory
│   │   ├── models/
│   │   │   └── entities.py      # ORM: FailedPayment, RecoveryAttempt, AuditEvent
│   │   ├── schemas/             # Pydantic request/response models
│   │   ├── services/
│   │   │   ├── ai_explainer.py      # LLM / template explanation generator
│   │   │   ├── guardrails.py        # SafetyGuardrailEngine / GuardrailService
│   │   │   ├── razorpay_client.py   # Mock & Real client + factory
│   │   │   └── revenue_optimizer.py # Deterministic EIR optimizer
│   │   ├── dependencies.py      # FastAPI dependency injection (get_db)
│   │   └── main.py              # Application factory, lifespan, middleware
│   └── tests/
│       ├── conftest.py          # In-memory SQLite fixtures (StaticPool)
│       ├── test_api.py          # Integration tests (TestClient)
│       ├── test_guardrails.py   # Unit tests — safety guardrail engine
│       ├── test_optimizer.py    # Unit tests — revenue optimizer math
│       ├── test_config.py       # Config validation tests
│       └── test_razorpay_client.py  # Mock/Real client factory tests
├── frontend/
│   ├── app.py                   # ← Streamlit entrypoint (this file)
│   ├── api_client.py            # HTTP client broker — all backend calls go here
│   ├── components/
│   │   ├── kpi.py               # KPI card widget
│   │   └── nav.py               # Top navigation bar
│   └── views/
│       ├── dashboard.py         # Revenue intelligence KPIs + trend chart
│       ├── opportunities.py     # Ranked recovery opportunity list
│       ├── detail.py            # Single opportunity inspect & execute
│       ├── approvals.py         # Human-in-the-loop review portal
│       ├── analytics.py         # Channel & segment performance breakdown
│       └── experiments.py       # A/B strategy experiment monitor
├── ml/                          # XGBoost model artefacts + training scripts
├── data/                        # Seed data and sample failed payment CSVs
├── scripts/                     # Database seeding and utility scripts
├── .streamlit/config.toml       # Streamlit brand theme configuration
├── .env.example                 # Template — copy to .env and fill in values
├── requirements.txt             # Python dependencies
└── README.md                    # This file
```

---

## Quick-Start Setup

### Prerequisites

- Python 3.11+
- pip

### 1. Clone & install dependencies

```powershell
cd Razorpay-1
pip install -r requirements.txt
```

### 2. Configure environment

```powershell
Copy-Item .env.example .env
# Edit .env — set RAZORPAY_MODE=MOCK for local testing (no API keys needed)
```

### 3. Seed the database (optional demo data)

```powershell
$env:PYTHONPATH = "."
python scripts/seed_db.py
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `RAZORPAY_MODE` | `MOCK` | `MOCK` for deterministic local testing, `REAL` for live Razorpay API |
| `RAZORPAY_KEY_ID` | *(empty)* | Required when `RAZORPAY_MODE=REAL` |
| `RAZORPAY_KEY_SECRET` | *(empty)* | Required when `RAZORPAY_MODE=REAL` |
| `RAZORPAY_WEBHOOK_SECRET` | *(empty)* | HMAC secret for webhook signature verification |
| `DATABASE_URL` | `sqlite:///./nexarecover.db` | SQLAlchemy connection string |
| `API_BASE_URL` | `http://127.0.0.1:8000/api/v1` | Base URL used by Streamlit frontend |
| `SECRET_KEY` | `changeme-in-production` | JWT / session signing key |
| `DEBUG` | `false` | Enable FastAPI debug mode |

> **Security:** Setting `RAZORPAY_MODE=REAL` without valid `RAZORPAY_KEY_ID` / `RAZORPAY_KEY_SECRET` will raise an `EnvironmentError` at startup — **fail-closed** by design.

---

## Running the Application

### Start the FastAPI backend

```powershell
$env:PYTHONPATH = "."
uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
```

The API will be available at:
- **Swagger UI:** http://127.0.0.1:8000/docs  
- **ReDoc:** http://127.0.0.1:8000/redoc  
- **Health:** http://127.0.0.1:8000/api/v1/health  

### Start the Streamlit frontend (separate terminal)

```powershell
$env:PYTHONPATH = "."
streamlit run frontend/app.py
```

The dashboard opens at **http://localhost:8501**.

---

## API Reference

### Health & Readiness

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/health` | Liveness probe — returns `{"status": "ok"}` |
| `GET` | `/api/v1/ready` | Readiness probe — checks DB connectivity |

### Payments

| Method | Path | Body | Description |
|--------|------|------|-------------|
| `POST` | `/api/v1/payments/analyze` | `PaymentAnalysisRequest` | Classify failure, score recovery probability, recommend action |

**Request body:**
```json
{
  "transaction_id": "TXN123",
  "amount": 12500.0,
  "failure_reason": "TIMEOUT",
  "customer_id": "CUST456",
  "payment_method": "UPI",
  "merchant_id": "MERCH001"
}
```

### Recovery

| Method | Path | Body | Description |
|--------|------|------|-------------|
| `POST` | `/api/v1/recovery/recommend` | `RecoveryRecommendRequest` | Get ranked action recommendations with EIR |
| `POST` | `/api/v1/recovery/execute` | `RecoveryExecuteRequest` | Execute recommended action (requires `Idempotency-Key` header) |
| `GET`  | `/api/v1/recovery/{recovery_id}` | — | Get status of a specific recovery attempt |
| `POST` | `/api/v1/recovery/{recovery_id}/approve` | `ApprovalRequest` | Human reviewer approves a flagged action |
| `POST` | `/api/v1/recovery/{recovery_id}/reject` | `RejectionRequest` | Human reviewer rejects a flagged action |

**Execute request (with idempotency):**
```http
POST /api/v1/recovery/execute
Authorization: Bearer merchant_token_acme
Idempotency-Key: exec-TXN123-20260904-001
Content-Type: application/json

{
  "recovery_id": "REC789",
  "transaction_id": "TXN123",
  "action": "PAYMENT_LINK",
  "amount": 12500.0
}
```

### Dashboard

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/merchant/dashboard` | Aggregate KPIs + top recovery opportunities |

### Webhooks

| Method | Path | Headers | Description |
|--------|------|---------|-------------|
| `POST` | `/api/v1/webhooks/razorpay` | `X-Razorpay-Signature` | Receive Razorpay payment events |

---

## Webhook Simulation

Use the **Webhook Simulator** panel in the Streamlit sidebar, or call the API directly:

```powershell
# Simulate a payment.captured event (MOCK mode accepts "valid_mock_signature")
$body = @{
    event = "payment.captured"
    payload = @{
        payment = @{
            entity = @{
                id = "PAY_SIM_001"
                amount = 500000   # in paise
                currency = "INR"
                status = "captured"
            }
        }
    }
} | ConvertTo-Json -Depth 5

Invoke-RestMethod -Method POST `
    -Uri "http://127.0.0.1:8000/api/v1/webhooks/razorpay" `
    -Headers @{"X-Razorpay-Signature" = "valid_mock_signature"; "Content-Type" = "application/json"} `
    -Body $body
```

---

## Running Automated Tests

The test suite uses an **in-memory SQLite** database with `StaticPool` for speed and isolation. No external services are required.

```powershell
$env:PYTHONPATH = "."
python -m pytest backend/tests -v
```

Expected output:
```
backend/tests/test_api.py          ... PASSED
backend/tests/test_guardrails.py   ... PASSED
backend/tests/test_optimizer.py    ... PASSED
backend/tests/test_config.py       ... PASSED
backend/tests/test_razorpay_client.py ... PASSED
```

### Test coverage highlights

| Test File | What's Verified |
|-----------|----------------|
| `test_api.py` | All REST endpoints via `TestClient`; idempotency, guardrail enforcement, webhook signature check |
| `test_guardrails.py` | Retry limit, duplicate execution blocking, opt-out, high-value approval threshold |
| `test_optimizer.py` | EIR formula correctness, best-action selection, cost deduction, tie-breaking |
| `test_config.py` | `REAL` mode fails when credentials missing; `MOCK` mode requires no credentials |
| `test_razorpay_client.py` | Factory creates `MockRazorpayClient` in MOCK mode; `verify_webhook_signature` accepts valid mock signature |

---

## Safety Guardrails

All guardrails are **fail-closed**: if a check fails, the recovery action is blocked and the reason is logged to the `audit_events` table.

```
┌─────────────────────────────────────────────────────┐
│  GuardrailService.check(recovery_id, tx_id, ...)   │
│                                                     │
│  1. Idempotency check  → cached result if duplicate │
│  2. Retry limit (≤ 3) → block if exceeded           │
│  3. Opt-out check     → block if do_not_contact     │
│  4. High-value check  → require approval if > ₹10K  │
│  5. Allowlist check   → only known actions allowed  │
│                                                     │
│  All results written to audit_events table          │
└─────────────────────────────────────────────────────┘
```

---

## Razorpay Integration Modes

| Mode | `RAZORPAY_MODE` | Credentials Required | Network Calls | Use Case |
|------|----------------|----------------------|---------------|----------|
| Mock | `MOCK` | No | None | Local dev, CI/CD, demo |
| Real | `REAL` | Yes (Key ID + Secret) | Yes (live API) | Production / staging |

Switch modes by setting `RAZORPAY_MODE` in your `.env` file. The backend validates credentials at startup when `REAL` mode is configured.

---

*Built with ❤️ using FastAPI, Streamlit, SQLAlchemy, Razorpay Python SDK, XGBoost, and Plotly.*