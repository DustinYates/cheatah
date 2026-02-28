import { useState, useEffect, useRef } from 'react';
import { Phone, MessageSquare, Bot, Mail, Calendar, X, StickyNote, Check, Loader2 } from 'lucide-react';
import { api } from '../api/client';
import { formatSmartDateTime } from '../utils/dateFormat';
import { formatPhone } from '../utils/formatPhone';
import { buildUnifiedTimeline, getTimelineSources } from '../utils/timelineTransform';
import TimelineItem from './TimelineItem';
import LoadingState from './ui/LoadingState';
import './LeadDetailsModal.css';

/**
 * LeadDetailsModal Component
 * Displays a chronological timeline of all interactions with a lead
 */
export default function LeadDetailsModal({ lead, onClose }) {
  const [timeline, setTimeline] = useState([]);
  const [expandedItems, setExpandedItems] = useState(new Set());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [notes, setNotes] = useState(lead.notes || '');
  const [notesSaving, setNotesSaving] = useState(false);
  const [notesSaved, setNotesSaved] = useState(false);
  const notesRef = useRef(null);

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

  // Save notes
  const handleSaveNotes = async () => {
    setNotesSaving(true);
    setNotesSaved(false);
    try {
      await api.updateLeadNotes(lead.id, notes || null);
      lead.notes = notes || null;
      setNotesSaved(true);
      setTimeout(() => setNotesSaved(false), 2000);
    } catch (err) {
      console.error('Failed to save notes:', err);
    } finally {
      setNotesSaving(false);
    }
  };

  const notesChanged = notes !== (lead.notes || '');

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

        {/* Notes Section */}
        <div className="notes-section">
          <div className="notes-header">
            <StickyNote size={14} className="notes-icon" />
            <span className="notes-label">Notes</span>
            <div className="notes-actions">
              {notesSaved && (
                <span className="notes-saved-indicator">
                  <Check size={12} />
                  Saved
                </span>
              )}
              {notesChanged && (
                <button
                  className="notes-save-btn"
                  onClick={handleSaveNotes}
                  disabled={notesSaving}
                >
                  {notesSaving ? <Loader2 size={12} className="spin" /> : 'Save'}
                </button>
              )}
            </div>
          </div>
          <textarea
            ref={notesRef}
            className="notes-textarea"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="Add notes about this lead..."
            rows={3}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && (e.metaKey || e.ctrlKey) && notesChanged) {
                handleSaveNotes();
              }
            }}
          />
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
