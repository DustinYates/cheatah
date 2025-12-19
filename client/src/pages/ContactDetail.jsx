import { useState, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { api } from '../api/client';
import { useFetchData } from '../hooks/useFetchData';
import { LoadingState, EmptyState, ErrorState } from '../components/ui';
import './ContactDetail.css';

export default function ContactDetail() {
  const { id } = useParams();
  const navigate = useNavigate();

  const fetchContact = useCallback(async () => {
    const data = await api.getContact(id);
    return data;
  }, [id]);

  const fetchConversation = useCallback(async () => {
    try {
      const data = await api.getContactConversation(id);
      return data;
    } catch (err) {
      return null;
    }
  }, [id]);

  const { data: contact, loading: contactLoading, error: contactError } = useFetchData(fetchContact);
  const { data: conversation, loading: convLoading } = useFetchData(fetchConversation);

  if (contactLoading) {
    return <LoadingState message="Loading contact..." fullPage />;
  }

  if (contactError) {
    return (
      <div className="contact-detail-page">
        <ErrorState message={contactError} onRetry={() => navigate('/contacts')} />
      </div>
    );
  }

  if (!contact) {
    return (
      <div className="contact-detail-page">
        <EmptyState icon="👤" title="Contact not found" />
      </div>
    );
  }

  return (
    <div className="contact-detail-page">
      <div className="page-header">
        <button className="back-btn" onClick={() => navigate('/contacts')}>
          ← Back to Contacts
        </button>
        <h1>Contact Details</h1>
      </div>

      <div className="contact-detail-grid">
        <div className="contact-info-card">
          <div className="contact-avatar-large">
            {(contact.name || 'U')[0].toUpperCase()}
          </div>
          <h2>{contact.name || 'Unknown'}</h2>
          <div className="contact-details">
            <div className="detail-row">
              <span className="label">Email:</span>
              <span className="value">{contact.email || '-'}</span>
            </div>
            <div className="detail-row">
              <span className="label">Phone:</span>
              <span className="value">{contact.phone_number || '-'}</span>
            </div>
            <div className="detail-row">
              <span className="label">Source:</span>
              <span className="value">{contact.source || 'web_chat'}</span>
            </div>
            <div className="detail-row">
              <span className="label">Added:</span>
              <span className="value">{new Date(contact.created_at).toLocaleDateString()}</span>
            </div>
          </div>
        </div>

        <div className="conversation-card">
          <h3>Conversation History</h3>
          {convLoading ? (
            <LoadingState message="Loading conversation..." />
          ) : conversation && conversation.messages?.length > 0 ? (
            <div className="messages-list">
              {conversation.messages.map((msg, idx) => (
                <div key={idx} className={`message ${msg.role}`}>
                  <div className="message-role">{msg.role === 'user' ? '👤 User' : '🤖 Bot'}</div>
                  <div className="message-content">{msg.content}</div>
                  <div className="message-time">
                    {new Date(msg.created_at).toLocaleString()}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <EmptyState 
              icon="💬" 
              title="No conversation history" 
              description="No chat messages found for this contact."
            />
          )}
        </div>
      </div>
    </div>
  );
}
