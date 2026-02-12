import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api/client';
import { useAuth } from '../context/AuthContext';
import { LoadingState, ErrorState } from '../components/ui';
import './Onboarding.css';

export default function Onboarding() {
  const navigate = useNavigate();
  const { refreshProfile } = useAuth();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [fieldErrors, setFieldErrors] = useState({});
  const [formData, setFormData] = useState({
    business_name: '',
    website_url: '',
    phone_number: '',
    twilio_phone: '',
    email: '',
  });

  const validateField = (name, value) => {
    const errors = { ...fieldErrors };

    switch (name) {
      case 'website_url':
        if (value.trim()) {
          try {
            new URL(value);
            delete errors.website_url;
          } catch {
            errors.website_url = 'Please enter a valid URL (e.g., https://example.com)';
          }
        } else {
          delete errors.website_url;
        }
        break;
      case 'phone_number':
        if (value.trim()) {
          const phoneRegex = /^[\d\s\-+()]+$/;
          if (!phoneRegex.test(value) || value.replace(/\D/g, '').length < 10) {
            errors.phone_number = 'Please enter a valid phone number';
          } else {
            delete errors.phone_number;
          }
        } else {
          delete errors.phone_number;
        }
        break;
      case 'email':
        if (value.trim()) {
          const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
          if (!emailRegex.test(value)) {
            errors.email = 'Please enter a valid email address';
          } else {
            delete errors.email;
          }
        } else {
          delete errors.email;
        }
        break;
      default:
        delete errors[name];
        break;
    }

    setFieldErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const loadProfile = useCallback(async () => {
    setLoading(true);
    setError('');
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
      setError(err.message || 'Failed to load profile. Please try refreshing the page.');
      console.error('Failed to load profile:', err);
    } finally {
      setLoading(false);
    }
  }, [navigate]);

  useEffect(() => {
    loadProfile();
  }, [loadProfile]);

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData({ ...formData, [name]: value });
    // Clear field error when user starts typing
    if (fieldErrors[name]) {
      setFieldErrors({ ...fieldErrors, [name]: undefined });
    }
  };

  const handleBlur = (e) => {
    validateField(e.target.name, e.target.value);
  };

  const validateForm = () => {
    const fields = ['website_url', 'phone_number', 'email'];
    let isValid = true;

    fields.forEach(field => {
      if (!validateField(field, formData[field])) {
        isValid = false;
      }
    });

    return isValid;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setFieldErrors({});
    
    if (!validateForm()) {
      setError('Please fix the errors below before continuing');
      return;
    }

    setSaving(true);

    try {
      const updated = await api.updateBusinessProfile(formData);
      if (refreshProfile) {
        await refreshProfile();
      }
      navigate('/');
    } catch (err) {
      setError(err.message || 'Failed to save profile. Please try again.');
      console.error('Failed to save profile:', err);
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="onboarding-container">
        <LoadingState message="Loading your profile..." fullPage />
      </div>
    );
  }

  // Show ErrorState if there's an error during initial load (before form is shown)
  if (error && !formData.business_name && !formData.website_url && !formData.phone_number && !formData.email) {
    return (
      <div className="onboarding-container">
        <ErrorState message={error} onRetry={loadProfile} />
      </div>
    );
  }

  return (
    <div className="onboarding-container">
      <div className="onboarding-card">
        <h1>Welcome to ConvoPro</h1>
        <p className="subtitle">Let's set up your business profile to get started</p>

        {error && <div className="error-message" role="alert">{error}</div>}

        <form onSubmit={handleSubmit} noValidate>
          <div className="form-group">
            <label htmlFor="business_name">
              Business Name
            </label>
            <input
              type="text"
              id="business_name"
              name="business_name"
              value={formData.business_name}
              onChange={handleChange}
              onBlur={handleBlur}
              placeholder="Your Business Name"
              aria-invalid={!!fieldErrors.business_name}
              aria-describedby={fieldErrors.business_name ? 'business_name-error' : undefined}
            />
            {fieldErrors.business_name && (
              <span id="business_name-error" className="field-error" role="alert">
                {fieldErrors.business_name}
              </span>
            )}
          </div>

          <div className="form-group">
            <label htmlFor="website_url">
              Website URL
            </label>
            <input
              type="url"
              id="website_url"
              name="website_url"
              value={formData.website_url}
              onChange={handleChange}
              onBlur={handleBlur}
              placeholder="https://yourbusiness.com"
              aria-invalid={!!fieldErrors.website_url}
              aria-describedby={fieldErrors.website_url ? 'website_url-error' : undefined}
            />
            {fieldErrors.website_url && (
              <span id="website_url-error" className="field-error" role="alert">
                {fieldErrors.website_url}
              </span>
            )}
          </div>

          <div className="form-group">
            <label htmlFor="phone_number">
              Phone Number
            </label>
            <input
              type="tel"
              id="phone_number"
              name="phone_number"
              value={formData.phone_number}
              onChange={handleChange}
              onBlur={handleBlur}
              placeholder="+1 (555) 123-4567"
              aria-invalid={!!fieldErrors.phone_number}
              aria-describedby={fieldErrors.phone_number ? 'phone_number-error' : undefined}
            />
            {fieldErrors.phone_number && (
              <span id="phone_number-error" className="field-error" role="alert">
                {fieldErrors.phone_number}
              </span>
            )}
          </div>

          <div className="form-group">
            <label htmlFor="email">
              Email Address
            </label>
            <input
              type="email"
              id="email"
              name="email"
              value={formData.email}
              onChange={handleChange}
              onBlur={handleBlur}
              placeholder="contact@yourbusiness.com"
              aria-invalid={!!fieldErrors.email}
              aria-describedby={fieldErrors.email ? 'email-error' : undefined}
            />
            {fieldErrors.email && (
              <span id="email-error" className="field-error" role="alert">
                {fieldErrors.email}
              </span>
            )}
          </div>


          <button 
            type="submit" 
            className="submit-btn" 
            disabled={saving}
            aria-busy={saving}
          >
            {saving ? 'Saving...' : 'Complete Setup'}
          </button>
        </form>
      </div>
    </div>
  );
}
