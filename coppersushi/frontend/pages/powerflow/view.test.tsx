// @vitest-environment jsdom
import React from 'react';
import {afterEach,expect,test,vi} from 'vitest';
import {act,cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import {OpfView} from './view';
const metadata={version:2,nodes:[{id:'n',longitude:1,latitude:2,country:'DE',voltage_kv:220}],branches:[],net_power_scale_mw:10};
const interval=(i:number)=>({timestamp:`2024-08-29T${10+i}:00:00Z`,nodes:[{node:'n',net_power_mw:i,load_mw:null,generators:[]}],branches:[]});
vi.mock('./render',()=>({POWER_SCALE_MW:150,renderHour:(_metadata:unknown,value:{nodes:{net_power_mw:number}[]})=>({data:[{name:`hour ${value.nodes[0].net_power_mw}`}],layout:{mapbox:{}}})}));
const plot = vi.hoisted(()=>({auto:true,complete:()=>{}}));
vi.mock('../../map/plot',()=>({Plot:({data,onRendered}:{data:{name:string}[];onRendered:()=>void})=>{
  React.useEffect(()=>{plot.complete=onRendered;if(plot.auto) onRendered();},[data]);return <div data-testid="hour">{data[0].name}</div>;
}}));
afterEach(()=>{cleanup();vi.unstubAllGlobals();plot.auto=true;});
test('late response from an old selection cannot replace the selected hour',async()=>{
  const pending = new Map<string,(value:unknown)=>void>();
  vi.stubGlobal('fetch',vi.fn((url:string)=>url.endsWith('manifest.json') ? Promise.resolve({ok:true,json:async()=>({version:2,generation:'a'.repeat(24),snapshots:['2024-08-29T10:00:00Z','2024-08-29T11:00:00Z','2024-08-29T12:00:00Z']})}) : url.endsWith('metadata.json') ? Promise.resolve({ok:true,json:async()=>metadata}) : new Promise(resolve=>pending.set(url.split('/').at(-1)!,resolve))));
  const client = new QueryClient({defaultOptions:{queries:{retry:false}}});
  render(<QueryClientProvider client={client}><OpfView token="test"/></QueryClientProvider>);
  const slider = await screen.findByRole('slider');
  await waitFor(()=>expect(pending.has('0.json')).toBe(true));
  fireEvent.change(slider,{target:{value:'1'}});
  await waitFor(()=>expect(pending.has('1.json')).toBe(true));
  fireEvent.change(slider,{target:{value:'2'}});
  await waitFor(()=>expect(pending.has('2.json')).toBe(true));
  const reply=(i:number)=>pending.get(`${i}.json`)!({ok:true,json:async()=>interval(i)});
  reply(2);
  await screen.findByText('hour 2');
  reply(1);reply(0);
  await waitFor(()=>expect(screen.getByTestId('hour').textContent).toBe('hour 2'));
});


test('loading stays visible until Plotly finishes the selected hour',async()=>{
  plot.auto=false;
  vi.stubGlobal('fetch',vi.fn((url:string)=>Promise.resolve({ok:true,json:async()=>url.endsWith('manifest.json')
    ? {version:2,generation:'a'.repeat(24),snapshots:['2024-08-29T10:00:00Z']}
    : url.endsWith('metadata.json') ? metadata : interval(0)})));
  const client = new QueryClient({defaultOptions:{queries:{retry:false}}});
  render(<QueryClientProvider client={client}><OpfView token="test"/></QueryClientProvider>);
  await screen.findByText('hour 0');
  expect(screen.getByText('Loading Power Flow…').getAttribute('role')).toBe('status');
  expect(screen.getByText(/loading selected hour/)).toBeTruthy();
  act(()=>plot.complete());
  await waitFor(()=>expect(screen.queryByText('Loading Power Flow…')).toBeNull());
  expect(screen.queryByText(/loading selected hour/)).toBeNull();
});
