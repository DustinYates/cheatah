import { useState, useMemo } from 'react';
import './YearlyActivityGraph.css';

const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
// getISOWeek returns the ISO 8601 week number (1-53)
const getISOWeek = (date) => {
  const d = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()));
  d.setUTCDate(d.getUTCDate() + 4 - (d.getUTCDay() || 7));
  const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
  return Math.ceil(((d - yearStart) / 86400000 + 1) / 7);
};

/**
 * GitHub-style yearly contribution graph.
 * Shows 52 weeks of activity with color intensity based on volume.
 */
export default function YearlyActivityGraph({ data = [], metric = 'total' }) {
  const [hovered, setHovered] = useState(null);

  // Build a map of date -> value and calculate weeks
  const { weeks, maxVal, weekLabels } = useMemo(() => {
    const dataMap = {};
    let max = 1;

    for (const d of data) {
      const val = metric === 'calls' ? (d.calls || 0)
        : metric === 'sms' ? (d.sms || 0)
        : (d.calls || 0) + (d.sms || 0) + (d.emails || 0);
      dataMap[d.date] = { ...d, val };
      if (val > max) max = val;
    }

    // Generate last 52 weeks of dates
    const today = new Date();
    const weeks = [];
    const labels = [];

    // Start from 52 weeks ago, aligned to Sunday
    const start = new Date(today);
    start.setDate(start.getDate() - 364 - start.getDay());

    for (let w = 0; w < 53; w++) {
      const week = [];
      for (let d = 0; d < 7; d++) {
        const date = new Date(start);
        date.setDate(start.getDate() + w * 7 + d);
        const dateStr = date.toISOString().split('T')[0];
        const cell = dataMap[dateStr];

        // Track week number labels (use Monday of each week)
        if (d === 1) {
          const wn = getISOWeek(date);
          // Show every 4th week to avoid crowding
          if (wn % 4 === 1) {
            labels.push({ week: w, label: `W${wn}` });
          }
        }

        week.push({
          date: dateStr,
          dayOfWeek: d,
          val: cell?.val || 0,
          calls: cell?.calls || 0,
          sms: cell?.sms || 0,
          emails: cell?.emails || 0,
          isFuture: date > today,
        });
      }
      weeks.push(week);
    }

    return { weeks, maxVal: max, weekLabels: labels };
  }, [data, metric]);

  const getLevel = (val) => {
    if (val === 0) return 0;
    const ratio = val / maxVal;
    if (ratio <= 0.25) return 1;
    if (ratio <= 0.5) return 2;
    if (ratio <= 0.75) return 3;
    return 4;
  };

  const formatDate = (dateStr) => {
    const date = new Date(dateStr + 'T00:00:00');
    return date.toLocaleDateString('en-US', {
      weekday: 'short',
      month: 'short',
      day: 'numeric',
      year: 'numeric'
    });
  };

  return (
    <div className="yearly-graph-container">
      <div className="yearly-graph">
        {/* Week number labels */}
        <div className="yearly-month-row">
          <div className="yearly-day-spacer" />
          {weeks.map((_, weekIdx) => {
            const label = weekLabels.find(l => l.week === weekIdx);
            return (
              <div key={weekIdx} className="yearly-month-cell">
                {label?.label || ''}
              </div>
            );
          })}
        </div>

        {/* Day rows */}
        {[0, 1, 2, 3, 4, 5, 6].map(dayIdx => (
          <div key={dayIdx} className="yearly-day-row">
            <div className="yearly-day-label">
              {dayIdx === 1 ? 'Mon' : dayIdx === 3 ? 'Wed' : dayIdx === 5 ? 'Fri' : ''}
            </div>
            {weeks.map((week, weekIdx) => {
              const cell = week[dayIdx];
              return (
                <div
                  key={weekIdx}
                  className={`yearly-cell level-${cell.isFuture ? 'future' : getLevel(cell.val)}`}
                  onMouseEnter={() => !cell.isFuture && setHovered(cell)}
                  onMouseLeave={() => setHovered(null)}
                />
              );
            })}
          </div>
        ))}
      </div>

      {/* Legend */}
      <div className="yearly-legend">
        <span className="yearly-legend-label">Less</span>
        <div className="yearly-cell level-0" />
        <div className="yearly-cell level-1" />
        <div className="yearly-cell level-2" />
        <div className="yearly-cell level-3" />
        <div className="yearly-cell level-4" />
        <span className="yearly-legend-label">More</span>
      </div>

      {/* Tooltip */}
      {hovered && (
        <div className="yearly-tooltip">
          <strong>{hovered.val} interactions</strong> on {formatDate(hovered.date)}
          {hovered.calls > 0 && <span> | {hovered.calls} calls</span>}
          {hovered.sms > 0 && <span> | {hovered.sms} SMS</span>}
          {hovered.emails > 0 && <span> | {hovered.emails} emails</span>}
        </div>
      )}
    </div>
  );
}
