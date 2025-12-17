import { useState, useCallback } from 'react';
import { api } from '../api/client';
import { useFetchData } from '../hooks/useFetchData';
import { useAuth } from '../context/AuthContext';
import { LoadingState, EmptyState, ErrorState } from '../components/ui';
import './Contacts.css';

export default function Contacts() {
  const { user, selectedTenantId } = useAuth();
  const [search, setSearch] = useState('');

  const fetchContacts = useCallback(async () => {
    try {
      const data = await api.getContacts();
      return Array.isArray(data) ? data : data.contacts || [];
    } catch (err) {
      // If it's a "Not Found" error, treat as empty (no contacts yet)
      if (err.message?.includes('Not Found') || err.message?.includes('not found')) {
        return [];
      }
      // Re-throw other errors
      throw err;
    }
  }, []);

  const { data: contacts, loading, error, refetch } = useFetchData(fetchContacts, { defaultValue: [] });

  // Check if global admin without tenant selected
  const needsTenant = user?.is_global_admin && !selectedTenantId;

  const filteredContacts = contacts.filter(contact => 
    (contact.name || '').toLowerCase().includes(search.toLowerCase()) ||
    (contact.phone_number || '').includes(search) ||
    (contact.email || '').toLowerCase().includes(search.toLowerCase())
  );

  if (needsTenant) {
    return (
      <div className="contacts-page">
        <EmptyState
          icon="👥"
          title="Select a tenant to view contacts"
          description="Please select a tenant from the dropdown above to view their contacts."
        />
      </div>
    );
  }

  if (loading) {
    return <LoadingState message="Loading contacts..." fullPage />;
  }

  if (error) {
    // Check if error is about tenant context
    if (error.includes('Tenant context required') || error.includes('Tenant context')) {
      return (
        <div className="contacts-page">
          <EmptyState
            icon="👥"
            title="Select a tenant to view contacts"
            description="Please select a tenant from the dropdown above to view their contacts."
          />
        </div>
      );
    }
    // Check if it's a "Not Found" error - treat as empty
    if (error.includes('Not Found') || error.includes('not found')) {
      // Show empty state instead of error
      return (
        <div className="contacts-page">
          <div className="page-header">
            <h1>Contacts</h1>
            <div className="search-box">
              <input
                type="text"
                placeholder="Search contacts..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                disabled
              />
            </div>
          </div>
          <EmptyState 
            icon="👥"
            title="No verified contacts yet"
            description="Contacts will appear here once they opt in through the chatbot."
          />
        </div>
      );
    }
    return (
      <div className="contacts-page">
        <ErrorState message={error} onRetry={refetch} />
      </div>
    );
  }

  return (
    <div className="contacts-page">
      <div className="page-header">
        <h1>Contacts</h1>
        <div className="search-box">
          <input
            type="text"
            placeholder="Search contacts..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
      </div>

      {contacts.length === 0 ? (
        <EmptyState 
          icon="👥"
          title="No verified contacts yet"
          description="Contacts will appear here once they opt in through the chatbot."
        />
      ) : (
        <div className="contacts-table-container">
          <table className="contacts-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Phone</th>
                <th>Email</th>
                <th>Status</th>
                <th>Added</th>
              </tr>
            </thead>
            <tbody>
              {filteredContacts.map((contact) => (
                <tr key={contact.id}>
                  <td>
                    <div className="contact-name">
                      <div className="avatar">
                        {(contact.name || 'U')[0].toUpperCase()}
                      </div>
                      {contact.name || 'Unknown'}
                    </div>
                  </td>
                  <td>{contact.phone_number}</td>
                  <td>{contact.email || '-'}</td>
                  <td>
                    <span className={`status ${contact.opt_in_status || 'verified'}`}>
                      {contact.opt_in_status || 'Verified'}
                    </span>
                  </td>
                  <td>{new Date(contact.created_at).toLocaleDateString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
          
          {filteredContacts.length === 0 && search && (
            <EmptyState 
              icon="🔍"
              title="No matches found"
              description={`No contacts match "${search}". Try a different search term.`}
            />
          )}
        </div>
      )}
    </div>
  );
}
