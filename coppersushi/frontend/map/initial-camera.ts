// Rounded bounds of the Core zone outline bundle; the starting view needs modest clearance, not exact fitting.
const CORE_BOUNDS = [-4.8, 41.3, 29.8, 55.1] as const;

/** One starting camera, computed before Graph mounts; map interactions own later camera changes. */
export function initialCoreCamera(width: number, height: number) {
  return initialBoundsCamera(CORE_BOUNDS, width, height);
}

export type MapBounds = readonly [west:number, south:number, east:number, north:number];

/** Fit geographic extents in Mercator space, leaving clearance for map controls. */
export function initialBoundsCamera(bounds:MapBounds, width:number, height:number, pitch = 0) {
  const [west, south, east, north] = bounds;
  const mercatorY = (latitude: number) => (1 - Math.asinh(Math.tan(latitude * Math.PI / 180)) / Math.PI) / 2;
  const top = mercatorY(north), bottom = mercatorY(south);
  const availableWidth = Math.max(160, width - 56);
  const availableHeight = Math.max(160, height - (width <= 650 ? 300 : 240));
  // Mapbox's default field of view gives a camera distance of 1.5 viewport heights.
  // Fit the projected rectangle, including the larger near (southern) edge.
  const distance = 1.5 * height;
  const sin = Math.sin(pitch * Math.PI / 180), cos = Math.cos(pitch * Math.PI / 180);
  const spanX = (east - west) / 360, spanY = bottom - top;
  const offset = (scale:number) => sin === 0 ? 0 :
    -(sin * (spanY * scale) ** 2) / (2 * (distance + Math.sqrt(distance ** 2 + (sin * spanY * scale) ** 2)));
  const fits = (scale:number) => {
    const middle = offset(scale), near = middle + spanY * scale / 2, far = middle - spanY * scale / 2;
    const projectY = (y:number) => y * cos * distance / (distance - y * sin);
    return distance > near * sin &&
      spanX * scale * distance / (distance - near * sin) <= availableWidth &&
      projectY(near) - projectY(far) <= availableHeight;
  };
  let low = 0, high = 512 * 2 ** 15;
  for (let i=0;i<60;i++) {const middle=(low+high)/2;if(fits(middle)) low=middle;else high=middle;}
  const scale = low;
  const centerY = (top + bottom) / 2 - offset(scale) / scale;
  return {
    center: {lon: (west + east) / 2, lat: Math.atan(Math.sinh(Math.PI * (1 - 2 * centerY))) * 180 / Math.PI},
    zoom: Math.log2(scale / 512), bearing: 0, pitch,
  };
}
