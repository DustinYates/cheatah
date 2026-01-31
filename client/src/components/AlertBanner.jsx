import { AlertTriangle, X } from 'lucide-react';
import './AlertBanner.css';

/**
 * Sticky alert banner for active critical anomalies/burst incidents.
 */
export default function AlertBanner({ severity = 'warning', message, onDismiss }) {
  return (
    <div className={`alert-banner alert-${severity}`}>
      <AlertTriangle size={18} />
      <span className="alert-message">{message}</span>
      {onDismiss && (
        <button className="alert-dismiss" onClick={onDismiss}>
          <X size={16} />
        </button>
      )}
    </div>
  );
}
