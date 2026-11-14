// @vitest-environment jsdom
import React from 'react';
import {act, cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, expect, test, vi} from 'vitest';
import {CnecPage} from './index';
import {reduceSelection} from '../../controls/state';
import type {PlotlyFigure} from '../../map/figure';

function CnecView(props: Omit<React.ComponentProps<typeof CnecPage>, 'selection' | 'onAction'> & {day: string; interval?: number}) {
  const [selection, onAction] = React.useReducer(reduceSelection, {
    day: props.day, interval: props.interval ?? 0, reference: 'DE', selected: null,
  });
  return <CnecPage {...props} selection={selection} onAction={onAction}/>;
}

interface Pending {path: string; body?: {day: string; interval: number; selected: number | null}; resolve: (value: Response) => void}
let pending: Pending[];
let missNextPublication: boolean;
let graph: PlotlyFigure;
let clickGraph: (change: {clickData: unknown}) => void;
vi.mock('../../map/map-graph', () => ({MapGraph: (props: {figure: PlotlyFigure; onClick: (event: unknown) => void}) => {
  graph = props.figure;
  clickGraph = change => props.onClick(change.clickData);
  return <div aria-label="Map">{props.figure.data.map(t=>t.name).join(',')}</div>;
}}));
beforeEach(() => {
  window.history.replaceState(null, "", "/cnec/2024-08-29");

  pending = [];
  missNextPublication = false;
  vi.stubGlobal('fetch', vi.fn((url: string, options: RequestInit) => new Promise<Response>(resolve => {
    if (url.endsWith('/manifest.json')) {
      const selected = url.endsWith('/2024-08-29/manifest.json');
      const missing = !selected || missNextPublication;
      if (selected) missNextPublication = false;
      resolve(missing ? new Response(null,{status:404})
        : new Response(JSON.stringify({version:3,day:'2024-08-29',generation:'a'.repeat(24)})));
      return;
    }
    pending.push({path: url, body: options.body ? JSON.parse(String(options.body)) : undefined, resolve});
  })));

});
afterEach(() => {cleanup(); vi.unstubAllGlobals();});

const interval = {index: 0, label: 'Thu 29 Aug 2024 · 00:00 CEST', prices: {DE: 100, FR: 90}, constraints: [], alpha: 1, caps: [], notes: []};
const first = {version: 3, day: '2024-08-29', labels: [interval.label, 'Thu 29 Aug 2024 · 00:15 CEST'], zones: [{zone:'DE',name:'Germany',centre:[10,50],rings:[[[9,49],[11,49],[11,51],[9,49]]]},{zone:'FR',name:'France',centre:[2,47],rings:[[[1,46],[3,46],[3,48],[1,46]]]}], elements: {}, intervals: [interval], price_range: [90, 100]};
const full = {...first, intervals: [interval, {...interval, index: 1, label: first.labels[1]}]};
async function reply(path: string, data: object, status = 200) {
  await waitFor(() => expect(pending.some(p => p.path.endsWith(path))).toBe(true));
  const index = pending.findIndex(p => p.path.endsWith(path));
  await act(async () => {pending.splice(index, 1)[0].resolve(new Response(JSON.stringify(data), {status}));});
}
async function open() {
  const basemap={version:8,sources:{},layers:[]};
  render(<CnecView id="cnec" day="2024-08-29" min_day="2024-01-01" token="token" basemap={basemap}/>);
  const {intervals,...metadata}=first;
  await reply('/metadata.json',metadata);
  await reply('/0.json',interval);
  await waitFor(()=>expect(graph.data.some(t=>t.name==='published day-ahead price')).toBe(true));
  return basemap;
}

test('show first interval, share background request, then navigate locally', async () => {
  await open();
  await waitFor(() => expect(graph.data.some(t => t.name === 'published day-ahead price')).toBe(true));
  await waitFor(() => expect(pending).toHaveLength(1));
  fireEvent.click(screen.getByRole('button', {name: 'Next interval'}));
  expect(screen.getByRole('status', {name: 'Map loading'})).toBeTruthy();
  expect(pending).toHaveLength(1);
  await reply('/1.json', full.intervals[1]);
  await waitFor(() => expect(screen.queryByRole('status', {name: 'Map loading'})).toBeNull());
  fireEvent.change(screen.getByLabelText('Reference country'), {target: {value: 'FR'}});
  fireEvent.click(screen.getByRole('button', {name: 'Previous interval'}));
  fireEvent.click(screen.getByRole('button', {name: 'Next interval'}));
  expect(fetch).toHaveBeenCalledTimes(5);
});

test('background failure retains first interval and offers retry', async () => {
  await open();
  fireEvent.click(screen.getByRole('button',{name:'Next interval'}));
  await reply('/1.json', {error: 'Not published yet'}, 503);
  await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('Prepared data request failed (503)'));
  await waitFor(() => expect(graph.data.some(t => t.name === 'published day-ahead price')).toBe(true));
  fireEvent.click(screen.getByRole('button', {name: 'Retry'}));
  await reply('/1.json', full.intervals[1]);
  await waitFor(() => expect(screen.queryByRole('alert')).toBeNull());
});

test('pending interval identifies the data still on screen', async () => {
  await open();
  await waitFor(() => expect(pending).toHaveLength(1));
  fireEvent.click(screen.getByRole('button', {name: 'Next interval'}));
  expect(screen.getByRole('status', {name: 'Map loading'}).textContent).toContain('Showing 00:00 CEST');
  await reply('/1.json', {error: 'Unavailable'}, 503);
  await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('Showing 00:00 CEST'));
});

test('invalid initial interval can recover without a page reload', async () => {
  render(<CnecView id="cnec" day="2024-08-29" interval={999} min_day="2024-01-01" token="token" basemap="dark"/>);
  const {intervals,...metadata}=first;
  await reply('/metadata.json',metadata);
  fireEvent.click(await screen.findByRole('button', {name:'Go to first interval'}));
  await waitFor(() => expect(pending.some(p=>p.path.endsWith('/0.json'))).toBe(true));
});

test('invalid bundle is rejected at the browser boundary', async () => {
  render(<CnecView id="cnec" day="2024-08-29" min_day="2024-01-01" token="token" basemap="dark"/>);
  await reply('/metadata.json', {version:3});
  await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('Invalid metadata response'));
});

test('the mounted graph selects constraints using current interval options', async () => {
  await open();
  const row={source_id:42,eic:'11T0-0000-0984-D',name:'Published line',direction:'DIRECT',contingency:null,shadow_price:10,ram:100,capacity:200,geometry:null,ptdfs:{DE:0,FR:0.1}};
  await reply('/1.json', {...full.intervals[1],constraints:[row]});
  await waitFor(()=>expect(pending).toHaveLength(0));
  fireEvent.click(screen.getByRole('button',{name:'Next interval'}));
  await waitFor(async()=>{
    await act(async()=>clickGraph({clickData:{points:[{customdata:['11T0-0000-0984-D']}]}}));
    expect(graph.data.some(t=>t.name==='ray contributions')).toBe(true);
  });
  expect(fetch).toHaveBeenCalledTimes(5);
});

test('an unprepared day shows availability and never starts upstream work', async()=>{
  missNextPublication = true;
  render(<CnecView id="cnec" day="2024-08-29" min_day="2024-01-01" token="token" basemap="dark"/>);
  await screen.findByText(/Data is unavailable for this day/);
  expect(fetch).toHaveBeenCalledTimes(2);
  expect(pending).toHaveLength(0);
});

test('all remaining intervals start together and selection shares their in-flight requests',async()=>{
  const labels=Array.from({length:8},(_,i)=>`Thu 29 Aug 2024 · ${String(Math.floor(i/4)).padStart(2,'0')}:${String(i%4*15).padStart(2,'0')} CEST`);
  render(<CnecView id="cnec" day="2024-08-29" min_day="2024-01-01" token="token" basemap="dark"/>);
  const {intervals,...metadata}=first;
  await reply('/metadata.json',{...metadata,labels});
  await reply('/0.json',interval);
  await waitFor(()=>expect(pending).toHaveLength(7));
  const started=vi.mocked(fetch).mock.calls.filter(([url])=>String(url).endsWith('/1.json')).length;
  fireEvent.change(screen.getByRole('slider',{name:'Market interval'}),{target:{value:'1'}});
  expect(vi.mocked(fetch).mock.calls.filter(([url])=>String(url).endsWith('/1.json'))).toHaveLength(started);
  fireEvent.change(screen.getByRole('slider',{name:'Market interval'}),{target:{value:'7'}});
  await waitFor(()=>expect(pending.some(p=>p.path.endsWith('/7.json'))).toBe(true));
  const call = vi.mocked(fetch).mock.calls.find(([url])=>String(url).endsWith('/1.json'))!;
  expect((call[1]?.signal as AbortSignal).aborted).toBe(false);
  await reply('/7.json',{...interval,index:7,label:labels[7]});
  await waitFor(()=>expect(screen.queryByRole('status',{name:'Map loading'})).toBeNull());
  expect(vi.mocked(fetch).mock.calls.filter(([url])=>String(url).endsWith('/7.json'))).toHaveLength(1);
});

test('an invalid deep link recovers when the slider chooses a valid interval',async()=>{
  render(<CnecView id="cnec" day="2024-08-29" interval={999} min_day="2024-01-01" token="token" basemap="dark"/>);
  const {intervals,...metadata}=first;
  await reply('/metadata.json',metadata);
  await screen.findByText(/This interval is outside/);
  fireEvent.change(screen.getByRole('slider',{name:'Market interval'}),{target:{value:'1'}});
  await reply('/1.json',full.intervals[1]);
  await waitFor(()=>expect(graph.data.some(t=>t.name==='published day-ahead price')).toBe(true));
  expect(screen.queryByRole('alert')).toBeNull();
});

test('an unavailable day is rechecked automatically, then polling stops after publication', async () => {
  vi.useFakeTimers();
  try {
    missNextPublication = true;
    render(<CnecView id="cnec" day="2024-08-29" min_day="2024-01-01" token="token" basemap="dark"/>);
    await act(async () => {await vi.advanceTimersByTimeAsync(1);});
    const before = vi.mocked(fetch).mock.calls.filter(([url])=>String(url).endsWith('/2024-08-29/manifest.json')).length;
    await act(async () => {await vi.advanceTimersByTimeAsync(60_000);});
    expect(vi.mocked(fetch).mock.calls.filter(([url])=>String(url).endsWith('/2024-08-29/manifest.json'))).toHaveLength(before+1);
    await act(async () => {await vi.advanceTimersByTimeAsync(120_000);});
    expect(vi.mocked(fetch).mock.calls.filter(([url])=>String(url).endsWith('/2024-08-29/manifest.json'))).toHaveLength(before+1);
  } finally {cleanup(); vi.useRealTimers();}
});

test.each(['pending','failed'])('selection can leave a %s initial interval', async state => {
  render(<CnecView id="cnec" day="2024-08-29" min_day="2024-01-01" token="token" basemap="dark"/>);
  const {intervals,...metadata}=first;
  await reply('/metadata.json',metadata);
  await waitFor(()=>expect((screen.getByRole('button',{name:'Next interval'}) as HTMLButtonElement).disabled).toBe(false));
  if (state === 'failed') await reply('/0.json',{},503);
  fireEvent.click(screen.getByRole('button',{name:'Next interval'}));
  await reply('/1.json',full.intervals[1]);
  await waitFor(()=>expect(graph.data.some(t=>t.name==='published day-ahead price')).toBe(true));
  expect(screen.queryByRole('alert')).toBeNull();
});

test('day loading retains the slider geometry and selected time',async()=>{
  await open();
  const slider=screen.getByRole('slider',{name:'Market interval'});
  const ticks=document.querySelectorAll('.cnec-tick').length;
  vi.mocked(fetch).mockImplementationOnce(()=>new Promise(()=>{}));
  fireEvent.click(screen.getByRole('button',{name:'Next day'}));
  await screen.findByRole('status',{name:'Map loading'});
  expect(screen.getByRole('slider',{name:'Market interval'})).toBe(slider);
  expect(slider.getAttribute('max')).toBe('1');
  expect(slider.getAttribute('value')).toBe('0');
  expect(document.querySelectorAll('.cnec-tick')).toHaveLength(ticks);
  expect(document.querySelector('.cnec-control-row output')?.textContent).toBe('00:00 CEST');
  expect(document.querySelector('.cnec-time-controls')?.getAttribute('aria-busy')).toBe('true');
});


test('legend bounds appear from metadata before an interval or market figure is ready',async()=>{
  render(<CnecView id="cnec" day="2024-08-29" min_day="2024-01-01" token="token" basemap="dark"/>);
  const legend=screen.getByLabelText('Daily day-ahead price scale');
  const slots=legend.querySelector('.cnec-price-range')!;
  expect(screen.getByText('Day-ahead · €/MWh')).toBeTruthy();
  expect(slots.textContent).toBe('\u00a0\u00a0');
  const {intervals,...metadata}=first;
  await reply('/metadata.json',metadata);
  await waitFor(()=>expect(slots.textContent).toBe('90100'));
  expect(screen.getByLabelText('Daily day-ahead price scale')).toBe(legend);
  expect(graph.data.some(trace=>trace.type==='choroplethmapbox')).toBe(false);
  expect(screen.getByRole('status',{name:'Map loading'})).toBeTruthy();
});
