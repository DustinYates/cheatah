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
  formatDateInTimeZone,
  formatRangeLabel,
  getBucketBounds,
  getPresetRange,
  parseDateInTimeZone,
  resolveTimeZone,
} from '../utils/dateRange';
import './WidgetAnalytics.css';

const STORAGE_KEY = 'widgetAnalyticsDateRange';
const PRESET_VALUES = new Set(DATE_RANGE_PRESETS.map((preset) => preset.value));

const formatPercent = (rate) => {
  if (!rate || rate === 0) return '0%';
  return `${(rate * 100).toFixed(1)}%`;
};

const formatNumber = (num) => {
  if (!num || num === 0) return '0';
  return num.toLocaleString();
};

const formatTime = (ms) => {
  if (!ms || ms === 0) return '0ms';
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
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

export default function WidgetAnalytics() {
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
    return { preset: '30d', ...getPresetRange('30d', browserTimeZone) };
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

  const fetchAnalytics = useCallback(async () => {
    if (!range?.startDate || !range?.endDate) {
      return null;
    }
    const params = buildParamsFromRange(range, timeZone);
    return api.getWidgetAnalytics(params);
  }, [range, timeZone]);

  const { data, loading, error, refetch } = useFetchData(fetchAnalytics, {
    defaultValue: null,
    immediate: !needsTenant,
    deps: [selectedTenantId, range.startDate, range.endDate, timeZone],
  });

  // Fetch widget settings to show auto-open indicator
  const fetchSettings = useCallback(async () => {
    return api.getWidgetSettings();
  }, []);

  const { data: widgetSettings } = useFetchData(fetchSettings, {
    defaultValue: null,
    immediate: !needsTenant,
    deps: [selectedTenantId],
  });

  const isAutoOpenEnabled = widgetSettings?.behavior?.openBehavior === 'auto';
  const autoOpenDelay = widgetSettings?.behavior?.autoOpenDelay || 0;

  useEffect(() => {
    if (!data?.timezone || data.timezone === timeZone) return;
    const aligned = alignRangeToTimeZone(range, timeZone, data.timezone);
    setTimeZone(data.timezone);
    setRange(aligned);
    persistRange(aligned, data.timezone, setSearchParams, true);
  }, [data?.timezone, range, setSearchParams, timeZone]);

  const hasData = data && data.visibility && data.visibility.impressions > 0;

  if (needsTenant) {
    return (
      <div className="widget-analytics-page">
        <EmptyState
          icon="DATA"
          title="Select a tenant to view analytics"
          description="Please select a tenant from the dropdown above to view widget analytics."
        />
      </div>
    );
  }

  if (loading) {
    return <LoadingState message="Loading widget analytics..." fullPage />;
  }

  if (error) {
    if (error.includes('Tenant context required') || error.includes('Tenant context')) {
      return (
        <div className="widget-analytics-page">
          <EmptyState
            icon="DATA"
            title="Select a tenant to view analytics"
            description="Please select a tenant from the dropdown above to view widget analytics."
          />
        </div>
      );
    }
    return (
      <div className="widget-analytics-page">
        <ErrorState message={error} onRetry={refetch} />
      </div>
    );
  }

  const rangeLabel = formatRangeLabel(range.startDate, range.endDate, timeZone);

  const header = (
    <div className="widget-analytics-header">
      <div className="widget-analytics-header-top">
        <div className="widget-analytics-title">
          <h1>Widget Analytics</h1>
          {rangeLabel && (
            <p className="widget-analytics-subtitle">Tracking widget engagement from {rangeLabel}.</p>
          )}
        </div>
        <DateRangeFilter value={range} timeZone={timeZone} onChange={handleRangeChange} />
      </div>
      {hasData && (
        <div className="widget-analytics-summary">
          <div>
            <span className="summary-value">{formatNumber(data.visibility.impressions)}</span>
            <span className="summary-label">Impressions</span>
          </div>
          <div>
            <span className="summary-value">{formatPercent(data.attention.open_rate)}</span>
            <span className="summary-label">Open Rate</span>
          </div>
          <div>
            <span className="summary-value">{formatPercent(data.visibility.above_fold_rate)}</span>
            <span className="summary-label">Above Fold</span>
          </div>
          <div>
            <span className="summary-value">{formatPercent(data.attention.manual_open_rate)}</span>
            <span className="summary-label">Manual Opens</span>
          </div>
        </div>
      )}
    </div>
  );

  if (!hasData) {
    return (
      <div className="widget-analytics-page">
        {header}
        <EmptyState
          icon="INFO"
          title="No widget data yet"
          description="Analytics will appear once visitors start viewing your chat widget."
        />
      </div>
    );
  }

  return (
    <div className="widget-analytics-page">
      {header}

      <div className="widget-analytics-grid">
        {/* Visibility Metrics */}
        <section className="widget-analytics-card">
          <div className="widget-analytics-card-header">
            <div>
              <h2>Visibility Metrics</h2>
              <p>How often the widget is seen by visitors.</p>
            </div>
          </div>
          <div className="metric-rows">
            <div className="metric-row">
              <span className="metric-label">
                Widget Impressions
                <span className="info-icon" title="Times the widget loaded on a page">i</span>
              </span>
              <span className="metric-value">{formatNumber(data.visibility.impressions)}</span>
            </div>
            <div className="metric-row">
              <span className="metric-label">
                Render Success Rate
                <span className="info-icon" title="Percentage of impressions that rendered without errors">i</span>
              </span>
              <span className="metric-value">{formatPercent(data.visibility.render_success_rate)}</span>
            </div>
            <div className="metric-row">
              <span className="metric-label">
                Above-the-Fold Views
                <span className="info-icon" title="Widget visible without scrolling">i</span>
              </span>
              <span className="metric-value">
                {formatNumber(data.visibility.above_fold_views)} ({formatPercent(data.visibility.above_fold_rate)})
              </span>
            </div>
            <div className="metric-row">
              <span className="metric-label">
                Avg Time to First View
                <span className="info-icon" title="Average time until widget first became visible">i</span>
              </span>
              <span className="metric-value">{formatTime(data.visibility.avg_time_to_first_view_ms)}</span>
            </div>
          </div>
        </section>

        {/* Attention Capture */}
        <section className="widget-analytics-card">
          <div className="widget-analytics-card-header">
            <div>
              <h2>Attention Capture</h2>
              <p>How effectively the widget captures visitor attention.</p>
            </div>
          </div>
          {isAutoOpenEnabled && (
            <div className="auto-open-indicator">
              <span className="auto-open-badge">Auto-Open Enabled</span>
              <span className="auto-open-detail">
                Widget opens automatically after {autoOpenDelay}s
              </span>
            </div>
          )}
          <div className="metric-rows">
            <div className="metric-row">
              <span className="metric-label">
                Widget Opens
                <span className="info-icon" title="Total times the chat was opened">i</span>
              </span>
              <span className="metric-value">
                {formatNumber(data.attention.widget_opens)} ({formatPercent(data.attention.open_rate)})
              </span>
            </div>
            <div className="metric-row">
              <span className="metric-label">
                Manual Opens
                <span className="info-icon" title="User clicked to open (not auto-opened)">i</span>
              </span>
              <span className="metric-value">
                {formatNumber(data.attention.manual_opens)} ({formatPercent(data.attention.manual_open_rate)})
              </span>
            </div>
            <div className="metric-row">
              <span className="metric-label">
                Auto-Opens
                <span className="info-icon" title="Widget opened automatically based on settings">i</span>
              </span>
              <span className="metric-value">{formatNumber(data.attention.auto_opens)}</span>
            </div>
            <div className="metric-row">
              <span className="metric-label">
                Auto-Open Dismiss Rate
                <span className="info-icon" title="Percentage of auto-opens that were immediately closed">i</span>
              </span>
              <span className="metric-value">
                {formatNumber(data.attention.auto_open_dismiss_count)} ({formatPercent(data.attention.auto_open_dismiss_rate)})
              </span>
            </div>
            <div className="metric-row">
              <span className="metric-label">
                Hover/Focus Events
                <span className="info-icon" title="User hovered or focused on widget without opening">i</span>
              </span>
              <span className="metric-value">
                {formatNumber(data.attention.hover_count)} ({formatPercent(data.attention.hover_rate)})
              </span>
            </div>
          </div>
        </section>

        {/* Engagement Funnel */}
        <section className="widget-analytics-card widget-analytics-card-wide">
          <div className="widget-analytics-card-header">
            <div>
              <h2>Engagement Funnel</h2>
              <p>Visitor journey from impression to engagement.</p>
            </div>
          </div>
          <div className="funnel-container">
            <div className="funnel-step">
              <div className="funnel-bar" style={{ width: '100%' }} />
              <div className="funnel-label">
                <span className="funnel-count">{formatNumber(data.visibility.impressions)}</span>
                <span className="funnel-name">Impressions</span>
              </div>
            </div>
            <div className="funnel-step">
              <div
                className="funnel-bar"
                style={{
                  width: data.visibility.impressions > 0
                    ? `${Math.max(5, (data.attention.hover_count / data.visibility.impressions) * 100)}%`
                    : '5%'
                }}
              />
              <div className="funnel-label">
                <span className="funnel-count">{formatNumber(data.attention.hover_count)}</span>
                <span className="funnel-name">Hover/Focus</span>
              </div>
            </div>
            <div className="funnel-step">
              <div
                className="funnel-bar funnel-bar-primary"
                style={{
                  width: data.visibility.impressions > 0
                    ? `${Math.max(5, (data.attention.widget_opens / data.visibility.impressions) * 100)}%`
                    : '5%'
                }}
              />
              <div className="funnel-label">
                <span className="funnel-count">{formatNumber(data.attention.widget_opens)}</span>
                <span className="funnel-name">Opens</span>
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
