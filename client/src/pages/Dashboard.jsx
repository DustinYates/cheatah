import { useState, useEffect } from 'react';
import { api } from '../api/client';
import { LoadingState, EmptyState, ErrorState } from '../components/ui';
import { formatSmartDateTime } from '../utils/dateFormat';
import './Dashboard.css';

export default function Dashboard() {
  const [leads, setLeads] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [actionLoading, setActionLoading] = useState(null);

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    setLoading(true);
    setError('');
    try {
      const leadsData = await api.getLeads({ limit: 50 }).catch(() => ({ leads: [] }));
      // Sort by created_at descending (most recent first)
      const sortedLeads = (leadsData.leads || leadsData || []).sort(
        (a, b) => new Date(b.created_at) - new Date(a.created_at)
      );
      setLeads(sortedLeads);
    } catch (err) {
      setError('Failed to load dashboard data');
    } finally {
      setLoading(false);
    }
  };

  const handleVerify = async (leadId) => {
    setActionLoading(leadId);
    try {
      await api.updateLeadStatus(leadId, 'verified');
      // Update local state
      setLeads(leads.map(lead => 
        lead.id === leadId ? { ...lead, status: 'verified' } : lead
      ));
    } catch (err) {
      setError('Failed to verify lead');
    } finally {
      setActionLoading(null);
    }
  };

  const handleMarkUnknown = async (leadId) => {
    setActionLoading(leadId);
    try {
      await api.updateLeadStatus(leadId, 'unknown');
      // Update local state
      setLeads(leads.map(lead => 
        lead.id === leadId ? { ...lead, status: 'unknown' } : lead
      ));
    } catch (err) {
      setError('Failed to mark lead as unknown');
    } finally {
      setActionLoading(null);
    }
  };

  const handleDelete = async (leadId, leadName) => {
    if (!confirm(`Are you sure you want to delete "${leadName || 'this lead'}"? This action cannot be undone.`)) {
      return;
    }
    
    setActionLoading(leadId);
    try {
      await api.deleteLead(leadId);
      // Remove from local state using functional update to ensure we have latest state
      setLeads(prevLeads => prevLeads.filter(lead => lead.id !== leadId));
      setError(''); // Clear any previous errors
    } catch (err) {
      console.error('Delete error details:', {
        message: err.message,
        stack: err.stack,
        error: err
      });
      setError(`Failed to delete lead: ${err.message || 'Unknown error'}`);
    } finally {
      setActionLoading(null);
    }
  };

  if (loading) {
    return <LoadingState message="Loading dashboard..." fullPage />;
  }

  if (error && leads.length === 0) {
    return <ErrorState message={error} onRetry={fetchData} />;
  }

  const getRowClassName = (lead) => {
    if (lead.status === 'verified' || lead.status === 'unknown') {
      return 'lead-row processed';
    }
    return 'lead-row';
  };

  return (
    <div className="dashboard">
      <h1>Dashboard</h1>

      <div className="dashboard-grid">
        <div className="card leads-card leads-card-wide">
          <h2>Recent Leads</h2>
          {error && <div className="error">{error}</div>}

          {leads.length === 0 ? (
            <EmptyState
              icon="📋"
              title="No leads yet"
              description="Start conversations to generate leads."
            />
          ) : (
            <div className="leads-table-container">
              <table className="leads-table">
                <thead>
                  <tr>
                    <th className="col-name">Name</th>
                    <th className="col-email">Email</th>
                    <th className="col-phone">Phone</th>
                    <th className="col-date">Date</th>
                    <th className="col-status">Status</th>
                    <th className="col-actions">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {leads.map((lead) => (
                    <tr key={lead.id} className={getRowClassName(lead)}>
                      <td className="col-name">{lead.name || 'Unknown'}</td>
                      <td className="col-email">{lead.email || '-'}</td>
                      <td className="col-phone">{lead.phone || '-'}</td>
                      <td className="col-date">{formatSmartDateTime(lead.created_at)}</td>
                      <td className="col-status">
                        <span className={`status-badge ${lead.status || 'new'}`}>
                          {lead.status || 'New'}
                        </span>
                      </td>
                      <td className="actions-cell col-actions">
                        {(!lead.status || lead.status === 'new') ? (
                          <>
                            <button
                              className="btn-action btn-verify"
                              onClick={() => handleVerify(lead.id)}
                              disabled={actionLoading === lead.id}
                              title="Mark as verified lead"
                            >
                              {actionLoading === lead.id ? '...' : '✓ Verify'}
                            </button>
                            <button
                              className="btn-action btn-unknown"
                              onClick={() => handleMarkUnknown(lead.id)}
                              disabled={actionLoading === lead.id}
                              title="Mark as unknown/spam"
                            >
                              {actionLoading === lead.id ? '...' : '? Unknown'}
                            </button>
                          </>
                        ) : lead.status === 'verified' ? (
                          <button
                            className="btn-action btn-verify"
                            onClick={() => handleVerify(lead.id)}
                            disabled={actionLoading === lead.id}
                            title="Re-sync to create contact"
                          >
                            {actionLoading === lead.id ? '...' : '⟳ Sync'}
                          </button>
                        ) : (
                          <span className="action-done">—</span>
                        )}
                        <button
                          className="btn-action btn-delete"
                          onClick={() => handleDelete(lead.id, lead.name)}
                          disabled={actionLoading === lead.id}
                          title="Permanently delete this lead"
                        >
                          {actionLoading === lead.id ? '...' : '✕'}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
