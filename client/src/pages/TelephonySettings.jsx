import { useState, useEffect, useRef } from 'react';
import { useAuth } from '../context/AuthContext';
import { api } from '../api/client';
import { LoadingState, ErrorState, EmptyState, ToastContainer } from '../components/ui';
import './TelephonySettings.css';

// Collapsible Section Component
function CollapsibleSection({ title, badge, defaultOpen = true, children }) {
  const [isOpen, setIsOpen] = useState(defaultOpen);

  return (
    <div className={`telephony-section ${isOpen ? '' : 'collapsed'}`}>
      <div className="telephony-section-header" onClick={() => setIsOpen(!isOpen)}>
        <div className="telephony-section-header-left">
          <span className="chevron">{isOpen ? '▼' : '▶'}</span>
          <span className="telephony-section-title">{title}</span>
        </div>
        {badge}
      </div>
      <div className="telephony-section-content">{children}</div>
    </div>
  );
}

const MASKED_VALUE = '••••••••••••';

function CredentialField({
  label,
  field,
  configured,
  revealedValue,
  isAdmin,
  onReveal,
  onCopy,
  isRevealing,
}) {
  const displayValue = revealedValue
    ? revealedValue
    : configured
      ? MASKED_VALUE
      : 'Not configured';

  return (
    <div className="credential-row">
      <div className="credential-label">
        <span>{label}</span>
        <div className="credential-badges">
          {configured ? (
            <span className="status-badge configured">Configured</span>
          ) : (
            <span className="status-badge missing">Not configured</span>
          )}
          <span className="status-badge locked">Locked</span>
        </div>
      </div>
      <div
        className={`credential-value ${revealedValue ? 'revealed' : ''}`}
        title={!isAdmin ? 'Restricted — Admin access required' : undefined}
      >
        {displayValue}
      </div>
      <div className="credential-actions">
        {isAdmin ? (
          <>
            <button
              className="btn btn-secondary btn-small"
              onClick={() => onReveal(field)}
              disabled={!configured || isRevealing}
            >
              {isRevealing ? 'Revealing...' : 'Reveal'}
            </button>
            <button
              className="btn btn-secondary btn-small"
              onClick={() => onCopy(field)}
              disabled={!revealedValue}
            >
              Copy
            </button>
          </>
        ) : (
          <span className="credential-restricted">Restricted — Admin access required</span>
        )}
      </div>
    </div>
  );
}

export default function TelephonySettings() {
  const { user, selectedTenantId } = useAuth();
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
    // Voxie (SMS only)
    voxie_api_key_prefix: '',
    voxie_team_id: '',
    voxie_phone_number: '',
    // Voice
    voice_phone_number: '',
  });

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
    // Voxie (SMS only)
    voxie_api_key: '',
    voxie_team_id: '',
    voxie_phone_number: '',
    // Voice
    voice_phone_number: '',
  });

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);
  const [validating, setValidating] = useState(false);
  const [message, setMessage] = useState({ type: '', text: '' });
  const [copiedUrl, setCopiedUrl] = useState(null);
  const [isEditingCredentials, setIsEditingCredentials] = useState(false);
  const [credentialDrafts, setCredentialDrafts] = useState({
    twilio_account_sid: '',
    twilio_auth_token: '',
    twilio_phone_number: '',
    telnyx_api_key: '',
    telnyx_messaging_profile_id: '',
    telnyx_connection_id: '',
    telnyx_phone_number: '',
    voxie_api_key: '',
    voxie_team_id: '',
    voxie_phone_number: '',
  });
  const [revealedCredentials, setRevealedCredentials] = useState({});
  const [revealingFields, setRevealingFields] = useState({});
  const revealTimers = useRef({});
  const [toasts, setToasts] = useState([]);
  const isGlobalAdmin = user?.is_global_admin;
  const isAdmin = Boolean(isGlobalAdmin);

  useEffect(() => {
    if (!isGlobalAdmin) {
      setLoading(false);
      return;
    }
    if (!selectedTenantId) {
      setLoading(false);
      return;
    }
    fetchConfig();
  }, [selectedTenantId, isGlobalAdmin]);

  useEffect(() => {
    const handleHide = () => {
      clearAllReveals();
    };

    window.addEventListener('blur', handleHide);
    document.addEventListener('visibilitychange', handleHide);

    return () => {
      window.removeEventListener('blur', handleHide);
      document.removeEventListener('visibilitychange', handleHide);
    };
  }, []);

  useEffect(() => {
    clearAllReveals();
    resetCredentialDrafts();
  }, [formData.provider]);

  const resetCredentialDrafts = () => {
    setCredentialDrafts({
      twilio_account_sid: '',
      twilio_auth_token: '',
      twilio_phone_number: '',
      telnyx_api_key: '',
      telnyx_messaging_profile_id: '',
      telnyx_connection_id: '',
      telnyx_phone_number: '',
      voxie_api_key: '',
      voxie_team_id: '',
      voxie_phone_number: '',
    });
  };

  const applyConfigToFormData = (data) => {
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
      voxie_team_id: data.voxie_team_id || '',
      voxie_phone_number: data.voxie_phone_number || '',
      voice_phone_number: data.voice_phone_number || '',
    }));
  };

  const fetchConfig = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getTelephonyConfig();
      setConfig(data);
      applyConfigToFormData(data);
    } catch (err) {
      console.error('Error fetching telephony config:', err);
      if (!err.message?.includes('404')) {
        setError(err.message || 'Failed to load telephony config');
      }
    } finally {
      setLoading(false);
    }
  };

  const saveConfig = async () => {
    setSaving(true);
    setMessage({ type: '', text: '' });

    try {
      const payload = getEffectiveFormData();
      const data = await api.updateTelephonyConfig(payload);
      setConfig(data);
      applyConfigToFormData(data);
      setMessage({ type: 'success', text: 'Configuration saved successfully!' });
      setFormData(prev => ({
        ...prev,
        twilio_auth_token: '',
        telnyx_api_key: '',
        voxie_api_key: '',
      }));
      resetCredentialDrafts();
      setIsEditingCredentials(false);
    } catch (err) {
      setMessage({ type: 'error', text: err.message || 'Failed to save configuration' });
    } finally {
      setSaving(false);
    }
  };

  const validateCredentials = async () => {
    setValidating(true);
    setMessage({ type: '', text: '' });
    const effectiveData = getEffectiveFormData();

    const payload = { provider: formData.provider };

    if (formData.provider === 'twilio') {
      payload.twilio_account_sid = effectiveData.twilio_account_sid;
      payload.twilio_auth_token = effectiveData.twilio_auth_token;
    } else if (formData.provider === 'telnyx') {
      payload.telnyx_api_key = effectiveData.telnyx_api_key;
    } else if (formData.provider === 'voxie') {
      payload.voxie_api_key = effectiveData.voxie_api_key;
      payload.voxie_team_id = effectiveData.voxie_team_id;
    }

    try {
      const data = await api.validateTelephonyCredentials(payload);
      if (data.valid) {
        setMessage({ type: 'success', text: data.message || 'Credentials are valid!' });
      } else {
        setMessage({ type: 'error', text: data.error || 'Invalid credentials' });
      }
    } catch (err) {
      setMessage({ type: 'error', text: err.message || 'Network error. Please try again.' });
    } finally {
      setValidating(false);
    }
  };

  const getEffectiveFormData = () => {
    const overrides = {};
    Object.entries(credentialDrafts).forEach(([key, value]) => {
      if (value && value.trim() !== '') {
        overrides[key] = value.trim();
      }
    });
    return { ...formData, ...overrides };
  };

  const clearAllReveals = () => {
    Object.values(revealTimers.current).forEach(timer => clearTimeout(timer));
    revealTimers.current = {};
    setRevealedCredentials({});
    setRevealingFields({});
  };

  const addToast = (type, text, duration = 2500) => {
    const id = `${Date.now()}-${Math.random()}`;
    setToasts(prev => [...prev, { id, type, message: text, duration }]);
  };

  const removeToast = (id) => {
    setToasts(prev => prev.filter(toast => toast.id !== id));
  };

  const scheduleAutoHide = (field) => {
    if (revealTimers.current[field]) {
      clearTimeout(revealTimers.current[field]);
    }
    revealTimers.current[field] = setTimeout(() => {
      setRevealedCredentials(prev => {
        const next = { ...prev };
        delete next[field];
        return next;
      });
      delete revealTimers.current[field];
    }, 30000);
  };

  const handleRevealCredential = async (field) => {
    if (!isAdmin) {
      return;
    }
    const confirmed = window.confirm('You are about to view a sensitive credential.');
    if (!confirmed) {
      return;
    }

    setRevealingFields(prev => ({ ...prev, [field]: true }));
    try {
      let value = null;
      if (field === 'telnyx_api_key' || field === 'twilio_auth_token' || field === 'voxie_api_key') {
        const data = await api.revealTelephonyCredential(field);
        value = data.value;
      } else {
        value = config[field] || '';
        if (!value) {
          addToast('error', 'Credential not configured');
          return;
        }
        await api.auditTelephonyCredentialAction('reveal', field);
      }

      setRevealedCredentials(prev => ({ ...prev, [field]: value }));
      scheduleAutoHide(field);
    } catch (err) {
      addToast('error', err.message || 'Failed to reveal credential');
    } finally {
      setRevealingFields(prev => ({ ...prev, [field]: false }));
    }
  };

  const handleCopyCredential = async (field) => {
    const value = revealedCredentials[field];
    if (!value) {
      return;
    }
    try {
      await navigator.clipboard.writeText(value);
      await api.auditTelephonyCredentialAction('copy', field);
      addToast('info', 'Copied — handle securely');
    } catch (err) {
      addToast('error', 'Copy failed');
    }
  };

  const getWebhookUrls = () => {
    const baseUrl = window.location.origin;
    if (formData.provider === 'telnyx') {
      return {
        smsInbound: `${baseUrl}/api/v1/telnyx/sms/inbound`,
        smsStatus: `${baseUrl}/api/v1/telnyx/sms/status`,
        voiceInbound: `${baseUrl}/api/v1/voice/telnyx/inbound`,
        voiceStatus: `${baseUrl}/api/v1/voice/telnyx/status`,
      };
    } else if (formData.provider === 'voxie') {
      return {
        smsInbound: `${baseUrl}/api/v1/voxie/sms/inbound`,
        smsStatus: `${baseUrl}/api/v1/voxie/sms/status`,
        voiceInbound: null,
        voiceStatus: null,
      };
    }
    return {
      smsInbound: `${baseUrl}/api/v1/sms/inbound`,
      smsStatus: `${baseUrl}/api/v1/sms/status`,
      voiceInbound: `${baseUrl}/api/v1/voice/inbound`,
      voiceStatus: `${baseUrl}/api/v1/voice/status`,
    };
  };

  const copyToClipboard = async (text, key) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedUrl(key);
      setTimeout(() => setCopiedUrl(null), 2000);
    } catch (err) {
      console.error('Failed to copy:', err);
    }
  };

  // Status badge helper
  const getCredentialStatus = () => {
    if (formData.provider === 'twilio') {
      return config.has_twilio_auth_token ? 'configured' : null;
    } else if (formData.provider === 'telnyx') {
      return config.telnyx_api_key_prefix ? 'configured' : null;
    } else if (formData.provider === 'voxie') {
      return config.voxie_api_key_prefix ? 'configured' : null;
    }
    return null;
  };

  const needsTenant = isGlobalAdmin && !selectedTenantId;

  if (user && !isGlobalAdmin) {
    return (
      <div className="page-container">
        <EmptyState
          icon="lock"
          title="Admin access required"
          description="Telephony credentials are only accessible to global admins."
        />
      </div>
    );
  }

  if (needsTenant) {
    return (
      <div className="page-container">
        <EmptyState
          icon="phone"
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
            icon="phone"
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
  const credentialStatus = getCredentialStatus();
  const telnyxCredentials = [
    {
      field: 'telnyx_api_key',
      label: 'API Key',
      configured: Boolean(config.telnyx_api_key_prefix),
    },
    {
      field: 'telnyx_messaging_profile_id',
      label: 'Messaging Profile ID',
      configured: Boolean(config.telnyx_messaging_profile_id),
    },
    {
      field: 'telnyx_connection_id',
      label: 'Connection ID (Voice)',
      configured: Boolean(config.telnyx_connection_id),
    },
    {
      field: 'telnyx_phone_number',
      label: 'SMS Phone Number',
      configured: Boolean(config.telnyx_phone_number),
    },
  ];
  const twilioCredentials = [
    {
      field: 'twilio_account_sid',
      label: 'Account SID',
      configured: Boolean(config.twilio_account_sid),
    },
    {
      field: 'twilio_auth_token',
      label: 'Auth Token',
      configured: Boolean(config.has_twilio_auth_token),
    },
    {
      field: 'twilio_phone_number',
      label: 'SMS Phone Number',
      configured: Boolean(config.twilio_phone_number),
    },
  ];
  const voxieCredentials = [
    {
      field: 'voxie_api_key',
      label: 'API Key',
      configured: Boolean(config.voxie_api_key_prefix),
    },
    {
      field: 'voxie_team_id',
      label: 'Team ID',
      configured: Boolean(config.voxie_team_id),
    },
    {
      field: 'voxie_phone_number',
      label: 'SMS Phone Number',
      configured: Boolean(config.voxie_phone_number),
    },
  ];

  return (
    <div className="telephony-container">
      <h1>Telephony Settings</h1>
      <p className="subtitle">Configure SMS and Voice provider for this tenant</p>

      {message.text && (
        <div className={`telephony-alert ${message.type}`}>{message.text}</div>
      )}
      <ToastContainer toasts={toasts} removeToast={removeToast} />

      {/* Provider & Features Section */}
      <CollapsibleSection title="Provider & Features" defaultOpen={true}>
        <div style={{ marginBottom: '16px' }}>
          <label style={{ fontSize: '0.85rem', fontWeight: 500, color: '#666', marginBottom: '8px', display: 'block' }}>
            Select Provider
          </label>
          <div className="provider-radio-row">
            <label className="provider-radio-option">
              <input
                type="radio"
                name="provider"
                value="twilio"
                checked={formData.provider === 'twilio'}
                onChange={(e) => setFormData({ ...formData, provider: e.target.value })}
              />
              <span className="provider-name">Twilio</span>
              <span className="provider-desc">- SMS & Voice</span>
            </label>
            <label className="provider-radio-option">
              <input
                type="radio"
                name="provider"
                value="telnyx"
                checked={formData.provider === 'telnyx'}
                onChange={(e) => setFormData({ ...formData, provider: e.target.value })}
              />
              <span className="provider-name">Telnyx</span>
              <span className="provider-desc">- SMS & Voice</span>
            </label>
            <label className="provider-radio-option">
              <input
                type="radio"
                name="provider"
                value="voxie"
                checked={formData.provider === 'voxie'}
                onChange={(e) => setFormData({ ...formData, provider: e.target.value, voice_enabled: false })}
              />
              <span className="provider-name">Voxie</span>
              <span className="provider-desc">- SMS only</span>
            </label>
          </div>
        </div>

        <div>
          <label style={{ fontSize: '0.85rem', fontWeight: 500, color: '#666', marginBottom: '8px', display: 'block' }}>
            Enabled Features
          </label>
          <div className="feature-toggles">
            <label className="toggle-item">
              <input
                type="checkbox"
                checked={formData.sms_enabled}
                onChange={(e) => setFormData({ ...formData, sms_enabled: e.target.checked })}
              />
              <span className="toggle-label">SMS</span>
            </label>
            <label className={`toggle-item ${formData.provider === 'voxie' ? 'disabled' : ''}`}>
              <input
                type="checkbox"
                checked={formData.voice_enabled}
                onChange={(e) => setFormData({ ...formData, voice_enabled: e.target.checked })}
                disabled={formData.provider === 'voxie'}
              />
              <span className="toggle-label">Voice</span>
              {formData.provider === 'voxie' && <span className="toggle-badge">N/A</span>}
            </label>
          </div>
        </div>
      </CollapsibleSection>

      {/* Credentials Section */}
      <CollapsibleSection
        title="Credentials"
        defaultOpen={false}
        badge={credentialStatus && <span className="status-badge configured">Configured</span>}
      >
        <div className="credentials-header">
          <p className="help-text credential-edit-note">
            Sensitive credentials are hidden by default and auto-hide after 30 seconds or page blur.
          </p>
          {isAdmin && (
            <button
              className="btn btn-secondary btn-small"
              onClick={() => {
                if (isEditingCredentials) {
                  setIsEditingCredentials(false);
                  resetCredentialDrafts();
                } else {
                  setIsEditingCredentials(true);
                }
              }}
            >
              {isEditingCredentials ? 'Exit Edit Mode' : 'Edit Credentials'}
            </button>
          )}
        </div>

        {!isEditingCredentials && formData.provider === 'twilio' && (
          <div className="credentials-locked">
            {twilioCredentials.map(credential => (
              <CredentialField
                key={credential.field}
                label={credential.label}
                field={credential.field}
                configured={credential.configured}
                revealedValue={revealedCredentials[credential.field]}
                isAdmin={isAdmin}
                onReveal={handleRevealCredential}
                onCopy={handleCopyCredential}
                isRevealing={Boolean(revealingFields[credential.field])}
              />
            ))}
          </div>
        )}

        {!isEditingCredentials && formData.provider === 'telnyx' && (
          <div className="credentials-locked">
            {telnyxCredentials.map(credential => (
              <CredentialField
                key={credential.field}
                label={credential.label}
                field={credential.field}
                configured={credential.configured}
                revealedValue={revealedCredentials[credential.field]}
                isAdmin={isAdmin}
                onReveal={handleRevealCredential}
                onCopy={handleCopyCredential}
                isRevealing={Boolean(revealingFields[credential.field])}
              />
            ))}
          </div>
        )}

        {!isEditingCredentials && formData.provider === 'voxie' && (
          <div className="credentials-locked">
            {voxieCredentials.map(credential => (
              <CredentialField
                key={credential.field}
                label={credential.label}
                field={credential.field}
                configured={credential.configured}
                revealedValue={revealedCredentials[credential.field]}
                isAdmin={isAdmin}
                onReveal={handleRevealCredential}
                onCopy={handleCopyCredential}
                isRevealing={Boolean(revealingFields[credential.field])}
              />
            ))}
          </div>
        )}

        {isEditingCredentials && formData.provider === 'twilio' && (
          <div className="credentials-inline">
            <p className="help-text">Enter new values to rotate credentials.</p>
            <div className="credentials-row">
              <div className="form-group">
                <label>Account SID</label>
                <input
                  type="text"
                  value={credentialDrafts.twilio_account_sid}
                  onChange={(e) => setCredentialDrafts({ ...credentialDrafts, twilio_account_sid: e.target.value })}
                />
              </div>
              <div className="form-group">
                <label>Auth Token</label>
                <input
                  type="password"
                  value={credentialDrafts.twilio_auth_token}
                  onChange={(e) => setCredentialDrafts({ ...credentialDrafts, twilio_auth_token: e.target.value })}
                />
              </div>
            </div>
            <div className="form-group">
              <label>SMS Phone Number</label>
              <input
                type="tel"
                value={credentialDrafts.twilio_phone_number}
                onChange={(e) => setCredentialDrafts({ ...credentialDrafts, twilio_phone_number: e.target.value })}
              />
            </div>
            <div className="btn-row">
              <button
                className="btn btn-secondary"
                onClick={validateCredentials}
                disabled={validating || !getEffectiveFormData().twilio_account_sid || !getEffectiveFormData().twilio_auth_token}
              >
                {validating ? 'Testing...' : 'Test Credentials'}
              </button>
            </div>
          </div>
        )}

        {isEditingCredentials && formData.provider === 'telnyx' && (
          <div className="credentials-inline">
            <p className="help-text">Enter new values to rotate credentials.</p>
            <div className="credentials-row">
              <div className="form-group">
                <label>API Key</label>
                <input
                  type="password"
                  value={credentialDrafts.telnyx_api_key}
                  onChange={(e) => setCredentialDrafts({ ...credentialDrafts, telnyx_api_key: e.target.value })}
                />
              </div>
              <div className="form-group">
                <label>Messaging Profile ID</label>
                <input
                  type="text"
                  value={credentialDrafts.telnyx_messaging_profile_id}
                  onChange={(e) => setCredentialDrafts({ ...credentialDrafts, telnyx_messaging_profile_id: e.target.value })}
                />
              </div>
            </div>
            <div className="credentials-row">
              <div className="form-group">
                <label>Connection ID (Voice)</label>
                <input
                  type="text"
                  value={credentialDrafts.telnyx_connection_id}
                  onChange={(e) => setCredentialDrafts({ ...credentialDrafts, telnyx_connection_id: e.target.value })}
                />
              </div>
              <div className="form-group">
                <label>SMS Phone Number</label>
                <input
                  type="tel"
                  value={credentialDrafts.telnyx_phone_number}
                  onChange={(e) => setCredentialDrafts({ ...credentialDrafts, telnyx_phone_number: e.target.value })}
                />
              </div>
            </div>
            <div className="btn-row">
              <button
                className="btn btn-secondary"
                onClick={validateCredentials}
                disabled={validating || !getEffectiveFormData().telnyx_api_key}
              >
                {validating ? 'Testing...' : 'Test Credentials'}
              </button>
            </div>
          </div>
        )}

        {isEditingCredentials && formData.provider === 'voxie' && (
          <div className="credentials-inline">
            <p className="help-text">Enter new values to rotate credentials.</p>
            <div className="credentials-row">
              <div className="form-group">
                <label>API Key</label>
                <input
                  type="password"
                  value={credentialDrafts.voxie_api_key}
                  onChange={(e) => setCredentialDrafts({ ...credentialDrafts, voxie_api_key: e.target.value })}
                />
              </div>
              <div className="form-group">
                <label>Team ID</label>
                <input
                  type="text"
                  value={credentialDrafts.voxie_team_id}
                  onChange={(e) => setCredentialDrafts({ ...credentialDrafts, voxie_team_id: e.target.value })}
                />
              </div>
            </div>
            <div className="form-group">
              <label>SMS Phone Number</label>
              <input
                type="tel"
                value={credentialDrafts.voxie_phone_number}
                onChange={(e) => setCredentialDrafts({ ...credentialDrafts, voxie_phone_number: e.target.value })}
              />
            </div>
            <div className="btn-row">
              <button
                className="btn btn-secondary"
                onClick={validateCredentials}
                disabled={validating || !getEffectiveFormData().voxie_api_key || !getEffectiveFormData().voxie_team_id}
              >
                {validating ? 'Testing...' : 'Test Credentials'}
              </button>
            </div>
          </div>
        )}
      </CollapsibleSection>

      {/* Voice Phone Number (if different from SMS) */}
      {formData.voice_enabled && (
        <CollapsibleSection title="Voice Settings" defaultOpen={false}>
          <div className="form-group">
            <label>Voice Phone Number (optional)</label>
            <input
              type="tel"
              value={formData.voice_phone_number}
              onChange={(e) => setFormData({ ...formData, voice_phone_number: e.target.value })}
              placeholder="Leave empty to use SMS number"
            />
            <p className="help-text">Use a different number for voice calls</p>
          </div>
        </CollapsibleSection>
      )}

      {/* Webhooks Section */}
      <CollapsibleSection title="Webhook URLs" defaultOpen={false}>
        <p className="help-text" style={{ marginTop: 0, marginBottom: '12px' }}>
          Configure these URLs in your {formData.provider === 'voxie' ? 'Voxie' : formData.provider === 'telnyx' ? 'Telnyx' : 'Twilio'} dashboard
        </p>
        <div className="webhook-grid">
          <div className="webhook-item">
            <label>SMS Inbound</label>
            <div className="webhook-url-container">
              <code>{webhookUrls.smsInbound}</code>
              <button
                className={`copy-btn ${copiedUrl === 'smsInbound' ? 'copied' : ''}`}
                onClick={() => copyToClipboard(webhookUrls.smsInbound, 'smsInbound')}
              >
                {copiedUrl === 'smsInbound' ? 'Copied' : 'Copy'}
              </button>
            </div>
          </div>
          <div className="webhook-item">
            <label>SMS Status</label>
            <div className="webhook-url-container">
              <code>{webhookUrls.smsStatus}</code>
              <button
                className={`copy-btn ${copiedUrl === 'smsStatus' ? 'copied' : ''}`}
                onClick={() => copyToClipboard(webhookUrls.smsStatus, 'smsStatus')}
              >
                {copiedUrl === 'smsStatus' ? 'Copied' : 'Copy'}
              </button>
            </div>
          </div>
          {formData.voice_enabled && webhookUrls.voiceInbound && (
            <>
              <div className="webhook-item">
                <label>Voice Inbound</label>
                <div className="webhook-url-container">
                  <code>{webhookUrls.voiceInbound}</code>
                  <button
                    className={`copy-btn ${copiedUrl === 'voiceInbound' ? 'copied' : ''}`}
                    onClick={() => copyToClipboard(webhookUrls.voiceInbound, 'voiceInbound')}
                  >
                    {copiedUrl === 'voiceInbound' ? 'Copied' : 'Copy'}
                  </button>
                </div>
              </div>
              <div className="webhook-item">
                <label>Voice Status</label>
                <div className="webhook-url-container">
                  <code>{webhookUrls.voiceStatus}</code>
                  <button
                    className={`copy-btn ${copiedUrl === 'voiceStatus' ? 'copied' : ''}`}
                    onClick={() => copyToClipboard(webhookUrls.voiceStatus, 'voiceStatus')}
                  >
                    {copiedUrl === 'voiceStatus' ? 'Copied' : 'Copy'}
                  </button>
                </div>
              </div>
            </>
          )}
        </div>
      </CollapsibleSection>

      {/* Save Button */}
      <div className="action-row" style={{ borderTop: 'none', marginTop: '16px', paddingTop: 0 }}>
        <button className="btn btn-primary" onClick={saveConfig} disabled={saving}>
          {saving ? 'Saving...' : 'Save Configuration'}
        </button>
      </div>
    </div>
  );
}
