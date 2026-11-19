import React from 'react';
import type {Investigation} from './data';
import {PRICE_COLORSCALE} from '../../map/price-scale';
import {formatDay} from '../../controls/date-time-controls';
const count=new Intl.NumberFormat('en-GB');
const percent=(n:number,d:number)=>`${(100*n/d).toFixed(1)}%`;

/** Two views of the same fixed population; table filters never change this denominator. */
export function Breakdown({study,showTitle=true}:{study:Investigation;showTitle?:boolean}){
  const c=study.coverage, imports=c.imports;
  const importTotal=imports ? imports.shortfall + imports.no_shortfall : 0;
  const remainder=c.nonbinding-importTotal;
  const importStart=1000*(1-importTotal/c.expected);
  const importShort=1000*(imports?.shortfall ?? 0)/c.expected;
  const color=(i:number)=>PRICE_COLORSCALE[i][1];
  const noShort=1000*c.no_shortfall_binding/c.expected,full=1000*c.binding/c.expected,zoom=c.binding ? 1000*c.no_shortfall_binding/c.binding : 0;
  return <section className="study-breakdown" aria-labelledby={showTitle?'breakdown-heading':undefined} aria-label={showTitle?undefined:'Polish export-cap breakdown'}><p className="export-cap-eyebrow">Poland · day-ahead market</p>
    {showTitle&&<h1 id="breakdown-heading">When export caps bind,<br/>were reserves under-procured?</h1>}
    <p>{formatDay(study.start)}–{formatDay(study.end)} · {count.format(c.expected)} quarter-hours</p>
    <div className="study-bar-labels"><span><strong>{count.format(c.binding)} · {percent(c.binding,c.expected)}</strong>Binding export cap</span><span><strong>{count.format(remainder)} · {percent(remainder,c.expected)}</strong>{imports?'No confirmed binding cap':'No binding export cap'}</span>
      {imports && <span><strong>{count.format(importTotal)} · {percent(importTotal,c.expected)}</strong>Binding import cap</span>}</div>
    <svg className="study-bars" viewBox="0 0 1000 130" preserveAspectRatio="none" role="img" aria-label={`${c.binding} binding export quarters out of ${c.expected}; ${c.shortfall_binding} with procurement shortfall and ${c.no_shortfall_binding} without. ${imports ? `${importTotal} binding import quarters, ${imports.shortfall} with downward shortfall and ${imports.no_shortfall} without.` : ''}`}>
      <rect x="0" y="0" width={noShort} height="40" fill={color(6)}/><rect x={noShort} y="0" width={full-noShort} height="40" fill={color(5)}/><rect className="study-nonbinding" x={full} y="0" width={importStart-full} height="40"/>
      {imports && <><rect x={importStart} y="0" width={importShort} height="40" fill={color(2)}/><rect x={importStart+importShort} y="0" width={1000-importStart-importShort} height="40" fill={color(0)}/></>}
      <path className="study-connector" d={`M0 40 L0 90 M${full} 40 L1000 90`}/>
      <rect x="0" y="90" width={zoom} height="40" fill={color(6)}/><rect x={zoom} y="90" width={1000-zoom} height="40" fill={color(5)}/>
    </svg>
    <div className="study-bar-labels"><span><strong>{count.format(c.no_shortfall_binding)} · {percent(c.no_shortfall_binding,c.binding)}</strong>No upward shortfall</span><span><strong>{count.format(c.shortfall_binding)} · {percent(c.shortfall_binding,c.binding)}</strong>Upward shortfall</span></div>
    {imports && <p className="study-import-note">Binding imports · <svg className="study-key" aria-hidden="true" viewBox="0 0 10 10"><rect width="10" height="10" fill={color(2)}/></svg> {count.format(imports.shortfall)} with downward shortfall · <svg className="study-key" aria-hidden="true" viewBox="0 0 10 10"><rect width="10" height="10" fill={color(0)}/></svg> {count.format(imports.no_shortfall)} without.
      {imports.unconfirmed>0 && <> Gray includes {count.format(imports.unconfirmed)} quarters at the import limit with an unconfirmed price effect.</>}</p>}
    <svg className="study-conclusion" viewBox="0 0 340 100" role="img" aria-label={percent(c.no_shortfall_binding,c.binding)}><text x="0" y="80" fill={color(6)}>{percent(c.no_shortfall_binding,c.binding)}</text></svg>
    <p className="study-finding">of binding export quarters had no aggregate upward procurement shortfall.</p>
    <p className="export-cap-note">Procurement sufficiency does not establish operational reserve availability or whether the cap was justified. This is the fixed investigated window; table filters do not change these counts.</p>
  </section>;
}
