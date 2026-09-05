import streamlit as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dashboard.api_client import get_merchant_metrics, get_merchants

st.set_page_config(page_title="RecoverAI - Metrics", layout="wide")
st.title("Recovery Metrics")

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

try:
    metrics = get_merchant_metrics(merchant_id)

    col1, col2, col3, col4 = st.columns(4)

    col1.metric(
        "Revenue at Risk",
        f"₹{metrics['total_amount_at_risk_minor'] / 100:,.2f}",
    )
    col2.metric(
        "Recovered Revenue",
        f"₹{metrics['recovered_amount_minor'] / 100:,.2f}",
        delta=f"{metrics['recovery_rate_percent']:.1f}% recovery rate",
    )
    col3.metric("Total Cases", f"{metrics['total_cases']:,}")
    col4.metric("Recovered Cases", f"{metrics['recovered_cases']:,}")

    col5, col6, col7, col8 = st.columns(4)

    col5.metric("Recovery Actions", f"{metrics['total_actions']:,}")
    col6.metric(
        "Avg Time to Recovery",
        f"{metrics['avg_time_to_recovery_hours']:.1f} hrs",
    )
    col7.metric("Stopped Cases", f"{metrics['stopped_cases']:,}")
    col8.metric("Escalated Cases", f"{metrics['escalated_cases']:,}")

    st.divider()

    st.info(
        "Incremental Recovered Revenue (RecoverAI vs baseline) is reported in the "
        "Simulation tab and is based on a labelled synthetic benchmark."
    )

except Exception as e:
    st.error(f"Failed to load metrics: {e}")