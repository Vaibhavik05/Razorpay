import streamlit as st

def render_top_nav(merchant_name: str = "Acme Store", environment: str = "TEST", status: str = "Healthy"):
    """
    Renders top navigation bar conforming to 09_UI_UX_DESIGN_SPEC.md Section 7
    High information density, clean typography, system status indicator.
    """
    col1, col2, col3 = st.columns([4, 2, 2])
    with col1:
        st.markdown(
            f"""
            <div style="display: flex; align-items: center; gap: 12px; padding: 4px 0;">
                <span style="font-size: 24px; font-weight: 800; letter-spacing: -0.5px; color: #0F172A;">
                    ⚡ NexaRecover <span style="color: #2563EB;">AI</span>
                </span>
                <span style="background-color: #F1F5F9; color: #475569; font-size: 11px; font-weight: 600; padding: 2px 8px; border-radius: 4px; border: 1px solid #E2E8F0;">
                    REVENUE INTELLIGENCE
                </span>
            </div>
            """,
            unsafe_allow_html=True
        )
    with col2:
        st.markdown(
            f"""
            <div style="text-align: right; padding: 6px 0; font-size: 13px; color: #334155;">
                <strong>Merchant:</strong> {merchant_name} &nbsp;|&nbsp; 
                <span style="background-color: #FEF3C7; color: #92400E; font-size: 11px; padding: 2px 6px; border-radius: 4px; font-weight: bold;">{environment}</span>
            </div>
            """,
            unsafe_allow_html=True
        )
    with col3:
        status_color = "#10B981" if status.lower() == "healthy" else "#F59E0B"
        st.markdown(
            f"""
            <div style="text-align: right; padding: 6px 0; font-size: 13px; color: #334155;">
                <span style="display: inline-block; width: 8px; height: 8px; border-radius: 50%; background-color: {status_color}; margin-right: 6px;"></span>
                <strong>Status:</strong> {status}
            </div>
            """,
            unsafe_allow_html=True
        )
    st.markdown("<hr style='margin: 8px 0 20px 0; border: none; border-top: 1px solid #E2E8F0;' />", unsafe_allow_html=True)
