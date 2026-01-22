import {
  addDays,
  addMonths,
  differenceInCalendarDays,
  endOfDay,
  endOfMonth,
  startOfDay,
  startOfMonth,
  startOfYear,
  subDays,
  subMonths,
} from 'date-fns';
import { formatInTimeZone, fromZonedTime, toZonedTime } from 'date-fns-tz';

export const DATE_RANGE_PRESETS = [
  { value: '7d', label: 'Last 7 days' },
  { value: '30d', label: 'Last 30 days' },
  { value: '90d', label: 'Last 90 days' },
  { value: '12mo', label: 'Past 12 months' },
  { value: 'ytd', label: 'Year to Date' },
  { value: 'custom', label: 'Custom Range…' },
];

export function resolveTimeZone(timeZone) {
  return timeZone || Intl.DateTimeFormat().resolvedOptions().timeZone || 'America/Chicago';
}

export function formatDateForInput(date, timeZone) {
  if (!date) return '';
  const tz = resolveTimeZone(timeZone);
  return formatInTimeZone(date, tz, 'yyyy-MM-dd');
}

export function parseDateInput(value, timeZone) {
  if (!value) return null;
  const tz = resolveTimeZone(timeZone);
  return fromZonedTime(`${value}T00:00:00`, tz);
}

export function parseDateInTimeZone(value, timeZone) {
  if (!value) return null;
  const tz = resolveTimeZone(timeZone);
  return fromZonedTime(`${value}T00:00:00`, tz);
}

export function formatDateInTimeZone(date, formatString, timeZone) {
  if (!date) return '';
  const tz = resolveTimeZone(timeZone);
  return formatInTimeZone(date, tz, formatString);
}

export function formatRangeLabel(startDate, endDate, timeZone, formatString = 'MMM d, yyyy') {
  if (!startDate) return '';
  const tz = resolveTimeZone(timeZone);
  const startLabel = formatInTimeZone(startDate, tz, formatString);
  if (!endDate) return startLabel;
  const endLabel = formatInTimeZone(endDate, tz, formatString);
  return `${startLabel} to ${endLabel}`;
}

export function getRangeLengthDays(startDate, endDate, timeZone) {
  if (!startDate || !endDate) return 0;
  const tz = resolveTimeZone(timeZone);
  const startZoned = toZonedTime(startDate, tz);
  const endZoned = toZonedTime(endDate, tz);
  return differenceInCalendarDays(endZoned, startZoned) + 1;
}

export function getPresetRange(preset, timeZone) {
  const tz = resolveTimeZone(timeZone);
  const nowZoned = toZonedTime(new Date(), tz);
  let startZoned = startOfDay(nowZoned);
  let endZoned = endOfDay(nowZoned);

  switch (preset) {
    case '30d':
      startZoned = startOfDay(subDays(nowZoned, 29));
      break;
    case '90d':
      startZoned = startOfDay(subDays(nowZoned, 89));
      break;
    case '12mo':
      startZoned = startOfDay(subMonths(nowZoned, 12));
      break;
    case 'ytd':
      startZoned = startOfDay(startOfYear(nowZoned));
      endZoned = endOfDay(nowZoned);
      break;
    case '7d':
    default:
      startZoned = startOfDay(subDays(nowZoned, 6));
      break;
  }

  return {
    startDate: fromZonedTime(startZoned, tz),
    endDate: fromZonedTime(endZoned, tz),
  };
}

export function alignRangeToTimeZone(range, previousTimeZone, nextTimeZone) {
  if (!range?.startDate || !range?.endDate) return range;
  const prevTz = resolveTimeZone(previousTimeZone);
  const nextTz = resolveTimeZone(nextTimeZone);

  if (range.preset && range.preset !== 'custom') {
    return {
      ...range,
      ...getPresetRange(range.preset, nextTz),
    };
  }

  const startLabel = formatInTimeZone(range.startDate, prevTz, 'yyyy-MM-dd');
  const endLabel = formatInTimeZone(range.endDate, prevTz, 'yyyy-MM-dd');

  return {
    ...range,
    startDate: fromZonedTime(`${startLabel}T00:00:00`, nextTz),
    endDate: fromZonedTime(`${endLabel}T23:59:59`, nextTz),
  };
}

export function clampCustomRange(startDate, endDate, timeZone) {
  const tz = resolveTimeZone(timeZone);
  if (!startDate || !endDate) return { startDate, endDate };
  const startZoned = startOfDay(toZonedTime(startDate, tz));
  const endZoned = endOfDay(toZonedTime(endDate, tz));
  if (endZoned < startZoned) {
    return {
      startDate: fromZonedTime(startZoned, tz),
      endDate: fromZonedTime(startZoned, tz),
    };
  }
  return {
    startDate: fromZonedTime(startZoned, tz),
    endDate: fromZonedTime(endZoned, tz),
  };
}

export function getBucketBounds(date, granularity, timeZone) {
  const tz = resolveTimeZone(timeZone);
  const zonedDate = toZonedTime(date, tz);

  if (granularity === 'month') {
    return {
      start: fromZonedTime(startOfMonth(zonedDate), tz),
      end: fromZonedTime(endOfMonth(zonedDate), tz),
    };
  }

  return {
    start: fromZonedTime(startOfDay(zonedDate), tz),
    end: fromZonedTime(endOfDay(zonedDate), tz),
  };
}

export function getBucketKey(date, timeZone) {
  const tz = resolveTimeZone(timeZone);
  return formatInTimeZone(date, tz, 'yyyy-MM-dd');
}

export function getPresetLabel(preset) {
  return DATE_RANGE_PRESETS.find((option) => option.value === preset)?.label || 'Custom Range…';
}

export function getRangeTypeByDays(days) {
  if (days <= 45) return 'day';
  return 'month';
}

export function buildTimeBuckets(startDate, endDate, granularity, timeZone) {
  if (!startDate || !endDate) return [];
  const tz = resolveTimeZone(timeZone);
  const buckets = [];
  let cursor = startOfDay(toZonedTime(startDate, tz));
  const endCursor = startOfDay(toZonedTime(endDate, tz));

  if (granularity === 'month') {
    cursor = startOfMonth(cursor);
    const endMonth = startOfMonth(endCursor);
    while (cursor <= endMonth) {
      const bucketStart = fromZonedTime(startOfMonth(cursor), tz);
      const bucketEnd = fromZonedTime(endOfMonth(cursor), tz);
      buckets.push({
        key: getBucketKey(bucketStart, tz),
        bucketStart,
        bucketEnd,
      });
      cursor = addMonths(cursor, 1);
    }
    return buckets;
  }

  while (cursor <= endCursor) {
    const bucketStart = fromZonedTime(startOfDay(cursor), tz);
    const bucketEnd = fromZonedTime(endOfDay(cursor), tz);
    buckets.push({
      key: getBucketKey(bucketStart, tz),
      bucketStart,
      bucketEnd,
    });
    cursor = addDays(cursor, 1);
  }

  return buckets;
}
