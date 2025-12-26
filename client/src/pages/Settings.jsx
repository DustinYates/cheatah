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
  
  // Embed code state
  const [embedCode, setEmbedCode] = useState(null);
  const [embedLoading, setEmbedLoading] = useState(false);
  const [embedError, setEmbedError] = useState('');
  const [copied, setCopied] = useState(false);

  const fetchProfile = useCallback(() => api.getBusinessProfile(), []);
  const { data: profile, loading, error, refetch } = useFetchData(fetchProfile);
  
  // Fetch embed code
  const fetchEmbedCode = useCallback(async () => {
    if (user?.is_global_admin && !selectedTenantId) return;
    setEmbedLoading(true);
    setEmbedError('');
    try {
      const data = await api.getEmbedCode();
      setEmbedCode(data);
    } catch (err) {
      setEmbedError(err.message || 'Failed to load embed code');
    } finally {
      setEmbedLoading(false);
    }
  }, [user, selectedTenantId]);

  useEffect(() => {
    fetchEmbedCode();
  }, [fetchEmbedCode]);

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

      {/* Embed Code Section */}
      <div className="embed-code-section">
        <h2>Website Chat Widget</h2>
        <p className="description">
          Copy this code and paste it into your WordPress footer or use a plugin like "Insert Headers and Footers".
        </p>

        {embedLoading && (
          <div className="embed-loading">Loading embed code...</div>
        )}

        {embedError && (
          <div className="error-message">{embedError}</div>
        )}

        {embedCode && (
          <>
            {embedCode.warning && (
              <div className="embed-warning">
                <span className="warning-icon">⚠️</span>
                <span>{embedCode.warning}</span>
              </div>
            )}

            <div className="embed-code-container">
              <div className="embed-code-header">
                <span className="embed-code-label">
                  {embedCode.has_published_prompt ? 'Your Embed Code (Ready to Use)' : 'Your Embed Code (Not Active)'}
                </span>
                <button
                  type="button"
                  className={`copy-btn ${copied ? 'copied' : ''}`}
                  onClick={async () => {
                    try {
                      await navigator.clipboard.writeText(embedCode.embed_code);
                      setCopied(true);
                      setTimeout(() => setCopied(false), 2000);
                    } catch (err) {
                      console.error('Failed to copy:', err);
                    }
                  }}
                >
                  {copied ? '✓ Copied!' : 'Copy Code'}
                </button>
              </div>
              <textarea
                readOnly
                value={embedCode.embed_code}
                className={`embed-code-textarea ${!embedCode.has_published_prompt ? 'inactive' : ''}`}
                rows={15}
              />
            </div>

            <div className="embed-instructions">
              <h3>Installation Instructions</h3>
              <ol>
                <li>Copy the code above by clicking the "Copy Code" button</li>
                <li>In WordPress, go to <strong>Appearance → Theme File Editor</strong></li>
                <li>Add the code to your theme's <code>footer.php</code> file before the closing <code>&lt;/body&gt;</code> tag</li>
                <li>Alternatively, use a plugin like <strong>"Insert Headers and Footers"</strong> and paste the code in the Footer section</li>
              </ol>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
