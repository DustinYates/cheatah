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

    init: function(config) {
      this.config = config;
      this.createWidget();
      this.attachEventListeners();
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
        <div class="cc-toggle-wrapper" id="cc-toggle-wrapper">
          <button class="cc-widget-toggle" id="cc-toggle" aria-label="Open chat">
            <svg class="cc-robot-icon" viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg">
              <!-- Gear teeth -->
              <path d="M50 5 L55 15 L60 5 L65 12 L72 3 L75 13 L83 6 L84 16 L93 12 L91 22 L100 20 L96 30 L100 35 L95 42 L100 50 L95 58 L100 65 L96 70 L100 80 L91 78 L93 88 L84 84 L83 94 L75 87 L72 97 L65 88 L60 95 L55 85 L50 95 L45 85 L40 95 L35 88 L28 97 L25 87 L17 94 L16 84 L7 88 L9 78 L0 80 L4 70 L0 65 L5 58 L0 50 L5 42 L0 35 L4 30 L0 20 L9 22 L7 12 L16 16 L17 6 L25 13 L28 3 L35 12 L40 5 L45 15 L50 5Z" 
                    fill="none" stroke="currentColor" stroke-width="3" stroke-linejoin="round"/>
              <!-- Robot head -->
              <rect x="30" y="35" width="40" height="35" rx="8" fill="none" stroke="currentColor" stroke-width="3"/>
              <!-- Robot eyes -->
              <rect x="38" y="45" width="6" height="10" rx="2" fill="currentColor"/>
              <rect x="56" y="45" width="6" height="10" rx="2" fill="currentColor"/>
              <!-- Robot antenna -->
              <line x1="50" y1="35" x2="50" y2="25" stroke="currentColor" stroke-width="3" stroke-linecap="round"/>
              <circle cx="50" cy="23" r="4" fill="currentColor"/>
            </svg>
          </button>
          <span class="cc-toggle-label">Chat</span>
        </div>
      `;
      document.body.appendChild(widget);
      this.injectStyles();
    },

    injectStyles: function() {
      const style = document.createElement('style');
      style.textContent = `
        #chatter-cheetah-widget {
          position: fixed;
          bottom: 20px;
          right: 20px;
          z-index: 10000;
          font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
        }
        
        /* Toggle button wrapper */
        .cc-toggle-wrapper {
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 6px;
        }
        
        .cc-widget-toggle {
          width: 70px;
          height: 70px;
          border-radius: 50%;
          background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
          color: #00d4ff;
          border: 3px solid #00d4ff;
          font-size: 24px;
          cursor: pointer;
          box-shadow: 
            0 0 20px rgba(0, 212, 255, 0.5),
            0 0 40px rgba(0, 212, 255, 0.3),
            0 0 60px rgba(0, 212, 255, 0.1),
            inset 0 0 20px rgba(0, 212, 255, 0.1);
          transition: all 0.3s ease;
          animation: cc-glow-pulse 2s ease-in-out infinite;
          display: flex;
          align-items: center;
          justify-content: center;
          padding: 12px;
        }
        
        .cc-robot-icon {
          width: 40px;
          height: 40px;
        }
        
        @keyframes cc-glow-pulse {
          0%, 100% {
            box-shadow: 
              0 0 20px rgba(0, 212, 255, 0.5),
              0 0 40px rgba(0, 212, 255, 0.3),
              0 0 60px rgba(0, 212, 255, 0.1),
              inset 0 0 20px rgba(0, 212, 255, 0.1);
            border-color: #00d4ff;
          }
          50% {
            box-shadow: 
              0 0 25px rgba(0, 212, 255, 0.7),
              0 0 50px rgba(0, 212, 255, 0.4),
              0 0 75px rgba(0, 212, 255, 0.2),
              inset 0 0 25px rgba(0, 212, 255, 0.15);
            border-color: #4ddbff;
          }
        }
        
        .cc-widget-toggle:hover {
          transform: scale(1.1);
          box-shadow: 
            0 0 30px rgba(0, 212, 255, 0.7),
            0 0 60px rgba(0, 212, 255, 0.5),
            0 0 90px rgba(0, 212, 255, 0.3),
            inset 0 0 30px rgba(0, 212, 255, 0.2);
        }
        
        .cc-toggle-label {
          color: #1a1a2e;
          font-size: 14px;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 1px;
          text-shadow: 0 1px 2px rgba(255, 255, 255, 0.8);
        }
        
        .cc-widget-container {
          width: 370px;
          height: 520px;
          background: linear-gradient(180deg, #ffffff 0%, #f8f9fa 100%);
          border-radius: 16px;
          box-shadow: 
            0 10px 40px rgba(0, 0, 0, 0.15),
            0 0 20px rgba(0, 212, 255, 0.1);
          display: flex;
          flex-direction: column;
          overflow: hidden;
          border: 1px solid rgba(0, 212, 255, 0.2);
        }
        
        .cc-widget-header {
          background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
          color: white;
          padding: 16px 20px;
          display: flex;
          justify-content: space-between;
          align-items: center;
          border-bottom: 2px solid #00d4ff;
        }
        
        .cc-widget-title {
          font-weight: 600;
          font-size: 16px;
          color: #00d4ff;
        }
        
        .cc-widget-minimize, .cc-widget-close {
          background: transparent;
          border: none;
          color: #00d4ff;
          font-size: 20px;
          cursor: pointer;
          padding: 4px 8px;
          border-radius: 4px;
          transition: all 0.2s;
        }
        
        .cc-widget-minimize:hover, .cc-widget-close:hover {
          background: rgba(0, 212, 255, 0.2);
        }
        
        .cc-widget-messages {
          flex: 1;
          overflow-y: auto;
          padding: 16px;
          display: flex;
          flex-direction: column;
          gap: 12px;
        }
        
        .cc-message {
          max-width: 85%;
          padding: 12px 16px;
          border-radius: 16px;
          font-size: 14px;
          line-height: 1.5;
          animation: cc-message-fade-in 0.3s ease;
        }
        
        @keyframes cc-message-fade-in {
          from {
            opacity: 0;
            transform: translateY(10px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }
        
        .cc-message.user {
          background: linear-gradient(135deg, #0f3460 0%, #16213e 100%);
          color: white;
          align-self: flex-end;
          border-bottom-right-radius: 4px;
        }
        
        .cc-message.assistant {
          background: #f0f2f5;
          color: #1a1a2e;
          align-self: flex-start;
          border-bottom-left-radius: 4px;
          border: 1px solid #e4e6ea;
        }
        
        .cc-widget-input-container {
          display: flex;
          padding: 16px;
          gap: 10px;
          background: white;
          border-top: 1px solid #e4e6ea;
        }
        
        #cc-message-input {
          flex: 1;
          padding: 12px 16px;
          border: 2px solid #e4e6ea;
          border-radius: 24px;
          outline: none;
          font-size: 14px;
          transition: border-color 0.2s;
        }
        
        #cc-message-input:focus {
          border-color: #00d4ff;
        }
        
        #cc-send-button {
          padding: 12px 24px;
          background: linear-gradient(135deg, #0f3460 0%, #16213e 100%);
          color: #00d4ff;
          border: 2px solid #00d4ff;
          border-radius: 24px;
          cursor: pointer;
          font-weight: 600;
          font-size: 14px;
          transition: all 0.2s;
        }
        
        #cc-send-button:hover {
          background: linear-gradient(135deg, #16213e 0%, #1a1a2e 100%);
          box-shadow: 0 0 15px rgba(0, 212, 255, 0.4);
        }
        
        .cc-widget-contact-form {
          padding: 16px;
          background: #f8f9fa;
          border-top: 1px solid #e4e6ea;
        }
        
        .cc-widget-contact-form p {
          margin: 0 0 12px 0;
          font-size: 14px;
          color: #1a1a2e;
        }
        
        .cc-widget-contact-form input {
          width: 100%;
          padding: 10px 14px;
          border: 2px solid #e4e6ea;
          border-radius: 8px;
          margin-bottom: 10px;
          font-size: 14px;
          box-sizing: border-box;
          transition: border-color 0.2s;
        }
        
        .cc-widget-contact-form input:focus {
          outline: none;
          border-color: #00d4ff;
        }
        
        #cc-submit-contact {
          width: 100%;
          padding: 12px;
          background: linear-gradient(135deg, #0f3460 0%, #16213e 100%);
          color: #00d4ff;
          border: 2px solid #00d4ff;
          border-radius: 8px;
          cursor: pointer;
          font-weight: 600;
          font-size: 14px;
          transition: all 0.2s;
        }
        
        #cc-submit-contact:hover {
          box-shadow: 0 0 15px rgba(0, 212, 255, 0.4);
        }
        
        .cc-widget-loading {
          padding: 12px 16px;
          text-align: center;
          color: #0f3460;
          font-style: italic;
          font-size: 14px;
        }
        
        .cc-widget-container.minimized {
          height: 60px;
        }
        
        .cc-widget-container.minimized .cc-widget-messages,
        .cc-widget-container.minimized .cc-widget-input-container,
        .cc-widget-container.minimized .cc-widget-contact-form {
          display: none;
        }
        
        /* Responsive */
        @media (max-width: 480px) {
          #chatter-cheetah-widget {
            bottom: 10px;
            right: 10px;
          }
          
          .cc-widget-container {
            width: calc(100vw - 20px);
            height: 70vh;
            max-height: 500px;
          }
          
          .cc-widget-toggle {
            width: 60px;
            height: 60px;
          }
          
          .cc-robot-icon {
            width: 32px;
            height: 32px;
          }
        }
      `;
      document.head.appendChild(style);
    },

    attachEventListeners: function() {
      const toggle = document.getElementById('cc-toggle');
      const toggleWrapper = document.getElementById('cc-toggle-wrapper');
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
      const toggleWrapper = document.getElementById('cc-toggle-wrapper');
      
      if (this.isOpen) {
        this.closeWidget();
      } else {
        container.style.display = 'flex';
        toggleWrapper.style.display = 'none';
        this.isOpen = true;
        this.isMinimized = false;
        document.getElementById('cc-message-input').focus();
      }
    },

    closeWidget: function() {
      const container = document.querySelector('.cc-widget-container');
      const toggleWrapper = document.getElementById('cc-toggle-wrapper');
      container.style.display = 'none';
      toggleWrapper.style.display = 'flex';
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
