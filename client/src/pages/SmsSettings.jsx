import { useState, useEffect, useMemo, useCallback } from 'react';
import { useAuth } from '../context/AuthContext';
import { LoadingState, ErrorState, EmptyState } from '../components/ui';

const API_BASE = '/api/v1';

const defaultBusinessHours = {
  monday: { start: '09:00', end: '17:00', closed: false },
  tuesday: { start: '09:00', end: '17:00', closed: false },
  wednesday: { start: '09:00', end: '17:00', closed: false },
  thursday: { start: '09:00', end: '17:00', closed: false },
  friday: { start: '09:00', end: '17:00', closed: false },
  saturday: { start: '', end: '', closed: true },
  sunday: { start: '', end: '', closed: true },
};

const dayLabels = [
  { key: 'monday', label: 'Mon', fullLabel: 'Monday' },
  { key: 'tuesday', label: 'Tue', fullLabel: 'Tuesday' },
  { key: 'wednesday', label: 'Wed', fullLabel: 'Wednesday' },
  { key: 'thursday', label: 'Thu', fullLabel: 'Thursday' },
  { key: 'friday', label: 'Fri', fullLabel: 'Friday' },
  { key: 'saturday', label: 'Sat', fullLabel: 'Saturday' },
  { key: 'sunday', label: 'Sun', fullLabel: 'Sunday' },
];

const normalizeBusinessHours = (hours) => {
  if (!hours) return defaultBusinessHours;
  const normalized = {};
  for (const day of dayLabels) {
    const dayData = hours[day.key] || {};
    const isClosed = dayData.closed === true || (!dayData.start && !dayData.end);
    normalized[day.key] = {
      start: dayData.start || '09:00',
      end: dayData.end || '17:00',
      closed: isClosed,
    };
  }
  return normalized;
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
    followup_enabled: false,
    followup_delay_minutes: 5,
    followup_sources: ['email'],
    followup_initial_message: '',
  });
  const [originalSettings, setOriginalSettings] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState(null);

  const isDirty = useMemo(() => {
    if (!originalSettings) return false;
    return JSON.stringify(settings) !== JSON.stringify(originalSettings);
  }, [settings, originalSettings]);

  const showToast = useCallback((message, type = 'success') => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 3000);
  }, []);

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
      const response = await fetch(`${API_BASE}/sms/settings`, { headers });
      if (response.ok) {
        const data = await response.json();
        const normalizedSettings = {
          ...data,
          business_hours: normalizeBusinessHours(data.business_hours),
        };
        setSettings(normalizedSettings);
        setOriginalSettings(normalizedSettings);
      } else if (response.status === 404) {
        const defaultState = {
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
          followup_sources: ['email'],
          followup_initial_message: '',
        };
        setSettings(defaultState);
        setOriginalSettings(defaultState);
      } else {
        const errorData = await response.json().catch(() => ({}));
        setError(errorData.detail || 'Failed to load SMS settings');
      }
    } catch (err) {
      if (err.message?.includes('Not Found') || err.message?.includes('not found')) {
        const defaultState = {
          is_enabled: false,
          phone_number: null,
          auto_reply_enabled: false,
          auto_reply_message: '',
          initial_outreach_message: "Hi! Thanks for reaching out...",
          business_hours_enabled: false,
          timezone: 'America/Chicago',
          business_hours: defaultBusinessHours,
          followup_enabled: false,
          followup_delay_minutes: 5,
          followup_sources: ['email'],
          followup_initial_message: '',
        };
        setSettings(defaultState);
        setOriginalSettings(defaultState);
      } else {
        setError(err.message || 'Failed to load SMS settings');
      }
    } finally {
      setLoading(false);
    }
  };

  const saveSettings = async () => {
    setSaving(true);
    try {
      const headers = {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
      };
      if (user?.is_global_admin && selectedTenantId) {
        headers['X-Tenant-Id'] = selectedTenantId.toString();
      }

      // Convert business_hours back to API format (without closed, use empty strings)
      const apiBusinessHours = {};
      for (const day of dayLabels) {
        const dayData = settings.business_hours[day.key];
        apiBusinessHours[day.key] = {
          start: dayData.closed ? '' : dayData.start,
          end: dayData.closed ? '' : dayData.end,
        };
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
          business_hours: apiBusinessHours,
          followup_enabled: settings.followup_enabled,
          followup_delay_minutes: settings.followup_delay_minutes,
          followup_sources: ['email'], // Email follow-up only
          followup_initial_message: settings.followup_initial_message,
        }),
      });

      if (response.ok) {
        const data = await response.json();
        const normalizedSettings = {
          ...data,
          business_hours: normalizeBusinessHours(data.business_hours),
        };
        setSettings(normalizedSettings);
        setOriginalSettings(normalizedSettings);
        showToast('Settings saved successfully');
      } else {
        const errorData = await response.json();
        showToast(errorData.detail || 'Failed to save settings', 'error');
      }
    } catch {
      showToast('Network error. Please try again.', 'error');
    } finally {
      setSaving(false);
    }
  };

  const handleCancel = () => {
    if (originalSettings) {
      setSettings(originalSettings);
    }
  };

  const updateSetting = (key, value) => {
    setSettings(prev => ({ ...prev, [key]: value }));
  };

  const needsTenant = user?.is_global_admin && !selectedTenantId;

  if (needsTenant) {
    return (
      <div className="sms-page">
        <EmptyState
          icon="SMS"
          title="Select a tenant to manage SMS settings"
          description="Please select a tenant from the dropdown above."
        />
      </div>
    );
  }

  if (loading) {
    return (
      <div className="sms-page">
        <LoadingState message="Loading SMS settings..." fullPage />
      </div>
    );
  }

  if (error && !error.includes('Not Found')) {
    if (error.includes('Tenant context')) {
      return (
        <div className="sms-page">
          <EmptyState
            icon="SMS"
            title="Select a tenant to manage SMS settings"
            description="Please select a tenant from the dropdown above."
          />
        </div>
      );
    }
    return (
      <div className="sms-page">
        <ErrorState message={error} onRetry={fetchSettings} />
      </div>
    );
  }

  return (
    <div className="sms-page">
      {/* Sticky Save Bar */}
      <div className={`sms-save-bar ${isDirty ? 'sms-save-bar--visible' : ''}`}>
        <div className="sms-save-bar__content">
          <span className="sms-save-bar__text">You have unsaved changes</span>
          <div className="sms-save-bar__actions">
            <button
              type="button"
              className="sms-btn sms-btn--ghost"
              onClick={handleCancel}
              disabled={saving}
            >
              Cancel
            </button>
            <button
              type="button"
              className="sms-btn sms-btn--primary"
              onClick={saveSettings}
              disabled={saving}
            >
              {saving ? 'Saving...' : 'Save Changes'}
            </button>
          </div>
        </div>
      </div>

      {/* Toast Notification */}
      {toast && (
        <div className={`sms-toast sms-toast--${toast.type}`}>
          {toast.type === 'success' ? '✓' : '!'} {toast.message}
        </div>
      )}

      {/* Header */}
      <header className="sms-header">
        <h1 className="sms-header__title">SMS Settings</h1>
        <p className="sms-header__subtitle">Control when we reply and what messages we send.</p>
      </header>

      <div className="sms-cards">
        {/* Card A: SMS Line */}
        <section className="sms-card">
          <div className="sms-card__header">
            <h2 className="sms-card__title">SMS Line</h2>
          </div>
          <div className="sms-card__body">
            <div className="sms-field">
              <label className="sms-field__label">Assigned Number</label>
              <div className="sms-field__value">
                {settings.phone_number ? (
                  <div className="sms-phone-status">
                    <span className="sms-phone-number">{settings.phone_number}</span>
                    <span className="sms-status-badge sms-status-badge--active">Active</span>
                  </div>
                ) : (
                  <div className="sms-phone-status">
                    <span className="sms-status-badge sms-status-badge--inactive">Not Assigned</span>
                    <span className="sms-field__hint">Contact support to assign a number.</span>
                  </div>
                )}
              </div>
            </div>

            <div className="sms-field sms-field--toggle">
              <label className="sms-toggle" htmlFor="sms-enabled">
                <input
                  id="sms-enabled"
                  type="checkbox"
                  checked={settings.is_enabled}
                  onChange={(e) => updateSetting('is_enabled', e.target.checked)}
                  disabled={!settings.phone_number}
                  className="sms-toggle__input"
                />
                <span className="sms-toggle__switch" />
                <span className="sms-toggle__label">SMS Enabled</span>
              </label>
              <p className="sms-field__description">
                {settings.phone_number
                  ? 'When enabled, the system can send and receive SMS messages.'
                  : 'Assign a phone number to enable SMS messaging.'}
              </p>
            </div>
          </div>
        </section>

      </div>

      {/* Bottom Save Button (always visible) */}
      <div className="sms-actions">
        <button
          type="button"
          className="sms-btn sms-btn--primary sms-btn--lg"
          onClick={saveSettings}
          disabled={saving || !isDirty}
        >
          {saving ? 'Saving...' : 'Save Settings'}
        </button>
      </div>

      <style>{`
        .sms-page {
          max-width: 720px;
          margin: 0 auto;
          padding: 1rem 1.5rem 3rem;
        }

        /* Sticky Save Bar */
        .sms-save-bar {
          position: fixed;
          top: 0;
          left: 0;
          right: 0;
          z-index: 100;
          background: #1a1a1a;
          transform: translateY(-100%);
          transition: transform 0.2s ease;
        }
        .sms-save-bar--visible {
          transform: translateY(0);
        }
        .sms-save-bar__content {
          max-width: 720px;
          margin: 0 auto;
          padding: 0.75rem 1.5rem;
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 1rem;
        }
        .sms-save-bar__text {
          color: #fff;
          font-size: 0.875rem;
          font-weight: 500;
        }
        .sms-save-bar__actions {
          display: flex;
          gap: 0.5rem;
        }

        /* Toast */
        .sms-toast {
          position: fixed;
          bottom: 1.5rem;
          left: 50%;
          transform: translateX(-50%);
          padding: 0.75rem 1.25rem;
          border-radius: 8px;
          font-size: 0.875rem;
          font-weight: 500;
          z-index: 200;
          animation: slideUp 0.3s ease;
        }
        .sms-toast--success {
          background: #065f46;
          color: #fff;
        }
        .sms-toast--error {
          background: #991b1b;
          color: #fff;
        }
        @keyframes slideUp {
          from { opacity: 0; transform: translate(-50%, 10px); }
          to { opacity: 1; transform: translate(-50%, 0); }
        }

        /* Header */
        .sms-header {
          margin-bottom: 1.5rem;
        }
        .sms-header__title {
          font-size: 1.5rem;
          font-weight: 600;
          color: #111;
          margin: 0 0 0.25rem;
        }
        .sms-header__subtitle {
          font-size: 0.9375rem;
          color: #666;
          margin: 0;
        }

        /* Cards */
        .sms-cards {
          display: flex;
          flex-direction: column;
          gap: 1rem;
        }
        .sms-card {
          background: #fff;
          border: 1px solid #e5e5e5;
          border-radius: 12px;
          overflow: hidden;
        }
        .sms-card--disabled {
          opacity: 0.6;
          pointer-events: none;
        }
        .sms-card__header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 1rem 1.25rem;
          border-bottom: 1px solid #f0f0f0;
          background: #fafafa;
        }
        .sms-card__title {
          font-size: 1rem;
          font-weight: 600;
          color: #111;
          margin: 0;
        }
        .sms-card__badge {
          font-size: 0.6875rem;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.03em;
          padding: 0.25rem 0.5rem;
          border-radius: 4px;
          background: #f3f4f6;
          color: #6b7280;
        }
        .sms-card__body {
          padding: 1.25rem;
          display: flex;
          flex-direction: column;
          gap: 1rem;
        }
        .sms-card__description {
          font-size: 0.875rem;
          color: #666;
          margin: 0;
          line-height: 1.5;
        }

        /* Fields */
        .sms-field {
          display: flex;
          flex-direction: column;
          gap: 0.375rem;
        }
        .sms-field--row {
          flex-direction: row;
          align-items: center;
          gap: 0.75rem;
        }
        .sms-field--toggle {
          gap: 0.25rem;
        }
        .sms-field__label {
          font-size: 0.875rem;
          font-weight: 500;
          color: #333;
        }
        .sms-field__value {
          display: flex;
          flex-direction: column;
          gap: 0.25rem;
        }
        .sms-field__description {
          font-size: 0.8125rem;
          color: #666;
          margin: 0;
          line-height: 1.4;
        }
        .sms-field__hint {
          font-size: 0.75rem;
          color: #888;
          margin-top: 0.25rem;
        }

        /* Phone Status */
        .sms-phone-status {
          display: flex;
          align-items: center;
          gap: 0.75rem;
          flex-wrap: wrap;
        }
        .sms-phone-number {
          font-size: 1.125rem;
          font-weight: 600;
          font-family: ui-monospace, monospace;
          color: #111;
        }
        .sms-status-badge {
          font-size: 0.6875rem;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.03em;
          padding: 0.25rem 0.5rem;
          border-radius: 4px;
        }
        .sms-status-badge--active {
          background: #dcfce7;
          color: #166534;
        }
        .sms-status-badge--inactive {
          background: #fef3c7;
          color: #92400e;
        }

        /* Toggle Switch */
        .sms-toggle {
          display: flex;
          align-items: center;
          gap: 0.75rem;
          cursor: pointer;
        }
        .sms-toggle__input {
          position: absolute;
          opacity: 0;
          width: 0;
          height: 0;
        }
        .sms-toggle__switch {
          position: relative;
          width: 44px;
          height: 24px;
          background: #d1d5db;
          border-radius: 12px;
          transition: background 0.2s;
          flex-shrink: 0;
        }
        .sms-toggle__switch::after {
          content: '';
          position: absolute;
          top: 2px;
          left: 2px;
          width: 20px;
          height: 20px;
          background: #fff;
          border-radius: 50%;
          transition: transform 0.2s;
          box-shadow: 0 1px 3px rgba(0,0,0,0.15);
        }
        .sms-toggle__input:checked + .sms-toggle__switch {
          background: #4f46e5;
        }
        .sms-toggle__input:checked + .sms-toggle__switch::after {
          transform: translateX(20px);
        }
        .sms-toggle__input:focus-visible + .sms-toggle__switch {
          box-shadow: 0 0 0 3px rgba(79, 70, 229, 0.3);
        }
        .sms-toggle__input:disabled + .sms-toggle__switch {
          opacity: 0.5;
          cursor: not-allowed;
        }
        .sms-toggle__label {
          font-size: 0.9375rem;
          font-weight: 500;
          color: #111;
        }

        /* Select */
        .sms-select {
          padding: 0.5rem 0.75rem;
          font-size: 0.875rem;
          border: 1px solid #d1d5db;
          border-radius: 6px;
          background: #fff;
          color: #111;
          min-width: 180px;
        }
        .sms-select:focus {
          outline: none;
          border-color: #4f46e5;
          box-shadow: 0 0 0 3px rgba(79, 70, 229, 0.15);
        }

        /* Summary */
        .sms-summary {
          display: flex;
          align-items: center;
          gap: 0.5rem;
          padding: 0.625rem 0.875rem;
          background: #f0f9ff;
          border-radius: 8px;
          border: 1px solid #bae6fd;
        }
        .sms-summary__icon {
          font-size: 1rem;
        }
        .sms-summary__text {
          font-size: 0.8125rem;
          color: #0369a1;
          font-weight: 500;
        }

        /* Schedule Grid */
        .sms-schedule {
          border: 1px solid #e5e5e5;
          border-radius: 8px;
          overflow: hidden;
        }
        .sms-schedule__header {
          display: grid;
          grid-template-columns: 100px 1fr 80px;
          gap: 0.5rem;
          padding: 0.625rem 0.875rem;
          background: #f9fafb;
          border-bottom: 1px solid #e5e5e5;
          font-size: 0.6875rem;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.05em;
          color: #6b7280;
        }
        .sms-schedule__col--status {
          text-align: center;
        }
        .sms-schedule__row {
          display: grid;
          grid-template-columns: 100px 1fr 80px;
          gap: 0.5rem;
          padding: 0.625rem 0.875rem;
          align-items: center;
          border-bottom: 1px solid #f0f0f0;
        }
        .sms-schedule__row:last-child {
          border-bottom: none;
        }
        .sms-schedule__row--closed {
          background: #fafafa;
        }
        .sms-schedule__day {
          font-size: 0.875rem;
          font-weight: 500;
          color: #333;
        }
        .sms-schedule__times {
          display: flex;
          align-items: center;
          gap: 0.5rem;
        }
        .sms-schedule__sep {
          font-size: 0.75rem;
          color: #888;
        }
        .sms-schedule__closed-label {
          font-size: 0.8125rem;
          color: #888;
          font-style: italic;
        }
        .sms-time-input {
          padding: 0.375rem 0.5rem;
          font-size: 0.8125rem;
          border: 1px solid #d1d5db;
          border-radius: 6px;
          width: 100px;
        }
        .sms-time-input:focus {
          outline: none;
          border-color: #4f46e5;
        }
        .sms-closed-toggle {
          padding: 0.375rem 0.625rem;
          font-size: 0.75rem;
          font-weight: 500;
          border: 1px solid #d1d5db;
          border-radius: 6px;
          background: #fff;
          color: #4b5563;
          cursor: pointer;
          transition: all 0.15s;
        }
        .sms-closed-toggle:hover {
          border-color: #9ca3af;
        }
        .sms-closed-toggle--active {
          background: #fee2e2;
          border-color: #fca5a5;
          color: #991b1b;
        }

        /* Radio Group */
        .sms-radio-group {
          display: flex;
          flex-direction: column;
          gap: 0.75rem;
        }
        .sms-radio {
          display: flex;
          align-items: flex-start;
          gap: 0.75rem;
          cursor: pointer;
          padding: 0.75rem;
          border: 1px solid #e5e5e5;
          border-radius: 8px;
          transition: all 0.15s;
        }
        .sms-radio:hover {
          border-color: #c7d2fe;
          background: #f5f5ff;
        }
        .sms-radio:has(.sms-radio__input:checked) {
          border-color: #4f46e5;
          background: #eef2ff;
        }
        .sms-radio__input {
          position: absolute;
          opacity: 0;
        }
        .sms-radio__mark {
          width: 20px;
          height: 20px;
          border: 2px solid #d1d5db;
          border-radius: 50%;
          flex-shrink: 0;
          position: relative;
          margin-top: 2px;
        }
        .sms-radio__input:checked + .sms-radio__mark {
          border-color: #4f46e5;
        }
        .sms-radio__input:checked + .sms-radio__mark::after {
          content: '';
          position: absolute;
          top: 4px;
          left: 4px;
          width: 8px;
          height: 8px;
          background: #4f46e5;
          border-radius: 50%;
        }
        .sms-radio__content {
          display: flex;
          flex-direction: column;
          gap: 0.125rem;
        }
        .sms-radio__label {
          font-size: 0.9375rem;
          font-weight: 500;
          color: #111;
        }
        .sms-radio__description {
          font-size: 0.8125rem;
          color: #666;
        }

        /* Textarea */
        .sms-field--textarea {
          gap: 0.5rem;
        }
        .sms-textarea-wrapper {
          position: relative;
        }
        .sms-textarea {
          width: 100%;
          padding: 0.75rem;
          font-size: 0.875rem;
          font-family: inherit;
          border: 1px solid #d1d5db;
          border-radius: 8px;
          resize: none;
          line-height: 1.5;
        }
        .sms-textarea:focus {
          outline: none;
          border-color: #4f46e5;
          box-shadow: 0 0 0 3px rgba(79, 70, 229, 0.15);
        }
        .sms-textarea__count {
          position: absolute;
          bottom: 0.5rem;
          right: 0.75rem;
          font-size: 0.6875rem;
          color: #9ca3af;
        }

        /* Input */
        .sms-input-group {
          display: flex;
          align-items: center;
          gap: 0.5rem;
        }
        .sms-input {
          padding: 0.5rem 0.75rem;
          font-size: 0.875rem;
          border: 1px solid #d1d5db;
          border-radius: 6px;
        }
        .sms-input--number {
          width: 80px;
          text-align: center;
        }
        .sms-input:focus {
          outline: none;
          border-color: #4f46e5;
          box-shadow: 0 0 0 3px rgba(79, 70, 229, 0.15);
        }
        .sms-input-group__suffix {
          font-size: 0.875rem;
          color: #666;
        }

        /* Chip Group */
        .sms-chip-group {
          display: flex;
          gap: 0.5rem;
          flex-wrap: wrap;
        }
        .sms-chip {
          padding: 0.5rem 1rem;
          font-size: 0.8125rem;
          font-weight: 500;
          border: 1px solid #d1d5db;
          border-radius: 20px;
          background: #fff;
          color: #4b5563;
          cursor: pointer;
          transition: all 0.15s;
        }
        .sms-chip:hover {
          border-color: #a5b4fc;
          background: #f5f5ff;
        }
        .sms-chip--active {
          background: #4f46e5;
          border-color: #4f46e5;
          color: #fff;
        }
        .sms-chip--active:hover {
          background: #4338ca;
          border-color: #4338ca;
        }

        /* Buttons */
        .sms-btn {
          padding: 0.5rem 1rem;
          font-size: 0.875rem;
          font-weight: 500;
          border-radius: 6px;
          cursor: pointer;
          transition: all 0.15s;
          border: none;
        }
        .sms-btn:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }
        .sms-btn--primary {
          background: #4f46e5;
          color: #fff;
        }
        .sms-btn--primary:hover:not(:disabled) {
          background: #4338ca;
        }
        .sms-btn--ghost {
          background: transparent;
          color: #fff;
          border: 1px solid rgba(255,255,255,0.3);
        }
        .sms-btn--ghost:hover:not(:disabled) {
          background: rgba(255,255,255,0.1);
        }
        .sms-btn--lg {
          padding: 0.75rem 2rem;
          font-size: 1rem;
        }

        /* Actions */
        .sms-actions {
          margin-top: 1.5rem;
          display: flex;
          justify-content: flex-start;
        }

        /* Responsive */
        @media (max-width: 640px) {
          .sms-page {
            padding: 1rem;
          }
          .sms-field--row {
            flex-direction: column;
            align-items: flex-start;
          }
          .sms-schedule__header,
          .sms-schedule__row {
            grid-template-columns: 1fr;
            gap: 0.375rem;
          }
          .sms-schedule__col--status {
            text-align: left;
          }
          .sms-schedule__times {
            flex-wrap: wrap;
          }
          .sms-save-bar__content {
            padding: 0.75rem 1rem;
            flex-direction: column;
            gap: 0.75rem;
          }
        }
      `}</style>
    </div>
  );
}
