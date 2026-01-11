import { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import { LoadingState, ErrorState, EmptyState } from '../components/ui';

const API_BASE = '/api/v1';

const defaultBusinessHours = {
  monday: { start: '09:00', end: '17:00' },
  tuesday: { start: '09:00', end: '17:00' },
  wednesday: { start: '09:00', end: '17:00' },
  thursday: { start: '09:00', end: '17:00' },
  friday: { start: '09:00', end: '17:00' },
  saturday: { start: '', end: '' },
  sunday: { start: '', end: '' },
};

export default function SmsSettings() {
  const { token, user, selectedTenantId } = useAuth();
  const [settings, setSettings] = useState({
    is_enabled: false,
    phone_number: null,
    auto_reply_enabled: false,
    auto_reply_message: '',
    initial_outreach_message: "Hi! Thanks for reaching out. I'm an AI assistant and happy to help answer your questions. What can I help you with today?",
    business_hours_enabled: false,
    timezone: 'America/Chicago',
    business_hours: defaultBusinessHours,
    // Follow-up settings
    followup_enabled: false,
    followup_delay_minutes: 5,
    followup_sources: ['email', 'voice_call', 'sms'],
    followup_initial_message: '',
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState({ type: '', text: '' });

  useEffect(() => {
    fetchSettings();
  }, [token, selectedTenantId]);

  const fetchSettings = async () => {
    setLoading(true);
    setError(null);
    try {
      const headers = { 'Authorization': `Bearer ${token}` };
      if (user?.is_global_admin && selectedTenantId) {
        headers['X-Tenant-Id'] = selectedTenantId.toString();
      }
      const response = await fetch(`${API_BASE}/sms/settings`, {
        headers,
      });
      if (response.ok) {
        const data = await response.json();
        setSettings({
          ...data,
          business_hours: data.business_hours || defaultBusinessHours,
        });
      } else if (response.status === 404) {
        // 404 means no settings exist yet - use defaults (already set in state)
        // Don't set error, just use default values
        setSettings({
          is_enabled: false,
          phone_number: null,
          auto_reply_enabled: false,
          auto_reply_message: '',
          initial_outreach_message: "Hi! Thanks for reaching out. I'm an AI assistant and happy to help answer your questions. What can I help you with today?",
          business_hours_enabled: false,
          timezone: 'America/Chicago',
          business_hours: defaultBusinessHours,
          followup_enabled: false,
          followup_delay_minutes: 5,
          followup_sources: ['email', 'voice_call', 'sms'],
          followup_initial_message: '',
        });
      } else {
        const errorData = await response.json().catch(() => ({}));
        setError(errorData.detail || 'Failed to load SMS settings');
      }
    } catch (error) {
      // Only set error if it's not a "Not Found" type error
      if (error.message?.includes('Not Found') || error.message?.includes('not found')) {
        // Use defaults, don't show error
        setSettings({
          is_enabled: false,
          phone_number: null,
          auto_reply_enabled: false,
          auto_reply_message: '',
          initial_outreach_message: "Hi! Thanks for reaching out. I'm an AI assistant and happy to help answer your questions. What can I help you with today?",
          business_hours_enabled: false,
          timezone: 'America/Chicago',
          business_hours: defaultBusinessHours,
          followup_enabled: false,
          followup_delay_minutes: 5,
          followup_sources: ['email', 'voice_call', 'sms'],
          followup_initial_message: '',
        });
      } else {
        console.error('Error fetching SMS settings:', error);
        setError(error.message || 'Failed to load SMS settings');
      }
    } finally {
      setLoading(false);
    }
  };

  const saveSettings = async () => {
    setSaving(true);
    setMessage({ type: '', text: '' });

    try {
      const headers = {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
      };
      if (user?.is_global_admin && selectedTenantId) {
        headers['X-Tenant-Id'] = selectedTenantId.toString();
      }
      const response = await fetch(`${API_BASE}/sms/settings`, {
        method: 'PUT',
        headers,
        body: JSON.stringify({
          is_enabled: settings.is_enabled,
          auto_reply_enabled: settings.auto_reply_enabled,
          auto_reply_message: settings.auto_reply_message,
          initial_outreach_message: settings.initial_outreach_message,
          business_hours_enabled: settings.business_hours_enabled,
          timezone: settings.timezone,
          business_hours: settings.business_hours,
          followup_enabled: settings.followup_enabled,
          followup_delay_minutes: settings.followup_delay_minutes,
          followup_sources: settings.followup_sources,
          followup_initial_message: settings.followup_initial_message,
        }),
      });

      if (response.ok) {
        const data = await response.json();
        setSettings({
          ...data,
          business_hours: data.business_hours || defaultBusinessHours,
        });
        setMessage({ type: 'success', text: 'Settings saved successfully!' });
      } else {
        const errorData = await response.json();
        setMessage({ type: 'error', text: errorData.detail || 'Failed to save settings' });
      }
    } catch {
      setMessage({ type: 'error', text: 'Network error. Please try again.' });
    } finally {
      setSaving(false);
    }
  };


  // Check if global admin without tenant selected
  const needsTenant = user?.is_global_admin && !selectedTenantId;

  if (needsTenant) {
    return (
      <div className="page-container sms-settings">
        <EmptyState
          icon="📱"
          title="Select a tenant to manage SMS settings"
          description="Please select a tenant from the dropdown above to manage their SMS settings."
        />
      </div>
    );
  }

  if (loading) {
    return (
      <div className="page-container sms-settings">
        <LoadingState message="Loading SMS settings..." fullPage />
      </div>
    );
  }

  if (error) {
    // Check if error is about tenant context
    if (error.includes('Tenant context required') || error.includes('Tenant context')) {
      return (
        <div className="page-container sms-settings">
          <EmptyState
            icon="📱"
            title="Select a tenant to manage SMS settings"
            description="Please select a tenant from the dropdown above to manage their SMS settings."
          />
        </div>
      );
    }
    // Don't show error for "Not Found" - we already handled it in fetchSettings
    // Only show error for actual failures
    if (!error.includes('Not Found') && !error.includes('not found')) {
      return (
        <div className="page-container sms-settings">
          <ErrorState message={error} onRetry={fetchSettings} />
        </div>
      );
    }
    // If it was a "Not Found", continue to render the form with defaults
  }

  const updateBusinessHours = (day, field, value) => {
    setSettings((prev) => ({
      ...prev,
      business_hours: {
        ...prev.business_hours,
        [day]: {
          ...prev.business_hours?.[day],
          [field]: value,
        },
      },
    }));
  };

  const dayLabels = [
    { key: 'monday', label: 'Monday' },
    { key: 'tuesday', label: 'Tuesday' },
    { key: 'wednesday', label: 'Wednesday' },
    { key: 'thursday', label: 'Thursday' },
    { key: 'friday', label: 'Friday' },
    { key: 'saturday', label: 'Saturday' },
    { key: 'sunday', label: 'Sunday' },
  ];
  const smsEnabled = settings.is_enabled && !!settings.phone_number;
  const messagingDisabled = !smsEnabled;
  const afterHoursDisabled = messagingDisabled || !settings.business_hours_enabled;

  return (
    <div className="page-container sms-settings">
      <div className="page-header">
        <span className="page-title">SMS Settings</span>
      </div>

      {message.text && (
        <div className={`alert ${message.type === 'error' ? 'alert-error' : 'alert-success'}`}>
          {message.text}
        </div>
      )}

      <div className="card primary-card">
        <div className="section">
          <div className="section-header">
            <div>
              <div className="section-title">SMS Status</div>
              <p className="section-subtitle">Confirm your assigned number and master SMS switch.</p>
            </div>
          </div>
          <div className="section-body">
            <div className="form-grid">
              <div className="form-row">
                <span className="form-label">Assigned number</span>
                <div className="form-control">
                  {settings.phone_number ? (
                    <div className="inline-status active">
                      <span className="phone-number">{settings.phone_number}</span>
                      <span className="status-dot" aria-hidden="true"></span>
                      <span className="status-label">Assigned</span>
                    </div>
                  ) : (
                    <div className="inline-status inactive">
                      <span className="status-dot" aria-hidden="true"></span>
                      <span className="status-label">Not Assigned</span>
                    </div>
                  )}
                </div>
              </div>
              {!settings.phone_number && (
                <div className="help-text tight">Contact support to assign a phone number.</div>
              )}

              <div className="form-row">
                <label className="form-label" htmlFor="sms-enabled">
                  SMS Enabled
                </label>
                <div className="form-control">
                  <input
                    id="sms-enabled"
                    type="checkbox"
                    checked={settings.is_enabled}
                    onChange={(e) => setSettings({ ...settings, is_enabled: e.target.checked })}
                    disabled={!settings.phone_number}
                    title={
                      settings.phone_number
                        ? 'Enable or disable SMS sending for this tenant.'
                        : 'Assign a phone number to enable SMS.'
                    }
                  />
                </div>
              </div>
              {!settings.phone_number && (
                <div className="help-text tight">Assign a phone number to enable SMS.</div>
              )}
            </div>
          </div>
        </div>

        <div className="section-divider"></div>

        <div className={`section ${messagingDisabled ? 'section-disabled' : ''}`}>
          <div className="section-header">
            <div>
              <div className="section-title">Messaging Behavior</div>
              <p className="section-subtitle">Define when the system responds automatically.</p>
            </div>
            {messagingDisabled && <span className="section-status">SMS Off</span>}
          </div>
          <fieldset className="section-body" disabled={messagingDisabled}>
            <div className="subsection">
              <div className="subsection-title">Business Hours</div>
              <div className="form-grid">
                <div className="form-row">
                  <label className="form-label" htmlFor="business-hours-enabled">
                    Respect business hours
                  </label>
                  <div className="form-control">
                    <input
                      id="business-hours-enabled"
                      type="checkbox"
                      checked={settings.business_hours_enabled}
                      onChange={(e) => setSettings({ ...settings, business_hours_enabled: e.target.checked })}
                      title="Enforce responses during the hours below."
                    />
                  </div>
                </div>

                {settings.business_hours_enabled && (
                  <>
                    <div className="inline-note">
                      Messages outside business hours will use the after-hours behavior below.
                    </div>
                    <div className="form-row">
                      <label className="form-label" htmlFor="sms-timezone">
                        Timezone
                      </label>
                      <div className="form-control">
                        <select
                          id="sms-timezone"
                          value={settings.timezone}
                          onChange={(e) => setSettings({ ...settings, timezone: e.target.value })}
                        >
                          <option value="America/New_York">Eastern Time</option>
                          <option value="America/Chicago">Central Time</option>
                          <option value="America/Denver">Mountain Time</option>
                          <option value="America/Los_Angeles">Pacific Time</option>
                        </select>
                      </div>
                    </div>

                    <div className="form-row form-row-top">
                      <span className="form-label">Hours</span>
                      <div className="form-control">
                        <div className="hours-grid">
                          {dayLabels.map((day) => {
                            const range = settings.business_hours?.[day.key] || { start: '', end: '' };
                            return (
                              <div key={day.key} className="hours-row">
                                <div className="hours-day">{day.label}</div>
                                <div className="hours-time">
                                  <input
                                    type="time"
                                    value={range.start || ''}
                                    onChange={(e) => updateBusinessHours(day.key, 'start', e.target.value)}
                                    aria-label={`${day.label} start time`}
                                  />
                                  <span className="hours-sep">to</span>
                                  <input
                                    type="time"
                                    value={range.end || ''}
                                    onChange={(e) => updateBusinessHours(day.key, 'end', e.target.value)}
                                    aria-label={`${day.label} end time`}
                                  />
                                </div>
                              </div>
                            );
                          })}
                        </div>
                        <div className="help-text tight">Leave a day blank to mark it as closed.</div>
                      </div>
                    </div>
                  </>
                )}
              </div>
            </div>

            <div className="subsection-divider"></div>

            <div className={`subsection ${afterHoursDisabled ? 'subsection-disabled' : ''}`}>
              <div className="subsection-title">After-Hours Message</div>
              {!settings.business_hours_enabled && !messagingDisabled && (
                <div className="inline-note">Enable Business Hours to send after-hours messages.</div>
              )}
              <fieldset className="subsection-body" disabled={afterHoursDisabled}>
                <div className="form-grid">
                  <div className="form-row">
                    <label className="form-label" htmlFor="after-hours-enabled">
                      Send after-hours SMS
                    </label>
                    <div className="form-control">
                      <input
                        id="after-hours-enabled"
                        type="checkbox"
                        checked={settings.auto_reply_enabled}
                        onChange={(e) => setSettings({ ...settings, auto_reply_enabled: e.target.checked })}
                        title="Send a reply when messages arrive outside business hours."
                      />
                    </div>
                  </div>

                  {settings.auto_reply_enabled && !afterHoursDisabled && (
                    <div className="form-row form-row-top">
                      <label className="form-label" htmlFor="after-hours-message">
                        After-Hours Message
                      </label>
                      <div className="form-control">
                        <textarea
                          id="after-hours-message"
                          className="textarea-compact textarea-short"
                          value={settings.auto_reply_message || ''}
                          onChange={(e) => setSettings({ ...settings, auto_reply_message: e.target.value })}
                          placeholder="We're currently outside business hours. We'll respond when we're back."
                          rows={2}
                        />
                      </div>
                    </div>
                  )}
                </div>
              </fieldset>
            </div>
          </fieldset>
        </div>

        <div className="section-divider"></div>

        <div className={`section ${messagingDisabled ? 'section-disabled' : ''}`}>
          <div className="section-header">
            <div>
              <div className="section-title">Follow-Up Automation</div>
              <p className="section-subtitle">Send a follow-up if someone does not reply.</p>
            </div>
            {messagingDisabled && <span className="section-status">SMS Off</span>}
          </div>
          <fieldset className="section-body" disabled={messagingDisabled}>
            <div className="form-grid">
              <div className="form-row">
                <label className="form-label" htmlFor="followup-enabled">
                  Send follow-up SMS
                </label>
                <div className="form-control">
                  <input
                    id="followup-enabled"
                    type="checkbox"
                    checked={settings.followup_enabled}
                    onChange={(e) => setSettings({ ...settings, followup_enabled: e.target.checked })}
                    title="Send a follow-up text for new leads."
                  />
                </div>
              </div>

              {settings.followup_enabled && !messagingDisabled && (
                <>
                  <div className="inline-note">
                    Sent if the lead does not reply within the delay window.
                  </div>
                  <div className="form-row">
                    <label className="form-label" htmlFor="followup-delay">
                      Follow-Up Delay (minutes)
                    </label>
                    <div className="form-control">
                      <input
                        id="followup-delay"
                        type="number"
                        min="1"
                        max="60"
                        value={settings.followup_delay_minutes}
                        onChange={(e) =>
                          setSettings({
                            ...settings,
                            followup_delay_minutes: parseInt(e.target.value) || 5,
                          })
                        }
                      />
                    </div>
                  </div>

                  <div className="form-row form-row-top">
                    <span className="form-label">Lead sources</span>
                    <div className="form-control">
                      <div className="checkbox-grid">
                        <label className="checkbox-label">
                          <input
                            type="checkbox"
                            checked={settings.followup_sources?.includes('email')}
                            onChange={(e) => {
                              const sources = settings.followup_sources || [];
                              if (e.target.checked) {
                                setSettings({ ...settings, followup_sources: [...sources, 'email'] });
                              } else {
                                setSettings({ ...settings, followup_sources: sources.filter(s => s !== 'email') });
                              }
                            }}
                          />
                          Email
                        </label>
                        <label className="checkbox-label">
                          <input
                            type="checkbox"
                            checked={settings.followup_sources?.includes('voice_call')}
                            onChange={(e) => {
                              const sources = settings.followup_sources || [];
                              if (e.target.checked) {
                                setSettings({ ...settings, followup_sources: [...sources, 'voice_call'] });
                              } else {
                                setSettings({ ...settings, followup_sources: sources.filter(s => s !== 'voice_call') });
                              }
                            }}
                          />
                          Calls
                        </label>
                        <label className="checkbox-label">
                          <input
                            type="checkbox"
                            checked={settings.followup_sources?.includes('sms')}
                            onChange={(e) => {
                              const sources = settings.followup_sources || [];
                              if (e.target.checked) {
                                setSettings({ ...settings, followup_sources: [...sources, 'sms'] });
                              } else {
                                setSettings({ ...settings, followup_sources: sources.filter(s => s !== 'sms') });
                              }
                            }}
                          />
                          SMS
                        </label>
                      </div>
                    </div>
                  </div>

                  <div className="form-row form-row-top">
                    <label className="form-label" htmlFor="followup-message">
                      Follow-Up SMS Content
                    </label>
                    <div className="form-control">
                      <textarea
                        id="followup-message"
                        className="textarea-compact textarea-short"
                        value={settings.followup_initial_message || ''}
                        onChange={(e) => setSettings({ ...settings, followup_initial_message: e.target.value })}
                        placeholder="Leave empty for AI-generated follow-up. Use {name} or {first_name}."
                        rows={2}
                      />
                    </div>
                  </div>
                </>
              )}
            </div>
          </fieldset>
        </div>

        <div className="section-divider"></div>

        <div className={`section ${messagingDisabled ? 'section-disabled' : ''}`}>
          <div className="section-header">
            <div>
              <div className="section-title">Settings / Tests</div>
              <p className="section-subtitle">
                Used only when you manually initiate a conversation. Not used for inbound messages or automation.
              </p>
            </div>
            {messagingDisabled && <span className="section-status">SMS Off</span>}
          </div>
          <fieldset className="section-body" disabled={messagingDisabled}>
            <div className="form-grid">
              <div className="form-row form-row-top">
                <label className="form-label" htmlFor="initial-message">
                  Initial message
                </label>
                <div className="form-control">
                  <textarea
                    id="initial-message"
                    className="textarea-compact textarea-short"
                    value={settings.initial_outreach_message || ''}
                    onChange={(e) => setSettings({ ...settings, initial_outreach_message: e.target.value })}
                    placeholder="Hi! Thanks for reaching out..."
                    rows={2}
                  />
                </div>
              </div>
            </div>
          </fieldset>
        </div>
      </div>

      <div className="page-actions">
        <button
          className="btn btn-primary"
          onClick={saveSettings}
          disabled={saving}
          title="Save all SMS settings"
        >
          {saving ? 'Saving...' : 'Save Settings'}
        </button>
      </div>

      <style>{`
        .page-container.sms-settings {
          max-width: 960px;
          margin: 0 auto;
          padding: 1rem 1.25rem 1.5rem;
        }

        .page-header {
          margin-bottom: 0.5rem;
        }

        .page-title {
          font-size: 1rem;
          font-weight: 600;
          color: #1a1a1a;
        }

        .card {
          background: #fff;
          border-radius: 8px;
          padding: 0.7rem;
          margin-bottom: 0.65rem;
          box-shadow: 0 1px 2px rgba(0, 0, 0, 0.08);
        }

        .primary-card {
          display: flex;
          flex-direction: column;
          gap: 0.7rem;
        }

        .section {
          display: flex;
          flex-direction: column;
          gap: 0.45rem;
        }

        .section-header {
          display: flex;
          justify-content: space-between;
          align-items: flex-start;
          gap: 0.75rem;
        }

        .section-title {
          font-size: 0.88rem;
          font-weight: 600;
          color: #2c2c2c;
          margin: 0;
        }

        .section-subtitle {
          margin: 0.15rem 0 0;
          font-size: 0.82rem;
          color: #666;
        }

        .section-status {
          font-size: 0.7rem;
          font-weight: 600;
          letter-spacing: 0.04em;
          text-transform: uppercase;
          color: #666;
          background: #f2f2f2;
          padding: 0.2rem 0.45rem;
          border-radius: 999px;
          align-self: flex-start;
        }

        .section-body,
        .subsection-body {
          border: none;
          padding: 0;
          margin: 0;
          min-width: 0;
        }

        .section-body {
          display: flex;
          flex-direction: column;
          gap: 0.55rem;
        }

        .section-disabled {
          opacity: 0.6;
        }

        .section-divider {
          height: 1px;
          background: #eee;
          margin: 0.3rem 0;
        }

        .subsection {
          display: flex;
          flex-direction: column;
          gap: 0.45rem;
        }

        .subsection-title {
          font-size: 0.82rem;
          font-weight: 600;
          color: #4a4a4a;
          text-transform: uppercase;
          letter-spacing: 0.02em;
        }

        .subsection-divider {
          height: 1px;
          background: #efefef;
          margin: 0.2rem 0;
        }

        .subsection-disabled {
          opacity: 0.7;
        }

        .form-grid {
          display: flex;
          flex-direction: column;
          gap: 0.45rem;
        }

        .form-row {
          display: grid;
          grid-template-columns: 160px 1fr;
          align-items: center;
          gap: 0.5rem;
        }

        .form-row-top {
          align-items: start;
        }

        .form-label {
          font-size: 0.85rem;
          font-weight: 500;
          color: #444;
        }

        .form-control {
          display: flex;
          align-items: center;
          gap: 0.5rem;
          flex-wrap: wrap;
        }

        .inline-status {
          display: inline-flex;
          align-items: center;
          gap: 0.4rem;
          flex-wrap: wrap;
        }

        .status-dot {
          width: 8px;
          height: 8px;
          border-radius: 50%;
          background: #ccc;
        }

        .inline-status.active .status-dot {
          background: #34a853;
        }

        .inline-status.inactive .status-dot {
          background: #f9ab00;
        }

        .phone-number {
          font-size: 1rem;
          font-weight: 600;
          font-family: monospace;
        }

        .status-label {
          color: #666;
          font-size: 0.85rem;
        }

        .inline-note {
          font-size: 0.8rem;
          color: #555;
          margin: 0.1rem 0 0;
        }

        .hours-grid {
          display: grid;
          gap: 0.35rem;
        }

        .hours-row {
          display: grid;
          grid-template-columns: 110px 1fr;
          align-items: center;
          gap: 0.5rem;
        }

        .hours-day {
          font-weight: 500;
          font-size: 0.85rem;
        }

        .hours-time {
          display: flex;
          align-items: center;
          gap: 0.4rem;
          flex-wrap: wrap;
        }

        .hours-time input[type="time"] {
          padding: 0.25rem 0.4rem;
          font-size: 0.85rem;
        }

        .hours-sep {
          color: #666;
          font-size: 0.8rem;
        }

        .checkbox-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
          gap: 0.35rem 0.75rem;
        }

        .checkbox-label {
          display: inline-flex;
          align-items: center;
          gap: 0.35rem;
          font-weight: 400;
          font-size: 0.85rem;
          cursor: pointer;
        }

        .checkbox-label input[type="checkbox"] {
          width: 14px;
          height: 14px;
        }

        input[type="number"] {
          width: 110px;
          padding: 0.4rem 0.5rem;
          border: 1px solid #ddd;
          border-radius: 6px;
          font-size: 0.9rem;
          color: #333;
        }

        input[type="checkbox"] {
          width: 16px;
          height: 16px;
          cursor: pointer;
        }

        textarea,
        select {
          width: 100%;
          padding: 0.45rem 0.5rem;
          border: 1px solid #ddd;
          border-radius: 6px;
          font-size: 0.9rem;
          font-family: inherit;
          color: #333;
        }

        select {
          max-width: 240px;
        }

        textarea {
          resize: none;
        }

        .textarea-compact {
          height: 72px;
        }

        .textarea-short {
          height: 64px;
        }

        input:focus,
        textarea:focus,
        select:focus {
          outline: none;
          border-color: #4285f4;
          box-shadow: 0 0 0 2px rgba(66, 133, 244, 0.16);
        }

        .help-text {
          font-size: 0.8rem;
          color: #666;
          margin: 0.25rem 0 0;
          line-height: 1.3;
        }

        .help-text.tight {
          margin-top: 0.25rem;
        }

        .alert {
          padding: 0.5rem 0.75rem;
          border-radius: 6px;
          margin-bottom: 0.75rem;
          font-size: 0.9rem;
        }

        .alert-success {
          background: #e6f4ea;
          color: #1e7e34;
        }

        .alert-error {
          background: #fce8e6;
          color: #c5221f;
        }

        .page-actions {
          display: flex;
          justify-content: flex-start;
          margin-top: 0.5rem;
        }

        .btn {
          padding: 0.5rem 1.25rem;
          border: none;
          border-radius: 6px;
          font-size: 0.9rem;
          font-weight: 500;
          cursor: pointer;
          transition: background-color 0.2s;
        }

        .btn:disabled {
          opacity: 0.6;
          cursor: not-allowed;
        }

        .btn-primary {
          background: #4285f4;
          color: white;
        }

        .btn-primary:hover:not(:disabled) {
          background: #3367d6;
        }

        @media (max-width: 720px) {
          .form-row {
            grid-template-columns: 1fr;
          }

          .form-control {
            width: 100%;
          }

          .hours-row {
            grid-template-columns: 1fr;
          }
        }
      `}</style>
    </div>
  );
}
