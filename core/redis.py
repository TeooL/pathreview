"""Shared Redis client dependency."""

import redis

from core.config import settings


def get_redis_client() -> redis.Redis:
    """FastAPI dependency that provides a Redis client built from settings.redis_url."""
    return redis.from_url(settings.redis_url, decode_responses=True)
