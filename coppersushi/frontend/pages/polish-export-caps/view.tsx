import React,{memo,useCallback,useLayoutEffect,useMemo,useRef,useState} from 'react';
import {BrowserRouter,useLocation,useNavigate} from 'react-router-dom';
import {CnecPage,type PageProps} from '../cnec';
import {reduceSelection,type Action} from '../../controls/state';
import type {MapCamera} from '../../map/camera';
import {intervalLabel,shortfall,type Investigation as Study} from './data';
import {columns,readState,writeState,sortRows,filterRows,valueOf,type ViewState,type NumericFilters} from './state';
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
  const [filterError,setFilterError]=useState<string|null>(null);
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
  const embed=location.pathname.startsWith('/embed/');
  function applyFilters(event:React.FormEvent<HTMLFormElement>){
    event.preventDefault();const form=new FormData(event.currentTarget),filters:NumericFilters={};
    for(const c of columns){
      if(c.key==='utc')continue;
      const range:{min?:number;max?:number}={};
      for(const bound of ['min','max'] as const){const raw=String(form.get(`${c.key}-${bound}`)??'');if(raw!=='')range[bound]=Number(raw);}
      if((range.min!==undefined&&!Number.isFinite(range.min))||(range.max!==undefined&&!Number.isFinite(range.max))||
         (range.min!==undefined&&range.max!==undefined&&range.min>range.max)){
        setFilterError(`Enter a valid minimum and maximum for ${c.label}.`);return;
      }
      if(range.min!==undefined||range.max!==undefined)filters[c.key]=range;
    }
    setFilterError(null);change({...state,filters});
  }
  return <article className={`export-cap-page${embed?' intervals-embed':''}`}>
    {!embed&&<><Breakdown study={study}/><Sources study={study}/></>}
    <div className="study-explorer">
    <section className="study-map-section" aria-labelledby="export-map-heading"><div className="export-cap-heading"><h2 id="export-map-heading">Critical Elements ⚡️</h2><a href={`${location.pathname}${writeState(state)}`}>Permalink</a></div>
      <p className="export-cap-selected">{active?intervalLabel(active.utc):`${day} · interval ${interval} · no binding row in this study`}
        {active&&!rows.includes(active)&&' · selected interval is outside the table filters'}</p>
      <div className="export-cap-map"><NativeMap {...config} id="polish-cap-map" selection={selection} onAction={onAction} camera={camera} onCamera={onCamera} generation={study.generations[day]}/></div>
    </section>
    <section className="study-table-section" aria-labelledby="binding-heading"><div className="export-cap-heading"><h2 id="binding-heading">Binding intervals</h2></div>

      <p className="export-cap-note">Select a timestamp to update the map.</p>
      <DateRange from={state.from} to={state.to} start={study.start} end={study.end} onChange={(from,to)=>change({...state,from,to})}/>
      <form key={JSON.stringify(state.filters)} onSubmit={applyFilters}>
        <div className="study-table-toolbar"><p role="status">{number.format(rows.length)} of {number.format(study.rows.length)} binding intervals</p>
          <div><button type="submit">Apply numeric filters</button><button type="button" onClick={()=>{setFilterError(null);change({...state,filters:{},from:undefined,to:undefined,sort:'shadow',order:'desc'});}}>Reset table</button></div>
        </div>
        {filterError&&<p role="alert">{filterError}</p>}
        <div className="export-cap-table" tabIndex={0} aria-label="Binding intervals; scroll horizontally for all columns"><table>
          <thead><tr>{columns.map(c=><th key={c.key} scope="col" aria-sort={state.sort===c.key?(state.order==='asc'?'ascending':'descending'):'none'}>
            <button type="button" onClick={()=>change({...state,sort:c.key,order:state.sort===c.key&&state.order==='desc'?'asc':'desc'})}>{c.label}<span>{c.unit}{state.sort===c.key?(state.order==='desc'?' ↓':' ↑'):''}</span></button>
          </th>)}</tr><tr className="study-column-filters">{columns.map(c=><td key={c.key}>{c.key==='utc'?<small>Inclusive date range above</small>:<div>{(['min','max'] as const).map(bound=><input
            key={bound} type="number" step="any" name={`${c.key}-${bound}`} aria-label={`${c.label} ${bound==='min'?'minimum':'maximum'}`} placeholder={bound==='min'?'Min':'Max'} defaultValue={state.filters[c.key]?.[bound]??''}/>)}</div>}</td>)}</tr></thead>
          <tbody>{rows.map(row=>{
            const next={...state,selection:{...selection,day:row.date,interval:row.index,selected:'cap:PL'}};
            return <tr key={row.utc} className={row===active?'selected-interval':undefined}>{columns.map(c=><td key={c.key} className={c.key==='shortfall'&&shortfall(row)>0?'has-shortfall':undefined}>
              {c.key==='utc'?<a href={`${location.pathname}${writeState(next)}`} aria-current={row===active?'true':undefined} onClick={event=>{
                if(event.button!==0||event.metaKey||event.ctrlKey||event.shiftKey||event.altKey)return;
                event.preventDefault();change(next);
              }}>{intervalLabel(row.utc)}</a>:number.format(valueOf(row,c.key))}
            </td>)}</tr>;
          })}</tbody></table></div>
      </form>
      {rows.length===0&&<p role="status">No binding intervals match these filters.</p>}
      <p className="export-cap-note">Required and procured figures are aggregate upward capacity, in MW. Shortfall is required − procured; negative values mean procurement above the requirement. Procurement sufficiency does not establish operational reserve availability or whether the cap was justified.</p>
    </section>
    </div>
    {embed&&<Sources study={study}/>}
  </article>;
}
