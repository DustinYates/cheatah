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
import './ConversationAnalytics.css';

const STORAGE_KEY = 'conversationAnalyticsDateRange';
const PRESET_VALUES = new Set(DATE_RANGE_PRESETS.map((preset) => preset.value));

const formatDuration = (minutes) => {
  if (!minutes || minutes === 0) return '0m';
  if (minutes < 1) return `${Math.round(minutes * 60)}s`;
  if (minutes < 60) return `${minutes.toFixed(1)}m`;
  const hours = Math.floor(minutes / 60);
  const mins = Math.round(minutes % 60);
  return mins > 0 ? `${hours}h ${mins}m` : `${hours}h`;
};

const formatSeconds = (seconds) => {
  if (!seconds || seconds === 0) return '0s';
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const minutes = Math.floor(seconds / 60);
  const secs = Math.round(seconds % 60);
  return secs > 0 ? `${minutes}m ${secs}s` : `${minutes}m`;
};

const formatPercent = (rate) => {
  if (!rate || rate === 0) return '0%';
  return `${(rate * 100).toFixed(1)}%`;
};

const formatIntentLabel = (intent) => {
  if (!intent) return 'Unknown';
  return intent
    .split('_')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
};

const CHANNEL_COLORS = {
  web: '#3f8f66',
  sms: '#c0842b',
  voice: '#4f6fd9',
};

const CHANNEL_LABELS = {
  web: 'Web Chat',
  sms: 'SMS',
  voice: 'Voice',
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

export default function ConversationAnalytics() {
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
    return api.getConversationAnalytics(params);
  }, [range, timeZone]);

  const { data, loading, error, refetch } = useFetchData(fetchAnalytics, {
    defaultValue: null,
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

  const hasData = data && data.conversation_length && data.escalation_metrics.total_conversations > 0;

  if (needsTenant) {
    return (
      <div className="conversation-analytics-page">
        <EmptyState
          icon="DATA"
          title="Select a tenant to view analytics"
          description="Please select a tenant from the dropdown above to view conversation analytics."
        />
      </div>
    );
  }

  if (loading) {
    return <LoadingState message="Loading conversation analytics..." fullPage />;
  }

  if (error) {
    if (error.includes('Tenant context required') || error.includes('Tenant context')) {
      return (
        <div className="conversation-analytics-page">
          <EmptyState
            icon="DATA"
            title="Select a tenant to view analytics"
            description="Please select a tenant from the dropdown above to view conversation analytics."
          />
        </div>
      );
    }
    return (
      <div className="conversation-analytics-page">
        <ErrorState message={error} onRetry={refetch} />
      </div>
    );
  }

  const rangeLabel = formatRangeLabel(range.startDate, range.endDate, timeZone);

  const header = (
    <div className="conv-analytics-header">
      <div className="conv-analytics-header-top">
        <div className="conv-analytics-title">
          <h1>Conversation Analytics</h1>
          {rangeLabel && (
            <p className="conv-analytics-subtitle">Analyzing conversations from {rangeLabel}.</p>
          )}
        </div>
        <DateRangeFilter value={range} timeZone={timeZone} onChange={handleRangeChange} />
      </div>
      {hasData && (
        <div className="conv-analytics-summary">
          <div>
            <span className="summary-value">{data.conversation_length.avg_message_count}</span>
            <span className="summary-label">Avg Messages</span>
          </div>
          <div>
            <span className="summary-value">{formatDuration(data.conversation_length.avg_duration_minutes)}</span>
            <span className="summary-label">Avg Duration</span>
          </div>
          <div>
            <span className="summary-value">{formatPercent(data.escalation_metrics.escalation_rate)}</span>
            <span className="summary-label">Escalation Rate</span>
          </div>
          <div>
            <span className="summary-value">{formatSeconds(data.response_times.avg_response_time_seconds)}</span>
            <span className="summary-label">Avg Response Time</span>
          </div>
        </div>
      )}
    </div>
  );

  if (!hasData) {
    return (
      <div className="conversation-analytics-page">
        {header}
        <EmptyState
          icon="INFO"
          title="No conversation data yet"
          description="Analytics will appear once customers start having conversations."
        />
      </div>
    );
  }

  const byChannel = data.conversation_length.by_channel || {};
  const channels = Object.keys(byChannel);
  const maxMessages = Math.max(1, ...channels.map((ch) => byChannel[ch]?.avg_messages || 0));
  const maxDuration = Math.max(1, ...channels.map((ch) => byChannel[ch]?.avg_duration_minutes || 0));

  const responseByChannel = data.response_times.by_channel || {};
  const responseChannels = Object.keys(responseByChannel);
  const maxResponseTime = Math.max(1, ...responseChannels.map((ch) => responseByChannel[ch] || 0));

  const intentDistribution = data.intent_distribution || [];
  const maxIntentCount = Math.max(1, ...intentDistribution.map((i) => i.count));

  return (
    <div className="conversation-analytics-page">
      {header}

      <div className="conv-analytics-grid">
        {/* Conversation Length by Channel */}
        <section className="conv-analytics-card">
          <div className="conv-analytics-card-header">
            <div>
              <h2>Conversation Length by Channel</h2>
              <p>Average messages and duration per conversation.</p>
            </div>
          </div>
          <div className="channel-metrics">
            {channels.length === 0 ? (
              <p className="no-data-message">No channel data available</p>
            ) : (
              channels.map((channel) => {
                const metrics = byChannel[channel];
                const msgWidth = ((metrics?.avg_messages || 0) / maxMessages) * 100;
                const durWidth = ((metrics?.avg_duration_minutes || 0) / maxDuration) * 100;
                return (
                  <div key={channel} className="channel-row">
                    <div className="channel-label">{CHANNEL_LABELS[channel] || channel}</div>
                    <div className="channel-bars">
                      <div className="channel-bar-row">
                        <div
                          className="channel-bar"
                          style={{
                            width: `${msgWidth}%`,
                            backgroundColor: CHANNEL_COLORS[channel] || '#666',
                          }}
                        />
                        <span className="channel-value">{metrics?.avg_messages || 0} msgs</span>
                      </div>
                      <div className="channel-bar-row">
                        <div
                          className="channel-bar duration"
                          style={{
                            width: `${durWidth}%`,
                            backgroundColor: CHANNEL_COLORS[channel] || '#666',
                            opacity: 0.6,
                          }}
                        />
                        <span className="channel-value">{formatDuration(metrics?.avg_duration_minutes || 0)}</span>
                      </div>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </section>

        {/* Escalation Metrics */}
        <section className="conv-analytics-card">
          <div className="conv-analytics-card-header">
            <div>
              <h2>Escalation Rate</h2>
              <p>Percentage of conversations requiring human handoff.</p>
            </div>
          </div>
          <div className="escalation-metrics">
            <div className="escalation-rate-display">
              <div className="escalation-rate-circle">
                <span className="escalation-rate-value">
                  {formatPercent(data.escalation_metrics.escalation_rate)}
                </span>
              </div>
              <div className="escalation-details">
                <div className="escalation-detail">
                  <span className="detail-value">{data.escalation_metrics.total_conversations}</span>
                  <span className="detail-label">Total Conversations</span>
                </div>
                <div className="escalation-detail">
                  <span className="detail-value">{data.escalation_metrics.total_escalations}</span>
                  <span className="detail-label">Escalations</span>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* Response Time by Channel */}
        <section className="conv-analytics-card">
          <div className="conv-analytics-card-header">
            <div>
              <h2>Response Time by Channel</h2>
              <p>Average time to respond to customer messages.</p>
            </div>
          </div>
          <div className="channel-metrics">
            {responseChannels.length === 0 ? (
              <p className="no-data-message">No response time data available</p>
            ) : (
              responseChannels.map((channel) => {
                const time = responseByChannel[channel] || 0;
                const width = (time / maxResponseTime) * 100;
                return (
                  <div key={channel} className="channel-row">
                    <div className="channel-label">{CHANNEL_LABELS[channel] || channel}</div>
                    <div className="channel-bars">
                      <div className="channel-bar-row">
                        <div
                          className="channel-bar"
                          style={{
                            width: `${width}%`,
                            backgroundColor: CHANNEL_COLORS[channel] || '#666',
                          }}
                        />
                        <span className="channel-value">{formatSeconds(time)}</span>
                      </div>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </section>

        {/* Intent Distribution */}
        <section className="conv-analytics-card">
          <div className="conv-analytics-card-header">
            <div>
              <h2>Customer Intents</h2>
              <p>Common reasons customers call (from voice calls only).</p>
            </div>
          </div>
          <div className="intent-distribution">
            {intentDistribution.length === 0 ? (
              <p className="no-data-message">No intent data available. Intents are captured from voice calls with summaries.</p>
            ) : (
              intentDistribution.map((item) => {
                const width = (item.count / maxIntentCount) * 100;
                return (
                  <div key={item.intent} className="intent-row">
                    <div className="intent-label">{formatIntentLabel(item.intent)}</div>
                    <div className="intent-bar-container">
                      <div
                        className="intent-bar"
                        style={{ width: `${width}%` }}
                      />
                      <span className="intent-value">{item.count} ({item.percentage}%)</span>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
