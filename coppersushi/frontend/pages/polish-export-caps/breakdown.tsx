import React from 'react';
import type {Investigation} from './data';
import {PRICE_COLORSCALE} from '../../map/price-scale';
import {formatDay} from '../../controls/date-time-controls';
const count=new Intl.NumberFormat('en-GB');
const percent=(n:number,d:number)=>`${(100*n/d).toFixed(1)}%`;

/** Two views of the same fixed population; table filters never change this denominator. */
export function Breakdown({study}:{study:Investigation}){
  const c=study.coverage,teal=PRICE_COLORSCALE[1][1];
  const short=1000*c.shortfall_binding/c.expected,full=1000*c.binding/c.expected,zoom=1000*c.shortfall_binding/c.binding;
  return <section className="study-breakdown" aria-labelledby="breakdown-heading"><p className="export-cap-eyebrow">Poland · day-ahead market</p>
    <h1 id="breakdown-heading">When export caps bind,<br/>were reserves under-procured?</h1>
    <p>{formatDay(study.start)}–{formatDay(study.end)} · {count.format(c.expected)} quarter-hours</p>
    <div className="study-bar-labels"><span><strong>{count.format(c.binding)} · {percent(c.binding,c.expected)}</strong>Binding export cap</span><span><strong>{count.format(c.nonbinding)} · {percent(c.nonbinding,c.expected)}</strong>Nonbinding</span></div>
    <svg className="study-bars" viewBox="0 0 1000 130" preserveAspectRatio="none" role="img" aria-label={`${c.binding} binding quarters out of ${c.expected}; ${c.shortfall_binding} with procurement shortfall and ${c.no_shortfall_binding} without.`}>
      <rect x="0" y="0" width={short} height="40" fill={teal}/><rect x={short} y="0" width={full-short} height="40" className="study-no-shortfall"/><rect className="study-nonbinding" x={full} y="0" width={1000-full} height="40"/>
      <path className="study-connector" d={`M0 40 L0 90 M${full} 40 L1000 90`}/>
      <rect x="0" y="90" width={zoom} height="40" fill={teal}/><rect x={zoom} y="90" width={1000-zoom} height="40" className="study-no-shortfall"/>
    </svg>
    <div className="study-bar-labels"><span><strong>{count.format(c.shortfall_binding)} · {percent(c.shortfall_binding,c.binding)}</strong>Procurement shortfall</span><span><strong>{count.format(c.no_shortfall_binding)} · {percent(c.no_shortfall_binding,c.binding)}</strong>No procurement shortfall</span></div>
    <svg className="study-conclusion" viewBox="0 0 340 100" role="img" aria-label={percent(c.no_shortfall_binding,c.binding)}><text x="0" y="80" className="study-no-shortfall">{percent(c.no_shortfall_binding,c.binding)}</text></svg>
    <p className="study-finding">of binding quarters had no aggregate upward procurement shortfall.</p>
    <p className="export-cap-note">Procurement sufficiency does not establish operational reserve availability or whether the cap was justified. This is the fixed investigated window; table filters do not change these counts.</p>
  </section>;
}
