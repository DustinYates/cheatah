import { useState, useEffect, useMemo, useCallback } from 'react';
import { useAuth } from '../context/AuthContext';
import { LoadingState, ErrorState, EmptyState } from '../components/ui';
import './CampaignSettings.css';

const API_BASE = '/api/v1';

function formatDelay(minutes) {
  if (minutes < 60) return `${minutes} min`;
  if (minutes < 1440) return `${Math.round(minutes / 60)} hours`;
  return `${Math.round(minutes / 1440)} days`;
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
  const [campaigns, setCampaigns] = useState([]);
  const [originalCampaigns, setOriginalCampaigns] = useState([]);
  const [enrollments, setEnrollments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);
  const [cancellingId, setCancellingId] = useState(null);
  const [toast, setToast] = useState(null);
  const [expandedSections, setExpandedSections] = useState({});

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

      const [campaignsRes, enrollmentsRes] = await Promise.all([
        fetch(`${API_BASE}/drip-campaigns`, { headers }),
        fetch(`${API_BASE}/drip-campaigns/enrollments/list?status_filter=active`, { headers }),
      ]);

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
          is_enabled: campaign.is_enabled,
          trigger_delay_minutes: campaign.trigger_delay_minutes,
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
          Manage automated follow-up sequences for new leads.
        </p>
      </header>

      <div className="sms-cards">
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
              <h2 className="sms-card__title">
                {campaign.campaign_type === 'kids' ? 'Kids' : 'Adults'} Drip Campaign
              </h2>
              <span className={`sms-card__badge ${campaign.is_enabled ? 'sms-card__badge--new' : ''}`}>
                {campaign.is_enabled ? 'ACTIVE' : 'OFF'}
              </span>
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
                  <span className="sms-toggle__label">
                    Enable {campaign.campaign_type === 'kids' ? 'Kids' : 'Adults'} Drip Campaign
                  </span>
                </label>
              </div>

              {/* Trigger Delay */}
              <div className="sms-field">
                <label className="sms-field__label">Trigger Delay</label>
                <div className="sms-input-group">
                  <input
                    type="number"
                    className="sms-input sms-input--number"
                    min="0"
                    max="1440"
                    value={campaign.trigger_delay_minutes}
                    onChange={(e) =>
                      updateCampaign(campaign.id, 'trigger_delay_minutes', parseInt(e.target.value, 10) || 0)
                    }
                  />
                  <span className="sms-input-group__suffix">minutes after enrollment</span>
                </div>
                <p className="sms-field__hint">
                  How long to wait after a lead is enrolled before sending the first message.
                </p>
              </div>

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
                    {campaign.steps
                      .sort((a, b) => a.step_number - b.step_number)
                      .map((step) => (
                        <div key={step.step_number} className="campaign-step">
                          <div className="campaign-step__header">
                            <span className="campaign-step__badge">Step {step.step_number}</span>
                            <span className="campaign-step__delay">
                              {formatDelay(step.delay_minutes)} delay
                            </span>
                          </div>

                          <div className="sms-field">
                            <label className="sms-field__label">Message Template</label>
                            <textarea
                              className="sms-textarea"
                              rows={3}
                              value={step.message_template}
                              onChange={(e) =>
                                updateStep(campaign.id, step.step_number, 'message_template', e.target.value)
                              }
                            />
                          </div>

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

                          {step.check_availability && (
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
                      ))}
                  </div>
                )}
              </div>

              {/* Response Templates Section */}
              {campaign.response_templates && Object.keys(campaign.response_templates).length > 0 && (
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

        {/* ── Active Enrollments ──────────────────────────────────────── */}
        <section className="sms-card">
          <div className="sms-card__header">
            <h2 className="sms-card__title">Active Enrollments</h2>
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
    </div>
  );
}
