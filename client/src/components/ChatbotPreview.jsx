import { useState, useRef, useEffect } from 'react';
import { api } from '../api/client';
import { renderLinkifiedText } from '../utils/linkify';
import './ChatbotPreview.css';

/**
 * ChatbotPreview - An embedded chat preview for testing the website chatbot
 *
 * This component provides a device-styled preview of the chatbot, allowing
 * tenants to test their web chat configuration directly from the settings page.
 */
export default function ChatbotPreview({ className = '' }) {
  const [messages, setMessages] = useState([
    { role: 'assistant', content: "Hi! I'm here to help. What can I assist you with today?" }
  ]);
  const [inputValue, setInputValue] = useState('');
  const [loading, setLoading] = useState(false);
  const [sessionId, setSessionId] = useState(null);
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);

  // Sample prompts to help users get started
  const samplePrompts = [
    "What swim classes do you offer?",
    "How much do lessons cost?",
    "What ages do you teach?",
    "Where are you located?"
  ];

  // Scroll to bottom when new messages arrive
  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, loading]);

  const handleSubmit = async (e) => {
    e?.preventDefault();
    const message = inputValue.trim();
    if (!message || loading) return;

    // Build history from existing messages
    const history = messages
      .filter((msg) => msg.role !== 'error')
      .map((msg) => ({ role: msg.role, content: msg.content }));

    // Add user message
    setMessages((prev) => [...prev, { role: 'user', content: message }]);
    setInputValue('');
    setLoading(true);

    try {
      // Test with bundle_id: null to use the active/live prompt
      const result = await api.testPrompt(null, message, history);

      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: result.response },
      ]);
    } catch (err) {
      console.error('ChatbotPreview test error:', err);
      let errorMessage = err.message || 'Test failed. Please try again.';
      // Add hint for common issues
      if (errorMessage.includes('No active prompt') || errorMessage.includes('not found')) {
        errorMessage = 'No web chat prompt configured. Please save a Web Chat prompt first.';
      }
      setMessages((prev) => [
        ...prev,
        { role: 'error', content: errorMessage },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleSamplePrompt = (prompt) => {
    setInputValue(prompt);
    inputRef.current?.focus();
  };

  const clearChat = () => {
    setMessages([
      { role: 'assistant', content: "Hi! I'm here to help. What can I assist you with today?" }
    ]);
    setSessionId(null);
  };

  return (
    <div className={`chatbot-preview ${className}`}>
      <div className="chatbot-preview__header">
        <div className="chatbot-preview__header-content">
          <h3>Test Your Chatbot</h3>
          <p>See how your website chatbot responds to visitors with the current prompt configuration.</p>
        </div>
        <button
          className="chatbot-preview__clear-btn"
          onClick={clearChat}
          title="Reset conversation"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" />
          </svg>
          Reset
        </button>
      </div>

      <div className="chatbot-preview__container">
        {/* Device Frame */}
        <div className="chatbot-preview__device">
          <div className="chatbot-preview__device-notch"></div>

          {/* Chat Widget */}
          <div className="chatbot-preview__widget">
            {/* Widget Header */}
            <div className="chatbot-preview__widget-header">
              <div className="chatbot-preview__widget-header-content">
                <span className="chatbot-preview__widget-avatar">🐆</span>
                <div className="chatbot-preview__widget-info">
                  <span className="chatbot-preview__widget-title">Chat Support</span>
                  <span className="chatbot-preview__widget-status">
                    <span className="chatbot-preview__status-dot"></span>
                    Online
                  </span>
                </div>
              </div>
              <div className="chatbot-preview__widget-actions">
                <span className="chatbot-preview__widget-action">−</span>
                <span className="chatbot-preview__widget-action">×</span>
              </div>
            </div>

            {/* Messages */}
            <div className="chatbot-preview__messages">
              {messages.map((msg, idx) => (
                <div
                  key={`${msg.role}-${idx}`}
                  className={`chatbot-preview__message chatbot-preview__message--${msg.role}`}
                >
                  {msg.role === 'assistant' && (
                    <span className="chatbot-preview__message-avatar">🐆</span>
                  )}
                  <div className="chatbot-preview__bubble">
                    {renderLinkifiedText(msg.content)}
                  </div>
                </div>
              ))}

              {/* Typing indicator */}
              {loading && (
                <div className="chatbot-preview__message chatbot-preview__message--assistant">
                  <span className="chatbot-preview__message-avatar">🐆</span>
                  <div className="chatbot-preview__bubble chatbot-preview__typing">
                    <span></span>
                    <span></span>
                    <span></span>
                  </div>
                </div>
              )}

              <div ref={messagesEndRef} />
            </div>

            {/* Input */}
            <form className="chatbot-preview__input-area" onSubmit={handleSubmit}>
              <input
                ref={inputRef}
                type="text"
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Type your message..."
                disabled={loading}
                className="chatbot-preview__input"
              />
              <button
                type="submit"
                disabled={loading || !inputValue.trim()}
                className="chatbot-preview__send-btn"
              >
                Send
              </button>
            </form>
          </div>
        </div>

        {/* Sample Prompts */}
        <div className="chatbot-preview__samples">
          <h4>Try these sample messages:</h4>
          <div className="chatbot-preview__sample-list">
            {samplePrompts.map((prompt, idx) => (
              <button
                key={idx}
                className="chatbot-preview__sample-btn"
                onClick={() => handleSamplePrompt(prompt)}
                disabled={loading}
              >
                {prompt}
              </button>
            ))}
          </div>
          <p className="chatbot-preview__hint">
            Click a sample message or type your own to see how the chatbot responds.
          </p>
        </div>
      </div>
    </div>
  );
}
