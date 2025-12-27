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
                        <div className="actions-container">
                          {(!lead.status || lead.status === 'new') ? (
                            <>
                              <button
                                className="btn-action btn-verify"
                                onClick={() => handleVerify(lead.id)}
                                disabled={actionLoading === lead.id}
                                title="Mark as verified lead"
                                aria-label="Verify lead"
                              >
                                {actionLoading === lead.id ? (
                                  <span className="spinner">⋯</span>
                                ) : (
                                  <svg className="icon" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                                    <path fillRule="evenodd" d="M16.704 4.153a.75.75 0 01.143 1.052l-8 10.5a.75.75 0 01-1.127.075l-4.5-4.5a.75.75 0 011.06-1.06l3.894 3.893 7.48-9.817a.75.75 0 011.05-.143z" clipRule="evenodd" />
                                  </svg>
                                )}
                              </button>
                              <button
                                className="btn-action btn-unknown"
                                onClick={() => handleMarkUnknown(lead.id)}
                                disabled={actionLoading === lead.id}
                                title="Mark as unknown/spam"
                                aria-label="Mark as unknown"
                              >
                                {actionLoading === lead.id ? (
                                  <span className="spinner">⋯</span>
                                ) : (
                                  <svg className="icon" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                                    <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-8-5a.75.75 0 01.75.75v4.5a.75.75 0 01-1.5 0v-4.5A.75.75 0 0110 5zm0 10a1 1 0 100-2 1 1 0 000 2z" clipRule="evenodd" />
                                  </svg>
                                )}
                              </button>
                            </>
                          ) : lead.status === 'verified' ? (
                            <button
                              className="btn-action btn-sync"
                              onClick={() => handleVerify(lead.id)}
                              disabled={actionLoading === lead.id}
                              title="Re-sync to create contact"
                              aria-label="Sync contact"
                            >
                              {actionLoading === lead.id ? (
                                <span className="spinner">⋯</span>
                              ) : (
                                <svg className="icon" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                                  <path fillRule="evenodd" d="M15.312 11.424a5.5 5.5 0 01-9.201 2.466l-.312-.311h2.433a.75.75 0 000-1.5H3.989a.75.75 0 00-.75.75v4.242a.75.75 0 001.5 0v-2.43l.31.31a7 7 0 0011.712-3.138.75.75 0 00-1.449-.39zm1.23-3.723a.75.75 0 00.219-.53V2.929a.75.75 0 00-1.5 0V5.36l-.31-.31A7 7 0 003.239 8.188a.75.75 0 101.448.389A5.5 5.5 0 0113.89 6.11l.311.31h-2.432a.75.75 0 000 1.5h4.243a.75.75 0 00.53-.219z" clipRule="evenodd" />
                                </svg>
                              )}
                            </button>
                          ) : (
                            <div className="action-placeholder" aria-hidden="true"></div>
                          )}
                          <button
                            className="btn-action btn-delete"
                            onClick={() => handleDelete(lead.id, lead.name)}
                            disabled={actionLoading === lead.id}
                            title="Permanently delete this lead"
                            aria-label="Delete lead"
                          >
                            {actionLoading === lead.id ? (
                              <span className="spinner">⋯</span>
                            ) : (
                              <svg className="icon" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                                <path fillRule="evenodd" d="M8.75 1A2.75 2.75 0 006 3.75v.443c-.795.077-1.584.176-2.365.298a.75.75 0 10.23 1.482l.149-.022.841 10.518A2.75 2.75 0 007.596 19h4.807a2.75 2.75 0 002.742-2.53l.841-10.52.149.023a.75.75 0 00.23-1.482A41.03 41.03 0 0014 4.193V3.75A2.75 2.75 0 0011.25 1h-2.5zM10 4c.84 0 1.673.025 2.5.075V3.75c0-.69-.56-1.25-1.25-1.25h-2.5c-.69 0-1.25.56-1.25 1.25v.325C8.327 4.025 9.16 4 10 4zM8.58 7.72a.75.75 0 00-1.5.06l.3 7.5a.75.75 0 101.5-.06l-.3-7.5zm4.34.06a.75.75 0 10-1.5-.06l-.3 7.5a.75.75 0 101.5.06l.3-7.5z" clipRule="evenodd" />
                              </svg>
                            )}
                          </button>
                        </div>
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
