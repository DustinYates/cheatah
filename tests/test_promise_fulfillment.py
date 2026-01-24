"""Tests for promise fulfillment service."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.domain.services.promise_fulfillment_service import PromiseFulfillmentService
from app.domain.services.promise_detector import DetectedPromise


@pytest.fixture
def mock_session():
    """Create a mock database session."""
    return AsyncMock()


@pytest.fixture
def fulfillment_service(mock_session):
    """Create PromiseFulfillmentService with mocked dependencies."""
    return PromiseFulfillmentService(mock_session)


class TestBuildUrlFromText:
    """Tests for the _build_url_from_text method."""

    def test_build_url_location_only_cypress(self, fulfillment_service):
        """Test URL building with Cypress location only."""
        text = "I want to register at La Fitness Cypress"
        url = fulfillment_service._build_url_from_text(text)

        assert url is not None
        assert "loc=LAFCypress" in url
        assert "type=" not in url

    def test_build_url_location_only_langham(self, fulfillment_service):
        """Test URL building with Langham Creek location only."""
        text = "I'm interested in classes at Langham Creek"
        url = fulfillment_service._build_url_from_text(text)

        assert url is not None
        assert "loc=LALANG" in url
        assert "type=" not in url

    def test_build_url_location_only_spring(self, fulfillment_service):
        """Test URL building with 24 Hour Fitness Spring location only."""
        text = "Please register me for 24 hour fitness spring"
        url = fulfillment_service._build_url_from_text(text)

        assert url is not None
        assert "loc=24Spring" in url

    def test_build_url_location_and_level_starfish(self, fulfillment_service):
        """Test URL building with location and Starfish level."""
        text = "I want to enroll my child in Starfish class at Cypress"
        url = fulfillment_service._build_url_from_text(text)

        assert url is not None
        assert "loc=LAFCypress" in url
        assert "type=Starfish" in url

    def test_build_url_location_and_level_adult(self, fulfillment_service):
        """Test URL building with location and Adult Level 3."""
        text = "I'm looking for adult level 3 classes at 24 hour fitness spring"
        url = fulfillment_service._build_url_from_text(text)

        assert url is not None
        assert "loc=24Spring" in url
        assert "type=Adult%20Level%203" in url

    def test_build_url_location_and_level_young_adult(self, fulfillment_service):
        """Test URL building with Young Adult level."""
        text = "My teenager needs young adult level 2 at langham creek"
        url = fulfillment_service._build_url_from_text(text)

        assert url is not None
        assert "loc=LALANG" in url
        assert "type=Young%20Adult%202" in url

    def test_build_url_location_and_level_turtle(self, fulfillment_service):
        """Test URL building with Turtle 1 level."""
        text = "We want turtle 1 classes at cypress"
        url = fulfillment_service._build_url_from_text(text)

        assert url is not None
        assert "loc=LAFCypress" in url
        assert "type=Turtle%201" in url

    def test_build_url_no_location_returns_none(self, fulfillment_service):
        """Test that URL building returns None when no location is found."""
        text = "I want to enroll in swimming classes"
        url = fulfillment_service._build_url_from_text(text)

        assert url is None

    def test_build_url_case_insensitive(self, fulfillment_service):
        """Test that location/level detection is case insensitive."""
        text = "I want STARFISH classes at LA FITNESS CYPRESS"
        url = fulfillment_service._build_url_from_text(text)

        assert url is not None
        assert "loc=LAFCypress" in url
        assert "type=Starfish" in url

    def test_build_url_spanish_location_mention(self, fulfillment_service):
        """Test URL building from Spanish conversation mentioning location."""
        # Spanish speakers might mention the location naturally
        text = "Quiero inscribir a mi hijo en clases de natación en Spring"
        url = fulfillment_service._build_url_from_text(text)

        assert url is not None
        assert "loc=24Spring" in url

    def test_build_url_level_variations(self, fulfillment_service):
        """Test various level name variations."""
        test_cases = [
            ("minnow classes at cypress", "Minnow"),
            ("dolphin level at spring", "Dolphin"),
            ("barracuda at langham", "Barracuda"),
            ("shark 2 at cypress", "Shark%202"),
            ("seahorse at spring", "Seahorse"),
            ("tadpole at langham creek", "Tadpole"),
            ("swimboree at cypress", "Swimboree"),
        ]

        for text, expected_type in test_cases:
            url = fulfillment_service._build_url_from_text(text)
            assert url is not None, f"Failed for text: {text}"
            assert f"type={expected_type}" in url, f"Expected type={expected_type} in URL for: {text}"

    def test_build_url_longer_match_preferred(self, fulfillment_service):
        """Test that longer location matches are preferred (e.g., 'langham creek' over 'langham')."""
        text = "Register at la fitness langham creek for starfish"
        url = fulfillment_service._build_url_from_text(text)

        assert url is not None
        assert "loc=LALANG" in url
        # Should match "la fitness langham creek" not just "langham"


class TestComposeMessage:
    """Tests for the _compose_message method."""

    def test_compose_message_with_name_and_url(self, fulfillment_service):
        """Test message composition with name and URL placeholders."""
        template = "Hi {name}! Here's your registration link: {url}"
        asset_config = {"url": "https://example.com/fallback"}

        message = fulfillment_service._compose_message(
            template=template,
            asset_config=asset_config,
            name="John",
            url="https://britishswimschool.com/cypress-spring/register/?loc=LAFCypress"
        )

        assert "Hi John!" in message
        assert "https://britishswimschool.com/cypress-spring/register/?loc=LAFCypress" in message

    def test_compose_message_fallback_name(self, fulfillment_service):
        """Test that 'there' is used when name is None."""
        template = "Hi {name}! Here's your link: {url}"
        asset_config = {"url": "https://example.com"}

        message = fulfillment_service._compose_message(
            template=template,
            asset_config=asset_config,
            name=None,
            url="https://example.com"
        )

        assert "Hi there!" in message

    def test_compose_message_fallback_url(self, fulfillment_service):
        """Test that asset_config URL is used when url parameter is None."""
        template = "Hi {name}! Register here: {url}"
        asset_config = {"url": "https://fallback.url/register"}

        message = fulfillment_service._compose_message(
            template=template,
            asset_config=asset_config,
            name="Jane",
            url=None
        )

        assert "https://fallback.url/register" in message

    def test_compose_message_truncation(self, fulfillment_service):
        """Test that long messages are truncated to SMS limit."""
        # Create a template that will exceed 160 characters
        template = "Hi {name}! Thank you for your interest in British Swim School. Here is your personalized registration link with all the details: {url}"
        asset_config = {"url": "https://britishswimschool.com/cypress-spring/register/?loc=24Spring&type=Adult%20Level%203"}

        message = fulfillment_service._compose_message(
            template=template,
            asset_config=asset_config,
            name="Alexandra",
            url="https://britishswimschool.com/cypress-spring/register/?loc=24Spring&type=Adult%20Level%203"
        )

        assert len(message) <= 160
        assert message.endswith("...")


class TestFulfillPromise:
    """Tests for the fulfill_promise method."""

    @pytest.mark.asyncio
    async def test_fulfill_promise_with_dynamic_url(self, mock_session):
        """Test promise fulfillment with dynamic URL extraction."""
        service = PromiseFulfillmentService(mock_session)

        # Mock DNC service to not block
        with patch('app.domain.services.promise_fulfillment_service.DncService') as MockDnc:
            MockDnc.return_value.is_blocked = AsyncMock(return_value=False)

            # Mock Redis to not find duplicate
            with patch('app.domain.services.promise_fulfillment_service.redis_client') as mock_redis:
                mock_redis.exists = AsyncMock(return_value=False)
                mock_redis.set = AsyncMock()

                # Mock sendable assets config
                mock_prompt_config = MagicMock()
                mock_prompt_config.config_json = {
                    "sendable_assets": {
                        "registration_link": {
                            "enabled": True,
                            "url": "https://fallback.url",
                            "sms_template": "Hi {name}! Register here: {url}"
                        }
                    }
                }
                mock_result = MagicMock()
                mock_result.scalar_one_or_none.return_value = mock_prompt_config
                mock_session.execute = AsyncMock(return_value=mock_result)

                # Mock _send_sms
                with patch.object(service, '_send_sms', new_callable=AsyncMock) as mock_send:
                    mock_send.return_value = {"status": "sent", "message_id": "test123"}

                    promise = DetectedPromise(
                        asset_type="registration_link",
                        confidence=0.9,
                        original_text="I'll text you the registration link"
                    )

                    result = await service.fulfill_promise(
                        tenant_id=1,
                        conversation_id=100,
                        promise=promise,
                        phone="+15551234567",
                        name="Maria",
                        ai_response="I'll send you the registration link for Starfish classes at Cypress."
                    )

                    # Verify _send_sms was called
                    mock_send.assert_called_once()
                    call_args = mock_send.call_args

                    # The message should contain the dynamic URL
                    message = call_args[1]["message"] if "message" in call_args[1] else call_args[0][2]
                    assert "https://britishswimschool.com/cypress-spring/register/" in message
                    assert "loc=LAFCypress" in message

    @pytest.mark.asyncio
    async def test_fulfill_promise_dedup_redis(self, mock_session):
        """Test that duplicate promises are skipped via Redis."""
        service = PromiseFulfillmentService(mock_session)

        # Mock DNC service to not block
        with patch('app.domain.services.promise_fulfillment_service.DncService') as MockDnc:
            MockDnc.return_value.is_blocked = AsyncMock(return_value=False)

            with patch('app.domain.services.promise_fulfillment_service.redis_client') as mock_redis:
                # Redis reports already sent
                mock_redis.exists = AsyncMock(return_value=True)

                promise = DetectedPromise(
                    asset_type="registration_link",
                    confidence=0.9,
                    original_text="I'll text you the registration link"
                )

                result = await service.fulfill_promise(
                    tenant_id=1,
                    conversation_id=100,
                    promise=promise,
                    phone="+15551234567",
                )

                assert result["status"] == "skipped"
                assert result["reason"] == "already_sent_recently"


class TestRegistrationUrlBuilder:
    """Tests for the registration URL builder utility."""

    def test_build_url_all_locations(self):
        """Test URL building for all valid locations."""
        from app.utils.registration_url_builder import build_registration_url

        # Test all three locations
        url_lalang = build_registration_url("LALANG")
        assert "loc=LALANG" in url_lalang

        url_cypress = build_registration_url("LAFCypress")
        assert "loc=LAFCypress" in url_cypress

        url_spring = build_registration_url("24Spring")
        assert "loc=24Spring" in url_spring

    def test_build_url_with_type(self):
        """Test URL building with type parameter."""
        from app.utils.registration_url_builder import build_registration_url

        url = build_registration_url("LAFCypress", "Adult Level 3")
        assert "loc=LAFCypress" in url
        assert "type=Adult%20Level%203" in url

    def test_build_url_invalid_location_raises(self):
        """Test that invalid location raises error."""
        from app.utils.registration_url_builder import (
            build_registration_url,
            InvalidLocationCodeError,
        )

        with pytest.raises(InvalidLocationCodeError):
            build_registration_url("INVALID_LOCATION")

    def test_build_url_invalid_type_raises(self):
        """Test that invalid type raises error."""
        from app.utils.registration_url_builder import (
            build_registration_url,
            InvalidTypeCodeError,
        )

        with pytest.raises(InvalidTypeCodeError):
            build_registration_url("LAFCypress", "Invalid Level")

    def test_level_name_to_type_code(self):
        """Test level name to type code mapping."""
        from app.utils.registration_url_builder import LEVEL_NAME_TO_TYPE_CODE

        # Test a few mappings
        assert LEVEL_NAME_TO_TYPE_CODE["Adult Level 3"] == "Adult%20Level%203"
        assert LEVEL_NAME_TO_TYPE_CODE["Starfish"] == "Starfish"
        assert LEVEL_NAME_TO_TYPE_CODE["Young Adult 2"] == "Young%20Adult%202"
        assert LEVEL_NAME_TO_TYPE_CODE["Turtle 1"] == "Turtle%201"
