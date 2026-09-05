import streamlit as st
import pandas as pd
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dashboard.api_client import get_cases, get_case_detail, get_merchants

st.set_page_config(page_title="RecoverAI - Cases", layout="wide")
st.title("Recovery Cases")


def humanize(value: str) -> str:
    return value.replace("_", " ").title()


try:
    merchants = get_merchants()
except Exception as e:
    st.error(f"Failed to reach backend: {e}")
    st.stop()

if not merchants:
    st.warning("No merchants found. Run once: `python scripts/seed_demo_data.py`")
    st.stop()

merchant_names = [m["name"] for m in merchants]
default_index = (
    merchant_names.index("Demo Merchant") if "Demo Merchant" in merchant_names else 0
)
selected_name = st.selectbox("Select Merchant", merchant_names, index=default_index)
merchant_id = next(m for m in merchants if m["name"] == selected_name)["id"]

st.divider()

status_filter = st.selectbox(
    "Filter by Status",
    ["All", "ELIGIBLE", "ANALYSING", "ACTION_SELECTED", "ACTION_SCHEDULED",
     "WAITING", "RECOVERED", "STOPPED", "ESCALATED"],
)

try:
    status_param = None if status_filter == "All" else status_filter
    result = get_cases(merchant_id, limit=50, offset=0, status=status_param)

    cases = result["items"]
    total = result["total_count"]

    st.markdown(f"Showing **{len(cases)}** of **{total:,}** cases")

    if not cases:
        st.info("No cases found for this filter.")
        st.stop()

    df = pd.DataFrame(cases)
    df["amount_inr"] = df["amount_minor"] / 100
    df["created_display"] = pd.to_datetime(df["created_at"]).dt.strftime("%Y-%m-%d %H:%M")
    df["status_display"] = df["status"].map(humanize)

    display_df = df[["id", "status_display", "failure_category", "amount_inr", "created_display"]].copy()
    display_df.columns = ["Case ID", "Status", "Failure Category", "Amount (INR)", "Created At"]

    st.dataframe(display_df, use_container_width=True, hide_index=True)

    st.divider()

    st.subheader("Case Detail and AI Audit Trail")

    case_ids = [c["id"] for c in cases]
    selected_case_id = st.selectbox("Select a case to inspect", case_ids)

    if selected_case_id:
        detail = get_case_detail(merchant_id, selected_case_id)

        case_info = detail["case"]
        actions = detail["actions"]
        audit_trail = detail["audit_trail"]

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Status", humanize(case_info["status"]))
        col2.metric("Amount", f"₹{case_info['amount_minor'] / 100:,.2f}")
        col3.metric("Failure", case_info.get("failure_category") or "N/A")
        col4.metric("Actions", len(actions))

        st.divider()

        st.subheader("Recovery Actions")
        if actions:
            actions_df = pd.DataFrame(actions)
            actions_df["created_display"] = pd.to_datetime(actions_df["created_at"]).dt.strftime("%Y-%m-%d %H:%M")
            actions_df["provider_reference"] = actions_df["provider_reference"].fillna("-")

            actions_df = actions_df[
                ["action_type", "status", "attempt_number", "provider_reference", "created_display"]
            ].copy()
            actions_df.columns = ["Action", "Status", "Attempt", "Provider Reference", "Created At"]
            actions_df["Action"] = actions_df["Action"].map(humanize)
            actions_df["Status"] = actions_df["Status"].map(humanize)

            st.dataframe(actions_df, use_container_width=True, hide_index=True)
        else:
            st.info("No actions taken yet.")

        st.divider()

        st.subheader("Decision Audit Trail")
        st.markdown(
            "This timeline shows exactly why each decision was made: the engine "
            "recommendation, the policy verdict, and the agent source. This is the "
            "explainability layer a support agent or auditor would use."
        )

        for entry in audit_trail:
            title = f"{entry['event_type']} | {entry['actor']} | {entry['created_at'][:19]}"
            with st.expander(title, expanded=False):
                st.json(entry["payload"])

except Exception as e:
    st.error(f"Failed to load cases: {e}")