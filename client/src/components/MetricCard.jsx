import { useState } from 'react';
import { HelpCircle, Settings } from 'lucide-react';
import './MetricCard.css';

/**
 * Progressive-disclosure metric card.
 *
 * - Shows value + label by default
 * - Hover (i) icon -> tooltip with "Computed using..." summary
 * - Hover gear icon -> config summary tooltip
 * - Click card -> drilldown callback
 * - Click gear -> config detail callback
 */
export default function MetricCard({
  label,
  value,
  subValue,
  tooltip,
  configSummary,
  onDrilldown,
  onConfigClick,
  trend,
  severity,
  className = '',
}) {
  const [showTooltip, setShowTooltip] = useState(false);
  const [showConfigTip, setShowConfigTip] = useState(false);

  const trendClass = trend > 0 ? 'trend-up' : trend < 0 ? 'trend-down' : '';
  const severityClass = severity ? `severity-${severity}` : '';

  return (
    <div
      className={`metric-card ${severityClass} ${onDrilldown ? 'clickable' : ''} ${className}`}
      onClick={onDrilldown}
    >
      <div className="metric-card-header">
        <span className="metric-card-label">{label}</span>
        <div className="metric-card-icons">
          {tooltip && (
            <span
              className="metric-card-info"
              onMouseEnter={() => setShowTooltip(true)}
              onMouseLeave={() => setShowTooltip(false)}
            >
              <HelpCircle size={14} />
              {showTooltip && (
                <div className="metric-tooltip">{tooltip}</div>
              )}
            </span>
          )}
          {configSummary && (
            <span
              className="metric-card-config"
              onMouseEnter={() => setShowConfigTip(true)}
              onMouseLeave={() => setShowConfigTip(false)}
              onClick={(e) => {
                e.stopPropagation();
                onConfigClick?.();
              }}
            >
              <Settings size={14} />
              {showConfigTip && (
                <div className="metric-tooltip">{configSummary}</div>
              )}
            </span>
          )}
        </div>
      </div>
      <div className="metric-card-body">
        <span className="metric-card-value">{value}</span>
        {subValue && <span className="metric-card-sub">{subValue}</span>}
        {trend !== undefined && trend !== null && (
          <span className={`metric-card-trend ${trendClass}`}>
            {trend > 0 ? '+' : ''}{trend}%
          </span>
        )}
      </div>
    </div>
  );
}
