import { useState, useEffect, useCallback } from 'react';
import { Phone, MessageSquare, Mail, MessagesSquare, Clock, ChevronDown } from 'lucide-react';
import { api } from '../api/client';
import './ContactHistoryModal.css';

const CHANNEL_ICONS = {
  call: Phone,
  sms: MessageSquare,
  email: Mail,
  chat: MessagesSquare,
};

const CHANNEL_LABELS = {
  call: 'Voice Call',
  sms: 'SMS',
  email: 'Email',
  chat: 'Web Chat',
};

const CHANNEL_COLORS = {
  call: '#8b5cf6',
  sms: '#10b981',
  email: '#f59e0b',
  chat: '#3b82f6',
};

function formatRelativeTime(timestamp) {
  const date = new Date(timestamp);
  const now = new Date();
  const diffMs = now - date;
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffMins < 1) return 'Just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;

  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function formatFullDateTime(timestamp) {
  const date = new Date(timestamp);
  return date.toLocaleString('en-US', {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
}

export default function ContactHistoryModal({ contact, onClose }) {
  const [activities, setActivities] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [channelFilter, setChannelFilter] = useState(null);

  const fetchActivities = useCallback(async (pageNum = 1, append = false) => {
    try {
      if (pageNum === 1) {
        setLoading(true);
      } else {
        setLoadingMore(true);
      }

      const data = await api.getContactActivityFeed(contact.id, pageNum, 20, channelFilter);

      if (append) {
        setActivities(prev => [...prev, ...data.items]);
      } else {
        setActivities(data.items);
      }

      setHasMore(data.has_more);
      setPage(pageNum);
    } catch (err) {
      setError(err.message || 'Failed to load activity');
    } finally {
      setLoading(false);
      setLoadingMore(false);
    }
  }, [contact.id, channelFilter]);

  useEffect(() => {
    if (contact?.id) {
      fetchActivities(1, false);
    }
  }, [contact?.id, fetchActivities]);

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

  const handleLoadMore = () => {
    if (!loadingMore && hasMore) {
      fetchActivities(page + 1, true);
    }
  };

  const handleFilterChange = (channel) => {
    setChannelFilter(channel === channelFilter ? null : channel);
    setPage(1);
  };

  return (
    <div className="history-modal-overlay" onClick={onClose}>
      <div className="history-modal-drawer" onClick={(e) => e.stopPropagation()}>
        <div className="history-modal-header">
          <div className="history-modal-contact">
            <div className="history-modal-avatar">
              {(contact.name || 'U')[0].toUpperCase()}
            </div>
            <div className="history-modal-info">
              <h3>{contact.name || 'Unknown'}</h3>
              <span className="history-modal-sub">
                {contact.email || contact.phone || '-'}
              </span>
            </div>
          </div>
          <button className="history-modal-close" onClick={onClose}>×</button>
        </div>

        {/* Channel filter pills */}
        <div className="history-filter-bar">
          <button
            className={`filter-pill ${!channelFilter ? 'active' : ''}`}
            onClick={() => handleFilterChange(null)}
          >
            All
          </button>
          {Object.keys(CHANNEL_ICONS).map(channel => {
            const Icon = CHANNEL_ICONS[channel];
            return (
              <button
                key={channel}
                className={`filter-pill ${channelFilter === channel ? 'active' : ''}`}
                onClick={() => handleFilterChange(channel)}
                style={{ '--channel-color': CHANNEL_COLORS[channel] }}
              >
                <Icon size={12} />
                {CHANNEL_LABELS[channel]}
              </button>
            );
          })}
        </div>

        <div className="history-modal-body">
          {loading ? (
            <div className="history-modal-loading">
              <div className="spinner"></div>
              <p>Loading history...</p>
            </div>
          ) : error ? (
            <div className="history-modal-empty">
              <Clock size={32} strokeWidth={1.5} />
              <p>Failed to load history</p>
              <span className="empty-sub">{error}</span>
            </div>
          ) : activities.length > 0 ? (
            <div className="history-timeline">
              {activities.map((activity, index) => {
                const Icon = CHANNEL_ICONS[activity.type] || MessageSquare;
                const color = CHANNEL_COLORS[activity.type] || '#6b7280';

                return (
                  <div key={activity.id} className="timeline-item">
                    <div className="timeline-connector">
                      <div
                        className="timeline-icon"
                        style={{ backgroundColor: color }}
                      >
                        <Icon size={14} color="white" />
                      </div>
                      {index < activities.length - 1 && <div className="timeline-line" />}
                    </div>
                    <div className="timeline-content">
                      <div className="timeline-header">
                        <span className="timeline-type" style={{ color }}>
                          {CHANNEL_LABELS[activity.type] || activity.type}
                        </span>
                        <span
                          className="timeline-time"
                          title={formatFullDateTime(activity.timestamp)}
                        >
                          {formatRelativeTime(activity.timestamp)}
                        </span>
                      </div>
                      <div className="timeline-summary">
                        {activity.summary}
                      </div>
                      {activity.details && (
                        <div className="timeline-details">
                          {activity.details.intent && (
                            <span className="detail-badge intent">
                              {activity.details.intent.replace(/_/g, ' ')}
                            </span>
                          )}
                          {activity.details.outcome && (
                            <span className="detail-badge outcome">
                              {activity.details.outcome.replace(/_/g, ' ')}
                            </span>
                          )}
                          {activity.details.message_count > 0 && (
                            <span className="detail-badge count">
                              {activity.details.message_count} messages
                            </span>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}

              {hasMore && (
                <div className="timeline-load-more">
                  <button
                    onClick={handleLoadMore}
                    disabled={loadingMore}
                    className="btn-load-more"
                  >
                    {loadingMore ? (
                      <>Loading...</>
                    ) : (
                      <>
                        <ChevronDown size={14} />
                        Load more
                      </>
                    )}
                  </button>
                </div>
              )}
            </div>
          ) : (
            <div className="history-modal-empty">
              <Clock size={32} strokeWidth={1.5} />
              <p>No communication history</p>
              <span className="empty-sub">
                {channelFilter
                  ? `No ${CHANNEL_LABELS[channelFilter]} activity found`
                  : 'This contact has no recorded interactions yet.'}
              </span>
            </div>
          )}
        </div>

        <div className="history-modal-footer">
          <span className="history-total">
            {activities.length} {activities.length === 1 ? 'interaction' : 'interactions'}
            {channelFilter && ` (${CHANNEL_LABELS[channelFilter]})`}
          </span>
        </div>
      </div>
    </div>
  );
}
