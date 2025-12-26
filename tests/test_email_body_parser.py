"""Tests for email body parser."""

import pytest

from app.domain.services.email_body_parser import EmailBodyParser


class TestEmailBodyParser:
    """Test cases for EmailBodyParser."""

    def setup_method(self):
        """Set up test fixtures."""
        self.parser = EmailBodyParser()

    def test_parse_structured_form_data(self):
        """Test parsing structured form data with standard format."""
        body = """
        Name: John Doe
        Email: john.doe@example.com
        Phone: (972) 464-6277
        Location Email: goswimcypressspring@britishswimschool.com
        Franchise Code: 545911
        """
        
        result = self.parser.parse(body)
        
        assert result["name"] == "John Doe"
        assert result["email"] == "john.doe@example.com"
        assert result["phone"] == "+19724646277"  # E.164 format
        assert "location email" in result["additional_fields"]
        assert result["additional_fields"]["location email"] == "goswimcypressspring@britishswimschool.com"
        assert "franchise code" in result["additional_fields"]

    def test_parse_varying_formats(self):
        """Test parsing with varying label formats."""
        body = """
        Student Name: Jane Smith
        E-mail: jane@example.com
        Phone Number: 972-464-6277
        """
        
        result = self.parser.parse(body)
        
        assert result["name"] == "Jane Smith"
        assert result["email"] == "jane@example.com"
        assert result["phone"] == "+19724646277"

    def test_parse_dash_separator(self):
        """Test parsing with dash separator."""
        body = """
        Name - Bob Johnson
        Email - bob@example.com
        Phone - (254) 640-0994
        """
        
        result = self.parser.parse(body)
        
        assert result["name"] == "Bob Johnson"
        assert result["email"] == "bob@example.com"
        assert result["phone"] == "+12546400994"

    def test_parse_email_with_name_format(self):
        """Test parsing email in 'Name <email>' format."""
        body = """
        Name: Kimi Knight
        Email: Dustin Yates <dyaters68@yahoo.com>
        Phone: (254) 640-0994
        """
        
        result = self.parser.parse(body)
        
        assert result["name"] == "Kimi Knight"
        assert result["email"] == "dyaters68@yahoo.com"  # Should extract just email
        assert result["phone"] == "+12546400994"

    def test_phone_formatting_various_formats(self):
        """Test phone number formatting from various input formats."""
        test_cases = [
            ("(972) 464-6277", "+19724646277"),
            ("972-464-6277", "+19724646277"),
            ("9724646277", "+19724646277"),
            ("19724646277", "+19724646277"),
            ("+1 972 464 6277", "+19724646277"),
        ]
        
        for input_phone, expected in test_cases:
            body = f"Phone: {input_phone}"
            result = self.parser.parse(body)
            assert result["phone"] == expected, f"Failed for input: {input_phone}"

    def test_email_validation_rejects_names(self):
        """Test that names are not accepted as email addresses."""
        body = """
        Name: John Doe
        Email: Dustin Yates
        Phone: (972) 464-6277
        """
        
        result = self.parser.parse(body)
        
        # Should not accept "Dustin Yates" as email
        assert result["email"] is None or "@" in result["email"]

    def test_name_extraction_handles_special_cases(self):
        """Test name extraction handles various edge cases."""
        test_cases = [
            ("Name: John  Doe", "John Doe"),  # Multiple spaces
            ("Name:  John Doe  ", "John Doe"),  # Leading/trailing spaces
            ("Name: John-Doe", "John-Doe"),  # Hyphenated name
            ("Name: O'Connor", "O'Connor"),  # Apostrophe
        ]
        
        for input_line, expected in test_cases:
            result = self.parser.parse(input_line)
            assert result["name"] == expected, f"Failed for input: {input_line}"

    def test_additional_fields_extraction(self):
        """Test that additional fields beyond name/email/phone are captured."""
        body = """
        Name: Test User
        Email: test@example.com
        Phone: (972) 464-6277
        Location Email: location@example.com
        Franchise Code: 545911
        Location Code: LALANG
        Class Code: Adult Level 2
        HubSpot Cookie: 51576c37b8f4ee3899fcbf08c807ef5f
        UTM Source: google
        """
        
        result = self.parser.parse(body)
        
        assert result["name"] == "Test User"
        assert result["email"] == "test@example.com"
        assert result["phone"] == "+19724646277"
        
        # Check additional fields
        additional = result["additional_fields"]
        assert additional["location email"] == "location@example.com"
        assert additional["franchise code"] == "545911"
        assert additional["location code"] == "LALANG"
        assert additional["class code"] == "Adult Level 2"
        assert additional["hubspot cookie"] == "51576c37b8f4ee3899fcbf08c807ef5f"
        assert additional["utm source"] == "google"

    def test_empty_body(self):
        """Test parsing empty email body."""
        result = self.parser.parse("")
        
        assert result["name"] is None
        assert result["email"] is None
        assert result["phone"] is None
        assert result["additional_fields"] == {}
        assert result["metadata"] == {}

    def test_no_structured_data(self):
        """Test parsing email body with no structured data."""
        body = "This is just a regular email message without any structured form data."
        
        result = self.parser.parse(body)
        
        # Should still try to extract email/phone from body text
        # But name should be None without structured data
        assert result["name"] is None

    def test_fallback_email_extraction(self):
        """Test fallback email extraction from body text."""
        body = "Please contact me at john@example.com for more information."
        
        result = self.parser.parse(body)
        
        assert result["email"] == "john@example.com"

    def test_fallback_phone_extraction(self):
        """Test fallback phone extraction from body text."""
        body = "You can reach me at (972) 464-6277 anytime."
        
        result = self.parser.parse(body)
        
        assert result["phone"] == "+19724646277"

    def test_multiple_emails_prefers_structured(self):
        """Test that structured email is preferred over extracted email."""
        body = """
        Email: primary@example.com
        Contact me at secondary@example.com for details.
        """
        
        result = self.parser.parse(body)
        
        assert result["email"] == "primary@example.com"

    def test_name_cleaning_removes_email_patterns(self):
        """Test that names containing email patterns are rejected."""
        body = "Name: john@example.com"
        
        result = self.parser.parse(body)
        
        # Should not accept email as name
        assert result["name"] is None

    def test_name_cleaning_removes_phone_patterns(self):
        """Test that names containing phone patterns are rejected."""
        body = "Name: (972) 464-6277"
        
        result = self.parser.parse(body)
        
        # Should not accept phone as name
        assert result["name"] is None

    def test_metadata_includes_parsing_info(self):
        """Test that metadata includes parsing information."""
        body = """
        Name: Test User
        Email: test@example.com
        Phone: (972) 464-6277
        Location: Test Location
        """
        
        result = self.parser.parse(body)
        
        assert "metadata" in result
        assert "parsed_fields" in result["metadata"]
        assert "original_phone" in result["metadata"]

    def test_real_world_example_1(self):
        """Test with real-world email format from images."""
        body = """
        Location Email: goswimcypressspring@britishswimschool.com
        HubSpot Cookie: 51576c37b8f4ee3899fcbf08c807ef5f
        UTM Source: google
        UTM Medium: performancemax
        UTM Campaign: campaignname
        Class ID: 20845810
        Student Name: Olawunmi Ayodele
        Email: wunta23@yahoo.com
        Phone: (972) 464-6277
        How did you hear about us?:
        """
        
        result = self.parser.parse(body)
        
        assert result["name"] == "Olawunmi Ayodele"
        assert result["email"] == "wunta23@yahoo.com"
        assert result["phone"] == "+19724646277"
        assert result["additional_fields"]["location email"] == "goswimcypressspring@britishswimschool.com"
        assert result["additional_fields"]["class id"] == "20845810"

    def test_real_world_example_2(self):
        """Test with another real-world email format."""
        body = """
        Name: Kimi Knight
        Email: kimiknight1964@gmail.com
        Phone: (254) 640-0994
        Type of Lessons: Over 3
        Address: 77429
        Marketing Opt-in: Yes
        Location Email: goswimcypressspring@britishswimschool.com
        Franchise Code: 545911
        """
        
        result = self.parser.parse(body)
        
        assert result["name"] == "Kimi Knight"
        assert result["email"] == "kimiknight1964@gmail.com"
        assert result["phone"] == "+12546400994"
        assert result["additional_fields"]["type of lessons"] == "Over 3"
        assert result["additional_fields"]["address"] == "77429"
        assert result["additional_fields"]["franchise code"] == "545911"

    def test_case_insensitive_labels(self):
        """Test that label matching is case-insensitive."""
        body = """
        NAME: John Doe
        EMAIL: john@example.com
        PHONE: (972) 464-6277
        """
        
        result = self.parser.parse(body)
        
        assert result["name"] == "John Doe"
        assert result["email"] == "john@example.com"
        assert result["phone"] == "+19724646277"

    def test_multiline_values(self):
        """Test handling of values that might span multiple lines."""
        body = """
        Name: John
        Doe
        Email: john@example.com
        Phone: (972) 464-6277
        """
        
        # Note: This is a limitation - multiline values won't be captured
        # But the parser should still extract what it can
        result = self.parser.parse(body)
        
        assert result["name"] == "John"  # Only first line captured
        assert result["email"] == "john@example.com"
        assert result["phone"] == "+19724646277"

    def test_table_format_parsing(self):
        """Test parsing form data where labels and values are on separate lines (HTML table format)."""
        # This simulates what happens when an HTML table is converted to plain text
        # Each table cell becomes its own line
        body = """
Name
Kimi Knight
Email
kimiknight1964@gmail.com
Phone
(254) 640-0994
Type of Lessons
Over 3
Address
77429
Marketing Opt-in
Yes
Location Email
goswimcypressspring@britishswimschool.com
Franchise Code
545911
        """
        
        result = self.parser.parse(body)
        
        assert result["name"] == "Kimi Knight"
        assert result["email"] == "kimiknight1964@gmail.com"
        assert result["phone"] == "+12546400994"
        assert result["additional_fields"]["type of lessons"] == "Over 3"
        assert result["additional_fields"]["address"] == "77429"
        assert result["additional_fields"]["franchise code"] == "545911"

    def test_mixed_format_table_and_colon(self):
        """Test parsing when some fields use colon format and others use table format."""
        body = """
Name: John Doe
Email
john@example.com
Phone: (972) 464-6277
Location
Test Location
        """
        
        result = self.parser.parse(body)
        
        assert result["name"] == "John Doe"
        assert result["email"] == "john@example.com"
        assert result["phone"] == "+19724646277"
        assert result["additional_fields"]["location"] == "Test Location"

    def test_sender_name_not_used_for_structured_form_data(self):
        """Test that when form data has a Name field, it's used instead of email sender name."""
        # Simulate what happens in EmailService._extract_contact_info
        body = """
Name
Kimi Knight
Email
kimiknight1964@gmail.com
Phone
(254) 640-0994
        """
        
        result = self.parser.parse(body)
        
        # The parsed name should be from the form, not from any email header
        assert result["name"] == "Kimi Knight"
        # Should have structured data indicators
        assert result["metadata"]["parsed_fields"]

