import { useState, useMemo } from 'react';
import './ActivityHeatmap.css';

const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

/**
 * Get color based on activity count
 */
function getActivityColor(count, maxCount) {
  if (count === 0) return '#ebedf0';
  const intensity = Math.min(count / Math.max(maxCount, 1), 1);
  if (intensity < 0.25) return '#9be9a8';
  if (intensity < 0.5) return '#40c463';
  if (intensity < 0.75) return '#30a14e';
  return '#216e39';
}

/**
 * Generate week columns for the past year
 */
function generateWeeks(data, endDate) {
  const dataMap = new Map();
  let maxCount = 1;

  // Build lookup map
  for (const item of data) {
    dataMap.set(item.date, item);
    if (item.count > maxCount) maxCount = item.count;
  }

  const end = new Date(endDate);
  const start = new Date(end);
  start.setDate(start.getDate() - 364); // 52 weeks

  // Adjust start to beginning of week (Sunday)
  const startDay = start.getDay();
  start.setDate(start.getDate() - startDay);

  const weeks = [];
  let currentDate = new Date(start);

  while (currentDate <= end) {
    const week = [];
    for (let d = 0; d < 7; d++) {
      const dateStr = currentDate.toISOString().split('T')[0];
      const dayData = dataMap.get(dateStr);
      week.push({
        date: dateStr,
        dayOfWeek: currentDate.getDay(),
        count: dayData?.count || 0,
        sms: dayData?.sms || 0,
        call: dayData?.call || 0,
        email: dayData?.email || 0,
        chat: dayData?.chat || 0,
        isInRange: currentDate >= new Date(start) && currentDate <= end,
      });
      currentDate.setDate(currentDate.getDate() + 1);
    }
    weeks.push(week);
  }

  return { weeks, maxCount };
}

/**
 * Generate month labels for the heatmap
 */
function generateMonthLabels(weeks) {
  const labels = [];
  let lastMonth = -1;

  weeks.forEach((week, weekIdx) => {
    // Check the first day of each week
    const firstDay = week[0];
    const date = new Date(firstDay.date);
    const month = date.getMonth();

    if (month !== lastMonth) {
      labels.push({ month: MONTHS[month], weekIdx });
      lastMonth = month;
    }
  });

  return labels;
}

/**
 * GitHub-style activity heatmap
 */
export default function ActivityHeatmap({ data = [], startDate, endDate, total = 0 }) {
  const [tooltip, setTooltip] = useState(null);

  const { weeks, maxCount } = useMemo(
    () => generateWeeks(data, endDate || new Date().toISOString().split('T')[0]),
    [data, endDate]
  );

  const monthLabels = useMemo(() => generateMonthLabels(weeks), [weeks]);

  const formatTooltipDate = (dateStr) => {
    const date = new Date(dateStr + 'T00:00:00');
    return date.toLocaleDateString('en-US', {
      weekday: 'short',
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    });
  };

  return (
    <div className="activity-heatmap">
      <div className="heatmap-header">
        <h3 className="heatmap-title">Activity</h3>
        <span className="heatmap-total">
          {total} interaction{total !== 1 ? 's' : ''} in the last year
        </span>
      </div>

      <div className="heatmap-container">
        {/* Month labels */}
        <div className="heatmap-months">
          {monthLabels.map((label, idx) => (
            <span
              key={idx}
              className="month-label"
              style={{ gridColumnStart: label.weekIdx + 2 }}
            >
              {label.month}
            </span>
          ))}
        </div>

        <div className="heatmap-grid">
          {/* Day labels */}
          <div className="heatmap-days">
            <span className="day-label"></span>
            <span className="day-label">Mon</span>
            <span className="day-label"></span>
            <span className="day-label">Wed</span>
            <span className="day-label"></span>
            <span className="day-label">Fri</span>
            <span className="day-label"></span>
          </div>

          {/* Weeks grid */}
          <div className="heatmap-weeks">
            {weeks.map((week, weekIdx) => (
              <div key={weekIdx} className="heatmap-week">
                {week.map((day, dayIdx) => (
                  <div
                    key={dayIdx}
                    className="heatmap-cell"
                    style={{ backgroundColor: getActivityColor(day.count, maxCount) }}
                    onMouseEnter={(e) => {
                      const rect = e.target.getBoundingClientRect();
                      setTooltip({
                        x: rect.left + rect.width / 2,
                        y: rect.top,
                        ...day,
                      });
                    }}
                    onMouseLeave={() => setTooltip(null)}
                  />
                ))}
              </div>
            ))}
          </div>
        </div>

        {/* Legend */}
        <div className="heatmap-legend">
          <span className="legend-label">Less</span>
          <div className="legend-cells">
            <div className="legend-cell" style={{ backgroundColor: '#ebedf0' }} />
            <div className="legend-cell" style={{ backgroundColor: '#9be9a8' }} />
            <div className="legend-cell" style={{ backgroundColor: '#40c463' }} />
            <div className="legend-cell" style={{ backgroundColor: '#30a14e' }} />
            <div className="legend-cell" style={{ backgroundColor: '#216e39' }} />
          </div>
          <span className="legend-label">More</span>
        </div>
      </div>

      {/* Tooltip */}
      {tooltip && (
        <div
          className="heatmap-tooltip"
          style={{
            left: tooltip.x,
            top: tooltip.y - 40,
          }}
        >
          <strong>
            {tooltip.count} interaction{tooltip.count !== 1 ? 's' : ''}
          </strong>
          <span className="tooltip-date">{formatTooltipDate(tooltip.date)}</span>
          {tooltip.count > 0 && (
            <div className="tooltip-breakdown">
              {tooltip.call > 0 && <span>{tooltip.call} call{tooltip.call !== 1 ? 's' : ''}</span>}
              {tooltip.sms > 0 && <span>{tooltip.sms} SMS</span>}
              {tooltip.email > 0 && <span>{tooltip.email} email{tooltip.email !== 1 ? 's' : ''}</span>}
              {tooltip.chat > 0 && <span>{tooltip.chat} chat{tooltip.chat !== 1 ? 's' : ''}</span>}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
