import { useState, useCallback, useEffect, useMemo, useRef } from 'react';
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
    cooldownDays: 0,
    autoOpenMessageEnabled: false,
    autoOpenMessage: ''
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
  },
  icon: {
    type: 'emoji',
    emoji: '💬',
    imageUrl: '',
    shape: 'circle',
    customBorderRadius: '50%',
    size: 'medium',
    customSize: '60px',
    showLabel: false,
    labelText: '',
    labelPosition: 'inside',
    labelBackgroundColor: '#ffffff',
    labelTextColor: '#333333',
    labelFontSize: '12px',
    fallbackToEmoji: true
  },
  attention: {
    attentionAnimation: 'none',
    attentionCycles: 2,
    unreadDot: false,
    unreadDotColor: '#ff3b30',
    unreadDotPosition: 'top-right'
  },
  motion: {
    launcherVisibility: 'immediate',
    entryAnimation: 'none',
    openAnimation: 'none',
    delaySeconds: 8,
    scrollPercent: 35,
    exitIntentEnabled: false,
    exitIntentAction: 'show'
  },
  microInteractions: {
    typingIndicator: false,
    typingIndicatorDurationMs: 1200,
    blinkCursor: false,
    hoverEffect: 'scale',
    buttonAnimation: 'none'
  },
  copy: {
    launcherPromptsEnabled: false,
    launcherPrompts: [
      'Have a question?',
      'Need help right now?',
      'Get a quick answer'
    ],
    launcherPromptRotateSeconds: 6,
    contextualPromptsEnabled: false,
    contextualPrompts: [
      { match: '/pricing', text: 'Want help choosing a plan?' },
      { match: '/contact', text: 'Prefer texting instead?' }
    ],
    greetingEnabled: false,
    greetingMode: 'time',
    greetingMorning: 'Good morning! How can we help?',
    greetingAfternoon: 'Good afternoon! How can we help?',
    greetingEvening: 'Good evening! How can we help?',
    greetingPageRules: []
  },
  sound: {
    chimeOnOpen: false,
    messageTicks: false,
    hapticFeedback: false,
    volume: 0.2
  },
  socialProof: {
    showResponseTime: false,
    responseTimeText: 'Typically replies in under 1 min',
    availabilityText: '',
    showAvatar: false,
    avatarUrl: '',
    agentName: 'Cheetah Assistant'
  },
  rules: {
    animateOncePerSession: true,
    stopAfterInteraction: true,
    maxAnimationSeconds: 3,
    respectReducedMotion: true,
    disableOnMobile: false
  }
};

const fontOptions = [
  {
    label: 'System',
    value: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif"
  },
  {
    label: 'Open Sans',
    value: "'Open Sans', Arial, sans-serif"
  },
  {
    label: 'Source Sans 3',
    value: "'Source Sans 3', 'Source Sans Pro', Arial, sans-serif"
  },
  {
    label: 'Roboto',
    value: "'Roboto', Arial, sans-serif"
  },
  {
    label: 'Montserrat',
    value: "'Montserrat', 'Helvetica Neue', Arial, sans-serif"
  },
  {
    label: 'Poppins',
    value: "'Poppins', 'Helvetica Neue', Arial, sans-serif"
  },
  {
    label: 'Playfair Display',
    value: "'Playfair Display', 'Times New Roman', serif"
  },
  {
    label: 'Merriweather',
    value: "'Merriweather', Georgia, serif"
  },
  {
    label: 'Lora',
    value: "'Lora', Georgia, serif"
  }
];

const previewTargetByCategory = {
  colors: 'window',
  typography: 'window',
  layout: 'window',
  behavior: 'window',
  messages: 'window',
  copy: 'window',
  microInteractions: 'window',
  sound: 'window',
  socialProof: 'window',
  accessibility: 'window',
  icon: 'launcher',
  attention: 'launcher',
  motion: 'launcher',
  rules: 'launcher'
};

const emojiOptions = [
  { label: 'Speech Bubble', value: '💬' },
  { label: 'Waving Hand', value: '👋' },
  { label: 'Robot', value: '🤖' },
  { label: 'Headset', value: '🎧' },
  { label: 'Sparkles', value: '✨' },
  { label: 'Lightning', value: '⚡' },
  { label: 'Question Mark', value: '❓' },
  { label: 'Chat Bubble', value: '🗨️' },
  { label: 'Smile', value: '😊' },
  { label: 'Megaphone', value: '📣' }
];

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
  const [widgetBaseline, setWidgetBaseline] = useState(defaultWidgetSettings);
  const [widgetSaving, setWidgetSaving] = useState(false);
  const [widgetSuccess, setWidgetSuccess] = useState('');
  const [widgetError, setWidgetError] = useState('');
  const [widgetLoading, setWidgetLoading] = useState(false);
  const [showWidgetAdvanced, setShowWidgetAdvanced] = useState(false);
  const [previewFocus, setPreviewFocus] = useState('');
  const [previewPulse, setPreviewPulse] = useState('');
  const previewPulseTimeout = useRef(null);

  // Telephony config state (for SMS phone number display)
  const [telephonyConfig, setTelephonyConfig] = useState(null);
  const iconSizeMap = {
    small: '50px',
    medium: '60px',
    large: '75px',
    'extra-large': '90px'
  };
  const previewIconSize = widgetSettings.icon.size === 'custom'
    ? widgetSettings.icon.customSize || iconSizeMap.medium
    : iconSizeMap[widgetSettings.icon.size] || iconSizeMap.medium;
  const previewIconRadius = (() => {
    switch (widgetSettings.icon.shape) {
      case 'rounded-square':
        return '16px';
      case 'pill':
        return '999px';
      case 'square':
        return '6px';
      case 'custom':
        return widgetSettings.icon.customBorderRadius || '18px';
      case 'circle':
      default:
        return '50%';
    }
  })();
  const previewFontFamily = widgetSettings.typography.fontFamily || 'inherit';
  const previewFontSize = widgetSettings.typography.fontSize || '14px';
  const previewLabelPosition = widgetSettings.icon.labelPosition === 'beside'
    ? 'left'
    : widgetSettings.icon.labelPosition;
  const hasWidgetChanges = useMemo(
    () => JSON.stringify(widgetSettings) !== JSON.stringify(widgetBaseline),
    [widgetSettings, widgetBaseline]
  );

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
      setWidgetBaseline(data);
    } catch (err) {
      setWidgetError(err.message || 'Failed to load widget settings');
    } finally {
      setWidgetLoading(false);
    }
  }, [user, selectedTenantId]);

  useEffect(() => {
    fetchWidgetSettings();
  }, [fetchWidgetSettings]);

  useEffect(() => {
    if (!hasWidgetChanges) return;
    const handleBeforeUnload = (event) => {
      event.preventDefault();
      event.returnValue = '';
    };
    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => window.removeEventListener('beforeunload', handleBeforeUnload);
  }, [hasWidgetChanges]);

  useEffect(() => () => {
    if (previewPulseTimeout.current) {
      clearTimeout(previewPulseTimeout.current);
    }
  }, []);

  // Fetch telephony config for SMS phone display
  const fetchTelephonyConfig = useCallback(async () => {
    if (user?.is_global_admin && !selectedTenantId) return;
    try {
      const data = await api.getTelephonyConfig();
      setTelephonyConfig(data);
    } catch (err) {
      // Telephony config is optional, don't show error
      console.log('Telephony config not available:', err.message);
    }
  }, [user, selectedTenantId]);

  useEffect(() => {
    fetchTelephonyConfig();
  }, [fetchTelephonyConfig]);

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

  const pulsePreview = useCallback((category) => {
    const target = previewTargetByCategory[category] || 'window';
    setPreviewPulse(target);
    if (previewPulseTimeout.current) {
      clearTimeout(previewPulseTimeout.current);
    }
    previewPulseTimeout.current = setTimeout(() => {
      setPreviewPulse('');
    }, 650);
  }, []);

  const handlePreviewHover = useCallback((event) => {
    const targetElement = event.target.closest('[data-preview-target]');
    if (!targetElement) return;
    setPreviewFocus(targetElement.dataset.previewTarget || '');
  }, []);

  const handleWidgetChange = (category, field, value) => {
    setWidgetSettings(prev => ({
      ...prev,
      [category]: {
        ...prev[category],
        [field]: value
      }
    }));
    pulsePreview(category);
  };

  const handleWidgetListChange = (category, field, list) => {
    setWidgetSettings(prev => ({
      ...prev,
      [category]: {
        ...prev[category],
        [field]: list
      }
    }));
    pulsePreview(category);
  };

  const handleWidgetListItemChange = (category, field, index, key, value) => {
    setWidgetSettings(prev => ({
      ...prev,
      [category]: {
        ...prev[category],
        [field]: (prev[category][field] || []).map((item, idx) => (
          idx === index ? { ...item, [key]: value } : item
        ))
      }
    }));
    pulsePreview(category);
  };

  const addWidgetListItem = (category, field, item) => {
    setWidgetSettings(prev => ({
      ...prev,
      [category]: {
        ...prev[category],
        [field]: [...(prev[category][field] || []), item]
      }
    }));
    pulsePreview(category);
  };

  const removeWidgetListItem = (category, field, index) => {
    setWidgetSettings(prev => ({
      ...prev,
      [category]: {
        ...prev[category],
        [field]: (prev[category][field] || []).filter((_, idx) => idx !== index)
      }
    }));
    pulsePreview(category);
  };

  const handleWidgetSubmit = async (e) => {
    e.preventDefault();
    setWidgetError('');
    setWidgetSuccess('');
    setWidgetSaving(true);

    try {
      await api.updateWidgetSettings(widgetSettings);
      setWidgetBaseline(widgetSettings);
      setWidgetSuccess('Saved for this tenant');
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
            {' '}<a href="/telephony-settings">Configure in Telephony Settings</a>
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

        {!widgetLoading && (
          <div className="widget-customization-layout">
            <form
              onSubmit={handleWidgetSubmit}
              className="settings-form widget-customization-form"
              onMouseOver={handlePreviewHover}
              onMouseLeave={() => setPreviewFocus('')}
            >
              <div className="widget-customization-toolbar">
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={showWidgetAdvanced}
                    onChange={(e) => setShowWidgetAdvanced(e.target.checked)}
                  />
                  <span>Show advanced settings</span>
                  <span className="info-icon" title="Reveals power-user controls like z-index and motion limits.">ⓘ</span>
                </label>
              </div>

              <details open>
                <summary>Core Appearance</summary>
                <div className="form-section" data-preview-target="window">
                  <div className="form-group color-control">
                    <label htmlFor="widget-primary-color">
                      <span>Primary Color</span>
                      <span className="info-icon" title="Select the primary brand color used for headers and buttons.">ⓘ</span>
                    </label>
                    <input
                      type="color"
                      id="widget-primary-color"
                      className="color-swatch"
                      value={widgetSettings.colors.primary}
                      onChange={(e) => handleWidgetChange('colors', 'primary', e.target.value)}
                    />
                  </div>

                  <div className="form-group color-control">
                    <label htmlFor="widget-secondary-color">
                      <span>Secondary Color</span>
                      <span className="info-icon" title="Accent color used for secondary buttons and highlights.">ⓘ</span>
                    </label>
                    <input
                      type="color"
                      id="widget-secondary-color"
                      className="color-swatch"
                      value={widgetSettings.colors.secondary}
                      onChange={(e) => handleWidgetChange('colors', 'secondary', e.target.value)}
                    />
                  </div>

                  <div className="form-group color-control">
                    <label htmlFor="widget-background-color">
                      <span>Background Color</span>
                      <span className="info-icon" title="Sets the widget body background color.">ⓘ</span>
                    </label>
                    <input
                      type="color"
                      id="widget-background-color"
                      className="color-swatch"
                      value={widgetSettings.colors.background}
                      onChange={(e) => handleWidgetChange('colors', 'background', e.target.value)}
                    />
                  </div>

                  <div className="form-group color-control">
                    <label htmlFor="widget-text-color">
                      <span>Text Color</span>
                      <span className="info-icon" title="Controls the default text color inside the widget.">ⓘ</span>
                    </label>
                    <input
                      type="color"
                      id="widget-text-color"
                      className="color-swatch"
                      value={widgetSettings.colors.text}
                      onChange={(e) => handleWidgetChange('colors', 'text', e.target.value)}
                    />
                  </div>

                  <div className="form-group color-control">
                    <label htmlFor="widget-border-color">
                      <span>Border Color</span>
                      <span className="info-icon" title="Defines the border and divider color.">ⓘ</span>
                    </label>
                    <input
                      type="color"
                      id="widget-border-color"
                      className="color-swatch"
                      value={widgetSettings.colors.borderColor}
                      onChange={(e) => handleWidgetChange('colors', 'borderColor', e.target.value)}
                    />
                  </div>

                  <div className="form-group">
                    <label htmlFor="widget-border-radius">
                      Border Radius <span className="info-icon" title="Controls how rounded the widget corners appear.">ⓘ</span>
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
                    <label htmlFor="widget-font-family">
                      Font Family <span className="info-icon" title="Sets the font used throughout the widget.">ⓘ</span>
                    </label>
                    <select
                      id="widget-font-family"
                      value={widgetSettings.typography.fontFamily}
                      onChange={(e) => handleWidgetChange('typography', 'fontFamily', e.target.value)}
                    >
                      {fontOptions.map((option) => (
                        <option key={option.value} value={option.value} style={{ fontFamily: option.value }}>
                          {option.label} - Aa Bb 123
                        </option>
                      ))}
                    </select>
                  </div>

                  <div className="form-group">
                    <label htmlFor="widget-font-size">
                      Font Size <span className="info-icon" title="Sets the base text size for messages and buttons.">ⓘ</span>
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
                      Font Weight <span className="info-icon" title="Controls the boldness of text in the widget.">ⓘ</span>
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

              <details>
                <summary>Launcher Button</summary>
                <div className="form-section" data-preview-target="launcher">
                  <div className="form-group">
                    <label htmlFor="widget-icon-type">
                      Icon Type <span className="info-icon" title="Choose whether to use an emoji or custom image.">ⓘ</span>
                    </label>
                    <select
                      id="widget-icon-type"
                      value={widgetSettings.icon.type}
                      onChange={(e) => handleWidgetChange('icon', 'type', e.target.value)}
                    >
                      <option value="emoji">Emoji</option>
                      <option value="image">Custom Image</option>
                    </select>
                  </div>

                  {widgetSettings.icon.type === 'emoji' && (
                    <div className="form-group">
                      <label htmlFor="widget-icon-emoji">
                        Emoji / Icon Selector <span className="info-icon" title="Pick the emoji that appears in the launcher.">ⓘ</span>
                      </label>
                      <select
                        id="widget-icon-emoji"
                        value={widgetSettings.icon.emoji}
                        onChange={(e) => handleWidgetChange('icon', 'emoji', e.target.value)}
                      >
                        {emojiOptions.map((option) => (
                          <option key={option.value} value={option.value}>
                            {option.value} {option.label}
                          </option>
                        ))}
                      </select>
                    </div>
                  )}

                  {widgetSettings.icon.type === 'image' && (
                    <>
                      <div className="form-group">
                        <label htmlFor="widget-icon-image-url">
                          Image URL <span className="info-icon" title="Paste the URL of your logo or custom icon.">ⓘ</span>
                        </label>
                        <input
                          type="url"
                          id="widget-icon-image-url"
                          value={widgetSettings.icon.imageUrl}
                          onChange={(e) => handleWidgetChange('icon', 'imageUrl', e.target.value)}
                          placeholder="https://example.com/logo.png"
                        />
                        <small>Recommended: Square image, PNG or SVG format, transparent background.</small>
                      </div>

                      <div className="form-group">
                        <label className="checkbox-label">
                          <input
                            type="checkbox"
                            checked={widgetSettings.icon.fallbackToEmoji}
                            onChange={(e) => handleWidgetChange('icon', 'fallbackToEmoji', e.target.checked)}
                          />
                          <span>Fallback to emoji if image fails to load</span>
                          <span className="info-icon" title="Shows the emoji when the image URL cannot be loaded.">ⓘ</span>
                        </label>
                      </div>
                    </>
                  )}

                  <div className="form-group">
                    <label htmlFor="widget-icon-shape">
                      Icon Shape <span className="info-icon" title="Defines the launcher button shape.">ⓘ</span>
                    </label>
                    <select
                      id="widget-icon-shape"
                      value={widgetSettings.icon.shape}
                      onChange={(e) => handleWidgetChange('icon', 'shape', e.target.value)}
                    >
                      <option value="circle">Circle</option>
                      <option value="rounded-square">Rounded Square</option>
                      <option value="pill">Pill/Capsule</option>
                      <option value="square">Square</option>
                      <option value="custom">Custom Border Radius</option>
                    </select>
                  </div>

                  {widgetSettings.icon.shape === 'custom' && (
                    <div className="form-group">
                      <label htmlFor="widget-icon-border-radius">
                        Custom Border Radius <span className="info-icon" title="CSS border-radius value (e.g., 15px, 25%).">ⓘ</span>
                      </label>
                      <input
                        type="text"
                        id="widget-icon-border-radius"
                        value={widgetSettings.icon.customBorderRadius}
                        onChange={(e) => handleWidgetChange('icon', 'customBorderRadius', e.target.value)}
                        placeholder="50%"
                      />
                    </div>
                  )}

                  <div className="form-group">
                    <label htmlFor="widget-icon-size">
                      Icon Size <span className="info-icon" title="Controls the launcher button size.">ⓘ</span>
                    </label>
                    <select
                      id="widget-icon-size"
                      value={widgetSettings.icon.size}
                      onChange={(e) => handleWidgetChange('icon', 'size', e.target.value)}
                    >
                      <option value="small">Small (50px)</option>
                      <option value="medium">Medium (60px)</option>
                      <option value="large">Large (75px)</option>
                      <option value="extra-large">Extra Large (90px)</option>
                      <option value="custom">Custom Size</option>
                    </select>
                  </div>

                  {widgetSettings.icon.size === 'custom' && (
                    <div className="form-group">
                      <label htmlFor="widget-icon-custom-size">
                        Custom Size <span className="info-icon" title="Set a custom size in pixels (e.g., 70px).">ⓘ</span>
                      </label>
                      <input
                        type="text"
                        id="widget-icon-custom-size"
                        value={widgetSettings.icon.customSize}
                        onChange={(e) => handleWidgetChange('icon', 'customSize', e.target.value)}
                        placeholder="60px"
                      />
                    </div>
                  )}

                  <div className="form-group">
                    <label className="checkbox-label">
                      <input
                        type="checkbox"
                        checked={widgetSettings.icon.showLabel}
                        onChange={(e) => handleWidgetChange('icon', 'showLabel', e.target.checked)}
                      />
                      <span>Show Label / Badge</span>
                      <span className="info-icon" title="Adds a short label near the launcher to invite clicks.">ⓘ</span>
                    </label>
                    <small className="checkbox-helper">Helpful for prompting visitors to start a chat.</small>
                  </div>

                  {widgetSettings.icon.showLabel && (
                    <>
                      <div className="form-group">
                        <label htmlFor="widget-icon-label-text">
                          Label Text <span className="info-icon" title="Text displayed inside or near the launcher.">ⓘ</span>
                        </label>
                        <input
                          type="text"
                          id="widget-icon-label-text"
                          value={widgetSettings.icon.labelText}
                          onChange={(e) => handleWidgetChange('icon', 'labelText', e.target.value)}
                          placeholder="Chat"
                          maxLength={20}
                        />
                      </div>

                      <div className="form-group">
                      <label htmlFor="widget-icon-label-position">
                        Label Position <span className="info-icon" title="Controls where the label appears around the launcher.">ⓘ</span>
                      </label>
                      <select
                        id="widget-icon-label-position"
                        value={previewLabelPosition}
                        onChange={(e) => handleWidgetChange('icon', 'labelPosition', e.target.value)}
                      >
                        <option value="inside">Inside Icon</option>
                        <option value="below">Below Icon</option>
                        <option value="left">Left of Icon</option>
                        <option value="right">Right of Icon</option>
                        <option value="hover">Show on Hover</option>
                      </select>
                    </div>

                      <div className="form-group color-control">
                        <label htmlFor="widget-icon-label-bg-color">
                          <span>Label Background Color</span>
                          <span className="info-icon" title="Background color for the label or badge.">ⓘ</span>
                        </label>
                        <input
                          type="color"
                          id="widget-icon-label-bg-color"
                          className="color-swatch"
                          value={widgetSettings.icon.labelBackgroundColor}
                          onChange={(e) => handleWidgetChange('icon', 'labelBackgroundColor', e.target.value)}
                        />
                      </div>

                      <div className="form-group color-control">
                        <label htmlFor="widget-icon-label-text-color">
                          <span>Label Text Color</span>
                          <span className="info-icon" title="Color for the label text.">ⓘ</span>
                        </label>
                        <input
                          type="color"
                          id="widget-icon-label-text-color"
                          className="color-swatch"
                          value={widgetSettings.icon.labelTextColor}
                          onChange={(e) => handleWidgetChange('icon', 'labelTextColor', e.target.value)}
                        />
                      </div>

                      <div className="form-group">
                        <label htmlFor="widget-icon-label-font-size">
                          Label Font Size <span className="info-icon" title="Font size for label text (e.g., 12px).">ⓘ</span>
                        </label>
                        <input
                          type="text"
                          id="widget-icon-label-font-size"
                          value={widgetSettings.icon.labelFontSize}
                          onChange={(e) => handleWidgetChange('icon', 'labelFontSize', e.target.value)}
                          placeholder="12px"
                        />
                      </div>
                    </>
                  )}
                </div>
              </details>

              <details>
                <summary>Layout & Placement</summary>
                <div className="form-section" data-preview-target="window">
                  <div className="form-group">
                    <label htmlFor="widget-position">
                      Position <span className="info-icon" title="Choose where the widget appears on the page.">ⓘ</span>
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
                      Max Width <span className="info-icon" title="Sets the maximum width of the widget window.">ⓘ</span>
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
                      Max Height <span className="info-icon" title="Sets the maximum height of the widget window.">ⓘ</span>
                    </label>
                    <input
                      type="text"
                      id="widget-max-height"
                      value={widgetSettings.layout.maxHeight}
                      onChange={(e) => handleWidgetChange('layout', 'maxHeight', e.target.value)}
                      placeholder="500px"
                    />
                  </div>

                  {showWidgetAdvanced && (
                    <div className="form-group">
                      <label htmlFor="widget-z-index">
                        Z-Index <span className="info-icon" title="Controls stacking order above other page elements.">ⓘ</span>
                      </label>
                      <input
                        type="number"
                        id="widget-z-index"
                        value={widgetSettings.layout.zIndex}
                        onChange={(e) => handleWidgetChange('layout', 'zIndex', e.target.value)}
                        placeholder="10000"
                      />
                    </div>
                  )}
                </div>
              </details>

              <details>
                <summary>Open Behavior</summary>
                <div className="form-section" data-preview-target="window">
                  <div className="form-group">
                    <label htmlFor="widget-open-behavior">
                      Open Behavior <span className="info-icon" title="Choose whether the widget opens on click or automatically.">ⓘ</span>
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
                    <>
                      <div className="form-group">
                        <label htmlFor="widget-auto-open-delay">
                          Auto-Open Delay (seconds) <span className="info-icon" title="Delay before the widget opens automatically.">ⓘ</span>
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

                      <div className="form-group">
                        <label className="checkbox-label">
                          <input
                            type="checkbox"
                            checked={widgetSettings.behavior.autoOpenMessageEnabled}
                            onChange={(e) => handleWidgetChange('behavior', 'autoOpenMessageEnabled', e.target.checked)}
                          />
                          <span>Show auto-open message</span>
                          <span className="info-icon" title="Adds a short prompt when the widget auto-opens.">ⓘ</span>
                        </label>
                        <small className="checkbox-helper">A friendly message can boost responses.</small>
                      </div>

                      {widgetSettings.behavior.autoOpenMessageEnabled && (
                        <div className="form-group">
                          <label htmlFor="widget-auto-open-message">
                            Auto-Open Message <span className="info-icon" title="Text shown when the widget opens automatically.">ⓘ</span>
                          </label>
                          <input
                            type="text"
                            id="widget-auto-open-message"
                            value={widgetSettings.behavior.autoOpenMessage}
                            onChange={(e) => handleWidgetChange('behavior', 'autoOpenMessage', e.target.value)}
                            placeholder="Hi there! Want help finding the right solution?"
                            maxLength={120}
                          />
                        </div>
                      )}
                    </>
                  )}

                  <div className="form-group">
                    <label className="checkbox-label">
                      <input
                        type="checkbox"
                        checked={widgetSettings.rules.animateOncePerSession}
                        onChange={(e) => handleWidgetChange('rules', 'animateOncePerSession', e.target.checked)}
                      />
                      <span>Animate once per session</span>
                      <span className="info-icon" title="Plays attention effects only once per visitor session.">ⓘ</span>
                    </label>
                  </div>

                  <div className="form-group">
                    <label className="checkbox-label">
                      <input
                        type="checkbox"
                        checked={widgetSettings.rules.stopAfterInteraction}
                        onChange={(e) => handleWidgetChange('rules', 'stopAfterInteraction', e.target.checked)}
                      />
                      <span>Stop attention effects after first interaction</span>
                      <span className="info-icon" title="Stops attention effects once the visitor engages.">ⓘ</span>
                    </label>
                  </div>
                </div>
              </details>

              <details>
                <summary>Attention & Motion</summary>
                <div className="form-section" data-preview-target="launcher">
                  <div className="form-group">
                    <label htmlFor="widget-attention-animation">
                      Launcher Attention Animation <span className="info-icon" title="Pick a subtle animation to draw attention.">ⓘ</span>
                    </label>
                    <select
                      id="widget-attention-animation"
                      value={widgetSettings.attention.attentionAnimation}
                      onChange={(e) => handleWidgetChange('attention', 'attentionAnimation', e.target.value)}
                    >
                      <option value="none">None</option>
                      <option value="bounce">Subtle Bounce</option>
                      <option value="pulse">Pulse</option>
                      <option value="glow">Glow</option>
                      <option value="breathing">Breathing</option>
                      <option value="corner-nudge">Corner Nudge</option>
                    </select>
                  </div>

                  <div className="form-group">
                    <label htmlFor="widget-attention-cycles">
                      Animation Cycles <span className="info-icon" title="How many times the attention animation plays.">ⓘ</span>
                    </label>
                    <input
                      type="number"
                      id="widget-attention-cycles"
                      min="1"
                      max="3"
                      value={widgetSettings.attention.attentionCycles}
                      onChange={(e) => handleWidgetChange('attention', 'attentionCycles', parseInt(e.target.value, 10) || 1)}
                    />
                  </div>

                  {showWidgetAdvanced && (
                    <div className="form-group">
                      <label htmlFor="widget-max-animation">
                        Max Animation Duration (seconds) <span className="info-icon" title="Caps how long attention effects can run.">ⓘ</span>
                      </label>
                      <input
                        type="number"
                        id="widget-max-animation"
                        min="1"
                        max="5"
                        value={widgetSettings.rules.maxAnimationSeconds}
                        onChange={(e) => handleWidgetChange('rules', 'maxAnimationSeconds', parseInt(e.target.value, 10) || 3)}
                      />
                    </div>
                  )}

                  <div className="form-group">
                    <label className="checkbox-label">
                      <input
                        type="checkbox"
                        checked={widgetSettings.attention.unreadDot}
                        onChange={(e) => handleWidgetChange('attention', 'unreadDot', e.target.checked)}
                      />
                      <span>Show unread dot until first interaction</span>
                      <span className="info-icon" title="Displays a dot on the launcher to suggest unread activity.">ⓘ</span>
                    </label>
                  </div>

                  {widgetSettings.attention.unreadDot && (
                    <>
                      <div className="form-group color-control">
                        <label htmlFor="widget-unread-dot-color">
                          <span>Unread Dot Color</span>
                          <span className="info-icon" title="Sets the color of the unread dot indicator.">ⓘ</span>
                        </label>
                        <input
                          type="color"
                          id="widget-unread-dot-color"
                          className="color-swatch"
                          value={widgetSettings.attention.unreadDotColor}
                          onChange={(e) => handleWidgetChange('attention', 'unreadDotColor', e.target.value)}
                        />
                      </div>

                      <div className="form-group">
                        <label htmlFor="widget-unread-dot-position">
                          Unread Dot Position <span className="info-icon" title="Choose where the unread dot appears on the launcher.">ⓘ</span>
                        </label>
                        <select
                          id="widget-unread-dot-position"
                          value={widgetSettings.attention.unreadDotPosition}
                          onChange={(e) => handleWidgetChange('attention', 'unreadDotPosition', e.target.value)}
                        >
                          <option value="top-right">Top Right</option>
                          <option value="top-left">Top Left</option>
                          <option value="bottom-right">Bottom Right</option>
                          <option value="bottom-left">Bottom Left</option>
                        </select>
                      </div>
                    </>
                  )}

                  <div className="form-group">
                    <label htmlFor="widget-launcher-visibility">
                      Launcher Reveal <span className="info-icon" title="Controls when the launcher appears on the page.">ⓘ</span>
                    </label>
                    <select
                      id="widget-launcher-visibility"
                      value={widgetSettings.motion.launcherVisibility}
                      onChange={(e) => handleWidgetChange('motion', 'launcherVisibility', e.target.value)}
                    >
                      <option value="immediate">Immediate</option>
                      <option value="delay">Delayed Entrance</option>
                      <option value="scroll">Scroll Trigger</option>
                      <option value="exit-intent">Exit Intent</option>
                    </select>
                  </div>

                  {widgetSettings.motion.launcherVisibility === 'delay' && (
                    <div className="form-group">
                      <label htmlFor="widget-launcher-delay">
                        Delay (seconds) <span className="info-icon" title="Delay before showing the launcher.">ⓘ</span>
                      </label>
                      <input
                        type="number"
                        id="widget-launcher-delay"
                        min="1"
                        max="30"
                        value={widgetSettings.motion.delaySeconds}
                        onChange={(e) => handleWidgetChange('motion', 'delaySeconds', parseInt(e.target.value, 10) || 5)}
                      />
                    </div>
                  )}

                  {widgetSettings.motion.launcherVisibility === 'scroll' && (
                    <div className="form-group">
                      <label htmlFor="widget-launcher-scroll">
                        Scroll Trigger (%) <span className="info-icon" title="Show the launcher after this scroll depth.">ⓘ</span>
                      </label>
                      <input
                        type="number"
                        id="widget-launcher-scroll"
                        min="10"
                        max="90"
                        value={widgetSettings.motion.scrollPercent}
                        onChange={(e) => handleWidgetChange('motion', 'scrollPercent', parseInt(e.target.value, 10) || 30)}
                      />
                    </div>
                  )}

                  {widgetSettings.motion.launcherVisibility === 'exit-intent' && (
                    <>
                      <div className="form-group">
                        <label className="checkbox-label">
                          <input
                            type="checkbox"
                            checked={widgetSettings.motion.exitIntentEnabled}
                            onChange={(e) => handleWidgetChange('motion', 'exitIntentEnabled', e.target.checked)}
                          />
                          <span>Enable exit-intent detection (desktop only)</span>
                          <span className="info-icon" title="Detects when a user is about to leave on desktop.">ⓘ</span>
                        </label>
                      </div>

                      {widgetSettings.motion.exitIntentEnabled && (
                        <div className="form-group">
                          <label htmlFor="widget-exit-intent-action">
                            Exit Intent Action <span className="info-icon" title="Choose what happens when exit intent is detected.">ⓘ</span>
                          </label>
                          <select
                            id="widget-exit-intent-action"
                            value={widgetSettings.motion.exitIntentAction}
                            onChange={(e) => handleWidgetChange('motion', 'exitIntentAction', e.target.value)}
                          >
                            <option value="show">Show Launcher</option>
                            <option value="open">Open Widget</option>
                          </select>
                        </div>
                      )}
                    </>
                  )}

                  <div className="form-group">
                    <label htmlFor="widget-entry-animation">
                      Launcher Entry Animation <span className="info-icon" title="How the launcher animates into view.">ⓘ</span>
                    </label>
                    <select
                      id="widget-entry-animation"
                      value={widgetSettings.motion.entryAnimation}
                      onChange={(e) => handleWidgetChange('motion', 'entryAnimation', e.target.value)}
                    >
                      <option value="none">None</option>
                      <option value="slide-up">Slide Up</option>
                      <option value="slide-left">Slide In From Right</option>
                      <option value="slide-right">Slide In From Left</option>
                      <option value="fade">Fade</option>
                    </select>
                  </div>

                  <div className="form-group">
                    <label htmlFor="widget-open-animation">
                      Widget Open Animation <span className="info-icon" title="Controls the animation when the chat opens.">ⓘ</span>
                    </label>
                    <select
                      id="widget-open-animation"
                      value={widgetSettings.motion.openAnimation}
                      onChange={(e) => handleWidgetChange('motion', 'openAnimation', e.target.value)}
                    >
                      <option value="none">None</option>
                      <option value="slide-up">Slide Up</option>
                      <option value="slide-left">Slide In From Right</option>
                      <option value="slide-right">Slide In From Left</option>
                      <option value="fade">Fade</option>
                    </select>
                  </div>

                  {showWidgetAdvanced && (
                    <>
                      <div className="form-group">
                        <label className="checkbox-label">
                          <input
                            type="checkbox"
                            checked={widgetSettings.rules.respectReducedMotion}
                            onChange={(e) => handleWidgetChange('rules', 'respectReducedMotion', e.target.checked)}
                          />
                          <span>Respect prefers-reduced-motion</span>
                          <span className="info-icon" title="Honors user accessibility settings for motion.">ⓘ</span>
                        </label>
                      </div>

                      <div className="form-group">
                        <label className="checkbox-label">
                          <input
                            type="checkbox"
                            checked={widgetSettings.rules.disableOnMobile}
                            onChange={(e) => handleWidgetChange('rules', 'disableOnMobile', e.target.checked)}
                          />
                          <span>Disable attention effects on mobile</span>
                          <span className="info-icon" title="Turns off attention effects for smaller screens.">ⓘ</span>
                        </label>
                      </div>
                    </>
                  )}
                </div>
              </details>

              <details>
                <summary>Micro-Interactions</summary>
                <div className="form-section" data-preview-target="window">
                  <div className="form-group">
                    <label className="checkbox-label">
                      <input
                        type="checkbox"
                        checked={widgetSettings.microInteractions.typingIndicator}
                        onChange={(e) => handleWidgetChange('microInteractions', 'typingIndicator', e.target.checked)}
                      />
                      <span>Typing indicator before first message</span>
                      <span className="info-icon" title="Shows a short typing animation before the first reply.">ⓘ</span>
                    </label>
                  </div>

                  {widgetSettings.microInteractions.typingIndicator && (
                    <div className="form-group">
                      <label htmlFor="widget-typing-duration">
                        Typing Indicator Duration (ms) <span className="info-icon" title="How long the typing indicator runs.">ⓘ</span>
                      </label>
                      <input
                        type="number"
                        id="widget-typing-duration"
                        min="600"
                        max="3000"
                        value={widgetSettings.microInteractions.typingIndicatorDurationMs}
                        onChange={(e) => handleWidgetChange('microInteractions', 'typingIndicatorDurationMs', parseInt(e.target.value, 10) || 1200)}
                      />
                    </div>
                  )}

                  <div className="form-group">
                    <label className="checkbox-label">
                      <input
                        type="checkbox"
                        checked={widgetSettings.microInteractions.blinkCursor}
                        onChange={(e) => handleWidgetChange('microInteractions', 'blinkCursor', e.target.checked)}
                      />
                      <span>Blinking cursor</span>
                      <span className="info-icon" title="Adds a blinking cursor in the input field.">ⓘ</span>
                    </label>
                  </div>

                  <div className="form-group">
                    <label htmlFor="widget-hover-effect">
                      Hover Reaction <span className="info-icon" title="How the launcher reacts when hovered.">ⓘ</span>
                    </label>
                    <select
                      id="widget-hover-effect"
                      value={widgetSettings.microInteractions.hoverEffect}
                      onChange={(e) => handleWidgetChange('microInteractions', 'hoverEffect', e.target.value)}
                    >
                      <option value="none">None</option>
                      <option value="lift">Slight Lift</option>
                      <option value="scale">Subtle Scale</option>
                      <option value="color">Color Shift</option>
                    </select>
                  </div>

                  <div className="form-group">
                    <label htmlFor="widget-button-animation">
                      Button Press Animation <span className="info-icon" title="Feedback animation when pressing buttons.">ⓘ</span>
                    </label>
                    <select
                      id="widget-button-animation"
                      value={widgetSettings.microInteractions.buttonAnimation}
                      onChange={(e) => handleWidgetChange('microInteractions', 'buttonAnimation', e.target.value)}
                    >
                      <option value="none">None</option>
                      <option value="press">Press</option>
                      <option value="ripple">Ripple</option>
                    </select>
                  </div>
                </div>
              </details>

              <details>
                <summary>Copy & Messaging</summary>
                <div className="form-section" data-preview-target="window">
                  <div className="form-group">
                    <label htmlFor="widget-welcome-message">
                      Welcome Message <span className="info-icon" title="Headline shown in the widget header.">ⓘ</span>
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
                      Input Placeholder <span className="info-icon" title="Placeholder text inside the message input.">ⓘ</span>
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
                      Send Button Text <span className="info-icon" title="Text shown on the send button.">ⓘ</span>
                    </label>
                    <input
                      type="text"
                      id="widget-send-button-text"
                      value={widgetSettings.messages.sendButtonText}
                      onChange={(e) => handleWidgetChange('messages', 'sendButtonText', e.target.value)}
                      placeholder="Send"
                    />
                  </div>

                  <div className="form-group">
                    <label className="checkbox-label">
                      <input
                        type="checkbox"
                        checked={widgetSettings.copy.launcherPromptsEnabled}
                        onChange={(e) => handleWidgetChange('copy', 'launcherPromptsEnabled', e.target.checked)}
                      />
                      <span>Rotate launcher micro-prompts</span>
                      <span className="info-icon" title="Cycles short prompts next to the launcher.">ⓘ</span>
                    </label>
                  </div>

                  {widgetSettings.copy.launcherPromptsEnabled && (
                    <>
                      <div className="form-group">
                        <label htmlFor="widget-launcher-prompts">
                          Launcher Prompts (one per line) <span className="info-icon" title="Each line becomes a rotating launcher prompt.">ⓘ</span>
                        </label>
                        <textarea
                          id="widget-launcher-prompts"
                          rows={4}
                          value={(widgetSettings.copy.launcherPrompts || []).join('\n')}
                          onChange={(e) => handleWidgetListChange(
                            'copy',
                            'launcherPrompts',
                            e.target.value.split('\n').map((line) => line.trim()).filter(Boolean)
                          )}
                        />
                      </div>

                      <div className="form-group">
                        <label htmlFor="widget-launcher-rotate">
                          Rotate Every (seconds) <span className="info-icon" title="How often the launcher prompt rotates.">ⓘ</span>
                        </label>
                        <input
                          type="number"
                          id="widget-launcher-rotate"
                          min="3"
                          max="15"
                          value={widgetSettings.copy.launcherPromptRotateSeconds}
                          onChange={(e) => handleWidgetChange('copy', 'launcherPromptRotateSeconds', parseInt(e.target.value, 10) || 6)}
                        />
                      </div>
                    </>
                  )}

                  <div className="form-group">
                    <label className="checkbox-label">
                      <input
                        type="checkbox"
                        checked={widgetSettings.copy.contextualPromptsEnabled}
                        onChange={(e) => handleWidgetChange('copy', 'contextualPromptsEnabled', e.target.checked)}
                      />
                      <span>Contextual launcher text</span>
                      <span className="info-icon" title="Show different launcher prompts by page or URL.">ⓘ</span>
                    </label>
                  </div>

                  {widgetSettings.copy.contextualPromptsEnabled && (
                    <div className="form-group">
                      <label>
                        Contextual Prompt Rules <span className="info-icon" title="Match a URL pattern to a custom launcher prompt.">ⓘ</span>
                      </label>
                      <div className="rule-list">
                        {(widgetSettings.copy.contextualPrompts || []).map((rule, index) => (
                          <div key={`${rule.match}-${index}`} className="rule-row">
                            <input
                              type="text"
                              placeholder="URL match (e.g., /pricing)"
                              title="Page path or pattern to match."
                              value={rule.match}
                              onChange={(e) => handleWidgetListItemChange('copy', 'contextualPrompts', index, 'match', e.target.value)}
                            />
                            <input
                              type="text"
                              placeholder="Prompt text"
                              title="Short prompt shown when the URL matches."
                              value={rule.text}
                              onChange={(e) => handleWidgetListItemChange('copy', 'contextualPrompts', index, 'text', e.target.value)}
                            />
                            <button
                              type="button"
                              className="btn btn-danger btn-sm"
                              title="Remove this rule"
                              onClick={() => removeWidgetListItem('copy', 'contextualPrompts', index)}
                            >
                              Remove
                            </button>
                          </div>
                        ))}
                      </div>
                      <button
                        type="button"
                        className="btn btn-secondary btn-sm"
                        title="Add a new rule"
                        onClick={() => addWidgetListItem('copy', 'contextualPrompts', { match: '', text: '' })}
                      >
                        + Add Rule
                      </button>
                    </div>
                  )}

                  <div className="form-group">
                    <label className="checkbox-label">
                      <input
                        type="checkbox"
                        checked={widgetSettings.copy.greetingEnabled}
                        onChange={(e) => handleWidgetChange('copy', 'greetingEnabled', e.target.checked)}
                      />
                      <span>Personalized greeting</span>
                      <span className="info-icon" title="Shows a greeting based on time or page.">ⓘ</span>
                    </label>
                  </div>

                  {widgetSettings.copy.greetingEnabled && (
                    <>
                      <div className="form-group">
                        <label htmlFor="widget-greeting-mode">
                          Greeting Mode <span className="info-icon" title="Choose when greetings should change.">ⓘ</span>
                        </label>
                        <select
                          id="widget-greeting-mode"
                          value={widgetSettings.copy.greetingMode}
                          onChange={(e) => handleWidgetChange('copy', 'greetingMode', e.target.value)}
                        >
                          <option value="time">Time of Day</option>
                          <option value="page">Page Based</option>
                          <option value="both">Time + Page</option>
                        </select>
                      </div>

                      {(widgetSettings.copy.greetingMode === 'time' || widgetSettings.copy.greetingMode === 'both') && (
                        <>
                          <div className="form-group">
                            <label htmlFor="widget-greeting-morning">
                              Morning Greeting <span className="info-icon" title="Greeting shown in the morning hours.">ⓘ</span>
                            </label>
                            <input
                              type="text"
                              id="widget-greeting-morning"
                              value={widgetSettings.copy.greetingMorning}
                              onChange={(e) => handleWidgetChange('copy', 'greetingMorning', e.target.value)}
                            />
                          </div>
                          <div className="form-group">
                            <label htmlFor="widget-greeting-afternoon">
                              Afternoon Greeting <span className="info-icon" title="Greeting shown in the afternoon hours.">ⓘ</span>
                            </label>
                            <input
                              type="text"
                              id="widget-greeting-afternoon"
                              value={widgetSettings.copy.greetingAfternoon}
                              onChange={(e) => handleWidgetChange('copy', 'greetingAfternoon', e.target.value)}
                            />
                          </div>
                          <div className="form-group">
                            <label htmlFor="widget-greeting-evening">
                              Evening Greeting <span className="info-icon" title="Greeting shown in the evening hours.">ⓘ</span>
                            </label>
                            <input
                              type="text"
                              id="widget-greeting-evening"
                              value={widgetSettings.copy.greetingEvening}
                              onChange={(e) => handleWidgetChange('copy', 'greetingEvening', e.target.value)}
                            />
                          </div>
                        </>
                      )}

                      {(widgetSettings.copy.greetingMode === 'page' || widgetSettings.copy.greetingMode === 'both') && (
                        <div className="form-group">
                          <label>
                            Page-Based Greeting Rules <span className="info-icon" title="Match URLs to custom greeting text.">ⓘ</span>
                          </label>
                          <div className="rule-list">
                            {(widgetSettings.copy.greetingPageRules || []).map((rule, index) => (
                              <div key={`${rule.match}-${index}`} className="rule-row">
                                <input
                                  type="text"
                                  placeholder="URL match (e.g., /pricing)"
                                  title="Page path or pattern to match."
                                  value={rule.match}
                                  onChange={(e) => handleWidgetListItemChange('copy', 'greetingPageRules', index, 'match', e.target.value)}
                                />
                                <input
                                  type="text"
                                  placeholder="Greeting text"
                                  title="Greeting shown when the URL matches."
                                  value={rule.text}
                                  onChange={(e) => handleWidgetListItemChange('copy', 'greetingPageRules', index, 'text', e.target.value)}
                                />
                                <button
                                  type="button"
                                  className="btn btn-danger btn-sm"
                                  title="Remove this rule"
                                  onClick={() => removeWidgetListItem('copy', 'greetingPageRules', index)}
                                >
                                  Remove
                                </button>
                              </div>
                            ))}
                          </div>
                          <button
                            type="button"
                            className="btn btn-secondary btn-sm"
                            title="Add a new rule"
                            onClick={() => addWidgetListItem('copy', 'greetingPageRules', { match: '', text: '' })}
                          >
                            + Add Rule
                          </button>
                        </div>
                      )}
                    </>
                  )}
                </div>
              </details>

              <details>
                <summary>Sound & Feedback</summary>
                <div className="form-section" data-preview-target="window">
                  <div className="form-group">
                    <label className="checkbox-label">
                      <input
                        type="checkbox"
                        checked={widgetSettings.sound.chimeOnOpen}
                        onChange={(e) => handleWidgetChange('sound', 'chimeOnOpen', e.target.checked)}
                      />
                      <span>Soft chime on first open</span>
                      <span className="info-icon" title="Plays a short sound the first time the widget opens.">ⓘ</span>
                    </label>
                  </div>

                  <div className="form-group">
                    <label className="checkbox-label">
                      <input
                        type="checkbox"
                        checked={widgetSettings.sound.messageTicks}
                        onChange={(e) => handleWidgetChange('sound', 'messageTicks', e.target.checked)}
                      />
                      <span>Message sent/received ticks</span>
                      <span className="info-icon" title="Adds light tick sounds for send/receive events.">ⓘ</span>
                    </label>
                  </div>

                  <div className="form-group">
                    <label className="checkbox-label">
                      <input
                        type="checkbox"
                        checked={widgetSettings.sound.hapticFeedback}
                        onChange={(e) => handleWidgetChange('sound', 'hapticFeedback', e.target.checked)}
                      />
                      <span>Haptic feedback (mobile)</span>
                      <span className="info-icon" title="Adds a subtle vibration-style response on mobile.">ⓘ</span>
                    </label>
                  </div>

                  <div className="form-group">
                    <label htmlFor="widget-sound-volume">
                      Volume (0-1) <span className="info-icon" title="Set how loud widget sounds should be.">ⓘ</span>
                    </label>
                    <input
                      type="number"
                      id="widget-sound-volume"
                      min="0"
                      max="1"
                      step="0.1"
                      value={widgetSettings.sound.volume}
                      onChange={(e) => handleWidgetChange('sound', 'volume', parseFloat(e.target.value) || 0)}
                    />
                  </div>
                </div>
              </details>

              <details>
                <summary>Social Proof & Trust</summary>
                <div className="form-section" data-preview-target="window">
                  <div className="form-group">
                    <label className="checkbox-label">
                      <input
                        type="checkbox"
                        checked={widgetSettings.socialProof.showResponseTime}
                        onChange={(e) => handleWidgetChange('socialProof', 'showResponseTime', e.target.checked)}
                      />
                      <span>Show response time</span>
                      <span className="info-icon" title="Shows a response time hint to build trust.">ⓘ</span>
                    </label>
                  </div>

                  {widgetSettings.socialProof.showResponseTime && (
                    <div className="form-group">
                      <label htmlFor="widget-response-time">
                        Response Time Text <span className="info-icon" title="Text shown under the header to set expectations.">ⓘ</span>
                      </label>
                      <input
                        type="text"
                        id="widget-response-time"
                        value={widgetSettings.socialProof.responseTimeText}
                        onChange={(e) => handleWidgetChange('socialProof', 'responseTimeText', e.target.value)}
                      />
                    </div>
                  )}

                  <div className="form-group">
                    <label htmlFor="widget-availability-text">
                      Availability Text <span className="info-icon" title="Short line explaining hours or availability.">ⓘ</span>
                    </label>
                    <input
                      type="text"
                      id="widget-availability-text"
                      value={widgetSettings.socialProof.availabilityText}
                      onChange={(e) => handleWidgetChange('socialProof', 'availabilityText', e.target.value)}
                    />
                  </div>

                  <div className="form-group">
                    <label className="checkbox-label">
                      <input
                        type="checkbox"
                        checked={widgetSettings.socialProof.showAvatar}
                        onChange={(e) => handleWidgetChange('socialProof', 'showAvatar', e.target.checked)}
                      />
                      <span>Show avatar + name</span>
                      <span className="info-icon" title="Displays an agent avatar and name in the widget.">ⓘ</span>
                    </label>
                  </div>

                  {widgetSettings.socialProof.showAvatar && (
                    <>
                      <div className="form-group">
                        <label htmlFor="widget-agent-name">
                          Agent Name <span className="info-icon" title="Name shown next to the avatar.">ⓘ</span>
                        </label>
                        <input
                          type="text"
                          id="widget-agent-name"
                          value={widgetSettings.socialProof.agentName}
                          onChange={(e) => handleWidgetChange('socialProof', 'agentName', e.target.value)}
                        />
                      </div>

                      <div className="form-group">
                        <label htmlFor="widget-avatar-url">
                          Avatar URL <span className="info-icon" title="Image URL for the agent avatar.">ⓘ</span>
                        </label>
                        <input
                          type="url"
                          id="widget-avatar-url"
                          value={widgetSettings.socialProof.avatarUrl}
                          onChange={(e) => handleWidgetChange('socialProof', 'avatarUrl', e.target.value)}
                          placeholder="https://example.com/avatar.png"
                        />
                      </div>
                    </>
                  )}
                </div>
              </details>

              <details>
                <summary>Accessibility</summary>
                <div className="form-section" data-preview-target="window">
                  <div className="form-group">
                    <label className="checkbox-label">
                      <input
                        type="checkbox"
                        checked={widgetSettings.accessibility.darkMode}
                        onChange={(e) => handleWidgetChange('accessibility', 'darkMode', e.target.checked)}
                      />
                      <span>Dark mode</span>
                      <span className="info-icon" title="Switches the widget to a darker color scheme.">ⓘ</span>
                    </label>
                  </div>

                  <div className="form-group">
                    <label className="checkbox-label">
                      <input
                        type="checkbox"
                        checked={widgetSettings.accessibility.highContrast}
                        onChange={(e) => handleWidgetChange('accessibility', 'highContrast', e.target.checked)}
                      />
                      <span>High contrast</span>
                      <span className="info-icon" title="Boosts contrast to improve readability.">ⓘ</span>
                    </label>
                  </div>

                  <div className="form-group">
                    <label className="checkbox-label">
                      <input
                        type="checkbox"
                        checked={widgetSettings.accessibility.focusOutline}
                        onChange={(e) => handleWidgetChange('accessibility', 'focusOutline', e.target.checked)}
                      />
                      <span>Focus outline</span>
                      <span className="info-icon" title="Shows focus outlines for keyboard navigation.">ⓘ</span>
                    </label>
                  </div>
                </div>
              </details>

              <div className="widget-customization-actions">
                <button type="submit" className="save-btn" disabled={widgetSaving}>
                  {widgetSaving ? 'Saving...' : 'Save Changes'}
                </button>
                {widgetSuccess && (
                  <span className="widget-save-status" role="status">
                    {widgetSuccess}
                  </span>
                )}
              </div>
            </form>

            <div className="widget-customization-preview" aria-label="Widget preview">
              <div className="widget-preview-card">
                <div className="widget-preview-header">
                  <h3>Live Preview</h3>
                  <p>See your widget styles update in real time.</p>
                </div>

                <div className="widget-preview-viewport">
                  <div
                    className={`widget-preview-window${previewFocus === 'window' ? ' preview-highlight' : ''}${previewPulse === 'window' ? ' preview-pulse' : ''}`}
                    style={{
                      background: widgetSettings.colors.background,
                      color: widgetSettings.colors.text,
                      borderColor: widgetSettings.colors.borderColor,
                      borderRadius: widgetSettings.layout.borderRadius,
                      boxShadow: widgetSettings.layout.boxShadow,
                      maxWidth: widgetSettings.layout.maxWidth,
                      fontFamily: previewFontFamily,
                      fontSize: previewFontSize
                    }}
                  >
                    <div
                      className="widget-preview-titlebar"
                      style={{
                        background: widgetSettings.colors.primary,
                        color: widgetSettings.colors.buttonText
                      }}
                    >
                      <span>{widgetSettings.messages.welcomeMessage || 'Chat with us'}</span>
                      <span className="widget-preview-status">Online</span>
                    </div>
                    <div className="widget-preview-body">
                      <div className="widget-preview-bubble widget-preview-bubble-in">
                        Hi! Need help getting started?
                      </div>
                      <div
                        className="widget-preview-bubble widget-preview-bubble-out"
                        style={{
                          background: widgetSettings.colors.secondary,
                          color: widgetSettings.colors.buttonText
                        }}
                      >
                        I want to customize the widget.
                      </div>
                    </div>
                    <div className="widget-preview-input">
                      <span className="widget-preview-placeholder">
                        {widgetSettings.messages.placeholder || 'Type your message...'}
                      </span>
                      <button
                        type="button"
                        style={{
                          background: widgetSettings.colors.primary,
                          color: widgetSettings.colors.buttonText
                        }}
                      >
                        {widgetSettings.messages.sendButtonText || 'Send'}
                      </button>
                    </div>
                  </div>

                  <div className="widget-preview-icon-wrap">
                    <div
                      className={`widget-preview-icon${previewFocus === 'launcher' ? ' preview-highlight' : ''}${previewPulse === 'launcher' ? ' preview-pulse' : ''}`}
                      style={{
                        width: previewIconSize,
                        height: previewIconSize,
                        borderRadius: previewIconRadius,
                        background: widgetSettings.colors.primary,
                        color: widgetSettings.colors.buttonText
                      }}
                    >
                      {widgetSettings.icon.type === 'emoji' && (widgetSettings.icon.emoji || '💬')}
                      {widgetSettings.icon.type === 'image' && widgetSettings.icon.imageUrl && (
                        <img src={widgetSettings.icon.imageUrl} alt="Widget icon preview" />
                      )}
                      {widgetSettings.icon.type === 'image' && !widgetSettings.icon.imageUrl && (
                        <span>{widgetSettings.icon.fallbackToEmoji ? (widgetSettings.icon.emoji || '💬') : '◎'}</span>
                      )}
                      {widgetSettings.attention.unreadDot && (
                        <span
                          className={`widget-preview-unread widget-preview-unread-${widgetSettings.attention.unreadDotPosition}`}
                          style={{ background: widgetSettings.attention.unreadDotColor }}
                        />
                      )}
                    </div>
                    {widgetSettings.icon.showLabel && (
                      <div
                        className={`widget-preview-label widget-preview-label-${previewLabelPosition}`}
                        style={{
                          background: widgetSettings.icon.labelBackgroundColor,
                          color: widgetSettings.icon.labelTextColor,
                          fontSize: widgetSettings.icon.labelFontSize
                        }}
                      >
                        {widgetSettings.icon.labelText || 'Chat'}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
