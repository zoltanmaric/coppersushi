import Ajv from 'ajv';
import addFormats from 'ajv-formats';
import schema from './contracts.json';
import type {Investigation, BindingInterval} from './contracts';
export type {Investigation, BindingInterval} from './contracts';
const ajv=new Ajv();addFormats(ajv);
const validStudy=ajv.compile<Investigation>(schema);
const validManifest=ajv.compile<{version:1;generation:string}>({type:'object',additionalProperties:false,required:['version','generation'],
  properties:{version:{const:1},generation:{type:'string',pattern:'^[0-9a-f]{24}$'}}});
const dayFormat=new Intl.DateTimeFormat('en-CA',{timeZone:'Europe/Brussels',year:'numeric',month:'2-digit',day:'2-digit'});
const labelFormat=new Intl.DateTimeFormat('en-GB',{timeZone:'Europe/Brussels',day:'2-digit',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit',timeZoneName:'short'});
export function intervalLabel(utc:string){return labelFormat.format(new Date(utc));}
export function shortfall(row:BindingInterval){return row.required.mw-row.procured.mw;}

export function parseStudy(value:unknown):Investigation {
  if(!validStudy(value))throw new Error('Invalid investigation data');
  const c=value.coverage,seen=new Set<string>();
  if(c.unknown || c.expected!==c.observed || c.binding+c.nonbinding!==c.observed || c.binding!==value.rows.length || c.shortfall_binding+c.no_shortfall_binding!==c.binding)
    throw new Error('Study population is incomplete or inconsistent');
  for(const row of value.rows){
    const instant=new Date(row.utc),key=instant.toISOString();
    if(seen.has(key)||dayFormat.format(instant)!==row.date||row.date<value.start||row.date>value.end||!value.generations[row.date])
      throw new Error('Inconsistent investigation interval identity');
    for(const reserve of [row.required,row.procured])
      if(Math.abs(reserve.products.reduce((a,b)=>a+b,0)-reserve.mw)>1e-7)throw new Error('Inconsistent reserve total');
    seen.add(key);
  }
  if(value.rows.filter(r=>shortfall(r)>0).length!==c.shortfall_binding)throw new Error('Graphic and table disagree');
  return value;
}
async function json(url:string){const response=await fetch(url);if(!response.ok)throw new Error(`Investigation data failed (${response.status})`);return response.json() as Promise<unknown>;}
export async function fetchStudy():Promise<Investigation>{
  const base='/data/cnec/studies/polish-export-caps';
  const manifest=await json(`${base}/manifest.json`);
  if(!validManifest(manifest))throw new Error('Invalid study manifest');
  return parseStudy(await json(`${base}/${manifest.generation}.json`));
}
