from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "RecoverAI"
    environment: str = "local"
    debug: bool = False

    host: str = "127.0.0.1"
    port: int = 8000

    log_level: str = "INFO"

    database_url: str = "postgresql+psycopg://postgres:recoverai_local_dev@localhost:5432/recoverai"
    test_database_url: str = "postgresql+psycopg://postgres:recoverai_local_dev@localhost:5432/recoverai_test"

    db_pool_size: int = 5
    db_max_overflow: int = 5
    db_pool_timeout: int = 10
    db_connect_timeout: int = 5

    redis_url: str = "redis://localhost:6379/0"
    redis_socket_timeout: int = 2

    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_webhook_secret: str = "local_webhook_secret_change_me"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()