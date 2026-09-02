from typing import Optional

import redis

from app.config import settings


_client: Optional[redis.Redis] = None


def get_redis() -> redis.Redis:
    global _client

    if _client is None:
        _client = redis.Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_timeout=settings.redis_socket_timeout,
            socket_connect_timeout=settings.redis_socket_timeout,
        )

    return _client


def check_redis() -> bool:
    return bool(get_redis().ping())