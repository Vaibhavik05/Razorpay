import streamlit as st
import pandas as pd
import plotly.express as px
from frontend.api_client import APIClient

def render_analytics(client: APIClient):
    st.markdown("### 📈 Recovery Analytics & Performance")
    st.caption("Deep-dive breakdowns across recovery channels, failure roots, and customer profiles.")

    # 1. Action Performance Breakdown (09_UI_UX_DESIGN_SPEC.md Section 25)
    st.markdown("#### ⚡ Channel & Action Performance")
    action_data = [
        {"Channel": "Payment Link", "Recovery Rate": "72%", "Incremental Revenue": "₹4.2L", "ROI": "1,840%"},
        {"Channel": "Smart Retry", "Recovery Rate": "54%", "Incremental Revenue": "₹2.1L", "ROI": "1,120%"},
        {"Channel": "Customer Notification", "Recovery Rate": "61%", "Incremental Revenue": "₹1.7L", "ROI": "740%"},
        {"Channel": "Human Escalation", "Recovery Rate": "80%", "Incremental Revenue": "₹0.9L", "ROI": "450%"}
    ]
    st.table(action_data)

    c1, c2 = st.columns(2)
    with c1:
        # Failure Reason Analysis (Section 26)
        st.markdown("#### 🔍 Recovery by Failure Reason")
        failure_df = pd.DataFrame([
            {"Failure Reason": "Timeout", "Recovery Rate": 72},
            {"Failure Reason": "Network Error", "Recovery Rate": 68},
            {"Failure Reason": "Bank Decline", "Recovery Rate": 41},
            {"Failure Reason": "Insufficient Funds", "Recovery Rate": 29},
            {"Failure Reason": "Unknown", "Recovery Rate": 21}
        ])
        fig_fail = px.bar(
            failure_df,
            x="Failure Reason",
            y="Recovery Rate",
            text="Recovery Rate",
            color="Recovery Rate",
            color_continuous_scale="Blues"
        )
        fig_fail.update_layout(height=280, margin=dict(l=10, r=10, t=20, b=10), yaxis_ticksuffix="%")
        st.plotly_chart(fig_fail, use_container_width=True)

    with c2:
        # Customer Segment Analysis (Section 27)
        st.markdown("#### 👥 Recovery by Customer Segment")
        segment_df = pd.DataFrame([
            {"Segment": "High Value", "Recovery Rate": 82},
            {"Segment": "Returning", "Recovery Rate": 76},
            {"Segment": "New", "Recovery Rate": 41},
            {"Segment": "Low Frequency", "Recovery Rate": 35}
        ])
        fig_seg = px.bar(
            segment_df,
            x="Segment",
            y="Recovery Rate",
            text="Recovery Rate",
            color="Recovery Rate",
            color_continuous_scale="Greens"
        )
        fig_seg.update_layout(height=280, margin=dict(l=10, r=10, t=20, b=10), yaxis_ticksuffix="%")
        st.plotly_chart(fig_seg, use_container_width=True)
