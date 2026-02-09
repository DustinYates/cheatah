import { useCallback, useEffect, useMemo, useState } from 'react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts';
import { api } from '../api/client';
import { useAuth } from '../context/AuthContext';
import { LoadingState, EmptyState, ErrorState } from '../components/ui';
import MetricCard from '../components/MetricCard';
import './TopicAnalytics.css';

const TOPIC_LABELS = {
  pricing: 'Pricing & Costs',
  scheduling: 'Scheduling & Booking',
  hours_location: 'Hours & Location',
  class_info: 'Class Information',
  registration: 'Registration & Enrollment',
  support_request: 'Support / Human',
  wrong_number: 'Wrong Number',
  general_inquiry: 'General Questions',
};

const TOPIC_COLORS = {
  pricing: '#3b82f6',
  scheduling: '#8b5cf6',
  hours_location: '#f59e0b',
  class_info: '#10b981',
  registration: '#06b6d4',
  support_request: '#ef4444',
  wrong_number: '#6b7280',
  general_inquiry: '#a3a3a3',
};

const CHANNEL_LABELS = {
  sms: 'SMS',
  voice: 'Voice',
  web: 'Web Chat',
  email: 'Email',
};

const CHANNEL_COLORS = {
  sms: '#c0842b',
  voice: '#4f6fd9',
  web: '#3f8f66',
  email: '#9333ea',
};

function formatTopicLabel(topic) {
  return TOPIC_LABELS[topic] || topic.split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
}

export default function TopicAnalytics() {
  const { selectedTenantId } = useAuth();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [days, setDays] = useState(30);
  const [channelFilter, setChannelFilter] = useState('');

  const fetchData = useCallback(async () => {
    if (!selectedTenantId) return;
    setLoading(true);
    setError(null);
    try {
      const now = new Date();
      const start = new Date(now);
      start.setDate(start.getDate() - days);
      const params = {
        start_date: start.toISOString().split('T')[0],
        end_date: now.toISOString().split('T')[0],
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
      };
      if (channelFilter) {
        params.channel = channelFilter;
      }
      const result = await api.getTopicAnalytics(params);
      setData(result);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [selectedTenantId, days, channelFilter]);

  useEffect(() => { fetchData(); }, [fetchData]);

  // Prepare chart data
  const chartData = useMemo(() => {
    if (!data?.topics) return [];
    return data.topics.map(t => ({
      name: formatTopicLabel(t.topic),
      topic: t.topic,
      count: t.count,
      percentage: t.percentage,
    }));
  }, [data]);

  const topTopic = chartData.length > 0 ? chartData[0].name : '--';
  const coverage = data
    ? data.total_classified + data.total_unclassified > 0
      ? ((data.total_classified / (data.total_classified + data.total_unclassified)) * 100).toFixed(1)
      : '0'
    : '--';

  if (!selectedTenantId) {
    return <EmptyState message="Select a tenant to view topic analytics." />;
  }
  if (loading) return <LoadingState />;
  if (error) return <ErrorState message={error} onRetry={fetchData} />;
  if (!data) return <EmptyState message="No data available." />;

  const byChannel = data.by_channel || {};
  const channels = Object.keys(byChannel);

  return (
    <div className="topics-page">
      <div className="topics-page-header">
        <h1>Conversation Topics</h1>
        <div className="topics-page-controls">
          <select value={channelFilter} onChange={e => setChannelFilter(e.target.value)}>
            <option value="">All Channels</option>
            <option value="sms">SMS</option>
            <option value="voice">Voice</option>
            <option value="web">Web Chat</option>
            <option value="email">Email</option>
          </select>
          <select value={days} onChange={e => setDays(Number(e.target.value))}>
            <option value={7}>Last 7 days</option>
            <option value={30}>Last 30 days</option>
            <option value={90}>Last 90 days</option>
          </select>
        </div>
      </div>

      {/* Summary row */}
      <section className="topics-summary-row">
        <MetricCard
          label="Classified"
          value={data.total_classified?.toLocaleString() || '0'}
          tooltip="Conversations with a detected topic in this period."
        />
        <MetricCard
          label="Top Topic"
          value={topTopic}
          tooltip="The most common conversation topic."
        />
        <MetricCard
          label="Coverage"
          value={`${coverage}%`}
          tooltip="Percentage of conversations that have been classified."
        />
      </section>

      {/* Main histogram */}
      <section className="topics-card">
        <h2>Topic Distribution</h2>
        <p>What customers ask about most across {channelFilter ? CHANNEL_LABELS[channelFilter] || channelFilter : 'all channels'}.</p>
        {chartData.length === 0 ? (
          <div className="topics-empty-state">
            <p className="topics-empty-title">No topics classified yet</p>
            <p className="topics-empty-desc">
              Topics are automatically classified by a background worker.
              If conversations exist but aren't classified, the worker may not have run yet for this period.
            </p>
            <button className="topics-refresh-btn" onClick={fetchData}>Refresh</button>
          </div>
        ) : (
          <div className="topics-chart-container">
            <ResponsiveContainer width="100%" height={Math.max(200, chartData.length * 45)}>
              <BarChart data={chartData} layout="vertical" margin={{ top: 5, right: 30, bottom: 5, left: 140 }}>
                <XAxis type="number" />
                <YAxis type="category" dataKey="name" width={130} tick={{ fontSize: 13 }} />
                <Tooltip
                  formatter={(value, name, props) => [`${value} (${props.payload.percentage}%)`, 'Conversations']}
                />
                <Bar dataKey="count" radius={[0, 4, 4, 0]} barSize={24}>
                  {chartData.map((entry) => (
                    <Cell key={entry.topic} fill={TOPIC_COLORS[entry.topic] || '#8884d8'} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </section>

      {/* Channel breakdown */}
      {channels.length > 0 && !channelFilter && (
        <section className="topics-card">
          <h2>By Channel</h2>
          <p>Topic breakdown per communication channel.</p>
          <div className="topics-channel-grid">
            {channels.map(ch => {
              const chTopics = byChannel[ch] || [];
              const maxCount = Math.max(1, ...chTopics.map(t => t.count));
              return (
                <div key={ch} className="topics-channel-card">
                  <h3>{CHANNEL_LABELS[ch] || ch}</h3>
                  {chTopics.length === 0 ? (
                    <p className="topics-empty">No data</p>
                  ) : (
                    chTopics.map(t => (
                      <div key={t.topic} className="topics-bar-row">
                        <span className="topics-bar-label">{formatTopicLabel(t.topic)}</span>
                        <div className="topics-bar-container">
                          <div
                            className="topics-bar"
                            style={{
                              width: `${(t.count / maxCount) * 100}%`,
                              background: CHANNEL_COLORS[ch] || '#8884d8',
                            }}
                          />
                        </div>
                        <span className="topics-bar-value">{t.count} ({t.percentage}%)</span>
                      </div>
                    ))
                  )}
                </div>
              );
            })}
          </div>
        </section>
      )}
    </div>
  );
}
