import { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import { LoadingState, ErrorState, EmptyState } from '../components/ui';

const API_BASE = '/api/v1';

const DEFAULT_KEYWORDS = [
  'speak to human',
  'talk to person',
  'real person',
  'agent',
  'representative',
  'manager',
  'supervisor',
  'escalate',
];

const DAYS_OF_WEEK = [
  { key: 'sunday', label: 'Sun' },
  { key: 'monday', label: 'Mon' },
  { key: 'tuesday', label: 'Tue' },
  { key: 'wednesday', label: 'Wed' },
  { key: 'thursday', label: 'Thu' },
  { key: 'friday', label: 'Fri' },
  { key: 'saturday', label: 'Sat' },
];

const TIMEZONES = [
  { value: 'America/New_York', label: 'Eastern Time (ET)' },
  { value: 'America/Chicago', label: 'Central Time (CT)' },
  { value: 'America/Denver', label: 'Mountain Time (MT)' },
  { value: 'America/Los_Angeles', label: 'Pacific Time (PT)' },
  { value: 'America/Phoenix', label: 'Arizona (no DST)' },
  { value: 'America/Anchorage', label: 'Alaska Time (AKT)' },
  { value: 'Pacific/Honolulu', label: 'Hawaii Time (HT)' },
];

export default function EscalationSettings() {
  const { token, user, selectedTenantId } = useAuth();
  const [settings, setSettings] = useState({
    enabled: true,
    notification_methods: ['email', 'sms'],
    custom_keywords: [],
    alert_phone_override: '',
    quiet_hours: {
      enabled: false,
      start_time: '22:00',
      end_time: '07:00',
      days: ['sunday', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday'],
      timezone: 'America/Chicago',
    },
  });
  const [businessPhone, setBusinessPhone] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState({ type: '', text: '' });
  const [newKeyword, setNewKeyword] = useState('');

  useEffect(() => {
    fetchSettings();
  }, [token, selectedTenantId]);

  const getHeaders = () => {
    const headers = { 'Authorization': `Bearer ${token}` };
    if (user?.is_global_admin && selectedTenantId) {
      headers['X-Tenant-Id'] = selectedTenantId.toString();
    }
    return headers;
  };

  const fetchSettings = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE}/escalation/settings`, {
        headers: getHeaders(),
      });
      if (response.ok) {
        const data = await response.json();
        const quietHours = data.settings.quiet_hours || {};
        setSettings({
          enabled: data.settings.enabled,
          notification_methods: data.settings.notification_methods || ['email', 'sms'],
          custom_keywords: data.settings.custom_keywords || [],
          alert_phone_override: data.settings.alert_phone_override || '',
          quiet_hours: {
            enabled: quietHours.enabled || false,
            start_time: quietHours.start_time || '22:00',
            end_time: quietHours.end_time || '07:00',
            days: quietHours.days || ['sunday', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday'],
            timezone: quietHours.timezone || 'America/Chicago',
          },
        });
        setBusinessPhone(data.business_phone);
      } else if (response.status === 404) {
        // Use defaults
        setSettings({
          enabled: true,
          notification_methods: ['email', 'sms'],
          custom_keywords: [],
          alert_phone_override: '',
          quiet_hours: {
            enabled: false,
            start_time: '22:00',
            end_time: '07:00',
            days: ['sunday', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday'],
            timezone: 'America/Chicago',
          },
        });
      } else {
        const errorData = await response.json().catch(() => ({}));
        setError(errorData.detail || 'Failed to load escalation settings');
      }
    } catch (err) {
      console.error('Error fetching escalation settings:', err);
      setError(err.message || 'Failed to load escalation settings');
    } finally {
      setLoading(false);
    }
  };

  const saveSettings = async () => {
    setSaving(true);
    setMessage({ type: '', text: '' });

    try {
      const response = await fetch(`${API_BASE}/escalation/settings`, {
        method: 'PUT',
        headers: {
          ...getHeaders(),
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          enabled: settings.enabled,
          notification_methods: settings.notification_methods,
          custom_keywords: settings.custom_keywords,
          alert_phone_override: settings.alert_phone_override || null,
          quiet_hours: settings.quiet_hours,
        }),
      });

      if (response.ok) {
        setMessage({ type: 'success', text: 'Escalation settings saved successfully!' });
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

  const toggleMethod = (method) => {
    setSettings((prev) => {
      const methods = prev.notification_methods || [];
      if (methods.includes(method)) {
        return { ...prev, notification_methods: methods.filter((m) => m !== method) };
      } else {
        return { ...prev, notification_methods: [...methods, method] };
      }
    });
  };

  const addKeyword = () => {
    const keyword = newKeyword.trim().toLowerCase();
    if (keyword && !settings.custom_keywords.includes(keyword) && !DEFAULT_KEYWORDS.includes(keyword)) {
      setSettings((prev) => ({
        ...prev,
        custom_keywords: [...prev.custom_keywords, keyword],
      }));
      setNewKeyword('');
    }
  };

  const removeKeyword = (keyword) => {
    setSettings((prev) => ({
      ...prev,
      custom_keywords: prev.custom_keywords.filter((k) => k !== keyword),
    }));
  };

  const toggleQuietDay = (day) => {
    setSettings((prev) => {
      const days = prev.quiet_hours.days || [];
      const newDays = days.includes(day)
        ? days.filter((d) => d !== day)
        : [...days, day];
      return {
        ...prev,
        quiet_hours: { ...prev.quiet_hours, days: newDays },
      };
    });
  };

  const updateQuietHours = (field, value) => {
    setSettings((prev) => ({
      ...prev,
      quiet_hours: { ...prev.quiet_hours, [field]: value },
    }));
  };

  const needsTenant = user?.is_global_admin && !selectedTenantId;

  if (needsTenant) {
    return (
      <div className="page-container escalation-settings">
        <EmptyState
          icon="🚨"
          title="Select a tenant to manage escalation settings"
          description="Please select a tenant from the dropdown above to manage their escalation settings."
        />
      </div>
    );
  }

  if (loading) {
    return (
      <div className="page-container escalation-settings">
        <LoadingState message="Loading escalation settings..." fullPage />
      </div>
    );
  }

  if (error) {
    if (error.includes('Tenant context required') || error.includes('Tenant context')) {
      return (
        <div className="page-container escalation-settings">
          <EmptyState
            icon="🚨"
            title="Select a tenant to manage escalation settings"
            description="Please select a tenant from the dropdown above to manage their escalation settings."
          />
        </div>
      );
    }
    return (
      <div className="page-container escalation-settings">
        <ErrorState message={error} onRetry={fetchSettings} />
      </div>
    );
  }

  return (
    <div className="page-container escalation-settings">
      <div className="page-header">
        <span className="page-title">Escalation Settings</span>
        <p className="page-subtitle">
          Configure how you're notified when a customer requests to speak with a human.
          When detected, you'll receive immediate alerts via your selected methods.
        </p>
      </div>

      {message.text && (
        <div className={`alert ${message.type === 'error' ? 'alert-error' : 'alert-success'}`}>
          {message.text}
        </div>
      )}

      <div className="card">
        <div className="section">
          <div className="section-title">Escalation Alerts</div>

          <div className="form-row">
            <label className="form-label" htmlFor="escalation-enabled">
              Enable alerts
            </label>
            <div className="form-control">
              <input
                id="escalation-enabled"
                type="checkbox"
                checked={settings.enabled}
                onChange={(e) => setSettings({ ...settings, enabled: e.target.checked })}
              />
            </div>
          </div>
          <div className="help-text">
            When enabled, you'll be notified immediately when a customer requests human assistance.
          </div>
        </div>

        <div className="section-divider"></div>

        <div className="section">
          <div className="section-title">Notification Methods</div>
          <p className="help-text" style={{ marginBottom: '0.5rem' }}>
            Choose how you want to be notified when a customer requests a human.
          </p>

          <div className="checkbox-grid">
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={settings.notification_methods?.includes('email')}
                onChange={() => toggleMethod('email')}
              />
              Email
            </label>
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={settings.notification_methods?.includes('sms')}
                onChange={() => toggleMethod('sms')}
              />
              SMS Text Message
            </label>
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={settings.notification_methods?.includes('in_app')}
                onChange={() => toggleMethod('in_app')}
              />
              In-App Notification
            </label>
          </div>
        </div>

        <div className="section-divider"></div>

        <div className="section">
          <div className="section-title">Quiet Hours</div>
          <p className="help-text" style={{ marginBottom: '0.5rem' }}>
            Suppress alerts during specific hours. Escalations will still be logged but notifications won't be sent.
          </p>

          <div className="form-row">
            <label className="form-label" htmlFor="quiet-hours-enabled">
              Enable quiet hours
            </label>
            <div className="form-control">
              <input
                id="quiet-hours-enabled"
                type="checkbox"
                checked={settings.quiet_hours.enabled}
                onChange={(e) => updateQuietHours('enabled', e.target.checked)}
              />
            </div>
          </div>

          {settings.quiet_hours.enabled && (
            <div className="quiet-hours-config">
              <div className="time-range">
                <div className="time-input-group">
                  <label htmlFor="quiet-start">From</label>
                  <input
                    id="quiet-start"
                    type="time"
                    value={settings.quiet_hours.start_time}
                    onChange={(e) => updateQuietHours('start_time', e.target.value)}
                  />
                </div>
                <span className="time-separator">to</span>
                <div className="time-input-group">
                  <label htmlFor="quiet-end">Until</label>
                  <input
                    id="quiet-end"
                    type="time"
                    value={settings.quiet_hours.end_time}
                    onChange={(e) => updateQuietHours('end_time', e.target.value)}
                  />
                </div>
              </div>

              <div className="days-selector">
                <span className="days-label">Active on:</span>
                <div className="days-buttons">
                  {DAYS_OF_WEEK.map((day) => (
                    <button
                      key={day.key}
                      type="button"
                      className={`day-btn ${settings.quiet_hours.days.includes(day.key) ? 'active' : ''}`}
                      onClick={() => toggleQuietDay(day.key)}
                    >
                      {day.label}
                    </button>
                  ))}
                </div>
              </div>

              <div className="timezone-select">
                <label htmlFor="quiet-timezone">Timezone</label>
                <select
                  id="quiet-timezone"
                  value={settings.quiet_hours.timezone}
                  onChange={(e) => updateQuietHours('timezone', e.target.value)}
                >
                  {TIMEZONES.map((tz) => (
                    <option key={tz.value} value={tz.value}>
                      {tz.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          )}
        </div>

        <div className="section-divider"></div>

        <div className="section">
          <div className="section-title">SMS Alert Phone Number</div>

          {businessPhone ? (
            <div className="phone-info">
              <span className="phone-label">Business Profile Phone:</span>
              <span className="phone-number">{businessPhone}</span>
              <span className="phone-note">(used by default)</span>
            </div>
          ) : (
            <div className="phone-warning">
              No phone number configured in your Business Profile. Add one to receive SMS alerts.
            </div>
          )}

          <div className="form-row" style={{ marginTop: '0.5rem' }}>
            <label className="form-label" htmlFor="alert-phone-override">
              Override phone
            </label>
            <div className="form-control">
              <input
                id="alert-phone-override"
                type="tel"
                value={settings.alert_phone_override}
                onChange={(e) => setSettings({ ...settings, alert_phone_override: e.target.value })}
                placeholder="+1 (555) 123-4567"
              />
            </div>
          </div>
          <div className="help-text">
            Optionally specify a different phone number for escalation SMS alerts.
          </div>
        </div>

        <div className="section-divider"></div>

        <div className="section">
          <div className="section-title">Escalation Keywords</div>
          <p className="help-text" style={{ marginBottom: '0.75rem' }}>
            These words and phrases trigger an escalation alert when customers use them.
          </p>

          <div className="keywords-section">
            <div className="keywords-group">
              <span className="keywords-label">Default keywords (always active):</span>
              <div className="keywords-list">
                {DEFAULT_KEYWORDS.map((keyword) => (
                  <span key={keyword} className="keyword-tag default">
                    {keyword}
                  </span>
                ))}
              </div>
            </div>

            <div className="keywords-group">
              <span className="keywords-label">Custom keywords:</span>
              <div className="keywords-list">
                {settings.custom_keywords.length > 0 ? (
                  settings.custom_keywords.map((keyword) => (
                    <span key={keyword} className="keyword-tag custom">
                      {keyword}
                      <button
                        className="keyword-remove"
                        onClick={() => removeKeyword(keyword)}
                        title="Remove keyword"
                      >
                        x
                      </button>
                    </span>
                  ))
                ) : (
                  <span className="no-keywords">No custom keywords added</span>
                )}
              </div>

              <div className="add-keyword">
                <input
                  type="text"
                  value={newKeyword}
                  onChange={(e) => setNewKeyword(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && addKeyword()}
                  placeholder="Add a custom keyword..."
                />
                <button className="btn btn-secondary" onClick={addKeyword} disabled={!newKeyword.trim()}>
                  Add
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="page-actions">
        <button className="btn btn-primary" onClick={saveSettings} disabled={saving}>
          {saving ? 'Saving...' : 'Save Settings'}
        </button>
      </div>

      <style>{`
        .page-container.escalation-settings {
          max-width: 800px;
          margin: 0 auto;
          padding: 1rem 1.25rem 1.5rem;
        }

        .page-header {
          margin-bottom: 1rem;
        }

        .page-title {
          font-size: 1rem;
          font-weight: 600;
          color: #1a1a1a;
        }

        .page-subtitle {
          font-size: 0.85rem;
          color: #666;
          margin: 0.5rem 0 0;
          line-height: 1.4;
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

        .card {
          background: #fff;
          border-radius: 8px;
          padding: 0.75rem;
          margin-bottom: 0.75rem;
          box-shadow: 0 1px 2px rgba(0, 0, 0, 0.08);
        }

        .section {
          display: flex;
          flex-direction: column;
          gap: 0.5rem;
        }

        .section-title {
          font-size: 0.78rem;
          font-weight: 600;
          color: #444;
          margin: 0;
          text-transform: uppercase;
        }

        .section-divider {
          height: 1px;
          background: #eee;
          margin: 0.75rem 0;
        }

        .form-row {
          display: grid;
          grid-template-columns: 160px 1fr;
          align-items: center;
          gap: 0.5rem;
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
        }

        input[type="checkbox"] {
          width: 16px;
          height: 16px;
          cursor: pointer;
        }

        input[type="tel"],
        input[type="text"] {
          padding: 0.4rem 0.5rem;
          border: 1px solid #ddd;
          border-radius: 6px;
          font-size: 0.9rem;
          color: #333;
          width: 100%;
          max-width: 280px;
        }

        input:focus {
          outline: none;
          border-color: #4285f4;
          box-shadow: 0 0 0 2px rgba(66, 133, 244, 0.16);
        }

        .help-text {
          font-size: 0.8rem;
          color: #666;
          margin-top: 0.25rem;
          line-height: 1.3;
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

        .phone-info {
          display: flex;
          align-items: center;
          gap: 0.5rem;
          flex-wrap: wrap;
        }

        .phone-label {
          font-size: 0.85rem;
          color: #666;
        }

        .phone-number {
          font-size: 0.95rem;
          font-weight: 600;
          font-family: monospace;
        }

        .phone-note {
          font-size: 0.8rem;
          color: #888;
        }

        .phone-warning {
          font-size: 0.85rem;
          color: #b45309;
          background: #fef7e0;
          padding: 0.5rem 0.75rem;
          border-radius: 6px;
        }

        .quiet-hours-config {
          display: flex;
          flex-direction: column;
          gap: 0.75rem;
          margin-top: 0.5rem;
          padding: 0.75rem;
          background: #f8f9fa;
          border-radius: 6px;
        }

        .time-range {
          display: flex;
          align-items: flex-end;
          gap: 0.5rem;
          flex-wrap: wrap;
        }

        .time-input-group {
          display: flex;
          flex-direction: column;
          gap: 0.25rem;
        }

        .time-input-group label {
          font-size: 0.75rem;
          color: #666;
        }

        .time-input-group input[type="time"] {
          padding: 0.4rem 0.5rem;
          border: 1px solid #ddd;
          border-radius: 6px;
          font-size: 0.9rem;
          color: #333;
        }

        .time-separator {
          font-size: 0.85rem;
          color: #666;
          padding-bottom: 0.4rem;
        }

        .days-selector {
          display: flex;
          flex-direction: column;
          gap: 0.35rem;
        }

        .days-label {
          font-size: 0.75rem;
          color: #666;
        }

        .days-buttons {
          display: flex;
          gap: 0.25rem;
          flex-wrap: wrap;
        }

        .day-btn {
          padding: 0.35rem 0.5rem;
          border: 1px solid #ddd;
          border-radius: 4px;
          background: #fff;
          font-size: 0.8rem;
          cursor: pointer;
          transition: all 0.15s;
          min-width: 40px;
        }

        .day-btn:hover {
          border-color: #4285f4;
        }

        .day-btn.active {
          background: #4285f4;
          border-color: #4285f4;
          color: white;
        }

        .timezone-select {
          display: flex;
          flex-direction: column;
          gap: 0.25rem;
        }

        .timezone-select label {
          font-size: 0.75rem;
          color: #666;
        }

        .timezone-select select {
          padding: 0.4rem 0.5rem;
          border: 1px solid #ddd;
          border-radius: 6px;
          font-size: 0.85rem;
          color: #333;
          background: #fff;
          max-width: 250px;
        }

        .timezone-select select:focus {
          outline: none;
          border-color: #4285f4;
          box-shadow: 0 0 0 2px rgba(66, 133, 244, 0.16);
        }

        .keywords-section {
          display: flex;
          flex-direction: column;
          gap: 1rem;
        }

        .keywords-group {
          display: flex;
          flex-direction: column;
          gap: 0.35rem;
        }

        .keywords-label {
          font-size: 0.8rem;
          font-weight: 500;
          color: #666;
        }

        .keywords-list {
          display: flex;
          flex-wrap: wrap;
          gap: 0.35rem;
        }

        .keyword-tag {
          display: inline-flex;
          align-items: center;
          gap: 0.25rem;
          padding: 0.25rem 0.5rem;
          border-radius: 12px;
          font-size: 0.8rem;
        }

        .keyword-tag.default {
          background: #f1f3f4;
          color: #666;
        }

        .keyword-tag.custom {
          background: #e8f0fe;
          color: #1a73e8;
        }

        .keyword-remove {
          background: none;
          border: none;
          padding: 0;
          margin-left: 0.15rem;
          cursor: pointer;
          font-size: 0.85rem;
          color: #1a73e8;
          line-height: 1;
        }

        .keyword-remove:hover {
          color: #c5221f;
        }

        .no-keywords {
          font-size: 0.8rem;
          color: #888;
          font-style: italic;
        }

        .add-keyword {
          display: flex;
          gap: 0.5rem;
          margin-top: 0.25rem;
        }

        .add-keyword input {
          flex: 1;
          max-width: 300px;
        }

        .page-actions {
          display: flex;
          justify-content: flex-start;
          margin-top: 0.5rem;
        }

        .btn {
          padding: 0.5rem 1rem;
          border: none;
          border-radius: 6px;
          font-size: 0.85rem;
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
          padding: 0.5rem 1.25rem;
        }

        .btn-primary:hover:not(:disabled) {
          background: #3367d6;
        }

        .btn-secondary {
          background: #f1f3f4;
          color: #333;
        }

        .btn-secondary:hover:not(:disabled) {
          background: #e8eaed;
        }

        @media (max-width: 600px) {
          .form-row {
            grid-template-columns: 1fr;
          }

          .checkbox-grid {
            grid-template-columns: 1fr;
          }
        }
      `}</style>
    </div>
  );
}
