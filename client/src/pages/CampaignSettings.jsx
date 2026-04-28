import { useState, useEffect, useMemo, useCallback } from 'react';
import { useAuth } from '../context/AuthContext';
import { LoadingState, ErrorState, EmptyState } from '../components/ui';
import { usePipelineStages } from '../hooks/usePipelineStages';
import './CampaignSettings.css';

const API_BASE = '/api/v1';

function formatDelay(minutes) {
  if (minutes < 60) return `${minutes} min`;
  if (minutes < 1440) return `${Math.round(minutes / 60)} hours`;
  return `${Math.round(minutes / 1440)} days`;
}

function toMinutes(value, unit) {
  const n = parseInt(value, 10);
  if (Number.isNaN(n) || n < 0) return 0;
  if (unit === 'days') return n * 1440;
  if (unit === 'hours') return n * 60;
  return n;
}

function splitMinutes(minutes) {
  const m = Number(minutes) || 0;
  if (m > 0 && m % 1440 === 0) return { value: m / 1440, unit: 'days' };
  if (m > 0 && m % 60 === 0) return { value: m / 60, unit: 'hours' };
  return { value: m, unit: 'minutes' };
}

function formatDateTime(isoString) {
  if (!isoString) return '—';
  const d = new Date(isoString);
  return d.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
}

const STATUS_COLORS = {
  active: 'sms-status-badge--active',
  responded: 'sms-status-badge--modified',
  completed: 'sms-status-badge--active',
  cancelled: 'sms-status-badge--inactive',
};

export default function CampaignSettings() {
  const { token, user, selectedTenantId } = useAuth();
  const { stages: pipelineStages, stageMap } = usePipelineStages();
  const [campaigns, setCampaigns] = useState([]);
  const [originalCampaigns, setOriginalCampaigns] = useState([]);
  const [enrollments, setEnrollments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);
  const [cancellingId, setCancellingId] = useState(null);
  const [toast, setToast] = useState(null);
  const [expandedSections, setExpandedSections] = useState({});
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newCampaignDraft, setNewCampaignDraft] = useState({
    name: '',
    audience_filter: 'any',
    match_all_tags: true,
    tag_filter: '',
    trigger_delay_value: 10,
    trigger_delay_unit: 'minutes',
    total_attempts: 3,
    spacing_value: 1,
    spacing_unit: 'days',
  });
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState(null);
  const [deletingId, setDeletingId] = useState(null);
  const [dripSettings, setDripSettings] = useState({ drip_affects_pipeline: true });
  const [savingSettings, setSavingSettings] = useState(false);

  const [viewMode, setViewMode] = useState(() => {
    if (typeof window === 'undefined') return 'simple';
    return window.localStorage.getItem('campaignSettings.viewMode') || 'simple';
  });
  const isSimple = viewMode === 'simple';
  const setViewModePersistent = useCallback((mode) => {
    setViewMode(mode);
    if (typeof window !== 'undefined') {
      window.localStorage.setItem('campaignSettings.viewMode', mode);
    }
  }, []);

  const isDirty = useMemo(() => {
    if (!originalCampaigns.length) return false;
    return JSON.stringify(campaigns) !== JSON.stringify(originalCampaigns);
  }, [campaigns, originalCampaigns]);

  const showToast = useCallback((message, type = 'success') => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 3000);
  }, []);

  const buildHeaders = useCallback((includeContentType = false) => {
    const headers = { 'Authorization': `Bearer ${token}` };
    if (includeContentType) {
      headers['Content-Type'] = 'application/json';
    }
    if (user?.is_global_admin && selectedTenantId) {
      headers['X-Tenant-Id'] = selectedTenantId.toString();
    }
    return headers;
  }, [token, user?.is_global_admin, selectedTenantId]);

  useEffect(() => {
    fetchData();
  }, [token, selectedTenantId]);

  const fetchData = async () => {
    setLoading(true);
    setError(null);
    try {
      const headers = buildHeaders();

      const [campaignsRes, enrollmentsRes, settingsRes] = await Promise.all([
        fetch(`${API_BASE}/drip-campaigns`, { headers }),
        fetch(`${API_BASE}/drip-campaigns/enrollments/list?status_filter=active`, { headers }),
        fetch(`${API_BASE}/drip-campaigns/settings`, { headers }),
      ]);

      if (settingsRes.ok) {
        setDripSettings(await settingsRes.json());
      }

      if (campaignsRes.ok) {
        const data = await campaignsRes.json();
        setCampaigns(data);
        setOriginalCampaigns(JSON.parse(JSON.stringify(data)));
      } else if (campaignsRes.status === 404) {
        setCampaigns([]);
        setOriginalCampaigns([]);
      } else {
        const errorData = await campaignsRes.json().catch(() => ({}));
        setError(errorData.detail || 'Failed to load campaign settings');
      }

      if (enrollmentsRes.ok) {
        setEnrollments(await enrollmentsRes.json());
      } else {
        setEnrollments([]);
      }
    } catch (err) {
      setError(err.message || 'Failed to load campaign settings');
    } finally {
      setLoading(false);
    }
  };

  const saveSettings = async () => {
    setSaving(true);
    try {
      const headers = buildHeaders(true);

      for (const campaign of campaigns) {
        // Find the original to see if anything changed
        const original = originalCampaigns.find(c => c.id === campaign.id);
        if (!original || JSON.stringify(campaign) === JSON.stringify(original)) continue;

        // Save campaign-level settings
        const campaignPayload = {
          name: campaign.name,
          campaign_type: campaign.campaign_type || 'custom',
          audience_filter: campaign.audience_filter ?? null,
          tag_filter: campaign.tag_filter ?? null,
          priority: campaign.priority ?? 100,
          is_enabled: campaign.is_enabled,
          trigger_delay_minutes: campaign.trigger_delay_minutes,
          send_window_start: campaign.send_window_start || '08:00',
          send_window_end: campaign.send_window_end || '21:00',
          response_templates: campaign.response_templates,
        };

        const campaignRes = await fetch(`${API_BASE}/drip-campaigns/${campaign.id}`, {
          method: 'PUT',
          headers,
          body: JSON.stringify(campaignPayload),
        });

        if (!campaignRes.ok) {
          const errorData = await campaignRes.json().catch(() => ({}));
          throw new Error(errorData.detail || `Failed to save ${campaign.name}`);
        }

        // Save steps if changed
        if (JSON.stringify(campaign.steps) !== JSON.stringify(original.steps)) {
          const stepsPayload = campaign.steps.map(s => ({
            step_number: s.step_number,
            delay_minutes: s.delay_minutes,
            message_template: s.message_template,
            check_availability: s.check_availability,
            fallback_template: s.fallback_template,
          }));

          const stepsRes = await fetch(`${API_BASE}/drip-campaigns/${campaign.id}/steps`, {
            method: 'PUT',
            headers,
            body: JSON.stringify(stepsPayload),
          });

          if (!stepsRes.ok) {
            const errorData = await stepsRes.json().catch(() => ({}));
            throw new Error(errorData.detail || `Failed to save steps for ${campaign.name}`);
          }
        }
      }

      // Reload data
      const reloadRes = await fetch(`${API_BASE}/drip-campaigns`, { headers: buildHeaders() });
      if (reloadRes.ok) {
        const data = await reloadRes.json();
        setCampaigns(data);
        setOriginalCampaigns(JSON.parse(JSON.stringify(data)));
      }

      showToast('Campaign settings saved successfully');
    } catch (err) {
      showToast(err.message || 'Failed to save settings', 'error');
    } finally {
      setSaving(false);
    }
  };

  const handleCancel = () => {
    setCampaigns(JSON.parse(JSON.stringify(originalCampaigns)));
  };

  const updateCampaign = (campaignId, key, value) => {
    setCampaigns(prev =>
      prev.map(c => c.id === campaignId ? { ...c, [key]: value } : c)
    );
  };

  const updateStep = (campaignId, stepNumber, key, value) => {
    setCampaigns(prev =>
      prev.map(c => {
        if (c.id !== campaignId) return c;
        return {
          ...c,
          steps: c.steps.map(s =>
            s.step_number === stepNumber ? { ...s, [key]: value } : s
          ),
        };
      })
    );
  };

  const updateResponseTemplate = (campaignId, category, key, value) => {
    setCampaigns(prev =>
      prev.map(c => {
        if (c.id !== campaignId) return c;
        const templates = { ...(c.response_templates || {}) };
        templates[category] = { ...(templates[category] || {}), [key]: value };
        return { ...c, response_templates: templates };
      })
    );
  };

  const toggleSection = (key) => {
    setExpandedSections(prev => ({ ...prev, [key]: !prev[key] }));
  };

  const createCampaign = async () => {
    setCreateError(null);
    if (!newCampaignDraft.name.trim()) {
      setCreateError('Name is required');
      return;
    }
    const requestedAttempts = Math.max(1, parseInt(newCampaignDraft.total_attempts, 10) || 1);
    const cap = dripSettings.max_attempts;
    if (cap != null && requestedAttempts > cap) {
      const bridgeList = (dripSettings.pipeline_bridges || []).join('; ') || '(none)';
      setCreateError(
        `Drip campaigns can only have one message per pipeline bridge ` +
        `(a transition between stages). Your pipeline supports ${cap} ` +
        `bridge${cap === 1 ? '' : 's'}: ${bridgeList}. You requested ` +
        `${requestedAttempts}. Reduce 'Number of attempts' to ${cap}, add more ` +
        `pipeline stages, or turn off "drip affects pipeline" in settings.`
      );
      return;
    }
    setCreating(true);
    try {
      const tagList = newCampaignDraft.match_all_tags
        ? []
        : newCampaignDraft.tag_filter
            .split(',')
            .map(t => t.trim())
            .filter(Boolean);

      const triggerMinutes = toMinutes(
        newCampaignDraft.trigger_delay_value,
        newCampaignDraft.trigger_delay_unit,
      );
      const spacingMinutes = toMinutes(
        newCampaignDraft.spacing_value,
        newCampaignDraft.spacing_unit,
      );
      const attempts = Math.max(1, parseInt(newCampaignDraft.total_attempts, 10) || 1);

      const steps = Array.from({ length: attempts }, (_, i) => ({
        step_number: i + 1,
        delay_minutes: i === 0 ? 0 : spacingMinutes,
        message_template: '',
        check_availability: false,
        fallback_template: null,
      }));

      const payload = {
        name: newCampaignDraft.name.trim(),
        campaign_type: 'custom',
        audience_filter: newCampaignDraft.audience_filter === 'any' ? null : newCampaignDraft.audience_filter,
        tag_filter: tagList.length ? tagList : null,
        priority: 100,
        trigger_delay_minutes: triggerMinutes,
        is_enabled: false,
        steps,
      };
      const res = await fetch(`${API_BASE}/drip-campaigns`, {
        method: 'POST',
        headers: buildHeaders(true),
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        const detail = errorData.detail || 'Failed to create campaign';
        setCreateError(detail);
        throw new Error(detail);
      }
      setShowCreateModal(false);
      setNewCampaignDraft({
        name: '',
        audience_filter: 'any',
        match_all_tags: true,
        tag_filter: '',
        trigger_delay_value: 10,
        trigger_delay_unit: 'minutes',
        total_attempts: 3,
        spacing_value: 1,
        spacing_unit: 'days',
      });
      showToast('Campaign created — fill in the message templates and enable when ready');
      await fetchData();
    } catch (err) {
      showToast(err.message || 'Failed to create campaign', 'error');
    } finally {
      setCreating(false);
    }
  };

  const deleteCampaign = async (campaignId, campaignName) => {
    if (!window.confirm(`Delete "${campaignName}"? This will cancel any active enrollments.`)) {
      return;
    }
    setDeletingId(campaignId);
    try {
      const res = await fetch(`${API_BASE}/drip-campaigns/${campaignId}`, {
        method: 'DELETE',
        headers: buildHeaders(),
      });
      if (!res.ok && res.status !== 204) {
        const errorData = await res.json().catch(() => ({}));
        throw new Error(errorData.detail || 'Failed to delete campaign');
      }
      showToast('Campaign deleted');
      await fetchData();
    } catch (err) {
      showToast(err.message || 'Failed to delete campaign', 'error');
    } finally {
      setDeletingId(null);
    }
  };

  const updateDripSetting = async (key, value) => {
    const previous = { ...dripSettings };
    setDripSettings({ ...dripSettings, [key]: value });
    setSavingSettings(true);
    try {
      const res = await fetch(`${API_BASE}/drip-campaigns/settings`, {
        method: 'PUT',
        headers: buildHeaders(true),
        body: JSON.stringify({ [key]: value }),
      });
      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        throw new Error(errorData.detail || 'Failed to save setting');
      }
      const updated = await res.json();
      setDripSettings(updated);
      showToast('Setting saved');
    } catch (err) {
      setDripSettings(previous);
      showToast(err.message || 'Failed to save setting', 'error');
    } finally {
      setSavingSettings(false);
    }
  };

  const cancelEnrollment = async (enrollmentId) => {
    setCancellingId(enrollmentId);
    try {
      const res = await fetch(`${API_BASE}/drip-campaigns/enrollments/${enrollmentId}/cancel`, {
        method: 'POST',
        headers: buildHeaders(true),
      });
      if (res.ok) {
        setEnrollments(prev => prev.filter(e => e.id !== enrollmentId));
        showToast('Enrollment cancelled');
      } else {
        const errorData = await res.json().catch(() => ({}));
        showToast(errorData.detail || 'Failed to cancel enrollment', 'error');
      }
    } catch {
      showToast('Network error', 'error');
    } finally {
      setCancellingId(null);
    }
  };

  // ── Guards ─────────────────────────────────────────────────────────────

  const needsTenant = user?.is_global_admin && !selectedTenantId;

  if (needsTenant) {
    return (
      <div className="campaign-page">
        <EmptyState
          icon="SMS"
          title="Select a tenant to manage campaign settings"
          description="Please select a tenant from the dropdown above."
        />
      </div>
    );
  }

  if (loading) {
    return (
      <div className="campaign-page">
        <LoadingState message="Loading campaign settings..." fullPage />
      </div>
    );
  }

  if (error) {
    if (error.includes('Tenant context')) {
      return (
        <div className="campaign-page">
          <EmptyState
            icon="SMS"
            title="Select a tenant to manage campaign settings"
            description="Please select a tenant from the dropdown above."
          />
        </div>
      );
    }
    return (
      <div className="campaign-page">
        <ErrorState message={error} onRetry={fetchData} />
      </div>
    );
  }

  // ── Render ─────────────────────────────────────────────────────────────

  return (
    <div className="campaign-page">
      {/* Sticky Save Bar */}
      <div className={`sms-save-bar ${isDirty ? 'sms-save-bar--visible' : ''}`}>
        <div className="sms-save-bar__content">
          <span className="sms-save-bar__text">You have unsaved changes</span>
          <div className="sms-save-bar__actions">
            <button
              type="button"
              className="sms-btn sms-btn--ghost"
              onClick={handleCancel}
              disabled={saving}
            >
              Cancel
            </button>
            <button
              type="button"
              className="sms-btn sms-btn--primary"
              onClick={saveSettings}
              disabled={saving}
            >
              {saving ? 'Saving...' : 'Save Changes'}
            </button>
          </div>
        </div>
      </div>

      {/* Toast */}
      {toast && (
        <div className={`sms-toast sms-toast--${toast.type}`}>
          {toast.type === 'success' ? '\u2713' : '!'} {toast.message}
        </div>
      )}

      {/* Header */}
      <header className="sms-header">
        <h1 className="sms-header__title">Drip Campaigns</h1>
        <p className="sms-header__subtitle">
          {isSimple
            ? 'Toggle a campaign on and every new lead gets enrolled until they reply STOP, become a customer, or finish all messages.'
            : 'Manage automated follow-up sequences for new leads. Each campaign can target leads by audience and tags.'}
        </p>
        <div
          style={{
            marginTop: '12px',
            display: 'inline-flex',
            border: '1px solid #d1d5db',
            borderRadius: '8px',
            overflow: 'hidden',
          }}
        >
          <button
            type="button"
            className="sms-btn"
            style={{
              borderRadius: 0,
              background: viewMode === 'simple' ? '#4f46e5' : '#fff',
              color: viewMode === 'simple' ? '#fff' : '#374151',
              border: 'none',
            }}
            onClick={() => setViewModePersistent('simple')}
          >
            Simple
          </button>
          <button
            type="button"
            className="sms-btn"
            style={{
              borderRadius: 0,
              background: viewMode === 'advanced' ? '#4f46e5' : '#fff',
              color: viewMode === 'advanced' ? '#fff' : '#374151',
              border: 'none',
            }}
            onClick={() => setViewModePersistent('advanced')}
          >
            Advanced
          </button>
        </div>
        {isSimple && (
          <div
            style={{
              marginTop: '12px',
              padding: '12px 14px',
              background: '#fef3c7',
              border: '1px solid #fde68a',
              borderRadius: '8px',
              fontSize: '13px',
              color: '#92400e',
            }}
          >
            Auto-enrollment is OFF by default. To start enrolling new leads, set
            <code style={{ margin: '0 4px' }}>auto_enroll_new_leads = true</code>
            on this tenant's <code>tenant_business_profiles</code> row. Flip back to
            <code style={{ margin: '0 4px' }}>false</code> to stop.
          </div>
        )}
        <div style={{ marginTop: '12px' }}>
          <button
            type="button"
            className="sms-btn sms-btn--primary"
            onClick={() => setShowCreateModal(true)}
          >
            + New Campaign
          </button>
        </div>
      </header>

      <div className="sms-cards">
        {/* ── Drip Behavior Settings ───────────────────────────────────── */}
        <section className="sms-card">
          <div className="sms-card__header">
            <h2 className="sms-card__title">Drip Behavior</h2>
          </div>
          <div className="sms-card__body">
            <div className="sms-field sms-field--toggle">
              <label className="sms-toggle" htmlFor="drip-affects-pipeline">
                <input
                  id="drip-affects-pipeline"
                  type="checkbox"
                  checked={dripSettings.drip_affects_pipeline}
                  onChange={(e) => updateDripSetting('drip_affects_pipeline', e.target.checked)}
                  disabled={savingSettings}
                  className="sms-toggle__input"
                />
                <span className="sms-toggle__switch" />
                <span className="sms-toggle__label">
                  Drip campaigns advance pipeline stages
                </span>
              </label>
              <p className="sms-field__hint" style={{ marginTop: '8px' }}>
                When on (default), each drip step advances the lead's pipeline stage by one position. The final step uses the customer-match rule: enrolled if matched, missed otherwise. Turn off if this tenant doesn't use a kanban pipeline or wants stages to be human-managed only.
              </p>
            </div>
          </div>
        </section>

        {/* ── Campaign Cards ───────────────────────────────────────────── */}
        {campaigns.length === 0 && (
          <section className="sms-card">
            <div className="sms-card__body">
              <EmptyState
                icon="SMS"
                title="No campaigns configured"
                description="Drip campaigns haven't been set up for this tenant yet."
              />
            </div>
          </section>
        )}

        {campaigns.map((campaign) => (
          <section key={campaign.id} className="sms-card">
            <div className="sms-card__header">
              <h2 className="sms-card__title">{campaign.name}</h2>
              <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                <span className={`sms-card__badge ${campaign.is_enabled ? 'sms-card__badge--new' : ''}`}>
                  {campaign.is_enabled ? 'ACTIVE' : 'OFF'}
                </span>
                <button
                  type="button"
                  className="sms-btn sms-btn--ghost campaign-btn--sm"
                  onClick={() => deleteCampaign(campaign.id, campaign.name)}
                  disabled={deletingId === campaign.id}
                  style={{ color: '#b91c1c' }}
                >
                  {deletingId === campaign.id ? 'Deleting...' : 'Delete'}
                </button>
              </div>
            </div>
            <div className="sms-card__body">
              {/* Enable Toggle */}
              <div className="sms-field sms-field--toggle">
                <label className="sms-toggle" htmlFor={`campaign-enabled-${campaign.id}`}>
                  <input
                    id={`campaign-enabled-${campaign.id}`}
                    type="checkbox"
                    checked={campaign.is_enabled}
                    onChange={(e) => updateCampaign(campaign.id, 'is_enabled', e.target.checked)}
                    className="sms-toggle__input"
                  />
                  <span className="sms-toggle__switch" />
                  <span className="sms-toggle__label">Enable {campaign.name}</span>
                </label>
              </div>

              {/* Campaign Name */}
              <div className="sms-field">
                <label className="sms-field__label">Campaign Name</label>
                <input
                  type="text"
                  className="sms-input"
                  value={campaign.name}
                  onChange={(e) => updateCampaign(campaign.id, 'name', e.target.value)}
                />
              </div>

              {/* Audience Filter — routing control, always visible */}
              <div className="sms-field">
                <label className="sms-field__label">Audience</label>
                <select
                  className="sms-input"
                  value={campaign.audience_filter || 'any'}
                  onChange={(e) =>
                    updateCampaign(campaign.id, 'audience_filter', e.target.value === 'any' ? null : e.target.value)
                  }
                >
                  <option value="any">Any audience</option>
                  <option value="adult">Adult</option>
                  <option value="child">Child (any age)</option>
                  <option value="under_3">Child — under 3</option>
                </select>
                <p className="sms-field__hint">
                  Only leads matching this audience enter this campaign. Auto-detected from the lead's qualifying-question answer, class, or ad source.
                </p>
              </div>

              {/* Tag Filter — routing control, always visible */}
              {(() => {
                const matchAll = campaign.tag_filter == null;
                return (
                  <div className="sms-field">
                    <label className="sms-field__label">Required Tags</label>
                    <div className="sms-field sms-field--toggle" style={{ marginBottom: '8px' }}>
                      <label className="sms-toggle" htmlFor={`match-all-tags-${campaign.id}`}>
                        <input
                          id={`match-all-tags-${campaign.id}`}
                          type="checkbox"
                          checked={matchAll}
                          onChange={(e) => {
                            updateCampaign(
                              campaign.id,
                              'tag_filter',
                              e.target.checked ? null : (campaign.tag_filter || []),
                            );
                          }}
                          className="sms-toggle__input"
                        />
                        <span className="sms-toggle__switch" />
                        <span className="sms-toggle__label">Match all leads (no tag filter)</span>
                      </label>
                    </div>
                    {!matchAll && (
                      <>
                        <input
                          type="text"
                          className="sms-input"
                          value={(campaign.tag_filter || []).join(', ')}
                          onChange={(e) => {
                            const list = e.target.value
                              .split(',')
                              .map(t => t.trim())
                              .filter(Boolean);
                            updateCampaign(campaign.id, 'tag_filter', list);
                          }}
                          placeholder="e.g. Meta IG, Starfish (comma-separated)"
                        />
                        <p className="sms-field__hint">
                          Lead must have ALL listed tags. Matches both auto-derived tags (location, class, source) and manual tags.
                        </p>
                      </>
                    )}
                  </div>
                );
              })()}

              {/* Trigger Delay + Send Window (side-by-side) */}
              {(() => {
                const split = splitMinutes(campaign.trigger_delay_minutes);
                const winStart = campaign.send_window_start || '08:00';
                const winEnd = campaign.send_window_end || '21:00';
                return (
                  <div style={{ display: 'flex', gap: '24px', flexWrap: 'wrap', alignItems: 'flex-start' }}>
                    <div className="sms-field" style={{ flex: '1 1 220px', minWidth: '220px' }}>
                      <label className="sms-field__label">First message after</label>
                      <div className="sms-input-group">
                        <input
                          type="number"
                          className="sms-input sms-input--number"
                          min="0"
                          value={split.value}
                          onChange={(e) =>
                            updateCampaign(
                              campaign.id,
                              'trigger_delay_minutes',
                              toMinutes(e.target.value, split.unit),
                            )
                          }
                        />
                        <select
                          className="sms-input"
                          style={{ maxWidth: '120px' }}
                          value={split.unit}
                          onChange={(e) =>
                            updateCampaign(
                              campaign.id,
                              'trigger_delay_minutes',
                              toMinutes(split.value, e.target.value),
                            )
                          }
                        >
                          <option value="minutes">minutes</option>
                          <option value="hours">hours</option>
                          <option value="days">days</option>
                        </select>
                      </div>
                      <p className="sms-field__hint">
                        How long to wait after a lead arrives before sending the first message.
                      </p>
                    </div>

                    <div className="sms-field" style={{ flex: '1 1 260px', minWidth: '260px' }}>
                      <label className="sms-field__label">Send window (tenant timezone)</label>
                      <div className="sms-input-group" style={{ alignItems: 'center' }}>
                        <input
                          type="time"
                          className="sms-input"
                          min="07:00"
                          max="22:00"
                          step="900"
                          value={winStart}
                          onChange={(e) =>
                            updateCampaign(campaign.id, 'send_window_start', e.target.value)
                          }
                          style={{ maxWidth: '120px' }}
                        />
                        <span style={{ color: '#6b7280' }}>to</span>
                        <input
                          type="time"
                          className="sms-input"
                          min="07:00"
                          max="22:00"
                          step="900"
                          value={winEnd}
                          onChange={(e) =>
                            updateCampaign(campaign.id, 'send_window_end', e.target.value)
                          }
                          style={{ maxWidth: '120px' }}
                        />
                      </div>
                      <p className="sms-field__hint">
                        Drip steps only fire inside this window (07:00–22:00 max). Anything that lands outside is deferred to the next window-open. Protects leads from late-night texts.
                      </p>
                    </div>
                  </div>
                );
              })()}

              {/* Steps Section */}
              <div className="campaign-section">
                <button
                  type="button"
                  className="campaign-section__toggle"
                  onClick={() => toggleSection(`steps-${campaign.id}`)}
                >
                  <span className="campaign-section__arrow">
                    {expandedSections[`steps-${campaign.id}`] ? '\u25BC' : '\u25B6'}
                  </span>
                  <span className="campaign-section__title">
                    Message Steps ({campaign.steps.length})
                  </span>
                </button>

                {expandedSections[`steps-${campaign.id}`] && (
                  <div className="campaign-steps">
                    {dripSettings.max_attempts != null
                      && campaign.steps.length > dripSettings.max_attempts && (
                      <div
                        role="alert"
                        style={{
                          margin: '8px 0 12px',
                          padding: '10px 12px',
                          borderRadius: 6,
                          background: '#fef2f2',
                          border: '1px solid #fecaca',
                          color: '#991b1b',
                          fontSize: 13,
                          lineHeight: 1.4,
                        }}
                      >
                        This campaign has {campaign.steps.length} steps but your pipeline only
                        supports {dripSettings.max_attempts} bridge{dripSettings.max_attempts === 1 ? '' : 's'}
                        {' '}
                        ({(dripSettings.pipeline_bridges || []).join('; ') || 'none'}).
                        Steps beyond #{dripSettings.max_attempts} have no pipeline transition and won't
                        save when you next edit steps. Trim the campaign or add pipeline stages.
                      </div>
                    )}
                    {[...campaign.steps]
                      .sort((a, b) => a.step_number - b.step_number)
                      .map((step, idx, arr) => {
                        // Step N moves the lead from pipeline position N-1 → N.
                        // Show the transition as "From → To" using the stage labels.
                        // Last step is terminal: lead lands on "missed" (no SMS sent),
                        // unless they've become a customer — then silent enroll.
                        // Outcome stages (enrolled/missed) are externally determined;
                        // auto-advance never sets them on non-last steps, so the
                        // badge holds at the current stage with no arrow.
                        const isLastStep = idx === arr.length - 1;
                        const fromStage = pipelineStages?.[step.step_number - 1];
                        const toStage = pipelineStages?.[step.step_number];
                        const missedStage = stageMap?.missed;
                        const OUTCOME_KEYS = new Set(['enrolled', 'missed']);
                        const targetIsOutcome = toStage && OUTCOME_KEYS.has(toStage.key);
                        let badgeLabel;
                        let badgeColor;
                        if (isLastStep && fromStage) {
                          badgeLabel = `${fromStage.label} → ${missedStage?.label || 'Missed'}`;
                          badgeColor = missedStage?.color || '#6b7280';
                        } else if (fromStage && targetIsOutcome) {
                          badgeLabel = fromStage.label;
                          badgeColor = fromStage.color;
                        } else if (fromStage && toStage) {
                          badgeLabel = `${fromStage.label} → ${toStage.label}`;
                          badgeColor = toStage.color;
                        } else if (toStage && !targetIsOutcome) {
                          badgeLabel = toStage.label;
                          badgeColor = toStage.color;
                        } else {
                          badgeLabel = `Step ${step.step_number}`;
                          badgeColor = null;
                        }
                        // Sample placeholder text per step position.
                        const samplePlaceholder = step.step_number === 1
                          ? "Hi {{first_name}}! Just following up on your interest. Happy to answer any questions whenever works for you."
                          : "Hi {{first_name}}, circling back to see if you have any questions. Reply anytime!";
                        return (
                        <div key={step.step_number} className="campaign-step">
                          <div className="campaign-step__header">
                            <span
                              className="campaign-step__badge"
                              style={badgeColor ? {
                                background: badgeColor,
                                color: '#fff',
                              } : undefined}
                            >
                              {badgeLabel}
                            </span>
                            <span className="campaign-step__delay">
                              {formatDelay(step.delay_minutes)} delay
                            </span>
                          </div>

                          <div className="sms-field">
                            <label className="sms-field__label">Message Template</label>
                            <textarea
                              className="sms-textarea"
                              rows={3}
                              placeholder={samplePlaceholder}
                              value={step.message_template}
                              onChange={(e) =>
                                updateStep(campaign.id, step.step_number, 'message_template', e.target.value)
                              }
                            />
                          </div>

                          {!isSimple && (
                            <div className="sms-field sms-field--toggle">
                              <label className="sms-toggle" htmlFor={`step-avail-${campaign.id}-${step.step_number}`}>
                                <input
                                  id={`step-avail-${campaign.id}-${step.step_number}`}
                                  type="checkbox"
                                  checked={step.check_availability}
                                  onChange={(e) =>
                                    updateStep(campaign.id, step.step_number, 'check_availability', e.target.checked)
                                  }
                                  className="sms-toggle__input"
                                />
                                <span className="sms-toggle__switch" />
                                <span className="sms-toggle__label">Check availability before sending</span>
                              </label>
                            </div>
                          )}

                          {!isSimple && step.check_availability && (
                            <div className="sms-field">
                              <label className="sms-field__label">Fallback Template</label>
                              <textarea
                                className="sms-textarea"
                                rows={2}
                                value={step.fallback_template || ''}
                                onChange={(e) =>
                                  updateStep(campaign.id, step.step_number, 'fallback_template', e.target.value || null)
                                }
                                placeholder="Message to send when no classes are available"
                              />
                              <p className="sms-field__hint">
                                Sent instead of the main template when no availability is found.
                              </p>
                            </div>
                          )}
                        </div>
                        );
                      })}
                  </div>
                )}
              </div>

              {/* Response Templates Section — Advanced only */}
              {!isSimple && campaign.response_templates && Object.keys(campaign.response_templates).length > 0 && (
                <div className="campaign-section">
                  <button
                    type="button"
                    className="campaign-section__toggle"
                    onClick={() => toggleSection(`responses-${campaign.id}`)}
                  >
                    <span className="campaign-section__arrow">
                      {expandedSections[`responses-${campaign.id}`] ? '\u25BC' : '\u25B6'}
                    </span>
                    <span className="campaign-section__title">
                      Response Templates ({Object.keys(campaign.response_templates).length})
                    </span>
                  </button>

                  {expandedSections[`responses-${campaign.id}`] && (
                    <div className="campaign-response-templates">
                      {Object.entries(campaign.response_templates).map(([category, templateData]) => (
                        <div key={category} className="campaign-response-card">
                          <div className="campaign-response-card__header">
                            <span className="campaign-response-card__category">
                              {category.replace(/_/g, ' ')}
                            </span>
                            {templateData.action && (
                              <span className="campaign-response-card__action">
                                {templateData.action}
                              </span>
                            )}
                          </div>

                          {templateData.keywords && templateData.keywords.length > 0 && (
                            <div className="campaign-keywords">
                              {templateData.keywords.map((kw) => (
                                <span key={kw} className="campaign-keyword">{kw}</span>
                              ))}
                            </div>
                          )}

                          <div className="sms-field">
                            <label className="sms-field__label">Reply</label>
                            <textarea
                              className="sms-textarea"
                              rows={2}
                              value={templateData.reply || ''}
                              onChange={(e) =>
                                updateResponseTemplate(campaign.id, category, 'reply', e.target.value)
                              }
                            />
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          </section>
        ))}

        {/* ── Active Drips ──────────────────────────────────────── */}
        <section className="sms-card">
          <div className="sms-card__header">
            <h2 className="sms-card__title">Active Drips</h2>
            <span className="sms-card__badge">
              {enrollments.length}
            </span>
          </div>
          <div className="sms-card__body" style={{ padding: 0 }}>
            {enrollments.length === 0 ? (
              <div className="campaign-enrollments-empty">
                No active enrollments right now.
              </div>
            ) : (
              <div className="campaign-enrollments-table-wrapper">
                <table className="campaign-enrollments-table">
                  <thead>
                    <tr>
                      <th>Lead</th>
                      <th>Phone</th>
                      <th>Campaign</th>
                      <th>Step</th>
                      <th>Status</th>
                      <th>Next Message</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {enrollments.map((enrollment) => (
                      <tr key={enrollment.id}>
                        <td className="campaign-enrollments-table__name">
                          {enrollment.lead_name || `Lead #${enrollment.lead_id}`}
                        </td>
                        <td className="campaign-enrollments-table__phone">
                          {enrollment.lead_phone || '—'}
                        </td>
                        <td>
                          <span className="campaign-enrollments-table__campaign">
                            {enrollment.campaign_name || enrollment.campaign_type || '—'}
                          </span>
                        </td>
                        <td>
                          <span className="campaign-enrollments-table__step">
                            {enrollment.current_step}/{enrollment.total_steps}
                          </span>
                        </td>
                        <td>
                          <span className={`sms-status-badge ${STATUS_COLORS[enrollment.status] || ''}`}>
                            {enrollment.status}
                          </span>
                        </td>
                        <td className="campaign-enrollments-table__date">
                          {formatDateTime(enrollment.next_step_at)}
                        </td>
                        <td>
                          {enrollment.status === 'active' && (
                            <button
                              type="button"
                              className="sms-btn sms-btn--secondary campaign-btn--sm"
                              onClick={() => cancelEnrollment(enrollment.id)}
                              disabled={cancellingId === enrollment.id}
                            >
                              {cancellingId === enrollment.id ? 'Cancelling...' : 'Cancel'}
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </section>
      </div>

      {/* Bottom Save Button */}
      <div className="sms-actions">
        <button
          type="button"
          className="sms-btn sms-btn--primary sms-btn--lg"
          onClick={saveSettings}
          disabled={saving || !isDirty}
        >
          {saving ? 'Saving...' : 'Save Settings'}
        </button>
      </div>

      {/* Create Campaign Modal */}
      {showCreateModal && (
        <div
          className="sms-modal-backdrop"
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,0.5)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
          }}
          onClick={() => !creating && (setShowCreateModal(false), setCreateError(null))}
        >
          <div
            className="sms-card"
            style={{ maxWidth: '520px', width: '90%' }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="sms-card__header">
              <h2 className="sms-card__title">New Drip Campaign</h2>
            </div>
            <div className="sms-card__body">
              <div className="sms-field">
                <label className="sms-field__label">Name</label>
                <input
                  type="text"
                  className="sms-input"
                  value={newCampaignDraft.name}
                  onChange={(e) => setNewCampaignDraft(d => ({ ...d, name: e.target.value }))}
                  placeholder="e.g. Meta IG — Adult Lessons"
                  autoFocus
                />
              </div>

              <div className="sms-field">
                <label className="sms-field__label">Audience</label>
                <select
                  className="sms-input"
                  value={newCampaignDraft.audience_filter}
                  onChange={(e) => setNewCampaignDraft(d => ({ ...d, audience_filter: e.target.value }))}
                >
                  <option value="any">Any audience</option>
                  <option value="adult">Adult</option>
                  <option value="child">Child (any age)</option>
                  <option value="under_3">Child — under 3</option>
                </select>
                <p className="sms-field__hint">
                  Only leads matching this audience enter this campaign.
                </p>
              </div>

              <div className="sms-field">
                <label className="sms-field__label">Required Tags</label>
                <div className="sms-field sms-field--toggle" style={{ marginBottom: '8px' }}>
                  <label className="sms-toggle" htmlFor="new-match-all-tags">
                    <input
                      id="new-match-all-tags"
                      type="checkbox"
                      checked={newCampaignDraft.match_all_tags}
                      onChange={(e) =>
                        setNewCampaignDraft(d => ({ ...d, match_all_tags: e.target.checked }))
                      }
                      className="sms-toggle__input"
                    />
                    <span className="sms-toggle__switch" />
                    <span className="sms-toggle__label">Match all leads (no tag filter)</span>
                  </label>
                </div>
                {!newCampaignDraft.match_all_tags && (
                  <input
                    type="text"
                    className="sms-input"
                    value={newCampaignDraft.tag_filter}
                    onChange={(e) => setNewCampaignDraft(d => ({ ...d, tag_filter: e.target.value }))}
                    placeholder="comma-separated, e.g. Meta IG, Starfish"
                  />
                )}
              </div>

              <div className="sms-field">
                <label className="sms-field__label">First message after</label>
                <div className="sms-input-group">
                  <input
                    type="number"
                    className="sms-input sms-input--number"
                    min="0"
                    value={newCampaignDraft.trigger_delay_value}
                    onChange={(e) =>
                      setNewCampaignDraft(d => ({ ...d, trigger_delay_value: e.target.value }))
                    }
                  />
                  <select
                    className="sms-input"
                    style={{ maxWidth: '120px' }}
                    value={newCampaignDraft.trigger_delay_unit}
                    onChange={(e) =>
                      setNewCampaignDraft(d => ({ ...d, trigger_delay_unit: e.target.value }))
                    }
                  >
                    <option value="minutes">minutes</option>
                    <option value="hours">hours</option>
                    <option value="days">days</option>
                  </select>
                </div>
                <p className="sms-field__hint">How long to wait after a lead arrives before the first message.</p>
              </div>

              <div className="sms-field">
                <label className="sms-field__label">Number of attempts</label>
                <input
                  type="number"
                  className="sms-input sms-input--number"
                  min="1"
                  max={dripSettings.max_attempts ?? 20}
                  value={newCampaignDraft.total_attempts}
                  onChange={(e) => {
                    const cap = dripSettings.max_attempts ?? 20;
                    const raw = parseInt(e.target.value, 10);
                    const clamped = Number.isFinite(raw)
                      ? Math.max(1, Math.min(cap, raw))
                      : e.target.value;
                    setNewCampaignDraft(d => ({ ...d, total_attempts: clamped }));
                    setCreateError(null);
                  }}
                />
                <p className="sms-field__hint">
                  {dripSettings.max_attempts != null
                    ? `One message per pipeline bridge — capped at ${dripSettings.max_attempts}.`
                    : 'Total messages to send before the campaign completes.'}
                </p>
                {dripSettings.pipeline_bridges?.length > 0 && (
                  <div className="sms-field__hint" style={{ marginTop: 8 }}>
                    <strong>Bridges this drip will cover:</strong>
                    <ul style={{ margin: '4px 0 0 16px', padding: 0 }}>
                      {dripSettings.pipeline_bridges
                        .slice(0, Math.max(1, parseInt(newCampaignDraft.total_attempts, 10) || 1))
                        .map((b, i) => (
                          <li key={i}>{`Step ${i + 1}: ${b}`}</li>
                        ))}
                    </ul>
                  </div>
                )}
              </div>

              {parseInt(newCampaignDraft.total_attempts, 10) > 1 && (
                <div className="sms-field">
                  <label className="sms-field__label">Time between attempts</label>
                  <div className="sms-input-group">
                    <input
                      type="number"
                      className="sms-input sms-input--number"
                      min="0"
                      value={newCampaignDraft.spacing_value}
                      onChange={(e) =>
                        setNewCampaignDraft(d => ({ ...d, spacing_value: e.target.value }))
                      }
                    />
                    <select
                      className="sms-input"
                      style={{ maxWidth: '120px' }}
                      value={newCampaignDraft.spacing_unit}
                      onChange={(e) =>
                        setNewCampaignDraft(d => ({ ...d, spacing_unit: e.target.value }))
                      }
                    >
                      <option value="minutes">minutes</option>
                      <option value="hours">hours</option>
                      <option value="days">days</option>
                    </select>
                  </div>
                </div>
              )}

              <p className="sms-field__hint" style={{ marginTop: '12px' }}>
                The campaign will be created disabled with empty message templates. Fill them in and enable when ready.
              </p>

              {createError && (
                <div
                  role="alert"
                  style={{
                    marginTop: 12,
                    padding: '10px 12px',
                    borderRadius: 6,
                    background: '#fef2f2',
                    border: '1px solid #fecaca',
                    color: '#991b1b',
                    fontSize: 13,
                    lineHeight: 1.4,
                  }}
                >
                  {createError}
                </div>
              )}
            </div>
            <div className="sms-actions" style={{ padding: '16px 24px', borderTop: '1px solid #e5e7eb', display: 'flex', gap: '8px', justifyContent: 'flex-end' }}>
              <button
                type="button"
                className="sms-btn sms-btn--ghost"
                onClick={() => { setShowCreateModal(false); setCreateError(null); }}
                disabled={creating}
              >
                Cancel
              </button>
              <button
                type="button"
                className="sms-btn sms-btn--primary"
                onClick={createCampaign}
                disabled={creating}
              >
                {creating ? 'Creating...' : 'Create Campaign'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
