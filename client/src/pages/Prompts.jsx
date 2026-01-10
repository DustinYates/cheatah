import { useState, useEffect, useMemo, useRef } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { api } from '../api/client';
import { LoadingState, EmptyState, ErrorState } from '../components/ui';
import { ToastContainer } from '../components/ui/Toast';
import { formatDateTimeParts } from '../utils/dateFormat';
import { useAuth } from '../context/AuthContext';
import './Prompts.css';

function RevealField({ label, value }) {
  const [revealed, setRevealed] = useState(false);
  const safeValue = value === null || value === undefined ? '' : String(value);

  return (
    <span className="reveal-field">
      <span className="reveal-field__label">{label}:</span>
      <span className="reveal-field__value">{revealed ? safeValue : '******'}</span>
      <button
        type="button"
        className="reveal-field__toggle"
        onClick={() => setRevealed((prev) => !prev)}
        aria-pressed={revealed}
        aria-label={`${revealed ? 'Hide' : 'Reveal'} ${label}`}
      >
        {revealed ? 'Hide' : 'Reveal'}
      </button>
    </span>
  );
}

// V2 JSON Config Component
function V2ConfigSection({ onToast, showIds }) {
  const [baseConfig, setBaseConfig] = useState(null);
  const [config, setConfig] = useState(null);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [showBaseModal, setShowBaseModal] = useState(false);
  const [jsonInput, setJsonInput] = useState('');
  const [saving, setSaving] = useState(false);
  const [validating, setValidating] = useState(false);
  const [validationResult, setValidationResult] = useState(null);
  const [previewPrompt, setPreviewPrompt] = useState(null);
  const [previewChannel, setPreviewChannel] = useState('chat');
  const [showPreview, setShowPreview] = useState(false);
  const [previewLoading, setPreviewLoading] = useState(false);

  useEffect(() => {
    fetchAll();
  }, []);

  const fetchAll = async () => {
    setLoading(true);
    try {
      const [baseData, tenantData] = await Promise.all([
        api.getBaseConfig().catch(() => null),
        api.getPromptConfig().catch(() => null),
      ]);
      setBaseConfig(baseData);
      setConfig(tenantData);
      if (tenantData?.config) {
        setJsonInput(JSON.stringify(tenantData.config, null, 2));
      }
    } catch (err) {
      setConfig(null);
    } finally {
      setLoading(false);
    }
  };

  const handleValidate = async () => {
    setValidating(true);
    setValidationResult(null);
    try {
      const parsed = JSON.parse(jsonInput);
      const result = await api.validatePromptConfig(parsed);
      setValidationResult(result);
    } catch (err) {
      if (err instanceof SyntaxError) {
        setValidationResult({ valid: false, message: 'Invalid JSON syntax', errors: [{ message: err.message }] });
      } else {
        setValidationResult({ valid: false, message: err.message });
      }
    } finally {
      setValidating(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const parsed = JSON.parse(jsonInput);
      const result = await api.upsertPromptConfig(parsed);
      setConfig(result);
      setShowModal(false);
      onToast('Prompt config saved successfully!', 'success');
      setValidationResult(null);
    } catch (err) {
      if (err instanceof SyntaxError) {
        onToast('Invalid JSON syntax: ' + err.message, 'error');
      } else {
        onToast('Failed to save: ' + err.message, 'error');
      }
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!confirm('Delete the v2 prompt config? The chatbot will fall back to v1 prompts.')) return;
    try {
      await api.deletePromptConfig();
      setConfig(null);
      setJsonInput('');
      onToast('Prompt config deleted', 'success');
    } catch (err) {
      onToast('Failed to delete: ' + err.message, 'error');
    }
  };

  const handlePreview = async () => {
    setPreviewLoading(true);
    try {
      const result = await api.previewPromptConfig(previewChannel);
      setPreviewPrompt(result.prompt);
      setShowPreview(true);
    } catch (err) {
      onToast('Failed to preview: ' + err.message, 'error');
    } finally {
      setPreviewLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="v2-config-section">
        <div className="v2-config-card v2-config-card--loading">
          <span>Loading prompt configuration...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="v2-config-section">
      <div className="v2-config-header-row">
        <h3 className="v2-section-title">Prompt Configuration (v2)</h3>
        <p className="v2-section-subtitle">Base rules + tenant-specific data combine into the final prompt</p>
      </div>

      <div className="v2-config-grid">
        {/* Base Config Card (Read-only) */}
        <div className="v2-config-card v2-config-card--base">
          <div className="v2-config-header">
            <div className="v2-config-title">
              <span className="v2-config-icon">⚙️</span>
              <div>
                <h3>Base Config</h3>
                <p className="v2-config-subtitle">Hardcoded conversation rules</p>
              </div>
            </div>
            <span className="status-pill status-pill--system">
              <span className="status-pill__icon">🔒</span>
              <span className="status-pill__label">System</span>
            </span>
          </div>

          {baseConfig && (
            <div className="v2-config-sections-list">
              {Object.keys(baseConfig.sections || {}).slice(0, 4).map((key) => (
                <span key={key} className="v2-section-chip">{key}</span>
              ))}
              {Object.keys(baseConfig.sections || {}).length > 4 && (
                <span className="v2-section-chip v2-section-chip--more">+{Object.keys(baseConfig.sections).length - 4} more</span>
              )}
            </div>
          )}

          <div className="v2-config-actions">
            <button className="btn btn--ghost btn--sm" onClick={() => setShowBaseModal(true)}>
              View Base Rules
            </button>
          </div>
        </div>

        {/* Tenant Config Card (Editable) */}
        <div className={`v2-config-card ${config ? 'v2-config-card--active' : ''}`}>
          <div className="v2-config-header">
            <div className="v2-config-title">
              <span className="v2-config-icon">📋</span>
              <div>
                <h3>Tenant Config</h3>
                <p className="v2-config-subtitle">
                  {config ? 'Locations, levels, tuition, policies' : 'Not configured yet'}
                </p>
              </div>
            </div>
            {config ? (
              <span className="status-pill status-pill--active">
                <span className="status-pill__icon">●</span>
                <span className="status-pill__label">Active</span>
              </span>
            ) : (
              <span className="status-pill status-pill--muted">
                <span className="status-pill__icon">○</span>
                <span className="status-pill__label">Not Set</span>
              </span>
            )}
          </div>

          {config && (
            <div className="v2-config-meta">
              <span>Updated: {formatDateTimeParts(config.updated_at).date}</span>
              {showIds && config.id !== undefined && config.id !== null && (
                <RevealField label="Config ID" value={config.id} />
              )}
            </div>
          )}

          <div className="v2-config-actions">
            <button className="btn btn--primary btn--sm" onClick={() => setShowModal(true)}>
              {config ? 'Edit Config' : 'Upload Config'}
            </button>
            {config && (
              <>
                <button className="btn btn--ghost btn--sm" onClick={handlePreview} disabled={previewLoading}>
                  {previewLoading ? 'Loading...' : 'Preview Combined'}
                </button>
                <button className="btn btn--ghost btn--sm btn--danger" onClick={handleDelete}>
                  Delete
                </button>
              </>
            )}
          </div>
        </div>
      </div>

      {/* Base Config Modal */}
      {showBaseModal && baseConfig && (
        <div className="modal-overlay" onClick={() => setShowBaseModal(false)}>
          <div className="modal large-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Base Configuration (Read-only)</h2>
              <button className="modal-close" onClick={() => setShowBaseModal(false)}>×</button>
            </div>

            <p className="v2-base-hint">
              These are the hardcoded conversation rules that apply to all tenants. They cannot be edited through the UI.
            </p>

            <div className="v2-base-sections">
              {Object.entries(baseConfig.sections || {}).map(([key, content]) => (
                <details key={key} className="v2-base-section">
                  <summary className="v2-base-section-header">
                    <span className="v2-base-section-key">{key}</span>
                    <span className="v2-base-section-preview">{content.substring(0, 60)}...</span>
                  </summary>
                  <pre className="v2-base-section-content">{content}</pre>
                </details>
              ))}
            </div>

            <div className="modal-actions">
              <button className="btn btn--ghost" onClick={() => setShowBaseModal(false)}>Close</button>
            </div>
          </div>
        </div>
      )}

      {showModal && (
        <div className="modal-overlay" onClick={() => setShowModal(false)}>
          <div className="modal large-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>{config ? 'Edit JSON Config' : 'Upload JSON Config'}</h2>
              <button className="modal-close" onClick={() => setShowModal(false)}>×</button>
            </div>

            <div className="v2-config-editor">
              <p className="v2-config-editor-hint">
                Paste the JSON configuration from Google Forms below. The config will be validated before saving.
              </p>
              <textarea
                className="v2-config-textarea"
                value={jsonInput}
                onChange={(e) => {
                  setJsonInput(e.target.value);
                  setValidationResult(null);
                }}
                placeholder='{"schema_version": "bss_chatbot_prompt_v1", "tenant_id": "...", ...}'
                rows={20}
              />

              {validationResult && (
                <div className={`v2-validation-result ${validationResult.valid ? 'v2-validation-result--success' : 'v2-validation-result--error'}`}>
                  <strong>{validationResult.valid ? '✓ Valid' : '✗ Invalid'}</strong>
                  <span>{validationResult.message}</span>
                  {validationResult.errors && (
                    <ul>
                      {validationResult.errors.map((err, i) => (
                        <li key={i}>{err.location ? `${err.location}: ` : ''}{err.message}</li>
                      ))}
                    </ul>
                  )}
                  {validationResult.valid && validationResult.sections_count && (
                    <div className="v2-validation-counts">
                      <span>Locations: {validationResult.sections_count.locations}</span>
                      <span>Levels: {validationResult.sections_count.levels}</span>
                      <span>Tuition: {validationResult.sections_count.tuition}</span>
                      <span>Policies: {validationResult.sections_count.policies}</span>
                    </div>
                  )}
                </div>
              )}
            </div>

            <div className="modal-actions">
              <button className="btn btn--ghost" onClick={() => setShowModal(false)}>Cancel</button>
              <button className="btn btn--secondary" onClick={handleValidate} disabled={validating || !jsonInput.trim()}>
                {validating ? 'Validating...' : 'Validate'}
              </button>
              <button className="btn btn--primary" onClick={handleSave} disabled={saving || !jsonInput.trim()}>
                {saving ? 'Saving...' : 'Save Config'}
              </button>
            </div>
          </div>
        </div>
      )}

      {showPreview && (
        <div className="modal-overlay" onClick={() => setShowPreview(false)}>
          <div className="modal large-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Prompt Preview</h2>
              <button className="modal-close" onClick={() => setShowPreview(false)}>×</button>
            </div>

            <div className="v2-preview-tabs">
              {['chat', 'voice', 'sms'].map((ch) => (
                <button
                  key={ch}
                  className={`v2-preview-tab ${previewChannel === ch ? 'v2-preview-tab--active' : ''}`}
                  onClick={() => {
                    setPreviewChannel(ch);
                    setPreviewLoading(true);
                    api.previewPromptConfig(ch).then((result) => {
                      setPreviewPrompt(result.prompt);
                      setPreviewLoading(false);
                    }).catch(() => setPreviewLoading(false));
                  }}
                >
                  {ch.charAt(0).toUpperCase() + ch.slice(1)}
                </button>
              ))}
            </div>

            <div className="v2-preview-content">
              {previewLoading ? (
                <LoadingState message="Loading preview..." />
              ) : (
                <pre className="v2-preview-text">{previewPrompt}</pre>
              )}
            </div>

            <div className="modal-actions">
              <button className="btn btn--ghost" onClick={() => setShowPreview(false)}>Close</button>
              <button
                className="btn btn--primary"
                onClick={async () => {
                  try {
                    await navigator.clipboard.writeText(previewPrompt);
                    onToast('Copied to clipboard!', 'success');
                  } catch (err) {
                    onToast('Failed to copy', 'error');
                  }
                }}
              >
                Copy to Clipboard
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

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
  const { user, selectedTenantId } = useAuth();
  const isGlobalAdmin = user?.is_global_admin;
  const needsTenant = isGlobalAdmin && !selectedTenantId;
  
  const [bundles, setBundles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [editBundle, setEditBundle] = useState(null);
  const [testBundle, setTestBundle] = useState(null);
  const [testMessages, setTestMessages] = useState([]);
  const [testInput, setTestInput] = useState('');
  const [testResult, setTestResult] = useState(null);
  const [testLoading, setTestLoading] = useState(false);
  const [publishing, setPublishing] = useState(null);
  const [deleting, setDeleting] = useState(null);
  const [deactivating, setDeactivating] = useState(null);
  const lastTestMessageRef = useRef(null);
  
  // Toolbar state
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [sortBy, setSortBy] = useState('updated');
  const [toasts, setToasts] = useState([]);

  // Voice prompt state
  const [activeTab, setActiveTab] = useState('sections');
  const [voicePrompt, setVoicePrompt] = useState(null);
  const [voiceLoading, setVoiceLoading] = useState(false);
  const [voiceCopied, setVoiceCopied] = useState(false);

  // Handle test parameter from URL (when redirecting from wizard)
  useEffect(() => {
    const testBundleId = searchParams.get('test');
    if (testBundleId && bundles.length > 0) {
      const bundleToTest = bundles.find(b => b.id === parseInt(testBundleId, 10));
      if (bundleToTest) {
        openTest(bundleToTest);
        // Clear the parameter from URL
        setSearchParams({});
      }
    }
  }, [bundles, searchParams, setSearchParams]);

  useEffect(() => {
    if (!isGlobalAdmin || needsTenant) {
      setLoading(false);
      return;
    }
    fetchBundles();
  }, [isGlobalAdmin, needsTenant]);

  if (user && !isGlobalAdmin) {
    return (
      <div className="page-container">
        <EmptyState
          icon="🔒"
          title="Admin access required"
          description="Prompt configuration is only accessible to global admins."
        />
      </div>
    );
  }

  if (needsTenant) {
    return (
      <div className="page-container">
        <EmptyState
          icon="🧭"
          title="Select a tenant to manage prompts"
          description="Please select a tenant from the dropdown above to manage prompt configuration."
        />
      </div>
    );
  }

  // Scroll to the start of the last message so users can read from the top
  useEffect(() => {
    if (lastTestMessageRef.current) {
      lastTestMessageRef.current.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }, [testMessages, testLoading]);

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
      // Call dedicated deactivate endpoint
      const updated = await api.deactivatePromptBundle(bundle.id);
      setBundles(bundles.map(b => b.id === updated.id ? updated : b));
      addToast('Prompt deactivated successfully', 'success');
    } catch (err) {
      addToast('Failed to deactivate prompt: ' + err.message, 'error');
    } finally {
      setDeactivating(null);
    }
  };

  const resetTestState = () => {
    setTestMessages([]);
    setTestInput('');
    setTestResult(null);
    setTestLoading(false);
  };

  const handleTest = async (e) => {
    e.preventDefault();
    const message = testInput.trim();
    if (!message || !testBundle) return;

    const history = testMessages.filter((msg) => msg.role !== 'error');
    const nextUserMessage = { role: 'user', content: message };

    setTestMessages((prev) => [...prev, nextUserMessage]);
    setTestInput('');
    setTestLoading(true);
    setTestResult(null);

    try {
      const result = await api.testPrompt(testBundle?.id, message, history);
      setTestMessages((prev) => [
        ...prev,
        { role: 'assistant', content: result.response },
      ]);
      setTestResult({ composed_prompt: result.composed_prompt });
    } catch (err) {
      const errorMessage = err.message || 'Test failed';
      setTestMessages((prev) => [
        ...prev,
        { role: 'error', content: errorMessage },
      ]);
      setTestResult({ error: errorMessage });
    } finally {
      setTestLoading(false);
    }
  };

  const openTest = (bundle) => {
    resetTestState();
    setTestBundle(bundle);
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

  // Load voice prompt for a bundle
  const loadVoicePrompt = async (bundleId) => {
    if (voicePrompt?.bundle_id === bundleId) return; // Already loaded
    setVoiceLoading(true);
    try {
      const data = await api.getVoicePrompt(bundleId);
      setVoicePrompt(data);
    } catch (err) {
      addToast('Failed to generate voice prompt: ' + err.message, 'error');
    } finally {
      setVoiceLoading(false);
    }
  };

  // Reset voice tab state when modal closes
  const resetVoiceState = () => {
    setActiveTab('sections');
    setVoicePrompt(null);
    setVoiceCopied(false);
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
            Use the AI Wizard to create custom prompts for your chatbot.
          </p>
        </div>
        <div className="prompts-header__actions">
          <button
            className="btn btn--ai btn--lg"
            onClick={() => navigate('/settings/prompts/wizard')}
          >
            <span className="btn__icon">✨</span>
            Build with AI
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

        <div className="toolbar__tabs" role="tablist" aria-label="Filter prompts by status">
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
              role="tab"
              aria-selected={statusFilter === tab.value}
              type="button"
            >
              {tab.label}
            </button>
          ))}
        </div>

        <div className="toolbar__sort-wrapper">
          <select
            className="toolbar__sort"
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value)}
            aria-label="Sort prompts"
          >
            <option value="updated">Last updated</option>
            <option value="created">Recently created</option>
            <option value="name">Name (A-Z)</option>
          </select>
        </div>
      </div>

      {/* V2 JSON Config Section */}
      <V2ConfigSection onToast={addToast} showIds={isGlobalAdmin} />

      {/* Edit Bundle Modal */}
      {editBundle && (
        <div className="modal-overlay" onClick={() => { setEditBundle(null); resetVoiceState(); }}>
          <div
            className="modal large-modal"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="modal-header">
              <div className="modal-title-group">
                <h2>{editBundle.status === 'production' ? 'View Prompt' : 'Edit Prompt'}: {editBundle.name}</h2>
                {getStatusBadge(editBundle.status)}
              </div>
              <button className="modal-close" onClick={() => { setEditBundle(null); resetVoiceState(); }}>×</button>
            </div>

            {editBundle.status === 'production' ? (
              <>
                <div className="production-warning">
                  <span className="warning-icon">⚠️</span>
                  <span>This prompt is currently live. To make changes, deactivate it first or create a new draft.</span>
                </div>

                {/* Tab Navigation */}
                <div className="modal-tabs">
                  <button
                    className={`modal-tab ${activeTab === 'sections' ? 'modal-tab--active' : ''}`}
                    onClick={() => setActiveTab('sections')}
                  >
                    Prompt Sections
                  </button>
                  <button
                    className={`modal-tab ${activeTab === 'voice' ? 'modal-tab--active' : ''}`}
                    onClick={() => {
                      setActiveTab('voice');
                      loadVoicePrompt(editBundle.id);
                    }}
                  >
                    Voice Version
                  </button>
                </div>

                {/* Sections Tab Content */}
                {activeTab === 'sections' && (
                  <div className="readonly-sections" tabIndex={0}>
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
                )}

                {/* Voice Tab Content */}
                {activeTab === 'voice' && (
                  <div className="voice-prompt-container">
                    <div className="voice-prompt-header">
                      <h3>Auto-Generated Voice Prompt</h3>
                      <p className="voice-prompt-description">
                        This voice-optimized version is automatically generated from your chat prompt.
                        Copy it to use in Telnyx or other voice platforms.
                      </p>
                    </div>

                    {voiceLoading ? (
                      <div className="voice-prompt-loading">
                        <LoadingState message="Generating voice prompt..." />
                      </div>
                    ) : voicePrompt ? (
                      <>
                        <div className="voice-prompt-content">
                          <pre className="voice-prompt-text">{voicePrompt.voice_prompt}</pre>
                        </div>
                        <div className="voice-prompt-actions">
                          <button
                            className={`btn btn--primary ${voiceCopied ? 'btn--success' : ''}`}
                            onClick={async () => {
                              try {
                                await navigator.clipboard.writeText(voicePrompt.voice_prompt);
                                setVoiceCopied(true);
                                addToast('Voice prompt copied to clipboard!', 'success');
                                setTimeout(() => setVoiceCopied(false), 2000);
                              } catch (err) {
                                addToast('Failed to copy: ' + err.message, 'error');
                              }
                            }}
                          >
                            {voiceCopied ? 'Copied!' : 'Copy to Clipboard'}
                          </button>
                        </div>
                      </>
                    ) : (
                      <div className="voice-prompt-error">
                        Unable to generate voice prompt.
                      </div>
                    )}
                  </div>
                )}

                <div className="modal-actions">
                  <button
                    type="button"
                    className="btn-warning"
                    onClick={() => { setEditBundle(null); resetVoiceState(); handleDeactivate(editBundle); }}
                    disabled={deactivating === editBundle.id}
                  >
                    {deactivating === editBundle.id ? 'Deactivating...' : 'Deactivate Prompt'}
                  </button>
                  <button type="button" className="btn-secondary" onClick={() => { setEditBundle(null); resetVoiceState(); }}>
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
        <div className="modal-overlay" onClick={() => { setTestBundle(null); resetTestState(); }}>
          <div className="modal test-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Test: {testBundle.name}</h2>
              <button className="modal-close" onClick={() => { setTestBundle(null); resetTestState(); }}>×</button>
            </div>
            <p className="modal-subtitle">Chat with the test bot using the same pipeline as production.</p>
            <div className="test-chat">
              <div className="test-chat__header">
                <span className="test-chat__hint">Tip: press Enter to send, Shift+Enter for a new line.</span>
                <button type="button" className="btn btn--ghost btn--sm" onClick={resetTestState}>
                  Clear chat
                </button>
              </div>
              <div className="test-chat__messages">
                {testMessages.length === 0 ? (
                  <div className="test-chat__empty">
                    Start the conversation to see how your chatbot responds.
                  </div>
                ) : (
                  testMessages.map((message, idx) => (
                    <div
                      key={`${message.role}-${idx}`}
                      className={`test-chat__message test-chat__message--${message.role}`}
                      ref={idx === testMessages.length - 1 ? lastTestMessageRef : null}
                    >
                      <div className="test-chat__bubble">{message.content}</div>
                    </div>
                  ))
                )}
                {testLoading && (
                  <div className="test-chat__message test-chat__message--assistant">
                    <div className="test-chat__bubble test-chat__typing">
                      <span />
                      <span />
                      <span />
                    </div>
                  </div>
                )}
              </div>
              <form className="test-chat__composer" onSubmit={handleTest}>
                <textarea
                  value={testInput}
                  onChange={(e) => setTestInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault();
                      handleTest(e);
                    }
                  }}
                  placeholder="Type a message... (e.g., 'What swim classes do you offer for a 4 year old?')"
                  rows={2}
                  disabled={testLoading}
                />
                <button type="submit" className="btn-primary" disabled={testLoading || !testInput.trim()}>
                  {testLoading ? 'Sending...' : 'Send'}
                </button>
              </form>
              {testResult?.composed_prompt && (
                <details className="debug-details">
                  <summary>View Composed Prompt (Debug)</summary>
                  <pre className="composed-prompt">{testResult.composed_prompt}</pre>
                </details>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Prompts List */}
      <div className="prompts-content">
        {bundles.length === 0 ? (
          <div className="empty-state-wizard">
            <div className="empty-state-wizard__icon">💬</div>
            <h2>No custom prompts yet</h2>
            <p>Create your first chatbot prompt using the AI Wizard - just answer a few questions about your business!</p>
            <div className="empty-state-wizard__actions">
              <button
                className="btn btn--ai btn--lg"
                onClick={() => navigate('/settings/prompts/wizard')}
              >
                <span className="btn__icon">✨</span>
                Build with AI Wizard
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
                    <div className="prompt-item__row">
                      <div className="prompt-item__title-group">
                        <h3 className="prompt-item__title">{bundle.name}</h3>
                        {getStatusBadge(bundle.status)}
                      </div>
                      <div className="prompt-item__meta">
                        {updatedAt && (
                          <span className="prompt-item__meta-item">
                            Updated {formatDateTimeParts(updatedAt).date}
                          </span>
                        )}
                        {bundle.published_at && (
                          <span className="prompt-item__meta-item">
                            Published {formatDateTimeParts(bundle.published_at).date}
                          </span>
                        )}
                        {isGlobalAdmin && bundle.id !== undefined && bundle.id !== null && (
                          <RevealField label="ID" value={bundle.id} />
                        )}
                      </div>
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
                      onClick={() => openTest(bundle)}
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
