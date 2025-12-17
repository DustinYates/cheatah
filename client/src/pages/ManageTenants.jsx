import { useState, useEffect } from 'react';
import { api } from '../api/client';
import { LoadingState, EmptyState, ErrorState } from '../components/ui';
import './ManageTenants.css';

export default function ManageTenants() {
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
    } catch (err) {
      setError(err.message || 'Failed to create tenant');
    } finally {
      setCreating(false);
    }
  };

  if (loading) {
    return <LoadingState message="Loading tenants..." fullPage />;
  }

  if (error && tenants.length === 0) {
    return <ErrorState message={error} onRetry={fetchTenants} />;
  }

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
                <th>Name</th>
                <th>Subdomain</th>
                <th>Status</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {tenants.map((tenant) => (
                <tr key={tenant.id}>
                  <td>{tenant.id}</td>
                  <td>{tenant.name}</td>
                  <td>{tenant.subdomain || '-'}</td>
                  <td>
                    <span className={`status ${tenant.is_active ? 'active' : 'inactive'}`}>
                      {tenant.is_active ? 'Active' : 'Inactive'}
                    </span>
                  </td>
                  <td>{new Date(tenant.created_at).toLocaleDateString()}</td>
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

