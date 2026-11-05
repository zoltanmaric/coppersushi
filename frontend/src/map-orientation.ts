interface OrientationControls {
  dragRotate: {disable(): void};
  touchZoomRotate: {disableRotation(): void};
  touchPitch: {disable(): void};
  keyboard: {disableRotation(): void};
}

/** Plotly.js 3.7.0 has no public bridge to its Mapbox 1.13.4 gesture controls. */
export function lockMapOrientation(plot: HTMLElement) {
  const map = (plot as HTMLElement & {
    _fullLayout?: {mapbox?: {_subplot?: {map?: OrientationControls}}};
  })._fullLayout?.mapbox?._subplot?.map;
  if (!map) return;
  map.dragRotate.disable();
  map.touchZoomRotate.disableRotation();
  map.touchPitch.disable();
  map.keyboard.disableRotation();
}
