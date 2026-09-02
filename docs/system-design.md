# RecoverAI System Design

## Status
Milestone 2 Complete. Core Data Model established.

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

## Data Model (Milestone 2)
### Core Tables
- `merchants`: Multi-tenant isolation.
- `payments`: Authoritative payment state. Money stored as `BIGINT` minor units.
- `recovery_cases`: State machine driven recovery tracking. Includes `version` for optimistic concurrency.
- `recovery_actions`: Idempotent action execution records.
- `audit_events`: Append-only JSONB audit trail.

### Invariants Enforced by PostgreSQL
- `UNIQUE(merchant_id, provider, provider_payment_id)` prevents duplicate payment ingestion.
- `UNIQUE(payment_id)` on recovery_cases ensures 1:1 mapping.
- `UNIQUE(idempotency_key)` on recovery_actions guarantees effectively-once execution.
- Check constraints prevent negative money amounts and invalid currency formats.

### State Machine
Terminal states (`RECOVERED`, `STOPPED`, `ESCALATED`) cannot regress. Application logic validates transitions before database writes.

## Infrastructure
- FastAPI (Stateless API)
- PostgreSQL 16 (Source of Truth, Port 5433 locally to avoid host conflicts)
- Redis 7 (Ephemeral Queue/Cache)
- Alembic (Schema Migrations)