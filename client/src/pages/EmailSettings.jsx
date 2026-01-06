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
    lead_capture_subject_prefixes: [],
  });
  const [newPrefix, setNewPrefix] = useState('');

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
        lead_capture_subject_prefixes: settings.lead_capture_subject_prefixes || [],
      });
    }
  }, [settings]);

  const handleAddPrefix = () => {
    const trimmed = newPrefix.trim();
    if (trimmed && !formData.lead_capture_subject_prefixes.includes(trimmed)) {
      setFormData(prev => ({
        ...prev,
        lead_capture_subject_prefixes: [...prev.lead_capture_subject_prefixes, trimmed],
      }));
      setNewPrefix('');
    }
  };

  const handleRemovePrefix = (prefixToRemove) => {
    setFormData(prev => ({
      ...prev,
      lead_capture_subject_prefixes: prev.lead_capture_subject_prefixes.filter(p => p !== prefixToRemove),
    }));
  };

  const handlePrefixKeyDown = (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleAddPrefix();
    }
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
    if (!window.confirm('Are you sure you want to disconnect Gmail? Lead capture from emails will stop working.')) {
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
          description="Please select a tenant from the dropdown above to manage their email lead capture settings."
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
            description="Please select a tenant from the dropdown above to manage their email lead capture settings."
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
      <h1>Email Lead Capture</h1>
      <p className="description">
        Connect your Gmail account to automatically capture leads from incoming emails.
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
            <p>Connect your Gmail account to enable lead capture from emails.</p>
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
            <h2>Lead Capture</h2>
            <p className="section-description">
              Configure which email subjects should create leads. Only emails with subjects that start with one of these prefixes will create leads.
            </p>

            <div className="form-group">
              <label>Subject Prefixes for Lead Capture</label>
              <div className="prefix-list">
                {formData.lead_capture_subject_prefixes.length === 0 ? (
                  <div className="prefix-empty">No prefixes configured. No leads will be created from emails.</div>
                ) : (
                  formData.lead_capture_subject_prefixes.map((prefix, index) => (
                    <div key={index} className="prefix-item">
                      <span className="prefix-text">{prefix}</span>
                      <button
                        type="button"
                        className="prefix-remove"
                        onClick={() => handleRemovePrefix(prefix)}
                        title="Remove prefix"
                      >
                        ×
                      </button>
                    </div>
                  ))
                )}
              </div>
              <div className="prefix-add-row">
                <input
                  type="text"
                  value={newPrefix}
                  onChange={(e) => setNewPrefix(e.target.value)}
                  onKeyDown={handlePrefixKeyDown}
                  placeholder="Enter a subject prefix..."
                  className="prefix-input"
                />
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={handleAddPrefix}
                  disabled={!newPrefix.trim()}
                >
                  Add Prefix
                </button>
              </div>
              <small>
                Emails with subjects starting with these prefixes (case-insensitive) will create leads. 
                Examples: "Email Capture from Booking Page", "Get In Touch Form Submission"
              </small>
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
