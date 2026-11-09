import React, {useId, useRef, useState} from 'react';
import {autoUpdate, offset, shift, size, useFloating} from '@floating-ui/react-dom';
import {useQuery} from '@tanstack/react-query';
import {publicationOptions} from '../data/day-data';
import {useMarketToday} from './market-day';
import {DayPicker} from '@daypicker/react';
import '@daypicker/react/style.css';

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
  const dialog = useRef<HTMLDialogElement | null>(null);
  const dialogId = useId();
  const [open, setOpen] = useState(false);
  const today = useMarketToday();
  const tomorrow = stepDay(today, 1);
  const publication = useQuery({...publicationOptions(tomorrow), enabled: open || day >= today});
  const maxDay = publication.data ? tomorrow : today;
  const latest = new Date(`${maxDay}T00:00:00Z`);
  const {refs, floatingStyles} = useFloating({
    open, placement: 'top-start', strategy: 'fixed', whileElementsMounted: autoUpdate,
    middleware: [offset(8), shift({padding: 12}), size({padding: 12,
      apply: ({availableHeight, elements}) => {
        elements.floating.style.maxHeight = `${Math.max(0, availableHeight)}px`;
      },
    })],
  });
  const selected = new Date(`${day}T00:00:00Z`);
  const earliest = new Date(`${minDay}T00:00:00Z`);
  return <div className="cnec-date-time">
    <div className="cnec-control-row">
      <StepButton direction="previous" aria-label="Previous day" disabled={day <= minDay} onClick={() => onDay(stepDay(day, -1))}/>
      <button ref={refs.setReference} type="button" className="cnec-date-picker" aria-label={`Delivery day: ${formatDay(day)}`}
        aria-haspopup="dialog" aria-expanded={open} aria-controls={dialogId}
        onClick={() => {dialog.current?.showModal(); setOpen(true);}}>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <rect x="3" y="5" width="18" height="16" rx="2" stroke="currentColor" strokeWidth="1.6"/>
          <path d="M7 3v4m10-4v4M3 11h18" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/>
        </svg>
        <span aria-hidden="true">{formatDay(day)}</span>
      </button>
      <dialog ref={node => {dialog.current = node; refs.setFloating(node);}} style={floatingStyles} id={dialogId} className="cnec-calendar" aria-label="Choose delivery day"
        onClose={() => setOpen(false)}
        onClick={e => {if (e.target === e.currentTarget) dialog.current?.close();}}>
        {open && <DayPicker mode="single" required autoFocus timeZone="UTC" weekStartsOn={1}
          selected={selected} defaultMonth={selected} startMonth={earliest} endMonth={latest} disabled={[{before: earliest}, {after: latest}]}
          onSelect={date => {
            const next = date.toISOString().slice(0, 10);
            dialog.current?.close();
            if (next !== day) onDay(next);
          }}/>}
        <button type="button" className="cnec-calendar-close" onClick={() => dialog.current?.close()}>Close</button>
      </dialog>
      <StepButton direction="next" aria-label="Next day" disabled={day >= maxDay} onClick={() => onDay(stepDay(day, 1))}/>
    </div>
    <div className="cnec-control-row">
      <StepButton direction="previous" aria-label="Previous interval" disabled={previousDisabled} onClick={onPrevious}/>
      <output>{time || '—'}</output>
      <StepButton direction="next" aria-label="Next interval" disabled={nextDisabled} onClick={onNext}/>
    </div>
  </div>;
}
