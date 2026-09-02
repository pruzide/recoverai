# Real Challenge Log

This document records actual engineering problems encountered during development, how they were diagnosed, and the principles learned.

---

## C-001: Local infrastructure port conflict causing misdirected database connection

### Problem
The `/ready` endpoint returned a `503 Service Unavailable` status.

### Symptoms
- `/health` returned `200 OK` (process was alive).
- `/ready` returned `{"status":"not_ready","checks":{"database":"error","redis":"ok"}}`.
- Redis was functioning correctly, isolating the issue to the PostgreSQL connection.

### Root cause
A locally installed Windows PostgreSQL service (`postgresql-x64-18`) was actively listening on host port `5432`. Because Docker could not bind its container to the already-occupied port, the FastAPI application was silently connecting to the local Windows Postgres instead of the containerized one, resulting in a `FATAL: password authentication failed` error.

### Investigation
1. Inspected the `readiness_database_failed` JSON log from `uvicorn`, which explicitly stated the failure was `password authentication failed`, proving a server *was* listening on port `5432`.
2. Ran `netstat -ano | findstr ":5432"` and `Get-Service` to identify the process holding the port.
3. Discovered the local Windows PostgreSQL service was occupying the standard port.

### Fix
Moved the Docker Postgres port mapping to `5433` in `docker-compose.yml` to avoid the host conflict. Updated the `DATABASE_URL` in `.env` to point to port `5433`.

### Why the fix worked
Isolating the containerized database on an unoccupied host port (`5433`) prevented the network conflict, allowing the app to correctly route TCP traffic to the intended Dockerized PostgreSQL instance.

### Tradeoff
Using non-standard ports locally requires strict configuration management. If a new developer joins, they must ensure their `.env` matches the `docker-compose.yml` port mappings.

### What we learned
1. "Password authentication failed" proves a server IS listening on the network path, but it might be the *wrong* server.
2. Local development environments often have hidden services occupying standard ports. Isolating infrastructure ports prevents these conflicts.
3. A `503` readiness response is the system telling the truth. The fix was to repair the dependency routing, not to silence the probe.

---

## C-002: Configuration drift - application ignoring updated environment variables

### Problem
After updating the database port to `5433` in `.env`, the application continued to fail the database readiness check.

### Symptoms
- `curl.exe -i http://127.0.0.1:8000/ready` still returned `503`.
- The database error persisted despite the `docker-compose.yml` and `.env` files appearing correct in the editor.

### Root cause
Configuration drift / unsaved file state. The `pydantic-settings` library reads the `.env` file only when the application starts (or if the hot-reloader detects a Python file change, not a `.env` change). The physical `.env` file on disk had not actually been updated to port `5433` before the server restarted.

### Investigation
Read the exact port number in the `psycopg.OperationalError` JSON log. It explicitly stated `port 5432`, proving the application was still reading the old configuration. Verified the file contents via the terminal command `type .env | findstr DATABASE_URL`.

### Fix
1. Hard-stopped the `uvicorn` process (`Ctrl+C`).
2. Force-updated the `.env` file using PowerShell to ensure the port was correctly written: `(Get-Content .env) -replace 'localhost:5432', 'localhost:5433' | Set-Content .env`.
3. Restarted `uvicorn` so `pydantic-settings` would load the new environment variables into memory.

### Why the fix worked
Ensuring the physical file contained the correct port and performing a full process restart allowed `pydantic-settings` to parse and inject the updated `DATABASE_URL` into the application's configuration context.

### Tradeoff
Local `.env` files are highly prone to human error (forgetting to save, editing `.env.example` by mistake, or relying on hot-reloaders that don't watch environment files).

### What we learned
1. Always trust the application logs over assumptions. The structured log explicitly revealed the internal state (the port it was trying to reach).
2. In production, never rely on local text files for configuration. Use centralized Secret Managers (like AWS Secrets Manager or HashiCorp Vault) that inject variables directly into the container's memory at startup to eliminate "forgot to save" errors.