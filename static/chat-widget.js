/**
 * Chatter Cheetah Web Chat Widget
 * Simple embeddable chat widget for WordPress and other websites
 * 
 * Usage:
 * <script src="https://your-api-domain.com/static/chat-widget.js"></script>
 * <script>
 *   ChatterCheetah.init({
 *     apiUrl: 'https://your-api-domain.com/api/v1',
 *     tenantId: 1,
 *     scrollBehavior: 'top'
 *   });
 * </script>
 */

(function() {
  'use strict';

  // Initialize dataLayer for GTM compatibility (ES5)
  window.dataLayer = window.dataLayer || [];

  const ChatterCheetah = {
    config: null,
    sessionId: null,
    isOpen: false,
    isMinimized: false,
    settings: null,
    messages: [], // In-memory message cache
    promptInterval: null,
    promptTarget: null,
    promptUsesBubble: true,
    labelDefaultText: '',
    typingTimeout: null,
    entryTimeout: null,
    attentionTimeout: null,
    autoOpenTimeout: null,
    exitIntentBound: false,
    scrollHandler: null,
    pendingEscalationMessage: null, // Store message while waiting for contact info
    userMessageCount: 0, // Track user messages for GA4 analytics

    // Widget Analytics Tracking
    analyticsQueue: [],
    analyticsFlushInterval: null,
    visitorId: null,
    pageLoadTime: null,
    wasAutoOpened: false,

    // GTM dataLayer event helper (ES5 compatible)
    pushDataLayerEvent: function(eventName, additionalData) {
      var eventData = {
        event: eventName,
        tenant_id: this.config ? this.config.tenantId : null,
        timestamp: new Date().toISOString()
      };
      if (additionalData) {
        for (var key in additionalData) {
          if (additionalData.hasOwnProperty(key)) {
            eventData[key] = additionalData[key];
          }
        }
      }
      window.dataLayer.push(eventData);
    },

    // Storage keys (tenant-specific to avoid conflicts)
    getStorageKey: function(suffix) {
      return `cc_${this.config.tenantId}_${suffix}`;
    },

    getSessionFlag: function(flag) {
      return sessionStorage.getItem(this.getStorageKey(flag)) === 'true';
    },

    setSessionFlag: function(flag, value) {
      sessionStorage.setItem(this.getStorageKey(flag), value ? 'true' : 'false');
    },

    isMobile: function() {
      return window.matchMedia && window.matchMedia('(hover: none)').matches;
    },

    prefersReducedMotion: function() {
      return window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    },

    // Initialize or restore visitor ID (persistent across sessions)
    initVisitorId: function() {
      var key = 'cc_visitor_id';
      var storedId = null;
      try {
        storedId = localStorage.getItem(key);
      } catch (e) {
        // localStorage may be disabled
      }
      if (storedId) {
        this.visitorId = storedId;
      } else {
        // Generate UUID-like ID
        this.visitorId = 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
          var r = Math.random() * 16 | 0;
          var v = c === 'x' ? r : (r & 0x3 | 0x8);
          return v.toString(16);
        });
        try {
          localStorage.setItem(key, this.visitorId);
        } catch (e) {
          // localStorage may be disabled
        }
      }
    },

    // Track analytics event (batched for efficiency)
    trackEvent: function(eventType, eventData, settingsSnapshot) {
      if (!this.config || !this.visitorId) return;

      var event = {
        event_type: eventType,
        session_id: this.sessionId || null,
        event_data: eventData || {},
        client_timestamp: new Date().toISOString()
      };

      // Add settings snapshot if provided (for A/B testing)
      if (settingsSnapshot) {
        event.settings_snapshot = settingsSnapshot;
      }

      this.analyticsQueue.push(event);

      // Flush immediately for important events
      var immediateEvents = ['widget_open', 'first_message', 'lead_collected'];
      if (immediateEvents.indexOf(eventType) !== -1) {
        this.flushAnalytics();
      }
    },

    // Flush analytics queue to server
    flushAnalytics: function() {
      var self = this;
      if (this.analyticsQueue.length === 0 || !this.config) return;

      var events = this.analyticsQueue.slice();
      this.analyticsQueue = [];

      var payload = {
        tenant_id: this.config.tenantId,
        visitor_id: this.visitorId,
        events: events
      };

      var url = this.config.apiUrl + '/widget/events';
      var data = JSON.stringify(payload);

      // Use sendBeacon for reliability (especially on page unload)
      if (navigator.sendBeacon) {
        try {
          navigator.sendBeacon(url, new Blob([data], { type: 'application/json' }));
        } catch (e) {
          // Fall back to fetch
          this.sendAnalyticsFetch(url, data, events);
        }
      } else {
        this.sendAnalyticsFetch(url, data, events);
      }
    },

    // Fallback fetch for analytics
    sendAnalyticsFetch: function(url, data, events) {
      var self = this;
      fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: data,
        keepalive: true
      }).catch(function() {
        // Re-queue on failure (but limit to avoid infinite growth)
        if (self.analyticsQueue.length < 50) {
          self.analyticsQueue = events.concat(self.analyticsQueue);
        }
      });
    },

    // Start analytics flush interval
    startAnalyticsInterval: function() {
      var self = this;
      if (this.analyticsFlushInterval) return;

      // Flush every 10 seconds
      this.analyticsFlushInterval = setInterval(function() {
        self.flushAnalytics();
      }, 10000);

      // Flush on page unload
      window.addEventListener('beforeunload', function() {
        self.flushAnalytics();
      });

      // Also flush on visibility change (tab hidden)
      document.addEventListener('visibilitychange', function() {
        if (document.visibilityState === 'hidden') {
          self.flushAnalytics();
        }
      });
    },

    // Track impression and viewport visibility
    trackImpression: function() {
      var self = this;

      // Build comprehensive settings snapshot for A/B testing analysis
      var settingsSnapshot = null;
      if (this.settings) {
        settingsSnapshot = {
          // Behavior settings
          open_behavior: (this.settings.behavior && this.settings.behavior.openBehavior) || 'click',
          auto_open_delay: (this.settings.behavior && this.settings.behavior.autoOpenDelay) || 0,
          // Attention settings
          attention_animation: (this.settings.attention && this.settings.attention.attentionAnimation) || 'none',
          unread_dot: (this.settings.attention && this.settings.attention.unreadDot) || false,
          // Motion settings
          launcher_visibility: (this.settings.motion && this.settings.motion.launcherVisibility) || 'immediate',
          entry_animation: (this.settings.motion && this.settings.motion.entryAnimation) || 'none',
          // Layout/appearance settings
          position: (this.settings.layout && this.settings.layout.position) || 'bottom-right',
          border_radius: (this.settings.layout && this.settings.layout.borderRadius) || '10px',
          // Icon settings
          icon_type: (this.settings.icon && this.settings.icon.type) || 'emoji',
          icon_shape: (this.settings.icon && this.settings.icon.shape) || 'circle',
          icon_size: (this.settings.icon && this.settings.icon.size) || 'medium',
          show_label: (this.settings.icon && this.settings.icon.showLabel) || false,
          // Colors (key branding)
          primary_color: (this.settings.colors && this.settings.colors.primary) || '#007bff',
          // Copy/messaging settings
          launcher_prompts_enabled: (this.settings.copy && this.settings.copy.launcherPromptsEnabled) || false,
          greeting_enabled: (this.settings.copy && this.settings.copy.greetingEnabled) || false,
          // Social proof
          show_response_time: (this.settings.socialProof && this.settings.socialProof.showResponseTime) || false,
          show_avatar: (this.settings.socialProof && this.settings.socialProof.showAvatar) || false
        };
      }

      // Track page impression with settings snapshot as separate field for A/B testing
      this.trackEvent('impression', {
        page_url: window.location.href,
        referrer: document.referrer || '',
        viewport_width: window.innerWidth,
        viewport_height: window.innerHeight
      }, settingsSnapshot);

      // Track viewport visibility using IntersectionObserver
      var toggle = document.getElementById('cc-toggle');
      if (!toggle || typeof IntersectionObserver === 'undefined') return;

      var startTime = Date.now();
      var observer = new IntersectionObserver(function(entries) {
        entries.forEach(function(entry) {
          if (entry.isIntersecting) {
            var timeToView = Date.now() - startTime;
            var rect = entry.boundingClientRect;
            var wasAboveFold = rect.top < window.innerHeight && rect.top >= 0;

            self.trackEvent('viewport_visible', {
              time_to_first_view_ms: timeToView,
              was_above_fold: wasAboveFold
            });

            observer.disconnect();
          }
        });
      }, { threshold: 0.5 });

      observer.observe(toggle);
    },

    // Track hover/focus events on the launcher
    trackHoverFocus: function() {
      var self = this;
      var toggle = document.getElementById('cc-toggle');
      if (!toggle) return;

      var hoverStartTime = null;

      toggle.addEventListener('mouseenter', function() {
        hoverStartTime = Date.now();
      });

      toggle.addEventListener('mouseleave', function() {
        if (hoverStartTime) {
          var duration = Date.now() - hoverStartTime;
          // Only track if hover lasted > 500ms (filters out quick pass-overs)
          if (duration > 500) {
            self.trackEvent('hover', { duration_ms: duration });
          }
          hoverStartTime = null;
        }
      });

      toggle.addEventListener('focus', function() {
        self.trackEvent('focus', {});
      });
    },

    init: function(config) {
      // Default to top so new messages keep the start of responses visible
      this.config = Object.assign({ scrollBehavior: 'top' }, config);
      this.pageLoadTime = Date.now();
      this.initVisitorId();
      this.createWidget();
      this.attachEventListeners();
      this.fetchSettings();
      this.restoreSession(); // Restore previous session on init
      this.startAnalyticsInterval();
      // Track impression after widget is created (defer to allow DOM to settle)
      var self = this;
      setTimeout(function() {
        self.trackImpression();
        self.trackHoverFocus();
      }, 100);
    },

    // Restore session from sessionStorage (clears when tab closes)
    restoreSession: function() {
      try {
        const storedSessionId = sessionStorage.getItem(this.getStorageKey('session_id'));
        const storedMessages = sessionStorage.getItem(this.getStorageKey('messages'));
        const storedIsOpen = sessionStorage.getItem(this.getStorageKey('is_open'));

        if (storedSessionId) {
          this.sessionId = storedSessionId;
        }

        if (storedMessages) {
          this.messages = JSON.parse(storedMessages);
          this.messages.forEach(msg => {
            this.renderMessage(msg.text, msg.role, false);
          });
          // Restore user message count from restored messages for GA4 tracking
          this.userMessageCount = this.messages.filter(function(m) { return m.role === 'user'; }).length;
        }

        // Restore open/closed state
        if (storedIsOpen === 'true') {
          this.toggleWidget();
        }

        if ((storedMessages && this.messages.length > 0) || storedIsOpen === 'true') {
          this.setSessionFlag('interacted', true);
        }
      } catch (err) {
        console.error('Failed to restore chat session:', err);
      }
    },

    // Save session to sessionStorage (clears when tab closes)
    saveSession: function() {
      try {
        if (this.sessionId) {
          sessionStorage.setItem(this.getStorageKey('session_id'), this.sessionId);
        }
        sessionStorage.setItem(this.getStorageKey('messages'), JSON.stringify(this.messages));
        sessionStorage.setItem(this.getStorageKey('is_open'), this.isOpen.toString());
      } catch (err) {
        console.error('Failed to save chat session:', err);
      }
    },

    // Clear session (for starting fresh)
    clearSession: function() {
      try {
        sessionStorage.removeItem(this.getStorageKey('session_id'));
        sessionStorage.removeItem(this.getStorageKey('messages'));
        sessionStorage.removeItem(this.getStorageKey('is_open'));
        this.sessionId = null;
        this.messages = [];
        const messagesContainer = document.getElementById('cc-messages');
        if (messagesContainer) {
          messagesContainer.innerHTML = '';
        }
      } catch (err) {
        console.error('Failed to clear chat session:', err);
      }
    },

    // Start a new chat conversation
    startNewChat: function() {
      this.clearSession();
      this.userMessageCount = 0; // Reset message count for GA4 tracking
      this.hideContactForm();
      // Re-enable inputs in case they were disabled
      const messageInput = document.getElementById('cc-message-input');
      const sendButton = document.getElementById('cc-send-button');
      if (messageInput) {
        messageInput.disabled = false;
        messageInput.focus();
      }
      if (sendButton) {
        sendButton.disabled = false;
      }
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
      this.settings = settings;

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

        const toggle = document.getElementById('cc-toggle');
        if (toggle) {
          toggle.setAttribute('data-position', settings.layout.position || 'bottom-right');
        }
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
        if (settings.behavior.openBehavior === 'auto') {
          const delaySeconds = Math.max(0, settings.behavior.autoOpenDelay || 0);
          clearTimeout(this.autoOpenTimeout);
          this.autoOpenTimeout = setTimeout(() => {
            if (!this.isOpen) {
              this.toggleWidget({ autoOpen: true });
            }
          }, delaySeconds * 1000);
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

      if (settings.rules?.respectReducedMotion && this.prefersReducedMotion()) {
        widget.classList.add('cc-reduced-motion');
      } else {
        widget.classList.remove('cc-reduced-motion');
      }

      // Apply icon settings
      if (settings.icon) {
        this.applyIconSettings(settings.icon);
      }

      this.applySocialProof(settings);
      this.applyCopySettings(settings);
      this.applyMicroInteractions(settings);
      this.applyMotionSettings(settings);
      this.applyAttentionSettings(settings);
      this.applySoundSettings(settings);
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
        'rounded-square': '16px',
        'pill': '50px',
        'square': '0',
        'custom': iconSettings.customBorderRadius || '50%'
      };
      toggle.style.borderRadius = shapeMap[iconSettings.shape] || '50%';

      // Apply icon type (emoji or image)
      // Determine image URL based on source (upload vs url)
      let imageUrl = null;
      if (iconSettings.type === 'image') {
        if (iconSettings.imageSource === 'upload' && iconSettings.imageAssetUrl) {
          // Use uploaded asset URL with cache busting
          imageUrl = iconSettings.imageAssetUrl + (iconSettings.imageAssetUrl.includes('?') ? '&' : '?') + 'v=' + Date.now();
        } else if (iconSettings.imageSource === 'url' && iconSettings.imageUrl) {
          // Use external URL
          imageUrl = iconSettings.imageUrl;
        } else if (iconSettings.imageUrl) {
          // Backwards compatibility: use imageUrl if no imageSource specified
          imageUrl = iconSettings.imageUrl;
        }
      }

      if (imageUrl) {
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
        img.src = imageUrl;
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
          this.labelDefaultText = iconSettings.labelText;
          iconLabel.textContent = iconSettings.labelText;
          iconLabel.style.display = 'block';
          iconLabel.style.backgroundColor = iconSettings.labelBackgroundColor;
          iconLabel.style.color = iconSettings.labelTextColor;
          iconLabel.style.fontSize = iconSettings.labelFontSize;

          // Position label based on labelPosition
          const labelPosition = iconSettings.labelPosition === 'beside' ? 'left' : iconSettings.labelPosition;
          toggle.setAttribute('data-label-position', labelPosition);
        }
      } else {
        if (iconLabel) {
          iconLabel.style.display = 'none';
        }
      }
    },

    applySocialProof: function(settings) {
      const widget = document.getElementById('chatter-cheetah-widget');
      if (!widget || !settings.socialProof) return;

      const titleEl = widget.querySelector('.cc-widget-title');
      const subtitleEl = widget.querySelector('.cc-widget-subtitle');
      const responseTimeEl = widget.querySelector('.cc-widget-response-time');
      const avatarEl = widget.querySelector('.cc-widget-avatar');
      const agentName = settings.socialProof.agentName || 'Assistant';

      const greetingText = this.getGreetingText(settings.copy);
      const availabilityText = settings.socialProof.availabilityText || '';
      const responseText = settings.socialProof.showResponseTime ? settings.socialProof.responseTimeText : '';

      const baseTitle = titleEl ? titleEl.textContent : 'Chat with us';
      let titleText = baseTitle;
      let subtitleText = availabilityText;
      let secondaryText = responseText;

      if (greetingText) {
        titleText = greetingText;
        subtitleText = availabilityText;
      }

      if (settings.socialProof.showAvatar) {
        titleText = agentName;
        subtitleText = greetingText || availabilityText;
      }

      if (!secondaryText && greetingText && availabilityText && settings.socialProof.showAvatar) {
        secondaryText = availabilityText;
      }

      if (titleEl) {
        titleEl.textContent = titleText;
      }

      if (subtitleEl) {
        subtitleEl.textContent = subtitleText;
        subtitleEl.style.display = subtitleText ? 'block' : 'none';
      }

      if (responseTimeEl) {
        responseTimeEl.textContent = secondaryText;
        responseTimeEl.style.display = secondaryText ? 'block' : 'none';
      }

      if (avatarEl) {
        if (settings.socialProof.showAvatar) {
          avatarEl.style.display = 'block';
          avatarEl.innerHTML = '';
          if (settings.socialProof.avatarUrl) {
            const img = document.createElement('img');
            img.src = settings.socialProof.avatarUrl;
            img.alt = agentName;
            avatarEl.appendChild(img);
          } else {
            avatarEl.textContent = agentName.charAt(0).toUpperCase();
          }
        } else {
          avatarEl.style.display = 'none';
        }
      }
    },

    applyCopySettings: function(settings) {
      const copySettings = settings.copy || {};
      const promptEl = document.querySelector('.cc-launcher-prompt');
      const iconLabel = document.querySelector('.cc-icon-label');
      const useLabelPrompt = iconLabel && iconLabel.style.display !== 'none';
      if (!promptEl) return;
      if (settings.rules?.stopAfterInteraction && this.getSessionFlag('interacted')) {
        this.stopPromptRotation();
        return;
      }

      const contextualText = copySettings.contextualPromptsEnabled
        ? this.getContextualText(copySettings.contextualPrompts)
        : '';

      if (copySettings.launcherPromptsEnabled && copySettings.launcherPrompts?.length) {
        const prompts = contextualText ? [contextualText] : copySettings.launcherPrompts;
        if (useLabelPrompt) {
          if (promptEl) {
            promptEl.classList.remove('is-visible');
            promptEl.style.display = 'none';
          }
          this.startPromptRotation(prompts, copySettings.launcherPromptRotateSeconds || 6, iconLabel, false);
        } else {
          this.startPromptRotation(prompts, copySettings.launcherPromptRotateSeconds || 6, promptEl, true);
        }
      } else if (contextualText) {
        if (useLabelPrompt) {
          if (promptEl) {
            promptEl.classList.remove('is-visible');
            promptEl.style.display = 'none';
          }
          this.startPromptRotation([contextualText], copySettings.launcherPromptRotateSeconds || 6, iconLabel, false);
        } else {
          this.startPromptRotation([contextualText], copySettings.launcherPromptRotateSeconds || 6, promptEl, true);
        }
      } else {
        this.stopPromptRotation();
      }
    },

    applyMicroInteractions: function(settings) {
      const micro = settings.microInteractions || {};
      const toggle = document.getElementById('cc-toggle');
      const inputEl = document.getElementById('cc-message-input');
      const sendButton = document.getElementById('cc-send-button');

      if (toggle) {
        toggle.setAttribute('data-hover', micro.hoverEffect || 'none');
        if (micro.buttonAnimation === 'press') {
          toggle.classList.add('cc-pressable');
        } else {
          toggle.classList.remove('cc-pressable');
        }
      }

      if (inputEl) {
        if (micro.blinkCursor) {
          inputEl.classList.add('cc-blink-cursor');
        } else {
          inputEl.classList.remove('cc-blink-cursor');
        }
      }

      if (sendButton) {
        if (micro.buttonAnimation === 'press') {
          sendButton.classList.add('cc-pressable');
        } else {
          sendButton.classList.remove('cc-pressable');
        }
      }
    },

    applyMotionSettings: function(settings) {
      const motion = settings.motion || {};
      const rules = settings.rules || {};
      const toggle = document.getElementById('cc-toggle');
      if (!toggle) return;

      const disableMotion = (rules.disableOnMobile && this.isMobile())
        || (rules.respectReducedMotion && this.prefersReducedMotion());

      if (disableMotion || motion.launcherVisibility === 'immediate') {
        this.showLauncher(motion.entryAnimation);
        return;
      }

      toggle.style.display = 'none';

      if (motion.launcherVisibility === 'delay') {
        clearTimeout(this.entryTimeout);
        this.entryTimeout = setTimeout(() => {
          this.showLauncher(motion.entryAnimation);
        }, (motion.delaySeconds || 8) * 1000);
        return;
      }

      if (motion.launcherVisibility === 'scroll') {
        if (this.scrollHandler) {
          window.removeEventListener('scroll', this.scrollHandler);
        }
        this.scrollHandler = () => {
          const scrollTop = window.scrollY || document.documentElement.scrollTop;
          const docHeight = document.documentElement.scrollHeight - window.innerHeight;
          const scrolledPercent = docHeight > 0 ? (scrollTop / docHeight) * 100 : 0;
          if (scrolledPercent >= (motion.scrollPercent || 35)) {
            window.removeEventListener('scroll', this.scrollHandler);
            this.showLauncher(motion.entryAnimation);
          }
        };
        window.addEventListener('scroll', this.scrollHandler, { passive: true });
        return;
      }

      if (motion.launcherVisibility === 'exit-intent' && motion.exitIntentEnabled && !this.isMobile()) {
        if (!this.exitIntentBound) {
          this.exitIntentBound = true;
          document.addEventListener('mousemove', (event) => {
            if (event.clientY <= 10 && !this.getSessionFlag('exit_intent_triggered')) {
              this.setSessionFlag('exit_intent_triggered', true);
              if (motion.exitIntentAction === 'open') {
                this.showLauncher(motion.entryAnimation);
                this.toggleWidget();
              } else {
                this.showLauncher(motion.entryAnimation);
              }
            }
          });
        }
      } else if (motion.launcherVisibility === 'exit-intent' && !motion.exitIntentEnabled) {
        this.showLauncher(motion.entryAnimation);
      }
    },

    applyAttentionSettings: function(settings) {
      const attention = settings.attention || {};
      const rules = settings.rules || {};
      const toggle = document.getElementById('cc-toggle');
      if (!toggle) return;

      const disableMotion = (rules.disableOnMobile && this.isMobile())
        || (rules.respectReducedMotion && this.prefersReducedMotion());

      toggle.setAttribute('data-dot-position', attention.unreadDotPosition || 'top-right');
      const unreadDot = toggle.querySelector('.cc-unread-dot');
      if (unreadDot) {
        unreadDot.style.backgroundColor = attention.unreadDotColor || '#ff3b30';
        unreadDot.style.display = attention.unreadDot && !this.getSessionFlag('interacted') ? 'block' : 'none';
      }

      if (disableMotion || attention.attentionAnimation === 'none') {
        toggle.classList.remove('cc-attention');
        toggle.removeAttribute('data-attention');
        return;
      }

      if (toggle.style.display === 'none') {
        toggle.classList.remove('cc-attention');
        toggle.removeAttribute('data-attention');
        return;
      }

      if (rules.stopAfterInteraction && this.getSessionFlag('interacted')) {
        return;
      }

      if (rules.animateOncePerSession && this.getSessionFlag('attention_played')) {
        return;
      }

      const durationMap = {
        bounce: 1.2,
        pulse: 1.3,
        glow: 1.8,
        breathing: 2.4,
        'corner-nudge': 1.2
      };
      const maxDuration = Math.max(1, rules.maxAnimationSeconds || 3);
      const duration = Math.min(durationMap[attention.attentionAnimation] || 1.2, maxDuration);
      toggle.style.setProperty('--cc-attention-duration', `${duration}s`);
      toggle.style.setProperty('--cc-attention-iterations', attention.attentionCycles || 2);
      toggle.classList.add('cc-attention');
      toggle.setAttribute('data-attention', attention.attentionAnimation);
      this.setSessionFlag('attention_played', true);

      if (attention.attentionAnimation === 'corner-nudge') {
        const position = toggle.getAttribute('data-position') || 'bottom-right';
        const nudgeX = position.endsWith('right') ? -6 : 6;
        const nudgeY = position.startsWith('bottom') ? -6 : 6;
        toggle.style.setProperty('--cc-nudge-x', `${nudgeX}px`);
        toggle.style.setProperty('--cc-nudge-y', `${nudgeY}px`);
      }
    },

    applySoundSettings: function(settings) {
      this.soundSettings = settings.sound || {};
    },

    showLauncher: function(entryAnimation) {
      const toggle = document.getElementById('cc-toggle');
      const rules = this.settings?.rules || {};
      if (!toggle || this.isOpen) return;

      toggle.style.display = 'flex';
      if (entryAnimation && entryAnimation !== 'none') {
        if (!rules.animateOncePerSession || !this.getSessionFlag('entry_played')) {
          toggle.classList.add('cc-launcher-entry');
          toggle.setAttribute('data-entry', entryAnimation);
          this.setSessionFlag('entry_played', true);
          setTimeout(() => toggle.classList.remove('cc-launcher-entry'), 400);
        }
      }
      this.applyAttentionSettings(this.settings || {});
    },

    startPromptRotation: function(prompts, rotateSeconds, targetEl, usesBubble) {
      if (!targetEl || !prompts?.length) return;
      clearInterval(this.promptInterval);
      this.promptTarget = targetEl;
      this.promptUsesBubble = !!usesBubble;
      let index = 0;
      targetEl.textContent = prompts[index];
      targetEl.style.display = 'block';
      if (this.promptUsesBubble) {
        targetEl.classList.add('is-visible');
      }

      if (prompts.length > 1) {
        this.promptInterval = setInterval(() => {
          index = (index + 1) % prompts.length;
          targetEl.textContent = prompts[index];
        }, Math.max(3, rotateSeconds || 6) * 1000);
      }
    },

    stopPromptRotation: function() {
      clearInterval(this.promptInterval);
      this.promptInterval = null;
      if (this.promptTarget) {
        if (this.promptUsesBubble) {
          this.promptTarget.classList.remove('is-visible');
          this.promptTarget.style.display = 'none';
        } else if (this.labelDefaultText) {
          this.promptTarget.textContent = this.labelDefaultText;
        }
      }
      this.promptTarget = null;
      this.promptUsesBubble = true;
    },

    getContextualText: function(rules = []) {
      const path = window.location.pathname || '';
      const match = rules.find(rule => rule.match && path.includes(rule.match));
      return match ? match.text : '';
    },

    getGreetingText: function(copySettings = {}) {
      if (!copySettings.greetingEnabled) return '';

      const mode = copySettings.greetingMode || 'time';
      const hour = new Date().getHours();
      let greeting = '';

      if (mode === 'time' || mode === 'both') {
        if (hour < 12) greeting = copySettings.greetingMorning || '';
        else if (hour < 18) greeting = copySettings.greetingAfternoon || '';
        else greeting = copySettings.greetingEvening || '';
      }

      if (mode === 'page' || mode === 'both') {
        const pageGreeting = this.getContextualText(copySettings.greetingPageRules);
        greeting = pageGreeting || greeting;
      }

      return greeting;
    },

    markInteracted: function() {
      if (!this.getSessionFlag('interacted')) {
        this.setSessionFlag('interacted', true);
      }
      const toggle = document.getElementById('cc-toggle');
      const unreadDot = toggle ? toggle.querySelector('.cc-unread-dot') : null;
      if (unreadDot) unreadDot.style.display = 'none';
      if (this.settings?.rules?.stopAfterInteraction) {
        if (toggle) {
          toggle.classList.remove('cc-attention');
          toggle.removeAttribute('data-attention');
        }
        this.stopPromptRotation();
      }
    },

    showTypingIndicator: function(durationMs) {
      const messagesContainer = document.getElementById('cc-messages');
      if (!messagesContainer) return;
      if (this.messages.length > 0) return;

      const indicator = document.createElement('div');
      indicator.className = 'cc-typing-indicator';
      indicator.innerHTML = '<span></span><span></span><span></span>';
      messagesContainer.appendChild(indicator);
      if (this.getScrollBehavior() === 'bottom') {
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
      }

      clearTimeout(this.typingTimeout);
      this.typingTimeout = setTimeout(() => {
        indicator.remove();
      }, durationMs || 1200);
    },

    playChime: function() {
      if (!this.soundSettings?.chimeOnOpen) return;
      this.playTone(520, 0.12);
    },

    playTick: function() {
      if (!this.soundSettings?.messageTicks) return;
      this.playTone(880, 0.05);
    },

    playTone: function(frequency, duration) {
      const volume = this.soundSettings?.volume ?? 0.2;
      try {
        const context = new (window.AudioContext || window.webkitAudioContext)();
        const oscillator = context.createOscillator();
        const gainNode = context.createGain();
        oscillator.type = 'sine';
        oscillator.frequency.value = frequency;
        gainNode.gain.value = volume;
        oscillator.connect(gainNode);
        gainNode.connect(context.destination);
        oscillator.start();
        setTimeout(() => {
          oscillator.stop();
          context.close();
        }, duration * 1000);
      } catch (err) {
        // Ignore audio errors (autoplay restrictions, unsupported devices)
      }
    },

    vibrate: function() {
      if (this.soundSettings?.hapticFeedback && navigator.vibrate) {
        navigator.vibrate(10);
      }
    },

    createRipple: function(event, element) {
      if (this.settings?.microInteractions?.buttonAnimation !== 'ripple') return;
      const rect = element.getBoundingClientRect();
      const size = Math.max(rect.width, rect.height);
      const ripple = document.createElement('span');
      ripple.className = 'cc-ripple';
      ripple.style.width = ripple.style.height = `${size}px`;
      ripple.style.left = `${event.clientX - rect.left - size / 2}px`;
      ripple.style.top = `${event.clientY - rect.top - size / 2}px`;
      element.appendChild(ripple);
      setTimeout(() => ripple.remove(), 500);
    },

    createWidget: function() {
      // Create widget container
      const widget = document.createElement('div');
      widget.id = 'chatter-cheetah-widget';
      widget.innerHTML = `
        <div class="cc-widget-container" style="display: none;">
          <div class="cc-widget-header">
            <div class="cc-widget-header-info">
              <div class="cc-widget-avatar" style="display: none;"></div>
              <div class="cc-widget-header-text">
                <span class="cc-widget-title">Chat with us</span>
                <span class="cc-widget-subtitle" style="display: none;"></span>
                <span class="cc-widget-response-time" style="display: none;"></span>
              </div>
            </div>
            <button class="cc-widget-new-chat" aria-label="New chat" title="Start new conversation">↻</button>
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
            <div class="cc-contact-form-header">
              <p>Before we connect you with our team, please provide your contact information (phone or email):</p>
              <button class="cc-contact-close" id="cc-contact-close" type="button" aria-label="Close contact form">Not now</button>
            </div>
            <input type="text" id="cc-name-input" placeholder="Name (optional)" />
            <input type="email" id="cc-email-input" placeholder="Email *" />
            <input type="tel" id="cc-phone-input" placeholder="Phone *" />
            <p style="margin: 5px 0; font-size: 11px; color: #6b7280;">* At least one contact method required</p>
            <button id="cc-submit-contact">Submit</button>
          </div>
          <div class="cc-widget-loading" id="cc-loading" style="display: none;">
            <span>Thinking...</span>
          </div>
        </div>
        <button class="cc-widget-toggle" id="cc-toggle" aria-label="Open chat">
          <span class="cc-icon-wrapper">💬</span>
          <span class="cc-icon-label" style="display: none;"></span>
          <span class="cc-unread-dot" style="display: none;"></span>
          <span class="cc-launcher-prompt" style="display: none;" aria-live="polite"></span>
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
          border: 1px solid rgba(255,255,255,0.25);
          font-size: 24px;
          font-weight: 600;
          cursor: pointer;
          box-shadow: 0 12px 24px rgba(15, 23, 42, 0.2);
          transition: transform 0.2s, box-shadow 0.2s, background 0.2s, border-color 0.2s;
          display: flex;
          align-items: center;
          justify-content: center;
          position: relative;
          overflow: visible;
        }
        .cc-widget-toggle:hover {
          transform: none;
        }
        .cc-widget-toggle[data-hover="lift"]:hover {
          transform: translateY(-4px);
          box-shadow: 0 10px 20px rgba(0,0,0,0.25);
        }
        .cc-widget-toggle[data-hover="scale"]:hover {
          transform: scale(1.1);
        }
        .cc-widget-toggle[data-hover="color"]:hover {
          filter: brightness(1.08);
        }
        .cc-icon-wrapper {
          display: flex;
          align-items: center;
          justify-content: center;
          width: 100%;
          height: 100%;
          font-size: 24px;
          line-height: 1;
        }
        .cc-icon-image {
          max-width: 70%;
          max-height: 70%;
          object-fit: contain;
        }
        .cc-icon-label {
          position: absolute;
          white-space: nowrap;
          padding: 6px 12px;
          border-radius: 999px;
          font-size: 12px;
          font-weight: 600;
          line-height: 1.1;
          border: 1px solid rgba(15, 23, 42, 0.08);
          box-shadow: 0 12px 24px rgba(15, 23, 42, 0.18);
          pointer-events: none;
        }
        .cc-unread-dot {
          position: absolute;
          width: 10px;
          height: 10px;
          border-radius: 50%;
          border: 2px solid #fff;
          top: 6px;
          right: 6px;
        }
        .cc-widget-toggle[data-dot-position="top-left"] .cc-unread-dot {
          left: 6px;
          right: auto;
        }
        .cc-widget-toggle[data-dot-position="bottom-right"] .cc-unread-dot {
          top: auto;
          bottom: 6px;
        }
        .cc-widget-toggle[data-dot-position="bottom-left"] .cc-unread-dot {
          top: auto;
          bottom: 6px;
          left: 6px;
          right: auto;
        }
        .cc-launcher-prompt {
          position: absolute;
          max-width: 220px;
          padding: 6px 10px;
          border-radius: 14px;
          background: #ffffff;
          color: #1f2937;
          font-size: 12px;
          font-weight: 600;
          box-shadow: 0 6px 18px rgba(0,0,0,0.15);
          white-space: nowrap;
          opacity: 0;
          transform: translateY(6px);
          transition: opacity 0.2s, transform 0.2s;
          pointer-events: none;
        }
        .cc-launcher-prompt.is-visible {
          opacity: 1;
          transform: translateY(0);
        }
        .cc-widget-toggle[data-position^="bottom"] .cc-launcher-prompt,
        .cc-widget-toggle[data-position^="top"] .cc-launcher-prompt {
          bottom: calc(100% + 10px);
        }
        .cc-widget-toggle[data-position$="left"] .cc-launcher-prompt {
          left: 0;
        }
        .cc-widget-toggle[data-position$="right"] .cc-launcher-prompt {
          right: 0;
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
        .cc-widget-toggle[data-label-position="left"] .cc-icon-label {
          right: calc(100% + 10px);
          top: 50%;
          transform: translateY(-50%);
        }
        .cc-widget-toggle[data-label-position="right"] .cc-icon-label {
          left: calc(100% + 10px);
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
          border: 1px solid var(--cc-border-color);
          display: flex;
          flex-direction: column;
          overflow: hidden;
        }
        .cc-widget-container.cc-open-animate[data-open-animation="slide-up"] {
          animation: cc-slide-up 0.25s ease;
        }
        .cc-widget-container.cc-open-animate[data-open-animation="slide-left"] {
          animation: cc-slide-left 0.25s ease;
        }
        .cc-widget-container.cc-open-animate[data-open-animation="slide-right"] {
          animation: cc-slide-right 0.25s ease;
        }
        .cc-widget-container.cc-open-animate[data-open-animation="fade"] {
          animation: cc-fade-in 0.2s ease;
        }
        .cc-widget-header {
          background: var(--cc-primary);
          color: var(--cc-button-text);
          padding: 12px 16px;
          display: flex;
          justify-content: space-between;
          align-items: center;
          gap: 8px;
          border-bottom: 1px solid rgba(255,255,255,0.18);
        }
        .cc-widget-header-info {
          display: flex;
          align-items: center;
          gap: 10px;
        }
        .cc-widget-avatar {
          width: 28px;
          height: 28px;
          border-radius: 50%;
          background: rgba(255,255,255,0.2);
          overflow: hidden;
          flex-shrink: 0;
          display: flex;
          align-items: center;
          justify-content: center;
          font-weight: 600;
          font-size: 14px;
        }
        .cc-widget-avatar img {
          width: 100%;
          height: 100%;
          object-fit: cover;
        }
        .cc-widget-header-text {
          display: flex;
          flex-direction: column;
          gap: 2px;
        }
        .cc-widget-title {
          font-weight: 600;
        }
        .cc-widget-subtitle,
        .cc-widget-response-time {
          font-size: 11px;
          opacity: 0.8;
        }
        .cc-widget-minimize, .cc-widget-close, .cc-widget-new-chat {
          background: none;
          border: none;
          color: var(--cc-button-text);
          font-size: 20px;
          cursor: pointer;
          padding: 0 5px;
        }
        .cc-widget-new-chat {
          font-size: 16px;
          opacity: 0.8;
          margin-left: auto;
          margin-right: 5px;
        }
        .cc-widget-new-chat:hover {
          opacity: 1;
        }
        .cc-widget-messages {
          flex: 1;
          overflow-y: auto;
          padding: 15px;
          background: #f8fafc;
        }
        .cc-message {
          margin-bottom: 10px;
          padding: 12px 14px;
          border-radius: 16px;
          max-width: 80%;
          word-wrap: break-word;
          white-space: pre-wrap;
          overflow-wrap: anywhere;
          font-size: var(--cc-font-size);
          line-height: var(--cc-line-height);
          box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
        }
        /* URL Links - styled for proper wrapping without breaking */
        .cc-message-link {
          color: var(--cc-link-color);
          text-decoration: underline;
          word-break: break-all;
          overflow-wrap: anywhere;
        }
        .cc-message.user .cc-message-link {
          color: rgba(255, 255, 255, 0.9);
        }
        .cc-message-link:hover {
          text-decoration: none;
          opacity: 0.85;
        }
        .cc-message.user {
          background: var(--cc-secondary);
          color: var(--cc-button-text);
          margin-left: auto;
          text-align: right;
          border-top-right-radius: 6px;
          box-shadow: 0 10px 18px rgba(15, 23, 42, 0.16);
        }
        .cc-message.assistant {
          background: rgba(15, 23, 42, 0.08);
          color: var(--cc-text);
          border-top-left-radius: 6px;
        }
        .cc-widget-input-container {
          padding: 12px 14px;
          border-top: 1px solid rgba(148, 163, 184, 0.25);
          display: flex;
          gap: 8px;
        }
        #cc-message-input {
          flex: 1;
          padding: 10px 14px;
          border: 1px solid var(--cc-border-color);
          border-radius: 999px;
          font-size: var(--cc-font-size);
          font-family: var(--cc-font-family);
          background: #ffffff;
        }
        #cc-send-button {
          padding: 8px 16px;
          background: var(--cc-primary);
          color: var(--cc-button-text);
          border: none;
          border-radius: 999px;
          cursor: pointer;
          font-weight: 600;
          font-family: var(--cc-font-family);
          position: relative;
          overflow: hidden;
          box-shadow: 0 8px 18px rgba(15, 23, 42, 0.18);
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
        .cc-contact-form-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 12px;
          margin-bottom: 12px;
        }
        .cc-contact-form-header p {
          margin: 0;
          font-weight: 600;
        }
        .cc-contact-close {
          background: transparent;
          border: none;
          color: #6b7280;
          font-size: 12px;
          font-weight: 600;
          cursor: pointer;
          padding: 4px 8px;
          border-radius: 8px;
          transition: background 0.2s ease, color 0.2s ease;
          white-space: nowrap;
        }
        .cc-contact-close:hover {
          background: rgba(0,0,0,0.06);
          color: #374151;
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
        .cc-typing-indicator {
          display: inline-flex;
          gap: 4px;
          padding: 8px 12px;
          background: var(--cc-background);
          border: 1px solid var(--cc-border-color);
          border-radius: 10px;
          margin-bottom: 10px;
        }
        .cc-typing-indicator span {
          width: 6px;
          height: 6px;
          background: var(--cc-text);
          border-radius: 50%;
          opacity: 0.4;
          animation: cc-typing 1.2s infinite;
        }
        .cc-typing-indicator span:nth-child(2) {
          animation-delay: 0.2s;
        }
        .cc-typing-indicator span:nth-child(3) {
          animation-delay: 0.4s;
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
        #cc-message-input.cc-blink-cursor {
          animation: cc-cursor-blink 1s steps(2, start) infinite;
          box-shadow: inset 1px 0 0 var(--cc-text);
        }
        .cc-pressable:active {
          transform: scale(0.98);
        }
        .cc-ripple {
          position: absolute;
          border-radius: 50%;
          transform: scale(0);
          background: rgba(255,255,255,0.5);
          animation: cc-ripple 0.45s ease-out;
          pointer-events: none;
        }
        .cc-launcher-entry[data-entry="slide-up"] {
          animation: cc-slide-up 0.3s ease;
        }
        .cc-launcher-entry[data-entry="slide-left"] {
          animation: cc-slide-left 0.3s ease;
        }
        .cc-launcher-entry[data-entry="slide-right"] {
          animation: cc-slide-right 0.3s ease;
        }
        .cc-launcher-entry[data-entry="fade"] {
          animation: cc-fade-in 0.2s ease;
        }
        .cc-attention[data-attention="bounce"] {
          animation: cc-bounce var(--cc-attention-duration, 1.2s) ease;
          animation-iteration-count: var(--cc-attention-iterations, 2);
        }
        .cc-attention[data-attention="pulse"] {
          animation: cc-pulse var(--cc-attention-duration, 1.3s) ease;
          animation-iteration-count: var(--cc-attention-iterations, 2);
        }
        .cc-attention[data-attention="glow"] {
          animation: cc-glow var(--cc-attention-duration, 1.8s) ease;
          animation-iteration-count: var(--cc-attention-iterations, 2);
        }
        .cc-attention[data-attention="breathing"] {
          animation: cc-breathing var(--cc-attention-duration, 2.4s) ease-in-out;
          animation-iteration-count: var(--cc-attention-iterations, 2);
        }
        .cc-attention[data-attention="corner-nudge"] {
          animation: cc-nudge var(--cc-attention-duration, 1.2s) ease;
          animation-iteration-count: var(--cc-attention-iterations, 2);
        }
        .cc-reduced-motion,
        .cc-reduced-motion * {
          animation: none !important;
          transition: none !important;
        }
        @keyframes cc-typing {
          0%, 60%, 100% { transform: translateY(0); opacity: 0.4; }
          30% { transform: translateY(-4px); opacity: 1; }
        }
        @keyframes cc-cursor-blink {
          0%, 49% { box-shadow: inset 1px 0 0 var(--cc-text); }
          50%, 100% { box-shadow: inset 1px 0 0 transparent; }
        }
        @keyframes cc-ripple {
          to { transform: scale(2.4); opacity: 0; }
        }
        @keyframes cc-slide-up {
          from { transform: translateY(12px); opacity: 0; }
          to { transform: translateY(0); opacity: 1; }
        }
        @keyframes cc-slide-left {
          from { transform: translateX(12px); opacity: 0; }
          to { transform: translateX(0); opacity: 1; }
        }
        @keyframes cc-slide-right {
          from { transform: translateX(-12px); opacity: 0; }
          to { transform: translateX(0); opacity: 1; }
        }
        @keyframes cc-fade-in {
          from { opacity: 0; }
          to { opacity: 1; }
        }
        @keyframes cc-bounce {
          0%, 100% { transform: translateY(0); }
          50% { transform: translateY(-8px); }
        }
        @keyframes cc-pulse {
          0%, 100% { transform: scale(1); }
          50% { transform: scale(1.06); }
        }
        @keyframes cc-glow {
          0%, 100% { box-shadow: 0 2px 10px rgba(0,0,0,0.2); }
          50% { box-shadow: 0 0 18px rgba(79, 70, 229, 0.4); }
        }
        @keyframes cc-breathing {
          0%, 100% { transform: scale(1); }
          50% { transform: scale(1.03); }
        }
        @keyframes cc-nudge {
          0%, 100% { transform: translate(0, 0); }
          50% { transform: translate(var(--cc-nudge-x, -6px), var(--cc-nudge-y, -6px)); }
        }
      `;
      document.head.appendChild(style);
    },

    attachEventListeners: function() {
      const toggle = document.getElementById('cc-toggle');
      const close = document.querySelector('.cc-widget-close');
      const minimize = document.querySelector('.cc-widget-minimize');
      const newChat = document.querySelector('.cc-widget-new-chat');
      const sendButton = document.getElementById('cc-send-button');
      const messageInput = document.getElementById('cc-message-input');
      const submitContact = document.getElementById('cc-submit-contact');
      const closeContact = document.getElementById('cc-contact-close');

      toggle.addEventListener('click', (event) => {
        this.markInteracted();
        this.vibrate();
        this.createRipple(event, toggle);
        this.toggleWidget();
      });
      close.addEventListener('click', () => this.closeWidget());
      minimize.addEventListener('click', () => this.minimizeWidget());
      newChat.addEventListener('click', () => this.startNewChat());
      sendButton.addEventListener('click', (event) => {
        this.markInteracted();
        this.vibrate();
        this.createRipple(event, sendButton);
        this.sendMessage();
      });
      submitContact.addEventListener('click', () => this.submitContactInfo());
      if (closeContact) {
        closeContact.addEventListener('click', () => this.hideContactForm());
      }

      messageInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
          this.sendMessage();
        }
      });

      messageInput.addEventListener('focus', () => this.markInteracted());
    },

    toggleWidget: function(options = {}) {
      const container = document.querySelector('.cc-widget-container');
      const toggle = document.getElementById('cc-toggle');

      if (this.isOpen) {
        this.closeWidget();
      } else {
        container.style.display = 'flex';
        toggle.style.display = 'none';
        this.isOpen = true;
        this.isMinimized = false;
        this.saveSession(); // Persist open state

        // Track widget open analytics
        var timeOnPage = this.pageLoadTime ? Date.now() - this.pageLoadTime : 0;
        this.trackEvent('widget_open', {
          trigger: options.autoOpen ? 'auto' : 'click',
          time_on_page_ms: timeOnPage
        });
        if (options.autoOpen) {
          this.trackEvent('auto_open', {});
          this.wasAutoOpened = true;
        } else {
          this.trackEvent('manual_open', {});
          this.wasAutoOpened = false;
        }

        // Track chat opened event for GA4
        this.pushDataLayerEvent('chat_button_opened');
        document.getElementById('cc-message-input').focus();
        if (this.settings?.motion?.openAnimation && this.settings.motion.openAnimation !== 'none') {
          container.classList.add('cc-open-animate');
          container.setAttribute('data-open-animation', this.settings.motion.openAnimation);
          setTimeout(() => container.classList.remove('cc-open-animate'), 400);
        }
        if (!this.getSessionFlag('chime_played')) {
          this.playChime();
          this.setSessionFlag('chime_played', true);
        }
        if (this.settings?.microInteractions?.typingIndicator) {
          this.showTypingIndicator(this.settings.microInteractions.typingIndicatorDurationMs);
        }
        if (options.autoOpen && this.settings?.behavior?.autoOpenMessageEnabled) {
          const message = (this.settings.behavior.autoOpenMessage || '').trim();
          if (message && !this.getSessionFlag('auto_open_message')) {
            this.addMessage(message, 'assistant');
            this.setSessionFlag('auto_open_message', true);
          }
        }
        // Scroll to preferred position after restoring messages
        const messagesContainer = document.getElementById('cc-messages');
        if (messagesContainer) {
          messagesContainer.scrollTop =
            this.getScrollBehavior() === 'top' ? 0 : messagesContainer.scrollHeight;
        }
      }
    },

    closeWidget: function() {
      const container = document.querySelector('.cc-widget-container');
      const toggle = document.getElementById('cc-toggle');

      // Track auto-open dismiss if widget was auto-opened and closed without interaction
      if (this.wasAutoOpened && this.userMessageCount === 0) {
        this.trackEvent('auto_open_dismiss', {});
      }

      container.style.display = 'none';
      toggle.style.display = 'block';
      this.isOpen = false;
      this.wasAutoOpened = false;
      this.saveSession(); // Persist closed state
    },

    minimizeWidget: function() {
      const container = document.querySelector('.cc-widget-container');
      container.classList.toggle('minimized');
      this.isMinimized = !this.isMinimized;
    },

    // Sanitize URL by removing any embedded whitespace (fixes broken URLs from LLM output)
    sanitizeUrl: function(url) {
      return url.replace(/\s+/g, '');
    },

    // Join URLs that the LLM split across multiple lines
    // e.g., "https://britishswimschool\n.com/path" -> "https://britishswimschool.com/path"
    joinSplitUrls: function(text) {
      let result = text;
      let iterations = 0;
      const maxIterations = 15; // Safety limit - may need multiple passes

      while (iterations < maxIterations) {
        const before = result;

        // Match: URL + whitespace + any non-whitespace chunk
        result = result.replace(
          /(https?:\/\/[^\s<>"']+)(\s+)(\S+)/gi,
          (match, urlPart, whitespace, continuation) => {
            // Always join if continuation contains URL-indicative characters
            // (dots, slashes, query params, percent-encoding, equals, ampersands)
            if (/[.\/\?&=%]/.test(continuation)) {
              return urlPart + continuation;
            }

            // Join path segments that follow an incomplete URL path
            // e.g., "https://site.com/cy" + "press-spring" should join
            if (/^[a-z0-9][a-z0-9\-_]*$/i.test(continuation)) {
              // Check if URL ends with a partial path (ends with /word or just domain)
              if (/\/[a-z0-9\-_]*$/i.test(urlPart)) {
                return urlPart + continuation;
              }
            }

            return match; // Don't join - probably regular text
          }
        );

        if (result === before) break;
        iterations++;
      }
      return result;
    },

    // Convert text to safe HTML (no markdown rendering). Guardrail: only plain text or simple links.
    linkifyText: function(text) {
      // URL pattern - captures full URLs including query strings and encoded characters
      // Note: We capture generously and then clean up trailing punctuation
      const urlRegex = /(https?:\/\/[^\s<>"']+)/gi;

      const escapeHtml = (str) => {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
      };

      const preprocessMarkdown = (str) => {
        const lines = str.split('\n').map((line) => {
          // Strip markdown headings
          let cleaned = line.replace(/^#{1,6}\s*/, '');
          // Strip bold/underline markers
          cleaned = cleaned.replace(/\*\*(.+?)\*\*/g, '$1').replace(/__(.+?)__/g, '$1');
          // Convert table-style rows to bullets
          if (cleaned.includes('|')) {
            const cells = cleaned.split('|').map((c) => c.trim()).filter(Boolean);
            if (cells.length > 1) {
              cleaned = `• ${cells.join(' — ')}`;
            }
          }
          return cleaned;
        });
        return lines.join('\n');
      };

      const self = this;
      // First, join any URLs that were split across lines
      const textWithJoinedUrls = this.joinSplitUrls(text);

      // Nuclear option: Find BSS URLs and strip ALL internal whitespace
      // Pattern: https://britishswimschool followed by URL chars with possible whitespace
      let cleanedText = textWithJoinedUrls;
      const bssUrlPattern = /(https?:\/\/britishswimschool)([.\w\-\/%?&=\s]+?)(?=\s+[A-Z]|\s+Would|\s+Let|\s+I\s|\s+You|\s+If|\s+Feel|\s*$)/gi;
      cleanedText = cleanedText.replace(bssUrlPattern, (match, start, rest) => {
        // Strip all whitespace from the URL portion
        return start + rest.replace(/\s+/g, '');
      });

      const safeText = preprocessMarkdown(cleanedText);
      let processed = escapeHtml(safeText);

      // Replace URLs with clickable links
      processed = processed.replace(urlRegex, (match) => {
        let url = match;
        let trailing = '';

        // Remove trailing punctuation that's not part of the URL
        while (url.length > 0 && /[.,;:!?)}\]>]$/.test(url)) {
          // Keep trailing ) only if there's a matching ( in the URL
          if (url.endsWith(')') && url.includes('(')) {
            break;
          }
          trailing = url.slice(-1) + trailing;
          url = url.slice(0, -1);
        }

        // Sanitize the URL (remove any embedded whitespace)
        const cleanUrl = self.sanitizeUrl(url);

        return `<a href="${cleanUrl}" target="_blank" rel="noopener noreferrer" class="cc-message-link">${cleanUrl}</a>${trailing}`;
      });

      // Preserve line breaks
      processed = processed.replace(/\n/g, '<br>');

      return processed;
    },

    // Render message to DOM (without saving - used for restoration)
    renderMessage: function(text, role, scroll = true) {
      const messagesContainer = document.getElementById('cc-messages');
      const message = document.createElement('div');
      message.className = `cc-message ${role}`;
      message.innerHTML = this.linkifyText(text);
      messagesContainer.appendChild(message);
      if (scroll) {
        this.scrollMessageIntoView(messagesContainer, message, role);
      }
    },

    // Detect if message contains escalation keywords
    detectEscalationIntent: function(message) {
      const escalationKeywords = [
        'speak to human', 'talk to person', 'real person', 'agent',
        'representative', 'manager', 'supervisor', 'escalate',
        'speak with human', 'talk with person', 'human support',
        'speak to a human', 'talk to a person', 'real human'
      ];
      const lowerMessage = message.toLowerCase();
      return escalationKeywords.some(keyword => lowerMessage.includes(keyword));
    },

    scrollMessageIntoView: function(container, message, role) {
      if (!container || !message) return;
      const padding = 8;
      if (this.getScrollBehavior() === 'top') {
        container.scrollTop = Math.max(message.offsetTop - padding, 0);
        return;
      }
      if (role === 'assistant') {
        // Scroll to the start of the assistant response
        container.scrollTop = Math.max(message.offsetTop - padding, 0);
      } else {
        // Keep user messages pinned to bottom
        container.scrollTop = container.scrollHeight;
      }
    },

    getScrollBehavior: function() {
      return this.config?.scrollBehavior === 'top' ? 'top' : 'bottom';
    },

    // Add message to UI and save to storage
    addMessage: function(text, role) {
      this.messages.push({ text, role, timestamp: Date.now() });
      this.renderMessage(text, role, true);
      this.saveSession();
      this.playTick();
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
      const nameInput = document.getElementById('cc-name-input');
      const emailInput = document.getElementById('cc-email-input');
      const phoneInput = document.getElementById('cc-phone-input');

      const name = nameInput.value.trim();
      const email = emailInput.value.trim();
      const phone = phoneInput.value.trim();

      // Require phone OR email (at least one)
      const hasPhone = phone !== '';
      const hasEmail = email !== '';

      if (!hasPhone && !hasEmail) {
        alert('Please provide at least a phone number or email address so we can reach you.');
        return;
      }

      // Basic email format validation if email provided
      if (hasEmail && !email.includes('@')) {
        alert('Please enter a valid email address.');
        return;
      }

      // Store contact info in sessionStorage for this session
      sessionStorage.setItem(this.getStorageKey('user_name'), name);
      sessionStorage.setItem(this.getStorageKey('user_email'), email);
      sessionStorage.setItem(this.getStorageKey('user_phone'), phone);

      // Track lead collection when name + (phone or email) provided
      if (name && (hasPhone || hasEmail)) {
        this.pushDataLayerEvent('chat_lead_collected', {
          session_id: this.sessionId,
          has_email: hasEmail,
          has_phone: hasPhone
        });
      }

      this.hideContactForm();

      // Send the pending escalation message if one exists
      if (this.pendingEscalationMessage) {
        const pendingMsg = this.pendingEscalationMessage;
        this.pendingEscalationMessage = null;

        // Track user message events for GA4
        this.userMessageCount++;
        if (this.userMessageCount === 1) {
          this.pushDataLayerEvent('chat_first_message_sent', {
            session_id: this.sessionId
          });
        } else if (this.userMessageCount === 2) {
          this.pushDataLayerEvent('chat_second_message_sent', {
            session_id: this.sessionId
          });
        }

        // Add user message to UI first
        this.addMessage(pendingMsg, 'user');

        // Send to backend with contact info
        this.sendMessageToBackend(pendingMsg, name, email, phone);
      }
    },

    sendMessage: function() {
      const messageInput = document.getElementById('cc-message-input');
      const message = messageInput ? messageInput.value.trim() : '';

      if (!message) {
        return;
      }

      // Check if this is an escalation request
      const isEscalation = this.detectEscalationIntent(message);

      if (isEscalation) {
        // Check if we already have contact info in sessionStorage
        const storedEmail = sessionStorage.getItem(this.getStorageKey('user_email')) || '';
        const storedPhone = sessionStorage.getItem(this.getStorageKey('user_phone')) || '';
        const hasContactInfo = storedEmail.trim() !== '' || storedPhone.trim() !== '';

        if (!hasContactInfo) {
          // Store the message and show contact form
          this.pendingEscalationMessage = message;
          messageInput.value = '';
          this.showContactForm();
          return;
        }
      }

      // Proceed with sending the message
      const storedName = sessionStorage.getItem(this.getStorageKey('user_name')) || '';
      const storedEmail = sessionStorage.getItem(this.getStorageKey('user_email')) || '';
      const storedPhone = sessionStorage.getItem(this.getStorageKey('user_phone')) || '';

      // Track user message events for GA4
      this.userMessageCount++;
      if (this.userMessageCount === 1) {
        this.pushDataLayerEvent('chat_first_message_sent', {
          session_id: this.sessionId
        });
        // Track first message for widget analytics
        this.trackEvent('first_message', {
          session_id: this.sessionId
        });
      } else if (this.userMessageCount === 2) {
        this.pushDataLayerEvent('chat_second_message_sent', {
          session_id: this.sessionId
        });
      }

      this.addMessage(message, 'user');
      messageInput.value = '';
      this.sendMessageToBackend(message, storedName, storedEmail, storedPhone);
    },

    sendMessageToBackend: async function(message, name, email, phone) {
      const messageInput = document.getElementById('cc-message-input');
      const sendButton = document.getElementById('cc-send-button');
      const loading = document.getElementById('cc-loading');

      this.markInteracted();

      // Only disable send button to prevent double-sends, keep input enabled for typing
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

        // Update session ID and persist it
        this.sessionId = data.session_id;
        this.saveSession();

        // Add assistant response
        this.addMessage(data.response, 'assistant');

        // Handle conversation complete
        if (data.conversation_complete) {
          if (messageInput) messageInput.disabled = true;
          if (sendButton) sendButton.disabled = true;
        }

      } catch (error) {
        console.error('Chat error:', error);
        this.addMessage('Sorry, I encountered an error. Please try again.', 'assistant');
      } finally {
        // Re-enable send button
        if (sendButton) sendButton.disabled = false;
        loading.style.display = 'none';
        if (messageInput) messageInput.focus();
      }
    },
  };

  // Expose globally
  window.ChatterCheetah = ChatterCheetah;
})();
