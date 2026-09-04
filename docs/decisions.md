# Engineering Decision Log

## D-001: Use a modular monolith

Decision:
Start with a modular monolith instead of microservices.

Reason:
The project is small and deadline-constrained. Microservices would add network failures, deployment complexity, distributed tracing, and cross-service consistency problems without clear benefit.

Tradeoff:
A monolith may need refactoring before extreme scale.

Failure mode avoided:
Distributed system complexity before product correctness exists.

When reconsider:
When modules have different scaling, ownership, or deployment requirements.

## D-002: PostgreSQL is the source of truth

Decision:
PostgreSQL stores durable business state.

Reason:
Recovery requires transactions, constraints, unique keys, relationships, and auditability.

Tradeoff:
PostgreSQL must be monitored and scaled carefully.

Failure mode avoided:
Ephemeral memory or cache state being lost on restart.

When reconsider:
We do not reconsider the source-of-truth role. We may add replicas, partitioning, or sharding later if scale demands.

## D-003: Redis is not the source of truth

Decision:
Redis is used only for ephemeral coordination.

Reason:
Redis is fast but not appropriate as the durable system of record for financial recovery state.

Tradeoff:
If Redis goes down, asynchronous processing may be delayed.

Failure mode avoided:
Loss of business state when cache/queue infrastructure restarts.

When reconsider:
We do not reconsider this for core financial state.

## D-004: Separate `/health` and `/ready`

Decision:
Use `/health` for liveness and `/ready` for readiness.

Reason:
A process can be alive while dependencies are unavailable.

Tradeoff:
Slightly more operational complexity.

Failure mode avoided:
Sending traffic to instances that cannot safely process requests.

When reconsider:
No need to reconsider for this project.

## D-005: Use structured JSON logs

Decision:
Use structlog with JSON output.

Reason:
Debugging distributed recovery flows requires machine-readable logs with correlation fields.

Tradeoff:
JSON logs are less human-friendly without tooling.

Failure mode avoided:
Unsearchable logs during incidents.

When reconsider:
Only the logging library may change, not the structured logging principle.

## D-006: Store money as integer minor units

Decision:
Use BIGINT minor units plus an explicit currency code.

Reason:
Floating-point arithmetic is unsafe for money and causes silent rounding errors.

Tradeoff:
Application code must convert display amounts (e.g., paise to rupees).

Failure mode avoided:
Financial rounding errors and reconciliation mismatches.

When reconsider:
Never for authoritative money storage.

## D-007: Store all timestamps in UTC

Decision:
Use timezone-aware UTC timestamps for all database records.

Reason:
Merchants and customers operate across time zones. Local time creates scheduling and reporting bugs.

Tradeoff:
The presentation layer must convert UTC to local time for human readability.

Failure mode avoided:
Wrong recovery timing, incorrect SLA metrics, and scheduling drift.

When reconsider:
Never.

## D-008: Use explicit recovery state machine

Decision:
Recovery cases use controlled enum statuses and validated state transitions.

Reason:
Prevents impossible business states (e.g., a recovered case receiving a new reminder).

Tradeoff:
Requires maintaining and testing explicit transition rules.

Failure mode avoided:
Terminal states (RECOVERED, STOPPED, ESCALATED) regressing and causing duplicate customer contact.

When reconsider:
Only when new legitimate business states are introduced.

## D-009: Add version column to recovery_cases

Decision:
Include an integer `version` column on recovery cases from Day 1.

Reason:
Concurrency safety must be designed early to support optimistic locking.

Tradeoff:
Slight overhead on every state update.

Failure mode avoided:
Two concurrent workers processing the same case and creating duplicate financial actions.

When reconsider:
We may choose pessimistic row locking (`SELECT FOR UPDATE`) later, but the version column remains useful for auditing and API ETags.

## D-010: Use Alembic for schema migrations

Decision:
Manage all database schema changes with Alembic.

Reason:
Schema evolution must be repeatable, version-controlled, and auditable across environments.

Tradeoff:
Adds migration tooling complexity compared to `Base.metadata.create_all()`.

Failure mode avoided:
Manual schema drift, missing constraints in production, and unsafe manual SQL execution.

When reconsider:
Do not reconsider.

## D-011: Isolate local Docker ports

Decision:
Map local PostgreSQL to host port `5433` instead of the standard `5432`.

Reason:
Prevents silent network conflicts with natively installed developer tools (like Windows PostgreSQL services) on the host machine.

Tradeoff:
Non-standard local ports require strict `.env` management and developer onboarding documentation.

Failure mode avoided:
The application silently connecting to the wrong local database instance and failing authentication or corrupting local dev data.

When reconsider:
Never for local development.

## D-012: Webhook Inbox Table

Decision:
Persist provider webhooks in a `webhook_events` table with a `UNIQUE(provider, provider_event_id)` constraint.

Reason:
Webhooks are delivered at-least-once. Deduplication must be durable and survive process restarts.

Tradeoff:
Additional database write per webhook.

Failure mode avoided:
Duplicate recovery cases and duplicate customer actions.

When reconsider:
Do not reconsider.

## D-013: Transactional Outbox

Decision:
Write outbox events in the same PostgreSQL transaction as business state.

Reason:
Prevents the dual-write problem where business state commits but queue publishing fails.

Tradeoff:
Requires a background outbox dispatcher (to be built in Milestone 4).

Failure mode avoided:
Committed recovery cases with no worker processing.

When reconsider:
Only replace Redis dispatcher technology, not the outbox principle.

## D-014: HTTP 200 for duplicate webhooks

Decision:
Duplicate webhook delivery returns HTTP 200 instead of an error code.

Reason:
The event was already successfully processed. Returning an error causes unnecessary provider retries.

Tradeoff:
Duplicates are not treated as operational errors by default.

Failure mode avoided:
Provider retry storms due to semantic misunderstandings.

When reconsider:
Only if provider behavior strictly requires different semantics.

## D-015: Verify HMAC signature on raw body

Decision:
Read the raw HTTP request body and verify the HMAC-SHA256 signature *before* parsing JSON.

Reason:
JSON re-serialization can alter whitespace, key order, or encoding, breaking signature verification.

Tradeoff:
Endpoint must manually read raw body before Pydantic validation.

Failure mode avoided:
Valid provider webhooks being rejected due to serialization mismatches, or fake webhooks being accepted.

When reconsider:
Never.