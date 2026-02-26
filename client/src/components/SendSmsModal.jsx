import { useState, useEffect, useRef } from 'react';
import { api } from '../api/client';
import './SendSmsModal.css';

export default function SendSmsModal({ lead, onClose, onSuccess }) {
  const [message, setMessage] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const textareaRef = useRef(null);

  useEffect(() => {
    const handleEscape = (e) => {
      if (e.key === 'Escape' && !loading) onClose();
    };
    document.addEventListener('keydown', handleEscape);
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', handleEscape);
      document.body.style.overflow = '';
    };
  }, [onClose, loading]);

  useEffect(() => {
    textareaRef.current?.focus();
  }, []);

  const handleSend = async (e) => {
    e.preventDefault();
    if (!message.trim() || loading) return;

    setLoading(true);
    setError('');
    setSuccess('');

    try {
      await api.sendManualSms(lead.phone, message.trim());
      setSuccess('Message sent!');
      setTimeout(() => {
        onSuccess?.();
        onClose();
      }, 1000);
    } catch (err) {
      setError(err.message || 'Failed to send SMS');
    } finally {
      setLoading(false);
    }
  };

  const charCount = message.length;
  const segments = Math.ceil(charCount / 160) || 1;

  return (
    <div className="sms-modal-overlay" onClick={loading ? undefined : onClose}>
      <div className="sms-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Text {lead.name || 'Lead'}</h2>
          <button className="close-btn" onClick={onClose} disabled={loading}>×</button>
        </div>

        <form onSubmit={handleSend}>
          <div className="modal-body">
            {error && <div className="error-message">{error}</div>}
            {success && <div className="success-message">{success}</div>}

            <div className="form-group">
              <label>To</label>
              <input type="text" value={lead.phone} disabled />
            </div>

            <div className="form-group">
              <label htmlFor="sms-message">Message</label>
              <textarea
                id="sms-message"
                ref={textareaRef}
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                placeholder="Type your message..."
                maxLength={1600}
                disabled={loading || !!success}
              />
              <div className={`char-count${charCount > 160 ? ' warning' : ''}`}>
                {charCount} / 160{segments > 1 ? ` (${segments} segments)` : ''}
              </div>
            </div>
          </div>

          <div className="modal-footer">
            <button
              type="button"
              className="btn-cancel"
              onClick={onClose}
              disabled={loading}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="btn-send"
              disabled={!message.trim() || loading || !!success}
            >
              {loading ? 'Sending...' : 'Send'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
