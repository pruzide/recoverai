import streamlit as st

st.set_page_config(
    page_title="RecoverAI Dashboard",
    layout="wide",
)

st.title("RecoverAI - Autonomous Revenue Recovery Engine")

st.markdown("**Track 03: AI Revenue Recovery**")

st.markdown(
    "RecoverAI detects revenue lost through failed payments, selects bounded "
    "recovery interventions using a deterministic engine, policy guardrails and "
    "a bounded Agentic AI layer, executes them safely, and measures incremental "
    "revenue recovered."
)

st.markdown("Use the sidebar to explore **Metrics**, **Cases** and **Simulation**.")

st.divider()

st.subheader("Recovery Pipeline")

st.markdown(
    "The system implements the full required pipeline. The LLM never owns "
    "financial correctness; deterministic software and policy do."
)

pipeline = ["Detect", "Understand", "Decide", "Policy Check", "Act", "Observe", "Measure"]

cols = st.columns(len(pipeline) * 2 - 1)
for i, step in enumerate(pipeline):
    cols[i * 2].markdown(f"**{step}**")
    if i < len(pipeline) - 1:
        cols[i * 2 + 1].markdown("--→")

st.divider()

st.subheader("System Architecture")

ARCH_DIAGRAM = """Razorpay Webhook (test mode)
        |  signature verify + schema validate (FastAPI)
        v
PostgreSQL webhook inbox   (UNIQUE provider_event_id = dedup)
        |  single transaction: webhook + payment + case + outbox
        v
Transactional outbox       (dual-write protection)
        |  dispatcher polls PENDING / due events
        v
Redis queue -> Celery workers (acks_late, bounded retries, jitter)
        |
        v
Deterministic engine -> merchant policy -> bounded LangGraph agent
        |  structured output, enum actions only, final policy check
        v
Executor: payment link / reminder / wait / stop / escalate
        |  idempotency keys, atomic claims, stale-job checks
        v
Outcome webhooks -> state machine -> audit trail -> metrics"""

st.code(ARCH_DIAGRAM, language="text")

st.divider()

st.subheader("Correctness Principles")

col1, col2, col3 = st.columns(3)

with col1:
    st.markdown(
        """
**Financial Safety**
- Integer minor units (no floats)
- UTC timestamps
- Multi-tenant scoping (merchant_id everywhere)
- Database constraints as final boundary
"""
    )

with col2:
    st.markdown(
        """
**Concurrency Safety**
- Optimistic versioning on recovery cases
- Idempotent action keys
- Atomic state transitions (rowcount checks)
- Stale-job detection before side effects
"""
    )

with col3:
    st.markdown(
        """
**AI Safety**
- Bounded action enum only
- Structured output validation
- Policy has override authority
- Deterministic fallback on any LLM failure
"""
    )

st.divider()

st.caption(
    "All benchmark numbers shown in the Simulation tab are SIMULATED BENCHMARK "
    "data and are never presented as production revenue."
)