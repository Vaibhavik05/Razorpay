import streamlit as st
from frontend.api_client import APIClient


def render_experiments(client: APIClient):
    st.markdown("### Strategy Experiments")
    st.caption("Experiment reporting is not exposed by the current backend contract.")
    st.info("No experiment results are available.")
