import { useState, useEffect } from 'react';
import { api } from '../api/client';
import { usePipelineStages } from '../hooks/usePipelineStages';
import './PipelineSettings.css';

const DEFAULT_STAGES = [
  { key: 'new_lead', label: 'New Lead', color: '#1d4ed8' },
  { key: 'contacted', label: 'Contacted', color: '#b45309' },
  { key: 'interested', label: 'Interested', color: '#be185d' },
  { key: 'registered', label: 'Registered', color: '#047857' },
  { key: 'enrolled', label: 'Enrolled', color: '#4338ca' },
];

const PRESET_COLORS = [
  '#1d4ed8', '#b45309', '#be185d', '#047857', '#4338ca',
  '#dc2626', '#ea580c', '#ca8a04', '#16a34a', '#0891b2',
  '#7c3aed', '#c026d3', '#475569', '#0d9488', '#2563eb',
];

function generateKey(label) {
  return label.trim().toLowerCase().replace(/\s+/g, '_').replace(/[^a-z0-9_]/g, '').slice(0, 50);
}

export default function PipelineSettings() {
  const { invalidate } = usePipelineStages();
  const [stages, setStages] = useState([]);
  const [original, setOriginal] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);

  useEffect(() => {
    loadStages();
  }, []);

  async function loadStages() {
    try {
      setLoading(true);
      const data = await api.getPipelineStages();
      const loaded = (data.stages || []).map((s) => ({
        key: s.key,
        label: s.label,
        color: s.color,
        isNew: false,
      }));
      setStages(loaded);
      setOriginal(JSON.parse(JSON.stringify(loaded)));
    } catch {
      setError('Failed to load pipeline stages');
    } finally {
      setLoading(false);
    }
  }

  const hasChanges = JSON.stringify(stages) !== JSON.stringify(original);

  function handleLabelChange(idx, label) {
    setStages((prev) => {
      const next = [...prev];
      next[idx] = { ...next[idx], label };
      // Auto-generate key for new stages
      if (next[idx].isNew) {
        next[idx].key = generateKey(label);
      }
      return next;
    });
  }

  function handleColorChange(idx, color) {
    setStages((prev) => {
      const next = [...prev];
      next[idx] = { ...next[idx], color };
      return next;
    });
  }

  function handleMoveUp(idx) {
    if (idx === 0) return;
    setStages((prev) => {
      const next = [...prev];
      [next[idx - 1], next[idx]] = [next[idx], next[idx - 1]];
      return next;
    });
  }

  function handleMoveDown(idx) {
    setStages((prev) => {
      if (idx >= prev.length - 1) return prev;
      const next = [...prev];
      [next[idx], next[idx + 1]] = [next[idx + 1], next[idx]];
      return next;
    });
  }

  function handleRemove(idx) {
    setStages((prev) => prev.filter((_, i) => i !== idx));
  }

  function handleAdd() {
    const usedColors = new Set(stages.map((s) => s.color));
    const nextColor = PRESET_COLORS.find((c) => !usedColors.has(c)) || '#6b7280';
    setStages((prev) => [
      ...prev,
      { key: '', label: '', color: nextColor, isNew: true },
    ]);
  }

  function handleResetDefaults() {
    setStages(DEFAULT_STAGES.map((s) => ({ ...s, isNew: false })));
  }

  function handleCancel() {
    setStages(JSON.parse(JSON.stringify(original)));
  }

  async function handleSave() {
    setError(null);
    setSuccess(null);

    // Validate
    for (const s of stages) {
      if (!s.label.trim()) {
        setError('All stages must have a label.');
        return;
      }
    }
    const keys = stages.map((s) => s.isNew ? generateKey(s.label) : s.key);
    const keySet = new Set();
    for (const k of keys) {
      if (!k) {
        setError('All stages must have a valid key (from label).');
        return;
      }
      if (keySet.has(k)) {
        setError(`Duplicate stage key: "${k}". Each stage needs a unique label.`);
        return;
      }
      keySet.add(k);
    }

    setSaving(true);
    try {
      const payload = stages.map((s, i) => ({
        key: s.isNew ? generateKey(s.label) : s.key,
        label: s.label.trim(),
        color: s.color,
      }));
      await api.updatePipelineStages(payload);
      invalidate();
      await loadStages();
      setSuccess('Pipeline stages saved.');
      setTimeout(() => setSuccess(null), 3000);
    } catch (err) {
      setError(err.message || 'Failed to save.');
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <div className="pipeline-settings">
        <h1>Pipeline Settings</h1>
        <p className="pipeline-loading">Loading...</p>
      </div>
    );
  }

  return (
    <div className="pipeline-settings">
      <div className="pipeline-settings__header">
        <div>
          <h1>Pipeline Settings</h1>
          <p className="pipeline-settings__desc">
            Customize the stages in your Kanban pipeline. These labels appear on the Pipeline board and Connections page tags.
          </p>
        </div>
        <button
          className="btn-reset-defaults"
          onClick={handleResetDefaults}
          type="button"
        >
          Reset to Defaults
        </button>
      </div>

      {error && <div className="pipeline-alert pipeline-alert--error">{error}</div>}
      {success && <div className="pipeline-alert pipeline-alert--success">{success}</div>}

      <div className="pipeline-stages-list">
        <div className="pipeline-stages-list__header">
          <span className="col-order">#</span>
          <span className="col-color">Color</span>
          <span className="col-label">Label</span>
          <span className="col-key">Key</span>
          <span className="col-actions">Actions</span>
        </div>

        {stages.map((stage, idx) => (
          <div key={idx} className="pipeline-stage-row">
            <span className="col-order">{idx + 1}</span>
            <span className="col-color">
              <div className="color-picker-wrapper">
                <span
                  className="color-swatch"
                  style={{ backgroundColor: stage.color }}
                />
                <input
                  type="color"
                  value={stage.color}
                  onChange={(e) => handleColorChange(idx, e.target.value)}
                  className="color-input"
                  title="Pick color"
                />
              </div>
            </span>
            <span className="col-label">
              <input
                type="text"
                value={stage.label}
                onChange={(e) => handleLabelChange(idx, e.target.value)}
                placeholder="Stage name..."
                className="label-input"
                maxLength={100}
              />
            </span>
            <span className="col-key">
              <code className="key-display">
                {stage.isNew ? generateKey(stage.label) || '...' : stage.key}
              </code>
            </span>
            <span className="col-actions">
              <button
                className="btn-icon"
                onClick={() => handleMoveUp(idx)}
                disabled={idx === 0}
                title="Move up"
                type="button"
              >
                &#x2191;
              </button>
              <button
                className="btn-icon"
                onClick={() => handleMoveDown(idx)}
                disabled={idx === stages.length - 1}
                title="Move down"
                type="button"
              >
                &#x2193;
              </button>
              <button
                className="btn-icon btn-icon--danger"
                onClick={() => handleRemove(idx)}
                disabled={stages.length <= 1}
                title="Remove stage"
                type="button"
              >
                &#x2715;
              </button>
            </span>
          </div>
        ))}
      </div>

      <button className="btn-add-stage" onClick={handleAdd} type="button">
        + Add Stage
      </button>

      <div className="pipeline-settings__footer">
        <button
          className="btn-cancel"
          onClick={handleCancel}
          disabled={!hasChanges || saving}
          type="button"
        >
          Cancel
        </button>
        <button
          className="btn-save"
          onClick={handleSave}
          disabled={!hasChanges || saving || stages.length === 0}
          type="button"
        >
          {saving ? 'Saving...' : 'Save Changes'}
        </button>
      </div>
    </div>
  );
}
