// @vitest-environment jsdom
import React from 'react';
import {act, cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, expect, test, vi} from 'vitest';
import {CnecPage} from './index';
import {reduceSelection} from './state';
import type {PlotlyFigure} from './contracts';

function CnecView(props: Omit<React.ComponentProps<typeof CnecPage>, 'selection' | 'onAction'> & {day: string}) {
  const [selection, onAction] = React.useReducer(reduceSelection, {
    day: props.day, interval: 0, reference: 'DE', selected: null, source: 'constraints',
  });
  return <CnecPage {...props} selection={selection} onAction={onAction}/>;
}

interface Pending {path: string; body?: {day: string; interval: number; selected: number | null}; resolve: (value: Response) => void}
let pending: Pending[];
let graph: PlotlyFigure;
let clickGraph: (change: {clickData: {points: {customdata: string[]}[]}}) => void;
vi.mock('./plot', () => ({Plot: (props: {data: PlotlyFigure['data']; layout: PlotlyFigure['layout']; onClick: (click: unknown) => void}) => {
  graph = {data: props.data, layout: props.layout};
  clickGraph = change => props.onClick(change.clickData);
  return <div aria-label="Map">{props.data.map(t=>t.name).join(',')}</div>;
}}));
beforeEach(() => {
  window.history.replaceState(null, "", "/cnec/2024-08-29");

  pending = [];
  vi.stubGlobal('fetch', vi.fn((url: string, options: RequestInit) => new Promise<Response>(resolve => {
    if (url.endsWith('/manifest.json')) {resolve(new Response(null, {status:404})); return;}
    pending.push({path: url, body: options.body ? JSON.parse(String(options.body)) : undefined, resolve});
  })));

});
afterEach(() => {cleanup(); vi.unstubAllGlobals();});

const interval = {index: 0, label: 'Thu 29 Aug 2024 · 00:00 CEST', prices: {DE: 100, FR: 90}, constraints: [], alpha: 1, caps: [], notes: []};
const first = {version: 1, day: '2024-08-29', labels: [interval.label, 'Thu 29 Aug 2024 · 00:15 CEST'], zones: [], elements: {}, intervals: [interval], price_range: [90, 100]};
const full = {...first, intervals: [interval, {...interval, index: 1, label: first.labels[1]}]};
async function reply(path: string, data: object, status = 200) {
  await waitFor(() => expect(pending.some(p => p.path.endsWith(path))).toBe(true));
  const index = pending.findIndex(p => p.path.endsWith(path));
  await act(async () => {pending.splice(index, 1)[0].resolve(new Response(JSON.stringify(data), {status}));});
}
async function open() {
  render(<CnecView id="cnec" day="2024-08-29" min_day="2024-01-01" token="token" basemap={{version: 8, sources: {}, layers: []}}/>);
  await reply('bundle/2024-08-29?interval=0', first);
}

test('show first interval, share background request, then navigate locally', async () => {
  await open();
  await waitFor(() => expect(graph.data.some(t => t.name === 'published day-ahead price')).toBe(true));
  await waitFor(() => expect(pending).toHaveLength(1));
  fireEvent.click(screen.getByRole('button', {name: 'Next interval'}));
  expect(screen.getByRole('status', {name: 'Map loading'})).toBeTruthy();
  expect(pending).toHaveLength(1);
  await reply('bundle/2024-08-29', full);
  await waitFor(() => expect(screen.queryByRole('status', {name: 'Map loading'})).toBeNull());
  fireEvent.change(screen.getByLabelText('Reference country'), {target: {value: 'FR'}});
  fireEvent.click(screen.getByRole('button', {name: 'Previous interval'}));
  fireEvent.click(screen.getByRole('button', {name: 'Next interval'}));
  expect(fetch).toHaveBeenCalledTimes(3);
});

test('background failure retains first interval and offers retry', async () => {
  await open();
  await reply('bundle/2024-08-29', {error: 'Not published yet'}, 503);
  await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('Not published yet'));
  await waitFor(() => expect(graph.data.some(t => t.name === 'published day-ahead price')).toBe(true));
  fireEvent.click(screen.getByRole('button', {name: 'Retry'}));
  await reply('bundle/2024-08-29', full);
  await waitFor(() => expect(screen.queryByRole('alert')).toBeNull());
});

test('pending interval identifies the data still on screen', async () => {
  await open();
  await waitFor(() => expect(pending).toHaveLength(1));
  fireEvent.click(screen.getByRole('button', {name: 'Next interval'}));
  expect(screen.getByRole('status', {name: 'Map loading'}).textContent).toContain('Showing 00:00 CEST');
  await reply('bundle/2024-08-29', {error: 'Unavailable'}, 503);
  await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('Showing 00:00 CEST'));
});

test('invalid initial interval can recover without a page reload', async () => {
  render(<CnecPage id="cnec" min_day="2024-01-01" token="token" basemap="dark"
    selection={{day:'2024-08-29',interval:999,reference:'DE',selected:null,source:'constraints'}} onAction={() => {}}/>);
  await reply('bundle/2024-08-29?interval=999', {error:'Interval is outside the selected market day'}, 400);
  fireEvent.click(await screen.findByRole('button', {name:'Go to first interval'}));
  await waitFor(() => expect(pending.some(p=>p.path.endsWith('?interval=0'))).toBe(true));
});

test('invalid bundle is rejected at the browser boundary', async () => {
  render(<CnecView id="cnec" day="2024-08-29" min_day="2024-01-01" token="token" basemap="dark"/>);
  await reply('bundle/2024-08-29?interval=0', {version:1});
  await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('Invalid bundle response'));
});

test('the mounted graph selects constraints using current interval options', async () => {
  await open();
  const row={source_id:42,name:'Published line',direction:'DIRECT',contingency:null,shadow_price:10,ram:100,capacity:200,geometry:null,ptdfs:{DE:0,FR:0.1}};
  await reply('bundle/2024-08-29', {...full,intervals:[interval,{...full.intervals[1],constraints:[row]}]});
  await waitFor(()=>expect(pending).toHaveLength(0));
  fireEvent.click(screen.getByRole('button',{name:'Next interval'}));
  await act(async()=>clickGraph({clickData:{points:[{customdata:['42']}]}}));
  expect(graph.data.some(t=>t.name==='ray contributions')).toBe(true);
  expect(fetch).toHaveBeenCalledTimes(3);
});
