import { useState, useEffect } from 'react';
import { api } from '../api/client';
import './EditContactModal.css';

export default function EditContactModal({ contact, onSuccess, onCancel }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [formData, setFormData] = useState({
    name: contact?.name || '',
    email: contact?.email || '',
    phone: contact?.phone || '',
    // Profile fields
    location: contact?.location || '',
    company: contact?.company || '',
    role: contact?.role || '',
    notes: contact?.notes || '',
  });
  const [aliases, setAliases] = useState([]);
  const [loadingAliases, setLoadingAliases] = useState(true);
  const [newAlias, setNewAlias] = useState({ alias_type: 'email', value: '' });
  const [addingAlias, setAddingAlias] = useState(false);

  useEffect(() => {
    if (contact?.id) {
      fetchAliases();
    }
  }, [contact?.id]);

  const fetchAliases = async () => {
    setLoadingAliases(true);
    try {
      const data = await api.getContactAliases(contact.id);
      setAliases(data || []);
    } catch (err) {
      console.error('Failed to fetch aliases:', err);
    } finally {
      setLoadingAliases(false);
    }
  };

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData(prev => ({ ...prev, [name]: value }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');

    try {
      await api.updateContact(contact.id, {
        name: formData.name || null,
        email: formData.email || null,
        phone: formData.phone || null,
        // Profile fields
        location: formData.location || null,
        company: formData.company || null,
        role: formData.role || null,
        notes: formData.notes || null,
      });
      onSuccess();
    } catch (err) {
      setError(err.message || 'Failed to update contact');
      setLoading(false);
    }
  };

  const handleAddAlias = async () => {
    if (!newAlias.value.trim()) return;
    
    setAddingAlias(true);
    setError('');
    
    try {
      const alias = await api.addContactAlias(contact.id, {
        alias_type: newAlias.alias_type,
        value: newAlias.value.trim(),
        is_primary: false,
      });
      setAliases(prev => [...prev, alias]);
      setNewAlias({ alias_type: 'email', value: '' });
    } catch (err) {
      setError(err.message || 'Failed to add alias');
    } finally {
      setAddingAlias(false);
    }
  };

  const handleRemoveAlias = async (aliasId) => {
    try {
      await api.removeContactAlias(contact.id, aliasId);
      setAliases(prev => prev.filter(a => a.id !== aliasId));
    } catch (err) {
      setError(err.message || 'Failed to remove alias');
    }
  };

  const handleSetPrimary = async (aliasId, aliasType) => {
    try {
      await api.setPrimaryAlias(contact.id, aliasId);
      // Update local state
      setAliases(prev => prev.map(a => ({
        ...a,
        is_primary: a.id === aliasId ? true : (a.alias_type === aliasType ? false : a.is_primary)
      })));
      // Update form data with new primary value
      const alias = aliases.find(a => a.id === aliasId);
      if (alias) {
        if (aliasType === 'email') setFormData(prev => ({ ...prev, email: alias.value }));
        if (aliasType === 'phone') setFormData(prev => ({ ...prev, phone: alias.value }));
        if (aliasType === 'name') setFormData(prev => ({ ...prev, name: alias.value }));
      }
    } catch (err) {
      setError(err.message || 'Failed to set primary alias');
    }
  };

  const groupedAliases = {
    email: aliases.filter(a => a.alias_type === 'email'),
    phone: aliases.filter(a => a.alias_type === 'phone'),
    name: aliases.filter(a => a.alias_type === 'name'),
  };

  return (
    <div className="modal-overlay" onClick={onCancel}>
      <div className="modal edit-contact-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Edit Contact</h2>
          <button className="close-btn" onClick={onCancel} disabled={loading}>×</button>
        </div>

        <form onSubmit={handleSubmit}>
          <div className="modal-body">
            {error && <div className="error-message">{error}</div>}

            <div className="form-section">
              <h3>Contact Information</h3>
              
              <div className="form-group">
                <label htmlFor="name">Name</label>
                <input
                  type="text"
                  id="name"
                  name="name"
                  value={formData.name}
                  onChange={handleChange}
                  placeholder="Contact name"
                />
              </div>

              <div className="form-group">
                <label htmlFor="email">Primary Email</label>
                <input
                  type="email"
                  id="email"
                  name="email"
                  value={formData.email}
                  onChange={handleChange}
                  placeholder="primary@email.com"
                />
              </div>

              <div className="form-group">
                <label htmlFor="phone">Primary Phone</label>
                <input
                  type="tel"
                  id="phone"
                  name="phone"
                  value={formData.phone}
                  onChange={handleChange}
                  placeholder="+1 555-123-4567"
                />
              </div>
            </div>

            <div className="form-section">
              <h3>Profile Information</h3>

              <div className="form-row">
                <div className="form-group">
                  <label htmlFor="location">Location</label>
                  <input
                    type="text"
                    id="location"
                    name="location"
                    value={formData.location}
                    onChange={handleChange}
                    placeholder="City, State"
                  />
                </div>

                <div className="form-group">
                  <label htmlFor="company">Company</label>
                  <input
                    type="text"
                    id="company"
                    name="company"
                    value={formData.company}
                    onChange={handleChange}
                    placeholder="Company name"
                  />
                </div>
              </div>

              <div className="form-group">
                <label htmlFor="role">Role / Title</label>
                <input
                  type="text"
                  id="role"
                  name="role"
                  value={formData.role}
                  onChange={handleChange}
                  placeholder="Job title or role"
                />
              </div>

              <div className="form-group">
                <label htmlFor="notes">Notes</label>
                <textarea
                  id="notes"
                  name="notes"
                  value={formData.notes}
                  onChange={handleChange}
                  placeholder="Add notes about this contact..."
                  rows={4}
                />
              </div>
            </div>

            <div className="form-section aliases-section">
              <h3>Additional Identifiers (Aliases)</h3>
              <p className="section-description">
                Add alternate emails, phone numbers, or name spellings for this contact.
              </p>

              {loadingAliases ? (
                <div className="loading-aliases">Loading aliases...</div>
              ) : (
                <>
                  {/* Email Aliases */}
                  {groupedAliases.email.length > 0 && (
                    <div className="alias-group">
                      <h4>Emails</h4>
                      <div className="alias-list">
                        {groupedAliases.email.map(alias => (
                          <div key={alias.id} className={`alias-item ${alias.is_primary ? 'primary' : ''}`}>
                            <span className="alias-value">{alias.value}</span>
                            {alias.is_primary ? (
                              <span className="primary-badge">Primary</span>
                            ) : (
                              <div className="alias-actions">
                                <button
                                  type="button"
                                  className="btn-set-primary"
                                  onClick={() => handleSetPrimary(alias.id, 'email')}
                                  title="Set as primary"
                                >
                                  Set Primary
                                </button>
                                <button
                                  type="button"
                                  className="btn-remove-alias"
                                  onClick={() => handleRemoveAlias(alias.id)}
                                  title="Remove"
                                >
                                  ×
                                </button>
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Phone Aliases */}
                  {groupedAliases.phone.length > 0 && (
                    <div className="alias-group">
                      <h4>Phone Numbers</h4>
                      <div className="alias-list">
                        {groupedAliases.phone.map(alias => (
                          <div key={alias.id} className={`alias-item ${alias.is_primary ? 'primary' : ''}`}>
                            <span className="alias-value">{alias.value}</span>
                            {alias.is_primary ? (
                              <span className="primary-badge">Primary</span>
                            ) : (
                              <div className="alias-actions">
                                <button
                                  type="button"
                                  className="btn-set-primary"
                                  onClick={() => handleSetPrimary(alias.id, 'phone')}
                                  title="Set as primary"
                                >
                                  Set Primary
                                </button>
                                <button
                                  type="button"
                                  className="btn-remove-alias"
                                  onClick={() => handleRemoveAlias(alias.id)}
                                  title="Remove"
                                >
                                  ×
                                </button>
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Name Aliases */}
                  {groupedAliases.name.length > 0 && (
                    <div className="alias-group">
                      <h4>Name Variations</h4>
                      <div className="alias-list">
                        {groupedAliases.name.map(alias => (
                          <div key={alias.id} className={`alias-item ${alias.is_primary ? 'primary' : ''}`}>
                            <span className="alias-value">{alias.value}</span>
                            {alias.is_primary ? (
                              <span className="primary-badge">Primary</span>
                            ) : (
                              <div className="alias-actions">
                                <button
                                  type="button"
                                  className="btn-set-primary"
                                  onClick={() => handleSetPrimary(alias.id, 'name')}
                                  title="Set as primary"
                                >
                                  Set Primary
                                </button>
                                <button
                                  type="button"
                                  className="btn-remove-alias"
                                  onClick={() => handleRemoveAlias(alias.id)}
                                  title="Remove"
                                >
                                  ×
                                </button>
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Add New Alias */}
                  <div className="add-alias-form">
                    <select
                      value={newAlias.alias_type}
                      onChange={(e) => setNewAlias(prev => ({ ...prev, alias_type: e.target.value }))}
                      disabled={addingAlias}
                    >
                      <option value="email">Email</option>
                      <option value="phone">Phone</option>
                      <option value="name">Name</option>
                    </select>
                    <input
                      type="text"
                      value={newAlias.value}
                      onChange={(e) => setNewAlias(prev => ({ ...prev, value: e.target.value }))}
                      placeholder={`Add ${newAlias.alias_type}...`}
                      disabled={addingAlias}
                    />
                    <button
                      type="button"
                      className="btn-add-alias"
                      onClick={handleAddAlias}
                      disabled={addingAlias || !newAlias.value.trim()}
                    >
                      {addingAlias ? 'Adding...' : 'Add'}
                    </button>
                  </div>
                </>
              )}
            </div>
          </div>

          <div className="modal-footer">
            <button type="button" className="btn-cancel" onClick={onCancel} disabled={loading}>
              Cancel
            </button>
            <button type="submit" className="btn-save" disabled={loading}>
              {loading ? 'Saving...' : 'Save Changes'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

