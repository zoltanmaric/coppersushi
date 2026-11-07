import type {PlotlyFigure} from './figure';

export type LngLat = readonly [lon: number, lat: number];
export type SelectionEffect = {kind: 'line'; endpoints: readonly [LngLat, LngLat]} |
  {kind: 'transformer'; center: LngLat};
export interface OverlayModel {ambient: LngLat[][]; selections: SelectionEffect[]}
const finite = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value);
const object = (value: unknown): Record<string, unknown> | null =>
  value !== null && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : null;

/** Optional drawing metadata enters here; invalid decoration never suppresses a native map glyph. */
export function overlayModel(figure: PlotlyFigure): OverlayModel {
  const model: OverlayModel = {ambient: [], selections: []};
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
    if (meta.effect === 'line') {
      for (const points of segments) if (points.length === 2)
        model.selections.push({kind:'line',endpoints:[points[0],points[1]]});
    } else if (meta.effect === 'transformer') {
      for (const points of segments) for (const center of points)
        model.selections.push({kind:'transformer',center});
    }
  }
  return model;
}
