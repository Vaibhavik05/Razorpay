import streamlit as st
from frontend.api_client import APIClient

def render_approvals(client: APIClient):
    st.markdown("### 🛡️ Human-in-the-Loop Review Portal")
    st.caption("Review queue for high-value transactions and policy-flagged recovery actions.")

    # High-value demo opportunity requiring approval
    rec_id = "REC_PAY_10293"
    tx_id = "PAY_10293"
    amount = 25000.0

    st.markdown(
        f"""
        <div style="background:#FFFBEB;border:1px solid #FDE68A;border-radius:8px;padding:16px;margin-bottom:16px;">
            <div style="font-size:12px;font-weight:700;color:#B45309;text-transform:uppercase;">APPROVAL REQUIRED</div>
            <div style="font-size:20px;font-weight:800;color:#78350F;margin:4px 0;">Transaction {tx_id} — ₹{amount:,.2f}</div>
            <div style="font-size:13px;color:#92400E;">
                <strong>Recommended Action:</strong> HUMAN_ESCALATION<br/>
                <strong>Trigger:</strong> High-value transaction exceeds automated auto-recovery policy threshold (₹10,000).<br/>
                <strong>Customer:</strong> CUST456 (Loyal Segment, 83% Success Rate)<br/>
                <strong>Failure Reason:</strong> TIMEOUT
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    comment = st.text_input("Reviewer Comment / Rationale", value="Approved after validating transaction validity with merchant policy.")

    c1, c2 = st.columns(2)
    with c1:
        if st.button("✅ Approve Recovery Action", type="primary", use_container_width=True):
            # Use reviewer token client
            reviewer_client = APIClient(token="reviewer_token")
            res = reviewer_client.approve_recovery(rec_id, reviewer_id="USER_REVIEWER_1", comment=comment)
            if res.get("success"):
                st.success(f"Recovery {rec_id} APPROVED by USER_REVIEWER_1! Audit log recorded.")
            else:
                st.error(f"Approval failed: {res.get('error', {}).get('message')}")

    with c2:
        if st.button("❌ Reject Action", use_container_width=True):
            reviewer_client = APIClient(token="reviewer_token")
            res = reviewer_client.reject_recovery(rec_id, reviewer_id="USER_REVIEWER_1", reason="Transaction requires manual merchant confirmation.")
            if res.get("success"):
                st.info(f"Recovery {rec_id} REJECTED. State updated to REJECTED.")
            else:
                st.error(f"Rejection failed: {res.get('error', {}).get('message')}")
