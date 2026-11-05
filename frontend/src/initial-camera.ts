// Rounded bounds of the Core zone outline bundle; the starting view needs modest clearance, not exact fitting.
const CORE_BOUNDS = [-4.8, 41.3, 29.8, 55.1] as const;

/** One starting camera, computed before Graph mounts; map interactions own later camera changes. */
export function initialCoreCamera(width: number, height: number) {
  const [west, south, east, north] = CORE_BOUNDS;
  const mercatorY = (latitude: number) => (1 - Math.asinh(Math.tan(latitude * Math.PI / 180)) / Math.PI) / 2;
  const top = mercatorY(north), bottom = mercatorY(south);
  const availableWidth = Math.max(160, width - 56);
  const availableHeight = Math.max(160, height - (width <= 650 ? 300 : 240));
  const scale = Math.min(availableWidth / ((east - west) / 360), availableHeight / (bottom - top));
  return {
    center: {lon: (west + east) / 2, lat: Math.atan(Math.sinh(Math.PI * (1 - top - bottom))) * 180 / Math.PI},
    zoom: Math.log2(scale / 512), bearing: 0, pitch: 0,
  };
}
