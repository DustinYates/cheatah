import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { formatDateInTimeZone, getPresetRange } from './dateRange';

describe('date range presets', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2025-01-10T12:00:00Z'));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('computes last 7 days in UTC', () => {
    const range = getPresetRange('7d', 'UTC');
    expect(formatDateInTimeZone(range.startDate, 'yyyy-MM-dd', 'UTC')).toBe('2025-01-04');
    expect(formatDateInTimeZone(range.endDate, 'yyyy-MM-dd', 'UTC')).toBe('2025-01-10');
  });

  it('computes year to date in UTC', () => {
    const range = getPresetRange('ytd', 'UTC');
    expect(formatDateInTimeZone(range.startDate, 'yyyy-MM-dd', 'UTC')).toBe('2025-01-01');
    expect(formatDateInTimeZone(range.endDate, 'yyyy-MM-dd', 'UTC')).toBe('2025-01-10');
  });

  it('computes past 12 months in UTC', () => {
    const range = getPresetRange('12mo', 'UTC');
    expect(formatDateInTimeZone(range.startDate, 'yyyy-MM-dd', 'UTC')).toBe('2024-01-10');
    expect(formatDateInTimeZone(range.endDate, 'yyyy-MM-dd', 'UTC')).toBe('2025-01-10');
  });
});
