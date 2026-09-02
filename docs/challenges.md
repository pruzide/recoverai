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