"""Tests for business hours service."""

import pytest
from datetime import datetime
from unittest.mock import patch

from app.domain.services.business_hours_service import is_within_business_hours


class TestBusinessHoursService:
    """Test cases for business hours checking logic."""

    def test_returns_true_when_disabled(self):
        """Test returns True when business hours are disabled."""
        result = is_within_business_hours(
            business_hours={"monday": {"start": "09:00", "end": "17:00"}},
            timezone_str="UTC",
            business_hours_enabled=False,
        )
        assert result is True

    def test_returns_true_when_no_hours_configured(self):
        """Test returns True when no business hours configured."""
        result = is_within_business_hours(
            business_hours=None,
            timezone_str="UTC",
            business_hours_enabled=True,
        )
        assert result is True

    def test_returns_true_when_hours_empty(self):
        """Test returns True when hours dict is empty."""
        result = is_within_business_hours(
            business_hours={},
            timezone_str="UTC",
            business_hours_enabled=True,
        )
        assert result is True

    @patch('app.domain.services.business_hours_service.datetime')
    def test_within_business_hours(self, mock_datetime):
        """Test returns True when within business hours."""
        import pytz
        # Mock to Monday 10:00 AM UTC
        mock_now = datetime(2025, 1, 13, 10, 0, 0, tzinfo=pytz.UTC)
        mock_datetime.now.return_value = mock_now
        mock_datetime.strptime = datetime.strptime
        
        result = is_within_business_hours(
            business_hours={"monday": {"start": "09:00", "end": "17:00"}},
            timezone_str="UTC",
            business_hours_enabled=True,
        )
        assert result is True

    @patch('app.domain.services.business_hours_service.datetime')
    def test_before_business_hours(self, mock_datetime):
        """Test returns False when before business hours."""
        import pytz
        # Mock to Monday 8:00 AM UTC (before 9 AM)
        mock_now = datetime(2025, 1, 13, 8, 0, 0, tzinfo=pytz.UTC)
        mock_datetime.now.return_value = mock_now
        mock_datetime.strptime = datetime.strptime
        
        result = is_within_business_hours(
            business_hours={"monday": {"start": "09:00", "end": "17:00"}},
            timezone_str="UTC",
            business_hours_enabled=True,
        )
        assert result is False

    @patch('app.domain.services.business_hours_service.datetime')
    def test_after_business_hours(self, mock_datetime):
        """Test returns False when after business hours."""
        import pytz
        # Mock to Monday 6:00 PM UTC (after 5 PM)
        mock_now = datetime(2025, 1, 13, 18, 0, 0, tzinfo=pytz.UTC)
        mock_datetime.now.return_value = mock_now
        mock_datetime.strptime = datetime.strptime
        
        result = is_within_business_hours(
            business_hours={"monday": {"start": "09:00", "end": "17:00"}},
            timezone_str="UTC",
            business_hours_enabled=True,
        )
        assert result is False

    @patch('app.domain.services.business_hours_service.datetime')
    def test_closed_day(self, mock_datetime):
        """Test returns False on a day not in business hours."""
        import pytz
        # Mock to Sunday 10:00 AM UTC
        mock_now = datetime(2025, 1, 12, 10, 0, 0, tzinfo=pytz.UTC)
        mock_datetime.now.return_value = mock_now
        mock_datetime.strptime = datetime.strptime
        
        result = is_within_business_hours(
            business_hours={"monday": {"start": "09:00", "end": "17:00"}},  # Only Monday
            timezone_str="UTC",
            business_hours_enabled=True,
        )
        assert result is False

    @patch('app.domain.services.business_hours_service.datetime')
    def test_at_boundary_start(self, mock_datetime):
        """Test returns True at exact start time."""
        import pytz
        # Mock to Monday 9:00 AM UTC exactly
        mock_now = datetime(2025, 1, 13, 9, 0, 0, tzinfo=pytz.UTC)
        mock_datetime.now.return_value = mock_now
        mock_datetime.strptime = datetime.strptime
        
        result = is_within_business_hours(
            business_hours={"monday": {"start": "09:00", "end": "17:00"}},
            timezone_str="UTC",
            business_hours_enabled=True,
        )
        assert result is True

    @patch('app.domain.services.business_hours_service.datetime')
    def test_at_boundary_end(self, mock_datetime):
        """Test returns True at exact end time."""
        import pytz
        # Mock to Monday 5:00 PM UTC exactly
        mock_now = datetime(2025, 1, 13, 17, 0, 0, tzinfo=pytz.UTC)
        mock_datetime.now.return_value = mock_now
        mock_datetime.strptime = datetime.strptime
        
        result = is_within_business_hours(
            business_hours={"monday": {"start": "09:00", "end": "17:00"}},
            timezone_str="UTC",
            business_hours_enabled=True,
        )
        assert result is True

    @patch('app.domain.services.business_hours_service.datetime')
    def test_full_week_hours(self, mock_datetime):
        """Test with full week of business hours."""
        import pytz
        # Mock to Wednesday 2:00 PM UTC
        mock_now = datetime(2025, 1, 15, 14, 0, 0, tzinfo=pytz.UTC)
        mock_datetime.now.return_value = mock_now
        mock_datetime.strptime = datetime.strptime
        
        business_hours = {
            "monday": {"start": "09:00", "end": "17:00"},
            "tuesday": {"start": "09:00", "end": "17:00"},
            "wednesday": {"start": "09:00", "end": "17:00"},
            "thursday": {"start": "09:00", "end": "17:00"},
            "friday": {"start": "09:00", "end": "17:00"},
        }
        
        result = is_within_business_hours(
            business_hours=business_hours,
            timezone_str="UTC",
            business_hours_enabled=True,
        )
        assert result is True

    @patch('app.domain.services.business_hours_service.datetime')
    def test_different_timezone(self, mock_datetime):
        """Test with different timezone."""
        import pytz
        # Mock to Monday 2:00 PM EST (19:00 UTC)
        est = pytz.timezone("America/New_York")
        mock_now = datetime(2025, 1, 13, 14, 0, 0, tzinfo=est)
        mock_datetime.now.return_value = mock_now
        mock_datetime.strptime = datetime.strptime
        
        result = is_within_business_hours(
            business_hours={"monday": {"start": "09:00", "end": "17:00"}},
            timezone_str="America/New_York",
            business_hours_enabled=True,
        )
        assert result is True

    def test_handles_invalid_timezone_gracefully(self):
        """Test handles invalid timezone by defaulting to open."""
        # Invalid timezone should not crash and should default to True
        result = is_within_business_hours(
            business_hours={"monday": {"start": "09:00", "end": "17:00"}},
            timezone_str="Invalid/Timezone",
            business_hours_enabled=True,
        )
        # Should return True (default to open on error)
        assert result is True

    def test_handles_invalid_time_format_gracefully(self):
        """Test handles invalid time format by defaulting to open."""
        result = is_within_business_hours(
            business_hours={"monday": {"start": "invalid", "end": "17:00"}},
            timezone_str="UTC",
            business_hours_enabled=True,
        )
        # Should return True (default to open on error)
        assert result is True

    def test_handles_missing_start_end(self):
        """Test handles missing start/end times."""
        result = is_within_business_hours(
            business_hours={"monday": {}},  # No start/end
            timezone_str="UTC",
            business_hours_enabled=True,
        )
        # Should return False (closed if configuration is incomplete)
        assert result is False

