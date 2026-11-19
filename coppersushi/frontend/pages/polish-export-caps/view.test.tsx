// @vitest-environment jsdom
import React from 'react';
import {afterEach,expect,test,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,within} from '@testing-library/react';
import {ExportCapView} from './view';
import type {PageProps} from '../cnec';

let mounts=0, renders=0;
vi.mock('../cnec',()=>({CnecPage:(props:PageProps)=>{
  React.useEffect(()=>{mounts++;},[]);renders++;
  return <div data-testid="map">{props.selection.day}/{props.selection.interval}
    <button onClick={()=>props.onCamera?.({lat:52,lon:20,zoom:5})}>Pan map</button>
  </div>;
}}));
afterEach(()=>{cleanup();mounts=0;renders=0;window.history.replaceState(null,'','/');});
test('cross-day timestamp changes preserve one map; sorting does not render it again',()=>{
  const reserve={status:'available' as const,mw:2000,products:[500,500,500,500] as [number,number,number,number],published_at:'2026-11-15T06:00:00Z'};
  const base={required:reserve,procured:reserve,cap:0,price:90};
  window.history.replaceState(null,'','/polish-export-caps');
  render(<ExportCapView min_day="2025-11-05" token="test" basemap={{}} study={{version:1,start:'2026-11-16',end:'2026-11-17',coverage:{expected:192,observed:192,unknown:0,binding:2,nonbinding:190,shortfall_binding:0,no_shortfall_binding:2},generations:{'2026-11-16':'a'.repeat(24),'2026-11-17':'b'.repeat(24)},sources:[],overlap_verified:0,rows:[
    {...base,date:'2026-11-16',utc:'2026-11-16T11:45:00Z',index:51,shadow:200},
    {...base,date:'2026-11-17',utc:'2026-11-17T04:45:00Z',index:23,shadow:100},
  ]}}/>);
  fireEvent.click(screen.getByText('Pan map'));
  fireEvent.click(screen.getByRole('link',{name:'17 Nov 2026, 05:45 CET'}));
  expect(screen.getByTestId('map').textContent).toContain('2026-11-17/23');
  expect(window.location.search).toContain('lat=52&lon=20&zoom=5');
  expect(mounts).toBe(1);
  const before=renders;
  fireEvent.click(screen.getByRole('button',{name:'Shortfall MW'}));
  expect(renders).toBe(before);
  expect(window.location.search).toContain('sort=shortfall');
  fireEvent.change(screen.getByLabelText('Shadow price minimum'),{target:{value:'150'}});
  fireEvent.submit(screen.getByLabelText('Shadow price minimum').closest('form')!);
  expect(screen.queryByRole('link',{name:'17 Nov 2026, 05:45 CET'})).toBeNull();
  expect(mounts).toBe(1);
  fireEvent.click(within(screen.getByLabelText('Shadow price minimum').closest('form')!).getByText('Clear'));
  expect(screen.getByRole('link',{name:'17 Nov 2026, 05:45 CET'})).toBeTruthy();
});
