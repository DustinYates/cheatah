import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api/client';
import { useAuth } from '../context/AuthContext';
import './Onboarding.css';

export default function Onboarding() {
  const navigate = useNavigate();
  const { user, refreshProfile } = useAuth();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
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
      if (profile.profile_complete) {
        navigate('/');
      }
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
    setSaving(true);

    if (!formData.business_name || !formData.website_url || !formData.phone_number || !formData.email) {
      setError('Please fill in all required fields');
      setSaving(false);
      return;
    }

    try {
      const updated = await api.updateBusinessProfile(formData);
      if (updated.profile_complete) {
        if (refreshProfile) {
          await refreshProfile();
        }
        navigate('/');
      } else {
        setError('Please fill in all required fields');
      }
    } catch (err) {
      setError(err.message || 'Failed to save profile');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <div className="onboarding-container"><p>Loading...</p></div>;
  }

  return (
    <div className="onboarding-container">
      <div className="onboarding-card">
        <h1>Welcome to Chatter Cheetah</h1>
        <p className="subtitle">Let's set up your business profile to get started</p>

        {error && <div className="error-message">{error}</div>}

        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label htmlFor="business_name">Business Name *</label>
            <input
              type="text"
              id="business_name"
              name="business_name"
              value={formData.business_name}
              onChange={handleChange}
              placeholder="Your Business Name"
              required
            />
          </div>

          <div className="form-group">
            <label htmlFor="website_url">Website URL (for chatbot) *</label>
            <input
              type="url"
              id="website_url"
              name="website_url"
              value={formData.website_url}
              onChange={handleChange}
              placeholder="https://yourbusiness.com"
              required
            />
          </div>

          <div className="form-group">
            <label htmlFor="phone_number">Phone Number *</label>
            <input
              type="tel"
              id="phone_number"
              name="phone_number"
              value={formData.phone_number}
              onChange={handleChange}
              placeholder="+1 (555) 123-4567"
              required
            />
          </div>

          <div className="form-group">
            <label htmlFor="email">Email Address *</label>
            <input
              type="email"
              id="email"
              name="email"
              value={formData.email}
              onChange={handleChange}
              placeholder="contact@yourbusiness.com"
              required
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

          <button type="submit" className="submit-btn" disabled={saving}>
            {saving ? 'Saving...' : 'Complete Setup'}
          </button>
        </form>
      </div>
    </div>
  );
}
