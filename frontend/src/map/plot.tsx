import React, {useEffect, useLayoutEffect, useRef} from 'react';
import type {PlotlyFigure} from './figure';

export interface PlotElement extends HTMLDivElement {
  on(event: string, handler: (event: unknown) => unknown): void;
  removeListener(event: string, handler: (event: unknown) => unknown): void;
}
interface PlotlyRuntime {
  react(plot: HTMLElement, figure: {data: PlotlyFigure['data']; layout: PlotlyFigure['layout']; config: object}): Promise<unknown>;
  purge(plot: HTMLElement): void;

}
declare global {interface Window {Plotly: PlotlyRuntime}}

interface Props {
  id: string; data: PlotlyFigure['data']; layout: PlotlyFigure['layout']; config: object;
  onRendered: (element: PlotElement) => void; onError: (error: Error) => void;
  onClick: (event: unknown) => void;
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
