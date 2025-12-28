"""Email body parser for extracting structured form data from email bodies."""

import logging
import re
from typing import Any

try:
    import phonenumbers
    from phonenumbers import NumberParseException
    PHONENUMBERS_AVAILABLE = True
except ImportError:
    PHONENUMBERS_AVAILABLE = False
    logging.warning("phonenumbers library not available. Phone number formatting will be limited.")

logger = logging.getLogger(__name__)


class EmailBodyParser:
    """Parser for extracting structured form data from email bodies."""

    # Common field label variations
    NAME_LABELS = [
        r"^name$",
        r"^student\s*name$",
        r"^full\s*name$",
        r"^contact\s*name$",
    ]
    
    EMAIL_LABELS = [
        r"^email$",
        r"^e-mail$",
        r"^email\s*address$",
    ]
    
    PHONE_LABELS = [
        r"^phone$",
        r"^phone\s*number$",
        r"^telephone$",
        r"^mobile$",
        r"^cell$",
    ]

    # Email validation regex
    EMAIL_PATTERN = re.compile(
        r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    )

    def parse(self, email_body: str) -> dict[str, Any]:
        """Parse structured form data from email body.
        
        Args:
            email_body: The email body text to parse
            
        Returns:
            Dictionary with:
            - name: Extracted name (str | None)
            - email: Extracted email (str | None)
            - phone: Extracted phone in E.164 format (str | None)
            - additional_fields: Dictionary of other parsed fields
            - metadata: Dictionary with original values and parsing info
        """
        if not email_body:
            return {
                "name": None,
                "email": None,
                "phone": None,
                "additional_fields": {},
                "metadata": {},
            }
        
        # Remove HTML tags if present (basic cleanup)
        # Use _strip_html_tags to preserve email addresses in angle brackets
        email_body = self._strip_html_tags(email_body)
        # Decode HTML entities (basic ones)
        email_body = email_body.replace('&nbsp;', ' ').replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
        
        # Normalize line endings and split into lines
        body_lines = email_body.replace('\r\n', '\n').replace('\r', '\n').split('\n')
        
        # Parse key-value pairs
        parsed_data = self._parse_key_value_pairs(body_lines)
        
        # Log parsed data for debugging
        logger.debug(f"Email body parser - parsed_data keys: {list(parsed_data.keys())}")
        if 'name' in parsed_data:
            logger.debug(f"Email body parser - found 'name' key with value: {parsed_data['name']}")
        
        # Extract primary fields
        name = self._extract_name(parsed_data, email_body)
        email = self._extract_email(parsed_data, email_body)
        phone = self._extract_phone(parsed_data, email_body)
        
        logger.debug(f"Email body parser - extracted name={name}, email={email}, phone={phone}")
        
        # Get additional fields (everything except name, email, phone)
        additional_fields = {
            k: v for k, v in parsed_data.items()
            if k.lower() not in ['name', 'email', 'phone', 'phone number', 'telephone', 'mobile', 'cell']
        }
        
        # Build metadata
        metadata = {
            "parsed_fields": list(parsed_data.keys()),
            "original_phone": parsed_data.get('phone') or parsed_data.get('phone number') or parsed_data.get('telephone') or parsed_data.get('mobile') or parsed_data.get('cell'),
        }
        
        return {
            "name": name,
            "email": email,
            "phone": phone,
            "additional_fields": additional_fields,
            "metadata": metadata,
        }

    def _strip_html_tags(self, text: str) -> str:
        """Strip HTML tags from text, but preserve email addresses in angle brackets.
        
        Args:
            text: Text that may contain HTML tags
            
        Returns:
            Text with HTML tags removed but email addresses preserved
        """
        if not text:
            return text
        
        # First, temporarily protect email addresses in angle brackets
        # Match patterns like <email@example.com>
        email_placeholder = {}
        placeholder_idx = 0
        
        def protect_email(match: re.Match) -> str:
            nonlocal placeholder_idx
            email = match.group(0)
            # Check if it looks like an email (contains @ and .)
            if '@' in email and '.' in email:
                placeholder = f"__EMAIL_PLACEHOLDER_{placeholder_idx}__"
                email_placeholder[placeholder] = email
                placeholder_idx += 1
                return placeholder
            return email
        
        # Protect emails in angle brackets
        text = re.sub(r'<[^>]+@[^>]+\.[^>]+>', protect_email, text)
        
        # Now remove actual HTML tags
        text = re.sub(r'<[^>]+>', '', text)
        
        # Restore protected email addresses
        for placeholder, email in email_placeholder.items():
            text = text.replace(placeholder, email)
        
        return text.strip()

    def _parse_key_value_pairs(self, lines: list[str]) -> dict[str, str]:
        """Parse key-value pairs from email body lines.
        
        Handles formats like:
        - "Name: John Doe"
        - "Name - John Doe"
        - "Name:John Doe"
        - "Name:  John Doe" (multiple spaces)
        - Table format where label and value are on consecutive lines:
          Name
          John Doe
        
        Args:
            lines: List of email body lines
            
        Returns:
            Dictionary of field_name -> field_value
        """
        parsed = {}
        
        # Known form field labels (for table format detection)
        known_labels = {
            'name', 'email', 'phone', 'address', 'type of lessons', 
            'marketing opt-in', 'location email', 'franchise code',
            'student name', 'full name', 'contact name', 'phone number',
            'telephone', 'mobile', 'cell', 'e-mail', 'email address',
            'class id', 'location code', 'class code', 'utm source',
            'utm medium', 'utm campaign', 'hubspot cookie', 'location',
            'how did you hear about us?', 'how did you hear about us',
        }
        
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if not line:
                i += 1
                continue
            
            # Clean line: replace non-breaking spaces with regular spaces
            line = line.replace('\xa0', ' ').replace('&nbsp;', ' ')
            
            # Handle pipe-delimited table format: "| Label |" followed by "| \xa0 | Value |"
            # This format comes from HTML tables converted to text
            if line.startswith('|') and line.endswith('|'):
                # Extract content between pipes, strip whitespace
                inner = line.strip('|').strip()
                # Check if this is a known label
                inner_lower = inner.lower()
                if inner_lower in known_labels:
                    # Look at the next line for the value
                    if i + 1 < len(lines):
                        next_line = lines[i + 1].strip().replace('\xa0', ' ').replace('&nbsp;', ' ')
                        if next_line.startswith('|') and next_line.endswith('|'):
                            # Extract value from pipe-delimited format: "| \xa0 | Value |" or "| Value |"
                            inner_parts = [p.strip() for p in next_line.strip('|').split('|')]
                            # Take the last non-empty part as the value
                            value = None
                            for part in reversed(inner_parts):
                                if part and part.strip():
                                    value = part.strip()
                                    break
                            if value and value.lower() not in known_labels:
                                parsed[inner_lower] = value
                                logger.debug(f"Pipe table format: found '{inner}' = '{value}'")
                                i += 2
                                continue
                i += 1
                continue
            
            # Try colon separator first (most common)
            if ':' in line:
                parts = line.split(':', 1)
                if len(parts) == 2:
                    key = parts[0].strip()
                    value = parts[1].strip()
                    # Remove markdown formatting from key (e.g., **Name**)
                    key = re.sub(r'\*\*?', '', key).strip()
                    # Remove HTML tags from value (but not email angle brackets like <email@example.com>)
                    value = self._strip_html_tags(value)

                    # Check if value contains another field label concatenated (e.g., "abc@aol.comPhone:212")
                    # This handles cases where line breaks were stripped from HTML
                    if value:
                        # Find the EARLIEST occurrence of any known label in the value
                        earliest_idx = len(value)
                        earliest_label = None
                        for label in known_labels:
                            # Create case-insensitive pattern to find label followed by colon
                            label_pattern = re.compile(rf'({re.escape(label)})\s*:', re.IGNORECASE)
                            label_match = label_pattern.search(value)
                            if label_match and label_match.start() < earliest_idx and label_match.start() > 0:
                                earliest_idx = label_match.start()
                                earliest_label = label

                        if earliest_label is not None:
                            # Split the value at the earliest label
                            actual_value = value[:earliest_idx].strip()
                            remaining = value[earliest_idx:].strip()
                            if actual_value:
                                parsed[key.lower()] = actual_value
                                logger.debug(f"Split concatenated value: '{key}' = '{actual_value}', remaining: '{remaining}'")
                            # Add remaining as a virtual line to parse later
                            if remaining:
                                lines.insert(i + 1, remaining)
                            i += 1
                            continue  # Continue to process the inserted line
                        else:
                            # No label found in value, use as-is
                            if key and value:
                                parsed[key.lower()] = value
                                i += 1
                                continue
                    else:
                        i += 1
                    # If key exists but value is empty, check next line
                    if key and not value:
                        if i + 1 < len(lines):
                            next_line = lines[i + 1].strip()
                            # Next line should be a value (not another key)
                            if next_line and ':' not in next_line:
                                value = self._strip_html_tags(next_line)
                                if value:
                                    parsed[key.lower()] = value
                                    i += 2
                                    continue
            
            # Try dash separator
            if ' - ' in line or ' – ' in line:
                parts = re.split(r'\s*[-–]\s*', line, 1)
                if len(parts) == 2:
                    key = parts[0].strip()
                    value = parts[1].strip()
                    if key and value:
                        parsed[key.lower()] = value
                        i += 1
                        continue
            
            # Try pipe separator
            if '|' in line:
                parts = line.split('|', 1)
                if len(parts) == 2:
                    key = parts[0].strip()
                    value = parts[1].strip()
                    if key and value:
                        parsed[key.lower()] = value
                        i += 1
                        continue
            
            # Check for table format: label on one line, value on the next
            # This handles HTML tables that become "Label\nValue" after stripping
            line_lower = line.lower()
            if line_lower in known_labels:
                if i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    # Next line should be a value (not empty and not another known label)
                    if next_line and next_line.lower() not in known_labels:
                        # Make sure it's not a key:value pair
                        if ':' not in next_line or not any(lbl in next_line.lower() for lbl in known_labels):
                            value = re.sub(r'<[^>]+>', '', next_line).strip()
                            if value:
                                parsed[line_lower] = value
                                logger.debug(f"Table format: found '{line}' = '{value}'")
                                i += 2
                                continue
            
            i += 1
        
        return parsed

    def _extract_name(self, parsed_data: dict[str, str], email_body: str) -> str | None:
        """Extract and clean name from parsed data.
        
        Args:
            parsed_data: Dictionary of parsed key-value pairs
            email_body: Original email body for fallback extraction
            
        Returns:
            Cleaned name or None
        """
        # Try to find name in parsed data using label patterns
        for label_pattern in self.NAME_LABELS:
            for key, value in parsed_data.items():
                if re.search(label_pattern, key, re.IGNORECASE):
                    name = self._clean_name(value)
                    if name:
                        logger.debug(f"Found name using pattern {label_pattern}: {name}")
                        return name
        
        # Fallback: look for "name" key (exact match)
        if 'name' in parsed_data:
            name = self._clean_name(parsed_data['name'])
            if name:
                logger.debug(f"Found name using 'name' key: {name}")
                return name
        
        # Additional fallback: search entire body for "Name:" pattern if not found in parsed data
        # This handles cases where the parsing might have missed it
        name_patterns = [
            r'name\s*:\s*([^\n\r<]+)',
            r'name\s*-\s*([^\n\r<]+)',
            r'student\s+name\s*:\s*([^\n\r<]+)',
        ]
        
        for pattern in name_patterns:
            match = re.search(pattern, email_body, re.IGNORECASE)
            if match:
                potential_name = match.group(1).strip()
                name = self._clean_name(potential_name)
                if name:
                    logger.debug(f"Found name using body search pattern {pattern}: {name}")
                    return name
        
        # Very aggressive fallback: look for "Name:" anywhere in the body, even with HTML or special chars
        # This is a last resort to catch names that might have been missed
        aggressive_patterns = [
            # Simple pattern: "Name:" followed by value (most common)
            r'Name\s*:\s*([^\n\r<]+)',
            # With markdown bold
            r'\*\*?Name\*\*?\s*:?\s*([^\n\r<*]+)',
            # At start of line
            r'(?:^|\n)\s*Name\s*:?\s*([^\n\r<]+?)(?:\n|$)',
            # With HTML tags
            r'<[^>]*>Name[^<]*:?\s*([^<\n\r]+)',
            # Any variation
            r'Name[^:]*:\s*([^\n\r<]+)',
        ]
        
        for pattern in aggressive_patterns:
            match = re.search(pattern, email_body, re.IGNORECASE | re.MULTILINE)
            if match:
                potential_name = match.group(1).strip()
                # Remove any remaining HTML tags or special formatting
                potential_name = re.sub(r'<[^>]+>', '', potential_name)
                potential_name = re.sub(r'\*\*?', '', potential_name)  # Remove markdown bold
                potential_name = potential_name.strip('*').strip()
                name = self._clean_name(potential_name)
                if name:
                    logger.debug(f"Found name using aggressive pattern {pattern}: {name}")
                    return name
        
        logger.debug("No name found in email body")
        return None

    def _clean_name(self, name: str) -> str | None:
        """Clean and validate a name string.
        
        Args:
            name: Raw name string
            
        Returns:
            Cleaned name or None if invalid
        """
        if not name:
            return None
        
        # Clean whitespace first
        name = ' '.join(name.split())
        name = name.strip()
        
        # Remove angle brackets if present
        name = re.sub(r'[<>]', '', name)
        
        # Remove email-like patterns (if someone put an email in name field)
        # But be careful - don't reject names that happen to contain @ in a non-email context
        if '@' in name:
            # Check if it's actually an email address
            if self.EMAIL_PATTERN.search(name):
                return None
            # If it's not a full email, just remove the @ symbol and continue
            name = name.replace('@', '')
        
        # Remove phone-like patterns (but allow names with some numbers)
        # Only reject if it looks like a phone number format
        phone_match = re.search(r'\(?\d{3}\)?\s*-?\s*\d{3}\s*-?\s*\d{4}', name)
        if phone_match and len(phone_match.group(0)) >= 10:
            # If the name is mostly a phone number, reject it
            if len(phone_match.group(0)) >= len(name) * 0.7:
                return None
        
        # Basic validation: should have at least 2 characters and not be all numbers
        if len(name) < 2:
            return None
        
        # Don't reject if it's all numbers - some names might have numbers (e.g., "John 2nd")
        # But reject if it's clearly just a number sequence
        if name.replace(' ', '').isdigit() and len(name.replace(' ', '')) > 3:
            return None
        
        # Reject common non-name values
        name_lower = name.lower()
        if name_lower in ['n/a', 'none', 'null', 'unknown', 'name', 'email', 'phone']:
            return None
        
        return name.strip()

    def _extract_email(self, parsed_data: dict[str, str], email_body: str) -> str | None:
        """Extract and validate email from parsed data.
        
        Args:
            parsed_data: Dictionary of parsed key-value pairs
            email_body: Original email body for fallback extraction
            
        Returns:
            Validated email address or None
        """
        # Try to find email in parsed data
        for label_pattern in self.EMAIL_LABELS:
            for key, value in parsed_data.items():
                if re.search(label_pattern, key, re.IGNORECASE):
                    email = self._clean_email(value)
                    if email:
                        return email
        
        # Fallback: look for "email" key
        if 'email' in parsed_data:
            email = self._clean_email(parsed_data['email'])
            if email:
                return email
        
        # Fallback: search entire body for email addresses
        emails = self.EMAIL_PATTERN.findall(email_body)
        if emails:
            # Prefer emails that look like actual addresses (not in angle brackets with names)
            for email in emails:
                cleaned = self._clean_email(email)
                if cleaned:
                    return cleaned
        
        return None

    def _clean_email(self, email: str) -> str | None:
        """Clean and validate an email address.

        Args:
            email: Raw email string (may include "Name <email@example.com>" format)

        Returns:
            Cleaned email address or None if invalid
        """
        if not email:
            return None

        # Extract email from "Name <email@example.com>" format
        match = re.search(r'<([^>]+)>', email)
        if match:
            email = match.group(1)
        else:
            # Remove any name prefix
            email = email.strip()
            # If it contains a space and @, try to extract just the email part
            if ' ' in email and '@' in email:
                parts = email.split()
                for part in parts:
                    if '@' in part:
                        email = part.strip('<>')
                        break

        # Clean whitespace
        email = email.strip()

        # Use search to find the actual email within the string
        # This handles cases like "abc@aol.comPhone:212-212-1111" where text is concatenated
        # Use a stricter pattern that stops at uppercase letters after TLD (likely next field label)
        email_extract_pattern = re.compile(
            r'([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[a-z]{2,})(?=[A-Z]|$|[^a-zA-Z0-9.])',
            re.IGNORECASE
        )
        extract_match = email_extract_pattern.search(email)
        if extract_match:
            email = extract_match.group(1)

        # Basic validation: must contain @ and look like an email
        if not self.EMAIL_PATTERN.match(email):
            return None

        # Don't accept names as emails (basic check)
        # If it doesn't have @, it's not an email
        if '@' not in email:
            return None

        # Check for common non-email patterns
        if email.lower() in ['name', 'email', 'phone', 'n/a', 'none', 'null']:
            return None

        return email.lower()

    def _extract_phone(self, parsed_data: dict[str, str], email_body: str) -> str | None:
        """Extract and format phone number to E.164 format.
        
        Args:
            parsed_data: Dictionary of parsed key-value pairs
            email_body: Original email body for fallback extraction
            
        Returns:
            Phone number in E.164 format or None
        """
        # Try to find phone in parsed data
        phone_value = None
        for label_pattern in self.PHONE_LABELS:
            for key, value in parsed_data.items():
                if re.search(label_pattern, key, re.IGNORECASE):
                    phone_value = value
                    break
            if phone_value:
                break
        
        # Fallback: look for common phone keys
        if not phone_value:
            for key in ['phone', 'phone number', 'telephone', 'mobile', 'cell']:
                if key in parsed_data:
                    phone_value = parsed_data[key]
                    break
        
        # Fallback: search entire body for phone patterns
        if not phone_value:
            phone_pattern = r'\b(?:\+?1[-.\s]?)?\(?([0-9]{3})\)?[-.\s]?([0-9]{3})[-.\s]?([0-9]{4})\b'
            matches = re.findall(phone_pattern, email_body)
            if matches:
                # Take first match and reconstruct
                area, exchange, number = matches[0]
                phone_value = f"({area}) {exchange}-{number}"
        
        if not phone_value:
            return None
        
        return self._format_phone_e164(phone_value)

    def _format_phone_e164(self, phone: str) -> str | None:
        """Format phone number to E.164 format.
        
        Args:
            phone: Raw phone number string
            
        Returns:
            Phone number in E.164 format (e.g., +1234567890) or None if invalid
        """
        if not phone:
            return None
        
        # Clean the phone string
        phone = re.sub(r'[^\d+]', '', phone)
        
        # If phonenumbers library is available, use it
        if PHONENUMBERS_AVAILABLE:
            try:
                # Try parsing as US number first (default region)
                parsed = phonenumbers.parse(phone, "US")
                if phonenumbers.is_valid_number(parsed):
                    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
            except NumberParseException:
                pass
            
            # Try without region (for international numbers)
            try:
                parsed = phonenumbers.parse(phone, None)
                if phonenumbers.is_valid_number(parsed):
                    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
            except NumberParseException:
                pass
        
        # Fallback: basic formatting for US numbers
        # Remove all non-digits
        digits = re.sub(r'\D', '', phone)
        
        # If it starts with 1, remove it (we'll add +1)
        if digits.startswith('1') and len(digits) == 11:
            digits = digits[1:]
        
        # Must be 10 digits for US number
        if len(digits) == 10:
            return f"+1{digits}"
        
        # If it already starts with +, try to use as-is if it looks valid
        if phone.startswith('+') and len(digits) >= 10:
            return f"+{digits}" if not phone.startswith('+') else phone
        
        return None

