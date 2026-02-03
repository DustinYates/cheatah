import { useState, useEffect, useCallback } from 'react';
import { Phone, MessageSquare, Mail, Bot, ChevronDown, Loader2 } from 'lucide-react';
import { api } from '../../api/client';
import { formatSmartDateTime } from '../../utils/dateFormat';
import './ActivityFeed.css';

/**
 * Get icon component for activity type
 */
function getTypeIcon(type) {
  switch (type) {
    case 'call':
      return Phone;
    case 'sms':
      return MessageSquare;
    case 'email':
      return Mail;
    case 'chat':
      return Bot;
    default:
      return MessageSquare;
  }
}

/**
 * Get display label for activity type
 */
function getTypeLabel(type) {
  switch (type) {
    case 'call':
      return 'Voice Call';
    case 'sms':
      return 'SMS';
    case 'email':
      return 'Email';
    case 'chat':
      return 'Web Chat';
    default:
      return type;
  }
}

/**
 * Single activity item
 */
function ActivityFeedItem({ item, isExpanded, onToggle }) {
  const Icon = getTypeIcon(item.type);

  return (
    <div className={`activity-feed-item activity-feed-item--${item.type}`}>
      <div className="activity-feed-item-icon">
        <Icon size={16} />
      </div>

      <div className="activity-feed-item-content">
        <button className="activity-feed-item-header" onClick={onToggle}>
          <div className="activity-feed-item-info">
            <span className="activity-feed-item-type">{getTypeLabel(item.type)}</span>
            <span className="activity-feed-item-summary">{item.summary}</span>
          </div>
          <div className="activity-feed-item-meta">
            <span className="activity-feed-item-time">
              {formatSmartDateTime(item.timestamp)}
            </span>
            {item.details && (
              <ChevronDown
                size={14}
                className={`activity-feed-item-chevron ${isExpanded ? 'expanded' : ''}`}
              />
            )}
          </div>
        </button>

        {isExpanded && item.details && (
          <div className="activity-feed-item-details">
            {item.type === 'call' && (
              <>
                {item.details.duration && (
                  <div className="detail-row">
                    <span className="detail-label">Duration:</span>
                    <span className="detail-value">
                      {Math.floor(item.details.duration / 60)}m {item.details.duration % 60}s
                    </span>
                  </div>
                )}
                {item.details.intent && (
                  <div className="detail-row">
                    <span className="detail-label">Intent:</span>
                    <span className="detail-value">
                      {item.details.intent.replace(/_/g, ' ')}
                    </span>
                  </div>
                )}
                {item.details.outcome && (
                  <div className="detail-row">
                    <span className="detail-label">Outcome:</span>
                    <span className="detail-value">
                      {item.details.outcome.replace(/_/g, ' ')}
                    </span>
                  </div>
                )}
              </>
            )}
            {(item.type === 'sms' || item.type === 'chat') && item.details.message_count && (
              <div className="detail-row">
                <span className="detail-label">Messages:</span>
                <span className="detail-value">{item.details.message_count}</span>
              </div>
            )}
            {item.type === 'email' && item.details.subject && (
              <div className="detail-row">
                <span className="detail-label">Subject:</span>
                <span className="detail-value">{item.details.subject}</span>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

/**
 * Activity feed with pagination
 */
export default function ActivityFeed({ contactId, pageSize = 10 }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(false);
  const [total, setTotal] = useState(0);
  const [expandedId, setExpandedId] = useState(null);
  const [filter, setFilter] = useState(null);

  const fetchFeed = useCallback(async (pageNum, channelFilter) => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getContactActivityFeed(contactId, pageNum, pageSize, channelFilter);
      if (pageNum === 1) {
        setItems(data.items);
      } else {
        setItems(prev => [...prev, ...data.items]);
      }
      setHasMore(data.has_more);
      setTotal(data.total);
    } catch (err) {
      setError(err.message || 'Failed to load activity feed');
    } finally {
      setLoading(false);
    }
  }, [contactId, pageSize]);

  useEffect(() => {
    setPage(1);
    fetchFeed(1, filter);
  }, [contactId, filter, fetchFeed]);

  const loadMore = () => {
    const nextPage = page + 1;
    setPage(nextPage);
    fetchFeed(nextPage, filter);
  };

  const handleFilterChange = (newFilter) => {
    setFilter(newFilter === filter ? null : newFilter);
  };

  return (
    <div className="activity-feed">
      <div className="activity-feed-header">
        <h3 className="activity-feed-title">Activity Feed</h3>
        <div className="activity-feed-filters">
          {['call', 'sms', 'email', 'chat'].map((type) => (
            <button
              key={type}
              className={`filter-btn ${filter === type ? 'active' : ''}`}
              onClick={() => handleFilterChange(type)}
            >
              {getTypeLabel(type)}
            </button>
          ))}
        </div>
      </div>

      {error && (
        <div className="activity-feed-error">
          {error}
          <button onClick={() => fetchFeed(1, filter)}>Retry</button>
        </div>
      )}

      {items.length === 0 && !loading && (
        <div className="activity-feed-empty">
          <p>No activity found{filter ? ` for ${getTypeLabel(filter)}` : ''}.</p>
        </div>
      )}

      <div className="activity-feed-list">
        {items.map((item) => (
          <ActivityFeedItem
            key={item.id}
            item={item}
            isExpanded={expandedId === item.id}
            onToggle={() => setExpandedId(expandedId === item.id ? null : item.id)}
          />
        ))}
      </div>

      {loading && (
        <div className="activity-feed-loading">
          <Loader2 size={20} className="spinner" />
          <span>Loading...</span>
        </div>
      )}

      {hasMore && !loading && (
        <button className="activity-feed-load-more" onClick={loadMore}>
          Load more ({items.length} of {total})
        </button>
      )}
    </div>
  );
}
