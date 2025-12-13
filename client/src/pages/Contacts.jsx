import { useState, useCallback } from 'react';
import { api } from '../api/client';
import { useFetchData } from '../hooks/useFetchData';
import './Contacts.css';

export default function Contacts() {
  const [search, setSearch] = useState('');

  const fetchContacts = useCallback(async () => {
    const data = await api.getContacts().catch(() => []);
    return Array.isArray(data) ? data : data.contacts || [];
  }, []);

  const { data: contacts, loading } = useFetchData(fetchContacts, { defaultValue: [] });

  const filteredContacts = contacts.filter(contact => 
    (contact.name || '').toLowerCase().includes(search.toLowerCase()) ||
    (contact.phone_number || '').includes(search) ||
    (contact.email || '').toLowerCase().includes(search.toLowerCase())
  );

  if (loading) {
    return <div className="loading">Loading contacts...</div>;
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
        <div className="empty-state">
          <p>No verified contacts yet. Contacts will appear here once they opt in.</p>
        </div>
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
            <div className="no-results">
              No contacts match your search.
            </div>
          )}
        </div>
      )}
    </div>
  );
}
