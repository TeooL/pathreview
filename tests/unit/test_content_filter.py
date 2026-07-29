"""Tests for content_filter.py"""

from unittest.mock import Mock

import pytest

from safety.content_filter import ContentFilter


@pytest.mark.unit
class TestContentFilter:
    """Test suite for ContentFilter."""

    def test_self_harm_language_is_filtered(self):
        """Test self-harm language is detected and replaced."""
        text = "Some feedback that says hurt yourself over this."

        filtered_text, was_filtered = ContentFilter.filter(text)

        assert was_filtered is True
        assert "[CONTENT REMOVED]" in filtered_text

    def test_benign_text_is_not_filtered(self):
        """Test ordinary feedback passes through unchanged."""
        text = "Your README could use a clearer setup section."

        filtered_text, was_filtered = ContentFilter.filter(text)

        assert was_filtered is False
        assert filtered_text == text

    def test_logs_event_to_monitor_when_filtered(self):
        """Test a SafetyMonitor is notified when content is filtered."""
        monitor = Mock()
        text = "Some feedback that says hurt yourself over this."

        ContentFilter.filter(text, monitor=monitor)

        monitor.log_event.assert_called_once_with("content_filtered", {})

    def test_does_not_log_event_when_not_filtered(self):
        """Test a SafetyMonitor is not notified when nothing was filtered."""
        monitor = Mock()

        ContentFilter.filter("Your README could use a clearer setup section.", monitor=monitor)

        monitor.log_event.assert_not_called()

    def test_monitor_is_optional(self):
        """Test filter still works with no monitor passed."""
        text = "Some feedback that says hurt yourself over this."

        filtered_text, was_filtered = ContentFilter.filter(text)

        assert was_filtered is True
