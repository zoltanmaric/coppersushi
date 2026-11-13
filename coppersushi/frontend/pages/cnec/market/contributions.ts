import type {MarketInterval} from '../data/contracts';
import type {CoreZone} from './reference';

/** Normalized-FB contribution; missing inputs remain unavailable. */
export function contributions(
  interval: MarketInterval,
  id: string,
  reference: CoreZone,
): Partial<Record<CoreZone, number>> | null {
  const cap = id === 'cap:PL' ? interval.caps[0] : undefined;
  if (cap)
    return Object.fromEntries(
      Object.keys(interval.prices).map((z) => [
        z,
        cap.delta * ((z === "PL" ? 1 : 0) - (reference === "PL" ? 1 : 0)),
      ]),
    );
  const rows = interval.constraints.filter(r => r.eic === id), alpha = interval.alpha;
  if (!rows.length) return {};
  if (alpha === null || !(alpha > 0 && alpha <= 1) || rows.some(r => r.ptdfs[reference] === undefined)) return null;
  return Object.fromEntries(Object.keys(interval.prices).flatMap(zone => {
    if (rows.some(r => r.ptdfs[zone as CoreZone] === undefined)) return [];
    return [[zone, rows.reduce((total,r) => total - r.shadow_price * (r.ptdfs[zone as CoreZone]! - r.ptdfs[reference]!) / alpha, 0)]];
  }));
}
