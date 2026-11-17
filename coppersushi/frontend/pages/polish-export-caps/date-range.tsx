import React,{useId,useRef} from 'react';
import {DayPicker} from '@daypicker/react';
import {formatDay} from '../../controls/date-time-controls';
import '@daypicker/react/style.css';

/** Inclusive delivery dates, using the map's calendar and UTC date-only convention. */
export function DateRange({from,to,start,end,onChange}:{from?:string;to?:string;start:string;end:string;onChange:(from?:string,to?:string)=>void}){
  const id=useId(),popover=useRef<HTMLDivElement>(null);
  const date=(day:string)=>new Date(`${day}T00:00:00Z`);
  return <div className="study-date-range">
    <button type="button" {...{popovertarget:id}} aria-haspopup="dialog" aria-controls={id}>
      {from||to?`${from?formatDay(from):'Start'} – ${to?formatDay(to):'End'}`:'All delivery dates'}
    </button>
    {(from||to)&&<button type="button" onClick={()=>onChange()} aria-label="Clear date range">Clear dates</button>}
    <div {...{popover:'auto'}} id={id} ref={popover} role="dialog" aria-label="Filter delivery dates" className="cnec-calendar study-calendar">
      <DayPicker mode="range" timeZone="UTC" weekStartsOn={1} today={date(end)} defaultMonth={date(from??start)}
        startMonth={date(start)} endMonth={date(end)} disabled={[{before:date(start)},{after:date(end)}]}
        selected={from?{from:date(from),to:to?date(to):undefined}:undefined}
        onSelect={range=>onChange(range?.from?.toISOString().slice(0,10),range?.to?.toISOString().slice(0,10))}/>
      <div className="study-calendar-actions"><button onClick={()=>onChange()}>Clear dates</button><button className="cnec-calendar-close" onClick={()=>popover.current?.hidePopover()}>Close</button></div>
    </div>
  </div>;
}
