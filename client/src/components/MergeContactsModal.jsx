import { useState, useEffect } from 'react';
import { api } from '../api/client';
import './MergeContactsModal.css';

export default function MergeContactsModal({ contacts, onSuccess, onCancel }) {
  const [step, setStep] = useState(1); // 1: Select Primary, 2: Resolve Conflicts, 3: Confirm
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [preview, setPreview] = useState(null);
  const [primaryContactId, setPrimaryContactId] = useState(null);
  const [fieldResolutions, setFieldResolutions] = useState({});
  const [merging, setMerging] = useState(false);

  // Fetch merge preview on mount
  useEffect(() => {
    fetchPreview();
  }, []);

  const fetchPreview = async () => {
    setLoading(true);
    setError('');
    try {
      const contactIds = contacts.map(c => c.id);
      const data = await api.getMergePreview(contactIds);
      setPreview(data);
      if (data.suggested_primary_id) {
        setPrimaryContactId(data.suggested_primary_id);
      }
      
      // Initialize field resolutions to "primary" for all conflicts
      const initialResolutions = {};
      data.conflicts.forEach(conflict => {
        initialResolutions[conflict.field] = 'primary';
      });
      setFieldResolutions(initialResolutions);
    } catch (err) {
      setError(err.message || 'Failed to get merge preview');
    } finally {
      setLoading(false);
    }
  };

  const handleSelectPrimary = (contactId) => {
    setPrimaryContactId(contactId);
  };

  const handleFieldResolution = (field, value) => {
    setFieldResolutions(prev => ({
      ...prev,
      [field]: value
    }));
  };

  const handleNext = () => {
    if (step === 1) {
      if (!primaryContactId) {
        setError('Please select a primary contact');
        return;
      }
      setError('');
      // Skip conflict step if no conflicts
      if (!preview?.conflicts?.length) {
        setStep(3);
      } else {
        setStep(2);
      }
    } else if (step === 2) {
      setStep(3);
    }
  };

  const handleBack = () => {
    setError('');
    if (step === 3 && !preview?.conflicts?.length) {
      setStep(1);
    } else {
      setStep(step - 1);
    }
  };

  const handleMerge = async () => {
    setMerging(true);
    setError('');
    try {
      const secondaryIds = contacts
        .filter(c => c.id !== primaryContactId)
        .map(c => c.id);
      
      await api.mergeContacts(primaryContactId, secondaryIds, fieldResolutions);
      onSuccess();
    } catch (err) {
      console.error('Merge failed:', err);
      setError(err.message || 'Failed to merge contacts');
      setMerging(false);
    }
  };

  const getPrimaryContact = () => contacts.find(c => c.id === primaryContactId);
  const getSecondaryContacts = () => contacts.filter(c => c.id !== primaryContactId);

  const renderStep1 = () => (
    <div className="merge-step">
      <h3>Step 1: Select Primary Contact</h3>
      <p className="step-description">
        Choose which contact will be the primary record. The other contact(s) will be merged into this one.
      </p>
      
      <div className="contact-selection">
        {contacts.map(contact => (
          <label 
            key={contact.id} 
            className={`contact-option ${primaryContactId === contact.id ? 'selected' : ''}`}
          >
            <input
              type="radio"
              name="primary-contact"
              checked={primaryContactId === contact.id}
              onChange={() => handleSelectPrimary(contact.id)}
            />
            <div className="contact-card">
              <div className="contact-avatar">
                {(contact.name || 'U')[0].toUpperCase()}
              </div>
              <div className="contact-details">
                <strong>{contact.name || 'Unknown'}</strong>
                {contact.email && <span>📧 {contact.email}</span>}
                {contact.phone_number && <span>📱 {contact.phone_number}</span>}
                <span className="created-date">
                  Created: {new Date(contact.created_at).toLocaleDateString()}
                </span>
              </div>
              {primaryContactId === contact.id && (
                <span className="primary-badge">Primary</span>
              )}
            </div>
          </label>
        ))}
      </div>
    </div>
  );

  const renderStep2 = () => (
    <div className="merge-step">
      <h3>Step 2: Resolve Conflicts</h3>
      <p className="step-description">
        These contacts have different values for some fields. Choose which value to keep as the primary.
      </p>
      
      {preview?.conflicts?.length === 0 ? (
        <div className="no-conflicts">
          <span>✅</span>
          <p>No conflicts detected! All fields match or are empty.</p>
        </div>
      ) : (
        <div className="conflicts-list">
          {preview?.conflicts?.map(conflict => (
            <div key={conflict.field} className="conflict-item">
              <h4 className="conflict-field">{conflict.field.charAt(0).toUpperCase() + conflict.field.slice(1)}</h4>
              <div className="conflict-options">
                {Object.entries(conflict.values).map(([contactId, value]) => {
                  const contact = contacts.find(c => c.id === parseInt(contactId));
                  const isPrimary = parseInt(contactId) === primaryContactId;
                  const isSelected = fieldResolutions[conflict.field] === (isPrimary ? 'primary' : parseInt(contactId));
                  
                  return (
                    <label 
                      key={contactId}
                      className={`conflict-option ${isSelected ? 'selected' : ''}`}
                    >
                      <input
                        type="radio"
                        name={`conflict-${conflict.field}`}
                        checked={isSelected}
                        onChange={() => handleFieldResolution(
                          conflict.field, 
                          isPrimary ? 'primary' : parseInt(contactId)
                        )}
                      />
                      <div className="option-content">
                        <span className="option-value">{value || '(empty)'}</span>
                        <span className="option-source">
                          from {contact?.name || 'Unknown'}
                          {isPrimary && ' (primary)'}
                        </span>
                      </div>
                    </label>
                  );
                })}
              </div>
              <p className="conflict-note">
                💡 Non-selected values will be saved as aliases
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  );

  const renderStep3 = () => {
    const primary = getPrimaryContact();
    const secondaries = getSecondaryContacts();
    
    return (
      <div className="merge-step">
        <h3>Step 3: Confirm Merge</h3>
        <p className="step-description">
          Review the merge operation before confirming.
        </p>
        
        <div className="merge-summary">
          <div className="summary-section">
            <h4>Primary Contact (will survive)</h4>
            <div className="summary-contact primary">
              <div className="contact-avatar">
                {(primary?.name || 'U')[0].toUpperCase()}
              </div>
              <div className="contact-info">
                <strong>{primary?.name || 'Unknown'}</strong>
                <span>{primary?.email || '-'}</span>
                <span>{primary?.phone_number || '-'}</span>
              </div>
            </div>
          </div>
          
          <div className="merge-arrow">
            <span>⬅️ Merging into</span>
          </div>
          
          <div className="summary-section">
            <h4>Contacts to Merge ({secondaries.length})</h4>
            {secondaries.map(contact => (
              <div key={contact.id} className="summary-contact secondary">
                <div className="contact-avatar secondary">
                  {(contact.name || 'U')[0].toUpperCase()}
                </div>
                <div className="contact-info">
                  <strong>{contact.name || 'Unknown'}</strong>
                  <span>{contact.email || '-'}</span>
                  <span>{contact.phone_number || '-'}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
        
        <div className="merge-effects">
          <h4>What will happen:</h4>
          <ul>
            <li>✅ All conversations will be linked to the primary contact</li>
            <li>✅ Secondary contact values will be saved as aliases</li>
            <li>✅ Merge history will be recorded for audit</li>
            <li>⚠️ Secondary contacts will be marked as merged (hidden from lists)</li>
          </ul>
        </div>
      </div>
    );
  };

  return (
    <div className="modal-overlay" onClick={onCancel}>
      <div className="modal merge-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>🔗 Merge Contacts</h2>
          <button className="close-btn" onClick={onCancel} disabled={merging}>×</button>
        </div>
        
        <div className="modal-body">
          {/* Progress indicator */}
          <div className="merge-progress">
            <div className={`progress-step ${step >= 1 ? 'active' : ''} ${step > 1 ? 'completed' : ''}`}>
              <span className="step-number">1</span>
              <span className="step-label">Select Primary</span>
            </div>
            <div className="progress-line"></div>
            <div className={`progress-step ${step >= 2 ? 'active' : ''} ${step > 2 ? 'completed' : ''}`}>
              <span className="step-number">2</span>
              <span className="step-label">Resolve Conflicts</span>
            </div>
            <div className="progress-line"></div>
            <div className={`progress-step ${step >= 3 ? 'active' : ''}`}>
              <span className="step-number">3</span>
              <span className="step-label">Confirm</span>
            </div>
          </div>
          
          {error && <div className="error-message">{error}</div>}
          
          {loading ? (
            <div className="loading-state">
              <div className="spinner"></div>
              <p>Loading merge preview...</p>
            </div>
          ) : (
            <>
              {step === 1 && renderStep1()}
              {step === 2 && renderStep2()}
              {step === 3 && renderStep3()}
            </>
          )}
        </div>
        
        <div className="modal-footer">
          {step > 1 && (
            <button 
              className="btn-back" 
              onClick={handleBack}
              disabled={merging}
            >
              ← Back
            </button>
          )}
          <div className="footer-right">
            <button 
              className="btn-cancel" 
              onClick={onCancel}
              disabled={merging}
            >
              Cancel
            </button>
            {step < 3 ? (
              <button 
                className="btn-next" 
                onClick={handleNext}
                disabled={loading || !primaryContactId}
              >
                Next →
              </button>
            ) : (
              <button 
                className="btn-merge" 
                onClick={handleMerge}
                disabled={merging}
              >
                {merging ? 'Merging...' : 'Confirm Merge'}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
