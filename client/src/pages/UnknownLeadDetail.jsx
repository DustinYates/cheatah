import { useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { api } from '../api/client';
import { useFetchData } from '../hooks/useFetchData';
import { LoadingState, EmptyState, ErrorState } from '../components/ui';
import './ContactDetail.css';

export default function UnknownLeadDetail() {
  const { id } = useParams();
  const navigate = useNavigate();

  const fetchLead = useCallback(async () => {
    const data = await api.getLead(id);
    return data;
  }, [id]);

  const fetchConversation = useCallback(async () => {
    try {
      const data = await api.getLeadConversation(id);
      return data;
    } catch (err) {
      return null;
    }
  }, [id]);

  const { data: lead, loading: leadLoading, error: leadError, refetch } = useFetchData(fetchLead);
  const { data: conversation, loading: convLoading, refetch: refetchConv } = useFetchData(fetchConversation);

  const handleVerify = async () => {
    try {
      await api.updateLeadStatus(id, 'verified');
      navigate('/contacts');
    } catch (err) {
      console.error('Failed to verify:', err);
    }
  };

  const handleDismiss = async () => {
    try {
      await api.updateLeadStatus(id, 'dismissed');
      navigate('/unknown');
    } catch (err) {
      console.error('Failed to dismiss:', err);
    }
  };

  if (leadLoading) {
    return <LoadingState message="Loading lead..." fullPage />;
  }

  if (leadError) {
    return (
      <div className="contact-detail-page">
        <ErrorState message={leadError} onRetry={() => navigate('/unknown')} />
      </div>
    );
  }

  if (!lead) {
    return (
      <div className="contact-detail-page">
        <EmptyState icon="👤" title="Lead not found" />
      </div>
    );
  }

  return (
    <div className="contact-detail-page">
      <div className="page-header">
        <button className="back-btn" onClick={() => navigate('/unknown')}>
          ← Back to Unknown Leads
        </button>
        <h1>Review Lead</h1>
      </div>

      <div className="contact-detail-grid">
        <div className="contact-info-card">
          <div className="contact-avatar-large" style={{ background: '#f59e0b' }}>
            {(lead.name || '?')[0].toUpperCase()}
          </div>
          <h2>{lead.name || 'Unknown'}</h2>
          <span className="status-badge unknown">Unknown</span>
          <div className="contact-details">
            <div className="detail-row">
              <span className="label">Email:</span>
              <span className="value">{lead.email || '-'}</span>
            </div>
            <div className="detail-row">
              <span className="label">Phone:</span>
              <span className="value">{lead.phone || '-'}</span>
            </div>
            <div className="detail-row">
              <span className="label">Created:</span>
              <span className="value">{new Date(lead.created_at).toLocaleDateString()}</span>
            </div>
          </div>
          <div className="action-buttons">
            <button className="btn-verify-large" onClick={handleVerify}>
              ✓ Verify as Contact
            </button>
            <button className="btn-dismiss" onClick={handleDismiss}>
              ✗ Dismiss
            </button>
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
              description="No chat messages found for this lead."
            />
          )}
        </div>
      </div>
    </div>
  );
}
