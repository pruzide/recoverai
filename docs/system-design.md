# RecoverAI System Design

## Status
Milestone 5 Complete. Core Data Model, Webhook Ingestion, Transactional Outbox, Async Worker Processing, and Concurrency Safety established.

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