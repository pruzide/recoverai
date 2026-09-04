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
Requires a background outbox dispatcher (built in Milestone 4).

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

## D-016: Use Celery for async recovery work

Decision:
Use Celery workers and a Redis broker for background recovery processing instead of FastAPI BackgroundTasks.

Reason:
Recovery work is financially critical and must survive API restarts, support retries, and scale horizontally.

Tradeoff:
Adds operational complexity (another process and broker to manage).

Failure mode avoided:
Lost background work and blocked webhook handling if the API process crashes.

When reconsider:
Only if recovery work becomes trivial and non-critical.

## D-017: Use a separate outbox dispatcher process

Decision:
Use a dedicated background process to poll the outbox table and publish events to Celery.

Reason:
The webhook API must remain lightweight and strictly bounded in latency. Publishing to a queue can fail or lag without blocking provider HTTP responses.

Tradeoff:
Requires running and monitoring an additional process.

Failure mode avoided:
Webhook latency spikes and direct dual-write failures.

When reconsider:
The dispatcher logic may move into a scheduler service later, but the decoupled polling principle remains.

## D-018: Use late task acknowledgement

Decision:
Configure Celery with `task_acks_late=True` and `task_reject_on_worker_lost=True`.

Reason:
Tasks should only be removed from the queue *after* successful execution, not when they are merely fetched by a worker.

Tradeoff:
Duplicate task delivery is possible if a worker crashes mid-execution.

Failure mode avoided:
Permanent task loss when a worker process is killed or crashes during database operations.

When reconsider:
Only for non-critical tasks where duplicate execution is strictly worse than task loss.

## D-019: Use bounded retries with exponential backoff and jitter

Decision:
Retry transient task failures (like database connection blips) using exponential backoff with randomized jitter.

Reason:
Prevents "thundering herd" scenarios where thousands of failed tasks retry at the exact same millisecond and overwhelm a recovering dependency.

Tradeoff:
Increases the total time to recover from a prolonged outage.

Failure mode avoided:
Retry storms that permanently take down downstream services like PostgreSQL or external APIs.

When reconsider:
Tune the base delay, cap, and max retries based on production observability metrics.

## D-020: Use optimistic concurrency for recovery case transitions

Decision:
Use version-guarded `UPDATE` statements (`WHERE version = expected_version`) for worker state transitions instead of pessimistic row locking (`SELECT ... FOR UPDATE`).

Reason:
State transitions are short and conflicts are relatively rare. Optimistic concurrency prevents duplicate transitions without holding long database locks that could block other workers.

Tradeoff:
Conflicting workers may perform discarded work (read state, attempt update, realize version changed, exit).

Failure mode avoided:
Duplicate state transitions, duplicate audit events, and duplicate customer actions caused by concurrent workers or queue redelivery.

When reconsider:
If a future workflow requires a complex, long-running read-modify-write transaction across multiple tables, pessimistic row locking may be preferable.

## D-021: Audit only after successful atomic transition

Decision:
Write `audit_events` records only *after* the guarded `UPDATE` statement succeeds (rowcount == 1).

Reason:
The audit trail must represent committed business truth. If a worker loses an optimistic concurrency race, it must not write an audit log claiming it changed the state.

Tradeoff:
Requires strict ordering discipline in the worker task logic.

Failure mode avoided:
Audit logs claiming transitions happened when they actually failed due to concurrency conflicts.

When reconsider:
Do not reconsider.

## D-022: Use idempotency keys and savepoints for recovery action creation

Decision:
Create recovery actions using deterministic unique `idempotency_key` constraints, wrapped in SQLAlchemy `begin_nested()` savepoints to handle race conditions.

Reason:
At-least-once queue delivery means two workers might try to create the exact same recovery action simultaneously. The unique constraint prevents duplicates, and the savepoint allows the transaction to catch the `IntegrityError` and return the existing action without aborting the entire business transaction.

Tradeoff:
Slightly more complex database insertion logic.

Failure mode avoided:
Duplicate payment links or duplicate reminders sent to the customer.

When reconsider:
Do not reconsider. Idempotency is non-negotiable for financial actions.

## D-023: Separate decision from execution

Decision:
Separate the recovery strategy decision from the actual external execution.

Reason:
Deciding to send a reminder or create a payment link is a business logic step. Actually calling an external API is an infrastructure step. Mixing them makes the system fragile to network timeouts.

Tradeoff:
Requires more state transitions (e.g., `ACTION_SELECTED` -> `EXECUTING`).

Failure mode avoided:
Network timeouts or external API outages corrupting the internal decision state or blocking the worker.

When reconsider:
Do not reconsider. Decision and execution must remain decoupled.

## D-024: Pure function for strategy evaluation

Decision:
Implement the deterministic recovery engine as a pure Python function that takes context and returns a decision, without accessing the database or network.

Reason:
Business rules must be trivially testable, extremely fast, and immune to infrastructure outages.

Tradeoff:
Requires the worker to load all necessary context before calling the function.

Failure mode avoided:
Untestable logic, slow simulations, and cascading failures when the database is under load.

When reconsider:
Do not reconsider. Domain logic should remain pure.

## D-025: Deterministic policy engine

Decision:
Policy checks are deterministic and separate from the recovery engine and the future agentic AI.

Reason:
Safety rules (like max reminders or high-value escalation) must be predictable, auditable, and strictly enforced.

Tradeoff:
Less flexibility than probabilistic decision-making.

Failure mode avoided:
An LLM or heuristic hallucinating an exception to a hard financial or customer-experience limit.

When reconsider:
Do not reconsider deterministic policy ownership. AI may suggest actions, but policy owns permission.

## D-026: Policy returns safe fallback action

Decision:
When a candidate action is denied by policy, the engine returns a final safe fallback action (e.g., `STOP`, `WAIT`, `ESCALATE`) rather than just returning `False`.

Reason:
The system must not leave cases stuck in an intermediate state after a policy denial.

Tradeoff:
Fallback logic adds complexity to the state machine transitions.

Failure mode avoided:
Denied cases remaining forever in `ANALYSING` or `ACTION_SELECTED` without resolution.

When reconsider:
If product requirements prefer explicit human review queues for every single denial instead of automated fallbacks.

## D-027: Merchant-specific policy table

Decision:
Store merchant policy limits in a dedicated `merchant_policies` table rather than using global hardcoded constants.

Reason:
Different merchants have different risk tolerances, customer bases, and operational capacities.

Tradeoff:
Requires an additional database table, migration, and context-loading query.

Failure mode avoided:
Global policy settings harming merchant-specific customer experience or ignoring merchant-specific risk profiles.

When reconsider:
Do not reconsider multi-tenant policy support.