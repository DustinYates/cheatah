import { useState, useEffect } from 'react';
import { api } from '../api/client';
import { LoadingState, EmptyState, ErrorState } from '../components/ui';
import { formatSmartDateTime } from '../utils/dateFormat';
import './Dashboard.css';

// Robot icon SVG component
const RobotIcon = () => (
  <svg
    width="20"
    height="20"
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
    width="20"
    height="20"
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
    width="18"
    height="18"
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

export default function Dashboard() {
  const [leads, setLeads] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [actionLoading, setActionLoading] = useState(null);
  const [selectedLead, setSelectedLead] = useState(null);
  const [conversationData, setConversationData] = useState(null);
  const [loadingConversation, setLoadingConversation] = useState(false);

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    setLoading(true);
    setError('');
    try {
      const leadsData = await api.getLeads({ limit: 50 }).catch(() => ({ leads: [] }));
      // Sort by created_at descending (most recent first)
      const sortedLeads = (leadsData.leads || leadsData || []).sort(
        (a, b) => new Date(b.created_at) - new Date(a.created_at)
      );
      setLeads(sortedLeads);
    } catch (err) {
      setError('Failed to load dashboard data');
    } finally {
      setLoading(false);
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

  const handleViewDetails = async (lead) => {
    setSelectedLead(lead);
    setLoadingConversation(true);
    setConversationData(null);
    try {
      const data = await api.getLeadConversation(lead.id);
      setConversationData(data);
    } catch (err) {
      console.error('Failed to load conversation:', err);
    } finally {
      setLoadingConversation(false);
    }
  };

  const closeModal = () => {
    setSelectedLead(null);
    setConversationData(null);
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
        return { icon: '💬', title: 'Text Message' };
      case 'email':
        return { icon: <EnvelopeIcon />, title: 'Email' };
      default:
        return { icon: <RobotIcon />, title: 'Chatbot' };
    }
  };

  const getResponseIndicator = (lead) => {
    if (lead.llm_responded === true) {
      return { className: 'responded', title: 'LLM responded' };
    } else if (lead.llm_responded === false) {
      return { className: 'not-responded', title: 'No LLM response' };
    }
    return { className: 'no-conversation', title: 'No conversation' };
  };

  return (
    <div className="dashboard">
      <h1>Dashboard</h1>

      <div className="dashboard-grid">
        <div className="card leads-card leads-card-wide">
          <h2>Recent Leads</h2>
          {error && <div className="error">{error}</div>}

          {leads.length === 0 ? (
            <EmptyState
              icon="📋"
              title="No leads yet"
              description="Start conversations to generate leads."
            />
          ) : (
            <div className="leads-table-container">
              <table className="leads-table">
                <thead>
                  <tr>
                    <th className="col-name">Name</th>
                    <th className="col-email">Email</th>
                    <th className="col-phone">Phone</th>
                    <th className="col-source">Source</th>
                    <th className="col-date">Date</th>
                    <th className="col-status">Status</th>
                    <th className="col-actions">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {leads.map((lead) => (
                    <tr key={lead.id} className={getRowClassName(lead)}>
                      <td className="col-name">{lead.name || 'Unknown'}</td>
                      <td className="col-email">{lead.email || '-'}</td>
                      <td className="col-phone">{lead.phone || '-'}</td>
                      <td className="col-source">
                        <span className="source-icon" title={getSourceIcon(lead).title}>
                          {getSourceIcon(lead).icon}
                        </span>
                        <span
                          className={`response-indicator ${getResponseIndicator(lead).className}`}
                          title={getResponseIndicator(lead).title}
                        />
                      </td>
                      <td className="col-date">{formatSmartDateTime(lead.created_at)}</td>
                      <td className="col-status">
                        <span className={`status-badge ${lead.status || 'new'}`}>
                          {lead.status || 'New'}
                        </span>
                        <button
                          className="btn-chat-icon"
                          onClick={() => handleViewDetails(lead)}
                          title="View details"
                          aria-label="View lead details"
                        >
                          <ChatIcon />
                        </button>
                      </td>
                      <td className="actions-cell col-actions">
                        <div className="actions-container">
                          {(!lead.status || lead.status === 'new') ? (
                            <>
                              <button
                                className="btn-action btn-verify"
                                onClick={() => handleVerify(lead.id)}
                                disabled={actionLoading === lead.id}
                                title="Mark as verified lead"
                                aria-label="Verify lead"
                              >
                                {actionLoading === lead.id ? (
                                  <span className="spinner">⋯</span>
                                ) : (
                                  <svg className="icon" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                                    <path fillRule="evenodd" d="M16.704 4.153a.75.75 0 01.143 1.052l-8 10.5a.75.75 0 01-1.127.075l-4.5-4.5a.75.75 0 011.06-1.06l3.894 3.893 7.48-9.817a.75.75 0 011.05-.143z" clipRule="evenodd" />
                                  </svg>
                                )}
                              </button>
                              <button
                                className="btn-action btn-unknown"
                                onClick={() => handleMarkUnknown(lead.id)}
                                disabled={actionLoading === lead.id}
                                title="Mark as unknown/spam"
                                aria-label="Mark as unknown"
                              >
                                {actionLoading === lead.id ? (
                                  <span className="spinner">⋯</span>
                                ) : (
                                  <svg className="icon" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                                    <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-8-5a.75.75 0 01.75.75v4.5a.75.75 0 01-1.5 0v-4.5A.75.75 0 0110 5zm0 10a1 1 0 100-2 1 1 0 000 2z" clipRule="evenodd" />
                                  </svg>
                                )}
                              </button>
                            </>
                          ) : lead.status === 'verified' ? (
                            <button
                              className="btn-action btn-sync"
                              onClick={() => handleVerify(lead.id)}
                              disabled={actionLoading === lead.id}
                              title="Re-sync to create contact"
                              aria-label="Sync contact"
                            >
                              {actionLoading === lead.id ? (
                                <span className="spinner">⋯</span>
                              ) : (
                                <svg className="icon" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                                  <path fillRule="evenodd" d="M15.312 11.424a5.5 5.5 0 01-9.201 2.466l-.312-.311h2.433a.75.75 0 000-1.5H3.989a.75.75 0 00-.75.75v4.242a.75.75 0 001.5 0v-2.43l.31.31a7 7 0 0011.712-3.138.75.75 0 00-1.449-.39zm1.23-3.723a.75.75 0 00.219-.53V2.929a.75.75 0 00-1.5 0V5.36l-.31-.31A7 7 0 003.239 8.188a.75.75 0 101.448.389A5.5 5.5 0 0113.89 6.11l.311.31h-2.432a.75.75 0 000 1.5h4.243a.75.75 0 00.53-.219z" clipRule="evenodd" />
                                </svg>
                              )}
                            </button>
                          ) : (
                            <div className="action-placeholder" aria-hidden="true"></div>
                          )}
                          <button
                            className="btn-action btn-delete"
                            onClick={() => handleDelete(lead.id, lead.name)}
                            disabled={actionLoading === lead.id}
                            title="Permanently delete this lead"
                            aria-label="Delete lead"
                          >
                            {actionLoading === lead.id ? (
                              <span className="spinner">⋯</span>
                            ) : (
                              <svg className="icon" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                                <path fillRule="evenodd" d="M8.75 1A2.75 2.75 0 006 3.75v.443c-.795.077-1.584.176-2.365.298a.75.75 0 10.23 1.482l.149-.022.841 10.518A2.75 2.75 0 007.596 19h4.807a2.75 2.75 0 002.742-2.53l.841-10.52.149.023a.75.75 0 00.23-1.482A41.03 41.03 0 0014 4.193V3.75A2.75 2.75 0 0011.25 1h-2.5zM10 4c.84 0 1.673.025 2.5.075V3.75c0-.69-.56-1.25-1.25-1.25h-2.5c-.69 0-1.25.56-1.25 1.25v.325C8.327 4.025 9.16 4 10 4zM8.58 7.72a.75.75 0 00-1.5.06l.3 7.5a.75.75 0 101.5-.06l-.3-7.5zm4.34.06a.75.75 0 10-1.5-.06l-.3 7.5a.75.75 0 101.5.06l.3-7.5z" clipRule="evenodd" />
                              </svg>
                            )}
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
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
                  <span className="value">{selectedLead.extra_data?.source || 'chatbot'}</span>
                </div>
              </div>

              {/* Form Submission Data */}
              {selectedLead.extra_data && Object.keys(selectedLead.extra_data).filter(k => k !== 'source' && k !== 'parsing_metadata').length > 0 && (
                <div className="lead-detail-section">
                  <h4>Form Submission Details</h4>
                  <p className="form-note">This person completed a form for more information.</p>
                  <div className="form-fields">
                    {Object.entries(selectedLead.extra_data)
                      .filter(([key]) => key !== 'source' && key !== 'parsing_metadata')
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
