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
      <div className="page-container">
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
      <div className="page-container">
        <LoadingState message="Loading SMS settings..." fullPage />
      </div>
    );
  }

  if (error) {
    // Check if error is about tenant context
    if (error.includes('Tenant context required') || error.includes('Tenant context')) {
      return (
        <div className="page-container">
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
        <div className="page-container">
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

  return (
    <div className="page-container">
      <h1>SMS Settings</h1>

      {message.text && (
        <div className={`alert ${message.type === 'error' ? 'alert-error' : 'alert-success'}`}>
          {message.text}
        </div>
      )}

      {/* Phone Number Status */}
      <div className="card">
        <h2>Phone Number</h2>
        {settings.phone_number ? (
          <div className="phone-status active">
            <span className="status-dot"></span>
            <span className="phone-number">{settings.phone_number}</span>
            <span className="status-label">Assigned</span>
          </div>
        ) : (
          <div className="phone-status inactive">
            <span className="status-dot"></span>
            <span className="status-label">No phone number assigned</span>
            <p className="help-text">Contact support to get a phone number assigned to your account.</p>
          </div>
        )}
      </div>

      {/* SMS Enable/Disable */}
      <div className="card">
        <h2>SMS Status</h2>
        <label className="toggle-row">
          <span>Enable SMS</span>
          <input
            type="checkbox"
            checked={settings.is_enabled}
            onChange={(e) => setSettings({ ...settings, is_enabled: e.target.checked })}
            disabled={!settings.phone_number}
          />
        </label>
        {!settings.phone_number && (
          <p className="help-text">You need an assigned phone number to enable SMS.</p>
        )}
      </div>

      {/* Initial Outreach Message */}
      <div className="card">
        <h2>Initial Outreach Message</h2>
        <p className="help-text">
          This message is sent when you manually initiate contact with a customer.
          The AI will continue the conversation when they reply.
        </p>
        <textarea
          value={settings.initial_outreach_message || ''}
          onChange={(e) => setSettings({ ...settings, initial_outreach_message: e.target.value })}
          placeholder="Hi! Thanks for reaching out..."
          rows={3}
        />
      </div>

      {/* Auto-Reply Settings */}
      <div className="card">
        <h2>Auto-Reply (Outside Business Hours)</h2>
        <p className="help-text">
          The AI will respond during the hours you set below. Outside those hours, you can send an auto-reply message.
        </p>
        <label className="toggle-row">
          <span>Enable business hours</span>
          <input
            type="checkbox"
            checked={settings.business_hours_enabled}
            onChange={(e) => setSettings({ ...settings, business_hours_enabled: e.target.checked })}
          />
        </label>

        {settings.business_hours_enabled && (
          <>
            <div className="form-group">
              <label>Timezone</label>
              <select
                value={settings.timezone}
                onChange={(e) => setSettings({ ...settings, timezone: e.target.value })}
              >
                <option value="America/New_York">Eastern Time</option>
                <option value="America/Chicago">Central Time</option>
                <option value="America/Denver">Mountain Time</option>
                <option value="America/Los_Angeles">Pacific Time</option>
              </select>
            </div>

            <div className="form-group">
              <label>Business hours</label>
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
              <p className="help-text">Leave a day blank to mark it as closed.</p>
            </div>

            <label className="toggle-row">
              <span>Send auto-reply outside hours</span>
              <input
                type="checkbox"
                checked={settings.auto_reply_enabled}
                onChange={(e) => setSettings({ ...settings, auto_reply_enabled: e.target.checked })}
              />
            </label>

            {settings.auto_reply_enabled && (
              <div className="form-group">
                <label>Auto-reply message</label>
                <textarea
                  value={settings.auto_reply_message || ''}
                  onChange={(e) => setSettings({ ...settings, auto_reply_message: e.target.value })}
                  placeholder="We're currently outside business hours. We'll respond as soon as we're back!"
                  rows={2}
                />
              </div>
            )}
          </>
        )}
      </div>

      {/* Auto Follow-up Settings */}
      <div className="card">
        <h2>Auto Follow-up for New Leads</h2>
        <p className="help-text">
          Automatically send a follow-up text message when a new lead is captured from email forms,
          phone calls, or other sources.
        </p>

        <label className="toggle-row">
          <span>Enable auto follow-up</span>
          <input
            type="checkbox"
            checked={settings.followup_enabled}
            onChange={(e) => setSettings({ ...settings, followup_enabled: e.target.checked })}
            disabled={!settings.phone_number}
          />
        </label>
        {!settings.phone_number && (
          <p className="help-text">You need an assigned phone number to enable auto follow-up.</p>
        )}

        {settings.followup_enabled && (
          <>
            <div className="form-group">
              <label>Delay before sending (minutes)</label>
              <input
                type="number"
                min="1"
                max="60"
                value={settings.followup_delay_minutes}
                onChange={(e) => setSettings({ ...settings, followup_delay_minutes: parseInt(e.target.value) || 5 })}
              />
              <p className="help-text">How long to wait after capturing a lead before sending the follow-up text.</p>
            </div>

            <div className="form-group">
              <label>Trigger follow-up for leads from:</label>
              <div className="checkbox-group">
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
                  Email form submissions
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
                  Voice calls
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
                  SMS inquiries
                </label>
              </div>
            </div>

            <div className="form-group">
              <label>Custom follow-up message (optional)</label>
              <textarea
                value={settings.followup_initial_message || ''}
                onChange={(e) => setSettings({ ...settings, followup_initial_message: e.target.value })}
                placeholder="Leave empty for AI-generated messages. Use {name} or {first_name} for personalization."
                rows={3}
              />
              <p className="help-text">
                If empty, the AI will generate a contextual follow-up message based on the lead source.
                You can use {'{name}'} or {'{first_name}'} placeholders.
              </p>
            </div>
          </>
        )}
      </div>

      <button className="btn btn-primary" onClick={saveSettings} disabled={saving}>
        {saving ? 'Saving...' : 'Save Settings'}
      </button>

      <style>{`
        .page-container {
          max-width: 800px;
          margin: 0 auto;
          padding: 2rem;
        }

        h1 {
          margin-bottom: 1.5rem;
          color: #1a1a1a;
        }

        .card {
          background: #fff;
          border-radius: 8px;
          padding: 1.5rem;
          margin-bottom: 1.5rem;
          box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
        }

        .card h2 {
          font-size: 1.1rem;
          margin-bottom: 1rem;
          color: #333;
        }

        .phone-status {
          display: flex;
          align-items: center;
          gap: 0.75rem;
          padding: 1rem;
          background: #f5f5f5;
          border-radius: 6px;
        }

        .phone-status.active {
          background: #e6f4ea;
        }

        .phone-status.inactive {
          background: #fef7e0;
          flex-direction: column;
          align-items: flex-start;
        }

        .status-dot {
          width: 10px;
          height: 10px;
          border-radius: 50%;
          background: #ccc;
        }

        .phone-status.active .status-dot {
          background: #34a853;
        }

        .phone-status.inactive .status-dot {
          background: #f9ab00;
        }

        .phone-number {
          font-size: 1.25rem;
          font-weight: 600;
          font-family: monospace;
        }

        .status-label {
          color: #666;
          font-size: 0.9rem;
        }

        .toggle-row {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 0.75rem 0;
          cursor: pointer;
        }

        .toggle-row input[type="checkbox"] {
          width: 20px;
          height: 20px;
          cursor: pointer;
        }

        .form-group {
          margin: 1rem 0;
        }

        .form-group label {
          display: block;
          margin-bottom: 0.5rem;
          font-weight: 500;
        }

        .checkbox-group {
          display: flex;
          flex-direction: column;
          gap: 0.5rem;
          margin-top: 0.5rem;
        }

        .checkbox-label {
          display: flex;
          align-items: center;
          gap: 0.5rem;
          font-weight: normal;
          cursor: pointer;
        }

        .checkbox-label input[type="checkbox"] {
          width: 16px;
          height: 16px;
          cursor: pointer;
        }

        .hours-grid {
          display: flex;
          flex-direction: column;
          gap: 0.75rem;
          margin-top: 0.5rem;
        }

        .hours-row {
          display: flex;
          align-items: center;
          gap: 1rem;
          flex-wrap: wrap;
        }

        .hours-day {
          width: 110px;
          font-weight: 500;
        }

        .hours-time {
          display: flex;
          align-items: center;
          gap: 0.5rem;
        }

        .hours-time input[type="time"] {
          padding: 0.4rem 0.5rem;
        }

        .hours-sep {
          color: #666;
          font-size: 0.9rem;
        }

        input[type="number"] {
          width: 100px;
          padding: 0.5rem;
          border: 1px solid #ddd;
          border-radius: 6px;
          font-size: 1rem;
          color: #333;
        }

        input[type="tel"],
        textarea,
        select {
          width: 100%;
          padding: 0.75rem;
          border: 1px solid #ddd;
          border-radius: 6px;
          font-size: 1rem;
          font-family: inherit;
        }

        textarea {
          resize: vertical;
        }

        input:focus,
        textarea:focus,
        select:focus {
          outline: none;
          border-color: #4285f4;
          box-shadow: 0 0 0 2px rgba(66, 133, 244, 0.2);
        }

        .help-text {
          font-size: 0.875rem;
          color: #666;
          margin: 0.5rem 0;
        }

        .btn {
          padding: 0.75rem 1.5rem;
          border: none;
          border-radius: 6px;
          font-size: 1rem;
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

        .btn-secondary {
          background: #34a853;
          color: white;
        }

        .btn-secondary:hover:not(:disabled) {
          background: #2d8e47;
        }

        .alert {
          padding: 1rem;
          border-radius: 6px;
          margin-bottom: 1.5rem;
        }

        .alert-success {
          background: #e6f4ea;
          color: #1e7e34;
        }

        .alert-error {
          background: #fce8e6;
          color: #c5221f;
        }

        .loading {
          text-align: center;
          padding: 3rem;
          color: #666;
        }
      `}</style>
    </div>
  );
}
