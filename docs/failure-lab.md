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