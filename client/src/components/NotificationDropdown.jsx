import { useEffect, useRef } from 'react';
import { MessageSquare, Smartphone, Phone, Mail, AlertCircle } from 'lucide-react';
import './NotificationDropdown.css';

const CHANNEL_ICONS = {
  web: MessageSquare,
  sms: Smartphone,
  voice: Phone,
  email: Mail,
};

const TYPE_ICONS = {
  new_message: null, // uses channel icon
  escalation: AlertCircle,
  call_summary: Phone,
  lead_captured: MessageSquare,
  high_intent_lead: MessageSquare,
};

function timeAgo(dateStr) {
  const seconds = Math.floor((Date.now() - new Date(dateStr).getTime()) / 1000);
  if (seconds < 60) return 'just now';
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h`;
  return `${Math.floor(hours / 24)}d`;
}

function getIcon(notification) {
  if (notification.notification_type === 'new_message') {
    const channel = notification.extra_data?.channel || 'web';
    return CHANNEL_ICONS[channel] || MessageSquare;
  }
  return TYPE_ICONS[notification.notification_type] || AlertCircle;
}

export default function NotificationDropdown({
  notifications,
  unreadCount,
  onMarkRead,
  onMarkAllRead,
  onClose,
  onNavigate,
}) {
  const dropdownRef = useRef(null);

  // Close on click outside
  useEffect(() => {
    function handleClickOutside(e) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target)) {
        // Check if click is on the bell button itself (parent handles toggle)
        if (e.target.closest('.notification-bell')) return;
        onClose();
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [onClose]);

  const handleItemClick = (notification) => {
    if (!notification.is_read) {
      onMarkRead(notification.id);
    }
    if (notification.action_url) {
      onNavigate(notification.action_url);
    }
  };

  return (
    <div className="notification-dropdown" ref={dropdownRef}>
      <div className="notification-dropdown__header">
        <span className="notification-dropdown__title">Notifications</span>
        {unreadCount > 0 && (
          <button
            className="notification-dropdown__mark-all"
            onClick={onMarkAllRead}
          >
            Mark all read
          </button>
        )}
      </div>

      <div className="notification-dropdown__list">
        {notifications.length === 0 ? (
          <div className="notification-dropdown__empty">
            No notifications yet
          </div>
        ) : (
          notifications.map((n) => {
            const Icon = getIcon(n);
            return (
              <div
                key={n.id}
                className={`notification-dropdown__item ${!n.is_read ? 'notification-dropdown__item--unread' : ''}`}
                onClick={() => handleItemClick(n)}
              >
                <div className="notification-dropdown__item-icon">
                  <Icon size={14} />
                </div>
                <div className="notification-dropdown__item-body">
                  <div className="notification-dropdown__item-title">{n.title}</div>
                  <div className="notification-dropdown__item-message">{n.message}</div>
                </div>
                <div className="notification-dropdown__item-meta">
                  <span className="notification-dropdown__item-time">{timeAgo(n.created_at)}</span>
                  {!n.is_read && <span className="notification-dropdown__item-dot" />}
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
