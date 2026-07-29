"""Tests for safety/monitoring.py"""

from unittest.mock import Mock, patch

import pytest

from safety.monitoring import SafetyMonitor


@pytest.mark.unit
class TestSafetyMonitor:
    """Test suite for SafetyMonitor."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        return Mock()

    @pytest.fixture
    def monitor(self, mock_redis):
        """Create a SafetyMonitor instance with mocked Redis."""
        return SafetyMonitor(mock_redis)

    def test_log_event_records_valid_event_type(self, monitor, mock_redis):
        """Test logging a valid event type writes to the sorted set."""
        mock_redis.zadd = Mock()
        mock_redis.zremrangebyscore = Mock()
        mock_redis.expire = Mock()

        monitor.log_event("pii_detected", {"field": "email"})

        mock_redis.zadd.assert_called_once()
        key, mapping = mock_redis.zadd.call_args[0]
        assert key == "safety:events:pii_detected"
        assert len(mapping) == 1

    def test_log_event_sets_expiry(self, monitor, mock_redis):
        """Test logging an event sets a TTL on the key."""
        mock_redis.zadd = Mock()
        mock_redis.zremrangebyscore = Mock()
        mock_redis.expire = Mock()

        monitor.log_event("rate_limited", {"user_id": 1})

        mock_redis.expire.assert_called_once()
        key, ttl = mock_redis.expire.call_args[0]
        assert key == "safety:events:rate_limited"
        assert ttl == SafetyMonitor.MAX_RETENTION_HOURS * 3600

    def test_log_event_prunes_stale_entries(self, monitor, mock_redis):
        """Test logging an event prunes entries older than MAX_RETENTION_HOURS."""
        mock_redis.zadd = Mock()
        mock_redis.zremrangebyscore = Mock()
        mock_redis.expire = Mock()

        with patch("time.time", return_value=100_000):
            monitor.log_event("bias_detected", {})

        mock_redis.zremrangebyscore.assert_called_once()
        key, min_score, max_score = mock_redis.zremrangebyscore.call_args[0]
        assert key == "safety:events:bias_detected"
        assert min_score == 0
        assert max_score == 100_000 - SafetyMonitor.MAX_RETENTION_HOURS * 3600

    def test_log_event_rejects_unknown_event_type(self, monitor, mock_redis):
        """Test unknown event types are not recorded."""
        mock_redis.zadd = Mock()

        monitor.log_event("not_a_real_type", {})

        mock_redis.zadd.assert_not_called()

    def test_log_event_handles_redis_error(self, monitor, mock_redis):
        """Test a Redis failure while logging doesn't raise."""
        mock_redis.zadd = Mock(side_effect=Exception("Redis error"))

        with patch("safety.monitoring.logger"):
            monitor.log_event("pii_detected", {})  # should not raise

    def test_get_event_count_returns_redis_zcount(self, monitor, mock_redis):
        """Test get_event_count reads from the sorted set via zcount."""
        mock_redis.zcount = Mock(return_value=3)

        count = monitor.get_event_count("pii_detected")

        assert count == 3
        mock_redis.zcount.assert_called_once()
        key, min_score, max_score = mock_redis.zcount.call_args[0]
        assert key == "safety:events:pii_detected"
        assert max_score == "+inf"

    def test_get_event_count_uses_window_hours(self, monitor, mock_redis):
        """Test get_event_count scopes the window to window_hours."""
        mock_redis.zcount = Mock(return_value=0)

        with patch("time.time", return_value=100_000):
            monitor.get_event_count("pii_detected", window_hours=2)

        key, min_score, max_score = mock_redis.zcount.call_args[0]
        assert min_score == 100_000 - 2 * 3600

    def test_get_event_count_handles_redis_error(self, monitor, mock_redis):
        """Test get_event_count returns 0 on Redis failure instead of raising."""
        mock_redis.zcount = Mock(side_effect=Exception("Redis error"))

        with patch("safety.monitoring.logger"):
            count = monitor.get_event_count("pii_detected")

        assert count == 0

    def test_get_total_event_count_sums_all_event_types(self, monitor, mock_redis):
        """Test get_total_event_count sums counts across all VALID_EVENT_TYPES."""
        mock_redis.zcount = Mock(return_value=2)

        total = monitor.get_total_event_count()

        assert total == 2 * len(SafetyMonitor.VALID_EVENT_TYPES)
        assert mock_redis.zcount.call_count == len(SafetyMonitor.VALID_EVENT_TYPES)

    def test_get_total_event_count_zero_when_no_events(self, monitor, mock_redis):
        """Test get_total_event_count returns 0 when nothing has been logged."""
        mock_redis.zcount = Mock(return_value=0)

        assert monitor.get_total_event_count() == 0

    def test_events_outside_window_are_not_counted(self, monitor, mock_redis):
        """Test an event logged outside the requested window doesn't count toward it."""
        real_redis_store = {}

        def fake_zadd(key, mapping):
            real_redis_store.setdefault(key, {}).update(mapping)

        def fake_zcount(key, min_score, max_score):
            scores = real_redis_store.get(key, {}).values()
            return sum(1 for s in scores if s >= min_score)

        mock_redis.zadd = Mock(side_effect=fake_zadd)
        mock_redis.zremrangebyscore = Mock()
        mock_redis.expire = Mock()
        mock_redis.zcount = Mock(side_effect=fake_zcount)

        with patch("time.time", return_value=1_000_000):
            monitor.log_event("pii_detected", {})  # event two hours ago

        with patch("time.time", return_value=1_000_000 + 2 * 3600):
            count_last_hour = monitor.get_event_count("pii_detected", window_hours=1)
            count_last_three_hours = monitor.get_event_count("pii_detected", window_hours=3)

        assert count_last_hour == 0
        assert count_last_three_hours == 1
