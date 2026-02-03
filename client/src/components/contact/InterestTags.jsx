import { useState } from 'react';
import { X, Plus } from 'lucide-react';
import './InterestTags.css';

/**
 * Generate a deterministic color for a tag
 */
function tagToColor(tag) {
  let hash = 0;
  for (let i = 0; i < tag.length; i++) {
    hash = tag.charCodeAt(i) + ((hash << 5) - hash);
  }
  const hue = (hash % 12) * 30; // 12 distinct colors
  return `hsl(${hue}, 70%, 95%)`;
}

function tagToTextColor(tag) {
  let hash = 0;
  for (let i = 0; i < tag.length; i++) {
    hash = tag.charCodeAt(i) + ((hash << 5) - hash);
  }
  const hue = (hash % 12) * 30;
  return `hsl(${hue}, 70%, 35%)`;
}

/**
 * Single tag pill
 */
function TagPill({ tag, onRemove, editable }) {
  return (
    <span
      className="tag-pill"
      style={{
        backgroundColor: tagToColor(tag),
        color: tagToTextColor(tag),
      }}
    >
      {tag}
      {editable && (
        <button
          className="tag-remove"
          onClick={() => onRemove(tag)}
          aria-label={`Remove ${tag}`}
        >
          <X size={12} />
        </button>
      )}
    </span>
  );
}

/**
 * Editable interest tags component
 */
export default function InterestTags({
  tags = [],
  onAdd,
  onRemove,
  editable = true,
  maxTags = 10,
  placeholder = 'Add tag...',
}) {
  const [inputValue, setInputValue] = useState('');
  const [isAdding, setIsAdding] = useState(false);

  const handleAdd = () => {
    const trimmed = inputValue.trim().toLowerCase();
    if (trimmed && !tags.includes(trimmed) && tags.length < maxTags) {
      onAdd(trimmed);
      setInputValue('');
      setIsAdding(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleAdd();
    } else if (e.key === 'Escape') {
      setInputValue('');
      setIsAdding(false);
    }
  };

  return (
    <div className="interest-tags">
      <div className="interest-tags-header">
        <h3 className="interest-tags-title">Interests</h3>
      </div>

      <div className="tags-container">
        {tags.length === 0 && !editable && (
          <span className="no-tags">No interests added</span>
        )}

        {tags.map((tag) => (
          <TagPill
            key={tag}
            tag={tag}
            onRemove={onRemove}
            editable={editable}
          />
        ))}

        {editable && tags.length < maxTags && (
          <>
            {isAdding ? (
              <div className="tag-input-wrapper">
                <input
                  type="text"
                  className="tag-input"
                  value={inputValue}
                  onChange={(e) => setInputValue(e.target.value)}
                  onKeyDown={handleKeyDown}
                  onBlur={() => {
                    if (!inputValue.trim()) {
                      setIsAdding(false);
                    }
                  }}
                  placeholder={placeholder}
                  autoFocus
                  maxLength={30}
                />
                <button
                  className="tag-input-add"
                  onClick={handleAdd}
                  disabled={!inputValue.trim()}
                >
                  <Plus size={14} />
                </button>
              </div>
            ) : (
              <button
                className="add-tag-btn"
                onClick={() => setIsAdding(true)}
              >
                <Plus size={14} />
                Add
              </button>
            )}
          </>
        )}
      </div>
    </div>
  );
}
