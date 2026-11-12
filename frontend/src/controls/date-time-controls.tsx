import {StepButton} from './step-button';
import React, {useId, useRef} from 'react';
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
export function DateTimeControls(props:Props) {
  const today = useMarketToday();
  const tomorrow = stepDay(today, 1);
  const publication = useQuery(publicationOptions(tomorrow));
  return <CalendarTimeControls {...props} today={today} maxDay={publication.data ? tomorrow : today}/>;
}

/** Calendar presentation receives availability from its owning market page. */
export function CalendarTimeControls({day, minDay, time, previousDisabled, nextDisabled, onDay, onPrevious, onNext,today,maxDay}: Props & {today:string;maxDay:string}) {
  const calendar = useRef<HTMLDivElement | null>(null);
  const calendarId = useId();
  const latest = new Date(`${maxDay}T00:00:00Z`);
  const {refs, floatingStyles} = useFloating({
    placement: 'top-start', strategy: 'fixed', whileElementsMounted: autoUpdate,
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
      <button {...{popovertarget: calendarId}} ref={refs.setReference} type="button" className="cnec-date-picker" aria-label={`Delivery day: ${formatDay(day)}`}
        aria-haspopup="dialog" aria-controls={calendarId}>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <rect x="3" y="5" width="18" height="16" rx="2" stroke="currentColor" strokeWidth="1.6"/>
          <path d="M7 3v4m10-4v4M3 11h18" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/>
        </svg>
        <span aria-hidden="true">{formatDay(day)}</span>
      </button>
      <div {...{popover: 'auto'}} ref={node => {calendar.current = node; refs.setFloating(node);}}
        style={floatingStyles} id={calendarId} className="cnec-calendar" role="dialog" aria-label="Choose delivery day">
        <DayPicker key={day} mode="single" required timeZone="UTC" today={new Date(`${today}T00:00:00Z`)} weekStartsOn={1}
          selected={selected} defaultMonth={selected} startMonth={earliest} endMonth={latest} disabled={[{before: earliest}, {after: latest}]}
          onSelect={date => {
            const next = date.toISOString().slice(0, 10);
            calendar.current?.hidePopover();
            if (next !== day) onDay(next);
          }}/>
        <button type="button" className="cnec-calendar-close" onClick={() => calendar.current?.hidePopover()}>Close</button>
      </div>
      <StepButton direction="next" aria-label="Next day" disabled={day >= maxDay} onClick={() => onDay(stepDay(day, 1))}/>
    </div>
    <div className="cnec-control-row">
      <StepButton direction="previous" aria-label="Previous interval" disabled={previousDisabled} onClick={onPrevious}/>
      <output>{time || '—'}</output>
      <StepButton direction="next" aria-label="Next interval" disabled={nextDisabled} onClick={onNext}/>
    </div>
  </div>;
}
