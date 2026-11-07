import {contributions} from './market/contributions';
import React, {useEffect, useMemo, useRef, useState, useReducer} from 'react';
import {QueryClient, QueryClientProvider} from '@tanstack/react-query';
import {BrowserRouter, Link, Navigate, Route, Routes, useLocation, useNavigate, useParams} from 'react-router-dom';
import {useDayData, IntervalPrefetch} from './data/day-data';
import {dayFigure, zoneFeatures, selectionIds} from './map/day-figure';
import {Timeline} from './controls/timeline';
import {Plot} from './map/plot';
import {reduceRender} from './map/render-state';
import {CORE_ZONES} from './market/reference';
import {DateTimeControls} from './controls/date-time-controls';
import {reduceSelection} from './controls/state';
import type {Selection, Action} from './controls/state';
import {viewFromUrl, viewSearch} from './controls/view-url';
import {mapSelection} from './map/map-selection';
import {MapDecoration} from './map/map-decoration';
import {initialCoreCamera} from './map/initial-camera';
import type {PlotlyFigure} from './map/figure';
import {PriceLegend} from './controls/price-legend';

import {overlayModel} from './map/overlay-model';
import type {OverlayModel} from './map/overlay-model';
import type {CountryLabel} from './map/country-labels';
import type {CoreZone} from './market/reference';
import './style.css';

interface Props {id: string; day: string; min_day: string; token: string; basemap: PlotlyFigure['layout']['mapbox']['style']}
interface GraphChange {clickData?: unknown}
interface GraphProps {id: string; figure: PlotlyFigure; config: object; style: object; setProps: (change: GraphChange) => void; overlay: OverlayModel; hidden: boolean; countries: CountryLabel[]; onReference: (zone: CoreZone) => void}
const Graph = (props: GraphProps) => {
  const [render,dispatch] = useReducer(reduceRender<GraphProps>,{active:props,pending:null,busy:true});
  useEffect(()=>{dispatch({type:'request',value:props});},[props]);
  const {overlay, hidden, figure, id, config, style, setProps, countries, onReference} = render.active;
  const interactive = !render.busy && props.figure === figure;
  const complete = () => dispatch({type:'complete',figure});
  const host = useRef<HTMLDivElement>(null);
  const data = useMemo(() => structuredClone(figure.data), [figure.data]);
  // Mapbox mutates its style (including removing empty layer layouts). Keep this
  // owned layout until the actual layout input changes, or Plotly reloads the style.
  const layout = useMemo(() => structuredClone(figure.layout), [figure.layout]);
  const [error, setError] = useState<string | null>(null);
  return <div ref={host} style={style}>
    <Plot divId={id} data={data} layout={layout} config={config}
      style={{height:'100%',width:'100%'}} useResizeHandler
      onInitialized={() => {setError(null);complete();}}
      onUpdate={updated => {if (updated.data === data) {setError(null);complete();}}}
      onClick={(clickData: unknown) => {if (interactive) setProps({clickData});}}
      onError={error=>{setError(error.message);complete();}}/>
    <MapDecoration host={host} model={overlay} hidden={hidden} countries={countries} onReference={zone=>{if (interactive) onReference(zone);}}/>
    {error && <div role="alert">Map: {error}</div>}
  </div>;
};

const plotConfig = {responsive: true, displayModeBar: false, scrollZoom: true};

type HostProps = Omit<Props, 'day'> & {default_day: string};

export function CnecView(props: HostProps) {
  return <BrowserRouter><Routes>
    <Route path="/cnec/:day?" element={<RoutedCnecPage {...props}/>}/>
  </Routes></BrowserRouter>;
}

function RoutedCnecPage({default_day, ...props}: HostProps) {
  const {day} = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  let selection: Selection;
  try {
    selection = viewFromUrl(day ?? default_day, location.search);
  } catch {
    return <section role="alert">Invalid delivery day. <Link to="/cnec" replace>Open the current day</Link>.</section>;
  }
  if (selection.day < props.min_day) return <Navigate to="/cnec" replace/>;
  const onAction = (action: Action) => {
    const next = reduceSelection(selection, action);
    if (next === selection) return;
    navigate({pathname: `/cnec/${next.day}`, search: viewSearch(next, location.search), hash: location.hash},
      {replace: true});
  };
  return <CnecPage {...props} selection={selection} onAction={onAction}/>;
}

/** React page; the host owns routing and supplies the delivery-day navigation action. */
type PageProps = Omit<Props, 'day'> & {selection: Selection; onAction: (action: Action) => void};
export function CnecPage(props: PageProps) {
  const [client] = useState(() => new QueryClient({defaultOptions: {queries: {
    retry: false, staleTime: 300_000, refetchOnWindowFocus: false, refetchOnReconnect: false, refetchOnMount: false,
  }}}));
  // Mapbox requires absolute sprite URLs, including for same-origin assets.
  const basemap = useMemo(() => props.basemap !== null && typeof props.basemap === 'object' && 'sprite' in props.basemap && typeof props.basemap.sprite === 'string'
    ? {...props.basemap, sprite: new URL(props.basemap.sprite, window.location.href).href} : props.basemap, [props.basemap]);
  return <QueryClientProvider client={client}><View {...props} basemap={basemap}/></QueryClientProvider>;
}

function shell(token: string, basemap: Props['basemap'], camera: ReturnType<typeof initialCoreCamera>): PlotlyFigure {
  return {data: [{type: 'scattermapbox', mode: 'lines', lon: [], lat: []}], layout: {
    mapbox: {style: basemap, accesstoken: token, ...camera},
    clickanywhere: true, uirevision: 'cnec-camera', margin: {t: 0, b: 0, l: 0, r: 0}, showlegend: false,
    paper_bgcolor: '#1b1b1b',
  }};
}

function View({id, min_day, token, basemap, selection, onAction: dispatch}: PageProps) {
  const {day, interval, selected, reference} = selection;


  const [initialCamera] = useState(() => initialCoreCamera(window.innerWidth, window.innerHeight));
  const {publication,metadata,current: intervalQuery,data,labels,generation} = useDayData(day,interval);
  const validInterval = !!metadata.data && interval >= 0 && interval < labels.length;
  const mapCurrent = validInterval && data?.index === interval && !intervalQuery.isPlaceholderData;
  const geography = useMemo(() => metadata.data ? zoneFeatures(metadata.data) : null,[metadata.data]);
  const countries = useMemo(() => (metadata.data?.zones ?? []).flatMap(zone => {
    const price = data?.prices[zone.zone];
    return price === undefined ? [] : [{zone:zone.zone,name:zone.name,centre:zone.centre,price}];
  }),[metadata.data,data]);
  const emptyFigure = useMemo(() => shell(token,basemap,initialCamera),[token,basemap,initialCamera]);
  const graphFigure = useMemo(() => metadata.data && data && geography
    ? dayFigure({...metadata.data,intervals:[data]},data.index,mapCurrent ? selected : null,reference,emptyFigure.layout,geography)
    : emptyFigure,[metadata.data,data,geography,mapCurrent,selected,reference,emptyFigure]);
  const current = mapCurrent ? data : null;
  const options = current ? selectionIds(current) : [];
  const notes = [...(current?.notes ?? [])];
  if (current && selected !== null && current.constraints.some(r => r.eic === selected) &&
      contributions(current, selected, reference) === null)
    notes.push('Contribution unavailable: missing FB scaling factor or country sensitivities.');
  if (current && selected !== null && !options.includes(selected))
    notes.push(`Selected element ${selected} is not binding in this interval.`);
  function mapClick(change: GraphChange) {
    const action = mapSelection(change.clickData, options, selected, mapCurrent);
    if (action) dispatch(action);
  }

  return <section id={id} className="cnec-react">
    <IntervalPrefetch day={day} generation={generation} count={labels.length} enabled={!!data && !!metadata.data}/>
    <div className="cnec-map-container">
      <Graph id={`${id}-map`} figure={graphFigure} setProps={mapClick} overlay={overlayModel(graphFigure)} hidden={!mapCurrent}
        countries={countries} onReference={reference=>dispatch({type:'reference',reference})}
        config={plotConfig} style={{height: '100%'}}/>
      <small className="cnec-sources">
        Data: <a href="https://publicationtool.jao.eu/core/" target="_blank" rel="noopener noreferrer">JAO</a> · {' '}
        <a href="https://www.electricitymaps.com/" target="_blank" rel="noopener noreferrer">Electricity Maps</a> · {' '}
        <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">© OpenStreetMap contributors</a>
      </small>
      <div className="cnec-map-tools">
        <PriceLegend figure={graphFigure}/>
        <label className="cnec-reference cnec-panel">Reference
          <select aria-label="Reference country" value={reference}
            onChange={e => dispatch({type: 'reference', reference: CORE_ZONES.find(zone => zone === e.target.value)!})}>
            {CORE_ZONES.map(zone => <option key={zone} value={zone}>{zone}</option>)}
          </select>
        </label>
      </div>

      <aside className="cnec-progress" aria-live="polite">
        {metadata.data && !validInterval && <div role="alert">This interval is outside the selected day.{' '}
          <button onClick={() => {dispatch({type:'interval',interval:0});}}>Go to first interval</button>
        </div>}
        {(publication.isFetching || metadata.isFetching || (!mapCurrent && intervalQuery.isFetching)) && <div role="status" aria-label="Map loading">Loading interval…{data && !mapCurrent && <div>Showing {data.label.split(' · ')[1]}.</div>}</div>}
        {publication.isSuccess && !publication.data && <div role="status">This day has not been prepared yet. Checking automatically every minute. <button onClick={() => void publication.refetch()}>Check again</button></div>}
        {notes.map(note => <div role="status" key={note}>{note}</div>)}
        {([['Publication',publication],['Metadata',metadata],['Interval',intervalQuery]] as const).map(([name,query])=>query.error && <div role="alert" key={name}>{name}: {query.error.message}{data && !mapCurrent && ` Showing ${data.label.split(' · ')[1]}.`} <button onClick={()=>void query.refetch()}>Retry</button></div>)}
      </aside>
    <div className="cnec-time-controls">
      <DateTimeControls day={day} minDay={min_day} time={labels[interval]?.split(' · ')[1] ?? ''}
        previousDisabled={!labels.length || interval === 0}
        nextDisabled={!labels.length || interval === labels.length - 1}
        onDay={day => dispatch({type: 'day', day})} onPrevious={() => dispatch({type: 'interval', interval: interval - 1})}
        onNext={() => dispatch({type: 'interval', interval: interval + 1})}/>
      <div className="cnec-slider-panel cnec-panel">
      <Timeline labels={labels} interval={interval} disabled={!labels.length}
        onChange={interval => dispatch({type: 'interval', interval})}/>
      </div>
    </div>
    </div>
  </section>;
}
