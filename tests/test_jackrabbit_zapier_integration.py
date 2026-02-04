"""Tests to verify Jackrabbit API and Zapier integration patterns.

This test file documents and verifies the two integration patterns used:
1. Direct Jackrabbit API - for class schedule/openings data
2. Zapier middleware - for customer lookups by phone
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

# Test that Jackrabbit client uses direct API (not Zapier)


class TestJackrabbitDirectAPI:
    """Verify that class schedule fetching uses direct Jackrabbit API."""

    @pytest.mark.asyncio
    async def test_fetch_classes_calls_jackrabbit_directly(self):
        """Jackrabbit client should call OpeningsJson API directly, not Zapier."""
        from app.infrastructure.jackrabbit_client import fetch_classes, JACKRABBIT_OPENINGS_URL, _cache

        # Clear cache to ensure fresh request
        _cache.clear()

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "rows": [
                {
                    "id": "123",
                    "name": "Beginner Swim",
                    "location_name": "Main Pool",
                    "meeting_days": {"mon": True, "wed": True},
                    "start_time": "10:00",
                    "end_time": "11:00",
                    "openings": {"calculated_openings": 5},
                    "tuition": {"fee": 100},
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()

        with patch("app.infrastructure.jackrabbit_client.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_client.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await fetch_classes("test_org_id")

            # Verify direct Jackrabbit API was called
            mock_instance.get.assert_called_once_with(
                JACKRABBIT_OPENINGS_URL,
                params={"OrgID": "test_org_id"}
            )

            # Verify response was processed correctly
            assert len(result) == 1
            assert result[0]["name"] == "Beginner Swim"
            assert result[0]["openings"] == 5

    def test_jackrabbit_url_is_direct_api(self):
        """Verify JACKRABBIT_OPENINGS_URL points to Jackrabbit, not Zapier."""
        from app.infrastructure.jackrabbit_client import JACKRABBIT_OPENINGS_URL

        assert "jackrabbitclass.com" in JACKRABBIT_OPENINGS_URL
        assert "zapier" not in JACKRABBIT_OPENINGS_URL.lower()
        assert "OpeningsJson" in JACKRABBIT_OPENINGS_URL

    @pytest.mark.asyncio
    async def test_fetch_classes_caches_results(self):
        """Verify caching works to avoid excessive API calls."""
        from app.infrastructure.jackrabbit_client import fetch_classes, _cache

        # Clear cache
        _cache.clear()

        mock_response = MagicMock()
        mock_response.json.return_value = {"rows": []}
        mock_response.raise_for_status = MagicMock()

        with patch("app.infrastructure.jackrabbit_client.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_client.return_value.__aexit__ = AsyncMock(return_value=None)

            # First call should hit API
            await fetch_classes("cache_test_org")
            assert mock_instance.get.call_count == 1

            # Second call should use cache
            await fetch_classes("cache_test_org")
            assert mock_instance.get.call_count == 1  # Still 1, used cache


class TestZapierCustomerLookup:
    """Verify that customer lookups use Zapier middleware."""

    def test_zapier_service_exists(self):
        """Verify ZapierIntegrationService is used for customer operations."""
        from app.domain.services.zapier_integration_service import ZapierIntegrationService

        # Service should exist and have customer lookup method
        assert hasattr(ZapierIntegrationService, "send_customer_lookup")
        assert hasattr(ZapierIntegrationService, "send_customer_query")

    def test_customer_lookup_service_uses_zapier(self):
        """Verify CustomerLookupService delegates to Zapier, not direct Jackrabbit API."""
        from app.domain.services.customer_lookup_service import CustomerLookupService
        import inspect

        # Check the lookup_by_phone method uses zapier_service
        source = inspect.getsource(CustomerLookupService.lookup_by_phone)
        assert "zapier_service" in source
        assert "send_customer_lookup" in source

        # Verify it does NOT call jackrabbit_client directly
        assert "jackrabbit_client" not in source
        assert "OpeningsJson" not in source

    def test_zapier_service_sends_webhook_not_direct_api(self):
        """Verify Zapier service sends webhooks, not direct Jackrabbit calls."""
        from app.domain.services.zapier_integration_service import ZapierIntegrationService
        import inspect

        source = inspect.getsource(ZapierIntegrationService.send_customer_lookup)

        # Should use webhook_url from config
        assert "webhook_url" in source

        # Should NOT call Jackrabbit directly
        assert "jackrabbitclass.com" not in source
        assert "OpeningsJson" not in source


class TestIntegrationPatternSummary:
    """Summary tests documenting the two integration patterns."""

    def test_class_schedule_pattern(self):
        """
        Pattern 1: Class Schedule/Openings
        - Uses: Direct Jackrabbit API
        - Endpoint: https://app.jackrabbitclass.com/jr3.0/Openings/OpeningsJson
        - Auth: OrgID parameter only (public API)
        - Why: Public class data doesn't need customer-specific access
        """
        from app.infrastructure.jackrabbit_client import JACKRABBIT_OPENINGS_URL

        # Document the pattern
        assert "jackrabbitclass.com" in JACKRABBIT_OPENINGS_URL
        assert "Openings" in JACKRABBIT_OPENINGS_URL

    def test_customer_lookup_pattern(self):
        """
        Pattern 2: Customer Lookup/Query
        - Uses: Zapier webhook middleware
        - Flow: App -> Zapier Webhook -> Jackrabbit API -> Zapier Callback -> App
        - Auth: Jackrabbit API keys (1 and 2) passed through Zapier
        - Why: Customer data requires authenticated Jackrabbit API access,
               and Zapier handles the lookup logic + callback pattern
        """
        from app.domain.services.customer_lookup_service import CustomerLookupService

        # Verify the service exists and uses Zapier
        assert hasattr(CustomerLookupService, "lookup_by_phone")


class TestConfigRequirements:
    """Tests documenting config requirements for each pattern."""

    def test_jackrabbit_direct_requires_org_id(self):
        """Direct Jackrabbit API only needs Organization ID."""
        from app.infrastructure.jackrabbit_client import fetch_classes
        import inspect

        sig = inspect.signature(fetch_classes)
        params = list(sig.parameters.keys())

        # Only needs org_id
        assert "org_id" in params
        assert len(params) == 1

    def test_zapier_requires_webhook_and_api_keys(self):
        """Zapier integration requires webhook URL and Jackrabbit API keys."""
        from app.persistence.models.tenant_customer_service_config import TenantCustomerServiceConfig

        # Check model has required fields
        assert hasattr(TenantCustomerServiceConfig, "zapier_webhook_url")
        assert hasattr(TenantCustomerServiceConfig, "zapier_callback_secret")
        assert hasattr(TenantCustomerServiceConfig, "jackrabbit_api_key_1")
        assert hasattr(TenantCustomerServiceConfig, "jackrabbit_api_key_2")
