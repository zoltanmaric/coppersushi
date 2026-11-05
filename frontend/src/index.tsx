import React, {useCallback, useEffect, useLayoutEffect, useMemo, useReducer, useRef, useState} from 'react';
import {QueryClient, QueryClientProvider, useQuery} from '@tanstack/react-query';
import {BrowserRouter, Route, Routes, useLocation, useNavigate, useParams} from 'react-router-dom';
import {fetchCnec} from './api';
import {Timeline} from './timeline';
import {reduceSelection} from './state';
import type {PlotlyFigure, LayerResponse, ConstraintOption} from './contracts';
import {PriceLegend} from './price-legend';
import './style.css';

interface Props {id: string; day: string; min_day: string; token: string; basemap: PlotlyFigure['layout']['mapbox']['style']}
interface GraphChange {clickData?: {points: {customdata?: unknown}[]} | null}
interface GraphProps {id: string; figure: PlotlyFigure; config: object; style: object; setProps: (change: GraphChange) => void}
// Reuse Dash's Graph component and its Plotly loader instead of shipping Plotly twice.
const Graph = (props: GraphProps) => {
  const Component = (window as unknown as {dash_core_components: {Graph: React.ComponentType<GraphProps>}}).dash_core_components.Graph;
  // Dash binds event listeners once; forward them to the current React handler.
  const handler = useRef(props.setProps);
  useLayoutEffect(() => {handler.current = props.setProps;}, [props.setProps]);
  const setProps = useCallback((change: GraphChange) => handler.current(change), []);
  return <Component {...props} setProps={setProps}/>;
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
  const changeDay = useCallback((day: string) => navigate({
    pathname: `/cnec/${day}`, search: location.search, hash: location.hash,
  }), [navigate, location.search, location.hash]);
  return <CnecPage {...props} day={day ?? default_day} navigate={changeDay}/>;
}

/** React page; the host owns routing and supplies the delivery-day navigation action. */
export function CnecPage(props: Props & {navigate: (day: string) => void}) {
  const [client] = useState(() => new QueryClient({defaultOptions: {queries: {
    retry: false, staleTime: 300_000, refetchOnWindowFocus: false, refetchOnReconnect: false, refetchOnMount: false,
  }}}));
  return <QueryClientProvider client={client}><View {...props}/></QueryClientProvider>;
}

function shell(token: string, basemap: Props['basemap']): PlotlyFigure {
  return {data: [{type: 'scattermapbox', lon: [], lat: []}], layout: {
    mapbox: {style: basemap, accesstoken: token, center: {lat: 50, lon: 10}, zoom: 3.5},
    uirevision: 'cnec-camera', margin: {t: 0, b: 0, l: 0, r: 0}, showlegend: false,
    paper_bgcolor: '#1b1b1b',
  }};
}

function combine(token: string, basemap: Props['basemap'], prices?: LayerResponse, constraints?: LayerResponse, caps?: LayerResponse): PlotlyFigure {
  const initial = shell(token, basemap);
  if (!prices && !constraints) return initial;
  const priceData = prices?.figure.data ?? [];
  return {data: [...priceData.slice(0, 1), ...(constraints?.figure.data ?? []), ...(caps?.figure.data.filter(t => t.meta === 'country-cap') ?? []), ...priceData.slice(1)],
    layout: {...(constraints?.figure.layout ?? prices?.figure.layout ?? initial.layout), uirevision: 'cnec-camera'}};
}

function View({id, day: routeDay, min_day, token, basemap, navigate}: Props & {navigate: (day: string) => void}) {
  const [selection, dispatch] = useReducer(reduceSelection, {day: routeDay, interval: 0, selected: null, source: "constraints"});
  useEffect(() => {dispatch({type: 'day', day: routeDay});}, [routeDay]);
  const {day, interval, selected, source} = selection;
  const view = {day, interval, selected};
  const calendar = useQuery({queryKey: ['calendar', day], queryFn: ({signal}) => fetchCnec('day', `day/${day}`, signal)});
  const validInterval = !!calendar.data && interval < calendar.data.labels.length;
  const prices = useQuery({queryKey: ['prices', day, interval], enabled: validInterval,
    queryFn: ({signal}) => fetchCnec('layer', 'prices', signal, {day, interval, selected: null})});
  const constraints = useQuery({queryKey: ['constraints', day, interval], enabled: validInterval,
    queryFn: ({signal}) => fetchCnec('layer', 'constraints', signal, {day, interval, selected: null})});
  const attribution = useQuery({queryKey: ['attribution', day], enabled: constraints.isSuccess,
    queryFn: ({signal}) => fetchCnec('attribution', `attribution/${day}`, signal)});
  const caps = useQuery({queryKey: ['enriched', day, interval, null, attribution.dataUpdatedAt],
    enabled: prices.isSuccess && constraints.isSuccess && attribution.isSuccess,
    queryFn: ({signal}) => fetchCnec('layer', 'enriched', signal, {day, interval, selected: null, attribution: attribution.data})});
  const highlight = useQuery({queryKey: ['highlight', day, interval, selected],
    enabled: selected !== null && constraints.isSuccess,
    queryFn: ({signal}) => fetchCnec('layer', 'constraints', signal, view)});
  const enriched = useQuery({queryKey: ['enriched', day, interval, selected, attribution.dataUpdatedAt],
    enabled: selected !== null && prices.isSuccess && constraints.isSuccess && attribution.isSuccess,
    queryFn: ({signal}) => fetchCnec('layer', 'enriched', signal, {...view, attribution: attribution.data})});
  const full = selected === null ? caps.data : enriched.data;
  const figure = useMemo(() => full?.figure ?? combine(token, basemap, prices.data, highlight.data ?? constraints.data, caps.data),
    [token, basemap, full, prices.data, highlight.data, constraints.data, caps.data]);
  const candidate = useMemo(() => {
    const copy = structuredClone(figure);
    // Keep camera inputs stable even when a newly arrived layer suggests different bounds.
    const counts = new Map<string, number>();
    for (const trace of copy.data) {
      const name = String(trace.name ?? trace.type);
      const ordinal = counts.get(name) ?? 0;
      counts.set(name, ordinal + 1);
      trace.uid = `t${Array.from(name, c => c.codePointAt(0)!.toString(16)).join("-")}-${ordinal}`;
    }
    copy.layout.mapbox.style = basemap;
    copy.layout.mapbox.center = {lat: 50, lon: 10};
    copy.layout.mapbox.zoom = 3.5;
    return copy;
  }, [figure, basemap]);
  // Publish one interval update after its independently fetched layers settle.
  // The retained figure carries its own timestamp while the controls request a new interval.
  const settled = validInterval && !prices.isPending && !constraints.isPending &&
    (prices.isError || constraints.isError || attribution.isError || (attribution.isSuccess && !caps.isPending)) &&
    (selected === null || prices.isError || constraints.isError || attribution.isError || enriched.isSuccess || enriched.isError);
  const [displayed, setDisplayed] = useState<{day: string; interval: number; selected: number | null; figure: PlotlyFigure} | null>(null);
  useEffect(() => {
    if (settled) setDisplayed({day, interval, selected, figure: candidate});
  }, [settled, day, interval, selected, candidate]);
  const emptyFigure = useMemo(() => shell(token, basemap), [token, basemap]);
  const graphFigure = displayed?.day === day ? displayed.figure : settled ? candidate : emptyFigure;
  const mapCurrent = displayed?.day === day && displayed.interval === interval && displayed.selected === selected;
  const options = full?.options ?? caps.data?.options ?? constraints.data?.options ?? [];
  useEffect(() => {
    const readyOptions = source === 'constraints' ? constraints.data?.options : caps.data?.options;
    if (selected !== null && readyOptions && !readyOptions.some(o => o.value === String(selected))) {
      dispatch({type: 'select', selected: null, source: 'constraints'});
    }
  }, [selected, source, constraints.data, caps.data]);
  const failures = [
    ['Calendar', calendar], ['Prices', prices], ['Constraints', constraints],
    ['Attribution', attribution], ['Country caps', caps], ['Selection', highlight],
    ...(selected === null ? [] : [['Contributions', enriched] as const]),
  ] as const;
  const loading = !calendar.data && calendar.isFetching ? 'Loading market intervals…' : !prices.data && prices.isFetching ? 'Loading prices…' :
    !constraints.data && constraints.isFetching ? 'Loading constraints…' :
    (attribution.isFetching || caps.isFetching || enriched.isFetching) ? 'Loading price contributions…' : '';
  function select(value: string) {
    const option = options.find(o => o.value === value);
    if (option) dispatch({type: 'select', selected: value === '' ? null : Number(value), source: option.source});
  }
  function mapClick(change: GraphChange) {
    if (!mapCurrent) return;
    const values = change.clickData?.points[0]?.customdata;
    if (!Array.isArray(values) || typeof values[0] !== 'string') return;
    const candidates = values[0].split(',');
    if (selected !== null && candidates.includes(String(selected))) return;
    const option = options.find((o: ConstraintOption) => o.value && candidates.includes(o.value));
    if (option) select(option.value);
  }
  return <section id={id} className="cnec-react">
    <div className="cnec-controls">
      <input aria-label="Delivery day" type="date" min={min_day} value={day} onChange={e => {
        if (e.target.value >= min_day && e.target.value !== day) navigate(e.target.value);
      }}/>
      <select aria-label="Binding constraint" value={selected === null ? '' : String(selected)}
        disabled={!constraints.data} onChange={e => select(e.target.value)}>
        {!options.length && <option value="">Select a binding row</option>}
        {selected !== null && !options.some(o => o.value === String(selected)) && <option value={selected}>Selected row {selected}</option>}
        {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
      <span>{selected === null ? '' : `Reference: ${enriched.isSuccess ? enriched.data.reference ?? 'unavailable' : enriched.isError || prices.isError || attribution.isError ? 'unavailable' : 'pending'}`}</span>
    </div>
    <div className="cnec-map-container">
      <Graph id={`${id}-map`} figure={graphFigure} setProps={mapClick}
        config={{responsive: true, displayModeBar: false, scrollZoom: true}} style={{height: '100%'}}/>
      <small className="cnec-sources">
        Data: <a href="https://publicationtool.jao.eu/core/">JAO</a> · {' '}
        <a href="https://www.electricitymaps.com/">Electricity Maps</a> · {' '}
        <a href="https://www.openstreetmap.org/copyright">© OpenStreetMap contributors</a>
      </small>
      <PriceLegend figure={graphFigure}/>
      <aside className="cnec-progress" aria-live="polite">
        {loading && <div role="status" aria-label="Map loading">{loading}</div>}
        {full?.notes.map(note => <div role="status" key={note}>{note}</div>)}
        {failures.map(([name, query]) => query.error && <div role="alert" key={name}>
          {name}: {query.error.message} <button onClick={() => void query.refetch()}>Retry</button>
        </div>)}
      </aside>
    </div>
    <div className="cnec-time-controls">
      <button disabled={!validInterval || interval === 0} onClick={() => dispatch({type: 'interval', interval: interval - 1})}>Previous</button>
      <button disabled={!validInterval || interval === (calendar.data?.labels.length ?? 0) - 1}
        onClick={() => dispatch({type: 'interval', interval: interval + 1})}>Next</button>
      <output>{calendar.data?.labels[interval]}</output>
      <Timeline labels={calendar.data?.labels ?? []} interval={interval} disabled={!validInterval}
        onChange={interval => dispatch({type: 'interval', interval})}/>
    </div>
  </section>;
}
