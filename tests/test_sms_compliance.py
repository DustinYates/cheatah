"""Tests for SMS compliance handling."""

import pytest

from app.domain.services.compliance_handler import ComplianceHandler


def test_stop_keyword_detection():
    """Test STOP keyword detection."""
    handler = ComplianceHandler()
    
    result = handler.check_compliance("STOP")
    assert result.action == "stop"
    assert not result.is_compliant
    assert result.response_message is not None
    
    result = handler.check_compliance("stopall")
    assert result.action == "stop"
    
    result = handler.check_compliance("unsubscribe")
    assert result.action == "stop"


def test_help_keyword_detection():
    """Test HELP keyword detection."""
    handler = ComplianceHandler()
    
    result = handler.check_compliance("HELP")
    assert result.action == "help"
    assert result.is_compliant
    assert result.response_message is not None
    
    result = handler.check_compliance("info")
    assert result.action == "help"


def test_opt_in_keyword_detection():
    """Test OPT-IN keyword detection."""
    handler = ComplianceHandler()
    
    result = handler.check_compliance("START")
    assert result.action == "opt_in"
    assert result.is_compliant
    
    result = handler.check_compliance("yes")
    assert result.action == "opt_in"


def test_normal_message():
    """Test normal message (no compliance keywords)."""
    handler = ComplianceHandler()
    
    result = handler.check_compliance("Hello, I need help")
    assert result.action == "allow"
    assert result.is_compliant
    assert result.response_message is None

