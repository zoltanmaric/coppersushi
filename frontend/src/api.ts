import Ajv from 'ajv';
import addFormats from 'ajv-formats';
import schema from './contracts.json';
import type {CnecContracts} from './contracts';

const ajv = new Ajv();
addFormats(ajv);
ajv.addSchema(schema, 'cnec');
const validators = {
  manifest: ajv.compile<CnecContracts['manifest']>({$ref: 'cnec#/$defs/DayManifest'}),
  bundle: ajv.compile<CnecContracts['bundle']>({$ref: 'cnec#/$defs/DayBundle'}),
};

export async function fetchCnec<K extends keyof typeof validators>(
  kind: K, path: string, signal: AbortSignal, body?: object,
): Promise<CnecContracts[K]> {
  const response = await fetch(`/api/cnec/${path}`, {
    signal, ...(body ? {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)} : {}),
  });
  const payload: unknown = await response.json();
  if (!response.ok) {
    const error = ajv.compile<CnecContracts['error']>({$ref: 'cnec#/$defs/ApiError'});
    throw new Error(error(payload) ? payload.error : `Request failed (${response.status})`);
  }
  if (!validators[kind](payload)) throw new Error(`Invalid ${kind} response: ${ajv.errorsText(validators[kind].errors)}`);
  // The validator is selected by K and validates the same indexed contract.
  return payload as CnecContracts[K];
}

export async function fetchManifest(day: string, signal: AbortSignal): Promise<CnecContracts['manifest'] | null> {
  const response = await fetch(`/data/cnec/v1/${day}/manifest.json`, {signal});
  // Private S3 returns 403 for absent keys without bucket-list permission.
  if (response.status === 404 || response.status === 403) return null;
  if (!response.ok) throw new Error(`Publication request failed (${response.status})`);
  const payload: unknown = await response.json();
  if (!validators.manifest(payload) || payload.day !== day) throw new Error('Invalid day manifest');
  return payload;
}

export async function fetchBundle(day: string, interval: number | null, manifest: CnecContracts['manifest'] | null, signal: AbortSignal): Promise<CnecContracts['bundle']> {
  if (!manifest) return fetchCnec('bundle', `bundle/${day}${interval === null ? '' : `?interval=${interval}`}`, signal);
  const response = await fetch(`/data/cnec/v1/${day}/${manifest.generation}/${interval === null ? 'day' : interval}.json`, {signal});
  if (!response.ok) throw new Error(`Prepared data request failed (${response.status})`);
  const payload: unknown = await response.json();
  if (!validators.bundle(payload) || payload.day !== day) throw new Error('Invalid day bundle');
  return payload;
}
