import streamlit as st
import pandas as pd
from frontend.api_client import APIClient

def render_opportunities(client: APIClient):
    st.markdown("### 🎯 Recovery Opportunities")
    st.caption("Prioritized failed transactions ranked by deterministic **Expected Incremental Revenue**.")

    # 1. Filters & Search (09_UI_UX_DESIGN_SPEC.md Section 47-48)
    col1, col2, col3, col4 = st.columns([3, 2, 2, 2])
    with col1:
        search_query = st.text_input("🔍 Search Payment / Recovery ID", placeholder="e.g. TXN123, PAY_DEMO_001").strip()
    with col2:
        failure_filter = st.selectbox("Failure Reason", ["All", "TIMEOUT", "INSUFFICIENT_FUNDS", "BANK_DECLINE", "NETWORK_ERROR"])
    with col3:
        action_filter = st.selectbox("Recommended Action", ["All", "PAYMENT_LINK", "RETRY", "CUSTOMER_NOTIFICATION", "HUMAN_ESCALATION"])
    with col4:
        status_filter = st.selectbox("Status", ["All", "RECOMMENDED", "APPROVAL_REQUIRED", "EXECUTED", "RECOVERED"])

    # 2. Fetch opportunities from DB via Dashboard API or direct records
    try:
        dash_res = client.get_dashboard()
        if not dash_res.get("success"):
            st.error("Failed to fetch opportunities from API.")
            return
        top_opps = dash_res.get("data", {}).get("top_opportunities", [])
    except Exception as ex:
        st.error(f"API Error: {ex}")
        return

    # Add canonical demo items if not in list
    canonical_items = [
        {
            "recovery_id": "REC789",
            "transaction_id": "TXN123",
            "amount": 12500.0,
            "failure_reason": "TIMEOUT",
            "recommended_action": "PAYMENT_LINK",
            "expected_incremental_revenue": 2150.0,
            "confidence": 0.91,
            "risk_level": "LOW",
            "status": "RECOMMENDED"
        },
        {
            "recovery_id": "REC_DEMO_001",
            "transaction_id": "PAY_DEMO_001",
            "amount": 5000.0,
            "failure_reason": "TIMEOUT",
            "recommended_action": "PAYMENT_LINK",
            "expected_incremental_revenue": 2250.0,
            "confidence": 0.89,
            "risk_level": "LOW",
            "status": "RECOMMENDED"
        },
        {
            "recovery_id": "REC_PAY_10293",
            "transaction_id": "PAY_10293",
            "amount": 25000.0,
            "failure_reason": "TIMEOUT",
            "recommended_action": "HUMAN_ESCALATION",
            "expected_incremental_revenue": 4500.0,
            "confidence": 0.85,
            "risk_level": "HIGH",
            "status": "APPROVAL_REQUIRED"
        }
    ]

    # Combine and deduplicate
    seen = set()
    combined_opps = []
    for item in canonical_items + top_opps:
        r_id = item.get("recovery_id")
        if r_id not in seen:
            seen.add(r_id)
            combined_opps.append(item)

    # Filter
    filtered = []
    for opp in combined_opps:
        t_id = opp.get("transaction_id", "")
        r_id = opp.get("recovery_id", "")
        f_reason = opp.get("failure_reason", "")
        act = opp.get("recommended_action", "")
        st_val = opp.get("status", "RECOMMENDED")

        if search_query and (search_query.lower() not in t_id.lower() and search_query.lower() not in r_id.lower()):
            continue
        if failure_filter != "All" and failure_filter != f_reason:
            continue
        if action_filter != "All" and action_filter != act:
            continue
        if status_filter != "All" and status_filter != st_val:
            continue

        filtered.append(opp)

    # Sort primarily by Expected Incremental Revenue (09_UI_UX_DESIGN_SPEC.md Section 13)
    filtered.sort(key=lambda x: x.get("expected_incremental_revenue", 0.0), reverse=True)

    if not filtered:
        st.info("No recovery opportunities found matching the selected filters.")
        return

    st.markdown(f"**Found {len(filtered)} opportunities** (ranked by highest incremental return)")

    # Render table with action buttons
    for idx, opp in enumerate(filtered):
        r_id = opp.get("recovery_id")
        t_id = opp.get("transaction_id")
        amt = opp.get("amount", 0.0)
        inc_rev = opp.get("expected_incremental_revenue", 0.0)
        action = opp.get("recommended_action")
        risk = opp.get("risk_level", "LOW")
        conf = opp.get("confidence", 0.85)

        with st.container():
            c1, c2, c3, c4, c5, c6 = st.columns([2, 2, 2, 2, 2, 2])
            with c1:
                st.markdown(f"**{t_id}**<br/><span style='font-size:11px;color:#64748B;'>{r_id}</span>", unsafe_allow_html=True)
            with c2:
                st.markdown(f"**₹{amt:,.2f}**<br/><span style='font-size:11px;color:#64748B;'>Amount</span>", unsafe_allow_html=True)
            with c3:
                st.markdown(f"<span style='color:#10B981;font-weight:700;'>+₹{inc_rev:,.2f}</span><br/><span style='font-size:11px;color:#64748B;'>Inc. Revenue</span>", unsafe_allow_html=True)
            with c4:
                st.markdown(f"**{action}**<br/><span style='font-size:11px;color:#64748B;'>Conf: {conf:.0%}</span>", unsafe_allow_html=True)
            with c5:
                badge_bg = "#DCFCE7" if risk == "LOW" else ("#FEF3C7" if risk == "MEDIUM" else "#FEE2E2")
                badge_fg = "#166534" if risk == "LOW" else ("#92400E" if risk == "MEDIUM" else "#991B1B")
                st.markdown(f"<span style='background:{badge_bg};color:{badge_fg};padding:3px 8px;border-radius:4px;font-size:12px;font-weight:600;'>{risk} RISK</span>", unsafe_allow_html=True)
            with c6:
                if st.button("Inspect & Act", key=f"btn_act_{r_id}_{idx}"):
                    st.session_state["selected_recovery_id"] = r_id
                    st.session_state["selected_tx_id"] = t_id
                    st.session_state["selected_amount"] = amt
                    st.session_state["selected_failure"] = opp.get("failure_reason", "TIMEOUT")
                    st.session_state["selected_action"] = action
                    st.session_state["current_page"] = "Opportunity Details"
                    st.rerun()
            st.markdown("<hr style='margin:6px 0 10px 0;border-top:1px solid #F1F5F9;'/>", unsafe_allow_html=True)
