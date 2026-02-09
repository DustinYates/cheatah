import { useState, useEffect, useCallback } from 'react';
import { useAuth } from '../context/AuthContext';
import { api } from '../api/client';
import { LoadingState, ErrorState, EmptyState } from '../components/ui';
import { Phone, Settings, Save, RefreshCw } from 'lucide-react';
import './CustomerSupportSettings.css';

export default function CustomerSupportSettings() {
  const { user, selectedTenantId } = useAuth();
  const [config, setConfig] = useState({
    is_enabled: false,
    telnyx_agent_id: '',
    telnyx_phone_number: '',
    telnyx_messaging_profile_id: '',
    support_sms_enabled: true,
    support_voice_enabled: true,
    handoff_mode: 'take_message',
    transfer_number: '',
    system_prompt_override: '',
    routing_rules: {
      business_hours_only: false,
      fallback_to_human: true,
      max_conversation_turns: 10,
      auto_lookup_customer: true,
    },
  });
  const [originalConfig, setOriginalConfig] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [toast, setToast] = useState(null);

  const needsTenant = user?.is_global_admin && !selectedTenantId;

  const showToast = useCallback((message, type = 'success') => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 3000);
  }, []);

  const fetchConfig = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getCustomerSupportConfig();
      if (data) {
        setConfig({
          is_enabled: data.is_enabled || false,
          telnyx_agent_id: data.telnyx_agent_id || '',
          telnyx_phone_number: data.telnyx_phone_number || '',
          telnyx_messaging_profile_id: data.telnyx_messaging_profile_id || '',
          support_sms_enabled: data.support_sms_enabled ?? true,
          support_voice_enabled: data.support_voice_enabled ?? true,
          handoff_mode: data.handoff_mode || 'take_message',
          transfer_number: data.transfer_number || '',
          system_prompt_override: data.system_prompt_override || '',
          routing_rules: data.routing_rules || {
            business_hours_only: false,
            fallback_to_human: true,
            max_conversation_turns: 10,
            auto_lookup_customer: true,
          },
        });
        setOriginalConfig(data);
      }
    } catch (err) {
      if (!err.message?.includes('Not Found')) {
        setError(err.message);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!needsTenant) {
      fetchConfig();
    } else {
      setLoading(false);
    }
  }, [fetchConfig, needsTenant, selectedTenantId]);

  const handleSave = async () => {
    setSaving(true);
    try {
      await api.updateCustomerSupportConfig(config);
      setOriginalConfig(config);
      showToast('Settings saved successfully');
    } catch (err) {
      showToast(err.message || 'Failed to save settings', 'error');
    } finally {
      setSaving(false);
    }
  };

  const updateConfig = (field, value) => {
    setConfig(prev => ({ ...prev, [field]: value }));
  };

  const updateRoutingRule = (field, value) => {
    setConfig(prev => ({
      ...prev,
      routing_rules: { ...prev.routing_rules, [field]: value },
    }));
  };

  const hasChanges = JSON.stringify(config) !== JSON.stringify(originalConfig);

  if (needsTenant) {
    return (
      <div className="customer-support-settings">
        <EmptyState
          icon={<Settings size={32} strokeWidth={1.5} />}
          title="Select a tenant"
          description="Please select a tenant from the dropdown above to configure customer support settings."
        />
      </div>
    );
  }

  if (loading) {
    return <LoadingState message="Loading settings..." fullPage />;
  }

  if (error) {
    return <ErrorState message={error} onRetry={fetchConfig} />;
  }

  return (
    <div className="customer-support-settings">
      {toast && (
        <div className={`toast toast-${toast.type}`}>
          {toast.message}
        </div>
      )}

      <div className="page-header">
        <div>
          <h1>Customer Support Settings</h1>
          <p className="subtitle">Configure your dedicated customer support AI agent</p>
        </div>
        <div className="header-actions">
          <button className="btn-icon" onClick={fetchConfig} title="Refresh">
            <RefreshCw size={16} />
          </button>
          <button
            className="btn-primary"
            onClick={handleSave}
            disabled={saving || !hasChanges}
          >
            <Save size={14} />
            <span>{saving ? 'Saving...' : 'Save Changes'}</span>
          </button>
        </div>
      </div>

      <div className="settings-content">
        {/* Enable/Disable Section */}
        <div className="settings-section">
          <div className="section-header">
            <h2>Customer Support Agent</h2>
            <label className="toggle">
              <input
                type="checkbox"
                checked={config.is_enabled}
                onChange={(e) => updateConfig('is_enabled', e.target.checked)}
              />
              <span className="toggle-slider"></span>
              <span className="toggle-label">{config.is_enabled ? 'Enabled' : 'Disabled'}</span>
            </label>
          </div>
          <p className="section-description">
            Enable a dedicated support line for existing customers to get help with their accounts.
          </p>
        </div>

        {/* Telnyx Configuration - Global Admin Only */}
        {user?.is_global_admin && (
        <div className="settings-section">
          <h2>Telnyx Configuration</h2>
          <p className="section-description">
            Configure the Telnyx AI agent and phone number for customer support.
          </p>

          <div className="form-group">
            <label>Support Phone Number</label>
            <input
              type="text"
              value={config.telnyx_phone_number}
              onChange={(e) => updateConfig('telnyx_phone_number', e.target.value)}
              placeholder="+1234567890"
            />
            <span className="help-text">Dedicated phone number for customer support calls/SMS</span>
          </div>

          <div className="form-group">
            <label>Telnyx Agent ID</label>
            <input
              type="text"
              value={config.telnyx_agent_id}
              onChange={(e) => updateConfig('telnyx_agent_id', e.target.value)}
              placeholder="assistant-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
            />
            <span className="help-text">AI assistant configured for customer support</span>
          </div>

          <div className="form-group">
            <label>Messaging Profile ID</label>
            <input
              type="text"
              value={config.telnyx_messaging_profile_id}
              onChange={(e) => updateConfig('telnyx_messaging_profile_id', e.target.value)}
              placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
            />
          </div>
        </div>
        )}

        {/* Channel Configuration */}
        <div className="settings-section">
          <h2>Channels</h2>
          <p className="section-description">Enable or disable support channels.</p>

          <div className="checkbox-group">
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={config.support_voice_enabled}
                onChange={(e) => updateConfig('support_voice_enabled', e.target.checked)}
              />
              <span>Voice Calls</span>
            </label>
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={config.support_sms_enabled}
                onChange={(e) => updateConfig('support_sms_enabled', e.target.checked)}
              />
              <span>SMS</span>
            </label>
          </div>
        </div>

        {/* Handoff Settings */}
        <div className="settings-section">
          <h2>Escalation & Handoff</h2>
          <p className="section-description">Configure how calls are transferred to human agents.</p>

          <div className="form-group">
            <label>Handoff Mode</label>
            <select
              value={config.handoff_mode}
              onChange={(e) => updateConfig('handoff_mode', e.target.value)}
            >
              <option value="take_message">Take Message</option>
              <option value="live_transfer">Live Transfer</option>
            </select>
          </div>

          <div className="form-group">
            <label>Transfer Number</label>
            <input
              type="text"
              value={config.transfer_number}
              onChange={(e) => updateConfig('transfer_number', e.target.value)}
              placeholder="+1234567890"
              disabled={config.handoff_mode !== 'live_transfer'}
            />
            <span className="help-text">Human support line for live transfers</span>
          </div>
        </div>

        {/* Routing Rules */}
        <div className="settings-section">
          <h2>Routing Rules</h2>

          <div className="checkbox-group">
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={config.routing_rules.auto_lookup_customer}
                onChange={(e) => updateRoutingRule('auto_lookup_customer', e.target.checked)}
              />
              <span>Auto-lookup customer by phone number</span>
            </label>
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={config.routing_rules.fallback_to_human}
                onChange={(e) => updateRoutingRule('fallback_to_human', e.target.checked)}
              />
              <span>Fallback to human if AI can't help</span>
            </label>
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={config.routing_rules.business_hours_only}
                onChange={(e) => updateRoutingRule('business_hours_only', e.target.checked)}
              />
              <span>Only active during business hours</span>
            </label>
          </div>

          <div className="form-group">
            <label>Max Conversation Turns</label>
            <input
              type="number"
              value={config.routing_rules.max_conversation_turns}
              onChange={(e) => updateRoutingRule('max_conversation_turns', parseInt(e.target.value) || 10)}
              min="1"
              max="50"
            />
            <span className="help-text">Maximum back-and-forth exchanges before escalation</span>
          </div>
        </div>

        {/* System Prompt Override */}
        <div className="settings-section">
          <h2>System Prompt Override</h2>
          <p className="section-description">
            Custom instructions for the support AI agent. Leave empty to use the default Telnyx agent prompt.
          </p>

          <div className="form-group">
            <textarea
              value={config.system_prompt_override}
              onChange={(e) => updateConfig('system_prompt_override', e.target.value)}
              placeholder="Enter custom system prompt..."
              rows={6}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
