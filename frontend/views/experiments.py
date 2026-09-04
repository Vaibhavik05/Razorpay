import streamlit as st
from frontend.api_client import APIClient

def render_experiments(client: APIClient):
    st.markdown("### 🧪 Strategy Experiments & A/B Testing")
    st.caption("Empirical testing of automated recovery workflows against control baselines (09_UI_UX_DESIGN_SPEC.md Section 32).")

    st.markdown(
        """
        <div style="background:#F8FAFC;border:1px solid #CBD5E1;border-radius:8px;padding:20px;margin-bottom:20px;">
            <div style="display:flex;justify-content:space-between;align-items:center;">
                <div>
                    <span style="font-size:12px;font-weight:700;color:#64748B;text-transform:uppercase;">Active Experiment #EXP-2026-01</span>
                    <div style="font-size:20px;font-weight:800;color:#0F172A;margin-top:2px;">Smart Retry vs Instant Payment Link</div>
                </div>
                <span style="background:#DCFCE7;color:#166534;font-size:12px;font-weight:700;padding:4px 10px;border-radius:20px;">RUNNING</span>
            </div>
            <div style="font-size:13px;color:#475569;margin-top:10px;">
                <strong>Segment:</strong> Returning Customers with Network/Timeout Failure &nbsp;|&nbsp;
                <strong>Sample Size:</strong> 2,400 transactions
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Control (Retry)", "42.0%")
    with c2:
        st.metric("Treatment (Payment Link)", "61.0%")
    with c3:
        st.metric("Incremental Lift", "+19.0 pts", delta="+19.0 pts")
    with c4:
        st.metric("Incremental Revenue", "₹82,000", delta="+₹82K")

    st.markdown("#### ⚙️ Configure New Experiment")
    with st.expander("Create New Strategy Experiment"):
        st.selectbox("Target Customer Segment", ["Returning Customers", "High Value Customers", "New Customers", "All Segments"])
        st.selectbox("Control Action", ["RETRY", "NO_ACTION"])
        st.selectbox("Treatment Action", ["PAYMENT_LINK", "CUSTOMER_NOTIFICATION"])
        st.slider("Traffic Split (% Treatment)", min_value=10, max_value=90, value=50)
        if st.button("Deploy Experiment"):
            st.success("New experiment deployed to production recovery gateway!")
