import { useState, useEffect, useRef } from 'react';
import { Phone, MessageSquare, Bot, Mail, Calendar, X, StickyNote, Check, Loader2, ListTodo, Trash2, Plus, Send, User, MapPin, Waves, GraduationCap, Megaphone, Sparkles, BarChart3, ChevronDown } from 'lucide-react';
import { api } from '../api/client';
import { formatSmartDateTime } from '../utils/dateFormat';
import { formatPhone } from '../utils/formatPhone';
import { buildUnifiedTimeline, getTimelineSources } from '../utils/timelineTransform';
import TimelineItem from './TimelineItem';
import SendSmsModal from './SendSmsModal';
import LoadingState from './ui/LoadingState';
import './LeadDetailsModal.css';

const TAG_ICONS = {
  audience: User,
  zip: MapPin,
  location: Waves,
  class: GraduationCap,
  lesson_type: GraduationCap,
  source: Megaphone,
  heard_via: Sparkles,
  utm: BarChart3,
};

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

  // Tag state
  const [tagList, setTagList] = useState(Array.isArray(lead.tags) ? lead.tags : []);
  const [customTags, setCustomTags] = useState(Array.isArray(lead.custom_tags) ? lead.custom_tags : []);
  const [newTag, setNewTag] = useState('');
  const [tagSaving, setTagSaving] = useState(false);

  // SMS modal state
  const [showSmsModal, setShowSmsModal] = useState(false);

  // Tasks state
  const [tasks, setTasks] = useState([]);
  const [newTaskTitle, setNewTaskTitle] = useState('');
  const [newTaskDueDate, setNewTaskDueDate] = useState('');
  const [taskAdding, setTaskAdding] = useState(false);

  // Collapsible section state — default collapsed to give conversation more room
  const [notesExpanded, setNotesExpanded] = useState(Boolean((lead.notes || '').trim()));
  const [tasksExpanded, setTasksExpanded] = useState(false);

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

        // Fetch tasks
        try {
          const tasksData = await api.getLeadTasks(lead.id);
          setTasks(tasksData || []);
          if (tasksData && tasksData.some((t) => !t.is_completed)) {
            setTasksExpanded(true);
          }
        } catch (taskErr) {
          console.warn('Failed to load tasks:', taskErr);
        }
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

  const handleAddTag = async () => {
    const value = newTag.trim();
    if (!value || tagSaving) return;
    setTagSaving(true);
    try {
      const updated = await api.addLeadTag(lead.id, value);
      setTagList(Array.isArray(updated.tags) ? updated.tags : tagList);
      setCustomTags(Array.isArray(updated.custom_tags) ? updated.custom_tags : customTags);
      lead.tags = updated.tags;
      lead.custom_tags = updated.custom_tags;
      setNewTag('');
    } catch (err) {
      console.error('Failed to add tag:', err);
    } finally {
      setTagSaving(false);
    }
  };

  const handleRemoveTag = async (tagValue) => {
    if (tagSaving) return;
    setTagSaving(true);
    try {
      const updated = await api.removeLeadTag(lead.id, tagValue);
      setTagList(Array.isArray(updated.tags) ? updated.tags : tagList);
      setCustomTags(Array.isArray(updated.custom_tags) ? updated.custom_tags : customTags);
      lead.tags = updated.tags;
      lead.custom_tags = updated.custom_tags;
    } catch (err) {
      console.error('Failed to remove tag:', err);
    } finally {
      setTagSaving(false);
    }
  };

  // Task handlers
  const handleAddTask = async () => {
    if (!newTaskTitle.trim()) return;
    setTaskAdding(true);
    try {
      const task = await api.createLeadTask(lead.id, {
        title: newTaskTitle.trim(),
        due_date: newTaskDueDate || null,
      });
      setTasks((prev) => [...prev, task]);
      setNewTaskTitle('');
      setNewTaskDueDate('');
    } catch (err) {
      console.error('Failed to create task:', err);
    } finally {
      setTaskAdding(false);
    }
  };

  const handleToggleTask = async (task) => {
    const updated = { is_completed: !task.is_completed };
    // Optimistic update
    setTasks((prev) =>
      prev.map((t) => (t.id === task.id ? { ...t, ...updated } : t))
    );
    try {
      await api.updateLeadTask(lead.id, task.id, updated);
    } catch (err) {
      // Revert
      setTasks((prev) =>
        prev.map((t) => (t.id === task.id ? task : t))
      );
    }
  };

  const handleDeleteTask = async (taskId) => {
    setTasks((prev) => prev.filter((t) => t.id !== taskId));
    try {
      await api.deleteLeadTask(lead.id, taskId);
    } catch (err) {
      // Refetch on error
      const tasksData = await api.getLeadTasks(lead.id);
      setTasks(tasksData || []);
    }
  };

  const isOverdue = (dueDateStr) => {
    if (!dueDateStr) return false;
    const due = new Date(dueDateStr);
    const now = new Date();
    return due < now;
  };

  const formatDueDate = (dueDateStr) => {
    if (!dueDateStr) return '';
    const due = new Date(dueDateStr);
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const tomorrow = new Date(today);
    tomorrow.setDate(tomorrow.getDate() + 1);
    const dueDay = new Date(due);
    dueDay.setHours(0, 0, 0, 0);

    if (dueDay.getTime() === today.getTime()) return 'Today';
    if (dueDay.getTime() === tomorrow.getTime()) return 'Tomorrow';
    return due.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
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

          <div className="lead-tags">
            {tagList.map((tag, idx) => {
              const Icon = TAG_ICONS[tag.category] || Sparkles;
              return (
                <span
                  key={`${tag.category}-${idx}-${tag.value}`}
                  className={`lead-tag lead-tag--${tag.category}${tag.editable ? ' lead-tag--editable' : ''}`}
                  title={`${tag.label}: ${tag.value}`}
                >
                  <Icon size={12} className="lead-tag__icon" strokeWidth={2.25} />
                  <span className="lead-tag__value">{tag.value}</span>
                  {tag.editable && (
                    <button
                      type="button"
                      className="lead-tag__remove"
                      onClick={() => handleRemoveTag(tag.value)}
                      disabled={tagSaving}
                      aria-label={`Remove ${tag.value}`}
                    >
                      <X size={10} strokeWidth={2.5} />
                    </button>
                  )}
                </span>
              );
            })}
            <form
              className="lead-tag-add"
              onSubmit={(e) => {
                e.preventDefault();
                handleAddTag();
              }}
            >
              <input
                type="text"
                className="lead-tag-add__input"
                placeholder="+ Add tag"
                value={newTag}
                onChange={(e) => setNewTag(e.target.value)}
                maxLength={32}
                disabled={tagSaving}
              />
            </form>
          </div>
        </div>

        {/* Notes Section */}
        <div className={`notes-section ${notesExpanded ? 'expanded' : 'collapsed'}`}>
          <div
            className="notes-header section-header-toggle"
            onClick={() => setNotesExpanded((v) => !v)}
            role="button"
            tabIndex={0}
            aria-expanded={notesExpanded}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                setNotesExpanded((v) => !v);
              }
            }}
          >
            <StickyNote size={14} className="notes-icon" />
            <span className="notes-label">Notes</span>
            {!notesExpanded && (notes || '').trim() && (
              <span className="section-preview">{notes}</span>
            )}
            <div className="notes-actions" onClick={(e) => e.stopPropagation()}>
              {notesSaved && (
                <span className="notes-saved-indicator">
                  <Check size={12} />
                  Saved
                </span>
              )}
              {notesChanged && notesExpanded && (
                <button
                  className="notes-save-btn"
                  onClick={handleSaveNotes}
                  disabled={notesSaving}
                  type="button"
                >
                  {notesSaving ? <Loader2 size={12} className="spin" /> : 'Save'}
                </button>
              )}
            </div>
            <ChevronDown
              size={14}
              className={`section-chevron ${notesExpanded ? 'expanded' : ''}`}
            />
          </div>
          {notesExpanded && (
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
          )}
        </div>

        {/* Tasks Section */}
        <div className={`tasks-section ${tasksExpanded ? 'expanded' : 'collapsed'}`}>
          <div
            className="tasks-header section-header-toggle"
            onClick={() => setTasksExpanded((v) => !v)}
            role="button"
            tabIndex={0}
            aria-expanded={tasksExpanded}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                setTasksExpanded((v) => !v);
              }
            }}
          >
            <ListTodo size={14} className="tasks-icon" />
            <span className="tasks-label">Tasks</span>
            <span className="tasks-count">
              {tasks.filter((t) => !t.is_completed).length}
            </span>
            <ChevronDown
              size={14}
              className={`section-chevron ${tasksExpanded ? 'expanded' : ''}`}
            />
          </div>

          {/* Task list */}
          {tasksExpanded && tasks.length > 0 && (
            <div className="tasks-list">
              {tasks.map((task) => (
                <div
                  key={task.id}
                  className={`task-item ${task.is_completed ? 'task-item--completed' : ''}`}
                >
                  <label className="task-checkbox-label">
                    <input
                      type="checkbox"
                      checked={task.is_completed}
                      onChange={() => handleToggleTask(task)}
                      className="task-checkbox"
                    />
                    <span className="task-title">{task.title}</span>
                  </label>
                  {task.due_date && !task.is_completed && (
                    <span
                      className={`task-due ${isOverdue(task.due_date) ? 'task-due--overdue' : ''}`}
                    >
                      {formatDueDate(task.due_date)}
                    </span>
                  )}
                  <button
                    className="task-delete-btn"
                    onClick={() => handleDeleteTask(task.id)}
                    title="Delete task"
                    type="button"
                  >
                    <Trash2 size={12} />
                  </button>
                </div>
              ))}
            </div>
          )}

          {/* Add task form */}
          {tasksExpanded && (
            <div className="task-add-form">
              <input
                type="text"
                className="task-add-input"
                value={newTaskTitle}
                onChange={(e) => setNewTaskTitle(e.target.value)}
                placeholder="Add a task..."
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && newTaskTitle.trim()) handleAddTask();
                }}
              />
              <input
                type="date"
                className="task-add-date"
                value={newTaskDueDate}
                onChange={(e) => setNewTaskDueDate(e.target.value)}
              />
              <button
                className="task-add-btn"
                onClick={handleAddTask}
                disabled={!newTaskTitle.trim() || taskAdding}
                type="button"
              >
                {taskAdding ? <Loader2 size={12} className="spin" /> : <Plus size={14} />}
              </button>
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
              {lead.phone && (
                <div className="timeline-sms-action">
                  <button
                    className="timeline-sms-btn"
                    onClick={() => setShowSmsModal(true)}
                    title="Send SMS"
                    type="button"
                  >
                    <Send size={14} />
                  </button>
                </div>
              )}
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
      {/* SMS Modal */}
      {showSmsModal && (
        <SendSmsModal
          lead={lead}
          onClose={() => setShowSmsModal(false)}
          onSuccess={() => {
            // Refresh timeline to show the sent message
            const refresh = async () => {
              try {
                const conversationData = await api.getLeadConversation(lead.id);
                const timelineData = buildUnifiedTimeline(lead, conversationData);
                setTimeline(timelineData);
              } catch (err) {
                console.warn('Failed to refresh timeline after SMS send:', err);
              }
            };
            refresh();
          }}
        />
      )}
    </div>
  );
}
