import schema from './contracts.json';
import type {ViewRequest} from './contracts';

export type CoreZone = NonNullable<ViewRequest['reference']>;
export const CORE_ZONES = schema.$defs.ViewRequest.properties.reference.anyOf[0].enum as CoreZone[];
export function coreZone(value: unknown): CoreZone | null {
  return typeof value === 'string' && CORE_ZONES.some(zone => zone === value) ? value as CoreZone : null;
}
