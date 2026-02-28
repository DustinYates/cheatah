import { useState, useCallback, useEffect, useMemo } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Pencil, Trash2, Users, Search, Clock, ChevronLeft, ChevronRight } from 'lucide-react';
import { api } from '../api/client';
import { useFetchData } from '../hooks/useFetchData';
import { useAuth } from '../context/AuthContext';
import { LoadingState, EmptyState, ErrorState } from '../components/ui';
import ContactHistoryModal from '../components/ContactHistoryModal';
import EditContactModal from '../components/EditContactModal';
import MergeContactsModal from '../components/MergeContactsModal';
import { formatDateTimeParts } from '../utils/dateFormat';
import { formatPhone } from '../utils/formatPhone';
import './Connections.css';

const PIPELINE_STAGE_LABELS = {
  new_lead: 'New Lead',
  contacted: 'Contacted',
  interested: 'Interested',
  registered: 'Registered',
  enrolled: 'Enrolled',
};

const CUSTOMER_STATUS_LABELS = {
  active: 'Active',
  inactive: 'Inactive',
  suspended: 'Suspended',
};

// Format name - detect phone numbers masquerading as names
function formatName(name) {
  if (!name) return null;
  const trimmed = name.trim();
  if (/^caller\s/i.test(trimmed)) return null;
  if (/^\+?\d{7,}$/.test(trimmed)) return null;
  return trimmed;
}

export default function Connections() {
  const { user, selectedTenantId } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [search, setSearch] = useState('');
  const [selectedContact, setSelectedContact] = useState(null);
  const [editingContact, setEditingContact] = useState(null);
  const [selectedForMerge, setSelectedForMerge] = useState([]);
  const [showMergeModal, setShowMergeModal] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState(null);
  const [deleting, setDeleting] = useState(false);
  const [typeFilter, setTypeFilter] = useState('');
  const [stageFilter, setStageFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [sortBy, setSortBy] = useState('created_at');
  const [sortDir, setSortDir] = useState('desc');
  const [showBulkDeleteConfirm, setShowBulkDeleteConfirm] = useState(false);
  const [bulkDeleting, setBulkDeleting] = useState(false);
  const [page, setPage] = useState(1);
  const pageSize = 50;

  const fetchConnections = useCallback(async () => {
    try {
      const data = await api.getConnections({ page_size: 10000 });
      if (Array.isArray(data)) return data;
      if (data?.items) return data.items;
      return [];
    } catch (err) {
      if (err.message?.includes('Not Found') || err.message?.includes('not found')) {
        return [];
      }
      throw err;
    }
  }, []);

  const fetchStats = useCallback(async () => {
    try {
      return await api.getConnectionStats();
    } catch {
      return null;
    }
  }, []);

  const { data: connections, loading, error, refetch } = useFetchData(fetchConnections, { defaultValue: [], deps: [selectedTenantId] });
  const { data: stats, refetch: refetchStats } = useFetchData(fetchStats, { defaultValue: null, deps: [selectedTenantId] });

  useEffect(() => {
    if (selectedTenantId || (user && !user.is_global_admin)) {
      refetch();
      refetchStats();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.key]);

  const needsTenant = user?.is_global_admin && !selectedTenantId;

  const filteredConnections = connections
    .filter(conn => {
      const matchesSearch = !search ||
        (conn.name || '').toLowerCase().includes(search.toLowerCase()) ||
        (conn.phone || '').includes(search) ||
        (conn.email || '').toLowerCase().includes(search.toLowerCase()) ||
        (conn.customer_name || '').toLowerCase().includes(search.toLowerCase());

      const matchesType = !typeFilter ||
        (typeFilter === 'contact' && conn.record_type === 'contact') ||
        (typeFilter === 'customer' && conn.record_type === 'customer') ||
        (typeFilter === 'both' && conn.record_type === 'both');

      const matchesStage = !stageFilter || conn.pipeline_stage === stageFilter;
      const matchesStatus = !statusFilter || conn.customer_status === statusFilter;

      return matchesSearch && matchesType && matchesStage && matchesStatus;
    })
    .sort((a, b) => {
      let comparison = 0;
      switch (sortBy) {
        case 'name':
          comparison = (a.name || a.customer_name || '').localeCompare(b.name || b.customer_name || '');
          break;
        case 'last_contacted':
          comparison = new Date(a.last_contacted || 0) - new Date(b.last_contacted || 0);
          break;
        case 'pipeline_stage':
          comparison = (a.pipeline_stage || '').localeCompare(b.pipeline_stage || '');
          break;
        default: // created_at
          comparison = new Date(a.created_at || 0) - new Date(b.created_at || 0);
      }
      return sortDir === 'desc' ? -comparison : comparison;
    });

  useEffect(() => {
    setPage(1);
  }, [search, typeFilter, stageFilter, statusFilter, sortBy, sortDir]);

  const totalPages = Math.max(1, Math.ceil(filteredConnections.length / pageSize));
  const paginatedConnections = useMemo(() => {
    const start = (page - 1) * pageSize;
    return filteredConnections.slice(start, start + pageSize);
  }, [filteredConnections, page, pageSize]);

  const handleRowClick = (conn) => {
    if (conn.contact_id) {
      navigate(`/connections/${conn.contact_id}`);
    } else if (conn.customer_id) {
      navigate(`/connections/customer/${conn.customer_id}`);
    }
  };

  const handleViewChat = (e, conn) => {
    e.stopPropagation();
    if (conn.contact_id) {
      setSelectedContact(conn);
    }
  };

  const handleEdit = (e, conn) => {
    e.stopPropagation();
    if (conn.contact_id) {
      setEditingContact(conn);
    }
  };

  const handleEditSuccess = () => {
    setEditingContact(null);
    refetch();
    refetchStats();
  };

  const handleDelete = async (conn) => {
    setDeleting(true);
    try {
      if (conn.contact_id) {
        await api.deleteContact(conn.contact_id);
      } else if (conn.customer_id) {
        await api.deleteCustomer(conn.customer_id);
      }
      setDeleteConfirm(null);
      refetch();
      refetchStats();
    } catch (err) {
      alert(err.message || 'Failed to delete');
    } finally {
      setDeleting(false);
    }
  };

  const toggleMergeSelection = (conn) => {
    if (!conn.contact_id) return; // Only contacts can be merged
    setSelectedForMerge(prev => {
      const isSelected = prev.some(c => c.id === conn.contact_id);
      if (isSelected) {
        return prev.filter(c => c.id !== conn.contact_id);
      }
      return [...prev, { ...conn, id: conn.contact_id }];
    });
  };

  const handleMergeSuccess = () => {
    setShowMergeModal(false);
    setSelectedForMerge([]);
    refetch();
    refetchStats();
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
    setStageFilter('');
    setStatusFilter('');
    setSearch('');
  };

  const hasActiveFilters = typeFilter || stageFilter || statusFilter || search;

  const handleSelectAll = () => {
    const selectableOnPage = paginatedConnections.filter(c => c.contact_id);
    if (selectedForMerge.length === selectableOnPage.length && selectableOnPage.length > 0) {
      setSelectedForMerge([]);
    } else {
      setSelectedForMerge(selectableOnPage.map(c => ({ ...c, id: c.contact_id })));
    }
  };

  const handleBulkDelete = async () => {
    setBulkDeleting(true);
    try {
      for (const conn of selectedForMerge) {
        if (conn.contact_id) {
          await api.deleteContact(conn.contact_id);
        } else if (conn.customer_id) {
          await api.deleteCustomer(conn.customer_id);
        }
      }
      setShowBulkDeleteConfirm(false);
      setSelectedForMerge([]);
      refetch();
      refetchStats();
    } catch (err) {
      alert(err.message || 'Failed to delete some items');
    } finally {
      setBulkDeleting(false);
    }
  };

  if (needsTenant) {
    return (
      <div className="connections-page">
        <EmptyState
          icon={<Users size={32} strokeWidth={1.5} />}
          title="Select a tenant to view connections"
          description="Please select a tenant from the dropdown above to view their connections."
        />
      </div>
    );
  }

  if (loading) {
    return <LoadingState message="Loading connections..." fullPage />;
  }

  if (error) {
    if (error.includes('Tenant context required') || error.includes('Tenant context')) {
      return (
        <div className="connections-page">
          <EmptyState
            icon={<Users size={32} strokeWidth={1.5} />}
            title="Select a tenant to view connections"
            description="Please select a tenant from the dropdown above to view their connections."
          />
        </div>
      );
    }
    if (error.includes('Not Found') || error.includes('not found')) {
      return (
        <div className="connections-page">
          <div className="page-header">
            <h1>Connections</h1>
          </div>
          <EmptyState
            icon={<Users size={32} strokeWidth={1.5} />}
            title="No connections yet"
            description="Connections will appear here as contacts and customers are added."
          />
        </div>
      );
    }
    return (
      <div className="connections-page">
        <ErrorState message={error} onRetry={refetch} />
      </div>
    );
  }

  return (
    <div className="connections-page">
      <div className="page-header">
        <div className="page-header-left">
          <h1>Connections</h1>
          {stats && (
            <div className="connections-stats">
              <span className="stat-total">{stats.total} total</span>
              {stats.linked > 0 && <span className="stat-item stat-linked">{stats.linked} linked</span>}
              {stats.contacts_only > 0 && <span className="stat-item stat-contacts">{stats.contacts_only} contacts</span>}
              {stats.customers_only > 0 && <span className="stat-item stat-customers">{stats.customers_only} customers</span>}
            </div>
          )}
        </div>
        <div className="header-actions">
          <div className="search-box">
            <Search size={14} className="search-icon" />
            <input
              type="text"
              placeholder="Search connections..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              aria-label="Search connections"
            />
          </div>
        </div>
      </div>

      {/* Filter Bar */}
      <div className="connections-filters">
        <select
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value)}
          className="filter-select"
          aria-label="Filter by type"
        >
          <option value="">All Types</option>
          <option value="contact">Contacts Only</option>
          <option value="customer">Customers Only</option>
          <option value="both">Linked (Both)</option>
        </select>

        <select
          value={stageFilter}
          onChange={(e) => setStageFilter(e.target.value)}
          className="filter-select"
          aria-label="Filter by pipeline stage"
        >
          <option value="">All Stages</option>
          {Object.entries(PIPELINE_STAGE_LABELS).map(([key, label]) => (
            <option key={key} value={key}>{label}</option>
          ))}
        </select>

        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="filter-select"
          aria-label="Filter by customer status"
        >
          <option value="">All Statuses</option>
          {Object.entries(CUSTOMER_STATUS_LABELS).map(([key, label]) => (
            <option key={key} value={key}>{label}</option>
          ))}
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
          <option value="pipeline_stage">Sort: Stage</option>
        </select>

        <button
          className={`sort-direction-btn ${sortDir}`}
          onClick={() => setSortDir(prev => prev === 'asc' ? 'desc' : 'asc')}
          title={sortDir === 'asc' ? 'Ascending' : 'Descending'}
          aria-label={sortDir === 'asc' ? 'Sort ascending' : 'Sort descending'}
        >
          {sortDir === 'asc' ? '\u2191' : '\u2193'}
        </button>

        {hasActiveFilters && (
          <button className="btn-clear-filters" onClick={clearFilters}>
            Clear
          </button>
        )}

        <span className="filter-count">
          {filteredConnections.length} of {connections.length}
        </span>
      </div>

      {/* Bulk Actions Bar */}
      {selectedForMerge.length > 0 && (
        <div className="bulk-action-bar">
          <span className="bulk-count">
            {selectedForMerge.length} selected
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

      {connections.length === 0 ? (
        <EmptyState
          icon={<Users size={32} strokeWidth={1.5} />}
          title="No connections yet"
          description="Connections will appear here as contacts and customers are added."
        />
      ) : (
        <div className="connections-table-container">
          <table className="connections-table">
            <thead>
              <tr>
                <th className="th-checkbox">
                  <input
                    type="checkbox"
                    checked={
                      paginatedConnections.filter(c => c.contact_id).length > 0 &&
                      selectedForMerge.length === paginatedConnections.filter(c => c.contact_id).length
                    }
                    onChange={handleSelectAll}
                    title="Select all contacts"
                    aria-label="Select all contacts"
                  />
                </th>
                <th
                  className={`col-name sortable ${sortBy === 'name' ? 'sorted' : ''}`}
                  onClick={() => handleSort('name')}
                >
                  Name {sortBy === 'name' && (sortDir === 'asc' ? '\u2191' : '\u2193')}
                </th>
                <th className="col-tags">Tags</th>
                <th className="col-phone">Phone</th>
                <th
                  className={`col-added sortable ${sortBy === 'created_at' ? 'sorted' : ''}`}
                  onClick={() => handleSort('created_at')}
                >
                  Added {sortBy === 'created_at' && (sortDir === 'asc' ? '\u2191' : '\u2193')}
                </th>
                <th
                  className={`col-last-contacted sortable ${sortBy === 'last_contacted' ? 'sorted' : ''}`}
                  onClick={() => handleSort('last_contacted')}
                >
                  Last Contact {sortBy === 'last_contacted' && (sortDir === 'asc' ? '\u2191' : '\u2193')}
                </th>
                <th className="col-actions">Actions</th>
              </tr>
            </thead>
            <tbody>
              {paginatedConnections.map((conn) => {
                const isSelectedForMerge = conn.contact_id && selectedForMerge.some(c => c.id === conn.contact_id);
                const displayName = formatName(conn.name) || formatName(conn.customer_name) || 'Unknown';
                return (
                  <tr
                    key={`${conn.record_type}-${conn.contact_id || conn.customer_id}`}
                    className={`${isSelectedForMerge ? 'selected-for-merge' : ''} clickable-row`}
                    onClick={() => handleRowClick(conn)}
                  >
                    <td className="td-checkbox" onClick={(e) => e.stopPropagation()}>
                      <input
                        type="checkbox"
                        checked={!!isSelectedForMerge}
                        onChange={() => toggleMergeSelection(conn)}
                        disabled={!conn.contact_id}
                        title={conn.contact_id ? 'Select for merge' : 'Only contacts can be merged'}
                      />
                    </td>
                    <td className="col-name">
                      <div className="connection-person">
                        <span className="connection-person__name">{displayName}</span>
                        <span className="connection-person__email">{conn.email || '-'}</span>
                      </div>
                    </td>
                    <td className="col-tags">
                      <div className="tag-group">
                        {conn.pipeline_stage && (
                          <span className={`pipeline-badge stage-${conn.pipeline_stage}`}>
                            {PIPELINE_STAGE_LABELS[conn.pipeline_stage] || conn.pipeline_stage}
                          </span>
                        )}
                        {conn.customer_status && (
                          <span className={`status-badge status-${conn.customer_status}`}>
                            {CUSTOMER_STATUS_LABELS[conn.customer_status] || conn.customer_status}
                          </span>
                        )}
                        {conn.has_interactions && (
                          <span className="interaction-badge">ConvoPro</span>
                        )}
                        {!conn.pipeline_stage && !conn.customer_status && !conn.has_interactions && (
                          <span className="connection-text-muted">-</span>
                        )}
                      </div>
                    </td>
                    <td className="col-phone">
                      <span className="connection-phone" title={conn.phone || '-'}>
                        {formatPhone(conn.phone)}
                      </span>
                    </td>
                    <td className="col-added">
                      <span className="connection-date">
                        {formatDateTimeParts(conn.created_at).date}
                      </span>
                    </td>
                    <td className="col-last-contacted">
                      {conn.last_contacted ? (
                        <span className="connection-date" title={formatDateTimeParts(conn.last_contacted).time}>
                          {formatDateTimeParts(conn.last_contacted).date}
                        </span>
                      ) : (
                        <span className="connection-text-muted">-</span>
                      )}
                    </td>
                    <td className="col-actions" onClick={(e) => e.stopPropagation()}>
                      <div className="action-buttons">
                        {conn.contact_id && (
                          <button
                            className="btn-action btn-history"
                            onClick={(e) => handleViewChat(e, conn)}
                            data-tooltip="History"
                            aria-label="View communication history"
                          >
                            <Clock size={14} />
                          </button>
                        )}
                        {conn.contact_id && (
                          <button
                            className="btn-action btn-edit"
                            onClick={(e) => handleEdit(e, conn)}
                            data-tooltip="Edit"
                            aria-label="Edit connection"
                          >
                            <Pencil size={14} />
                          </button>
                        )}
                        <button
                          className="btn-action btn-delete"
                          onClick={(e) => {
                            e.stopPropagation();
                            setDeleteConfirm(conn);
                          }}
                          data-tooltip="Delete"
                          aria-label="Delete connection"
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                      <details className="action-menu">
                        <summary
                          className="action-menu-trigger"
                          onClick={(e) => e.stopPropagation()}
                          aria-label="Open actions"
                          title="Open actions"
                        >
                          ...
                        </summary>
                        <div className="action-menu-list">
                          {conn.contact_id && (
                            <button
                              type="button"
                              onClick={(e) => {
                                handleViewChat(e, conn);
                                e.currentTarget.closest('details')?.removeAttribute('open');
                              }}
                            >
                              <Clock size={14} />
                              <span>History</span>
                            </button>
                          )}
                          {conn.contact_id && (
                            <button
                              type="button"
                              onClick={(e) => {
                                handleEdit(e, conn);
                                e.currentTarget.closest('details')?.removeAttribute('open');
                              }}
                            >
                              <Pencil size={14} />
                              <span>Edit</span>
                            </button>
                          )}
                          <button
                            type="button"
                            className="destructive"
                            onClick={(e) => {
                              e.stopPropagation();
                              setDeleteConfirm(conn);
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

          {paginatedConnections.length === 0 && search && (
            <EmptyState
              icon={<Search size={32} strokeWidth={1.5} />}
              title="No matches found"
              description={`No connections match "${search}". Try a different search term.`}
            />
          )}

          {/* Pagination Controls */}
          {filteredConnections.length > pageSize && (
            <div className="pagination-bar">
              <span className="pagination-info">
                {(page - 1) * pageSize + 1}–{Math.min(page * pageSize, filteredConnections.length)} of {filteredConnections.length}
              </span>
              <div className="pagination-buttons">
                <button className="pagination-btn" onClick={() => setPage(1)} disabled={page === 1} aria-label="First page">
                  First
                </button>
                <button className="pagination-btn" onClick={() => setPage(p => p - 1)} disabled={page === 1} aria-label="Previous page">
                  <ChevronLeft size={14} />
                </button>
                <span className="pagination-current">Page {page} of {totalPages}</span>
                <button className="pagination-btn" onClick={() => setPage(p => p + 1)} disabled={page === totalPages} aria-label="Next page">
                  <ChevronRight size={14} />
                </button>
                <button className="pagination-btn" onClick={() => setPage(totalPages)} disabled={page === totalPages} aria-label="Last page">
                  Last
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* History Modal */}
      {selectedContact && (
        <ContactHistoryModal
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
              <h2>Delete {deleteConfirm.contact_id ? 'Contact' : 'Customer'}</h2>
              <button className="close-btn" onClick={() => setDeleteConfirm(null)} disabled={deleting}>
                ×
              </button>
            </div>
            <div className="modal-body">
              <p>Are you sure you want to permanently delete this {deleteConfirm.contact_id ? 'contact' : 'customer'}?</p>
              <div className="delete-contact-info">
                <strong>{deleteConfirm.name || deleteConfirm.customer_name || 'Unknown'}</strong>
                <span>{deleteConfirm.email || deleteConfirm.phone || 'No contact info'}</span>
              </div>
              <p className="warning-text">
                This action cannot be undone. All associated data will be permanently removed.
              </p>
            </div>
            <div className="modal-footer">
              <button className="btn-cancel" onClick={() => setDeleteConfirm(null)} disabled={deleting}>
                Cancel
              </button>
              <button className="btn-delete-confirm" onClick={() => handleDelete(deleteConfirm)} disabled={deleting}>
                {deleting ? 'Deleting...' : 'Delete'}
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
              <h2>Delete {selectedForMerge.length} Items</h2>
              <button className="close-btn" onClick={() => setShowBulkDeleteConfirm(false)} disabled={bulkDeleting}>
                ×
              </button>
            </div>
            <div className="modal-body">
              <p>Are you sure you want to permanently delete {selectedForMerge.length} item{selectedForMerge.length > 1 ? 's' : ''}?</p>
              <div className="bulk-delete-list">
                {selectedForMerge.slice(0, 5).map(conn => (
                  <div key={conn.contact_id || conn.customer_id} className="bulk-delete-item">
                    {conn.name || conn.customer_name || 'Unknown'} — {conn.email || conn.phone || 'No info'}
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
              <button className="btn-cancel" onClick={() => setShowBulkDeleteConfirm(false)} disabled={bulkDeleting}>
                Cancel
              </button>
              <button className="btn-delete-confirm" onClick={handleBulkDelete} disabled={bulkDeleting}>
                {bulkDeleting ? 'Deleting...' : `Delete ${selectedForMerge.length} Items`}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
