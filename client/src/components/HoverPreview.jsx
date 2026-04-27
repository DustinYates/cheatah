import { useRef, useState, useCallback } from 'react';
import { createPortal } from 'react-dom';

const SPEAKER_LABEL = {
  assistant: 'AI',
  user: 'Them',
  voice: 'Voice',
  system: 'System',
};

const TIP_STYLE = {
  position: 'fixed',
  zIndex: 9999,
  maxWidth: 360,
  padding: '8px 10px',
  background: 'rgba(17, 24, 39, 0.95)',
  color: '#fff',
  borderRadius: 6,
  fontSize: 13,
  lineHeight: 1.4,
  boxShadow: '0 6px 20px rgba(0,0,0,0.25)',
  pointerEvents: 'none',
  whiteSpace: 'normal',
  wordBreak: 'break-word',
};

const SPEAKER_STYLE = {
  display: 'inline-block',
  marginRight: 6,
  fontWeight: 600,
  opacity: 0.85,
};

export function useHoverPreview({ text, role, delay = 100 }) {
  const [pos, setPos] = useState(null);
  const timerRef = useRef(null);
  const lastEventRef = useRef({ x: 0, y: 0 });

  const clearTimer = () => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  };

  const handleEnter = useCallback((e) => {
    if (!text) return;
    lastEventRef.current = { x: e.clientX, y: e.clientY };
    clearTimer();
    timerRef.current = setTimeout(() => {
      setPos({ ...lastEventRef.current });
    }, delay);
  }, [text, delay]);

  const handleMove = useCallback((e) => {
    lastEventRef.current = { x: e.clientX, y: e.clientY };
    setPos((prev) => (prev ? { x: e.clientX, y: e.clientY } : prev));
  }, []);

  const handleLeave = useCallback(() => {
    clearTimer();
    setPos(null);
  }, []);

  if (!text) {
    return { handlers: {}, tooltip: null };
  }

  const speaker = role ? SPEAKER_LABEL[role] || null : null;

  const tooltip = pos
    ? createPortal(
        <div
          style={{
            ...TIP_STYLE,
            left: Math.min(pos.x + 14, window.innerWidth - 380),
            top: Math.min(pos.y + 14, window.innerHeight - 80),
          }}
        >
          {speaker && <span style={SPEAKER_STYLE}>{speaker}:</span>}
          <span>{text}</span>
        </div>,
        document.body
      )
    : null;

  return {
    handlers: {
      onMouseEnter: handleEnter,
      onMouseMove: handleMove,
      onMouseLeave: handleLeave,
    },
    tooltip,
  };
}

export function HoverPreviewWrapper({ text, role, delay, children }) {
  const { handlers, tooltip } = useHoverPreview({ text, role, delay });
  return (
    <>
      {children(handlers)}
      {tooltip}
    </>
  );
}
