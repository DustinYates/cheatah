import { useState } from 'react';
import './CHIGauge.css';

/**
 * Small circular gauge for CHI score display.
 * Red (0-40), Yellow (40-70), Green (70-100).
 * Hover shows signal breakdown.
 */
export default function CHIGauge({ score, size = 64, signals, label, noDataMessage }) {
  const [showDetail, setShowDetail] = useState(false);

  const displayScore = score != null ? Math.round(score) : '--';
  const color = score == null ? '#d4d4d8'
    : score < 40 ? '#dc2626'
    : score < 70 ? '#d97706'
    : '#16a34a';

  const circumference = 2 * Math.PI * 24;
  const progress = score != null ? (score / 100) * circumference : 0;

  return (
    <div
      className="chi-gauge"
      onMouseEnter={() => setShowDetail(true)}
      onMouseLeave={() => setShowDetail(false)}
    >
      <svg width={size} height={size} viewBox="0 0 56 56">
        {/* Background circle */}
        <circle
          cx="28" cy="28" r="24"
          fill="none"
          stroke="#e4e4e7"
          strokeWidth="4"
        />
        {/* Progress arc */}
        <circle
          cx="28" cy="28" r="24"
          fill="none"
          stroke={color}
          strokeWidth="4"
          strokeDasharray={circumference}
          strokeDashoffset={circumference - progress}
          strokeLinecap="round"
          transform="rotate(-90 28 28)"
        />
        {/* Score text */}
        <text
          x="28" y="30"
          textAnchor="middle"
          dominantBaseline="central"
          fontSize="14"
          fontWeight="700"
          fill={color}
        >
          {displayScore}
        </text>
      </svg>
      {label && <span className="chi-gauge-label">{label}</span>}
      {score == null && noDataMessage && (
        <span className="chi-gauge-no-data">{noDataMessage}</span>
      )}

      {showDetail && signals && signals.length > 0 && (
        <div className="chi-gauge-detail">
          <div className="chi-detail-title">Signal Breakdown</div>
          {signals.map((s, i) => (
            <div key={i} className={`chi-signal ${s.weight < 0 ? 'negative' : 'positive'}`}>
              <span className="chi-signal-name">{s.name.replace(/_/g, ' ')}</span>
              <span className="chi-signal-weight">
                {s.weight > 0 ? '+' : ''}{s.weight}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
