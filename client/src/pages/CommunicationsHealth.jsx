import { useCallback, useEffect, useState } from 'react';
import { api } from '../api/client';
import { useAuth } from '../context/AuthContext';
import { LoadingState, EmptyState, ErrorState } from '../components/ui';
import MetricCard from '../components/MetricCard';
import AlertBanner from '../components/AlertBanner';
import TimeOfDayHeatmap from '../components/TimeOfDayHeatmap';
import YearlyActivityGraph from '../components/YearlyActivityGraph';
import SideDrawer from '../components/SideDrawer';
import './CommunicationsHealth.css';

const formatNumber = (n) => {
  if (n == null) return '--';
  return n.toLocaleString();
};

const formatMinutes = (m) => {
  if (!m) return '0';
  if (m < 60) return `${m.toFixed(1)}m`;
  return `${(m / 60).toFixed(1)}h`;
};

const formatSeconds = (s) => {
  if (!s) return '0s';
  if (s < 60) return `${Math.round(s)}s`;
  const min = Math.floor(s / 60);
  const sec = Math.round(s % 60);
  return sec > 0 ? `${min}m ${sec}s` : `${min}m`;
};

export default function CommunicationsHealth() {
  const { selectedTenantId } = useAuth();
  const [data, setData] = useState(null);
  const [heatmap, setHeatmap] = useState(null);
  const [yearly, setYearly] = useState(null);
  const [anomalies, setAnomalies] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [days, setDays] = useState(7);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drawerContent, setDrawerContent] = useState(null);

  const fetchData = useCallback(async () => {
    if (!selectedTenantId) return;
    setLoading(true);
    setError(null);
    try {
      const [health, heatmapRes, yearlyRes, anomalyRes] = await Promise.all([
        api.request(`/analytics/communications-health?days=${days}`),
        api.request(`/analytics/communications-health/heatmap?days=${days}`),
        api.request('/analytics/communications-health/yearly'),
        api.request('/analytics/anomalies?status=active'),
      ]);
      setData(health);
      setHeatmap(heatmapRes);
      setYearly(yearlyRes);
      setAnomalies(anomalyRes);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [selectedTenantId, days]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const openDrilldown = (title, content) => {
    setDrawerContent({ title, content });
    setDrawerOpen(true);
  };

  if (!selectedTenantId) {
    return <EmptyState message="Select a tenant to view communications health." />;
  }
  if (loading) return <LoadingState />;
  if (error) return <ErrorState message={error} onRetry={fetchData} />;
  if (!data) return <EmptyState message="No data available." />;

  const { calls, sms, email, total_interactions, channel_mix, trend, call_duration, bot_human, reliability } = data;
  const activeAlerts = anomalies?.alerts?.filter(a => a.status === 'active') || [];

  return (
    <div className="comms-health">
      <div className="comms-health-header">
        <h1>Communications Health</h1>
        <div className="comms-health-controls">
          <select value={days} onChange={e => setDays(Number(e.target.value))}>
            <option value={1}>Last 24 hours</option>
            <option value={7}>Last 7 days</option>
            <option value={30}>Last 30 days</option>
          </select>
        </div>
      </div>

      {activeAlerts.length > 0 && (
        <AlertBanner
          severity={activeAlerts.some(a => a.severity === 'critical') ? 'critical' : 'warning'}
          message={`${activeAlerts.length} active anomaly alert${activeAlerts.length > 1 ? 's' : ''} detected`}
        />
      )}

      {/* Summary cards */}
      <section className="comms-health-summary">
        <MetricCard
          label="Total Interactions"
          value={formatNumber(total_interactions)}
          trend={trend?.change_pct}
          tooltip="Sum of all calls, SMS messages, and emails in the selected period."
          onDrilldown={() => openDrilldown('Channel Breakdown', (
            <div className="drilldown-list">
              <div className="drilldown-row"><span>Calls</span><span>{formatNumber(calls?.total)} (In: {formatNumber(calls?.inbound)} / Out: {formatNumber(calls?.outbound)})</span></div>
              <div className="drilldown-row"><span>SMS</span><span>{formatNumber(sms?.total)} (In: {formatNumber(sms?.inbound)} / Out: {formatNumber(sms?.outbound)})</span></div>
              <div className="drilldown-row"><span>Email</span><span>{formatNumber(email?.total)} (In: {formatNumber(email?.inbound)} / Out: {formatNumber(email?.outbound)})</span></div>
            </div>
          ))}
        />
        <MetricCard
          label="Calls"
          value={formatNumber(calls?.total)}
          subValue={`${channel_mix?.calls || 0}%`}
          tooltip="Total voice calls. Percentage shows share of all interactions."
        />
        <MetricCard
          label="SMS"
          value={formatNumber(sms?.total)}
          subValue={`${channel_mix?.sms || 0}%`}
          tooltip="Total SMS messages (inbound user + outbound assistant)."
        />
        <MetricCard
          label="Email"
          value={formatNumber(email?.total)}
          subValue={`${channel_mix?.email || 0}%`}
          tooltip="Total email interactions."
        />
      </section>

      {/* Call Duration */}
      <section className="comms-health-card">
        <h2>Call Duration</h2>
        <div className="comms-health-metrics-grid">
          <MetricCard label="Total Minutes" value={formatMinutes(call_duration?.total_minutes)} tooltip="Sum of all call durations." />
          <MetricCard label="Avg Duration" value={formatSeconds(call_duration?.avg_seconds)} tooltip="Mean call duration in seconds." />
          <MetricCard label="Median Duration" value={formatSeconds(call_duration?.median_seconds)} tooltip="Median call duration." />
          <MetricCard
            label="Short Calls"
            value={`${call_duration?.short_call_pct || 0}%`}
            tooltip="Percentage of calls shorter than 30 seconds."
            severity={call_duration?.short_call_pct > 40 ? 'warning' : undefined}
          />
          <MetricCard
            label="Long Calls"
            value={`${call_duration?.long_call_pct || 0}%`}
            tooltip="Percentage of calls longer than 10 minutes."
          />
        </div>
      </section>

      {/* Bot vs Human */}
      <section className="comms-health-card">
        <h2>Bot vs Human Workload</h2>
        <div className="comms-health-metrics-grid">
          <MetricCard label="Bot Handled" value={`${bot_human?.bot_handled_pct || 0}%`} tooltip="Conversations fully handled by AI without escalation." />
          <MetricCard label="Escalated" value={`${bot_human?.escalated_pct || 0}%`} tooltip="Conversations escalated to human agents." severity={bot_human?.escalated_pct > 30 ? 'warning' : undefined} />
          <MetricCard label="Bot Resolution Rate" value={`${bot_human?.bot_resolution_rate || 0}%`} tooltip="Conversations resolved by bot without human intervention." />
          <MetricCard label="Escalation Rate" value={`${bot_human?.escalation_rate || 0}%`} tooltip="Rate of conversations requiring human escalation." />
        </div>
      </section>

      {/* Reliability */}
      <section className="comms-health-card">
        <h2>Reliability</h2>
        <div className="comms-health-metrics-grid">
          <MetricCard label="Dropped Calls" value={formatNumber(reliability?.dropped_calls)} tooltip="Calls that ended before connecting (no-answer, busy, canceled)." severity={reliability?.dropped_calls > 10 ? 'warning' : undefined} />
          <MetricCard label="Failed Calls" value={formatNumber(reliability?.failed_calls)} tooltip="Calls that failed to connect." severity={reliability?.failed_calls > 0 ? 'critical' : undefined} />
          <MetricCard label="Failed SMS" value={formatNumber(reliability?.failed_sms)} tooltip="SMS messages that failed to deliver." severity={reliability?.failed_sms > 5 ? 'warning' : undefined} />
          <MetricCard label="Bounced Emails" value={formatNumber(reliability?.bounced_emails)} tooltip="Emails that bounced back." />
        </div>
      </section>

      {/* Heatmap */}
      <section className="comms-health-card">
        <h2>Volume by Time of Day</h2>
        <TimeOfDayHeatmap cells={heatmap?.cells || []} metric="calls" />
      </section>

      {/* Yearly Activity */}
      <section className="comms-health-card">
        <h2>Activity Over the Past Year</h2>
        <YearlyActivityGraph data={yearly?.cells || []} metric="total" />
      </section>

      {/* Anomaly alerts */}
      {anomalies?.alerts?.length > 0 && (
        <section className="comms-health-card">
          <h2>Recent Anomaly Alerts</h2>
          <div className="anomaly-list">
            {anomalies.alerts.map(alert => (
              <div key={alert.id} className={`anomaly-item anomaly-${alert.severity}`}>
                <div className="anomaly-badge">{alert.severity}</div>
                <div className="anomaly-info">
                  <span className="anomaly-type">{alert.alert_type.replace(/_/g, ' ')}</span>
                  <span className="anomaly-detail">
                    {alert.metric_name}: {alert.current_value.toFixed(1)} (baseline: {alert.baseline_value.toFixed(1)})
                  </span>
                </div>
                <span className="anomaly-time">{new Date(alert.detected_at).toLocaleString()}</span>
              </div>
            ))}
          </div>
        </section>
      )}

      <SideDrawer
        title={drawerContent?.title || ''}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
      >
        {drawerContent?.content}
      </SideDrawer>
    </div>
  );
}
