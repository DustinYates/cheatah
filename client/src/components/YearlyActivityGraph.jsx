import { useState, useMemo } from 'react';
import './YearlyActivityGraph.css';

const MONTH_NAMES = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

/**
 * Monthly activity graph — 12 cells, one per month, colored by volume.
 */
export default function YearlyActivityGraph({ data = [], metric = 'total' }) {
  const [hovered, setHovered] = useState(null);

  const { months, maxVal } = useMemo(() => {
    // Aggregate daily data into months
    const monthMap = {};

    for (const d of data) {
      const key = d.date?.slice(0, 7); // "YYYY-MM"
      if (!key) continue;
      const val = metric === 'calls' ? (d.calls || 0)
        : metric === 'sms' ? (d.sms || 0)
        : (d.calls || 0) + (d.sms || 0) + (d.emails || 0);

      if (!monthMap[key]) {
        monthMap[key] = { calls: 0, sms: 0, emails: 0, val: 0, days: 0 };
      }
      monthMap[key].calls += d.calls || 0;
      monthMap[key].sms += d.sms || 0;
      monthMap[key].emails += d.emails || 0;
      monthMap[key].val += val;
      monthMap[key].days += 1;
    }

    // Build last 12 months
    const today = new Date();
    const months = [];
    let max = 1;

    for (let i = 11; i >= 0; i--) {
      const date = new Date(today.getFullYear(), today.getMonth() - i, 1);
      const key = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`;
      const agg = monthMap[key] || { calls: 0, sms: 0, emails: 0, val: 0, days: 0 };
      const isFuture = date > today;

      months.push({
        key,
        label: MONTH_NAMES[date.getMonth()],
        year: date.getFullYear(),
        ...agg,
        isFuture,
      });

      if (agg.val > max) max = agg.val;
    }

    return { months, maxVal: max };
  }, [data, metric]);

  const getLevel = (val) => {
    if (val === 0) return 0;
    const ratio = val / maxVal;
    if (ratio <= 0.25) return 1;
    if (ratio <= 0.5) return 2;
    if (ratio <= 0.75) return 3;
    return 4;
  };

  return (
    <div className="yearly-graph-container">
      <div className="yearly-months">
        {months.map((m) => (
          <div
            key={m.key}
            className="yearly-month-block"
            onMouseEnter={() => !m.isFuture && setHovered(m)}
            onMouseLeave={() => setHovered(null)}
          >
            <div className={`yearly-cell yearly-cell-lg level-${m.isFuture ? 'future' : getLevel(m.val)}`} />
            <span className="yearly-month-label">{m.label}</span>
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
          <strong>{hovered.val} interactions</strong> in {hovered.label} {hovered.year}
          {hovered.calls > 0 && <span> | {hovered.calls} calls</span>}
          {hovered.sms > 0 && <span> | {hovered.sms} SMS</span>}
          {hovered.emails > 0 && <span> | {hovered.emails} emails</span>}
        </div>
      )}
    </div>
  );
}
