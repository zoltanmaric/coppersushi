import React from 'react';
import type {CoreZone} from './reference';
import type {LngLat} from './overlay-model';

export interface CountryLabel {zone: CoreZone; name: string; centre: LngLat; price: number}

/** React retains each label node while its price and native projected position change. */
export function CountryLabels({labels, project, onReference}: {
  labels: CountryLabel[]; project: ((point: LngLat) => [number,number]) | null;
  onReference: (zone: CoreZone) => void;
}) {
  if (!project) return null;
  return <div className="cnec-country-labels" aria-label="Country prices">
    {labels.map(label => {
      const [x,y]=project(label.centre);
      return <button key={label.zone} style={{transform:`translate(${x}px,${y}px) translate(-50%,-50%)`}}
        aria-label={`Use ${label.name} as reference`} onClickCapture={event=>{event.stopPropagation();onReference(label.zone);}}>
        <span>{label.name}</span><span>€{label.price.toFixed(2)}</span>
      </button>;
    })}
  </div>;
}
