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