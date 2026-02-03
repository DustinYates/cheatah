import { useState, useEffect, useRef } from 'react';

const CHANNEL_COLORS = {
  sms: { bg: '#dbeafe', color: '#1e40af', label: 'SMS' },
  web: { bg: '#dcfce7', color: '#166534', label: 'Web' },
  voice: { bg: '#ede9fe', color: '#5b21b6', label: 'Voice' },
  email: { bg: '#ffedd5', color: '#9a3412', label: 'Email' },
};

function timeAgo(dateStr) {
  if (!dateStr) return '';
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now - date;
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return 'now';
  if (diffMin < 60) return `${diffMin}m`;
  const diffHrs = Math.floor(diffMin / 60);
  if (diffHrs < 24) return `${diffHrs}h`;
  const diffDays = Math.floor(diffHrs / 24);
  if (diffDays < 7) return `${diffDays}d`;
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

function truncate(text, maxLen = 60) {
  if (!text) return '';
  return text.length > maxLen ? text.slice(0, maxLen) + '...' : text;
}

export default function InboxConversationList({
  conversations,
  total,
  selectedId,
  onSelect,
  filters,
  onFilterChange,
  loading,
  onLoadMore,
}) {
  const [searchInput, setSearchInput] = useState(filters.search || '');
  const debounceRef = useRef(null);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      if (searchInput !== (filters.search || '')) {
        onFilterChange({ ...filters, search: searchInput || '' });
      }
    }, 300);
    return () => clearTimeout(debounceRef.current);
  }, [searchInput]);

  const handleChannelChange = (e) => {
    onFilterChange({ ...filters, channel: e.target.value });
  };

  const handleStatusChange = (e) => {
    onFilterChange({ ...filters, status: e.target.value });
  };

  return (
    <div className="inbox-list">
      <div className="inbox-list-header">
        <h2>Inbox</h2>
        <span className="inbox-list-count">{total} conversations</span>
      </div>

      <div className="inbox-list-filters">
        <input
          type="text"
          className="inbox-search"
          placeholder="Search name, phone, or email..."
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
        />
        <div className="inbox-filter-row">
          <select
            className="inbox-filter-select"
            value={filters.channel || ''}
            onChange={handleChannelChange}
          >
            <option value="">All channels</option>
            <option value="sms">SMS</option>
            <option value="web">Web Chat</option>
            <option value="voice">Voice</option>
            <option value="email">Email</option>
          </select>
          <select
            className="inbox-filter-select"
            value={filters.status || ''}
            onChange={handleStatusChange}
          >
            <option value="">All status</option>
            <option value="open">Open</option>
            <option value="resolved">Resolved</option>
          </select>
        </div>
      </div>

      <div className="inbox-list-items">
        {loading && conversations.length === 0 ? (
          <div className="inbox-list-loading">
            <div className="spinner" />
            <span>Loading conversations...</span>
          </div>
        ) : conversations.length === 0 ? (
          <div className="inbox-list-empty">
            <span>No conversations found</span>
          </div>
        ) : (
          <>
            {conversations.map((conv) => {
              const channel = CHANNEL_COLORS[conv.channel] || CHANNEL_COLORS.web;
              const displayName =
                conv.contact_name ||
                conv.contact_phone ||
                conv.phone_number ||
                conv.contact_email ||
                'Anonymous';
              const isActive = conv.id === selectedId;
              const needsAttention = conv.last_message_role === 'user';
              const hasEscalation = conv.pending_escalations > 0;

              return (
                <button
                  key={conv.id}
                  className={`inbox-list-item ${isActive ? 'active' : ''}`}
                  onClick={() => onSelect(conv.id)}
                >
                  <div className="inbox-item-avatar">
                    {displayName[0].toUpperCase()}
                  </div>
                  <div className="inbox-item-content">
                    <div className="inbox-item-top">
                      <span className="inbox-item-name">{displayName}</span>
                      <span className="inbox-item-time">
                        {timeAgo(conv.last_message_at || conv.updated_at)}
                      </span>
                    </div>
                    <div className="inbox-item-bottom">
                      <span className="inbox-item-preview">
                        {truncate(conv.last_message_content)}
                      </span>
                    </div>
                    <div className="inbox-item-badges">
                      <span
                        className="inbox-channel-badge"
                        style={{ background: channel.bg, color: channel.color }}
                      >
                        {channel.label}
                      </span>
                      {conv.status === 'resolved' && (
                        <span className="inbox-status-badge resolved">Resolved</span>
                      )}
                      {hasEscalation && (
                        <span className="inbox-escalation-badge" title="Pending escalation">
                          Escalated
                        </span>
                      )}
                    </div>
                  </div>
                  {needsAttention && !isActive && (
                    <span className="inbox-unread-dot" />
                  )}
                </button>
              );
            })}
            {conversations.length < total && (
              <button className="inbox-load-more" onClick={onLoadMore}>
                Load more
              </button>
            )}
          </>
        )}
      </div>
    </div>
  );
}
