import React, {useEffect, useMemo, useReducer, useState} from 'react';
import {useQuery} from '@tanstack/react-query';
import {Plot} from '../map/plot';
import {reduceRender} from '../map/render-state';
import type {PlotlyFigure} from '../map/figure';
import {fetchManifest,fetchHour,defaultHour,timeLabel,fullLabel} from './data';

const config = {responsive:true,displayModeBar:false,scrollZoom:true};
const ignoreClick = () => {};
function HourMap({figure,onError}:{figure:PlotlyFigure;onError:(error:Error)=>void}) {
  const [state,dispatch] = useReducer(reduceRender<{figure:PlotlyFigure}>,{active:{figure},pending:null,busy:true});
  useEffect(()=>{dispatch({type:'request',value:{figure}});},[figure]);
  const active = state.active.figure;
  const data = useMemo(()=>structuredClone(active.data),[active]);
  const layout = useMemo(()=>structuredClone(active.layout),[active]);
  return <Plot id="opf-map" data={data} layout={layout} config={config} onClick={ignoreClick}
    onRendered={()=>dispatch({type:'complete',figure:active})}
    onError={error=>{onError(error);dispatch({type:'complete',figure:active});}}/>;
}
export function OpfView({token}:{token:string}) {
  const manifest = useQuery({queryKey:['opf-manifest'],queryFn:({signal})=>fetchManifest(signal)});
  const times = manifest.data?.snapshots ?? [];
  const [selection,setSelection] = useState<number|null>(null);
  const selected = selection ?? (times.length ? defaultHour(times) : 0);
  const generation = manifest.data?.generation;
  const hour = useQuery({queryKey:['opf-hour',generation,selected],enabled:!!generation,
    queryFn:({signal})=>fetchHour(generation!,selected,signal),placeholderData:previous=>previous});
  const [mapError,setMapError] = useState<string|null>(null);
  const figure = useMemo(()=>hour.data ? {...hour.data,layout:{...hour.data.layout,uirevision:'opf-2024',
    mapbox:{...hour.data.layout.mapbox,accesstoken:token}}} : null,[hour.data,token]);
  const error = manifest.error ?? hour.error;
  return <section className="opf-static" aria-label="Power Flow">
    <div className="opf-map-host">{figure && <HourMap figure={figure} onError={e=>setMapError(e.message)}/>}
      {(manifest.isFetching || hour.isFetching) && <div className="opf-notice" role="status">Loading Power Flow…</div>}
      {error && <div className="opf-notice" role="alert">{error.message} <button onClick={()=>void (manifest.error?manifest:hour).refetch()}>Retry</button></div>}
      {mapError && <div className="opf-notice" role="alert">Map: {mapError}</div>}
    </div>
    {times.length>0 && <div className="opf-controls">
      <output>{fullLabel.format(new Date(times[selected]))}{hour.isPlaceholderData && ' · loading selected hour'}</output>
      <input aria-label="Power Flow hour" type="range" min={0} max={times.length-1} step={1} value={selected}
        onChange={event=>{setMapError(null);setSelection(Number(event.target.value));}}/>
      <div className="opf-marks">{times.map((time,index)=>index%4===0 || index===times.length-1 ? <span key={time}>{timeLabel.format(new Date(time))}</span>:null)}</div>
    </div>}
  </section>;
}
