import { useState, useEffect, useCallback } from 'react';
import { api } from '../api/client';
import { useAuth } from '../context/AuthContext';
import { useFetchData } from '../hooks/useFetchData';
import InboxConversationList from '../components/InboxConversationList';
import InboxConversationDetail from '../components/InboxConversationDetail';
import { LoadingState, EmptyState, ErrorState } from '../components/ui';
import './Inbox.css';

const PAGE_SIZE = 50;

export default function Inbox() {
  const { user, selectedTenantId } = useAuth();
  const needsTenant = user?.is_global_admin && !selectedTenantId;

  const [selectedConversationId, setSelectedConversationId] = useState(null);
  const [filters, setFilters] = useState({ channel: '', status: '', search: '' });
  const [page, setPage] = useState(0);

  // Reset selection when filters or tenant change
  useEffect(() => {
    setSelectedConversationId(null);
    setPage(0);
  }, [filters.channel, filters.status, filters.search, selectedTenantId]);

  const fetchConversations = useCallback(async () => {
    const params = { skip: page * PAGE_SIZE, limit: PAGE_SIZE };
    if (filters.channel) params.channel = filters.channel;
    if (filters.status) params.status = filters.status;
    if (filters.search) params.search = filters.search;
    return api.getInboxConversations(params);
  }, [page, filters]);

  const { data: listData, loading, error, refetch } = useFetchData(fetchConversations, {
    defaultValue: { conversations: [], total: 0 },
    immediate: !needsTenant,
    deps: [selectedTenantId, page, filters.channel, filters.status, filters.search],
  });

  // Auto-refresh list every 30s
  useEffect(() => {
    if (needsTenant) return;
    const interval = setInterval(refetch, 30000);
    return () => clearInterval(interval);
  }, [refetch, needsTenant]);

  const handleLoadMore = () => {
    setPage((p) => p + 1);
  };

  if (needsTenant) {
    return (
      <div className="inbox-page">
        <EmptyState
          icon="DATA"
          title="Select a tenant to view inbox"
          description="Please select a tenant from the dropdown above."
        />
      </div>
    );
  }

  return (
    <div className="inbox-page">
      <div className="inbox-list-panel">
        <InboxConversationList
          conversations={listData.conversations}
          total={listData.total}
          selectedId={selectedConversationId}
          onSelect={setSelectedConversationId}
          filters={filters}
          onFilterChange={setFilters}
          loading={loading}
          onLoadMore={handleLoadMore}
        />
      </div>
      <div className="inbox-detail-panel">
        {selectedConversationId ? (
          <InboxConversationDetail
            conversationId={selectedConversationId}
            onStatusChange={refetch}
          />
        ) : (
          <div className="inbox-detail-placeholder">
            <div className="inbox-detail-placeholder-content">
              <span className="inbox-detail-placeholder-icon">&#9993;</span>
              <h3>Select a conversation</h3>
              <p>Choose a conversation from the left to view messages and reply.</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
