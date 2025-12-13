import { useState, useEffect } from 'react';
import { api } from '../api/client';
import './Settings.css';

export default function Settings() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [success, setSuccess] = useState('');
  const [error, setError] = useState('');
  const [formData, setFormData] = useState({
    business_name: '',
    website_url: '',
    phone_number: '',
    twilio_phone: '',
    email: '',
  });

  useEffect(() => {
    loadProfile();
  }, []);

  const loadProfile = async () => {
    try {
      const profile = await api.getBusinessProfile();
      setFormData({
        business_name: profile.business_name || '',
        website_url: profile.website_url || '',
        phone_number: profile.phone_number || '',
        twilio_phone: profile.twilio_phone || '',
        email: profile.email || '',
      });
    } catch (err) {
      setError('Failed to load profile');
    } finally {
      setLoading(false);
    }
  };

  const handleChange = (e) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setSuccess('');
    setSaving(true);

    try {
      await api.updateBusinessProfile(formData);
      setSuccess('Profile updated successfully');
    } catch (err) {
      setError(err.message || 'Failed to save profile');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <div className="settings-page"><p>Loading...</p></div>;
  }

  return (
    <div className="settings-page">
      <h1>Business Profile Settings</h1>
      <p className="description">Update your business information used in customer communications.</p>

      {error && <div className="error-message">{error}</div>}
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
            placeholder="https://yourbusiness.com"
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
            placeholder="+1 (555) 123-4567"
          />
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

        <div className="form-group">
          <label htmlFor="twilio_phone">Twilio Phone (optional)</label>
          <input
            type="tel"
            id="twilio_phone"
            name="twilio_phone"
            value={formData.twilio_phone}
            onChange={handleChange}
            placeholder="+1 (555) 987-6543"
          />
          <small>For automated SMS/calls. Leave blank if not using.</small>
        </div>

        <button type="submit" className="save-btn" disabled={saving}>
          {saving ? 'Saving...' : 'Save Changes'}
        </button>
      </form>
    </div>
  );
}
