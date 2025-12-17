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
        <button class="cc-widget-toggle" id="cc-toggle" aria-label="Open chat">
          💬
        </button>
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
        .cc-widget-toggle {
          width: 60px;
          height: 60px;
          border-radius: 50%;
          background: #007bff;
          color: white;
          border: none;
          font-size: 24px;
          cursor: pointer;
          box-shadow: 0 2px 10px rgba(0,0,0,0.2);
          transition: transform 0.2s;
        }
        .cc-widget-toggle:hover {
          transform: scale(1.1);
        }
        .cc-widget-container {
          width: 350px;
          height: 500px;
          background: white;
          border-radius: 10px;
          box-shadow: 0 4px 20px rgba(0,0,0,0.15);
          display: flex;
          flex-direction: column;
          overflow: hidden;
        }
        .cc-widget-header {
          background: #007bff;
          color: white;
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
          color: white;
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
        }
        .cc-message.user {
          background: #007bff;
          color: white;
          margin-left: auto;
          text-align: right;
        }
        .cc-message.assistant {
          background: white;
          color: #333;
          border: 1px solid #ddd;
        }
        .cc-widget-input-container {
          padding: 15px;
          border-top: 1px solid #ddd;
          display: flex;
          gap: 10px;
        }
        #cc-message-input {
          flex: 1;
          padding: 10px;
          border: 1px solid #ddd;
          border-radius: 5px;
          font-size: 14px;
        }
        #cc-send-button {
          padding: 10px 20px;
          background: #007bff;
          color: white;
          border: none;
          border-radius: 5px;
          cursor: pointer;
          font-weight: 600;
        }
        #cc-send-button:hover {
          background: #0056b3;
        }
        #cc-send-button:disabled {
          background: #ccc;
          cursor: not-allowed;
        }
        .cc-widget-contact-form {
          padding: 15px;
          border-top: 1px solid #ddd;
          background: #fff3cd;
        }
        .cc-widget-contact-form input {
          width: 100%;
          padding: 8px;
          margin: 5px 0;
          border: 1px solid #ddd;
          border-radius: 5px;
          box-sizing: border-box;
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

