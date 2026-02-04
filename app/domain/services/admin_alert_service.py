"""Admin alert service for per-tenant issue notifications.

Sends SMS notifications to tenant admins when issues occur:
- SMS bursts (spam/loops)
- Anomaly alerts (volume drops, escalation spikes)
- Service health issues (API failures)

Each tenant can configure their own alert phone and enable/disable alerts
via escalation_settings in TenantPromptConfig:
- escalation_settings.admin_alerts_enabled (default: True)
- escalation_settings.alert_phone_override (or falls back to business profile phone)
"""

import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.models.anomaly_alert import AnomalyAlert
from app.persistence.models.service_health_incident import ServiceHealthIncident
from app.persistence.models.sms_burst_incident import SmsBurstIncident
from app.persistence.models.tenant import Tenant, TenantBusinessProfile
from app.persistence.models.tenant_sms_config import TenantSmsConfig
from app.settings import settings

logger = logging.getLogger(__name__)

# Cooldown periods to prevent notification spam (in minutes)
BURST_COOLDOWN_MINUTES = 30
ANOMALY_COOLDOWN_MINUTES = 60
SERVICE_HEALTH_COOLDOWN_MINUTES = 30

# Default error threshold for service health alerts
DEFAULT_ERROR_THRESHOLD = 3


class AdminAlertService:
    """Centralized service for admin notifications about system issues.

    Configuration is per-tenant via escalation_settings in TenantPromptConfig:
    {
        "escalation_settings": {
            "admin_alerts_enabled": true,  // Toggle alerts on/off
            "alert_phone_override": "+1234567890"  // Override destination phone
        }
    }
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialize admin alert service."""
        self.session = session

    async def _get_tenant_alert_settings(self, tenant_id: int) -> dict[str, Any]:
        """Get tenant's admin alert settings from escalation_settings.

        Returns dict with:
            - enabled: bool (default True)
            - alert_phone: str | None
        """
        from app.persistence.models.tenant_prompt_config import TenantPromptConfig

        try:
            stmt = select(TenantPromptConfig.config_json).where(
                TenantPromptConfig.tenant_id == tenant_id
            )
            result = await self.session.execute(stmt)
            config_json = result.scalar_one_or_none()

            if config_json:
                escalation_settings = config_json.get("escalation_settings", {})
                return {
                    "enabled": escalation_settings.get("admin_alerts_enabled", True),
                    "alert_phone": escalation_settings.get("alert_phone_override"),
                }
        except Exception as e:
            logger.warning(f"Failed to get alert settings for tenant {tenant_id}: {e}")

        return {"enabled": True, "alert_phone": None}

    async def notify_sms_burst(
        self,
        incident: SmsBurstIncident,
    ) -> dict[str, Any]:
        """Send admin notification for SMS burst incident.

        Args:
            incident: The SmsBurstIncident that was detected

        Returns:
            Dictionary with notification status and details
        """
        # Check per-tenant settings
        alert_settings = await self._get_tenant_alert_settings(incident.tenant_id)
        if not alert_settings["enabled"]:
            return {"status": "disabled", "reason": "admin_alerts_enabled is False for tenant"}

        # Check if already notified within cooldown period
        if incident.admin_notified_at:
            cooldown_cutoff = datetime.utcnow() - timedelta(minutes=BURST_COOLDOWN_MINUTES)
            if incident.admin_notified_at > cooldown_cutoff:
                logger.debug(
                    f"Skipping SMS burst notification - already notified at {incident.admin_notified_at}"
                )
                return {"status": "cooldown", "notified_at": incident.admin_notified_at.isoformat()}

        # Only notify for warning or higher severity
        if incident.severity not in ("warning", "high", "critical"):
            return {"status": "skipped", "reason": f"severity {incident.severity} too low"}

        # Get tenant name for the message
        tenant_name = await self._get_tenant_name(incident.tenant_id)

        # Format the notification message
        message = (
            f"[ALERT] SMS Burst - {tenant_name}\n"
            f"{incident.message_count} texts to {incident.to_number} "
            f"in {incident.time_window_seconds}s. "
            f"Cause: {incident.likely_cause or 'unknown'}"
        )

        # Send notification
        result = await self._send_admin_sms(incident.tenant_id, message)

        # Update incident with notification timestamp
        if result.get("status") == "sent":
            incident.admin_notified_at = datetime.utcnow()
            await self.session.commit()
            logger.info(
                f"Admin notified of SMS burst: incident_id={incident.id}, "
                f"tenant={incident.tenant_id}, severity={incident.severity}"
            )

        return result

    async def notify_anomaly(
        self,
        alert: AnomalyAlert,
    ) -> dict[str, Any]:
        """Send admin notification for anomaly alert.

        Args:
            alert: The AnomalyAlert that was created

        Returns:
            Dictionary with notification status and details
        """
        # Check per-tenant settings
        alert_settings = await self._get_tenant_alert_settings(alert.tenant_id)
        if not alert_settings["enabled"]:
            return {"status": "disabled", "reason": "admin_alerts_enabled is False for tenant"}

        # Check if already notified within cooldown period
        if alert.admin_notified_at:
            cooldown_cutoff = datetime.utcnow() - timedelta(minutes=ANOMALY_COOLDOWN_MINUTES)
            if alert.admin_notified_at > cooldown_cutoff:
                logger.debug(
                    f"Skipping anomaly notification - already notified at {alert.admin_notified_at}"
                )
                return {"status": "cooldown", "notified_at": alert.admin_notified_at.isoformat()}

        # Only notify for warning or critical (skip info)
        if alert.severity == "info":
            return {"status": "skipped", "reason": "info severity not notified"}

        # Get tenant name for the message
        tenant_name = await self._get_tenant_name(alert.tenant_id)

        # Calculate percent change
        if alert.baseline_value and alert.baseline_value > 0:
            percent_change = round(
                ((alert.current_value - alert.baseline_value) / alert.baseline_value) * 100
            )
        else:
            percent_change = 0

        # Format alert type for display
        alert_type_display = alert.alert_type.replace("_", " ").title()

        # Format the notification message
        message = (
            f"[ALERT] {alert_type_display} - {tenant_name}\n"
            f"{alert.metric_name}: {alert.current_value:.0f} vs baseline {alert.baseline_value:.0f} "
            f"({percent_change:+d}%)"
        )

        # Send notification
        result = await self._send_admin_sms(alert.tenant_id, message)

        # Update alert with notification timestamp
        if result.get("status") == "sent":
            alert.admin_notified_at = datetime.utcnow()
            await self.session.commit()
            logger.info(
                f"Admin notified of anomaly: alert_id={alert.id}, "
                f"tenant={alert.tenant_id}, type={alert.alert_type}"
            )

        return result

    async def notify_service_outage(
        self,
        incident: ServiceHealthIncident,
    ) -> dict[str, Any]:
        """Send admin notification for service health issue.

        Args:
            incident: The ServiceHealthIncident to notify about

        Returns:
            Dictionary with notification status and details
        """
        # For tenant-specific incidents, check per-tenant settings
        # For global incidents (no tenant_id), use global setting
        if incident.tenant_id:
            alert_settings = await self._get_tenant_alert_settings(incident.tenant_id)
            if not alert_settings["enabled"]:
                return {"status": "disabled", "reason": "admin_alerts_enabled is False for tenant"}
        else:
            # Global incident - use global setting
            if not settings.admin_alert_enabled:
                return {"status": "disabled", "reason": "global admin_alert_enabled is False"}

        # Check if already notified within cooldown period
        if incident.admin_notified_at:
            cooldown_cutoff = datetime.utcnow() - timedelta(minutes=SERVICE_HEALTH_COOLDOWN_MINUTES)
            if incident.admin_notified_at > cooldown_cutoff:
                logger.debug(
                    f"Skipping service outage notification - already notified at {incident.admin_notified_at}"
                )
                return {"status": "cooldown", "notified_at": incident.admin_notified_at.isoformat()}

        # Only notify for warning or critical severity
        if incident.severity not in ("warning", "critical"):
            return {"status": "skipped", "reason": f"severity {incident.severity} too low"}

        # Format the notification message
        if incident.tenant_id:
            tenant_name = await self._get_tenant_name(incident.tenant_id)
            message = (
                f"[CRITICAL] {incident.service_name.title()} Issue - {tenant_name}\n"
                f"{incident.error_count} {incident.error_type} errors. "
                f"Last: {(incident.error_message or 'unknown')[:80]}"
            )
        else:
            # Global incident
            message = (
                f"[CRITICAL] {incident.service_name.title()} Service Issue\n"
                f"{incident.error_count} {incident.error_type} errors. "
                f"Last: {(incident.error_message or 'unknown')[:80]}"
            )

        # Send notification (use global admin phone for global incidents)
        if incident.tenant_id:
            result = await self._send_admin_sms(incident.tenant_id, message)
        else:
            result = await self._send_global_admin_sms(message)

        # Update incident with notification timestamp
        if result.get("status") == "sent":
            incident.admin_notified_at = datetime.utcnow()
            await self.session.commit()
            logger.info(
                f"Admin notified of service outage: incident_id={incident.id}, "
                f"service={incident.service_name}, errors={incident.error_count}"
            )

        return result

    async def record_service_error(
        self,
        service_name: str,
        error_type: str,
        error_message: str | None = None,
        tenant_id: int | None = None,
    ) -> ServiceHealthIncident | None:
        """Record an external service error and notify if threshold reached.

        Args:
            service_name: Name of the service (telnyx, gmail, gemini, etc.)
            error_type: Type of error (timeout, auth_failed, rate_limited, api_error)
            error_message: Optional error message/details
            tenant_id: Optional tenant ID (None for global incidents)

        Returns:
            The ServiceHealthIncident if created/updated, None on error
        """
        try:
            # Look for existing active incident for this service+tenant+error_type
            stmt = (
                select(ServiceHealthIncident)
                .where(
                    ServiceHealthIncident.service_name == service_name,
                    ServiceHealthIncident.error_type == error_type,
                    ServiceHealthIncident.status == "active",
                )
            )
            if tenant_id:
                stmt = stmt.where(ServiceHealthIncident.tenant_id == tenant_id)
            else:
                stmt = stmt.where(ServiceHealthIncident.tenant_id.is_(None))

            stmt = stmt.order_by(ServiceHealthIncident.first_error_at.desc()).limit(1)
            result = await self.session.execute(stmt)
            existing = result.scalar_one_or_none()

            if existing:
                # Update existing incident
                existing.error_count += 1
                existing.last_error_at = datetime.utcnow()
                existing.error_message = error_message
                # Escalate severity based on error count
                if existing.error_count >= settings.admin_alert_error_threshold * 2:
                    existing.severity = "critical"
                elif existing.error_count >= settings.admin_alert_error_threshold:
                    existing.severity = "warning"
                await self.session.commit()
                incident = existing
            else:
                # Create new incident
                incident = ServiceHealthIncident(
                    tenant_id=tenant_id,
                    service_name=service_name,
                    error_type=error_type,
                    error_message=error_message,
                    error_count=1,
                    first_error_at=datetime.utcnow(),
                    last_error_at=datetime.utcnow(),
                    severity="info",  # Start at info, escalate based on count
                    status="active",
                )
                self.session.add(incident)
                await self.session.commit()
                await self.session.refresh(incident)

            # Check if we should notify (threshold reached and not already notified)
            if (
                incident.error_count >= settings.admin_alert_error_threshold
                and not incident.admin_notified_at
            ):
                await self.notify_service_outage(incident)

            return incident

        except Exception as e:
            logger.error(f"Failed to record service error: {e}", exc_info=True)
            return None

    async def _get_tenant_name(self, tenant_id: int) -> str:
        """Get tenant name for notification messages."""
        try:
            stmt = select(Tenant.name).where(Tenant.id == tenant_id)
            result = await self.session.execute(stmt)
            name = result.scalar_one_or_none()
            return name or f"Tenant {tenant_id}"
        except Exception:
            return f"Tenant {tenant_id}"

    async def _send_admin_sms(
        self,
        tenant_id: int,
        message: str,
        alert_phone: str | None = None,
    ) -> dict[str, Any]:
        """Send SMS notification to tenant admin using tenant's Telnyx config.

        Args:
            tenant_id: The tenant to send the alert for
            message: The alert message
            alert_phone: Pre-fetched alert phone (optional, will look up if not provided)

        Uses alert_phone_override from escalation_settings, or falls back to
        business profile phone.
        """
        from app.infrastructure.telephony.telnyx_provider import TelnyxSmsProvider

        try:
            # Get tenant's SMS config for Telnyx credentials
            stmt = select(TenantSmsConfig).where(TenantSmsConfig.tenant_id == tenant_id)
            result = await self.session.execute(stmt)
            sms_config = result.scalar_one_or_none()

            if not sms_config or not sms_config.telnyx_api_key:
                logger.warning(f"No Telnyx config for tenant {tenant_id}, cannot send admin SMS")
                return {"status": "not_configured", "reason": "no Telnyx config"}

            # Get destination phone if not provided
            to_number = alert_phone
            if not to_number:
                # Look up from escalation_settings
                alert_settings = await self._get_tenant_alert_settings(tenant_id)
                to_number = alert_settings.get("alert_phone")

            # Fall back to business profile phone
            if not to_number:
                stmt = select(TenantBusinessProfile.phone_number).where(
                    TenantBusinessProfile.tenant_id == tenant_id
                )
                result = await self.session.execute(stmt)
                to_number = result.scalar_one_or_none()

            if not to_number:
                logger.warning(f"No admin phone for tenant {tenant_id}")
                return {"status": "no_phone", "reason": "no destination phone configured"}

            # Normalize phone number to E.164
            if not to_number.startswith("+"):
                to_number = f"+1{to_number.replace('-', '').replace(' ', '').replace('(', '').replace(')', '')}"

            # Send via Telnyx
            provider = TelnyxSmsProvider(
                api_key=sms_config.telnyx_api_key,
                messaging_profile_id=sms_config.telnyx_messaging_profile_id,
            )

            sms_result = await provider.send_sms(
                to=to_number,
                from_=sms_config.telnyx_phone_number,
                body=message[:160],
            )

            logger.info(
                f"Admin alert SMS sent: tenant={tenant_id}, to={to_number}, "
                f"message_id={sms_result.message_id}"
            )

            return {
                "status": "sent",
                "message_id": sms_result.message_id,
                "to": to_number,
            }

        except Exception as e:
            logger.error(f"Failed to send admin SMS for tenant {tenant_id}: {e}", exc_info=True)
            return {"status": "error", "error": str(e)}

    async def _send_global_admin_sms(
        self,
        message: str,
    ) -> dict[str, Any]:
        """Send SMS to global admin phone (for system-wide issues).

        Uses ADMIN_ALERT_PHONE env var and a default tenant's Telnyx config.
        """
        from app.infrastructure.telephony.telnyx_provider import TelnyxSmsProvider

        if not settings.admin_alert_phone:
            logger.warning("No ADMIN_ALERT_PHONE configured, cannot send global admin SMS")
            return {"status": "not_configured", "reason": "ADMIN_ALERT_PHONE not set"}

        try:
            # Use first available tenant's Telnyx config (typically tenant_id=1)
            stmt = (
                select(TenantSmsConfig)
                .where(TenantSmsConfig.telnyx_api_key.isnot(None))
                .limit(1)
            )
            result = await self.session.execute(stmt)
            sms_config = result.scalar_one_or_none()

            if not sms_config:
                logger.warning("No Telnyx config available for global admin SMS")
                return {"status": "not_configured", "reason": "no Telnyx config available"}

            # Normalize destination phone
            to_number = settings.admin_alert_phone
            if not to_number.startswith("+"):
                to_number = f"+1{to_number.replace('-', '').replace(' ', '').replace('(', '').replace(')', '')}"

            # Send via Telnyx
            provider = TelnyxSmsProvider(
                api_key=sms_config.telnyx_api_key,
                messaging_profile_id=sms_config.telnyx_messaging_profile_id,
            )

            sms_result = await provider.send_sms(
                to=to_number,
                from_=sms_config.telnyx_phone_number,
                body=message[:160],
            )

            logger.info(
                f"Global admin alert SMS sent: to={to_number}, message_id={sms_result.message_id}"
            )

            return {
                "status": "sent",
                "message_id": sms_result.message_id,
                "to": to_number,
            }

        except Exception as e:
            logger.error(f"Failed to send global admin SMS: {e}", exc_info=True)
            return {"status": "error", "error": str(e)}
