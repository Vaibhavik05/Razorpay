import streamlit as st
import pandas as pd
from frontend.components.kpi import render_kpi_card
from frontend.api_client import APIClient

def render_dashboard(client: APIClient):
    st.markdown("### 📊 Revenue Intelligence Dashboard")
    st.caption("Real-time telemetry on revenue at risk, automated recovery actions, and financial yield.")

    # 1. Fetch Dashboard Data from API
    try:
        dash_res = client.get_dashboard()
        if not dash_res.get("success"):
            st.error(f"Failed to load dashboard: {dash_res.get('error', {}).get('message')}")
            return
        dash_data = dash_res.get("data", {})
    except Exception as ex:
        st.error(f"Cannot connect to backend API: {ex}. Ensure FastAPI backend is running.")
        return

    # 2. Render 4 Primary Fintech KPI Cards (09_UI_UX_DESIGN_SPEC.md Section 9)
    rev_at_risk = dash_data.get("revenue_at_risk", 0.0)
    rev_recovered = dash_data.get("recovered_revenue", 0.0)
    inc_revenue = dash_data.get("incremental_revenue", 0.0)
    rec_rate = dash_data.get("recovery_rate", 0.0) * 100
    avg_rec_val = dash_data.get("average_recovery_value", 0.0)

    kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)
    with kpi1:
        render_kpi_card(
            title="Revenue At Risk",
            value=f"₹{rev_at_risk / 100000:,.1f}L" if rev_at_risk >= 100000 else f"₹{rev_at_risk:,.0f}",
            subtext="from backend records",
            trend="",
            is_positive=False
        )
    with kpi2:
        render_kpi_card(
            title="Recovered Revenue",
            value=f"₹{rev_recovered / 100000:,.1f}L" if rev_recovered >= 100000 else f"₹{rev_recovered:,.0f}",
            subtext="from backend records",
            trend="",
            is_positive=True
        )
    with kpi3:
        render_kpi_card(
            title="Recovery Rate",
            value=f"{rec_rate:.1f}%",
            subtext="vs previous period",
            trend="↑ 5.8 pts",
            is_positive=True
        )
    with kpi4:
        render_kpi_card(
            title="Incremental Revenue",
            value=f"₹{inc_revenue / 100000:,.1f}L" if inc_revenue >= 100000 else f"₹{inc_revenue:,.0f}",
            subtext="from recorded recoveries",
            trend="",
            is_positive=True
        )
    with kpi5:
        render_kpi_card(
            title="Avg Recovery Value",
            value=f"₹{avg_rec_val:,.0f}",
            subtext="Per recovered payment",
            trend="",
            is_positive=True
        )

    # 3. Trend Chart (09_UI_UX_DESIGN_SPEC.md Section 11)
    st.markdown("#### 📈 Revenue Recovery Trend")
    st.info("Time-series recovery data is not available from the backend yet.")

    # 4. Top Opportunities & AI Actions Summary (Section 8, 30)
    col_opp, col_actions = st.columns([5, 3])
    
    with col_opp:
        st.markdown("#### 🎯 Top Recovery Opportunities")
        top_opps = dash_data.get("top_opportunities", [])
        if top_opps:
            opp_rows = []
            for opp in top_opps[:6]:
                opp_rows.append({
                    "Recovery ID": opp.get("recovery_id"),
                    "Payment ID": opp.get("transaction_id"),
                    "Amount": f"₹{opp.get('amount', 0):,.2f}",
                    "Expected Gain": f"₹{opp.get('expected_incremental_revenue', 0):,.2f}",
                    "Recommended Action": opp.get("recommended_action"),
                    "Risk Level": opp.get("risk_level")
                })
            df_opp = pd.DataFrame(opp_rows)
            st.dataframe(df_opp, use_container_width=True, hide_index=True)
            st.caption("💡 Switch to 'Recovery Opportunities' in the sidebar to review and execute any of these opportunities.")
        else:
            st.info("No active recovery opportunities found.")

    with col_actions:
        st.markdown("#### ⚡ AI Actions Today")
        st.markdown(
            """
            <div style="background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px; padding: 16px;">
                <div style="display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid #EDF2F7;">
                    <span>🔄 Smart Retries</span>
                    <strong>Not available</strong>
                </div>
                <div style="display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid #EDF2F7;">
                    <span>🔗 Payment Links</span>
                    <strong>Not available</strong>
                </div>
                <div style="display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid #EDF2F7;">
                    <span>📩 Customer Notifications</span>
                    <strong>Not available</strong>
                </div>
                <div style="display: flex; justify-content: space-between; padding: 6px 0;">
                    <span>👤 Reviewer Escalations</span>
                    <strong>Not available</strong>
                </div>
                <hr style="margin: 12px 0 8px 0; border: none; border-top: 1px solid #CBD5E1;" />
                <div style="font-size: 13px; color: #475569;">
                    <strong>Total Yield Today:</strong> Not available
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )
