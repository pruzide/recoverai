# RecoverAI System Design

## Status
Milestone 7 Complete. Core Data Model, Webhook Ingestion, Transactional Outbox, Async Worker Processing, Concurrency Safety, Deterministic Recovery Engine, and Policy Engine established.

## Goal
RecoverAI detects failed payments and safely coordinates bounded recovery interventions.

The core flow is:
DETECT → UNDERSTAND → DECIDE → POLICY CHECK → ACT → OBSERVE → MEASURE

## Architecture Principles
1. PostgreSQL is the authoritative source of truth.
2. Redis is ephemeral coordination infrastructure, not business truth.
3. FastAPI must remain stateless.
4. Important business state must survive restarts.
5. Financial correctness must not depend on LLM availability.
6. Webhook processing must be lightweight and fast.
7. Delivery may occur more than once, but business side effects must occur effectively once.

## Data Model (Milestone 2 & 3)
### Core Tables
- `merchants`: Multi-tenant isolation.
- `payments`: Authoritative payment state. Money stored as `BIGINT` minor units.
- `recovery_cases`: State machine driven recovery tracking. Includes `version` for optimistic concurrency.
- `recovery_actions`: Idempotent action execution records.
- `audit_events`: Append-only JSONB audit trail.
- `webhook_events`: Durable inbox for provider events.
- `outbox_events`: Durable queue for deferred worker processing.

### Invariants Enforced by PostgreSQL
- `UNIQUE(merchant_id, provider, provider_payment_id)` prevents duplicate payment ingestion.
- `UNIQUE(payment_id)` on recovery_cases ensures 1:1 mapping.
- `UNIQUE(idempotency_key)` on recovery_actions guarantees effectively-once execution.
- `UNIQUE(provider, provider_event_id)` on webhook_events guarantees webhook deduplication.
- Check constraints prevent negative money amounts and invalid currency formats.

### State Machine
Terminal states (`RECOVERED`, `STOPPED`, `ESCALATED`) cannot regress. Application logic validates transitions before database writes.

## Webhook Ingestion (Milestone 3)
RecoverAI exposes: `POST /webhooks/razorpay/{merchant_id}`

The webhook flow is:
1. Read raw HTTP body.
2. Verify HMAC-SHA256 signature.
3. Parse and validate JSON payload.
4. Begin PostgreSQL transaction.
5. Insert into `webhook_events` (deduplicate via unique constraint).
6. Create or update `payments` and `recovery_cases`.
7. Insert `audit_events`.
8. Insert `outbox_events`.
9. Commit transaction.
10. Return HTTP 200 quickly.

### Supported Events
- `payment.failed`: Transitions case to `ELIGIBLE` and creates outbox event.
- `payment.captured`: Transitions active case to `RECOVERED`, cancels pending actions, and creates outbox event.

### Out-of-Order Protection
If `payment.captured` arrives before `payment.failed`, the system does not create a recovery case for a payment that already succeeded.

## Transactional Outbox
The `outbox_events` table stores future work inside the exact same database transaction as business state. 
This prevents the dual-write problem where a database commit succeeds but a queue publish fails, resulting in lost recovery work.

## Async Processing (Milestone 4)
RecoverAI decouples webhook ingestion from heavy recovery processing using an asynchronous worker architecture.

### Worker Flow
1. The Webhook API commits business state and an `outbox_events` row to PostgreSQL.
2. The Outbox Dispatcher continuously polls for `PENDING` outbox rows using `FOR UPDATE SKIP LOCKED`.
3. The Dispatcher publishes a Celery task to the Redis broker and marks the outbox row `PUBLISHED`.
4. Celery Workers consume tasks from the `recoverai` queue.
5. Workers load the recovery case, validate the current state machine status, and transition it (e.g., `ELIGIBLE` -> `ANALYSING`).
6. Workers write an `audit_events` record to prove execution.

### Delivery & Retry Model
- **At-Least-Once Delivery**: The system assumes tasks may be delivered more than once. Workers are strictly idempotent.
- **Late Acknowledgement**: `task_acks_late=True` ensures tasks are only removed from the queue after successful database commits.
- **Bounded Retries**: Transient failures (e.g., DB connection blips) trigger retries with exponential backoff and jitter to prevent thundering herds.
- **Backpressure**: If workers process slower than webhooks arrive, the Redis queue safely absorbs the burst while the API remains responsive.

## Concurrency & Idempotency (Milestone 5)
RecoverAI assumes duplicate webhook delivery, duplicate queue delivery, concurrent workers, and stale tasks. The system separates delivery from side effects to guarantee effectively-once business behavior.

### Optimistic Concurrency Control
Worker state transitions use version-guarded atomic updates:
```sql
UPDATE recovery_cases
SET status = 'ANALYSING', version = 2, updated_at = NOW()
WHERE id = '...' AND status = 'ELIGIBLE' AND version = 1;
```
If rowcount == 1, the worker won the transition and writes an audit log. If rowcount == 0, another worker won or the state changed, and the task is safely ignored. This prevents long-held pessimistic row locks (SELECT ... FOR UPDATE) while strictly preventing duplicate transitions.

### Stale Job Protection
Workers reload the current state from PostgreSQL before executing logic. If a case has transitioned to a terminal state (e.g., RECOVERED via a late payment.captured webhook) while the task was sitting in the queue, the worker detects the state mismatch and exits without executing stale recovery actions.

### Idempotent Action Creation
Recovery actions (e.g., CREATE_PAYMENT_LINK) are created using deterministic idempotency_key unique constraints. To handle concurrent insertion races, the application uses SQLAlchemy savepoints (begin_nested()). If a unique constraint violation occurs, the savepoint catches the error and returns the existing action, ensuring the broader business transaction does not abort and duplicate actions are never created.

## Deterministic Recovery Engine (Milestone 6)
RecoverAI separates the *decision* of what to do from the *execution* of the action.

### Strategy Evaluation
Recovery decisions are made by a pure, deterministic domain function: `evaluate_recovery`.
This function takes `amount_minor` and `failure_category` and returns a `RecoveryDecision` containing the `action`, `reason`, and optional `delay`.

Because it is a pure function, it:
- Contains no database or network calls.
- Is trivially unit-testable.
- Can evaluate millions of scenarios per second for business simulations.

### State Chaining
The worker chains state transitions atomically using optimistic concurrency:
1. `ELIGIBLE` -> `ANALYSING`
2. Evaluate decision
3. Create `RecoveryAction` idempotently
4. `ANALYSING` -> `ACTION_SELECTED`
5. `ACTION_SELECTED` -> `STOPPED` / `ESCALATED` / `ACTION_SCHEDULED` (if applicable)

### Execution Separation
Milestone 6 only selects the action and schedules it. Actual execution (calling external APIs like Razorpay or sending emails) is deferred to later milestones. This protects the decision engine from network failures and external API rate limits.

## Policy Engine (Milestone 7)
The policy engine acts as a deterministic safety layer between the recovery engine's recommendations and the system's actual execution.

### Purpose
The policy engine determines whether a candidate recovery action is permitted. It protects against:
- Excessive customer contact (spam).
- Duplicate active payment links.
- Automatic action on high-value cases without human review.
- Actions on terminal recovery cases.

### Policy Rules
Current deterministic policies enforced:
- `MAX_ACTIONS_PER_CASE`
- `MAX_REMINDERS_PER_CASE`
- `ONE_ACTIVE_PAYMENT_LINK`
- `HIGH_VALUE_ESCALATION_THRESHOLD`
- `TERMINAL_STATE_PROTECTION`

### Evaluation Model
The policy engine is pure and deterministic.
Inputs:
- Case status and amount.
- Candidate action from the recovery engine.
- Contextual counts (total actions, reminders, active links).
- Merchant-specific limits.

Output:
- `approved` (boolean)
- `final_action` (the permitted action or safe fallback)
- `reason` (audit trail)

### Fallback Behavior
If a candidate action is denied, the policy engine returns a safe fallback:
- High value -> `ESCALATE`
- Max actions reached -> `STOP`
- Max reminders reached -> `STOP`
- Active payment link exists -> `WAIT`
- Terminal state -> `STOP`

### Merchant Policies
Merchant policies are stored in the `merchant_policies` table. Each merchant has exactly one policy row, allowing different merchants to configure their own risk tolerances and customer contact limits. Default policies are created automatically when a recovery case is first processed.

### Bounded Agentic AI (Milestone 8)
RecoverAI integrates Agentic AI strictly for contextual strategy selection, ensuring AI never owns financial correctness or execution.

### Agent Role & Boundaries
The LangGraph agent participates only in strategy selection. It does not own state transitions, policy enforcement, money movement, or external execution. The agent is restricted to a strict enum of supported actions (WAIT, CREATE_PAYMENT_LINK, SEND_REMINDER, STOP, ESCALATE).

### Agent Flow
1. AgentDecisionRequest is built with bounded context (amount, failure category, action counts, engine candidate, deterministic fallback).
2. The LangGraph graph executes decide -> validate nodes.
3. The LLM adapter (app/agents/llm.py) calls the provider (mock or real) with a strict timeout.
4. Output is validated against a strict Pydantic schema (AgentDecisionOutput).
5. A final policy check revalidates the agent-selected action.

### Structured Output & Fallback Model
The agent must return structured JSON. Invalid JSON, timeouts, or illegal actions (e.g., REFUND_CUSTOMER) are immediately rejected.
If the agent fails or its suggestion is denied by the final policy check, the system falls back to the deterministic policy engine's decision.
Fallback reasons include: llm_disabled, llm_failed, invalid_agent_action, agent_graph_failed.

### Observability
The audit payload now captures the full decision lineage:

1. engine_action (deterministic candidate)
2. deterministic_action (policy fallback)
3. agent_action (LLM suggestion)
4. agent_source (llm or deterministic_fallback)
5. final_action (actual permitted action)

This supports future ML training by recording context-action-outcome tuples and comparing deterministic vs. agent-assisted recovery rates.

### End-to-End Execution & Provider Integration (Milestone 9)
RecoverAI connects the recovery brain to real-world financial side effects safely and idempotently.

### Execution Model
Approved scheduled actions are executed by a dedicated worker flow:

- The outbox dispatcher publishes due events (respecting deliver_at schedules). 
- The worker loads the action and recovery case.
- Final Policy Check: The worker re-evaluates the deterministic policy engine and checks for terminal states. If the case is already RECOVERED or policy limits are now exceeded, the action is cancelled.
- Action Claim: The worker atomically transitions the action from APPROVED to EXECUTING to prevent duplicate execution by concurrent workers.
- External Execution: The worker calls the external provider (e.g., Razorpay) outside the database transaction to prevent connection pool exhaustion.
- Finalization: The worker records the success/failure, stores the provider reference, and transitions the case safely (e.g., ACTION_SCHEDULED -> WAITING).

### Razorpay Payment Links & Notes Mapping
When creating a Razorpay payment link, RecoverAI injects its own identifiers into the provider's notes metadata:

- recoverai_merchant_id
- recoverai_recovery_case_id
- recoverai_recovery_action_id
- recoverai_original_payment_reference

When the customer pays and Razorpay sends a payment.captured webhook, the webhook handler extracts these notes to deterministically map the new payment back to the original recovery case, transitioning it to RECOVERED and cancelling any pending actions.

### Scheduled Outbox Delivery
The outbox_events table includes a deliver_at timestamp. The dispatcher only publishes events where deliver_at IS NULL OR deliver_at <= NOW(). This provides durable, database-backed delayed execution for strategies like WAIT, without relying on fragile in-memory sleeps or external cron jobs.

### Failure Handling & Reconciliation
External calls use strict timeouts. If an external call succeeds but the worker crashes before finalizing the database state, the action remains in EXECUTING. Production reconciliation processes must query the external provider using the stable idempotency_key (passed as reference_id) to determine if the side effect actually occurred before retrying.

### Simulator & Business Experiment (Milestone 10)
RecoverAI includes a controlled simulation environment to benchmark the recovery strategy against a naive baseline using synthetic data.

### Architecture
1. Population Generator: Creates a deterministic, seeded synthetic population of failed payments with varying amounts and failure categories.
2. Baseline Strategy: A naive fixed-rule strategy (e.g., always send a reminder).
3. RecoverAI Strategy: Calls the actual pure evaluate_recovery() and evaluate_policy() functions to make context-aware decisions.
4. Simulated Outcome Model: Applies hypothesis-based recovery probabilities to the selected actions.
5. Metrics Aggregation: Calculates recovery rate, recovered revenue, customer contacts, and incremental recovered revenue.

### Purpose & Limitations
The simulator proves that the deterministic engine and policy logic scale correctly and outperform naive strategies under controlled assumptions.

All outputs are strictly labelled SIMULATED BENCHMARK — NOT PRODUCTION DATA.
Simulated probabilities are hypotheses. Real-world validation requires production deployment with holdout groups to measure actual incremental recovered revenue.

### Dashboard API, Metrics, and Explainability (Milestone 11)
RecoverAI exposes a strictly bounded, read-optimized API layer for merchant dashboards and AI observability.

### CQRS and Read/Write Separation
The system logically separates the write-path (webhooks, workers, execution) from the read-path (dashboard API). Read operations never block write transactions and never trigger side effects.

### SQL-Level Aggregation
Dashboard metrics (Recovery Rate, Revenue at Risk, Recovered Revenue) are calculated using PostgreSQL SUM, COUNT, and CASE aggregations. This prevents the API from loading thousands of ORM objects into memory, ensuring sub-100ms response times even for merchants with millions of failed payments.

### Strict Pagination
All list endpoints enforce strict pagination limits (e.g., maximum 100 rows per request) via Pydantic Query validation. This protects the database from unbounded scans and the API from memory exhaustion.

### AI Explainability
The /dashboard/cases/{id} endpoint returns the complete audit_trail for a recovery case. By exposing the raw JSONB payloads from audit_events, the system provides full transparency into the decision lineage:

- What the deterministic engine recommended.
- What the LangGraph agent suggested (and its confidence/reasoning).
- Whether the policy engine approved or denied the action.
- The final executed action.

This ensures that every automated financial intervention is fully auditable and explainable to support agents and compliance officers.