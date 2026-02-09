/**
 * Format a phone number for display.
 * Converts E.164 format (+15551234567) or raw digits (5551234567) to (555) 123-4567.
 */
export function formatPhone(phone) {
  if (!phone) return '-';

  const cleaned = phone.replace(/\D/g, '');

  // US number with country code: 12815551234 -> (281) 555-1234
  if (cleaned.length === 11 && cleaned.startsWith('1')) {
    return `(${cleaned.slice(1, 4)}) ${cleaned.slice(4, 7)}-${cleaned.slice(7)}`;
  }

  // US number without country code: 2815551234 -> (281) 555-1234
  if (cleaned.length === 10) {
    return `(${cleaned.slice(0, 3)}) ${cleaned.slice(3, 6)}-${cleaned.slice(6)}`;
  }

  // Non-US or unrecognized — return as-is
  return phone;
}
