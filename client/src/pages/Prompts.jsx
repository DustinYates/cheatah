import { useState, useEffect, useMemo, useRef } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { api } from '../api/client';
import { LoadingState, EmptyState, ErrorState } from '../components/ui';
import { ToastContainer } from '../components/ui/Toast';
import { formatDateTimeParts } from '../utils/dateFormat';
import { useAuth } from '../context/AuthContext';
import './Prompts.css';

// ========================================
// Utility Components
// ========================================

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

// ========================================
// Collapsible Section Component
// ========================================

function CollapsibleSection({ title, badge, helperText, defaultOpen = false, children }) {
  const [isOpen, setIsOpen] = useState(defaultOpen);

  return (
    <div className={`prompts-section ${isOpen ? '' : 'prompts-section--collapsed'}`}>
      <div
        className="prompts-section__header"
        onClick={() => setIsOpen(!isOpen)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            setIsOpen(!isOpen);
          }
        }}
        role="button"
        tabIndex={0}
        aria-expanded={isOpen}
      >
        <div className="prompts-section__header-left">
          <span className="prompts-section__chevron">
            {isOpen ? '▼' : '▶'}
          </span>
          <span className="prompts-section__title">{title}</span>
          {helperText && (
            <span className="prompts-section__helper">{helperText}</span>
          )}
        </div>
        {badge}
      </div>
      <div className="prompts-section__content">{children}</div>
    </div>
  );
}

// ========================================
// Channel Prompts Section (Web, Voice, SMS tabs)
// ========================================

const CHANNEL_TABS = [
  { key: 'web', label: 'Web Chat', icon: '💬', description: 'Website chatbot prompt' },
  { key: 'voice', label: 'Voice', icon: '📞', description: 'Phone/voice bot prompt' },
  { key: 'sms', label: 'SMS', icon: '📱', description: 'Text message bot prompt' },
];

// ========================================
// Master Prompt Generator
// ========================================

function MasterPromptGenerator({ value, onChange, onGenerate }) {
  return (
    <div className="master-prompt-card">
      <div className="master-prompt-card__header">
        <div>
          <h2>Tenant Prompt Drop-In</h2>
          <p>Paste the tenant’s source prompt once. We’ll generate channel-safe versions for Web, Voice, and SMS.</p>
        </div>
        <button
          className="btn btn--primary"
          onClick={onGenerate}
          disabled={!value.trim()}
        >
          Generate channel prompts
        </button>
      </div>

      <textarea
        className="master-prompt-card__textarea"
        placeholder="Paste the tenant prompt or working doc here. We’ll apply channel-specific rules automatically."
        value={value}
        onChange={(e) => onChange(e.target.value)}
        rows={8}
        spellCheck={false}
      />
    </div>
  );
}

function ArchivePromptStorage({ value, onChange }) {
  return (
    <div className="master-prompt-card">
      <div className="master-prompt-card__header">
        <div>
          <h2>Archive: Previous LLM Versions</h2>
          <p>Drop older prompt drafts here for reference only. This storage does not affect the live prompts.</p>
        </div>
      </div>

      <textarea
        className="master-prompt-card__textarea"
        placeholder="Paste prior LLM prompt versions or notes. Not used by the generator."
        value={value}
        onChange={(e) => onChange(e.target.value)}
        rows={8}
        spellCheck={false}
      />
    </div>
  );
}

function ChannelPromptsSection({
  channelPrompts,
  activeChannel,
  setActiveChannel,
  onSave,
  onDelete,
  saving,
  loading,
  addToast,
  injectedPrompts,
}) {
  const [editedPrompt, setEditedPrompt] = useState('');
  const [hasChanges, setHasChanges] = useState(false);

  // Update edited prompt when channel changes or prompts load
  useEffect(() => {
    const promptKey = `${activeChannel}_prompt`;
    const injected = injectedPrompts?.[activeChannel];
    if (injected !== undefined && injected !== null) {
      setEditedPrompt(injected);
      setHasChanges(true);
      return;
    }
    const currentPrompt = channelPrompts?.[promptKey] || '';
    setEditedPrompt(currentPrompt);
    setHasChanges(false);
  }, [activeChannel, channelPrompts, injectedPrompts]);

  const handlePromptChange = (value) => {
    setEditedPrompt(value);
    const promptKey = `${activeChannel}_prompt`;
    const originalPrompt = channelPrompts?.[promptKey] || '';
    setHasChanges(value !== originalPrompt);
  };

  const handleSave = async () => {
    await onSave(activeChannel, editedPrompt);
    setHasChanges(false);
  };

  const handleDelete = async () => {
    if (!confirm(`Delete the ${activeChannel} prompt? The channel will fall back to assembled prompts.`)) return;
    await onDelete(activeChannel);
    setEditedPrompt('');
    setHasChanges(false);
  };

  const handleCopy = async () => {
    if (!editedPrompt) return;
    try {
      await navigator.clipboard.writeText(editedPrompt);
      addToast('Prompt copied to clipboard', 'success');
    } catch (err) {
      addToast('Failed to copy prompt: ' + err.message, 'error');
    }
  };

  const currentTab = CHANNEL_TABS.find(t => t.key === activeChannel);
  const hasPrompt = editedPrompt && editedPrompt.trim().length > 0;

  if (loading) {
    return (
      <div className="channel-prompts-section">
        <div className="channel-prompts-loading">
          <span>Loading channel prompts...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="channel-prompts-section">
      {/* Channel Tabs */}
      <div className="channel-tabs">
        {CHANNEL_TABS.map((tab) => {
          const promptKey = `${tab.key}_prompt`;
          const hasContent = channelPrompts?.[promptKey];
          return (
            <button
              key={tab.key}
              className={`channel-tab ${activeChannel === tab.key ? 'channel-tab--active' : ''} ${hasContent ? 'channel-tab--has-content' : ''}`}
              onClick={() => setActiveChannel(tab.key)}
            >
              <span className="channel-tab__icon">{tab.icon}</span>
              <span className="channel-tab__label">{tab.label}</span>
              {hasContent && <span className="channel-tab__indicator">●</span>}
            </button>
          );
        })}
      </div>

      {/* Editor Area */}
      <div className="channel-editor">
        <div className="channel-editor__header">
          <div className="channel-editor__title">
            <span className="channel-editor__icon">{currentTab?.icon}</span>
            <div>
              <h3>{currentTab?.label} Prompt</h3>
              <p className="channel-editor__description">{currentTab?.description}</p>
            </div>
          </div>
          <div className="channel-editor__status">
            {hasPrompt ? (
              <span className="status-pill status-pill--live">
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
        </div>

        <textarea
          className="channel-editor__textarea"
          value={editedPrompt}
          onChange={(e) => handlePromptChange(e.target.value)}
          placeholder={`Enter the full system prompt for ${currentTab?.label}...`}
          rows={20}
          spellCheck={false}
        />

        <div className="channel-editor__footer">
          <div className="channel-editor__meta">
            {hasChanges && <span className="channel-editor__unsaved">Unsaved changes</span>}
            <span className="channel-editor__char-count">{editedPrompt.length.toLocaleString()} characters</span>
          </div>
          <div className="channel-editor__actions">
            <button
              className="btn btn--ghost"
              onClick={handleCopy}
              disabled={!hasPrompt}
            >
              Copy Prompt
            </button>
            {hasPrompt && (
              <button
                className="btn btn--ghost btn--danger"
                onClick={handleDelete}
                disabled={saving}
              >
                Delete Prompt
              </button>
            )}
            <button
              className="btn btn--primary"
              onClick={handleSave}
              disabled={saving || !hasChanges}
            >
              {saving ? 'Saving...' : 'Save Prompt'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ========================================
// Live Prompt Section (Hero) - Legacy
// ========================================

function LivePromptSection({
  config,
  baseConfig,
  onPreview,
  onEditConfig,
  previewLoading,
  configLoading,
}) {
  const hasActiveConfig = config !== null;

  if (configLoading) {
    return (
      <div className="live-prompt-section">
        <div className="live-prompt-card live-prompt-card--loading">
          <span>Loading prompt configuration...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="live-prompt-section">
      <div className="live-prompt-card">
        <div className="live-prompt-card__header">
          <div className="live-prompt-card__title">
            <span className="live-prompt-card__icon">✓</span>
            <div>
              <h2>Live Combined Prompt</h2>
              <p className="live-prompt-card__pipeline">
                Base Config + Tenant Config = Final Prompt
              </p>
            </div>
          </div>
          <span className="status-pill status-pill--live">
            <span className="status-pill__icon">●</span>
            <span className="status-pill__label">Live</span>
          </span>
        </div>

        <div className="live-prompt-card__actions">
          <button
            className="btn btn--primary"
            onClick={onPreview}
            disabled={previewLoading || !hasActiveConfig}
          >
            {previewLoading ? 'Loading...' : 'Preview Combined (Live)'}
          </button>
          <button
            className="btn btn--ghost"
            onClick={onEditConfig}
          >
            Edit Tenant Config
          </button>
        </div>

        {!hasActiveConfig && (
          <div className="live-prompt-card__warning">
            <span>⚠️</span>
            <span>No Tenant Config set. The chatbot is using base config only.</span>
          </div>
        )}
      </div>
    </div>
  );
}

// ========================================
// Backup Item Component
// ========================================

function BackupItem({
  bundle,
  onView,
  onTest,
  onRestore,
  onDelete,
  restoring,
  deleting,
  showIds,
}) {
  const updatedAt = bundle.updated_at || bundle.created_at;

  return (
    <div className="backup-item">
      <div className="backup-item__main">
        <div className="backup-item__row">
          <div className="backup-item__title-group">
            <h3 className="backup-item__title">{bundle.name}</h3>
            <span className="status-pill status-pill--backup">
              <span className="status-pill__icon">📦</span>
              <span className="status-pill__label">Backup - Not used</span>
            </span>
          </div>
          <div className="backup-item__meta">
            {updatedAt && (
              <span className="backup-item__meta-item">
                Updated {formatDateTimeParts(updatedAt).date}
              </span>
            )}
            {showIds && bundle.id !== undefined && (
              <RevealField label="ID" value={bundle.id} />
            )}
          </div>
        </div>
      </div>

      <div className="backup-item__actions">
        <button
          className="btn btn--ghost btn--sm"
          onClick={() => onView(bundle)}
        >
          View
        </button>
        <button
          className="btn btn--ghost btn--sm"
          onClick={() => onTest(bundle)}
        >
          Test
        </button>
        <button
          className="btn btn--secondary btn--sm"
          onClick={() => onRestore(bundle)}
          disabled={restoring === bundle.id}
        >
          {restoring === bundle.id ? 'Restoring...' : 'Restore'}
        </button>
        <button
          className="btn btn--ghost btn--sm btn--danger"
          onClick={() => onDelete(bundle)}
          disabled={deleting === bundle.id}
        >
          {deleting === bundle.id ? 'Deleting...' : 'Delete'}
        </button>
      </div>
    </div>
  );
}

// ========================================
// Constants
// ========================================

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

// ========================================
// Main Prompts Component
// ========================================

export default function Prompts() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { user, selectedTenantId } = useAuth();
  const isGlobalAdmin = user?.is_global_admin;
  const needsTenant = isGlobalAdmin && !selectedTenantId;

  // V2 Config State (lifted from V2ConfigSection)
  const [baseConfig, setBaseConfig] = useState(null);
  const [config, setConfig] = useState(null);
  const [configLoading, setConfigLoading] = useState(true);
  const [showConfigModal, setShowConfigModal] = useState(false);
  const [showBaseModal, setShowBaseModal] = useState(false);
  const [jsonInput, setJsonInput] = useState('');
  const [saving, setSaving] = useState(false);
  const [validating, setValidating] = useState(false);
  const [validationResult, setValidationResult] = useState(null);
  const [previewPrompt, setPreviewPrompt] = useState(null);
  const [previewChannel, setPreviewChannel] = useState('chat');
  const [showPreview, setShowPreview] = useState(false);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [masterPrompt, setMasterPrompt] = useState('');
  const [generatedPrompts, setGeneratedPrompts] = useState(null);
  const [archivedPrompt, setArchivedPrompt] = useState('');

  // Bundles State (backups)
  const [bundles, setBundles] = useState([]);
  const [bundlesLoading, setBundlesLoading] = useState(true);
  const [error, setError] = useState(null);
  const [editBundle, setEditBundle] = useState(null);
  const [testBundle, setTestBundle] = useState(null);
  const [testMessages, setTestMessages] = useState([]);
  const [testInput, setTestInput] = useState('');
  const [testResult, setTestResult] = useState(null);
  const [testLoading, setTestLoading] = useState(false);
  const [restoring, setRestoring] = useState(null);
  const [deleting, setDeleting] = useState(null);
  const [deactivating, setDeactivating] = useState(null);
  const lastTestMessageRef = useRef(null);

  // Toolbar state (for backups section)
  const [searchQuery, setSearchQuery] = useState('');
  const [sortBy, setSortBy] = useState('updated');
  const [toasts, setToasts] = useState([]);

  // Voice prompt state
  const [activeTab, setActiveTab] = useState('sections');
  const [voicePrompt, setVoicePrompt] = useState(null);
  const [voiceLoading, setVoiceLoading] = useState(false);
  const [voiceCopied, setVoiceCopied] = useState(false);

  // Channel prompts state (unified architecture)
  const [channelPrompts, setChannelPrompts] = useState(null);
  const [channelPromptsLoading, setChannelPromptsLoading] = useState(true);
  const [activeChannel, setActiveChannel] = useState('web');
  const [channelSaving, setChannelSaving] = useState(false);

  // ========================================
  // Prompt Generator (master -> channel variants)
  // ========================================

  const buildWebPrompt = (context) => `Channel: Web Chat (Text UI)
Primary goal: Accuracy, clarity, and structured guidance.

Channel rules:
- Allowed: URLs and clickable links, bullet lists/tables, multiple questions in one turn, explicit confirmations, step-by-step instructions, repeating info verbatim when helpful.
- Restrictions: Do not assume intent—confirm before actions. Do not capture PII without consent. Avoid long paragraphs; chunk responses. No silent state changes—narrate what you are doing.
- Special rules: Can show full addresses and pricing numerically. Can ask for email/phone inline. Maintain visible state (e.g., "Step 2 of 4").

Tenant context (ground your answers in this): 
${context}

Response style:
- Label steps and confirm before progressing.
- Keep answers scannable with bullets and short paragraphs.
- Restate critical info (locations, schedules, policies, pricing) exactly as provided.`;

  const buildVoicePrompt = (context) => `Channel: Voice (Phone / IVR / AI Voice)
Primary goal: Natural speech, zero ambiguity, zero cognitive load.

Hard restrictions (critical):
- Never read or spell URLs, email addresses, full street addresses, symbols, or formatting.
- Never speak the words "slash", "dot", "dash", "underscore", "percent", or "colon".
- Never stack questions; ask one at a time.
- Never give dense lists (>3 items).

Required behaviors:
- Always confirm understanding after key steps; narrate step changes ("Moving to enrollment step.").
- Ask for ZIP code before discussing locations.
- Use speech-safe phrasing only.
- For email addresses, spell letter-by-letter only during confirmation.

Special rules:
- Pricing must be verbalized (e.g., "two hundred sixty six dollars"), not shown.
- Links are not spoken; offer to send via SMS/email instead.

Tenant context (convert to speech-safe responses; summarize addresses/links instead of reading them):
${context}

Speech style:
- One question at a time, short confirmations ("Got it.", "Okay.").
- Offer to send details via SMS/email for anything with links/addresses.
- Keep lists to max 3 items; otherwise summarize and offer details via SMS.`;

  const buildSmsPrompt = (context) => `Channel: SMS / Text Messaging
Primary goal: Brevity, clarity, low interruption.

Channel rules:
- Allowed: Short links, one idea per message, yes/no or single-choice questions, simple confirmations, quick follow-up nudges.
- Restrictions: No long explanations, no multi-step flows in one message, no walls of text, avoid back-and-forth loops.
- Required: Each message must be skimmable in <5 seconds and include its own context (assume the user may come back later).
- Special rules: Links are okay. Addresses should be shortened (cross streets preferred). Pricing should be summarized, not itemized. Avoid emojis unless brand-approved.

Tenant context (condense to SMS-friendly snippets):
${context}

Message style:
- Keep to 1–3 short sentences; prefer numbered or bullet-like lines.
- Always include quick context and a single clear action/question.
- Use links sparingly; avoid long addresses—shorten to cross streets or area.`;

  const generateChannelPrompts = () => {
    const context = masterPrompt.trim();
    if (!context) {
      addToast('Paste the tenant prompt before generating channel versions.', 'error');
      return;
    }
    const newPrompts = {
      web: buildWebPrompt(context),
      voice: buildVoicePrompt(context),
      sms: buildSmsPrompt(context),
    };
    setGeneratedPrompts(newPrompts);
    setActiveChannel('web');
    addToast('Generated channel-safe prompts. Review and save each one.', 'success');
  };

  // ========================================
  // Data Fetching
  // ========================================

  useEffect(() => {
    if (!isGlobalAdmin || needsTenant) {
      setConfigLoading(false);
      setBundlesLoading(false);
      return;
    }
    fetchAllData();
  }, [isGlobalAdmin, needsTenant, selectedTenantId]);

  useEffect(() => {
    if (!showConfigModal) {
      return undefined;
    }
    const originalOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = originalOverflow;
    };
  }, [showConfigModal]);

  const fetchAllData = async () => {
    await Promise.all([fetchConfig(), fetchBundles(), fetchChannelPrompts()]);
  };

  const fetchChannelPrompts = async () => {
    setChannelPromptsLoading(true);
    try {
      const data = await api.getChannelPrompts();
      setChannelPrompts(data);
    } catch (err) {
      console.error('Failed to fetch channel prompts:', err);
      setChannelPrompts(null);
    } finally {
      setChannelPromptsLoading(false);
    }
  };

  const fetchConfig = async () => {
    setConfigLoading(true);
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
      setConfigLoading(false);
    }
  };

  const fetchBundles = async () => {
    setBundlesLoading(true);
    setError(null);
    try {
      const data = await api.getPromptBundles().catch(() => []);
      setBundles(Array.isArray(data) ? data : []);
    } catch (err) {
      console.error('Failed to fetch bundles:', err);
      setError(err.message || 'Failed to load prompt bundles');
    } finally {
      setBundlesLoading(false);
    }
  };

  // Handle test parameter from URL (when redirecting from wizard)
  useEffect(() => {
    const testBundleId = searchParams.get('test');
    if (testBundleId && bundles.length > 0) {
      const bundleToTest = bundles.find(b => b.id === parseInt(testBundleId, 10));
      if (bundleToTest) {
        openTest(bundleToTest);
        setSearchParams({});
      }
    }
  }, [bundles, searchParams, setSearchParams]);

  // Scroll to the start of the last message
  useEffect(() => {
    if (lastTestMessageRef.current) {
      lastTestMessageRef.current.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }, [testMessages, testLoading]);

  // ========================================
  // Access Control
  // ========================================

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

  // ========================================
  // Config Handlers
  // ========================================

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

  const handleSaveConfig = async () => {
    setSaving(true);
    try {
      const parsed = JSON.parse(jsonInput);
      const result = await api.upsertPromptConfig(parsed);
      setConfig(result);
      setShowConfigModal(false);
      addToast('Prompt config saved successfully!', 'success');
      setValidationResult(null);
    } catch (err) {
      if (err instanceof SyntaxError) {
        addToast('Invalid JSON syntax: ' + err.message, 'error');
      } else {
        addToast('Failed to save: ' + err.message, 'error');
      }
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteConfig = async () => {
    if (!confirm('Delete the prompt config? The chatbot will fall back to base config only.')) return;
    try {
      await api.deletePromptConfig();
      setConfig(null);
      setJsonInput('');
      addToast('Prompt config deleted', 'success');
    } catch (err) {
      addToast('Failed to delete: ' + err.message, 'error');
    }
  };

  const handlePreview = async () => {
    setPreviewLoading(true);
    try {
      const result = await api.previewPromptConfig(previewChannel);
      setPreviewPrompt(result.prompt);
      setShowPreview(true);
    } catch (err) {
      addToast('Failed to preview: ' + err.message, 'error');
    } finally {
      setPreviewLoading(false);
    }
  };

  // ========================================
  // Channel Prompt Handlers
  // ========================================

  const handleSaveChannelPrompt = async (channel, prompt) => {
    setChannelSaving(true);
    try {
      await api.setChannelPrompt(channel, prompt);
      // Update local state
      setChannelPrompts(prev => ({
        ...prev,
        [`${channel}_prompt`]: prompt,
        [`has_${channel}`]: true,
      }));
      addToast(`${channel.charAt(0).toUpperCase() + channel.slice(1)} prompt saved!`, 'success');
    } catch (err) {
      addToast('Failed to save prompt: ' + err.message, 'error');
    } finally {
      setChannelSaving(false);
    }
  };

  const handleDeleteChannelPrompt = async (channel) => {
    setChannelSaving(true);
    try {
      await api.deleteChannelPrompt(channel);
      // Update local state
      setChannelPrompts(prev => ({
        ...prev,
        [`${channel}_prompt`]: null,
        [`has_${channel}`]: false,
      }));
      addToast(`${channel.charAt(0).toUpperCase() + channel.slice(1)} prompt deleted`, 'success');
    } catch (err) {
      addToast('Failed to delete prompt: ' + err.message, 'error');
    } finally {
      setChannelSaving(false);
    }
  };

  // ========================================
  // Bundle Handlers
  // ========================================

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

  const handleRestore = async (bundle) => {
    if (!confirm(
      `Restore "${bundle.name}" as the active Tenant Config?\n\n` +
      `This will replace the current tenant configuration with this backup.`
    )) return;

    setRestoring(bundle.id);
    try {
      // Try to call restore endpoint if available, otherwise show info message
      if (api.restorePromptBundle) {
        await api.restorePromptBundle(bundle.id);
        await fetchConfig();
        addToast('Prompt restored successfully', 'success');
      } else {
        addToast('Restore functionality coming soon. Please manually copy the prompt content to Tenant Config.', 'info');
      }
    } catch (err) {
      addToast('Failed to restore: ' + err.message, 'error');
    } finally {
      setRestoring(null);
    }
  };

  const handleDeleteBundle = async (bundle) => {
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
    if (!confirm(`Deactivate "${bundle.name}"?\n\nThis will remove it from production.`)) return;

    setDeactivating(bundle.id);
    try {
      const updated = await api.deactivatePromptBundle(bundle.id);
      setBundles(bundles.map(b => b.id === updated.id ? updated : b));
      addToast('Prompt deactivated successfully', 'success');
    } catch (err) {
      addToast('Failed to deactivate prompt: ' + err.message, 'error');
    } finally {
      setDeactivating(null);
    }
  };

  // ========================================
  // Test Handlers
  // ========================================

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

  // ========================================
  // Section Helpers
  // ========================================

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

  const getScopeInfo = (scopeValue) => {
    return ALL_SCOPES.find(s => s.value === scopeValue) || { label: scopeValue, icon: '📝', readonly: false };
  };

  const isBaseScope = (scope) => BASE_SCOPES.includes(scope);
  const isEditableScope = (scope) => !BASE_SCOPES.includes(scope);

  // ========================================
  // Toast Management
  // ========================================

  const addToast = (message, type = 'success') => {
    const id = Date.now();
    setToasts(prev => [...prev, { id, message, type, duration: 3000 }]);
  };

  const removeToast = (id) => {
    setToasts(prev => prev.filter(t => t.id !== id));
  };

  // ========================================
  // Voice Prompt
  // ========================================

  const loadVoicePrompt = async (bundleId) => {
    if (voicePrompt?.bundle_id === bundleId) return;
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

  const resetVoiceState = () => {
    setActiveTab('sections');
    setVoicePrompt(null);
    setVoiceCopied(false);
  };

  // ========================================
  // Filter and Sort Bundles (for Backups)
  // ========================================

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
  }, [bundles, searchQuery, sortBy]);

  // ========================================
  // Loading State
  // ========================================

  if (configLoading && bundlesLoading) {
    return (
      <div className="prompts-page">
        <LoadingState message="Loading prompts..." fullPage />
      </div>
    );
  }

  if (error) {
    return (
      <div className="prompts-page">
        <ErrorState message={error} onRetry={fetchAllData} />
      </div>
    );
  }

  // ========================================
  // Render
  // ========================================

  return (
    <div className="prompts-page">
      <ToastContainer toasts={toasts} removeToast={removeToast} />

      {/* Header */}
      <div className="prompts-header">
        <div className="prompts-header__title">
          <h1>Prompts</h1>
          <p className="prompts-header__subtitle">
            Manage your chatbot's prompt configuration
          </p>
        </div>
      </div>

      {/* Master Prompt Generator */}
      <MasterPromptGenerator
        value={masterPrompt}
        onChange={setMasterPrompt}
        onGenerate={generateChannelPrompts}
      />

      {/* Archive box (reference only) */}
      <ArchivePromptStorage
        value={archivedPrompt}
        onChange={setArchivedPrompt}
      />

      {/* Channel Prompts (Web, Voice, SMS) */}
      <ChannelPromptsSection
        channelPrompts={channelPrompts}
        activeChannel={activeChannel}
        setActiveChannel={setActiveChannel}
        onSave={handleSaveChannelPrompt}
        onDelete={handleDeleteChannelPrompt}
        saving={channelSaving}
        loading={channelPromptsLoading}
        addToast={addToast}
        injectedPrompts={generatedPrompts}
      />

      {/* ========================================
          Modals
          ======================================== */}

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

      {/* Tenant Config Editor Modal */}
      {showConfigModal && (
        <div className="modal-overlay" onClick={() => setShowConfigModal(false)}>
          <div className="modal large-modal v2-config-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>{config ? 'Edit JSON Config' : 'Upload JSON Config'}</h2>
              <button className="modal-close" onClick={() => setShowConfigModal(false)}>×</button>
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
                spellCheck={false}
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
              <button className="btn btn--ghost" onClick={() => setShowConfigModal(false)}>Cancel</button>
              <button className="btn btn--secondary" onClick={handleValidate} disabled={validating || !jsonInput.trim()}>
                {validating ? 'Validating...' : 'Validate'}
              </button>
              <button className="btn btn--primary" onClick={handleSaveConfig} disabled={saving || !jsonInput.trim()}>
                {saving ? 'Saving...' : 'Save Config'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Preview Modal */}
      {showPreview && (
        <div className="modal-overlay" onClick={() => setShowPreview(false)}>
          <div className="modal large-modal preview-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Live Prompt Preview</h2>
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
                    addToast('Copied to clipboard!', 'success');
                  } catch (err) {
                    addToast('Failed to copy', 'error');
                  }
                }}
              >
                Copy to Clipboard
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Edit Bundle Modal (for viewing/editing backups) */}
      {editBundle && (
        <div className="modal-overlay" onClick={() => { setEditBundle(null); resetVoiceState(); }}>
          <div
            className="modal large-modal"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="modal-header">
              <div className="modal-title-group">
                <h2>View Backup: {editBundle.name}</h2>
                <span className="status-pill status-pill--backup">
                  <span className="status-pill__icon">📦</span>
                  <span className="status-pill__label">Backup</span>
                </span>
              </div>
              <button className="modal-close" onClick={() => { setEditBundle(null); resetVoiceState(); }}>×</button>
            </div>

            <div className="backup-info-banner">
              <span>ℹ️</span>
              <span>This is a backup prompt. It is not currently used by the chatbot. Use "Restore" to make it active.</span>
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
                className="btn btn--secondary"
                onClick={() => handleRestore(editBundle)}
                disabled={restoring === editBundle.id}
              >
                {restoring === editBundle.id ? 'Restoring...' : 'Restore as Active'}
              </button>
              <button type="button" className="btn btn--ghost" onClick={() => { setEditBundle(null); resetVoiceState(); }}>
                Close
              </button>
            </div>
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
            <p className="modal-subtitle">Chat with the test bot using this backup prompt.</p>
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
    </div>
  );
}
