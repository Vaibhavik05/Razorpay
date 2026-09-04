import pandas as pd
import streamlit as st
from frontend.api_client import APIClient


def render_audit(client: APIClient):
    st.markdown("### Audit Trail")
    recovery_id = st.session_state.get("selected_recovery_id")
    if not recovery_id:
        st.info("Select an opportunity to inspect its audit history.")
        return
    try:
        response = client.get_audit(recovery_id)
        events = response.get("data", {}).get("events", []) if response.get("success") else []
    except Exception as ex:
        st.error(f"Unable to load audit history: {ex}")
        return
    if events:
        st.dataframe(pd.DataFrame(events), use_container_width=True, hide_index=True)
    else:
        st.info("No audit events recorded for this opportunity.")
