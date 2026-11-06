import React, {useEffect, useReducer, useRef} from 'react';
import {createPortal} from 'react-dom';
import {ConstraintOverlay} from './constraint-overlay';
import {lockMapOrientation, mapInstance} from './mapbox-adapter';
import type {MapboxMap} from './mapbox-adapter';
import type {OverlayModel} from './overlay-model';
import {CountryLabels} from './country-labels';
import type {CountryLabel} from './country-labels';
import type {CoreZone} from './reference';

interface PlotElement extends HTMLElement {
  on(event: 'plotly_afterplot', handler: () => void): void;
  removeListener?(event: 'plotly_afterplot', handler: () => void): void;
}

/** Native camera events redraw only decoration, never the parent figure or request state. */
export function MapDecoration({host, model, hidden, countries, onReference}: {
  host: React.RefObject<HTMLDivElement>; model: OverlayModel; hidden: boolean;
  countries: CountryLabel[]; onReference: (zone: CoreZone) => void;
}) {
  const activeMap = useRef<MapboxMap | null>(null);
  const [, redraw] = useReducer(n => n + 1, 0);
  useEffect(() => {
    let plot: PlotElement | null = null;
    const refresh = () => redraw();
    const detach = () => {
      const map = activeMap.current;
      if (!map) return;
      for (const event of ['movestart', 'moveend', 'resize']) map.off(event, refresh);
      map.off('remove', removed);
      activeMap.current = null;
    };
    const removed = () => {detach(); refresh();};
    const bind = () => {
      const map = plot ? mapInstance(plot) : null;
      if (map !== activeMap.current) {
        detach();
        activeMap.current = map;
        if (map) {
          for (const event of ['movestart', 'moveend', 'resize']) map.on(event, refresh);
          map.on('remove', removed);
        }
      }
      if (map) lockMapOrientation(map);
      refresh();
    };
    // React mounts Plotly asynchronously; afterplot also catches native map replacement.
    const attach = () => {
      const node = host.current?.querySelector<PlotElement>('.js-plotly-plot');
      if (!node || typeof node.on !== 'function') return;
      plot = node;
      plot.on('plotly_afterplot', bind);
      bind();
      observer.disconnect();
    };
    const observer = new MutationObserver(attach);
    observer.observe(host.current!, {childList: true, subtree: true});
    attach();
    return () => {
      observer.disconnect();
      plot?.removeListener?.('plotly_afterplot', bind);
      detach();
    };
  }, [host]);
  const map = activeMap.current;
  const bounds = map?.getBounds();
  // One flat, canonical world: native symbols still render in unsupported decoration views.
  const visible = !hidden && map && !map.isMoving() && map.getPitch() === 0 && map.getBearing() === 0 &&
    bounds && bounds.getWest() >= -180 && bounds.getEast() <= 180;
  const project = map ? (point: Parameters<typeof map.project>[0]): [number,number] => {
    const {x, y} = map.project(point);
    return [x, y];
  } : null;
  return <><ConstraintOverlay model={model} project={visible ? project : null}/>
    {map && createPortal(<CountryLabels labels={countries} map={map} onReference={onReference}/>,map.getCanvasContainer())}</>;
}
