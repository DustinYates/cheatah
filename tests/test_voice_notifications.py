"""Tests for voice call notifications."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from app.infrastructure.notifications import NotificationService
from app.persistence.models.notification import Notification, NotificationPriority, NotificationType


@pytest.fixture
def mock_session():
    """Create a mock database session."""
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.execute = AsyncMock()
    return session


@pytest.fixture
def notification_service(mock_session):
    """Create a notification service with mocked dependencies."""
    service = NotificationService(mock_session)
    return service


class TestNotifyCallSummary:
    """Tests for call summary notifications."""

    @pytest.mark.asyncio
    async def test_creates_notification_with_correct_type(self, notification_service, mock_session):
        """Test that notification is created with correct type."""
        # Mock user repository to return admins
        mock_admin = MagicMock()
        mock_admin.id = 1
        mock_admin.email = "admin@example.com"
        mock_admin.role = "tenant_admin"
        
        notification_service.user_repo.list = AsyncMock(return_value=[mock_admin])
        
        result = await notification_service.notify_call_summary(
            tenant_id=1,
            call_id=123,
            summary_text="Caller asked about pricing",
            intent="pricing_info",
            outcome="info_provided",
            caller_phone="+15555551234",
            methods=["in_app"],
        )
        
        assert result["status"] == "sent"
        # Verify add was called (notification created)
        assert mock_session.add.called

    @pytest.mark.asyncio
    async def test_includes_metadata_in_notification(self, notification_service, mock_session):
        """Test that metadata is included in the notification."""
        mock_admin = MagicMock()
        mock_admin.id = 1
        mock_admin.email = "admin@example.com"
        mock_admin.role = "tenant_admin"
        
        notification_service.user_repo.list = AsyncMock(return_value=[mock_admin])
        
        # Capture the notification that was added
        added_notification = None
        def capture_add(notification):
            nonlocal added_notification
            added_notification = notification
        mock_session.add = capture_add
        
        await notification_service.notify_call_summary(
            tenant_id=1,
            call_id=123,
            summary_text="Caller asked about pricing",
            intent="pricing_info",
            outcome="info_provided",
            caller_phone="+15555551234",
            recording_url="https://example.com/recording.mp3",
            methods=["in_app"],
        )
        
        assert added_notification is not None
        assert added_notification.extra_data["call_id"] == 123
        assert added_notification.extra_data["intent"] == "pricing_info"
        assert added_notification.extra_data["outcome"] == "info_provided"
        assert added_notification.extra_data["recording_url"] == "https://example.com/recording.mp3"

    @pytest.mark.asyncio
    async def test_high_priority_for_booking_outcome(self, notification_service, mock_session):
        """Test that booking requests get high priority."""
        mock_admin = MagicMock()
        mock_admin.id = 1
        mock_admin.email = "admin@example.com"
        mock_admin.role = "tenant_admin"
        
        notification_service.user_repo.list = AsyncMock(return_value=[mock_admin])
        
        added_notification = None
        def capture_add(notification):
            nonlocal added_notification
            added_notification = notification
        mock_session.add = capture_add
        
        await notification_service.notify_call_summary(
            tenant_id=1,
            call_id=123,
            summary_text="Caller wants to book",
            intent="booking_request",
            outcome="booking_requested",
            caller_phone="+15555551234",
            methods=["in_app"],
        )
        
        assert added_notification is not None
        assert added_notification.priority == NotificationPriority.HIGH


class TestNotifyHandoff:
    """Tests for handoff notifications."""

    @pytest.mark.asyncio
    async def test_creates_handoff_notification(self, notification_service, mock_session):
        """Test that handoff notification is created."""
        mock_admin = MagicMock()
        mock_admin.id = 1
        mock_admin.email = "admin@example.com"
        mock_admin.role = "tenant_admin"
        
        notification_service.user_repo.list = AsyncMock(return_value=[mock_admin])
        
        result = await notification_service.notify_handoff(
            tenant_id=1,
            call_id=123,
            reason="caller_requested_human",
            caller_phone="+15555551234",
            handoff_mode="live_transfer",
            transfer_number="+15555555678",
            methods=["in_app"],
        )
        
        assert result["status"] == "sent"

    @pytest.mark.asyncio
    async def test_handoff_notification_is_high_priority(self, notification_service, mock_session):
        """Test that handoff notifications are high priority."""
        mock_admin = MagicMock()
        mock_admin.id = 1
        mock_admin.email = "admin@example.com"
        mock_admin.role = "tenant_admin"
        
        notification_service.user_repo.list = AsyncMock(return_value=[mock_admin])
        
        added_notification = None
        def capture_add(notification):
            nonlocal added_notification
            added_notification = notification
        mock_session.add = capture_add
        
        await notification_service.notify_handoff(
            tenant_id=1,
            call_id=123,
            reason="caller_requested_human",
            caller_phone="+15555551234",
            handoff_mode="live_transfer",
            methods=["in_app"],
        )
        
        assert added_notification is not None
        assert added_notification.priority == NotificationPriority.HIGH


class TestNotifyVoicemail:
    """Tests for voicemail notifications."""

    @pytest.mark.asyncio
    async def test_creates_voicemail_notification(self, notification_service, mock_session):
        """Test that voicemail notification is created."""
        mock_admin = MagicMock()
        mock_admin.id = 1
        mock_admin.email = "admin@example.com"
        mock_admin.role = "tenant_admin"
        
        notification_service.user_repo.list = AsyncMock(return_value=[mock_admin])
        
        result = await notification_service.notify_voicemail(
            tenant_id=1,
            call_id=123,
            caller_phone="+15555551234",
            recording_url="https://example.com/voicemail.mp3",
            methods=["in_app"],
        )
        
        assert result["status"] == "sent"


class TestGetNotifications:
    """Tests for getting notifications."""

    @pytest.mark.asyncio
    async def test_gets_unread_notifications(self, notification_service, mock_session):
        """Test getting unread notifications."""
        mock_notification = MagicMock()
        mock_notification.id = 1
        mock_notification.is_read = False
        
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_notification]
        mock_session.execute = AsyncMock(return_value=mock_result)
        
        notifications = await notification_service.get_unread_notifications(
            tenant_id=1,
            user_id=1,
        )
        
        assert len(notifications) == 1


class TestMarkNotificationRead:
    """Tests for marking notifications as read."""

    @pytest.mark.asyncio
    async def test_marks_notification_as_read(self, notification_service, mock_session):
        """Test marking a notification as read."""
        mock_notification = MagicMock()
        mock_notification.id = 1
        mock_notification.tenant_id = 1
        mock_notification.user_id = 1
        mock_notification.is_read = False
        
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_notification
        mock_session.execute = AsyncMock(return_value=mock_result)
        
        result = await notification_service.mark_notification_read(
            tenant_id=1,
            user_id=1,
            notification_id=1,
        )
        
        assert result is True
        mock_notification.mark_as_read.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_false_for_missing_notification(self, notification_service, mock_session):
        """Test that False is returned for missing notification."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)
        
        result = await notification_service.mark_notification_read(
            tenant_id=1,
            user_id=1,
            notification_id=999,
        )
        
        assert result is False

