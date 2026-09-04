import streamlit as st

def render_kpi_card(title: str, value: str, subtext: str = "", trend: str = "", is_positive: bool = True):
    """
    Renders a clean, high-density fintech KPI card (09_UI_UX_DESIGN_SPEC.md Section 9-10)
    No huge gradients, subtle borders, crisp typography.
    """
    trend_color = "#10B981" if is_positive else "#EF4444"
    trend_html = f"<span style='color: {trend_color}; font-weight: 600; font-size: 12px;'>{trend}</span>" if trend else ""
    
    st.markdown(
        f"""
        <div style="
            background: #FFFFFF;
            border: 1px solid #E2E8F0;
            border-radius: 8px;
            padding: 16px 20px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.04);
            margin-bottom: 12px;
        ">
            <div style="font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; color: #64748B;">
                {title}
            </div>
            <div style="font-size: 28px; font-weight: 800; color: #0F172A; margin: 4px 0 2px 0; letter-spacing: -0.5px;">
                {value}
            </div>
            <div style="font-size: 12px; color: #64748B; display: flex; align-items: center; gap: 6px;">
                {trend_html}
                <span>{subtext}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )
