import {useEffect, useLayoutEffect, useRef} from 'react';
import type {MapboxMap} from './mapbox-adapter';

/** North-up, flat map view, independent of the selected market interval. */
export interface MapCamera {lat: number; lon: number; zoom: number}

function sameCamera(a: MapCamera, b: MapCamera) {
  return Math.abs(a.lat-b.lat)<0.00001 && Math.abs(a.lon-b.lon)<0.00001 && Math.abs(a.zoom-b.zoom)<0.00001;
}
function readCamera(map: MapboxMap): MapCamera {
  const {lat,lng} = map.getCenter();
  return {lat,lon:((lng+180)%360+360)%360-180,zoom:map.getZoom()};
}

/** Observe native move completion; restoring URL state does not feed back into navigation. */
export function useMapCamera(map: MapboxMap | null, camera?: MapCamera, onChange?: (camera: MapCamera)=>void) {
  const latest = useRef({camera,onChange});
  useLayoutEffect(()=>{latest.current={camera,onChange};});
  useEffect(()=>{
    if (!map || !onChange) return;
    const moved = ()=>{
      const next = readCamera(map);
      if (!latest.current.camera || !sameCamera(next,latest.current.camera)) latest.current.onChange?.(next);
    };
    map.on('moveend',moved);
    return ()=>{map.off('moveend',moved);};
  },[map,!!onChange]);
  useEffect(()=>{
    if (map && camera && !sameCamera(readCamera(map),camera))
      map.jumpTo({center:[camera.lon,camera.lat],zoom:camera.zoom});
  },[map,camera?.lat,camera?.lon,camera?.zoom]);
}
