"""
frontend/app.py — NexaRecover AI · Streamlit Application Entrypoint
=====================================================================
Orchestrates all views via sidebar navigation and role-based access control.

Architecture rule: The frontend NEVER performs business logic or financial
calculations directly; all data and actions are brokered via FastAPI.
"""
import sys
import os

# Ensure workspace root is on path so `frontend.*` imports resolve correctly
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import streamlit as st

# ── Page config must be the very first Streamlit call ────────────────────────
st.set_page_config(
    page_title="NexaRecover AI · Revenue Intelligence",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        "Get Help": None,
        "Report a bug": None,
        "About": "NexaRecover AI — Razorpay Payment Recovery & Revenue Intelligence Platform",
    },
)

# ── Custom fintech CSS theme ─────────────────────────────────────────────────
st.markdown(
    """
    <style>
    /* ---- Google Inter typography ---- */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif !important;
    }

    /* ---- Global background ---- */
    .stApp {
        background-color: #F8FAFC;
    }

    /* ---- Remove default Streamlit padding top ---- */
    .block-container {
        padding-top: 1.2rem !important;
        padding-bottom: 2rem !important;
    }

    /* ---- Sidebar ---- */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0F172A 0%, #1E293B 100%) !important;
        border-right: 1px solid #334155;
    }
    [data-testid="stSidebar"] * {
        color: #CBD5E1 !important;
    }
    [data-testid="stSidebar"] .stRadio label,
    [data-testid="stSidebar"] .stSelectbox label {
        color: #94A3B8 !important;
        font-size: 11px !important;
        text-transform: uppercase !important;
        letter-spacing: 0.8px !important;
    }

    /* ---- KPI / Metric cards ---- */
    [data-testid="metric-container"] {
        background: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 10px;
        padding: 14px 16px !important;
        box-shadow: 0 1px 3px rgba(0,0,0,0.06);
    }
    [data-testid="metric-container"] label {
        color: #475569 !important;
        font-size: 12px !important;
        font-weight: 600 !important;
        text-transform: uppercase !important;
        letter-spacing: 0.6px !important;
    }
    [data-testid="metric-container"] [data-testid="stMetricValue"] {
        font-size: 26px !important;
        font-weight: 800 !important;
        color: #0F172A !important;
    }

    /* ---- Buttons ---- */
    .stButton > button {
        font-family: 'Inter', sans-serif !important;
        font-weight: 600 !important;
        border-radius: 6px !important;
        transition: all 0.15s ease-in-out !important;
    }
    .stButton > button[kind="primary"] {
        background: #2563EB !important;
        border-color: #1D4ED8 !important;
    }
    .stButton > button[kind="primary"]:hover {
        background: #1D4ED8 !important;
        transform: translateY(-1px) !important;
        box-shadow: 0 4px 12px rgba(37,99,235,0.35) !important;
    }

    /* ---- Dataframes ---- */
    .stDataFrame {
        border: 1px solid #E2E8F0 !important;
        border-radius: 8px !important;
        overflow: hidden;
    }

    /* ---- Horizontal rule ---- */
    hr {
        border: none !important;
        border-top: 1px solid #E2E8F0 !important;
        margin: 12px 0 !important;
    }

    /* ---- Status badge utility ---- */
    .badge-green  { background:#DCFCE7;color:#166534;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:700; }
    .badge-yellow { background:#FEF3C7;color:#92400E;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:700; }
    .badge-red    { background:#FEE2E2;color:#991B1B;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:700; }
    .badge-blue   { background:#DBEAFE;color:#1D4ED8;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:700; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Lazy imports (after path setup) ─────────────────────────────────────────
from frontend.api_client import APIClient
from frontend.components.nav import render_top_nav
from frontend.views.dashboard import render_dashboard
from frontend.views.opportunities import render_opportunities
from frontend.views.detail import render_detail
from frontend.views.approvals import render_approvals
from frontend.views.analytics import render_analytics
from frontend.views.experiments import render_experiments

# ── Session state defaults ───────────────────────────────────────────────────
_DEFAULTS = {
    "current_page": "Dashboard",
    "persona": "Merchant",
    "selected_recovery_id": None,
    "selected_tx_id": None,
    "selected_amount": None,
    "selected_failure": "TIMEOUT",
    "selected_action": "PAYMENT_LINK",
}
for k, v in _DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── Backend health probe ──────────────────────────────────────────────────────
def _probe_backend(client: APIClient) -> tuple[str, str]:
    """Returns (status_label, env_label) for top nav rendering."""
    try:
        resp = client.get_health()
        health_data = resp.get("data", {})
        if resp.get("success") and health_data.get("status") == "healthy":
            env = health_data.get("environment", resp.get("environment", "TEST")).upper()
            return "Healthy", env
    except Exception:
        pass
    return "Degraded", "UNKNOWN"

# ── Sidebar ──────────────────────────────────────────────────────────────────
PAGES = [
    "Dashboard",
    "Recovery Opportunities",
    "Opportunity Details",
    "Approvals Queue",
    "Analytics",
    "Strategy Experiments",
    "System Health & Config",
]

PERSONA_TOKENS = {
    "Merchant":  "merchant_token_acme",
    "Reviewer":  "reviewer_token",
    "Admin":     "admin_token",
}

with st.sidebar:
    # Brand mark
    st.markdown(
        """
        <div style="padding: 20px 0 10px 0;">
            <div style="font-size:20px;font-weight:800;letter-spacing:-0.5px;color:#F8FAFC;">
                ⚡ NexaRecover <span style="color:#60A5FA;">AI</span>
            </div>
            <div style="font-size:10px;font-weight:600;color:#64748B;letter-spacing:1px;margin-top:2px;">
                REVENUE INTELLIGENCE PLATFORM
            </div>
        </div>
        <hr style="border-top:1px solid #334155;margin:0 0 16px 0;" />
        """,
        unsafe_allow_html=True,
    )

    # Role / persona switcher
    st.markdown(
        "<div style='font-size:10px;font-weight:700;color:#64748B;letter-spacing:0.8px;text-transform:uppercase;margin-bottom:4px;'>Active Role</div>",
        unsafe_allow_html=True,
    )
    persona = st.selectbox(
        "persona_selector",
        options=list(PERSONA_TOKENS.keys()),
        index=list(PERSONA_TOKENS.keys()).index(st.session_state["persona"]),
        label_visibility="collapsed",
    )
    if persona != st.session_state["persona"]:
        st.session_state["persona"] = persona
        st.rerun()

    st.markdown("<div style='height:12px;'></div>", unsafe_allow_html=True)

    # View navigation
    st.markdown(
        "<div style='font-size:10px;font-weight:700;color:#64748B;letter-spacing:0.8px;text-transform:uppercase;margin-bottom:4px;'>Navigation</div>",
        unsafe_allow_html=True,
    )
    for page in PAGES:
        is_active = st.session_state["current_page"] == page
        btn_style = (
            "background:#2563EB;color:#FFFFFF;border-radius:6px;padding:8px 12px;"
            "font-weight:600;margin-bottom:2px;cursor:pointer;display:block;"
            if is_active
            else
            "background:transparent;color:#94A3B8;border-radius:6px;padding:8px 12px;"
            "font-weight:400;margin-bottom:2px;cursor:pointer;display:block;"
        )
        if st.button(
            page,
            key=f"nav_{page}",
            use_container_width=True,
        ):
            st.session_state["current_page"] = page
            st.rerun()

    st.markdown("<hr style='border-top:1px solid #334155;margin:16px 0;' />", unsafe_allow_html=True)

    # Webhook simulation panel
    with st.expander("🔧 Webhook Simulator", expanded=False):
        sim_payment_id = st.text_input("Payment ID", value="PAY_SIM_001", key="sim_pay_id")
        sim_amount = st.number_input("Amount (INR)", min_value=100.0, value=5000.0, step=100.0, key="sim_amount")
        sim_event = st.selectbox(
            "Event",
            ["payment.captured", "payment.failed", "subscription.charged"],
            key="sim_event",
        )
        if st.button("▶ Send Webhook", key="sim_send", use_container_width=True):
            try:
                _sim_client = APIClient(token=PERSONA_TOKENS[st.session_state["persona"]])
                result = _sim_client.send_webhook(sim_event, sim_payment_id, sim_amount)
                if result.get("success") or result.get("status") == "received":
                    st.success("✅ Webhook delivered!")
                else:
                    st.warning(f"Response: {result}")
            except Exception as e:
                st.error(f"Error: {e}")

    st.markdown(
        "<div style='font-size:10px;color:#334155;padding:12px 0 4px 0;'>© 2026 NexaRecover AI</div>",
        unsafe_allow_html=True,
    )

# ── Instantiate API client with current persona token ────────────────────────
client = APIClient(token=PERSONA_TOKENS[st.session_state["persona"]])

# ── Top navigation bar ───────────────────────────────────────────────────────
_status, _env = _probe_backend(client)
render_top_nav(
    merchant_name="Acme Store",
    environment=_env,
    status=_status,
)

# ── Route to active view ──────────────────────────────────────────────────────
page = st.session_state["current_page"]

if page == "Dashboard":
    render_dashboard(client)

elif page == "Recovery Opportunities":
    render_opportunities(client)

elif page == "Opportunity Details":
    if st.session_state.get("selected_recovery_id"):
        render_detail(client)
    else:
        st.info("💡 Select a recovery opportunity from the **Recovery Opportunities** view to inspect its details and execute a recovery action.")
        if st.button("← Go to Recovery Opportunities"):
            st.session_state["current_page"] = "Recovery Opportunities"
            st.rerun()

elif page == "Approvals Queue":
    render_approvals(client)

elif page == "Analytics":
    render_analytics(client)

elif page == "Strategy Experiments":
    render_experiments(client)

elif page == "System Health & Config":
    st.markdown("### 🔧 System Health & Configuration")
    st.caption("Live backend diagnostics and environment configuration overview.")

    col_h, col_r = st.columns(2)
    with col_h:
        st.markdown("#### Health Check")
        try:
            h = client.get_health()
            st.json(h)
        except Exception as e:
            st.error(f"Backend unreachable: {e}")

    with col_r:
        st.markdown("#### Readiness Check")
        try:
            r = client.get_readiness()
            st.json(r)
        except Exception as e:
            st.error(f"Readiness probe failed: {e}")

    st.markdown("---")
    st.markdown("#### Environment Summary")

    env_rows = {
        "API Base URL": client.base_url,
        "Razorpay Mode": os.getenv("RAZORPAY_MODE", "MOCK"),
        "Backend Status": _status,
        "Active Role": st.session_state["persona"],
        "Token": PERSONA_TOKENS[st.session_state["persona"]],
    }
    for k, v in env_rows.items():
        c1, c2 = st.columns([2, 4])
        with c1:
            st.markdown(f"**{k}**")
        with c2:
            st.code(v, language=None)
