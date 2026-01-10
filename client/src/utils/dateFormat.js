import { format, isToday, isYesterday } from 'date-fns';
import { toZonedTime, format as formatTz } from 'date-fns-tz';

const CENTRAL_TZ = 'America/Chicago';

function normalizeTimestamp(dateString) {
  if (!dateString) return dateString;

  const trimmed = dateString.trim();
  if (!trimmed) return trimmed;

  const hasTimezone = /[zZ]|[+-]\d{2}:?\d{2}$/.test(trimmed);
  if (hasTimezone) return trimmed;

  const withT = trimmed.includes('T') ? trimmed : trimmed.replace(' ', 'T');
  return `${withT}Z`;
}

export function formatSmartDateTime(dateString) {
  try {
    if (!dateString) return '—';

    const normalized = normalizeTimestamp(dateString);
    const date = new Date(normalized);
    if (isNaN(date.getTime())) return '—';

    const centralDate = toZonedTime(date, CENTRAL_TZ);
    const tzAbbr = formatTz(centralDate, 'zzz', { timeZone: CENTRAL_TZ });

    if (isToday(centralDate)) {
      return `Today ${format(centralDate, 'h:mm a')} ${tzAbbr}`;
    }

    if (isYesterday(centralDate)) {
      return `Yesterday ${format(centralDate, 'h:mm a')} ${tzAbbr}`;
    }

    return `${format(centralDate, 'MMM d h:mm a')} ${tzAbbr}`;
  } catch (error) {
    console.error('Date formatting error:', error);
    return '—';
  }
}

export function formatDateTimeParts(dateString) {
  try {
    if (!dateString) return { date: '—', time: '—', tzAbbr: '' };

    const normalized = normalizeTimestamp(dateString);
    const date = new Date(normalized);
    if (isNaN(date.getTime())) return { date: '—', time: '—', tzAbbr: '' };

    const centralDate = toZonedTime(date, CENTRAL_TZ);
    const tzAbbr = formatTz(centralDate, 'zzz', { timeZone: CENTRAL_TZ });

    return {
      date: format(centralDate, 'MMM d, yyyy'),
      time: format(centralDate, 'h:mm a'),
      tzAbbr,
    };
  } catch (error) {
    console.error('Date formatting error:', error);
    return { date: '—', time: '—', tzAbbr: '' };
  }
}

export function formatLocalDateTime(dateString) {
  try {
    if (!dateString) return '—';

    const normalized = normalizeTimestamp(dateString);
    const date = new Date(normalized);
    if (isNaN(date.getTime())) return '—';

    return format(date, 'MMM d, yyyy h:mm a');
  } catch (error) {
    console.error('Local date formatting error:', error);
    return '—';
  }
}
