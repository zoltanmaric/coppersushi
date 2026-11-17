import {viewFromUrl} from '../../controls/view-url';
import type {Selection} from '../../controls/state';
import type {MapCamera} from '../../map/camera';
import {shortfall, type BindingInterval} from './data';

export const columns = [
  {key:'utc',label:'Date & time',unit:''}, {key:'shadow',label:'Shadow price',unit:'€/MWh'},
  {key:'required',label:'Required reserve',unit:'MW'}, {key:'procured',label:'Procured reserve',unit:'MW'},
  {key:'shortfall',label:'Shortfall',unit:'MW'}, {key:'cap',label:'Export cap',unit:'MW'},
  {key:'price',label:'Polish day-ahead price',unit:'€/MWh'},
] as const;
export type SortKey = typeof columns[number]['key'];
export type NumericKey = Exclude<SortKey,'utc'>;
export type NumericFilters = Partial<Record<NumericKey,{min?:number;max?:number}>>;
export interface ViewState {selection: Selection; camera?: MapCamera; sort: SortKey; order: 'asc'|'desc'; from?:string; to?:string; filters:NumericFilters}
export function valueOf(row:BindingInterval,key:NumericKey):number {
  return key==='shortfall'?shortfall(row):key==='required'||key==='procured'?row[key].mw:row[key];
} 

export function readState(search: string, initial: BindingInterval): ViewState {
  const params = new URLSearchParams(search);
  const day = params.get('day') ?? initial.date;
  const selection = viewFromUrl(day, search);
  if (!params.has('interval')) selection.interval = params.has('day') ? 0 : initial.index;
  if (!params.has('reference')) selection.reference = 'PL';
  if (!params.has('constraint')) selection.selected = 'cap:PL';
  else if (params.get('constraint') === 'none') selection.selected = null;
  for (const [key,value] of [['interval',String(selection.interval)],['reference',selection.reference],['constraint',selection.selected ?? 'none']])
    if (params.has(key) && params.get(key) !== value) throw new Error(`Invalid ${key} in link`);
  const sort = params.get('sort') ?? 'shadow', order = params.get('order') ?? 'desc';
  if (!columns.some(c=>c.key===sort) || !['asc','desc'].includes(order)) throw new Error('Invalid table sort in link');
  let camera: MapCamera | undefined;
  if (['lat','lon','zoom'].some(key=>params.has(key))) {
    const values = ['lat','lon','zoom'].map(key=>{
      const raw=params.get(key);
      if (!raw?.trim() || !Number.isFinite(Number(raw))) throw new Error('Invalid map camera in link');
      return Number(raw);
    });
    const [lat,lon,zoom]=values;
    if (Math.abs(lat)>85.051129 || Math.abs(lon)>180 || zoom<0 || zoom>22) throw new Error('Map camera is outside supported bounds');
    camera={lat,lon,zoom};
  }
  const from=params.get('from')??undefined,to=params.get('to')??undefined;
  for(const day of [from,to])if(day!==undefined)viewFromUrl(day,'');
  if(from&&to&&from>to)throw new Error('Date range is reversed');
  const filters:NumericFilters={};
  for(const c of columns){
    if(c.key==='utc')continue;
    const range:{min?:number;max?:number}={};
    for(const bound of ['min','max'] as const){
      const key=c.key+(bound==='min'?'Min':'Max'), raw=params.get(key);
      if(raw!==null){
        if(!raw.trim()||!Number.isFinite(Number(raw)))throw new Error(`Invalid ${c.label} filter`);
        range[bound]=Number(raw);
      }
    }
    if(range.min!==undefined&&range.max!==undefined&&range.min>range.max)throw new Error(`Reversed ${c.label} range`);
    if(range.min!==undefined||range.max!==undefined)filters[c.key]=range;
  }
  return {selection,camera,sort:sort as SortKey,order:order as ViewState['order'],from,to,filters};
}
export function writeState(state: ViewState): string {
  const s=state.selection;
  const params=new URLSearchParams({day:s.day,interval:String(s.interval),reference:s.reference,constraint:s.selected ?? 'none'});
  if(state.sort!=='shadow') params.set('sort',state.sort);
  if(state.order!=='desc') params.set('order',state.order);
  if(state.camera) for(const key of ['lat','lon','zoom'] as const) params.set(key,String(Number(state.camera[key].toFixed(6))));
  if(state.from)params.set('from',state.from);
  if(state.to)params.set('to',state.to);
  for(const c of columns){if(c.key==='utc')continue;for(const bound of ['min','max'] as const){
    const value=state.filters[c.key]?.[bound];
    if(value!==undefined)params.set(c.key+(bound==='min'?'Min':'Max'),String(value));
  }}
  return `?${params}`;
}
export function sortRows(rows: BindingInterval[], sort: SortKey, order: ViewState['order']) {
  return [...rows].sort((a,b)=>{
    const comparison=sort==='utc' ? Date.parse(a.utc)-Date.parse(b.utc) : valueOf(a,sort)-valueOf(b,sort);
    return comparison*(order==='asc'?1:-1) || Date.parse(a.utc)-Date.parse(b.utc);
  });
}

export function filterRows(rows:BindingInterval[],state:ViewState){
  return rows.filter(row=>(!state.from||row.date>=state.from)&&(!state.to||row.date<=state.to)&&columns.every(c=>{
    if(c.key==='utc')return true;
    const range=state.filters[c.key],value=valueOf(row,c.key);
    return !range||((range.min===undefined||value>=range.min)&&(range.max===undefined||value<=range.max));
  }));
}
