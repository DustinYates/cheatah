import { useState, useEffect, useRef, useCallback } from 'react';
import { api } from '../api/client';

const CHANNEL_COLORS = {
  sms: { bg: '#dbeafe', color: '#1e40af', label: 'SMS' },
  web: { bg: '#dcfce7', color: '#166534', label: 'Web' },
  voice: { bg: '#ede9fe', color: '#5b21b6', label: 'Voice' },
  email: { bg: '#ffedd5', color: '#9a3412', label: 'Email' },
};

const REPLY_CHANNELS = new Set(['sms', 'web']);

function formatMessageTime(dateStr) {
  if (!dateStr) return '';
  const d = new Date(dateStr);
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function formatDateSeparator(dateStr) {
  if (!dateStr) return '';
  const d = new Date(dateStr);
  const today = new Date();
  const yesterday = new Date(today);
  yesterday.setDate(yesterday.getDate() - 1);

  if (d.toDateString() === today.toDateString()) return 'Today';
  if (d.toDateString() === yesterday.toDateString()) return 'Yesterday';
  return d.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' });
}

export default function InboxConversationDetail({ conversationId, onStatusChange }) {
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [replyText, setReplyText] = useState('');
  const [sending, setSending] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const messagesEndRef = useRef(null);
  const pollRef = useRef(null);

  const fetchDetail = useCallback(async () => {
    try {
      const data = await api.getInboxConversation(conversationId);
      setDetail(data);
      setError(null);
    } catch (err) {
      setError(err.message || 'Failed to load conversation');
    } finally {
      setLoading(false);
    }
  }, [conversationId]);

  // Initial fetch
  useEffect(() => {
    setLoading(true);
    setDetail(null);
    setReplyText('');
    fetchDetail();
  }, [conversationId, fetchDetail]);

  // Poll for new messages every 10s
  useEffect(() => {
    pollRef.current = setInterval(fetchDetail, 10000);
    return () => clearInterval(pollRef.current);
  }, [fetchDetail]);

  // Auto-scroll to bottom
  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [detail?.messages?.length]);

  const handleSendReply = async (e) => {
    e.preventDefault();
    if (!replyText.trim() || sending) return;

    setSending(true);
    try {
      await api.replyToConversation(conversationId, replyText.trim());
      setReplyText('');
      await fetchDetail();
    } catch (err) {
      alert(err.message || 'Failed to send reply');
    } finally {
      setSending(false);
    }
  };

  const handleResolve = async () => {
    setActionLoading(true);
    try {
      await api.resolveConversation(conversationId);
      await fetchDetail();
      onStatusChange?.();
    } catch (err) {
      alert(err.message || 'Failed to resolve conversation');
    } finally {
      setActionLoading(false);
    }
  };

  const handleReopen = async () => {
    setActionLoading(true);
    try {
      await api.reopenConversation(conversationId);
      await fetchDetail();
      onStatusChange?.();
    } catch (err) {
      alert(err.message || 'Failed to reopen conversation');
    } finally {
      setActionLoading(false);
    }
  };

  const handleResolveEscalation = async (escalationId) => {
    setActionLoading(true);
    try {
      await api.resolveInboxEscalation(escalationId, 'Resolved from inbox');
      await fetchDetail();
      onStatusChange?.();
    } catch (err) {
      alert(err.message || 'Failed to resolve escalation');
    } finally {
      setActionLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="inbox-detail-loading">
        <div className="spinner" />
        <span>Loading conversation...</span>
      </div>
    );
  }

  if (error || !detail) {
    return (
      <div className="inbox-detail-error">
        <p>{error || 'Conversation not found'}</p>
        <button onClick={fetchDetail}>Retry</button>
      </div>
    );
  }

  const channel = CHANNEL_COLORS[detail.channel] || CHANNEL_COLORS.web;
  const canReply = REPLY_CHANNELS.has(detail.channel);
  const pendingEscalations = (detail.escalations || []).filter(
    (e) => e.status === 'pending' || e.status === 'notified'
  );
  const displayName =
    detail.contact?.name ||
    detail.contact?.phone ||
    detail.phone_number ||
    detail.contact?.email ||
    'Anonymous';

  // Group messages by date for separators
  let lastDateStr = '';
  const messagesWithSeparators = [];
  for (const msg of detail.messages || []) {
    if (msg.role === 'system') continue;
    const dateStr = msg.created_at ? new Date(msg.created_at).toDateString() : '';
    if (dateStr && dateStr !== lastDateStr) {
      messagesWithSeparators.push({ type: 'separator', date: msg.created_at });
      lastDateStr = dateStr;
    }
    messagesWithSeparators.push({ type: 'message', ...msg });
  }

  return (
    <div className="inbox-detail">
      {/* Header */}
      <div className="inbox-detail-header">
        <div className="inbox-detail-header-left">
          <div className="inbox-detail-avatar">
            {displayName[0].toUpperCase()}
          </div>
          <div className="inbox-detail-contact">
            <h3>{displayName}</h3>
            <div className="inbox-detail-meta">
              {detail.contact?.phone && (
                <span>{detail.contact.phone}</span>
              )}
              {detail.contact?.email && (
                <span>{detail.contact.email}</span>
              )}
            </div>
          </div>
        </div>
        <div className="inbox-detail-header-right">
          <span
            className="inbox-channel-badge"
            style={{ background: channel.bg, color: channel.color }}
          >
            {channel.label}
          </span>
          <span
            className={`inbox-status-pill ${detail.status}`}
          >
            {detail.status === 'open' ? 'Open' : 'Resolved'}
          </span>
          {detail.status === 'open' ? (
            <button
              className="inbox-action-btn resolve"
              onClick={handleResolve}
              disabled={actionLoading}
            >
              Resolve
            </button>
          ) : (
            <button
              className="inbox-action-btn reopen"
              onClick={handleReopen}
              disabled={actionLoading}
            >
              Reopen
            </button>
          )}
        </div>
      </div>

      {/* Escalation banner */}
      {pendingEscalations.length > 0 && (
        <div className="inbox-escalation-banner">
          <div className="inbox-escalation-banner-text">
            <strong>Escalation pending</strong>
            <span>
              {pendingEscalations[0].reason} &mdash; &ldquo;{pendingEscalations[0].trigger_message}&rdquo;
            </span>
          </div>
          <button
            className="inbox-action-btn resolve-esc"
            onClick={() => handleResolveEscalation(pendingEscalations[0].id)}
            disabled={actionLoading}
          >
            Resolve Escalation
          </button>
        </div>
      )}

      {/* Messages */}
      <div className="inbox-detail-messages">
        {messagesWithSeparators.length === 0 ? (
          <div className="inbox-detail-empty">No messages in this conversation.</div>
        ) : (
          messagesWithSeparators.map((item, idx) => {
            if (item.type === 'separator') {
              return (
                <div key={`sep-${idx}`} className="inbox-date-separator">
                  <span>{formatDateSeparator(item.date)}</span>
                </div>
              );
            }

            const isHuman = item.metadata?.human_reply;

            return (
              <div key={item.id} className={`inbox-message ${item.role}`}>
                <div className="inbox-message-bubble">
                  <div className="inbox-message-content">{item.content}</div>
                  <div className="inbox-message-footer">
                    {isHuman && <span className="inbox-human-label">Human</span>}
                    <span className="inbox-message-time">
                      {formatMessageTime(item.created_at)}
                    </span>
                  </div>
                </div>
              </div>
            );
          })
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Reply composer */}
      {canReply ? (
        <form className="inbox-reply-composer" onSubmit={handleSendReply}>
          <textarea
            className="inbox-reply-input"
            placeholder={`Reply via ${detail.channel === 'sms' ? 'SMS' : 'web chat'}...`}
            value={replyText}
            onChange={(e) => setReplyText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleSendReply(e);
              }
            }}
            rows={2}
          />
          <button
            type="submit"
            className="inbox-reply-send"
            disabled={!replyText.trim() || sending}
          >
            {sending ? 'Sending...' : 'Send'}
          </button>
        </form>
      ) : (
        <div className="inbox-readonly-footer">
          Read-only &mdash; {detail.channel === 'voice' ? 'voice transcript' : 'email thread'}
        </div>
      )}
    </div>
  );
}
