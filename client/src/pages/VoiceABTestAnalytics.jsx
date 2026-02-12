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
  parseDateInTimeZone,
  resolveTimeZone,
} from '../utils/dateRange';
import './VoiceABTestAnalytics.css';

const STORAGE_KEY = 'voiceABTestDateRange';
const PRESET_VALUES = new Set(DATE_RANGE_PRESETS.map((preset) => preset.value));

const VARIANT_COLORS = ['#6366f1', '#f59e0b', '#10b981', '#ef4444', '#8b5cf6'];

const formatSeconds = (seconds) => {
  if (!seconds || seconds === 0) return '0s';
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const minutes = Math.floor(seconds / 60);
  const secs = Math.round(seconds % 60);
  return secs > 0 ? `${minutes}m ${secs}s` : `${minutes}m`;
};

const formatMinutes = (minutes) => {
  if (!minutes || minutes === 0) return '0m';
  if (minutes < 60) return `${minutes.toFixed(1)}m`;
  const hours = Math.floor(minutes / 60);
  const mins = Math.round(minutes % 60);
  return mins > 0 ? `${hours}h ${mins}m` : `${hours}h`;
};

const formatPercent = (rate) => {
  if (!rate || rate === 0) return '0%';
  return `${(rate * 100).toFixed(1)}%`;
};

const formatNumber = (num) => {
  if (!num || num === 0) return '0';
  return num.toLocaleString();
};

const formatIntentLabel = (intent) => {
  if (!intent) return 'Unknown';
  return intent
    .split('_')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
};

// --- URL / localStorage date range helpers (mirrors ConversationAnalytics) ---

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

// --- Delta calculation helper ---

function computeDelta(variantValue, controlValue) {
  if (!controlValue || controlValue === 0) return null;
  const diff = ((variantValue - controlValue) / controlValue) * 100;
  return diff;
}

function DeltaIndicator({ value, higherIsBetter = true }) {
  if (value === null || value === undefined) return null;
  const isPositive = value > 0;
  const isGood = higherIsBetter ? isPositive : !isPositive;
  const className = Math.abs(value) < 0.5
    ? 'voice-ab-metric-delta neutral'
    : isGood
      ? 'voice-ab-metric-delta positive'
      : 'voice-ab-metric-delta negative';
  return (
    <span className={className}>
      {value > 0 ? '+' : ''}{value.toFixed(1)}%
    </span>
  );
}

// =============================================================================
// Main Component
// =============================================================================

export default function VoiceABTestAnalytics() {
  const { user, selectedTenantId } = useAuth();
  const needsTenant = user?.is_global_admin && !selectedTenantId;
  const [searchParams, setSearchParams] = useSearchParams();

  const browserTimeZone = useMemo(() => resolveTimeZone(), []);
  const [timeZone, setTimeZone] = useState(browserTimeZone);

  // Date range state
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

  // Test list + selected test
  const [tests, setTests] = useState([]);
  const [selectedTestId, setSelectedTestId] = useState(null);
  const [testsLoading, setTestsLoading] = useState(true);
  const [testsError, setTestsError] = useState(null);

  const fetchTests = useCallback(async () => {
    setTestsLoading(true);
    setTestsError(null);
    try {
      const result = await api.getVoiceABTests();
      const list = Array.isArray(result) ? result : result?.tests || [];
      setTests(list);
      if (list.length > 0 && !selectedTestId) {
        setSelectedTestId(list[0].id);
      }
    } catch (err) {
      setTestsError(err.message);
    } finally {
      setTestsLoading(false);
    }
  }, [selectedTestId]);

  useEffect(() => {
    if (!needsTenant) fetchTests();
  }, [needsTenant, fetchTests]);

  // Analytics data
  const fetchAnalytics = useCallback(async () => {
    if (!range?.startDate || !range?.endDate || !selectedTestId) return null;
    const params = buildParamsFromRange(range, timeZone);
    params.test_id = selectedTestId;
    return api.getVoiceABTestAnalytics(params);
  }, [range, timeZone, selectedTestId]);

  const { data, loading, error, refetch } = useFetchData(fetchAnalytics, {
    defaultValue: null,
    immediate: !needsTenant && !!selectedTestId,
    deps: [selectedTenantId, range.startDate, range.endDate, timeZone, selectedTestId],
  });

  // Sync server timezone
  useEffect(() => {
    if (!data?.timezone || data.timezone === timeZone) return;
    const aligned = alignRangeToTimeZone(range, timeZone, data.timezone);
    setTimeZone(data.timezone);
    setRange(aligned);
    persistRange(aligned, data.timezone, setSearchParams, true);
  }, [data?.timezone, range, setSearchParams, timeZone]);

  // Manage test section state
  const [manageOpen, setManageOpen] = useState(false);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [newTestName, setNewTestName] = useState('');
  const [newVariants, setNewVariants] = useState([
    { voice_model: '', label: '', is_control: true },
    { voice_model: '', label: '', is_control: false },
  ]);
  const [saving, setSaving] = useState(false);

  // --- Derived data ---

  const variants = data?.variants || [];
  const controlVariant = variants.find((v) => v.is_control) || variants[0] || null;
  const totalCalls = data?.total_calls || 0;
  const totalLeads = variants.reduce((sum, v) => sum + (v.lead_count || 0), 0);
  const hasData = data && variants.length > 0 && totalCalls > 0;
  const rangeLabel = formatRangeLabel(range.startDate, range.endDate, timeZone);

  // Build combined intent keys across all variants
  const allIntentKeys = useMemo(() => {
    const keys = new Set();
    variants.forEach((v) => {
      if (v.intent_distribution) {
        Object.keys(v.intent_distribution).forEach((k) => keys.add(k));
      }
    });
    return [...keys].sort();
  }, [variants]);

  // Build combined outcome keys
  const allOutcomeKeys = useMemo(() => {
    const keys = new Set();
    variants.forEach((v) => {
      if (v.outcome_distribution) {
        Object.keys(v.outcome_distribution).forEach((k) => keys.add(k));
      }
    });
    return [...keys].sort();
  }, [variants]);

  // Build daily trend data: merge all variants into a single date-keyed map
  const dailyTrendData = useMemo(() => {
    const dateMap = {};
    variants.forEach((v, idx) => {
      (v.daily_series || []).forEach((day) => {
        if (!dateMap[day.date]) dateMap[day.date] = {};
        dateMap[day.date][v.variant_id || idx] = day;
      });
    });
    return Object.entries(dateMap)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([date, byVariant]) => ({ date, byVariant }));
  }, [variants]);

  const maxDailyCalls = useMemo(() => {
    let max = 1;
    dailyTrendData.forEach(({ byVariant }) => {
      Object.values(byVariant).forEach((d) => {
        if (d.calls > max) max = d.calls;
      });
    });
    return max;
  }, [dailyTrendData]);

  // =========================================================================
  // CRUD handlers
  // =========================================================================

  const handleCreateTest = async () => {
    if (!newTestName.trim() || newVariants.length < 2) return;
    const hasControl = newVariants.some((v) => v.is_control);
    if (!hasControl) return;
    const validVariants = newVariants.filter((v) => v.voice_model.trim() && v.label.trim());
    if (validVariants.length < 2) return;

    setSaving(true);
    try {
      const result = await api.createVoiceABTest({
        name: newTestName.trim(),
        started_at: new Date().toISOString(),
        variants: validVariants,
      });
      setShowCreateForm(false);
      setNewTestName('');
      setNewVariants([
        { voice_model: '', label: '', is_control: true },
        { voice_model: '', label: '', is_control: false },
      ]);
      await fetchTests();
      if (result?.id) setSelectedTestId(result.id);
    } catch (err) {
      alert(`Failed to create test: ${err.message}`);
    } finally {
      setSaving(false);
    }
  };

  const handleEndTest = async () => {
    if (!selectedTestId) return;
    if (!window.confirm('Are you sure you want to end this test?')) return;
    setSaving(true);
    try {
      await api.updateVoiceABTest(selectedTestId, {
        status: 'completed',
        ended_at: new Date().toISOString(),
      });
      await fetchTests();
      refetch();
    } catch (err) {
      alert(`Failed to end test: ${err.message}`);
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteTest = async () => {
    if (!selectedTestId) return;
    if (!window.confirm('Are you sure you want to delete this test? This cannot be undone.')) return;
    setSaving(true);
    try {
      await api.deleteVoiceABTest(selectedTestId);
      setSelectedTestId(null);
      await fetchTests();
    } catch (err) {
      alert(`Failed to delete test: ${err.message}`);
    } finally {
      setSaving(false);
    }
  };

  const addVariantToForm = () => {
    setNewVariants([...newVariants, { voice_model: '', label: '', is_control: false }]);
  };

  const removeVariantFromForm = (index) => {
    if (newVariants.length <= 2) return;
    setNewVariants(newVariants.filter((_, i) => i !== index));
  };

  const updateVariantInForm = (index, field, value) => {
    const updated = [...newVariants];
    updated[index] = { ...updated[index], [field]: value };
    if (field === 'is_control' && value === true) {
      updated.forEach((v, i) => {
        if (i !== index) updated[i] = { ...v, is_control: false };
      });
    }
    setNewVariants(updated);
  };

  // =========================================================================
  // Render
  // =========================================================================

  if (needsTenant) {
    return (
      <div className="voice-ab-page">
        <EmptyState
          icon="DATA"
          title="Select a tenant to view analytics"
          description="Please select a tenant from the dropdown above to view Voice A/B Test analytics."
        />
      </div>
    );
  }

  if (testsLoading && !tests.length) {
    return <LoadingState message="Loading A/B tests..." fullPage />;
  }

  if (testsError) {
    return (
      <div className="voice-ab-page">
        <ErrorState message={testsError} onRetry={fetchTests} />
      </div>
    );
  }

  // --- No tests exist at all ---
  if (tests.length === 0 && !testsLoading) {
    return (
      <div className="voice-ab-page">
        <div className="voice-ab-header">
          <div className="voice-ab-header-top">
            <div className="voice-ab-title">
              <h1>Voice Agent A/B Testing</h1>
              <p className="voice-ab-subtitle">Compare voice model performance side-by-side.</p>
            </div>
          </div>
        </div>

        <EmptyState
          icon="DATA"
          title="No A/B tests yet"
          description="Create your first voice agent A/B test to start comparing voice models."
        />

        <div style={{ marginTop: '1.5rem' }}>
          {renderCreateForm()}
        </div>
      </div>
    );
  }

  const selectedTest = tests.find((t) => t.id === selectedTestId) || tests[0];

  // --- Header ---
  const header = (
    <div className="voice-ab-header">
      <div className="voice-ab-header-top">
        <div className="voice-ab-title">
          <h1>Voice Agent A/B Testing</h1>
          {rangeLabel && (
            <p className="voice-ab-subtitle">
              {data?.test_name || selectedTest?.name || 'Test'}{' '}
              <span className={`voice-ab-status ${data?.test_status || selectedTest?.status || 'active'}`}>
                {data?.test_status || selectedTest?.status || 'active'}
              </span>
              {' '}&mdash; {rangeLabel}
            </p>
          )}
        </div>
        <div className="voice-ab-controls">
          <select
            className="voice-ab-test-select"
            value={selectedTestId || ''}
            onChange={(e) => setSelectedTestId(Number(e.target.value))}
          >
            {tests.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name} ({t.status || 'active'})
              </option>
            ))}
          </select>
          <button
            className="voice-ab-new-test-btn"
            onClick={() => { setManageOpen(true); setShowCreateForm(true); }}
          >
            + New Test
          </button>
          <DateRangeFilter value={range} timeZone={timeZone} onChange={handleRangeChange} />
        </div>
      </div>

      {hasData && (
        <div className="voice-ab-summary">
          <MetricCard
            label="Total Calls"
            value={formatNumber(totalCalls)}
            tooltip="Total calls across all variants in this period."
          />
          <MetricCard
            label="Total Leads"
            value={formatNumber(totalLeads)}
            tooltip="Leads captured across all variants in this period."
          />
          <MetricCard
            label="Variants"
            value={variants.length}
            tooltip="Number of voice model variants in this test."
          />
        </div>
      )}
    </div>
  );

  if (loading) {
    return (
      <div className="voice-ab-page">
        {header}
        <LoadingState message="Loading A/B test analytics..." />
      </div>
    );
  }

  if (error) {
    if (error.includes('Tenant context required') || error.includes('Tenant context')) {
      return (
        <div className="voice-ab-page">
          <EmptyState
            icon="DATA"
            title="Select a tenant to view analytics"
            description="Please select a tenant from the dropdown above to view Voice A/B Test analytics."
          />
        </div>
      );
    }
    return (
      <div className="voice-ab-page">
        {header}
        <ErrorState message={error} onRetry={refetch} />
      </div>
    );
  }

  if (!hasData) {
    return (
      <div className="voice-ab-page">
        {header}
        <EmptyState
          icon="INFO"
          title="No call data yet"
          description="Analytics will appear once calls come in for the selected A/B test and date range."
        />
        {renderManageSection()}
      </div>
    );
  }

  // =========================================================================
  // Main analytics view
  // =========================================================================

  return (
    <div className="voice-ab-page">
      {header}

      {/* Variant comparison columns */}
      <div className="voice-ab-variants-row">
        {variants.map((variant, idx) => {
          const color = VARIANT_COLORS[idx % VARIANT_COLORS.length];
          const isControl = variant.is_control;
          const callDelta = isControl ? null : computeDelta(variant.call_count, controlVariant?.call_count);
          const convDelta = isControl ? null : computeDelta(variant.lead_conversion_rate, controlVariant?.lead_conversion_rate);
          const durationDelta = isControl ? null : computeDelta(variant.avg_duration_seconds, controlVariant?.avg_duration_seconds);
          const handoffDelta = isControl ? null : computeDelta(variant.handoff_rate, controlVariant?.handoff_rate);

          return (
            <div key={variant.variant_id || idx} className="voice-ab-variant-col">
              <div className="voice-ab-variant-header" style={{ borderBottomColor: color }}>
                <span className="voice-ab-variant-color" style={{ backgroundColor: color }} />
                <span className="voice-ab-variant-name">{variant.label}</span>
                <span className="voice-ab-variant-model">{variant.voice_model}</span>
                {isControl && <span className="voice-ab-control-badge">Control</span>}
              </div>
              <div className="voice-ab-variant-metrics">
                <div className="voice-ab-metric">
                  <span className="voice-ab-metric-label">Calls</span>
                  <span className="voice-ab-metric-value">{formatNumber(variant.call_count)}</span>
                  <DeltaIndicator value={callDelta} higherIsBetter />
                </div>
                <div className="voice-ab-metric">
                  <span className="voice-ab-metric-label">Avg Duration</span>
                  <span className="voice-ab-metric-value">{formatSeconds(variant.avg_duration_seconds)}</span>
                  <DeltaIndicator value={durationDelta} higherIsBetter />
                </div>
                <div className="voice-ab-metric">
                  <span className="voice-ab-metric-label">Lead Rate</span>
                  <span className="voice-ab-metric-value">{formatPercent(variant.lead_conversion_rate)}</span>
                  <DeltaIndicator value={convDelta} higherIsBetter />
                </div>
                <div className="voice-ab-metric">
                  <span className="voice-ab-metric-label">Handoff Rate</span>
                  <span className="voice-ab-metric-value">{formatPercent(variant.handoff_rate)}</span>
                  <DeltaIndicator value={handoffDelta} higherIsBetter={false} />
                </div>
              </div>
            </div>
          );
        })}
      </div>

      <div className="voice-ab-grid">
        {/* Intent Distribution */}
        {allIntentKeys.length > 0 && (
          <section className="voice-ab-card voice-ab-card-wide">
            <div className="voice-ab-card-header">
              <div>
                <h2>Intent Distribution</h2>
                <p>Customer intent breakdown per variant.</p>
              </div>
            </div>
            <div className="voice-ab-legend">
              {variants.map((v, idx) => (
                <span key={v.variant_id || idx} className="voice-ab-legend-item">
                  <span className="voice-ab-legend-dot" style={{ backgroundColor: VARIANT_COLORS[idx % VARIANT_COLORS.length] }} />
                  {v.label}
                </span>
              ))}
            </div>
            {allIntentKeys.map((intent) => {
              const maxCount = Math.max(1, ...variants.map((v) => (v.intent_distribution?.[intent] || 0)));
              return (
                <div key={intent} className="voice-ab-dist-row">
                  <span className="voice-ab-dist-label">{formatIntentLabel(intent)}</span>
                  <div className="voice-ab-dist-bars">
                    {variants.map((v, idx) => {
                      const count = v.intent_distribution?.[intent] || 0;
                      const width = (count / maxCount) * 100;
                      return (
                        <div key={v.variant_id || idx} className="voice-ab-dist-bar-row">
                          <div
                            className="voice-ab-dist-bar"
                            style={{
                              width: `${width}%`,
                              backgroundColor: VARIANT_COLORS[idx % VARIANT_COLORS.length],
                            }}
                          />
                          <span className="voice-ab-dist-value">{count}</span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </section>
        )}

        {/* Outcome Distribution */}
        {allOutcomeKeys.length > 0 && (
          <section className="voice-ab-card voice-ab-card-wide">
            <div className="voice-ab-card-header">
              <div>
                <h2>Outcome Distribution</h2>
                <p>Call outcomes per variant.</p>
              </div>
            </div>
            <div className="voice-ab-legend">
              {variants.map((v, idx) => (
                <span key={v.variant_id || idx} className="voice-ab-legend-item">
                  <span className="voice-ab-legend-dot" style={{ backgroundColor: VARIANT_COLORS[idx % VARIANT_COLORS.length] }} />
                  {v.label}
                </span>
              ))}
            </div>
            {allOutcomeKeys.map((outcome) => {
              const maxCount = Math.max(1, ...variants.map((v) => (v.outcome_distribution?.[outcome] || 0)));
              return (
                <div key={outcome} className="voice-ab-dist-row">
                  <span className="voice-ab-dist-label">{formatIntentLabel(outcome)}</span>
                  <div className="voice-ab-dist-bars">
                    {variants.map((v, idx) => {
                      const count = v.outcome_distribution?.[outcome] || 0;
                      const width = (count / maxCount) * 100;
                      return (
                        <div key={v.variant_id || idx} className="voice-ab-dist-bar-row">
                          <div
                            className="voice-ab-dist-bar"
                            style={{
                              width: `${width}%`,
                              backgroundColor: VARIANT_COLORS[idx % VARIANT_COLORS.length],
                            }}
                          />
                          <span className="voice-ab-dist-value">{count}</span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </section>
        )}

        {/* Daily Trend */}
        {dailyTrendData.length > 0 && (
          <section className="voice-ab-card voice-ab-card-wide">
            <div className="voice-ab-card-header">
              <div>
                <h2>Daily Trend</h2>
                <p>Calls and leads per day, per variant.</p>
              </div>
            </div>
            <div className="voice-ab-legend">
              {variants.map((v, idx) => (
                <span key={v.variant_id || idx} className="voice-ab-legend-item">
                  <span className="voice-ab-legend-dot" style={{ backgroundColor: VARIANT_COLORS[idx % VARIANT_COLORS.length] }} />
                  {v.label}
                </span>
              ))}
            </div>
            <div style={{ overflowX: 'auto' }}>
              <table className="voice-ab-trend-table">
                <thead>
                  <tr>
                    <th>Date</th>
                    {variants.map((v, idx) => (
                      <th key={v.variant_id || idx} style={{ color: VARIANT_COLORS[idx % VARIANT_COLORS.length] }}>
                        {v.label} Calls
                      </th>
                    ))}
                    {variants.map((v, idx) => (
                      <th key={`leads-${v.variant_id || idx}`} style={{ color: VARIANT_COLORS[idx % VARIANT_COLORS.length] }}>
                        {v.label} Leads
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {dailyTrendData.map(({ date, byVariant }) => (
                    <tr key={date}>
                      <td className="voice-ab-trend-date">{date}</td>
                      {variants.map((v, idx) => {
                        const day = byVariant[v.variant_id || idx];
                        const calls = day?.calls || 0;
                        const barWidth = (calls / maxDailyCalls) * 100;
                        return (
                          <td key={v.variant_id || idx} className="voice-ab-trend-bar-cell">
                            <div className="voice-ab-trend-bar-container">
                              <div
                                className="voice-ab-trend-bar"
                                style={{
                                  width: `${barWidth}%`,
                                  backgroundColor: VARIANT_COLORS[idx % VARIANT_COLORS.length],
                                }}
                              />
                              <span className="voice-ab-trend-value">{calls}</span>
                            </div>
                          </td>
                        );
                      })}
                      {variants.map((v, idx) => {
                        const day = byVariant[v.variant_id || idx];
                        const leads = day?.leads || 0;
                        return (
                          <td key={`leads-${v.variant_id || idx}`}>
                            <span style={{ fontWeight: leads > 0 ? 600 : 400, color: leads > 0 ? '#10b981' : 'inherit' }}>
                              {leads}
                            </span>
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}
      </div>

      {/* Manage Test section */}
      {renderManageSection()}
    </div>
  );

  // =========================================================================
  // Sub-renders
  // =========================================================================

  function renderManageSection() {
    return (
      <div className="voice-ab-manage">
        <button
          className="voice-ab-manage-toggle"
          onClick={() => setManageOpen(!manageOpen)}
        >
          <span className={`voice-ab-manage-chevron ${manageOpen ? 'expanded' : ''}`}>&#9654;</span>
          Manage Tests
        </button>
        {manageOpen && (
          <div className="voice-ab-manage-content">
            {selectedTest && (
              <div className="voice-ab-manage-actions">
                {(data?.test_status || selectedTest?.status) === 'active' && (
                  <button
                    className="voice-ab-btn"
                    onClick={handleEndTest}
                    disabled={saving}
                  >
                    End Test
                  </button>
                )}
                <button
                  className="voice-ab-btn danger"
                  onClick={handleDeleteTest}
                  disabled={saving}
                >
                  Delete Test
                </button>
                <button
                  className="voice-ab-btn primary"
                  onClick={() => setShowCreateForm(!showCreateForm)}
                >
                  {showCreateForm ? 'Cancel' : '+ New Test'}
                </button>
              </div>
            )}

            {showCreateForm && renderCreateForm()}
          </div>
        )}
      </div>
    );
  }

  function renderCreateForm() {
    return (
      <div className="voice-ab-form">
        <div className="voice-ab-form-group">
          <label>Test Name</label>
          <input
            type="text"
            placeholder="e.g. Jessica vs DBOT"
            value={newTestName}
            onChange={(e) => setNewTestName(e.target.value)}
          />
        </div>

        <div className="voice-ab-form-group">
          <label>Variants (min 2)</label>
          <div className="voice-ab-variant-list">
            {newVariants.map((v, idx) => (
              <div key={idx} className="voice-ab-variant-form-row">
                <div className="voice-ab-form-group">
                  <label>Voice Model</label>
                  <input
                    type="text"
                    placeholder="e.g. ElevenLabsJessica"
                    value={v.voice_model}
                    onChange={(e) => updateVariantInForm(idx, 'voice_model', e.target.value)}
                  />
                </div>
                <div className="voice-ab-form-group">
                  <label>Label</label>
                  <input
                    type="text"
                    placeholder="e.g. Jessica"
                    value={v.label}
                    onChange={(e) => updateVariantInForm(idx, 'label', e.target.value)}
                  />
                </div>
                <div className="voice-ab-form-group">
                  <label>
                    <input
                      type="radio"
                      name="control"
                      checked={v.is_control}
                      onChange={() => updateVariantInForm(idx, 'is_control', true)}
                    />{' '}
                    Control
                  </label>
                </div>
                {newVariants.length > 2 && (
                  <button
                    className="voice-ab-remove-btn"
                    title="Remove variant"
                    onClick={() => removeVariantFromForm(idx)}
                  >
                    &times;
                  </button>
                )}
              </div>
            ))}
          </div>
          <button className="voice-ab-btn" onClick={addVariantToForm} style={{ alignSelf: 'flex-start', marginTop: '0.5rem' }}>
            + Add Variant
          </button>
        </div>

        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <button
            className="voice-ab-btn primary"
            onClick={handleCreateTest}
            disabled={saving || !newTestName.trim() || newVariants.filter((v) => v.voice_model.trim() && v.label.trim()).length < 2}
          >
            {saving ? 'Creating...' : 'Create Test'}
          </button>
          <button className="voice-ab-btn" onClick={() => setShowCreateForm(false)}>
            Cancel
          </button>
        </div>
      </div>
    );
  }
}
