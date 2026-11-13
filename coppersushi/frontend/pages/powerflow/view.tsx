import {initialBoundsCamera} from '../../map/initial-camera';
import {MapControls} from '../../controls/map-controls';
import React, {useEffect, useLayoutEffect, useMemo, useReducer, useState, useRef} from 'react';
import {useQuery} from '@tanstack/react-query';
import {Plot} from '../../map/plot';
import {reduceRender} from '../../map/render-state';
import type {PlotlyFigure} from '../../map/figure';
import {ScaleLegend} from '../../controls/price-legend';
import {MapHelp} from '../../controls/map-help';
import {IntervalControls} from '../../controls/interval-controls';
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
  const [selection,setSelection] = useState<number|null>(()=>{const raw=new URLSearchParams(window.location.search).get('hour');return raw!==null && /^\d+$/.test(raw) ? Number(raw) : null;});
  const selected = selection!==null && selection<times.length ? selection : (times.length ? defaultHour(times) : 0);
  useEffect(()=>{if(times.length){const url=new URL(window.location.href);url.searchParams.set('hour',String(selected));window.history.replaceState(null,'',url);}},[selected,times.length]);
  const generation = manifest.data?.generation;
  const hour = useQuery({queryKey:['opf-hour',generation,selected],enabled:!!generation,
    queryFn:({signal})=>fetchHour(generation!,selected,signal),placeholderData:previous=>previous});
  const viewport = useRef<HTMLElement>(null);
  const [viewportSize,setViewportSize] = useState<{width:number;height:number}|null>(null);
  useLayoutEffect(()=>{const rect=viewport.current!.getBoundingClientRect();setViewportSize({width:rect.width,height:rect.height});},[]);
  const initialCamera = useRef<ReturnType<typeof initialBoundsCamera> | null>(null);
  if (hour.data && viewportSize && !initialCamera.current) {
    const size = viewportSize;
    initialCamera.current = initialBoundsCamera(hour.data.bounds, size.width, size.height, 60);
  }
  const [renderedFigure,setRenderedFigure] = useState<PlotlyFigure|null>(null);
  const [mapError,setMapError] = useState<string|null>(null);
  const figure = useMemo(()=>hour.data && initialCamera.current ? {...hour.data,layout:{...hour.data.layout,uirevision:'opf-2024',
    mapbox:{...hour.data.layout.mapbox,...initialCamera.current,accesstoken:token}}} : null,[hour.data,token,viewportSize]);
  const error = manifest.error ?? hour.error;
  const current = !!figure && !hour.isPlaceholderData && renderedFigure===figure;
  const loading = !error && !mapError && (manifest.isFetching || hour.isFetching || (!!figure && !current));
  return <section ref={viewport} className="opf-static" aria-label="Power Flow 🍣">
    <div className="opf-map-host">{figure && <HourMap figure={figure} onError={e=>setMapError(e.message)} onRendered={completed=>{setRenderedFigure(completed);setMapError(null);}}/>}
      {loading && <div className="opf-notice" role="status">Loading Power Flow…</div>}
      {error && <div className="opf-notice" role="alert">{error.message} <button onClick={()=>void (manifest.error?manifest:hour).refetch()}>Retry</button></div>}
      {mapError && <div className="opf-notice" role="alert">Map: {mapError}</div>}
    </div>
    <MapControls legend={<ScaleLegend reversed saturated title="Net power feed-in · MW" description="Node net power scale" range={hour.data?.scale ? [-hour.data.scale,hour.data.scale] : null}/>} help={<MapHelp page="powerflow"/>} controls={times.length ?       <IntervalControls date={<span className="opf-fixed-date">{times.length ? new Intl.DateTimeFormat('en-GB',{timeZone:'Europe/Brussels',day:'numeric',month:'short',year:'numeric'}).format(new Date(times[0])) : ''}</span>} labels={times.map(time=>fullLabel.format(new Date(time)).split(', ').at(-1)!)} interval={selected} onChange={value=>{setMapError(null);setSelection(value);}}/> : null}/>

  </section>;
}
