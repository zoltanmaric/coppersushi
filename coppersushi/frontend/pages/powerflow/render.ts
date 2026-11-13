import type {Dataset, Interval} from './contracts';
import type {PlotlyFigure} from '../../map/figure';

/** Fixed symmetric saturation limits in MW, shared by map and legend. */
export const POWER_SCALE_MW = 150;

type Metadata = Omit<Dataset, 'intervals'>;
const escape = (text:string) => text.replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]!));
const number = (value:number) => String(Math.round(value*100)/100);
const identity = (branch:{component:string;name:string}) => JSON.stringify([branch.component,branch.name]);

/** Build presentation from validated network values; positive flow follows bus0 → bus1. */
export function renderHour(metadata:Metadata, interval:Interval, colorscale:unknown):PlotlyFigure {
  const nodes = new Map(metadata.nodes.map(node=>[node.id,node]));
  const branches = new Map(metadata.branches.map(branch=>[identity(branch),branch]));
  const loaded:{lon:(number|null)[];lat:(number|null)[]} = {lon:[],lat:[]};
  const easy:{lon:(number|null)[];lat:(number|null)[]} = {lon:[],lat:[]};
  const arrows:{lon:number[];lat:number[];angle:number[];text:string[]} = {lon:[],lat:[],angle:[],text:[]};
  for(const value of interval.branches) {
    const branch=branches.get(identity(value));
    if(!branch) throw new Error('Unknown Power Flow branch');
    const start=nodes.get(branch.bus0),end=nodes.get(branch.bus1);
    if(!start || !end) throw new Error('Unknown Power Flow endpoint');
    const target=branch.capacity_mw!==null && Math.abs(value.flow_mw)/branch.capacity_mw*100>99 ? loaded : easy;
    target.lon.push(start.longitude,end.longitude,null);target.lat.push(start.latitude,end.latitude,null);
    if(Math.abs(value.flow_mw)>.5) {
      arrows.lon.push(branch.midpoint_longitude);arrows.lat.push(branch.midpoint_latitude);
      arrows.angle.push(value.flow_mw>=0?branch.forward_bearing:branch.reverse_bearing);
      arrows.text.push(`<b>Flow:</b> ${Math.trunc(Math.abs(value.flow_mw))}/${branch.capacity_mw===null?'unknown':Math.trunc(branch.capacity_mw)} MW`);
    }
  }
  const lon:number[]=[],lat:number[]=[],text:string[]=[],power:number[]=[];
  for(const value of interval.nodes) {
    const node=nodes.get(value.node);if(!node) throw new Error('Unknown Power Flow node');
    lon.push(node.longitude);lat.push(node.latitude);power.push(value.net_power_mw);
    const generation=value.generators.map(g=>`<b>${escape(g.technology)}</b>: ${number(g.power_mw)}/${g.available_mw===null?'unknown':number(g.available_mw)} MW<br>`).join('\n<b>+</b> ');
    text.push(`<b>${escape(node.id)}</b> · ${escape(node.country)} · ${Math.trunc(node.voltage_kv)} kV<br>`+
      (generation?`<b>Generation:</b><br>${generation}--<br>`:'')+
      (value.load_mw===null?'':`<b>- Load</b>: ${number(value.load_mw)} MW<br>===<br>`)+
      `<b>= Net power: ${number(value.net_power_mw)} MW</b>`);
  }
  return {data:[
    {type:'scattermapbox',...loaded,mode:'lines',line:{width:4,color:'#a72af5'},hoverinfo:'none'},
    {type:'scattermapbox',...easy,mode:'lines',line:{width:.5,color:'gray'},hoverinfo:'none'},
    {type:'scattermapbox',lon:arrows.lon,lat:arrows.lat,text:arrows.text,mode:'markers',hoverinfo:'text',hoverlabel:{bgcolor:'#222',bordercolor:'#666',font:{color:'#eee'}},marker:{size:7,symbol:'triangle',angle:arrows.angle}},
    {type:'scattermapbox',lon,lat,text,mode:'markers',hoverinfo:'text',marker:{color:power,colorscale,reversescale:true,cmin:-POWER_SCALE_MW,cmax:POWER_SCALE_MW,size:power.map(Math.abs),sizemin:2.5,sizemode:'area',sizeref:(Math.max(...power.map(Math.abs))||1)/121}}
  ],layout:{paper_bgcolor:'#191a1a',uirevision:'opf-2024',showlegend:false,hovermode:'closest',margin:{l:0,r:0,t:0,b:0},mapbox:{style:'dark',center:{lat:53,lon:9},zoom:3.9,pitch:60}}};
}
