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
  const textareaRef = useRef(null);

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
