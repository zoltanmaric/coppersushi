import React, {useEffect, useMemo, useReducer, useState} from 'react';
import {useQuery} from '@tanstack/react-query';
import {Plot} from '../map/plot';
import {reduceRender} from '../map/render-state';
import type {PlotlyFigure} from '../map/figure';
import {MapHelp} from '../controls/map-help';
import {IntervalControls} from '../controls/interval-controls';
import {fetchManifest,fetchHour,defaultHour,fullLabel} from './data';

const config = {responsive:true,displayModeBar:false,scrollZoom:true};
const ignoreClick = () => {};
function HourMap({figure,onError,onRendered}:{figure:PlotlyFigure;onError:(error:Error)=>void;onRendered:(figure:PlotlyFigure)=>void}) {
  const [state,dispatch] = useReducer(reduceRender<{figure:PlotlyFigure}>,{active:{figure},pending:null,busy:true});
  useEffect(()=>{dispatch({type:'request',value:{figure}});},[figure]);
  const active = state.active.figure;
  const data = useMemo(()=>structuredClone(active.data),[active]);
  const layout = useMemo(()=>structuredClone(active.layout),[active]);
  return <Plot id="opf-map" data={data} layout={layout} config={config} onClick={ignoreClick}
    onRendered={()=>{onRendered(active);dispatch({type:'complete',figure:active});}}
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
  const [renderedFigure,setRenderedFigure] = useState<PlotlyFigure|null>(null);
  const [mapError,setMapError] = useState<string|null>(null);
  const figure = useMemo(()=>hour.data ? {...hour.data,layout:{...hour.data.layout,uirevision:'opf-2024',
    mapbox:{...hour.data.layout.mapbox,accesstoken:token}}} : null,[hour.data,token]);
  const error = manifest.error ?? hour.error;
  const current = !!figure && !hour.isPlaceholderData && renderedFigure===figure;
  const loading = !error && !mapError && (manifest.isFetching || hour.isFetching || (!!figure && !current));
  return <section className="opf-static" aria-label="Power Flow">
    <div className="opf-map-host"><div className="cnec-map-tools"><MapHelp page="powerflow"/></div>{figure && <HourMap figure={figure} onError={e=>setMapError(e.message)} onRendered={completed=>{setRenderedFigure(completed);setMapError(null);}}/>}
      {loading && <div className="opf-notice" role="status">Loading Power Flow…</div>}
      {error && <div className="opf-notice" role="alert">{error.message} <button onClick={()=>void (manifest.error?manifest:hour).refetch()}>Retry</button></div>}
      {mapError && <div className="opf-notice" role="alert">Map: {mapError}</div>}
    </div>
    {times.length>0 && <div className="opf-controls">
      <IntervalControls date={<span>29 Aug 2024</span>} labels={times.map(time=>fullLabel.format(new Date(time)))} interval={selected} onChange={value=>{setMapError(null);setSelection(value);}}/>
      {!current && !error && <span role="status">loading selected hour</span>}
    </div>}
  </section>;
}
