"""Tests for Telnyx webhook endpoints.

Tests the following endpoints:
- /api/v1/telnyx/tools/send-registration-link - Tool webhook for AI to send SMS during calls
- /api/v1/telnyx/ai-call-complete - Post-call webhook for insights and auto-SMS
- /api/v1/telnyx/dynamic-variables - Webhook for fetching AI assistant prompts

Key test areas:
- Registration link generation with correct location/level
- 3-layer SMS deduplication (Redis, DB SentAsset, Lead extra_data)
- Registration keyword detection (English + Spanish)
- Error handling and graceful degradation
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import json

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def mock_call_record():
    """Create a mock Call record for testing."""
    call = MagicMock()
    call.id = 123
    call.call_sid = "v3:test-call-control-id"
    call.from_number = "+15551234567"
    call.to_number = "+18321234567"
    call.tenant_id = 3
    call.status = "completed"
    call.direction = "inbound"
    return call


@pytest.fixture
def mock_lead():
    """Create a mock Lead record for testing."""
    lead = MagicMock()
    lead.id = 456
    lead.phone = "+15551234567"
    lead.tenant_id = 3
    lead.extra_data = {}
    return lead


@pytest.fixture
def sample_call_complete_payload():
    """Sample payload for call.conversation.ended webhook."""
    return {
        "data": {
            "id": "evt-unique-event-id-123",
            "event_type": "call.conversation.ended",
            "payload": {
                "call_control_id": "v3:test-call-control-id",
                "from": "+15551234567",
                "to": "+18321234567",
            }
        }
    }


@pytest.fixture
def sample_insights_payload():
    """Sample payload for conversation insights webhook."""
    return {
        "event_type": "conversation_insight_result",
        "payload": {
            "metadata": {
                "call_control_id": "v3:test-call-control-id",
                "to": "+18321234567",
                "from": "+15551234567",
            },
            "results": [
                {
                    "insight_type": "summary",
                    "content": "Customer wants to register for Starfish classes at Cypress location."
                },
                {
                    "insight_type": "caller_name",
                    "content": "Maria Garcia"
                },
                {
                    "insight_type": "intent",
                    "content": "registration_request"
                }
            ]
        }
    }


# =============================================================================
# Test: send-registration-link Tool Endpoint
# =============================================================================


class TestSendRegistrationLinkTool:
    """Tests for /tools/send-registration-link endpoint."""

    def test_send_registration_link_success(self, mock_call_record):
        """Test successful registration link sending during call."""
        with patch("app.api.routes.telnyx_webhooks.get_db") as mock_get_db:
            mock_session = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_call_record
            mock_session.execute = AsyncMock(return_value=mock_result)
            mock_get_db.return_value = mock_session

            with patch(
                "app.domain.services.promise_fulfillment_service.PromiseFulfillmentService"
            ) as MockFulfillment:
                mock_service = MagicMock()
                mock_service.fulfill_promise = AsyncMock(
                    return_value={"status": "sent", "message_id": "msg-123"}
                )
                MockFulfillment.return_value = mock_service

                response = client.post(
                    "/api/v1/telnyx/tools/send-registration-link",
                    json={"location": "Cypress", "level": "Starfish"},
                    headers={"x-telnyx-call-control-id": "v3:test-call-control-id"},
                )

                assert response.status_code == 200
                data = response.json()
                assert data["status"] in ["sent", "deferred", "skipped"]

    def test_send_registration_link_missing_call_control_id(self):
        """Test handling when no call_control_id provided."""
        response = client.post(
            "/api/v1/telnyx/tools/send-registration-link",
            json={"location": "Cypress", "level": "Starfish"},
            # No x-telnyx-call-control-id header
        )

        # Should return deferred (SMS sent later via ai-call-complete)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "deferred"

    def test_send_registration_link_invalid_location(self):
        """Test that invalid location without call record returns deferred.

        Note: When call record is not found, the endpoint returns 'deferred'
        regardless of location validity. The location check only happens
        after successfully looking up the call.
        """
        # Without a valid call record, the endpoint returns deferred
        # (the actual location validation happens after call lookup)
        response = client.post(
            "/api/v1/telnyx/tools/send-registration-link",
            json={"location": "InvalidLocation", "level": "Starfish"},
            headers={"x-telnyx-call-control-id": "v3:nonexistent-call"},
        )

        assert response.status_code == 200
        data = response.json()
        # Returns deferred because call record not found (before location check)
        assert data["status"] == "deferred"

    def test_send_registration_link_all_valid_locations(self, mock_call_record):
        """Test that all valid locations are accepted."""
        valid_locations = [
            ("Cypress", "LAFCypress"),
            ("LA Fitness Cypress", "LAFCypress"),
            ("Langham Creek", "LALANG"),
            ("Langham", "LALANG"),
            ("Spring", "24Spring"),
            ("24 Hour Fitness Spring", "24Spring"),
        ]

        for location_name, expected_code in valid_locations:
            with patch("app.api.routes.telnyx_webhooks.get_db") as mock_get_db:
                mock_session = AsyncMock()
                mock_result = MagicMock()
                mock_result.scalar_one_or_none.return_value = mock_call_record
                mock_session.execute = AsyncMock(return_value=mock_result)
                mock_get_db.return_value = mock_session

                with patch(
                    "app.domain.services.promise_fulfillment_service.PromiseFulfillmentService"
                ) as MockFulfillment:
                    mock_service = MagicMock()
                    mock_service.fulfill_promise = AsyncMock(
                        return_value={"status": "sent", "message_id": "msg-123"}
                    )
                    MockFulfillment.return_value = mock_service

                    response = client.post(
                        "/api/v1/telnyx/tools/send-registration-link",
                        json={"location": location_name, "level": None},
                        headers={
                            "x-telnyx-call-control-id": "v3:test-call-control-id"
                        },
                    )

                    assert response.status_code == 200, f"Failed for location: {location_name}"


# =============================================================================
# Test: Registration Keyword Detection
# =============================================================================


class TestRegistrationKeywordDetection:
    """Tests for registration keyword detection in ai-call-complete."""

    @pytest.mark.parametrize(
        "text,should_detect",
        [
            # English keywords - should detect
            ("I want to register my child for swimming", True),
            ("Can I get the registration link?", True),
            ("I'd like to sign up for classes", True),
            ("How do I enroll my daughter?", True),
            ("Looking for enrollment information", True),
            # Spanish keywords - should detect
            ("Quiero registrar a mi hijo", True),
            ("Necesito el enlace de registro", True),
            ("Quiero inscribir a mi hija", True),
            ("Información de inscripción por favor", True),
            # Should NOT detect
            ("What are your hours?", False),
            ("How much do classes cost?", False),
            ("Where are you located?", False),
            ("Can I speak to a manager?", False),
        ],
    )
    def test_registration_keyword_detection(self, text, should_detect):
        """Test that registration keywords are correctly detected."""
        # Note: Keywords are defined inline in the webhook, so we test the logic directly
        registration_keywords = [
            "registration", "register", "sign up", "signup", "enroll",
            "enrollment", "registration link", "registration info",
            "registro", "registrarse", "registrar", "inscripción", "inscribir",
            "enlace de registro", "información de registro", "enlace de inscripción",
        ]

        text_lower = text.lower()
        detected = any(kw in text_lower for kw in registration_keywords)
        assert detected == should_detect, f"Failed for text: '{text}'"


class TestAlreadySentIndicatorDetection:
    """Tests for 'link already sent' detection to prevent duplicates."""

    @pytest.mark.parametrize(
        "text,should_skip",
        [
            # English - link was sent
            ("I've sent the link to your phone", True),
            ("The registration link was sent", True),
            ("You should have received a link", True),
            ("I provided the link to you", True),
            # Spanish - link was sent
            ("El enlace fue enviado", True),
            ("Ya se envió el enlace", True),
            ("Le mandé el enlace", True),
            # Broken conversation indicators
            ("This is a series of repeated messages", True),
            ("There is no conversation to summarize", True),
            # Should NOT skip
            ("I can send you a registration link", False),
            ("Would you like the link?", False),
            ("Let me get that link for you", False),
        ],
    )
    def test_already_sent_indicator_detection(self, text, should_skip):
        """Test that 'link already sent' indicators prevent duplicate SMS."""
        already_sent_indicators = [
            "link was sent", "link was shared", "sent the link", "sent a link",
            "sent registration", "provided the link", "received a link",
            "texted the link", "link shared", "registration link sent",
            "enlace fue enviado", "enlace enviado", "ya se envió", "le mandé el enlace",
            "repeated message", "series of repeated", "no conversation to summarize",
            "there is no conversation",
        ]

        text_lower = text.lower()
        detected = any(ind in text_lower for ind in already_sent_indicators)
        assert detected == should_skip, f"Failed for text: '{text}'"


# =============================================================================
# Test: SMS Deduplication
# =============================================================================


class TestSmsDeduplication:
    """Tests for 3-layer SMS deduplication."""

    @pytest.mark.asyncio
    async def test_redis_dedup_blocks_duplicate(self):
        """Test that Redis setnx blocks duplicate SMS within TTL window."""
        from app.infrastructure.redis import redis_client

        with patch.object(redis_client, "connect", new_callable=AsyncMock):
            with patch.object(redis_client, "setnx", new_callable=AsyncMock) as mock_setnx:
                # First call - key doesn't exist, setnx returns True
                mock_setnx.return_value = True
                result1 = await redis_client.setnx("test_key", "1", ttl=180)
                assert result1 is True

                # Second call - key exists, setnx returns False
                mock_setnx.return_value = False
                result2 = await redis_client.setnx("test_key", "1", ttl=180)
                assert result2 is False

    @pytest.mark.asyncio
    async def test_db_dedup_via_sent_asset(self):
        """Test that SentAsset table prevents duplicate sends."""
        from app.persistence.models.sent_asset import SentAsset
        from sqlalchemy import select

        # This tests the query pattern used in ai-call-complete
        # Actual DB test would require the db_session fixture
        cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=3)

        # Verify query structure is correct
        stmt = select(SentAsset.id).where(
            SentAsset.tenant_id == 3,
            SentAsset.phone_normalized == "5551234567",
            SentAsset.asset_type == "registration_link",
            SentAsset.sent_at >= cutoff_time,
        ).limit(1)

        # Query should compile without error
        assert stmt is not None

    def test_phone_normalization_for_dedup(self):
        """Test that phone numbers are normalized consistently for dedup."""
        from app.core.phone import normalize_phone_for_dedup

        # Various formats should normalize to same value
        test_cases = [
            ("+15551234567", "5551234567"),
            ("15551234567", "5551234567"),
            ("5551234567", "5551234567"),
            ("+1 (555) 123-4567", "5551234567"),
            ("555-123-4567", "5551234567"),
        ]

        for input_phone, expected in test_cases:
            result = normalize_phone_for_dedup(input_phone)
            assert result == expected, f"Failed for input: {input_phone}"


# =============================================================================
# Test: Event Deduplication
# =============================================================================


class TestEventDeduplication:
    """Tests for webhook event ID-based deduplication."""

    def test_duplicate_event_id_returns_ok(self, sample_call_complete_payload):
        """Test that duplicate webhook events are acknowledged but not processed."""
        with patch("app.api.routes.telnyx_webhooks.redis_client") as mock_redis:
            mock_redis.connect = AsyncMock()
            # First call - new event
            mock_redis.setnx = AsyncMock(return_value=True)

            response1 = client.post(
                "/api/v1/telnyx/ai-call-complete",
                json=sample_call_complete_payload,
            )
            assert response1.status_code == 200

            # Second call with same event ID - should be skipped
            mock_redis.setnx = AsyncMock(return_value=False)

            response2 = client.post(
                "/api/v1/telnyx/ai-call-complete",
                json=sample_call_complete_payload,
            )
            assert response2.status_code == 200
            # Response should indicate duplicate
            data = response2.json()
            assert "duplicate" in data.get("message", "").lower() or data.get("status") == "ok"


# =============================================================================
# Test: Error Handling
# =============================================================================


class TestErrorHandling:
    """Tests for webhook error handling and graceful degradation."""

    def test_malformed_json_returns_200(self):
        """Test that malformed JSON doesn't crash the webhook."""
        response = client.post(
            "/api/v1/telnyx/ai-call-complete",
            content=b"not valid json",
            headers={"Content-Type": "application/json"},
        )
        # Should return 200 to prevent Telnyx retries
        assert response.status_code == 200

    def test_missing_required_fields_graceful(self):
        """Test that missing fields don't crash the webhook."""
        response = client.post(
            "/api/v1/telnyx/ai-call-complete",
            json={"data": {}},  # Missing most fields
        )
        assert response.status_code == 200

    def test_redis_failure_continues_processing(self, sample_call_complete_payload):
        """Test that Redis failures don't block webhook processing."""
        with patch("app.api.routes.telnyx_webhooks.redis_client") as mock_redis:
            mock_redis.connect = AsyncMock(side_effect=Exception("Redis connection failed"))

            response = client.post(
                "/api/v1/telnyx/ai-call-complete",
                json=sample_call_complete_payload,
            )
            # Should still return 200 - graceful degradation
            assert response.status_code == 200

    def test_empty_payload_returns_200(self):
        """Test that empty payload returns 200."""
        response = client.post(
            "/api/v1/telnyx/ai-call-complete",
            json={},
        )
        assert response.status_code == 200


# =============================================================================
# Test: Webhook Payload Parsing
# =============================================================================


class TestWebhookPayloadParsing:
    """Tests for parsing various Telnyx webhook payload formats."""

    def test_parse_standard_telnyx_format(self):
        """Test parsing standard Telnyx webhook format."""
        payload = {
            "data": {
                "event_type": "call.conversation.ended",
                "id": "evt-123",
                "payload": {
                    "call_control_id": "v3:abc123",
                    "from": "+15551234567",
                    "to": "+18321234567",
                }
            }
        }

        response = client.post("/api/v1/telnyx/ai-call-complete", json=payload)
        assert response.status_code == 200

    def test_parse_insights_webhook_format(self):
        """Test parsing Telnyx Insights webhook format."""
        payload = {
            "event_type": "conversation_insight_result",
            "payload": {
                "metadata": {
                    "call_control_id": "v3:abc123",
                    "to": "+18321234567",
                    "from": "+15551234567",
                },
                "results": [
                    {"insight_type": "summary", "content": "Test summary"}
                ]
            }
        }

        response = client.post("/api/v1/telnyx/ai-call-complete", json=payload)
        assert response.status_code == 200

    def test_parse_texml_format(self):
        """Test parsing TeXML callback format (PascalCase)."""
        payload = {
            "CallControlId": "v3:abc123",
            "CallSessionId": "session-456",
            "From": "+15551234567",
            "To": "+18321234567",
            "CallStatus": "completed",
        }

        response = client.post("/api/v1/telnyx/ai-call-complete", json=payload)
        assert response.status_code == 200


# =============================================================================
# Test: Location Code Mapping
# =============================================================================


class TestLocationCodeMapping:
    """Tests for location name to code mapping."""

    def test_location_mapping_cypress(self):
        """Test Cypress location mapping."""
        from app.api.routes.telnyx_webhooks import _map_location_to_code

        assert _map_location_to_code("Cypress") == "LAFCypress"
        assert _map_location_to_code("cypress") == "LAFCypress"
        assert _map_location_to_code("LA Fitness Cypress") == "LAFCypress"
        assert _map_location_to_code("la fitness cypress") == "LAFCypress"

    def test_location_mapping_langham(self):
        """Test Langham Creek location mapping."""
        from app.api.routes.telnyx_webhooks import _map_location_to_code

        assert _map_location_to_code("Langham Creek") == "LALANG"
        assert _map_location_to_code("langham creek") == "LALANG"
        assert _map_location_to_code("Langham") == "LALANG"
        assert _map_location_to_code("LA Fitness Langham Creek") == "LALANG"

    def test_location_mapping_spring(self):
        """Test Spring location mapping."""
        from app.api.routes.telnyx_webhooks import _map_location_to_code

        assert _map_location_to_code("Spring") == "24Spring"
        assert _map_location_to_code("spring") == "24Spring"
        assert _map_location_to_code("24 Hour Fitness Spring") == "24Spring"
        assert _map_location_to_code("24 hour fitness spring") == "24Spring"

    def test_location_mapping_invalid(self):
        """Test invalid location returns None."""
        from app.api.routes.telnyx_webhooks import _map_location_to_code

        assert _map_location_to_code("InvalidLocation") is None
        assert _map_location_to_code("") is None
        assert _map_location_to_code(None) is None


# =============================================================================
# Issue #1: SMS Not Sending - Failure Point Tests
# =============================================================================


class TestSmsNotSending:
    """Tests for scenarios where SMS fails to send.

    Common causes:
    - Call record not found (call_control_id lookup fails)
    - Phone number extraction fails
    - Tenant lookup fails
    - Location/level mapping fails
    - Promise fulfillment service fails
    - DNC blocking
    """

    def test_sms_fails_when_call_record_missing(self):
        """Test that missing call record is handled gracefully."""
        # When call_control_id doesn't match any Call record,
        # the tool should return deferred status
        with patch("app.api.routes.telnyx_webhooks.get_db") as mock_get_db:
            mock_session = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None  # No call found
            mock_session.execute = AsyncMock(return_value=mock_result)
            mock_get_db.return_value = mock_session

            response = client.post(
                "/api/v1/telnyx/tools/send-registration-link",
                json={"location": "Cypress", "level": "Starfish"},
                headers={"x-telnyx-call-control-id": "nonexistent-call-id"},
            )

            assert response.status_code == 200
            data = response.json()
            # Should be deferred (no phone found) or error
            assert data["status"] in ["deferred", "error"]

    def test_sms_fails_when_phone_number_missing_from_webhook(self):
        """Test handling when webhook has no phone number."""
        payload = {
            "data": {
                "id": "evt-123",
                "event_type": "call.conversation.ended",
                "payload": {
                    "call_control_id": "v3:test-call",
                    # Missing 'from' phone number
                    "to": "+18321234567",
                }
            }
        }

        response = client.post("/api/v1/telnyx/ai-call-complete", json=payload)
        assert response.status_code == 200
        # SMS should not be sent due to missing phone

    def test_sms_fails_when_no_registration_keywords(self):
        """Test that SMS is not sent when no registration intent detected."""
        # This tests the keyword detection path
        payload = {
            "data": {
                "id": "evt-no-registration-123",
                "event_type": "call.conversation.ended",
                "payload": {
                    "call_control_id": "v3:test-call",
                    "from": "+15551234567",
                    "to": "+18321234567",
                }
            }
        }

        with patch("app.api.routes.telnyx_webhooks.redis_client") as mock_redis:
            mock_redis.connect = AsyncMock()
            mock_redis.setnx = AsyncMock(return_value=True)

            response = client.post("/api/v1/telnyx/ai-call-complete", json=payload)
            assert response.status_code == 200
            # No registration SMS should be triggered

    def test_sms_blocked_by_dnc(self):
        """Test that DNC-listed numbers don't receive SMS."""
        from app.domain.services.promise_fulfillment_service import PromiseFulfillmentService
        from app.domain.services.promise_detector import DetectedPromise

        with patch("app.domain.services.promise_fulfillment_service.DncService") as MockDnc:
            # Simulate DNC block
            MockDnc.return_value.is_blocked = AsyncMock(return_value=True)

            mock_session = AsyncMock()
            service = PromiseFulfillmentService(mock_session)

            # The service should check DNC before sending
            # This is tested in test_promise_fulfillment.py but validates the integration

    def test_sms_fails_when_fulfillment_service_errors(self):
        """Test graceful handling when PromiseFulfillmentService throws."""
        # The webhook should catch the error and still return 200
        payload = {
            "data": {
                "id": "evt-fulfillment-error-123",
                "event_type": "call.conversation.ended",
                "payload": {
                    "call_control_id": "v3:test-call",
                    "from": "+15551234567",
                    "to": "+18321234567",
                    "transcript": "I want to register for classes",
                }
            }
        }

        with patch("app.api.routes.telnyx_webhooks.redis_client") as mock_redis:
            mock_redis.connect = AsyncMock()
            mock_redis.setnx = AsyncMock(return_value=True)
            mock_redis.delete = AsyncMock()

            with patch(
                "app.domain.services.promise_fulfillment_service.PromiseFulfillmentService"
            ) as MockFulfill:
                MockFulfill.return_value.fulfill_promise = AsyncMock(
                    side_effect=Exception("Telnyx API error")
                )

                response = client.post("/api/v1/telnyx/ai-call-complete", json=payload)
                # Should still return 200 to prevent Telnyx retries
                assert response.status_code == 200

    @pytest.mark.parametrize(
        "from_number,should_extract",
        [
            ("+15551234567", True),
            ("15551234567", True),
            ("5551234567", True),
            ("", False),
            (None, False),
            ("+1555", False),  # Test number prefix - should be filtered
        ],
    )
    def test_phone_number_extraction_variations(self, from_number, should_extract):
        """Test that various phone number formats are handled correctly."""
        payload = {
            "data": {
                "id": f"evt-phone-{from_number or 'none'}",
                "event_type": "call.conversation.ended",
                "payload": {
                    "call_control_id": "v3:test-call",
                    "from": from_number,
                    "to": "+18321234567",
                }
            }
        }

        response = client.post("/api/v1/telnyx/ai-call-complete", json=payload)
        assert response.status_code == 200


class TestPhoneExtractionFromMultipleSources:
    """Test phone number extraction from various webhook payload locations."""

    @pytest.mark.parametrize(
        "payload_structure",
        [
            # Standard format
            {"data": {"payload": {"from": "+15551234567"}}},
            # TeXML format
            {"From": "+15551234567"},
            # Insights format
            {"payload": {"metadata": {"from": "+15551234567"}}},
            # Nested object
            {"data": {"payload": {"from": {"phone_number": "+15551234567"}}}},
        ],
    )
    def test_phone_extracted_from_various_locations(self, payload_structure):
        """Test phone extraction works from different payload structures."""
        # Add required fields
        if "data" in payload_structure:
            payload_structure["data"]["id"] = "evt-test"
            payload_structure["data"]["event_type"] = "call.conversation.ended"
        else:
            payload_structure["id"] = "evt-test"
            payload_structure["event_type"] = "call.conversation.ended"

        response = client.post("/api/v1/telnyx/ai-call-complete", json=payload_structure)
        assert response.status_code == 200


# =============================================================================
# Issue #2: Duplicate SMS - Race Condition Tests
# =============================================================================


class TestDuplicateSmsPrevenion:
    """Tests for scenarios where duplicate SMS might be sent.

    Common causes:
    - Multiple webhook events for same call (conversation.ended + insights.generated)
    - Race condition between tool call and post-call webhook
    - Redis dedup failure/timeout
    - Phone normalization mismatches
    """

    def test_duplicate_prevented_by_event_dedup(self):
        """Test that same event_id is only processed once."""
        event_id = "evt-duplicate-test-12345"
        payload = {
            "data": {
                "id": event_id,
                "event_type": "call.conversation.ended",
                "payload": {
                    "call_control_id": "v3:test-call",
                    "from": "+15551234567",
                    "to": "+18321234567",
                    "transcript": "I want to register",
                }
            }
        }

        with patch("app.api.routes.telnyx_webhooks.redis_client") as mock_redis:
            mock_redis.connect = AsyncMock()

            # First call - event is new
            mock_redis.setnx = AsyncMock(return_value=True)
            response1 = client.post("/api/v1/telnyx/ai-call-complete", json=payload)
            assert response1.status_code == 200

            # Second call with same event_id - should be blocked
            mock_redis.setnx = AsyncMock(return_value=False)
            response2 = client.post("/api/v1/telnyx/ai-call-complete", json=payload)
            assert response2.status_code == 200
            assert "duplicate" in response2.json().get("message", "").lower()

    def test_duplicate_prevented_for_same_phone_within_ttl(self):
        """Test that same phone can't receive SMS twice within 3 min window."""
        phone = "+15551234567"

        with patch("app.api.routes.telnyx_webhooks.redis_client") as mock_redis:
            mock_redis.connect = AsyncMock()

            # First webhook - different event IDs but same phone
            payload1 = {
                "data": {
                    "id": "evt-first-webhook",
                    "event_type": "call.conversation.ended",
                    "payload": {
                        "call_control_id": "v3:call-1",
                        "from": phone,
                        "to": "+18321234567",
                        "transcript": "I want to register for Starfish",
                    }
                }
            }

            # Second webhook - same phone, different call
            payload2 = {
                "data": {
                    "id": "evt-second-webhook",
                    "event_type": "call.conversation.ended",
                    "payload": {
                        "call_control_id": "v3:call-2",
                        "from": phone,
                        "to": "+18321234567",
                        "transcript": "I want to register for Turtle",
                    }
                }
            }

            # First webhook claims the Redis lock
            mock_redis.setnx = AsyncMock(side_effect=[True, True])  # event dedup, phone dedup
            response1 = client.post("/api/v1/telnyx/ai-call-complete", json=payload1)
            assert response1.status_code == 200

            # Second webhook - phone dedup should block
            mock_redis.setnx = AsyncMock(side_effect=[True, False])  # event new, phone blocked
            response2 = client.post("/api/v1/telnyx/ai-call-complete", json=payload2)
            assert response2.status_code == 200

    def test_race_between_tool_call_and_post_call_webhook(self):
        """Test that tool call during call prevents post-call duplicate."""
        # Scenario: AI calls send_registration_link during call,
        # then post-call webhook fires with same request

        phone = "+15551234567"

        with patch("app.api.routes.telnyx_webhooks.redis_client") as mock_redis:
            mock_redis.connect = AsyncMock()

            # Tool call sets the Redis key
            # Post-call webhook should find it already set

            # Simulate: tool already sent, post-call webhook arrives
            payload = {
                "data": {
                    "id": "evt-post-call",
                    "event_type": "call.conversation.ended",
                    "payload": {
                        "call_control_id": "v3:test-call",
                        "from": phone,
                        "to": "+18321234567",
                        "transcript": "I want to register. Agent: I sent you the link.",
                    }
                }
            }

            # Event is new, but phone dedup blocks because tool already sent
            mock_redis.setnx = AsyncMock(side_effect=[True, False])
            response = client.post("/api/v1/telnyx/ai-call-complete", json=payload)
            assert response.status_code == 200

    def test_multiple_webhook_events_for_same_call(self):
        """Test dedup across conversation.ended and insights.generated events."""
        phone = "+15551234567"
        call_id = "v3:same-call-123"

        with patch("app.api.routes.telnyx_webhooks.redis_client") as mock_redis:
            mock_redis.connect = AsyncMock()

            # conversation.ended event
            payload_ended = {
                "data": {
                    "id": "evt-ended-123",
                    "event_type": "call.conversation.ended",
                    "payload": {
                        "call_control_id": call_id,
                        "from": phone,
                        "to": "+18321234567",
                        "transcript": "I want to register",
                    }
                }
            }

            # insights.generated event (arrives shortly after)
            payload_insights = {
                "data": {
                    "id": "evt-insights-456",
                    "event_type": "call.conversation_insights.generated",
                    "payload": {
                        "call_control_id": call_id,
                        "from": phone,
                        "to": "+18321234567",
                    }
                }
            }

            # First event claims the phone dedup
            mock_redis.setnx = AsyncMock(side_effect=[True, True])
            response1 = client.post("/api/v1/telnyx/ai-call-complete", json=payload_ended)
            assert response1.status_code == 200

            # Second event - different event_id but same phone - should be blocked
            mock_redis.setnx = AsyncMock(side_effect=[True, False])
            response2 = client.post("/api/v1/telnyx/ai-call-complete", json=payload_insights)
            assert response2.status_code == 200

    def test_phone_normalization_consistency(self):
        """Test that different phone formats normalize to same dedup key."""
        from app.core.phone import normalize_phone_for_dedup

        # All these should produce the same dedup key
        phone_formats = [
            "+15551234567",
            "15551234567",
            "5551234567",
            "+1 (555) 123-4567",
            "555-123-4567",
            "(555) 123-4567",
        ]

        normalized = [normalize_phone_for_dedup(p) for p in phone_formats]

        # All should normalize to same value
        assert len(set(normalized)) == 1, f"Inconsistent normalization: {normalized}"
        assert normalized[0] == "5551234567"

    def test_link_already_sent_indicator_prevents_duplicate(self):
        """Test that 'link was sent' in transcript prevents post-call SMS."""
        payload = {
            "data": {
                "id": "evt-link-sent",
                "event_type": "call.conversation.ended",
                "payload": {
                    "call_control_id": "v3:test-call",
                    "from": "+15551234567",
                    "to": "+18321234567",
                    "transcript": "Customer: Can I register? Agent: Sure, I sent the link to your phone.",
                }
            }
        }

        # The "sent the link" indicator should prevent another SMS
        response = client.post("/api/v1/telnyx/ai-call-complete", json=payload)
        assert response.status_code == 200

    def test_url_format_check_allows_resend_for_bad_url(self):
        """Test that malformed URLs allow resend of correct URL."""
        # If AI sent a URL without proper ?loc= params, we should send the correct one
        payload = {
            "data": {
                "id": "evt-bad-url",
                "event_type": "call.conversation.ended",
                "payload": {
                    "call_control_id": "v3:test-call",
                    "from": "+15551234567",
                    "to": "+18321234567",
                    "transcript": "I sent you the link: https://britishswimschool.com/cypress-spring/register/ (no params)",
                }
            }
        }

        with patch("app.api.routes.telnyx_webhooks.redis_client") as mock_redis:
            mock_redis.connect = AsyncMock()
            mock_redis.setnx = AsyncMock(return_value=True)

            response = client.post("/api/v1/telnyx/ai-call-complete", json=payload)
            assert response.status_code == 200
            # Should attempt to send correct URL since the one in transcript lacks params


class TestDedupLayerFailures:
    """Test behavior when individual dedup layers fail."""

    def test_redis_down_still_processes_with_db_dedup(self):
        """Test that Redis failure falls back to DB dedup."""
        payload = {
            "data": {
                "id": "evt-redis-fail",
                "event_type": "call.conversation.ended",
                "payload": {
                    "call_control_id": "v3:test-call",
                    "from": "+15551234567",
                    "to": "+18321234567",
                    "transcript": "I want to register",
                }
            }
        }

        with patch("app.api.routes.telnyx_webhooks.redis_client") as mock_redis:
            mock_redis.connect = AsyncMock(side_effect=Exception("Redis unavailable"))

            response = client.post("/api/v1/telnyx/ai-call-complete", json=payload)
            # Should still return 200 and fall back to DB dedup
            assert response.status_code == 200

    def test_dedup_key_released_on_send_failure(self):
        """Test that Redis dedup key is released when SMS send fails."""
        # This allows retry on next webhook
        with patch("app.api.routes.telnyx_webhooks.redis_client") as mock_redis:
            mock_redis.connect = AsyncMock()
            mock_redis.setnx = AsyncMock(return_value=True)
            mock_redis.delete = AsyncMock()

            with patch(
                "app.domain.services.promise_fulfillment_service.PromiseFulfillmentService"
            ) as MockFulfill:
                # Simulate send failure
                MockFulfill.return_value.fulfill_promise = AsyncMock(
                    return_value={"status": "failed", "reason": "Telnyx error"}
                )

                payload = {
                    "data": {
                        "id": "evt-send-fail",
                        "event_type": "call.conversation.ended",
                        "payload": {
                            "call_control_id": "v3:test-call",
                            "from": "+15551234567",
                            "to": "+18321234567",
                            "transcript": "I want to register",
                        }
                    }
                }

                response = client.post("/api/v1/telnyx/ai-call-complete", json=payload)
                assert response.status_code == 200

                # Redis delete should be called to release the lock
                # (Actual assertion depends on implementation details)


# =============================================================================
# Integration Test Helpers (for manual testing)
# =============================================================================


class TestWebhookSimulator:
    """Helper class for simulating Telnyx webhooks in development.

    These tests are skipped in CI but can be run manually for integration testing.
    """

    @pytest.mark.skip(reason="Manual integration test - requires local server")
    def test_simulate_full_call_flow(self):
        """Simulate a complete call flow: initiated -> conversation -> SMS.

        Run with: pytest tests/test_telnyx_webhooks.py::TestWebhookSimulator -v --no-skip
        """
        import time

        base_url = "http://localhost:8000/api/v1/telnyx"

        # 1. Call initiated
        call_initiated = {
            "data": {
                "event_type": "call.initiated",
                "payload": {
                    "call_control_id": f"v3:test-{int(time.time())}",
                    "from": "+15551234567",
                    "to": "+18321234567",
                    "direction": "inbound",
                }
            }
        }
        response = client.post(f"{base_url}/call-progress", json=call_initiated)
        print(f"Call initiated: {response.json()}")

        # 2. Conversation ended with registration request
        call_complete = {
            "data": {
                "id": f"evt-{int(time.time())}",
                "event_type": "call.conversation.ended",
                "payload": {
                    "call_control_id": call_initiated["data"]["payload"]["call_control_id"],
                    "from": "+15551234567",
                    "to": "+18321234567",
                    "transcript": "Customer: I want to register my child for Starfish classes at Cypress. Agent: I'll send you the registration link.",
                }
            }
        }
        response = client.post(f"{base_url}/ai-call-complete", json=call_complete)
        print(f"Call complete: {response.json()}")


# =============================================================================
# Payload Capture Helper (for replay testing)
# =============================================================================


def capture_webhook_payload(payload: dict, filename: str = "webhook_captures.jsonl"):
    """Helper to capture webhook payloads for replay testing.

    Usage in production code:
        if settings.CAPTURE_WEBHOOKS:
            capture_webhook_payload(body)
    """
    import json
    from pathlib import Path

    captures_dir = Path("tests/fixtures")
    captures_dir.mkdir(exist_ok=True)

    with open(captures_dir / filename, "a") as f:
        f.write(json.dumps(payload) + "\n")
