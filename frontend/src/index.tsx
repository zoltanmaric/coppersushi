import React, {useEffect, useMemo, useRef, useState} from 'react';
import {QueryClient, QueryClientProvider, useQuery, useQueryClient} from '@tanstack/react-query';
import {BrowserRouter, Link, Navigate, Route, Routes, useLocation, useNavigate, useParams} from 'react-router-dom';
import {fetchBundle, fetchManifest} from './api';
import {dayFigure, zoneFeatures, optionsFor, contributions} from './day-figure';
import {Timeline} from './timeline';
import {Plot} from './plot';
import {CORE_ZONES} from './reference';
import {DateTimeControls} from './date-time-controls';
import {reduceSelection} from './state';
import type {Selection, Action} from './state';
import {viewFromUrl, viewSearch} from './view-url';
import {mapSelection} from './map-selection';
import {MapDecoration} from './map-decoration';
import {initialCoreCamera} from './initial-camera';
import type {PlotlyFigure} from './contracts';
import {PriceLegend} from './price-legend';

import {overlayModel} from './overlay-model';
import type {OverlayModel} from './overlay-model';
import './style.css';

interface Props {id: string; day: string; min_day: string; token: string; basemap: PlotlyFigure['layout']['mapbox']['style']}
interface GraphChange {clickData?: unknown}
interface GraphProps {id: string; figure: PlotlyFigure; config: object; style: object; setProps: (change: GraphChange) => void; overlay: OverlayModel; hidden: boolean}
const Graph = ({overlay, hidden, figure, id, config, style, setProps}: GraphProps) => {
  const host = useRef<HTMLDivElement>(null);
  const drawing = useMemo(() => structuredClone(figure), [figure]);
  const [error, setError] = useState<string | null>(null);
  return <div ref={host} style={style}>
    <Plot divId={id} data={drawing.data} layout={drawing.layout} config={config}
      style={{height:'100%',width:'100%'}} useResizeHandler
      onAfterPlot={() => setError(null)} onClick={(clickData: unknown) => setProps({clickData})} onError={error=>setError(error.message)}/>
    <MapDecoration host={host} model={overlay} hidden={hidden}/>
    {error && <div role="alert">Map: {error}</div>}
  </div>;
};

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
  const client = useQueryClient();


  const [initialCamera] = useState(() => initialCoreCamera(window.innerWidth, window.innerHeight));
  const [initial, setInitial] = useState({day, interval});
  const initialInterval = initial.day === day ? initial.interval : interval;
  useEffect(() => {if (initial.day !== day) setInitial({day, interval});}, [day, interval, initial.day]);
  const publication = useQuery({queryKey: ['publication', day], queryFn: ({signal}) => fetchManifest(day, signal)});
  const generation = publication.data?.generation ?? null;
  const first = useQuery({queryKey: ['interval', day, generation, initialInterval],
    queryFn: ({signal}) => fetchBundle(day, initialInterval, publication.data ?? null, signal),
    enabled: publication.isSuccess && !client.getQueryData(['bundle', day, generation])});
  const wholeDay = useQuery({queryKey: ['bundle', day, generation], enabled: first.isSuccess,
    queryFn: ({signal}) => fetchBundle(day, null, publication.data ?? null, signal)});
  const bundle = wholeDay.data ? wholeDay : first;
  const labels = bundle.data?.labels ?? [];
  const validInterval = !!bundle.data && interval < labels.length && bundle.data.intervals.some(i=>i.index===interval);
  const geography = useMemo(() => bundle.data ? zoneFeatures(bundle.data) : null, [bundle.data]);
  const emptyFigure = useMemo(() => shell(token, basemap, initialCamera), [token, basemap, initialCamera]);
  const displayInterval = validInterval ? interval : initialInterval;
  const graphFigure = useMemo(() => bundle.data && geography && bundle.data.intervals.length > 0
    ? dayFigure(bundle.data, displayInterval, validInterval ? selected : null, reference, emptyFigure.layout, geography) : emptyFigure,
    [bundle.data, validInterval, geography, displayInterval, selected, reference, emptyFigure]);
  const mapCurrent = validInterval;
  const current = validInterval ? bundle.data!.intervals.find(i=>i.index===interval)! : null;
  const options = current ? optionsFor(current) : [];
  useEffect(() => {
    if (current && selected !== null && !options.some(o => o.value === String(selected)))
      dispatch({type: 'select', selected: null, source: 'constraints'});
  }, [current, selected]);
  const notes = [...(current?.notes ?? [])];
  if (current && selected !== null && current.constraints.some(r => r.source_id === selected) &&
      contributions(current, selected, reference) === null)
    notes.push('Contribution unavailable: missing or zero FB scaling factor α.');
  function mapClick(change: GraphChange) {
    const action = mapSelection(change.clickData, options, selected, mapCurrent);
    if (action) dispatch(action);
  }

  return <section id={id} className="cnec-react">
    <div className="cnec-map-container">
      <Graph id={`${id}-map`} figure={graphFigure} setProps={mapClick} overlay={overlayModel(graphFigure)} hidden={!mapCurrent}
        config={{responsive: true, displayModeBar: false, scrollZoom: true}} style={{height: '100%'}}/>
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
        {bundle.data && interval >= labels.length && <div role="alert">This interval is outside the selected day.{' '}
          <button onClick={() => dispatch({type: 'interval', interval: 0})}>Go to first interval</button>
        </div>}
        {(!bundle.data || !validInterval) && (publication.isFetching || first.isFetching || wholeDay.isFetching) && <div role="status" aria-label="Map loading">Loading day…{bundle.data && !validInterval && <div>Showing {labels[displayInterval]?.split(' · ')[1]}.</div>}</div>}
        {publication.error && <div role="alert">Publication: {publication.error.message} <button onClick={() => void publication.refetch()}>Retry</button></div>}
        {wholeDay.error && <div role="alert">Remaining intervals: {wholeDay.error.message}{!validInterval && ` Showing ${labels[displayInterval]?.split(' · ')[1]}.`} <button onClick={() => void wholeDay.refetch()}>Retry</button></div>}
        {notes.map(note => <div role="status" key={note}>{note}</div>)}
        {bundle.error && <div role="alert">Day: {bundle.error.message} <button onClick={() => {setInitial({day, interval: 0}); dispatch({type: 'interval', interval: 0});}}>Go to first interval</button> <button onClick={() => void bundle.refetch()}>Retry</button></div>}
      </aside>
    <div className="cnec-time-controls">
      <DateTimeControls day={day} minDay={min_day} time={labels[interval]?.split(' · ')[1] ?? ''}
        previousDisabled={!labels.length || interval === 0}
        nextDisabled={!labels.length || interval === labels.length - 1}
        onDay={day => dispatch({type: 'day', day})} onPrevious={() => dispatch({type: 'interval', interval: interval - 1})}
        onNext={() => dispatch({type: 'interval', interval: interval + 1})}/>
      <div className="cnec-slider-panel cnec-panel">
      <Timeline labels={labels} interval={interval} disabled={!labels.length}
        onScrubbingChange={() => {}} onChange={interval => dispatch({type: 'interval', interval})}/>
      </div>
    </div>
    </div>
  </section>;
}
