import type {PlotlyFigure} from './contracts';

export type LngLat = readonly [lon: number, lat: number];
export type SelectionEffect = {kind: 'line'; endpoints: readonly [LngLat, LngLat]} |
  {kind: 'transformer'; center: LngLat};
export interface OverlayModel {ambient: LngLat[][]; selection: SelectionEffect | null}
export interface Camera {lat: number; lon: number; zoom: number; bearing: number; pitch: number}
const finite = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value);
const object = (value: unknown): Record<string, unknown> | null =>
  value !== null && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : null;

/** Optional drawing metadata enters here; invalid decoration never suppresses a native map glyph. */
export function overlayModel(figure: PlotlyFigure): OverlayModel {
  const model: OverlayModel = {ambient: [], selection: null};
  for (const trace of figure.data) {
    const meta = object(trace.meta);
    if (!meta || (!meta.ambient && !meta.effect)) continue;
    const xs = trace.lon, ys = trace.lat;
    if (!Array.isArray(xs) || !Array.isArray(ys) || xs.length !== ys.length) continue;
    const segments: LngLat[][] = [[]];
    xs.forEach((x, i) => {
      const y = ys[i];
      if (finite(x) && finite(y) && Math.abs(y) <= 85.051129) segments.at(-1)!.push([x, y]);
      else if (segments.at(-1)!.length) segments.push([]);
    });
    if (meta.ambient === true) model.ambient.push(...segments.filter(s => s.length > 1));
    const points = segments[0];
    if (meta.effect === 'line' && xs.length === 2 && points.length === 2) {
      model.selection = {kind: 'line', endpoints: [points[0], points[1]]};
    } else if (meta.effect === 'transformer' && xs.length === 1 && points.length === 1) {
      model.selection = {kind: 'transformer', center: points[0]};
    }
  }
  return model;
}

/** Relayout events are partial camera updates; ignore malformed external values. */
export function updateCamera(previous: Camera, update: Record<string, unknown>): Camera {
  const center = object(update['mapbox.center']);
  return {
    lat: finite(center?.lat) ? center.lat : previous.lat,
    lon: finite(center?.lon) ? center.lon : previous.lon,
    zoom: finite(update['mapbox.zoom']) ? update['mapbox.zoom'] : previous.zoom,
    bearing: finite(update['mapbox.bearing']) ? update['mapbox.bearing'] : previous.bearing,
    pitch: finite(update['mapbox.pitch']) ? update['mapbox.pitch'] : previous.pitch,
  };
}

/** The decorative projector supports a flat viewport inside one canonical world only. */
export function supportsDecoration(camera: Camera, width: number, height: number): boolean {
  if (![...Object.values(camera), width, height].every(finite) || width <= 0 || height <= 0 ||
      camera.pitch !== 0 || Math.abs(camera.lat) > 85.051129) return false;
  const scale = 512 * 2 ** camera.zoom;
  const angle = camera.bearing * Math.PI / 180;
  const extent = (Math.abs(Math.cos(angle)) * width + Math.abs(Math.sin(angle)) * height) / 2;
  const center = (camera.lon + 180) / 360 * scale;
  return Number.isFinite(scale) && center - extent >= 0 && center + extent <= scale;
}
