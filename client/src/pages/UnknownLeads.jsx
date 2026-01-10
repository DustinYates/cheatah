import { useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api/client';
import { useFetchData } from '../hooks/useFetchData';
import { useAuth } from '../context/AuthContext';
import { LoadingState, EmptyState, ErrorState } from '../components/ui';
import { formatDateTimeParts } from '../utils/dateFormat';
import './UnknownLeads.css';

export default function UnknownLeads() {
  const { user, selectedTenantId } = useAuth();
  const navigate = useNavigate();
  const [search, setSearch] = useState('');
  const [sourceFilter, setSourceFilter] = useState('all'); // 'all', 'voice', 'chat'

  const fetchLeads = useCallback(async () => {
    // Fetch all leads, not just unknown
    const data = await api.getLeads({});
    return Array.isArray(data) ? data : data.leads || [];
  }, []);

  const { data: leads, loading, error, refetch } = useFetchData(fetchLeads, { defaultValue: [] });

  const needsTenant = user?.is_global_admin && !selectedTenantId;

  // Helper to check if lead is from voice call
  const isVoiceLead = (lead) => lead.extra_data?.voice_calls?.length > 0;

  // Filter by search and source
  const filteredLeads = leads.filter(lead => {
    const matchesSearch =
      (lead.name || '').toLowerCase().includes(search.toLowerCase()) ||
      (lead.phone || '').includes(search) ||
      (lead.email || '').toLowerCase().includes(search.toLowerCase());

    const matchesSource =
      sourceFilter === 'all' ||
      (sourceFilter === 'voice' && isVoiceLead(lead)) ||
      (sourceFilter === 'chat' && !isVoiceLead(lead));

    return matchesSearch && matchesSource;
  });

  const handleViewConversation = (lead) => {
    navigate(`/analytics/unknowns/${lead.id}`);
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
        <h1>Leads</h1>
        <p className="page-description">
          All captured leads from chat and voice calls.
        </p>
        <div className="search-filter-row">
          <div className="search-box">
            <input
              type="text"
              placeholder="Search leads..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <div className="source-filter">
            <select
              value={sourceFilter}
              onChange={(e) => setSourceFilter(e.target.value)}
            >
              <option value="all">All Sources</option>
              <option value="voice">📞 Voice Calls</option>
              <option value="chat">💬 Chat</option>
            </select>
          </div>
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
                <th>Source</th>
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
                  <td className="source-cell">
                    {isVoiceLead(lead) ? (
                      <span className="source-icon voice" title="Voice Call">📞</span>
                    ) : (
                      <span className="source-icon chat" title="Chat">💬</span>
                    )}
                  </td>
                  <td>{lead.name || 'Unknown'}</td>
                  <td>{lead.email || '-'}</td>
                  <td>{lead.phone || '-'}</td>
                  <td>{formatDateTimeParts(lead.created_at).date}</td>
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
