import {initialBoundsCamera} from '../../map/initial-camera';
import {MapControls} from '../../controls/map-controls';
import React, {useEffect, useMemo, useState, useRef} from 'react';
import {useQuery} from '@tanstack/react-query';
import {MapGraph} from '../../map/map-graph';
import {MapFrame,useMapViewport} from '../../map/map-frame';
import type {PlotlyFigure} from '../../map/figure';
import {ScaleLegend} from '../../controls/price-legend';
import {MapHelp} from '../../controls/map-help';
import {IntervalControls} from '../../controls/interval-controls';
import {fetchManifest,fetchHour,defaultHour,fullLabel} from './data';

const config = {responsive:true,displayModeBar:false,scrollZoom:true};
export function OpfView({token}:{token:string}) {
  const manifest = useQuery({queryKey:['opf-manifest'],queryFn:({signal})=>fetchManifest(signal)});
  const times = manifest.data?.snapshots ?? [];
  const [selection,setSelection] = useState<number|null>(()=>{const raw=new URLSearchParams(window.location.search).get('hour');return raw!==null && /^\d+$/.test(raw) ? Number(raw) : null;});
  const selected = selection!==null && selection<times.length ? selection : (times.length ? defaultHour(times) : 0);
  useEffect(()=>{if(times.length){const url=new URL(window.location.href);url.searchParams.set('hour',String(selected));window.history.replaceState(null,'',url);}},[selected,times.length]);
  const generation = manifest.data?.generation;
  const hour = useQuery({queryKey:['opf-hour',generation,selected],enabled:!!generation,
    queryFn:({signal})=>fetchHour(generation!,selected,signal),placeholderData:previous=>previous});
  const viewport = useMapViewport();
  const initialCamera = useRef<ReturnType<typeof initialBoundsCamera> | null>(null);
  if (hour.data && viewport.size && !initialCamera.current) {
    const size = viewport.size;
    initialCamera.current = initialBoundsCamera(hour.data.bounds, size.width, size.height, 60);
  }
  const [renderedFigure,setRenderedFigure] = useState<PlotlyFigure|null>(null);
  const [mapError,setMapError] = useState<string|null>(null);
  const figure = useMemo(()=>hour.data && initialCamera.current ? {...hour.data,layout:{...hour.data.layout,uirevision:'opf-2024',
    mapbox:{...hour.data.layout.mapbox,...initialCamera.current,accesstoken:token}}} : null,[hour.data,token,viewport.size]);
  const error = manifest.error ?? hour.error;
  const current = !!figure && !hour.isPlaceholderData && renderedFigure===figure;
  const loading = !error && !mapError && (manifest.isFetching || hour.isFetching || (!!figure && !current));
  return <MapFrame ref={viewport.ref} label="Power Flow 🍣">
    <div className="map-canvas">{figure && <MapGraph id="opf-map" config={config} figure={figure} onError={e=>setMapError(e?.message ?? null)} onRendered={completed=>{setRenderedFigure(completed);setMapError(null);}}/>}

    </div>
    <MapControls loading={loading} status={<>
      {error && <div role="alert">{error.message} <button onClick={()=>void (manifest.error?manifest:hour).refetch()}>Retry</button></div>}
      {mapError && <div role="alert">Map: {mapError}</div>}
</>} legend={<ScaleLegend reversed saturated title="Net power feed-in · MW" description="Node net power scale" range={hour.data?.scale ? [-hour.data.scale,hour.data.scale] : null}/>} help={<MapHelp page="powerflow"/>} controls={times.length ?       <IntervalControls date={<div className="cnec-control-row"><span className="opf-fixed-date">{times.length ? new Intl.DateTimeFormat('en-GB',{timeZone:'Europe/Brussels',day:'numeric',month:'short',year:'numeric'}).format(new Date(times[0])) : ''}</span></div>} labels={times.map(time=>fullLabel.format(new Date(time)).split(', ').at(-1)!)} interval={selected} onChange={value=>{setMapError(null);setSelection(value);}}/> : null}/>

  </MapFrame>;
}
