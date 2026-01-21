import { useState, useCallback, useEffect, useRef } from 'react';
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
    is_enabled: true,
    lead_capture_subject_prefixes: [],
  });
  const [newPrefix, setNewPrefix] = useState('');

  // Subject-specific SMS templates state
  const [subjectTemplates, setSubjectTemplates] = useState({});
  const [newTemplateSubject, setNewTemplateSubject] = useState('');
  const [newTemplateMessage, setNewTemplateMessage] = useState('');
  const [editingTemplate, setEditingTemplate] = useState(null);
  const templateSubjectInputRef = useRef(null);

  const fetchSettings = useCallback(() => api.getEmailSettings(), []);
  const { data: settings, loading, error, refetch } = useFetchData(fetchSettings);

  // Fetch SMS settings for subject templates
  const fetchSmsSettings = useCallback(() => api.getSmsSettings(), []);
  const { data: smsSettings, loading: smsLoading, refetch: refetchSms } = useFetchData(fetchSmsSettings);

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
        is_enabled: settings.is_enabled ?? true,
        lead_capture_subject_prefixes: settings.lead_capture_subject_prefixes || [],
      });
    }
  }, [settings]);

  // Initialize subject templates from SMS settings
  useEffect(() => {
    if (smsSettings?.followup_subject_templates) {
      setSubjectTemplates(smsSettings.followup_subject_templates);
    }
  }, [smsSettings]);

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

  // Subject template handlers
  const handleAddTemplate = () => {
    const subject = newTemplateSubject.trim();
    const message = newTemplateMessage.trim();
    if (subject && message) {
      setSubjectTemplates(prev => ({
        ...prev,
        [subject]: message,
      }));
      setNewTemplateSubject('');
      setNewTemplateMessage('');
      // Auto-focus subject input for adding multiple templates quickly
      setTimeout(() => templateSubjectInputRef.current?.focus(), 0);
    }
  };

  const handleRemoveTemplate = (subject) => {
    setSubjectTemplates(prev => {
      const updated = { ...prev };
      delete updated[subject];
      return updated;
    });
  };

  const handleEditTemplate = (subject) => {
    setEditingTemplate(subject);
    setNewTemplateSubject(subject);
    setNewTemplateMessage(subjectTemplates[subject]);
  };

  const handleSaveEditTemplate = () => {
    const subject = newTemplateSubject.trim();
    const message = newTemplateMessage.trim();
    if (subject && message) {
      setSubjectTemplates(prev => {
        const updated = { ...prev };
        // If subject changed, remove old key
        if (editingTemplate && editingTemplate !== subject) {
          delete updated[editingTemplate];
        }
        updated[subject] = message;
        return updated;
      });
      setNewTemplateSubject('');
      setNewTemplateMessage('');
      setEditingTemplate(null);
    }
  };

  const handleCancelEditTemplate = () => {
    setNewTemplateSubject('');
    setNewTemplateMessage('');
    setEditingTemplate(null);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setFormError('');
    setSuccess('');
    setSaving(true);

    try {
      // Save email settings
      await api.updateEmailSettings(formData);

      // Save SMS subject templates if there are any configured
      if (Object.keys(subjectTemplates).length > 0 || smsSettings?.followup_subject_templates) {
        await api.updateSmsSettings({
          ...smsSettings,
          followup_subject_templates: Object.keys(subjectTemplates).length > 0 ? subjectTemplates : null,
        });
        refetchSms();
      }

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
          {/* Enable/Disable Email Processing */}
          <section className="settings-section">
            <h2>Email Processing</h2>
            <div className="form-group">
              <label className="email-processing-toggle">
                <span className="email-processing-toggle__text">
                  {formData.is_enabled ? 'Email processing enabled' : 'Email processing disabled'}
                </span>
                <span className="email-processing-toggle__control">
                  <input
                    id="email-processing-toggle"
                    type="checkbox"
                    checked={formData.is_enabled}
                    onChange={(e) => setFormData(prev => ({ ...prev, is_enabled: e.target.checked }))}
                    className="email-processing-toggle__input"
                    aria-describedby="email-processing-help"
                  />
                  <span className="email-processing-toggle__switch" aria-hidden="true"></span>
                </span>
              </label>
              <small id="email-processing-help">
                When enabled, incoming emails will be monitored and leads will be created based on the configured subject prefixes below.
              </small>
            </div>
          </section>

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

      {/* Subject-Specific SMS Templates Section - Available for all tenants */}
      <section className="settings-section">
        <h2>SMS Follow-up Templates</h2>
        <p className="section-description">
          Configure custom SMS messages based on lead source or email subject.
          When a lead is captured, the follow-up SMS will use the template
          that matches the trigger.
        </p>

        <div className="form-group">
          <label>Subject-Specific Templates</label>

          {Object.keys(subjectTemplates).length === 0 ? (
            <div className="template-empty">
              No subject-specific templates configured. Default follow-up messages will be used.
            </div>
          ) : (
            <div className="template-list">
              {Object.entries(subjectTemplates).map(([subject, message]) => (
                <div key={subject} className="template-item">
                  <div className="template-header">
                    <span className="template-subject">Subject: "{subject}"</span>
                    <div className="template-actions">
                      <button
                        type="button"
                        className="template-edit"
                        onClick={() => handleEditTemplate(subject)}
                        title="Edit template"
                      >
                        Edit
                      </button>
                      <button
                        type="button"
                        className="template-remove"
                        onClick={() => handleRemoveTemplate(subject)}
                        title="Remove template"
                      >
                        ×
                      </button>
                    </div>
                  </div>
                  <div className="template-message">{message}</div>
                </div>
              ))}
            </div>
          )}

          <div className="template-add-form">
            <h4>{editingTemplate ? 'Edit Template' : 'Add New Template'}</h4>
            <div className="template-form-group">
              <label htmlFor="template-subject">Subject Prefix</label>
              <input
                ref={templateSubjectInputRef}
                id="template-subject"
                type="text"
                value={newTemplateSubject}
                onChange={(e) => setNewTemplateSubject(e.target.value)}
                placeholder="e.g., Get In Touch"
                className="template-input"
              />
            </div>
            <div className="template-form-group">
              <label htmlFor="template-message">SMS Message</label>
              <textarea
                id="template-message"
                value={newTemplateMessage}
                onChange={(e) => setNewTemplateMessage(e.target.value)}
                placeholder="Hi, {first_name}. Thank you for reaching out..."
                className="template-textarea"
                rows={3}
              />
              <small className="template-help">
                Use {'{first_name}'} or {'{name}'} as placeholders for the lead's name.
              </small>
            </div>
            <div className="template-form-actions">
              {editingTemplate ? (
                <>
                  <button
                    type="button"
                    className="btn-secondary"
                    onClick={handleCancelEditTemplate}
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    className="btn-primary"
                    onClick={handleSaveEditTemplate}
                    disabled={!newTemplateSubject.trim() || !newTemplateMessage.trim()}
                  >
                    Save Changes
                  </button>
                </>
              ) : (
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={handleAddTemplate}
                  disabled={!newTemplateSubject.trim() || !newTemplateMessage.trim()}
                >
                  Add Template
                </button>
              )}
            </div>
          </div>

          <button
            type="button"
            className="save-btn"
            disabled={saving}
            onClick={async () => {
              setSaving(true);
              setFormError('');
              setSuccess('');
              try {
                // Add any pending template from the form first
                let templatesToSave = { ...subjectTemplates };
                const pendingSubject = newTemplateSubject.trim();
                const pendingMessage = newTemplateMessage.trim();
                if (pendingSubject && pendingMessage) {
                  templatesToSave[pendingSubject] = pendingMessage;
                  // Clear the form
                  setNewTemplateSubject('');
                  setNewTemplateMessage('');
                  setEditingTemplate(null);
                  // Update local state too
                  setSubjectTemplates(templatesToSave);
                }

                await api.updateSmsSettings({
                  ...smsSettings,
                  followup_subject_templates: Object.keys(templatesToSave).length > 0 ? templatesToSave : null,
                });
                refetchSms();
                setSuccess('SMS templates saved successfully');
              } catch (err) {
                setFormError(err.message || 'Failed to save SMS templates');
              } finally {
                setSaving(false);
              }
            }}
          >
            {saving ? 'Saving...' : 'Save SMS Templates'}
          </button>
        </div>
      </section>
    </div>
  );
}
