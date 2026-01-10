import { useCallback, useMemo } from 'react';
import { format, parseISO } from 'date-fns';
import { api } from '../api/client';
import { useFetchData } from '../hooks/useFetchData';
import { useAuth } from '../context/AuthContext';
import { LoadingState, EmptyState, ErrorState } from '../components/ui';
import './Plots.css';

const formatShortDate = (value) => {
  try {
    return format(parseISO(value), 'MMM d');
  } catch {
    return value;
  }
};

const formatLongDate = (value) => {
  try {
    return format(parseISO(value), 'MMM d, yyyy');
  } catch {
    return value;
  }
};

const formatMinutes = (value) => {
  const minutes = Number(value) || 0;
  if (minutes === 0) return '0';
  if (Number.isInteger(minutes)) return minutes.toString();
  return minutes.toFixed(1);
};

const getLabelInterval = (count) => {
  if (count <= 7) return 1;
  if (count <= 14) return 2;
  return Math.ceil(count / 8);
};

export default function Plots() {
  const { user, selectedTenantId } = useAuth();
  const needsTenant = user?.is_global_admin && !selectedTenantId;

  const fetchUsage = useCallback(async () => api.getUsageAnalytics(), []);
  const { data, loading, error, refetch } = useFetchData(fetchUsage, {
    defaultValue: { onboarded_date: null, series: [] },
    immediate: !needsTenant,
    deps: [selectedTenantId],
  });

  const usageSeries = data?.series || [];
  const labelInterval = getLabelInterval(usageSeries.length);

  const totals = useMemo(() => {
    return usageSeries.reduce(
      (acc, day) => {
        acc.smsIn += day.sms_in || 0;
        acc.smsOut += day.sms_out || 0;
        acc.chatbot += day.chatbot_interactions || 0;
        acc.callMinutes += Number(day.call_minutes || 0);
        acc.callCount += day.call_count || 0;
        return acc;
      },
      { smsIn: 0, smsOut: 0, chatbot: 0, callMinutes: 0, callCount: 0 }
    );
  }, [usageSeries]);

  const hasUsage = usageSeries.some(
    (day) =>
      day.sms_in ||
      day.sms_out ||
      day.chatbot_interactions ||
      day.call_count ||
      Number(day.call_minutes || 0) > 0
  );

  const interactionSeries = useMemo(
    () =>
      usageSeries.map((day) => {
        const smsIn = day.sms_in || 0;
        const smsOut = day.sms_out || 0;
        const textTotal = smsIn + smsOut;
        return {
          date: day.date,
          smsIn,
          smsOut,
          text: textTotal,
          phone: day.call_count || 0,
          chat: day.chatbot_interactions || 0,
        };
      }),
    [usageSeries]
  );

  const interactionMaxValue = Math.max(
    0,
    ...interactionSeries.map((day) => day.text + day.phone + day.chat)
  );
  const callMaxValue = Math.max(0, ...usageSeries.map((day) => Number(day.call_minutes || 0)));
  const interactionScaleMax = interactionMaxValue || 1;
  const callScaleMax = callMaxValue || 1;

  const rangeStart = data?.onboarded_date;
  const rangeEnd = usageSeries.length ? usageSeries[usageSeries.length - 1].date : rangeStart;

  if (needsTenant) {
    return (
      <div className="plots-page">
        <EmptyState
          icon="DATA"
          title="Select a tenant to view analytics"
          description="Please select a tenant from the dropdown above to view usage analytics."
        />
      </div>
    );
  }

  if (loading) {
    return <LoadingState message="Loading usage analytics..." fullPage />;
  }

  if (error) {
    if (error.includes('Tenant context required') || error.includes('Tenant context')) {
      return (
        <div className="plots-page">
          <EmptyState
            icon="DATA"
            title="Select a tenant to view analytics"
            description="Please select a tenant from the dropdown above to view usage analytics."
          />
        </div>
      );
    }
    return (
      <div className="plots-page">
        <ErrorState message={error} onRetry={refetch} />
      </div>
    );
  }

  if (!hasUsage) {
    return (
      <div className="plots-page">
        <h1>Usage Analytics</h1>
        <EmptyState
          icon="INFO"
          title="No usage yet"
          description="Usage will appear once customers start texting, chatting, or calling."
        />
      </div>
    );
  }

  return (
    <div className="plots-page">
      <div className="plots-header">
        <div>
          <h1>Usage Analytics</h1>
          {rangeStart && (
            <p className="plots-subtitle">
              Tracking usage from {formatLongDate(rangeStart)}{rangeEnd ? ` to ${formatLongDate(rangeEnd)}` : ''}.
            </p>
          )}
        </div>
        <div className="plots-summary">
          <div>
            <span className="summary-value">{totals.smsIn + totals.smsOut}</span>
            <span className="summary-label">Texts</span>
          </div>
          <div>
            <span className="summary-value">{totals.chatbot}</span>
            <span className="summary-label">Chatbot</span>
          </div>
          <div>
            <span className="summary-value">{totals.callCount}</span>
            <span className="summary-label">Phone Calls</span>
          </div>
          <div>
            <span className="summary-value">{formatMinutes(totals.callMinutes)}</span>
            <span className="summary-label">Call Minutes</span>
          </div>
        </div>
      </div>

      <div className="usage-grid">
        <section className="usage-card">
          <div className="usage-card-header">
            <div>
              <h2>Interaction Mix</h2>
              <p>Daily counts for texts, phone calls, and chatbot interactions</p>
            </div>
            <div className="usage-legend">
              <span className="legend-item">
                <span className="legend-swatch text" />
                Texts
              </span>
              <span className="legend-item">
                <span className="legend-swatch phone" />
                Phone
              </span>
              <span className="legend-item">
                <span className="legend-swatch chatbot" />
                Chatbot
              </span>
            </div>
          </div>
          <div className="usage-chart">
            <div className="usage-y-axis">
              <span>{Math.round(interactionMaxValue)}</span>
              <span>{Math.round(interactionMaxValue / 2)}</span>
              <span>0</span>
            </div>
            <div className="usage-bars">
              {interactionSeries.map((day, index) => {
                const textHeight = (day.text / interactionScaleMax) * 100;
                const phoneHeight = (day.phone / interactionScaleMax) * 100;
                const chatHeight = (day.chat / interactionScaleMax) * 100;
                const showLabel = index % labelInterval === 0 || index === interactionSeries.length - 1;
                const tooltip = `${formatLongDate(day.date)} - Texts: ${day.text} (in ${day.smsIn}, out ${day.smsOut}), Phone: ${day.phone}, Chatbot: ${day.chat}`;
                return (
                  <div className="usage-bar-column" key={day.date}>
                    <div
                      className="usage-bar-track"
                      title={tooltip}
                    >
                      <div className="usage-bar text" style={{ height: `${textHeight}%` }} />
                      <div className="usage-bar phone" style={{ height: `${phoneHeight}%` }} />
                      <div className="usage-bar chatbot" style={{ height: `${chatHeight}%` }} />
                    </div>
                    <span className="usage-x-label">{showLabel ? formatShortDate(day.date) : ''}</span>
                  </div>
                );
              })}
            </div>
          </div>
        </section>

        <section className="usage-card">
          <div className="usage-card-header">
            <div>
              <h2>Phone Call Duration</h2>
              <p>Total call duration per day (minutes)</p>
            </div>
            <div className="usage-legend">
              <span className="legend-item">
                <span className="legend-swatch calls" />
                Minutes
              </span>
            </div>
          </div>
          <div className="usage-chart">
            <div className="usage-y-axis">
              <span>{formatMinutes(callMaxValue)}</span>
              <span>{formatMinutes(callMaxValue / 2)}</span>
              <span>0</span>
            </div>
            <div className="usage-bars">
              {usageSeries.map((day, index) => {
                const minutes = Number(day.call_minutes || 0);
                const height = (minutes / callScaleMax) * 100;
                const showLabel = index % labelInterval === 0 || index === usageSeries.length - 1;
                return (
                  <div className="usage-bar-column" key={day.date}>
                    <div
                      className="usage-bar-track"
                      title={`${formatLongDate(day.date)} - ${formatMinutes(minutes)} minutes`}
                    >
                      <div className="usage-bar calls" style={{ height: `${height}%` }} />
                    </div>
                    <span className="usage-x-label">{showLabel ? formatShortDate(day.date) : ''}</span>
                  </div>
                );
              })}
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
