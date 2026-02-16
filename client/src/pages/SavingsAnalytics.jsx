import { useCallback, useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
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
  getRangeLengthDays,
  parseDateInTimeZone,
  resolveTimeZone,
} from '../utils/dateRange';
import './SavingsAnalytics.css';

const STORAGE_KEY = 'savingsAnalyticsDateRange';
const METHODOLOGY_STORAGE_KEY = 'savingsMethodologyExpanded';
const PRESET_VALUES = new Set(DATE_RANGE_PRESETS.map((preset) => preset.value));

const formatCurrency = (amount) => {
  if (!amount || amount === 0) return '$0.00';
  return `$${amount.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
};

const formatHours = (hours) => {
  if (!hours || hours === 0) return '0 hrs';
  return `${hours.toFixed(1)} hrs`;
};

const formatMinutes = (minutes) => {
  if (!minutes || minutes === 0) return '0 min';
  return `${minutes.toLocaleString(undefined, { maximumFractionDigits: 1 })} min`;
};

const formatNumber = (num) => {
  if (!num || num === 0) return '0';
  return num.toLocaleString();
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

function MethodologySection({ assumptions }) {
  const [expanded, setExpanded] = useState(() => {
    const stored = localStorage.getItem(METHODOLOGY_STORAGE_KEY);
    return stored === 'true';
  });

  const toggleExpanded = () => {
    const next = !expanded;
    setExpanded(next);
    localStorage.setItem(METHODOLOGY_STORAGE_KEY, String(next));
  };

  if (!assumptions) return null;

  return (
    <section className="savings-methodology-section">
      <button
        className="savings-methodology-toggle"
        onClick={toggleExpanded}
        aria-expanded={expanded}
      >
        <span className="methodology-icon">{expanded ? '▼' : '▶'}</span>
        <span>How are these savings calculated?</span>
      </button>

      {expanded && (
        <div className="savings-methodology-content">
          <h3>Methodology & Assumptions</h3>

          <div className="methodology-grid">
            <div className="methodology-card">
              <h4>Voice Calls</h4>
              <p>
                Hours saved equals the <strong>actual call duration</strong>. If the AI was on calls
                for 60 minutes, that's 60 minutes a human would have spent on the phone.
              </p>
              <p className="methodology-formula">
                Hours Saved = Total Call Minutes ÷ 60
              </p>
            </div>

            <div className="methodology-card">
              <h4>SMS Messages</h4>
              <p>
                Each AI response is estimated to take a human{' '}
                <strong>{assumptions.sms_minutes_per_message} minute{assumptions.sms_minutes_per_message !== 1 ? 's' : ''}</strong>{' '}
                to read the incoming message, think about an appropriate response, and send a reply.
              </p>
              <p className="methodology-formula">
                Hours Saved = (Messages × {assumptions.sms_minutes_per_message} min) ÷ 60
              </p>
            </div>

            <div className="methodology-card">
              <h4>Web Chat</h4>
              <p>
                Each AI response is estimated to take a human{' '}
                <strong>{assumptions.web_chat_minutes_per_message} minute{assumptions.web_chat_minutes_per_message !== 1 ? 's' : ''}</strong>{' '}
                per message. Web chat is shown separately and{' '}
                <strong>{assumptions.include_web_chat_in_total ? 'included in' : 'excluded from'}</strong> the
                total savings calculation.
              </p>
              <p className="methodology-formula">
                Hours Saved = (Messages × {assumptions.web_chat_minutes_per_message} min) ÷ 60
              </p>
            </div>

            <div className="methodology-card">
              <h4>Cost Savings</h4>
              <p>
                Dollar savings are calculated by multiplying hours saved by hourly labor rates:
              </p>
              <ul className="methodology-rates">
                <li>
                  <strong>Offshore:</strong> ${assumptions.offshore_rate_per_hour}/hour
                </li>
                <li>
                  <strong>Onshore:</strong> ${assumptions.onshore_rate_per_hour}/hour
                </li>
              </ul>
              <p className="methodology-note">
                These represent typical customer service labor costs. Actual savings depend on your
                specific staffing costs.
              </p>
            </div>
          </div>

          <div className="methodology-disclaimer">
            <strong>Note:</strong> These estimates assume a worker clocks in only to handle each
            interaction and clocks out immediately after—pure task time with no idle time, breaks,
            or overhead between tasks. Actual employee cost including benefits, training, and
            management overhead is not factored in. Real-world ROI may be higher when accounting
            for these additional labor costs.
          </div>
        </div>
      )}
    </section>
  );
}

export default function SavingsAnalytics() {
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
    return api.getSavingsAnalytics(params);
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

  const hasData = data && data.total_hours_saved > 0;

  const rangeDays = useMemo(
    () => getRangeLengthDays(range.startDate, range.endDate, timeZone),
    [range.startDate, range.endDate, timeZone]
  );

  const projectedAnnual = useMemo(() => {
    if (!hasData || !rangeDays || rangeDays <= 0) return null;
    const factor = 365 / rangeDays;
    return {
      offshore: (data.total_offshore_savings || 0) * factor,
      onshore: (data.total_onshore_savings || 0) * factor,
    };
  }, [hasData, rangeDays, data?.total_offshore_savings, data?.total_onshore_savings]);

  if (needsTenant) {
    return (
      <div className="savings-analytics-page">
        <EmptyState
          icon="DATA"
          title="Select a tenant to view analytics"
          description="Please select a tenant from the dropdown above to view savings analytics."
        />
      </div>
    );
  }

  if (loading) {
    return <LoadingState message="Loading savings analytics..." fullPage />;
  }

  if (error) {
    if (error.includes('Tenant context required') || error.includes('Tenant context')) {
      return (
        <div className="savings-analytics-page">
          <EmptyState
            icon="DATA"
            title="Select a tenant to view analytics"
            description="Please select a tenant from the dropdown above to view savings analytics."
          />
        </div>
      );
    }
    return (
      <div className="savings-analytics-page">
        <ErrorState message={error} onRetry={refetch} />
      </div>
    );
  }

  const rangeLabel = formatRangeLabel(range.startDate, range.endDate, timeZone);

  const header = (
    <div className="savings-analytics-header">
      <div className="savings-analytics-header-top">
        <div className="savings-analytics-title">
          <h1>Savings</h1>
          {rangeLabel && (
            <p className="savings-analytics-subtitle">
              Estimated cost savings from AI handling calls and messages from {rangeLabel}.
            </p>
          )}
        </div>
        <DateRangeFilter value={range} timeZone={timeZone} onChange={handleRangeChange} />
      </div>
      {hasData && (
        <div className="savings-analytics-summary">
          <MetricCard
            label="Hours Saved"
            value={formatHours(data.total_hours_saved)}
            tooltip={`Voice call minutes + SMS handling time (${data.assumptions?.sms_minutes_per_message || 1} min/msg).${data.assumptions?.include_web_chat_in_total ? ` Includes web chat (${data.assumptions?.web_chat_minutes_per_message || 1} min/msg).` : ' Web chat excluded from total.'}`}
          />
          <MetricCard
            label={`Offshore Savings ($${data.assumptions?.offshore_rate_per_hour || 7}/hr)`}
            value={formatCurrency(data.total_offshore_savings)}
            tooltip={`Total hours saved × $${data.assumptions?.offshore_rate_per_hour || 7}/hr offshore rate.`}
            className="savings-highlight-card"
          />
          <MetricCard
            label={`Onshore Savings ($${data.assumptions?.onshore_rate_per_hour || 14}/hr)`}
            value={formatCurrency(data.total_onshore_savings)}
            tooltip={`Total hours saved × $${data.assumptions?.onshore_rate_per_hour || 14}/hr onshore rate.`}
            className="savings-highlight-card"
          />
          <MetricCard
            label="Registration Links Sent"
            value={formatNumber(data.conversions?.total_links_sent)}
            tooltip="Count of registration links sent by the AI assistant."
          />
          {projectedAnnual && (
            <>
              <MetricCard
                label="Projected Annual (Offshore)"
                value={formatCurrency(projectedAnnual.offshore)}
                tooltip={`Annualized projection based on ${rangeDays} day${rangeDays !== 1 ? 's' : ''} of data.`}
                className="savings-projected-card"
              />
              <MetricCard
                label="Projected Annual (Onshore)"
                value={formatCurrency(projectedAnnual.onshore)}
                tooltip={`Annualized projection based on ${rangeDays} day${rangeDays !== 1 ? 's' : ''} of data.`}
                className="savings-projected-card"
              />
            </>
          )}
        </div>
      )}
    </div>
  );

  if (!hasData) {
    return (
      <div className="savings-analytics-page">
        {header}
        <EmptyState
          icon="INFO"
          title="No savings data yet"
          description="Savings will appear once your AI handles calls and conversations."
        />
      </div>
    );
  }

  return (
    <div className="savings-analytics-page">
      {header}

      <div className="savings-analytics-grid">
        {/* Voice Savings */}
        <section className="savings-analytics-card">
          <div className="savings-analytics-card-header">
            <div>
              <h2>Voice Savings</h2>
              <p>Time saved from AI handling phone calls.</p>
            </div>
          </div>
          <div className="metric-rows">
            <div className="metric-row">
              <span className="metric-label">
                Calls Handled
                <span className="info-icon" data-tooltip="Total phone calls handled by the AI assistant during this period.">i</span>
              </span>
              <span className="metric-value">{formatNumber(data.voice.count)}</span>
            </div>
            <div className="metric-row">
              <span className="metric-label">
                Total Call Time
                <span className="info-icon" data-tooltip="Actual minutes the AI spent on phone calls. This maps directly to hours saved.">i</span>
              </span>
              <span className="metric-value">{formatMinutes(data.voice.total_minutes)}</span>
            </div>
            <div className="metric-row">
              <span className="metric-label">Hours Saved</span>
              <span className="metric-value">{formatHours(data.voice.hours_saved)}</span>
            </div>
            <div className="metric-row">
              <span className="metric-label">Offshore Savings (${data.assumptions?.offshore_rate_per_hour || 7}/hr)</span>
              <span className="metric-value savings-highlight">{formatCurrency(data.voice.offshore_savings)}</span>
            </div>
            <div className="metric-row">
              <span className="metric-label">Onshore Savings (${data.assumptions?.onshore_rate_per_hour || 14}/hr)</span>
              <span className="metric-value savings-highlight">{formatCurrency(data.voice.onshore_savings)}</span>
            </div>
          </div>
        </section>

        {/* SMS Savings */}
        <section className="savings-analytics-card">
          <div className="savings-analytics-card-header">
            <div>
              <h2>SMS Savings</h2>
              <p>Time saved from AI handling text messages.</p>
            </div>
          </div>
          <div className="metric-rows">
            <div className="metric-row">
              <span className="metric-label">
                Messages Sent
                <span className="info-icon" data-tooltip="Total SMS responses sent by the AI assistant during this period.">i</span>
              </span>
              <span className="metric-value">{formatNumber(data.sms.count)}</span>
            </div>
            <div className="metric-row">
              <span className="metric-label">
                Est. Human Time
                <span className="info-icon" data-tooltip={`Each SMS response is estimated to take a human ~${data.assumptions?.sms_minutes_per_message || 1} minute(s) to read, think about, and reply.`}>i</span>
              </span>
              <span className="metric-value">{formatMinutes(data.sms.total_minutes)}</span>
            </div>
            <div className="metric-row">
              <span className="metric-label">Hours Saved</span>
              <span className="metric-value">{formatHours(data.sms.hours_saved)}</span>
            </div>
            <div className="metric-row">
              <span className="metric-label">Offshore Savings (${data.assumptions?.offshore_rate_per_hour || 7}/hr)</span>
              <span className="metric-value savings-highlight">{formatCurrency(data.sms.offshore_savings)}</span>
            </div>
            <div className="metric-row">
              <span className="metric-label">Onshore Savings (${data.assumptions?.onshore_rate_per_hour || 14}/hr)</span>
              <span className="metric-value savings-highlight">{formatCurrency(data.sms.onshore_savings)}</span>
            </div>
          </div>
        </section>

        {/* Web Chat Savings */}
        <section className="savings-analytics-card savings-analytics-card-secondary">
          <div className="savings-analytics-card-header">
            <div>
              <h2>Web Chat Savings</h2>
              <p>Time saved from AI handling web chat conversations.</p>
              {!data.assumptions?.include_web_chat_in_total && (
                <p className="excluded-note">Not included in totals above</p>
              )}
            </div>
          </div>
          <div className="metric-rows">
            <div className="metric-row">
              <span className="metric-label">
                Messages Sent
                <span className="info-icon" data-tooltip="Total web chat responses sent by the AI assistant during this period.">i</span>
              </span>
              <span className="metric-value">{formatNumber(data.web_chat.count)}</span>
            </div>
            <div className="metric-row">
              <span className="metric-label">
                Est. Human Time
                <span className="info-icon" data-tooltip={`Each web chat response is estimated to take a human ~${data.assumptions?.web_chat_minutes_per_message || 1} minute(s) to read, think about, and reply.`}>i</span>
              </span>
              <span className="metric-value">{formatMinutes(data.web_chat.total_minutes)}</span>
            </div>
            <div className="metric-row">
              <span className="metric-label">Hours Saved</span>
              <span className="metric-value">{formatHours(data.web_chat.hours_saved)}</span>
            </div>
            <div className="metric-row">
              <span className="metric-label">Offshore Savings (${data.assumptions?.offshore_rate_per_hour || 7}/hr)</span>
              <span className="metric-value savings-highlight">{formatCurrency(data.web_chat.offshore_savings)}</span>
            </div>
            <div className="metric-row">
              <span className="metric-label">Onshore Savings (${data.assumptions?.onshore_rate_per_hour || 14}/hr)</span>
              <span className="metric-value savings-highlight">{formatCurrency(data.web_chat.onshore_savings)}</span>
            </div>
          </div>
        </section>

        {/* Conversion Tracking */}
        <section className="savings-analytics-card">
          <div className="savings-analytics-card-header">
            <div>
              <h2>Conversions</h2>
              <p>Registration links sent by the AI bot.</p>
            </div>
          </div>
          <div className="metric-rows">
            <div className="metric-row">
              <span className="metric-label">
                Registration Links Sent
                <span className="info-icon" data-tooltip="Total registration links sent to prospective customers by the AI assistant.">i</span>
              </span>
              <span className="metric-value">{formatNumber(data.conversions.total_links_sent)}</span>
            </div>
            <div className="metric-row">
              <span className="metric-label">
                Unique Phone Numbers
                <span className="info-icon" data-tooltip="Number of distinct phone numbers that received at least one registration link.">i</span>
              </span>
              <span className="metric-value">{formatNumber(data.conversions.unique_phones_sent)}</span>
            </div>
            {data.conversions.by_asset_type && Object.keys(data.conversions.by_asset_type).length > 0 && (
              <>
                {Object.entries(data.conversions.by_asset_type).map(([type, count]) => (
                  <div className="metric-row" key={type}>
                    <span className="metric-label">{type.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}</span>
                    <span className="metric-value">{formatNumber(count)}</span>
                  </div>
                ))}
              </>
            )}
            <div className="metric-row">
              <span className="metric-label">
                Verified Enrollments
                <span className="info-icon" data-tooltip="Customers whose phone number or email matches someone who interacted with the AI via chat, SMS, or voice call. This is a running total that only grows over time.">i</span>
              </span>
              <span className="metric-value">{formatNumber(data.conversions.verified_enrollments || 0)}</span>
            </div>
            {(data.conversions.verified_phones || 0) > 0 && (
              <div className="metric-row">
                <span className="metric-label">
                  Verified Unique Phones
                  <span className="info-icon" data-tooltip="Distinct phone numbers that both interacted with the AI and appear as enrolled customers.">i</span>
                </span>
                <span className="metric-value">{formatNumber(data.conversions.verified_phones)}</span>
              </div>
            )}
          </div>
        </section>
      </div>

      <MethodologySection assumptions={data.assumptions} />
    </div>
  );
}
