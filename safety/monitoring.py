"""Safety event monitoring."""

import time
import uuid

import redis
import structlog

logger = structlog.get_logger()


class SafetyMonitor:
    """Monitor and log safety events."""

    # Valid event types
    VALID_EVENT_TYPES = {
        "pii_detected",
        "injection_attempt",
        "content_filtered",
        "bias_detected",
        "rate_limited",
    }

    # Longest window any caller can query; entries older than this are pruned
    # on write so each event type's sorted set doesn't grow unbounded.
    MAX_RETENTION_HOURS = 24

    def __init__(self, redis_client: redis.Redis):
        """Initialize safety monitor.

        Args:
            redis_client: Redis client
        """
        self.redis = redis_client

    def log_event(self, event_type: str, details: dict) -> None:
        """Log a safety event.

        Args:
            event_type: Type of event (from VALID_EVENT_TYPES)
            details: Event details dict
        """
        if event_type not in self.VALID_EVENT_TYPES:
            logger.warning("unknown_event_type", event_type=event_type)
            return

        try:
            # Log to structlog
            logger.warning("safety_event", event_type=event_type, **details)

            # Record the event in a per-type sorted set, scored by timestamp, so
            # get_event_count can answer "how many in the last N hours".
            key = f"safety:events:{event_type}"
            now = time.time()
            # Member includes a uuid so two events in the same tick don't collide.
            self.redis.zadd(key, {f"{now}:{uuid.uuid4()}": now})
            self.redis.zremrangebyscore(key, 0, now - self.MAX_RETENTION_HOURS * 3600)
            self.redis.expire(key, self.MAX_RETENTION_HOURS * 3600)

        except Exception as e:
            logger.error("safety_monitor_error", error=str(e))

    def get_event_count(self, event_type: str, window_hours: int = 1) -> int:
        """Get count of safety events in a rolling time window.

        Args:
            event_type: Type of event
            window_hours: Time window in hours, counted back from now

        Returns:
            Count of events in the window
        """
        key = f"safety:events:{event_type}"
        window_start = time.time() - (window_hours * 3600)

        try:
            return self.redis.zcount(key, window_start, "+inf")
        except Exception as e:
            logger.error("event_count_error", event_type=event_type, error=str(e))
            return 0

    def get_total_event_count(self, window_hours: int = 1) -> int:
        """Get the total safety event count across all event types in a rolling window.

        Args:
            window_hours: Time window in hours, counted back from now

        Returns:
            Sum of event counts across all VALID_EVENT_TYPES in the window
        """
        return sum(
            self.get_event_count(event_type, window_hours=window_hours)
            for event_type in self.VALID_EVENT_TYPES
        )
