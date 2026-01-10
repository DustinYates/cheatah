import { useState, useEffect } from 'react';
import { api } from '../api/client';
import { LoadingState, EmptyState, ErrorState } from '../components/ui';
import { formatSmartDateTime } from '../utils/dateFormat';
import './Dashboard.css';

// Robot icon SVG component
const RobotIcon = () => (
  <svg
    width="16"
    height="16"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    style={{ verticalAlign: 'middle' }}
  >
    {/* Antenna */}
    <line x1="12" y1="2" x2="12" y2="6" />
    <circle cx="12" cy="2" r="1" fill="currentColor" />
    {/* Head */}
    <rect x="4" y="6" width="16" height="12" rx="2" />
    {/* Eyes */}
    <circle cx="9" cy="11" r="1.5" fill="currentColor" />
    <circle cx="15" cy="11" r="1.5" fill="currentColor" />
    {/* Mouth */}
    <line x1="9" y1="15" x2="15" y2="15" />
    {/* Ears */}
    <rect x="1" y="9" width="2" height="5" rx="1" />
    <rect x="21" y="9" width="2" height="5" rx="1" />
  </svg>
);

// Envelope icon SVG component for email source
const EnvelopeIcon = () => (
  <svg
    width="16"
    height="16"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    style={{ verticalAlign: 'middle' }}
  >
    {/* Envelope body */}
    <rect x="2" y="4" width="20" height="16" rx="2" />
    {/* Envelope flap/seal lines */}
    <polyline points="2,4 12,13 22,4" />
  </svg>
);

// Chat icon SVG component
const ChatIcon = () => (
  <svg
    width="16"
    height="16"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    style={{ verticalAlign: 'middle' }}
  >
    <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z" />
  </svg>
);

// SMS Follow-up icon SVG component
const SmsFollowUpIcon = () => (
  <svg
    width="16"
    height="16"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    style={{ verticalAlign: 'middle' }}
  >
    {/* Phone with outgoing message */}
    <rect x="5" y="2" width="14" height="20" rx="2" />
    <line x1="12" y1="18" x2="12" y2="18.01" />
    {/* Arrow/send indicator */}
    <path d="M9 9l3-3 3 3" />
    <line x1="12" y1="6" x2="12" y2="12" />
  </svg>
);

// Text Bubble icon SVG component for SMS/Text source (iMessage style)
const TextBubbleIcon = () => (
  <svg
    width="16"
    height="16"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    style={{ verticalAlign: 'middle' }}
  >
    {/* Rectangular message bubble */}
    <rect x="3" y="4" width="18" height="13" rx="2" />
    {/* Tail/pointer at bottom */}
    <path d="M7 17 L7 21 L12 17" fill="none" />
    {/* Three dots indicating text */}
    <circle cx="8" cy="10.5" r="1" fill="currentColor" stroke="none" />
    <circle cx="12" cy="10.5" r="1" fill="currentColor" stroke="none" />
    <circle cx="16" cy="10.5" r="1" fill="currentColor" stroke="none" />
  </svg>
);

// Details icon SVG component (document with info)
const DetailsIcon = () => (
  <svg
    width="16"
    height="16"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    style={{ verticalAlign: 'middle' }}
  >
    {/* Document */}
    <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
    <polyline points="14,2 14,8 20,8" />
    {/* Info lines */}
    <line x1="8" y1="13" x2="16" y2="13" />
    <line x1="8" y1="17" x2="14" y2="17" />
  </svg>
);

const CompactTable = ({ containerClassName, tableClassName, children }) => (
  <div className={containerClassName}>
    <table className={tableClassName}>
      {children}
    </table>
  </div>
);

const IconButton = ({ className = '', title, ariaLabel, children, ...props }) => (
  <button
    type="button"
    className={`icon-button ${className}`.trim()}
    title={title}
    aria-label={ariaLabel || title}
    {...props}
  >
    {children}
  </button>
);

const StatusBadge = ({ status, label, variant = 'pill' }) => (
  <span
    className={`status-badge status-${status || 'new'} status-badge--${variant}`}
    title={label || status || 'New'}
    aria-label={label || status || 'New'}
  >
    {variant === 'dot' ? null : label || status || 'New'}
  </span>
);

export default function Dashboard() {
  const [leads, setLeads] = useState([]);
  const [calls, setCalls] = useState([]);
  const [loading, setLoading] = useState(true);
  const [callsLoading, setCallsLoading] = useState(true);
  const [error, setError] = useState('');
  const [actionLoading, setActionLoading] = useState(null);
  const [selectedLead, setSelectedLead] = useState(null);
  const [conversationData, setConversationData] = useState(null);
  const [loadingConversation, setLoadingConversation] = useState(false);
  const [relatedLeads, setRelatedLeads] = useState([]);
  const [loadingRelated, setLoadingRelated] = useState(false);
  const [openActionMenuId, setOpenActionMenuId] = useState(null);

  useEffect(() => {
    fetchData();
  }, []);

  useEffect(() => {
    if (openActionMenuId === null) return;

    const handleClick = (event) => {
      if (!event.target.closest('.action-menu')) {
        setOpenActionMenuId(null);
      }
    };

    document.addEventListener('click', handleClick);
    return () => document.removeEventListener('click', handleClick);
  }, [openActionMenuId]);

  const fetchData = async () => {
    setLoading(true);
    setCallsLoading(true);
    setError('');
    try {
      const [leadsResult, callsResult] = await Promise.allSettled([
        api.getLeads({ limit: 50 }),
        api.getCalls({ page: 1, page_size: 5 }),
      ]);

      if (leadsResult.status === 'fulfilled') {
        const leadsData = leadsResult.value;
        // Sort by created_at descending (most recent first)
        const sortedLeads = (leadsData.leads || leadsData || []).sort(
          (a, b) => new Date(b.created_at) - new Date(a.created_at)
        );
        setLeads(sortedLeads);
      } else {
        setLeads([]);
        throw leadsResult.reason;
      }

      if (callsResult.status === 'fulfilled') {
        const callsData = callsResult.value;
        setCalls(callsData.calls || []);
      } else {
        console.warn('Failed to load recent calls:', callsResult.reason);
        setCalls([]);
      }
    } catch (err) {
      setError('Failed to load dashboard data');
    } finally {
      setLoading(false);
      setCallsLoading(false);
    }
  };

  const handleVerify = async (leadId) => {
    setActionLoading(leadId);
    try {
      await api.updateLeadStatus(leadId, 'verified');
      // Update local state
      setLeads(leads.map(lead => 
        lead.id === leadId ? { ...lead, status: 'verified' } : lead
      ));
    } catch (err) {
      setError('Failed to verify lead');
    } finally {
      setActionLoading(null);
    }
  };

  const handleMarkUnknown = async (leadId) => {
    setActionLoading(leadId);
    try {
      await api.updateLeadStatus(leadId, 'unknown');
      // Update local state
      setLeads(leads.map(lead => 
        lead.id === leadId ? { ...lead, status: 'unknown' } : lead
      ));
    } catch (err) {
      setError('Failed to mark lead as unknown');
    } finally {
      setActionLoading(null);
    }
  };

  const handleDelete = async (leadId, leadName) => {
    if (!confirm(`Are you sure you want to delete "${leadName || 'this lead'}"? This action cannot be undone.`)) {
      return;
    }

    setActionLoading(leadId);
    try {
      await api.deleteLead(leadId);
      // Remove from local state using functional update to ensure we have latest state
      setLeads(prevLeads => prevLeads.filter(lead => lead.id !== leadId));
      setError(''); // Clear any previous errors
    } catch (err) {
      console.error('Delete error details:', {
        message: err.message,
        stack: err.stack,
        error: err
      });
      setError(`Failed to delete lead: ${err.message || 'Unknown error'}`);
    } finally {
      setActionLoading(null);
    }
  };

  const handleTriggerFollowUp = async (lead) => {
    if (!lead.phone) {
      setError('Cannot send follow-up: Lead has no phone number');
      return;
    }

    if (!confirm(`Send a follow-up SMS to ${lead.name || 'this lead'} at ${lead.phone}?`)) {
      return;
    }

    setActionLoading(`followup-${lead.id}`);
    try {
      const result = await api.triggerFollowUp(lead.id);
      if (result.success) {
        // Update local state to mark follow-up as scheduled
        setLeads(prevLeads => prevLeads.map(l =>
          l.id === lead.id
            ? { ...l, extra_data: { ...l.extra_data, followup_scheduled: true } }
            : l
        ));
        setError(''); // Clear any previous errors
      } else {
        setError(result.message || 'Failed to trigger follow-up');
      }
    } catch (err) {
      console.error('Follow-up error:', err);
      setError(`Failed to trigger follow-up: ${err.message || 'Unknown error'}`);
    } finally {
      setActionLoading(null);
    }
  };

  // Check if a lead can receive SMS follow-up (has phone + not already sent)
  const needsFollowUp = (lead) => {
    return lead.phone &&
           !lead.extra_data?.followup_sent_at &&
           !lead.extra_data?.followup_scheduled;
  };

  const handleViewDetails = async (lead) => {
    setSelectedLead(lead);
    setLoadingConversation(true);
    setLoadingRelated(true);
    setConversationData(null);
    setRelatedLeads([]);

    // Fetch conversation and related leads in parallel
    const [convResult, relatedResult] = await Promise.allSettled([
      api.getLeadConversation(lead.id),
      api.getRelatedLeads(lead.id),
    ]);

    if (convResult.status === 'fulfilled') {
      setConversationData(convResult.value);
    } else {
      console.error('Failed to load conversation:', convResult.reason);
    }

    if (relatedResult.status === 'fulfilled') {
      setRelatedLeads(relatedResult.value.leads || []);
    } else {
      console.error('Failed to load related leads:', relatedResult.reason);
    }

    setLoadingConversation(false);
    setLoadingRelated(false);
  };

  const closeModal = () => {
    setSelectedLead(null);
    setConversationData(null);
    setRelatedLeads([]);
  };

  if (loading) {
    return <LoadingState message="Loading dashboard..." fullPage />;
  }

  if (error && leads.length === 0) {
    return <ErrorState message={error} onRetry={fetchData} />;
  }

  const getRowClassName = (lead) => {
    if (lead.status === 'verified' || lead.status === 'unknown') {
      return 'lead-row processed';
    }
    return 'lead-row';
  };

  const getSourceIcon = (lead) => {
    // Check if lead has voice calls first (voice_calls array)
    if (lead.extra_data?.voice_calls?.length > 0) {
      return { icon: '📞', title: 'Phone Call' };
    }

    const source = lead.extra_data?.source;
    switch (source) {
      case 'chatbot':
      case 'web_chat':
      case 'web_chat_lead':
        return { icon: <RobotIcon />, title: 'Chatbot' };
      case 'voice_call':
      case 'phone':
      case 'call':
        return { icon: '📞', title: 'Phone Call' };
      case 'sms':
      case 'text':
        return { icon: <TextBubbleIcon />, title: 'Text Message' };
      case 'email':
        return { icon: <EnvelopeIcon />, title: 'Email' };
      default:
        return { icon: <RobotIcon />, title: 'Chatbot' };
    }
  };

  const getFollowUpIndicator = (lead) => {
    // Green: Agent handled successfully - llm_responded AND (verified OR followup sent)
    if (lead.llm_responded === true) {
      if (lead.status === 'verified' || lead.extra_data?.followup_sent_at) {
        return { className: 'handled', title: 'Handled - No follow-up needed' };
      }
      // LLM responded but still pending review
      return { className: 'pending', title: 'Pending review' };
    }

    // Red: Agent didn't respond - needs human follow-up
    if (lead.llm_responded === false) {
      return { className: 'needs-followup', title: 'Needs human follow-up' };
    }

    // Yellow: Unknown/new status with no conversation data
    if (lead.status === 'unknown') {
      return { className: 'pending', title: 'Status unknown' };
    }

    // Gray fallback: No conversation data
    return { className: 'no-data', title: 'No conversation data' };
  };

  const hasFrustrationSignal = (lead) => {
    const voiceCalls = lead.extra_data?.voice_calls;
    if (!Array.isArray(voiceCalls)) {
      return false;
    }

    return voiceCalls.some((call) => {
      const summary = `${call?.summary || call?.summary_text || ''}`;
      return /frustrat/i.test(summary);
    });
  };

  const hasFollowUpRequest = (lead) => {
    if (lead.extra_data?.followup_requested === true || lead.extra_data?.followup_request === true) {
      return true;
    }

    return needsFollowUp(lead);
  };

  const formatDuration = (seconds) => {
    if (!seconds) return '-';
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  const formatPhone = (phone) => {
    if (!phone) return '-';
    if (phone.length === 12 && phone.startsWith('+1')) {
      return `(${phone.slice(2, 5)}) ${phone.slice(5, 8)}-${phone.slice(8)}`;
    }
    return phone;
  };

  const formatLeadDate = (dateString) => {
    const formatted = formatSmartDateTime(dateString);
    return formatted.replace(/\s[A-Z]{2,4}$/, '');
  };

  // Format name - handle "none", "unknown", null, etc.
  const formatName = (name) => {
    if (!name) return 'None';
    const lower = name.toLowerCase().trim();
    if (lower === 'none' || lower === 'unknown' || lower === 'n/a' || lower === 'not provided') {
      return 'None';
    }
    return name;
  };

  return (
    <div className="dashboard">
      <div className="dashboard-header">
        <div className="dashboard-header__title">
          <h1>Dashboard</h1>
          <span className="dashboard-header__subtitle">Recent activity</span>
        </div>
      </div>

      <div className="dashboard-grid">
        <div className="card leads-card leads-card-wide">
          <div className="card-header">
            <h2>Recent Leads</h2>
            <a className="card-link" href="/contacts">View all</a>
          </div>
          {error && <div className="error">{error}</div>}

          {leads.length === 0 ? (
            <EmptyState
              icon="📋"
              title="No leads yet"
              description="Start conversations to generate leads."
            />
          ) : (
            <CompactTable containerClassName="leads-table-container" tableClassName="leads-table">
              <thead>
                <tr>
                  <th className="col-person">Lead</th>
                  <th className="col-phone">Phone</th>
                  <th className="col-source">Source</th>
                  <th className="col-date">Date</th>
                  <th className="col-details">Details</th>
                  <th className="col-actions">Actions</th>
                </tr>
              </thead>
              <tbody>
                {leads.map((lead) => (
                  <tr key={lead.id} className={getRowClassName(lead)}>
                    <td className="col-person">
                      <div className="lead-person">
                        <span className="lead-person__name">{formatName(lead.name)}</span>
                        <span className="lead-person__email">{lead.email || '—'}</span>
                      </div>
                    </td>
                    <td className="col-phone">
                      <span className="lead-phone">{formatPhone(lead.phone)}</span>
                    </td>
                    <td className="col-source">
                      <div className="source-badges">
                        <span className="source-badge" title={getSourceIcon(lead).title}>
                          <span className="source-icon">
                            {getSourceIcon(lead).icon}
                          </span>
                        </span>
                        <span
                          className={`followup-indicator ${getFollowUpIndicator(lead).className}`}
                          title={getFollowUpIndicator(lead).title}
                        />
                        {hasFrustrationSignal(lead) && (
                          <span
                            className="followup-alert"
                            title="Call ended with frustration"
                            aria-label="Call ended with frustration"
                          >
                            !
                          </span>
                        )}
                        {hasFollowUpRequest(lead) && (
                          <span
                            className="followup-arrow"
                            title="Follow-up requested"
                            aria-label="Follow-up requested"
                          />
                        )}
                      </div>
                    </td>
                    <td className="col-date">
                      <span className="lead-date">{formatLeadDate(lead.created_at)}</span>
                    </td>
                    <td className="col-details">
                      <div className="details-cell">
                        <StatusBadge status={lead.status || 'new'} variant="dot" />
                        <IconButton
                          className="icon-button--ghost"
                          onClick={() => handleViewDetails(lead)}
                          title="View details"
                          ariaLabel="View lead details"
                        >
                          <DetailsIcon />
                        </IconButton>
                      </div>
                    </td>
                    <td className="actions-cell col-actions">
                      <div className="actions-container">
                        {needsFollowUp(lead) && (
                          <IconButton
                            className="icon-button--soft icon-button--info"
                            onClick={() => handleTriggerFollowUp(lead)}
                            disabled={actionLoading === `followup-${lead.id}`}
                            title="Send follow-up SMS"
                            ariaLabel="Send follow-up SMS"
                          >
                            {actionLoading === `followup-${lead.id}` ? (
                              <span className="spinner">⋯</span>
                            ) : (
                              <SmsFollowUpIcon />
                            )}
                          </IconButton>
                        )}
                        {(!lead.status || lead.status === 'new') && (
                          <>
                            <IconButton
                              className="icon-button--soft icon-button--success"
                              onClick={() => handleVerify(lead.id)}
                              disabled={actionLoading === lead.id}
                              title="Mark as verified lead"
                              ariaLabel="Verify lead"
                            >
                              {actionLoading === lead.id ? (
                                <span className="spinner">⋯</span>
                              ) : (
                                <svg className="icon" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                                  <path fillRule="evenodd" d="M16.704 4.153a.75.75 0 01.143 1.052l-8 10.5a.75.75 0 01-1.127.075l-4.5-4.5a.75.75 0 011.06-1.06l3.894 3.893 7.48-9.817a.75.75 0 011.05-.143z" clipRule="evenodd" />
                                </svg>
                              )}
                            </IconButton>
                            <IconButton
                              className="icon-button--soft icon-button--warning"
                              onClick={() => handleMarkUnknown(lead.id)}
                              disabled={actionLoading === lead.id}
                              title="Mark as unknown/spam"
                              ariaLabel="Mark as unknown"
                            >
                              {actionLoading === lead.id ? (
                                <span className="spinner">⋯</span>
                              ) : (
                                <svg className="icon" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                                  <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-8-5a.75.75 0 01.75.75v4.5a.75.75 0 01-1.5 0v-4.5A.75.75 0 0110 5zm0 10a1 1 0 100-2 1 1 0 000 2z" clipRule="evenodd" />
                                </svg>
                              )}
                            </IconButton>
                          </>
                        )}
                        <div className="action-menu">
                          <IconButton
                            className="icon-button--ghost"
                            onClick={(event) => {
                              event.stopPropagation();
                              setOpenActionMenuId(openActionMenuId === lead.id ? null : lead.id);
                            }}
                            title="More actions"
                            ariaLabel="More actions"
                          >
                            ⋮
                          </IconButton>
                          {openActionMenuId === lead.id && (
                            <div className="action-menu__popover" role="menu">
                              <button
                                type="button"
                                className="action-menu__item action-menu__item--danger"
                                onClick={() => {
                                  setOpenActionMenuId(null);
                                  handleDelete(lead.id, lead.name);
                                }}
                                disabled={actionLoading === lead.id}
                                role="menuitem"
                              >
                                Delete lead
                              </button>
                            </div>
                          )}
                        </div>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </CompactTable>
          )}
        </div>

        <div className="card calls-card">
          <div className="card-header">
            <h2>Recent Calls</h2>
            <a className="card-link" href="/calls">View all</a>
          </div>

          {callsLoading ? (
            <LoadingState message="Loading calls..." />
          ) : calls.length === 0 ? (
            <EmptyState
              icon="📞"
              title="No calls yet"
              description="Voice calls will appear here once customers start calling."
            />
          ) : (
            <CompactTable containerClassName="calls-table-container" tableClassName="calls-table">
              <thead>
                <tr>
                  <th>Date & Time</th>
                  <th>Caller</th>
                  <th>Duration</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {calls.map((call) => (
                  <tr key={call.id}>
                    <td className="call-date">{formatLeadDate(call.created_at)}</td>
                    <td className="call-phone">{formatPhone(call.from_number)}</td>
                    <td className="call-duration">{formatDuration(call.duration)}</td>
                    <td>
                      <StatusBadge status={call.status || 'new'} label={call.status || 'New'} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </CompactTable>
          )}
        </div>
      </div>

      {/* Lead Details Modal */}
      {selectedLead && (
        <div className="lead-detail-modal-overlay" onClick={closeModal}>
          <div className="lead-detail-modal" onClick={(e) => e.stopPropagation()}>
            <div className="lead-detail-modal-header">
              <h3>Lead Details</h3>
              <button className="btn-close" onClick={closeModal}>×</button>
            </div>
            <div className="lead-detail-modal-body">
              {/* Lead Info Section */}
              <div className="lead-detail-section">
                <h4>Contact Information</h4>
                <div className="lead-detail-row">
                  <span className="label">Name:</span>
                  <span className="value">{selectedLead.name || 'Unknown'}</span>
                </div>
                <div className="lead-detail-row">
                  <span className="label">Email:</span>
                  <span className="value">{selectedLead.email || '-'}</span>
                </div>
                <div className="lead-detail-row">
                  <span className="label">Phone:</span>
                  <span className="value">{selectedLead.phone || '-'}</span>
                </div>
                <div className="lead-detail-row">
                  <span className="label">Source:</span>
                  <span className="value">
                    {selectedLead.extra_data?.voice_calls?.length > 0
                      ? 'Phone Call'
                      : selectedLead.extra_data?.source || 'Chatbot'}
                  </span>
                </div>
              </div>

              {/* Related Leads - Other interactions from same person */}
              {(relatedLeads.length > 0 || loadingRelated) && (
                <div className="lead-detail-section">
                  <h4>Related Interactions</h4>
                  {loadingRelated ? (
                    <LoadingState message="Loading related leads..." />
                  ) : (
                    <div className="related-leads-list">
                      {relatedLeads.map(related => (
                        <div key={related.id} className="related-lead-item">
                          <span className="related-lead-name">{related.name || 'Unknown'}</span>
                          <span className="related-lead-source">
                            {related.extra_data?.voice_calls?.length > 0
                              ? 'Phone Call'
                              : related.extra_data?.source || 'Chatbot'}
                          </span>
                          <span className="related-lead-date">
                            {formatSmartDateTime(related.created_at)}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* Voice Call Details */}
              {selectedLead.extra_data?.voice_calls?.length > 0 && (
                <div className="lead-detail-section">
                  <h4>Voice Calls</h4>
                  {selectedLead.extra_data.voice_calls.map((call, idx) => (
                    <div key={idx} className="voice-call-item" style={{ background: '#f8f9fa', padding: '12px', borderRadius: '6px', marginBottom: '8px' }}>
                      <div className="lead-detail-row">
                        <span className="label">Date:</span>
                        <span className="value">{call.call_date || 'Unknown'}</span>
                      </div>
                      {call.caller_name && (
                        <div className="lead-detail-row">
                          <span className="label">Name Given:</span>
                          <span className="value">{call.caller_name}</span>
                        </div>
                      )}
                      {call.caller_email && (
                        <div className="lead-detail-row">
                          <span className="label">Email Given:</span>
                          <span className="value">{call.caller_email}</span>
                        </div>
                      )}
                      {call.caller_intent && (
                        <div className="lead-detail-row">
                          <span className="label">Intent:</span>
                          <span className="value">{call.caller_intent}</span>
                        </div>
                      )}
                      {call.summary && (
                        <div className="lead-detail-row" style={{ flexDirection: 'column', alignItems: 'flex-start' }}>
                          <span className="label">Summary:</span>
                          <span className="value" style={{ marginTop: '4px' }}>{call.summary}</span>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}

              {/* Form Submission Data */}
              {selectedLead.extra_data && Object.keys(selectedLead.extra_data).filter(k => !['source', 'parsing_metadata', 'voice_calls', 'followup_sent_at', 'followup_scheduled'].includes(k)).length > 0 && (
                <div className="lead-detail-section">
                  <h4>Form Submission Details</h4>
                  <p className="form-note">This person completed a form for more information.</p>
                  <div className="form-fields">
                    {Object.entries(selectedLead.extra_data)
                      .filter(([key]) => !['source', 'parsing_metadata', 'voice_calls', 'followup_sent_at', 'followup_scheduled'].includes(key))
                      .map(([key, value]) => (
                        <div className="lead-detail-row" key={key}>
                          <span className="label">{key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}:</span>
                          <span className="value">{String(value)}</span>
                        </div>
                      ))
                    }
                  </div>
                </div>
              )}

              {/* Conversation History */}
              <div className="lead-detail-section">
                <h4>Conversation History</h4>
                {loadingConversation ? (
                  <LoadingState message="Loading conversation..." />
                ) : conversationData && conversationData.messages?.length > 0 ? (
                  <div className="messages-list">
                    {conversationData.messages.map((msg, idx) => (
                      <div key={idx} className={`message ${msg.role}`}>
                        <div className="message-role">{msg.role === 'user' ? 'User' : 'Bot'}</div>
                        <div className="message-content">{msg.content}</div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="no-conversation">No conversation history available.</p>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
