import { useState, useEffect } from 'react';
import { Phone, MessageSquare, Bot, Mail, Calendar, X } from 'lucide-react';
import { api } from '../api/client';
import { formatSmartDateTime } from '../utils/dateFormat';
import { buildUnifiedTimeline, getTimelineSources } from '../utils/timelineTransform';
import TimelineItem from './TimelineItem';
import LoadingState from './ui/LoadingState';
import './LeadDetailsModal.css';

/**
 * Format phone number for display
 */
function formatPhone(phone) {
  if (!phone) return '—';

  // Convert E.164 format (+15551234567) to readable format
  const cleaned = phone.replace(/\D/g, '');
  if (cleaned.length === 11 && cleaned.startsWith('1')) {
    const areaCode = cleaned.slice(1, 4);
    const prefix = cleaned.slice(4, 7);
    const line = cleaned.slice(7);
    return `(${areaCode}) ${prefix}-${line}`;
  }

  return phone;
}

/**
 * LeadDetailsModal Component
 * Displays a chronological timeline of all interactions with a lead
 */
export default function LeadDetailsModal({ lead, onClose }) {
  const [timeline, setTimeline] = useState([]);
  const [expandedItems, setExpandedItems] = useState(new Set());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Fetch conversation data and build timeline
  useEffect(() => {
    const fetchTimelineData = async () => {
      setLoading(true);
      setError(null);

      try {
        // Fetch conversation data (includes SMS and chatbot messages)
        const conversationData = await api.getLeadConversation(lead.id);

        // Build unified timeline
        const timelineData = buildUnifiedTimeline(lead, conversationData);
        setTimeline(timelineData);
      } catch (err) {
        console.error('Failed to load timeline:', err);
        setError('Failed to load interaction timeline');
        // Still show timeline with just voice calls if conversation fetch fails
        const timelineData = buildUnifiedTimeline(lead, null);
        setTimeline(timelineData);
      } finally {
        setLoading(false);
      }
    };

    fetchTimelineData();
  }, [lead.id]);

  // Toggle expand/collapse for a timeline item
  const toggleItem = (itemId) => {
    setExpandedItems(prev => {
      const next = new Set(prev);
      if (next.has(itemId)) {
        next.delete(itemId);
      } else {
        next.add(itemId);
      }
      return next;
    });
  };

  // Close modal on escape key
  useEffect(() => {
    const handleEscape = (e) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };

    document.addEventListener('keydown', handleEscape);
    return () => document.removeEventListener('keydown', handleEscape);
  }, [onClose]);

  // Prevent body scroll when modal is open
  useEffect(() => {
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = '';
    };
  }, []);

  // Get source types present in timeline
  const sources = getTimelineSources(timeline);

  return (
    <div className="lead-details-modal-overlay" onClick={onClose}>
      <div className="lead-details-modal" onClick={(e) => e.stopPropagation()}>
        {/* Modal Header */}
        <div className="modal-header">
          <h2>Lead Activity Timeline</h2>
          <button
            className="btn-close"
            onClick={onClose}
            type="button"
            aria-label="Close modal"
          >
            <X size={20} />
          </button>
        </div>

        {/* Sticky Summary Section */}
        <div className="sticky-summary">
          <h3 className="summary-name">{lead.name || 'Unknown Contact'}</h3>

          <div className="summary-grid">
            <div className="summary-item">
              <Mail size={14} className="summary-icon" />
              <span className="summary-label">Email</span>
              <span className="summary-value">{lead.email || '—'}</span>
            </div>

            <div className="summary-item">
              <Phone size={14} className="summary-icon" />
              <span className="summary-label">Phone</span>
              <span className="summary-value">{formatPhone(lead.phone)}</span>
            </div>

            <div className="summary-item">
              <Calendar size={14} className="summary-icon" />
              <span className="summary-label">First Contact</span>
              <span className="summary-value">
                {lead.created_at ? formatSmartDateTime(lead.created_at) : '—'}
              </span>
            </div>
          </div>

          {/* Source badges */}
          {(sources.hasVoiceCalls || sources.hasSMS || sources.hasChatbot || sources.hasEmail) && (
            <div className="summary-sources">
              {sources.hasVoiceCalls && (
                <span className="source-pill source-pill--voice">
                  <Phone size={12} />
                  <span>Voice</span>
                </span>
              )}
              {sources.hasSMS && (
                <span className="source-pill source-pill--sms">
                  <MessageSquare size={12} />
                  <span>SMS</span>
                </span>
              )}
              {sources.hasChatbot && (
                <span className="source-pill source-pill--chatbot">
                  <Bot size={12} />
                  <span>Chat</span>
                </span>
              )}
              {sources.hasEmail && (
                <span className="source-pill source-pill--email">
                  <Mail size={12} />
                  <span>Form</span>
                </span>
              )}
            </div>
          )}
        </div>

        {/* Timeline Body */}
        <div className="timeline-body">
          {loading ? (
            <div className="timeline-loading">
              <LoadingState message="Loading timeline..." />
            </div>
          ) : error && timeline.length === 0 ? (
            <div className="timeline-error">
              <p>{error}</p>
            </div>
          ) : timeline.length === 0 ? (
            <div className="timeline-empty">
              <Bot size={48} strokeWidth={1.5} className="empty-icon" />
              <p className="empty-text">No interactions yet</p>
              <p className="empty-subtext">
                Timeline will show voice calls, SMS messages, and chatbot conversations
              </p>
            </div>
          ) : (
            <div className="timeline-container">
              {timeline.map((item, index) => (
                <TimelineItem
                  key={item.id}
                  item={item}
                  isExpanded={expandedItems.has(item.id)}
                  onToggle={() => toggleItem(item.id)}
                  isLast={index === timeline.length - 1}
                />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
