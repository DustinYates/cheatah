import { useState, useEffect } from 'react';
import { api } from '../api/client';
import { getAllTemplates, cloneTemplateSections, TEMPLATE_CATEGORIES } from '../data/promptTemplates';
import './Prompts.css';

const SECTION_SCOPES = [
  { value: 'system', label: 'System Instructions', icon: '⚙️' },
  { value: 'base', label: 'Base Prompt', icon: '📋' },
  { value: 'pricing', label: 'Pricing Info', icon: '💰' },
  { value: 'faq', label: 'FAQ', icon: '❓' },
  { value: 'business_info', label: 'Business Info', icon: '🏢' },
  { value: 'custom', label: 'Custom', icon: '✏️' },
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
  const [deleting, setDeleting] = useState(null);
  const [deactivating, setDeactivating] = useState(null);

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

  const handleDelete = async (bundle) => {
    if (bundle.status === 'production') {
      alert('Cannot delete a production bundle. Deactivate it first or create a new production bundle.');
      return;
    }
    if (!confirm(`Delete "${bundle.name}"?\n\nThis action cannot be undone.`)) return;
    
    setDeleting(bundle.id);
    try {
      await api.deletePromptBundle(bundle.id);
      setBundles(bundles.filter(b => b.id !== bundle.id));
    } catch (err) {
      alert('Failed to delete: ' + err.message);
    } finally {
      setDeleting(null);
    }
  };

  const handleDeactivate = async (bundle) => {
    if (!confirm(`Deactivate "${bundle.name}"?\n\nThis will remove it from production. Your chatbot will use the default responses until you publish another bundle.`)) return;
    
    setDeactivating(bundle.id);
    try {
      // Call API to demote from production to draft
      const updated = await api.updatePromptBundle(bundle.id, {
        ...bundle,
        status: 'draft'
      });
      setBundles(bundles.map(b => b.id === updated.id ? { ...updated, status: 'draft' } : b));
      alert('Bundle deactivated. It is now a draft.');
    } catch (err) {
      alert('Failed to deactivate: ' + err.message);
    } finally {
      setDeactivating(null);
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
    const config = {
      draft: { color: '#6c757d', bg: '#f8f9fa', label: 'Draft' },
      testing: { color: '#856404', bg: '#fff3cd', label: 'Testing' },
      production: { color: '#155724', bg: '#d4edda', label: '● Live' },
    };
    const { color, bg, label } = config[status] || config.draft;
    return (
      <span className="status-badge" style={{ backgroundColor: bg, color }}>
        {label}
      </span>
    );
  };

  const getScopeInfo = (scopeValue) => {
    return SECTION_SCOPES.find(s => s.value === scopeValue) || { label: scopeValue, icon: '📝' };
  };

  if (loading) {
    return (
      <div className="prompts-page">
        <div className="loading-state">
          <div className="loading-spinner"></div>
          <p>Loading prompts...</p>
        </div>
      </div>
    );
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
            <div className="modal-header">
              <h2>Choose a Template</h2>
              <button className="modal-close" onClick={() => setShowTemplateSelector(false)}>×</button>
            </div>
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
                  <div className="template-meta">
                    <span className="template-category">
                      {TEMPLATE_CATEGORIES[template.category]?.name || template.category}
                    </span>
                    {template.id !== 'blank' && (
                      <span className="template-sections-count">
                        {template.sections.length} sections
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Two-Column Create/Edit Modal */}
      {showCreate && selectedTemplate && (
        <div className="modal-overlay" onClick={() => { setShowCreate(false); setSelectedTemplate(null); }}>
          <div className="modal two-column-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <div className="modal-title-group">
                <h2>Create from: {selectedTemplate.name}</h2>
                {selectedTemplate.id !== 'blank' && (
                  <span className="template-badge">Template</span>
                )}
              </div>
              <button className="modal-close" onClick={() => { setShowCreate(false); setSelectedTemplate(null); }}>×</button>
            </div>

            <div className="two-column-info-banner">
              <span className="info-icon">💡</span>
              <span>Replace text in <code>[BRACKETS]</code> with your specific information. The left column shows the template reference.</span>
            </div>

            <form onSubmit={handleCreate}>
              <div className="form-group bundle-name-input">
                <label>Bundle Name</label>
                <input
                  type="text"
                  value={newBundle.name}
                  onChange={(e) => setNewBundle({ ...newBundle, name: e.target.value })}
                  placeholder="e.g., Main Sales Prompt"
                  required
                />
              </div>

              <div className="two-column-sections">
                {newBundle.sections.map((section, idx) => {
                  const templateSection = selectedTemplate.sections?.[idx];
                  const scopeInfo = getScopeInfo(section.scope);
                  
                  return (
                    <div key={idx} className="two-column-section">
                      <div className="section-label-row">
                        <div className="section-label-left">
                          <span className="scope-icon">{scopeInfo.icon}</span>
                          <input
                            type="text"
                            className="section-key-input"
                            placeholder="Section key"
                            value={section.section_key}
                            onChange={(e) => updateSection(newBundle, setNewBundle, idx, 'section_key', e.target.value)}
                            required
                          />
                          <select
                            className="scope-select"
                            value={section.scope}
                            onChange={(e) => updateSection(newBundle, setNewBundle, idx, 'scope', e.target.value)}
                          >
                            {SECTION_SCOPES.map(s => (
                              <option key={s.value} value={s.value}>{s.label}</option>
                            ))}
                          </select>
                        </div>
                        <button
                          type="button"
                          className="btn-remove-section"
                          onClick={() => removeSection(newBundle, setNewBundle, idx)}
                          title="Remove section"
                        >
                          🗑️
                        </button>
                      </div>
                      
                      <div className="two-column-content">
                        {/* Left Column: Template Reference (Read-only) */}
                        <div className="column template-column">
                          <div className="column-header">
                            <span className="column-label">📖 Template Reference</span>
                          </div>
                          <div className="template-reference-content">
                            {templateSection?.content || (
                              <span className="no-template">No template content for this section</span>
                            )}
                          </div>
                        </div>

                        {/* Right Column: Your Content (Editable) */}
                        <div className="column edit-column">
                          <div className="column-header">
                            <span className="column-label">✏️ Your Content</span>
                          </div>
                          <textarea
                            value={section.content}
                            onChange={(e) => updateSection(newBundle, setNewBundle, idx, 'content', e.target.value)}
                            placeholder="Enter your customized content here..."
                            rows={10}
                            required
                          />
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>

              <button
                type="button"
                className="btn-add-section"
                onClick={() => addSection(newBundle, setNewBundle)}
              >
                + Add Section
              </button>

              <div className="modal-actions">
                <button type="button" className="btn-secondary" onClick={() => { setShowCreate(false); setSelectedTemplate(null); }}>
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

      {/* Simple Create Modal (Blank Template) */}
      {showCreate && selectedTemplate?.id === 'blank' && (
        <div className="modal-overlay" onClick={() => { setShowCreate(false); setSelectedTemplate(null); }}>
          <div className="modal large-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Create Prompt Bundle</h2>
              <button className="modal-close" onClick={() => { setShowCreate(false); setSelectedTemplate(null); }}>×</button>
            </div>

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
                  <div key={idx} className="section-editor">
                    <div className="section-editor-header">
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
                      <button
                        type="button"
                        className="btn-danger-small"
                        onClick={() => removeSection(newBundle, setNewBundle, idx)}
                      >
                        Remove
                      </button>
                    </div>
                    <textarea
                      value={section.content}
                      onChange={(e) => updateSection(newBundle, setNewBundle, idx, 'content', e.target.value)}
                      placeholder="Enter prompt content..."
                      rows={6}
                      required
                    />
                  </div>
                ))}
              </div>

              <div className="modal-actions">
                <button type="button" className="btn-secondary" onClick={() => { setShowCreate(false); setSelectedTemplate(null); }}>
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
            <div className="modal-header">
              <div className="modal-title-group">
                <h2>{editBundle.status === 'production' ? 'View' : 'Edit'}: {editBundle.name}</h2>
                {getStatusBadge(editBundle.status)}
              </div>
              <button className="modal-close" onClick={() => setEditBundle(null)}>×</button>
            </div>

            {editBundle.status === 'production' ? (
              <>
                <div className="production-warning">
                  <span className="warning-icon">⚠️</span>
                  <span>This bundle is live. To make changes, deactivate it first or create a new draft.</span>
                </div>
                <div className="readonly-sections">
                  {editBundle.sections?.map((section, idx) => {
                    const scopeInfo = getScopeInfo(section.scope);
                    return (
                      <div key={idx} className="section-readonly">
                        <div className="section-readonly-header">
                          <span className="scope-icon">{scopeInfo.icon}</span>
                          <span className="section-key-display">{section.section_key}</span>
                          <span className="section-scope-badge">{scopeInfo.label}</span>
                        </div>
                        <pre className="section-readonly-content">{section.content}</pre>
                      </div>
                    );
                  })}
                </div>
                <div className="modal-actions">
                  <button
                    type="button"
                    className="btn-warning"
                    onClick={() => { setEditBundle(null); handleDeactivate(editBundle); }}
                    disabled={deactivating === editBundle.id}
                  >
                    {deactivating === editBundle.id ? 'Deactivating...' : 'Deactivate Bundle'}
                  </button>
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

                <div className="sections-list">
                  {editBundle.sections?.map((section, idx) => {
                    const scopeInfo = getScopeInfo(section.scope);
                    return (
                      <div key={idx} className="section-editor">
                        <div className="section-editor-header">
                          <span className="scope-icon">{scopeInfo.icon}</span>
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
                    );
                  })}
                </div>

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
            <div className="modal-header">
              <h2>Test: {testBundle.name}</h2>
              <button className="modal-close" onClick={() => { setTestBundle(null); setTestResult(null); }}>×</button>
            </div>
            <p className="modal-subtitle">Send a test message to see how your chatbot responds</p>

            <form onSubmit={handleTest}>
              <div className="form-group">
                <label>Test Message</label>
                <textarea
                  value={testMessage}
                  onChange={(e) => setTestMessage(e.target.value)}
                  placeholder="Type a message to test... (e.g., 'What swim classes do you offer for a 4 year old?')"
                  rows={3}
                  required
                />
              </div>
              <button type="submit" className="btn-primary" disabled={testLoading}>
                {testLoading ? 'Testing...' : 'Send Test'}
              </button>

              {testResult && (
                <div className={`test-result ${testResult.error ? 'error' : 'success'}`}>
                  {testResult.error ? (
                    <div className="result-error">
                      <span className="error-icon">❌</span>
                      <span>Error: {testResult.error}</span>
                    </div>
                  ) : (
                    <>
                      <div className="result-section">
                        <label>AI Response:</label>
                        <div className="ai-response">{testResult.response}</div>
                      </div>
                      <details className="debug-details">
                        <summary>View Composed Prompt (Debug)</summary>
                        <pre className="composed-prompt">{testResult.composed_prompt}</pre>
                      </details>
                    </>
                  )}
                </div>
              )}
            </form>
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
                <span className="version-tag">v{bundle.version}</span>
                {bundle.published_at && (
                  <span className="published-date">
                    Published: {new Date(bundle.published_at).toLocaleDateString()}
                  </span>
                )}
                <span className="section-count">
                  {bundle.sections?.length || '?'} sections
                </span>
              </div>
              <div className="bundle-actions">
                <button className="btn-icon" onClick={() => setTestBundle(bundle)} title="Test">
                  🧪
                </button>
                <button className="btn-icon" onClick={() => openEdit(bundle)} title={bundle.status === 'production' ? 'View' : 'Edit'}>
                  {bundle.status === 'production' ? '👁️' : '✏️'}
                </button>
                
                {bundle.status === 'production' ? (
                  <button
                    className="btn-warning-small"
                    onClick={() => handleDeactivate(bundle)}
                    disabled={deactivating === bundle.id}
                    title="Deactivate"
                  >
                    {deactivating === bundle.id ? '...' : '⏸️ Deactivate'}
                  </button>
                ) : (
                  <>
                    <button
                      className="btn-success-small"
                      onClick={() => handlePublish(bundle.id)}
                      disabled={publishing === bundle.id}
                      title="Publish to production"
                    >
                      {publishing === bundle.id ? '...' : '🚀 Publish'}
                    </button>
                    <button
                      className="btn-danger-small"
                      onClick={() => handleDelete(bundle)}
                      disabled={deleting === bundle.id}
                      title="Delete"
                    >
                      {deleting === bundle.id ? '...' : '🗑️'}
                    </button>
                  </>
                )}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
