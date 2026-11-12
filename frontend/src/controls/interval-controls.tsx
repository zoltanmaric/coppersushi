import React from 'react';
import {Timeline} from './timeline';
import {StepButton} from './step-button';

/** Presentation shared by fixed-date and market-day maps. */
export function IntervalControls({date,labels,interval,onChange}:{date:React.ReactNode;labels:string[];interval:number;onChange:(index:number)=>void}) {
  return <div className="cnec-time-controls cnec-panel" aria-busy={!labels.length}>
    <div className="cnec-date-time"><div className="cnec-control-row">{date}</div><div className="cnec-control-row">
      <StepButton direction="previous" aria-label="Previous interval" disabled={interval<=0} onClick={()=>onChange(interval-1)}/>
      <output>{labels[interval]?.split(' · ').at(-1) ?? '—'}</output>
      <StepButton direction="next" aria-label="Next interval" disabled={!labels.length||interval>=labels.length-1} onClick={()=>onChange(interval+1)}/>
    </div></div>
    <div className="cnec-slider-panel"><Timeline labels={labels} interval={interval} disabled={!labels.length} onChange={onChange}/></div>
  </div>;
}
