"""Tests for api/routes/health.py"""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import HTTPException

from api.routes.health import health_check
from safety.monitoring import SafetyMonitor


@pytest.mark.unit
class TestHealthCheck:
    """Test suite for the /health endpoint."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock async database session that succeeds."""
        db = AsyncMock()
        db.execute = AsyncMock()
        return db

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client that succeeds and reports no events."""
        redis_client = Mock()
        redis_client.ping = Mock()
        redis_client.zcount = Mock(return_value=0)
        return redis_client

    @pytest.mark.asyncio
    async def test_all_dependencies_healthy_returns_200_payload(self, mock_db, mock_redis):
        """Test a fully healthy system returns status healthy without raising."""
        result = await health_check(db=mock_db, redis_client=mock_redis)

        assert result["status"] == "healthy"
        assert result["dependencies"]["postgres"] == "healthy"
        assert result["dependencies"]["redis"] == "healthy"

    @pytest.mark.asyncio
    async def test_safety_events_last_hour_reflects_monitor_count(self, mock_db, mock_redis):
        """Test safety_events_last_hour sums real counts from SafetyMonitor, not a hardcoded 0."""
        mock_redis.zcount = Mock(return_value=2)

        result = await health_check(db=mock_db, redis_client=mock_redis)

        assert result["safety_events_last_hour"] == 2 * len(SafetyMonitor.VALID_EVENT_TYPES)

    @pytest.mark.asyncio
    async def test_safety_events_last_hour_zero_when_no_events(self, mock_db, mock_redis):
        """Test safety_events_last_hour is 0 when no events have been logged."""
        result = await health_check(db=mock_db, redis_client=mock_redis)

        assert result["safety_events_last_hour"] == 0

    @pytest.mark.asyncio
    async def test_postgres_failure_raises_503(self, mock_db, mock_redis):
        """Test a Postgres failure surfaces as a 503."""
        mock_db.execute = AsyncMock(side_effect=Exception("connection refused"))

        with pytest.raises(HTTPException) as exc_info:
            await health_check(db=mock_db, redis_client=mock_redis)

        assert exc_info.value.status_code == 503
        assert exc_info.value.detail["dependencies"]["postgres"] == "unhealthy"

    @pytest.mark.asyncio
    async def test_redis_failure_raises_503(self, mock_db, mock_redis):
        """Test a Redis failure surfaces as a 503."""
        mock_redis.ping = Mock(side_effect=Exception("connection refused"))

        with pytest.raises(HTTPException) as exc_info:
            await health_check(db=mock_db, redis_client=mock_redis)

        assert exc_info.value.status_code == 503
        assert exc_info.value.detail["dependencies"]["redis"] == "unhealthy"

    @pytest.mark.asyncio
    async def test_safety_monitor_failure_does_not_break_health_check(self, mock_db, mock_redis):
        """Test a broken safety-event count degrades gracefully instead of failing the check.

        safety_events_last_hour is an optional metric — its own failure shouldn't flip
        the overall status to unhealthy the way a real dependency failure does.
        """
        with patch("api.routes.health.SafetyMonitor", side_effect=Exception("boom")):
            result = await health_check(db=mock_db, redis_client=mock_redis)

        assert result["status"] == "healthy"
        assert result["safety_events_last_hour"] == 0
