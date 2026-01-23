import { useCallback, useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Download } from 'lucide-react';
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

  // Fetch settings snapshots for A/B testing analysis
  const fetchSnapshots = useCallback(async () => {
    if (!range?.startDate || !range?.endDate) {
      return null;
    }
    const params = buildParamsFromRange(range, timeZone);
    return api.getWidgetSettingsSnapshots(params);
  }, [range, timeZone]);

  const { data: snapshotsData } = useFetchData(fetchSnapshots, {
    defaultValue: null,
    immediate: !needsTenant,
    deps: [selectedTenantId, range.startDate, range.endDate, timeZone],
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
                <span className="info-icon" data-tooltip="Total number of times the chat widget loaded on a page. Each page visit where the widget appears counts as one impression.">i</span>
              </span>
              <span className="metric-value">{formatNumber(data.visibility.impressions)}</span>
            </div>
            <div className="metric-row">
              <span className="metric-label">
                Render Success Rate
                <span className="info-icon" data-tooltip="Percentage of widget load attempts that rendered successfully without JavaScript errors. Low rates may indicate script conflicts or browser compatibility issues.">i</span>
              </span>
              <span className="metric-value">{formatPercent(data.visibility.render_success_rate)}</span>
            </div>
            <div className="metric-row">
              <span className="metric-label">
                Above-the-Fold Views
                <span className="info-icon" data-tooltip="Number of times the widget was visible without the visitor scrolling. Higher rates mean better initial visibility and more engagement opportunities.">i</span>
              </span>
              <span className="metric-value">
                {formatNumber(data.visibility.above_fold_views)} ({formatPercent(data.visibility.above_fold_rate)})
              </span>
            </div>
            <div className="metric-row">
              <span className="metric-label">
                Avg Time to First View
                <span className="info-icon" data-tooltip="Average time from page load until the widget becomes visible in the viewport. Lower times mean faster engagement opportunities.">i</span>
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
          <div className="metric-rows">
            <div className="metric-row">
              <span className="metric-label">
                Auto-Open Status
                <span className="info-icon" data-tooltip="Current setting for automatic widget expansion. When enabled, the widget opens after the specified delay to proactively engage visitors.">i</span>
              </span>
              <span className="metric-value">
                {isAutoOpenEnabled ? `Enabled (${autoOpenDelay}s delay)` : 'Disabled'}
              </span>
            </div>
            <div className="metric-row">
              <span className="metric-label">
                Widget Opens
                <span className="info-icon" data-tooltip="Total times the chat window was expanded (both manual clicks and auto-opens combined). The percentage shows your overall engagement rate.">i</span>
              </span>
              <span className="metric-value">
                {formatNumber(data.attention.widget_opens)} ({formatPercent(data.attention.open_rate)})
              </span>
            </div>
            <div className="metric-row">
              <span className="metric-label">
                Manual Opens
                <span className="info-icon" data-tooltip="Times visitors clicked to open the widget themselves. High manual opens indicate strong visitor intent and interest in engaging.">i</span>
              </span>
              <span className="metric-value">
                {formatNumber(data.attention.manual_opens)} ({formatPercent(data.attention.manual_open_rate)})
              </span>
            </div>
            <div className="metric-row">
              <span className="metric-label">
                Auto-Opens
                <span className="info-icon" data-tooltip="Times the widget opened automatically based on your auto-open settings. Compare with dismiss rate to measure auto-open effectiveness.">i</span>
              </span>
              <span className="metric-value">{formatNumber(data.attention.auto_opens)}</span>
            </div>
            <div className="metric-row">
              <span className="metric-label">
                Auto-Open Dismiss Rate
                <span className="info-icon" data-tooltip="Percentage of auto-opens where visitors immediately closed the widget. High rates may suggest adjusting the auto-open delay or disabling auto-open.">i</span>
              </span>
              <span className="metric-value">
                {formatNumber(data.attention.auto_open_dismiss_count)} ({formatPercent(data.attention.auto_open_dismiss_rate)})
              </span>
            </div>
            <div className="metric-row">
              <span className="metric-label">
                Hover/Focus Events
                <span className="info-icon" data-tooltip="Times visitors showed interest by hovering over or focusing on the widget without opening. High hover with low opens may indicate the widget needs a clearer call-to-action.">i</span>
              </span>
              <span className="metric-value">
                {formatNumber(data.attention.hover_count)} ({formatPercent(data.attention.hover_rate)})
              </span>
            </div>
          </div>
        </section>

        {/* Widget Configuration */}
        {widgetSettings && (
          <section className="widget-analytics-card widget-analytics-card-wide">
            <div className="widget-analytics-card-header">
              <div>
                <h2>Widget Configuration</h2>
                <p>Current widget settings that produced these analytics. Change settings to A/B test different configurations.</p>
              </div>
              <button
                className="config-download-btn"
                onClick={() => {
                  const exportData = {
                    exportedAt: new Date().toISOString(),
                    dateRange: {
                      start: formatDateInTimeZone(range.startDate, 'yyyy-MM-dd', timeZone),
                      end: formatDateInTimeZone(range.endDate, 'yyyy-MM-dd', timeZone),
                      timezone: timeZone,
                    },
                    settings: widgetSettings,
                    analytics: data ? {
                      summary: {
                        impressions: data.visibility?.impressions || 0,
                        openRate: data.attention?.open_rate || 0,
                        aboveFoldRate: data.visibility?.above_fold_rate || 0,
                        manualOpenRate: data.attention?.manual_open_rate || 0,
                      },
                      visibility: {
                        impressions: data.visibility?.impressions || 0,
                        renderSuccessRate: data.visibility?.render_success_rate || 0,
                        aboveFoldViews: data.visibility?.above_fold_views || 0,
                        aboveFoldRate: data.visibility?.above_fold_rate || 0,
                        avgTimeToFirstViewMs: data.visibility?.avg_time_to_first_view_ms || 0,
                      },
                      attention: {
                        autoOpenEnabled: isAutoOpenEnabled,
                        autoOpenDelay: autoOpenDelay,
                        widgetOpens: data.attention?.widget_opens || 0,
                        openRate: data.attention?.open_rate || 0,
                        manualOpens: data.attention?.manual_opens || 0,
                        manualOpenRate: data.attention?.manual_open_rate || 0,
                        autoOpens: data.attention?.auto_opens || 0,
                        autoOpenDismissCount: data.attention?.auto_open_dismiss_count || 0,
                        autoOpenDismissRate: data.attention?.auto_open_dismiss_rate || 0,
                        hoverCount: data.attention?.hover_count || 0,
                        hoverRate: data.attention?.hover_rate || 0,
                      },
                      funnel: {
                        impressions: data.visibility?.impressions || 0,
                        hoverFocus: data.attention?.hover_count || 0,
                        opens: data.attention?.widget_opens || 0,
                        hoverToImpressionRate: data.visibility?.impressions > 0
                          ? (data.attention?.hover_count || 0) / data.visibility.impressions
                          : 0,
                        openToImpressionRate: data.visibility?.impressions > 0
                          ? (data.attention?.widget_opens || 0) / data.visibility.impressions
                          : 0,
                      },
                    } : null,
                    abTestingData: snapshotsData?.variations?.length > 1 ? {
                      totalVariations: snapshotsData.total_variations,
                      variations: snapshotsData.variations.map(v => ({
                        settingsHash: v.settings_hash,
                        impressions: v.metrics.impressions,
                        widgetOpens: v.metrics.widget_opens,
                        openRate: v.metrics.open_rate,
                        firstSeen: v.metrics.first_seen,
                        lastSeen: v.metrics.last_seen,
                        settings: v.settings,
                      })),
                    } : null,
                  };
                  const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' });
                  const url = URL.createObjectURL(blob);
                  const a = document.createElement('a');
                  a.href = url;
                  a.download = `widget-analytics-${formatDateInTimeZone(range.startDate, 'yyyy-MM-dd', timeZone)}-to-${formatDateInTimeZone(range.endDate, 'yyyy-MM-dd', timeZone)}.json`;
                  a.click();
                  URL.revokeObjectURL(url);
                }}
                title="Download configuration and stats as JSON"
              >
                <Download size={16} />
                Export
              </button>
            </div>
            <div className="config-grid">
              <div className="config-section">
                <h3>Behavior</h3>
                <div className="config-items">
                  <div className="config-item">
                    <span className="config-label">
                      Open Behavior
                      <span className="info-icon" data-tooltip="How the widget opens - 'click' requires user action, 'auto' opens automatically after delay.">i</span>
                    </span>
                    <span className="config-value">{widgetSettings.behavior?.openBehavior || 'click'}</span>
                  </div>
                  <div className="config-item">
                    <span className="config-label">
                      Auto-Open Delay
                      <span className="info-icon" data-tooltip="Seconds to wait before auto-opening the widget (when auto-open is enabled).">i</span>
                    </span>
                    <span className="config-value">{widgetSettings.behavior?.autoOpenDelay || 0}s</span>
                  </div>
                  <div className="config-item">
                    <span className="config-label">
                      Cooldown Period
                      <span className="info-icon" data-tooltip="Days before showing auto-open again to the same visitor.">i</span>
                    </span>
                    <span className="config-value">{widgetSettings.behavior?.cooldownDays || 0} days</span>
                  </div>
                </div>
              </div>
              <div className="config-section">
                <h3>Appearance</h3>
                <div className="config-items">
                  <div className="config-item">
                    <span className="config-label">
                      Icon Type
                      <span className="info-icon" data-tooltip="The launcher button style - emoji, image, or custom icon.">i</span>
                    </span>
                    <span className="config-value config-value-icon">
                      {widgetSettings.icon?.type === 'emoji' && widgetSettings.icon?.emoji}
                      {widgetSettings.icon?.type || 'emoji'}
                    </span>
                  </div>
                  <div className="config-item">
                    <span className="config-label">
                      Icon Size
                      <span className="info-icon" data-tooltip="Size of the launcher button - affects visibility and click area.">i</span>
                    </span>
                    <span className="config-value">{widgetSettings.icon?.size || 'medium'}</span>
                  </div>
                  <div className="config-item">
                    <span className="config-label">
                      Primary Color
                      <span className="info-icon" data-tooltip="Main brand color used for the widget header and buttons.">i</span>
                    </span>
                    <span className="config-value">
                      <span
                        className="config-color-swatch"
                        style={{ backgroundColor: widgetSettings.colors?.primary || '#007bff' }}
                      />
                      {widgetSettings.colors?.primary || '#007bff'}
                    </span>
                  </div>
                </div>
              </div>
              <div className="config-section">
                <h3>Attention Grabbers</h3>
                <div className="config-items">
                  <div className="config-item">
                    <span className="config-label">
                      Animation
                      <span className="info-icon" data-tooltip="Attention animation to draw visitor eyes to the widget.">i</span>
                    </span>
                    <span className="config-value">{widgetSettings.attention?.attentionAnimation || 'none'}</span>
                  </div>
                  <div className="config-item">
                    <span className="config-label">
                      Unread Dot
                      <span className="info-icon" data-tooltip="Show a notification dot to simulate an unread message and drive opens.">i</span>
                    </span>
                    <span className="config-value">{widgetSettings.attention?.unreadDot ? 'Enabled' : 'Disabled'}</span>
                  </div>
                  <div className="config-item">
                    <span className="config-label">
                      Entry Animation
                      <span className="info-icon" data-tooltip="How the widget appears when it first loads on the page.">i</span>
                    </span>
                    <span className="config-value">{widgetSettings.motion?.entryAnimation || 'none'}</span>
                  </div>
                </div>
              </div>
              <div className="config-section">
                <h3>Position & Visibility</h3>
                <div className="config-items">
                  <div className="config-item">
                    <span className="config-label">
                      Position
                      <span className="info-icon" data-tooltip="Screen corner where the widget appears.">i</span>
                    </span>
                    <span className="config-value">{widgetSettings.layout?.position || 'bottom-right'}</span>
                  </div>
                  <div className="config-item">
                    <span className="config-label">
                      Launcher Visibility
                      <span className="info-icon" data-tooltip="When the launcher button first appears - immediately, on scroll, or after delay.">i</span>
                    </span>
                    <span className="config-value">{widgetSettings.motion?.launcherVisibility || 'immediate'}</span>
                  </div>
                  <div className="config-item">
                    <span className="config-label">
                      Show on Pages
                      <span className="info-icon" data-tooltip="Which pages display the widget (* = all pages).">i</span>
                    </span>
                    <span className="config-value config-value-truncate">{widgetSettings.behavior?.showOnPages || '*'}</span>
                  </div>
                </div>
              </div>
            </div>
          </section>
        )}

        {/* A/B Testing - Settings Variations */}
        {snapshotsData && snapshotsData.variations && snapshotsData.variations.length > 1 && (
          <section className="widget-analytics-card widget-analytics-card-wide">
            <div className="widget-analytics-card-header">
              <div>
                <h2>A/B Testing Results</h2>
                <p>
                  Compare performance across {snapshotsData.total_variations} different widget configurations used during this period.
                  <span className="info-icon" data-tooltip="When you change widget settings, each configuration's performance is tracked separately. Compare open rates to see which settings work best.">i</span>
                </p>
              </div>
            </div>
            <div className="ab-test-table">
              <div className="ab-test-header">
                <span className="ab-test-col ab-test-col-config">Configuration</span>
                <span className="ab-test-col ab-test-col-metric">Impressions</span>
                <span className="ab-test-col ab-test-col-metric">Opens</span>
                <span className="ab-test-col ab-test-col-metric">Open Rate</span>
                <span className="ab-test-col ab-test-col-date">Active Period</span>
              </div>
              {snapshotsData.variations.map((variation, index) => {
                const settings = variation.settings || {};
                const behavior = settings.behavior || {};
                const icon = settings.icon || {};
                const attention = settings.attention || {};
                const colors = settings.colors || {};

                // Create a summary of the key settings
                const configSummary = [
                  behavior.openBehavior === 'auto' ? `Auto-open (${behavior.autoOpenDelay}s)` : 'Click to open',
                  icon.type === 'emoji' ? icon.emoji : icon.type,
                  attention.attentionAnimation !== 'none' ? attention.attentionAnimation : null,
                  attention.unreadDot ? 'Unread dot' : null,
                ].filter(Boolean).join(' · ');

                const firstSeen = new Date(variation.metrics.first_seen);
                const lastSeen = new Date(variation.metrics.last_seen);
                const dateRange = firstSeen.toLocaleDateString() === lastSeen.toLocaleDateString()
                  ? firstSeen.toLocaleDateString()
                  : `${firstSeen.toLocaleDateString()} - ${lastSeen.toLocaleDateString()}`;

                // Determine if this is the best performing variation
                const bestOpenRate = Math.max(...snapshotsData.variations.map(v => v.metrics.open_rate));
                const isBest = variation.metrics.open_rate === bestOpenRate && snapshotsData.variations.length > 1;

                return (
                  <div key={variation.settings_hash} className={`ab-test-row ${isBest ? 'ab-test-row-best' : ''}`}>
                    <span className="ab-test-col ab-test-col-config">
                      <span
                        className="ab-test-color-indicator"
                        style={{ backgroundColor: colors.primary || '#007bff' }}
                      />
                      <span className="ab-test-config-text">
                        {configSummary || 'Default settings'}
                        {isBest && <span className="ab-test-badge">Best</span>}
                      </span>
                    </span>
                    <span className="ab-test-col ab-test-col-metric">{formatNumber(variation.metrics.impressions)}</span>
                    <span className="ab-test-col ab-test-col-metric">{formatNumber(variation.metrics.widget_opens)}</span>
                    <span className="ab-test-col ab-test-col-metric ab-test-col-rate">
                      {formatPercent(variation.metrics.open_rate)}
                    </span>
                    <span className="ab-test-col ab-test-col-date">{dateRange}</span>
                  </div>
                );
              })}
            </div>
          </section>
        )}

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
