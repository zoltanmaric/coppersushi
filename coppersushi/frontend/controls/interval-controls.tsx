import React from 'react';
import {Timeline} from './timeline';
import {StepButton} from './step-button';

/** One bottom panel for fixed-date and selectable-date maps. */
export function IntervalControls({date,labels,interval,onChange,busy=false}:{date:React.ReactNode;labels:string[];interval:number;onChange:(index:number)=>void;busy?:boolean}) {
  const disabled = busy || !labels.length;
  return <div className="cnec-time-controls cnec-panel" aria-busy={busy || disabled}>
    <div className="cnec-date-time">{date}
      <div className="cnec-control-row">
        <StepButton direction="previous" aria-label="Previous interval" disabled={disabled || interval<=0} onClick={()=>onChange(interval-1)}/>
        <output>{labels[interval]?.split(' · ').at(-1) || '—'}</output>
        <StepButton direction="next" aria-label="Next interval" disabled={disabled || interval>=labels.length-1} onClick={()=>onChange(interval+1)}/>
      </div>
    </div>
    <div className="cnec-slider-panel"><Timeline labels={labels} interval={interval} disabled={disabled} onChange={onChange}/></div>
  </div>;
}
