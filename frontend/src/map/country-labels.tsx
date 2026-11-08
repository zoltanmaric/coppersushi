import {useLayoutEffect} from 'react';
import {disableLabelFade} from './mapbox-adapter';
import type {MapboxMap} from './mapbox-adapter';
import {coreZone, type CoreZone} from '../market/reference';
import type {LngLat} from './overlay-model';

export interface CountryLabel {zone: CoreZone; name: string; centre: LngLat; price: number}
const id = 'country-price-labels';

export function countryAtPointer(map: MapboxMap, x: number, y: number): CoreZone | null {
  if (!map.getLayer(id)) return null;
  const rect = map.getCanvasContainer().getBoundingClientRect();
  const feature = map.queryRenderedFeatures([x - rect.left, y - rect.top], {layers: [id]})[0];
  return coreZone(feature?.properties?.zone);
}

/** Keep one native symbol layer so collision placement survives price updates without fading. */
export function CountryLabels({labels, map}: {labels: CountryLabel[]; map: MapboxMap}) {
  useLayoutEffect(() => {
    disableLabelFade(map);
    map.addSource(id, {type: 'geojson', data: {type: 'FeatureCollection', features: []}});
    map.addLayer({id, type: 'symbol', source: id, layout: {
      'text-field': '{text}', 'text-font': ['Open Sans Regular'], 'text-size': 14,
      'text-allow-overlap': false, 'text-ignore-placement': false, 'text-padding': 3,
    }, paint: {'text-color': '#fff'}});
    return () => {
      if (map.getLayer(id)) map.removeLayer(id);
      if (map.getSource(id)) map.removeSource(id);
    };
  }, [map]);
  useLayoutEffect(() => {
    map.getSource(id)?.setData({type: 'FeatureCollection', features: labels.map(label => ({
      type: 'Feature', id: label.zone, geometry: {type: 'Point', coordinates: label.centre},
      properties: {zone: label.zone, text: `${label.name}\n€${label.price.toFixed(2)}`},
    }))});
  }, [map, labels]);
  return null;
}
