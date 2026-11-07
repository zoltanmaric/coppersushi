import React from 'react';

/** Step calendar dates in UTC, independent of the browser's timezone and DST. */
export function stepDay(day: string, direction: number): string {
  const date = new Date(`${day}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + direction);
  return date.toISOString().slice(0, 10);
}

interface Props {
  day: string; minDay: string; time: string; previousDisabled: boolean; nextDisabled: boolean;
  onDay: (day: string) => void; onPrevious: () => void; onNext: () => void;
}
export function DateTimeControls({day, minDay, time, previousDisabled, nextDisabled, onDay, onPrevious, onNext}: Props) {
  return <div className="cnec-date-time cnec-panel">
    <div className="cnec-control-row">
      <button aria-label="Previous day" disabled={day <= minDay} onClick={() => onDay(stepDay(day, -1))}>‹</button>
      <input aria-label="Delivery day" type="date" min={minDay} value={day}
        onChange={e => {if (e.target.value >= minDay && e.target.value !== day) onDay(e.target.value);}}/>
      <button aria-label="Next day" onClick={() => onDay(stepDay(day, 1))}>›</button>
    </div>
    <div className="cnec-control-row">
      <button aria-label="Previous interval" disabled={previousDisabled} onClick={onPrevious}>‹</button>
      <output>{time || '—'}</output>
      <button aria-label="Next interval" disabled={nextDisabled} onClick={onNext}>›</button>
    </div>
  </div>;
}
