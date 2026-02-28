import { useState, useEffect, useCallback, useRef } from 'react';
import { createPortal } from 'react-dom';
import { api } from '../api/client';
import { useAuth } from '../context/AuthContext';
import { LoadingState, EmptyState, ErrorState } from '../components/ui';
import { formatSmartDateTime } from '../utils/dateFormat';
import { formatPhone } from '../utils/formatPhone';
import LeadDetailsModal from '../components/LeadDetailsModal';
import SendSmsModal from '../components/SendSmsModal';
import SideDrawer from '../components/SideDrawer';
import './Dashboard.css';

// Robot icon SVG component
const RobotIcon = () => (
  <svg
    width="16"
    height="16"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    style={{ verticalAlign: 'middle' }}
  >
    {/* Antenna */}
    <line x1="12" y1="2" x2="12" y2="6" />
    <circle cx="12" cy="2" r="1" fill="currentColor" />
    {/* Head */}
    <rect x="4" y="6" width="16" height="12" rx="2" />
    {/* Eyes */}
    <circle cx="9" cy="11" r="1.5" fill="currentColor" />
    <circle cx="15" cy="11" r="1.5" fill="currentColor" />
    {/* Mouth */}
    <line x1="9" y1="15" x2="15" y2="15" />
    {/* Ears */}
    <rect x="1" y="9" width="2" height="5" rx="1" />
    <rect x="21" y="9" width="2" height="5" rx="1" />
  </svg>
);

// Envelope icon SVG component for email source
const EnvelopeIcon = () => (
  <svg
    width="16"
    height="16"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    style={{ verticalAlign: 'middle' }}
  >
    {/* Envelope body */}
    <rect x="2" y="4" width="20" height="16" rx="2" />
    {/* Envelope flap/seal lines */}
    <polyline points="2,4 12,13 22,4" />
  </svg>
);

// Chat icon SVG component
const ChatIcon = () => (
  <svg
    width="16"
    height="16"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    style={{ verticalAlign: 'middle' }}
  >
    <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z" />
  </svg>
);

// SMS Follow-up icon SVG component
const SmsFollowUpIcon = () => (
  <svg
    width="16"
    height="16"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    style={{ verticalAlign: 'middle' }}
  >
    {/* Phone with outgoing message */}
    <rect x="5" y="2" width="14" height="20" rx="2" />
    <line x1="12" y1="18" x2="12" y2="18.01" />
    {/* Arrow/send indicator */}
    <path d="M9 9l3-3 3 3" />
    <line x1="12" y1="6" x2="12" y2="12" />
  </svg>
);

// Text Bubble icon SVG component for SMS/Text source (iMessage style)
const TextBubbleIcon = () => (
  <svg
    width="16"
    height="16"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    style={{ verticalAlign: 'middle' }}
  >
    {/* Rectangular message bubble */}
    <rect x="3" y="4" width="18" height="13" rx="2" />
    {/* Tail/pointer at bottom */}
    <path d="M7 17 L7 21 L12 17" fill="none" />
    {/* Three dots indicating text */}
    <circle cx="8" cy="10.5" r="1" fill="currentColor" stroke="none" />
    <circle cx="12" cy="10.5" r="1" fill="currentColor" stroke="none" />
    <circle cx="16" cy="10.5" r="1" fill="currentColor" stroke="none" />
  </svg>
);

// Details icon SVG component (document with info)
const DetailsIcon = () => (
  <svg
    width="16"
    height="16"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    style={{ verticalAlign: 'middle' }}
  >
    {/* Document */}
    <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
    <polyline points="14,2 14,8 20,8" />
    {/* Info lines */}
    <line x1="8" y1="13" x2="16" y2="13" />
    <line x1="8" y1="17" x2="14" y2="17" />
  </svg>
);

// Notes icon SVG component (pencil on notepad)
const NotesIcon = () => (
  <svg
    width="16"
    height="16"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    style={{ verticalAlign: 'middle' }}
  >
    <path d="M12 20h9" />
    <path d="M16.5 3.5a2.121 2.121 0 113 3L7 19l-4 1 1-4L16.5 3.5z" />
  </svg>
);

// Service status icons for Master Admin Dashboard
const SmsServiceIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <rect x="5" y="2" width="14" height="20" rx="2" />
    <line x1="12" y1="18" x2="12" y2="18.01" />
  </svg>
);

const VoiceServiceIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M22 16.92v3a2 2 0 01-2.18 2 19.79 19.79 0 01-8.63-3.07 19.5 19.5 0 01-6-6 19.79 19.79 0 01-3.07-8.67A2 2 0 014.11 2h3a2 2 0 012 1.72c.127.96.361 1.903.7 2.81a2 2 0 01-.45 2.11L8.09 9.91a16 16 0 006 6l1.27-1.27a2 2 0 012.11-.45c.907.339 1.85.573 2.81.7A2 2 0 0122 16.92z" />
  </svg>
);

const EmailServiceIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <rect x="2" y="4" width="20" height="16" rx="2" />
    <polyline points="2,4 12,13 22,4" />
  </svg>
);

const WidgetServiceIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <rect x="3" y="3" width="18" height="18" rx="2" />
    <path d="M3 9h18" />
    <path d="M9 21V9" />
  </svg>
);

const CustomerServiceIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2" />
    <circle cx="9" cy="7" r="4" />
    <path d="M23 21v-2a4 4 0 00-3-3.87" />
    <path d="M16 3.13a4 4 0 010 7.75" />
  </svg>
);

const PromptServiceIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 2L2 7l10 5 10-5-10-5z" />
    <path d="M2 17l10 5 10-5" />
    <path d="M2 12l10 5 10-5" />
  </svg>
);

// Service badge component for showing service status
const ServiceBadge = ({ enabled, configured, icon, title }) => {
  const statusClass = enabled
    ? configured
      ? 'service--active'
      : 'service--partial'
    : 'service--inactive';
  const tooltip = enabled
    ? configured
      ? `${title}: Active`
      : `${title}: Enabled (not configured)`
    : `${title}: Disabled`;

  return (
    <span className={`service-badge ${statusClass}`} title={tooltip}>
      {icon}
    </span>
  );
};

// Services cell component for the tenant table
const ServicesCell = ({ services, onClick }) => {
  if (!services) return <span className="text-muted">-</span>;

  return (
    <div
      className={`services-badges ${onClick ? 'services-badges--clickable' : ''}`}
      onClick={onClick}
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
    >
      <ServiceBadge
        enabled={services.sms?.enabled}
        configured={services.sms?.configured}
        icon={<SmsServiceIcon />}
        title="SMS"
      />
      <ServiceBadge
        enabled={services.voice?.enabled}
        configured={services.voice?.configured}
        icon={<VoiceServiceIcon />}
        title="Voice"
      />
      <ServiceBadge
        enabled={services.email?.enabled}
        configured={services.email?.configured}
        icon={<EmailServiceIcon />}
        title="Email"
      />
      <ServiceBadge
        enabled={services.widget?.enabled}
        configured={services.widget?.configured}
        icon={<WidgetServiceIcon />}
        title="Widget"
      />
      <ServiceBadge
        enabled={services.customer_service?.enabled}
        configured={services.customer_service?.configured}
        icon={<CustomerServiceIcon />}
        title="Customer Service"
      />
      <ServiceBadge
        enabled={services.prompt?.enabled}
        configured={services.prompt?.configured}
        icon={<PromptServiceIcon />}
        title="AI Prompt"
      />
    </div>
  );
};

// Alerts badge component for tenant table
const AlertsBadge = ({ count, severity }) => {
  if (!count) return <span className="text-muted">-</span>;

  const severityClass = {
    critical: 'alerts-badge--critical',
    warning: 'alerts-badge--warning',
    info: 'alerts-badge--info',
  }[severity] || '';

  return (
    <span className={`alerts-badge ${severityClass}`} title={`${count} active alert(s)`}>
      {count} {count === 1 ? 'issue' : 'issues'}
    </span>
  );
};

const CompactTable = ({ containerClassName, tableClassName, children }) => (
  <div className={containerClassName}>
    <table className={tableClassName}>
      {children}
    </table>
  </div>
);

const IconButton = ({ className = '', title, ariaLabel, children, ...props }) => (
  <button
    type="button"
    className={`icon-button ${className}`.trim()}
    title={title}
    aria-label={ariaLabel || title}
    {...props}
  >
    {children}
  </button>
);

const StatusBadge = ({ status, label, variant = 'pill' }) => (
  <span
    className={`status-badge status-${status || 'new'} status-badge--${variant}`}
    title={label || status || 'New'}
    aria-label={label || status || 'New'}
  >
    {variant === 'dot' ? null : label || status || 'New'}
  </span>
);

export default function Dashboard() {
  const { user, selectedTenantId, selectTenant } = useAuth();
  const [leads, setLeads] = useState([]);
  const [calls, setCalls] = useState([]);
  const [tenantsOverview, setTenantsOverview] = useState(null);
  const [loading, setLoading] = useState(true);
  const [callsLoading, setCallsLoading] = useState(true);
  const [error, setError] = useState('');
  const [actionLoading, setActionLoading] = useState(null);
  const [selectedLead, setSelectedLead] = useState(null);
  const [smsModalLead, setSmsModalLead] = useState(null);
  const [openActionMenuId, setOpenActionMenuId] = useState(null);
  const [selectedLeadIds, setSelectedLeadIds] = useState(new Set());
  const [bulkDeleteLoading, setBulkDeleteLoading] = useState(false);
  const [calendarEvents, setCalendarEvents] = useState([]);
  const [calendarWeekStart, setCalendarWeekStart] = useState('');
  const [calendarWeekEnd, setCalendarWeekEnd] = useState('');
  const [calendarLoading, setCalendarLoading] = useState(false);
  const [notesPopoverId, setNotesPopoverId] = useState(null);
  const [notesText, setNotesText] = useState('');
  const [notesSaving, setNotesSaving] = useState(false);
  const [notesPos, setNotesPos] = useState({ top: 0, left: 0 });
  const notesRef = useRef(null);
  const [leadsLimit, setLeadsLimit] = useState(() => {
    const saved = localStorage.getItem('dashboard_leads_limit');
    return saved ? parseInt(saved, 10) : 50;
  });
  const [leadsSearch, setLeadsSearch] = useState('');
  const [sourceFilter, setSourceFilter] = useState('all');
  // Master admin state
  const [period, setPeriod] = useState(7);
  const [openTenantMenuId, setOpenTenantMenuId] = useState(null);
  const [tenantActionLoading, setTenantActionLoading] = useState(null);
  const [configDrawerOpen, setConfigDrawerOpen] = useState(false);
  const [configDrawerTenant, setConfigDrawerTenant] = useState(null);
  const [configData, setConfigData] = useState(null);
  const [configLoading, setConfigLoading] = useState(false);

  // Check if master admin with no tenant selected
  const isMasterAdminView = user?.is_global_admin && !selectedTenantId;

  useEffect(() => {
    if (isMasterAdminView) {
      fetchTenantsOverview();
    } else {
      fetchData();
    }
  }, [leadsLimit, isMasterAdminView, selectedTenantId, period]);

  const fetchTenantsOverview = async () => {
    setLoading(true);
    setError('');
    try {
      const data = await api.getTenantsOverview(period);
      setTenantsOverview(data);
    } catch (err) {
      console.error('Failed to fetch tenants overview:', err);
      setError('Failed to load tenants overview');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (openActionMenuId === null) return;

    const handleClick = (event) => {
      if (!event.target.closest('.action-menu')) {
        setOpenActionMenuId(null);
      }
    };

    document.addEventListener('click', handleClick);
    return () => document.removeEventListener('click', handleClick);
  }, [openActionMenuId]);

  // Click-outside handler for tenant action menu
  useEffect(() => {
    if (openTenantMenuId === null) return;

    const handleClick = (event) => {
      if (!event.target.closest('.tenant-action-menu')) {
        setOpenTenantMenuId(null);
      }
    };

    document.addEventListener('click', handleClick);
    return () => document.removeEventListener('click', handleClick);
  }, [openTenantMenuId]);

  // Tenant action handlers
  const handleImpersonate = (tenantId) => {
    selectTenant(tenantId);
    setOpenTenantMenuId(null);
  };

  const handleOpenTenantTab = (tenantId) => {
    window.open(`${window.location.origin}/?tenant=${tenantId}`, '_blank');
    setOpenTenantMenuId(null);
  };

  const handleToggleSuspend = async (tenant) => {
    setTenantActionLoading(tenant.id);
    try {
      await api.updateTenant(tenant.id, { is_active: !tenant.is_active });
      await fetchTenantsOverview();
    } catch (err) {
      console.error('Failed to update tenant status:', err);
    } finally {
      setTenantActionLoading(null);
      setOpenTenantMenuId(null);
    }
  };

  // Config drawer handler
  const handleServiceClick = async (e, tenantId, tenantName) => {
    e.stopPropagation();
    setConfigDrawerTenant({ id: tenantId, name: tenantName });
    setConfigDrawerOpen(true);
    setConfigLoading(true);
    try {
      const data = await api.getTenantConfig(tenantId);
      setConfigData(data);
    } catch (err) {
      console.error('Failed to load tenant config:', err);
      setConfigData(null);
    } finally {
      setConfigLoading(false);
    }
  };

  const fetchData = async () => {
    setLoading(true);
    setCallsLoading(true);
    setError('');
    try {
      const [leadsResult, callsResult, calendarResult] = await Promise.allSettled([
        api.getLeads({ limit: leadsLimit }),
        api.getCalls({ page: 1, page_size: 5 }),
        api.getCalendarEvents(0),
      ]);

      if (leadsResult.status === 'fulfilled') {
        const leadsData = leadsResult.value;
        // Sort by updated_at descending (most recent activity first)
        const sortedLeads = (leadsData.leads || leadsData || []).sort(
          (a, b) => new Date(b.updated_at || b.created_at) - new Date(a.updated_at || a.created_at)
        );
        setLeads(sortedLeads);
      } else {
        setLeads([]);
        throw leadsResult.reason;
      }

      if (callsResult.status === 'fulfilled') {
        const callsData = callsResult.value;
        setCalls(callsData.calls || []);
      } else {
        console.warn('Failed to load recent calls:', callsResult.reason);
        setCalls([]);
      }

      if (calendarResult.status === 'fulfilled') {
        const calData = calendarResult.value;
        setCalendarEvents(calData.events || []);
        setCalendarWeekStart(calData.week_start || '');
        setCalendarWeekEnd(calData.week_end || '');
      } else {
        setCalendarEvents([]);
      }
    } catch (err) {
      setError('Failed to load dashboard data');
    } finally {
      setLoading(false);
      setCallsLoading(false);
    }
  };

  const handleLimitChange = (newLimit) => {
    setLeadsLimit(newLimit);
    localStorage.setItem('dashboard_leads_limit', newLimit.toString());
  };

  const handleMarkUnknown = async (leadId) => {
    setActionLoading(leadId);
    try {
      await api.updateLeadStatus(leadId, 'unknown');
      // Update local state
      setLeads(leads.map(lead => 
        lead.id === leadId ? { ...lead, status: 'unknown' } : lead
      ));
    } catch (err) {
      setError('Failed to mark lead as unknown');
    } finally {
      setActionLoading(null);
    }
  };

  const handleDelete = async (leadId, leadName) => {
    if (!confirm(`Are you sure you want to delete "${leadName || 'this lead'}"? This action cannot be undone.`)) {
      return;
    }

    setActionLoading(leadId);
    try {
      await api.deleteLead(leadId);
      // Remove from local state using functional update to ensure we have latest state
      setLeads(prevLeads => prevLeads.filter(lead => lead.id !== leadId));
      setError(''); // Clear any previous errors
    } catch (err) {
      console.error('Delete error details:', {
        message: err.message,
        stack: err.stack,
        error: err
      });
      setError(`Failed to delete lead: ${err.message || 'Unknown error'}`);
    } finally {
      setActionLoading(null);
    }
  };

  const handleTriggerFollowUp = async (lead) => {
    if (!lead.phone) {
      setError('Cannot send follow-up: Lead has no phone number');
      return;
    }

    if (!confirm(`Send a follow-up SMS to ${lead.name || 'this lead'} at ${lead.phone}?`)) {
      return;
    }

    setActionLoading(`followup-${lead.id}`);
    try {
      const result = await api.triggerFollowUp(lead.id);
      if (result.success) {
        // Update local state to mark follow-up as scheduled
        setLeads(prevLeads => prevLeads.map(l =>
          l.id === lead.id
            ? { ...l, extra_data: { ...l.extra_data, followup_scheduled: true } }
            : l
        ));
        setError(''); // Clear any previous errors
      } else {
        setError(result.message || 'Failed to trigger follow-up');
      }
    } catch (err) {
      console.error('Follow-up error:', err);
      setError(`Failed to trigger follow-up: ${err.message || 'Unknown error'}`);
    } finally {
      setActionLoading(null);
    }
  };

  const handleStopDrip = async (lead) => {
    if (!confirm(`Stop drip campaign for ${lead.name || 'this lead'}?`)) {
      return;
    }

    setActionLoading(`drip-${lead.id}`);
    try {
      await api.optOutLeadFromDrip(lead.id);
      setLeads(prevLeads => prevLeads.map(l =>
        l.id === lead.id
          ? { ...l, extra_data: { ...l.extra_data, drip_enrolled: false } }
          : l
      ));
      setError('');
    } catch (err) {
      setError(`Failed to stop drip: ${err.message || 'Unknown error'}`);
    } finally {
      setActionLoading(null);
    }
  };

  // Check if a lead can receive SMS follow-up (has phone + not already sent)
  const needsFollowUp = (lead) => {
    return lead.phone &&
           !lead.extra_data?.followup_sent_at &&
           !lead.extra_data?.followup_scheduled;
  };

  const handleViewDetails = (lead) => {
    setSelectedLead(lead);
  };

  const handleOpenNotes = (lead, e) => {
    if (notesPopoverId === lead.id) {
      handleCloseNotes();
      return;
    }
    const rect = e.currentTarget.getBoundingClientRect();
    setNotesPos({ top: rect.bottom + 4, left: rect.right - 280 });
    setNotesPopoverId(lead.id);
    setNotesText(lead.notes || '');
  };

  const handleCloseNotes = () => {
    setNotesPopoverId(null);
    setNotesText('');
  };

  const handleSaveNotes = async (leadId) => {
    setNotesSaving(true);
    try {
      const updated = await api.updateLeadNotes(leadId, notesText || null);
      setLeads((prev) => prev.map((l) => (l.id === leadId ? { ...l, notes: updated.notes } : l)));
      handleCloseNotes();
    } catch (err) {
      console.error('Failed to save notes:', err);
    } finally {
      setNotesSaving(false);
    }
  };

  // Close notes popover on outside click
  useEffect(() => {
    if (!notesPopoverId) return;
    const handleClick = (e) => {
      if (notesRef.current && !notesRef.current.contains(e.target)) {
        handleCloseNotes();
      }
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [notesPopoverId]);

  const handleSelectLead = (leadId) => {
    setSelectedLeadIds((prev) => {
      const next = new Set(prev);
      if (next.has(leadId)) {
        next.delete(leadId);
      } else {
        next.add(leadId);
      }
      return next;
    });
  };

  const handleSelectAll = () => {
    if (selectedLeadIds.size === leads.length) {
      setSelectedLeadIds(new Set());
    } else {
      setSelectedLeadIds(new Set(leads.map((lead) => lead.id)));
    }
  };

  const handleBulkDelete = async () => {
    if (selectedLeadIds.size === 0) return;

    const count = selectedLeadIds.size;
    if (!confirm(`Are you sure you want to delete ${count} lead${count > 1 ? 's' : ''}? This action cannot be undone.`)) {
      return;
    }

    setBulkDeleteLoading(true);
    try {
      const deletePromises = Array.from(selectedLeadIds).map((id) =>
        api.deleteLead(id).catch((err) => ({ error: true, id, message: err.message }))
      );
      const results = await Promise.all(deletePromises);
      const failed = results.filter((r) => r?.error);

      if (failed.length > 0) {
        setError(`Failed to delete ${failed.length} lead(s)`);
      } else {
        setError('');
      }

      // Remove successfully deleted leads from state
      const failedIds = new Set(failed.map((f) => f.id));
      setLeads((prevLeads) =>
        prevLeads.filter((lead) => !selectedLeadIds.has(lead.id) || failedIds.has(lead.id))
      );
      setSelectedLeadIds(new Set());
    } catch (err) {
      setError(`Failed to delete leads: ${err.message}`);
    } finally {
      setBulkDeleteLoading(false);
    }
  };

  const closeModal = () => {
    setSelectedLead(null);
  };

  if (loading) {
    return <LoadingState message="Loading dashboard..." fullPage />;
  }

  if (error && !tenantsOverview && leads.length === 0) {
    return <ErrorState message={error} onRetry={isMasterAdminView ? fetchTenantsOverview : fetchData} />;
  }

  // Format relative time for last activity
  const formatLastActivity = (isoString) => {
    if (!isoString) return 'No activity';
    // Backend returns UTC timestamps without 'Z' suffix - add it if missing
    // Check if string already has timezone info (ends with Z or has +/-HH:MM pattern)
    const hasTimezone = /Z$|[+-]\d{2}:\d{2}$/.test(isoString);
    const utcString = hasTimezone ? isoString : isoString + 'Z';
    const date = new Date(utcString);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;
    return date.toLocaleDateString();
  };

  // Config drawer content component
  const TenantConfigDrawer = ({ config, loading }) => {
    if (loading) return <div className="config-loading">Loading...</div>;
    if (!config) return <div className="config-empty">No configuration data.</div>;

    const ConfigSection = ({ title, icon, data, fields }) => {
      if (!data) return (
        <div className="config-section config-section--empty">
          <div className="config-section-header">
            <span className="config-icon">{icon}</span>
            <h4>{title}</h4>
          </div>
          <p className="config-not-configured">Not configured</p>
        </div>
      );

      return (
        <div className="config-section">
          <div className="config-section-header">
            <span className="config-icon">{icon}</span>
            <h4>{title}</h4>
            <span className={`config-status ${data.enabled ? 'config-status--active' : 'config-status--inactive'}`}>
              {data.enabled ? 'Active' : 'Inactive'}
            </span>
          </div>
          <div className="config-fields">
            {fields.map(({ key, label }) => (
              <div key={key} className="config-field">
                <span className="config-field-label">{label}</span>
                <span className="config-field-value">
                  {typeof data[key] === 'boolean'
                    ? (data[key] ? 'Yes' : 'No')
                    : (data[key] || '-')}
                </span>
              </div>
            ))}
          </div>
        </div>
      );
    };

    return (
      <div className="tenant-config-drawer">
        <ConfigSection
          title="SMS"
          icon={<SmsServiceIcon />}
          data={config.sms}
          fields={[
            { key: 'phone', label: 'Phone Number' },
            { key: 'api_key_configured', label: 'API Key' },
            { key: 'messaging_profile_id', label: 'Messaging Profile' },
          ]}
        />
        <ConfigSection
          title="Voice"
          icon={<VoiceServiceIcon />}
          data={config.voice}
          fields={[
            { key: 'agent_id', label: 'Agent ID' },
            { key: 'handoff_mode', label: 'Handoff Mode' },
            { key: 'transfer_number', label: 'Transfer Number' },
          ]}
        />
        <ConfigSection
          title="Email"
          icon={<EmailServiceIcon />}
          data={config.email}
          fields={[
            { key: 'gmail_email', label: 'Gmail' },
            { key: 'gmail_connected', label: 'Connected' },
            { key: 'watch_active', label: 'Watch Active' },
            { key: 'sendgrid_configured', label: 'SendGrid' },
          ]}
        />
        <ConfigSection
          title="Widget"
          icon={<WidgetServiceIcon />}
          data={config.widget}
          fields={[
            { key: 'settings_count', label: 'Settings Count' },
          ]}
        />
        <ConfigSection
          title="Customer Service"
          icon={<CustomerServiceIcon />}
          data={config.customer_service}
          fields={[
            { key: 'zapier_configured', label: 'Zapier' },
            { key: 'jackrabbit_key1_configured', label: 'Jackrabbit Key 1' },
            { key: 'jackrabbit_key2_configured', label: 'Jackrabbit Key 2' },
          ]}
        />
        <ConfigSection
          title="AI Prompt"
          icon={<PromptServiceIcon />}
          data={config.prompt}
          fields={[
            { key: 'active', label: 'Active' },
            { key: 'validated_at', label: 'Last Validated' },
          ]}
        />
      </div>
    );
  };

  // Master Admin Tenant Overview
  if (isMasterAdminView && tenantsOverview) {
    return (
      <div className="dashboard">
        <div className="dashboard-header">
          <div className="dashboard-header__title">
            <h1>Master Admin Dashboard</h1>
            <span className="dashboard-header__subtitle">All tenants overview</span>
          </div>
          <div className="period-toggle">
            {[1, 7, 30].map((d) => (
              <button
                key={d}
                className={`period-pill ${period === d ? 'period-pill--active' : ''}`}
                onClick={() => setPeriod(d)}
              >
                {d === 1 ? '24h' : `${d}d`}
              </button>
            ))}
          </div>
        </div>

        {/* Summary Stats */}
        <div className="tenant-overview-summary">
          <div className="summary-stat">
            <span className="summary-stat__value">{tenantsOverview.total_tenants}</span>
            <span className="summary-stat__label">Total Tenants</span>
          </div>
          <div className="summary-stat">
            <span className="summary-stat__value summary-stat__value--success">{tenantsOverview.active_tenants}</span>
            <span className="summary-stat__label">Active</span>
          </div>
          <div className="summary-stat">
            <span className="summary-stat__value summary-stat__value--muted">{tenantsOverview.total_tenants - tenantsOverview.active_tenants}</span>
            <span className="summary-stat__label">Inactive</span>
          </div>
        </div>

        {/* Tenants Table */}
        <div className="card">
          <div className="card-header">
            <h2>Tenants</h2>
          </div>
          <CompactTable containerClassName="leads-table-container" tableClassName="leads-table master-admin-table">
            <thead>
              <tr>
                <th>#</th>
                <th>Name</th>
                <th>Status</th>
                <th>Services</th>
                <th>Alerts</th>
                <th>Email</th>
                <th>Phones</th>
                <th>In</th>
                <th>Out</th>
                <th>Calls</th>
                <th>Mins</th>
                <th>Bot Leads</th>
                <th>Leads</th>
                <th>Activity</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {[...tenantsOverview.tenants].sort((a, b) => a.id - b.id).map((tenant) => (
                <tr
                  key={tenant.id}
                  className="lead-row"
                >
                  <td>{tenant.tenant_number || tenant.id}</td>
                  <td>
                    <div className="lead-person">
                      <span className="lead-person__name">{tenant.name}</span>
                      <span className="lead-person__email">{tenant.subdomain}</span>
                    </div>
                  </td>
                  <td>
                    <span className={`status-badge status-${tenant.is_active ? 'verified' : 'unknown'}`}>
                      {tenant.is_active ? 'Active' : 'Inactive'}
                    </span>
                  </td>
                  <td>
                    <ServicesCell
                      services={tenant.services}
                      onClick={(e) => handleServiceClick(e, tenant.id, tenant.name)}
                    />
                  </td>
                  <td>
                    <AlertsBadge count={tenant.active_alerts_count} severity={tenant.alert_severity} />
                  </td>
                  <td>
                    {tenant.gmail_email ? (
                      <span className="tenant-email" title={tenant.gmail_email}>
                        {tenant.gmail_email}
                      </span>
                    ) : (
                      <span className="text-muted">-</span>
                    )}
                  </td>
                  <td>
                    {tenant.telnyx_phone_numbers?.length > 0 ? (
                      <div className="phone-numbers">
                        {tenant.telnyx_phone_numbers.map((phone, idx) => (
                          <span key={idx} className="phone-number">{phone}</span>
                        ))}
                      </div>
                    ) : (
                      <span className="text-muted">-</span>
                    )}
                  </td>
                  <td>{tenant.sms_incoming_count || 0}</td>
                  <td>{tenant.sms_outgoing_count || 0}</td>
                  <td>{tenant.call_count || 0}</td>
                  <td>{tenant.call_minutes || 0}</td>
                  <td>{tenant.chatbot_leads_count || 0}</td>
                  <td>{tenant.total_leads}</td>
                  <td>{formatLastActivity(tenant.last_activity)}</td>
                  <td onClick={(e) => e.stopPropagation()}>
                    <div className="tenant-action-menu">
                      <button
                        className="icon-button icon-button--ghost"
                        onClick={() => setOpenTenantMenuId(openTenantMenuId === tenant.id ? null : tenant.id)}
                        disabled={tenantActionLoading === tenant.id}
                      >
                        &#8942;
                      </button>
                      {openTenantMenuId === tenant.id && (
                        <div className="action-menu__popover" role="menu">
                          <button
                            className="action-menu__item"
                            onClick={() => handleImpersonate(tenant.id)}
                          >
                            Switch to Tenant
                          </button>
                          <button
                            className="action-menu__item"
                            onClick={() => handleOpenTenantTab(tenant.id)}
                          >
                            Open in New Tab
                          </button>
                          <button
                            className={`action-menu__item ${tenant.is_active ? 'action-menu__item--danger' : ''}`}
                            onClick={() => handleToggleSuspend(tenant)}
                            disabled={tenantActionLoading === tenant.id}
                          >
                            {tenant.is_active ? 'Suspend Tenant' : 'Activate Tenant'}
                          </button>
                        </div>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </CompactTable>
        </div>

        {/* Config Drawer */}
        <SideDrawer
          title={configDrawerTenant ? `${configDrawerTenant.name} - Configuration` : 'Configuration'}
          open={configDrawerOpen}
          onClose={() => setConfigDrawerOpen(false)}
        >
          <TenantConfigDrawer config={configData} loading={configLoading} />
        </SideDrawer>
      </div>
    );
  }

  const getRowClassName = (lead) => {
    if (lead.status === 'verified' || lead.status === 'unknown') {
      return 'lead-row processed';
    }
    return 'lead-row';
  };

  const getSourceFlow = (lead) => {
    // Returns { inbound: [...], outbound: [...] } to show flow: inbound → outbound
    const inbound = [];
    const outbound = [];
    const seenInbound = new Set();
    const seenOutbound = new Set();

    // Helper to get icon for a source type
    const getIcon = (sourceType) => {
      switch (sourceType) {
        case 'email':
          return { icon: <EnvelopeIcon />, title: 'Email', shortLabel: 'Email', key: 'email' };
        case 'chatbot':
        case 'web_chat':
        case 'web_chat_lead':
          return { icon: <RobotIcon />, title: 'Chatbot', shortLabel: 'Chat', key: 'chatbot' };
        case 'voice_call':
        case 'phone':
        case 'call':
          return { icon: '📞', title: 'Phone Call', shortLabel: 'Call', key: 'call' };
        case 'sms':
        case 'text':
        case 'sms_ai_assistant':
        case 'sms_ai':
          return { icon: <TextBubbleIcon />, title: 'Text Message', shortLabel: 'SMS', key: 'sms' };
        default:
          return null;
      }
    };

    // Add inbound source
    const addInbound = (sourceType) => {
      const iconData = getIcon(sourceType);
      if (iconData && !seenInbound.has(iconData.key)) {
        inbound.push(iconData);
        seenInbound.add(iconData.key);
      }
    };

    // Check primary source (inbound)
    const source = lead.extra_data?.source;
    if (source) {
      addInbound(source);
    }

    // Check for voice calls (inbound)
    if (lead.extra_data?.voice_calls?.length > 0 && !seenInbound.has('call')) {
      inbound.push({ icon: '📞', title: 'Phone Call', shortLabel: 'Call', key: 'call' });
      seenInbound.add('call');
    }

    // Check conversation channel (inbound) - shows how the lead is currently engaged
    if (lead.conv_channel) {
      addInbound(lead.conv_channel);
    }

    // Check sources array (inbound - for merged leads)
    if (lead.extra_data?.sources) {
      for (const s of lead.extra_data.sources) {
        addInbound(s);
      }
    }

    // Default inbound to chatbot if none found
    if (inbound.length === 0) {
      inbound.push({ icon: <RobotIcon />, title: 'Chatbot', shortLabel: 'Chat', key: 'chatbot' });
    }

    // Check for AI SMS follow-up (outbound)
    if (lead.extra_data?.followup_sent_at && !seenOutbound.has('sms_followup')) {
      outbound.push({ icon: <SmsFollowUpIcon />, title: 'AI SMS Follow-up Sent', shortLabel: 'Follow-up', key: 'sms_followup' });
      seenOutbound.add('sms_followup');
    }

    return { inbound, outbound };
  };

  // Keep backward-compatible functions
  const getSourceIcons = (lead) => {
    const flow = getSourceFlow(lead);
    return [...flow.inbound, ...flow.outbound];
  };

  const getSourceIcon = (lead) => {
    const flow = getSourceFlow(lead);
    return flow.inbound[0];
  };

  const getFollowUpIndicator = (lead) => {
    // Green: Agent handled successfully - llm_responded AND (verified OR followup sent)
    if (lead.llm_responded === true) {
      if (lead.status === 'verified' || lead.extra_data?.followup_sent_at) {
        return { className: 'handled', title: 'Handled - No follow-up needed' };
      }
      // LLM responded but still pending review
      return { className: 'pending', title: 'Pending review' };
    }

    // Red: Agent didn't respond - needs human follow-up
    if (lead.llm_responded === false) {
      return { className: 'needs-followup', title: 'Needs human follow-up' };
    }

    // Yellow: Unknown/new status with no conversation data
    if (lead.status === 'unknown') {
      return { className: 'pending', title: 'Status unknown' };
    }

    // Voice call leads handled by AI agent
    if (lead.extra_data?.voice_calls?.length > 0) {
      const hasTranscript = lead.extra_data.voice_calls.some(vc => vc.transcript);
      if (hasTranscript) {
        return { className: 'handled', title: 'Voice call - AI handled' };
      }
      return { className: 'pending', title: 'Voice call - brief/no transcript' };
    }

    // Gray fallback: No conversation data
    return { className: 'no-data', title: 'No conversation data' };
  };

  const hasFrustrationSignal = (lead) => {
    const voiceCalls = lead.extra_data?.voice_calls;
    if (!Array.isArray(voiceCalls)) {
      return false;
    }

    return voiceCalls.some((call) => {
      const summary = `${call?.summary || call?.summary_text || ''}`;
      return /frustrat/i.test(summary);
    });
  };

  const hasFollowUpRequest = (lead) => {
    if (lead.extra_data?.followup_requested === true || lead.extra_data?.followup_request === true) {
      return true;
    }

    return needsFollowUp(lead);
  };

  const formatDuration = (seconds) => {
    if (!seconds) return '-';
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  const formatLeadDate = (dateString) => {
    const formatted = formatSmartDateTime(dateString);
    return formatted.replace(/\s[A-Z]{2,4}$/, '');
  };

  // Format name - handle invalid names, null, common acknowledgements, phone numbers as names
  const formatName = (name) => {
    if (!name) return 'Unknown';
    const trimmed = name.trim();
    const lower = trimmed.toLowerCase();

    // Detect "Caller +1832..." pattern (phone number masquerading as name)
    if (/^caller\s/i.test(trimmed)) return 'Unknown';

    // Detect raw phone numbers as names (+18327920114, 8327920114, etc.)
    if (/^\+?\d{7,}$/.test(trimmed)) return 'Unknown';

    // Common invalid name values
    const invalidNames = [
      'none', 'unknown', 'n/a', 'not provided', 'null', 'undefined',
      // Common acknowledgements that shouldn't be names
      'yes', 'yep', 'yeah', 'ok', 'okay', 'sure', 'good', 'great', 'fine',
      'thanks', 'thank you', 'no', 'nope', 'nah', 'hello', 'hi', 'hey',
      'can', 'will', 'maybe', 'test', 'testing', 'demo'
    ];

    if (invalidNames.includes(lower)) {
      return 'Unknown';
    }

    // Reject single character or very short names (except known short names)
    if (trimmed.length < 2) {
      return 'Unknown';
    }

    return trimmed;
  };

  const filteredLeads = leads.filter((lead) => {
    if (leadsSearch) {
      const q = leadsSearch.toLowerCase();
      const match =
        (lead.name || '').toLowerCase().includes(q) ||
        (lead.phone || '').includes(q) ||
        (lead.email || '').toLowerCase().includes(q);
      if (!match) return false;
    }
    if (sourceFilter !== 'all') {
      const flow = getSourceFlow(lead);
      const sources = flow.inbound.map((s) => s.key);
      if (!sources.includes(sourceFilter)) return false;
    }
    return true;
  });

  return (
    <div className="dashboard">
      <div className="dashboard-header">
        <div className="dashboard-header__title">
          <h1>Dashboard</h1>
          <span className="dashboard-header__subtitle">Recent activity</span>
        </div>
      </div>

      {/* Calendar Week View */}
      {calendarWeekStart && (
        <div className="card calendar-week-card">
          <div className="card-header">
            <h2>This Week</h2>
            <span className="calendar-week-range">
              {new Date(calendarWeekStart + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
              {' – '}
              {new Date(calendarWeekEnd + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
            </span>
          </div>
          {calendarLoading ? (
            <div className="calendar-empty">Loading...</div>
          ) : (
            <div className="calendar-week-grid">
              {(() => {
                // Build day columns Mon-Sun
                const days = [];
                const start = new Date(calendarWeekStart + 'T00:00:00');
                for (let i = 0; i < 7; i++) {
                  const day = new Date(start);
                  day.setDate(start.getDate() + i);
                  days.push(day);
                }
                const today = new Date();
                today.setHours(0, 0, 0, 0);

                return days.map((day) => {
                  const dayStr = day.toISOString().split('T')[0];
                  const isToday = day.getTime() === today.getTime();
                  const dayEvents = calendarEvents.filter((evt) => {
                    const evtDate = (evt.start || '').split('T')[0];
                    return evtDate === dayStr;
                  });

                  return (
                    <div key={dayStr} className={`calendar-day-col ${isToday ? 'calendar-day-col--today' : ''}`}>
                      <div className="calendar-day-header">
                        <span className="calendar-day-name">
                          {day.toLocaleDateString('en-US', { weekday: 'short' })}
                        </span>
                        <span className={`calendar-day-num ${isToday ? 'calendar-day-num--today' : ''}`}>
                          {day.getDate()}
                        </span>
                      </div>
                      <div className="calendar-day-events">
                        {dayEvents.length === 0 ? (
                          <span className="calendar-no-events">No events</span>
                        ) : (
                          dayEvents.map((evt) => {
                            const startTime = evt.all_day
                              ? 'All day'
                              : new Date(evt.start).toLocaleTimeString('en-US', {
                                  hour: 'numeric',
                                  minute: '2-digit',
                                  hour12: true,
                                });
                            return (
                              <div
                                key={evt.id}
                                className="calendar-event"
                                title={`${evt.summary}\n${startTime}`}
                              >
                                <span className="calendar-event-time">{startTime}</span>
                                <span className="calendar-event-title">{evt.summary}</span>
                              </div>
                            );
                          })
                        )}
                      </div>
                    </div>
                  );
                });
              })()}
            </div>
          )}
        </div>
      )}

      <div className="dashboard-grid">
        <div className="card leads-card leads-card-wide">
          <div className="card-header">
            <h2>Recent Leads</h2>
            <div className="card-header__actions">
              <input
                type="text"
                className="leads-search-input"
                placeholder="Search name, phone, email..."
                value={leadsSearch}
                onChange={(e) => setLeadsSearch(e.target.value)}
              />
              <select
                className="leads-source-filter"
                value={sourceFilter}
                onChange={(e) => setSourceFilter(e.target.value)}
              >
                <option value="all">All Sources</option>
                <option value="chatbot">Chat</option>
                <option value="call">Phone</option>
                <option value="sms">SMS</option>
                <option value="email">Email</option>
              </select>
              <div className="leads-limit-selector">
                <span className="leads-limit-label">Show:</span>
                <select
                  className="leads-limit-select"
                  value={leadsLimit}
                  onChange={(e) => handleLimitChange(parseInt(e.target.value, 10))}
                >
                  <option value={10}>10</option>
                  <option value={50}>50</option>
                  <option value={100}>100</option>
                </select>
              </div>
              {selectedLeadIds.size > 0 && (
                <button
                  className="btn btn--danger btn--sm"
                  onClick={handleBulkDelete}
                  disabled={bulkDeleteLoading}
                >
                  {bulkDeleteLoading ? 'Deleting...' : 'DELETE ALL'}
                </button>
              )}
              {(leadsSearch || sourceFilter !== 'all') && (
                <span className="leads-filter-count">{filteredLeads.length} of {leads.length}</span>
              )}
              <a className="card-link" href="/connections">View all</a>
            </div>
          </div>
          {error && <div className="error">{error}</div>}

          {leads.length === 0 ? (
            <EmptyState
              icon="📋"
              title="No leads yet"
              description="Start conversations to generate leads."
            />
          ) : (
            <CompactTable containerClassName="leads-table-container" tableClassName="leads-table">
              <thead>
                <tr>
                  <th className="col-select">
                    <input
                      type="checkbox"
                      checked={filteredLeads.length > 0 && selectedLeadIds.size === filteredLeads.length}
                      onChange={handleSelectAll}
                      title="Select all"
                      aria-label="Select all leads"
                    />
                  </th>
                  <th className="col-person">Lead</th>
                  <th className="col-phone">Phone</th>
                  <th className="col-source">Source</th>
                  <th className="col-date">Date</th>
                  <th className="col-details">Details</th>
                  <th className="col-actions">Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredLeads.map((lead) => (
                  <tr key={lead.id} className={getRowClassName(lead)}>
                    <td className="col-select">
                      <input
                        type="checkbox"
                        checked={selectedLeadIds.has(lead.id)}
                        onChange={() => handleSelectLead(lead.id)}
                        aria-label={`Select ${lead.name || 'lead'}`}
                      />
                    </td>
                    <td className="col-person">
                      <div className="lead-person">
                        <span className="lead-person__name">{formatName(lead.name)}</span>
                        <span className="lead-person__email">{lead.email || '—'}</span>
                      </div>
                    </td>
                    <td className="col-phone">
                      <span className="lead-phone">{formatPhone(lead.phone)}</span>
                    </td>
                    <td className="col-source">
                      <div className="source-badges">
                        {(() => {
                          const flow = getSourceFlow(lead);
                          return (
                            <>
                              {/* Inbound channel(s) */}
                              {flow.inbound.map((src) => (
                                <span key={src.key} className="source-badge" title={src.title}>
                                  <span className="source-icon">{src.icon}</span>
                                  <span className="source-label">{src.shortLabel}</span>
                                </span>
                              ))}
                              {/* Arrow if there's outbound */}
                              {flow.outbound.length > 0 && (
                                <span className="source-arrow" title="AI responded via">→</span>
                              )}
                              {/* Outbound channel(s) */}
                              {flow.outbound.map((src) => (
                                <span key={src.key} className="source-badge" title={src.title}>
                                  <span className="source-icon">{src.icon}</span>
                                  <span className="source-label">{src.shortLabel}</span>
                                </span>
                              ))}
                            </>
                          );
                        })()}
                        <span
                          className={`followup-indicator ${getFollowUpIndicator(lead).className}`}
                          title={getFollowUpIndicator(lead).title}
                        />
                        {hasFrustrationSignal(lead) && (
                          <span
                            className="followup-alert"
                            title="Call ended with frustration"
                            aria-label="Call ended with frustration"
                          >
                            !
                          </span>
                        )}
                        {hasFollowUpRequest(lead) && (
                          <span
                            className="followup-arrow"
                            title="Follow-up requested"
                            aria-label="Follow-up requested"
                          />
                        )}
                        {lead.extra_data?.drip_enrolled && (
                          <span className="drip-badge" title="Drip campaign active">
                            Drip
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="col-date">
                      <span className="lead-date">{formatLeadDate(lead.updated_at || lead.created_at)}</span>
                    </td>
                    <td className="col-details">
                      <div className="details-cell">
                        <IconButton
                          className="icon-button--ghost"
                          onClick={() => handleViewDetails(lead)}
                          title="View details"
                          ariaLabel="View lead details"
                        >
                          <DetailsIcon />
                        </IconButton>
                        <IconButton
                          className={`icon-button--ghost${lead.notes ? ' icon-button--has-notes' : ''}`}
                          onClick={(e) => handleOpenNotes(lead, e)}
                          title={lead.notes ? 'Edit notes' : 'Add notes'}
                          ariaLabel={lead.notes ? 'Edit notes' : 'Add notes'}
                        >
                          <NotesIcon />
                        </IconButton>
                      </div>
                      {notesPopoverId === lead.id && createPortal(
                        <div
                          className="notes-popover"
                          ref={notesRef}
                          style={{ top: notesPos.top, left: notesPos.left }}
                        >
                          <textarea
                            className="notes-textarea"
                            value={notesText}
                            onChange={(e) => setNotesText(e.target.value)}
                            placeholder="Add notes..."
                            rows={4}
                            autoFocus
                          />
                          <div className="notes-popover-actions">
                            <button
                              className="notes-btn notes-btn--cancel"
                              onClick={handleCloseNotes}
                              type="button"
                            >
                              Cancel
                            </button>
                            <button
                              className="notes-btn notes-btn--save"
                              onClick={() => handleSaveNotes(lead.id)}
                              disabled={notesSaving}
                              type="button"
                            >
                              {notesSaving ? 'Saving...' : 'Save'}
                            </button>
                          </div>
                        </div>,
                        document.body
                      )}
                    </td>
                    <td className="actions-cell col-actions">
                      <div className="actions-container">
                        {lead.extra_data?.drip_enrolled && (
                          <IconButton
                            className="icon-button--soft icon-button--warning"
                            onClick={() => handleStopDrip(lead)}
                            disabled={actionLoading === `drip-${lead.id}`}
                            title="Stop drip campaign"
                            ariaLabel="Stop drip campaign"
                          >
                            {actionLoading === `drip-${lead.id}` ? (
                              <span className="spinner">⋯</span>
                            ) : (
                              <svg className="icon" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8 7a1 1 0 00-1 1v4a1 1 0 001 1h4a1 1 0 001-1V8a1 1 0 00-1-1H8z" clipRule="evenodd" />
                              </svg>
                            )}
                          </IconButton>
                        )}
                        {needsFollowUp(lead) && (
                          <IconButton
                            className="icon-button--soft icon-button--info"
                            onClick={() => handleTriggerFollowUp(lead)}
                            disabled={actionLoading === `followup-${lead.id}`}
                            title="Send follow-up SMS"
                            ariaLabel="Send follow-up SMS"
                          >
                            {actionLoading === `followup-${lead.id}` ? (
                              <span className="spinner">⋯</span>
                            ) : (
                              <SmsFollowUpIcon />
                            )}
                          </IconButton>
                        )}
                        {lead.phone && (
                          <IconButton
                            className="icon-button--soft icon-button--info"
                            onClick={() => setSmsModalLead(lead)}
                            title="Send text message"
                            ariaLabel="Send text message"
                          >
                            <svg className="icon" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                              <path d="M3.505 2.365A41.369 41.369 0 019 2c1.863 0 3.697.124 5.495.365 1.247.167 2.18 1.108 2.435 2.268a4.45 4.45 0 00-.577-.025h-.002c-1.97 0-3.643.467-4.878 1.488C10.218 7.12 9.6 8.55 9.6 10.2c0 1.65.617 3.08 1.873 4.104.822.67 1.856 1.083 3.027 1.292l-2.073 2.073a.75.75 0 01-1.06 0L9 15.302l-3.088 3.088a.75.75 0 01-1.28-.53v-4.918a5.4 5.4 0 01-1.564-1.674C2.39 10.114 2 8.762 2 7.25c0-1.86.574-3.3 1.505-4.885zM16.351 6.1c-1.01 0-2.04.302-2.791.978C12.794 7.768 12.35 8.8 12.35 10.2s.444 2.432 1.21 3.122c.75.676 1.78.978 2.791.978.337 0 .663-.03.976-.088l.63.63a.5.5 0 00.854-.354v-1.462c.6-.773.939-1.735.939-2.826 0-1.4-.444-2.432-1.21-3.122-.75-.676-1.78-.978-2.79-.978z" />
                            </svg>
                          </IconButton>
                        )}
                        {(!lead.status || lead.status === 'new') && (
                          <IconButton
                            className="icon-button--soft icon-button--warning"
                            onClick={() => handleMarkUnknown(lead.id)}
                            disabled={actionLoading === lead.id}
                            title="Mark as unknown/spam"
                            ariaLabel="Mark as unknown"
                          >
                            {actionLoading === lead.id ? (
                              <span className="spinner">⋯</span>
                            ) : (
                              <svg className="icon" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                                <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-8-5a.75.75 0 01.75.75v4.5a.75.75 0 01-1.5 0v-4.5A.75.75 0 0110 5zm0 10a1 1 0 100-2 1 1 0 000 2z" clipRule="evenodd" />
                              </svg>
                            )}
                          </IconButton>
                        )}
                        <IconButton
                          className="icon-button--soft icon-button--danger"
                          onClick={() => handleDelete(lead.id, lead.name)}
                          disabled={actionLoading === lead.id}
                          title="Delete lead"
                          ariaLabel="Delete lead"
                        >
                          {actionLoading === lead.id ? (
                            <span className="spinner">⋯</span>
                          ) : (
                            <svg className="icon" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                              <path d="M7.5 2.5a.75.75 0 00-.75.75V4H4a.75.75 0 000 1.5h.643l.91 10.01A2.25 2.25 0 007.796 17.5h4.408a2.25 2.25 0 002.243-1.99l.91-10.01H16a.75.75 0 000-1.5h-2.75v-.75a.75.75 0 00-.75-.75h-5zM8.25 4V3.25h3.5V4h-3.5zM8 8.25c.414 0 .75.336.75.75v5a.75.75 0 01-1.5 0v-5c0-.414.336-.75.75-.75zm4 0c.414 0 .75.336.75.75v5a.75.75 0 01-1.5 0v-5c0-.414.336-.75.75-.75z" />
                            </svg>
                          )}
                        </IconButton>
                        <div className="action-menu">
                          <IconButton
                            className="icon-button--ghost"
                            onClick={(event) => {
                              event.stopPropagation();
                              setOpenActionMenuId(openActionMenuId === lead.id ? null : lead.id);
                            }}
                            title="More actions"
                            ariaLabel="More actions"
                          >
                            ⋮
                          </IconButton>
                          {openActionMenuId === lead.id && (
                            <div className="action-menu__popover" role="menu">
                              {lead.extra_data?.drip_enrolled && (
                                <button
                                  type="button"
                                  className="action-menu__item"
                                  onClick={() => {
                                    setOpenActionMenuId(null);
                                    handleStopDrip(lead);
                                  }}
                                  disabled={actionLoading === `drip-${lead.id}`}
                                  role="menuitem"
                                >
                                  Stop drip campaign
                                </button>
                              )}
                              <button
                                type="button"
                                className="action-menu__item action-menu__item--danger"
                                onClick={() => {
                                  setOpenActionMenuId(null);
                                  handleDelete(lead.id, lead.name);
                                }}
                                disabled={actionLoading === lead.id}
                                role="menuitem"
                              >
                                Delete lead
                              </button>
                            </div>
                          )}
                        </div>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </CompactTable>
          )}
        </div>

      </div>

      {/* Lead Details Modal */}
      {selectedLead && (
        <LeadDetailsModal
          lead={selectedLead}
          onClose={closeModal}
        />
      )}

      {/* Send SMS Modal */}
      {smsModalLead && (
        <SendSmsModal
          lead={smsModalLead}
          onClose={() => setSmsModalLead(null)}
          onSuccess={() => setSmsModalLead(null)}
        />
      )}
    </div>
  );
}
