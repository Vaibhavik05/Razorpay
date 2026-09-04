import streamlit as st
import uuid
import pandas as pd
from frontend.api_client import APIClient

def render_detail(client: APIClient):
    st.markdown("### 🔍 Payment Opportunity & Decision Engine")
    
    rec_id = st.session_state.get("selected_recovery_id", "REC789")
    tx_id = st.session_state.get("selected_tx_id", "TXN123")
    amount = st.session_state.get("selected_amount")
    failure = st.session_state.get("selected_failure", "TIMEOUT")
    rec_action = st.session_state.get("selected_action")

    st.caption(f"Inspecting Opportunity **{rec_id}** for Transaction **{tx_id}**")

    # Fetch live recommendation from backend API to ensure pure backend-driven calculations
    try:
        recommend_payload = {
            "transaction_id": tx_id,
            "merchant_id": "MERCHANT001",
            "customer_id": "CUST456",
            "amount": amount,
            "failure_reason": failure,
            "customer_type": "RETURNING"
        }
        res = client.recommend_recovery(recommend_payload)
        rec_data = res.get("data", {}) if res.get("success") else {}
    except Exception as ex:
        st.error(f"Failed to fetch live recommendation from API: {ex}")
        rec_data = {}

    if not rec_data:
        st.info("No decision data is available for this opportunity.")
        return

    recommended_action = rec_data.get("recommended_action", rec_action or "NO_ACTION")
    rec_prob = rec_data.get("recovery_probability", 0.0)
    inc_rev = rec_data.get("expected_incremental_revenue", 0.0)
    net_val = rec_data.get("expected_net_value", 0.0)
    confidence = rec_data.get("confidence", 0.0)
    risk_lvl = rec_data.get("risk_level", "UNKNOWN")
    requires_approval = rec_data.get("requires_approval", False)
    reason = rec_data.get("reason", "No explanation available.")
    amount = amount if amount is not None else 0.0

    # 1. Top context row: Payment Info + Customer Info (09_UI_UX_DESIGN_SPEC.md Section 15)
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(
            f"""
            <div style="background:#F8FAFC;border:1px solid #E2E8F0;border-radius:8px;padding:14px;">
                <div style="font-size:11px;font-weight:700;color:#64748B;text-transform:uppercase;">Payment Context</div>
                <div style="font-size:18px;font-weight:800;color:#0F172A;margin:4px 0;">₹{amount:,.2f}</div>
                <div style="font-size:12px;color:#475569;">
                    <strong>ID:</strong> {tx_id}<br/>
                    <strong>Method:</strong> UPI / CARD<br/>
                    <strong>Failure:</strong> <span style="color:#EF4444;font-weight:600;">{failure}</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )
    with c2:
        st.markdown(
            f"""
            <div style="background:#F8FAFC;border:1px solid #E2E8F0;border-radius:8px;padding:14px;">
                <div style="font-size:11px;font-weight:700;color:#64748B;text-transform:uppercase;">Customer Context</div>
                <div style="font-size:18px;font-weight:800;color:#0F172A;margin:4px 0;">CUST456</div>
                <div style="font-size:12px;color:#475569;">
                    <strong>Segment:</strong> Returning / Loyal<br/>
                    <strong>Historical context:</strong> Available to backend decisioning<br/>
                    <strong>Decision source:</strong> Recovery API
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )
    with c3:
        st.markdown(
            f"""
            <div style="background:#F8FAFC;border:1px solid #E2E8F0;border-radius:8px;padding:14px;">
                <div style="font-size:11px;font-weight:700;color:#64748B;text-transform:uppercase;">ML Model Inference</div>
                <div style="font-size:18px;font-weight:800;color:#0F172A;margin:4px 0;">{rec_prob:.0%} Recovery Prob</div>
                <div style="font-size:12px;color:#475569;">
                    <strong>Confidence:</strong> {confidence:.0%}<br/>
                    <strong>Algorithm:</strong> XGBoost v1.0<br/>
                    <strong>Risk Classification:</strong> <span style="font-weight:700;color:#2563EB;">{risk_lvl}</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )

    st.markdown("<br/>", unsafe_allow_html=True)

    # 2. Action Comparison Matrix (09_UI_UX_DESIGN_SPEC.md Section 16)
    st.markdown("#### ⚖️ Action Comparison Matrix")
    st.caption("Backend evaluates all candidate actions using recovery probability, uplift, cost, and risk.")
    
    comparisons = rec_data.get("action_comparisons", [])
    if comparisons:
        st.dataframe(pd.DataFrame(comparisons), use_container_width=True, hide_index=True)
    else:
        st.info("No action comparison data is available.")

    # 3. AI Recommendation & Guardrail Checks (Section 17 & 19)
    col_ai, col_guard = st.columns([5, 4])
    
    with col_ai:
        st.markdown(
            f"""
            <div style="background:#EFF6FF;border:1px solid #BFDBFE;border-radius:8px;padding:16px;">
                <div style="font-size:12px;font-weight:700;color:#1D4ED8;text-transform:uppercase;">AI Recommendation Card</div>
                <div style="font-size:22px;font-weight:800;color:#1E3A8A;margin:6px 0;">{recommended_action.replace('_', ' ')}</div>
                <div style="font-size:14px;color:#1E40AF;margin-bottom:8px;">
                    <strong>Expected Incremental Revenue:</strong> <span style="font-size:16px;font-weight:700;color:#15803D;">+₹{inc_rev:,.2f}</span>
                </div>
                <div style="font-size:13px;color:#1E3A8A;background:#FFFFFF;border:1px solid #DBEAFE;border-radius:6px;padding:10px;">
                    <strong>Why?</strong><br/>
                    {reason}
                </div>
                <div style="font-size:12px;color:#3B82F6;margin-top:8px;">
                    Confidence: <strong>{confidence:.0%}</strong> &nbsp;|&nbsp; Requires Human Approval: <strong>{requires_approval}</strong><br/>
                    Decision state: <strong>{rec_data.get('decision_state', 'UNKNOWN')}</strong>
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )

    with col_guard:
        st.markdown(
            """
            <div style="background:#F0FDF4;border:1px solid #BBF7D0;border-radius:8px;padding:16px;">
                <div style="font-size:12px;font-weight:700;color:#15803D;text-transform:uppercase;">Deterministic Guardrail Engine</div>
                <div style="font-size:13px;color:#166534;margin-top:8px;line-height:1.8;">
                    <strong>Guardrail Status:</strong> {rec_data.get('guardrail_status', 'UNKNOWN')}<br/>
                    <strong>Guardrail Reason:</strong> {rec_data.get('guardrail_reason', 'No reason provided.')}<br/>
                    <strong>Approval Required:</strong> {requires_approval}
                </div>
                <hr style="margin:10px 0;border-top:1px solid #DCFCE7;"/>
                <div style="font-size:12px;font-weight:700;color:#15803D;">
                    Status: <span style="background:#DCFCE7;padding:2px 6px;border-radius:4px;">{rec_data.get('guardrail_status', 'UNKNOWN')}</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )

    explanation = rec_data.get("llm_explanation")
    if explanation:
        st.info(f"Explanation ({explanation.get('source', 'fallback')}): {explanation.get('text', 'Unavailable')}")

    st.markdown("<br/>", unsafe_allow_html=True)

    # 4. Explicit Execution Section (09_UI_UX_DESIGN_SPEC.md Section 21-23)
    st.markdown("#### 🚀 Execute Recovery Action")
    st.write(f"Controlled execution status for **{recommended_action}** on payment **{tx_id}**.")

    idempotency_key = f"IDEMP_{rec_id}_{tx_id}"
    
    exec_col1, exec_col2 = st.columns([3, 2])
    with exec_col1:
        if recommended_action != "NO_ACTION" and st.button(f"⚡ Execute {recommended_action.replace('_', ' ')} for {tx_id}", type="primary", use_container_width=True):
            with st.spinner("Executing through Razorpay Adapter & Logging Audit Trail..."):
                exec_payload = {
                    "recovery_id": rec_id,
                    "transaction_id": tx_id,
                    "action": recommended_action,
                    "merchant_id": "MERCHANT001"
                }
                exec_res = client.execute_recovery(exec_payload, idempotency_key=idempotency_key)
                
                if exec_res.get("success"):
                    st.session_state[f"executed_{rec_id}"] = exec_res.get("data")
                    st.success(f"Action executed successfully! Status: SUCCESS")
                elif exec_res.get("data", {}).get("execution_status") == "APPROVAL_REQUIRED":
                    st.warning("⚠️ Action exceeds automatic execution threshold. Sent to Reviewer for approval.")
                else:
                    st.error(f"Execution blocked: {exec_res.get('message')}")

    # Display execution outcome if executed
    exec_info = st.session_state.get(f"executed_{rec_id}")
    if exec_info:
        st.markdown(
            f"""
            <div style="background:#F8FAFC;border:1px solid #10B981;border-radius:8px;padding:16px;margin-top:12px;">
                <div style="font-size:14px;font-weight:700;color:#0F172A;">✓ Recovery Action Completed</div>
                <div style="font-size:13px;color:#334155;margin-top:6px;">
                    <strong>Action:</strong> {exec_info.get('action')}<br/>
                    <strong>Payment Link ID:</strong> <code>{exec_info.get('payment_link_id', 'Not applicable')}</code><br/>
                    <strong>Link URL:</strong> {exec_info.get('payment_link_url', 'Not applicable')}<br/>
                    <strong>Status:</strong> <span style="color:#10B981;font-weight:700;">{exec_info.get('execution_status', 'SUCCESS')}</span><br/>
                    <strong>Timestamp:</strong> {exec_info.get('executed_at')}
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )

        st.markdown("##### 🔔 Simulate Customer Payment Completion (Razorpay Webhook)")
        if st.button("Simulate Razorpay Webhook (Payment Captured)"):
            with st.spinner("Emulating incoming Razorpay webhook..."):
                hook_res = client.send_webhook(
                    event_name="payment.captured",
                    payment_id=tx_id,
                    amount_inr=amount
                )
                if hook_res.get("success"):
                    st.balloons()
                    st.success(f"Webhook verified & processed! ₹{amount:,.2f} recorded as Recovered Revenue.")
                else:
                    st.error("Webhook processing failed.")

    st.markdown("#### Audit History")
    try:
        audit_response = client.get_audit(rec_id)
        audit_events = audit_response.get("data", {}).get("events", []) if audit_response.get("success") else []
        if audit_events:
            st.dataframe(pd.DataFrame(audit_events), use_container_width=True, hide_index=True)
        else:
            st.info("No audit events recorded for this opportunity.")
    except Exception as ex:
        st.info(f"Audit history unavailable: {ex}")
