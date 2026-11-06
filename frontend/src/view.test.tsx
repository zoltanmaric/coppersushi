// @vitest-environment jsdom
import React from 'react';
import {act, cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, expect, test, vi} from 'vitest';
import {CnecPage} from './index';
import responses from './fixtures/responses.json';
import type {PlotlyFigure} from './contracts';

function CnecView(props: Omit<React.ComponentProps<typeof CnecPage>, 'navigate'>) {
  const [day, navigate] = React.useState(props.day);
  return <CnecPage {...props} day={day} navigate={navigate}/>;
}

interface Pending {path: string; body?: {day: string; interval: number; selected: number | null}; resolve: (value: Response) => void}
let pending: Pending[];
let graph: PlotlyFigure;
let clickGraph: (change: {clickData: {points: {customdata: string[]}[]}}) => void;
beforeEach(() => {
  window.history.replaceState(null, "", "/cnec/2024-08-29");

  pending = [];
  vi.stubGlobal('fetch', vi.fn((url: string, options: RequestInit) => new Promise<Response>(resolve => {
    pending.push({path: url, body: options.body ? JSON.parse(String(options.body)) : undefined, resolve});
  })));
  Object.assign(window, {dash_core_components: {Graph: (props: {figure: PlotlyFigure; setProps: typeof clickGraph}) => {
    clickGraph = props.setProps;
    graph = props.figure;
    return <div aria-label="Map">{props.figure.data.map(t => t.name).join(',')}</div>;
  }}});
});
afterEach(() => {cleanup(); vi.unstubAllGlobals();});

async function reply(path: string, data: object, selected?: number | null, status = 200) {
  await waitFor(() => expect(pending.some(p => p.path.endsWith(path) && (selected === undefined || p.body?.selected === selected))).toBe(true));
  const index = pending.findIndex(p => p.path.endsWith(path) && (selected === undefined || p.body?.selected === selected));
  await act(async () => {pending.splice(index, 1)[0].resolve(new Response(JSON.stringify(data), {status}));});
}
async function open() {
  render(<CnecView id="cnec" day="2024-08-29" min_day="2024-01-01" token="token" basemap={{version: 8, sources: {}, layers: []}}/>);
  await reply('day/2024-08-29', responses.day);
}

test('first map appears after its layers settle', async () => {
  await open();
  await reply('prices', responses.prices);
  expect(screen.getByLabelText('Map').textContent).not.toContain('prices');
  await waitFor(() => expect(screen.getByRole('status', {name: 'Map loading'}).textContent).toBe('Loading constraints…'));
  await reply('constraints', responses.constraints);
  expect(screen.getByLabelText('Map').textContent).not.toContain('binding lines');
  await waitFor(() => expect(screen.getByRole('status', {name: 'Map loading'}).textContent).toBe('Loading price contributions…'));
  expect(pending.some(p => p.path.endsWith('attribution/2024-08-29'))).toBe(true);
  await waitFor(() => expect(screen.getByRole('status', {name: 'Map loading'}).textContent).toBe('Loading price contributions…'));
  expect(screen.getByLabelText('Map').textContent).not.toContain('prices');
  await reply('attribution/2024-08-29', responses.attribution);
  await reply('enriched', responses.caps, null);
  await waitFor(() => expect(screen.getByLabelText('Map').textContent).toContain('country cap'));
  expect(graph.layout.uirevision).toBe('cnec-camera');
});

test('late results from the previous day never appear on the new day', async () => {
  await open();
  await waitFor(() => expect(pending.some(p => p.path.endsWith('prices'))).toBe(true));
  fireEvent.change(screen.getByLabelText('Delivery day'), {target: {value: '2024-08-30'}});
  await reply('prices', responses.prices);
  await reply('constraints', responses.constraints);
  expect(screen.getByLabelText('Map').textContent).not.toContain('prices');
  expect(screen.getByLabelText('Map').textContent).not.toContain('binding lines');
  expect((screen.getByLabelText('Delivery day') as HTMLInputElement).value).toBe('2024-08-30');
});

test('attribution failure stays visible without removing prices or constraints; retry is targeted', async () => {
  await open();
  await reply('prices', responses.prices);
  await reply('constraints', responses.constraints);
  await reply('attribution/2024-08-29', {error: 'JAO unavailable'}, undefined, 500);
  await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('JAO unavailable'));
  expect(screen.getByLabelText('Map').textContent).toContain('binding lines');
  expect(screen.getByLabelText('Map').textContent).toContain('prices');
  fireEvent.click(screen.getByText('Retry'));
  await waitFor(() => expect(pending.filter(p => p.path.includes('attribution'))).toHaveLength(1));
  expect(pending.some(p => p.path.endsWith('prices') || p.path.endsWith('constraints'))).toBe(false);
});

test('an interval change clears old layers and late contributions cannot restore them', async () => {
  await open();
  await reply('prices', responses.prices);
  await reply('constraints', responses.constraints);
  await reply('attribution/2024-08-29', responses.attribution);
  await waitFor(() => expect(pending.some(p => p.path.endsWith('enriched'))).toBe(true));
  fireEvent.click(screen.getByRole('button', {name: 'Next interval'}));
  await reply('enriched', responses.enriched, null);
  expect(screen.getByLabelText('Map').textContent).not.toContain('contributions');
  expect((screen.getByLabelText('Market interval') as HTMLInputElement).value).toBe('1');
});

test('a single enrichment error produces one alert, and a failed calendar stops loading', async () => {
  await open();
  await reply('prices', responses.prices);
  await reply('constraints', responses.constraints);
  await reply('attribution/2024-08-29', responses.attribution);
  await reply('enriched', {error: 'render failed'}, null, 500);
  await waitFor(() => expect(screen.getAllByRole('alert')).toHaveLength(1));
  fireEvent.change(screen.getByLabelText('Delivery day'), {target: {value: '2024-08-30'}});
  await reply('day/2024-08-30', {error: 'calendar failed'}, undefined, 500);
  await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('calendar failed'));
  expect(screen.queryByRole('status', {name: 'Map loading'})).toBeNull();
});

test('invalid API payloads are visible errors, never successful empty layers', async () => {
  await open();
  await reply('prices', {unexpected: true});
  await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('Invalid layer response'));
  expect(screen.getByLabelText('Map').textContent).not.toContain('prices');
});


test('a loaded interval remains unchanged until the next interval layers settle', async () => {
  await open();
  await reply('prices', responses.prices);
  await reply('constraints', responses.constraints);
  await reply('attribution/2024-08-29', responses.attribution);
  await reply('enriched', responses.caps, null);
  await waitFor(() => expect(graph.data.some(t => t.name === 'country cap')).toBe(true));
  const displayed = graph;
  fireEvent.click(screen.getByRole('button', {name: 'Next interval'}));
  expect(graph).toBe(displayed);
  await reply('prices', {...responses.prices, request: {...responses.prices.request, interval: 1}});
  expect(graph).toBe(displayed);
  await reply('constraints', {...responses.constraints, request: {...responses.constraints.request, interval: 1}}, null);
  expect(graph).toBe(displayed);
  act(() => clickGraph({clickData: {points: [{customdata: ['1']}]}}));
  expect(pending.some(p => p.body?.selected !== null && p.body?.selected !== undefined)).toBe(false);
  await reply('enriched', {...responses.caps, request: {...responses.caps.request, interval: 1}}, null);
  await waitFor(() => expect(graph).not.toBe(displayed));
  expect(graph.data.map(t => t.uid)).toEqual(displayed.data.map(t => t.uid));
});


test('the initially bound graph callback selects constraints loaded later', async () => {
  await open();
  const initialClick = clickGraph;
  await reply('constraints', responses.constraints);
  await reply('prices', responses.prices);
  await reply('attribution/2024-08-29', responses.attribution);
  await reply('enriched', responses.caps, null);
  await waitFor(() => expect(graph.data.some(t => t.name === 'country cap')).toBe(true));
  act(() => initialClick({clickData: {points: [{customdata: ['-1']}]}}));
  await waitFor(() => expect(pending.some(p => p.body?.selected === -1)).toBe(true));
});


test('shows a specific unavailable attribution reason', async () => {
  await open();
  await reply('prices', responses.prices);
  await reply('constraints', responses.constraints);
  await reply('attribution/2024-08-29', {...responses.attribution, complete: false});
  await waitFor(() => expect(pending.some(p => p.path.endsWith('enriched'))).toBe(true));
  expect(screen.queryByText('Some attribution inputs are unavailable.')).toBeNull();
  expect(screen.queryByText('Poland cap attribution unavailable for this interval.')).toBeNull();
  await reply('enriched', {...responses.caps, notes: ['Poland cap attribution unavailable for this interval.']}, null);
  await waitFor(() => expect(screen.getByText('Poland cap attribution unavailable for this interval.')).toBeTruthy());
});

test('delivery picker rejects dates before the supported window', async () => {
  render(<CnecView id="cnec" day="2025-11-05" min_day="2025-11-05" token="token" basemap={{version: 8, sources: {}, layers: []}}/>);
  const picker = screen.getByLabelText('Delivery day') as HTMLInputElement;
  expect(picker.min).toBe('2025-11-05');
  fireEvent.change(picker, {target: {value: '2025-11-04'}});
  expect(picker.value).toBe('2025-11-05');
});

test('date selection delegates to the host without touching browser history', async () => {
  await open();
  window.history.replaceState(null, '', '/cnec/2024-08-29?view=map#detail');
  fireEvent.change(screen.getByLabelText('Delivery day'), {target: {value: '2024-08-30'}});
  expect((screen.getByLabelText('Delivery day') as HTMLInputElement).value).toBe('2024-08-30');
  expect(window.location.pathname).toBe('/cnec/2024-08-29');
  expect(window.location.search).toBe('?view=map');
  expect(window.location.hash).toBe('#detail');
});
