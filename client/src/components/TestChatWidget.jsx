import { useState, useRef, useEffect } from 'react';
import { api } from '../api/client';
import { renderLinkifiedText } from '../utils/linkify';
import './TestChatWidget.css';

/**
 * TestChatWidget - A floating chat widget for testing the active prompt
 *
 * This widget allows admins to quickly test the tenant's live prompt configuration
 * without opening a modal or navigating away from the prompts setup page.
 *
 * Props:
 * - onTestComplete: Optional callback when a test response is received
 * - className: Optional additional CSS class
 */
export default function TestChatWidget({ onTestComplete, className = '' }) {
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState([]);
  const [inputValue, setInputValue] = useState('');
  const [loading, setLoading] = useState(false);
  const [composedPrompt, setComposedPrompt] = useState(null);
  const [showDebug, setShowDebug] = useState(false);
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);

  // Scroll to bottom when new messages arrive
  useEffect(() => {
    if (messagesEndRef.current && isOpen) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, loading, isOpen]);

  // Focus input when widget opens
  useEffect(() => {
    if (isOpen && inputRef.current) {
      inputRef.current.focus();
    }
  }, [isOpen]);

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
    setComposedPrompt(null);

    try {
      // Test with bundle_id: null to use the active/live prompt
      const result = await api.testPrompt(null, message, history);

      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: result.response },
      ]);
      setComposedPrompt(result.composed_prompt);

      if (onTestComplete) {
        onTestComplete(result);
      }
    } catch (err) {
      const errorMessage = err.message || 'Test failed. Please try again.';
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

  const clearChat = () => {
    setMessages([]);
    setComposedPrompt(null);
    setShowDebug(false);
  };

  const toggleWidget = () => {
    setIsOpen(!isOpen);
  };

  return (
    <div className={`test-chat-widget ${isOpen ? 'test-chat-widget--open' : ''} ${className}`}>
      {/* Floating Button */}
      <button
        className="test-chat-widget__toggle"
        onClick={toggleWidget}
        aria-label={isOpen ? 'Close test chat' : 'Open test chat'}
        title="Test your chatbot"
      >
        {isOpen ? (
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        ) : (
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
          </svg>
        )}
      </button>

      {/* Chat Panel */}
      {isOpen && (
        <div className="test-chat-widget__panel">
          {/* Header */}
          <div className="test-chat-widget__header">
            <div className="test-chat-widget__header-left">
              <span className="test-chat-widget__avatar">🐆</span>
              <div className="test-chat-widget__header-text">
                <span className="test-chat-widget__title">Test Chat</span>
                <span className="test-chat-widget__subtitle">Testing live prompt</span>
              </div>
            </div>
            <div className="test-chat-widget__header-actions">
              <button
                className="test-chat-widget__action-btn"
                onClick={clearChat}
                title="Clear chat"
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <polyline points="3,6 5,6 21,6" />
                  <path d="M19,6v14a2,2,0,0,1-2,2H7a2,2,0,0,1-2-2V6" />
                  <path d="M10,11v6" />
                  <path d="M14,11v6" />
                </svg>
              </button>
              <button
                className="test-chat-widget__action-btn"
                onClick={toggleWidget}
                title="Close"
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <polyline points="6,9 12,15 18,9" />
                </svg>
              </button>
            </div>
          </div>

          {/* Messages */}
          <div className="test-chat-widget__messages">
            {messages.length === 0 ? (
              <div className="test-chat-widget__empty">
                <div className="test-chat-widget__empty-icon">💬</div>
                <p>Test your live prompt</p>
                <span>Send a message to see how your chatbot responds with the current configuration.</span>
              </div>
            ) : (
              messages.map((msg, idx) => (
                <div
                  key={`${msg.role}-${idx}`}
                  className={`test-chat-widget__message test-chat-widget__message--${msg.role}`}
                >
                  {msg.role === 'assistant' && (
                    <span className="test-chat-widget__message-avatar">🐆</span>
                  )}
                  <div className="test-chat-widget__bubble">
                    {renderLinkifiedText(msg.content)}
                  </div>
                </div>
              ))
            )}

            {/* Typing indicator */}
            {loading && (
              <div className="test-chat-widget__message test-chat-widget__message--assistant">
                <span className="test-chat-widget__message-avatar">🐆</span>
                <div className="test-chat-widget__bubble test-chat-widget__typing">
                  <span />
                  <span />
                  <span />
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>

          {/* Debug Panel */}
          {composedPrompt && (
            <div className="test-chat-widget__debug">
              <button
                className="test-chat-widget__debug-toggle"
                onClick={() => setShowDebug(!showDebug)}
              >
                <svg
                  width="12"
                  height="12"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  style={{ transform: showDebug ? 'rotate(90deg)' : 'rotate(0deg)' }}
                >
                  <polyline points="9,18 15,12 9,6" />
                </svg>
                View composed prompt
              </button>
              {showDebug && (
                <pre className="test-chat-widget__debug-content">
                  {composedPrompt}
                </pre>
              )}
            </div>
          )}

          {/* Input */}
          <form className="test-chat-widget__input-area" onSubmit={handleSubmit}>
            <textarea
              ref={inputRef}
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Type a test message..."
              rows={1}
              disabled={loading}
              className="test-chat-widget__input"
            />
            <button
              type="submit"
              disabled={loading || !inputValue.trim()}
              className="test-chat-widget__send-btn"
              title="Send message"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <line x1="22" y1="2" x2="11" y2="13" />
                <polygon points="22,2 15,22 11,13 2,9" />
              </svg>
            </button>
          </form>
        </div>
      )}
    </div>
  );
}
