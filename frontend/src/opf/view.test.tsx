// @vitest-environment jsdom
import React from 'react';
import {afterEach,expect,test,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import {OpfView} from './view';
vi.mock('../map/plot',()=>({Plot:({data,onRendered}:{data:{name:string}[];onRendered:()=>void})=>{
  React.useEffect(()=>{onRendered();},[data]);return <div data-testid="hour">{data[0].name}</div>;
}}));
afterEach(()=>{cleanup();vi.unstubAllGlobals();});
test('late response from an old selection cannot replace the selected hour',async()=>{
  const pending = new Map<string,(value:unknown)=>void>();
  vi.stubGlobal('fetch',vi.fn((url:string)=>url.endsWith('manifest.json') ? Promise.resolve({ok:true,json:async()=>({generation:'a'.repeat(24),snapshots:['2024-08-29T10:00:00Z','2024-08-29T11:00:00Z','2024-08-29T12:00:00Z']})}) : new Promise(resolve=>pending.set(url.split('/').at(-1)!,resolve))));
  const client = new QueryClient({defaultOptions:{queries:{retry:false}}});
  render(<QueryClientProvider client={client}><OpfView token="test"/></QueryClientProvider>);
  const slider = await screen.findByRole('slider');
  await waitFor(()=>expect(pending.has('0.json')).toBe(true));
  fireEvent.change(slider,{target:{value:'1'}});
  await waitFor(()=>expect(pending.has('1.json')).toBe(true));
  fireEvent.change(slider,{target:{value:'2'}});
  await waitFor(()=>expect(pending.has('2.json')).toBe(true));
  const reply=(i:number)=>pending.get(`${i}.json`)!({ok:true,json:async()=>({data:[{name:`hour ${i}`}],layout:{mapbox:{}}})});
  reply(2);
  await screen.findByText('hour 2');
  reply(1);reply(0);
  await waitFor(()=>expect(screen.getByTestId('hour').textContent).toBe('hour 2'));
});
