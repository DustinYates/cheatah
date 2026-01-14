"""Voice bot evaluation harness for TTFA and hallucination testing.

This module provides a lightweight evaluation harness for:
1. Testing time-to-first-audio (TTFA) latency
2. Detecting hallucination regressions
3. Validating response quality against golden transcripts

Run with: pytest tests/test_voice_eval_harness.py -v
"""

import pytest
import time
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass

from app.domain.services.voice_service import (
    VoiceService,
    VoiceIntent,
)


@pytest.fixture
def voice_service():
    """Create a VoiceService instance with mocked dependencies."""
    mock_session = MagicMock()
    with patch('app.domain.services.voice_service.LLMOrchestrator'):
        service = VoiceService(mock_session)
        service.llm_orchestrator = MagicMock()
        service.llm_orchestrator.generate = AsyncMock(return_value='{"name": null, "reason": null, "urgency": "medium", "preferred_callback_time": null}')
        return service


@dataclass
class EvalCase:
    """A test case for voice evaluation."""
    name: str
    transcript: str
    expected_behaviors: list[str]  # What the response should do
    forbidden_behaviors: list[str]  # What the response should NOT do
    known_facts: str | None = None  # Known facts to validate against


# Golden test cases for hallucination detection
HALLUCINATION_EVAL_CASES = [
    EvalCase(
        name="unknown_pricing",
        transcript="How much does it cost?",
        expected_behaviors=[
            "admits_uncertainty",  # Should say it doesn't have pricing info
            "offers_follow_up",    # Should offer to have someone follow up
        ],
        forbidden_behaviors=[
            "invents_price",       # Should NOT make up a price
            "invents_number",      # Should NOT make up a phone number
        ],
        known_facts="VERIFIED BUSINESS FACTS:\n- Business Name: Test Company\n- (No pricing information configured)",
    ),
    EvalCase(
        name="unknown_hours",
        transcript="What are your hours?",
        expected_behaviors=[
            "admits_uncertainty",
        ],
        forbidden_behaviors=[
            "invents_hours",       # Should NOT make up hours
        ],
        known_facts="VERIFIED BUSINESS FACTS:\n- Business Name: Test Company\n- (No hours configured)",
    ),
    EvalCase(
        name="unknown_address",
        transcript="Where are you located?",
        expected_behaviors=[
            "admits_uncertainty",
        ],
        forbidden_behaviors=[
            "invents_address",     # Should NOT make up an address
        ],
        known_facts="VERIFIED BUSINESS FACTS:\n- Business Name: Test Company\n- (No location configured)",
    ),
    EvalCase(
        name="known_business_name",
        transcript="What company is this?",
        expected_behaviors=[
            "uses_known_fact",     # Should use the business name from facts
        ],
        forbidden_behaviors=[],
        known_facts="VERIFIED BUSINESS FACTS:\n- Business Name: Acme Widgets Inc.",
    ),
]


class TestHallucinationGuards:
    """Tests for hallucination detection and blocking."""

    def test_detects_invented_phone_number(self, voice_service):
        """Test that invented phone numbers are flagged."""
        response = "You can reach us at 555-123-4567 for more information."
        known_facts = "VERIFIED BUSINESS FACTS:\n- Business Name: Test Company"
        
        result = voice_service._detect_potential_hallucination(response, known_facts)
        assert result is True, "Should detect invented phone number"

    def test_allows_known_phone_number(self, voice_service):
        """Test that phone numbers in known facts are allowed."""
        response = "You can reach us at 555-123-4567 for more information."
        known_facts = "VERIFIED BUSINESS FACTS:\n- Phone Number: 555-123-4567"
        
        result = voice_service._detect_potential_hallucination(response, known_facts)
        assert result is False, "Should allow phone number from known facts"

    def test_detects_invented_email(self, voice_service):
        """Test that invented emails are flagged."""
        response = "Email us at info@example.com for details."
        known_facts = "VERIFIED BUSINESS FACTS:\n- Business Name: Test Company"
        
        result = voice_service._detect_potential_hallucination(response, known_facts)
        assert result is True, "Should detect invented email"

    def test_allows_known_email(self, voice_service):
        """Test that emails in known facts are allowed."""
        response = "Email us at info@example.com for details."
        known_facts = "VERIFIED BUSINESS FACTS:\n- Email: info@example.com"
        
        result = voice_service._detect_potential_hallucination(response, known_facts)
        assert result is False, "Should allow email from known facts"

    def test_detects_invented_url(self, voice_service):
        """Test that invented URLs are flagged."""
        response = "Visit www.example.com for more info."
        known_facts = "VERIFIED BUSINESS FACTS:\n- Business Name: Test Company"
        
        result = voice_service._detect_potential_hallucination(response, known_facts)
        assert result is True, "Should detect invented URL"

    def test_allows_known_url(self, voice_service):
        """Test that URLs in known facts are allowed."""
        response = "Visit www.example.com for more info."
        known_facts = "VERIFIED BUSINESS FACTS:\n- Website: www.example.com"
        
        result = voice_service._detect_potential_hallucination(response, known_facts)
        assert result is False, "Should allow URL from known facts"

    def test_detects_invented_address(self, voice_service):
        """Test that invented addresses are flagged."""
        response = "We're located at 123 Main Street."
        known_facts = "VERIFIED BUSINESS FACTS:\n- Business Name: Test Company"
        
        result = voice_service._detect_potential_hallucination(response, known_facts)
        assert result is True, "Should detect invented address"

    def test_guardrails_block_hallucinated_content(self, voice_service):
        """Test that guardrails return safe fallback for hallucinated content."""
        response = "Our pricing starts at $99. Call us at 555-555-1234."
        known_facts = "VERIFIED BUSINESS FACTS:\n- Business Name: Test Company"
        
        result = voice_service._apply_response_guardrails(response, known_facts)
        
        # Should return safe fallback, not the original response
        assert "555-555-1234" not in result
        assert "don't have" in result.lower() or "take your information" in result.lower()


class TestFastIntentDetection:
    """Tests for the TTFA-optimized intent detection."""

    def test_fast_intent_is_synchronous(self, voice_service):
        """Test that fast intent detection doesn't require await."""
        # This should work without async/await
        result = voice_service._detect_intent_fast("How much does it cost?")
        assert result == VoiceIntent.PRICING_INFO

    def test_fast_intent_detects_pricing(self, voice_service):
        """Test fast detection of pricing intent."""
        test_cases = [
            "How much does it cost?",
            "What are your prices?",
            "What's the fee?",
        ]
        for text in test_cases:
            result = voice_service._detect_intent_fast(text)
            assert result == VoiceIntent.PRICING_INFO, f"Failed for: {text}"

    def test_fast_intent_detects_hours(self, voice_service):
        """Test fast detection of hours/location intent."""
        test_cases = [
            "What are your hours?",
            "When do you open?",
            "Where are you located?",
        ]
        for text in test_cases:
            result = voice_service._detect_intent_fast(text)
            assert result == VoiceIntent.HOURS_LOCATION, f"Failed for: {text}"

    def test_fast_intent_detects_booking(self, voice_service):
        """Test fast detection of booking intent."""
        test_cases = [
            "I want to book an appointment",
            "Can I schedule a lesson?",
        ]
        for text in test_cases:
            result = voice_service._detect_intent_fast(text)
            assert result == VoiceIntent.BOOKING_REQUEST, f"Failed for: {text}"

    def test_fast_intent_returns_general_for_ambiguous(self, voice_service):
        """Test that ambiguous messages return general inquiry (no LLM call)."""
        # Ambiguous messages that would trigger LLM in the full version
        test_cases = [
            "Hello",
            "Hi there",
            "I'm interested",
        ]
        for text in test_cases:
            result = voice_service._detect_intent_fast(text)
            assert result == VoiceIntent.GENERAL_INQUIRY, f"Failed for: {text}"


class TestTTFAMetrics:
    """Tests for TTFA latency tracking."""

    def test_fast_intent_is_fast(self, voice_service):
        """Test that fast intent detection completes quickly."""
        start = time.time()
        for _ in range(100):
            voice_service._detect_intent_fast("How much does it cost?")
        elapsed = time.time() - start
        
        # 100 iterations should complete in under 10ms
        assert elapsed < 0.01, f"Fast intent took {elapsed*1000:.1f}ms for 100 iterations"

    def test_hallucination_check_is_fast(self, voice_service):
        """Test that hallucination detection completes quickly."""
        response = "This is a test response with some text that should be checked."
        known_facts = "VERIFIED BUSINESS FACTS:\n- Business Name: Test Company"
        
        start = time.time()
        for _ in range(100):
            voice_service._detect_potential_hallucination(response, known_facts)
        elapsed = time.time() - start
        
        # 100 iterations should complete in under 50ms
        assert elapsed < 0.05, f"Hallucination check took {elapsed*1000:.1f}ms for 100 iterations"


class TestPromptGrounding:
    """Tests for the grounding facts system."""

    def test_format_business_hours(self, voice_service):
        """Test business hours formatting."""
        hours = {
            "monday": {"start": "09:00", "end": "17:00"},
            "tuesday": {"start": "09:00", "end": "17:00"},
            "wednesday": {"start": "09:00", "end": "17:00"},
            "thursday": {"start": "09:00", "end": "17:00"},
            "friday": {"start": "09:00", "end": "17:00"},
        }
        
        result = voice_service._format_business_hours(hours)
        
        assert "Monday: 09:00-17:00" in result
        assert "Friday: 09:00-17:00" in result
        # Weekend should not be included since not in hours dict
        assert "Saturday" not in result
        assert "Sunday" not in result

    def test_format_empty_business_hours(self, voice_service):
        """Test formatting with empty hours dict."""
        result = voice_service._format_business_hours({})
        assert result == ""

    def test_format_none_business_hours(self, voice_service):
        """Test formatting with None hours."""
        result = voice_service._format_business_hours(None)
        assert result == ""


class TestResponseQuality:
    """Tests for response quality characteristics."""

    def test_response_length_within_limits(self, voice_service):
        """Test that guardrails enforce max response length."""
        long_response = "This is a sentence. " * 50
        result = voice_service._apply_response_guardrails(long_response)
        
        assert len(result) <= voice_service.MAX_RESPONSE_CHARS

    def test_markdown_is_removed(self, voice_service):
        """Test that markdown formatting is stripped."""
        response = "Here's **bold** and *italic* text with `code` and [links](http://example.com)."
        result = voice_service._apply_response_guardrails(response)
        
        assert "**" not in result
        assert "*" not in result
        assert "`" not in result
        assert "http://" not in result

    def test_contractions_are_applied(self, voice_service):
        """Test that formal text is converted to contractions."""
        response = "I am happy to help. You are welcome to call back."
        result = voice_service._post_process_for_speech(response)

        assert "I'm" in result
        assert "you're" in result.lower()


# Benchmark utilities for TTFA tracking
class TTFABenchmark:
    """Utility class for tracking TTFA metrics."""
    
    def __init__(self):
        self.measurements = []
    
    def record(self, ttfa_ms: float, test_name: str):
        """Record a TTFA measurement."""
        self.measurements.append({
            "test": test_name,
            "ttfa_ms": ttfa_ms,
        })
    
    def summary(self) -> dict:
        """Get summary statistics."""
        if not self.measurements:
            return {"count": 0}
        
        ttfa_values = [m["ttfa_ms"] for m in self.measurements]
        return {
            "count": len(ttfa_values),
            "min_ms": min(ttfa_values),
            "max_ms": max(ttfa_values),
            "avg_ms": sum(ttfa_values) / len(ttfa_values),
        }


# Golden transcript test runner
def evaluate_response_against_case(response: str, case: EvalCase) -> dict:
    """Evaluate a response against expected behaviors.
    
    Args:
        response: The LLM response to evaluate
        case: The evaluation case with expected behaviors
        
    Returns:
        Dict with pass/fail for each behavior
    """
    results = {}
    lower_response = response.lower()
    
    # Check expected behaviors
    for behavior in case.expected_behaviors:
        if behavior == "admits_uncertainty":
            results[behavior] = any(phrase in lower_response for phrase in [
                "don't have", "not sure", "don't know", "unable to",
                "can't find", "no information", "not available",
            ])
        elif behavior == "offers_follow_up":
            results[behavior] = any(phrase in lower_response for phrase in [
                "get back to you", "follow up", "have someone",
                "take your", "contact you", "call you back",
            ])
        elif behavior == "uses_known_fact":
            # Check if known facts content appears in response
            if case.known_facts:
                for line in case.known_facts.split("\n"):
                    if ":" in line and "-" in line:
                        value = line.split(":")[-1].strip()
                        if value and len(value) > 3 and value.lower() in lower_response:
                            results[behavior] = True
                            break
                else:
                    results[behavior] = False
        else:
            results[behavior] = False  # Unknown behavior
    
    # Check forbidden behaviors
    for behavior in case.forbidden_behaviors:
        if behavior == "invents_price":
            # Look for price patterns like $XX, XX dollars
            import re
            results[f"no_{behavior}"] = not bool(re.search(r'\$\d+|\d+\s*dollars?', lower_response))
        elif behavior == "invents_number":
            import re
            # Check for phone number patterns not in known facts
            phone_pattern = r'\b(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)?\d{3}[-.\s]?\d{4}\b'
            matches = re.findall(phone_pattern, response)
            if matches and case.known_facts:
                for match in matches:
                    if match not in case.known_facts:
                        results[f"no_{behavior}"] = False
                        break
                else:
                    results[f"no_{behavior}"] = True
            else:
                results[f"no_{behavior}"] = len(matches) == 0
        elif behavior == "invents_hours":
            import re
            # Look for time patterns
            time_pattern = r'\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM)'
            results[f"no_{behavior}"] = not bool(re.search(time_pattern, response))
        elif behavior == "invents_address":
            import re
            # Look for address patterns
            addr_pattern = r'\b\d{1,5}\s+(?:[a-zA-Z]+\s+){1,3}(?:street|st|avenue|ave|road|rd|boulevard|blvd)\b'
            results[f"no_{behavior}"] = not bool(re.search(addr_pattern, lower_response))
        else:
            results[f"no_{behavior}"] = True
    
    return results

