import schema from '../data/contracts.json';
import type {ZoneGeometry} from '../data/contracts';

export type CoreZone = ZoneGeometry['zone'];
export const CORE_ZONES = schema.$defs.ZoneGeometry.properties.zone.enum as CoreZone[];
export function coreZone(value: unknown): CoreZone | null {
  return typeof value === 'string' && CORE_ZONES.some(zone => zone === value) ? value as CoreZone : null;
}
