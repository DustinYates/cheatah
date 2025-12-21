import { useState, useEffect, useMemo } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { api } from '../api/client';
import { getAllTemplates, cloneTemplateSections, TEMPLATE_CATEGORIES } from '../data/promptTemplates';
import { LoadingState, EmptyState, ErrorState } from '../components/ui';
import { ToastContainer } from '../components/ui/Toast';
import './Prompts.css';

// Base scopes - read-only, system-managed
const BASE_SCOPES = ['system', 'base'];

// Editable scopes - user can customize
const EDITABLE_SCOPES = [
  { value: 'pricing', label: 'Pricing Info', icon: '💰' },
  { value: 'faq', label: 'FAQ', icon: '❓' },
  { value: 'business_info', label: 'Business Info', icon: '🏢' },
  { value: 'custom', label: 'Custom', icon: '✏️' },
];

// All scopes for display/reference
const ALL_SCOPES = [
  { value: 'system', label: 'System Instructions', icon: '⚙️', readonly: true },
  { value: 'base', label: 'Base Prompt', icon: '📋', readonly: true },
  ...EDITABLE_SCOPES.map(s => ({ ...s, readonly: false })),
];

export default function Prompts() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  
  const [bundles, setBundles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
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
  
  // Toolbar state
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [sortBy, setSortBy] = useState('updated');
  const [toasts, setToasts] = useState([]);

  const [newBundle, setNewBundle] = useState({
    name: '',
    sections: [{ section_key: 'greeting', scope: 'custom', content: '', order: 0 }],
  });

  const templates = getAllTemplates();

  // Handle test parameter from URL (when redirecting from wizard)
  useEffect(() => {
    const testBundleId = searchParams.get('test');
    if (testBundleId && bundles.length > 0) {
      const bundleToTest = bundles.find(b => b.id === parseInt(testBundleId, 10));
      if (bundleToTest) {
        setTestBundle(bundleToTest);
        // Clear the parameter from URL
        setSearchParams({});
      }
    }
  }, [bundles, searchParams, setSearchParams]);

  useEffect(() => {
    fetchBundles();
  }, []);

  const fetchBundles = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getPromptBundles().catch(() => []);
      setBundles(Array.isArray(data) ? data : []);
    } catch (err) {
      console.error('Failed to fetch bundles:', err);
      setError(err.message || 'Failed to load prompt bundles');
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
      addToast('Prompt created successfully', 'success');
    } catch (err) {
      addToast('Failed to create prompt: ' + err.message, 'error');
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
      addToast('Prompt updated successfully', 'success');
    } catch (err) {
      addToast('Failed to update prompt: ' + err.message, 'error');
    }
  };

  const handlePublish = async (bundleId) => {
    if (!confirm('Publish this prompt? It will become live and active for all chatbot users.')) return;
    setPublishing(bundleId);
    try {
      const updated = await api.publishPromptBundle(bundleId);
      setBundles(bundles.map(b => b.id === updated.id ? updated : b));
      addToast('Prompt published successfully', 'success');
    } catch (err) {
      addToast('Failed to publish prompt: ' + err.message, 'error');
    } finally {
      setPublishing(null);
    }
  };

  const handleDelete = async (bundle) => {
    if (bundle.status === 'production') {
      addToast('Cannot delete a live prompt. Deactivate it first.', 'error');
      return;
    }
    if (!confirm(`Delete "${bundle.name}"?\n\nThis action cannot be undone.`)) return;
    
    setDeleting(bundle.id);
    try {
      await api.deletePromptBundle(bundle.id);
      setBundles(bundles.filter(b => b.id !== bundle.id));
      addToast('Prompt deleted successfully', 'success');
    } catch (err) {
      addToast('Failed to delete prompt: ' + err.message, 'error');
    } finally {
      setDeleting(null);
    }
  };

  const handleDeactivate = async (bundle) => {
    if (!confirm(`Deactivate "${bundle.name}"?\n\nThis will remove it from production. Your chatbot will use default responses until you publish another prompt.`)) return;
    
    setDeactivating(bundle.id);
    try {
      // Call API to demote from production to draft
      const updated = await api.updatePromptBundle(bundle.id, {
        ...bundle,
        status: 'draft'
      });
      setBundles(bundles.map(b => b.id === updated.id ? { ...updated, status: 'draft' } : b));
      addToast('Prompt deactivated successfully', 'success');
    } catch (err) {
      addToast('Failed to deactivate prompt: ' + err.message, 'error');
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
    } catch {
      alert('Failed to load bundle details');
    }
  };

  const addSection = (target, setTarget) => {
    const newSection = {
      section_key: '',
      scope: 'custom', // Default to custom (editable)
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
      draft: { color: '#475569', bg: '#f1f5f9', label: 'Draft', icon: '○' },
      testing: { color: '#d97706', bg: '#fffbeb', label: 'Testing', icon: '●' },
      production: { color: '#059669', bg: '#d1fae5', label: 'Live', icon: '●' },
    };
    const { color, bg, label, icon } = config[status] || config.draft;
    return (
      <span className="status-badge" style={{ backgroundColor: bg, color }}>
        <span className="status-badge__icon">{icon}</span>
        <span className="status-badge__label">{label}</span>
      </span>
    );
  };

  const getScopeInfo = (scopeValue) => {
    return ALL_SCOPES.find(s => s.value === scopeValue) || { label: scopeValue, icon: '📝', readonly: false };
  };

  const isBaseScope = (scope) => BASE_SCOPES.includes(scope);
  const isEditableScope = (scope) => !BASE_SCOPES.includes(scope);

  // Toast management
  const addToast = (message, type = 'success') => {
    const id = Date.now();
    setToasts(prev => [...prev, { id, message, type, duration: 3000 }]);
  };

  const removeToast = (id) => {
    setToasts(prev => prev.filter(t => t.id !== id));
  };

  // Filter and sort bundles
  const filteredAndSortedBundles = useMemo(() => {
    let filtered = bundles;

    // Search filter
    if (searchQuery) {
      const query = searchQuery.toLowerCase();
      filtered = filtered.filter(b => 
        b.name.toLowerCase().includes(query) ||
        b.sections?.some(s => s.section_key?.toLowerCase().includes(query))
      );
    }

    // Status filter
    if (statusFilter !== 'all') {
      filtered = filtered.filter(b => b.status === statusFilter);
    }

    // Sort
    filtered = [...filtered].sort((a, b) => {
      switch (sortBy) {
        case 'name':
          return a.name.localeCompare(b.name);
        case 'updated':
          const aDate = new Date(a.updated_at || a.created_at || 0);
          const bDate = new Date(b.updated_at || b.created_at || 0);
          return bDate - aDate;
        case 'created':
          const aCreated = new Date(a.created_at || 0);
          const bCreated = new Date(b.created_at || 0);
          return bCreated - aCreated;
        default:
          return 0;
      }
    });

    return filtered;
  }, [bundles, searchQuery, statusFilter, sortBy]);

  if (loading) {
    return (
      <div className="prompts-page">
        <LoadingState message="Loading prompts..." fullPage />
      </div>
    );
  }

  if (error) {
    return (
      <div className="prompts-page">
        <ErrorState message={error} onRetry={fetchBundles} />
      </div>
    );
  }

  return (
    <div className="prompts-page">
      <ToastContainer toasts={toasts} removeToast={removeToast} />
      
      {/* Modern Header */}
      <div className="prompts-header">
        <div className="prompts-header__title">
          <h1>Prompts</h1>
          <p className="prompts-header__subtitle">
            Base prompts are system-managed. Create custom prompts to personalize responses.
          </p>
        </div>
        <div className="prompts-header__actions">
          <button 
            className="btn btn--ai"
            onClick={() => navigate('/prompts/wizard')}
          >
            <span className="btn__icon">✨</span>
            Build with AI
          </button>
          <button 
            className="btn btn--primary"
            onClick={() => setShowTemplateSelector(true)}
          >
            <span className="btn__icon">+</span>
            Create Prompt
          </button>
        </div>
      </div>

      {/* Toolbar */}
      <div className="toolbar">
        <div className="toolbar__search">
          <svg className="toolbar__search-icon" width="16" height="16" viewBox="0 0 16 16" fill="none">
            <path d="M7 12A5 5 0 1 0 7 2a5 5 0 0 0 0 10zm0-1.5a3.5 3.5 0 1 1 0-7 3.5 3.5 0 0 1 0 7z" fill="currentColor"/>
            <path d="M10.5 10.5l3 3-1 1-3-3 1-1z" fill="currentColor"/>
          </svg>
          <input
            type="text"
            className="toolbar__search-input"
            placeholder="Search prompts..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>

        <div className="toolbar__filters">
          <div className="toolbar__tabs">
            {[
              { value: 'all', label: 'All' },
              { value: 'production', label: 'Live' },
              { value: 'draft', label: 'Draft' },
              { value: 'testing', label: 'Testing' },
            ].map(tab => (
              <button
                key={tab.value}
                className={`toolbar__tab ${statusFilter === tab.value ? 'toolbar__tab--active' : ''}`}
                onClick={() => setStatusFilter(tab.value)}
              >
                {tab.label}
              </button>
            ))}
          </div>

          <select
            className="toolbar__sort"
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value)}
          >
            <option value="updated">Last updated</option>
            <option value="created">Recently created</option>
            <option value="name">Name (A-Z)</option>
          </select>
        </div>
      </div>

      {/* Template Selector Modal */}
      {showTemplateSelector && (
        <div className="modal-overlay" onClick={() => setShowTemplateSelector(false)}>
          <div className="modal template-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Create New Prompt</h2>
              <button className="modal-close" onClick={() => setShowTemplateSelector(false)}>×</button>
            </div>
            <p className="modal-subtitle">Choose how you want to create your prompt</p>

            {/* AI Wizard - Recommended */}
            <div 
              className="ai-wizard-card"
              onClick={() => {
                setShowTemplateSelector(false);
                navigate('/prompts/wizard');
              }}
            >
              <div className="ai-wizard-card__badge">Recommended</div>
              <div className="ai-wizard-card__icon">✨</div>
              <div className="ai-wizard-card__content">
                <h3>Build with AI Wizard</h3>
                <p>Answer a few questions about your business and we'll create a customized prompt for you. Includes pricing, hours, FAQs, tone of voice, and more.</p>
              </div>
              <div className="ai-wizard-card__arrow">→</div>
            </div>

            <div className="template-divider">
              <span>Or choose a template</span>
            </div>

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
                <h2>Create Prompt: {selectedTemplate.name}</h2>
                {selectedTemplate.id !== 'blank' && (
                  <span className="template-badge">Using Template</span>
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
                <label>Prompt Name</label>
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
                            {EDITABLE_SCOPES.map(s => (
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
              <h2>Create New Prompt</h2>
              <button className="modal-close" onClick={() => { setShowCreate(false); setSelectedTemplate(null); }}>×</button>
            </div>

            <form onSubmit={handleCreate}>
              <div className="form-group">
                <label>Prompt Name</label>
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
                        {EDITABLE_SCOPES.map(s => (
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
                <h2>{editBundle.status === 'production' ? 'View Prompt' : 'Edit Prompt'}: {editBundle.name}</h2>
                {getStatusBadge(editBundle.status)}
              </div>
              <button className="modal-close" onClick={() => setEditBundle(null)}>×</button>
            </div>

            {editBundle.status === 'production' ? (
              <>
                <div className="production-warning">
                  <span className="warning-icon">⚠️</span>
                  <span>This prompt is currently live. To make changes, deactivate it first or create a new draft.</span>
                </div>
                <div className="readonly-sections">
                  {editBundle.sections?.map((section, idx) => {
                    const scopeInfo = getScopeInfo(section.scope);
                    const isBase = isBaseScope(section.scope);
                    return (
                      <div key={idx} className={`section-readonly ${isBase ? 'section-readonly--base' : ''}`}>
                        <div className="section-readonly-header">
                          <span className="scope-icon">{scopeInfo.icon}</span>
                          <span className="section-key-display">{section.section_key}</span>
                          <span className="section-scope-badge">{scopeInfo.label}</span>
                          {isBase && <span className="base-badge">Base (Read-only)</span>}
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
                    {deactivating === editBundle.id ? 'Deactivating...' : 'Deactivate Prompt'}
                  </button>
                  <button type="button" className="btn-secondary" onClick={() => setEditBundle(null)}>
                    Close
                  </button>
                </div>
              </>
            ) : (
              <form onSubmit={handleUpdate}>
                <div className="form-group">
                  <label>Prompt Name</label>
                  <input
                    type="text"
                    value={editBundle.name}
                    onChange={(e) => setEditBundle({ ...editBundle, name: e.target.value })}
                    required
                  />
                </div>

                {/* Base Sections (Read-only) */}
                {editBundle.sections?.some(s => isBaseScope(s.scope)) && (
                  <div className="sections-group">
                    <div className="sections-group-header">
                      <h3>Base Prompts (Read-only)</h3>
                      <span className="sections-group-description">These are system-managed and cannot be edited</span>
                    </div>
                    <div className="sections-list sections-list--readonly">
                      {editBundle.sections
                        .filter(section => isBaseScope(section.scope))
                        .map((section, idx) => {
                          const originalIdx = editBundle.sections.indexOf(section);
                          const scopeInfo = getScopeInfo(section.scope);
                          return (
                            <div key={originalIdx} className="section-readonly section-readonly--base">
                              <div className="section-readonly-header">
                                <span className="scope-icon">{scopeInfo.icon}</span>
                                <span className="section-key-display">{section.section_key}</span>
                                <span className="section-scope-badge">{scopeInfo.label}</span>
                                <span className="base-badge">Base (Read-only)</span>
                              </div>
                              <pre className="section-readonly-content">{section.content}</pre>
                            </div>
                          );
                        })}
                    </div>
                  </div>
                )}

                {/* Editable Sections */}
                <div className="sections-group">
                  <div className="sections-group-header">
                    <h3>Your Custom Prompts</h3>
                    <button
                      type="button"
                      className="btn-secondary btn-small"
                      onClick={() => addSection(editBundle, setEditBundle)}
                    >
                      + Add Custom Section
                    </button>
                  </div>
                  <div className="sections-list">
                    {editBundle.sections
                      .filter(section => isEditableScope(section.scope))
                      .map((section, idx) => {
                        const originalIdx = editBundle.sections.indexOf(section);
                        const scopeInfo = getScopeInfo(section.scope);
                        return (
                          <div key={originalIdx} className="section-editor">
                            <div className="section-editor-header">
                              <span className="scope-icon">{scopeInfo.icon}</span>
                              <input
                                type="text"
                                placeholder="Section key"
                                value={section.section_key}
                                onChange={(e) => updateSection(editBundle, setEditBundle, originalIdx, 'section_key', e.target.value)}
                                required
                              />
                              <select
                                value={section.scope}
                                onChange={(e) => updateSection(editBundle, setEditBundle, originalIdx, 'scope', e.target.value)}
                              >
                                {EDITABLE_SCOPES.map(s => (
                                  <option key={s.value} value={s.value}>{s.label}</option>
                                ))}
                              </select>
                              <button
                                type="button"
                                className="btn-danger-small"
                                onClick={() => removeSection(editBundle, setEditBundle, originalIdx)}
                              >
                                Remove
                              </button>
                            </div>
                            <textarea
                              value={section.content}
                              onChange={(e) => updateSection(editBundle, setEditBundle, originalIdx, 'content', e.target.value)}
                              rows={6}
                              required
                            />
                          </div>
                        );
                      })}
                    {editBundle.sections?.filter(s => isEditableScope(s.scope)).length === 0 && (
                      <div className="empty-sections-message">
                        <p>No custom sections yet. Click "+ Add Custom Section" to create your first editable prompt.</p>
                      </div>
                    )}
                  </div>
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

      {/* Prompts List */}
      <div className="prompts-content">
        {bundles.length === 0 ? (
          <div className="empty-state-wizard">
            <div className="empty-state-wizard__icon">💬</div>
            <h2>No custom prompts yet</h2>
            <p>Create your first chatbot prompt. We recommend using the AI Wizard - just answer a few questions about your business!</p>
            <div className="empty-state-wizard__actions">
              <button 
                className="btn btn--ai btn--lg"
                onClick={() => navigate('/prompts/wizard')}
              >
                <span className="btn__icon">✨</span>
                Build with AI Wizard
              </button>
              <button 
                className="btn btn--ghost"
                onClick={() => setShowTemplateSelector(true)}
              >
                Or use a template
              </button>
            </div>
          </div>
        ) : filteredAndSortedBundles.length === 0 ? (
          <div className="prompts-empty-filter">
            <p>No prompts match your filters.</p>
            <button 
              className="btn btn--ghost"
              onClick={() => {
                setSearchQuery('');
                setStatusFilter('all');
              }}
            >
              Clear filters
            </button>
          </div>
        ) : (
          <div className="prompts-list">
            {filteredAndSortedBundles.map((bundle) => {
              const updatedAt = bundle.updated_at || bundle.created_at;
              const isLive = bundle.status === 'production';
              
              return (
                <div 
                  key={bundle.id} 
                  className={`prompt-item ${isLive ? 'prompt-item--live' : ''}`}
                >
                  <div className="prompt-item__main">
                    <div className="prompt-item__header">
                      <h3 className="prompt-item__title">{bundle.name}</h3>
                      {getStatusBadge(bundle.status)}
                    </div>
                    
                    <div className="prompt-item__meta">
                      <span className="prompt-item__meta-item">
                        {bundle.sections?.length || 0} sections
                      </span>
                      {updatedAt && (
                        <span className="prompt-item__meta-item">
                          Updated {new Date(updatedAt).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                        </span>
                      )}
                      {bundle.published_at && (
                        <span className="prompt-item__meta-item">
                          Published {new Date(bundle.published_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                        </span>
                      )}
                    </div>
                  </div>

                  <div className="prompt-item__actions">
                    <button 
                      className="btn btn--ghost btn--sm"
                      onClick={() => openEdit(bundle)}
                      title={bundle.status === 'production' ? 'View' : 'Edit'}
                    >
                      {bundle.status === 'production' ? 'View' : 'Edit'}
                    </button>
                    
                    <button 
                      className="btn btn--ghost btn--sm"
                      onClick={() => setTestBundle(bundle)}
                      title="Test prompt"
                    >
                      Test
                    </button>
                    
                    {bundle.status === 'production' ? (
                      <button
                        className="btn btn--ghost btn--sm btn--warning"
                        onClick={() => handleDeactivate(bundle)}
                        disabled={deactivating === bundle.id}
                        title="Deactivate"
                      >
                        {deactivating === bundle.id ? 'Deactivating...' : 'Deactivate'}
                      </button>
                    ) : (
                      <>
                        <button
                          className="btn btn--primary btn--sm"
                          onClick={() => handlePublish(bundle.id)}
                          disabled={publishing === bundle.id}
                          title="Publish to production"
                        >
                          {publishing === bundle.id ? 'Publishing...' : 'Publish'}
                        </button>
                        <button
                          className="btn btn--ghost btn--sm btn--danger"
                          onClick={() => handleDelete(bundle)}
                          disabled={deleting === bundle.id}
                          title="Delete"
                        >
                          {deleting === bundle.id ? 'Deleting...' : 'Delete'}
                        </button>
                      </>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
