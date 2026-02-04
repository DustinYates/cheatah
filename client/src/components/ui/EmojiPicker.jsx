import { useState, useRef, useEffect } from 'react';
import './EmojiPicker.css';

// Curated emoji list - ~100 most common emojis (~2KB)
const EMOJI_CATEGORIES = {
  smileys: [
    '😀', '😃', '😄', '😁', '😅', '😂', '🤣', '😊', '😇', '🙂',
    '😉', '😌', '😍', '🥰', '😘', '😗', '😋', '😛', '😜', '🤪',
    '😎', '🤩', '🥳', '😏', '😬', '🤔', '🤗', '🤭', '😐', '😑',
    '😶', '🙄', '😌', '😔', '😪', '🤤', '😴', '😷', '🤧', '🥺',
    '😢', '😭', '😤', '😠', '🤯', '😱', '😨', '😰', '😥'
  ],
  gestures: [
    '👍', '👎', '👏', '🙌', '🤝', '👊', '✊', '🤛', '🤜', '🤞',
    '✌️', '🤟', '🤘', '👌', '🤌', '🤏', '👈', '👉', '👆', '👇',
    '☝️', '✋', '🤚', '🖐️', '🖖', '👋', '🤙', '💪', '🙏', '🫶'
  ],
  symbols: [
    '❤️', '🧡', '💛', '💚', '💙', '💜', '🖤', '🤍', '💔', '❣️',
    '💕', '💗', '💖', '💘', '💝', '🔥', '✨', '⭐', '🌟', '💫',
    '⚡', '💥', '💯', '✅', '❌', '⚠️', '🚫', '💡', '🎯', '🏆'
  ],
  objects: [
    '🎉', '🎊', '🎁', '🎈', '🚀', '💻', '📱', '💬', '📝', '📌',
    '📎', '🔗', '📧', '📅', '⏰', '🔔', '📊', '📈', '📉', '🗂️',
    '📁', '🔒', '🔓', '🔑', '🛠️', '⚙️', '🔧', '📦', '💼', '🎵'
  ]
};

const RECENT_KEY = 'forum_recent_emojis';
const MAX_RECENT = 16;

function getRecentEmojis() {
  try {
    return JSON.parse(localStorage.getItem(RECENT_KEY)) || [];
  } catch {
    return [];
  }
}

function addRecentEmoji(emoji) {
  const recent = getRecentEmojis().filter(e => e !== emoji);
  recent.unshift(emoji);
  localStorage.setItem(RECENT_KEY, JSON.stringify(recent.slice(0, MAX_RECENT)));
}

export default function EmojiPicker({ onSelect, position = 'top' }) {
  const [isOpen, setIsOpen] = useState(false);
  const [recentEmojis, setRecentEmojis] = useState(getRecentEmojis);
  const containerRef = useRef(null);

  // Close on outside click
  useEffect(() => {
    function handleClickOutside(e) {
      if (containerRef.current && !containerRef.current.contains(e.target)) {
        setIsOpen(false);
      }
    }
    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
      return () => document.removeEventListener('mousedown', handleClickOutside);
    }
  }, [isOpen]);

  // Close on escape
  useEffect(() => {
    function handleEscape(e) {
      if (e.key === 'Escape') {
        setIsOpen(false);
      }
    }
    if (isOpen) {
      document.addEventListener('keydown', handleEscape);
      return () => document.removeEventListener('keydown', handleEscape);
    }
  }, [isOpen]);

  const handleSelect = (emoji) => {
    addRecentEmoji(emoji);
    setRecentEmojis(getRecentEmojis());
    onSelect(emoji);
  };

  const categoryLabels = {
    recent: 'Recently Used',
    smileys: 'Smileys',
    gestures: 'Gestures',
    symbols: 'Symbols',
    objects: 'Objects'
  };

  // Prevent focus from leaving the textarea when clicking emoji UI
  const preventFocusLoss = (e) => e.preventDefault();

  return (
    <div className="emoji-picker-container" ref={containerRef}>
      <button
        type="button"
        className="emoji-picker-trigger"
        onMouseDown={preventFocusLoss}
        onClick={() => setIsOpen(!isOpen)}
        title="Add emoji"
        aria-label="Add emoji"
        aria-expanded={isOpen}
      >
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="10" />
          <path d="M8 14s1.5 2 4 2 4-2 4-2" />
          <line x1="9" y1="9" x2="9.01" y2="9" />
          <line x1="15" y1="9" x2="15.01" y2="9" />
        </svg>
      </button>

      {isOpen && (
        <div
          className={`emoji-picker-popover emoji-picker-popover--${position}`}
          onMouseDown={preventFocusLoss}
        >
          {recentEmojis.length > 0 && (
            <div className="emoji-section">
              <div className="emoji-section-label">{categoryLabels.recent}</div>
              <div className="emoji-grid">
                {recentEmojis.map((emoji, i) => (
                  <button
                    key={`recent-${i}`}
                    type="button"
                    className="emoji-btn"
                    onClick={() => handleSelect(emoji)}
                    title={emoji}
                  >
                    {emoji}
                  </button>
                ))}
              </div>
            </div>
          )}

          {Object.entries(EMOJI_CATEGORIES).map(([category, emojis]) => (
            <div key={category} className="emoji-section">
              <div className="emoji-section-label">{categoryLabels[category]}</div>
              <div className="emoji-grid">
                {emojis.map((emoji, i) => (
                  <button
                    key={`${category}-${i}`}
                    type="button"
                    className="emoji-btn"
                    onClick={() => handleSelect(emoji)}
                    title={emoji}
                  >
                    {emoji}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
