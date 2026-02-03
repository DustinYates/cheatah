import { useState, useCallback, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import { api } from '../api/client';
import { useFetchData } from '../hooks/useFetchData';
import { LoadingState, EmptyState, ErrorState } from '../components/ui';
import EditContactModal from '../components/EditContactModal';
import {
  ContactProfileHeader,
  ActivityHeatmap,
  ActivityFeed,
  InterestTags,
  CollapsibleSection,
} from '../components/contact';
import { formatDateTimeParts } from '../utils/dateFormat';
import './ContactDetail.css';

// Format duration as mm:ss
function formatDuration(seconds) {
  if (!seconds) return '-';
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${mins}:${secs.toString().padStart(2, '0')}`;
}

// Intent display labels
const INTENT_LABELS = {
  pricing_info: 'Pricing',
  hours_location: 'Hours/Location',
  booking_request: 'Booking',
  support_request: 'Support',
  wrong_number: 'Wrong Number',
  general_inquiry: 'General',
  unknown: 'Unknown',
};

export default function ContactDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [showEditModal, setShowEditModal] = useState(false);
  const [aliases, setAliases] = useState([]);
  const [loadingAliases, setLoadingAliases] = useState(true);
  const [mergeHistory, setMergeHistory] = useState([]);
  const [loadingHistory, setLoadingHistory] = useState(true);
  const [newAlias, setNewAlias] = useState({ alias_type: 'email', value: '' });
  const [addingAlias, setAddingAlias] = useState(false);
  const [error, setError] = useState('');
  const [calls, setCalls] = useState([]);
  const [loadingCalls, setLoadingCalls] = useState(true);
  const [selectedCall, setSelectedCall] = useState(null);
  const [emailConversations, setEmailConversations] = useState([]);
  const [loadingEmails, setLoadingEmails] = useState(true);
  const [dncStatus, setDncStatus] = useState({ is_blocked: false, record: null });
  const [dncLoading, setDncLoading] = useState(false);
  const [heatmapData, setHeatmapData] = useState(null);
  const [loadingHeatmap, setLoadingHeatmap] = useState(true);

  const fetchContact = useCallback(async () => {
    const data = await api.getContact(id, true);
    return data;
  }, [id]);

  const { data: contact, loading: contactLoading, error: contactError, refetch } = useFetchData(fetchContact);

  useEffect(() => {
    if (id) {
      fetchAliases();
      fetchMergeHistory();
      fetchCalls();
      fetchEmailConversations();
      fetchHeatmap();
    }
  }, [id]);

  // Fetch DNC status when contact loads
  useEffect(() => {
    if (contact?.phone || contact?.email) {
      fetchDncStatus();
    }
  }, [contact?.phone, contact?.email]);

  const fetchDncStatus = async () => {
    if (!contact?.phone && !contact?.email) return;
    try {
      const params = new URLSearchParams();
      if (contact.phone) params.append('phone', contact.phone);
      if (contact.email) params.append('email', contact.email);
      const data = await api.get(`/dnc/check?${params.toString()}`);
      setDncStatus(data);
    } catch (err) {
      console.error('Failed to fetch DNC status:', err);
    }
  };

  const handleToggleDnc = async () => {
    if (!contact?.phone && !contact?.email) return;
    setDncLoading(true);
    try {
      if (dncStatus.is_blocked) {
        await api.post('/dnc/unblock', {
          phone: contact.phone,
          email: contact.email,
          reason: 'Manually unblocked from contact detail page',
        });
      } else {
        await api.post('/dnc/block', {
          phone: contact.phone,
          email: contact.email,
          reason: 'Manually blocked from contact detail page',
        });
      }
      await fetchDncStatus();
    } catch (err) {
      setError(err.message || 'Failed to update DNC status');
    } finally {
      setDncLoading(false);
    }
  };

  const fetchHeatmap = async () => {
    setLoadingHeatmap(true);
    try {
      const data = await api.getContactActivityHeatmap(id, 365);
      setHeatmapData(data);
    } catch (err) {
      console.error('Failed to fetch heatmap:', err);
    } finally {
      setLoadingHeatmap(false);
    }
  };

  const fetchCalls = async () => {
    setLoadingCalls(true);
    try {
      const data = await api.getCallsForContact(id);
      setCalls(data || []);
    } catch (err) {
      console.error('Failed to fetch calls:', err);
    } finally {
      setLoadingCalls(false);
    }
  };

  const fetchEmailConversations = async () => {
    setLoadingEmails(true);
    try {
      const data = await api.getEmailConversationsForContact(id);
      setEmailConversations(data || []);
    } catch (err) {
      console.error('Failed to fetch email conversations:', err);
    } finally {
      setLoadingEmails(false);
    }
  };

  const fetchAliases = async () => {
    setLoadingAliases(true);
    try {
      const data = await api.getContactAliases(id);
      setAliases(data || []);
    } catch (err) {
      console.error('Failed to fetch aliases:', err);
    } finally {
      setLoadingAliases(false);
    }
  };

  const fetchMergeHistory = async () => {
    setLoadingHistory(true);
    try {
      const data = await api.getMergeHistory(id);
      setMergeHistory(data || []);
    } catch (err) {
      console.error('Failed to fetch merge history:', err);
    } finally {
      setLoadingHistory(false);
    }
  };

  const selectedCallDate = selectedCall ? formatDateTimeParts(selectedCall.created_at) : null;

  const handleAddAlias = async () => {
    if (!newAlias.value.trim()) return;

    setAddingAlias(true);
    setError('');

    try {
      const alias = await api.addContactAlias(id, {
        alias_type: newAlias.alias_type,
        value: newAlias.value.trim(),
        is_primary: false,
      });
      setAliases(prev => [...prev, alias]);
      setNewAlias({ alias_type: 'email', value: '' });
    } catch (err) {
      setError(err.message || 'Failed to add alias');
    } finally {
      setAddingAlias(false);
    }
  };

  const handleRemoveAlias = async (aliasId) => {
    try {
      await api.removeContactAlias(id, aliasId);
      setAliases(prev => prev.filter(a => a.id !== aliasId));
    } catch (err) {
      setError(err.message || 'Failed to remove alias');
    }
  };

  const handleSetPrimary = async (aliasId, aliasType) => {
    try {
      await api.setPrimaryAlias(id, aliasId);
      setAliases(prev => prev.map(a => ({
        ...a,
        is_primary: a.id === aliasId ? true : (a.alias_type === aliasType ? false : a.is_primary)
      })));
      refetch();
    } catch (err) {
      setError(err.message || 'Failed to set primary alias');
    }
  };

  const handleAddTag = async (tag) => {
    const currentTags = contact.tags || [];
    if (!currentTags.includes(tag)) {
      try {
        await api.updateContact(id, { tags: [...currentTags, tag] });
        refetch();
      } catch (err) {
        setError(err.message || 'Failed to add tag');
      }
    }
  };

  const handleRemoveTag = async (tag) => {
    const currentTags = contact.tags || [];
    try {
      await api.updateContact(id, { tags: currentTags.filter(t => t !== tag) });
      refetch();
    } catch (err) {
      setError(err.message || 'Failed to remove tag');
    }
  };

  const handleEditSuccess = () => {
    setShowEditModal(false);
    refetch();
    fetchAliases();
  };

  const groupedAliases = {
    email: aliases.filter(a => a.alias_type === 'email'),
    phone: aliases.filter(a => a.alias_type === 'phone'),
    name: aliases.filter(a => a.alias_type === 'name'),
  };

  // Calculate stats from heatmap data
  const stats = heatmapData ? {
    total: heatmapData.total_interactions,
    sms: heatmapData.data.reduce((acc, d) => acc + (d.sms || 0), 0),
    call: heatmapData.data.reduce((acc, d) => acc + (d.call || 0), 0),
    email: heatmapData.data.reduce((acc, d) => acc + (d.email || 0), 0),
    chat: heatmapData.data.reduce((acc, d) => acc + (d.chat || 0), 0),
  } : { total: 0, sms: 0, call: 0, email: 0, chat: 0 };

  if (contactLoading) {
    return <LoadingState message="Loading contact..." fullPage />;
  }

  if (contactError) {
    return (
      <div className="contact-detail-page">
        <ErrorState message={contactError} onRetry={() => navigate('/contacts')} />
      </div>
    );
  }

  if (!contact) {
    return (
      <div className="contact-detail-page">
        <EmptyState icon="user" title="Contact not found" />
      </div>
    );
  }

  return (
    <div className="contact-detail-page redesigned">
      {/* Back button */}
      <button className="back-btn" onClick={() => navigate('/contacts')}>
        <ArrowLeft size={18} />
        Back to Contacts
      </button>

      {error && <div className="error-banner">{error}</div>}

      {/* Profile Header */}
      <ContactProfileHeader
        contact={contact}
        stats={stats}
        dncStatus={dncStatus}
        onEdit={() => setShowEditModal(true)}
        onToggleDnc={handleToggleDnc}
        dncLoading={dncLoading}
      />

      {/* Main content grid */}
      <div className="contact-content-grid">
        {/* Left sidebar */}
        <aside className="contact-sidebar">
          {/* Activity Heatmap */}
          {!loadingHeatmap && heatmapData && (
            <ActivityHeatmap
              data={heatmapData.data}
              startDate={heatmapData.start_date}
              endDate={heatmapData.end_date}
              total={heatmapData.total_interactions}
            />
          )}

          {/* Interest Tags */}
          <InterestTags
            tags={contact.tags || []}
            onAdd={handleAddTag}
            onRemove={handleRemoveTag}
            editable={true}
          />

          {/* Notes */}
          {contact.notes && (
            <div className="notes-section">
              <h3 className="notes-title">Notes</h3>
              <p className="notes-content">{contact.notes}</p>
            </div>
          )}
        </aside>

        {/* Main content */}
        <main className="contact-main">
          {/* Activity Feed */}
          <ActivityFeed contactId={contact.id} pageSize={10} />

          {/* Aliases */}
          <CollapsibleSection
            title="Aliases & Identifiers"
            count={aliases.length}
            icon="id"
            emptyMessage="No aliases added"
          >
            {loadingAliases ? (
              <LoadingState message="Loading aliases..." />
            ) : (
              <div className="aliases-content">
                {/* Email Aliases */}
                {groupedAliases.email.length > 0 && (
                  <div className="alias-group">
                    <h4>Emails</h4>
                    <div className="alias-list">
                      {groupedAliases.email.map(alias => (
                        <div key={alias.id} className={`alias-item ${alias.is_primary ? 'primary' : ''}`}>
                          <span className="alias-value">{alias.value}</span>
                          {alias.is_primary ? (
                            <span className="primary-badge">Primary</span>
                          ) : (
                            <div className="alias-actions">
                              <button className="btn-set-primary" onClick={() => handleSetPrimary(alias.id, 'email')}>
                                Set Primary
                              </button>
                              <button className="btn-remove-alias" onClick={() => handleRemoveAlias(alias.id)}>
                                x
                              </button>
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Phone Aliases */}
                {groupedAliases.phone.length > 0 && (
                  <div className="alias-group">
                    <h4>Phone Numbers</h4>
                    <div className="alias-list">
                      {groupedAliases.phone.map(alias => (
                        <div key={alias.id} className={`alias-item ${alias.is_primary ? 'primary' : ''}`}>
                          <span className="alias-value">{alias.value}</span>
                          {alias.is_primary ? (
                            <span className="primary-badge">Primary</span>
                          ) : (
                            <div className="alias-actions">
                              <button className="btn-set-primary" onClick={() => handleSetPrimary(alias.id, 'phone')}>
                                Set Primary
                              </button>
                              <button className="btn-remove-alias" onClick={() => handleRemoveAlias(alias.id)}>
                                x
                              </button>
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Name Aliases */}
                {groupedAliases.name.length > 0 && (
                  <div className="alias-group">
                    <h4>Name Variations</h4>
                    <div className="alias-list">
                      {groupedAliases.name.map(alias => (
                        <div key={alias.id} className={`alias-item ${alias.is_primary ? 'primary' : ''}`}>
                          <span className="alias-value">{alias.value}</span>
                          {alias.is_primary ? (
                            <span className="primary-badge">Primary</span>
                          ) : (
                            <div className="alias-actions">
                              <button className="btn-set-primary" onClick={() => handleSetPrimary(alias.id, 'name')}>
                                Set Primary
                              </button>
                              <button className="btn-remove-alias" onClick={() => handleRemoveAlias(alias.id)}>
                                x
                              </button>
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Add New Alias */}
                <div className="add-alias-section">
                  <h4>Add New Alias</h4>
                  <div className="add-alias-form">
                    <select
                      value={newAlias.alias_type}
                      onChange={(e) => setNewAlias(prev => ({ ...prev, alias_type: e.target.value }))}
                      disabled={addingAlias}
                    >
                      <option value="email">Email</option>
                      <option value="phone">Phone</option>
                      <option value="name">Name</option>
                    </select>
                    <input
                      type="text"
                      value={newAlias.value}
                      onChange={(e) => setNewAlias(prev => ({ ...prev, value: e.target.value }))}
                      placeholder={`Enter ${newAlias.alias_type}...`}
                      disabled={addingAlias}
                    />
                    <button
                      className="btn-add-alias"
                      onClick={handleAddAlias}
                      disabled={addingAlias || !newAlias.value.trim()}
                    >
                      {addingAlias ? 'Adding...' : 'Add'}
                    </button>
                  </div>
                </div>
              </div>
            )}
          </CollapsibleSection>

          {/* Merge History */}
          <CollapsibleSection
            title="Merge History"
            count={mergeHistory.length}
            icon="merge"
            emptyMessage="No contacts merged into this record"
          >
            {loadingHistory ? (
              <LoadingState message="Loading merge history..." />
            ) : (
              <div className="merge-history-list">
                {mergeHistory.map(entry => (
                  <div key={entry.id} className="merge-entry">
                    <div className="merge-entry-header">
                      <span className="merge-date">
                        {entry.merged_at ? formatDateTimeParts(entry.merged_at).date : 'Unknown date'}
                      </span>
                      {entry.merged_by && (
                        <span className="merge-by">by {entry.merged_by}</span>
                      )}
                    </div>
                    {entry.merged_contact_data && (
                      <div className="merge-contact-data">
                        <span><strong>Name:</strong> {entry.merged_contact_data.name || '-'}</span>
                        <span><strong>Email:</strong> {entry.merged_contact_data.email || '-'}</span>
                        <span><strong>Phone:</strong> {entry.merged_contact_data.phone || '-'}</span>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </CollapsibleSection>

          {/* Email Conversations */}
          <CollapsibleSection
            title="Email Conversations"
            count={emailConversations.length}
            icon="mail"
            emptyMessage="No email conversations found"
          >
            {loadingEmails ? (
              <LoadingState message="Loading emails..." />
            ) : (
              <div className="emails-list">
                {emailConversations.map((email) => (
                  <div key={email.id} className="email-item">
                    <div className="email-item-header">
                      <span className="email-subject">{email.subject || '(No subject)'}</span>
                      <span className={`email-status status-${email.status}`}>{email.status}</span>
                    </div>
                    <div className="email-item-body">
                      <span className="email-from">{email.from_email}</span>
                      <span className="email-count">{email.message_count} message{email.message_count !== 1 ? 's' : ''}</span>
                    </div>
                    <div className="email-item-footer">
                      <span className="email-date">
                        {email.last_response_at
                          ? `Last response: ${formatDateTimeParts(email.last_response_at).date}`
                          : `Created: ${formatDateTimeParts(email.created_at).date}`
                        }
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CollapsibleSection>

          {/* Voice Calls */}
          <CollapsibleSection
            title="Voice Calls"
            count={calls.length}
            icon="phone"
            emptyMessage="No voice calls found"
          >
            {loadingCalls ? (
              <LoadingState message="Loading calls..." />
            ) : (
              <div className="calls-list">
                {calls.map((call) => {
                  const { date, time } = formatDateTimeParts(call.created_at);
                  return (
                    <div
                      key={call.id}
                      className="call-item"
                      onClick={() => setSelectedCall(call)}
                    >
                      <div className="call-item-header">
                        <span className="call-date">{date}</span>
                        <span className="call-time">{time}</span>
                      </div>
                      <div className="call-item-body">
                        <span className="call-duration">{formatDuration(call.duration)}</span>
                        {call.intent && (
                          <span className="call-intent">{INTENT_LABELS[call.intent] || call.intent}</span>
                        )}
                      </div>
                      {call.summary_preview && (
                        <div className="call-summary-preview">{call.summary_preview}</div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </CollapsibleSection>
        </main>
      </div>

      {/* Call Detail Modal */}
      {selectedCall && (
        <div className="call-detail-modal-overlay" onClick={() => setSelectedCall(null)}>
          <div className="call-detail-modal" onClick={(e) => e.stopPropagation()}>
            <div className="call-detail-modal-header">
              <h3>Call Details</h3>
              <button className="btn-close" onClick={() => setSelectedCall(null)}>x</button>
            </div>
            <div className="call-detail-modal-body">
              <div className="call-detail-row">
                <span className="label">Date:</span>
                <span className="value">
                  {selectedCallDate
                    ? `${selectedCallDate.date} ${selectedCallDate.time} ${selectedCallDate.tzAbbr}`.trim()
                    : '-'}
                </span>
              </div>
              <div className="call-detail-row">
                <span className="label">Duration:</span>
                <span className="value">{formatDuration(selectedCall.duration)}</span>
              </div>
              <div className="call-detail-row">
                <span className="label">Status:</span>
                <span className="value">{selectedCall.status}</span>
              </div>
              {selectedCall.intent && (
                <div className="call-detail-row">
                  <span className="label">Intent:</span>
                  <span className="value">{INTENT_LABELS[selectedCall.intent] || selectedCall.intent}</span>
                </div>
              )}
              {selectedCall.outcome && (
                <div className="call-detail-row">
                  <span className="label">Outcome:</span>
                  <span className="value">{selectedCall.outcome.replace('_', ' ')}</span>
                </div>
              )}
              {selectedCall.summary_preview && (
                <div className="call-detail-summary">
                  <span className="label">Summary:</span>
                  <p>{selectedCall.summary_preview}</p>
                </div>
              )}
              {selectedCall.recording_url && (
                <div className="call-detail-recording">
                  <a
                    href={selectedCall.recording_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="btn-listen"
                  >
                    Listen to Recording
                  </a>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Edit Modal */}
      {showEditModal && (
        <EditContactModal
          contact={contact}
          onSuccess={handleEditSuccess}
          onCancel={() => setShowEditModal(false)}
        />
      )}
    </div>
  );
}
