import { format, isToday, isYesterday } from 'date-fns';
import { toZonedTime, format as formatTz } from 'date-fns-tz';

const CENTRAL_TZ = 'America/Chicago';

export function formatSmartDateTime(dateString) {
  try {
    if (!dateString) return '—';

    const date = new Date(dateString);
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
