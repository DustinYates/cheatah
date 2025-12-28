import { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import { LoadingState, ErrorState, EmptyState } from '../components/ui';

const API_BASE = '/api/v1';

export default function TelephonySettings() {
  const { token, user, selectedTenantId } = useAuth();
  const [config, setConfig] = useState({
    id: 0,
    tenant_id: 0,
    provider: 'twilio',
    sms_enabled: false,
    voice_enabled: false,
    // Twilio
    twilio_account_sid: '',
    has_twilio_auth_token: false,
    twilio_phone_number: '',
    // Telnyx
    telnyx_api_key_prefix: '',
    telnyx_messaging_profile_id: '',
    telnyx_connection_id: '',
    telnyx_phone_number: '',
    // Voice
    voice_phone_number: '',
  });

  // Form state for editable fields (separate from display config)
  const [formData, setFormData] = useState({
    provider: 'twilio',
    sms_enabled: false,
    voice_enabled: false,
    // Twilio
    twilio_account_sid: '',
    twilio_auth_token: '',
    twilio_phone_number: '',
    // Telnyx
    telnyx_api_key: '',
    telnyx_messaging_profile_id: '',
    telnyx_connection_id: '',
    telnyx_phone_number: '',
    // Voice
    voice_phone_number: '',
  });

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);
  const [validating, setValidating] = useState(false);
  const [message, setMessage] = useState({ type: '', text: '' });

  useEffect(() => {
    fetchConfig();
  }, [token, selectedTenantId]);

  const fetchConfig = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE}/admin/telephony/config`, {
        headers: { 'Authorization': `Bearer ${token}` },
      });
      if (response.ok) {
        const data = await response.json();
        setConfig(data);
        // Populate form with existing values (but not secrets)
        setFormData(prev => ({
          ...prev,
          provider: data.provider || 'twilio',
          sms_enabled: data.sms_enabled || false,
          voice_enabled: data.voice_enabled || false,
          twilio_account_sid: data.twilio_account_sid || '',
          twilio_phone_number: data.twilio_phone_number || '',
          telnyx_messaging_profile_id: data.telnyx_messaging_profile_id || '',
          telnyx_connection_id: data.telnyx_connection_id || '',
          telnyx_phone_number: data.telnyx_phone_number || '',
          voice_phone_number: data.voice_phone_number || '',
        }));
      } else if (response.status === 404) {
        // No config yet, use defaults
      } else {
        const errorData = await response.json().catch(() => ({}));
        setError(errorData.detail || 'Failed to load telephony config');
      }
    } catch (err) {
      console.error('Error fetching telephony config:', err);
      setError(err.message || 'Failed to load telephony config');
    } finally {
      setLoading(false);
    }
  };

  const saveConfig = async () => {
    setSaving(true);
    setMessage({ type: '', text: '' });

    try {
      const response = await fetch(`${API_BASE}/admin/telephony/config`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(formData),
      });

      if (response.ok) {
        const data = await response.json();
        setConfig(data);
        setMessage({ type: 'success', text: 'Telephony configuration saved successfully!' });
        // Clear secret fields after save
        setFormData(prev => ({
          ...prev,
          twilio_auth_token: '',
          telnyx_api_key: '',
        }));
      } else {
        const errorData = await response.json();
        setMessage({ type: 'error', text: errorData.detail || 'Failed to save configuration' });
      }
    } catch (err) {
      setMessage({ type: 'error', text: 'Network error. Please try again.' });
    } finally {
      setSaving(false);
    }
  };

  const validateCredentials = async () => {
    setValidating(true);
    setMessage({ type: '', text: '' });

    const payload = {
      provider: formData.provider,
    };

    if (formData.provider === 'twilio') {
      payload.twilio_account_sid = formData.twilio_account_sid;
      payload.twilio_auth_token = formData.twilio_auth_token;
    } else {
      payload.telnyx_api_key = formData.telnyx_api_key;
    }

    try {
      const response = await fetch(`${API_BASE}/admin/telephony/validate-credentials`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
      });

      const data = await response.json();

      if (data.valid) {
        setMessage({ type: 'success', text: data.message || 'Credentials are valid!' });
      } else {
        setMessage({ type: 'error', text: data.error || 'Invalid credentials' });
      }
    } catch (err) {
      setMessage({ type: 'error', text: 'Network error. Please try again.' });
    } finally {
      setValidating(false);
    }
  };

  const getWebhookUrls = () => {
    const baseUrl = window.location.origin;
    if (formData.provider === 'telnyx') {
      return {
        smsInbound: `${baseUrl}/api/v1/sms/telnyx/inbound`,
        smsStatus: `${baseUrl}/api/v1/sms/telnyx/status`,
        voiceInbound: `${baseUrl}/api/v1/voice/telnyx/inbound`,
        voiceStatus: `${baseUrl}/api/v1/voice/telnyx/status`,
      };
    }
    return {
      smsInbound: `${baseUrl}/api/v1/sms/inbound`,
      smsStatus: `${baseUrl}/api/v1/sms/status`,
      voiceInbound: `${baseUrl}/api/v1/voice/inbound`,
      voiceStatus: `${baseUrl}/api/v1/voice/status`,
    };
  };

  // Check if global admin without tenant selected
  const needsTenant = user?.is_global_admin && !selectedTenantId;

  if (needsTenant) {
    return (
      <div className="page-container">
        <EmptyState
          icon="📞"
          title="Select a tenant to manage telephony settings"
          description="Please select a tenant from the dropdown above to manage their telephony configuration."
        />
      </div>
    );
  }

  if (loading) {
    return (
      <div className="page-container">
        <LoadingState message="Loading telephony settings..." fullPage />
      </div>
    );
  }

  if (error) {
    if (error.includes('Tenant context required') || error.includes('Tenant context')) {
      return (
        <div className="page-container">
          <EmptyState
            icon="📞"
            title="Select a tenant to manage telephony settings"
            description="Please select a tenant from the dropdown above to manage their telephony configuration."
          />
        </div>
      );
    }
    return (
      <div className="page-container">
        <ErrorState message={error} onRetry={fetchConfig} />
      </div>
    );
  }

  const webhookUrls = getWebhookUrls();

  return (
    <div className="page-container">
      <h1>Telephony Settings</h1>
      <p className="subtitle">Configure SMS and Voice provider for this tenant</p>

      {message.text && (
        <div className={`alert ${message.type === 'error' ? 'alert-error' : 'alert-success'}`}>
          {message.text}
        </div>
      )}

      {/* Provider Selection */}
      <div className="card">
        <h2>Telephony Provider</h2>
        <p className="help-text">Choose which provider handles SMS and Voice calls for this tenant.</p>

        <div className="provider-options">
          <label className={`provider-option ${formData.provider === 'twilio' ? 'selected' : ''}`}>
            <input
              type="radio"
              name="provider"
              value="twilio"
              checked={formData.provider === 'twilio'}
              onChange={(e) => setFormData({ ...formData, provider: e.target.value })}
            />
            <div className="provider-info">
              <strong>Twilio</strong>
              <span>Industry standard, reliable SMS & Voice</span>
            </div>
          </label>

          <label className={`provider-option ${formData.provider === 'telnyx' ? 'selected' : ''}`}>
            <input
              type="radio"
              name="provider"
              value="telnyx"
              checked={formData.provider === 'telnyx'}
              onChange={(e) => setFormData({ ...formData, provider: e.target.value })}
            />
            <div className="provider-info">
              <strong>Telnyx</strong>
              <span>Cost-effective alternative with TeXML support</span>
            </div>
          </label>
        </div>
      </div>

      {/* Feature Toggles */}
      <div className="card">
        <h2>Features</h2>
        <label className="toggle-row">
          <span>Enable SMS</span>
          <input
            type="checkbox"
            checked={formData.sms_enabled}
            onChange={(e) => setFormData({ ...formData, sms_enabled: e.target.checked })}
          />
        </label>
        <label className="toggle-row">
          <span>Enable Voice</span>
          <input
            type="checkbox"
            checked={formData.voice_enabled}
            onChange={(e) => setFormData({ ...formData, voice_enabled: e.target.checked })}
          />
        </label>
      </div>

      {/* Provider-specific Credentials */}
      {formData.provider === 'twilio' ? (
        <div className="card">
          <h2>Twilio Credentials</h2>

          <div className="form-group">
            <label>Account SID</label>
            <input
              type="text"
              value={formData.twilio_account_sid}
              onChange={(e) => setFormData({ ...formData, twilio_account_sid: e.target.value })}
              placeholder="ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
            />
          </div>

          <div className="form-group">
            <label>Auth Token {config.has_twilio_auth_token && <span className="saved-indicator">(saved)</span>}</label>
            <input
              type="password"
              value={formData.twilio_auth_token}
              onChange={(e) => setFormData({ ...formData, twilio_auth_token: e.target.value })}
              placeholder={config.has_twilio_auth_token ? '••••••••••••' : 'Enter auth token'}
            />
            {config.has_twilio_auth_token && (
              <p className="help-text">Leave empty to keep existing token</p>
            )}
          </div>

          <div className="form-group">
            <label>SMS Phone Number</label>
            <input
              type="tel"
              value={formData.twilio_phone_number}
              onChange={(e) => setFormData({ ...formData, twilio_phone_number: e.target.value })}
              placeholder="+15551234567"
            />
          </div>

          <button
            className="btn btn-secondary"
            onClick={validateCredentials}
            disabled={validating || !formData.twilio_account_sid || !formData.twilio_auth_token}
          >
            {validating ? 'Validating...' : 'Test Credentials'}
          </button>
        </div>
      ) : (
        <div className="card">
          <h2>Telnyx Credentials</h2>

          <div className="form-group">
            <label>API Key {config.telnyx_api_key_prefix && <span className="saved-indicator">(saved: {config.telnyx_api_key_prefix})</span>}</label>
            <input
              type="password"
              value={formData.telnyx_api_key}
              onChange={(e) => setFormData({ ...formData, telnyx_api_key: e.target.value })}
              placeholder={config.telnyx_api_key_prefix ? '••••••••••••' : 'Enter Telnyx API v2 key'}
            />
            {config.telnyx_api_key_prefix && (
              <p className="help-text">Leave empty to keep existing key</p>
            )}
          </div>

          <div className="form-group">
            <label>Messaging Profile ID</label>
            <input
              type="text"
              value={formData.telnyx_messaging_profile_id}
              onChange={(e) => setFormData({ ...formData, telnyx_messaging_profile_id: e.target.value })}
              placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
            />
            <p className="help-text">Required for SMS - find this in Telnyx Mission Control</p>
          </div>

          <div className="form-group">
            <label>Connection ID (for Voice)</label>
            <input
              type="text"
              value={formData.telnyx_connection_id}
              onChange={(e) => setFormData({ ...formData, telnyx_connection_id: e.target.value })}
              placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
            />
            <p className="help-text">Required for Voice - the TeXML Application connection</p>
          </div>

          <div className="form-group">
            <label>SMS Phone Number</label>
            <input
              type="tel"
              value={formData.telnyx_phone_number}
              onChange={(e) => setFormData({ ...formData, telnyx_phone_number: e.target.value })}
              placeholder="+15551234567"
            />
          </div>

          <button
            className="btn btn-secondary"
            onClick={validateCredentials}
            disabled={validating || !formData.telnyx_api_key}
          >
            {validating ? 'Validating...' : 'Test Credentials'}
          </button>
        </div>
      )}

      {/* Voice Phone Number */}
      {formData.voice_enabled && (
        <div className="card">
          <h2>Voice Phone Number</h2>
          <p className="help-text">Optional - use a different number for voice calls</p>
          <div className="form-group">
            <input
              type="tel"
              value={formData.voice_phone_number}
              onChange={(e) => setFormData({ ...formData, voice_phone_number: e.target.value })}
              placeholder="+15551234567 (leave empty to use SMS number)"
            />
          </div>
        </div>
      )}

      {/* Webhook URLs */}
      <div className="card">
        <h2>Webhook URLs</h2>
        <p className="help-text">Configure these URLs in your {formData.provider === 'telnyx' ? 'Telnyx' : 'Twilio'} dashboard</p>

        <div className="webhook-list">
          <div className="webhook-item">
            <label>SMS Inbound</label>
            <code>{webhookUrls.smsInbound}</code>
          </div>
          <div className="webhook-item">
            <label>SMS Status Callback</label>
            <code>{webhookUrls.smsStatus}</code>
          </div>
          {formData.voice_enabled && (
            <>
              <div className="webhook-item">
                <label>Voice Inbound</label>
                <code>{webhookUrls.voiceInbound}</code>
              </div>
              <div className="webhook-item">
                <label>Voice Status Callback</label>
                <code>{webhookUrls.voiceStatus}</code>
              </div>
            </>
          )}
        </div>
      </div>

      <button className="btn btn-primary" onClick={saveConfig} disabled={saving}>
        {saving ? 'Saving...' : 'Save Configuration'}
      </button>

      <style>{`
        .page-container {
          max-width: 800px;
          margin: 0 auto;
          padding: 2rem;
        }

        h1 {
          margin-bottom: 0.5rem;
          color: #1a1a1a;
        }

        .subtitle {
          color: #666;
          margin-bottom: 1.5rem;
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

        .provider-options {
          display: flex;
          gap: 1rem;
          flex-wrap: wrap;
        }

        .provider-option {
          display: flex;
          align-items: flex-start;
          gap: 0.75rem;
          padding: 1rem;
          border: 2px solid #ddd;
          border-radius: 8px;
          cursor: pointer;
          flex: 1;
          min-width: 200px;
          transition: border-color 0.2s, background-color 0.2s;
        }

        .provider-option:hover {
          border-color: #4285f4;
        }

        .provider-option.selected {
          border-color: #4285f4;
          background: #f0f7ff;
        }

        .provider-option input[type="radio"] {
          margin-top: 2px;
        }

        .provider-info {
          display: flex;
          flex-direction: column;
          gap: 0.25rem;
        }

        .provider-info strong {
          color: #333;
        }

        .provider-info span {
          font-size: 0.85rem;
          color: #666;
        }

        .toggle-row {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 0.75rem 0;
          cursor: pointer;
          border-bottom: 1px solid #eee;
        }

        .toggle-row:last-child {
          border-bottom: none;
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

        .saved-indicator {
          font-weight: normal;
          color: #34a853;
          font-size: 0.85rem;
        }

        input[type="text"],
        input[type="tel"],
        input[type="password"] {
          width: 100%;
          padding: 0.75rem;
          border: 1px solid #ddd;
          border-radius: 6px;
          font-size: 1rem;
          font-family: inherit;
        }

        input:focus {
          outline: none;
          border-color: #4285f4;
          box-shadow: 0 0 0 2px rgba(66, 133, 244, 0.2);
        }

        .help-text {
          font-size: 0.875rem;
          color: #666;
          margin: 0.5rem 0 0;
        }

        .webhook-list {
          display: flex;
          flex-direction: column;
          gap: 1rem;
        }

        .webhook-item {
          display: flex;
          flex-direction: column;
          gap: 0.25rem;
        }

        .webhook-item label {
          font-size: 0.85rem;
          font-weight: 500;
          color: #666;
        }

        .webhook-item code {
          background: #f5f5f5;
          padding: 0.5rem 0.75rem;
          border-radius: 4px;
          font-size: 0.85rem;
          word-break: break-all;
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
          background: #f5f5f5;
          color: #333;
          border: 1px solid #ddd;
        }

        .btn-secondary:hover:not(:disabled) {
          background: #e8e8e8;
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
      `}</style>
    </div>
  );
}
