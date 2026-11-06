import React from 'react';
import {createRoot} from 'react-dom/client';
import Ajv from 'ajv';
import {CnecView} from './index';

interface Config {default_day: string; min_day: string; token: string}
interface Basemap {layers: {id: string; type: string}[]; sources: Record<string, {url?: string}>; glyphs: string; sprite: string}
const ajv = new Ajv();
const validConfig = ajv.compile<Config>({type:'object',required:['default_day','min_day','token'],additionalProperties:false,
  properties:{default_day:{type:'string'},min_day:{type:'string'},token:{type:'string',minLength:1}}});
const validBasemap = ajv.compile<Basemap>({type:'object',required:['layers','sources','glyphs'],additionalProperties:true,
  properties:{layers:{type:'array',items:{type:'object',required:['id','type'],properties:{id:{type:'string'},type:{type:'string'}}}},
    sources:{type:'object',additionalProperties:{type:'object',properties:{url:{type:'string'}}}},glyphs:{type:'string'}}});
const root = createRoot(document.getElementById('cnec-root')!);
root.render(<div role="status">Loading map…</div>);
async function start() {
  const config: unknown = JSON.parse(document.getElementById('cnec-config')!.textContent!);
  if (!validConfig(config)) throw new Error('Invalid map configuration');
  const parts = new Intl.DateTimeFormat('en-CA', {timeZone:'Europe/Brussels',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date());
  config.default_day = ['year','month','day'].map(type => parts.find(part => part.type === type)!.value).join('-');
  const query = new URLSearchParams({access_token: config.token});
  const response = await fetch(`https://api.mapbox.com/styles/v1/mapbox/dark-v11?${query}`);
  if (!response.ok) throw new Error(`Basemap failed (${response.status})`);
  const style: unknown = await response.json();
  if (!validBasemap(style)) throw new Error('Invalid basemap style');
  style.layers = style.layers.filter((layer: {type: string}) => layer.type !== 'symbol');
  style.sprite = new URL('/assets/cnec-markers', window.location.href).href;
  style.glyphs = `https://api.mapbox.com/fonts/v1/${style.glyphs.replace('mapbox://fonts/', '')}?${query}`;
  for (const source of Object.values(style.sources) as {url?: string}[]) {
    if (source.url?.startsWith('mapbox://')) source.url = `https://api.mapbox.com/v4/${source.url.slice(9)}.json?secure&${query}`;
  }
  root.render(<CnecView id="cnec-view" {...config} basemap={style as unknown as React.ComponentProps<typeof CnecView>['basemap']}/>);
}
start().catch(error => root.render(<div role="alert">{String(error)}</div>));
