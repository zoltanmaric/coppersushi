import React from 'react';

const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sept', 'Oct', 'Nov', 'Dec'];

/** Format a validated ISO delivery day without assigning an instant or timezone. */
export function formatDay(day: string): string {
  const [year, month, date] = day.split('-');
  return `${Number(date)} ${months[Number(month) - 1]} ${year}`;
}

function StepButton({direction, ...props}: React.ComponentProps<'button'> & {direction: 'previous' | 'next'}) {
  return <button {...props}><svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <path d={direction === 'previous' ? 'm14 6-6 6 6 6' : 'm10 6 6 6-6 6'}
      stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
  </svg></button>;
}

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
  return <div className="cnec-date-time">
    <div className="cnec-control-row">
      <StepButton direction="previous" aria-label="Previous day" disabled={day <= minDay} onClick={() => onDay(stepDay(day, -1))}/>
      <label className="cnec-date-picker">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <rect x="3" y="5" width="18" height="16" rx="2" stroke="currentColor" strokeWidth="1.6"/>
          <path d="M7 3v4m10-4v4M3 11h18" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/>
        </svg>
        <span aria-hidden="true">{formatDay(day)}</span>
        <input aria-label="Delivery day" type="date" min={minDay} value={day}
          onClick={e => {
            try {
              e.currentTarget.showPicker();
              e.preventDefault();
            } catch {
              // Let the browser handle the native control if opening is unavailable.
            }
          }}
          onChange={e => {if (e.target.value >= minDay && e.target.value !== day) onDay(e.target.value);}}/>
      </label>
      <StepButton direction="next" aria-label="Next day" onClick={() => onDay(stepDay(day, 1))}/>
    </div>
    <div className="cnec-control-row">
      <StepButton direction="previous" aria-label="Previous interval" disabled={previousDisabled} onClick={onPrevious}/>
      <output>{time || '—'}</output>
      <StepButton direction="next" aria-label="Next interval" disabled={nextDisabled} onClick={onNext}/>
    </div>
  </div>;
}
