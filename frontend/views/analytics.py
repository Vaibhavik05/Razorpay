import pandas as pd
import streamlit as st
from frontend.api_client import APIClient


def render_analytics(client: APIClient):
    st.markdown("### Recovery Analytics & Performance")
    st.caption("Backend-derived recovery performance and financial outcomes.")
    try:
        response = client.get_metrics()
        metrics = response.get("data", {}) if response.get("success") else {}
    except Exception as ex:
        st.error(f"Unable to load analytics: {ex}")
        return
    if not metrics:
        st.info("No analytics data is available.")
        return
    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    kpi1.metric("Failed payments", metrics.get("total_failed_payments", 0))
    kpi2.metric("Revenue at risk", f"₹{metrics.get('total_revenue_at_risk', 0):,.2f}")
    kpi3.metric("Recovered revenue", f"₹{metrics.get('recovered_revenue', 0):,.2f}")
    kpi4.metric("Recovery rate", f"{metrics.get('recovery_rate', 0) * 100:.1f}%")
    st.markdown("#### Action performance")
    actions = metrics.get("actions") or []
    if actions:
        action_frame = pd.DataFrame(actions)
        action_frame["recovery_rate"] = action_frame["recovery_rate"] * 100
        st.dataframe(action_frame, use_container_width=True, hide_index=True)
    else:
        st.info("No action performance data is available.")
    st.markdown("#### Additional outcomes")
    st.json({
        "incremental_revenue": metrics.get("incremental_revenue", 0.0),
        "intervention_count": metrics.get("intervention_count", 0),
        "average_recovery_value": metrics.get("average_recovery_value", 0.0),
        "roi": metrics.get("roi", 0.0),
    })
