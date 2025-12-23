import { useState, useEffect } from 'react';
import { api } from '../api/client';
import './ChatModal.css';

export default function ChatModal({ contact, onClose }) {
  const [conversation, setConversation] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchConversation = async () => {
      try {
        setLoading(true);
        const data = await api.getContactConversation(contact.id);
        setConversation(data);
      } catch (err) {
        setError(err.message || 'Failed to load conversation');
      } finally {
        setLoading(false);
      }
    };

    if (contact?.id) {
      fetchConversation();
    }
  }, [contact?.id]);

  // Close on escape key
  useEffect(() => {
    const handleEscape = (e) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handleEscape);
    return () => document.removeEventListener('keydown', handleEscape);
  }, [onClose]);

  // Prevent body scroll when modal is open
  useEffect(() => {
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = 'unset';
    };
  }, []);

  return (
    <div className="chat-modal-overlay" onClick={onClose}>
      <div className="chat-modal-drawer" onClick={(e) => e.stopPropagation()}>
        <div className="chat-modal-header">
          <div className="chat-modal-contact">
            <div className="chat-modal-avatar">
              {(contact.name || 'U')[0].toUpperCase()}
            </div>
            <div className="chat-modal-info">
              <h3>{contact.name || 'Unknown'}</h3>
              <span className="chat-modal-email">{contact.email || contact.phone || '-'}</span>
            </div>
          </div>
          <button className="chat-modal-close" onClick={onClose}>×</button>
        </div>

        <div className="chat-modal-body">
          {loading ? (
            <div className="chat-modal-loading">
              <div className="spinner"></div>
              <p>Loading conversation...</p>
            </div>
          ) : error ? (
            <div className="chat-modal-empty">
              <span className="empty-icon">💬</span>
              <p>No conversation found</p>
              <span className="empty-sub">This contact may not have a linked chat history.</span>
            </div>
          ) : conversation?.messages?.length > 0 ? (
            <div className="chat-messages">
              {conversation.messages.map((msg) => (
                <div key={msg.id} className={`chat-message ${msg.role}`}>
                  <div className="message-bubble">
                    <div className="message-content">{msg.content}</div>
                    <div className="message-time">
                      {new Date(msg.created_at).toLocaleTimeString([], { 
                        hour: '2-digit', 
                        minute: '2-digit' 
                      })}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="chat-modal-empty">
              <span className="empty-icon">💬</span>
              <p>No messages yet</p>
            </div>
          )}
        </div>

        <div className="chat-modal-footer">
          <span className="chat-source">
            Source: {conversation?.channel || contact.source || 'web_chat'}
          </span>
          {conversation?.created_at && (
            <span className="chat-date">
              Started: {new Date(conversation.created_at).toLocaleDateString()}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
