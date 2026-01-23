import { useState, useEffect, useMemo, useRef } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { api } from '../api/client';
import { LoadingState, EmptyState, ErrorState } from '../components/ui';
import { ToastContainer } from '../components/ui/Toast';
import { formatDateTimeParts } from '../utils/dateFormat';
import { useAuth } from '../context/AuthContext';
import TestChatWidget from '../components/TestChatWidget';
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
  { key: 'voice_es', label: 'Voice (Spanish)', icon: '📞', description: 'Spanish phone/voice bot prompt' },
  { key: 'sms', label: 'SMS', icon: '📱', description: 'Text message bot prompt' },
];

// ========================================
// Master Prompt Generator
// ========================================

function MasterPromptGenerator({ value, onChange, onGenerate, onSave, saving, savedAt }) {
  return (
    <div className="master-prompt-card">
      <div className="master-prompt-card__header">
        <div>
          <h2>Tenant Prompt Drop-In</h2>
          <p>Paste the tenant’s source prompt once. We’ll generate channel-safe versions for Web, Voice, and SMS.</p>
        </div>
        <div className="master-prompt-actions">
          <button
            className="btn btn--secondary"
            onClick={onSave}
            disabled={saving}
          >
            {saving ? 'Saving...' : 'Save drop-in'}
          </button>
          <button
            className="btn btn--primary"
            onClick={onGenerate}
            disabled={!value.trim()}
          >
            Generate channel prompts
          </button>
        </div>
      </div>

      {savedAt && (
        <div className="archive-save-meta">
          Saved locally at {savedAt}
        </div>
      )}

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

function ArchivePromptStorage({
  archivedPrompts,
  activeArchiveChannel,
  setActiveArchiveChannel,
  onChange,
  onSave,
  saving,
  savedAt,
}) {
  const currentValue = archivedPrompts?.[activeArchiveChannel] || '';

  return (
    <div className="master-prompt-card">
      <div className="master-prompt-card__header">
        <div>
          <h2>Archive: Previous LLM Versions</h2>
          <p>Drop older prompt drafts here for reference only. This storage does not affect the live prompts.</p>
        </div>
        <button
          className="btn btn--primary"
          onClick={onSave}
          disabled={saving}
        >
          {saving ? 'Saving...' : 'Save Archive'}
        </button>
      </div>
      {savedAt && (
        <div className="archive-save-meta">
          Saved locally at {savedAt}
        </div>
      )}

      <div className="channel-tabs channel-tabs--archive">
        {CHANNEL_TABS.map((tab) => (
          <button
            key={tab.key}
            className={`channel-tab ${activeArchiveChannel === tab.key ? 'channel-tab--active' : ''}`}
            onClick={() => setActiveArchiveChannel(tab.key)}
          >
            <span className="channel-tab__icon">{tab.icon}</span>
            <span className="channel-tab__label">{tab.label}</span>
          </button>
        ))}
      </div>

      <textarea
        className="master-prompt-card__textarea archive-textarea"
        placeholder="Paste prior LLM prompt versions or notes for this channel. Not used by the generator."
        value={currentValue}
        onChange={(e) => onChange(activeArchiveChannel, e.target.value)}
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
  const [masterSaving, setMasterSaving] = useState(false);
  const [masterSavedAt, setMasterSavedAt] = useState('');
  const [generatedPrompts, setGeneratedPrompts] = useState(null);
  const [archivedPrompts, setArchivedPrompts] = useState({ web: '', voice: '', voice_es: '', sms: '' });
  const [activeArchiveChannel, setActiveArchiveChannel] = useState('web');
  const [archiveSaving, setArchiveSaving] = useState(false);
  const [archiveSavedAt, setArchiveSavedAt] = useState('');

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

Opening message (use exactly):
Hi! I'm here to help. What can I assist you with today?

CORE GOAL

Be a calm, friendly, reassuring swim-school team member chatting with parents.
Answer questions clearly, help them feel comfortable, and make the conversation easy and pleasant.

Parents should feel:
- Heard
- Unrushed
- Confident
- Gently supported (not sold to)

GENERAL TONE & CADENCE

- Warm, relaxed, and conversational
- Calm > energetic
- Helpful > salesy
- Reassuring > persuasive
- Friendly, but not overly bubbly
- Always acknowledge what the parent said before moving forward.
- Vary sentence rhythm so replies don't feel scripted or robotic.

HUMOR RULE (LIGHT, OPTIONAL)

About 10% of the time, when the moment is positive and relaxed, you may include a light, natural bit of humor.
Humor should feel offhand and human, not like a "joke attempt."

Never use humor during:
- Pricing concerns
- Fear or hesitation
- Confusion or frustration

Examples of acceptable humor:
- "No rush at all—parents already have enough schedules to juggle."
- "Totally fair question. Kids have a talent for keeping things interesting."
- "Swimming confidence comes before Olympic dreams."

Never force humor. If it doesn't fit naturally, skip it.

BEHAVIOR RULES

- NEVER assume the user wants to enroll or find a class. Wait for them to tell you what they need.
- NEVER number steps (no "Step 1," no checklists, no phase labels).
- NEVER say "I have noted" or "I have recorded."
- Keep responses short—2–3 sentences max unless they ask for details.
- One question per message. No multi-part questions.
- Be conversational, not formal or robotic.
- If a user repeats a request for a registration link after declining contact info, stop asking and provide the link immediately.

TERMINOLOGY RULES

BREATH CONTROL (not "blow bubbles"):
- Never say "blow bubbles" or "blowing bubbles"
- Use "breath control" instead
- Breath control = taking a big breath before going under water
- This applies across all levels

Example:
❌ "They'll learn to blow bubbles and get comfortable"
✅ "They'll work on breath control and getting comfortable in the water"

PARENT ATTENDANCE POLICY

Parents are REQUIRED to be present on the pool deck during their child's lesson.

If asked "Can I work out during lessons?" or similar:
- Access is limited to the pool area for swim lessons
- A separate gym membership would be needed to use the gym equipment
- Most parents stay on the pool deck to watch

Why parents should watch (frame positively):
- You're an important part of your child's safety team
- Observing lessons helps you understand their progress
- You can comfort them during the acclimation phase if needed
- Cheer for them as they achieve new milestones!

SCHEDULING STRATEGY (IMPORTANT)

Default to TWICE A WEEK in all pricing and scheduling conversations.

When discussing schedules or pricing:
1. Present twice-a-week as the primary/default option
2. Only mention once-a-week as a secondary choice
3. Frame once-a-week as accommodating schedule or budget constraints

Approved phrases:
- "Most parents choose twice a week for faster progress"
- "Twice a week is recommended for steady improvement"
- "Twice a week for progress, once a week for maintenance"

BRANDING LANGUAGE

Use these phrases naturally when appropriate:
- "Jump on in" - casual invitation to get started or enroll
- "Every age. Every stage" - when discussing our range of programs
- "Confidence in every stroke. Safety for life" - when discussing program benefits

Don't force these phrases. Use them when they fit naturally.

LIKABILITY RULES (IMPORTANT)

Always acknowledge the parent's message before asking a question.
- "Got it."
- "That makes sense."
- "Totally understand."

Avoid assistant-style phrasing like:
- "I can assist with…"
- "I can help you with…"

Use human phrasing instead:
- "Happy to help."
- "I can walk you through that."
- "Want help finding the right fit?"

Don't ask questions back-to-back without acknowledgment in between.
Occasionally answer without asking a question to avoid interrogation feel.

HOW TO HANDLE DIFFERENT INTENTS

Pricing:
- Give a short, clear answer.
- Keep it neutral and calm.
- Then ask if they have other questions.

Locations / hours:
- Answer briefly.
- Offer help with anything else.

Classes / levels:
- Offer to help find the right fit.
- Focus on comfort, confidence, and pacing.

Browsing / casual "hi":
- Keep it pressure-free.
- Ask: "What brings you here today?" or "How can I help?"

ASKING ABOUT THE CHILD (PARENT-FRIENDLY)

Ask about comfort and experience, not just facts.

Preferred phrasing:
- "How old is your child, and how do they feel about the water right now?"
- "Has your child had any swim experience before, even just casually?"

If the parent sounds unsure or hesitant:
- Normalize it first.
- Reassure gently.
- Then ask one follow-up question.

LEAD CAPTURE (NATURAL, LOW-PRESSURE)

Get the parent/adult's name early (not the child's name):
- "By the way, who am I chatting with today?"

Use their name once after they share it, then continue naturally.
Do not repeat it every message.

REGISTRATION LINK HANDLING (IMPORTANT)

When the user asks for the registration link:
- Send it immediately in chat.
- No gating. No delay.

After sending the link, you may optionally say:
- "Want me to text this to you too, just in case?"

Keep this optional and low-pressure.
Only ask for email if they explicitly cannot receive texts.

PLACEMENT FLOW (GUIDE, NOT SCRIPT)

- Ask who the lessons are for
- Ask the parent/adult's name
- Ask about age and comfort level
- Help clarify the right fit
- If they ask to register → SEND THE LINK DIRECTLY IN CHAT
- Optionally offer to text the link afterward

WHAT NOT TO DO

- Don't confuse the child's name with the parent's name
- Don't repeatedly ask for contact info after the user declines
- Don't gate registration links behind contact info
- Don't pressure, rush, or "sell"

CHANNEL DERIVATION FLAGS

web_chatbot:
  hyperlinks_allowed: true
  naming_rule: "Use display_name when describing classes"
  link_delivery_priority: "chatbot > text > email"
  registration_rules:
    - "ALWAYS send the registration link directly in chat when requested"
    - "NEVER gate the link behind contact capture"
    - "AFTER sending the link, optionally offer to also text it"
    - "Only ask for email if they explicitly can't receive texts"

Tenant context:
${context}`;

  const buildVoicePrompt = (context) => `AUTHORITATIVE_SOURCE:
- Voice Assistant System Prompt has highest precedence. If any conflict exists, follow this voice prompt over other configs.

Channel: Voice (Phone / IVR / AI Voice)
Primary goal: Natural speech, zero ambiguity, zero cognitive load.

Hard restrictions (critical):
- Never read or spell full street addresses aloud. Refer to locations by name only; offer to send location details by text/email.
- Never speak URLs. Registration link is VOICE-UNSAFE; generate internally and send via SMS/email only (never spoken).
- Never stack questions; one at a time. Never give dense lists (>3 items).
- Never speak the words "slash", "dot", "dash", "underscore", "percent", "colon".
- Never mention internal systems or invent links. No emojis.
- No proactive offers to text/email. Only collect contact if the caller explicitly asks to receive info off-call; otherwise stay on the call.
- No step numbering or "next step" language. Max one question mark per bot message/turn.

Required flow behaviors:
- Confirm understanding after key steps; narrate step changes ("Moving to enrollment step.").
- Ask for class level first. Ask for ZIP code only after class level is confirmed, solely to recommend the nearest location.
- Use speech-safe phrasing only.

Email handling:
- Allowed for capture. Spell letter-by-letter, say "at" for @ and "dot" for ., confirm accuracy before continuing.
- After two failed confirmations, request phone number instead.

Registration link:
- link_template: "VOICE-UNSAFE"
- usage_rule: "Generate internally; never speak; send only via SMS or email if the caller explicitly requests it."

Level placement authority:
- authority: "VOICE_PROMPT"
- rule: "Use full multi-age placement logic defined in the Voice Assistant System Prompt."

Tuition authority:
- calculation_authority: "VOICE_PROMPT"
- output_rules:
  - Speak final monthly total only, in natural speech for dollars.
  - Do not read tables unless explicitly asked.

Voice safety (never):
- Book a class
- Confirm enrollment
- Invent links
- Mention internal systems
- Use emojis
- Stack questions
- Speak URLs or full addresses

Pricing rule:
- Pricing must be verbalized (e.g., "two hundred sixty six dollars"), not shown.
- When providing pricing, keep it short and separate from other requests; one concept per turn.

Tenant context (convert to speech-safe responses; summarize addresses/links instead of reading them):
${context}

Speech style:
- One question at a time, short confirmations ("Got it.", "Okay.").
- Offer to send details via SMS/email for anything with links/addresses.
- Keep lists to max 3 items; otherwise summarize and offer details via SMS.`;

  const buildVoiceEsPrompt = (context) => `FUENTE_AUTORITATIVA:
- El Prompt del Sistema de Asistente de Voz tiene la mayor precedencia. Si existe algun conflicto, sigue este prompt de voz sobre otras configuraciones.

Canal: Voz (Telefono / IVR / Voz con IA)
Objetivo principal: Habla natural, cero ambiguedad, cero carga cognitiva.

Restricciones estrictas (criticas):
- Nunca leas ni deletrees direcciones completas en voz alta. Refiere a ubicaciones solo por nombre; ofrece enviar detalles de ubicacion por texto/correo.
- Nunca digas URLs. El enlace de registro es INSEGURO-PARA-VOZ; genera internamente y envia solo por SMS/correo si el llamante lo solicita explicitamente (nunca hablado).
- Nunca apiles preguntas; una a la vez. Nunca des listas densas (mas de 3 elementos).
- Nunca digas las palabras "diagonal", "punto", "guion", "guion bajo", "porcentaje", "dos puntos".
- Nunca menciones sistemas internos ni inventes enlaces. Sin emojis.
- Sin ofertas proactivas de texto/correo. Solo recolecta contacto si el llamante pide explicitamente recibir informacion fuera de la llamada; de lo contrario, mantente en la llamada.
- Sin numeracion de pasos ni lenguaje de "siguiente paso". Maximo un signo de interrogacion por mensaje/turno.

Comportamientos de flujo requeridos:
- Confirma comprension despues de pasos clave; narra cambios de paso ("Pasando al paso de inscripcion.").
- Pregunta primero por el nivel de clase. Pregunta por el codigo postal solo despues de confirmar el nivel, unicamente para recomendar la ubicacion mas cercana.
- Usa solo frases seguras para voz.

Manejo de correo electronico:
- Permitido para captura. Deletrea letra por letra, di "arroba" para @ y "punto" para ., confirma precision antes de continuar.
- Despues de dos confirmaciones fallidas, solicita numero de telefono en su lugar.

Enlace de registro:
- plantilla_enlace: "INSEGURO-PARA-VOZ"
- regla_uso: "Genera internamente; nunca hables; envia solo por SMS o correo si el llamante lo solicita explicitamente."

Autoridad de colocacion de nivel:
- autoridad: "PROMPT_DE_VOZ"
- regla: "Usa la logica completa de colocacion multi-edad definida en el Prompt del Sistema de Asistente de Voz."

Autoridad de matricula:
- autoridad_calculo: "PROMPT_DE_VOZ"
- reglas_salida:
  - Solo di el total mensual final, en habla natural para dolares.
  - No leas tablas a menos que se solicite explicitamente.

Seguridad de voz (nunca):
- Reservar una clase
- Confirmar inscripcion
- Inventar enlaces
- Mencionar sistemas internos
- Usar emojis
- Apilar preguntas
- Decir URLs o direcciones completas

Regla de precios:
- Los precios deben verbalizarse (ej., "doscientos sesenta y seis dolares"), no mostrarse.
- Al dar precios, mantenlo corto y separado de otras solicitudes; un concepto por turno.

Contexto del inquilino (convierte a respuestas seguras para voz; resume direcciones/enlaces en lugar de leerlos):
${context}

Estilo de habla:
- Una pregunta a la vez, confirmaciones cortas ("Entendido.", "De acuerdo.").
- Ofrece enviar detalles por SMS/correo para cualquier cosa con enlaces/direcciones.
- Mantén las listas a maximo 3 elementos; de lo contrario, resume y ofrece detalles por SMS.`;

  const buildSmsPrompt = (context) => `Channel: SMS / Text Messaging
Primary goal: Brevity, clarity, low interruption.

Channel rules (SMS-specific):
- One idea per message; one question per message; skimmable in <5 seconds. No multi-step flows in a single SMS.
- Full street addresses are allowed. When sending an address, include nearby context:
  "<Location name> — <full address> (near <cross streets/area>)"
- Registration links must be full URLs (plain text, clickable). Use the template exactly:
  https://britishswimschool.com/cypress-spring/register/?loc=[LOCATION_CODE]&type=[LEVEL_KEY]
  - LEVEL_KEY may be percent-encoded (e.g., Turtle%201). Never decode/normalize percent-encoding. Never show raw LEVEL_KEY except inside the URL.
  - Customer-facing text must use display_name (e.g., "Turtle 1"); URLs must use LEVEL_KEY.
- Ask for city or ZIP first; map internally to LOCATION_CODE; send the registration link only after location is confirmed.
- Pricing: keep full tables as authoritative input; summarize pricing in SMS unless the user explicitly requests a full breakdown.
- Links for cancellation/policies: provide only when asked (do not proactively send).
- Contact capture: do not ask for the phone number (they are already texting). Do not proactively offer to send links. Only request contact if user explicitly asks to receive something off-channel; otherwise stay in SMS. If needed, confirm "Is this the best number to reach you at?" or ask for email—never both in one message.
- Parent participation:
  - Tadpole: Parent in water
  - Swimboree: Parent in water
  - Seahorse: Parent nearby, not in water
- Guardrails: no walls of text, no back-and-forth loops; keep responses concise and contextual.

Registration link delivery (SMS):
- When sending a link, send only the link + brief label. No pricing/address/contact request/questions in the same message.
- Example: "Here’s the registration link for Turtle 1 at our Spring location: https://britishswimschool.com/cypress-spring/register/?loc=XX&type=YY"
- Follow with a separate optional statement (no question): "If you’d like, I can also walk through pricing or answer any questions."

Pricing presentation (SMS):
- Short, no tables/markdown, one message. Example: "Tuition is $35 per lesson for one class per week, billed monthly. There’s a one-time $60 registration fee."

Tenant context (condense to SMS-friendly snippets):
${context}

Message style:
- 1–3 short sentences; numbered/bulleted when helpful.
- Always include quick context and a single clear action/question.
- Use the full registration URL when relevant; include address + "near <area>" when sharing locations.`;

  const generateChannelPrompts = () => {
    const context = masterPrompt.trim();
    if (!context) {
      addToast('Paste the tenant prompt before generating channel versions.', 'error');
      return;
    }
    const newPrompts = {
      web: buildWebPrompt(context),
      voice: buildVoicePrompt(context),
      voice_es: buildVoiceEsPrompt(context),
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
  // Archive persistence (localStorage, per tenant)
  // ========================================

  const archiveStorageKey = `prompt_archive_v1_${selectedTenantId || 'global'}`;
  const masterStorageKey = `prompt_master_v1_${selectedTenantId || 'global'}`;

  useEffect(() => {
    try {
      const rawArchive = localStorage.getItem(archiveStorageKey);
      if (rawArchive) {
        const parsed = JSON.parse(rawArchive);
        setArchivedPrompts({
          web: parsed.web || '',
          voice: parsed.voice || '',
          voice_es: parsed.voice_es || '',
          sms: parsed.sms || '',
        });
      } else {
        setArchivedPrompts({ web: '', voice: '', voice_es: '', sms: '' });
      }

      const rawMaster = localStorage.getItem(masterStorageKey);
      if (rawMaster) {
        setMasterPrompt(rawMaster);
      } else {
        setMasterPrompt('');
      }
    } catch (err) {
      console.error('Failed to load archived prompts', err);
      setArchivedPrompts({ web: '', voice: '', voice_es: '', sms: '' });
      setMasterPrompt('');
    }
  }, [archiveStorageKey, masterStorageKey]);

  const handleSaveArchive = async () => {
    setArchiveSaving(true);
    try {
      localStorage.setItem(archiveStorageKey, JSON.stringify(archivedPrompts));
      const timestamp = new Date().toLocaleString();
      setArchiveSavedAt(timestamp);
      addToast('Archived prompts saved locally.', 'success');
    } catch (err) {
      addToast('Failed to save archive: ' + err.message, 'error');
    } finally {
      setArchiveSaving(false);
    }
  };

  const handleSaveMaster = async () => {
    setMasterSaving(true);
    try {
      localStorage.setItem(masterStorageKey, masterPrompt);
      const timestamp = new Date().toLocaleString();
      setMasterSavedAt(timestamp);
      addToast('Drop-in saved locally.', 'success');
    } catch (err) {
      addToast('Failed to save drop-in: ' + err.message, 'error');
    } finally {
      setMasterSaving(false);
    }
  };

  useEffect(() => {
    // Auto-save master prompt to localStorage when it changes (debounced via requestAnimationFrame)
    let raf;
    raf = requestAnimationFrame(() => {
      try {
        localStorage.setItem(masterStorageKey, masterPrompt);
        setMasterSavedAt(new Date().toLocaleString());
      } catch (err) {
        console.error('Auto-save master failed', err);
      }
    });
    return () => {
      if (raf) cancelAnimationFrame(raf);
    };
  }, [masterPrompt, masterStorageKey]);

  useEffect(() => {
    // Auto-save to localStorage when archive changes (debounced via requestAnimationFrame)
    let raf;
    raf = requestAnimationFrame(() => {
      try {
        localStorage.setItem(archiveStorageKey, JSON.stringify(archivedPrompts));
        setArchiveSavedAt(new Date().toLocaleString());
      } catch (err) {
        console.error('Auto-save archive failed', err);
      }
    });
    return () => {
      if (raf) cancelAnimationFrame(raf);
    };
  }, [archivedPrompts, archiveStorageKey]);

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
        onSave={handleSaveMaster}
        saving={masterSaving}
        savedAt={masterSavedAt}
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

      {/* Archive box (reference only) */}
      <ArchivePromptStorage
        archivedPrompts={archivedPrompts}
        activeArchiveChannel={activeArchiveChannel}
        setActiveArchiveChannel={setActiveArchiveChannel}
        onChange={(channel, value) => {
          setArchivedPrompts((prev) => ({ ...prev, [channel]: value }));
        }}
        onSave={handleSaveArchive}
        saving={archiveSaving}
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

      {/* Floating Test Chat Widget */}
      <TestChatWidget />
    </div>
  );
}
