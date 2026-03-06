import { format, isToday, isYesterday, formatDistanceToNow as dateFnsDistanceToNow } from 'date-fns';
import { toZonedTime, format as formatTz } from 'date-fns-tz';

let _defaultTz = 'America/Chicago';

export function setDefaultTimezone(tz) {
  if (tz) _defaultTz = tz;
}

export function getDefaultTimezone() {
  return _defaultTz;
}

function normalizeTimestamp(dateString) {
  if (!dateString) return dateString;

  const trimmed = dateString.trim();
  if (!trimmed) return trimmed;

  const hasTimezone = /[zZ]|[+-]\d{2}:?\d{2}$/.test(trimmed);
  if (hasTimezone) return trimmed;

  const withT = trimmed.includes('T') ? trimmed : trimmed.replace(' ', 'T');
  return `${withT}Z`;
}

export function formatSmartDateTime(dateString, tz = _defaultTz) {
  try {
    if (!dateString) return '—';

    const normalized = normalizeTimestamp(dateString);
    const date = new Date(normalized);
    if (isNaN(date.getTime())) return '—';

    const zonedDate = toZonedTime(date, tz);
    const tzAbbr = formatTz(zonedDate, 'zzz', { timeZone: tz });

    if (isToday(zonedDate)) {
      return `Today ${format(zonedDate, 'h:mm a')} ${tzAbbr}`;
    }

    if (isYesterday(zonedDate)) {
      return `Yesterday ${format(zonedDate, 'h:mm a')} ${tzAbbr}`;
    }

    return `${format(zonedDate, 'MMM d h:mm a')} ${tzAbbr}`;
  } catch (error) {
    console.error('Date formatting error:', error);
    return '—';
  }
}

export function formatDateTimeParts(dateString, tz = _defaultTz) {
  try {
    if (!dateString) return { date: '—', time: '—', tzAbbr: '' };

    const normalized = normalizeTimestamp(dateString);
    const date = new Date(normalized);
    if (isNaN(date.getTime())) return { date: '—', time: '—', tzAbbr: '' };

    const zonedDate = toZonedTime(date, tz);
    const tzAbbr = formatTz(zonedDate, 'zzz', { timeZone: tz });

    return {
      date: format(zonedDate, 'MMM d, yyyy'),
      time: format(zonedDate, 'h:mm a'),
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

export function formatDistanceToNow(dateString) {
  try {
    if (!dateString) return '—';

    const normalized = normalizeTimestamp(dateString);
    const date = new Date(normalized);
    if (isNaN(date.getTime())) return '—';

    return dateFnsDistanceToNow(date, { addSuffix: true });
  } catch (error) {
    console.error('Distance to now formatting error:', error);
    return '—';
  }
}
