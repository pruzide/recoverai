import os

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://postgres:recoverai_local_dev@localhost:5433/recoverai_test",
)

# Force tests to use the test database and known webhook secret.
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["RAZORPAY_WEBHOOK_SECRET"] = "test_webhook_secret"
os.environ["ENVIRONMENT"] = "test"

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.models.base import Base

# Import all models so Base.metadata knows every table.
import app.models  # noqa: F401


@pytest.fixture(scope="session")
def engine():
    engine = create_engine(
        TEST_DATABASE_URL,
        pool_pre_ping=True,
    )

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    yield engine

    engine.dispose()


@pytest.fixture()
def db_session(engine):
    TestSession = sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )

    session = TestSession()

    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture(autouse=True)
def clean_tables(engine):
    yield

    with engine.begin() as connection:
        connection.execute(
            text(
                """
                TRUNCATE TABLE
                    outbox_events,
                    audit_events,
                    recovery_actions,
                    recovery_cases,
                    payments,
                    webhook_events,
                    merchants
                RESTART IDENTITY CASCADE
                """
            )
        )