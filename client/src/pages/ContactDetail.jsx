import { useState, useCallback, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { api } from '../api/client';
import { useFetchData } from '../hooks/useFetchData';
import { LoadingState, EmptyState, ErrorState } from '../components/ui';
import EditContactModal from '../components/EditContactModal';
import './ContactDetail.css';

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

  const fetchContact = useCallback(async () => {
    const data = await api.getContact(id, true);
    return data;
  }, [id]);

  const fetchConversation = useCallback(async () => {
    try {
      const data = await api.getContactConversation(id);
      return data;
    } catch (err) {
      return null;
    }
  }, [id]);

  const { data: contact, loading: contactLoading, error: contactError, refetch } = useFetchData(fetchContact);
  const { data: conversation, loading: convLoading } = useFetchData(fetchConversation);

  useEffect(() => {
    if (id) {
      fetchAliases();
      fetchMergeHistory();
    }
  }, [id]);

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
        <EmptyState icon="👤" title="Contact not found" />
      </div>
    );
  }

  return (
    <div className="contact-detail-page">
      <div className="page-header">
        <button className="back-btn" onClick={() => navigate('/contacts')}>
          ← Back to Contacts
        </button>
        <div className="header-actions">
          <button className="btn-edit" onClick={() => setShowEditModal(true)}>
            ✏️ Edit Contact
          </button>
        </div>
      </div>

      {error && <div className="error-banner">{error}</div>}

      <div className="contact-detail-grid">
        {/* Contact Info Card */}
        <div className="contact-info-card">
          <div className="contact-avatar-large">
            {(contact.name || 'U')[0].toUpperCase()}
          </div>
          <h2>{contact.name || 'Unknown'}</h2>
          <div className="contact-details">
            <div className="detail-row">
              <span className="label">Email:</span>
              <span className="value">{contact.email || '-'}</span>
            </div>
            <div className="detail-row">
              <span className="label">Phone:</span>
              <span className="value">{contact.phone_number || '-'}</span>
            </div>
            <div className="detail-row">
              <span className="label">Source:</span>
              <span className="value">{contact.source || 'web_chat'}</span>
            </div>
            <div className="detail-row">
              <span className="label">Added:</span>
              <span className="value">{new Date(contact.created_at).toLocaleDateString()}</span>
            </div>
          </div>
        </div>

        {/* Aliases Card */}
        <div className="aliases-card">
          <h3>Aliases & Alternate Identifiers</h3>
          <p className="card-description">
            Manage alternate emails, phone numbers, and name spellings for this contact.
          </p>

          {loadingAliases ? (
            <LoadingState message="Loading aliases..." />
          ) : (
            <div className="aliases-content">
              {/* Email Aliases */}
              <div className="alias-group">
                <h4>Emails</h4>
                {groupedAliases.email.length > 0 ? (
                  <div className="alias-list">
                    {groupedAliases.email.map(alias => (
                      <div key={alias.id} className={`alias-item ${alias.is_primary ? 'primary' : ''}`}>
                        <span className="alias-value">{alias.value}</span>
                        {alias.is_primary ? (
                          <span className="primary-badge">Primary</span>
                        ) : (
                          <div className="alias-actions">
                            <button
                              className="btn-set-primary"
                              onClick={() => handleSetPrimary(alias.id, 'email')}
                            >
                              Set Primary
                            </button>
                            <button
                              className="btn-remove-alias"
                              onClick={() => handleRemoveAlias(alias.id)}
                            >
                              ×
                            </button>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="no-aliases">No email aliases</p>
                )}
              </div>

              {/* Phone Aliases */}
              <div className="alias-group">
                <h4>Phone Numbers</h4>
                {groupedAliases.phone.length > 0 ? (
                  <div className="alias-list">
                    {groupedAliases.phone.map(alias => (
                      <div key={alias.id} className={`alias-item ${alias.is_primary ? 'primary' : ''}`}>
                        <span className="alias-value">{alias.value}</span>
                        {alias.is_primary ? (
                          <span className="primary-badge">Primary</span>
                        ) : (
                          <div className="alias-actions">
                            <button
                              className="btn-set-primary"
                              onClick={() => handleSetPrimary(alias.id, 'phone')}
                            >
                              Set Primary
                            </button>
                            <button
                              className="btn-remove-alias"
                              onClick={() => handleRemoveAlias(alias.id)}
                            >
                              ×
                            </button>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="no-aliases">No phone aliases</p>
                )}
              </div>

              {/* Name Aliases */}
              <div className="alias-group">
                <h4>Name Variations</h4>
                {groupedAliases.name.length > 0 ? (
                  <div className="alias-list">
                    {groupedAliases.name.map(alias => (
                      <div key={alias.id} className={`alias-item ${alias.is_primary ? 'primary' : ''}`}>
                        <span className="alias-value">{alias.value}</span>
                        {alias.is_primary ? (
                          <span className="primary-badge">Primary</span>
                        ) : (
                          <div className="alias-actions">
                            <button
                              className="btn-set-primary"
                              onClick={() => handleSetPrimary(alias.id, 'name')}
                            >
                              Set Primary
                            </button>
                            <button
                              className="btn-remove-alias"
                              onClick={() => handleRemoveAlias(alias.id)}
                            >
                              ×
                            </button>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="no-aliases">No name variations</p>
                )}
              </div>

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
        </div>

        {/* Merge History Card */}
        {mergeHistory.length > 0 && (
          <div className="merge-history-card">
            <h3>Merge History</h3>
            <p className="card-description">
              Contacts that have been merged into this record.
            </p>
            <div className="merge-history-list">
              {mergeHistory.map(entry => (
                <div key={entry.id} className="merge-entry">
                  <div className="merge-entry-header">
                    <span className="merge-date">
                      {entry.merged_at ? new Date(entry.merged_at).toLocaleDateString() : 'Unknown date'}
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
          </div>
        )}

        {/* Conversation Card */}
        <div className="conversation-card">
          <h3>Conversation History</h3>
          {convLoading ? (
            <LoadingState message="Loading conversation..." />
          ) : conversation && conversation.messages?.length > 0 ? (
            <div className="messages-list">
              {conversation.messages.map((msg, idx) => (
                <div key={idx} className={`message ${msg.role}`}>
                  <div className="message-role">{msg.role === 'user' ? '👤 User' : '🤖 Bot'}</div>
                  <div className="message-content">{msg.content}</div>
                  <div className="message-time">
                    {new Date(msg.created_at).toLocaleString()}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <EmptyState 
              icon="💬" 
              title="No conversation history" 
              description="No chat messages found for this contact."
            />
          )}
        </div>
      </div>

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
