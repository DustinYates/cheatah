import { useState, useEffect, useRef } from 'react';
import { api } from '../api/client';
import './SendSmsModal.css';

const getAudience = (lead) => {
  const tag = Array.isArray(lead.tags)
    ? lead.tags.find((t) => t?.category === 'audience')
    : null;
  const value = tag?.value;
  if (value === 'Adult') return 'adult';
  if (value === 'Child' || value === 'Child (under 3)') return 'child';
  return 'unknown';
};

export default function MassSmsModal({ leads, stages = [], onClose, onSuccess }) {
  const [message, setMessage] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState(null);
  const [audienceFilter, setAudienceFilter] = useState('all');
  const [advanceStage, setAdvanceStage] = useState(false);
  const [templates, setTemplates] = useState([]);
  const [templatesLoading, setTemplatesLoading] = useState(false);
  const [templateError, setTemplateError] = useState('');
  const [manageOpen, setManageOpen] = useState(false);
  const textareaRef = useRef(null);

  useEffect(() => {
    let mounted = true;
    setTemplatesLoading(true);
    api.getSmsTemplates()
      .then((data) => {
        if (!mounted) return;
        setTemplates(Array.isArray(data?.templates) ? data.templates : []);
      })
      .catch((err) => {
        if (!mounted) return;
        setTemplateError(err.message || 'Failed to load templates');
      })
      .finally(() => {
        if (mounted) setTemplatesLoading(false);
      });
    return () => { mounted = false; };
  }, []);

  const handleApplyTemplate = (id) => {
    const t = templates.find((x) => String(x.id) === String(id));
    if (t) setMessage(t.body);
  };

  const handleSaveAsTemplate = async () => {
    const body = message.trim();
    if (!body) return;
    const name = window.prompt('Template name:');
    if (!name || !name.trim()) return;
    try {
      const created = await api.createSmsTemplate(name.trim(), body);
      setTemplates((prev) => [...prev, created].sort((a, b) => a.name.localeCompare(b.name)));
    } catch (err) {
      window.alert(err.message || 'Failed to save template');
    }
  };

  const handleRenameTemplate = async (t) => {
    const name = window.prompt('Rename template:', t.name);
    if (!name || !name.trim() || name.trim() === t.name) return;
    try {
      const updated = await api.updateSmsTemplate(t.id, { name: name.trim() });
      setTemplates((prev) =>
        prev
          .map((x) => (x.id === t.id ? updated : x))
          .sort((a, b) => a.name.localeCompare(b.name)),
      );
    } catch (err) {
      window.alert(err.message || 'Failed to rename template');
    }
  };

  const handleOverwriteTemplate = async (t) => {
    const body = message.trim();
    if (!body) {
      window.alert('Type a message first, then overwrite the template with it.');
      return;
    }
    if (!window.confirm(`Replace "${t.name}" with the current message?`)) return;
    try {
      const updated = await api.updateSmsTemplate(t.id, { body });
      setTemplates((prev) => prev.map((x) => (x.id === t.id ? updated : x)));
    } catch (err) {
      window.alert(err.message || 'Failed to update template');
    }
  };

  const handleDeleteTemplate = async (t) => {
    if (!window.confirm(`Delete template "${t.name}"?`)) return;
    try {
      await api.deleteSmsTemplate(t.id);
      setTemplates((prev) => prev.filter((x) => x.id !== t.id));
    } catch (err) {
      window.alert(err.message || 'Failed to delete template');
    }
  };

  const sortedStages = [...stages].sort((a, b) => (a.position ?? 0) - (b.position ?? 0));
  const nextStageFor = (currentKey) => {
    const idx = sortedStages.findIndex((s) => s.key === currentKey);
    if (idx < 0 || idx >= sortedStages.length - 1) return null;
    return sortedStages[idx + 1];
  };

  const audienceCounts = leads.reduce(
    (acc, l) => {
      if (!l.phone) return acc;
      const a = getAudience(l);
      acc[a] = (acc[a] || 0) + 1;
      acc.all += 1;
      return acc;
    },
    { all: 0, adult: 0, child: 0, unknown: 0 },
  );

  const filteredLeads = leads.filter((l) => {
    if (!l.phone) return false;
    if (audienceFilter === 'all') return true;
    return getAudience(l) === audienceFilter;
  });

  const recipientCount = filteredLeads.length;
  const totalWithPhone = audienceCounts.all;
  const noPhoneCount = leads.length - totalWithPhone;

  const advanceableCount = sortedStages.length === 0
    ? 0
    : filteredLeads.filter((l) => nextStageFor(l.pipeline_stage || sortedStages[0]?.key) !== null).length;

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

  const BATCH_SIZE = 500;
  const [progress, setProgress] = useState(null);

  const handleSend = async (e) => {
    e.preventDefault();
    if (!message.trim() || loading || recipientCount === 0) return;

    if (!window.confirm(`Send this message to ${recipientCount} contact${recipientCount !== 1 ? 's' : ''}?`)) {
      return;
    }

    setLoading(true);
    setError('');
    setResult(null);
    setProgress(null);

    try {
      const phones = filteredLeads.map((l) => l.phone);
      const totalBatches = Math.ceil(phones.length / BATCH_SIZE);
      const totals = { sent: 0, failed: 0, errors: [] };

      for (let i = 0; i < totalBatches; i++) {
        const batch = phones.slice(i * BATCH_SIZE, (i + 1) * BATCH_SIZE);
        if (totalBatches > 1) {
          setProgress({ current: i + 1, total: totalBatches, sent: totals.sent });
        }
        const res = await api.sendBulkSms(batch, message.trim());
        totals.sent += res.sent || 0;
        totals.failed += res.failed || 0;
        if (res.errors) totals.errors.push(...res.errors);
      }

      let advanced = 0;
      if (totals.sent > 0 && advanceStage && advanceableCount > 0) {
        const moves = filteredLeads
          .map((l) => {
            const next = nextStageFor(l.pipeline_stage || sortedStages[0]?.key);
            return next ? { id: l.id, nextKey: next.key } : null;
          })
          .filter(Boolean);
        const results = await Promise.allSettled(
          moves.map((m) => api.updateLeadPipelineStage(m.id, m.nextKey)),
        );
        advanced = results.filter((r) => r.status === 'fulfilled').length;
      }

      setResult({ ...totals, advanced });
      setProgress(null);
      if (totals.sent > 0) {
        setTimeout(() => {
          onSuccess?.();
          onClose();
        }, 2000);
      }
    } catch (err) {
      setError(err.message || 'Failed to send bulk SMS');
    } finally {
      setLoading(false);
      setProgress(null);
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
            {progress && (
              <div className="info-message">
                Sending batch {progress.current} of {progress.total}... ({progress.sent} sent so far)
              </div>
            )}
            {result && (
              <div className={result.failed > 0 ? 'error-message' : 'success-message'}>
                Sent: {result.sent}
                {result.failed > 0 ? `, Failed: ${result.failed}` : ''}
                {result.advanced > 0 ? `, Advanced: ${result.advanced}` : ''}
              </div>
            )}

            <div className="mass-sms-recipients">
              <label>Recipients</label>
              <div className="mass-sms-segments" role="tablist" aria-label="Audience filter">
                {[
                  { key: 'all', label: 'All', count: audienceCounts.all },
                  { key: 'adult', label: 'Adults', count: audienceCounts.adult },
                  { key: 'child', label: 'Children', count: audienceCounts.child },
                  ...(audienceCounts.unknown > 0
                    ? [{ key: 'unknown', label: 'Untagged', count: audienceCounts.unknown }]
                    : []),
                ].map((seg) => (
                  <button
                    key={seg.key}
                    type="button"
                    role="tab"
                    aria-selected={audienceFilter === seg.key}
                    className={`mass-sms-segment${audienceFilter === seg.key ? ' is-active' : ''}`}
                    onClick={() => setAudienceFilter(seg.key)}
                    disabled={loading || !!result || seg.count === 0}
                  >
                    {seg.label} <span className="mass-sms-segment__count">{seg.count}</span>
                  </button>
                ))}
              </div>
              <div className="mass-sms-summary">
                <span className="mass-sms-count">{recipientCount}</span> contact{recipientCount !== 1 ? 's' : ''} with phone numbers
                {noPhoneCount > 0 && (
                  <span className="mass-sms-skipped"> ({noPhoneCount} skipped — no phone)</span>
                )}
              </div>
              <div className="mass-sms-list">
                {filteredLeads.map((l) => (
                  <span key={l.id} className="mass-sms-chip">{l.name || l.phone}</span>
                ))}
              </div>
            </div>

            {sortedStages.length > 0 && (
              <label className={`mass-sms-advance${advanceableCount === 0 ? ' is-disabled' : ''}`}>
                <input
                  type="checkbox"
                  checked={advanceStage && advanceableCount > 0}
                  onChange={(e) => setAdvanceStage(e.target.checked)}
                  disabled={loading || !!result || advanceableCount === 0}
                />
                <span>
                  Advance to next pipeline stage after sending
                  {advanceableCount > 0 && advanceableCount < recipientCount && (
                    <span className="mass-sms-advance__note"> ({advanceableCount} of {recipientCount} eligible)</span>
                  )}
                  {advanceableCount === 0 && recipientCount > 0 && (
                    <span className="mass-sms-advance__note"> (none eligible — already at final stage)</span>
                  )}
                </span>
              </label>
            )}

            <div className="mass-sms-templates">
              <div className="mass-sms-templates__row">
                <select
                  className="mass-sms-templates__select"
                  value=""
                  onChange={(e) => {
                    if (e.target.value) {
                      handleApplyTemplate(e.target.value);
                      e.target.value = '';
                    }
                  }}
                  disabled={loading || !!result || templatesLoading || templates.length === 0}
                >
                  <option value="">
                    {templatesLoading
                      ? 'Loading templates...'
                      : templates.length === 0
                      ? 'No templates yet'
                      : 'Use template...'}
                  </option>
                  {templates.map((t) => (
                    <option key={t.id} value={t.id}>{t.name}</option>
                  ))}
                </select>
                <button
                  type="button"
                  className="mass-sms-templates__btn"
                  onClick={handleSaveAsTemplate}
                  disabled={loading || !!result || !message.trim()}
                  title={message.trim() ? 'Save current message as a new template' : 'Type a message first'}
                >
                  Save as new
                </button>
                {templates.length > 0 && (
                  <button
                    type="button"
                    className="mass-sms-templates__btn mass-sms-templates__btn--ghost"
                    onClick={() => setManageOpen((v) => !v)}
                    disabled={loading || !!result}
                  >
                    {manageOpen ? 'Done' : 'Manage'}
                  </button>
                )}
              </div>
              {templateError && <div className="mass-sms-templates__error">{templateError}</div>}
              {manageOpen && templates.length > 0 && (
                <ul className="mass-sms-templates__list">
                  {templates.map((t) => (
                    <li key={t.id} className="mass-sms-templates__item">
                      <span className="mass-sms-templates__name">{t.name}</span>
                      <div className="mass-sms-templates__actions">
                        <button type="button" onClick={() => handleRenameTemplate(t)} disabled={loading}>Rename</button>
                        <button type="button" onClick={() => handleOverwriteTemplate(t)} disabled={loading || !message.trim()} title={message.trim() ? 'Replace template body with current message' : 'Type a message first'}>Save current</button>
                        <button type="button" className="mass-sms-templates__delete" onClick={() => handleDeleteTemplate(t)} disabled={loading}>Delete</button>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
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
              {loading
                ? (progress ? `Sending batch ${progress.current}/${progress.total}...` : 'Sending...')
                : `Send to ${recipientCount}`}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
