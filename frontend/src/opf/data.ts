import Ajv from 'ajv';
import addFormats from 'ajv-formats';
import type {PlotlyFigure} from '../map/figure';

export interface OpfHour {data:PlotlyFigure['data']; layout:{mapbox:Record<string,unknown>;[key:string]:unknown}}
export interface OpfManifest {generation:string; snapshots:string[]}
const ajv = new Ajv();
addFormats(ajv);
const manifest = ajv.compile<OpfManifest>({type:'object',required:['generation','snapshots'],additionalProperties:false,
  properties:{generation:{type:'string',pattern:'^[a-f0-9]{24}$'},
    snapshots:{type:'array',minItems:1,uniqueItems:true,items:{type:'string',format:'date-time'}}}});
const figure = ajv.compile<OpfHour>({type:'object',required:['data','layout'],
  properties:{data:{type:'array',items:{type:'object'}},layout:{type:'object',required:['mapbox'],properties:{mapbox:{type:'object'}}}}});
const base = '/data/opf/v1/opf-2024';
async function read(path:string,signal:AbortSignal):Promise<unknown> {
  const response = await fetch(`${base}/${path}`,{signal});
  if (!response.ok) throw new Error(`Power Flow data request failed (${response.status})`);
  return response.json();
}
export async function fetchManifest(signal:AbortSignal):Promise<OpfManifest> {
  const value = await read('manifest.json',signal);
  if (!manifest(value) || value.snapshots.some((t,i,a)=>i>0 && Date.parse(t)<=Date.parse(a[i-1]))) throw new Error('Invalid Power Flow manifest');
  return value;
}
export async function fetchHour(generation:string,index:number,signal:AbortSignal):Promise<OpfHour> {
  const value = await read(`${generation}/${index}.json`,signal);
  if (!figure(value)) throw new Error('Invalid Power Flow figure');
  return value;
}
export function defaultHour(times:string[]):number {
  return times.reduce((best,time,index)=>Math.abs(Number(hour.format(new Date(time)))-12)<Math.abs(Number(hour.format(new Date(times[best])))-12)?index:best,0);
}
const hour = new Intl.DateTimeFormat('en-GB',{timeZone:'Europe/Brussels',hour:'2-digit',hourCycle:'h23'});
export const timeLabel = new Intl.DateTimeFormat('en-GB',{timeZone:'Europe/Brussels',hour:'2-digit',minute:'2-digit',hourCycle:'h23'});
export const fullLabel = new Intl.DateTimeFormat('en-GB',{timeZone:'Europe/Brussels',day:'numeric',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit',timeZoneName:'short',hourCycle:'h23'});
