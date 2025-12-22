"""Business hours service for checking if current time is within business hours."""

import logging
from datetime import datetime
from typing import Any
import pytz

logger = logging.getLogger(__name__)


def is_within_business_hours(
    business_hours: dict[str, Any] | None,
    timezone_str: str = "UTC",
    business_hours_enabled: bool = False,
) -> bool:
    """Check if current time is within business hours.
    
    Args:
        business_hours: Dictionary with business hours by day of week.
            Format: {"monday": {"start": "09:00", "end": "17:00"}, ...}
        timezone_str: Timezone string (e.g., "America/New_York")
        business_hours_enabled: Whether business hours checking is enabled
        
    Returns:
        True if within business hours, False otherwise.
        Returns True if business_hours_enabled is False (always open).
    """
    if not business_hours_enabled or not business_hours:
        return True  # Always open if not configured
    
    try:
        # Get current time in tenant's timezone
        tz = pytz.timezone(timezone_str)
        now = datetime.now(tz)
        current_day = now.strftime("%A").lower()  # monday, tuesday, etc.
        current_time = now.time()
        
        # Get business hours for current day
        day_hours = business_hours.get(current_day)
        if not day_hours:
            return False  # Closed on this day
        
        start_str = day_hours.get("start")
        end_str = day_hours.get("end")
        
        if not start_str or not end_str:
            return False  # Invalid configuration
        
        # Parse time strings (format: "HH:MM" or "H:MM")
        start_time = datetime.strptime(start_str, "%H:%M").time()
        end_time = datetime.strptime(end_str, "%H:%M").time()
        
        # Check if current time is within range
        if start_time <= end_time:
            # Normal case: start < end (e.g., 9:00 - 17:00)
            return start_time <= current_time <= end_time
        else:
            # Overnight case: start > end (e.g., 22:00 - 02:00)
            return current_time >= start_time or current_time <= end_time
            
    except Exception as e:
        logger.error(f"Error checking business hours: {e}", exc_info=True)
        return True  # Default to open on error

