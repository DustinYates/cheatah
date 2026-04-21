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

function formatCurrency(cents) {
  if (cents == null) return '—';
  return `$${(cents / 100).toFixed(0)}`;
}

function formatDate(iso) {
  if (!iso) return null;
  try {
    return new Date(iso).toLocaleDateString(undefined, { year: 'numeric', month: 'long', day: 'numeric' });
  } catch {
    return iso;
  }
}

function statusLabel(status) {
  if (!status) return 'No active plan';
  const map = {
    active: 'Active',
    trialing: 'Trial',
    past_due: 'Past due',
    canceled: 'Canceled',
    disabled: 'Disabled',
    incomplete: 'Incomplete',
    incomplete_expired: 'Expired',
    unpaid: 'Unpaid',
  };
  return map[status] || status;
}

export default function UsageBilling() {
  const { user, effectiveTenantId } = useAuth();
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const [subscription, setSubscription] = useState(null);
  const [plans, setPlans] = useState([]);
  const [subLoading, setSubLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(null);
  const [actionError, setActionError] = useState(null);
  const [returnNotice, setReturnNotice] = useState(null);

  const needsTenant = user?.is_global_admin && !effectiveTenantId;
  const isTenantAdmin = user?.role === 'admin' || user?.role === 'tenant_admin' || user?.is_global_admin;

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

  const fetchSubscription = useCallback(async () => {
    if (needsTenant) return;
    setSubLoading(true);
    try {
      const [sub, planList] = await Promise.all([
        api.getBillingSubscription(),
        api.getBillingPlans(),
      ]);
      setSubscription(sub);
      setPlans(planList || []);
    } catch (err) {
      console.error('Failed to load billing subscription/plans', err);
    } finally {
      setSubLoading(false);
    }
  }, [needsTenant, effectiveTenantId]);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const session = params.get('session');
    if (session === 'success') {
      setReturnNotice({ type: 'success', text: 'Subscription updated. Changes may take a moment to appear.' });
      window.history.replaceState({}, '', window.location.pathname);
    } else if (session === 'cancel') {
      window.history.replaceState({}, '', window.location.pathname);
    }
  }, []);

  useEffect(() => {
    fetchSubscription();
  }, [fetchSubscription]);

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

  const handleSelectPlan = async (priceId) => {
    if (!isTenantAdmin) return;
    setActionLoading(priceId);
    setActionError(null);
    try {
      const { url } = await api.createBillingCheckoutSession(priceId);
      window.location.href = url;
    } catch (err) {
      setActionError(err.message || 'Could not start checkout');
      setActionLoading(null);
    }
  };

  const handleManage = async () => {
    if (!isTenantAdmin) return;
    setActionLoading('portal');
    setActionError(null);
    try {
      const { url } = await api.createBillingPortalSession();
      window.location.href = url;
    } catch (err) {
      setActionError(err.message || 'Could not open billing portal');
      setActionLoading(null);
    }
  };

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

      {returnNotice && (
        <div className={`billing-notice billing-notice-${returnNotice.type}`}>
          {returnNotice.text}
        </div>
      )}

      {subscription?.subscription_status === 'past_due' && (
        <div className="billing-notice billing-notice-error">
          <strong>Payment failed.</strong> Update your payment method to avoid service interruption.
          {isTenantAdmin && (
            <button className="billing-link-btn" onClick={handleManage} disabled={actionLoading === 'portal'}>
              Update payment method
            </button>
          )}
        </div>
      )}

      {actionError && (
        <div className="billing-notice billing-notice-error">{actionError}</div>
      )}

      <div className="billing-account-cards">
        <div className="billing-account-card">
          <div className="billing-account-card-header">
            <h3>Current Plan</h3>
            {subscription?.subscription_status && (
              <span className={`billing-status-badge billing-status-${subscription.subscription_status}`}>
                {statusLabel(subscription.subscription_status)}
              </span>
            )}
          </div>
          {subLoading ? (
            <p className="billing-muted">Loading…</p>
          ) : subscription?.tier ? (
            <>
              <div className="billing-tier-name">{subscription.tier.charAt(0).toUpperCase() + subscription.tier.slice(1)}</div>
              {subscription.current_period_end && (
                <p className="billing-muted">
                  {subscription.subscription_status === 'trialing' ? 'Trial ends ' : 'Renews '}
                  {formatDate(subscription.current_period_end)}
                </p>
              )}
              {isTenantAdmin && (
                <button
                  className="billing-secondary-btn"
                  onClick={handleManage}
                  disabled={actionLoading === 'portal'}
                >
                  {actionLoading === 'portal' ? 'Opening…' : 'Manage subscription'}
                </button>
              )}
            </>
          ) : (
            <>
              <p className="billing-muted">No active subscription.</p>
              <p className="billing-muted billing-small">Choose a plan below to get started.</p>
            </>
          )}
        </div>

        <div className="billing-account-card">
          <div className="billing-account-card-header">
            <h3>Payment Method</h3>
          </div>
          {subLoading ? (
            <p className="billing-muted">Loading…</p>
          ) : subscription?.has_payment_method ? (
            <>
              <div className="billing-tier-name">
                {subscription.payment_method_brand === 'ACH' ? 'Bank account' : (subscription.payment_method_brand || 'Card')}
                {' '}•••• {subscription.payment_method_last4}
              </div>
              {isTenantAdmin && (
                <button
                  className="billing-secondary-btn"
                  onClick={handleManage}
                  disabled={actionLoading === 'portal'}
                >
                  Manage
                </button>
              )}
            </>
          ) : (
            <>
              <p className="billing-muted">No payment method on file.</p>
              {subscription?.tier && isTenantAdmin && (
                <button
                  className="billing-secondary-btn"
                  onClick={handleManage}
                  disabled={actionLoading === 'portal'}
                >
                  Add payment method
                </button>
              )}
            </>
          )}
        </div>
      </div>

      {plans.length > 0 && (
        <div className="billing-plans-section">
          <h2 className="billing-section-title">Available Plans</h2>
          <p className="billing-muted">ACH preferred — avoid card processing fees by paying with a bank account.</p>
          <div className="billing-plans-grid">
            {plans.map((plan) => {
              const isCurrent = subscription?.current_plan_price_id === plan.price_id;
              return (
                <div key={plan.price_id} className={`billing-plan-card${isCurrent ? ' billing-plan-current' : ''}`}>
                  <div className="billing-plan-name">{plan.name}</div>
                  {plan.description && <p className="billing-plan-desc">{plan.description}</p>}
                  <div className="billing-plan-price">
                    {formatCurrency(plan.amount_cents)}<span className="billing-plan-interval">/mo</span>
                  </div>
                  <ul className="billing-plan-features">
                    {plan.sms_limit > 0 && <li>{plan.sms_limit.toLocaleString()} SMS messages/mo</li>}
                    {plan.sms_limit === 0 && <li>No SMS</li>}
                    {plan.call_minutes_limit > 0 && <li>{plan.call_minutes_limit} voice minutes/mo</li>}
                    {plan.call_minutes_limit === 0 && <li>No voice agent</li>}
                    {plan.trial_days > 0 && <li><strong>{plan.trial_days}-day free trial</strong></li>}
                  </ul>
                  {isCurrent ? (
                    <button className="billing-primary-btn" disabled>Current plan</button>
                  ) : (
                    <button
                      className="billing-primary-btn"
                      onClick={() => handleSelectPlan(plan.price_id)}
                      disabled={!isTenantAdmin || actionLoading === plan.price_id}
                    >
                      {actionLoading === plan.price_id ? 'Loading…' : (subscription?.tier ? 'Switch plan' : 'Select')}
                    </button>
                  )}
                </div>
              );
            })}
          </div>
          {!isTenantAdmin && (
            <p className="billing-muted billing-small">Only tenant admins can change plans.</p>
          )}
        </div>
      )}

      <h2 className="billing-section-title">Usage</h2>

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
