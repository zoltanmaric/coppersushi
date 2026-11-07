import {useEffect, useRef} from 'react';
import type {RefObject} from 'react';
import type {MapboxMap} from './mapbox-adapter';
import {clearTooltip, hoverAtPointer} from './plot';

type Origin = 'canvas' | 'tooltip' | 'other';

/** One owner for gesture targeting and the independently persistent hover dismissal. */
export function useMapGestures(host: RefObject<HTMLDivElement>, map: MapboxMap | null, dismissible: boolean) {
  const origin = useRef<Origin>('other');
  const suppressed = useRef(false);
  const ownership = (next: Origin) => {
    origin.current = next;
    host.current?.classList.toggle('cnec-map-gesture', next === 'canvas');
  };
  const dismiss = () => {
    suppressed.current = true;
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
        suppressed.current = false;
        const plot = host.current?.querySelector<HTMLElement>('.js-plotly-plot');
        if (origin.current === 'canvas' && plot) hoverAtPointer(plot, event.clientX, event.clientY);
      },
      onPointerMoveCapture: (event: React.PointerEvent<HTMLDivElement>) => {
        if (event.pointerType === 'mouse' && event.buttons === 0) suppressed.current = false;
      },
      onPointerCancelCapture: () => ownership('other'),
      onClickCapture: (event: React.MouseEvent<HTMLDivElement>) => {
        if (origin.current === 'tooltip' && dismissible) {
          event.preventDefault();
          event.stopPropagation();
          dismiss();
        }
        ownership('other');
      },
    },
  };
}
