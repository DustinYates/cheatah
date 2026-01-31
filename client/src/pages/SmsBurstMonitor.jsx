import { useCallback, useEffect, useState } from 'react';
import { Settings, Eye, CheckCircle, AlertTriangle } from 'lucide-react';
import { api } from '../api/client';
import { useAuth } from '../context/AuthContext';
import { LoadingState, EmptyState, ErrorState } from '../components/ui';
import MetricCard from '../components/MetricCard';
import AlertBanner from '../components/AlertBanner';
import SideDrawer, { ConfigDiffView } from '../components/SideDrawer';
import './SmsBurstMonitor.css';

const BURST_CONFIG_DEFAULTS = {
  enabled: true,
  time_window_seconds: 180,
  message_threshold: 3,
  high_severity_threshold: 5,
  rapid_gap_min_seconds: 5,
  rapid_gap_max_seconds: 29,
  identical_content_threshold: 2,
  similarity_threshold: 0.9,
  auto_block_enabled: false,
  auto_block_threshold: 10,
  excluded_flows: [],
};

const CAUSE_LABELS = {
  duplicate_webhook: 'Duplicate Webhook',
  task_retry: 'Task Retry Loop',
  tool_loop: 'AI Tool Loop',
  callback_confusion: 'Callback Confusion',
  unknown: 'Unknown',
};

const formatTimeAgo = (dateStr) => {
  const diff = (Date.now() - new Date(dateStr).getTime()) / 1000;
  if (diff < 60) return `${Math.round(diff)}s ago`;
  if (diff < 3600) return `${Math.round(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.round(diff / 3600)}h ago`;
  return `${Math.round(diff / 86400)}d ago`;
};

export default function SmsBurstMonitor() {
  const { selectedTenantId } = useAuth();
  const [data, setData] = useState(null);
  const [config, setConfig] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [expandedId, setExpandedId] = useState(null);
  const [configEdits, setConfigEdits] = useState({});

  const fetchData = useCallback(async () => {
    if (!selectedTenantId) return;
    setLoading(true);
    setError(null);
    try {
      const [burstData, burstConfig] = await Promise.all([
        api.request('/analytics/sms-bursts?hours=24'),
        api.request('/analytics/sms-burst-config'),
      ]);
      setData(burstData);
      setConfig(burstConfig);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [selectedTenantId]);

  useEffect(() => { fetchData(); }, [fetchData]);

  // Auto-refresh every 30 seconds
  useEffect(() => {
    if (!selectedTenantId) return;
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, [selectedTenantId, fetchData]);

  const handleAction = async (incidentId, newStatus, notes) => {
    try {
      const params = new URLSearchParams({ status: newStatus });
      if (notes) params.set('notes', notes);
      await api.request(`/analytics/sms-bursts/${incidentId}?${params}`, { method: 'PATCH' });
      fetchData();
    } catch (err) {
      alert(`Failed to update: ${err.message}`);
    }
  };

  const handleSaveConfig = async () => {
    try {
      await api.request('/analytics/sms-burst-config', {
        method: 'PUT',
        body: JSON.stringify(configEdits),
      });
      setSettingsOpen(false);
      fetchData();
    } catch (err) {
      alert(`Failed to save: ${err.message}`);
    }
  };

  if (!selectedTenantId) {
    return <EmptyState message="Select a tenant to view SMS burst monitoring." />;
  }
  if (loading) return <LoadingState />;
  if (error) return <ErrorState message={error} onRetry={fetchData} />;
  if (!data) return <EmptyState message="No data available." />;

  const { summary, incidents } = data;
  const hasCritical = summary.active_critical_count > 0;

  return (
    <div className="burst-monitor">
      {hasCritical && (
        <AlertBanner
          severity="critical"
          message={`${summary.active_critical_count} critical SMS burst incident${summary.active_critical_count > 1 ? 's' : ''} — immediate attention required`}
        />
      )}

      <div className="burst-header">
        <h1>SMS Burst Detection</h1>
        <button className="burst-settings-btn" onClick={() => {
          setConfigEdits(config || BURST_CONFIG_DEFAULTS);
          setSettingsOpen(true);
        }}>
          <Settings size={16} /> Settings
        </button>
      </div>

      {/* Summary cards */}
      <section className="burst-summary">
        <MetricCard
          label="Incidents (24h)"
          value={summary.total_incidents_24h}
          tooltip="Total burst patterns detected in the last 24 hours."
          severity={summary.total_incidents_24h > 5 ? 'warning' : undefined}
        />
        <MetricCard
          label="Numbers Impacted"
          value={summary.numbers_impacted}
          tooltip="Unique phone numbers involved in burst incidents."
        />
        <MetricCard
          label="Messages in Bursts"
          value={summary.total_messages_in_bursts}
          tooltip="Total SMS messages that were part of burst patterns."
        />
        <MetricCard
          label="Worst Offender"
          value={summary.worst_offender_number || '--'}
          subValue={summary.worst_offender_count ? `${summary.worst_offender_count} msgs` : undefined}
          tooltip="Phone number with the highest burst message count."
          severity={summary.worst_offender_count > 10 ? 'critical' : undefined}
        />
      </section>

      {/* Incident table */}
      <section className="burst-card">
        <h2>Incident Feed <span className="burst-refresh-note">Auto-refreshes every 30s</span></h2>
        {incidents.length === 0 ? (
          <p className="burst-empty">No burst incidents detected. All clear.</p>
        ) : (
          <div className="burst-table">
            <div className="burst-table-header">
              <span>Severity</span>
              <span>Number</span>
              <span>Time</span>
              <span>Count</span>
              <span>Avg Gap</span>
              <span>Content</span>
              <span>Cause</span>
              <span>Status</span>
              <span>Actions</span>
            </div>
            {incidents.map(incident => (
              <div key={incident.id}>
                <div
                  className={`burst-table-row burst-row-${incident.severity}`}
                  onClick={() => setExpandedId(expandedId === incident.id ? null : incident.id)}
                >
                  <span className={`burst-severity-badge severity-${incident.severity}`}>
                    {incident.severity}
                  </span>
                  <span className="burst-number">{incident.to_number_masked}</span>
                  <span className="burst-time">{formatTimeAgo(incident.detected_at)}</span>
                  <span className="burst-count">{incident.message_count}</span>
                  <span className="burst-gap">{incident.avg_gap_seconds.toFixed(1)}s</span>
                  <span className="burst-content">
                    {incident.has_identical_content ? (
                      <span className="burst-identical">Identical</span>
                    ) : (
                      <span className="burst-varied">Varied</span>
                    )}
                  </span>
                  <span className="burst-cause">{CAUSE_LABELS[incident.likely_cause] || incident.likely_cause}</span>
                  <span className={`burst-status status-${incident.status}`}>{incident.status}</span>
                  <span className="burst-actions" onClick={e => e.stopPropagation()}>
                    {incident.status === 'active' && (
                      <>
                        <button
                          className="burst-action-btn"
                          title="Acknowledge"
                          onClick={() => handleAction(incident.id, 'acknowledged')}
                        >
                          <Eye size={14} />
                        </button>
                        <button
                          className="burst-action-btn resolve"
                          title="Resolve"
                          onClick={() => handleAction(incident.id, 'resolved')}
                        >
                          <CheckCircle size={14} />
                        </button>
                      </>
                    )}
                    {incident.status === 'acknowledged' && (
                      <button
                        className="burst-action-btn resolve"
                        title="Resolve"
                        onClick={() => handleAction(incident.id, 'resolved')}
                      >
                        <CheckCircle size={14} />
                      </button>
                    )}
                  </span>
                </div>

                {expandedId === incident.id && (
                  <div className="burst-expanded">
                    <div className="burst-detail-grid">
                      <div className="burst-detail-item">
                        <span className="burst-detail-label">Window</span>
                        <span>{incident.time_window_seconds}s ({incident.message_count} messages)</span>
                      </div>
                      <div className="burst-detail-item">
                        <span className="burst-detail-label">First Message</span>
                        <span>{new Date(incident.first_message_at).toLocaleString()}</span>
                      </div>
                      <div className="burst-detail-item">
                        <span className="burst-detail-label">Last Message</span>
                        <span>{new Date(incident.last_message_at).toLocaleString()}</span>
                      </div>
                      <div className="burst-detail-item">
                        <span className="burst-detail-label">Auto-Blocked</span>
                        <span>{incident.auto_blocked ? 'Yes' : 'No'}</span>
                      </div>
                      <div className="burst-detail-item">
                        <span className="burst-detail-label">Root Cause Hint</span>
                        <span>{CAUSE_LABELS[incident.likely_cause] || 'Unknown'}</span>
                      </div>
                      {incident.content_similarity_score && (
                        <div className="burst-detail-item">
                          <span className="burst-detail-label">Content Similarity</span>
                          <span>{(incident.content_similarity_score * 100).toFixed(0)}%</span>
                        </div>
                      )}
                    </div>
                    {incident.notes && (
                      <div className="burst-notes">
                        <strong>Notes:</strong> {incident.notes}
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Settings drawer */}
      <SideDrawer
        title="Burst Detection Settings"
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
      >
        <div className="burst-settings-form">
          <div className="burst-setting-group">
            <label>
              <input
                type="checkbox"
                checked={configEdits.enabled ?? true}
                onChange={e => setConfigEdits(prev => ({ ...prev, enabled: e.target.checked }))}
              />
              Detection Enabled
            </label>
          </div>

          <div className="burst-setting-group">
            <label>Time Window (seconds)</label>
            <input
              type="number"
              value={configEdits.time_window_seconds ?? 180}
              onChange={e => setConfigEdits(prev => ({ ...prev, time_window_seconds: Number(e.target.value) }))}
            />
          </div>

          <div className="burst-setting-group">
            <label>Message Threshold (flag at &ge;)</label>
            <input
              type="number"
              value={configEdits.message_threshold ?? 3}
              onChange={e => setConfigEdits(prev => ({ ...prev, message_threshold: Number(e.target.value) }))}
            />
          </div>

          <div className="burst-setting-group">
            <label>High Severity Threshold</label>
            <input
              type="number"
              value={configEdits.high_severity_threshold ?? 5}
              onChange={e => setConfigEdits(prev => ({ ...prev, high_severity_threshold: Number(e.target.value) }))}
            />
          </div>

          <div className="burst-setting-group">
            <label>Rapid Gap Range (seconds)</label>
            <div className="burst-range-inputs">
              <input
                type="number"
                value={configEdits.rapid_gap_min_seconds ?? 5}
                onChange={e => setConfigEdits(prev => ({ ...prev, rapid_gap_min_seconds: Number(e.target.value) }))}
              />
              <span>to</span>
              <input
                type="number"
                value={configEdits.rapid_gap_max_seconds ?? 29}
                onChange={e => setConfigEdits(prev => ({ ...prev, rapid_gap_max_seconds: Number(e.target.value) }))}
              />
            </div>
          </div>

          <div className="burst-setting-group">
            <label>
              <input
                type="checkbox"
                checked={configEdits.auto_block_enabled ?? false}
                onChange={e => setConfigEdits(prev => ({ ...prev, auto_block_enabled: e.target.checked }))}
              />
              Auto-Block Enabled
            </label>
            {configEdits.auto_block_enabled && (
              <div>
                <label>Block after N messages</label>
                <input
                  type="number"
                  value={configEdits.auto_block_threshold ?? 10}
                  onChange={e => setConfigEdits(prev => ({ ...prev, auto_block_threshold: Number(e.target.value) }))}
                />
              </div>
            )}
          </div>

          <ConfigDiffView
            currentConfig={configEdits}
            defaultConfig={BURST_CONFIG_DEFAULTS}
          />

          <button className="burst-save-btn" onClick={handleSaveConfig}>
            Save Settings
          </button>
        </div>
      </SideDrawer>
    </div>
  );
}
