import React, {useEffect, useLayoutEffect, useMemo, useReducer, useRef, useState} from 'react';
import {Plot} from './plot';
import {reduceRender} from './render-state';
import {MapDecoration} from './map-decoration';
import {mapInstance} from './mapbox-adapter';
import type {MapboxMap} from './mapbox-adapter';
import {useMapGestures} from './map-gestures';
import type {PlotlyFigure} from './figure';
import type {OverlayModel} from './overlay-model';
import type {CountryLabel} from './country-labels';
import type {CoreZone} from '../pages/cnec/market/reference';

interface Props {
  id: string; figure: PlotlyFigure; config: object; overlay?: OverlayModel; hidden?: boolean;
  countries?: CountryLabel[]; onReference?: (zone: CoreZone) => void;
  onClick?: (event: unknown) => void; compactTooltips?: boolean;
  onRendered?: (figure:PlotlyFigure)=>void; onError?: (error:Error|null)=>void;
}

type Snapshot = Pick<Props, 'figure' | 'overlay' | 'hidden' | 'countries'>;

/** Queue display data; intent callbacks always use the latest committed navigation state. */
export function MapGraph(props: Props) {
  const snapshot = useMemo<Snapshot>(() => ({figure:props.figure, overlay:props.overlay, hidden:props.hidden, countries:props.countries}),
    [props.figure, props.overlay, props.hidden, props.countries]);
  const [render, dispatch] = useReducer(reduceRender<Snapshot>, {active:snapshot, pending:null, busy:true});
  useEffect(() => {dispatch({type:'request', value:snapshot});}, [snapshot]);
  const {figure, overlay, hidden, countries} = render.active;
  const {id, config} = props;
  const [error, setError] = useState<string | null>(null);
  const interactive = !render.busy && props.figure === figure && error === null;
  const interaction = useRef({interactive, onClick:props.onClick});
  useLayoutEffect(() => {interaction.current = {interactive, onClick:props.onClick};});
  const host = useRef<HTMLDivElement>(null);
  const [map, setMap] = useState<MapboxMap | null>(null);
  const gestures = useMapGestures(host, map, props.compactTooltips ?? true, props.onReference ? zone => {if (interactive) props.onReference?.(zone);} : undefined);
  const completionFrame = useRef<number | null>(null);
  useEffect(() => () => {if (completionFrame.current !== null) cancelAnimationFrame(completionFrame.current);}, []);
  const complete = () => {
    // A paint between renders keeps continuous scrubbing responsive.
    completionFrame.current = requestAnimationFrame(() => {
      completionFrame.current = requestAnimationFrame(() => {
        completionFrame.current = null;
        dispatch({type:'complete', figure});
      });
    });
  };
  const data = useMemo(() => structuredClone(figure.data), [figure.data]);
  // Native Mapbox mutates this style; retain it until the actual layout input changes.
  const layout = useMemo(() => structuredClone(figure.layout), [figure.layout]);
  return <div ref={host} className="map-renderer" {...gestures.handlers}>
    <Plot id={id} data={data} layout={layout} config={config}
      onRendered={element => {setError(null);props.onError?.(null);setMap(mapInstance(element));props.onRendered?.(figure);complete();}}
      onError={error => {setError(error.message);props.onError?.(error);complete();}}
      onClick={event => {if (interaction.current.interactive) interaction.current.onClick?.(event);}}
      onBeforeHover={gestures.beforeHover}/>
    {overlay && <MapDecoration map={map} model={overlay} hidden={hidden ?? false} countries={countries ?? []}/>}

  </div>;
}
