import { useState } from 'react';
import './DeleteContactModal.css';

export default function DeleteContactModal({ contact, onConfirm, onCancel, isDeleting }) {
  const [confirmText, setConfirmText] = useState('');
  
  const canDelete = confirmText === 'DELETE';
  
  const handleSubmit = (e) => {
    e.preventDefault();
    if (canDelete && !isDeleting) {
      onConfirm();
    }
  };

  return (
    <div className="modal-overlay" onClick={onCancel}>
      <div className="modal delete-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>🗑️ Delete Contact</h2>
          <button className="close-btn" onClick={onCancel}>×</button>
        </div>
        
        <div className="modal-body">
          <div className="warning-box">
            <span className="warning-icon">⚠️</span>
            <p>You are about to delete this contact. This action will:</p>
            <ul>
              <li>Remove the contact from your contacts list</li>
              <li>Preserve all conversation history (it won't be deleted)</li>
              <li>Be reversible by an admin if needed</li>
            </ul>
          </div>
          
          <div className="contact-preview">
            <div className="contact-avatar">
              {(contact.name || 'U')[0].toUpperCase()}
            </div>
            <div className="contact-info">
              <strong>{contact.name || 'Unknown'}</strong>
              <span>{contact.email || contact.phone_number || 'No contact info'}</span>
            </div>
          </div>
          
          <form onSubmit={handleSubmit}>
            <div className="confirm-input-group">
              <label>Type <strong>DELETE</strong> to confirm:</label>
              <input
                type="text"
                value={confirmText}
                onChange={(e) => setConfirmText(e.target.value)}
                placeholder="DELETE"
                autoFocus
                disabled={isDeleting}
              />
            </div>
            
            <div className="modal-actions">
              <button 
                type="button" 
                className="btn-cancel" 
                onClick={onCancel}
                disabled={isDeleting}
              >
                Cancel
              </button>
              <button 
                type="submit" 
                className="btn-delete"
                disabled={!canDelete || isDeleting}
              >
                {isDeleting ? 'Deleting...' : 'Delete Contact'}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}
