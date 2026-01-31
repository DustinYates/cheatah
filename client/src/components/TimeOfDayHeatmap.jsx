import { useState } from 'react';
import './TimeOfDayHeatmap.css';

const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const HOURS = Array.from({ length: 24 }, (_, i) => i);

/**
 * 7x24 heatmap grid for call/SMS volume by day and hour.
 * Color intensity based on volume. Tooltip on hover.
 */
export default function TimeOfDayHeatmap({ cells = [], metric = 'calls' }) {
  const [hovered, setHovered] = useState(null);

  // Build lookup map
  const cellMap = {};
  let maxVal = 1;
  for (const c of cells) {
    const key = `${c.day}-${c.hour}`;
    const val = metric === 'sms' ? (c.sms || 0) : (c.calls || 0);
    cellMap[key] = { ...c, val };
    if (val > maxVal) maxVal = val;
  }

  const getIntensity = (val) => {
    if (val === 0) return 0;
    return Math.max(0.1, val / maxVal);
  };

  return (
    <div className="heatmap-container">
      <div className="heatmap-grid">
        {/* Hour labels */}
        <div className="heatmap-corner" />
        {HOURS.map(h => (
          <div key={h} className="heatmap-hour-label">
            {h === 0 ? '12a' : h < 12 ? `${h}a` : h === 12 ? '12p' : `${h - 12}p`}
          </div>
        ))}

        {/* Rows */}
        {DAYS.map((day, dayIdx) => (
          <div key={dayIdx} className="heatmap-row" style={{ display: 'contents' }}>
            <div className="heatmap-day-label">{day}</div>
            {HOURS.map(hour => {
              const key = `${dayIdx}-${hour}`;
              const cell = cellMap[key];
              const val = cell?.val || 0;
              const intensity = getIntensity(val);
              return (
                <div
                  key={hour}
                  className="heatmap-cell"
                  style={{
                    backgroundColor: val > 0
                      ? `rgba(74, 222, 128, ${intensity})`
                      : '#f4f4f5',
                  }}
                  onMouseEnter={() => setHovered({ day: DAYS[dayIdx], hour, val, cell })}
                  onMouseLeave={() => setHovered(null)}
                />
              );
            })}
          </div>
        ))}
      </div>

      {hovered && (
        <div className="heatmap-tooltip-fixed">
          {hovered.day} {hovered.hour}:00 — {hovered.val} {metric}
          {hovered.cell && metric === 'calls' && hovered.cell.sms > 0 && (
            <span> | {hovered.cell.sms} SMS</span>
          )}
        </div>
      )}
    </div>
  );
}
