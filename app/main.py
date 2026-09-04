import time
import uuid
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from structlog.contextvars import bind_contextvars, clear_contextvars

from app.config import settings
from app.db import check_database
from app.observability import setup_logging
from app.redis_client import check_redis
from app.webhooks.razorpay import router as razorpay_webhook_router


setup_logging()
logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "application_started",
        environment=settings.environment,
        app_name=settings.app_name,
    )
    yield
    logger.info("application_stopped")


app = FastAPI(
    title=settings.app_name,
    lifespan=lifespan,
)

app.include_router(razorpay_webhook_router)


@app.middleware("http")
async def add_request_context(request: Request, call_next):
    clear_contextvars()

    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.request_id = request_id

    bind_contextvars(
        request_id=request_id,
        method=request.method,
        path=request.url.path,
    )

    start = time.perf_counter()

    logger.info("request_started")

    try:
        response = await call_next(request)
    except Exception:
        duration_ms = (time.perf_counter() - start) * 1000
        logger.error(
            "request_failed",
            duration_ms=round(duration_ms, 2),
            exc_info=True,
        )
        raise

    duration_ms = (time.perf_counter() - start) * 1000

    response.headers["X-Request-ID"] = request_id

    logger.info(
        "request_completed",
        status_code=response.status_code,
        duration_ms=round(duration_ms, 2),
    )

    return response


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": settings.app_name,
        "environment": settings.environment,
    }


@app.get("/ready")
def ready():
    checks = {}
    is_ready = True

    try:
        check_database()
        checks["database"] = "ok"
    except Exception as exc:
        checks["database"] = "error"
        is_ready = False
        logger.error(
            "readiness_database_failed",
            error=str(exc),
        )

    try:
        check_redis()
        checks["redis"] = "ok"
    except Exception as exc:
        checks["redis"] = "error"
        is_ready = False
        logger.error(
            "readiness_redis_failed",
            error=str(exc),
        )

    return JSONResponse(
        content={
            "status": "ready" if is_ready else "not_ready",
            "checks": checks,
        },
        status_code=200 if is_ready else 503,
    )