import { useState } from 'react';
import { ChevronDown } from 'lucide-react';
import './CollapsibleSection.css';

/**
 * Collapsible section wrapper for existing contact detail features
 */
export default function CollapsibleSection({
  title,
  count = 0,
  defaultOpen = false,
  children,
  emptyMessage = 'No data',
  icon,
}) {
  const [isOpen, setIsOpen] = useState(defaultOpen);

  const hasContent = count > 0;

  return (
    <div className={`collapsible-section ${isOpen ? 'open' : ''}`}>
      <button
        className="collapsible-section-header"
        onClick={() => setIsOpen(!isOpen)}
        aria-expanded={isOpen}
      >
        <div className="collapsible-section-title">
          {icon && <span className="section-icon">{icon}</span>}
          <span>{title}</span>
          {count > 0 && <span className="section-count">{count}</span>}
        </div>
        <ChevronDown
          size={18}
          className={`section-chevron ${isOpen ? 'expanded' : ''}`}
        />
      </button>

      <div className={`collapsible-section-content ${isOpen ? 'open' : ''}`}>
        <div className="collapsible-section-inner">
          {hasContent ? children : (
            <p className="section-empty">{emptyMessage}</p>
          )}
        </div>
      </div>
    </div>
  );
}
