# Failure Lab

Purpose:
Deliberately create safe local failures to understand why correctness patterns exist.
Never leave unsafe experiment code in the production path.

## Lab 1: Naive in-memory state

Goal:
Prove that Python memory cannot coordinate multiple stateless API instances.

Experiment:
Run two instances of a toy FastAPI app.
Each instance stores processed events in a local Python set.
Send the same event to both instances.

Expected result:
Both instances process the event because they do not share memory.

Lesson:
Local memory is not a valid deduplication mechanism for distributed systems.

Correct future design:
Use PostgreSQL unique constraints and database transactions.

## Lab 2: Dual-Write Failure

Goal:
Prove why committing business state and then separately publishing to a queue is dangerous.

Experiment:
Run `python labs/dual_write_lab.py`.
1. Insert a payment into the database, commit, then simulate a queue publish crash.
2. Insert a payment AND an outbox row in the same transaction, commit, then simulate a queue publish crash.

Expected result:
Pattern 1 (Naive): 0 outbox rows exist. The recovery work is permanently lost.
Pattern 2 (Transactional Outbox): 1 outbox row exists. The recovery work is durable and can be retried later by a dispatcher.

Lesson:
Never commit business state and then separately publish work. Put the work intent into the exact same database transaction as the business state.

Correct future design:
Use the `outbox_events` table to store work intent, and a separate background worker to read pending outbox rows and publish them to Redis/Celery.

## Lab 3: Redis Outage and Outbox Durability

Goal:
Prove that a Redis broker outage delays async processing but does not permanently lose durable recovery work.

Experiment:
1. Send a `payment.failed` webhook to the API.
2. Verify the `outbox_events` table contains a new row with `status = PENDING`.
3. Stop the Redis container (`docker compose stop redis`).
4. Run the outbox dispatcher manually (`python scripts/dispatch_once.py`).
5. Observe the dispatcher fail to publish, but the outbox row remains `PENDING` with `attempts` incremented and `last_error` populated.
6. Restart Redis (`docker compose start redis`).
7. Run the dispatcher again.
8. Observe the outbox row transition to `PUBLISHED`.
9. Verify the Celery worker picks up the task and transitions the recovery case to `ANALYSING`.

Expected result:
Redis downtime causes a temporary processing delay. Once Redis recovers, the dispatcher successfully publishes the durable work intent, and the worker completes the business flow.

Lesson:
The queue broker (Redis) is merely a transport mechanism. PostgreSQL owns the durable work intent. A queue failure increases latency but does not cause data loss.

Correct future design:
Always write work intent to the transactional outbox before attempting to publish to the message broker.

## Lab 4: Concurrent Worker State Transitions (Optimistic Concurrency)

Goal:
Prove that optimistic concurrency control prevents duplicate state transitions and duplicate audit events when multiple workers race to process the same recovery case.

Experiment:
Run `python labs/concurrent_case_transition_lab.py`.
1. Create a recovery case in the `ELIGIBLE` state with `version = 1`.
2. Spawn two Python threads simulating two concurrent Celery workers.
3. Use a `threading.Barrier` to force both threads to read the case state and attempt the atomic `UPDATE ... WHERE version = 1` at the exact same millisecond.
4. Observe the database state and audit logs after both threads finish.

Expected result:
- `Successful transitions: 1`
- `Conflicted transitions: 1`
- `Final case status: ANALYSING`
- `Final case version: 2`
- `Audit events: 1`

Lesson:
Queue delivery and worker execution can happen concurrently. Relying on application-level `if status == 'ELIGIBLE'` checks is unsafe because both workers will read `ELIGIBLE`. The database-level `WHERE version = expected_version` constraint is the only safe way to ensure exactly one worker wins the right to mutate state and write audit logs.

Correct future design:
Always use atomic, version-guarded updates for critical state machine transitions in distributed workers.

## Lab 5: Pure vs Coupled Domain Engine

Goal:
Prove that mixing infrastructure (DB/Network) with business logic makes the system orders of magnitude slower and harder to test at scale.

Experiment:
Run `python labs/pure_vs_coupled_lab.py`.
1. Simulate 10,000 recovery cases using a "coupled" task that includes artificial `time.sleep()` delays to represent DB reads, external API calls, and DB writes.
2. Simulate the exact same 10,000 cases using the pure `evaluate_recovery()` domain function.

Expected result:
The pure domain engine processes the 10,000 cases roughly 1000x faster than the coupled simulation.

Lesson:
Business rules should be pure functions. By keeping infrastructure out of the decision logic, we can run massive business experiments (Milestone 10) on millions of rows in memory without touching the database.

Correct future design:
Always load context in the service/worker layer, pass it to a pure domain function, and then persist the results.

## Lab 6: Policy Bypass

Goal:
Prove why the deterministic recovery engine is not enough and why a policy engine is required to protect the business and the customer.

Experiment:
Run `python labs/policy_bypass_lab.py`.
1. Pass a high-value failed payment (e.g., ₹6,000) with an `expired_instrument` category to the pure recovery engine.
2. Observe the engine's recommendation.
3. Pass the engine's recommendation, along with the merchant's policy limits, to the policy engine.
4. Observe the final permitted action.

Expected result:
- Without policy: The engine recommends `CREATE_PAYMENT_LINK` (because expired instruments need new links).
- With policy: The policy engine denies the link and forces `ESCALATE` (because the amount exceeds the high-value threshold).

Lesson:
The recovery engine optimizes for *recovery probability*, but the policy engine optimizes for *business safety and customer experience*. Both are required.

Correct future design:
Never execute a recovery engine or LLM recommendation without passing it through the deterministic policy engine first.

## Lab 7: LLM Failure Modes and Deterministic Fallback

Goal:
Prove that AI provider failures (timeouts, malformed JSON, hallucinated actions) do not crash the recovery system or compromise financial correctness.

Experiment:
Run `python labs/llm_failure_lab.py`.
1. Configure the mock LLM to `normal` mode: Agent successfully parses JSON and selects an action.
2. Configure to `timeout` mode: Agent catches the timeout exception and falls back.
3. Configure to `malformed` mode: Agent catches the JSON decode error and falls back.
4. Configure to `illegal_action` mode (e.g., LLM outputs `REFUND_CUSTOMER`): Pydantic schema validation rejects the enum, and the agent falls back.

Expected result:
In all failure scenarios, the agent source becomes `deterministic_fallback`, and the system safely defaults to the policy engine's recommended action (e.g., `STOP`).

Lesson:
AI failure reduces optimization quality, but it must never take down revenue recovery. Strict schema validation and deterministic fallbacks are mandatory for production Agentic AI.

Correct future design:
Always wrap LLM calls in strict Pydantic schemas and provide a deterministic fallback path that guarantees forward progress.

## Lab 8: Stale Execution Protection (Final Policy Check)

Goal:
Prove that the final policy check prevents external side effects when the recovery case state has changed (e.g., customer paid) between action approval and execution.

Experiment:
Run `python labs/stale_execution_lab.py`.
1. Create a recovery case and an approved `CREATE_PAYMENT_LINK` action in the database.
2. Simulate the customer paying by manually transitioning the case to `RECOVERED` in the database.
3. Run the action executor against the approved action.
4. Observe the final state of the case and the action.

Expected result:
- Executor result: `{'status': 'cancelled', 'reason': 'terminal_state_protected'}`
- Case status remains: `RECOVERED`
- Action status transitions to: `CANCELLED`
- No external Razorpay API call is made.

Lesson:
State can change between the moment an action is approved and the moment a worker picks it up. Relying solely on the historical `APPROVED` status is unsafe. A final, real-time policy and state check is mandatory to prevent stale side effects.

Correct future design:
Always re-evaluate policy and terminal state protections inside the executor immediately before making external network calls.