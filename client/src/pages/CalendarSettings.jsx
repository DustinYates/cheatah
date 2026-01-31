import { useState, useCallback, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { api } from '../api/client';
import { useFetchData } from '../hooks/useFetchData';
import { useAuth } from '../context/AuthContext';
import { LoadingState, ErrorState } from '../components/ui';
import './CalendarSettings.css';

const DAYS_OF_WEEK = [
  { value: 0, label: 'Monday' },
  { value: 1, label: 'Tuesday' },
  { value: 2, label: 'Wednesday' },
  { value: 3, label: 'Thursday' },
  { value: 4, label: 'Friday' },
  { value: 5, label: 'Saturday' },
  { value: 6, label: 'Sunday' },
];

const DURATION_OPTIONS = [15, 30, 45, 60];
const BUFFER_OPTIONS = [0, 5, 10, 15, 30];

export default function CalendarSettings() {
  const { user, selectedTenantId } = useAuth();
  const [searchParams] = useSearchParams();
  const [saving, setSaving] = useState(false);
  const [success, setSuccess] = useState('');
  const [formError, setFormError] = useState('');
  const [connecting, setConnecting] = useState(false);
  const [disconnecting, setDisconnecting] = useState(false);

  const [formData, setFormData] = useState({
    booking_link_url: '',
    calendar_id: 'primary',
    scheduling_preferences: {
      meeting_duration_minutes: 30,
      buffer_minutes: 15,
      available_hours: { start: '09:00', end: '17:00' },
      available_days: [0, 1, 2, 3, 4],
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'America/New_York',
      max_advance_days: 14,
      meeting_title_template: 'Meeting with {customer_name}',
    },
  });

  const fetchSettings = useCallback(() => api.getCalendarSettings(), []);
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

  useEffect(() => {
    if (settings) {
      setFormData({
        booking_link_url: settings.booking_link_url || '',
        calendar_id: settings.calendar_id || 'primary',
        scheduling_preferences: settings.scheduling_preferences || formData.scheduling_preferences,
      });
    }
  }, [settings]);

  const needsTenant = user?.is_global_admin && !selectedTenantId;

  const handleConnect = async () => {
    setConnecting(true);
    setFormError('');
    try {
      const data = await api.startCalendarOAuth();
      window.location.href = data.authorization_url;
    } catch (err) {
      setFormError(err.message || 'Failed to start OAuth flow');
      setConnecting(false);
    }
  };

  const handleDisconnect = async () => {
    if (!confirm('Are you sure you want to disconnect Google Calendar?')) return;
    setDisconnecting(true);
    setFormError('');
    try {
      await api.disconnectCalendar();
      setSuccess('Google Calendar disconnected');
      refetch();
    } catch (err) {
      setFormError(err.message || 'Failed to disconnect');
    } finally {
      setDisconnecting(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    setFormError('');
    setSuccess('');
    try {
      await api.updateCalendarSettings(formData);
      setSuccess('Settings saved successfully');
      refetch();
    } catch (err) {
      setFormError(err.message || 'Failed to save settings');
    } finally {
      setSaving(false);
    }
  };

  const updatePref = (key, value) => {
    setFormData(prev => ({
      ...prev,
      scheduling_preferences: {
        ...prev.scheduling_preferences,
        [key]: value,
      },
    }));
  };

  const toggleDay = (dayValue) => {
    const current = formData.scheduling_preferences.available_days || [];
    const updated = current.includes(dayValue)
      ? current.filter(d => d !== dayValue)
      : [...current, dayValue].sort((a, b) => a - b);
    updatePref('available_days', updated);
  };

  if (loading) return <LoadingState message="Loading calendar settings..." />;
  if (error) return <ErrorState message={error} onRetry={refetch} />;

  if (needsTenant) {
    return (
      <div className="calendar-settings">
        <h1>Calendar Settings</h1>
        <div className="info-box">Please select a tenant from the header to manage calendar settings.</div>
      </div>
    );
  }

  const prefs = formData.scheduling_preferences;

  return (
    <div className="calendar-settings">
      <h1>Calendar Settings</h1>
      <p className="page-description">
        Connect your Google Calendar to let customers schedule meetings directly from the chatbot.
      </p>

      {success && <div className="success-message">{success}</div>}
      {formError && <div className="error-message">{formError}</div>}

      {/* Connection Status */}
      <section className="settings-section">
        <h2>Google Calendar Connection</h2>
        {settings?.is_connected ? (
          <div className="connection-status connected">
            <span className="status-badge connected">Connected</span>
            <span className="connected-email">{settings.google_email}</span>
            <button
              className="btn btn-danger btn-sm"
              onClick={handleDisconnect}
              disabled={disconnecting}
            >
              {disconnecting ? 'Disconnecting...' : 'Disconnect'}
            </button>
          </div>
        ) : (
          <div className="connection-status disconnected">
            <span className="status-badge disconnected">Not Connected</span>
            <button
              className="btn btn-primary"
              onClick={handleConnect}
              disabled={connecting}
            >
              {connecting ? 'Connecting...' : 'Connect Google Calendar'}
            </button>
            <p className="help-text">
              We'll request access to view your calendar availability and create events for booked meetings.
            </p>
          </div>
        )}
      </section>

      {/* Fallback Booking Link */}
      <section className="settings-section">
        <h2>Booking Link (Fallback)</h2>
        <p className="help-text">
          If Google Calendar is not connected, the chatbot will share this link instead.
        </p>
        <div className="form-group">
          <label htmlFor="booking-link">Booking URL</label>
          <input
            id="booking-link"
            type="url"
            value={formData.booking_link_url}
            onChange={(e) => setFormData(prev => ({ ...prev, booking_link_url: e.target.value }))}
            placeholder="https://calendly.com/your-link"
          />
        </div>
      </section>

      {/* Scheduling Preferences */}
      {settings?.is_connected && (
        <section className="settings-section">
          <h2>Scheduling Preferences</h2>

          <div className="form-row">
            <div className="form-group">
              <label htmlFor="duration">Meeting Duration</label>
              <select
                id="duration"
                value={prefs.meeting_duration_minutes}
                onChange={(e) => updatePref('meeting_duration_minutes', parseInt(e.target.value))}
              >
                {DURATION_OPTIONS.map(d => (
                  <option key={d} value={d}>{d} minutes</option>
                ))}
              </select>
            </div>

            <div className="form-group">
              <label htmlFor="buffer">Buffer Between Meetings</label>
              <select
                id="buffer"
                value={prefs.buffer_minutes}
                onChange={(e) => updatePref('buffer_minutes', parseInt(e.target.value))}
              >
                {BUFFER_OPTIONS.map(b => (
                  <option key={b} value={b}>{b === 0 ? 'No buffer' : `${b} minutes`}</option>
                ))}
              </select>
            </div>
          </div>

          <div className="form-row">
            <div className="form-group">
              <label htmlFor="hours-start">Available From</label>
              <input
                id="hours-start"
                type="time"
                value={prefs.available_hours?.start || '09:00'}
                onChange={(e) => updatePref('available_hours', { ...prefs.available_hours, start: e.target.value })}
              />
            </div>
            <div className="form-group">
              <label htmlFor="hours-end">Available Until</label>
              <input
                id="hours-end"
                type="time"
                value={prefs.available_hours?.end || '17:00'}
                onChange={(e) => updatePref('available_hours', { ...prefs.available_hours, end: e.target.value })}
              />
            </div>
          </div>

          <div className="form-group">
            <label>Available Days</label>
            <div className="days-grid">
              {DAYS_OF_WEEK.map(day => (
                <label key={day.value} className="day-checkbox">
                  <input
                    type="checkbox"
                    checked={(prefs.available_days || []).includes(day.value)}
                    onChange={() => toggleDay(day.value)}
                  />
                  <span>{day.label}</span>
                </label>
              ))}
            </div>
          </div>

          <div className="form-row">
            <div className="form-group">
              <label htmlFor="timezone">Timezone</label>
              <input
                id="timezone"
                type="text"
                value={prefs.timezone || ''}
                onChange={(e) => updatePref('timezone', e.target.value)}
                placeholder="America/New_York"
              />
            </div>
            <div className="form-group">
              <label htmlFor="max-advance">Max Advance Booking (days)</label>
              <input
                id="max-advance"
                type="number"
                min="1"
                max="90"
                value={prefs.max_advance_days || 14}
                onChange={(e) => updatePref('max_advance_days', parseInt(e.target.value))}
              />
            </div>
          </div>

          <div className="form-group">
            <label htmlFor="title-template">Meeting Title Template</label>
            <input
              id="title-template"
              type="text"
              value={prefs.meeting_title_template || ''}
              onChange={(e) => updatePref('meeting_title_template', e.target.value)}
              placeholder="Meeting with {customer_name}"
            />
            <span className="help-text">Use {'{customer_name}'} as a placeholder for the customer's name.</span>
          </div>
        </section>
      )}

      <div className="form-actions">
        <button
          className="btn btn-primary"
          onClick={handleSave}
          disabled={saving}
        >
          {saving ? 'Saving...' : 'Save Settings'}
        </button>
      </div>
    </div>
  );
}
