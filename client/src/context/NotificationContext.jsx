import { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react';
import { api } from '../api/client';
import { useAuth } from './AuthContext';

const NotificationContext = createContext(null);

const POLL_INTERVAL = 15000; // 15 seconds

export function NotificationProvider({ children }) {
  const { user, effectiveTenantId } = useAuth();
  const [notifications, setNotifications] = useState([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [toasts, setToasts] = useState([]);
  const [dropdownOpen, setDropdownOpen] = useState(false);

  // Track the newest notification we've seen to detect truly new ones
  const lastSeenRef = useRef(null);
  // Track notification IDs we've already toasted to avoid duplicates
  const toastedIdsRef = useRef(new Set());

  const shouldPoll = user && effectiveTenantId;

  const poll = useCallback(async () => {
    if (!shouldPoll) return;

    try {
      const params = { limit: '20', include_read: 'true' };
      if (lastSeenRef.current) {
        params.since = lastSeenRef.current;
      }

      const data = await api.getNotifications(params);
      const incoming = data.notifications || [];
      setUnreadCount(data.unread_count);

      if (incoming.length > 0) {
        // Find truly new notifications (not yet toasted)
        const newOnes = incoming.filter(n => !toastedIdsRef.current.has(n.id));

        // Only show toasts if we've done at least one poll (avoid toasting on first load)
        if (lastSeenRef.current && newOnes.length > 0) {
          setToasts(prev => [...prev, ...newOnes]);
          newOnes.forEach(n => toastedIdsRef.current.add(n.id));
        } else {
          // First load — just record the IDs so we don't toast them later
          incoming.forEach(n => toastedIdsRef.current.add(n.id));
        }

        // Update lastSeen to newest notification timestamp
        const newest = incoming[0]?.created_at;
        if (newest) {
          lastSeenRef.current = newest;
        }
      }

      // Merge into full notification list (replace — the API returns most recent)
      if (incoming.length > 0 || !lastSeenRef.current) {
        // Re-fetch full list for dropdown (without since filter)
        const fullData = await api.getNotifications({ limit: '20', include_read: 'true' });
        setNotifications(fullData.notifications || []);
        setUnreadCount(fullData.unread_count);
      }
    } catch (err) {
      // Silently ignore polling errors — will retry next interval
      console.debug('Notification poll failed:', err.message);
    }
  }, [shouldPoll]);

  // Start/stop polling
  useEffect(() => {
    if (!shouldPoll) {
      setNotifications([]);
      setUnreadCount(0);
      setToasts([]);
      lastSeenRef.current = null;
      toastedIdsRef.current.clear();
      return;
    }

    // Initial poll
    poll();

    const interval = setInterval(poll, POLL_INTERVAL);
    return () => clearInterval(interval);
  }, [shouldPoll, poll]);

  const dismissToast = useCallback((id) => {
    setToasts(prev => prev.filter(t => t.id !== id));
  }, []);

  const markRead = useCallback(async (notificationId) => {
    try {
      await api.markNotificationRead(notificationId);
      setNotifications(prev =>
        prev.map(n => n.id === notificationId ? { ...n, is_read: true } : n)
      );
      setUnreadCount(prev => Math.max(0, prev - 1));
    } catch (err) {
      console.error('Failed to mark notification read:', err);
    }
  }, []);

  const markAllRead = useCallback(async () => {
    try {
      await api.markAllNotificationsRead();
      setNotifications(prev => prev.map(n => ({ ...n, is_read: true })));
      setUnreadCount(0);
    } catch (err) {
      console.error('Failed to mark all notifications read:', err);
    }
  }, []);

  return (
    <NotificationContext.Provider
      value={{
        notifications,
        unreadCount,
        toasts,
        dismissToast,
        markRead,
        markAllRead,
        dropdownOpen,
        setDropdownOpen,
      }}
    >
      {children}
    </NotificationContext.Provider>
  );
}

export function useNotifications() {
  const context = useContext(NotificationContext);
  if (!context) {
    throw new Error('useNotifications must be used within a NotificationProvider');
  }
  return context;
}
