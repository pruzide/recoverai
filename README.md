# RecoverAI

A distributed, fault-tolerant **revenue recovery engine** for failed payment transactions.

RecoverAI replaces naive retry loops with a **context-aware, policy-guarded architecture**. It is designed for financial correctness, guaranteeing **effectively-once execution**, preventing stale side effects, and ensuring that AI-driven decisions never bypass deterministic business guardrails.

Financial correctness cannot depend on probabilistic models.

In RecoverAI, the **Agentic AI is strictly a strategy selector**. It suggests interventions; deterministic software and policy guardrails own execution, state transitions, and financial invariants.

> **AI failure degrades optimization quality. It never compromises revenue recovery or financial correctness.**

---

## Architecture & Data Flow

```text
[ Razorpay Webhooks ]
        │
        ▼
[ FastAPI Ingestion ]
        │
        ├── HMAC Verification
        ├── Schema Validation
        │
        ▼
[ Webhook Inbox ]
        │
        └── Deduplication
        │
        ▼
[ PostgreSQL Transaction ]
        │
        └── Atomic Commit:
            ├── Payment
            ├── Recovery Case
            └── Outbox Event
        │
        ▼
[ Outbox Dispatcher ]
        │
        └── Polls PENDING / Due Events
        │
        ▼
[ Redis Queue ]
        │
        ▼
[ Celery Workers ]
        │
        ▼
[ Deterministic Engine ]
        │
        ├── Context Evaluation
        ├── Business Rules
        │
        └───────────────▶ [ Bounded LangGraph Agent ]
        │                          │
        │                          ▼
        │                 [ Structured Output ]
        │                          │
        ▼                          ▼
[ Policy Guardrails ] ◀──── Final Authority
        │
        ▼
[ Action Executor ]
        │
        ├── Atomic Claim
        ├── Final State Check
        │
        ▼
[ Razorpay API ]
        │
        └── Payment Links
        │
        ▼
[ Observability ]
        │
        ├── SQL Aggregation
        ├── Audit Trails
        │
        ▼
[ Streamlit Dashboard ]
```

---

## Distributed Systems Invariants

RecoverAI prioritizes **correctness over feature volume**.

The system implements production-grade distributed systems patterns to solve common reliability problems in fintech systems.

### 1. The Dual-Write Problem

**Challenge**

Committing a database transaction and subsequently publishing an event to a message queue creates a failure window.

For example:

```text
Database Commit
      │
      ▼
 Application Crash
      │
      X
Queue Publish Never Happens
```

The business state is committed, but the asynchronous work is permanently lost.

**Resolution — Transactional Outbox Pattern**

Business state and work intent are written inside the **same PostgreSQL transaction**.

```text
BEGIN TRANSACTION

INSERT payment
INSERT recovery_case
INSERT outbox_event

COMMIT
```

A separate **Outbox Dispatcher** continuously polls pending outbox events and publishes them to Redis.

If Redis or the broker is unavailable, the event remains in PostgreSQL and can be retried later.

> Work may be delayed, but it is never silently lost.

---

### 2. Concurrent Worker Collisions

**Challenge**

Redis and Celery provide **at-least-once task delivery**.

Multiple workers may therefore attempt to process the same recovery action concurrently.

Without protection, this could create:

- Duplicate payment links
- Duplicate customer reminders
- Conflicting state transitions
- Multiple external API calls

**Resolution — Optimistic Concurrency Control + Idempotency**

State transitions use version-guarded atomic updates.

Conceptually:

```sql
UPDATE recovery_cases
SET
    state = 'PROCESSING',
    version = version + 1
WHERE
    id = :case_id
    AND version = :expected_version;
```

Only one competing worker can successfully transition the expected version.

Action creation additionally uses **deterministic idempotency keys**.

Database savepoints are used to handle insertion races gracefully without aborting the parent transaction.

This provides effectively-once business execution even though the queue itself provides at-least-once delivery.

---

### 3. Stale Job Execution

**Challenge**

A recovery action may be queued while a case is still unresolved.

Before the worker executes it, however, the customer may complete the payment through another method.

Without a final state check, the queued worker could still:

- Generate an unnecessary payment link
- Send another reminder
- Trigger an invalid recovery action

**Resolution — Final Policy Check + Atomic Claiming**

Immediately before any external side effect, the worker:

1. Reloads the latest recovery case state.
2. Re-evaluates the deterministic policy engine.
3. Checks terminal-state protections.
4. Atomically claims the action.
5. Calls the external API only if the action is still valid.

If the case is already:

```text
RECOVERED
```

the pending recovery action is cancelled.

> No stale side effects are allowed to reach external systems.

---

### 4. Thundering Herds on Queue Retries

**Challenge**

Suppose PostgreSQL temporarily becomes unavailable.

Thousands of Celery jobs may fail at approximately the same time.

If every task retries simultaneously:

```text
Database Recovers
      │
      ▼
Thousands of Retries
      │
      ▼
Database Overloaded Again
```

The recovering dependency can immediately fail again.

**Resolution — Bounded Retries with Exponential Backoff and Jitter**

Celery workers use late acknowledgements:

```text
task_acks_late
```

Retries use exponential backoff with randomized jitter.

Conceptually:

```text
Retry 1 → ~2 seconds
Retry 2 → ~4 seconds
Retry 3 → ~8 seconds
Retry 4 → ~16 seconds
```

Random jitter spreads retry traffic across time and prevents synchronized retry storms.

---

## AI Safety & Boundaries

RecoverAI integrates a **LangGraph agent** for contextual recovery strategy selection.

However, the LLM is explicitly prevented from owning financial correctness.

### Bounded Action Space

The agent can only select from a strict predefined action enum.

```text
WAIT
CREATE_PAYMENT_LINK
SEND_REMINDER
STOP
ESCALATE
```

The model cannot invent arbitrary executable actions.

Free-form outputs are rejected.

---

### Structured Output Validation

All LLM responses are parsed using strict **Pydantic schemas**.

Invalid outputs such as:

- Malformed JSON
- Missing fields
- Unsupported actions
- Hallucinated action types

are rejected before reaching the execution layer.

---

### Deterministic Override

The AI proposes an action.

The deterministic **Policy Engine decides whether the action is permitted**.

For example:

```text
Agent Suggestion:
SEND_REMINDER

Existing Reminder Count:
3

Maximum Allowed:
3

Policy Decision:
REJECT
```

The LLM cannot override deterministic business limits.

---

### Graceful Degradation

If the LLM:

- Times out
- Returns invalid output
- Becomes unavailable
- Exceeds latency limits
- Is intentionally disabled

RecoverAI automatically falls back to the deterministic recovery engine.

Therefore:

```text
LLM Available
     │
     ▼
Potentially Better Strategy Selection

LLM Unavailable
     │
     ▼
Deterministic Recovery Continues
```

AI availability affects **optimization quality**, not correctness.

---

## Data Modeling Standards

### Money

All monetary values are stored as:

```text
BIGINT minor units
```

Examples:

```text
₹549.99  → 54999 paise
$120.50  → 12050 cents
```

Every monetary record also contains an explicit currency code.

Example:

```text
amount_minor = 54999
currency = "INR"
```

Floating-point arithmetic is strictly prohibited for financial calculations.

---

### Time

All timestamps are stored as **timezone-aware UTC timestamps**.

```text
Database
   │
   ▼
UTC Timestamp
   │
   ▼
Presentation Layer
   │
   ▼
Local Timezone Conversion
```

Timezone conversion occurs only at the presentation layer.

---

### Multi-Tenancy

Every business record is scoped using:

```text
merchant_id
```

Multi-tenancy is designed into the schema from Day 1.

Tenant isolation is enforced through:

- Query filters
- Database constraints
- Merchant-scoped uniqueness rules
- Merchant-aware idempotency

This prevents accidental cross-tenant data access.

---

## Tech Stack

| Layer | Technology |
|---|---|
| API & Ingestion | FastAPI |
| Validation | Pydantic |
| ASGI Server | Uvicorn |
| Database | PostgreSQL |
| ORM | SQLAlchemy 2.0 |
| Database Migrations | Alembic |
| Task Queue | Celery |
| Message Broker | Redis |
| Agentic AI | LangGraph |
| Payment Provider | Razorpay |
| Structured Logging | Structlog |
| Dashboard | Streamlit |
| Testing | Pytest |
| API Testing | HTTPX |
| Containerization | Docker / Docker Compose |

---

## Local Execution

### Prerequisites

Install the following before running RecoverAI locally:

- Python 3.11+
- Docker Desktop
- Git

---

## Setup

### 1. Clone the Repository

```bash
git clone <repository-url>
cd RecoverAI
```

### 2. Create the Python Environment

#### Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install project dependencies:

```powershell
pip install -r requirements.txt
```

Create the local environment file:

```powershell
Copy-Item .env.example .env
```

---

### 3. Start Infrastructure

Start PostgreSQL and Redis:

```powershell
docker compose up -d
```

Run database migrations:

```powershell
python -m alembic upgrade head
```

---

### 4. Seed Demo Data

Seed deterministic demo data used by the dashboard:

```powershell
python scripts/seed_demo_data.py
```

---

## Running the Stack

The provided PowerShell script starts:

- FastAPI
- Celery workers
- Outbox dispatcher
- Streamlit dashboard

Each service runs in an isolated terminal window while using the project's virtual environment.

Run:

```powershell
.\scripts\run_all.ps1
```

---

## Local Endpoints

| Service | URL |
|---|---|
| Streamlit Dashboard | http://localhost:8501 |
| FastAPI Swagger Docs | http://127.0.0.1:8000/docs |

---

## Simulation & Benchmarking

RecoverAI includes a controlled simulation environment for comparing the context-aware recovery strategy against a naive retry baseline.

Run:

```bash
python scripts/run_simulation.py --size 10000 --seed 42
```

Example parameters:

```text
--size 10000
```

Controls the number of simulated payment cases.

```text
--seed 42
```

Ensures reproducible simulations.

---

## Simulation Methodology

The simulation generates synthetic payment populations and evaluates recovery strategies under controlled assumptions.

The purpose of the simulation is to compare:

```text
Naive Retry Strategy
        VS
Context-Aware RecoverAI Strategy
```

across the same synthetic population.

Possible evaluation metrics include:

- Recovery rate
- Number of customer interventions
- Payment-link creation volume
- Retry volume
- Recovery latency
- Estimated recovered revenue
- Unnecessary customer contacts

---

## Important Benchmark Disclaimer

> **SIMULATED BENCHMARK — NOT PRODUCTION DATA**

RecoverAI does **not currently possess genuine historical merchant recovery data**.

The simulation therefore uses:

- Synthetic payment populations
- Hypothesis-based customer behavior
- Assumed recovery probabilities
- Controlled deterministic random seeds

Simulation outputs must not be interpreted as proven production revenue improvements.

The benchmark demonstrates that:

1. The architecture can execute the recovery workflow at scale.
2. Recovery strategies can be compared reproducibly.
3. Context-aware policies can outperform naive retry rules under defined assumptions.
4. The system provides the infrastructure required for future production experimentation.

Real-world validation requires deployment against merchant traffic using controlled experiments and holdout groups.

---

## Reliability Model

RecoverAI assumes that distributed infrastructure will eventually fail.

The architecture therefore explicitly handles:

```text
Duplicate Webhooks
Duplicate Queue Delivery
Worker Crashes
Database Outages
Redis Outages
LLM Failures
External API Failures
Concurrent Workers
Delayed Jobs
Stale Recovery Actions
Process Restarts
Network Timeouts
```

Correctness is achieved through combinations of:

- Idempotency
- Atomic database transactions
- Optimistic concurrency control
- Transactional outbox
- Retry boundaries
- Terminal-state validation
- Deterministic policy checks
- Auditable state transitions

---

## Execution Safety Model

Every recovery action follows the same high-level execution pipeline:

```text
Event Received
      │
      ▼
Validate
      │
      ▼
Deduplicate
      │
      ▼
Persist Business State
      │
      ▼
Persist Work Intent
      │
      ▼
Queue Work
      │
      ▼
Evaluate Context
      │
      ▼
Agent Suggests Strategy
      │
      ▼
Policy Engine Validates
      │
      ▼
Atomic Action Claim
      │
      ▼
Final State Check
      │
      ▼
External Side Effect
      │
      ▼
Persist Result
      │
      ▼
Audit + Observability
```

The most important design principle is:

> **No external financial side effect is executed solely because an LLM requested it.**

---

## Documentation Index

RecoverAI includes detailed engineering documentation covering the reasoning behind the architecture.

| Document | Description |
|---|---|
| **System Design** | Architectural overview, component boundaries, data model, state machines, and execution flows |
| **Engineering Decisions** | 49 Architecture Decision Records (ADRs) explaining major engineering and pattern-selection decisions |
| **Real Challenges** | 19 real engineering problems encountered and resolved during development |
| **Failure Labs** | 12 deliberate experiments designed to break the system locally and demonstrate correctness guarantees |

---

## Engineering Goals

RecoverAI is intentionally designed to demonstrate more than API development.

The project focuses on:

- Distributed systems correctness
- Financial idempotency
- Reliable asynchronous processing
- Fault tolerance
- Concurrency control
- Safe AI integration
- State-machine-driven workflows
- Production observability
- Failure-mode analysis
- Scalable system design

The goal is not simply to retry failed payments.

The goal is to build a recovery engine that remains **correct when infrastructure, workers, external APIs, and AI components fail in unpredictable ways**.

---

## Design Principle

```text
Probabilistic AI
      │
      ▼
Strategy Recommendation
      │
      ▼
Deterministic Policy
      │
      ▼
Concurrency Protection
      │
      ▼
Atomic Execution
      │
      ▼
External Financial Side Effect
```

> **AI chooses strategy. Deterministic software owns correctness.**

