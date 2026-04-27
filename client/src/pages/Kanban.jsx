import { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api/client';
import { usePipelineStages } from '../hooks/usePipelineStages';
import LeadDetailsModal from '../components/LeadDetailsModal';
import LeadScoreBadge from '../components/LeadScoreBadge';
import { HoverPreviewWrapper } from '../components/HoverPreview';
import SendSmsModal from '../components/SendSmsModal';
import MassSmsModal from '../components/MassSmsModal';
import EditLeadModal from '../components/EditLeadModal';
import { formatSmartDateTime } from '../utils/dateFormat';
import './Kanban.css';

function CalendarWeekView() {
  const [calendarEvents, setCalendarEvents] = useState([]);
  const [calendarTasks, setCalendarTasks] = useState([]);
  const [weekStart, setWeekStart] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchCalendar() {
      try {
        const [calResult, tasksResult] = await Promise.allSettled([
          api.getCalendarEvents(0),
          api.getUpcomingTasks(7),
        ]);
        if (calResult.status === 'fulfilled') {
          const data = calResult.value;
          setCalendarEvents(data.events || []);
          setWeekStart(data.week_start || '');
        }
        if (tasksResult.status === 'fulfilled') {
          setCalendarTasks(tasksResult.value || []);
        }
      } finally {
        setLoading(false);
      }
    }
    fetchCalendar();
  }, []);

  // Build week days — use API week_start if available, otherwise compute from today (Mon-Sun)
  const today = new Date();
  today.setHours(0, 0, 0, 0);

  const days = [];
  if (weekStart) {
    const start = new Date(weekStart + 'T00:00:00');
    for (let i = 0; i < 7; i++) {
      const day = new Date(start);
      day.setDate(start.getDate() + i);
      days.push(day);
    }
  } else if (!loading) {
    // Fallback: compute current week Mon-Sun
    const dow = today.getDay(); // 0=Sun
    const monday = new Date(today);
    monday.setDate(today.getDate() - ((dow + 6) % 7));
    for (let i = 0; i < 7; i++) {
      const day = new Date(monday);
      day.setDate(monday.getDate() + i);
      days.push(day);
    }
  }

  const displayStart = days[0];
  const displayEnd = days[6];

  return (
    <div className="kanban-calendar-card">
      <div className="kanban-calendar-header">
        <h2>This Week</h2>
        {displayStart && (
          <span className="kanban-calendar-range">
            {displayStart.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
            {' \u2013 '}
            {displayEnd.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
          </span>
        )}
      </div>
      {loading ? (
        <div className="kanban-calendar-empty">Loading...</div>
      ) : (
        <div className="kanban-calendar-grid">
          {days.map((day) => {
            const dayStr = day.toISOString().split('T')[0];
            const isToday = day.getTime() === today.getTime();
            const dayEvents = calendarEvents.filter((evt) => (evt.start || '').split('T')[0] === dayStr);
            const dayTasks = calendarTasks.filter((t) => (t.due_date || '').split('T')[0] === dayStr);
            const hasContent = dayEvents.length > 0 || dayTasks.length > 0;

            return (
              <div key={dayStr} className={`kanban-cal-day ${isToday ? 'kanban-cal-day--today' : ''}`}>
                <div className="kanban-cal-day-header">
                  <span className="kanban-cal-day-name">
                    {day.toLocaleDateString('en-US', { weekday: 'short' })}
                  </span>
                  <span className={`kanban-cal-day-num ${isToday ? 'kanban-cal-day-num--today' : ''}`}>
                    {day.getDate()}
                  </span>
                </div>
                <div className="kanban-cal-day-events">
                  {!hasContent ? (
                    <span className="kanban-cal-no-events">-</span>
                  ) : (
                    <>
                      {dayEvents.map((evt) => {
                        const startTime = evt.all_day
                          ? 'All day'
                          : new Date(evt.start).toLocaleTimeString('en-US', {
                              hour: 'numeric', minute: '2-digit', hour12: true,
                            });
                        return (
                          <div key={evt.id} className="kanban-cal-event" title={`${evt.summary}\n${startTime}`}>
                            <span className="kanban-cal-event-time">{startTime}</span>
                            <span className="kanban-cal-event-title">{evt.summary}</span>
                          </div>
                        );
                      })}
                      {dayTasks.map((t) => {
                        const taskOverdue = new Date(t.due_date) < new Date();
                        return (
                          <div
                            key={`task-${t.id}`}
                            className={`kanban-cal-task ${taskOverdue ? 'kanban-cal-task--overdue' : ''}`}
                            title={`Task: ${t.title}${t.lead_name ? ` (${t.lead_name})` : ''}`}
                          >
                            <span className="kanban-cal-task-icon">
                              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                                <polyline points="9 11 12 14 22 4" />
                                <path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11" />
                              </svg>
                            </span>
                            <span className="kanban-cal-task-title">{t.title}</span>
                          </div>
                        );
                      })}
                    </>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function channelIcon(channel) {
  if (!channel) return null;
  const c = channel.toLowerCase();
  if (c === 'sms' || c === 'telnyx_sms')
    return (
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z" />
      </svg>
    );
  if (c === 'voice' || c === 'telnyx_voice')
    return (
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M22 16.92v3a2 2 0 01-2.18 2 19.79 19.79 0 01-8.63-3.07 19.5 19.5 0 01-6-6 19.79 19.79 0 01-3.07-8.67A2 2 0 014.11 2h3a2 2 0 012 1.72c.127.96.361 1.903.7 2.81a2 2 0 01-.45 2.11L8.09 9.91a16 16 0 006 6l1.27-1.27a2 2 0 012.11-.45c.907.339 1.85.573 2.81.7A2 2 0 0122 16.92z" />
      </svg>
    );
  if (c === 'email')
    return (
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <rect x="2" y="4" width="20" height="16" rx="2" />
        <polyline points="2,4 12,13 22,4" />
      </svg>
    );
  if (c === 'chat' || c === 'web')
    return (
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M21 11.5a8.38 8.38 0 01-.9 3.8 8.5 8.5 0 01-7.6 4.7 8.38 8.38 0 01-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 01-.9-3.8 8.5 8.5 0 014.7-7.6 8.38 8.38 0 013.8-.9h.5a8.48 8.48 0 018 8v.5z" />
      </svg>
    );
  return null;
}

function getChannel(lead) {
  if (lead.extra_data?.source) return lead.extra_data.source;
  if (lead.extra_data?.channel) return lead.extra_data.channel;
  return null;
}

export default function Kanban() {
  const navigate = useNavigate();
  const { stages: STAGES, loading: stagesLoading, stageMap } = usePipelineStages();
  const [leads, setLeads] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedLead, setSelectedLead] = useState(null);
  const [smsLead, setSmsLead] = useState(null);
  const [editLead, setEditLead] = useState(null);
  const [mergeMode, setMergeMode] = useState(null); // { primaryId: X } when merging
  const [dragOverStage, setDragOverStage] = useState(null);
  const [selectedLeadIds, setSelectedLeadIds] = useState(new Set());
  const [massSmsLeads, setMassSmsLeads] = useState(null);
  const draggedLeadRef = useRef(null);

  const fetchLeads = useCallback(async () => {
    try {
      setLoading(true);
      const data = await api.getLeads({ limit: 500 });
      const items = data.leads || data || [];
      // Filter: must have name AND (phone OR email)
      const qualified = items.filter(
        (l) => l.name && (l.phone || l.email)
      );
      setLeads(qualified);
      setError(null);
    } catch (err) {
      setError(err.message || 'Failed to load leads');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchLeads();
  }, [fetchLeads]);

  const visibleStages = STAGES;
  const knownKeys = new Set(STAGES.map((s) => s.key));
  const firstKey = STAGES[0]?.key || 'new_lead';
  // Hide leads older than 15 days in these stages
  const AGE_HIDDEN_STAGES = new Set(['registered', 'lost_opportunity']);
  const fifteenDaysAgo = new Date();
  fifteenDaysAgo.setDate(fifteenDaysAgo.getDate() - 15);

  const groupedLeads = visibleStages.reduce((acc, stage) => {
    acc[stage.key] = leads.filter((l) => {
      if ((l.pipeline_stage || firstKey) !== stage.key) return false;
      if (AGE_HIDDEN_STAGES.has(stage.key)) {
        const leadDate = new Date(l.updated_at || l.created_at);
        if (leadDate < fifteenDaysAgo) return false;
      }
      return true;
    });
    return acc;
  }, {});
  // Collect orphaned leads (pipeline_stage not in any configured stage)
  const orphanedLeads = leads.filter(
    (l) => l.pipeline_stage && !knownKeys.has(l.pipeline_stage)
  );

  // Selection handlers
  const toggleLeadSelection = (e, leadId) => {
    e.stopPropagation();
    setSelectedLeadIds((prev) => {
      const next = new Set(prev);
      if (next.has(leadId)) next.delete(leadId);
      else next.add(leadId);
      return next;
    });
  };

  const toggleColumnSelection = (stageKey) => {
    const stageLeads = groupedLeads[stageKey] || [];
    const stageIds = stageLeads.map((l) => l.id);
    const allSelected = stageIds.length > 0 && stageIds.every((id) => selectedLeadIds.has(id));

    setSelectedLeadIds((prev) => {
      const next = new Set(prev);
      if (allSelected) {
        stageIds.forEach((id) => next.delete(id));
      } else {
        stageIds.forEach((id) => next.add(id));
      }
      return next;
    });
  };

  const clearSelection = () => setSelectedLeadIds(new Set());

  const selectedLeads = leads.filter((l) => selectedLeadIds.has(l.id));

  const handleMassSmsClick = () => {
    if (selectedLeads.length === 0) return;
    setMassSmsLeads(selectedLeads);
  };

  // Drag handlers
  const handleDragStart = (e, lead) => {
    draggedLeadRef.current = lead;
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', lead.id.toString());
    e.currentTarget.classList.add('dragging');
  };

  const handleDragEnd = (e) => {
    e.currentTarget.classList.remove('dragging');
    draggedLeadRef.current = null;
    setDragOverStage(null);
  };

  const handleDragOver = (e, stageKey) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    setDragOverStage(stageKey);
  };

  const handleDragLeave = (e, stageKey) => {
    // Only clear if leaving the column entirely
    if (!e.currentTarget.contains(e.relatedTarget)) {
      setDragOverStage(null);
    }
  };

  const handleDrop = async (e, targetStage) => {
    e.preventDefault();
    setDragOverStage(null);

    const lead = draggedLeadRef.current;
    if (!lead) return;

    const currentStage = lead.pipeline_stage || 'new_lead';
    if (currentStage === targetStage) return;

    // Optimistic update
    setLeads((prev) =>
      prev.map((l) =>
        l.id === lead.id ? { ...l, pipeline_stage: targetStage } : l
      )
    );

    try {
      await api.updateLeadPipelineStage(lead.id, targetStage);
    } catch (err) {
      // Revert on failure
      setLeads((prev) =>
        prev.map((l) =>
          l.id === lead.id ? { ...l, pipeline_stage: currentStage } : l
        )
      );
    }
  };

  const handleSmsClick = (e, lead) => {
    e.stopPropagation();
    setSmsLead(lead);
  };

  const handleEditClick = (e, lead) => {
    e.stopPropagation();
    setEditLead(lead);
  };

  const handleEditSuccess = async (updatedLead) => {
    setEditLead(null);
    // Update lead in state
    setLeads((prev) =>
      prev.map((l) => (l.id === updatedLead.id ? updatedLead : l))
    );
  };

  const handleOptOut = async (e, lead) => {
    e.stopPropagation();
    if (!window.confirm(`Add "${lead.name}" to Do Not Contact list?\n\nThis will block all future communications.`)) {
      return;
    }
    try {
      await api.blockContact({
        phone: lead.phone || undefined,
        email: lead.email || undefined,
        reason: 'Manual opt-out from pipeline',
      });
      // Remove from kanban view
      setLeads((prev) => prev.filter((l) => l.id !== lead.id));
    } catch (err) {
      alert(`Failed to opt out: ${err.message}`);
    }
  };

  const handleMergeClick = (e, lead) => {
    e.stopPropagation();
    setMergeMode({ primaryId: lead.id });
  };

  const handleMergeSecondarySelect = async (e, secondaryLead) => {
    e.stopPropagation();
    if (!mergeMode) return;

    const primaryId = mergeMode.primaryId;
    const secondaryId = secondaryLead.id;

    // Show confirmation
    if (
      !window.confirm(
        `Merge "${secondaryLead.name}" into "${
          leads.find((l) => l.id === primaryId)?.name
        }"?\n\nThe secondary lead will be deleted.`
      )
    ) {
      return;
    }

    try {
      await api.mergeLead(primaryId, secondaryId);
      // Remove secondary from state, refresh primary
      setLeads((prev) => {
        const updated = prev.filter((l) => l.id !== secondaryId);
        return updated;
      });
      setMergeMode(null);
    } catch (err) {
      alert(`Merge failed: ${err.message}`);
    }
  };

  const totalLeads = Object.values(groupedLeads).reduce((sum, arr) => sum + arr.length, 0) + orphanedLeads.length;

  if (loading || stagesLoading) {
    return (
      <div className="kanban-page">
        <div className="kanban-loading">Loading leads...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="kanban-page">
        <div className="kanban-error">{error}</div>
      </div>
    );
  }

  return (
    <div className="kanban-page">
      <div className="kanban-header">
        <h1>
          Pipeline
          <span className="lead-count">({totalLeads} leads)</span>
        </h1>
        <button
          className="kanban-settings-btn"
          onClick={() => navigate('/settings/pipeline')}
          title="Edit pipeline stages"
          type="button"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="3" />
            <path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83 0 2 2 0 010-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 010-2.83 2 2 0 012.83 0l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 0 2 2 0 010 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z" />
          </svg>
        </button>
      </div>

      <CalendarWeekView />

      <div className="kanban-board">
        {visibleStages.map((stage) => {
          const stageLeads = groupedLeads[stage.key] || [];
          return (
            <div
              key={stage.key}
              className={`kanban-column${dragOverStage === stage.key ? ' drag-over' : ''}`}
              data-stage={stage.key}
              onDragOver={(e) => handleDragOver(e, stage.key)}
              onDragLeave={(e) => handleDragLeave(e, stage.key)}
              onDrop={(e) => handleDrop(e, stage.key)}
            >
              <div className="kanban-column__header">
                <div className="kanban-column__header-left">
                  <input
                    type="checkbox"
                    className="kanban-column__select-all"
                    checked={stageLeads.length > 0 && stageLeads.every((l) => selectedLeadIds.has(l.id))}
                    onChange={() => toggleColumnSelection(stage.key)}
                    title={`Select all in ${stage.label}`}
                    disabled={stageLeads.length === 0}
                  />
                  <span className="kanban-column__title">{stage.label}</span>
                </div>
                <span
                  className="kanban-column__count"
                  style={{
                    backgroundColor: `${stage.color}20`,
                    color: stage.color,
                  }}
                >
                  {stageLeads.length}
                </span>
              </div>
              <div className="kanban-column__body">
                {stageLeads.length === 0 ? (
                  <div className="kanban-column__empty">No leads</div>
                ) : (
                  stageLeads.map((lead) => {
                    const channel = getChannel(lead);
                    const isMergeTarget = mergeMode && mergeMode.primaryId === lead.id;
                    const isMergeSecondary = mergeMode && mergeMode.primaryId !== lead.id;
                    return (
                      <HoverPreviewWrapper
                        key={lead.id}
                        text={lead.last_message_preview}
                        role={lead.last_message_role}
                      >
                        {(hoverHandlers) => (
                      <div
                        className={`kanban-card ${isMergeTarget ? 'merge-primary' : ''} ${
                          isMergeSecondary ? 'merge-secondary' : ''
                        } ${selectedLeadIds.has(lead.id) ? 'kanban-card--selected' : ''}`}
                        draggable={!mergeMode}
                        onDragStart={(e) => handleDragStart(e, lead)}
                        onDragEnd={handleDragEnd}
                        {...hoverHandlers}
                        onClick={() => {
                          if (mergeMode && mergeMode.primaryId !== lead.id) {
                            handleMergeSecondarySelect(
                              { stopPropagation: () => {} },
                              lead
                            );
                          } else if (!mergeMode) {
                            setSelectedLead(lead);
                            if (lead.unread_count > 0) {
                              lead.unread_count = 0;
                              api.getLead(lead.id).catch(() => {});
                            }
                          }
                        }}
                      >
                        <div className="kanban-card__header">
                          <input
                            type="checkbox"
                            className="kanban-card__checkbox"
                            checked={selectedLeadIds.has(lead.id)}
                            onChange={(e) => toggleLeadSelection(e, lead.id)}
                            onClick={(e) => e.stopPropagation()}
                          />
                          <div className="kanban-card__name">{lead.name}</div>
                          {lead.unread_count > 0 && (
                            <span className="kanban-card__unread-badge">{lead.unread_count}</span>
                          )}
                          <LeadScoreBadge score={lead.score} band={lead.score_band} />

                          {!mergeMode && (
                            <div className="kanban-card__actions">
                              {lead.phone && (
                                <button
                                  className="kanban-card__btn kanban-card__btn--sms"
                                  onClick={(e) => handleSmsClick(e, lead)}
                                  title="Send text message"
                                  type="button"
                                >
                                  <svg
                                    width="14"
                                    height="14"
                                    viewBox="0 0 24 24"
                                    fill="none"
                                    stroke="currentColor"
                                    strokeWidth="2"
                                    strokeLinecap="round"
                                    strokeLinejoin="round"
                                  >
                                    <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z" />
                                  </svg>
                                </button>
                              )}
                              <button
                                className="kanban-card__btn kanban-card__btn--edit"
                                onClick={(e) => handleEditClick(e, lead)}
                                title="Edit lead"
                                type="button"
                              >
                                <svg
                                  width="14"
                                  height="14"
                                  viewBox="0 0 24 24"
                                  fill="none"
                                  stroke="currentColor"
                                  strokeWidth="2"
                                  strokeLinecap="round"
                                  strokeLinejoin="round"
                                >
                                  <path d="M12 20h9" />
                                  <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19H4v-3L16.5 3.5z" />
                                </svg>
                              </button>
                              <button
                                className="kanban-card__btn kanban-card__btn--merge"
                                onClick={(e) => handleMergeClick(e, lead)}
                                title="Merge with duplicate"
                                type="button"
                              >
                                <svg
                                  width="14"
                                  height="14"
                                  viewBox="0 0 24 24"
                                  fill="none"
                                  stroke="currentColor"
                                  strokeWidth="2"
                                  strokeLinecap="round"
                                  strokeLinejoin="round"
                                >
                                  <circle cx="9" cy="5" r="3" />
                                  <circle cx="15" cy="5" r="3" />
                                  <path d="M9 8v3m0 0v3m6-6v6" />
                                  <path d="M9 17c-2 0-4 1-4 3v2h14v-2c0-2-2-3-4-3h-6z" />
                                </svg>
                              </button>
                              <button
                                className="kanban-card__btn kanban-card__btn--optout"
                                onClick={(e) => handleOptOut(e, lead)}
                                title="Do not contact"
                                type="button"
                              >
                                <svg
                                  width="14"
                                  height="14"
                                  viewBox="0 0 24 24"
                                  fill="none"
                                  stroke="currentColor"
                                  strokeWidth="2"
                                  strokeLinecap="round"
                                  strokeLinejoin="round"
                                >
                                  <circle cx="12" cy="12" r="10" />
                                  <line x1="4.93" y1="4.93" x2="19.07" y2="19.07" />
                                </svg>
                              </button>
                            </div>
                          )}
                          {mergeMode && mergeMode.primaryId === lead.id && (
                            <button
                              className="kanban-card__btn kanban-card__btn--cancel-merge"
                              onClick={(e) => {
                                e.stopPropagation();
                                setMergeMode(null);
                              }}
                              title="Cancel merge"
                              type="button"
                            >
                              ✕
                            </button>
                          )}
                        </div>
                        <div className="kanban-card__contact">
                          {lead.phone || lead.email}
                        </div>
                        {lead.pending_task_count > 0 && (
                          <div className="kanban-card__tasks">
                            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                              <polyline points="9 11 12 14 22 4" />
                              <path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11" />
                            </svg>
                            <span className={`kanban-card__task-text ${lead.next_task_due && new Date(lead.next_task_due) < new Date() ? 'kanban-card__task-text--overdue' : ''}`}>
                              {lead.pending_task_count} task{lead.pending_task_count > 1 ? 's' : ''}
                              {lead.next_task_due && (() => {
                                const due = new Date(lead.next_task_due);
                                const today = new Date();
                                today.setHours(0,0,0,0);
                                const dueDay = new Date(due);
                                dueDay.setHours(0,0,0,0);
                                if (dueDay.getTime() === today.getTime()) return ' · Today';
                                if (due < today) return ' · Overdue';
                                const tomorrow = new Date(today);
                                tomorrow.setDate(tomorrow.getDate() + 1);
                                if (dueDay.getTime() === tomorrow.getTime()) return ' · Tomorrow';
                                return ` · ${due.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}`;
                              })()}
                            </span>
                          </div>
                        )}
                        <div className="kanban-card__footer">
                          {channel ? (
                            <span className="kanban-card__channel">
                              {channelIcon(channel)}
                              {channel}
                            </span>
                          ) : (
                            <span />
                          )}
                          <span className="kanban-card__date">
                            {formatSmartDateTime(lead.updated_at || lead.created_at)}
                          </span>
                        </div>
                      </div>
                        )}
                      </HoverPreviewWrapper>
                    );
                  })
                )}
              </div>
            </div>
          );
        })}
        {orphanedLeads.length > 0 && (
          <div className="kanban-column" data-stage="uncategorized">
            <div className="kanban-column__header">
              <span className="kanban-column__title">Uncategorized</span>
              <span className="kanban-column__count">{orphanedLeads.length}</span>
            </div>
            <div className="kanban-column__body">
              {orphanedLeads.map((lead) => {
                const channel = getChannel(lead);
                const isMergeTarget = mergeMode && mergeMode.primaryId === lead.id;
                const isMergeSecondary = mergeMode && mergeMode.primaryId !== lead.id;
                return (
                  <HoverPreviewWrapper
                    key={lead.id}
                    text={lead.last_message_preview}
                    role={lead.last_message_role}
                  >
                    {(hoverHandlers) => (
                  <div
                    className={`kanban-card ${isMergeTarget ? 'merge-primary' : ''} ${
                      isMergeSecondary ? 'merge-secondary' : ''
                    } ${selectedLeadIds.has(lead.id) ? 'kanban-card--selected' : ''}`}
                    draggable={!mergeMode}
                    onDragStart={(e) => handleDragStart(e, lead)}
                    onDragEnd={handleDragEnd}
                    {...hoverHandlers}
                    onClick={() => {
                      if (mergeMode && mergeMode.primaryId !== lead.id) {
                        handleMergeSecondarySelect(
                          { stopPropagation: () => {} },
                          lead
                        );
                      } else if (!mergeMode) {
                        setSelectedLead(lead);
                        if (lead.unread_count > 0) {
                          lead.unread_count = 0;
                          api.getLead(lead.id).catch(() => {});
                        }
                      }
                    }}
                  >
                    <div className="kanban-card__header">
                      <input
                        type="checkbox"
                        className="kanban-card__checkbox"
                        checked={selectedLeadIds.has(lead.id)}
                        onChange={(e) => toggleLeadSelection(e, lead.id)}
                        onClick={(e) => e.stopPropagation()}
                      />
                      <div className="kanban-card__name">{lead.name}</div>
                      {lead.unread_count > 0 && (
                        <span className="kanban-card__unread-badge">{lead.unread_count}</span>
                      )}
                      {!mergeMode && (
                        <div className="kanban-card__actions">
                          {lead.phone && (
                            <button
                              className="kanban-card__btn kanban-card__btn--sms"
                              onClick={(e) => handleSmsClick(e, lead)}
                              title="Send text message"
                              type="button"
                            >
                              <svg
                                width="14"
                                height="14"
                                viewBox="0 0 24 24"
                                fill="none"
                                stroke="currentColor"
                                strokeWidth="2"
                                strokeLinecap="round"
                                strokeLinejoin="round"
                              >
                                <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z" />
                              </svg>
                            </button>
                          )}
                          <button
                            className="kanban-card__btn kanban-card__btn--edit"
                            onClick={(e) => handleEditClick(e, lead)}
                            title="Edit lead"
                            type="button"
                          >
                            <svg
                              width="14"
                              height="14"
                              viewBox="0 0 24 24"
                              fill="none"
                              stroke="currentColor"
                              strokeWidth="2"
                              strokeLinecap="round"
                              strokeLinejoin="round"
                            >
                              <path d="M12 20h9" />
                              <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19H4v-3L16.5 3.5z" />
                            </svg>
                          </button>
                          <button
                            className="kanban-card__btn kanban-card__btn--merge"
                            onClick={(e) => handleMergeClick(e, lead)}
                            title="Merge with duplicate"
                            type="button"
                          >
                            <svg
                              width="14"
                              height="14"
                              viewBox="0 0 24 24"
                              fill="none"
                              stroke="currentColor"
                              strokeWidth="2"
                              strokeLinecap="round"
                              strokeLinejoin="round"
                            >
                              <circle cx="9" cy="5" r="3" />
                              <circle cx="15" cy="5" r="3" />
                              <path d="M9 8v3m0 0v3m6-6v6" />
                              <path d="M9 17c-2 0-4 1-4 3v2h14v-2c0-2-2-3-4-3h-6z" />
                            </svg>
                          </button>
                          <button
                            className="kanban-card__btn kanban-card__btn--optout"
                            onClick={(e) => handleOptOut(e, lead)}
                            title="Do not contact"
                            type="button"
                          >
                            <svg
                              width="14"
                              height="14"
                              viewBox="0 0 24 24"
                              fill="none"
                              stroke="currentColor"
                              strokeWidth="2"
                              strokeLinecap="round"
                              strokeLinejoin="round"
                            >
                              <circle cx="12" cy="12" r="10" />
                              <line x1="4.93" y1="4.93" x2="19.07" y2="19.07" />
                            </svg>
                          </button>
                        </div>
                      )}
                      {mergeMode && mergeMode.primaryId === lead.id && (
                        <button
                          className="kanban-card__btn kanban-card__btn--cancel-merge"
                          onClick={(e) => {
                            e.stopPropagation();
                            setMergeMode(null);
                          }}
                          title="Cancel merge"
                          type="button"
                        >
                          ✕
                        </button>
                      )}
                    </div>
                    <div className="kanban-card__contact">
                      {lead.phone || lead.email}
                    </div>
                    <div className="kanban-card__footer">
                      {channel ? (
                        <span className="kanban-card__channel">
                          {channelIcon(channel)}
                          {channel}
                        </span>
                      ) : (
                        <span />
                      )}
                      <span className="kanban-card__date">
                        {formatSmartDateTime(lead.updated_at || lead.created_at)}
                      </span>
                    </div>
                  </div>
                    )}
                  </HoverPreviewWrapper>
                );
              })}
            </div>
          </div>
        )}
      </div>

      {editLead && (
        <EditLeadModal
          lead={editLead}
          onSuccess={handleEditSuccess}
          onCancel={() => setEditLead(null)}
        />
      )}

      {selectedLead && (
        <LeadDetailsModal
          lead={selectedLead}
          onClose={() => setSelectedLead(null)}
        />
      )}

      {smsLead && (
        <SendSmsModal
          lead={smsLead}
          onClose={() => setSmsLead(null)}
          onSuccess={fetchLeads}
        />
      )}

      {selectedLeadIds.size > 0 && (
        <div className="kanban-selection-bar">
          <span className="kanban-selection-bar__count">
            {selectedLeadIds.size} selected
          </span>
          <button
            className="kanban-selection-bar__btn kanban-selection-bar__btn--sms"
            onClick={handleMassSmsClick}
            type="button"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z" />
            </svg>
            Send Mass Text
          </button>
          <button
            className="kanban-selection-bar__btn kanban-selection-bar__btn--clear"
            onClick={clearSelection}
            type="button"
          >
            Clear
          </button>
        </div>
      )}

      {massSmsLeads && (
        <MassSmsModal
          leads={massSmsLeads}
          stages={STAGES}
          onClose={() => setMassSmsLeads(null)}
          onSuccess={() => {
            clearSelection();
            fetchLeads();
          }}
        />
      )}
    </div>
  );
}
