import { useState, useEffect } from 'react';
import { api } from '../api/client';
import { getAllTemplates, cloneTemplateSections, TEMPLATE_CATEGORIES } from '../data/promptTemplates';
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
  const [showTemplateSelector, setShowTemplateSelector] = useState(false);
  const [selectedTemplate, setSelectedTemplate] = useState(null);
  const [editBundle, setEditBundle] = useState(null);
  const [testBundle, setTestBundle] = useState(null);
  const [testMessage, setTestMessage] = useState('');
  const [testResult, setTestResult] = useState(null);
  const [testLoading, setTestLoading] = useState(false);
  const [publishing, setPublishing] = useState(null);
  const [expandedSections, setExpandedSections] = useState({});

  const [newBundle, setNewBundle] = useState({
    name: '',
    sections: [{ section_key: 'greeting', scope: 'custom', content: '', order: 0 }],
  });

  const templates = getAllTemplates();

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

  const handleSelectTemplate = (template) => {
    setSelectedTemplate(template);
    const sections = cloneTemplateSections(template.id);
    setNewBundle({
      name: template.id === 'blank' ? '' : `${template.name} - Draft`,
      sections: sections,
    });
    setShowTemplateSelector(false);
    setShowCreate(true);
  };

  const handleStartFromScratch = () => {
    setSelectedTemplate(null);
    setNewBundle({
      name: '',
      sections: [{ section_key: 'custom_section', scope: 'custom', content: '', order: 0 }],
    });
    setShowTemplateSelector(false);
    setShowCreate(true);
  };

  const handleCreate = async (e) => {
    e.preventDefault();
    try {
      const created = await api.createPromptBundle(newBundle);
      setBundles([created, ...bundles]);
      setNewBundle({ name: '', sections: [{ section_key: 'greeting', scope: 'custom', content: '', order: 0 }] });
      setShowCreate(false);
      setSelectedTemplate(null);
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

  const toggleSectionExpanded = (index) => {
    setExpandedSections(prev => ({
      ...prev,
      [index]: !prev[index]
    }));
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

  const getScopeLabel = (scopeValue) => {
    const scope = SECTION_SCOPES.find(s => s.value === scopeValue);
    return scope ? scope.label : scopeValue;
  };

  if (loading) {
    return <div className="loading">Loading prompts...</div>;
  }

  return (
    <div className="prompts-page">
      <div className="page-header">
        <div>
          <h1>Prompt Bundles</h1>
          <p className="page-subtitle">Create and manage your chatbot's personality and responses</p>
        </div>
        <button className="btn-primary" onClick={() => setShowTemplateSelector(true)}>
          + Create Bundle
        </button>
      </div>

      {/* Template Selector Modal */}
      {showTemplateSelector && (
        <div className="modal-overlay" onClick={() => setShowTemplateSelector(false)}>
          <div className="modal template-modal" onClick={(e) => e.stopPropagation()}>
            <h2>Choose a Template</h2>
            <p className="modal-subtitle">Start with a pre-built template or create from scratch</p>

            <div className="template-grid">
              {templates.map((template) => (
                <div
                  key={template.id}
                  className={`template-card ${template.id === 'blank' ? 'blank-template' : ''}`}
                  onClick={() => handleSelectTemplate(template)}
                >
                  <div className="template-icon">
                    {TEMPLATE_CATEGORIES[template.category]?.icon || '📝'}
                  </div>
                  <h3>{template.name}</h3>
                  <p>{template.description}</p>
                  <span className="template-category">
                    {TEMPLATE_CATEGORIES[template.category]?.name || template.category}
                  </span>
                  {template.id !== 'blank' && (
                    <span className="template-sections-count">
                      {template.sections.length} sections
                    </span>
                  )}
                </div>
              ))}
            </div>

            <div className="modal-actions">
              <button
                type="button"
                className="btn-secondary"
                onClick={() => setShowTemplateSelector(false)}
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Create/Edit Bundle Modal */}
      {showCreate && (
        <div className="modal-overlay" onClick={() => { setShowCreate(false); setSelectedTemplate(null); }}>
          <div className="modal large-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header-with-info">
              <h2>
                {selectedTemplate && selectedTemplate.id !== 'blank'
                  ? `Create from: ${selectedTemplate.name}`
                  : 'Create Prompt Bundle'}
              </h2>
              {selectedTemplate && selectedTemplate.id !== 'blank' && (
                <span className="template-badge">Template</span>
              )}
            </div>

            {selectedTemplate && selectedTemplate.id !== 'blank' && (
              <div className="template-info-banner">
                <strong>Tip:</strong> Replace text in [BRACKETS] with your specific information.
                You can add, remove, or modify any section.
              </div>
            )}

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

              <div className="sections-header">
                <h3>Sections ({newBundle.sections.length})</h3>
                <button
                  type="button"
                  className="btn-secondary btn-small"
                  onClick={() => addSection(newBundle, setNewBundle)}
                >
                  + Add Section
                </button>
              </div>

              <div className="sections-list">
                {newBundle.sections.map((section, idx) => (
                  <div key={idx} className={`section-editor ${expandedSections[idx] !== false ? 'expanded' : 'collapsed'}`}>
                    <div
                      className="section-header-bar"
                      onClick={() => toggleSectionExpanded(idx)}
                    >
                      <div className="section-header-left">
                        <span className="section-expand-icon">
                          {expandedSections[idx] !== false ? '▼' : '▶'}
                        </span>
                        <span className="section-key-display">
                          {section.section_key || 'Untitled Section'}
                        </span>
                        <span className="section-scope-badge">
                          {getScopeLabel(section.scope)}
                        </span>
                      </div>
                      <button
                        type="button"
                        className="btn-danger-small"
                        onClick={(e) => { e.stopPropagation(); removeSection(newBundle, setNewBundle, idx); }}
                      >
                        Remove
                      </button>
                    </div>

                    {expandedSections[idx] !== false && (
                      <div className="section-content">
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
                        </div>
                        <textarea
                          value={section.content}
                          onChange={(e) => updateSection(newBundle, setNewBundle, idx, 'content', e.target.value)}
                          placeholder="Enter prompt content for this section..."
                          rows={8}
                          required
                        />
                        {section.placeholder_hints && (
                          <div className="placeholder-hints">
                            <strong>Placeholders to replace:</strong>
                            <ul>
                              {Object.entries(section.placeholder_hints).map(([placeholder, hint]) => (
                                <li key={placeholder}>
                                  <code>{placeholder}</code> → {hint}
                                </li>
                              ))}
                            </ul>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                ))}
              </div>

              <div className="modal-actions">
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={() => { setShowCreate(false); setSelectedTemplate(null); }}
                >
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

      {/* Edit Bundle Modal */}
      {editBundle && (
        <div className="modal-overlay" onClick={() => setEditBundle(null)}>
          <div className="modal large-modal" onClick={(e) => e.stopPropagation()}>
            <h2>{editBundle.status === 'production' ? 'View' : 'Edit'} Bundle: {editBundle.name}</h2>
            {editBundle.status === 'production' ? (
              <>
                <p className="warning">This bundle is live. Create a new bundle to make changes.</p>
                <div className="readonly-sections">
                  {editBundle.sections?.map((section, idx) => (
                    <div key={idx} className="section-readonly">
                      <div className="section-readonly-header">
                        <span className="section-key-display">{section.section_key}</span>
                        <span className="section-scope-badge">{getScopeLabel(section.scope)}</span>
                      </div>
                      <pre className="section-readonly-content">{section.content}</pre>
                    </div>
                  ))}
                </div>
                <div className="modal-actions">
                  <button type="button" className="btn-secondary" onClick={() => setEditBundle(null)}>
                    Close
                  </button>
                </div>
              </>
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

                <div className="sections-header">
                  <h3>Sections ({editBundle.sections?.length || 0})</h3>
                  <button
                    type="button"
                    className="btn-secondary btn-small"
                    onClick={() => addSection(editBundle, setEditBundle)}
                  >
                    + Add Section
                  </button>
                </div>

                {editBundle.sections?.map((section, idx) => (
                  <div key={idx} className="section-editor expanded">
                    <div className="section-content">
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
                        <button
                          type="button"
                          className="btn-danger-small"
                          onClick={() => removeSection(editBundle, setEditBundle, idx)}
                        >
                          Remove
                        </button>
                      </div>
                      <textarea
                        value={section.content}
                        onChange={(e) => updateSection(editBundle, setEditBundle, idx, 'content', e.target.value)}
                        rows={6}
                        required
                      />
                    </div>
                  </div>
                ))}

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

      {/* Test Bundle Modal */}
      {testBundle && (
        <div className="modal-overlay" onClick={() => { setTestBundle(null); setTestResult(null); }}>
          <div className="modal test-modal" onClick={(e) => e.stopPropagation()}>
            <h2>Test: {testBundle.name}</h2>
            <p className="modal-subtitle">Send a test message to see how your chatbot responds</p>

            <form onSubmit={handleTest}>
              <div className="form-group">
                <label>Test Message</label>
                <textarea
                  value={testMessage}
                  onChange={(e) => setTestMessage(e.target.value)}
                  placeholder="Type a message to test the chatbot response... (e.g., 'What swim classes do you offer for a 4 year old?')"
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
                        <label>AI Response:</label>
                        <pre>{testResult.response}</pre>
                      </div>
                      <details>
                        <summary>View Composed Prompt (Debug)</summary>
                        <pre className="composed-prompt">{testResult.composed_prompt}</pre>
                      </details>
                    </>
                  )}
                </div>
              )}
            </form>
            <button
              className="btn-secondary close-btn"
              onClick={() => { setTestBundle(null); setTestResult(null); }}
            >
              Close
            </button>
          </div>
        </div>
      )}

      {/* Bundle List */}
      <div className="bundles-list">
        {bundles.length === 0 ? (
          <div className="empty-state">
            <div className="empty-state-icon">📝</div>
            <h3>No prompt bundles yet</h3>
            <p>Create your first bundle to customize how your chatbot responds to customers.</p>
            <button className="btn-primary" onClick={() => setShowTemplateSelector(true)}>
              + Create Your First Bundle
            </button>
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
