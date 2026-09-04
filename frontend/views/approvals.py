import streamlit as st
from frontend.api_client import APIClient


def render_approvals(client: APIClient):
    st.markdown("### Human-in-the-Loop Review Portal")
    st.caption("Review decisions that backend guardrails have marked for approval.")
    recovery_id = st.session_state.get("selected_recovery_id")
    if not recovery_id:
        st.info("Select an approval-required opportunity to review it here.")
        return
    try:
        response = client.get_recovery_status(recovery_id)
        status_data = response.get("data", {}) if response.get("success") else {}
    except Exception as ex:
        st.error(f"Unable to load approval status: {ex}")
        return
    if not status_data:
        st.info("No approval data is available for this opportunity.")
        return
    st.markdown(f"**Recovery:** {status_data.get('recovery_id')}  |  **Transaction:** {status_data.get('transaction_id')}")
    st.markdown(f"**Lifecycle status:** `{status_data.get('status', 'UNKNOWN')}`")
    if status_data.get("status") != "APPROVAL_REQUIRED":
        st.info("This recovery is not awaiting approval.")
        return
    comment = st.text_input("Reviewer comment", key=f"approval_comment_{recovery_id}")
    col_approve, col_reject = st.columns(2)
    with col_approve:
        if st.button("Approve recovery", type="primary", use_container_width=True):
            result = client.approve_recovery(recovery_id, reviewer_id="USER_REVIEWER_1", comment=comment)
            if result.get("success"):
                st.success("Recovery approved and recorded.")
            else:
                st.error(result.get("error", {}).get("message", "Approval failed."))
    with col_reject:
        if st.button("Reject recovery", use_container_width=True):
            result = client.reject_recovery(recovery_id, reviewer_id="USER_REVIEWER_1", reason=comment or "Reviewer rejected the recovery decision.")
            if result.get("success"):
                st.info("Recovery rejection recorded.")
            else:
                st.error(result.get("error", {}).get("message", "Rejection failed."))
