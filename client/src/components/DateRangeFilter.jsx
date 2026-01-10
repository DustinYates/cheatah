import { useEffect, useMemo, useState } from 'react';
import {
  DATE_RANGE_PRESETS,
  clampCustomRange,
  formatDateForInput,
  getPresetLabel,
  getPresetRange,
  parseDateInput,
  resolveTimeZone,
} from '../utils/dateRange';
import './DateRangeFilter.css';

export default function DateRangeFilter({ value, timeZone, onChange }) {
  const tz = resolveTimeZone(timeZone);
  const [isCustomOpen, setIsCustomOpen] = useState(false);
  const [draftStart, setDraftStart] = useState(value.startDate);
  const [draftEnd, setDraftEnd] = useState(value.endDate);

  useEffect(() => {
    setDraftStart(value.startDate);
    setDraftEnd(value.endDate);
  }, [value.startDate, value.endDate]);

  const selectValue = isCustomOpen ? 'custom' : value.preset;
  const presetLabel = useMemo(() => getPresetLabel(value.preset), [value.preset]);

  const handlePresetChange = (event) => {
    const preset = event.target.value;
    if (preset === 'custom') {
      setIsCustomOpen(true);
      setDraftStart(value.startDate);
      setDraftEnd(value.endDate);
      return;
    }

    const range = getPresetRange(preset, tz);
    onChange({ preset, ...range });
    setIsCustomOpen(false);
  };

  const handleApplyCustom = () => {
    const normalized = clampCustomRange(draftStart, draftEnd, tz);
    onChange({ preset: 'custom', ...normalized });
    setIsCustomOpen(false);
  };

  const handleCancelCustom = () => {
    setDraftStart(value.startDate);
    setDraftEnd(value.endDate);
    setIsCustomOpen(false);
  };

  const isApplyDisabled = !draftStart || !draftEnd;

  return (
    <div className="date-range-filter">
      <span className="date-range-label">Date Range</span>
      <div className="date-range-control">
        <select
          className="date-range-select"
          aria-label="Date Range"
          value={selectValue}
          onChange={handlePresetChange}
        >
          {DATE_RANGE_PRESETS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
        <span className="date-range-value" aria-hidden="true">
          {presetLabel}
        </span>
      </div>
      {isCustomOpen && (
        <div className="date-range-custom">
          <label>
            Start
            <input
              type="date"
              value={formatDateForInput(draftStart, tz)}
              onChange={(event) => setDraftStart(parseDateInput(event.target.value, tz))}
            />
          </label>
          <label>
            End
            <input
              type="date"
              value={formatDateForInput(draftEnd, tz)}
              onChange={(event) => setDraftEnd(parseDateInput(event.target.value, tz))}
            />
          </label>
          <div className="date-range-actions">
            <button className="secondary" type="button" onClick={handleCancelCustom}>
              Cancel
            </button>
            <button type="button" onClick={handleApplyCustom} disabled={isApplyDisabled}>
              Apply
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
