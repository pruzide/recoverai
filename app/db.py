from typing import Optional

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from app.config import settings


_engine: Optional[Engine] = None


def get_engine() -> Engine:
    global _engine

    if _engine is None:
        _engine = create_engine(
            settings.database_url,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_timeout=settings.db_pool_timeout,
            pool_pre_ping=True,
            pool_recycle=1800,
            connect_args={
                "connect_timeout": settings.db_connect_timeout,
            },
            future=True,
        )

    return _engine


def check_database() -> bool:
    engine = get_engine()

    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))

    return True