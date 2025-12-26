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

const defaultWidgetSettings = {
  colors: {
    primary: '#007bff',
    secondary: '#6c757d',
    background: '#ffffff',
    text: '#333333',
    buttonText: '#ffffff',
    linkColor: '#007bff',
    borderColor: '#ddd'
  },
  typography: {
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif",
    fontSize: '14px',
    fontWeight: '400',
    lineHeight: '1.5',
    letterSpacing: 'normal'
  },
  layout: {
    borderRadius: '10px',
    boxShadow: '0 4px 20px rgba(0,0,0,0.15)',
    shadowColor: 'rgba(0,0,0,0.15)',
    opacity: '1',
    position: 'bottom-right',
    zIndex: '10000',
    maxWidth: '350px',
    maxHeight: '500px'
  },
  behavior: {
    openBehavior: 'click',
    autoOpenDelay: 0,
    showOnPages: '*',
    cooldownDays: 0
  },
  animations: {
    type: 'none',
    duration: '0.3s',
    easing: 'ease-in-out'
  },
  messages: {
    welcomeMessage: 'Chat with us',
    placeholder: 'Type your message...',
    sendButtonText: 'Send'
  },
  accessibility: {
    darkMode: false,
    highContrast: false,
    focusOutline: true
  }
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

  // Widget settings state
  const [widgetSettings, setWidgetSettings] = useState(defaultWidgetSettings);
  const [widgetSaving, setWidgetSaving] = useState(false);
  const [widgetSuccess, setWidgetSuccess] = useState('');
  const [widgetError, setWidgetError] = useState('');
  const [widgetLoading, setWidgetLoading] = useState(false);

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

  // Fetch widget settings
  const fetchWidgetSettings = useCallback(async () => {
    if (user?.is_global_admin && !selectedTenantId) return;
    setWidgetLoading(true);
    setWidgetError('');
    try {
      const data = await api.getWidgetSettings();
      setWidgetSettings(data);
    } catch (err) {
      setWidgetError(err.message || 'Failed to load widget settings');
    } finally {
      setWidgetLoading(false);
    }
  }, [user, selectedTenantId]);

  useEffect(() => {
    fetchWidgetSettings();
  }, [fetchWidgetSettings]);

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

  const handleWidgetChange = (category, field, value) => {
    setWidgetSettings(prev => ({
      ...prev,
      [category]: {
        ...prev[category],
        [field]: value
      }
    }));
  };

  const handleWidgetSubmit = async (e) => {
    e.preventDefault();
    setWidgetError('');
    setWidgetSuccess('');
    setWidgetSaving(true);

    try {
      await api.updateWidgetSettings(widgetSettings);
      setWidgetSuccess('Widget settings updated successfully');
      setTimeout(() => setWidgetSuccess(''), 3000);
    } catch (err) {
      setWidgetError(err.message || 'Failed to save widget settings');
    } finally {
      setWidgetSaving(false);
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

      {/* Widget Customization Section */}
      <div className="widget-customization-section">
        <h2>Widget Customization</h2>
        <p className="description">
          Customize the appearance and behavior of your chat widget.
        </p>

        {widgetLoading && (
          <div className="widget-loading">Loading widget settings...</div>
        )}

        {widgetError && (
          <div className="error-message">{widgetError}</div>
        )}

        {widgetSuccess && (
          <div className="success-message">{widgetSuccess}</div>
        )}

        {!widgetLoading && (
          <form onSubmit={handleWidgetSubmit} className="settings-form">
            {/* Colors & Branding */}
            <details open>
              <summary>Colors & Branding</summary>
              <div className="form-section">
                <div className="form-group">
                  <label htmlFor="widget-primary-color">
                    Primary Color <span className="info-icon" title="Main color used for buttons and headers">ℹ️</span>
                  </label>
                  <input
                    type="color"
                    id="widget-primary-color"
                    value={widgetSettings.colors.primary}
                    onChange={(e) => handleWidgetChange('colors', 'primary', e.target.value)}
                  />
                </div>

                <div className="form-group">
                  <label htmlFor="widget-secondary-color">
                    Secondary Color <span className="info-icon" title="Secondary accent color">ℹ️</span>
                  </label>
                  <input
                    type="color"
                    id="widget-secondary-color"
                    value={widgetSettings.colors.secondary}
                    onChange={(e) => handleWidgetChange('colors', 'secondary', e.target.value)}
                  />
                </div>

                <div className="form-group">
                  <label htmlFor="widget-background-color">
                    Background Color <span className="info-icon" title="Widget background color">ℹ️</span>
                  </label>
                  <input
                    type="color"
                    id="widget-background-color"
                    value={widgetSettings.colors.background}
                    onChange={(e) => handleWidgetChange('colors', 'background', e.target.value)}
                  />
                </div>

                <div className="form-group">
                  <label htmlFor="widget-text-color">
                    Text Color <span className="info-icon" title="Default text color">ℹ️</span>
                  </label>
                  <input
                    type="color"
                    id="widget-text-color"
                    value={widgetSettings.colors.text}
                    onChange={(e) => handleWidgetChange('colors', 'text', e.target.value)}
                  />
                </div>

                <div className="form-group">
                  <label htmlFor="widget-border-color">
                    Border Color <span className="info-icon" title="Border and divider color">ℹ️</span>
                  </label>
                  <input
                    type="color"
                    id="widget-border-color"
                    value={widgetSettings.colors.borderColor}
                    onChange={(e) => handleWidgetChange('colors', 'borderColor', e.target.value)}
                  />
                </div>
              </div>
            </details>

            {/* Typography */}
            <details>
              <summary>Typography</summary>
              <div className="form-section">
                <div className="form-group">
                  <label htmlFor="widget-font-family">
                    Font Family <span className="info-icon" title="Font family for widget text">ℹ️</span>
                  </label>
                  <input
                    type="text"
                    id="widget-font-family"
                    value={widgetSettings.typography.fontFamily}
                    onChange={(e) => handleWidgetChange('typography', 'fontFamily', e.target.value)}
                    placeholder="System font stack"
                  />
                </div>

                <div className="form-group">
                  <label htmlFor="widget-font-size">
                    Font Size <span className="info-icon" title="Base font size (e.g., 14px, 1rem)">ℹ️</span>
                  </label>
                  <input
                    type="text"
                    id="widget-font-size"
                    value={widgetSettings.typography.fontSize}
                    onChange={(e) => handleWidgetChange('typography', 'fontSize', e.target.value)}
                    placeholder="14px"
                  />
                </div>

                <div className="form-group">
                  <label htmlFor="widget-font-weight">
                    Font Weight <span className="info-icon" title="Font weight (100-900)">ℹ️</span>
                  </label>
                  <select
                    id="widget-font-weight"
                    value={widgetSettings.typography.fontWeight}
                    onChange={(e) => handleWidgetChange('typography', 'fontWeight', e.target.value)}
                  >
                    <option value="300">Light (300)</option>
                    <option value="400">Normal (400)</option>
                    <option value="500">Medium (500)</option>
                    <option value="600">Semi-Bold (600)</option>
                    <option value="700">Bold (700)</option>
                  </select>
                </div>
              </div>
            </details>

            {/* Layout & Appearance */}
            <details>
              <summary>Layout & Appearance</summary>
              <div className="form-section">
                <div className="form-group">
                  <label htmlFor="widget-position">
                    Position <span className="info-icon" title="Widget position on the page">ℹ️</span>
                  </label>
                  <select
                    id="widget-position"
                    value={widgetSettings.layout.position}
                    onChange={(e) => handleWidgetChange('layout', 'position', e.target.value)}
                  >
                    <option value="bottom-right">Bottom Right</option>
                    <option value="bottom-left">Bottom Left</option>
                    <option value="top-right">Top Right</option>
                    <option value="top-left">Top Left</option>
                  </select>
                </div>

                <div className="form-group">
                  <label htmlFor="widget-max-width">
                    Max Width <span className="info-icon" title="Maximum widget width (e.g., 350px)">ℹ️</span>
                  </label>
                  <input
                    type="text"
                    id="widget-max-width"
                    value={widgetSettings.layout.maxWidth}
                    onChange={(e) => handleWidgetChange('layout', 'maxWidth', e.target.value)}
                    placeholder="350px"
                  />
                </div>

                <div className="form-group">
                  <label htmlFor="widget-max-height">
                    Max Height <span className="info-icon" title="Maximum widget height (e.g., 500px)">ℹ️</span>
                  </label>
                  <input
                    type="text"
                    id="widget-max-height"
                    value={widgetSettings.layout.maxHeight}
                    onChange={(e) => handleWidgetChange('layout', 'maxHeight', e.target.value)}
                    placeholder="500px"
                  />
                </div>

                <div className="form-group">
                  <label htmlFor="widget-border-radius">
                    Border Radius <span className="info-icon" title="Corner roundness (e.g., 10px)">ℹ️</span>
                  </label>
                  <input
                    type="text"
                    id="widget-border-radius"
                    value={widgetSettings.layout.borderRadius}
                    onChange={(e) => handleWidgetChange('layout', 'borderRadius', e.target.value)}
                    placeholder="10px"
                  />
                </div>

                <div className="form-group">
                  <label htmlFor="widget-z-index">
                    Z-Index <span className="info-icon" title="Layering priority (higher = on top)">ℹ️</span>
                  </label>
                  <input
                    type="number"
                    id="widget-z-index"
                    value={widgetSettings.layout.zIndex}
                    onChange={(e) => handleWidgetChange('layout', 'zIndex', e.target.value)}
                    placeholder="10000"
                  />
                </div>
              </div>
            </details>

            {/* Behavior */}
            <details>
              <summary>Behavior</summary>
              <div className="form-section">
                <div className="form-group">
                  <label htmlFor="widget-open-behavior">
                    Open Behavior <span className="info-icon" title="How the widget opens">ℹ️</span>
                  </label>
                  <select
                    id="widget-open-behavior"
                    value={widgetSettings.behavior.openBehavior}
                    onChange={(e) => handleWidgetChange('behavior', 'openBehavior', e.target.value)}
                  >
                    <option value="click">Click to Open</option>
                    <option value="auto">Auto-Open</option>
                  </select>
                </div>

                {widgetSettings.behavior.openBehavior === 'auto' && (
                  <div className="form-group">
                    <label htmlFor="widget-auto-open-delay">
                      Auto-Open Delay (seconds) <span className="info-icon" title="Delay before auto-opening">ℹ️</span>
                    </label>
                    <input
                      type="number"
                      id="widget-auto-open-delay"
                      value={widgetSettings.behavior.autoOpenDelay}
                      onChange={(e) => handleWidgetChange('behavior', 'autoOpenDelay', parseInt(e.target.value) || 0)}
                      min="0"
                      placeholder="0"
                    />
                  </div>
                )}
              </div>
            </details>

            {/* Messages */}
            <details>
              <summary>Messages</summary>
              <div className="form-section">
                <div className="form-group">
                  <label htmlFor="widget-welcome-message">
                    Welcome Message <span className="info-icon" title="Header text shown in widget">ℹ️</span>
                  </label>
                  <input
                    type="text"
                    id="widget-welcome-message"
                    value={widgetSettings.messages.welcomeMessage}
                    onChange={(e) => handleWidgetChange('messages', 'welcomeMessage', e.target.value)}
                    placeholder="Chat with us"
                  />
                </div>

                <div className="form-group">
                  <label htmlFor="widget-placeholder">
                    Input Placeholder <span className="info-icon" title="Placeholder text in message input">ℹ️</span>
                  </label>
                  <input
                    type="text"
                    id="widget-placeholder"
                    value={widgetSettings.messages.placeholder}
                    onChange={(e) => handleWidgetChange('messages', 'placeholder', e.target.value)}
                    placeholder="Type your message..."
                  />
                </div>

                <div className="form-group">
                  <label htmlFor="widget-send-button-text">
                    Send Button Text <span className="info-icon" title="Text on the send button">ℹ️</span>
                  </label>
                  <input
                    type="text"
                    id="widget-send-button-text"
                    value={widgetSettings.messages.sendButtonText}
                    onChange={(e) => handleWidgetChange('messages', 'sendButtonText', e.target.value)}
                    placeholder="Send"
                  />
                </div>
              </div>
            </details>

            {/* Accessibility */}
            <details>
              <summary>Accessibility</summary>
              <div className="form-section">
                <div className="form-group">
                  <label>
                    <input
                      type="checkbox"
                      checked={widgetSettings.accessibility.darkMode}
                      onChange={(e) => handleWidgetChange('accessibility', 'darkMode', e.target.checked)}
                    />
                    Dark Mode <span className="info-icon" title="Enable dark mode theme">ℹ️</span>
                  </label>
                </div>

                <div className="form-group">
                  <label>
                    <input
                      type="checkbox"
                      checked={widgetSettings.accessibility.highContrast}
                      onChange={(e) => handleWidgetChange('accessibility', 'highContrast', e.target.checked)}
                    />
                    High Contrast <span className="info-icon" title="Increase contrast for better visibility">ℹ️</span>
                  </label>
                </div>

                <div className="form-group">
                  <label>
                    <input
                      type="checkbox"
                      checked={widgetSettings.accessibility.focusOutline}
                      onChange={(e) => handleWidgetChange('accessibility', 'focusOutline', e.target.checked)}
                    />
                    Focus Outline <span className="info-icon" title="Show focus outline for keyboard navigation">ℹ️</span>
                  </label>
                </div>
              </div>
            </details>

            <button type="submit" className="save-btn" disabled={widgetSaving}>
              {widgetSaving ? 'Saving...' : 'Save Widget Settings'}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
