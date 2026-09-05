import streamlit as st
import json
from pathlib import Path

st.set_page_config(page_title="RecoverAI - Simulation", layout="wide")
st.title("Simulated Business Experiment")

st.warning(
    "**SIMULATED BENCHMARK - NOT PRODUCTION DATA**\n\n"
    "These results use synthetic payment failures and simulated recovery "
    "probabilities. They demonstrate the architecture and the measurement "
    "framework. Real outcome data is required for production validation."
)

st.divider()

SIMULATION_RESULTS_PATH = Path(__file__).resolve().parents[2] / "simulation_results.json"

if SIMULATION_RESULTS_PATH.exists():
    with open(SIMULATION_RESULTS_PATH) as f:
        results = json.load(f)

    baseline = results.get("baseline", {})
    recoverai = results.get("recoverai", {})
    incremental = results.get("incremental_recovered_revenue_minor", 0)

    st.subheader("Strategy Comparison")

    col1, col2, col3 = st.columns(3)

    col1.metric("Baseline Recovery Rate", f"{baseline.get('recovery_rate', 0):.1%}")
    col2.metric(
        "RecoverAI Recovery Rate",
        f"{recoverai.get('recovery_rate', 0):.1%}",
        delta=f"+{(recoverai.get('recovery_rate', 0) - baseline.get('recovery_rate', 0)) * 100:.1f} pp",
    )
    col3.metric("Incremental Recovered Revenue", f"₹{incremental / 100:,.2f}")

    st.divider()

    st.subheader("Detailed Metrics")

    st.markdown(
        "| Metric | Baseline | RecoverAI |\n"
        "|---|---:|---:|\n"
        f"| Total Cases | {baseline.get('total_cases', 0):,} | {recoverai.get('total_cases', 0):,} |\n"
        f"| Recovered Cases | {baseline.get('recovered_cases', 0):,} | {recoverai.get('recovered_cases', 0):,} |\n"
        f"| Recovered Amount | ₹{baseline.get('recovered_amount_minor', 0) / 100:,.2f} | ₹{recoverai.get('recovered_amount_minor', 0) / 100:,.2f} |\n"
        f"| Customer Contacts | {baseline.get('total_contacts', 0):,} | {recoverai.get('total_contacts', 0):,} |\n"
        f"| Contacts per Case | {baseline.get('total_contacts', 0) / max(baseline.get('total_cases', 1), 1):.2f} | {recoverai.get('total_contacts', 0) / max(recoverai.get('total_cases', 1), 1):.2f} |\n"
        f"| Avg Time to Recovery (hrs) | {baseline.get('avg_time_to_recovery_hours', 0):.1f} | {recoverai.get('avg_time_to_recovery_hours', 0):.1f} |"
    )

    st.divider()

    st.subheader("Action Distribution")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Baseline Actions**")
        for action, count in sorted(baseline.get("action_counts", {}).items()):
            st.markdown(f"- {action}: {count:,}")

    with col2:
        st.markdown("**RecoverAI Actions**")
        for action, count in sorted(recoverai.get("action_counts", {}).items()):
            st.markdown(f"- {action}: {count:,}")

else:
    st.info(
        "No simulation results found. Run:\n\n"
        "`python scripts/run_simulation.py --size 10000 --seed 42`"
    )

st.divider()

st.subheader("Why Simulation?")

st.markdown(
    "We do not have genuine historical merchant recovery data. Using synthetic "
    "labels to control financial actions would create unjustified confidence. "
    "The production learning loop is:\n\n"
    "Rules + Agent + Policy -> action -> outcome -> record (context, action, outcome) "
    "-> real merchant recovery history -> ML training. "
    "The optional ML layer (post-MVP) would only rank permitted actions, never override policy."
)