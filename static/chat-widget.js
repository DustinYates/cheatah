/**
 * Chatter Cheetah Web Chat Widget
 * Simple embeddable chat widget for WordPress and other websites
 * 
 * Usage:
 * <script src="https://your-api-domain.com/static/chat-widget.js"></script>
 * <script>
 *   ChatterCheetah.init({
 *     apiUrl: 'https://your-api-domain.com/api/v1',
 *     tenantId: 1
 *   });
 * </script>
 */

(function() {
  'use strict';

  const ChatterCheetah = {
    config: null,
    sessionId: null,
    isOpen: false,
    isMinimized: false,
    settings: null,

    init: function(config) {
      this.config = config;
      this.createWidget();
      this.attachEventListeners();
      this.fetchSettings();
    },

    fetchSettings: async function() {
      try {
        const response = await fetch(`${this.config.apiUrl}/widget/settings/public?tenant_id=${this.config.tenantId}`);
        if (response.ok) {
          const settings = await response.json();
          this.settings = settings;
          this.applySettings(settings);
        }
      } catch (err) {
        console.error('Failed to load widget settings:', err);
        // Widget will use default CSS values
      }
    },

    applySettings: function(settings) {
      const root = document.documentElement;
      const widget = document.getElementById('chatter-cheetah-widget');

      if (!widget || !settings) return;

      // Apply colors
      if (settings.colors) {
        root.style.setProperty('--cc-primary', settings.colors.primary);
        root.style.setProperty('--cc-secondary', settings.colors.secondary);
        root.style.setProperty('--cc-background', settings.colors.background);
        root.style.setProperty('--cc-text', settings.colors.text);
        root.style.setProperty('--cc-button-text', settings.colors.buttonText);
        root.style.setProperty('--cc-link-color', settings.colors.linkColor);
        root.style.setProperty('--cc-border-color', settings.colors.borderColor);
      }

      // Apply typography
      if (settings.typography) {
        root.style.setProperty('--cc-font-family', settings.typography.fontFamily);
        root.style.setProperty('--cc-font-size', settings.typography.fontSize);
        root.style.setProperty('--cc-font-weight', settings.typography.fontWeight);
        root.style.setProperty('--cc-line-height', settings.typography.lineHeight);
      }

      // Apply layout
      if (settings.layout) {
        root.style.setProperty('--cc-border-radius', settings.layout.borderRadius);
        root.style.setProperty('--cc-box-shadow', settings.layout.boxShadow);
        root.style.setProperty('--cc-z-index', settings.layout.zIndex);
        root.style.setProperty('--cc-max-width', settings.layout.maxWidth);
        root.style.setProperty('--cc-max-height', settings.layout.maxHeight);
        root.style.setProperty('--cc-opacity', settings.layout.opacity);

        // Apply position
        const positions = {
          'bottom-right': { bottom: '20px', right: '20px', top: 'auto', left: 'auto' },
          'bottom-left': { bottom: '20px', left: '20px', top: 'auto', right: 'auto' },
          'top-right': { top: '20px', right: '20px', bottom: 'auto', left: 'auto' },
          'top-left': { top: '20px', left: '20px', bottom: 'auto', right: 'auto' }
        };
        const pos = positions[settings.layout.position] || positions['bottom-right'];
        Object.keys(pos).forEach(key => {
          widget.style[key] = pos[key];
        });
      }

      // Apply messages
      if (settings.messages) {
        const titleEl = widget.querySelector('.cc-widget-title');
        if (titleEl) titleEl.textContent = settings.messages.welcomeMessage;

        const inputEl = widget.querySelector('#cc-message-input');
        if (inputEl) inputEl.placeholder = settings.messages.placeholder;

        const sendBtn = widget.querySelector('#cc-send-button');
        if (sendBtn) sendBtn.textContent = settings.messages.sendButtonText;
      }

      // Apply behavior
      if (settings.behavior) {
        if (settings.behavior.openBehavior === 'auto' && settings.behavior.autoOpenDelay > 0) {
          setTimeout(() => {
            if (!this.isOpen) {
              this.toggleWidget();
            }
          }, settings.behavior.autoOpenDelay * 1000);
        }
      }

      // Apply accessibility
      if (settings.accessibility) {
        if (settings.accessibility.darkMode) {
          widget.classList.add('cc-dark-mode');
        }
        if (settings.accessibility.highContrast) {
          widget.classList.add('cc-high-contrast');
        }
        if (!settings.accessibility.focusOutline) {
          widget.classList.add('cc-no-focus-outline');
        }
      }

      // Apply icon settings
      if (settings.icon) {
        this.applyIconSettings(settings.icon);
      }
    },

    applyIconSettings: function(iconSettings) {
      const toggle = document.getElementById('cc-toggle');
      const iconWrapper = toggle ? toggle.querySelector('.cc-icon-wrapper') : null;
      const iconLabel = toggle ? toggle.querySelector('.cc-icon-label') : null;

      if (!toggle) return;

      // Apply icon size
      const sizeMap = {
        'small': '50px',
        'medium': '60px',
        'large': '75px',
        'extra-large': '90px',
        'custom': iconSettings.customSize || '60px'
      };
      const size = sizeMap[iconSettings.size] || '60px';
      toggle.style.width = size;
      toggle.style.height = size;

      // Apply icon shape
      const shapeMap = {
        'circle': '50%',
        'rounded-square': '20%',
        'pill': '50px',
        'square': '0',
        'custom': iconSettings.customBorderRadius || '50%'
      };
      toggle.style.borderRadius = shapeMap[iconSettings.shape] || '50%';

      // Apply icon type (emoji or image)
      if (iconSettings.type === 'image' && iconSettings.imageUrl) {
        // Load custom image
        const img = new Image();
        img.onload = () => {
          if (iconWrapper) {
            iconWrapper.innerHTML = '';
            img.classList.add('cc-icon-image');
            iconWrapper.appendChild(img);
          }
        };
        img.onerror = () => {
          // Fallback to emoji if enabled
          if (iconSettings.fallbackToEmoji && iconWrapper) {
            iconWrapper.textContent = iconSettings.emoji || '💬';
          }
        };
        img.src = iconSettings.imageUrl;
        img.alt = 'Chat';
      } else {
        // Use emoji
        if (iconWrapper) {
          iconWrapper.textContent = iconSettings.emoji || '💬';
        }
      }

      // Apply label settings
      if (iconSettings.showLabel && iconSettings.labelText) {
        if (iconLabel) {
          iconLabel.textContent = iconSettings.labelText;
          iconLabel.style.display = 'block';
          iconLabel.style.backgroundColor = iconSettings.labelBackgroundColor;
          iconLabel.style.color = iconSettings.labelTextColor;
          iconLabel.style.fontSize = iconSettings.labelFontSize;

          // Position label based on labelPosition
          toggle.setAttribute('data-label-position', iconSettings.labelPosition);
        }
      } else {
        if (iconLabel) {
          iconLabel.style.display = 'none';
        }
      }
    },

    createWidget: function() {
      // Create widget container
      const widget = document.createElement('div');
      widget.id = 'chatter-cheetah-widget';
      widget.innerHTML = `
        <div class="cc-widget-container" style="display: none;">
          <div class="cc-widget-header">
            <span class="cc-widget-title">Chat with us</span>
            <button class="cc-widget-minimize" aria-label="Minimize">−</button>
            <button class="cc-widget-close" aria-label="Close">×</button>
          </div>
          <div class="cc-widget-messages" id="cc-messages"></div>
          <div class="cc-widget-input-container" id="cc-input-container">
            <input 
              type="text" 
              id="cc-message-input" 
              placeholder="Type your message..." 
              aria-label="Message input"
            />
            <button id="cc-send-button" aria-label="Send">Send</button>
          </div>
          <div class="cc-widget-contact-form" id="cc-contact-form" style="display: none;">
            <p>To help you better, please provide your contact information:</p>
            <input type="text" id="cc-name-input" placeholder="Name" />
            <input type="email" id="cc-email-input" placeholder="Email" />
            <input type="tel" id="cc-phone-input" placeholder="Phone" />
            <button id="cc-submit-contact">Submit</button>
          </div>
          <div class="cc-widget-loading" id="cc-loading" style="display: none;">
            <span>Thinking...</span>
          </div>
        </div>
        <button class="cc-widget-toggle" id="cc-toggle" aria-label="Open chat">
          <span class="cc-icon-wrapper">💬</span>
          <span class="cc-icon-label" style="display: none;"></span>
        </button>
      `;
      document.body.appendChild(widget);
      this.injectStyles();
    },

    injectStyles: function() {
      const style = document.createElement('style');
      style.textContent = `
        :root {
          --cc-primary: #007bff;
          --cc-secondary: #6c757d;
          --cc-background: #ffffff;
          --cc-text: #333333;
          --cc-button-text: #ffffff;
          --cc-link-color: #007bff;
          --cc-border-color: #ddd;
          --cc-font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
          --cc-font-size: 14px;
          --cc-font-weight: 400;
          --cc-line-height: 1.5;
          --cc-border-radius: 10px;
          --cc-box-shadow: 0 4px 20px rgba(0,0,0,0.15);
          --cc-z-index: 10000;
          --cc-max-width: 350px;
          --cc-max-height: 500px;
          --cc-opacity: 1;
        }
        #chatter-cheetah-widget {
          position: fixed;
          bottom: 20px;
          right: 20px;
          z-index: var(--cc-z-index);
          font-family: var(--cc-font-family);
          opacity: var(--cc-opacity);
        }
        .cc-widget-toggle {
          width: 60px;
          height: 60px;
          border-radius: 50%;
          background: var(--cc-primary);
          color: var(--cc-button-text);
          border: none;
          font-size: 24px;
          cursor: pointer;
          box-shadow: 0 2px 10px rgba(0,0,0,0.2);
          transition: transform 0.2s;
          display: flex;
          align-items: center;
          justify-content: center;
          position: relative;
          overflow: visible;
        }
        .cc-widget-toggle:hover {
          transform: scale(1.1);
        }
        .cc-icon-wrapper {
          display: flex;
          align-items: center;
          justify-content: center;
          width: 100%;
          height: 100%;
        }
        .cc-icon-image {
          max-width: 70%;
          max-height: 70%;
          object-fit: contain;
        }
        .cc-icon-label {
          position: absolute;
          white-space: nowrap;
          padding: 4px 8px;
          border-radius: 4px;
          font-size: 12px;
          font-weight: 500;
          box-shadow: 0 2px 4px rgba(0,0,0,0.1);
          pointer-events: none;
        }
        .cc-widget-toggle[data-label-position="inside"] .cc-icon-label {
          position: static;
          margin-top: 2px;
          font-size: 10px;
        }
        .cc-widget-toggle[data-label-position="inside"] .cc-icon-wrapper {
          flex-direction: column;
          font-size: 20px;
        }
        .cc-widget-toggle[data-label-position="below"] .cc-icon-label {
          bottom: -25px;
          left: 50%;
          transform: translateX(-50%);
        }
        .cc-widget-toggle[data-label-position="beside"] .cc-icon-label {
          right: calc(100% + 10px);
          top: 50%;
          transform: translateY(-50%);
        }
        .cc-widget-toggle[data-label-position="hover"] .cc-icon-label {
          right: calc(100% + 10px);
          top: 50%;
          transform: translateY(-50%);
          opacity: 0;
          transition: opacity 0.2s;
        }
        .cc-widget-toggle[data-label-position="hover"]:hover .cc-icon-label {
          opacity: 1;
        }
        .cc-widget-container {
          width: var(--cc-max-width);
          height: var(--cc-max-height);
          background: var(--cc-background);
          border-radius: var(--cc-border-radius);
          box-shadow: var(--cc-box-shadow);
          display: flex;
          flex-direction: column;
          overflow: hidden;
        }
        .cc-widget-header {
          background: var(--cc-primary);
          color: var(--cc-button-text);
          padding: 15px;
          display: flex;
          justify-content: space-between;
          align-items: center;
        }
        .cc-widget-title {
          font-weight: 600;
        }
        .cc-widget-minimize, .cc-widget-close {
          background: none;
          border: none;
          color: var(--cc-button-text);
          font-size: 20px;
          cursor: pointer;
          padding: 0 5px;
        }
        .cc-widget-messages {
          flex: 1;
          overflow-y: auto;
          padding: 15px;
          background: #f5f5f5;
        }
        .cc-message {
          margin-bottom: 10px;
          padding: 10px;
          border-radius: 8px;
          max-width: 80%;
          word-wrap: break-word;
          font-size: var(--cc-font-size);
          line-height: var(--cc-line-height);
        }
        .cc-message.user {
          background: var(--cc-primary);
          color: var(--cc-button-text);
          margin-left: auto;
          text-align: right;
        }
        .cc-message.assistant {
          background: var(--cc-background);
          color: var(--cc-text);
          border: 1px solid var(--cc-border-color);
        }
        .cc-widget-input-container {
          padding: 15px;
          border-top: 1px solid var(--cc-border-color);
          display: flex;
          gap: 10px;
        }
        #cc-message-input {
          flex: 1;
          padding: 10px;
          border: 1px solid var(--cc-border-color);
          border-radius: 5px;
          font-size: var(--cc-font-size);
          font-family: var(--cc-font-family);
        }
        #cc-send-button {
          padding: 10px 20px;
          background: var(--cc-primary);
          color: var(--cc-button-text);
          border: none;
          border-radius: 5px;
          cursor: pointer;
          font-weight: 600;
          font-family: var(--cc-font-family);
        }
        #cc-send-button:hover {
          opacity: 0.9;
        }
        #cc-send-button:disabled {
          background: #ccc;
          cursor: not-allowed;
        }
        .cc-widget-contact-form {
          padding: 15px;
          border-top: 1px solid var(--cc-border-color);
          background: #fff3cd;
        }
        .cc-widget-contact-form input {
          width: 100%;
          padding: 8px;
          margin: 5px 0;
          border: 1px solid var(--cc-border-color);
          border-radius: 5px;
          box-sizing: border-box;
          font-family: var(--cc-font-family);
        }
        #cc-submit-contact {
          width: 100%;
          padding: 10px;
          background: #28a745;
          color: white;
          border: none;
          border-radius: 5px;
          cursor: pointer;
          margin-top: 10px;
          font-family: var(--cc-font-family);
        }
        .cc-widget-loading {
          padding: 10px;
          text-align: center;
          color: #666;
          font-style: italic;
        }
        .cc-widget-container.minimized {
          height: 50px;
        }
        .cc-widget-container.minimized .cc-widget-messages,
        .cc-widget-container.minimized .cc-widget-input-container,
        .cc-widget-container.minimized .cc-widget-contact-form {
          display: none;
        }
        /* Accessibility classes */
        .cc-dark-mode .cc-widget-container {
          background: #1a1a1a;
          color: #ffffff;
        }
        .cc-dark-mode .cc-widget-messages {
          background: #2a2a2a;
        }
        .cc-dark-mode .cc-message.assistant {
          background: #333;
          color: #fff;
          border-color: #444;
        }
        .cc-high-contrast .cc-widget-container {
          border: 2px solid #000;
        }
        .cc-high-contrast .cc-message {
          border: 2px solid currentColor;
        }
        .cc-no-focus-outline *:focus {
          outline: none;
        }
      `;
      document.head.appendChild(style);
    },

    attachEventListeners: function() {
      const toggle = document.getElementById('cc-toggle');
      const close = document.querySelector('.cc-widget-close');
      const minimize = document.querySelector('.cc-widget-minimize');
      const sendButton = document.getElementById('cc-send-button');
      const messageInput = document.getElementById('cc-message-input');
      const submitContact = document.getElementById('cc-submit-contact');

      toggle.addEventListener('click', () => this.toggleWidget());
      close.addEventListener('click', () => this.closeWidget());
      minimize.addEventListener('click', () => this.minimizeWidget());
      sendButton.addEventListener('click', () => this.sendMessage());
      submitContact.addEventListener('click', () => this.submitContactInfo());

      messageInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
          this.sendMessage();
        }
      });
    },

    toggleWidget: function() {
      const container = document.querySelector('.cc-widget-container');
      const toggle = document.getElementById('cc-toggle');
      
      if (this.isOpen) {
        this.closeWidget();
      } else {
        container.style.display = 'flex';
        toggle.style.display = 'none';
        this.isOpen = true;
        this.isMinimized = false;
        document.getElementById('cc-message-input').focus();
      }
    },

    closeWidget: function() {
      const container = document.querySelector('.cc-widget-container');
      const toggle = document.getElementById('cc-toggle');
      container.style.display = 'none';
      toggle.style.display = 'block';
      this.isOpen = false;
    },

    minimizeWidget: function() {
      const container = document.querySelector('.cc-widget-container');
      container.classList.toggle('minimized');
      this.isMinimized = !this.isMinimized;
    },

    addMessage: function(text, role) {
      const messagesContainer = document.getElementById('cc-messages');
      const message = document.createElement('div');
      message.className = `cc-message ${role}`;
      message.textContent = text;
      messagesContainer.appendChild(message);
      messagesContainer.scrollTop = messagesContainer.scrollHeight;
    },

    showContactForm: function() {
      document.getElementById('cc-contact-form').style.display = 'block';
      document.getElementById('cc-input-container').style.display = 'none';
    },

    hideContactForm: function() {
      document.getElementById('cc-contact-form').style.display = 'none';
      document.getElementById('cc-input-container').style.display = 'flex';
    },

    submitContactInfo: function() {
      const name = document.getElementById('cc-name-input').value.trim();
      const email = document.getElementById('cc-email-input').value.trim();
      const phone = document.getElementById('cc-phone-input').value.trim();

      if (!name && !email && !phone) {
        alert('Please provide at least one contact method.');
        return;
      }

      // Send message with contact info
      this.sendMessage(name, email, phone);
      this.hideContactForm();
    },

    sendMessage: async function(name, email, phone) {
      const messageInput = document.getElementById('cc-message-input');
      const sendButton = document.getElementById('cc-send-button');
      const loading = document.getElementById('cc-loading');
      const message = messageInput ? messageInput.value.trim() : '';

      if (!message && !name && !email && !phone) {
        return;
      }

      // Add user message to UI
      if (message) {
        this.addMessage(message, 'user');
        messageInput.value = '';
      }

      // Disable input
      if (messageInput) messageInput.disabled = true;
      if (sendButton) sendButton.disabled = true;
      loading.style.display = 'block';

      try {
        const response = await fetch(`${this.config.apiUrl}/chat`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            tenant_id: this.config.tenantId,
            session_id: this.sessionId,
            message: message || 'Contact information provided',
            user_name: name || null,
            user_email: email || null,
            user_phone: phone || null,
          }),
        });

        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();
        
        // Update session ID
        this.sessionId = data.session_id;

        // Add assistant response
        this.addMessage(data.response, 'assistant');

        // Show contact form if needed
        if (data.requires_contact_info) {
          this.showContactForm();
        }

        // Handle conversation complete
        if (data.conversation_complete) {
          if (messageInput) messageInput.disabled = true;
          if (sendButton) sendButton.disabled = true;
        }

      } catch (error) {
        console.error('Chat error:', error);
        this.addMessage('Sorry, I encountered an error. Please try again.', 'assistant');
      } finally {
        // Re-enable input
        if (messageInput) messageInput.disabled = false;
        if (sendButton) sendButton.disabled = false;
        loading.style.display = 'none';
        if (messageInput) messageInput.focus();
      }
    },
  };

  // Expose globally
  window.ChatterCheetah = ChatterCheetah;
})();

