# RecoverAI — Autonomous Revenue Recovery Engine

**Track 03: AI Revenue Recovery**

RecoverAI detects revenue lost through failed payments, selects appropriate
bounded recovery interventions using deterministic rules + policy guardrails +
bounded Agentic AI, executes them safely, tracks outcomes, and measures
incremental revenue recovered.

## 🏗️ Architecture
Razorpay Webhook
↓
FastAPI (signature verify, schema validate)
↓
PostgreSQL Inbox (deduplicate via UNIQUE constraint)
↓
Transactional Outbox (dual-write protection)
↓
Redis Queue → Celery Workers
↓
Deterministic Engine → Policy Engine → Bounded LangGraph Agent
↓
Razorpay Payment Link / Reminder / Escalate / Stop
↓
Outcome Tracking → Metrics Dashboard

## 🔒 Correctness Principles

- **Financial Safety**: Integer minor units, UTC timestamps, multi-tenant scoping
- **Concurrency Safety**: Optimistic versioning, idempotent actions, atomic transitions
- **AI Safety**: Bounded action enum, structured output, policy override, deterministic fallback

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- Docker Desktop
- Git

### Setup

```bash
cd recoverai
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
python -m alembic upgrade head
