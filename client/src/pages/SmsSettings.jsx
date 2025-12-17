import { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import { LoadingState, ErrorState, EmptyState } from '../components/ui';

const API_BASE = '/api/v1';

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
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState({ type: '', text: '' });

  // Outreach state
  const [outreachPhone, setOutreachPhone] = useState('');
  const [outreachMessage, setOutreachMessage] = useState('');
  const [sendingOutreach, setSendingOutreach] = useState(false);

  useEffect(() => {
    fetchSettings();
  }, [token]);

  const fetchSettings = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE}/sms/settings`, {
        headers: { 'Authorization': `Bearer ${token}` },
      });
      if (response.ok) {
        const data = await response.json();
        setSettings(data);
        setOutreachMessage(data.initial_outreach_message || '');
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
        });
        setOutreachMessage("Hi! Thanks for reaching out. I'm an AI assistant and happy to help answer your questions. What can I help you with today?");
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
        });
        setOutreachMessage("Hi! Thanks for reaching out. I'm an AI assistant and happy to help answer your questions. What can I help you with today?");
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
      const response = await fetch(`${API_BASE}/sms/settings`, {
        method: 'PUT',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          is_enabled: settings.is_enabled,
          auto_reply_enabled: settings.auto_reply_enabled,
          auto_reply_message: settings.auto_reply_message,
          initial_outreach_message: settings.initial_outreach_message,
          business_hours_enabled: settings.business_hours_enabled,
          timezone: settings.timezone,
        }),
      });

      if (response.ok) {
        const data = await response.json();
        setSettings(data);
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

  const sendOutreach = async () => {
    if (!outreachPhone.trim()) {
      setMessage({ type: 'error', text: 'Please enter a phone number' });
      return;
    }

    setSendingOutreach(true);
    setMessage({ type: '', text: '' });

    try {
      const response = await fetch(`${API_BASE}/sms/outreach`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          phone_number: outreachPhone,
          custom_message: outreachMessage || null,
        }),
      });

      const data = await response.json();

      if (data.success) {
        setMessage({ type: 'success', text: `SMS sent successfully! Message ID: ${data.message_sid}` });
        setOutreachPhone('');
      } else {
        setMessage({ type: 'error', text: data.error || 'Failed to send SMS' });
      }
    } catch {
      setMessage({ type: 'error', text: 'Network error. Please try again.' });
    } finally {
      setSendingOutreach(false);
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

      <button className="btn btn-primary" onClick={saveSettings} disabled={saving}>
        {saving ? 'Saving...' : 'Save Settings'}
      </button>

      {/* Manual Outreach Section */}
      {settings.is_enabled && settings.phone_number && (
        <div className="card" style={{ marginTop: '2rem' }}>
          <h2>Send AI Follow-up</h2>
          <p className="help-text">
            Send an initial message to a customer. When they reply, the AI will handle the conversation.
          </p>

          <div className="form-group">
            <label>Customer Phone Number</label>
            <input
              type="tel"
              value={outreachPhone}
              onChange={(e) => setOutreachPhone(e.target.value)}
              placeholder="+1 (555) 123-4567"
            />
          </div>

          <div className="form-group">
            <label>Message (optional - uses default if empty)</label>
            <textarea
              value={outreachMessage}
              onChange={(e) => setOutreachMessage(e.target.value)}
              placeholder={settings.initial_outreach_message || "Hi! Thanks for reaching out..."}
              rows={3}
            />
          </div>

          <button
            className="btn btn-secondary"
            onClick={sendOutreach}
            disabled={sendingOutreach || !outreachPhone.trim()}
          >
            {sendingOutreach ? 'Sending...' : 'Send SMS'}
          </button>
        </div>
      )}

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
