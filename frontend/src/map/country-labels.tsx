import React, {useLayoutEffect, useRef} from 'react';
import type {MapboxMap} from './mapbox-adapter';
import type {CoreZone} from '../market/reference';
import type {LngLat} from './overlay-model';

export interface CountryLabel {zone: CoreZone; name: string; centre: LngLat; price: number}

/** React owns text; native movement updates positions synchronously without a React render. */
export function CountryLabels({labels, map, onReference}: {
  labels: CountryLabel[]; map: Pick<MapboxMap, 'project' | 'on' | 'off'>;
  onReference: (zone: CoreZone) => void;
}) {
  const host = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    const position = () => {
      const buttons = host.current!.children;
      labels.forEach((label, i) => {
        const {x,y} = map.project(label.centre);
        (buttons[i] as HTMLElement).style.transform = `translate(${x}px,${y}px) translate(-50%,-50%)`;
      });
    };
    position();
    for (const event of ['move','moveend','resize']) map.on(event,position);
    return () => {for (const event of ['move','moveend','resize']) map.off(event,position);};
  },[map,labels]);
  return <div ref={host} className="cnec-country-labels" aria-label="Country prices">
    {labels.map(label => {
      return <button key={label.zone}
        aria-label={`Use ${label.name} as reference`} onClickCapture={event=>{event.stopPropagation();onReference(label.zone);}}>
        <span>{label.name}</span><span>€{label.price.toFixed(2)}</span>
      </button>;
    })}
  </div>;
}
