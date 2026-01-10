import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api/client';
import { useAuth } from '../context/AuthContext';
import { LoadingState, EmptyState, ErrorState } from '../components/ui';
import { formatDateTimeParts } from '../utils/dateFormat';
import './ManageTenants.css';

export default function ManageTenants() {
  const navigate = useNavigate();
  const { selectTenant, refreshTenants } = useAuth();
  const [tenants, setTenants] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showCreate, setShowCreate] = useState(false);
  const [newTenant, setNewTenant] = useState({
    name: '',
    subdomain: '',
    is_active: true,
  });
  const [creating, setCreating] = useState(false);

  // Single-tenant view mode
  const [viewMode, setViewMode] = useState('list'); // 'list' or 'single'
  const [currentIndex, setCurrentIndex] = useState(0);
  const [editingTenant, setEditingTenant] = useState(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    fetchTenants();
  }, []);

  const fetchTenants = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getTenants();
      setTenants(Array.isArray(data) ? data : []);
    } catch (err) {
      console.error('Failed to fetch tenants:', err);
      setError(err.message || 'Failed to load tenants');
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = async (e) => {
    e.preventDefault();
    setCreating(true);
    setError(null);
    try {
      const created = await api.createTenant(newTenant);
      setTenants([...tenants, created]);
      setNewTenant({ name: '', subdomain: '', is_active: true });
      setShowCreate(false);
      if (refreshTenants) refreshTenants();
    } catch (err) {
      setError(err.message || 'Failed to create tenant');
    } finally {
      setCreating(false);
    }
  };

  const handleTenantFieldChange = (tenantId, field, value) => {
    setTenants((prevTenants) =>
      prevTenants.map((tenant) =>
        tenant.id === tenantId ? { ...tenant, [field]: value } : tenant
      )
    );
    // Also update editingTenant if in single view
    if (editingTenant && editingTenant.id === tenantId) {
      setEditingTenant({ ...editingTenant, [field]: value });
    }
  };

  const handleTenantFieldBlur = async (tenantId, field, value) => {
    const normalizedValue = value === '' ? null : value;
    setError(null);
    try {
      const updated = await api.updateTenant(tenantId, { [field]: normalizedValue });
      setTenants((prevTenants) =>
        prevTenants.map((tenant) => (tenant.id === tenantId ? updated : tenant))
      );
      if (editingTenant && editingTenant.id === tenantId) {
        setEditingTenant(updated);
      }
      if (refreshTenants) refreshTenants();
    } catch (err) {
      setError(err.message || 'Failed to update tenant');
    }
  };

  const handleSaveTenant = async () => {
    if (!editingTenant) return;
    setSaving(true);
    setError(null);
    try {
      const updated = await api.updateTenant(editingTenant.id, {
        tenant_number: editingTenant.tenant_number || null,
        name: editingTenant.name,
        tier: editingTenant.tier || null,
        end_date: editingTenant.end_date || null,
        is_active: editingTenant.is_active,
      });
      setTenants((prevTenants) =>
        prevTenants.map((tenant) => (tenant.id === updated.id ? updated : tenant))
      );
      setEditingTenant(updated);
      if (refreshTenants) refreshTenants();
    } catch (err) {
      setError(err.message || 'Failed to save tenant');
    } finally {
      setSaving(false);
    }
  };

  const handleViewTenant = (index) => {
    setCurrentIndex(index);
    setEditingTenant({ ...tenants[index] });
    setViewMode('single');
  };

  const handlePrevTenant = () => {
    if (currentIndex > 0) {
      const newIndex = currentIndex - 1;
      setCurrentIndex(newIndex);
      setEditingTenant({ ...tenants[newIndex] });
    }
  };

  const handleNextTenant = () => {
    if (currentIndex < tenants.length - 1) {
      const newIndex = currentIndex + 1;
      setCurrentIndex(newIndex);
      setEditingTenant({ ...tenants[newIndex] });
    }
  };

  const handleImpersonate = (tenantId) => {
    selectTenant(tenantId);
    navigate('/');
  };

  const handleBackToList = () => {
    setViewMode('list');
    setEditingTenant(null);
  };

  if (loading) {
    return <LoadingState message="Loading tenants..." fullPage />;
  }

  if (error && tenants.length === 0) {
    return <ErrorState message={error} onRetry={fetchTenants} />;
  }

  // Single Tenant View Mode
  if (viewMode === 'single' && editingTenant) {
    const editingTenantDate = formatDateTimeParts(editingTenant.created_at);
    return (
      <div className="manage-tenants-page">
        <div className="single-view-header">
          <button className="btn-back" onClick={handleBackToList}>
            ← Back to List
          </button>
          <div className="tenant-nav">
            <button
              className="btn-nav"
              onClick={handlePrevTenant}
              disabled={currentIndex === 0}
            >
              ← Previous
            </button>
            <span className="nav-indicator">
              Tenant {currentIndex + 1} of {tenants.length}
            </span>
            <button
              className="btn-nav"
              onClick={handleNextTenant}
              disabled={currentIndex === tenants.length - 1}
            >
              Next →
            </button>
          </div>
        </div>

        {error && <div className="error-message">{error}</div>}

        <div className="tenant-detail-card">
          <div className="tenant-detail-header">
            <h2>{editingTenant.name}</h2>
            <span className={`status ${editingTenant.is_active ? 'active' : 'inactive'}`}>
              {editingTenant.is_active ? 'Active' : 'Inactive'}
            </span>
          </div>

          <div className="tenant-detail-grid">
            <div className="detail-field">
              <label>System ID</label>
              <div className="readonly-value">{editingTenant.id}</div>
            </div>

            <div className="detail-field">
              <label>Tenant Number (Assignable ID)</label>
              <input
                type="text"
                value={editingTenant.tenant_number || ''}
                onChange={(e) => setEditingTenant({ ...editingTenant, tenant_number: e.target.value })}
                placeholder="Enter custom tenant ID..."
              />
              <small>Assign a custom identifier for this tenant</small>
            </div>

            <div className="detail-field">
              <label>Name</label>
              <input
                type="text"
                value={editingTenant.name || ''}
                onChange={(e) => setEditingTenant({ ...editingTenant, name: e.target.value })}
              />
            </div>

            <div className="detail-field">
              <label>Subdomain</label>
              <div className="readonly-value">{editingTenant.subdomain}</div>
            </div>

            <div className="detail-field">
              <label>Tier</label>
              <input
                type="text"
                value={editingTenant.tier || ''}
                onChange={(e) => setEditingTenant({ ...editingTenant, tier: e.target.value })}
                placeholder="e.g., basic, pro, enterprise"
              />
            </div>

            <div className="detail-field">
              <label>End Date</label>
              <input
                type="date"
                value={editingTenant.end_date || ''}
                onChange={(e) => setEditingTenant({ ...editingTenant, end_date: e.target.value })}
              />
            </div>

            <div className="detail-field">
              <label>Status</label>
              <select
                value={editingTenant.is_active ? 'active' : 'inactive'}
                onChange={(e) => setEditingTenant({ ...editingTenant, is_active: e.target.value === 'active' })}
              >
                <option value="active">Active</option>
                <option value="inactive">Inactive</option>
              </select>
            </div>

            <div className="detail-field">
              <label>Created</label>
              <div className="readonly-value">
                {`${editingTenantDate.date} ${editingTenantDate.time} ${editingTenantDate.tzAbbr}`.trim()}
              </div>
            </div>
          </div>

          <div className="tenant-detail-actions">
            <button
              className="btn-primary"
              onClick={handleSaveTenant}
              disabled={saving}
            >
              {saving ? 'Saving...' : 'Save Changes'}
            </button>
            <button
              className="btn-secondary"
              onClick={() => handleImpersonate(editingTenant.id)}
            >
              View Tenant Screens →
            </button>
          </div>
        </div>
      </div>
    );
  }

  // List View Mode
  return (
    <div className="manage-tenants-page">
      <div className="page-header">
        <div>
          <h1>Manage Tenants</h1>
          <p className="page-subtitle">Create and manage tenant accounts</p>
        </div>
        <button className="btn-primary" onClick={() => setShowCreate(true)}>
          + Create Tenant
        </button>
      </div>

      {error && <div className="error-message">{error}</div>}

      {tenants.length === 0 ? (
        <EmptyState
          icon="🏢"
          title="No tenants yet"
          description="Create your first tenant to get started."
          action={{
            label: "+ Create Tenant",
            onClick: () => setShowCreate(true)
          }}
        />
      ) : (
        <div className="tenants-table-container">
          <table className="tenants-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Tenant #</th>
                <th>Name</th>
                <th>Subdomain</th>
                <th>Status</th>
                <th>Created</th>
                <th>End Date</th>
                <th>Tier</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {tenants.map((tenant, index) => (
                <tr key={tenant.id}>
                  <td>{tenant.id}</td>
                  <td>
                    <input
                      className="tenant-input"
                      type="text"
                      value={tenant.tenant_number || ''}
                      onChange={(e) =>
                        handleTenantFieldChange(tenant.id, 'tenant_number', e.target.value)
                      }
                      onBlur={(e) => {
                        const trimmedValue = e.target.value.trim();
                        handleTenantFieldChange(tenant.id, 'tenant_number', trimmedValue);
                        handleTenantFieldBlur(tenant.id, 'tenant_number', trimmedValue);
                      }}
                      placeholder="Assign..."
                    />
                  </td>
                  <td>{tenant.name}</td>
                  <td>{tenant.subdomain || '-'}</td>
                  <td>
                    <span className={`status ${tenant.is_active ? 'active' : 'inactive'}`}>
                      {tenant.is_active ? 'Active' : 'Inactive'}
                    </span>
                  </td>
                  <td>{formatDateTimeParts(tenant.created_at).date}</td>
                  <td>
                    <input
                      className="tenant-input"
                      type="date"
                      value={tenant.end_date || ''}
                      onChange={(e) =>
                        handleTenantFieldChange(tenant.id, 'end_date', e.target.value)
                      }
                      onBlur={(e) =>
                        handleTenantFieldBlur(tenant.id, 'end_date', e.target.value)
                      }
                    />
                  </td>
                  <td>
                    <input
                      className="tenant-input"
                      type="text"
                      value={tenant.tier || ''}
                      onChange={(e) =>
                        handleTenantFieldChange(tenant.id, 'tier', e.target.value)
                      }
                      onBlur={(e) => {
                        const trimmedValue = e.target.value.trim();
                        handleTenantFieldChange(tenant.id, 'tier', trimmedValue);
                        handleTenantFieldBlur(tenant.id, 'tier', trimmedValue);
                      }}
                      placeholder="-"
                    />
                  </td>
                  <td className="actions-cell">
                    <button
                      className="btn-view"
                      onClick={() => handleViewTenant(index)}
                      title="View/Edit tenant details"
                    >
                      Edit
                    </button>
                    <button
                      className="btn-impersonate"
                      onClick={() => handleImpersonate(tenant.id)}
                      title="View this tenant's screens"
                    >
                      View →
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {showCreate && (
        <div className="modal-overlay" onClick={() => { setShowCreate(false); setError(null); }}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Create New Tenant</h2>
              <button className="modal-close" onClick={() => { setShowCreate(false); setError(null); }}>×</button>
            </div>
            <form onSubmit={handleCreate}>
              <div className="form-group">
                <label>Tenant Name</label>
                <input
                  type="text"
                  value={newTenant.name}
                  onChange={(e) => setNewTenant({ ...newTenant, name: e.target.value })}
                  placeholder="e.g., Acme Corporation"
                  required
                />
              </div>
              <div className="form-group">
                <label>Subdomain</label>
                <input
                  type="text"
                  value={newTenant.subdomain}
                  onChange={(e) => setNewTenant({ ...newTenant, subdomain: e.target.value })}
                  placeholder="e.g., acme"
                  required
                />
                <small>Lowercase letters, numbers, and hyphens only</small>
              </div>
              <div className="modal-actions">
                <button type="button" className="btn-secondary" onClick={() => { setShowCreate(false); setError(null); }}>
                  Cancel
                </button>
                <button type="submit" className="btn-primary" disabled={creating}>
                  {creating ? 'Creating...' : 'Create Tenant'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
