import type {MapBounds} from '../../map/initial-camera';
import Ajv from 'ajv';
import addFormats from 'ajv-formats';
import schema from './contracts.json';
import {PRICE_COLORSCALE} from '../../map/price-scale';
import type {Dataset} from './contracts';
import {renderHour,POWER_SCALE_MW} from './render';
import type {PlotlyFigure} from '../../map/figure';

export interface OpfHour {bounds:MapBounds;scale?:number;data:PlotlyFigure['data']; layout:{mapbox:Record<string,unknown>;[key:string]:unknown}}
export interface OpfManifest {generation:string; snapshots:string[]}
const ajv = new Ajv();
addFormats(ajv);
const manifest = ajv.compile<OpfManifest>({type:'object',required:['version','generation','snapshots'],additionalProperties:false,
  properties:{version:{const:2},generation:{type:'string',pattern:'^[a-f0-9]{24}$'},
    snapshots:{type:'array',minItems:1,uniqueItems:true,items:{type:'string',format:'date-time'}}}});
const base = '/data/opf/v2/opf-2024';
const dataset = ajv.compile<Dataset>(schema);
const metadataCache = new Map<string, Omit<Dataset,'intervals'>>();
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
  let metadata=metadataCache.get(generation);
  if(!metadata) {
    metadata=await read(`${generation}/metadata.json`,signal) as Omit<Dataset,'intervals'>;
  }
  const interval=await read(`${generation}/${index}.json`,signal);
  const candidate={...metadata,intervals:[interval]};
  if(!dataset(candidate)) throw new Error('Invalid Power Flow dataset');
  metadataCache.set(generation,metadata);
  const ids=new Set(metadata.nodes.map(node=>node.id));
  const branchKey=(branch:{component:string;name:string})=>JSON.stringify([branch.component,branch.name]);
  const branchIds=new Set(metadata.branches.map(branchKey));
  const values=candidate.intervals[0];
  if(ids.size!==metadata.nodes.length || branchIds.size!==metadata.branches.length ||
    metadata.branches.some(branch=>!ids.has(branch.bus0)||!ids.has(branch.bus1)) ||
    values.branches.length!==branchIds.size || new Set(values.branches.map(branchKey)).size!==branchIds.size ||
    values.branches.some(branch=>!branchIds.has(branchKey(branch))) || values.nodes.length!==ids.size)
    throw new Error('Incomplete Power Flow topology or interval');
  if(new Set(candidate.intervals[0].nodes.map(node=>node.node)).size!==ids.size || candidate.intervals[0].nodes.some(node=>!ids.has(node.node))) throw new Error('Incomplete Power Flow interval');
  const bounds:MapBounds = [
    Math.min(...metadata.nodes.map(n=>n.longitude)), Math.min(...metadata.nodes.map(n=>n.latitude)),
    Math.max(...metadata.nodes.map(n=>n.longitude)), Math.max(...metadata.nodes.map(n=>n.latitude)),
  ];
  const colorscale=PRICE_COLORSCALE;
  return {...renderHour(metadata,candidate.intervals[0],colorscale),scale:POWER_SCALE_MW,bounds} as OpfHour;
}
export function defaultHour(times:string[]):number {
  return times.reduce((best,time,index)=>Math.abs(Number(hour.format(new Date(time)))-12)<Math.abs(Number(hour.format(new Date(times[best])))-12)?index:best,0);
}
const hour = new Intl.DateTimeFormat('en-GB',{timeZone:'Europe/Brussels',hour:'2-digit',hourCycle:'h23'});
export const timeLabel = new Intl.DateTimeFormat('en-GB',{timeZone:'Europe/Brussels',hour:'2-digit',minute:'2-digit',hourCycle:'h23'});
export const fullLabel = new Intl.DateTimeFormat('en-GB',{timeZone:'Europe/Brussels',day:'numeric',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit',timeZoneName:'short',hourCycle:'h23'});
