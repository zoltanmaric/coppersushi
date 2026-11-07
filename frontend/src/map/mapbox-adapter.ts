import type {LngLat} from './overlay-model';

export interface MapboxMap {
  dragRotate: {disable(): void};
  touchZoomRotate: {disableRotation(): void};
  touchPitch: {disable(): void};
  keyboard: {disableRotation(): void};
  getCanvasContainer(): HTMLElement;
  project(point: LngLat): {x: number; y: number};
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
