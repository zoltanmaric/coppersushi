import React from 'react';
import {createRoot} from 'react-dom/client';
import Ajv from 'ajv';
import {CnecView} from './index';
import {marketDay} from '../../controls/market-day';
import {orderedMapLayers} from '../../map/map-layer-order';

interface Config {min_day: string; token: string}
interface Basemap {layers: {id: string; type: string}[]; sources: Record<string, {url?: string}>; glyphs: string; sprite: string}
const ajv = new Ajv();
const validConfig = ajv.compile<Config>({type:'object',required:['min_day','token'],additionalProperties:false,
  properties:{min_day:{type:'string'},token:{type:'string',minLength:1}}});
const validBasemap = ajv.compile<Basemap>({type:'object',required:['layers','sources','glyphs'],additionalProperties:true,
  properties:{layers:{type:'array',items:{type:'object',required:['id','type'],properties:{id:{type:'string'},type:{type:'string'}}}},
    sources:{type:'object',additionalProperties:{type:'object',properties:{url:{type:'string'}}}},glyphs:{type:'string'}}});
const root = createRoot(document.getElementById('app-root')!);
root.render(<div role="status">Loading map…</div>);
async function start() {
  const config: unknown = JSON.parse(document.getElementById('app-config')!.textContent!);
  if (!validConfig(config)) throw new Error('Invalid map configuration');
  const default_day = marketDay(new Date());
  const query = new URLSearchParams({access_token: config.token});
  const response = await fetch(`https://api.mapbox.com/styles/v1/mapbox/dark-v11?${query}`);
  if (!response.ok) throw new Error(`Basemap failed (${response.status})`);
  const style: unknown = await response.json();
  if (!validBasemap(style)) throw new Error('Invalid basemap style');
  style.layers = orderedMapLayers(style.layers.filter(layer => layer.type !== 'symbol'));
  style.sprite = new URL('/assets/cnec-markers', window.location.href).href;
  style.glyphs = `https://api.mapbox.com/fonts/v1/${style.glyphs.replace('mapbox://fonts/', '')}?${query}`;
  for (const source of Object.values(style.sources) as {url?: string}[]) {
    if (source.url?.startsWith('mapbox://')) source.url = `https://api.mapbox.com/v4/${source.url.slice(9)}.json?secure&${query}`;
  }
  root.render(<CnecView id="cnec-view" {...config} default_day={default_day} basemap={style as unknown as React.ComponentProps<typeof CnecView>['basemap']}/>);
}
start().catch(error => root.render(<div role="alert">{String(error)}</div>));
