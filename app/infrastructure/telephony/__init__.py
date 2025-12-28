"""Telephony provider infrastructure."""

from app.infrastructure.telephony.base import (
    SmsProviderProtocol,
    VoiceProviderProtocol,
    SmsResult,
    PhoneNumberResult,
)
from app.infrastructure.telephony.factory import TelephonyProviderFactory

__all__ = [
    "SmsProviderProtocol",
    "VoiceProviderProtocol",
    "SmsResult",
    "PhoneNumberResult",
    "TelephonyProviderFactory",
]
