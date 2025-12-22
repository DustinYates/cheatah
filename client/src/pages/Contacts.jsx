import { useState, useCallback } from 'react';
import { api } from '../api/client';
import { useFetchData } from '../hooks/useFetchData';
import { useAuth } from '../context/AuthContext';
import { LoadingState, EmptyState, ErrorState } from '../components/ui';
import ChatModal from '../components/ChatModal';
import EditContactModal from '../components/EditContactModal';
import MergeContactsModal from '../components/MergeContactsModal';
import './Contacts.css';

export default function Contacts() {
  const { user, selectedTenantId } = useAuth();
  const [search, setSearch] = useState('');
  const [selectedContact, setSelectedContact] = useState(null);
  const [editingContact, setEditingContact] = useState(null);
  const [selectedForMerge, setSelectedForMerge] = useState([]);
  const [showMergeModal, setShowMergeModal] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState(null);
  const [deleting, setDeleting] = useState(false);

  const fetchContacts = useCallback(async () => {
    try {
      const data = await api.getContacts();
      return Array.isArray(data) ? data : data.contacts || [];
    } catch (err) {
      if (err.message?.includes('Not Found') || err.message?.includes('not found')) {
        return [];
      }
      throw err;
    }
  }, []);

  const { data: contacts, loading, error, refetch } = useFetchData(fetchContacts, { defaultValue: [] });

  const needsTenant = user?.is_global_admin && !selectedTenantId;

  const filteredContacts = contacts.filter(contact => 
    (contact.name || '').toLowerCase().includes(search.toLowerCase()) ||
    (contact.phone_number || '').includes(search) ||
    (contact.email || '').toLowerCase().includes(search.toLowerCase())
  );

  const handleViewChat = (e, contact) => {
    e.stopPropagation();
    setSelectedContact(contact);
  };

  const handleEdit = (e, contact) => {
    e.stopPropagation();
    setEditingContact(contact);
  };

  const handleEditSuccess = () => {
    setEditingContact(null);
    refetch();
  };

  const handleDelete = async (contact) => {
    setDeleting(true);
    try {
      await api.deleteContact(contact.id);
      setDeleteConfirm(null);
      refetch();
    } catch (err) {
      alert(err.message || 'Failed to delete contact');
    } finally {
      setDeleting(false);
    }
  };

  const toggleMergeSelection = (contact) => {
    setSelectedForMerge(prev => {
      const isSelected = prev.some(c => c.id === contact.id);
      if (isSelected) {
        return prev.filter(c => c.id !== contact.id);
      }
      return [...prev, contact];
    });
  };

  const handleMergeSuccess = () => {
    setShowMergeModal(false);
    setSelectedForMerge([]);
    refetch();
  };

  const cancelMergeSelection = () => {
    setSelectedForMerge([]);
  };

  if (needsTenant) {
    return (
      <div className="contacts-page">
        <EmptyState
          icon="👥"
          title="Select a tenant to view contacts"
          description="Please select a tenant from the dropdown above to view their contacts."
        />
      </div>
    );
  }

  if (loading) {
    return <LoadingState message="Loading contacts..." fullPage />;
  }

  if (error) {
    if (error.includes('Tenant context required') || error.includes('Tenant context')) {
      return (
        <div className="contacts-page">
          <EmptyState
            icon="👥"
            title="Select a tenant to view contacts"
            description="Please select a tenant from the dropdown above to view their contacts."
          />
        </div>
      );
    }
    if (error.includes('Not Found') || error.includes('not found')) {
      return (
        <div className="contacts-page">
          <div className="page-header">
            <h1>Contacts</h1>
            <div className="search-box">
              <input
                type="text"
                placeholder="Search contacts..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                disabled
              />
            </div>
          </div>
          <EmptyState 
            icon="👥"
            title="No verified contacts yet"
            description="Contacts will appear here once they opt in through the chatbot."
          />
        </div>
      );
    }
    return (
      <div className="contacts-page">
        <ErrorState message={error} onRetry={refetch} />
      </div>
    );
  }

  return (
    <div className="contacts-page">
      <div className="page-header">
        <h1>Contacts</h1>
        <div className="header-actions">
          <div className="search-box">
            <input
              type="text"
              placeholder="Search contacts..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
        </div>
      </div>

      {/* Merge Selection Bar */}
      {selectedForMerge.length > 0 && (
        <div className="merge-selection-bar">
          <span className="merge-count">
            {selectedForMerge.length} contact{selectedForMerge.length > 1 ? 's' : ''} selected
          </span>
          <div className="merge-actions">
            <button 
              className="btn-cancel-merge"
              onClick={cancelMergeSelection}
            >
              Cancel
            </button>
            <button 
              className="btn-merge"
              onClick={() => setShowMergeModal(true)}
              disabled={selectedForMerge.length < 2}
            >
              Merge Selected
            </button>
          </div>
        </div>
      )}

      {contacts.length === 0 ? (
        <EmptyState 
          icon="👥"
          title="No verified contacts yet"
          description="Contacts will appear here once they opt in through the chatbot."
        />
      ) : (
        <div className="contacts-table-container">
          <table className="contacts-table">
            <thead>
              <tr>
                <th className="th-checkbox">
                  <span className="merge-hint" title="Select contacts to merge">
                    Merge
                  </span>
                </th>
                <th>Name</th>
                <th>Phone</th>
                <th>Email</th>
                <th>Status</th>
                <th>Added</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredContacts.map((contact) => {
                const isSelectedForMerge = selectedForMerge.some(c => c.id === contact.id);
                return (
                  <tr key={contact.id} className={isSelectedForMerge ? 'selected-for-merge' : ''}>
                    <td className="td-checkbox">
                      <input
                        type="checkbox"
                        checked={isSelectedForMerge}
                        onChange={() => toggleMergeSelection(contact)}
                        title="Select for merge"
                      />
                    </td>
                    <td>
                      <div className="contact-name">
                        <div className="avatar">
                          {(contact.name || 'U')[0].toUpperCase()}
                        </div>
                        {contact.name || 'Unknown'}
                      </div>
                    </td>
                    <td>{contact.phone_number || '-'}</td>
                    <td>{contact.email || '-'}</td>
                    <td>
                      <span className={`status ${contact.opt_in_status || 'verified'}`}>
                        {contact.opt_in_status || 'Verified'}
                      </span>
                    </td>
                    <td>{new Date(contact.created_at).toLocaleDateString()}</td>
                    <td>
                      <div className="action-buttons">
                        <button 
                          className="btn-action btn-chat"
                          onClick={(e) => handleViewChat(e, contact)}
                          title="View conversation history"
                        >
                          💬
                        </button>
                        <button 
                          className="btn-action btn-edit"
                          onClick={(e) => handleEdit(e, contact)}
                          title="Edit contact"
                        >
                          ✏️
                        </button>
                        <button 
                          className="btn-action btn-delete"
                          onClick={(e) => {
                            e.stopPropagation();
                            setDeleteConfirm(contact);
                          }}
                          title="Delete contact"
                        >
                          🗑️
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          
          {filteredContacts.length === 0 && search && (
            <EmptyState 
              icon="🔍"
              title="No matches found"
              description={`No contacts match "${search}". Try a different search term.`}
            />
          )}
        </div>
      )}

      {/* Chat Modal */}
      {selectedContact && (
        <ChatModal 
          contact={selectedContact} 
          onClose={() => setSelectedContact(null)} 
        />
      )}

      {/* Edit Modal */}
      {editingContact && (
        <EditContactModal
          contact={editingContact}
          onSuccess={handleEditSuccess}
          onCancel={() => setEditingContact(null)}
        />
      )}

      {/* Merge Modal */}
      {showMergeModal && selectedForMerge.length >= 2 && (
        <MergeContactsModal
          contacts={selectedForMerge}
          onSuccess={handleMergeSuccess}
          onCancel={() => setShowMergeModal(false)}
        />
      )}

      {/* Delete Confirmation Modal */}
      {deleteConfirm && (
        <div className="modal-overlay" onClick={() => !deleting && setDeleteConfirm(null)}>
          <div className="modal delete-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Delete Contact</h2>
              <button 
                className="close-btn" 
                onClick={() => setDeleteConfirm(null)}
                disabled={deleting}
              >
                ×
              </button>
            </div>
            <div className="modal-body">
              <p>Are you sure you want to permanently delete this contact?</p>
              <div className="delete-contact-info">
                <strong>{deleteConfirm.name || 'Unknown'}</strong>
                <span>{deleteConfirm.email || deleteConfirm.phone_number || 'No contact info'}</span>
              </div>
              <p className="warning-text">
                This action cannot be undone. All associated data will be permanently removed.
              </p>
            </div>
            <div className="modal-footer">
              <button 
                className="btn-cancel" 
                onClick={() => setDeleteConfirm(null)}
                disabled={deleting}
              >
                Cancel
              </button>
              <button 
                className="btn-delete-confirm"
                onClick={() => handleDelete(deleteConfirm)}
                disabled={deleting}
              >
                {deleting ? 'Deleting...' : 'Delete Contact'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
