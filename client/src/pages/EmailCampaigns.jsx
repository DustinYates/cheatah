import { useState, useEffect, useCallback } from 'react';
import { useAuth } from '../context/AuthContext';
import { LoadingState, ErrorState, EmptyState } from '../components/ui';
import './CampaignSettings.css';

const API_BASE = '/api/v1';

const STATUS_COLORS = {
  draft: '',
  scheduled: 'sms-status-badge--modified',
  sending: 'sms-status-badge--active',
  paused: 'sms-status-badge--inactive',
  completed: 'sms-status-badge--active',
};

const RECIPIENT_STATUS_COLORS = {
  pending: '',
  generating: 'sms-status-badge--modified',
  sent: 'sms-status-badge--active',
  failed: 'sms-status-badge--inactive',
  skipped: 'sms-status-badge--inactive',
};

function formatDateTime(isoString) {
  if (!isoString) return '\u2014';
  const d = new Date(isoString);
  return d.toLocaleString(undefined, {
    month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit',
  });
}

export default function EmailCampaigns() {
  const { token, user, selectedTenantId } = useAuth();
  const [campaigns, setCampaigns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [toast, setToast] = useState(null);

  // Detail view
  const [selectedCampaign, setSelectedCampaign] = useState(null);
  const [recipients, setRecipients] = useState([]);
  const [loadingDetail, setLoadingDetail] = useState(false);

  // Create form
  const [showCreate, setShowCreate] = useState(false);
  const [createForm, setCreateForm] = useState({
    name: '', subject_template: '', email_prompt_instructions: '',
    from_email: '', reply_to: '', unsubscribe_url: '', physical_address: '',
    batch_size: 50, batch_delay_seconds: 300,
  });
  const [creating, setCreating] = useState(false);

  // Add recipients
  const [showAddRecipients, setShowAddRecipients] = useState(false);
  const [recipientText, setRecipientText] = useState('');
  const [addingRecipients, setAddingRecipients] = useState(false);

  // Preview
  const [preview, setPreview] = useState(null);
  const [previewing, setPreviewing] = useState(false);

  // Sending
  const [actionLoading, setActionLoading] = useState(false);

  const showToast = useCallback((message, type = 'success') => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 3000);
  }, []);

  const buildHeaders = useCallback((includeContentType = false) => {
    const headers = { 'Authorization': `Bearer ${token}` };
    if (includeContentType) headers['Content-Type'] = 'application/json';
    if (user?.is_global_admin && selectedTenantId) {
      headers['X-Tenant-Id'] = selectedTenantId.toString();
    }
    return headers;
  }, [token, user?.is_global_admin, selectedTenantId]);

  // ── Fetch campaigns ─────────────────────────────────────────────────

  const fetchCampaigns = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/email-campaigns`, { headers: buildHeaders() });
      if (res.ok) {
        setCampaigns(await res.json());
      } else {
        const data = await res.json().catch(() => ({}));
        setError(data.detail || 'Failed to load campaigns');
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [buildHeaders]);

  useEffect(() => { fetchCampaigns(); }, [fetchCampaigns]);

  // ── Fetch campaign detail ───────────────────────────────────────────

  const openCampaign = async (campaignId) => {
    setLoadingDetail(true);
    setPreview(null);
    try {
      const [campRes, recipRes] = await Promise.all([
        fetch(`${API_BASE}/email-campaigns/${campaignId}`, { headers: buildHeaders() }),
        fetch(`${API_BASE}/email-campaigns/${campaignId}/recipients`, { headers: buildHeaders() }),
      ]);
      if (campRes.ok) setSelectedCampaign(await campRes.json());
      if (recipRes.ok) setRecipients(await recipRes.json());
    } catch (err) {
      showToast(err.message, 'error');
    } finally {
      setLoadingDetail(false);
    }
  };

  const closeCampaign = () => {
    setSelectedCampaign(null);
    setRecipients([]);
    setPreview(null);
    setShowAddRecipients(false);
  };

  // ── Create campaign ─────────────────────────────────────────────────

  const handleCreate = async (e) => {
    e.preventDefault();
    if (!createForm.name || !createForm.subject_template || !createForm.unsubscribe_url || !createForm.physical_address) {
      showToast('Please fill in all required fields', 'error');
      return;
    }
    setCreating(true);
    try {
      const res = await fetch(`${API_BASE}/email-campaigns`, {
        method: 'POST',
        headers: buildHeaders(true),
        body: JSON.stringify(createForm),
      });
      if (res.ok) {
        showToast('Campaign created');
        setShowCreate(false);
        setCreateForm({
          name: '', subject_template: '', email_prompt_instructions: '',
          from_email: '', reply_to: '', unsubscribe_url: '', physical_address: '',
          batch_size: 50, batch_delay_seconds: 300,
        });
        fetchCampaigns();
      } else {
        const data = await res.json().catch(() => ({}));
        showToast(data.detail || 'Failed to create campaign', 'error');
      }
    } catch (err) {
      showToast(err.message, 'error');
    } finally {
      setCreating(false);
    }
  };

  // ── Add recipients ──────────────────────────────────────────────────

  const handleAddRecipients = async () => {
    if (!recipientText.trim()) return;
    setAddingRecipients(true);
    try {
      // Parse JSON array or one-per-line email format
      let parsed;
      const trimmed = recipientText.trim();
      if (trimmed.startsWith('[')) {
        parsed = JSON.parse(trimmed);
      } else {
        // Simple format: one email per line, or "name <email>" per line
        parsed = trimmed.split('\n').filter(l => l.trim()).map(line => {
          const emailMatch = line.match(/([^\s<]+@[^\s>]+)/);
          const email = emailMatch ? emailMatch[1] : line.trim();
          const namePart = line.replace(email, '').replace(/[<>]/g, '').trim();
          return { email, name: namePart || undefined };
        });
      }

      const res = await fetch(`${API_BASE}/email-campaigns/${selectedCampaign.id}/recipients`, {
        method: 'POST',
        headers: buildHeaders(true),
        body: JSON.stringify(parsed),
      });
      if (res.ok) {
        const data = await res.json();
        showToast(`Added ${data.added} recipients`);
        setRecipientText('');
        setShowAddRecipients(false);
        openCampaign(selectedCampaign.id);
      } else {
        const data = await res.json().catch(() => ({}));
        showToast(data.detail || 'Failed to add recipients', 'error');
      }
    } catch (err) {
      showToast('Invalid format: use JSON array or one email per line', 'error');
    } finally {
      setAddingRecipients(false);
    }
  };

  // ── Campaign actions ────────────────────────────────────────────────

  const sendCampaign = async () => {
    if (!confirm('Start sending this campaign? Emails will be generated and sent in batches.')) return;
    setActionLoading(true);
    try {
      const res = await fetch(`${API_BASE}/email-campaigns/${selectedCampaign.id}/send`, {
        method: 'POST', headers: buildHeaders(true),
      });
      if (res.ok) {
        showToast('Campaign sending started');
        openCampaign(selectedCampaign.id);
        fetchCampaigns();
      } else {
        const data = await res.json().catch(() => ({}));
        showToast(data.detail || 'Failed to start campaign', 'error');
      }
    } catch (err) {
      showToast(err.message, 'error');
    } finally {
      setActionLoading(false);
    }
  };

  const pauseCampaign = async () => {
    setActionLoading(true);
    try {
      const res = await fetch(`${API_BASE}/email-campaigns/${selectedCampaign.id}/pause`, {
        method: 'POST', headers: buildHeaders(true),
      });
      if (res.ok) {
        showToast('Campaign paused');
        openCampaign(selectedCampaign.id);
        fetchCampaigns();
      } else {
        const data = await res.json().catch(() => ({}));
        showToast(data.detail || 'Failed to pause campaign', 'error');
      }
    } catch (err) {
      showToast(err.message, 'error');
    } finally {
      setActionLoading(false);
    }
  };

  const deleteCampaign = async () => {
    if (!confirm('Delete this campaign? This cannot be undone.')) return;
    setActionLoading(true);
    try {
      const res = await fetch(`${API_BASE}/email-campaigns/${selectedCampaign.id}`, {
        method: 'DELETE', headers: buildHeaders(),
      });
      if (res.ok || res.status === 204) {
        showToast('Campaign deleted');
        closeCampaign();
        fetchCampaigns();
      } else {
        const data = await res.json().catch(() => ({}));
        showToast(data.detail || 'Failed to delete', 'error');
      }
    } catch (err) {
      showToast(err.message, 'error');
    } finally {
      setActionLoading(false);
    }
  };

  const previewEmail = async () => {
    setPreviewing(true);
    try {
      const res = await fetch(`${API_BASE}/email-campaigns/${selectedCampaign.id}/preview`, {
        method: 'POST', headers: buildHeaders(true),
      });
      if (res.ok) {
        setPreview(await res.json());
      } else {
        const data = await res.json().catch(() => ({}));
        showToast(data.detail || 'Failed to generate preview', 'error');
      }
    } catch (err) {
      showToast(err.message, 'error');
    } finally {
      setPreviewing(false);
    }
  };

  // ── Guards ──────────────────────────────────────────────────────────

  const needsTenant = user?.is_global_admin && !selectedTenantId;
  if (needsTenant) {
    return (
      <div className="campaign-page">
        <EmptyState icon="SMS" title="Select a tenant" description="Please select a tenant from the dropdown above." />
      </div>
    );
  }
  if (loading) return <div className="campaign-page"><LoadingState message="Loading email campaigns..." fullPage /></div>;
  if (error) return <div className="campaign-page"><ErrorState message={error} onRetry={fetchCampaigns} /></div>;

  // ── Detail view ─────────────────────────────────────────────────────

  if (selectedCampaign) {
    const c = selectedCampaign;
    return (
      <div className="campaign-page">
        {toast && <div className={`sms-toast sms-toast--${toast.type}`}>{toast.type === 'success' ? '\u2713' : '!'} {toast.message}</div>}

        <header className="sms-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <button type="button" className="sms-btn sms-btn--ghost" onClick={closeCampaign}>&larr; Back</button>
            <h1 className="sms-header__title">{c.name}</h1>
            <span className={`sms-status-badge ${STATUS_COLORS[c.status] || ''}`}>{c.status}</span>
          </div>
        </header>

        {loadingDetail ? <LoadingState message="Loading..." /> : (
          <div className="sms-cards">
            {/* Campaign Info */}
            <section className="sms-card">
              <div className="sms-card__header">
                <h2 className="sms-card__title">Campaign Details</h2>
                <div style={{ display: 'flex', gap: '8px' }}>
                  {(c.status === 'draft' || c.status === 'paused') && (
                    <>
                      <button type="button" className="sms-btn sms-btn--primary" onClick={sendCampaign} disabled={actionLoading}>
                        {actionLoading ? 'Starting...' : 'Send Campaign'}
                      </button>
                      <button type="button" className="sms-btn sms-btn--secondary" onClick={previewEmail} disabled={previewing}>
                        {previewing ? 'Generating...' : 'Preview Email'}
                      </button>
                    </>
                  )}
                  {(c.status === 'scheduled' || c.status === 'sending') && (
                    <button type="button" className="sms-btn sms-btn--secondary" onClick={pauseCampaign} disabled={actionLoading}>
                      Pause
                    </button>
                  )}
                  {c.status === 'draft' && (
                    <button type="button" className="sms-btn sms-btn--ghost" onClick={deleteCampaign} disabled={actionLoading}>
                      Delete
                    </button>
                  )}
                </div>
              </div>
              <div className="sms-card__body">
                <div className="sms-field"><label className="sms-field__label">Subject Template</label><p>{c.subject_template}</p></div>
                {c.email_prompt_instructions && <div className="sms-field"><label className="sms-field__label">AI Instructions</label><p>{c.email_prompt_instructions}</p></div>}
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '16px' }}>
                  <div className="sms-field"><label className="sms-field__label">Total</label><p style={{ fontSize: '24px', fontWeight: 600 }}>{c.total_recipients}</p></div>
                  <div className="sms-field"><label className="sms-field__label">Sent</label><p style={{ fontSize: '24px', fontWeight: 600, color: '#059669' }}>{c.sent_count}</p></div>
                  <div className="sms-field"><label className="sms-field__label">Failed</label><p style={{ fontSize: '24px', fontWeight: 600, color: '#dc2626' }}>{c.failed_count}</p></div>
                </div>
              </div>
            </section>

            {/* Preview */}
            {preview && (
              <section className="sms-card">
                <div className="sms-card__header">
                  <h2 className="sms-card__title">Email Preview</h2>
                  <button type="button" className="sms-btn sms-btn--ghost" onClick={() => setPreview(null)}>Close</button>
                </div>
                <div className="sms-card__body">
                  <div className="sms-field"><label className="sms-field__label">To</label><p>{preview.recipient_name} &lt;{preview.recipient_email}&gt;</p></div>
                  <div className="sms-field"><label className="sms-field__label">Subject</label><p style={{ fontWeight: 600 }}>{preview.subject}</p></div>
                  <div className="sms-field">
                    <label className="sms-field__label">Body</label>
                    <div style={{ border: '1px solid #e5e7eb', borderRadius: '8px', padding: '16px', background: '#fff' }} dangerouslySetInnerHTML={{ __html: preview.body }} />
                  </div>
                </div>
              </section>
            )}

            {/* Recipients */}
            <section className="sms-card">
              <div className="sms-card__header">
                <h2 className="sms-card__title">Recipients</h2>
                {(c.status === 'draft' || c.status === 'paused') && (
                  <button type="button" className="sms-btn sms-btn--secondary" onClick={() => setShowAddRecipients(!showAddRecipients)}>
                    {showAddRecipients ? 'Cancel' : 'Add Recipients'}
                  </button>
                )}
              </div>
              <div className="sms-card__body" style={{ padding: 0 }}>
                {/* Add Recipients Form */}
                {showAddRecipients && (
                  <div style={{ padding: '16px', borderBottom: '1px solid #e5e7eb' }}>
                    <div className="sms-field">
                      <label className="sms-field__label">Paste recipients</label>
                      <textarea
                        className="sms-textarea"
                        rows={5}
                        value={recipientText}
                        onChange={(e) => setRecipientText(e.target.value)}
                        placeholder={'One per line: email or "Name <email>"\nOr paste a JSON array: [{"email":"a@b.com","name":"Alice","company":"Acme"}]'}
                      />
                    </div>
                    <button type="button" className="sms-btn sms-btn--primary" onClick={handleAddRecipients} disabled={addingRecipients}>
                      {addingRecipients ? 'Adding...' : 'Add'}
                    </button>
                  </div>
                )}

                {/* Recipients Table */}
                {recipients.length === 0 ? (
                  <div className="campaign-enrollments-empty">No recipients added yet.</div>
                ) : (
                  <div className="campaign-enrollments-table-wrapper">
                    <table className="campaign-enrollments-table">
                      <thead>
                        <tr>
                          <th>Email</th>
                          <th>Name</th>
                          <th>Company</th>
                          <th>Status</th>
                          <th>Subject</th>
                          <th>Sent</th>
                        </tr>
                      </thead>
                      <tbody>
                        {recipients.map((r) => (
                          <tr key={r.id}>
                            <td>{r.email}</td>
                            <td>{r.name || '\u2014'}</td>
                            <td>{r.company || '\u2014'}</td>
                            <td><span className={`sms-status-badge ${RECIPIENT_STATUS_COLORS[r.status] || ''}`}>{r.status}</span></td>
                            <td style={{ maxWidth: '200px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.generated_subject || '\u2014'}</td>
                            <td>{formatDateTime(r.sent_at)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </section>
          </div>
        )}
      </div>
    );
  }

  // ── List view ───────────────────────────────────────────────────────

  return (
    <div className="campaign-page">
      {toast && <div className={`sms-toast sms-toast--${toast.type}`}>{toast.type === 'success' ? '\u2713' : '!'} {toast.message}</div>}

      <header className="sms-header">
        <div>
          <h1 className="sms-header__title">Email Outreach</h1>
          <p className="sms-header__subtitle">Create and send AI-generated cold outreach emails using your bot's voice.</p>
        </div>
        <button type="button" className="sms-btn sms-btn--primary" onClick={() => setShowCreate(!showCreate)}>
          {showCreate ? 'Cancel' : 'New Campaign'}
        </button>
      </header>

      {/* Create Form */}
      {showCreate && (
        <section className="sms-card" style={{ marginBottom: '16px' }}>
          <div className="sms-card__header"><h2 className="sms-card__title">New Campaign</h2></div>
          <div className="sms-card__body">
            <form onSubmit={handleCreate}>
              <div className="sms-field">
                <label className="sms-field__label">Campaign Name *</label>
                <input className="sms-input" value={createForm.name} onChange={(e) => setCreateForm(f => ({ ...f, name: e.target.value }))} placeholder="March Cold Outreach" />
              </div>
              <div className="sms-field">
                <label className="sms-field__label">Subject Line Template *</label>
                <input className="sms-input" value={createForm.subject_template} onChange={(e) => setCreateForm(f => ({ ...f, subject_template: e.target.value }))} placeholder="Quick question about your business" />
                <p className="sms-field__hint">The AI can personalize this per recipient.</p>
              </div>
              <div className="sms-field">
                <label className="sms-field__label">AI Instructions</label>
                <textarea className="sms-textarea" rows={3} value={createForm.email_prompt_instructions} onChange={(e) => setCreateForm(f => ({ ...f, email_prompt_instructions: e.target.value }))} placeholder="Mention our March promo: 50% off first month. Focus on how we save them from missed calls." />
                <p className="sms-field__hint">Extra context for the AI when generating emails. Your bot's personality is used automatically.</p>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                <div className="sms-field">
                  <label className="sms-field__label">From Email</label>
                  <input className="sms-input" type="email" value={createForm.from_email} onChange={(e) => setCreateForm(f => ({ ...f, from_email: e.target.value }))} placeholder="Leave blank to use default" />
                </div>
                <div className="sms-field">
                  <label className="sms-field__label">Reply-To</label>
                  <input className="sms-input" type="email" value={createForm.reply_to} onChange={(e) => setCreateForm(f => ({ ...f, reply_to: e.target.value }))} placeholder="Leave blank to use from email" />
                </div>
              </div>
              <div className="sms-field">
                <label className="sms-field__label">Unsubscribe URL *</label>
                <input className="sms-input" value={createForm.unsubscribe_url} onChange={(e) => setCreateForm(f => ({ ...f, unsubscribe_url: e.target.value }))} placeholder="https://yoursite.com/unsubscribe" />
              </div>
              <div className="sms-field">
                <label className="sms-field__label">Physical Address *</label>
                <input className="sms-input" value={createForm.physical_address} onChange={(e) => setCreateForm(f => ({ ...f, physical_address: e.target.value }))} placeholder="123 Main St, City, State 12345" />
                <p className="sms-field__hint">Required by CAN-SPAM. Shown in email footer.</p>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                <div className="sms-field">
                  <label className="sms-field__label">Batch Size</label>
                  <input className="sms-input sms-input--number" type="number" min="1" max="200" value={createForm.batch_size} onChange={(e) => setCreateForm(f => ({ ...f, batch_size: parseInt(e.target.value, 10) || 50 }))} />
                  <p className="sms-field__hint">Emails per batch</p>
                </div>
                <div className="sms-field">
                  <label className="sms-field__label">Batch Delay (seconds)</label>
                  <input className="sms-input sms-input--number" type="number" min="60" max="3600" value={createForm.batch_delay_seconds} onChange={(e) => setCreateForm(f => ({ ...f, batch_delay_seconds: parseInt(e.target.value, 10) || 300 }))} />
                  <p className="sms-field__hint">Wait between batches</p>
                </div>
              </div>
              <div className="sms-actions">
                <button type="submit" className="sms-btn sms-btn--primary" disabled={creating}>
                  {creating ? 'Creating...' : 'Create Campaign'}
                </button>
              </div>
            </form>
          </div>
        </section>
      )}

      {/* Campaign List */}
      <div className="sms-cards">
        {campaigns.length === 0 && !showCreate && (
          <section className="sms-card">
            <div className="sms-card__body">
              <EmptyState icon="SMS" title="No email campaigns yet" description="Create your first cold outreach campaign to start sending AI-generated emails." />
            </div>
          </section>
        )}

        {campaigns.map((c) => (
          <section key={c.id} className="sms-card" style={{ cursor: 'pointer' }} onClick={() => openCampaign(c.id)}>
            <div className="sms-card__header">
              <h2 className="sms-card__title">{c.name}</h2>
              <span className={`sms-status-badge ${STATUS_COLORS[c.status] || ''}`}>{c.status.toUpperCase()}</span>
            </div>
            <div className="sms-card__body">
              <p style={{ color: '#6b7280', marginBottom: '8px' }}>{c.subject_template}</p>
              <div style={{ display: 'flex', gap: '24px', fontSize: '14px', color: '#9ca3af' }}>
                <span>Recipients: {c.total_recipients}</span>
                <span>Sent: {c.sent_count}</span>
                {c.failed_count > 0 && <span style={{ color: '#dc2626' }}>Failed: {c.failed_count}</span>}
                <span>Created: {formatDateTime(c.created_at)}</span>
              </div>
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}
