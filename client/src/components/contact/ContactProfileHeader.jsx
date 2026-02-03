import { MapPin, Building2, Briefcase, Mail, Phone, Pencil, ShieldAlert } from 'lucide-react';
import { formatDateTimeParts } from '../../utils/dateFormat';
import './ContactProfileHeader.css';

/**
 * Generate a deterministic color from a string (name)
 */
function stringToColor(str) {
  if (!str) return '#6b7280';
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    hash = str.charCodeAt(i) + ((hash << 5) - hash);
  }
  const hue = hash % 360;
  return `hsl(${hue}, 65%, 45%)`;
}

/**
 * Get initials from a name
 */
function getInitials(name) {
  if (!name) return '?';
  const parts = name.trim().split(/\s+/);
  if (parts.length === 1) {
    return parts[0].charAt(0).toUpperCase();
  }
  return (parts[0].charAt(0) + parts[parts.length - 1].charAt(0)).toUpperCase();
}

/**
 * Avatar component with initials
 */
function Avatar({ name, size = 120 }) {
  const color = stringToColor(name);
  const initials = getInitials(name);

  return (
    <div
      className="profile-avatar"
      style={{
        width: size,
        height: size,
        backgroundColor: color,
        fontSize: size * 0.4,
      }}
    >
      {initials}
    </div>
  );
}

/**
 * GitHub-style contact profile header
 */
export default function ContactProfileHeader({
  contact,
  stats = {},
  dncStatus = {},
  onEdit,
  onToggleDnc,
  dncLoading = false,
}) {
  const { date: memberSince } = contact.created_at
    ? formatDateTimeParts(contact.created_at)
    : { date: 'Unknown' };

  // Calculate channels used from stats
  const channelsUsed = [];
  if (stats.sms > 0) channelsUsed.push('SMS');
  if (stats.call > 0) channelsUsed.push('Voice');
  if (stats.email > 0) channelsUsed.push('Email');
  if (stats.chat > 0) channelsUsed.push('Chat');

  return (
    <div className="contact-profile-header">
      <div className="profile-header-main">
        <Avatar name={contact.name} size={120} />

        <div className="profile-info">
          <div className="profile-name-row">
            <h1 className="profile-name">{contact.name || 'Unknown Contact'}</h1>
            {dncStatus.is_blocked && (
              <span className="dnc-badge" title="Do Not Contact">
                <ShieldAlert size={14} />
                DNC
              </span>
            )}
          </div>

          {/* Location, Company, Role - only show if data exists */}
          <div className="profile-details">
            {contact.location && (
              <span className="profile-detail">
                <MapPin size={14} />
                {contact.location}
              </span>
            )}
            {contact.company && (
              <span className="profile-detail">
                <Building2 size={14} />
                {contact.company}
              </span>
            )}
            {contact.role && (
              <span className="profile-detail">
                <Briefcase size={14} />
                {contact.role}
              </span>
            )}
          </div>

          {/* Contact info */}
          <div className="profile-contact-info">
            {contact.email && (
              <a href={`mailto:${contact.email}`} className="profile-contact-link">
                <Mail size={14} />
                {contact.email}
              </a>
            )}
            {contact.phone && (
              <a href={`tel:${contact.phone}`} className="profile-contact-link">
                <Phone size={14} />
                {contact.phone}
              </a>
            )}
          </div>
        </div>

        <div className="profile-actions">
          <button className="btn-edit-profile" onClick={onEdit}>
            <Pencil size={16} />
            Edit
          </button>
          {(contact.phone || contact.email) && (
            <button
              className={`btn-dnc-toggle ${dncStatus.is_blocked ? 'blocked' : ''}`}
              onClick={onToggleDnc}
              disabled={dncLoading}
            >
              {dncLoading
                ? 'Updating...'
                : dncStatus.is_blocked
                ? 'Remove from DNC'
                : 'Add to DNC'}
            </button>
          )}
        </div>
      </div>

      {/* Stats row */}
      <div className="profile-stats-row">
        <div className="profile-stat">
          <span className="stat-value">{stats.total || 0}</span>
          <span className="stat-label">Interactions</span>
        </div>
        <div className="profile-stat">
          <span className="stat-value">{channelsUsed.length > 0 ? channelsUsed.join(', ') : 'None'}</span>
          <span className="stat-label">Channels</span>
        </div>
        <div className="profile-stat">
          <span className="stat-value">{memberSince}</span>
          <span className="stat-label">Member since</span>
        </div>
        {contact.source && (
          <div className="profile-stat">
            <span className="stat-value">{contact.source.replace('_', ' ')}</span>
            <span className="stat-label">Source</span>
          </div>
        )}
      </div>
    </div>
  );
}
