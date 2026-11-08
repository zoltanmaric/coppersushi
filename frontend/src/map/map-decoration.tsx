import React, {useEffect, useReducer} from 'react';
import {createPortal} from 'react-dom';
import {ConstraintOverlay} from './constraint-overlay';
import {lockMapOrientation} from './mapbox-adapter';
import type {MapboxMap} from './mapbox-adapter';
import type {OverlayModel} from './overlay-model';
import {CountryLabels} from './country-labels';
import type {CountryLabel} from './country-labels';

/** Native movement updates decoration without requesting or redrawing a market figure. */
export function MapDecoration({map, model, hidden, countries}: {
  map: MapboxMap | null; model: OverlayModel; hidden: boolean;
  countries: CountryLabel[];
}) {
  const [, redraw] = useReducer(n => n + 1, 0);
  useEffect(() => {
    if (!map) return;
    lockMapOrientation(map);
    const refresh = () => redraw();
    for (const event of ['movestart','moveend','resize']) map.on(event, refresh);
    return () => {for (const event of ['movestart','moveend','resize']) map.off(event, refresh);};
  }, [map]);
  const bounds = map?.getBounds();
  const visible = !hidden && map && !map.isMoving() && map.getPitch() === 0 && map.getBearing() === 0 &&
    bounds && bounds.getWest() >= -180 && bounds.getEast() <= 180;
  const project = map ? (point: Parameters<typeof map.project>[0]): [number,number] => {
    const {x,y} = map.project(point);
    return [x,y];
  } : null;
  return map && createPortal(<>
    <ConstraintOverlay model={model} project={visible ? project : null}/>
    <CountryLabels labels={countries} map={map}/>
  </>, map.getCanvasContainer());
}
