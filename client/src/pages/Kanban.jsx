import { useState, useEffect, useCallback, useRef } from 'react';
import { api } from '../api/client';
import LeadDetailsModal from '../components/LeadDetailsModal';
import SendSmsModal from '../components/SendSmsModal';
import { formatSmartDateTime } from '../utils/dateFormat';
import './Kanban.css';

const STAGES = [
  { key: 'new_lead', label: 'New Lead' },
  { key: 'contacted', label: 'Contacted' },
  { key: 'interested', label: 'Interested' },
  { key: 'registered', label: 'Registered' },
  { key: 'enrolled', label: 'Enrolled' },
];

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
  const [leads, setLeads] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedLead, setSelectedLead] = useState(null);
  const [smsLead, setSmsLead] = useState(null);
  const [dragOverStage, setDragOverStage] = useState(null);
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

  const groupedLeads = STAGES.reduce((acc, stage) => {
    acc[stage.key] = leads.filter(
      (l) => (l.pipeline_stage || 'new_lead') === stage.key
    );
    return acc;
  }, {});

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

  const totalLeads = leads.length;

  if (loading) {
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
      </div>

      <div className="kanban-board">
        {STAGES.map((stage) => {
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
                <span className="kanban-column__title">{stage.label}</span>
                <span className="kanban-column__count">{stageLeads.length}</span>
              </div>
              <div className="kanban-column__body">
                {stageLeads.length === 0 ? (
                  <div className="kanban-column__empty">No leads</div>
                ) : (
                  stageLeads.map((lead) => {
                    const channel = getChannel(lead);
                    return (
                      <div
                        key={lead.id}
                        className="kanban-card"
                        draggable
                        onDragStart={(e) => handleDragStart(e, lead)}
                        onDragEnd={handleDragEnd}
                        onClick={() => setSelectedLead(lead)}
                      >
                        <div className="kanban-card__name">{lead.name}</div>
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
                    );
                  })
                )}
              </div>
            </div>
          );
        })}
      </div>

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
    </div>
  );
}
