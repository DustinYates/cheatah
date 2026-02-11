import { useState, useEffect, useCallback } from 'react';
import { api } from '../api/client';
import { useAuth } from '../context/AuthContext';
import { LoadingState, EmptyState, ErrorState } from '../components/ui';
import './UsageBilling.css';

const MONTH_NAMES = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
];

function formatMinutes(value) {
  const m = Number(value) || 0;
  if (m === 0) return '0';
  if (m >= 100) return Math.round(m).toLocaleString();
  if (Number.isInteger(m)) return m.toString();
  return m.toFixed(1);
}

function UsageProgressBar({ used, limit, label, unit, subtext }) {
  const isUnlimited = limit === null || limit === undefined;
  const percentage = isUnlimited ? 0 : limit > 0 ? Math.min((used / limit) * 100, 100) : 0;
  const remaining = isUnlimited ? null : Math.max(limit - used, 0);

  let barColor = 'var(--billing-green)';
  if (!isUnlimited) {
    if (percentage > 90) barColor = 'var(--billing-red)';
    else if (percentage > 75) barColor = 'var(--billing-yellow)';
  }

  return (
    <div className="billing-usage-card">
      <div className="billing-usage-card-header">
        <h3>{label}</h3>
        {!isUnlimited && (
          <span className="billing-usage-percentage">{Math.round(percentage)}%</span>
        )}
      </div>
      <div className="billing-usage-values">
        <span className="billing-usage-used">
          {typeof used === 'number' && used % 1 !== 0 ? formatMinutes(used) : used.toLocaleString()}
        </span>
        <span className="billing-usage-separator">
          {isUnlimited ? unit : `/ ${limit.toLocaleString()} ${unit}`}
        </span>
      </div>
      {!isUnlimited ? (
        <>
          <div className="billing-progress-track">
            <div
              className="billing-progress-fill"
              style={{ width: `${percentage}%`, backgroundColor: barColor }}
            />
          </div>
          <div className="billing-usage-footer">
            <span>{remaining.toLocaleString()} {unit} remaining</span>
          </div>
        </>
      ) : (
        <div className="billing-usage-footer">
          <span className="billing-unlimited-badge">Unlimited</span>
        </div>
      )}
      {subtext && <p className="billing-usage-subtext">{subtext}</p>}
    </div>
  );
}

function DailyChart({ data, dataKey, label, color, formatValue }) {
  if (!data || data.length === 0) return null;

  const values = data.map(d => d[dataKey] || 0);
  const maxVal = Math.max(...values, 1);
  const labelInterval = data.length <= 10 ? 1 : data.length <= 20 ? 2 : Math.ceil(data.length / 10);

  return (
    <div className="billing-chart-section">
      <h3>{label}</h3>
      <div className="billing-chart">
        <div className="billing-y-axis">
          <span>{formatValue ? formatValue(maxVal) : maxVal}</span>
          <span>0</span>
        </div>
        <div className="billing-bars">
          {data.map((day, i) => {
            const val = day[dataKey] || 0;
            const height = (val / maxVal) * 100;
            const dayNum = new Date(day.date + 'T12:00:00').getDate();
            const showLabel = i % labelInterval === 0 || i === data.length - 1;
            return (
              <div className="billing-bar-column" key={day.date}>
                <div
                  className="billing-bar-track"
                  title={`${day.date}: ${formatValue ? formatValue(val) : val}`}
                >
                  {val > 0 && (
                    <div
                      className="billing-bar"
                      style={{ height: `${height}%`, backgroundColor: color }}
                    />
                  )}
                </div>
                {showLabel && <span className="billing-x-label">{dayNum}</span>}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

export default function UsageBilling() {
  const { user, effectiveTenantId } = useAuth();
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const needsTenant = user?.is_global_admin && !effectiveTenantId;

  const fetchData = useCallback(async () => {
    if (needsTenant) return;
    setLoading(true);
    setError(null);
    try {
      const result = await api.getBillingUsage({ year, month });
      setData(result);
    } catch (err) {
      setError(err.message || 'Failed to load billing data');
    } finally {
      setLoading(false);
    }
  }, [year, month, needsTenant, effectiveTenantId]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const goToPrevMonth = () => {
    if (month === 1) {
      setYear(y => y - 1);
      setMonth(12);
    } else {
      setMonth(m => m - 1);
    }
  };

  const goToNextMonth = () => {
    const isCurrentMonth = year === now.getFullYear() && month === now.getMonth() + 1;
    if (isCurrentMonth) return;
    if (month === 12) {
      setYear(y => y + 1);
      setMonth(1);
    } else {
      setMonth(m => m + 1);
    }
  };

  const isCurrentMonth = year === now.getFullYear() && month === now.getMonth() + 1;

  if (needsTenant) {
    return (
      <div className="billing-page">
        <EmptyState
          icon="DATA"
          title="Select a tenant to view billing"
          description="Choose a tenant from the dropdown above."
        />
      </div>
    );
  }

  if (loading) {
    return (
      <div className="billing-page">
        <LoadingState message="Loading billing data..." />
      </div>
    );
  }

  if (error) {
    return (
      <div className="billing-page">
        <ErrorState message={error} onRetry={fetchData} />
      </div>
    );
  }

  if (!data) {
    return (
      <div className="billing-page">
        <EmptyState icon="DATA" title="No billing data available" />
      </div>
    );
  }

  return (
    <div className="billing-page">
      <div className="billing-header">
        <div className="billing-title">
          <h1>Billing</h1>
          <p className="billing-subtitle">Monthly usage summary</p>
        </div>
        <div className="billing-month-nav">
          <button className="billing-nav-btn" onClick={goToPrevMonth} title="Previous month">
            &lsaquo;
          </button>
          <span className="billing-month-label">
            {MONTH_NAMES[month - 1]} {year}
          </span>
          <button
            className="billing-nav-btn"
            onClick={goToNextMonth}
            disabled={isCurrentMonth}
            title={isCurrentMonth ? 'Current month' : 'Next month'}
          >
            &rsaquo;
          </button>
        </div>
      </div>

      <div className="billing-cards">
        <UsageProgressBar
          used={data.call_minutes_used}
          limit={data.call_minutes_limit}
          label="Call Minutes"
          unit="minutes"
          subtext={`${data.call_count} total call${data.call_count !== 1 ? 's' : ''}`}
        />
        <UsageProgressBar
          used={data.sms_sent}
          limit={data.sms_limit}
          label="Text Messages Sent"
          unit="messages"
          subtext={`${data.sms_received} received`}
        />
      </div>

      {data.daily_breakdown && data.daily_breakdown.length > 0 && (
        <div className="billing-charts">
          <DailyChart
            data={data.daily_breakdown}
            dataKey="call_minutes"
            label="Daily Call Minutes"
            color="var(--billing-chart-calls)"
            formatValue={formatMinutes}
          />
          <DailyChart
            data={data.daily_breakdown}
            dataKey="sms_sent"
            label="Daily Texts Sent"
            color="var(--billing-chart-sms)"
            formatValue={v => Math.round(v).toString()}
          />
        </div>
      )}
    </div>
  );
}
