import { useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api/client';
import { useFetchData } from '../hooks/useFetchData';
import { useAuth } from '../context/AuthContext';
import { LoadingState, EmptyState, ErrorState } from '../components/ui';
import './UnknownLeads.css';

export default function UnknownLeads() {
  const { user, selectedTenantId } = useAuth();
  const navigate = useNavigate();
  const [search, setSearch] = useState('');

  const fetchUnknownLeads = useCallback(async () => {
    const data = await api.getLeads({ status: 'unknown' });
    return Array.isArray(data) ? data : data.leads || [];
  }, []);

  const { data: leads, loading, error, refetch } = useFetchData(fetchUnknownLeads, { defaultValue: [] });

  const needsTenant = user?.is_global_admin && !selectedTenantId;

  const filteredLeads = leads.filter(lead =>
    (lead.name || '').toLowerCase().includes(search.toLowerCase()) ||
    (lead.phone || '').includes(search) ||
    (lead.email || '').toLowerCase().includes(search.toLowerCase())
  );

  const handleViewConversation = (lead) => {
    navigate(`/unknown/${lead.id}`);
  };

  const handleMarkVerified = async (leadId) => {
    try {
      await api.updateLeadStatus(leadId, 'verified');
      refetch();
    } catch (err) {
      console.error('Failed to verify lead:', err);
    }
  };

  const handleDelete = async (leadId, leadName) => {
    if (!confirm(`Are you sure you want to delete "${leadName || 'this lead'}"? This action cannot be undone.`)) {
      return;
    }
    
    try {
      await api.deleteLead(leadId);
      refetch();
    } catch (err) {
      console.error('Failed to delete lead:', err);
    }
  };

  if (needsTenant) {
    return (
      <div className="unknown-leads-page">
        <EmptyState
          icon="❓"
          title="Select a tenant"
          description="Please select a tenant from the dropdown above."
        />
      </div>
    );
  }

  if (loading) {
    return <LoadingState message="Loading unknown leads..." fullPage />;
  }

  if (error) {
    return (
      <div className="unknown-leads-page">
        <ErrorState message={error} onRetry={refetch} />
      </div>
    );
  }

  return (
    <div className="unknown-leads-page">
      <div className="page-header">
        <h1>Unknown Leads</h1>
        <p className="page-description">
          Leads marked as unknown - review their conversations to verify or dismiss.
        </p>
        <div className="search-box">
          <input
            type="text"
            placeholder="Search unknown leads..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
      </div>

      {leads.length === 0 ? (
        <EmptyState
          icon="✅"
          title="No unknown leads"
          description="All leads have been verified or are pending review."
        />
      ) : (
        <div className="leads-table-container">
          <table className="leads-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Email</th>
                <th>Phone</th>
                <th>Date</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredLeads.map((lead) => (
                <tr key={lead.id}>
                  <td>{lead.name || 'Unknown'}</td>
                  <td>{lead.email || '-'}</td>
                  <td>{lead.phone || '-'}</td>
                  <td>{new Date(lead.created_at).toLocaleDateString()}</td>
                  <td className="actions">
                    <button
                      className="btn-view"
                      onClick={() => handleViewConversation(lead)}
                    >
                      View Chat
                    </button>
                    <button
                      className="btn-verify"
                      onClick={() => handleMarkVerified(lead.id)}
                    >
                      ✓ Verify
                    </button>
                    <button
                      className="btn-delete"
                      onClick={() => handleDelete(lead.id, lead.name)}
                    >
                      ✕ Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {filteredLeads.length === 0 && search && (
            <EmptyState
              icon="🔍"
              title="No matches found"
              description={`No leads match "${search}".`}
            />
          )}
        </div>
      )}
    </div>
  );
}
