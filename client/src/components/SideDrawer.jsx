import { useEffect } from 'react';
import { X } from 'lucide-react';
import './SideDrawer.css';

/**
 * Slide-in panel from right for drilldown data and config views.
 */
export default function SideDrawer({ title, open, onClose, children }) {
  useEffect(() => {
    if (open) {
      document.body.style.overflow = 'hidden';
    }
    return () => {
      document.body.style.overflow = '';
    };
  }, [open]);

  if (!open) return null;

  return (
    <>
      <div className="drawer-overlay" onClick={onClose} />
      <div className={`side-drawer ${open ? 'open' : ''}`}>
        <div className="drawer-header">
          <h3>{title}</h3>
          <button className="drawer-close" onClick={onClose}>
            <X size={20} />
          </button>
        </div>
        <div className="drawer-body">
          {children}
        </div>
      </div>
    </>
  );
}

/**
 * Config Diff view showing only non-default overrides.
 */
export function ConfigDiffView({ currentConfig, defaultConfig }) {
  const changedFields = Object.keys(currentConfig).filter(
    key => JSON.stringify(currentConfig[key]) !== JSON.stringify(defaultConfig[key])
  );

  if (changedFields.length === 0) {
    return <p className="config-diff-empty">All settings at defaults.</p>;
  }

  return (
    <div className="config-diff">
      <h4>Changed from defaults</h4>
      {changedFields.map(field => (
        <div key={field} className="config-diff-row">
          <span className="config-field-name">
            {field.replace(/_/g, ' ')}
          </span>
          <span className="config-field-old">{String(defaultConfig[field])}</span>
          <span className="config-field-arrow">&rarr;</span>
          <span className="config-field-new">{String(currentConfig[field])}</span>
        </div>
      ))}
    </div>
  );
}
