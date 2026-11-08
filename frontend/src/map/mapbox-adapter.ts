import type {LngLat} from './overlay-model';

export interface MapboxMap {
  dragRotate: {disable(): void};
  touchZoomRotate: {disableRotation(): void};
  touchPitch: {disable(): void};
  keyboard: {disableRotation(): void};
  getCanvasContainer(): HTMLElement;
  addSource(id: string, source: object): void;
  getSource(id: string): {setData(data: object): void} | undefined;
  removeSource(id: string): void;
  addLayer(layer: object): void;
  getLayer(id: string): object | undefined;
  removeLayer(id: string): void;
  queryRenderedFeatures(point: [number, number], options: {layers: string[]}): {properties?: Record<string, unknown>}[];
  project(point: LngLat): {x: number; y: number};
  unproject(point: [number, number]): {lng: number; lat: number};
  isMoving(): boolean;
  getPitch(): number;
  getBearing(): number;
  getBounds(): {getWest(): number; getEast(): number};
  on(event: string, handler: () => void): void;
  off(event: string, handler: () => void): void;
}

/** Plotly.js 3.7.0 has no public bridge to its Mapbox 1.13.4 instance. */
export function mapInstance(plot: HTMLElement): MapboxMap | null {
  return (plot as HTMLElement & {
    _fullLayout?: {mapbox?: {_subplot?: {map?: MapboxMap}}};
  })._fullLayout?.mapbox?._subplot?.map ?? null;
}

export function lockMapOrientation(map: MapboxMap) {
  map.dragRotate.disable();
  map.touchZoomRotate.disableRotation();
  map.touchPitch.disable();
  map.keyboard.disableRotation();
}

/** Plotly's pinned Mapbox 1.13.4 fork has a constructor fadeDuration option but no public setter. */
export function disableLabelFade(map: MapboxMap) {
  (map as MapboxMap & {_fadeDuration: number})._fadeDuration = 0;
}
