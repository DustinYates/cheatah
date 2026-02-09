import { useCallback, useEffect, useState } from 'react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts';
import { api } from '../api/client';
import { useAuth } from '../context/AuthContext';
import { LoadingState, EmptyState, ErrorState } from '../components/ui';
import MetricCard from '../components/MetricCard';
import CHIGauge from '../components/CHIGauge';
import './CustomerHappiness.css';

const BUCKET_COLORS = {
  '0-20': '#dc2626',
  '20-40': '#f97316',
  '40-60': '#eab308',
  '60-80': '#84cc16',
  '80-100': '#16a34a',
};

export default function CustomerHappiness() {
  const { selectedTenantId } = useAuth();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [days, setDays] = useState(7);

  const fetchData = useCallback(async () => {
    if (!selectedTenantId) return;
    setLoading(true);
    setError(null);
    try {
      const result = await api.request(`/analytics/chi?days=${days}`);
      setData(result);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [selectedTenantId, days]);

  useEffect(() => { fetchData(); }, [fetchData]);

  if (!selectedTenantId) {
    return <EmptyState message="Select a tenant to view happiness metrics." />;
  }
  if (loading) return <LoadingState />;
  if (error) return <ErrorState message={error} onRetry={fetchData} />;
  if (!data) return <EmptyState message="No data available." />;

  const { summary, distribution, top_frustration_drivers, repeat_contact_rate_48h, improvement_opportunities } = data;

  const belowThreshold = distribution
    .filter(d => d.bucket === '0-20' || d.bucket === '20-40')
    .reduce((sum, d) => sum + d.pct, 0);
  const aboveThreshold = distribution
    .filter(d => d.bucket === '80-100')
    .reduce((sum, d) => sum + d.pct, 0);

  return (
    <div className="chi-page">
      <div className="chi-page-header">
        <h1>Customer Happiness Index</h1>
        <div className="chi-page-controls">
          <select value={days} onChange={e => setDays(Number(e.target.value))}>
            <option value={1}>Today</option>
            <option value={7}>Last 7 days</option>
            <option value={30}>Last 30 days</option>
          </select>
        </div>
      </div>

      {/* Summary row */}
      <section className="chi-summary-row">
        <div className="chi-summary-gauge">
          <CHIGauge score={summary?.avg_chi_today} size={80} label="Today" noDataMessage="No data today" />
        </div>
        <div className="chi-summary-gauge">
          <CHIGauge score={summary?.avg_chi_7d} size={80} label={`${days}d Avg`} />
        </div>
        <MetricCard
          label="Trend"
          value={summary?.trend_pct != null ? `${summary.trend_pct > 0 ? '+' : ''}${summary.trend_pct}%` : '--'}
          tooltip="Change in average CHI compared to the previous period."
          trend={summary?.trend_pct}
        />
        <MetricCard
          label="Conversations Scored"
          value={summary?.conversations_scored?.toLocaleString() || '0'}
          tooltip="Number of conversations with CHI scores in this period."
        />
      </section>

      {/* Distribution */}
      <section className="chi-card">
        <h2>CHI Distribution</h2>
        <div className="chi-distribution-summary">
          <span className="chi-dist-bad">{belowThreshold.toFixed(1)}% below 40</span>
          <span className="chi-dist-good">{aboveThreshold.toFixed(1)}% above 80</span>
        </div>
        <div className="chi-chart-container">
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={distribution} margin={{ top: 10, right: 10, bottom: 0, left: 0 }}>
              <XAxis dataKey="bucket" tick={{ fontSize: 12 }} />
              <YAxis tick={{ fontSize: 12 }} />
              <Tooltip formatter={(val) => [`${val}`, 'Count']} />
              <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                {distribution.map((entry, idx) => (
                  <Cell key={idx} fill={BUCKET_COLORS[entry.bucket] || '#94a3b8'} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </section>

      {/* Top frustration drivers */}
      <section className="chi-card">
        <h2>Top Frustration Drivers</h2>
        {top_frustration_drivers.length === 0 ? (
          <p className="chi-empty">No frustration signals detected.</p>
        ) : (
          <div className="chi-drivers">
            {top_frustration_drivers.map((driver, i) => (
              <div key={i} className="chi-driver-row">
                <span className="chi-driver-name">{driver.signal.replace(/_/g, ' ')}</span>
                <div className="chi-driver-bar-container">
                  <div
                    className="chi-driver-bar"
                    style={{
                      width: `${Math.min(100, (driver.count / Math.max(1, top_frustration_drivers[0]?.count)) * 100)}%`,
                    }}
                  />
                </div>
                <span className="chi-driver-count">{driver.count}</span>
                <span className="chi-driver-impact">{driver.avg_impact.toFixed(1)} avg</span>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Repeat contact rate + improvements */}
      <div className="chi-bottom-row">
        <section className="chi-card">
          <h2>Repeat Contact Rate (48h)</h2>
          <div className="chi-repeat-rate">
            <span className="chi-repeat-value">{repeat_contact_rate_48h?.toFixed(1) || 0}%</span>
            <span className="chi-repeat-label">of contacts returned within 48 hours</span>
          </div>
        </section>

        <section className="chi-card">
          <h2>What to Improve</h2>
          {improvement_opportunities.length === 0 ? (
            <p className="chi-empty">No improvement recommendations yet.</p>
          ) : (
            <div className="chi-improvements">
              {improvement_opportunities.map((opp, i) => (
                <div key={i} className="chi-improvement-item">
                  <span className="chi-improvement-rank">#{i + 1}</span>
                  <div className="chi-improvement-detail">
                    <span className="chi-improvement-text">{opp.recommendation}</span>
                    <span className="chi-improvement-impact">CHI impact: {opp.estimated_chi_impact.toFixed(1)}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
