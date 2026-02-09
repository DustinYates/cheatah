import { useState, useCallback } from 'react';
import { useAuth } from '../context/AuthContext';
import { api } from '../api/client';
import { Send } from 'lucide-react';
import './Support.css';

export default function Support() {
  const { user } = useAuth();
  const [form, setForm] = useState({
    category: 'Bug Report',
    subject: '',
    message: '',
  });
  const [submitting, setSubmitting] = useState(false);
  const [toast, setToast] = useState(null);

  const showToast = useCallback((message, type = 'success') => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 4000);
  }, []);

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (!form.subject.trim() || !form.message.trim()) {
      showToast('Please fill in both subject and message.', 'error');
      return;
    }

    setSubmitting(true);
    try {
      await api.submitSupportRequest(form);
      showToast('Support request sent! We\'ll get back to you soon.');
      setForm({ category: 'Bug Report', subject: '', message: '' });
    } catch (err) {
      showToast(err.message || 'Failed to send request. Please try again.', 'error');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="support-page">
      {toast && (
        <div className={`toast toast-${toast.type}`}>{toast.message}</div>
      )}

      <div className="page-header">
        <h1>Support</h1>
        <p className="subtitle">
          Have an issue or idea? Let us know and we'll get back to you at {user?.email}.
        </p>
      </div>

      <form onSubmit={handleSubmit}>
        <div className="settings-section">
          <div className="form-group">
            <label>Category</label>
            <select
              value={form.category}
              onChange={(e) => setForm({ ...form, category: e.target.value })}
            >
              <option>Bug Report</option>
              <option>Feature Request</option>
              <option>General Question</option>
            </select>
          </div>

          <div className="form-group">
            <label>Subject</label>
            <input
              type="text"
              value={form.subject}
              onChange={(e) => setForm({ ...form, subject: e.target.value })}
              placeholder="Brief description of your issue or request"
            />
          </div>

          <div className="form-group">
            <label>Message</label>
            <textarea
              value={form.message}
              onChange={(e) => setForm({ ...form, message: e.target.value })}
              placeholder="Describe what you'd like or what's broken..."
            />
          </div>

          <div className="form-actions">
            <button
              type="submit"
              className="btn-primary"
              disabled={submitting}
            >
              <Send size={16} />
              {submitting ? 'Sending...' : 'Submit Request'}
            </button>
          </div>
        </div>
      </form>
    </div>
  );
}
