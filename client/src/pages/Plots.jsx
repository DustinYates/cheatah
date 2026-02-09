import { useCallback, useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { api } from '../api/client';
import { useFetchData } from '../hooks/useFetchData';
import { useAuth } from '../context/AuthContext';
import DateRangeFilter from '../components/DateRangeFilter';
import { LoadingState, EmptyState, ErrorState } from '../components/ui';
import {
  DATE_RANGE_PRESETS,
  alignRangeToTimeZone,
  buildTimeBuckets,
  formatDateInTimeZone,
  formatRangeLabel,
  getBucketBounds,
  getBucketKey,
  getPresetRange,
  getRangeLengthDays,
  getRangeTypeByDays,
  parseDateInTimeZone,
  resolveTimeZone,
} from '../utils/dateRange';
import './Plots.css';

const STORAGE_KEY = 'usageDateRange';
const PRESET_VALUES = new Set(DATE_RANGE_PRESETS.map((preset) => preset.value));

const formatMinutes = (value) => {
  const minutes = Number(value) || 0;
  if (minutes === 0) return '0';
  if (Number.isInteger(minutes)) return minutes.toString();
  return minutes.toFixed(1);
};

const getLabelInterval = (count, granularity) => {
  if (granularity === 'month') {
    return count > 12 ? 2 : 1;
  }
  if (count <= 7) return 1;
  if (count <= 14) return 2;
  return Math.ceil(count / 8);
};

const parseRangeFromParams = (params, timeZone) => {
  const preset = params.get('range');
  const startValue = params.get('start_date');
  const endValue = params.get('end_date');

  if (preset && PRESET_VALUES.has(preset) && preset !== 'custom') {
    return { preset, ...getPresetRange(preset, timeZone) };
  }

  if (startValue && endValue) {
    const startDate = parseDateInTimeZone(startValue, timeZone);
    const endDate = parseDateInTimeZone(endValue, timeZone);
    if (startDate && endDate) {
      const endBounds = getBucketBounds(endDate, 'day', timeZone);
      return { preset: 'custom', startDate, endDate: endBounds.end };
    }
  }

  return null;
};

const parseRangeFromStorage = (timeZone) => {
  const raw = localStorage.getItem(STORAGE_KEY);
  if (!raw) return null;
  try {
    const stored = JSON.parse(raw);
    if (!stored?.start_date || !stored?.end_date) return null;
    const startDate = parseDateInTimeZone(stored.start_date, timeZone);
    const endDate = parseDateInTimeZone(stored.end_date, timeZone);
    if (!startDate || !endDate) return null;
    const endBounds = getBucketBounds(endDate, 'day', timeZone);
    const preset = stored.preset && PRESET_VALUES.has(stored.preset) ? stored.preset : 'custom';
    return { preset, startDate, endDate: endBounds.end };
  } catch {
    return null;
  }
};

const buildParamsFromRange = (range, timeZone) => {
  const startDate = formatDateInTimeZone(range.startDate, 'yyyy-MM-dd', timeZone);
  const endDate = formatDateInTimeZone(range.endDate, 'yyyy-MM-dd', timeZone);
  return {
    range: range.preset,
    start_date: startDate,
    end_date: endDate,
    timezone: timeZone,
  };
};

const persistRange = (range, timeZone, setSearchParams, replace = false) => {
  const params = buildParamsFromRange(range, timeZone);
  setSearchParams(params, { replace });
  localStorage.setItem(STORAGE_KEY, JSON.stringify(params));
};

const formatBucketLabel = (bucket, granularity, timeZone) => {
  if (!bucket?.bucketStart) return '';
  const formatString = granularity === 'month' ? 'MMM yyyy' : 'MMM d, yyyy';
  if (granularity === 'day') {
    return formatDateInTimeZone(bucket.bucketStart, formatString, timeZone);
  }
  const startLabel = formatDateInTimeZone(bucket.bucketStart, formatString, timeZone);
  const endLabel = formatDateInTimeZone(bucket.bucketEnd, formatString, timeZone);
  return `${startLabel} – ${endLabel}`;
};

export default function Plots() {
  const { user, selectedTenantId } = useAuth();
  const needsTenant = user?.is_global_admin && !selectedTenantId;
  const [searchParams, setSearchParams] = useSearchParams();

  const browserTimeZone = useMemo(() => resolveTimeZone(), []);
  const [timeZone, setTimeZone] = useState(browserTimeZone);

  const [range, setRange] = useState(() => {
    const fromParams = parseRangeFromParams(searchParams, browserTimeZone);
    if (fromParams) return fromParams;
    const fromStorage = parseRangeFromStorage(browserTimeZone);
    if (fromStorage) return fromStorage;
    return { preset: '7d', ...getPresetRange('7d', browserTimeZone) };
  });

  useEffect(() => {
    if (!searchParams.get('range') && !searchParams.get('start_date')) {
      const fromStorage = parseRangeFromStorage(timeZone);
      if (fromStorage) {
        setRange(fromStorage);
        persistRange(fromStorage, timeZone, setSearchParams, true);
      }
    }
  }, [searchParams, setSearchParams, timeZone]);

  useEffect(() => {
    const parsed = parseRangeFromParams(searchParams, timeZone);
    if (!parsed) return;
    const currentStart = formatDateInTimeZone(range.startDate, 'yyyy-MM-dd', timeZone);
    const currentEnd = formatDateInTimeZone(range.endDate, 'yyyy-MM-dd', timeZone);
    const nextStart = formatDateInTimeZone(parsed.startDate, 'yyyy-MM-dd', timeZone);
    const nextEnd = formatDateInTimeZone(parsed.endDate, 'yyyy-MM-dd', timeZone);
    if (parsed.preset !== range.preset || currentStart !== nextStart || currentEnd !== nextEnd) {
      setRange(parsed);
    }
  }, [range, searchParams, timeZone]);

  const handleRangeChange = (nextRange) => {
    setRange(nextRange);
    persistRange(nextRange, timeZone, setSearchParams);
  };

  const fetchUsage = useCallback(async () => {
    if (!range?.startDate || !range?.endDate) {
      return { onboarded_date: null, series: [], timezone: timeZone };
    }
    const params = buildParamsFromRange(range, timeZone);
    return api.getUsageAnalytics(params);
  }, [range, timeZone]);

  const { data, loading, error, refetch } = useFetchData(fetchUsage, {
    defaultValue: { onboarded_date: null, series: [] },
    immediate: !needsTenant,
    deps: [selectedTenantId, range.startDate, range.endDate, timeZone],
  });

  useEffect(() => {
    if (!data?.timezone || data.timezone === timeZone) return;
    const aligned = alignRangeToTimeZone(range, timeZone, data.timezone);
    setTimeZone(data.timezone);
    setRange(aligned);
    persistRange(aligned, data.timezone, setSearchParams, true);
  }, [data?.timezone, range, setSearchParams, timeZone]);

  const usageSeries = data?.series || [];

  const totals = useMemo(() => {
    return usageSeries.reduce(
      (acc, day) => {
        acc.smsIn += day.sms_in || 0;
        acc.smsOut += day.sms_out || 0;
        acc.chatbot += day.chatbot_interactions || 0;
        acc.callMinutes += Number(day.call_minutes || 0);
        acc.callCount += day.call_count || 0;
        return acc;
      },
      { smsIn: 0, smsOut: 0, chatbot: 0, callMinutes: 0, callCount: 0 }
    );
  }, [usageSeries]);

  const hasUsage = usageSeries.some(
    (day) =>
      day.sms_in ||
      day.sms_out ||
      day.chatbot_interactions ||
      day.call_count ||
      Number(day.call_minutes || 0) > 0
  );

  const rangeDays = useMemo(
    () => getRangeLengthDays(range.startDate, range.endDate, timeZone),
    [range.endDate, range.startDate, timeZone]
  );
  const granularity = useMemo(() => getRangeTypeByDays(rangeDays), [rangeDays]);

  const bucketedSeries = useMemo(() => {
    const buckets = buildTimeBuckets(range.startDate, range.endDate, granularity, timeZone);
    const bucketMap = new Map(
      buckets.map((bucket) => [
        bucket.key,
        {
          ...bucket,
          sms_in: 0,
          sms_out: 0,
          chatbot_interactions: 0,
          call_count: 0,
          call_minutes: 0,
        },
      ])
    );

    usageSeries.forEach((day) => {
      const date = parseDateInTimeZone(day.date, timeZone) || new Date(day.date);
      if (!date || Number.isNaN(date.getTime())) return;
      const bounds = getBucketBounds(date, granularity, timeZone);
      const key = getBucketKey(bounds.start, timeZone);
      const bucket = bucketMap.get(key);
      if (!bucket) return;
      bucket.sms_in += day.sms_in || 0;
      bucket.sms_out += day.sms_out || 0;
      bucket.chatbot_interactions += day.chatbot_interactions || 0;
      bucket.call_count += day.call_count || 0;
      bucket.call_minutes += Number(day.call_minutes || 0);
    });

    return { granularity, buckets: Array.from(bucketMap.values()) };
  }, [granularity, range.endDate, range.startDate, timeZone, usageSeries]);

  const interactionSeries = useMemo(
    () =>
      bucketedSeries.buckets.map((day) => {
        const smsIn = day.sms_in || 0;
        const smsOut = day.sms_out || 0;
        const textTotal = smsIn + smsOut;
        return {
          ...day,
          smsIn,
          smsOut,
          text: textTotal,
          phone: day.call_count || 0,
          chat: day.chatbot_interactions || 0,
        };
      }),
    [bucketedSeries.buckets]
  );

  const interactionDisplaySeries = interactionSeries;
  const interactionLabelInterval = getLabelInterval(interactionDisplaySeries.length, granularity);
  const callDisplaySeries = bucketedSeries.buckets;
  const callLabelInterval = getLabelInterval(callDisplaySeries.length, granularity);

  const interactionMaxValue = Math.max(
    0,
    ...interactionDisplaySeries.map((day) => day.text + day.phone + day.chat)
  );
  const callMaxValue = Math.max(0, ...callDisplaySeries.map((day) => Number(day.call_minutes || 0)));
  const interactionScaleMax = interactionMaxValue || 1;
  const callScaleMax = callMaxValue || 1;

  if (needsTenant) {
    return (
      <div className="plots-page">
        <EmptyState
          icon="DATA"
          title="Select a tenant to view analytics"
          description="Please select a tenant from the dropdown above to view usage analytics."
        />
      </div>
    );
  }

  if (loading) {
    return <LoadingState message="Loading usage analytics..." fullPage />;
  }

  if (error) {
    if (error.includes('Tenant context required') || error.includes('Tenant context')) {
      return (
        <div className="plots-page">
          <EmptyState
            icon="DATA"
            title="Select a tenant to view analytics"
            description="Please select a tenant from the dropdown above to view usage analytics."
          />
        </div>
      );
    }
    return (
      <div className="plots-page">
        <ErrorState message={error} onRetry={refetch} />
      </div>
    );
  }

  const rangeLabel = formatRangeLabel(range.startDate, range.endDate, timeZone);
  const granularityLabel =
    granularity === 'day' ? 'Daily' : granularity === 'week' ? 'Weekly' : 'Monthly';

  const header = (
    <div className="plots-header">
      <div className="plots-header-top">
        <div className="plots-title">
          <h1>Usage Analytics</h1>
          {rangeLabel && (
            <p className="plots-subtitle">Tracking usage from {rangeLabel}.</p>
          )}
        </div>
        <DateRangeFilter value={range} timeZone={timeZone} onChange={handleRangeChange} />
      </div>
      {hasUsage && (
        <div className="plots-summary">
          <div>
            <span className="summary-value">{totals.smsIn + totals.smsOut}</span>
            <span className="summary-label">Texts</span>
          </div>
          <div>
            <span className="summary-value">{totals.chatbot}</span>
            <span className="summary-label">Chatbot</span>
          </div>
          <div>
            <span className="summary-value">{totals.callCount}</span>
            <span className="summary-label">Phone calls</span>
          </div>
          <div>
            <span className="summary-value">{formatMinutes(totals.callMinutes)}</span>
            <span className="summary-label">Call minutes</span>
          </div>
        </div>
      )}
    </div>
  );

  if (!hasUsage) {
    return (
      <div className="plots-page">
        {header}
        <EmptyState
          icon="INFO"
          title="No usage yet"
          description="Usage will appear once customers start texting, chatting, or calling."
        />
      </div>
    );
  }

  return (
    <div className="plots-page">
      {header}

      <div className="usage-grid">
        <section className="usage-card">
          <div className="usage-card-header">
            <div>
              <h2>{granularityLabel} Interactions</h2>
              <p>{granularityLabel} totals across channels.</p>
            </div>
            <div className="usage-legend">
              <span className="legend-item">
                <span className="legend-swatch text" />
                Texts
              </span>
              <span className="legend-item">
                <span className="legend-swatch phone" />
                Phone calls
              </span>
              <span className="legend-item">
                <span className="legend-swatch chatbot" />
                Chatbot
              </span>
            </div>
          </div>
          <div className="usage-chart">
            <div className="usage-y-axis">
              <span>{Math.round(interactionMaxValue)}</span>
              <span>0</span>
            </div>
            <div className="usage-bars">
              {interactionDisplaySeries.map((day, index) => {
                const textHeight = (day.text / interactionScaleMax) * 100;
                const phoneHeight = (day.phone / interactionScaleMax) * 100;
                const chatHeight = (day.chat / interactionScaleMax) * 100;
                const showLabel =
                  index % interactionLabelInterval === 0 ||
                  index === interactionDisplaySeries.length - 1;
                const tooltip = `${formatBucketLabel(day, granularity, timeZone)} - Texts: ${day.text} (in ${day.smsIn}, out ${day.smsOut}), Phone: ${day.phone}, Chatbot: ${day.chat}`;
                const labelFormat = granularity === 'month' ? 'MMM yyyy' : 'MMM d';
                const total = day.text + day.phone + day.chat;
                return (
                  <div className="usage-bar-column" key={day.key}>
                    <div className="usage-bar-track" title={tooltip}>
                      {total > 0 && <span className="usage-bar-total">{total}</span>}
                      {day.text > 0 && (
                        <div className="usage-bar text" style={{ height: `${textHeight}%` }} />
                      )}
                      {day.phone > 0 && (
                        <div className="usage-bar phone" style={{ height: `${phoneHeight}%` }} />
                      )}
                      {day.chat > 0 && (
                        <div className="usage-bar chatbot" style={{ height: `${chatHeight}%` }} />
                      )}
                    </div>
                    <span className="usage-x-label">
                      {showLabel
                        ? formatDateInTimeZone(day.bucketStart, labelFormat, timeZone)
                        : ''}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        </section>

        <section className="usage-card">
          <div className="usage-card-header">
            <div>
              <h2>
                {granularity === 'day'
                  ? 'Call Minutes by Day'
                  : granularity === 'week'
                    ? 'Call Minutes by Week'
                    : 'Call Minutes by Month'}
              </h2>
              <p>{granularityLabel} totals.</p>
            </div>
          </div>
          <div className="usage-chart">
            <div className="usage-y-axis">
              <span>{formatMinutes(callMaxValue)}</span>
              <span>0</span>
            </div>
            <div className={`usage-bars ${callDisplaySeries.length === 1 ? 'single-point' : ''}`}>
              {callDisplaySeries.map((day, index) => {
                const minutes = Number(day.call_minutes || 0);
                const height = (minutes / callScaleMax) * 100;
                const showLabel = index % callLabelInterval === 0 || index === callDisplaySeries.length - 1;
                const labelFormat = granularity === 'month' ? 'MMM yyyy' : 'MMM d';
                return (
                  <div className="usage-bar-column" key={day.key}>
                    <div
                      className="usage-bar-track"
                      title={`${formatBucketLabel(day, granularity, timeZone)} - ${formatMinutes(minutes)} minutes`}
                    >
                      {minutes > 0 && (
                        <>
                          <span className="usage-bar-label">{formatMinutes(minutes)}</span>
                          <div className="usage-bar calls" style={{ height: `${height}%` }} />
                        </>
                      )}
                    </div>
                    <span className="usage-x-label">
                      {showLabel ? formatDateInTimeZone(day.bucketStart, labelFormat, timeZone) : ''}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
