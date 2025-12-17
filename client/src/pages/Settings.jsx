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

export default function Settings() {
  const { user, selectedTenantId } = useAuth();
  const [saving, setSaving] = useState(false);
  const [success, setSuccess] = useState('');
  const [formError, setFormError] = useState('');
  const [formData, setFormData] = useState(defaultFormData);

  const fetchProfile = useCallback(() => api.getBusinessProfile(), []);
  const { data: profile, loading, error, refetch } = useFetchData(fetchProfile);

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
      <h1>Business Profile Settings</h1>
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
          <input
            type="url"
            id="website_url"
            name="website_url"
            value={formData.website_url}
            onChange={handleChange}
            placeholder="https://yourwebsite.com"
          />
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
          <label htmlFor="twilio_phone">Twilio Phone Number</label>
          <input
            type="tel"
            id="twilio_phone"
            name="twilio_phone"
            value={formData.twilio_phone}
            onChange={handleChange}
            placeholder="+15551234567"
          />
          <small>Your Twilio number for SMS communications</small>
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
