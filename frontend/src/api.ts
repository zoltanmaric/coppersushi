import Ajv from 'ajv';
import addFormats from 'ajv-formats';
import schema from './contracts.json';
import type {CnecContracts} from './contracts';

const ajv = new Ajv();
addFormats(ajv);
ajv.addSchema(schema, 'cnec');
const validators = {
  day: ajv.compile<CnecContracts['day']>({$ref: 'cnec#/$defs/DayResponse'}),
  layer: ajv.compile<CnecContracts['layer']>({$ref: 'cnec#/$defs/LayerResponse'}),
  attribution: ajv.compile<CnecContracts['attribution']>({$ref: 'cnec#/$defs/AttributionPayload'}),
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
