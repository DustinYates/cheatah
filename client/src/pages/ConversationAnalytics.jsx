import { useCallback, useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { HelpCircle } from 'lucide-react';
import { api } from '../api/client';
import { useFetchData } from '../hooks/useFetchData';
import { useAuth } from '../context/AuthContext';
import DateRangeFilter from '../components/DateRangeFilter';
import MetricCard from '../components/MetricCard';
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

const REASON_LABELS = {
  low_confidence: 'Bot Uncertainty',
  explicit_request: 'User Requested',
  manual: 'Manual',
  unknown: 'Unknown',
};

const formatNumber = (num) => {
  if (!num || num === 0) return '0';
  return num.toLocaleString();
};

const InfoTooltip = ({ text }) => (
  <span className="info-tooltip">
    <HelpCircle size={16} />
    <span className="info-tooltip-text">{text}</span>
  </span>
);

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
          <MetricCard
            label="Avg Messages"
            value={data.conversation_length.avg_message_count}
            tooltip="Computed using: average message count across all conversations in this period."
          />
          <MetricCard
            label="Avg Duration"
            value={formatDuration(data.conversation_length.avg_duration_minutes)}
            tooltip="Computed using: average time between first and last message per conversation."
          />
          <MetricCard
            label="Escalation Rate"
            value={formatPercent(data.escalation_metrics.escalation_rate)}
            tooltip="Computed using: escalated conversations / total conversations."
            severity={data.escalation_metrics.escalation_rate > 0.2 ? 'warning' : undefined}
          />
          <MetricCard
            label="Avg Response Time"
            value={formatSeconds(data.response_times.avg_response_time_seconds)}
            tooltip="Computed using: average delay between user message and next assistant response."
          />
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

        {/* Phone Call Statistics by Language */}
        {data.phone_call_statistics && data.phone_call_statistics.total_calls > 0 && (
          <section className="conv-analytics-card">
            <div className="conv-analytics-card-header">
              <div>
                <h2>Phone Call Statistics</h2>
                <p>Call volume and duration by language (Spanish vs English).</p>
              </div>
            </div>
            <div className="phone-call-stats">
              {/* Summary Row */}
              <div style={{ display: 'flex', justifyContent: 'space-around', textAlign: 'center', marginBottom: '1.5rem' }}>
                <div>
                  <span style={{ fontSize: '2rem', fontWeight: 700, color: 'var(--color-primary)' }}>
                    {formatNumber(data.phone_call_statistics.total_calls)}
                  </span>
                  <span style={{ display: 'block', fontSize: '0.75rem', color: 'var(--color-text-muted)', marginTop: '0.25rem' }}>
                    Total Calls
                  </span>
                </div>
                <div>
                  <span style={{ fontSize: '2rem', fontWeight: 700, color: 'var(--color-text-primary)' }}>
                    {formatDuration(data.phone_call_statistics.total_minutes)}
                  </span>
                  <span style={{ display: 'block', fontSize: '0.75rem', color: 'var(--color-text-muted)', marginTop: '0.25rem' }}>
                    Total Duration
                  </span>
                </div>
              </div>

              {/* Language Distribution Bar */}
              {Object.keys(data.phone_call_statistics.by_language).length > 0 && (
                <div style={{ marginBottom: '1.5rem' }}>
                  <h3 style={{ fontSize: '0.875rem', fontWeight: 600, marginBottom: '0.75rem' }}>Language Distribution</h3>
                  <div style={{ display: 'flex', height: '32px', borderRadius: '4px', overflow: 'hidden' }}>
                    {(() => {
                      const byLang = data.phone_call_statistics.by_language;
                      const langDist = data.phone_call_statistics.language_distribution || {};
                      const LANG_COLORS = {
                        english: '#3f8f66',
                        spanish: '#c0842b',
                        unknown: '#888888',
                      };
                      const LANG_LABELS = {
                        english: 'English',
                        spanish: 'Spanish',
                        unknown: 'Unknown',
                      };
                      return Object.entries(byLang).map(([lang, stats]) => {
                        const pct = langDist[lang] || 0;
                        if (pct === 0) return null;
                        return (
                          <div
                            key={lang}
                            style={{
                              width: `${pct}%`,
                              backgroundColor: LANG_COLORS[lang] || '#666',
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              minWidth: pct > 5 ? 'auto' : '0',
                            }}
                            title={`${LANG_LABELS[lang] || lang}: ${stats.call_count} calls (${pct}%)`}
                          >
                            {pct >= 15 && (
                              <span style={{ fontSize: '0.75rem', color: 'white', fontWeight: 600 }}>
                                {LANG_LABELS[lang] || lang} {pct}%
                              </span>
                            )}
                          </div>
                        );
                      });
                    })()}
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '0.5rem', fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>
                    {Object.entries(data.phone_call_statistics.by_language).map(([lang, stats]) => {
                      const LANG_COLORS = { english: '#3f8f66', spanish: '#c0842b', unknown: '#888888' };
                      const LANG_LABELS = { english: 'English', spanish: 'Spanish', unknown: 'Unknown' };
                      return (
                        <span key={lang} style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                          <span style={{ display: 'inline-block', width: '8px', height: '8px', borderRadius: '50%', backgroundColor: LANG_COLORS[lang] || '#666' }}></span>
                          {LANG_LABELS[lang] || lang}
                        </span>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Detailed Stats by Language */}
              {Object.keys(data.phone_call_statistics.by_language).length > 0 && (
                <div style={{ paddingTop: '1rem', borderTop: '1px solid var(--color-border-light)' }}>
                  <h3 style={{ fontSize: '0.875rem', fontWeight: 600, marginBottom: '0.75rem' }}>By Language</h3>
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.875rem' }}>
                    <thead>
                      <tr style={{ borderBottom: '1px solid var(--color-border)' }}>
                        <th style={{ textAlign: 'left', padding: '0.5rem 0.25rem', fontWeight: 600 }}>Language</th>
                        <th style={{ textAlign: 'right', padding: '0.5rem 0.25rem', fontWeight: 600 }}>Calls</th>
                        <th style={{ textAlign: 'right', padding: '0.5rem 0.25rem', fontWeight: 600 }}>Duration</th>
                        <th style={{ textAlign: 'right', padding: '0.5rem 0.25rem', fontWeight: 600 }}>Avg Call</th>
                        <th style={{ textAlign: 'right', padding: '0.5rem 0.25rem', fontWeight: 600 }}>Leads</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(data.phone_call_statistics.by_language).map(([lang, stats]) => {
                        const LANG_COLORS = { english: '#3f8f66', spanish: '#c0842b', unknown: '#888888' };
                        const LANG_LABELS = { english: 'English', spanish: 'Spanish', unknown: 'Unknown' };
                        return (
                          <tr key={lang} style={{ borderBottom: '1px solid var(--color-border-light)' }}>
                            <td style={{ padding: '0.5rem 0.25rem', fontWeight: 500 }}>
                              <span style={{ display: 'inline-block', width: '8px', height: '8px', borderRadius: '50%', backgroundColor: LANG_COLORS[lang] || '#666', marginRight: '0.5rem' }}></span>
                              {LANG_LABELS[lang] || lang}
                            </td>
                            <td style={{ textAlign: 'right', padding: '0.5rem 0.25rem' }}>{formatNumber(stats.call_count)}</td>
                            <td style={{ textAlign: 'right', padding: '0.5rem 0.25rem' }}>{formatDuration(stats.total_minutes)}</td>
                            <td style={{ textAlign: 'right', padding: '0.5rem 0.25rem' }}>{formatDuration(stats.avg_duration_minutes)}</td>
                            <td style={{ textAlign: 'right', padding: '0.5rem 0.25rem', color: stats.leads_generated > 0 ? 'var(--color-success)' : 'inherit' }}>
                              {formatNumber(stats.leads_generated)}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </section>
        )}

        {/* Escalation by Channel */}
        {data.escalation_by_channel && (
          <section className="conv-analytics-card">
            <div className="conv-analytics-card-header">
              <div>
                <h2>Escalation by Channel</h2>
                <p>Escalation rates broken down by communication channel.</p>
              </div>
            </div>
            <div className="channel-metrics">
              {(() => {
                const escByChannel = data.escalation_by_channel.by_channel || {};
                const escChannels = Object.keys(escByChannel);
                const maxEscRate = Math.max(0.01, ...escChannels.map((ch) => escByChannel[ch]?.rate || 0));

                return escChannels.length === 0 ? (
                  <p className="no-data-message">No escalation data by channel available</p>
                ) : (
                  escChannels.map((channel) => {
                    const escData = escByChannel[channel];
                    const width = ((escData?.rate || 0) / maxEscRate) * 100;
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
                            <span className="channel-value">
                              {formatPercent(escData?.rate || 0)} ({escData?.count || 0} / {escData?.conversations || 0})
                            </span>
                          </div>
                        </div>
                      </div>
                    );
                  })
                );
              })()}
            </div>
            {data.escalation_by_channel.by_reason && Object.keys(data.escalation_by_channel.by_reason).length > 0 && (
              <div className="escalation-reasons" style={{ marginTop: '1.5rem', paddingTop: '1rem', borderTop: '1px solid var(--color-border-light)' }}>
                <h3 style={{ fontSize: '0.875rem', fontWeight: 600, marginBottom: '0.75rem' }}>By Reason</h3>
                <div className="reason-list" style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
                  {Object.entries(data.escalation_by_channel.by_reason).map(([reason, count]) => (
                    <span key={reason} className="reason-badge" style={{
                      padding: '0.25rem 0.75rem',
                      backgroundColor: 'var(--color-bg-light)',
                      borderRadius: '1rem',
                      fontSize: '0.75rem',
                    }}>
                      {REASON_LABELS[reason] || formatIntentLabel(reason)}: {count}
                    </span>
                  ))}
                </div>
              </div>
            )}
            {data.escalation_by_channel.avg_messages_before_escalation > 0 && (
              <div className="escalation-timing" style={{ marginTop: '1rem', fontSize: '0.875rem', color: 'var(--color-text-secondary)' }}>
                Avg {data.escalation_by_channel.avg_messages_before_escalation} messages before escalation
              </div>
            )}
          </section>
        )}

        {/* Channel Effectiveness Matrix */}
        {data.channel_effectiveness && (
          <section className="conv-analytics-card conv-analytics-card-wide">
            <div className="conv-analytics-card-header">
              <div>
                <h2>
                  Channel Effectiveness
                  <InfoTooltip text="Compares performance metrics across Web Chat, SMS, and Voice channels. Conversion shows % of conversations that captured leads." />
                </h2>
                <p>Compare performance across communication channels.</p>
              </div>
            </div>
            <div className="channel-matrix" style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.875rem' }}>
                <thead>
                  <tr style={{ borderBottom: '2px solid var(--color-border)' }}>
                    <th style={{ textAlign: 'left', padding: '0.75rem 0.5rem', fontWeight: 600 }}>Channel</th>
                    <th style={{ textAlign: 'right', padding: '0.75rem 0.5rem', fontWeight: 600 }}>Conversations</th>
                    <th style={{ textAlign: 'right', padding: '0.75rem 0.5rem', fontWeight: 600 }}>Leads</th>
                    <th style={{ textAlign: 'right', padding: '0.75rem 0.5rem', fontWeight: 600 }}>Conversion</th>
                    <th style={{ textAlign: 'right', padding: '0.75rem 0.5rem', fontWeight: 600 }}>Escalation</th>
                    <th style={{ textAlign: 'right', padding: '0.75rem 0.5rem', fontWeight: 600 }}>Avg Msgs</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(data.channel_effectiveness.channels || {}).map(([channel, metrics]) => (
                    <tr key={channel} style={{ borderBottom: '1px solid var(--color-border-light)' }}>
                      <td style={{ padding: '0.75rem 0.5rem', fontWeight: 500 }}>
                        <span style={{ display: 'inline-block', width: '8px', height: '8px', borderRadius: '50%', backgroundColor: CHANNEL_COLORS[channel] || '#666', marginRight: '0.5rem' }}></span>
                        {CHANNEL_LABELS[channel] || channel}
                      </td>
                      <td style={{ textAlign: 'right', padding: '0.75rem 0.5rem' }}>{formatNumber(metrics.total_conversations)}</td>
                      <td style={{ textAlign: 'right', padding: '0.75rem 0.5rem' }}>{formatNumber(metrics.leads_captured)}</td>
                      <td style={{ textAlign: 'right', padding: '0.75rem 0.5rem', color: metrics.conversion_rate > 0.1 ? 'var(--color-success)' : 'inherit' }}>
                        {formatPercent(metrics.conversion_rate)}
                      </td>
                      <td style={{ textAlign: 'right', padding: '0.75rem 0.5rem', color: metrics.escalation_rate > 0.1 ? 'var(--color-warning)' : 'inherit' }}>
                        {formatPercent(metrics.escalation_rate)}
                      </td>
                      <td style={{ textAlign: 'right', padding: '0.75rem 0.5rem' }}>{metrics.avg_messages?.toFixed(1) || '0'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}

        {/* AI Value Metrics */}
        {data.ai_value && (
          <section className="conv-analytics-card">
            <div className="conv-analytics-card-header">
              <div>
                <h2>
                  AI Performance
                  <InfoTooltip text="Measures how well the AI handles conversations without human escalation. Resolution rate shows % resolved by AI alone." />
                </h2>
                <p>Conversations resolved without human intervention.</p>
              </div>
            </div>
            <div className="ai-value-metrics">
              <div className="ai-value-main" style={{ textAlign: 'center', marginBottom: '1.5rem' }}>
                <div className="ai-resolution-circle" style={{
                  width: '120px',
                  height: '120px',
                  borderRadius: '50%',
                  border: '8px solid var(--color-success)',
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  justifyContent: 'center',
                  margin: '0 auto',
                }}>
                  <span style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--color-success)' }}>
                    {formatPercent(data.ai_value.resolution_rate)}
                  </span>
                  <span style={{ fontSize: '0.625rem', color: 'var(--color-text-muted)' }}>Resolved by AI</span>
                </div>
              </div>
              <div className="ai-value-stats" style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '1rem', textAlign: 'center' }}>
                <div>
                  <span style={{ fontSize: '1.25rem', fontWeight: 700, display: 'block' }}>
                    {formatNumber(data.ai_value.conversations_resolved_without_human)}
                  </span>
                  <span style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>Resolved Without Human</span>
                </div>
                <div>
                  <span style={{ fontSize: '1.25rem', fontWeight: 700, display: 'block' }}>
                    {formatNumber(data.ai_value.leads_captured_automatically)}
                  </span>
                  <span style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>Leads Auto-Captured</span>
                </div>
                <div style={{ gridColumn: 'span 2' }}>
                  <span style={{ fontSize: '1.25rem', fontWeight: 700, display: 'block', color: 'var(--color-success)' }}>
                    {formatDuration(data.ai_value.estimated_staff_minutes_saved)}
                  </span>
                  <span style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>Est. Staff Time Saved</span>
                </div>
              </div>
            </div>
          </section>
        )}

        {/* Response Time Distribution */}
        {data.response_time_distribution && (
          <section className="conv-analytics-card">
            <div className="conv-analytics-card-header">
              <div>
                <h2>
                  Response Time Distribution
                  <InfoTooltip text="P50, P90, P99 are response time percentiles. P50 means 50% of responses were faster than this time." />
                </h2>
                <p>Response time percentiles across channels.</p>
              </div>
            </div>
            <div className="rt-distribution">
              <div className="rt-overall" style={{ display: 'flex', justifyContent: 'space-around', textAlign: 'center', marginBottom: '1.5rem', paddingBottom: '1rem', borderBottom: '1px solid var(--color-border-light)' }}>
                <div>
                  <span style={{ fontSize: '1.5rem', fontWeight: 700, display: 'block' }}>
                    {formatSeconds(data.response_time_distribution.p50_seconds)}
                  </span>
                  <span style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>P50</span>
                </div>
                <div>
                  <span style={{ fontSize: '1.5rem', fontWeight: 700, display: 'block' }}>
                    {formatSeconds(data.response_time_distribution.p90_seconds)}
                  </span>
                  <span style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>P90</span>
                </div>
                <div>
                  <span style={{ fontSize: '1.5rem', fontWeight: 700, display: 'block' }}>
                    {formatSeconds(data.response_time_distribution.p99_seconds)}
                  </span>
                  <span style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>P99</span>
                </div>
              </div>
              <div className="rt-first-response" style={{ textAlign: 'center', marginBottom: '1rem' }}>
                <span style={{ fontSize: '0.875rem', color: 'var(--color-text-muted)' }}>First Response Avg: </span>
                <span style={{ fontWeight: 600 }}>{formatSeconds(data.response_time_distribution.first_response_avg_seconds)}</span>
              </div>
              {data.response_time_distribution.by_channel && Object.keys(data.response_time_distribution.by_channel).length > 0 && (
                <div className="rt-by-channel">
                  <h3 style={{ fontSize: '0.875rem', fontWeight: 600, marginBottom: '0.75rem' }}>By Channel</h3>
                  {Object.entries(data.response_time_distribution.by_channel).map(([channel, metrics]) => (
                    <div key={channel} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '0.5rem 0', borderBottom: '1px solid var(--color-border-light)' }}>
                      <span style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                        <span style={{ display: 'inline-block', width: '8px', height: '8px', borderRadius: '50%', backgroundColor: CHANNEL_COLORS[channel] || '#666' }}></span>
                        {CHANNEL_LABELS[channel] || channel}
                      </span>
                      <span style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>
                        P50: {formatSeconds(metrics.p50)} | P90: {formatSeconds(metrics.p90)}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </section>
        )}

        {/* Phase 2: Drop-Off Analytics */}
        {data.drop_off && (
          <section className="conv-analytics-card">
            <div className="conv-analytics-card-header">
              <div>
                <h2>
                  Drop-Off Analytics
                  <InfoTooltip text="A conversation is 'completed' when it ends with a resolution: lead captured, registration link sent, escalation handled, or explicit goodbye. 'Dropped' means the user stopped responding without any resolution signal. Lower drop-off rates indicate better engagement." />
                </h2>
                <p>Conversations that ended without resolution.</p>
              </div>
            </div>
            <div className="drop-off-metrics">
              <div style={{ display: 'flex', justifyContent: 'space-around', textAlign: 'center', marginBottom: '1.5rem' }}>
                <div>
                  <div style={{
                    width: '100px',
                    height: '100px',
                    borderRadius: '50%',
                    border: `6px solid ${data.drop_off.drop_off_rate > 0.3 ? 'var(--color-warning)' : 'var(--color-success)'}`,
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    justifyContent: 'center',
                    margin: '0 auto',
                  }}>
                    <span style={{ fontSize: '1.25rem', fontWeight: 700, color: data.drop_off.drop_off_rate > 0.3 ? 'var(--color-warning)' : 'var(--color-success)' }}>
                      {formatPercent(data.drop_off.drop_off_rate)}
                    </span>
                    <span style={{ fontSize: '0.625rem', color: 'var(--color-text-muted)' }}>Drop-Off</span>
                  </div>
                </div>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '1rem', textAlign: 'center', paddingTop: '1rem', borderTop: '1px solid var(--color-border-light)' }}>
                <div>
                  <span style={{ fontSize: '1.25rem', fontWeight: 700, display: 'block' }}>{formatNumber(data.drop_off.completed_conversations)}</span>
                  <span style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>Completed</span>
                </div>
                <div>
                  <span style={{ fontSize: '1.25rem', fontWeight: 700, display: 'block', color: 'var(--color-warning)' }}>{formatNumber(data.drop_off.dropped_conversations)}</span>
                  <span style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>Dropped</span>
                </div>
                <div>
                  <span style={{ fontSize: '1.25rem', fontWeight: 700, display: 'block' }}>{data.drop_off.avg_messages_before_dropoff}</span>
                  <span style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>Avg Msgs Before</span>
                </div>
              </div>
              {data.drop_off.avg_time_to_dropoff_minutes > 0 && (
                <div style={{ textAlign: 'center', marginTop: '1rem', fontSize: '0.875rem', color: 'var(--color-text-muted)' }}>
                  Avg time to drop-off: {formatDuration(data.drop_off.avg_time_to_dropoff_minutes)}
                </div>
              )}
            </div>
          </section>
        )}

        {/* Phase 2: Pushback Detection */}
        {data.pushback && (
          <section className="conv-analytics-card">
            <div className="conv-analytics-card-header">
              <div>
                <h2>
                  User Friction Signals
                  <InfoTooltip text="Detects signs of user frustration like complaints or impatience in conversations." />
                </h2>
                <p>Detected frustration and impatience in conversations.</p>
              </div>
            </div>
            <div className="pushback-metrics">
              <div style={{ display: 'flex', justifyContent: 'space-around', textAlign: 'center', marginBottom: '1.5rem' }}>
                <div>
                  <span style={{ fontSize: '2rem', fontWeight: 700, color: data.pushback.pushback_rate > 0.1 ? 'var(--color-warning)' : 'var(--color-text-primary)' }}>
                    {formatPercent(data.pushback.pushback_rate)}
                  </span>
                  <span style={{ display: 'block', fontSize: '0.75rem', color: 'var(--color-text-muted)', marginTop: '0.25rem' }}>Pushback Rate</span>
                </div>
                <div>
                  <span style={{ fontSize: '2rem', fontWeight: 700 }}>{formatNumber(data.pushback.conversations_with_pushback)}</span>
                  <span style={{ display: 'block', fontSize: '0.75rem', color: 'var(--color-text-muted)', marginTop: '0.25rem' }}>Conversations</span>
                </div>
              </div>
              {data.pushback.by_type && Object.keys(data.pushback.by_type).length > 0 && (
                <div style={{ paddingTop: '1rem', borderTop: '1px solid var(--color-border-light)' }}>
                  <h3 style={{ fontSize: '0.875rem', fontWeight: 600, marginBottom: '0.75rem' }}>By Type</h3>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
                    {Object.entries(data.pushback.by_type).map(([type, count]) => (
                      <span key={type} style={{
                        padding: '0.25rem 0.75rem',
                        backgroundColor: type === 'frustration' ? 'var(--color-error-bg)' : 'var(--color-warning-bg)',
                        borderRadius: '1rem',
                        fontSize: '0.75rem',
                        border: `1px solid ${type === 'frustration' ? 'var(--color-error-border)' : 'var(--color-warning-border)'}`,
                      }}>
                        {formatIntentLabel(type)}: {count}
                      </span>
                    ))}
                  </div>
                </div>
              )}
              {data.pushback.common_triggers && data.pushback.common_triggers.length > 0 && (
                <div style={{ marginTop: '1rem', paddingTop: '1rem', borderTop: '1px solid var(--color-border-light)' }}>
                  <h3 style={{ fontSize: '0.875rem', fontWeight: 600, marginBottom: '0.5rem' }}>Common Phrases</h3>
                  <div style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)', fontStyle: 'italic' }}>
                    "{data.pushback.common_triggers.slice(0, 5).join('", "')}"
                  </div>
                </div>
              )}
            </div>
          </section>
        )}

        {/* Phase 2: Repetition Signals */}
        {data.repetition && (
          <section className="conv-analytics-card">
            <div className="conv-analytics-card-header">
              <div>
                <h2>
                  Conversation Confusion
                  <InfoTooltip text="Identifies when users or the bot repeated themselves or asked for clarification." />
                </h2>
                <p>Repeated questions and clarification requests.</p>
              </div>
            </div>
            <div className="repetition-metrics">
              <div style={{ display: 'flex', justifyContent: 'space-around', textAlign: 'center', marginBottom: '1.5rem' }}>
                <div>
                  <span style={{ fontSize: '2rem', fontWeight: 700, color: data.repetition.repetition_rate > 0.15 ? 'var(--color-warning)' : 'var(--color-text-primary)' }}>
                    {formatPercent(data.repetition.repetition_rate)}
                  </span>
                  <span style={{ display: 'block', fontSize: '0.75rem', color: 'var(--color-text-muted)', marginTop: '0.25rem' }}>Repetition Rate</span>
                </div>
                <div>
                  <span style={{ fontSize: '2rem', fontWeight: 700 }}>{(data.repetition.avg_repetition_score * 100).toFixed(0)}%</span>
                  <span style={{ display: 'block', fontSize: '0.75rem', color: 'var(--color-text-muted)', marginTop: '0.25rem' }}>Friction Score</span>
                </div>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '1rem', textAlign: 'center', paddingTop: '1rem', borderTop: '1px solid var(--color-border-light)' }}>
                <div>
                  <span style={{ fontSize: '1.25rem', fontWeight: 700, display: 'block' }}>{formatNumber(data.repetition.total_repeated_questions)}</span>
                  <span style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>Repeated Questions</span>
                </div>
                <div>
                  <span style={{ fontSize: '1.25rem', fontWeight: 700, display: 'block' }}>{formatNumber(data.repetition.total_user_clarifications)}</span>
                  <span style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>User Clarifications</span>
                </div>
                <div>
                  <span style={{ fontSize: '1.25rem', fontWeight: 700, display: 'block' }}>{formatNumber(data.repetition.total_bot_clarifications)}</span>
                  <span style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>Bot Clarifications</span>
                </div>
              </div>
            </div>
          </section>
        )}

        {/* Phase 2: Demand Intelligence */}
        {data.demand && (Object.keys(data.demand.requests_by_location).length > 0 || Object.keys(data.demand.requests_by_class_level).length > 0) && (
          <section className="conv-analytics-card conv-analytics-card-wide">
            <div className="conv-analytics-card-header">
              <div>
                <h2>
                  Demand Intelligence
                  <InfoTooltip text="Shows location and class demand patterns. Peak Hours displays the busiest times in Chicago timezone (CST/CDT)." />
                </h2>
                <p>Location and class demand patterns.</p>
              </div>
            </div>
            <div className="demand-metrics" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1.5rem' }}>
              {/* Location Demand */}
              {Object.keys(data.demand.requests_by_location).length > 0 && (
                <div>
                  <h3 style={{ fontSize: '0.875rem', fontWeight: 600, marginBottom: '0.75rem' }}>By Location</h3>
                  {(() => {
                    const locations = data.demand.requests_by_location;
                    const maxLoc = Math.max(1, ...Object.values(locations));
                    return Object.entries(locations).map(([loc, count]) => (
                      <div key={loc} style={{ marginBottom: '0.5rem' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.25rem', fontSize: '0.875rem' }}>
                          <span>{loc}</span>
                          <span style={{ fontWeight: 600 }}>{count}</span>
                        </div>
                        <div style={{ height: '6px', backgroundColor: 'var(--color-bg-light)', borderRadius: '3px' }}>
                          <div style={{ height: '100%', width: `${(count / maxLoc) * 100}%`, backgroundColor: 'var(--color-primary)', borderRadius: '3px' }}></div>
                        </div>
                      </div>
                    ));
                  })()}
                </div>
              )}

              {/* Class Level Demand */}
              {Object.keys(data.demand.requests_by_class_level).length > 0 && (
                <div>
                  <h3 style={{ fontSize: '0.875rem', fontWeight: 600, marginBottom: '0.75rem' }}>By Class Level</h3>
                  {(() => {
                    const classes = data.demand.requests_by_class_level;
                    const maxClass = Math.max(1, ...Object.values(classes));
                    return Object.entries(classes).map(([cls, count]) => (
                      <div key={cls} style={{ marginBottom: '0.5rem' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.25rem', fontSize: '0.875rem' }}>
                          <span>{cls}</span>
                          <span style={{ fontWeight: 600 }}>{count}</span>
                        </div>
                        <div style={{ height: '6px', backgroundColor: 'var(--color-bg-light)', borderRadius: '3px' }}>
                          <div style={{ height: '100%', width: `${(count / maxClass) * 100}%`, backgroundColor: '#4f6fd9', borderRadius: '3px' }}></div>
                        </div>
                      </div>
                    ));
                  })()}
                </div>
              )}

              {/* Adult vs Child Split */}
              {(data.demand.adult_vs_child.adult > 0 || data.demand.adult_vs_child.child > 0) && (
                <div>
                  <h3 style={{ fontSize: '0.875rem', fontWeight: 600, marginBottom: '0.75rem' }}>Adult vs Child</h3>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                    <div style={{ flex: 1 }}>
                      <div style={{ display: 'flex', height: '24px', borderRadius: '4px', overflow: 'hidden' }}>
                        {(() => {
                          const total = data.demand.adult_vs_child.adult + data.demand.adult_vs_child.child;
                          const adultPct = total > 0 ? (data.demand.adult_vs_child.adult / total) * 100 : 50;
                          return (
                            <>
                              <div style={{ width: `${adultPct}%`, backgroundColor: '#4f6fd9', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                                <span style={{ fontSize: '0.625rem', color: 'white', fontWeight: 600 }}>{data.demand.adult_vs_child.adult}</span>
                              </div>
                              <div style={{ width: `${100 - adultPct}%`, backgroundColor: '#c0842b', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                                <span style={{ fontSize: '0.625rem', color: 'white', fontWeight: 600 }}>{data.demand.adult_vs_child.child}</span>
                              </div>
                            </>
                          );
                        })()}
                      </div>
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '0.25rem', fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>
                        <span>Adult</span>
                        <span>Child</span>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* Time of Day - Histogram */}
              {Object.keys(data.demand.by_hour_of_day).length > 0 && (
                <div style={{ gridColumn: 'span 2' }}>
                  <h3 style={{ fontSize: '0.875rem', fontWeight: 600, marginBottom: '0.75rem' }}>Peak Hours</h3>
                  {(() => {
                    const hours = data.demand.by_hour_of_day;
                    const maxCount = Math.max(1, ...Object.values(hours));
                    const formatHourLabel = (h) => {
                      const hour = parseInt(h);
                      if (hour === 0) return '12a';
                      if (hour < 12) return `${hour}a`;
                      if (hour === 12) return '12p';
                      return `${hour - 12}p`;
                    };
                    return (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                        <div style={{ display: 'flex', alignItems: 'flex-end', gap: '2px', height: '100px' }}>
                          {Array.from({ length: 24 }, (_, hour) => {
                            const count = hours[hour] || hours[String(hour)] || 0;
                            const heightPct = (count / maxCount) * 100;
                            return (
                              <div
                                key={hour}
                                style={{
                                  flex: 1,
                                  height: `${Math.max(heightPct, count > 0 ? 4 : 0)}%`,
                                  backgroundColor: count > 0 ? 'var(--color-primary)' : 'var(--color-bg-light)',
                                  borderRadius: '2px 2px 0 0',
                                  minHeight: count > 0 ? '4px' : '0',
                                  cursor: 'pointer',
                                  transition: 'opacity 0.15s',
                                }}
                                title={`${formatHourLabel(hour)}: ${count} requests`}
                                onMouseEnter={(e) => (e.target.style.opacity = '0.8')}
                                onMouseLeave={(e) => (e.target.style.opacity = '1')}
                              />
                            );
                          })}
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.625rem', color: 'var(--color-text-muted)' }}>
                          <span>12a</span>
                          <span>6a</span>
                          <span>12p</span>
                          <span>6p</span>
                          <span>11p</span>
                        </div>
                      </div>
                    );
                  })()}
                </div>
              )}
            </div>
          </section>
        )}
      </div>
    </div>
  );
}
