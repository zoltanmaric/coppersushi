import Ajv from 'ajv';
import addFormats from 'ajv-formats';
import schema from './contracts.json';
import type {CnecContracts} from './contracts';

const ajv = new Ajv();
addFormats(ajv);
ajv.addSchema(schema, 'cnec');
const validators = {
  manifest: ajv.compile<CnecContracts['manifest']>({$ref: 'cnec#/$defs/DayManifest'}),
  metadata: ajv.compile<CnecContracts['metadata']>({$ref:'cnec#/$defs/DayMetadata'}),
  interval: ajv.compile<CnecContracts['interval']>({$ref:'cnec#/$defs/MarketInterval'}),
};

export async function fetchManifest(day: string, signal: AbortSignal): Promise<CnecContracts['manifest'] | null> {
  const response = await fetch(`/data/cnec/v3/${day}/manifest.json`, {signal});
  // Private S3 returns 403 for absent keys without bucket-list permission.
  if (response.status === 404 || response.status === 403) return null;
  if (!response.ok) throw new Error(`Publication request failed (${response.status})`);
  const payload: unknown = await response.json();
  if (!validators.manifest(payload) || payload.day !== day) throw new Error('Invalid day manifest');
  return payload;
}

export async function fetchDayPart<K extends 'metadata' | 'interval'>(kind: K, day: string, generation: string, index: number, signal: AbortSignal): Promise<CnecContracts[K]> {
  const file = kind === 'metadata' ? 'metadata' : index;
  const response = await fetch(`/data/cnec/v3/${day}/${generation}/${file}.json`, {signal});
  if (!response.ok) throw new Error(`Prepared data request failed (${response.status})`);
  const payload: unknown = await response.json();
  if (!validators[kind](payload)) throw new Error(`Invalid ${kind} response`);
  if (kind === 'metadata' && (payload as CnecContracts['metadata']).day !== day) throw new Error('Metadata belongs to another day');
  if (kind === 'interval' && (payload as CnecContracts['interval']).index !== index) throw new Error('Interval identity does not match its request');
  return payload as CnecContracts[K];
}
