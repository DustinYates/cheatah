import { useEffect } from 'react';
import { MessageSquare, Smartphone, Phone, Mail } from 'lucide-react';
import './MessageToast.css';

const CHANNEL_ICONS = {
  web: MessageSquare,
  sms: Smartphone,
  voice: Phone,
  email: Mail,
};

function timeAgo(dateStr) {
  const seconds = Math.floor((Date.now() - new Date(dateStr).getTime()) / 1000);
  if (seconds < 60) return 'just now';
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

export default function MessageToast({ notification, onDismiss, onClick }) {
  useEffect(() => {
    const timer = setTimeout(onDismiss, 6000);
    return () => clearTimeout(timer);
  }, [onDismiss]);

  const extra = notification.extra_data || {};
  const channel = extra.channel || 'web';
  const Icon = CHANNEL_ICONS[channel] || MessageSquare;

  return (
    <div className="message-toast" onClick={onClick} role="alert">
      <div className="message-toast__icon">
        <Icon size={16} />
      </div>
      <div className="message-toast__body">
        <div className="message-toast__sender">{notification.title}</div>
        <div className="message-toast__preview">{notification.message}</div>
        <div className="message-toast__time">{timeAgo(notification.created_at)}</div>
      </div>
      <button
        className="message-toast__close"
        onClick={(e) => { e.stopPropagation(); onDismiss(); }}
        aria-label="Dismiss"
      >
        &times;
      </button>
    </div>
  );
}
