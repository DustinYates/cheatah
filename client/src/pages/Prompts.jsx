import { useState, useEffect } from 'react';
import { api } from '../api/client';
import './Prompts.css';

const SECTION_SCOPES = [
  { value: 'system', label: 'System Instructions' },
  { value: 'base', label: 'Base Prompt' },
  { value: 'pricing', label: 'Pricing Info' },
  { value: 'faq', label: 'FAQ' },
  { value: 'business_info', label: 'Business Info' },
  { value: 'custom', label: 'Custom' },
];

export default function Prompts() {
  const [bundles, setBundles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [editBundle, setEditBundle] = useState(null);
  const [testBundle, setTestBundle] = useState(null);
  const [testMessage, setTestMessage] = useState('');
  const [testResult, setTestResult] = useState(null);
  const [testLoading, setTestLoading] = useState(false);
  const [publishing, setPublishing] = useState(null);
  
  const [newBundle, setNewBundle] = useState({
    name: '',
    sections: [{ section_key: 'greeting', scope: 'custom', content: '', order: 0 }],
  });

  useEffect(() => {
    fetchBundles();
  }, []);

  const fetchBundles = async () => {
    try {
      const data = await api.getPromptBundles().catch(() => []);
      setBundles(Array.isArray(data) ? data : []);
    } catch (err) {
      console.error('Failed to fetch bundles:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = async (e) => {
    e.preventDefault();
    try {
      const created = await api.createPromptBundle(newBundle);
      setBundles([created, ...bundles]);
      setNewBundle({ name: '', sections: [{ section_key: 'greeting', scope: 'custom', content: '', order: 0 }] });
      setShowCreate(false);
    } catch (err) {
      alert('Failed to create bundle: ' + err.message);
    }
  };

  const handleUpdate = async (e) => {
    e.preventDefault();
    try {
      const updated = await api.updatePromptBundle(editBundle.id, {
        name: editBundle.name,
        sections: editBundle.sections,
      });
      setBundles(bundles.map(b => b.id === updated.id ? updated : b));
      setEditBundle(null);
    } catch (err) {
      alert('Failed to update: ' + err.message);
    }
  };

  const handlePublish = async (bundleId) => {
    if (!confirm('Publish this prompt to production? This will make it live for all widget users.')) return;
    setPublishing(bundleId);
    try {
      const updated = await api.publishPromptBundle(bundleId);
      setBundles(bundles.map(b => b.id === updated.id ? updated : b));
      alert('Published successfully!');
    } catch (err) {
      alert('Failed to publish: ' + err.message);
    } finally {
      setPublishing(null);
    }
  };

  const handleTest = async (e) => {
    e.preventDefault();
    setTestLoading(true);
    setTestResult(null);
    try {
      const result = await api.testPrompt(testBundle?.id, testMessage);
      setTestResult(result);
    } catch (err) {
      setTestResult({ error: err.message });
    } finally {
      setTestLoading(false);
    }
  };

  const openEdit = async (bundle) => {
    try {
      const detail = await api.getPromptBundle(bundle.id);
      setEditBundle(detail);
    } catch (err) {
      alert('Failed to load bundle details');
    }
  };

  const addSection = (target, setTarget) => {
    const newSection = {
      section_key: '',
      scope: 'custom',
      content: '',
      order: target.sections.length,
    };
    setTarget({ ...target, sections: [...target.sections, newSection] });
  };

  const updateSection = (target, setTarget, index, field, value) => {
    const updated = [...target.sections];
    updated[index] = { ...updated[index], [field]: value };
    setTarget({ ...target, sections: updated });
  };

  const removeSection = (target, setTarget, index) => {
    const updated = target.sections.filter((_, i) => i !== index);
    setTarget({ ...target, sections: updated });
  };

  const getStatusBadge = (status) => {
    const colors = {
      draft: '#6c757d',
      testing: '#ffc107',
      production: '#28a745',
    };
    return (
      <span className="status-badge" style={{ backgroundColor: colors[status] || '#6c757d' }}>
        {status}
      </span>
    );
  };

  if (loading) {
    return <div className="loading">Loading prompts...</div>;
  }

  return (
    <div className="prompts-page">
      <div className="page-header">
        <h1>Prompt Bundles</h1>
        <button className="btn-primary" onClick={() => setShowCreate(true)}>
          Create Bundle
        </button>
      </div>

      {showCreate && (
        <div className="modal-overlay" onClick={() => setShowCreate(false)}>
          <div className="modal large-modal" onClick={(e) => e.stopPropagation()}>
            <h2>Create Prompt Bundle</h2>
            <form onSubmit={handleCreate}>
              <div className="form-group">
                <label>Bundle Name</label>
                <input
                  type="text"
                  value={newBundle.name}
                  onChange={(e) => setNewBundle({ ...newBundle, name: e.target.value })}
                  placeholder="e.g., Main Sales Prompt"
                  required
                />
              </div>

              <h3>Sections</h3>
              {newBundle.sections.map((section, idx) => (
                <div key={idx} className="section-editor">
                  <div className="section-header">
                    <input
                      type="text"
                      placeholder="Section key (e.g., greeting)"
                      value={section.section_key}
                      onChange={(e) => updateSection(newBundle, setNewBundle, idx, 'section_key', e.target.value)}
                      required
                    />
                    <select
                      value={section.scope}
                      onChange={(e) => updateSection(newBundle, setNewBundle, idx, 'scope', e.target.value)}
                    >
                      {SECTION_SCOPES.map(s => (
                        <option key={s.value} value={s.value}>{s.label}</option>
                      ))}
                    </select>
                    <button type="button" className="btn-danger-small" onClick={() => removeSection(newBundle, setNewBundle, idx)}>
                      Remove
                    </button>
                  </div>
                  <textarea
                    value={section.content}
                    onChange={(e) => updateSection(newBundle, setNewBundle, idx, 'content', e.target.value)}
                    placeholder="Enter prompt content for this section..."
                    rows={4}
                    required
                  />
                </div>
              ))}
              <button type="button" className="btn-secondary" onClick={() => addSection(newBundle, setNewBundle)}>
                + Add Section
              </button>

              <div className="modal-actions">
                <button type="button" className="btn-secondary" onClick={() => setShowCreate(false)}>
                  Cancel
                </button>
                <button type="submit" className="btn-primary">
                  Create Draft
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {editBundle && (
        <div className="modal-overlay" onClick={() => setEditBundle(null)}>
          <div className="modal large-modal" onClick={(e) => e.stopPropagation()}>
            <h2>Edit Bundle: {editBundle.name}</h2>
            {editBundle.status === 'production' ? (
              <p className="warning">This bundle is live. Create a new bundle to make changes.</p>
            ) : (
              <form onSubmit={handleUpdate}>
                <div className="form-group">
                  <label>Bundle Name</label>
                  <input
                    type="text"
                    value={editBundle.name}
                    onChange={(e) => setEditBundle({ ...editBundle, name: e.target.value })}
                    required
                  />
                </div>

                <h3>Sections</h3>
                {editBundle.sections?.map((section, idx) => (
                  <div key={idx} className="section-editor">
                    <div className="section-header">
                      <input
                        type="text"
                        placeholder="Section key"
                        value={section.section_key}
                        onChange={(e) => updateSection(editBundle, setEditBundle, idx, 'section_key', e.target.value)}
                        required
                      />
                      <select
                        value={section.scope}
                        onChange={(e) => updateSection(editBundle, setEditBundle, idx, 'scope', e.target.value)}
                      >
                        {SECTION_SCOPES.map(s => (
                          <option key={s.value} value={s.value}>{s.label}</option>
                        ))}
                      </select>
                      <button type="button" className="btn-danger-small" onClick={() => removeSection(editBundle, setEditBundle, idx)}>
                        Remove
                      </button>
                    </div>
                    <textarea
                      value={section.content}
                      onChange={(e) => updateSection(editBundle, setEditBundle, idx, 'content', e.target.value)}
                      rows={4}
                      required
                    />
                  </div>
                ))}
                <button type="button" className="btn-secondary" onClick={() => addSection(editBundle, setEditBundle)}>
                  + Add Section
                </button>

                <div className="modal-actions">
                  <button type="button" className="btn-secondary" onClick={() => setEditBundle(null)}>
                    Cancel
                  </button>
                  <button type="submit" className="btn-primary">
                    Save Changes
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}

      {testBundle && (
        <div className="modal-overlay" onClick={() => { setTestBundle(null); setTestResult(null); }}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h2>Test: {testBundle.name}</h2>
            <form onSubmit={handleTest}>
              <div className="form-group">
                <label>Test Message</label>
                <textarea
                  value={testMessage}
                  onChange={(e) => setTestMessage(e.target.value)}
                  placeholder="Type a message to test the chatbot response..."
                  rows={3}
                  required
                />
              </div>
              <button type="submit" className="btn-primary" disabled={testLoading}>
                {testLoading ? 'Testing...' : 'Send Test'}
              </button>
              
              {testResult && (
                <div className="test-result">
                  {testResult.error ? (
                    <p className="error">Error: {testResult.error}</p>
                  ) : (
                    <>
                      <div className="result-section">
                        <label>Response:</label>
                        <pre>{testResult.response}</pre>
                      </div>
                      <details>
                        <summary>View Composed Prompt</summary>
                        <pre className="composed-prompt">{testResult.composed_prompt}</pre>
                      </details>
                    </>
                  )}
                </div>
              )}
            </form>
            <button className="btn-secondary close-btn" onClick={() => { setTestBundle(null); setTestResult(null); }}>
              Close
            </button>
          </div>
        </div>
      )}

      <div className="bundles-list">
        {bundles.length === 0 ? (
          <div className="empty-state">
            <p>No prompt bundles yet. Create your first bundle to customize how your chatbot responds.</p>
          </div>
        ) : (
          bundles.map((bundle) => (
            <div key={bundle.id} className={`bundle-card ${bundle.status}`}>
              <div className="bundle-header">
                <h3>{bundle.name}</h3>
                {getStatusBadge(bundle.status)}
              </div>
              <div className="bundle-meta">
                <span>v{bundle.version}</span>
                {bundle.published_at && (
                  <span>Published: {new Date(bundle.published_at).toLocaleDateString()}</span>
                )}
              </div>
              <div className="bundle-actions">
                <button className="btn-secondary" onClick={() => setTestBundle(bundle)}>
                  Test
                </button>
                <button className="btn-secondary" onClick={() => openEdit(bundle)}>
                  {bundle.status === 'production' ? 'View' : 'Edit'}
                </button>
                {bundle.status !== 'production' && (
                  <button 
                    className="btn-primary" 
                    onClick={() => handlePublish(bundle.id)}
                    disabled={publishing === bundle.id}
                  >
                    {publishing === bundle.id ? 'Publishing...' : 'Publish'}
                  </button>
                )}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
