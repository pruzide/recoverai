# Real Challenge Log

This document records actual engineering problems encountered during development, how they were diagnosed, and the principles learned.

---

## C-001: Local infrastructure port conflict causing misdirected database connection

### Problem
The `/ready` endpoint returned a `503 Service Unavailable` status, and `pytest` failed with `password authentication failed`.

### Symptoms
- `/health` returned `200 OK` (process was alive).
- `/ready` returned `{"status":"not_ready","checks":{"database":"error","redis":"ok"}}`.
- `pytest` crashed with `FATAL: password authentication failed for user "postgres"`.

### Root cause
A locally installed Windows PostgreSQL service was actively listening on host port `5432`. Because Docker could not bind its container to the already-occupied port, the FastAPI application and `pytest` were silently connecting to the local Windows Postgres instead of the containerized one, resulting in an authentication failure.

### Investigation
1. Inspected the `readiness_database_failed` JSON log from `uvicorn`, which explicitly stated the failure was `password authentication failed`, proving a server *was* listening on port `5432`.
2. Realized Docker port mapping conflicts with existing local services. 

### Fix
Moved the Docker Postgres port mapping to `5433` in `docker-compose.yml` to avoid the host conflict. Updated the `DATABASE_URL` in `.env` and `tests/conftest.py` to point to port `5433`.

### Why the fix worked
Isolating the containerized database on an unoccupied host port (`5433`) prevented the network conflict, ensuring the app routed TCP traffic to the intended Dockerized PostgreSQL instance.

### Tradeoff
Using non-standard ports locally requires strict configuration management.

### What we learned
1. "Password authentication failed" proves a server IS listening on the network path, but it might be the *wrong* server.
2. Local development environments often have hidden services occupying standard ports. Isolating infrastructure ports prevents these conflicts.

---

## C-002: Configuration drift - application ignoring updated environment variables

### Problem
After updating the database port to `5433` in `.env`, the application continued to fail the database readiness check.

### Symptoms
- `curl.exe -i http://127.0.0.1:8000/ready` still returned `503`.
- The database error persisted despite the `docker-compose.yml` and `.env` files appearing correct in the editor.

### Root cause
Configuration drift / unsaved file state. The `pydantic-settings` library reads the `.env` file only when the application starts. The physical `.env` file on disk had not actually been updated to port `5433` before the server restarted (or the editor buffer wasn't flushed to disk).

### Investigation
Read the exact port number in the `psycopg.OperationalError` JSON log. It explicitly stated `port 5432`, proving the application was still reading the old configuration.

### Fix
1. Hard-stopped the `uvicorn` process.
2. Force-updated the `.env` file using PowerShell: `(Get-Content .env) -replace 'localhost:5432', 'localhost:5433' | Set-Content .env`.
3. Restarted `uvicorn`.

### Why the fix worked
Ensuring the physical file contained the correct port and performing a full process restart allowed `pydantic-settings` to parse and inject the updated `DATABASE_URL`.

### Tradeoff
Local `.env` files are highly prone to human error.

### What we learned
1. Always trust the application logs over assumptions. The structured log explicitly revealed the internal state.
2. In production, never rely on local text files for configuration. Use centralized Secret Managers that inject variables directly into the container's memory at startup.

---

## C-003: Alembic generated empty migration files

### Problem
Running `alembic revision --autogenerate` succeeded, but `alembic upgrade head` did not create any tables in PostgreSQL.

### Symptoms
The migration script ran without errors, but `\dt` in psql only showed `alembic_version`.

### Root cause
When `autogenerate` ran, the SQLAlchemy `Base.metadata` object was empty because the model classes had not been imported into the `env.py` execution context. Alembic compared an empty metadata object to an empty database, decided there were no changes, and generated a migration file containing only `pass`.

### Investigation
Opened the generated file in `alembic/versions/` and confirmed that `def upgrade():` was empty.

### Fix
Added explicit imports of the model modules directly inside `alembic/env.py`.

### Why the fix worked
Python only registers models to `metadata` when their files are actively imported. Explicitly importing the model modules ensures `metadata` is populated before Alembic compares it to the database schema.

### What we learned
In Python, simply defining classes in separate files doesn't register them in a central registry unless those files are actively imported by the script currently running.

---

## C-004: `pytest.raises` context manager missed implicit database flush

### Problem
The `test_duplicate_provider_payment_id_rejected` test failed with an unhandled `IntegrityError`, even though we were using `pytest.raises(IntegrityError)`.

### Symptoms
The test crashed on the second `create_failed_payment()` call, escaping the exception handler.

### Root cause
The helper function `create_failed_payment()` internally calls `session.flush()`. This caused the database to evaluate the unique constraint and throw the exception *inside* the function, before execution ever reached the `db_session.flush()` inside the `pytest.raises` block.

### Fix
Wrapped the second `create_failed_payment(...)` function call itself inside the `with pytest.raises(IntegrityError):` block.

### Why the fix worked
`pytest.raises` catches exceptions thrown anywhere within its indented block. By wrapping the function that triggers the implicit flush, we successfully caught the database constraint violation.

### What we learned
When testing database constraints, you must ensure the `flush()` or `commit()` that triggers the SQL evaluation actually happens inside the `pytest.raises` context manager. Helper functions that flush implicitly can cause exceptions to escape the context block.

---

## C-005: Alembic autogenerated migrations dropping Enum check constraints

### Problem
When generating the Milestone 3 migration, Alembic detected that the check constraints for string-based Enums (`paymentstatus`, `recoverycasestatus`, etc.) were "removed" and added `op.drop_constraint` commands to the `upgrade()` function.

### Symptoms
The migration applied successfully, but it silently stripped important database check constraints that enforce valid state machine statuses.

### Root cause
Alembic's autogenerate feature struggles to perfectly compare auto-generated check constraints created by SQLAlchemy's `native_enum=False` on PostgreSQL. It sees a mismatch between the model definition and the database schema and assumes the constraint should be dropped.

### Investigation
Reviewed the generated migration file and noticed `op.drop_constraint` commands targeting Enum status columns. Realized this would break database-level state machine protections.

### Fix
Ran `alembic downgrade -1` to reverse the migration. Manually deleted the 4 `op.drop_constraint` lines from `upgrade()` and the 4 `op.create_check_constraint` lines from `downgrade()`. Re-ran `alembic upgrade head`.

### Why the fix worked
By explicitly removing the autogenerated drop commands, we preserved the existing database invariants while still adding the new `webhook_events` and `outbox_events` tables.

### Tradeoff
We must carefully review autogenerated migrations whenever Enum definitions or check constraints are involved. We cannot blindly trust `--autogenerate`.

### What we learned
Automated schema tools are imperfect. Database invariants (like state machine constraints) are the final line of defense for financial correctness, and engineers must manually verify migrations that touch them.

---

## C-006: Pytest hardcoded port bypass

### Problem
After fixing the local port conflict by moving Postgres to port `5433`, `pytest` still failed with `password authentication failed`.

### Symptoms
Tests crashed with the exact same port 5432 authentication error despite the application running perfectly on port 5433.

### Root cause
The test configuration file (`tests/conftest.py`) contained a hardcoded fallback URL pointing to `localhost:5432` instead of the updated `5433`.

### Fix
Updated the fallback URL in `tests/conftest.py` to use port `5433`.

### Why the fix worked
Aligned the test suite's database connection string with the actual infrastructure routing.

### Tradeoff
None, just configuration drift.

### What we learned
Test suites must respect the exact same environment configuration and infrastructure routing as the application itself. Hardcoded fallbacks in test configurations can mask infrastructure changes.

---

## C-007: SQLAlchemy session reuse causing transaction state error

### Problem
The `dual_write_lab.py` script crashed with `InvalidRequestError: A transaction is already begun on this Session`.

### Symptoms
The lab failed on the second distinct transaction block.

### Root cause
Reusing the exact same `Session` object for multiple logically distinct `with session.begin():` blocks confused SQLAlchemy's internal transaction state tracking.

### Fix
Used `SessionLocal()` to create a fresh session object for each distinct unit of work (merchant creation, naive payment, outbox payment, cleanup).

### Why the fix worked
Completely isolated the transaction boundaries and prevented state leakage between distinct units of work.

### Tradeoff
Slightly more boilerplate code to instantiate sessions.

### What we learned
A SQLAlchemy `Session` represents a single unit of work. Do not reuse session objects across logically separate transactions. Always request a fresh session for a new transactional boundary.

---

## C-008: Celery worker crashes on Windows startup

### Problem
Running `celery -A app.celery_app worker` on Windows immediately crashed with a `ValueError` or `NotImplementedError` related to process forking.

### Symptoms
The worker process exited instantly. Logs showed errors originating from the `prefork` pool trying to use `os.fork()`.

### Root cause
Celery's default execution pool (`prefork`) relies on the POSIX `fork()` system call to spawn child worker processes. Windows does not support `os.fork()`.

### Investigation
Checked Celery documentation regarding Windows compatibility. Confirmed that `prefork` is unsupported on Windows natively.

### Fix
Added the `--pool=solo` flag to the local Windows worker startup command:
`celery -A app.celery_app:celery_app worker --loglevel=info --pool=solo -Q recoverai`

### Why the fix worked
The `solo` pool runs tasks synchronously in the main process without attempting to fork child processes, bypassing the Windows OS limitation.

### Tradeoff
The `solo` pool cannot process tasks concurrently. It is strictly for local development and debugging.

### What we learned
1. Celery on Windows is a local development convenience, not a production pattern.
2. Production workers must run in Linux containers where the default `prefork` pool (or `gevent`/`eventlet`) can properly manage concurrency and process isolation.

---

## C-009: SQLAlchemy `SAWarning` on DELETE during concurrent lab cleanup

### Problem
The `concurrent_case_transition_lab.py` script passed successfully but emitted `SAWarning: DELETE statement on table 'payments' expected to delete 1 row(s); 0 were matched` during the cleanup phase.

### Symptoms
The lab logic worked perfectly (1 success, 1 conflict, 1 audit event), but the terminal output was cluttered with SQLAlchemy warnings when deleting the merchant, payment, and recovery case records.

### Root cause
In Milestone 2, we configured foreign keys with `ondelete="CASCADE"`. When the lab script deleted the parent `Merchant` or `Payment`, PostgreSQL automatically cascaded the delete and removed the child `RecoveryCase` rows at the database level. A millisecond later, SQLAlchemy's session tried to explicitly delete those child rows from its memory, realized they were already gone in the DB, and threw a warning.

### Investigation
Traced the warning to the `cleanup()` function in the lab script. Verified that the database schema indeed contained `ON DELETE CASCADE` constraints.

### Fix
Recognized this as a harmless ORM-to-DB synchronization warning specific to the manual lab cleanup script, not a production bug. In production, records are rarely hard-deleted; they are state-transitioned to terminal states. No code change was strictly required for production, but understanding the difference between ORM-level and DB-level cascades was the key takeaway.

### Why the fix worked
Understanding that PostgreSQL had already correctly enforced referential integrity prevented unnecessary debugging of the application code.

### Tradeoff
ORMs can sometimes obscure what the underlying database engine is actually doing.

### What we learned
1. Database-level `ON DELETE CASCADE` happens independently of the ORM's session tracking.
2. In financial systems, we rarely hard-delete records anyway; we transition them to terminal states (e.g., `STOPPED`, `RECOVERED`) and archive them. Hard deletes are mostly for local test/lab cleanup.

---

## C-010: Stale test contract causing KeyError after schema evolution

### Problem
`pytest` failed with `KeyError: 'policy_approved'` in `test_recovery_task.py` after implementing Milestone 8.

### Symptoms
Four tests failed when trying to read `result["policy_approved"]` from the Celery task result dictionary.

### Root cause
Milestone 8 changed the Celery task result schema to include agent-specific fields (`agent_source`, `agent_action`, `final_policy_approved`). The Milestone 7 tests were still asserting against the old schema.

### Investigation
The error was a Python dictionary key lookup failure, not a database, Redis, or LangGraph failure. The task executed successfully but returned a different response shape.

### Fix
Updated `tests/test_recovery_task.py` to assert against the new Milestone 8 schema (`final_policy_approved`, `agent_source`, etc.).

### Why the fix worked
Aligned the test expectations with the actual task response contract.

### Tradeoff
No production code was changed; only test expectations were updated.

### What we learned
When changing internal task result schemas, all contract tests and downstream consumers must be updated in the same change set to prevent silent breakages.