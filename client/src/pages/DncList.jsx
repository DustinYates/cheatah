import { useState, useEffect, useCallback } from 'react';
import { useAuth } from '../context/AuthContext';
import './Settings.css';

export default function DncList() {
  const { token, selectedTenantId } = useAuth();
  const [records, setRecords] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showAddModal, setShowAddModal] = useState(false);
  const [showUnblockModal, setShowUnblockModal] = useState(false);
  const [selectedRecord, setSelectedRecord] = useState(null);
  const [formData, setFormData] = useState({ phone: '', email: '', reason: '' });
  const [submitting, setSubmitting] = useState(false);

  const fetchRecords = useCallback(async () => {
    try {
      setLoading(true);
      const headers = {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
      };
      if (selectedTenantId) {
        headers['X-Tenant-Id'] = selectedTenantId.toString();
      }

      const response = await fetch('/api/v1/dnc/list?limit=100', { headers });
      if (!response.ok) throw new Error('Failed to fetch DNC list');

      const data = await response.json();
      setRecords(data.records || []);
      setTotal(data.total || 0);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [token, selectedTenantId]);

  useEffect(() => {
    fetchRecords();
  }, [fetchRecords]);

  const handleAddBlock = async (e) => {
    e.preventDefault();
    if (!formData.phone && !formData.email) {
      setError('Please provide a phone number or email');
      return;
    }

    setSubmitting(true);
    try {
      const headers = {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
      };
      if (selectedTenantId) {
        headers['X-Tenant-Id'] = selectedTenantId.toString();
      }

      const response = await fetch('/api/v1/dnc/block', {
        method: 'POST',
        headers,
        body: JSON.stringify(formData),
      });

      if (!response.ok) {
        const err = await response.json();
        throw new Error(err.detail || 'Failed to add to DNC list');
      }

      setShowAddModal(false);
      setFormData({ phone: '', email: '', reason: '' });
      fetchRecords();
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  const handleUnblock = async () => {
    if (!selectedRecord) return;

    setSubmitting(true);
    try {
      const headers = {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
      };
      if (selectedTenantId) {
        headers['X-Tenant-Id'] = selectedTenantId.toString();
      }

      const response = await fetch('/api/v1/dnc/unblock', {
        method: 'POST',
        headers,
        body: JSON.stringify({
          phone: selectedRecord.phone_number,
          email: selectedRecord.email,
          reason: formData.reason,
        }),
      });

      if (!response.ok) {
        const err = await response.json();
        throw new Error(err.detail || 'Failed to unblock');
      }

      setShowUnblockModal(false);
      setSelectedRecord(null);
      setFormData({ phone: '', email: '', reason: '' });
      fetchRecords();
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  const formatDate = (dateString) => {
    if (!dateString) return '-';
    return new Date(dateString).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const getSourceBadge = (source) => {
    const badges = {
      sms: { label: 'SMS', className: 'badge-info' },
      email: { label: 'Email', className: 'badge-primary' },
      voice: { label: 'Voice', className: 'badge-warning' },
      manual: { label: 'Manual', className: 'badge-secondary' },
    };
    const badge = badges[source] || { label: source, className: 'badge-secondary' };
    return <span className={`badge ${badge.className}`}>{badge.label}</span>;
  };

  return (
    <div className="settings-page">
      <div className="settings-header">
        <h1>Do Not Contact List</h1>
        <p>Manage contacts who have requested not to receive communications.</p>
      </div>

      {error && (
        <div className="alert alert-error" onClick={() => setError(null)}>
          {error}
        </div>
      )}

      <div className="settings-card">
        <div className="card-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <h2>Blocked Contacts</h2>
            <p className="card-description">
              {total} contact{total !== 1 ? 's' : ''} blocked from receiving communications
            </p>
          </div>
          <button className="btn btn-primary" onClick={() => setShowAddModal(true)}>
            + Add to List
          </button>
        </div>

        {loading ? (
          <div className="loading-state">Loading...</div>
        ) : records.length === 0 ? (
          <div className="empty-state">
            <p>No contacts on the Do Not Contact list.</p>
          </div>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Contact</th>
                <th>Source</th>
                <th>Reason/Message</th>
                <th>Date Added</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {records.map((record) => (
                <tr key={record.id}>
                  <td>
                    {record.phone_number && <div>{record.phone_number}</div>}
                    {record.email && <div className="text-muted">{record.email}</div>}
                  </td>
                  <td>{getSourceBadge(record.source_channel)}</td>
                  <td className="text-truncate" style={{ maxWidth: '250px' }}>
                    {record.source_message || '-'}
                  </td>
                  <td>{formatDate(record.created_at)}</td>
                  <td>
                    <button
                      className="btn btn-sm btn-outline"
                      onClick={() => {
                        setSelectedRecord(record);
                        setShowUnblockModal(true);
                      }}
                    >
                      Unblock
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Add to DNC Modal */}
      {showAddModal && (
        <div className="modal-overlay" onClick={() => setShowAddModal(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>Add to Do Not Contact List</h3>
              <button className="modal-close" onClick={() => setShowAddModal(false)}>
                &times;
              </button>
            </div>
            <form onSubmit={handleAddBlock}>
              <div className="modal-body">
                <p className="text-muted" style={{ marginBottom: '1rem' }}>
                  Use this when a customer verbally requests not to be contacted.
                </p>
                <div className="form-group">
                  <label htmlFor="phone">Phone Number</label>
                  <input
                    type="tel"
                    id="phone"
                    placeholder="+1234567890"
                    value={formData.phone}
                    onChange={(e) => setFormData({ ...formData, phone: e.target.value })}
                  />
                </div>
                <div className="form-group">
                  <label htmlFor="email">Email Address</label>
                  <input
                    type="email"
                    id="email"
                    placeholder="email@example.com"
                    value={formData.email}
                    onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                  />
                </div>
                <div className="form-group">
                  <label htmlFor="reason">Reason (optional)</label>
                  <textarea
                    id="reason"
                    placeholder="e.g., Customer requested no contact during phone call"
                    value={formData.reason}
                    onChange={(e) => setFormData({ ...formData, reason: e.target.value })}
                    rows={3}
                  />
                </div>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-outline" onClick={() => setShowAddModal(false)}>
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary" disabled={submitting}>
                  {submitting ? 'Adding...' : 'Add to List'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Unblock Modal */}
      {showUnblockModal && selectedRecord && (
        <div className="modal-overlay" onClick={() => setShowUnblockModal(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>Unblock Contact</h3>
              <button className="modal-close" onClick={() => setShowUnblockModal(false)}>
                &times;
              </button>
            </div>
            <div className="modal-body">
              <p>
                Are you sure you want to remove{' '}
                <strong>{selectedRecord.phone_number || selectedRecord.email}</strong> from the Do Not
                Contact list?
              </p>
              <p className="text-muted" style={{ marginTop: '0.5rem' }}>
                This contact will be able to receive communications again.
              </p>
              <div className="form-group" style={{ marginTop: '1rem' }}>
                <label htmlFor="unblock-reason">Reason for Unblocking</label>
                <textarea
                  id="unblock-reason"
                  placeholder="e.g., Customer re-engaged and gave consent"
                  value={formData.reason}
                  onChange={(e) => setFormData({ ...formData, reason: e.target.value })}
                  rows={2}
                />
              </div>
            </div>
            <div className="modal-footer">
              <button
                type="button"
                className="btn btn-outline"
                onClick={() => {
                  setShowUnblockModal(false);
                  setSelectedRecord(null);
                  setFormData({ phone: '', email: '', reason: '' });
                }}
              >
                Cancel
              </button>
              <button className="btn btn-primary" onClick={handleUnblock} disabled={submitting}>
                {submitting ? 'Removing...' : 'Unblock Contact'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
