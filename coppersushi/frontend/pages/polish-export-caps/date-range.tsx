import React,{useId,useRef} from 'react';
import {DayPicker} from '@daypicker/react';
import {FilterButton} from './column-filter';
import '@daypicker/react/style.css';

/** Inclusive delivery dates, using the map's calendar and UTC date-only convention. */
export function DateRange({from,to,start,end,onChange}:{from?:string;to?:string;start:string;end:string;onChange:(from?:string,to?:string)=>void}){
  const id=useId(),popover=useRef<HTMLDivElement>(null);
  const date=(day:string)=>new Date(`${day}T00:00:00Z`);
  return <>
    <FilterButton id={id} label="Date & time" active={Boolean(from||to)}/>
    <div {...{popover:'auto'}} id={id} ref={popover} role="dialog" aria-label="Filter delivery dates" className="cnec-calendar study-calendar">
      <DayPicker mode="range" timeZone="UTC" weekStartsOn={1} today={date(end)} defaultMonth={date(from??start)}
        startMonth={date(start)} endMonth={date(end)} disabled={[{before:date(start)},{after:date(end)}]}
        selected={from?{from:date(from),to:to?date(to):undefined}:undefined}
        onSelect={range=>onChange(range?.from?.toISOString().slice(0,10),range?.to?.toISOString().slice(0,10))}/>
      <div className="study-calendar-actions"><button onClick={()=>onChange()}>Clear dates</button><button className="cnec-calendar-close" onClick={()=>popover.current?.hidePopover()}>Close</button></div>
    </div>
  </>;
}
