import { useState, useCallback, useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import { MessageSquare, Pencil, Trash2, Users, Search } from 'lucide-react';
import { api } from '../api/client';
import { useFetchData } from '../hooks/useFetchData';
import { useAuth } from '../context/AuthContext';
import { LoadingState, EmptyState, ErrorState } from '../components/ui';
import ChatModal from '../components/ChatModal';
import EditContactModal from '../components/EditContactModal';
import MergeContactsModal from '../components/MergeContactsModal';
import { formatDateTimeParts } from '../utils/dateFormat';
import './Contacts.css';

export default function Contacts() {
  const { user, selectedTenantId } = useAuth();
  const location = useLocation();
  const [search, setSearch] = useState('');
  const [selectedContact, setSelectedContact] = useState(null);
  const [editingContact, setEditingContact] = useState(null);
  const [selectedForMerge, setSelectedForMerge] = useState([]);
  const [showMergeModal, setShowMergeModal] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState(null);
  const [deleting, setDeleting] = useState(false);
  const [typeFilter, setTypeFilter] = useState(''); // '', 'lead', 'customer'
  const [sortBy, setSortBy] = useState('created_at');
  const [sortDir, setSortDir] = useState('desc');
  const [showBulkDeleteConfirm, setShowBulkDeleteConfirm] = useState(false);
  const [bulkDeleting, setBulkDeleting] = useState(false);

  const fetchContacts = useCallback(async () => {
    try {
      const data = await api.getContacts();
      if (Array.isArray(data)) {
        return data;
      }
      if (data?.items) {
        return data.items;
      }
      return data.contacts || [];
    } catch (err) {
      if (err.message?.includes('Not Found') || err.message?.includes('not found')) {
        return [];
      }
      throw err;
    }
  }, []);

  const { data: contacts, loading, error, refetch } = useFetchData(fetchContacts, { defaultValue: [], deps: [selectedTenantId] });

  // Refetch contacts when navigating to this page (e.g., after verifying a lead)
  // Use location.key which changes on each navigation, not pathname
  useEffect(() => {
    // Only refetch if we have a tenant context (to avoid 403 errors)
    if (selectedTenantId || (user && !user.is_global_admin)) {
      refetch();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.key]); // Only trigger on actual navigation, not on refetch changes

  const needsTenant = user?.is_global_admin && !selectedTenantId;

  const filteredContacts = contacts
    .filter(contact => {
      // Search filter
      const matchesSearch = !search ||
        (contact.name || '').toLowerCase().includes(search.toLowerCase()) ||
        (contact.phone || '').includes(search) ||
        (contact.email || '').toLowerCase().includes(search.toLowerCase());

      // Type filter
      const isCustomer = !!contact.customer_name;
      const matchesType = !typeFilter ||
        (typeFilter === 'customer' && isCustomer) ||
        (typeFilter === 'lead' && !isCustomer);

      return matchesSearch && matchesType;
    })
    .sort((a, b) => {
      let comparison = 0;
      switch (sortBy) {
        case 'name':
          comparison = (a.name || '').localeCompare(b.name || '');
          break;
        case 'last_contacted':
          comparison = new Date(a.last_contacted || 0) - new Date(b.last_contacted || 0);
          break;
        case 'type':
          comparison = (!!a.customer_name ? 1 : 0) - (!!b.customer_name ? 1 : 0);
          break;
        default: // created_at
          comparison = new Date(a.created_at || 0) - new Date(b.created_at || 0);
      }
      return sortDir === 'desc' ? -comparison : comparison;
    });

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

  const handleSort = (column) => {
    if (sortBy === column) {
      setSortDir(prev => prev === 'asc' ? 'desc' : 'asc');
    } else {
      setSortBy(column);
      setSortDir('desc');
    }
  };

  const clearFilters = () => {
    setTypeFilter('');
    setSearch('');
  };

  const handleSelectAll = () => {
    if (selectedForMerge.length === filteredContacts.length) {
      setSelectedForMerge([]);
    } else {
      setSelectedForMerge([...filteredContacts]);
    }
  };

  const handleBulkDelete = async () => {
    setBulkDeleting(true);
    try {
      // Delete contacts sequentially using existing API
      for (const contact of selectedForMerge) {
        await api.deleteContact(contact.id);
      }
      setShowBulkDeleteConfirm(false);
      setSelectedForMerge([]);
      refetch();
    } catch (err) {
      alert(err.message || 'Failed to delete some contacts');
    } finally {
      setBulkDeleting(false);
    }
  };

  if (needsTenant) {
    return (
      <div className="contacts-page">
        <EmptyState
          icon={<Users size={32} strokeWidth={1.5} />}
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
            icon={<Users size={32} strokeWidth={1.5} />}
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
              <Search size={14} className="search-icon" />
              <input
                type="text"
                placeholder="Search contacts..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                disabled
                aria-label="Search contacts"
              />
            </div>
          </div>
          <EmptyState
            icon={<Users size={32} strokeWidth={1.5} />}
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
            <Search size={14} className="search-icon" />
            <input
              type="text"
              placeholder="Search contacts..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              aria-label="Search contacts"
            />
          </div>
        </div>
      </div>

      {/* Filter Bar */}
      <div className="contacts-filters">
        <select
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value)}
          className="filter-select"
          aria-label="Filter by type"
        >
          <option value="">All Types</option>
          <option value="lead">Leads</option>
          <option value="customer">Customers</option>
        </select>

        <select
          value={sortBy}
          onChange={(e) => setSortBy(e.target.value)}
          className="filter-select"
          aria-label="Sort by"
        >
          <option value="created_at">Sort: Added</option>
          <option value="name">Sort: Name</option>
          <option value="last_contacted">Sort: Last Contacted</option>
          <option value="type">Sort: Type</option>
        </select>

        <button
          className={`sort-direction-btn ${sortDir}`}
          onClick={() => setSortDir(prev => prev === 'asc' ? 'desc' : 'asc')}
          title={sortDir === 'asc' ? 'Ascending' : 'Descending'}
          aria-label={sortDir === 'asc' ? 'Sort ascending' : 'Sort descending'}
        >
          {sortDir === 'asc' ? '↑' : '↓'}
        </button>

        {(typeFilter || search) && (
          <button className="btn-clear-filters" onClick={clearFilters}>
            Clear
          </button>
        )}

        <span className="filter-count">
          {filteredContacts.length} of {contacts.length}
        </span>
      </div>

      {/* Bulk Actions Bar */}
      {selectedForMerge.length > 0 && (
        <div className="bulk-action-bar">
          <span className="bulk-count">
            {selectedForMerge.length} contact{selectedForMerge.length > 1 ? 's' : ''} selected
          </span>
          <div className="bulk-actions">
            <button
              className="btn-bulk-action"
              onClick={cancelMergeSelection}
            >
              Clear Selection
            </button>
            <button
              className="btn-bulk-action btn-merge"
              onClick={() => setShowMergeModal(true)}
              disabled={selectedForMerge.length < 2}
              title={selectedForMerge.length < 2 ? 'Select at least 2 contacts to merge' : ''}
            >
              <Users size={14} />
              Merge
            </button>
            <button
              className="btn-bulk-action btn-delete"
              onClick={() => setShowBulkDeleteConfirm(true)}
            >
              <Trash2 size={14} />
              Delete
            </button>
          </div>
        </div>
      )}

      {contacts.length === 0 ? (
        <EmptyState
          icon={<Users size={32} strokeWidth={1.5} />}
          title="No verified contacts yet"
          description="Contacts will appear here once they opt in through the chatbot."
        />
      ) : (
        <div className="contacts-table-container">
          <table className="contacts-table">
            <thead>
              <tr>
                <th className="th-checkbox">
                  <input
                    type="checkbox"
                    checked={filteredContacts.length > 0 && selectedForMerge.length === filteredContacts.length}
                    onChange={handleSelectAll}
                    title="Select all contacts"
                    aria-label="Select all contacts"
                  />
                </th>
                <th
                  className={`col-name sortable ${sortBy === 'name' ? 'sorted' : ''}`}
                  onClick={() => handleSort('name')}
                >
                  Name {sortBy === 'name' && (sortDir === 'asc' ? '↑' : '↓')}
                </th>
                <th
                  className={`col-type sortable ${sortBy === 'type' ? 'sorted' : ''}`}
                  onClick={() => handleSort('type')}
                >
                  Type {sortBy === 'type' && (sortDir === 'asc' ? '↑' : '↓')}
                </th>
                <th className="col-phone">Phone</th>
                <th className="col-email">Email</th>
                <th
                  className={`col-added sortable ${sortBy === 'created_at' ? 'sorted' : ''}`}
                  onClick={() => handleSort('created_at')}
                >
                  Added {sortBy === 'created_at' && (sortDir === 'asc' ? '↑' : '↓')}
                </th>
                <th className="col-first-contacted">First Contacted</th>
                <th
                  className={`col-last-contacted sortable ${sortBy === 'last_contacted' ? 'sorted' : ''}`}
                  onClick={() => handleSort('last_contacted')}
                >
                  Last Contacted {sortBy === 'last_contacted' && (sortDir === 'asc' ? '↑' : '↓')}
                </th>
                <th className="col-actions">Actions</th>
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
                    <td className="col-name">
                      <div className="contact-name">
                        <div className="avatar">
                          {(contact.name || 'U')[0].toUpperCase()}
                        </div>
                        <span className="contact-name-text">
                          {contact.name || 'Unknown'}
                        </span>
                      </div>
                    </td>
                    <td className="col-type">
                      <span
                        className={`type-badge ${contact.customer_name ? 'type-customer' : 'type-lead'}`}
                        title={contact.customer_name ? `Matched: ${contact.customer_name}` : 'No Jackrabbit match'}
                      >
                        {contact.customer_name ? 'Customer' : 'Lead'}
                      </span>
                    </td>
                    <td className="col-phone">
                      <span className="contact-text contact-phone" title={contact.phone || '-'}>
                        {contact.phone || '-'}
                      </span>
                    </td>
                    <td className="col-email">
                      <span className="contact-text contact-email" title={contact.email || '-'}>
                        {contact.email || '-'}
                      </span>
                    </td>
                    <td className="col-added">
                      <span className="contact-date">
                        {formatDateTimeParts(contact.created_at).date}
                      </span>
                    </td>
                    <td className="col-first-contacted">
                      {contact.first_contacted ? (
                        <span className="contact-date" title={formatDateTimeParts(contact.first_contacted).time}>
                          {formatDateTimeParts(contact.first_contacted).date}
                        </span>
                      ) : (
                        <span className="contact-text-muted">-</span>
                      )}
                    </td>
                    <td className="col-last-contacted">
                      {contact.last_contacted ? (
                        <span className="contact-date" title={formatDateTimeParts(contact.last_contacted).time}>
                          {formatDateTimeParts(contact.last_contacted).date}
                        </span>
                      ) : (
                        <span className="contact-text-muted">-</span>
                      )}
                    </td>
                    <td className="col-actions">
                      <div className="action-buttons">
                        <button
                          className="btn-action btn-chat"
                          onClick={(e) => handleViewChat(e, contact)}
                          title="View conversation history"
                          aria-label="View conversation history"
                        >
                          <MessageSquare size={14} />
                        </button>
                        <button
                          className="btn-action btn-edit"
                          onClick={(e) => handleEdit(e, contact)}
                          title="Edit contact"
                          aria-label="Edit contact"
                        >
                          <Pencil size={14} />
                        </button>
                        <button
                          className="btn-action btn-delete"
                          onClick={(e) => {
                            e.stopPropagation();
                            setDeleteConfirm(contact);
                          }}
                          title="Delete contact"
                          aria-label="Delete contact"
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                      <details className="action-menu">
                        <summary
                          className="action-menu-trigger"
                          onClick={(e) => e.stopPropagation()}
                          aria-label="Open contact actions"
                          title="Open actions"
                        >
                          ...
                        </summary>
                        <div className="action-menu-list">
                          <button
                            type="button"
                            onClick={(e) => {
                              handleViewChat(e, contact);
                              e.currentTarget.closest('details')?.removeAttribute('open');
                            }}
                          >
                            <MessageSquare size={14} />
                            <span>Message</span>
                          </button>
                          <button
                            type="button"
                            onClick={(e) => {
                              handleEdit(e, contact);
                              e.currentTarget.closest('details')?.removeAttribute('open');
                            }}
                          >
                            <Pencil size={14} />
                            <span>Edit</span>
                          </button>
                          <button
                            type="button"
                            className="destructive"
                            onClick={(e) => {
                              e.stopPropagation();
                              setDeleteConfirm(contact);
                              e.currentTarget.closest('details')?.removeAttribute('open');
                            }}
                          >
                            <Trash2 size={14} />
                            <span>Delete</span>
                          </button>
                        </div>
                      </details>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          
          {filteredContacts.length === 0 && search && (
            <EmptyState
              icon={<Search size={32} strokeWidth={1.5} />}
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
                <span>{deleteConfirm.email || deleteConfirm.phone || 'No contact info'}</span>
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

      {/* Bulk Delete Confirmation Modal */}
      {showBulkDeleteConfirm && (
        <div className="modal-overlay" onClick={() => !bulkDeleting && setShowBulkDeleteConfirm(false)}>
          <div className="modal delete-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Delete {selectedForMerge.length} Contacts</h2>
              <button
                className="close-btn"
                onClick={() => setShowBulkDeleteConfirm(false)}
                disabled={bulkDeleting}
              >
                ×
              </button>
            </div>
            <div className="modal-body">
              <p>Are you sure you want to permanently delete {selectedForMerge.length} contact{selectedForMerge.length > 1 ? 's' : ''}?</p>
              <div className="bulk-delete-list">
                {selectedForMerge.slice(0, 5).map(contact => (
                  <div key={contact.id} className="bulk-delete-item">
                    {contact.name || 'Unknown'} — {contact.email || contact.phone || 'No contact info'}
                  </div>
                ))}
                {selectedForMerge.length > 5 && (
                  <div className="bulk-delete-more">
                    ...and {selectedForMerge.length - 5} more
                  </div>
                )}
              </div>
              <p className="warning-text">
                This action cannot be undone. All associated data will be permanently removed.
              </p>
            </div>
            <div className="modal-footer">
              <button
                className="btn-cancel"
                onClick={() => setShowBulkDeleteConfirm(false)}
                disabled={bulkDeleting}
              >
                Cancel
              </button>
              <button
                className="btn-delete-confirm"
                onClick={handleBulkDelete}
                disabled={bulkDeleting}
              >
                {bulkDeleting ? 'Deleting...' : `Delete ${selectedForMerge.length} Contacts`}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
