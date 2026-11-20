import React,{memo,useCallback,useLayoutEffect,useMemo,useRef} from 'react';
import {BrowserRouter,useLocation,useNavigate} from 'react-router-dom';
import {CnecPage,type PageProps} from '../cnec';
import {reduceSelection,type Action} from '../../controls/state';
import type {MapCamera} from '../../map/camera';
import {intervalLabel,shortfall,type Investigation as Study} from './data';
import {columns,readState,writeState,sortRows,filterRows,valueOf,type ViewState} from './state';
import {NumericFilter} from './column-filter';
import {DateRange} from './date-range';
import {Breakdown} from './breakdown';
import {Sources} from './sources';
import './style.css';

type Props=Pick<PageProps,'min_day'|'token'|'basemap'> & {study:Study};
const NativeMap=memo(CnecPage);
const number=new Intl.NumberFormat('en-GB',{maximumFractionDigits:2});

export function ExportCapView(props:Props){return <BrowserRouter><RoutedPage {...props}/></BrowserRouter>;}
function RoutedPage(props:Props){
  const location=useLocation();
  const first=useMemo(()=>sortRows(props.study.rows,'shadow','desc')[0],[props.study]);
  let state:ViewState;
  try {state=readState(location.search,first);}catch(error){
    return <section className="export-cap-page" role="alert">{String(error)}. <a href={location.pathname}>Reset view</a></section>;
  }
  return <Investigation {...props} state={state}/>;
}
function Investigation({study,state,...config}:Props & {state:ViewState}){
  const navigate=useNavigate(),location=useLocation(),latest=useRef(state);
  useLayoutEffect(()=>{latest.current=state;});
  const change=useCallback((next:ViewState)=>{navigate({search:writeState(next)},{replace:true});},[navigate]);
  const onAction=useCallback((action:Action)=>{
    const state=latest.current;change({...state,selection:reduceSelection(state.selection,action)});
  },[change]);
  const onCamera=useCallback((camera:MapCamera)=>{change({...latest.current,camera});},[change]);
  const {day,interval,selected,reference}=state.selection;
  const selection=useMemo(()=>({day,interval,selected,reference}),[day,interval,selected,reference]);
  const camera=useMemo(()=>state.camera,[state.camera?.lat,state.camera?.lon,state.camera?.zoom]);
  const rows=useMemo(()=>sortRows(filterRows(study.rows,state),state.sort,state.order),[study,state.from,state.to,state.filters,state.sort,state.order]);
  const active=study.rows.find(row=>row.date===day&&row.index===interval);
  const embed=document.body.dataset.embed === 'true';
  return <article className={`export-cap-page${embed?' intervals-embed':''}`}>
    {!embed&&<><Breakdown study={study}/><Sources study={study}/></>}
    <div className="study-explorer">
    <section className="study-map-section" aria-label="Critical Elements ⚡️">
      <div className="export-cap-map"><NativeMap {...config} id="polish-cap-map" selection={selection} onAction={onAction} camera={camera} onCamera={onCamera} generation={study.generations[day]}/></div>
    </section>
    <section className="study-table-section" aria-label="Binding intervals">
      <p className="export-cap-note" role="status">{rows.length < study.rows.length && `${number.format(rows.length)} of `}{number.format(study.rows.length)} binding intervals{active && !rows.includes(active) && '. The selected interval on the map is outside these filters.'}</p>
        <div className="export-cap-table" tabIndex={0} aria-label="Binding intervals; scroll horizontally for all columns"><table>
          <thead><tr>{columns.map(c=><th key={c.key} scope="col" aria-sort={state.sort===c.key?(state.order==='asc'?'ascending':'descending'):'none'}>
            <div className="study-column-heading"><button type="button" onClick={()=>change({...state,sort:c.key,order:state.sort===c.key&&state.order==='desc'?'asc':'desc'})}>{c.label}<span>{c.unit}{state.sort===c.key?(state.order==='desc'?' ↓':' ↑'):''}</span></button>
            {c.key==='utc'
              ? <DateRange from={state.from} to={state.to} start={study.start} end={study.end} onChange={(from,to)=>change({...state,from,to})}/>
              : <NumericFilter label={c.label} column={c.key} range={state.filters[c.key]} onChange={range=>{
                const filters={...state.filters};
                if(range)filters[c.key]=range;else delete filters[c.key];
                change({...state,filters});
              }}/>}
            </div>
          </th>)}</tr></thead>
          <tbody>{rows.map(row=>{
            const next={...state,selection:{...selection,day:row.date,interval:row.index,selected:'cap:PL'}};
            return <tr key={row.utc} className={row===active?'selected-interval':undefined}>{columns.map(c=><td key={c.key} className={c.key==='shortfall'&&shortfall(row)>0?'has-shortfall':undefined}>
              {c.key==='utc'?<a href={`${location.pathname}${writeState(next)}`} aria-current={row===active?'true':undefined} onClick={event=>{
                if(event.button!==0||event.metaKey||event.ctrlKey||event.shiftKey||event.altKey)return;
                event.preventDefault();change(next);
              }}>{intervalLabel(row.utc)}</a>:number.format(valueOf(row,c.key))}
            </td>)}</tr>;
          })}</tbody></table></div>
      <p className="export-cap-note">Required and procured figures are aggregate upward capacity, in MW. Shortfall is required − procured. Procurement sufficiency does not establish operational reserve availability or whether the cap was justified.</p>
    </section>
    </div>
    {embed&&<Sources study={study}/>}
  </article>;
}
