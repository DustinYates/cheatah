import { useState, useEffect, useRef } from 'react';
import { api } from '../api/client';
import './SendSmsModal.css';

export default function MassSmsModal({ leads, onClose, onSuccess }) {
  const [message, setMessage] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState(null);
  const textareaRef = useRef(null);

  const recipientCount = leads.filter((l) => l.phone).length;
  const noPhoneCount = leads.length - recipientCount;

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
    if (!message.trim() || loading || recipientCount === 0) return;

    if (!window.confirm(`Send this message to ${recipientCount} contact${recipientCount !== 1 ? 's' : ''}?`)) {
      return;
    }

    setLoading(true);
    setError('');
    setResult(null);

    try {
      const phones = leads.filter((l) => l.phone).map((l) => l.phone);
      const res = await api.sendBulkSms(phones, message.trim());
      setResult(res);
      if (res.sent > 0) {
        setTimeout(() => {
          onSuccess?.();
          onClose();
        }, 2000);
      }
    } catch (err) {
      setError(err.message || 'Failed to send bulk SMS');
    } finally {
      setLoading(false);
    }
  };

  const charCount = message.length;
  const segments = Math.ceil(charCount / 160) || 1;

  return (
    <div className="sms-modal-overlay" onClick={loading ? undefined : onClose}>
      <div className="sms-modal mass-sms-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Mass Text Message</h2>
          <button className="close-btn" onClick={onClose} disabled={loading}>×</button>
        </div>

        <form onSubmit={handleSend}>
          <div className="modal-body">
            {error && <div className="error-message">{error}</div>}
            {result && (
              <div className={result.failed > 0 ? 'error-message' : 'success-message'}>
                Sent: {result.sent}{result.failed > 0 ? `, Failed: ${result.failed}` : ''}
              </div>
            )}

            <div className="mass-sms-recipients">
              <label>Recipients</label>
              <div className="mass-sms-summary">
                <span className="mass-sms-count">{recipientCount}</span> contact{recipientCount !== 1 ? 's' : ''} with phone numbers
                {noPhoneCount > 0 && (
                  <span className="mass-sms-skipped"> ({noPhoneCount} skipped — no phone)</span>
                )}
              </div>
              <div className="mass-sms-list">
                {leads.filter((l) => l.phone).map((l) => (
                  <span key={l.id} className="mass-sms-chip">{l.name || l.phone}</span>
                ))}
              </div>
            </div>

            <div className="form-group">
              <label htmlFor="mass-sms-message">Message</label>
              <textarea
                id="mass-sms-message"
                ref={textareaRef}
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                placeholder="Type your message..."
                maxLength={1600}
                disabled={loading || !!result}
              />
              <div className={`char-count${charCount > 160 ? ' warning' : ''}`}>
                {charCount} / 160{segments > 1 ? ` (${segments} segments)` : ''}
              </div>
            </div>
          </div>

          <div className="modal-footer">
            <button type="button" className="btn-cancel" onClick={onClose} disabled={loading}>
              Cancel
            </button>
            <button
              type="submit"
              className="btn-send"
              disabled={!message.trim() || loading || !!result || recipientCount === 0}
            >
              {loading ? 'Sending...' : `Send to ${recipientCount}`}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
