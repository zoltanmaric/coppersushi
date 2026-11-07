import React, {useEffect, useLayoutEffect, useRef} from 'react';
import {mapInstance} from './mapbox-adapter';
import type {PlotlyFigure} from './figure';

export interface PlotElement extends HTMLDivElement {
  on(event: string, handler: (event: unknown) => unknown): void;
  removeListener(event: string, handler: (event: unknown) => unknown): void;
}
interface PlotlyRuntime {
  react(plot: HTMLElement, figure: {data: PlotlyFigure['data']; layout: PlotlyFigure['layout']; config: object}): Promise<unknown>;
  purge(plot: HTMLElement): void;
  Fx: {
    unhover(plot: HTMLElement): void;
    hover(plot: HTMLElement, point: {xval: number; yval: number; xpx: number; ypx: number}, subplot: string): void;
  };
}
declare global {interface Window {Plotly: PlotlyRuntime}}

interface Props {
  id: string; data: PlotlyFigure['data']; layout: PlotlyFigure['layout']; config: object;
  onRendered: (element: PlotElement) => void; onError: (error: Error) => void;
  onClick: (event: unknown) => void; onBeforeHover?: (event: unknown) => boolean;
}

/** No internal queue: the map owner submits a new figure only after this promise settles. */
export function Plot({id, data, layout, config, ...callbacks}: Props) {
  const element = useRef<PlotElement>(null);
  const current = useRef(callbacks);
  useLayoutEffect(() => {current.current = callbacks;});
  const pending = useRef<Promise<unknown>>(Promise.resolve());
  const bound = useRef(false);
  useEffect(() => {
    const plot = element.current!;
    let active = true;
    pending.current = Promise.resolve().then(() => window.Plotly.react(plot, {data, layout, config})).then(() => {
      if (!active) return;
      if (!bound.current) {
        plot.on('plotly_click', event => current.current.onClick(event));
        plot.on('plotly_beforehover', event => current.current.onBeforeHover?.(event));
        bound.current = true;
      }
      current.current.onRendered(plot);
    }, error => {if (active) current.current.onError(error instanceof Error ? error : new Error(String(error)));});
    return () => {active = false;};
  }, [data, layout, config]);
  useEffect(() => {
    const plot = element.current!;
    return () => {void pending.current.then(() => window.Plotly.purge(plot));};
  }, []);
  return <div id={id} ref={element} style={{height:'100%',width:'100%'}}/>;
}

export function clearTooltip(plot: HTMLElement) {window.Plotly.Fx.unhover(plot);}

/** Mapbox clicks consume cached hover hits, even when touch produces no mousemove. */
export function hoverAtPointer(plot: HTMLElement, clientX: number, clientY: number) {
  const map = mapInstance(plot), canvas = plot.querySelector<HTMLCanvasElement>('.mapboxgl-canvas');
  if (!map || !canvas) return;
  const bounds = canvas.getBoundingClientRect();
  const xpx = clientX - bounds.left, ypx = clientY - bounds.top;
  const {lng, lat} = map.unproject([xpx, ypx]);
  // unhover clears the previous hover throttle so this gesture resolves synchronously.
  window.Plotly.Fx.unhover(plot);
  window.Plotly.Fx.hover(plot, {xval:lng, yval:lat, xpx, ypx}, 'mapbox');
}
