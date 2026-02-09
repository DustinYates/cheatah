import { useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Users, Search, Plus, Trash2, RefreshCw } from 'lucide-react';
import { api } from '../api/client';
import { useFetchData } from '../hooks/useFetchData';
import { useAuth } from '../context/AuthContext';
import { LoadingState, EmptyState, ErrorState } from '../components/ui';
import { formatDateTimeParts } from '../utils/dateFormat';
import { formatPhone } from '../utils/formatPhone';
import './Customers.css';

export default function Customers() {
  const { user, selectedTenantId } = useAuth();
  const navigate = useNavigate();
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [deleteConfirm, setDeleteConfirm] = useState(null);
  const [deleting, setDeleting] = useState(false);
  const [page, setPage] = useState(1);
  const pageSize = 50;

  const fetchCustomers = useCallback(async () => {
    try {
      const params = { page, page_size: pageSize };
      if (statusFilter) params.status = statusFilter;
      if (search) params.search = search;
      const data = await api.getCustomers(params);
      return data;
    } catch (err) {
      if (err.message?.includes('Not Found') || err.message?.includes('not found')) {
        return { items: [], total: 0, page: 1, page_size: pageSize };
      }
      throw err;
    }
  }, [page, statusFilter, search]);

  const fetchStats = useCallback(async () => {
    try {
      return await api.getCustomerStats();
    } catch (err) {
      return { total: 0, active: 0, inactive: 0, suspended: 0 };
    }
  }, []);

  const { data: customersData, loading, error, refetch } = useFetchData(fetchCustomers, {
    defaultValue: { items: [], total: 0, page: 1, page_size: pageSize },
    deps: [selectedTenantId, page, statusFilter, search]
  });

  const { data: stats } = useFetchData(fetchStats, {
    defaultValue: { total: 0, active: 0, inactive: 0, suspended: 0 },
    deps: [selectedTenantId]
  });

  const customers = customersData?.items || [];
  const totalCustomers = customersData?.total || 0;
  const totalPages = Math.ceil(totalCustomers / pageSize);

  const needsTenant = user?.is_global_admin && !selectedTenantId;

  const handleDelete = async (customer) => {
    setDeleting(true);
    try {
      await api.deleteCustomer(customer.id);
      setDeleteConfirm(null);
      refetch();
    } catch (err) {
      alert(err.message || 'Failed to delete customer');
    } finally {
      setDeleting(false);
    }
  };

  const handleSearchSubmit = (e) => {
    e.preventDefault();
    setPage(1);
    refetch();
  };

  const getStatusBadgeClass = (status) => {
    switch (status) {
      case 'active': return 'status-badge status-active';
      case 'inactive': return 'status-badge status-inactive';
      case 'suspended': return 'status-badge status-suspended';
      default: return 'status-badge';
    }
  };

  if (needsTenant) {
    return (
      <div className="customers-page">
        <EmptyState
          icon={<Users size={32} strokeWidth={1.5} />}
          title="Select a tenant to view customers"
          description="Please select a tenant from the dropdown above to view their customers."
        />
      </div>
    );
  }

  if (loading && customers.length === 0) {
    return <LoadingState message="Loading customers..." fullPage />;
  }

  if (error && !error.includes('Not Found')) {
    if (error.includes('Tenant context required') || error.includes('Tenant context')) {
      return (
        <div className="customers-page">
          <EmptyState
            icon={<Users size={32} strokeWidth={1.5} />}
            title="Select a tenant to view customers"
            description="Please select a tenant from the dropdown above to view their customers."
          />
        </div>
      );
    }
    return <ErrorState message={error} onRetry={refetch} />;
  }

  return (
    <div className="customers-page">
      <div className="page-header">
        <div className="header-left">
          <h1>Customers</h1>
          <div className="stats-summary">
            <span className="stat-item">
              <span className="stat-value">{stats.total}</span> total
            </span>
            <span className="stat-divider">|</span>
            <span className="stat-item stat-active">
              <span className="stat-value">{stats.active}</span> active
            </span>
            <span className="stat-divider">|</span>
            <span className="stat-item stat-inactive">
              <span className="stat-value">{stats.inactive}</span> inactive
            </span>
          </div>
        </div>
        <div className="header-actions">
          <form onSubmit={handleSearchSubmit} className="search-box">
            <Search size={14} className="search-icon" />
            <input
              type="text"
              placeholder="Search customers..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </form>
          <select
            value={statusFilter}
            onChange={(e) => { setStatusFilter(e.target.value); setPage(1); }}
            className="status-filter"
          >
            <option value="">All Status</option>
            <option value="active">Active</option>
            <option value="inactive">Inactive</option>
            <option value="suspended">Suspended</option>
          </select>
          <button className="btn-icon" onClick={refetch} title="Refresh">
            <RefreshCw size={16} />
          </button>
        </div>
      </div>

      {customers.length === 0 ? (
        <EmptyState
          icon={<Users size={32} strokeWidth={1.5} />}
          title="No customers found"
          description={search || statusFilter
            ? "No customers match your filters. Try adjusting your search."
            : "Customers will appear here once synced from Jackrabbit."
          }
        />
      ) : (
        <>
          <div className="customers-table-wrapper">
            <table className="customers-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Phone</th>
                  <th>Email</th>
                  <th>Status</th>
                  <th>Account Type</th>
                  <th>Last Synced</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {customers.map(customer => {
                  const syncedParts = customer.last_synced_at
                    ? formatDateTimeParts(customer.last_synced_at)
                    : null;

                  return (
                    <tr
                      key={customer.id}
                      onClick={() => navigate(`/customers/${customer.id}`)}
                      className="customer-row"
                    >
                      <td className="name-cell">
                        <span className="customer-name">{customer.name || 'Unknown'}</span>
                        {customer.external_customer_id && (
                          <span className="external-id">#{customer.external_customer_id}</span>
                        )}
                      </td>
                      <td>{formatPhone(customer.phone)}</td>
                      <td>{customer.email || '-'}</td>
                      <td>
                        <span className={getStatusBadgeClass(customer.status)}>
                          {customer.status}
                        </span>
                      </td>
                      <td>{customer.account_type || '-'}</td>
                      <td>
                        {syncedParts ? (
                          <span className="date-time">
                            <span className="date">{syncedParts.date}</span>
                            <span className="time">{syncedParts.time}</span>
                          </span>
                        ) : (
                          <span className="never-synced">Never</span>
                        )}
                      </td>
                      <td className="actions-cell">
                        <button
                          className="btn-icon btn-danger"
                          onClick={(e) => {
                            e.stopPropagation();
                            setDeleteConfirm(customer);
                          }}
                          title="Delete"
                        >
                          <Trash2 size={14} />
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {totalPages > 1 && (
            <div className="pagination">
              <button
                className="btn-page"
                disabled={page === 1}
                onClick={() => setPage(p => p - 1)}
              >
                Previous
              </button>
              <span className="page-info">
                Page {page} of {totalPages} ({totalCustomers} customers)
              </span>
              <button
                className="btn-page"
                disabled={page >= totalPages}
                onClick={() => setPage(p => p + 1)}
              >
                Next
              </button>
            </div>
          )}
        </>
      )}

      {/* Delete Confirmation Modal */}
      {deleteConfirm && (
        <div className="modal-overlay" onClick={() => setDeleteConfirm(null)}>
          <div className="modal-content" onClick={e => e.stopPropagation()}>
            <h3>Delete Customer</h3>
            <p>Are you sure you want to delete <strong>{deleteConfirm.name || deleteConfirm.phone}</strong>?</p>
            <p className="warning">This action cannot be undone.</p>
            <div className="modal-actions">
              <button
                className="btn-secondary"
                onClick={() => setDeleteConfirm(null)}
                disabled={deleting}
              >
                Cancel
              </button>
              <button
                className="btn-danger"
                onClick={() => handleDelete(deleteConfirm)}
                disabled={deleting}
              >
                {deleting ? 'Deleting...' : 'Delete'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
