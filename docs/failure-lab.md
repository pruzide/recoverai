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