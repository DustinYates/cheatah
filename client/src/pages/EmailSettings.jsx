import { useState, useCallback, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { api } from '../api/client';
import { useFetchData } from '../hooks/useFetchData';
import { useAuth } from '../context/AuthContext';
import { LoadingState, ErrorState, EmptyState } from '../components/ui';
import './EmailSettings.css';

export default function EmailSettings() {
  const { user, selectedTenantId } = useAuth();
  const [searchParams] = useSearchParams();
  const [saving, setSaving] = useState(false);
  const [success, setSuccess] = useState('');
  const [formError, setFormError] = useState('');
  const [connecting, setConnecting] = useState(false);
  const [disconnecting, setDisconnecting] = useState(false);
  const [refreshingWatch, setRefreshingWatch] = useState(false);

  const [formData, setFormData] = useState({
    is_enabled: false,
    business_hours_enabled: false,
    auto_reply_outside_hours: true,
    auto_reply_message: '',
    response_signature: '',
    max_thread_depth: 10,
    escalation_rules: null,
  });

  const fetchSettings = useCallback(() => api.getEmailSettings(), []);
  const { data: settings, loading, error, refetch } = useFetchData(fetchSettings);

  // Check for OAuth callback params
  useEffect(() => {
    const connected = searchParams.get('connected');
    const email = searchParams.get('email');
    const errorParam = searchParams.get('error');

    if (connected === 'true' && email) {
      setSuccess(`Successfully connected to ${email}!`);
      refetch();
    } else if (errorParam) {
      setFormError(`OAuth error: ${errorParam}`);
    }
  }, [searchParams, refetch]);

  // Check if global admin without tenant selected
  const needsTenant = user?.is_global_admin && !selectedTenantId;

  useEffect(() => {
    if (settings) {
      setFormData({
        is_enabled: settings.is_enabled,
        business_hours_enabled: settings.business_hours_enabled,
        auto_reply_outside_hours: settings.auto_reply_outside_hours,
        auto_reply_message: settings.auto_reply_message || '',
        response_signature: settings.response_signature || '',
        max_thread_depth: settings.max_thread_depth || 10,
        escalation_rules: settings.escalation_rules,
      });
    }
  }, [settings]);

  const handleChange = (e) => {
    const { name, value, type, checked } = e.target;
    setFormData(prev => ({
      ...prev,
      [name]: type === 'checkbox' ? checked : value,
    }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setFormError('');
    setSuccess('');
    setSaving(true);

    try {
      await api.updateEmailSettings(formData);
      setSuccess('Settings updated successfully');
      refetch();
    } catch (err) {
      setFormError(err.message || 'Failed to save settings');
    } finally {
      setSaving(false);
    }
  };

  const handleConnectGmail = async () => {
    setFormError('');
    setConnecting(true);

    try {
      const response = await api.startEmailOAuth();
      // Redirect to Google OAuth
      window.location.href = response.authorization_url;
    } catch (err) {
      setFormError(err.message || 'Failed to start OAuth flow');
      setConnecting(false);
    }
  };

  const handleDisconnect = async () => {
    if (!window.confirm('Are you sure you want to disconnect Gmail? Email responses will stop working.')) {
      return;
    }

    setFormError('');
    setDisconnecting(true);

    try {
      await api.disconnectEmail();
      setSuccess('Gmail disconnected successfully');
      refetch();
    } catch (err) {
      setFormError(err.message || 'Failed to disconnect Gmail');
    } finally {
      setDisconnecting(false);
    }
  };

  const handleRefreshWatch = async () => {
    setFormError('');
    setRefreshingWatch(true);

    try {
      await api.refreshEmailWatch();
      setSuccess('Gmail watch refreshed successfully');
      refetch();
    } catch (err) {
      setFormError(err.message || 'Failed to refresh Gmail watch');
    } finally {
      setRefreshingWatch(false);
    }
  };

  if (needsTenant) {
    return (
      <div className="email-settings-page">
        <EmptyState
          icon="✉️"
          title="Select a tenant to manage email settings"
          description="Please select a tenant from the dropdown above to manage their email responder settings."
        />
      </div>
    );
  }

  if (loading) {
    return (
      <div className="email-settings-page">
        <LoadingState message="Loading email settings..." />
      </div>
    );
  }

  if (error && !settings) {
    if (error.includes('Tenant context required') || error.includes('Tenant context')) {
      return (
        <div className="email-settings-page">
          <EmptyState
            icon="✉️"
            title="Select a tenant to manage email settings"
            description="Please select a tenant from the dropdown above to manage their email responder settings."
          />
        </div>
      );
    }
    return (
      <div className="email-settings-page">
        <ErrorState message={error} onRetry={refetch} />
      </div>
    );
  }

  return (
    <div className="email-settings-page">
      <h1>Email Responder Settings</h1>
      <p className="description">
        Connect your Gmail account to automatically respond to customer emails with AI-powered responses.
      </p>

      {formError && <div className="error-message">{formError}</div>}
      {success && <div className="success-message">{success}</div>}

      {/* Gmail Connection Section */}
      <section className="settings-section">
        <h2>Gmail Connection</h2>
        
        {settings?.is_connected ? (
          <div className="connection-status connected">
            <div className="status-indicator">
              <span className="status-dot connected"></span>
              <span>Connected</span>
            </div>
            <div className="connected-email">
              <strong>Email:</strong> {settings.gmail_email}
            </div>
            <div className="watch-status">
              <strong>Push Notifications:</strong>{' '}
              {settings.watch_active ? (
                <span className="badge badge-success">Active</span>
              ) : (
                <span className="badge badge-warning">Inactive</span>
              )}
              <button
                type="button"
                className="btn-secondary btn-small"
                onClick={handleRefreshWatch}
                disabled={refreshingWatch}
              >
                {refreshingWatch ? 'Refreshing...' : 'Refresh Watch'}
              </button>
            </div>
            <button
              type="button"
              className="btn-danger"
              onClick={handleDisconnect}
              disabled={disconnecting}
            >
              {disconnecting ? 'Disconnecting...' : 'Disconnect Gmail'}
            </button>
          </div>
        ) : (
          <div className="connection-status disconnected">
            <div className="status-indicator">
              <span className="status-dot disconnected"></span>
              <span>Not Connected</span>
            </div>
            <p>Connect your Gmail account to enable AI-powered email responses.</p>
            <button
              type="button"
              className="btn-primary gmail-connect-btn"
              onClick={handleConnectGmail}
              disabled={connecting}
            >
              {connecting ? (
                'Connecting...'
              ) : (
                <>
                  <svg className="gmail-icon" viewBox="0 0 24 24" width="20" height="20">
                    <path fill="currentColor" d="M20 18h-2V9.25L12 13 6 9.25V18H4V6h1.2l6.8 4.25L18.8 6H20m0-2H4c-1.11 0-2 .89-2 2v12a2 2 0 002 2h16a2 2 0 002-2V6a2 2 0 00-2-2z"/>
                  </svg>
                  Connect Gmail
                </>
              )}
            </button>
          </div>
        )}
      </section>

      {/* Settings Form - Only show if connected */}
      {settings?.is_connected && (
        <form onSubmit={handleSubmit} className="settings-form">
          <section className="settings-section">
            <h2>Responder Settings</h2>

            <div className="form-group checkbox-group">
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  name="is_enabled"
                  checked={formData.is_enabled}
                  onChange={handleChange}
                />
                <span className="checkbox-text">Enable Email Responder</span>
              </label>
              <small>When enabled, AI will automatically respond to incoming emails.</small>
            </div>

            <div className="form-group">
              <label htmlFor="max_thread_depth">Thread Context Depth</label>
              <input
                type="number"
                id="max_thread_depth"
                name="max_thread_depth"
                value={formData.max_thread_depth}
                onChange={handleChange}
                min="1"
                max="50"
              />
              <small>Number of previous messages in thread to use as context (max 50)</small>
            </div>

            <div className="form-group">
              <label htmlFor="response_signature">Email Signature</label>
              <textarea
                id="response_signature"
                name="response_signature"
                value={formData.response_signature}
                onChange={handleChange}
                placeholder="Best regards,&#10;Your Business Name&#10;Phone: (555) 123-4567"
                rows={4}
              />
              <small>Signature to append to all AI-generated responses</small>
            </div>
          </section>

          <section className="settings-section">
            <h2>Business Hours</h2>

            <div className="form-group checkbox-group">
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  name="business_hours_enabled"
                  checked={formData.business_hours_enabled}
                  onChange={handleChange}
                />
                <span className="checkbox-text">Enable Business Hours</span>
              </label>
              <small>Use your business hours from profile settings</small>
            </div>

            <div className="form-group checkbox-group">
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  name="auto_reply_outside_hours"
                  checked={formData.auto_reply_outside_hours}
                  onChange={handleChange}
                  disabled={!formData.business_hours_enabled}
                />
                <span className="checkbox-text">Auto-reply Outside Hours</span>
              </label>
              <small>Send an automatic response when emails arrive outside business hours</small>
            </div>

            <div className="form-group">
              <label htmlFor="auto_reply_message">Auto-reply Message</label>
              <textarea
                id="auto_reply_message"
                name="auto_reply_message"
                value={formData.auto_reply_message}
                onChange={handleChange}
                placeholder="Thank you for your email. We're currently outside our business hours. We'll respond as soon as possible during our next business day."
                rows={3}
                disabled={!formData.business_hours_enabled || !formData.auto_reply_outside_hours}
              />
            </div>
          </section>

          <button type="submit" className="save-btn" disabled={saving}>
            {saving ? 'Saving...' : 'Save Settings'}
          </button>
        </form>
      )}
    </div>
  );
}

