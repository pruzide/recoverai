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