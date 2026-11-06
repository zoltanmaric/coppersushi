import type {MarketInterval} from '../data/contracts';
import type {CoreZone} from './reference';

/** Normalized-FB contribution; missing inputs remain unavailable. */
export function contributions(
  interval: MarketInterval,
  id: number,
  reference: CoreZone,
): Partial<Record<CoreZone, number>> | null {
  const cap = interval.caps.find((r) => r.source_id === id);
  if (cap)
    return Object.fromEntries(
      Object.keys(interval.prices).map((z) => [
        z,
        cap.delta * ((z === "PL" ? 1 : 0) - (reference === "PL" ? 1 : 0)),
      ]),
    );
  const row = interval.constraints.find((r) => r.source_id === id),
    alpha = interval.alpha;
  if (
    !row ||
    alpha === null ||
    !(alpha > 0 && alpha <= 1) ||
    row.ptdfs[reference] === undefined
  )
    return null;
  return Object.fromEntries(
    Object.entries(row.ptdfs).map(([z, p]) => [
      z,
      (-row.shadow_price * (p - row.ptdfs[reference]!)) / alpha,
    ]),
  );
}
