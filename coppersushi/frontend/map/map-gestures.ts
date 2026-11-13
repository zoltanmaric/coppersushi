import {useEffect, useRef} from 'react';
import type {RefObject} from 'react';
import type {MapboxMap} from './mapbox-adapter';
import {clearTooltip, hoverAtPointer} from './plot';
import {countryAtPointer} from './country-labels';
import type {CoreZone} from '../pages/cnec/market/reference';

type Origin = 'canvas' | 'country' | 'tooltip' | 'other';

/** One owner for gesture targeting and the independently persistent hover dismissal. */
export function useMapGestures(host: RefObject<HTMLDivElement>, map: MapboxMap | null, dismissible: boolean, onReference?: (zone: CoreZone) => void) {
  const origin = useRef<Origin>('other');
  const suppressed = useRef(false);
  const country = useRef<{zone: CoreZone; x: number; y: number} | null>(null);
  const ownership = (next: Origin) => {
    origin.current = next;
    host.current?.classList.toggle('cnec-map-gesture', next === 'canvas');
  };
  const dismiss = () => {
    suppressed.current = true;
    country.current = null;
    const plot = host.current?.querySelector<HTMLElement>('.js-plotly-plot');
    if (plot) clearTooltip(plot);
  };
  useEffect(() => {
    if (!map) return;
    for (const event of ['dragstart','zoomstart']) map.on(event, dismiss);
    return () => {for (const event of ['dragstart','zoomstart']) map.off(event, dismiss);};
  }, [map]);
  return {
    beforeHover: () => !suppressed.current,
    handlers: {
      onPointerDownCapture: (event: React.PointerEvent<HTMLDivElement>) => {
        const target = event.target;
        ownership(target instanceof HTMLCanvasElement ? 'canvas' : target instanceof Element && target.closest('.hovertext') ? 'tooltip' : 'other');
        const zone = origin.current === 'canvas' && map && onReference ? countryAtPointer(map, event.clientX, event.clientY) : null;
        country.current = zone ? {zone, x: event.clientX, y: event.clientY} : null;
        if (zone) ownership('country');
        suppressed.current = zone !== null;
        const plot = host.current?.querySelector<HTMLElement>('.js-plotly-plot');
        if (origin.current === 'canvas' && plot) hoverAtPointer(plot, event.clientX, event.clientY);
      },
      onPointerMoveCapture: (event: React.PointerEvent<HTMLDivElement>) => {
        if (event.pointerType === 'mouse' && event.buttons === 0) suppressed.current = false;
      },
      onPointerCancelCapture: () => {country.current = null; ownership('other');},
      onClickCapture: (event: React.MouseEvent<HTMLDivElement>) => {
        const hit = country.current;
        country.current = null;
        if (origin.current === 'country' && hit && Math.hypot(event.clientX - hit.x, event.clientY - hit.y) <= 5) {
          event.preventDefault();
          event.stopPropagation();
          onReference?.(hit.zone);
        } else if (origin.current === 'tooltip' && dismissible) {
          event.preventDefault();
          event.stopPropagation();
          dismiss();
        }
        ownership('other');
      },
    },
  };
}
