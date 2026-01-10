import { useState, useCallback } from 'react';
import { api } from '../api/client';
import { useFetchData } from '../hooks/useFetchData';
import { useAuth } from '../context/AuthContext';
import { LoadingState, EmptyState, ErrorState } from '../components/ui';
import { formatDateTimeParts } from '../utils/dateFormat';
import './Calls.css';

// Format duration as mm:ss
function formatDuration(seconds) {
  if (!seconds) return '-';
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${mins}:${secs.toString().padStart(2, '0')}`;
}

// Format phone number for display
function formatPhone(phone) {
  if (!phone) return '-';
  // Simple US format
  if (phone.length === 12 && phone.startsWith('+1')) {
    return `(${phone.slice(2, 5)}) ${phone.slice(5, 8)}-${phone.slice(8)}`;
  }
  return phone;
}

// Intent display labels
const INTENT_LABELS = {
  pricing_info: { label: 'Pricing', color: '#8b5cf6' },
  hours_location: { label: 'Hours/Location', color: '#06b6d4' },
  booking_request: { label: 'Booking', color: '#10b981' },
  support_request: { label: 'Support', color: '#f59e0b' },
  wrong_number: { label: 'Wrong Number', color: '#ef4444' },
  general_inquiry: { label: 'General', color: '#6b7280' },
  unknown: { label: 'Unknown', color: '#9ca3af' },
};

// Outcome display labels
const OUTCOME_LABELS = {
  lead_created: { label: 'Lead Captured', color: '#10b981' },
  info_provided: { label: 'Info Provided', color: '#3b82f6' },
  booking_requested: { label: 'Booking Requested', color: '#8b5cf6' },
  voicemail: { label: 'Voicemail', color: '#f59e0b' },
  transferred: { label: 'Transferred', color: '#06b6d4' },
  dismissed: { label: 'Dismissed', color: '#ef4444' },
  incomplete: { label: 'Incomplete', color: '#9ca3af' },
};

export default function Calls() {
  const { user, selectedTenantId } = useAuth();
  const [page, setPage] = useState(1);
  const [selectedCall, setSelectedCall] = useState(null);
  const [filters, setFilters] = useState({
    intent: '',
    outcome: '',
    status: '',
  });

  const fetchCalls = useCallback(async () => {
    try {
      const params = { page, page_size: 20 };
      if (filters.intent) params.intent = filters.intent;
      if (filters.outcome) params.outcome = filters.outcome;
      if (filters.status) params.status = filters.status;
      
      const data = await api.getCalls(params);
      return data;
    } catch (err) {
      if (err.message?.includes('Not Found') || err.message?.includes('not found')) {
        return { calls: [], total: 0, page: 1, page_size: 20, has_more: false };
      }
      throw err;
    }
  }, [page, filters]);

  const { data, loading, error, refetch } = useFetchData(fetchCalls, {
    defaultValue: { calls: [], total: 0, page: 1, page_size: 20, has_more: false },
  });

  const { calls, total, has_more } = data;

  const needsTenant = user?.is_global_admin && !selectedTenantId;

  const handleFilterChange = (key, value) => {
    setFilters(prev => ({ ...prev, [key]: value }));
    setPage(1);
  };

  const clearFilters = () => {
    setFilters({ intent: '', outcome: '', status: '' });
    setPage(1);
  };

  const hasActiveFilters = filters.intent || filters.outcome || filters.status;
  const selectedCallDate = selectedCall ? formatDateTimeParts(selectedCall.created_at) : null;

  if (needsTenant) {
    return (
      <div className="calls-page">
        <EmptyState
          icon="📞"
          title="Select a tenant to view calls"
          description="Please select a tenant from the dropdown above to view their call history."
        />
      </div>
    );
  }

  if (loading && calls.length === 0) {
    return <LoadingState message="Loading calls..." fullPage />;
  }

  if (error && calls.length === 0) {
    return (
      <div className="calls-page">
        <ErrorState message={error} onRetry={refetch} />
      </div>
    );
  }

  return (
    <div className="calls-page">
      <div className="page-header">
        <h1>Voice Calls</h1>
        <div className="calls-stats">
          <span className="stat-item">
            <span className="stat-number">{total}</span>
            <span className="stat-label">Total Calls</span>
          </span>
        </div>
      </div>

      {/* Filters */}
      <div className="calls-filters">
        <div className="filter-group">
          <label>Intent</label>
          <select
            value={filters.intent}
            onChange={(e) => handleFilterChange('intent', e.target.value)}
          >
            <option value="">All Intents</option>
            {Object.entries(INTENT_LABELS).map(([key, { label }]) => (
              <option key={key} value={key}>{label}</option>
            ))}
          </select>
        </div>
        <div className="filter-group">
          <label>Outcome</label>
          <select
            value={filters.outcome}
            onChange={(e) => handleFilterChange('outcome', e.target.value)}
          >
            <option value="">All Outcomes</option>
            {Object.entries(OUTCOME_LABELS).map(([key, { label }]) => (
              <option key={key} value={key}>{label}</option>
            ))}
          </select>
        </div>
        <div className="filter-group">
          <label>Status</label>
          <select
            value={filters.status}
            onChange={(e) => handleFilterChange('status', e.target.value)}
          >
            <option value="">All Statuses</option>
            <option value="completed">Completed</option>
            <option value="busy">Busy</option>
            <option value="no-answer">No Answer</option>
            <option value="failed">Failed</option>
          </select>
        </div>
        {hasActiveFilters && (
          <button className="btn-clear-filters" onClick={clearFilters}>
            Clear Filters
          </button>
        )}
      </div>

      {/* Calls Table */}
      {calls.length === 0 ? (
        <EmptyState
          icon="📞"
          title="No calls yet"
          description={hasActiveFilters 
            ? "No calls match your filters. Try adjusting the filters." 
            : "Voice calls will appear here once customers start calling."
          }
        />
      ) : (
        <>
          <div className="calls-table-container">
            <table className="calls-table">
              <thead>
                <tr>
                  <th>Date & Time</th>
                  <th>Caller</th>
                  <th>Name</th>
                  <th>Duration</th>
                  <th>Intent</th>
                  <th>Outcome</th>
                  <th>Status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {calls.map((call) => {
                  const { date, time } = formatDateTimeParts(call.created_at);
                  return (
                    <tr key={call.id} onClick={() => setSelectedCall(call)} className="clickable-row">
                      <td className="date-cell">
                        {date}
                        <span className="time-sub">{time}</span>
                      </td>
                    <td>{formatPhone(call.from_number)}</td>
                    <td className="name-cell">{call.summary?.extracted_fields?.name || '-'}</td>
                    <td>{formatDuration(call.duration)}</td>
                    <td>
                      {call.summary?.intent ? (
                        <span 
                          className="badge intent-badge"
                          style={{ backgroundColor: `${INTENT_LABELS[call.summary.intent]?.color}20`, color: INTENT_LABELS[call.summary.intent]?.color }}
                        >
                          {INTENT_LABELS[call.summary.intent]?.label || call.summary.intent}
                        </span>
                      ) : (
                        <span className="badge badge-empty">-</span>
                      )}
                    </td>
                    <td>
                      {call.summary?.outcome ? (
                        <span 
                          className="badge outcome-badge"
                          style={{ backgroundColor: `${OUTCOME_LABELS[call.summary.outcome]?.color}20`, color: OUTCOME_LABELS[call.summary.outcome]?.color }}
                        >
                          {OUTCOME_LABELS[call.summary.outcome]?.label || call.summary.outcome}
                        </span>
                      ) : (
                        <span className="badge badge-empty">-</span>
                      )}
                    </td>
                    <td>
                      <span className={`badge status-badge status-${call.status}`}>
                        {call.status}
                      </span>
                    </td>
                    <td className="actions-cell" onClick={(e) => e.stopPropagation()}>
                      <button 
                        className="btn-action"
                        onClick={() => setSelectedCall(call)}
                        title="View Details"
                      >
                        👁️
                      </button>
                      {call.recording_url && (
                        <a 
                          href={call.recording_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="btn-action"
                          title="Listen to Recording"
                        >
                          🎧
                        </a>
                      )}
                    </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          <div className="calls-pagination">
            <button
              className="btn-page"
              onClick={() => setPage(p => Math.max(1, p - 1))}
              disabled={page === 1}
            >
              Previous
            </button>
            <span className="page-info">
              Page {page} of {Math.ceil(total / 20) || 1}
            </span>
            <button
              className="btn-page"
              onClick={() => setPage(p => p + 1)}
              disabled={!has_more}
            >
              Next
            </button>
          </div>
        </>
      )}

      {/* Call Detail Modal */}
      {selectedCall && (
        <div className="call-modal-overlay" onClick={() => setSelectedCall(null)}>
          <div className="call-modal" onClick={(e) => e.stopPropagation()}>
            <div className="call-modal-header">
              <h2>Call Details</h2>
              <button className="btn-close" onClick={() => setSelectedCall(null)}>×</button>
            </div>
            <div className="call-modal-body">
              <div className="call-detail-grid">
                <div className="detail-item">
                  <label>Caller</label>
                  <span>{formatPhone(selectedCall.from_number)}</span>
                </div>
                <div className="detail-item">
                  <label>Date & Time</label>
                  <span>
                    {selectedCallDate
                      ? `${selectedCallDate.date} ${selectedCallDate.time} ${selectedCallDate.tzAbbr}`.trim()
                      : '—'}
                  </span>
                </div>
                <div className="detail-item">
                  <label>Duration</label>
                  <span>{formatDuration(selectedCall.duration)}</span>
                </div>
                <div className="detail-item">
                  <label>Status</label>
                  <span className={`badge status-badge status-${selectedCall.status}`}>
                    {selectedCall.status}
                  </span>
                </div>
                {selectedCall.summary?.intent && (
                  <div className="detail-item">
                    <label>Intent</label>
                    <span 
                      className="badge intent-badge"
                      style={{ backgroundColor: `${INTENT_LABELS[selectedCall.summary.intent]?.color}20`, color: INTENT_LABELS[selectedCall.summary.intent]?.color }}
                    >
                      {INTENT_LABELS[selectedCall.summary.intent]?.label}
                    </span>
                  </div>
                )}
                {selectedCall.summary?.outcome && (
                  <div className="detail-item">
                    <label>Outcome</label>
                    <span 
                      className="badge outcome-badge"
                      style={{ backgroundColor: `${OUTCOME_LABELS[selectedCall.summary.outcome]?.color}20`, color: OUTCOME_LABELS[selectedCall.summary.outcome]?.color }}
                    >
                      {OUTCOME_LABELS[selectedCall.summary.outcome]?.label}
                    </span>
                  </div>
                )}
              </div>

              {selectedCall.summary?.summary_text && (
                <div className="call-summary-section">
                  <h3>Summary</h3>
                  <p>{selectedCall.summary.summary_text}</p>
                </div>
              )}

              {selectedCall.summary?.extracted_fields && (
                <div className="call-extracted-section">
                  <h3>Extracted Information</h3>
                  <div className="extracted-grid">
                    {selectedCall.summary.extracted_fields.name && (
                      <div className="extracted-item">
                        <label>Name</label>
                        <span>{selectedCall.summary.extracted_fields.name}</span>
                      </div>
                    )}
                    {selectedCall.summary.extracted_fields.email && (
                      <div className="extracted-item">
                        <label>Email</label>
                        <span>{selectedCall.summary.extracted_fields.email}</span>
                      </div>
                    )}
                    {selectedCall.summary.extracted_fields.reason && (
                      <div className="extracted-item full-width">
                        <label>Reason for Calling</label>
                        <span>{selectedCall.summary.extracted_fields.reason}</span>
                      </div>
                    )}
                    {selectedCall.summary.extracted_fields.urgency && (
                      <div className="extracted-item">
                        <label>Urgency</label>
                        <span className={`urgency-${selectedCall.summary.extracted_fields.urgency}`}>
                          {selectedCall.summary.extracted_fields.urgency}
                        </span>
                      </div>
                    )}
                    {selectedCall.summary.extracted_fields.preferred_callback_time && (
                      <div className="extracted-item">
                        <label>Preferred Callback</label>
                        <span>{selectedCall.summary.extracted_fields.preferred_callback_time}</span>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {selectedCall.recording_url && (
                <div className="call-recording-section">
                  <h3>Recording</h3>
                  <a 
                    href={selectedCall.recording_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="btn-recording"
                  >
                    🎧 Listen to Recording
                  </a>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
