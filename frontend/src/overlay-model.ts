import type {PlotlyFigure} from './contracts';

export type LngLat = readonly [lon: number, lat: number];
export type SelectionEffect = {kind: 'line'; endpoints: readonly [LngLat, LngLat]} |
  {kind: 'transformer'; center: LngLat};
export interface OverlayModel {ambient: LngLat[][]; selection: SelectionEffect | null}
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
