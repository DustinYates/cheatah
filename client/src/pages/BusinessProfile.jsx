import { useState, useCallback, useEffect } from 'react';
import { api } from '../api/client';
import { useFetchData } from '../hooks/useFetchData';
import { useAuth } from '../context/AuthContext';
import { LoadingState, ErrorState, EmptyState } from '../components/ui';
import './Settings.css';

const defaultFormData = {
  business_name: '',
  website_url: '',
  phone_number: '',
  twilio_phone: '',
  email: '',
};

// Helper to get the active SMS phone number from telephony config
const getActiveSmsPhone = (telephonyConfig) => {
  if (!telephonyConfig) return { phone: '', provider: 'twilio', label: 'SMS Phone Number' };

  const provider = telephonyConfig.provider || 'twilio';
  if (provider === 'telnyx') {
    return {
      phone: telephonyConfig.telnyx_phone_number || '',
      provider: 'telnyx',
      label: 'Telnyx Phone Number'
    };
  }
  return {
    phone: telephonyConfig.twilio_phone_number || '',
    provider: 'twilio',
    label: 'Twilio Phone Number'
  };
};

export default function BusinessProfile() {
  const { user, selectedTenantId } = useAuth();
  const [saving, setSaving] = useState(false);
  const [success, setSuccess] = useState('');
  const [formError, setFormError] = useState('');
  const [formData, setFormData] = useState(defaultFormData);

  // Telephony config state (for SMS phone number display)
  const [telephonyConfig, setTelephonyConfig] = useState(null);

  // Scraping state
  const [scraping, setScraping] = useState(false);
  const [scrapeStatus, setScrapeStatus] = useState(null);

  const fetchProfile = useCallback(() => api.getBusinessProfile(), []);
  const { data: profile, loading, error, refetch } = useFetchData(fetchProfile);

  // Fetch telephony config for SMS phone display
  const fetchTelephonyConfig = useCallback(async () => {
    if (!user?.is_global_admin || !selectedTenantId) return;
    try {
      const data = await api.getTelephonyConfig();
      setTelephonyConfig(data);
    } catch (err) {
      // Telephony config is optional, don't show error
      console.log('Telephony config not available:', err.message);
    }
  }, [user, selectedTenantId]);

  // Fetch scrape status
  const fetchScrapeStatus = useCallback(async () => {
    if (user?.is_global_admin && !selectedTenantId) return;
    try {
      const data = await api.getScrapeStatus();
      setScrapeStatus(data);
    } catch (err) {
      console.log('Scrape status not available:', err.message);
    }
  }, [user, selectedTenantId]);

  // Trigger website rescrape
  const handleRescrape = async () => {
    if (!formData.website_url) {
      setFormError('Please enter a website URL first');
      return;
    }
    setScraping(true);
    setFormError('');
    setSuccess('');
    try {
      await api.triggerRescrape();
      setSuccess('Website scraping started! This may take a minute. Refresh to see results.');
      // Poll for completion
      const pollInterval = setInterval(async () => {
        const status = await api.getScrapeStatus();
        setScrapeStatus(status);
        if (!status.scraping_in_progress) {
          clearInterval(pollInterval);
          setScraping(false);
          if (status.has_scraped_data) {
            setSuccess('Website scraped successfully! Go to Prompts Setup to use the extracted data.');
          }
        }
      }, 3000);
      // Timeout after 2 minutes
      setTimeout(() => {
        clearInterval(pollInterval);
        setScraping(false);
      }, 120000);
    } catch (err) {
      setFormError(err.message || 'Failed to start scraping');
      setScraping(false);
    }
  };

  useEffect(() => {
    fetchTelephonyConfig();
    fetchScrapeStatus();
  }, [fetchTelephonyConfig, fetchScrapeStatus]);

  // Check if global admin without tenant selected
  const needsTenant = user?.is_global_admin && !selectedTenantId;

  useEffect(() => {
    if (profile) {
      setFormData({
        business_name: profile.business_name || '',
        website_url: profile.website_url || '',
        phone_number: profile.phone_number || '',
        twilio_phone: profile.twilio_phone || '',
        email: profile.email || '',
      });
    }
  }, [profile]);

  const handleChange = (e) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setFormError('');
    setSuccess('');
    setSaving(true);

    try {
      await api.updateBusinessProfile(formData);
      setSuccess('Profile updated successfully');
    } catch (err) {
      setFormError(err.message || 'Failed to save profile');
    } finally {
      setSaving(false);
    }
  };

  if (needsTenant) {
    return (
      <div className="settings-page">
        <EmptyState
          icon="⚙️"
          title="Select a tenant to manage settings"
          description="Please select a tenant from the dropdown above to manage their business profile settings."
        />
      </div>
    );
  }

  if (loading) {
    return (
      <div className="settings-page">
        <LoadingState message="Loading settings..." />
      </div>
    );
  }

  if (error && !profile) {
    // Check if error is about tenant context
    if (error.includes('Tenant context required') || error.includes('Tenant context')) {
      return (
        <div className="settings-page">
          <EmptyState
            icon="⚙️"
            title="Select a tenant to manage settings"
            description="Please select a tenant from the dropdown above to manage their business profile settings."
          />
        </div>
      );
    }
    return (
      <div className="settings-page">
        <ErrorState message={error} onRetry={refetch} />
      </div>
    );
  }

  return (
    <div className="settings-page">
      <h1>Business Profile</h1>
      <p className="description">Update your business information used in customer communications.</p>

      {formError && <div className="error-message">{formError}</div>}
      {success && <div className="success-message">{success}</div>}

      <form onSubmit={handleSubmit} className="settings-form">
        <div className="form-group">
          <label htmlFor="business_name">Business Name</label>
          <input
            type="text"
            id="business_name"
            name="business_name"
            value={formData.business_name}
            onChange={handleChange}
            placeholder="Your Business Name"
          />
        </div>

        <div className="form-group">
          <label htmlFor="website_url">Website URL</label>
          <div style={{ display: 'flex', gap: '10px', alignItems: 'flex-start' }}>
            <input
              type="url"
              id="website_url"
              name="website_url"
              value={formData.website_url}
              onChange={handleChange}
              placeholder="https://yourwebsite.com"
              style={{ flex: 1 }}
            />
            <button
              type="button"
              onClick={handleRescrape}
              disabled={scraping || !formData.website_url}
              style={{
                padding: '8px 16px',
                backgroundColor: scraping ? '#ccc' : '#4CAF50',
                color: 'white',
                border: 'none',
                borderRadius: '4px',
                cursor: scraping ? 'not-allowed' : 'pointer',
                whiteSpace: 'nowrap',
              }}
            >
              {scraping ? 'Scraping...' : 'Scrape Website'}
            </button>
          </div>
          <small>
            Click "Scrape Website" to extract business info for the Prompt Wizard.
            {scrapeStatus?.has_scraped_data && (
              <span style={{ color: 'green', marginLeft: '8px' }}>
                Last scraped: {new Date(scrapeStatus.last_scraped_at).toLocaleString()}
              </span>
            )}
          </small>
        </div>

        <div className="form-group">
          <label htmlFor="phone_number">Phone Number</label>
          <input
            type="tel"
            id="phone_number"
            name="phone_number"
            value={formData.phone_number}
            onChange={handleChange}
            placeholder="(555) 123-4567"
          />
        </div>

        <div className="form-group">
          <label htmlFor="twilio_phone">{getActiveSmsPhone(telephonyConfig).label}</label>
          <input
            type="tel"
            id="twilio_phone"
            name="twilio_phone"
            value={getActiveSmsPhone(telephonyConfig).phone || formData.twilio_phone}
            readOnly
            placeholder="Not configured"
            className="readonly-input"
          />
          <small>
            Your {getActiveSmsPhone(telephonyConfig).provider === 'telnyx' ? 'Telnyx' : 'Twilio'} number for SMS communications.
            {user?.is_global_admin && <> <a href="/telephony-settings">Configure in Telephony Settings</a></>}
          </small>
        </div>

        <div className="form-group">
          <label htmlFor="email">Email Address</label>
          <input
            type="email"
            id="email"
            name="email"
            value={formData.email}
            onChange={handleChange}
            placeholder="contact@yourbusiness.com"
          />
        </div>

        <button type="submit" className="save-btn" disabled={saving}>
          {saving ? 'Saving...' : 'Save Changes'}
        </button>
      </form>
    </div>
  );
}
