import { useState, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, User, Phone, Mail, Calendar, RefreshCw, Edit2, Save, X, DollarSign, Users, MapPin, Clock, BookOpen } from 'lucide-react';
import { api } from '../api/client';
import { useFetchData } from '../hooks/useFetchData';
import { useAuth } from '../context/AuthContext';
import { LoadingState, EmptyState, ErrorState } from '../components/ui';
import { formatDateTimeParts } from '../utils/dateFormat';
import './CustomerDetail.css';

export default function CustomerDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { selectedTenantId } = useAuth();
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [editData, setEditData] = useState({});

  const fetchCustomer = useCallback(async () => {
    return await api.getCustomer(id);
  }, [id]);

  const { data: customer, loading, error, refetch } = useFetchData(fetchCustomer, {
    defaultValue: null,
    deps: [selectedTenantId, id]
  });

  const handleEdit = () => {
    setEditData({
      name: customer.name || '',
      email: customer.email || '',
      phone: customer.phone || '',
      status: customer.status || 'active',
      account_type: customer.account_type || '',
    });
    setEditing(true);
  };

  const handleCancel = () => {
    setEditing(false);
    setEditData({});
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await api.updateCustomer(id, editData);
      setEditing(false);
      refetch();
    } catch (err) {
      alert(err.message || 'Failed to update customer');
    } finally {
      setSaving(false);
    }
  };

  const getStatusBadgeClass = (status) => {
    switch (status) {
      case 'active': return 'status-badge status-active';
      case 'inactive': return 'status-badge status-inactive';
      case 'suspended': return 'status-badge status-suspended';
      default: return 'status-badge';
    }
  };

  if (loading) {
    return <LoadingState message="Loading customer..." fullPage />;
  }

  if (error) {
    return <ErrorState message={error} onRetry={refetch} />;
  }

  if (!customer) {
    return (
      <div className="customer-detail-page">
        <EmptyState
          icon={<User size={32} strokeWidth={1.5} />}
          title="Customer not found"
          description="The customer you're looking for doesn't exist or has been deleted."
        />
      </div>
    );
  }

  const createdParts = formatDateTimeParts(customer.created_at);
  const syncedParts = customer.last_synced_at ? formatDateTimeParts(customer.last_synced_at) : null;

  return (
    <div className="customer-detail-page">
      <div className="page-header">
        <button className="btn-back" onClick={() => navigate('/connections')}>
          <ArrowLeft size={16} />
          <span>Back to Connections</span>
        </button>
        <div className="header-actions">
          <button className="btn-icon" onClick={refetch} title="Refresh">
            <RefreshCw size={16} />
          </button>
          {!editing && (
            <button className="btn-primary" onClick={handleEdit}>
              <Edit2 size={14} />
              <span>Edit</span>
            </button>
          )}
        </div>
      </div>

      <div className="customer-content">
        <div className="customer-header">
          <div className="customer-avatar">
            <User size={32} strokeWidth={1.5} />
          </div>
          <div className="customer-info">
            {editing ? (
              <input
                type="text"
                className="edit-name"
                value={editData.name}
                onChange={(e) => setEditData({ ...editData, name: e.target.value })}
                placeholder="Customer name"
              />
            ) : (
              <h1>{customer.name || 'Unknown Customer'}</h1>
            )}
            {customer.external_customer_id && (
              <span className="external-id">Jackrabbit ID: #{customer.external_customer_id}</span>
            )}
            <span className={getStatusBadgeClass(customer.status)}>
              {customer.status}
            </span>
          </div>
        </div>

        {editing && (
          <div className="edit-actions">
            <button className="btn-secondary" onClick={handleCancel} disabled={saving}>
              <X size={14} />
              <span>Cancel</span>
            </button>
            <button className="btn-primary" onClick={handleSave} disabled={saving}>
              <Save size={14} />
              <span>{saving ? 'Saving...' : 'Save'}</span>
            </button>
          </div>
        )}

        <div className="details-grid">
          <div className="detail-card">
            <h3>Contact Information</h3>
            <div className="detail-row">
              <Phone size={14} />
              {editing ? (
                <input
                  type="text"
                  value={editData.phone}
                  onChange={(e) => setEditData({ ...editData, phone: e.target.value })}
                />
              ) : (
                <span>{customer.phone}</span>
              )}
            </div>
            <div className="detail-row">
              <Mail size={14} />
              {editing ? (
                <input
                  type="email"
                  value={editData.email}
                  onChange={(e) => setEditData({ ...editData, email: e.target.value })}
                  placeholder="Email address"
                />
              ) : (
                <span>{customer.email || '-'}</span>
              )}
            </div>
          </div>

          <div className="detail-card">
            <h3>Account Details</h3>
            <div className="detail-row">
              <Users size={14} />
              <span className="label">Type:</span>
              {editing ? (
                <select
                  value={editData.account_type}
                  onChange={(e) => setEditData({ ...editData, account_type: e.target.value })}
                >
                  <option value="">Not specified</option>
                  <option value="family">Family</option>
                  <option value="individual">Individual</option>
                  <option value="business">Business</option>
                </select>
              ) : (
                <span>{customer.account_type || 'Not specified'}</span>
              )}
            </div>
            <div className="detail-row">
              <span className="label">Status:</span>
              {editing ? (
                <select
                  value={editData.status}
                  onChange={(e) => setEditData({ ...editData, status: e.target.value })}
                >
                  <option value="active">Active</option>
                  <option value="inactive">Inactive</option>
                  <option value="suspended">Suspended</option>
                </select>
              ) : (
                <span className={getStatusBadgeClass(customer.status)}>
                  {customer.status}
                </span>
              )}
            </div>
          </div>

          <div className="detail-card">
            <h3>Sync Information</h3>
            <div className="detail-row">
              <Calendar size={14} />
              <span className="label">Created:</span>
              <span>{createdParts.date} {createdParts.time}</span>
            </div>
            <div className="detail-row">
              <RefreshCw size={14} />
              <span className="label">Last Synced:</span>
              <span>
                {syncedParts
                  ? `${syncedParts.date} ${syncedParts.time}`
                  : 'Never'
                }
              </span>
            </div>
            <div className="detail-row">
              <span className="label">Source:</span>
              <span className="sync-source">{customer.sync_source || 'Unknown'}</span>
            </div>
          </div>
        </div>

        {/* Enrollments Section */}
        {customer.account_data?.enrollments && customer.account_data.enrollments.length > 0 && (
          <div className="enrollments-section">
            <h3><BookOpen size={16} /> Current Enrollments</h3>
            <div className="enrollments-list">
              {customer.account_data.enrollments.map((enrollment, idx) => (
                <div key={idx} className="enrollment-card">
                  <div className="enrollment-header">
                    <span className="class-name">{enrollment.class_name}</span>
                    <span className={`enrollment-status status-${enrollment.status || 'active'}`}>
                      {enrollment.status || 'Active'}
                    </span>
                  </div>
                  <div className="enrollment-details">
                    {enrollment.location && (
                      <div className="enrollment-detail">
                        <MapPin size={12} />
                        <span>{enrollment.location}</span>
                      </div>
                    )}
                    {enrollment.schedule && (
                      <div className="enrollment-detail">
                        <Clock size={12} />
                        <span>{enrollment.schedule}</span>
                      </div>
                    )}
                    {enrollment.instructor && (
                      <div className="enrollment-detail">
                        <User size={12} />
                        <span>{enrollment.instructor}</span>
                      </div>
                    )}
                    {enrollment.start_date && (
                      <div className="enrollment-detail">
                        <Calendar size={12} />
                        <span>Started: {enrollment.start_date}</span>
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Other Account Data */}
        {customer.account_data && Object.keys(customer.account_data).filter(k => k !== 'enrollments').length > 0 && (
          <div className="account-data-section">
            <h3>Account Data</h3>
            <div className="account-data-grid">
              {Object.entries(customer.account_data)
                .filter(([key]) => key !== 'enrollments')
                .map(([key, value]) => (
                <div key={key} className="account-data-item">
                  <span className="data-label">{key.replace(/_/g, ' ')}</span>
                  <span className="data-value">
                    {typeof value === 'object' ? JSON.stringify(value) : String(value)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
