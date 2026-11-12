// @vitest-environment jsdom
import React from 'react';
import {act, cleanup, render, screen, waitFor} from '@testing-library/react';
import {QueryClient, QueryClientProvider} from '@tanstack/react-query';
import {afterEach, expect, test, vi} from 'vitest';
import {DateTimeControls} from '../pages/cnec/date-time-controls';
import {marketDay} from './market-day';

const props = {day:'2026-11-09', minDay:'2026-11-01', time:'00:00 CET',
  previousDisabled:true, nextDisabled:false, onDay:vi.fn(), onPrevious:vi.fn(), onNext:vi.fn()};

afterEach(() => {cleanup(); vi.useRealTimers(); vi.unstubAllGlobals();});

test('tomorrow enables asynchronously from its manifest and shares the publication cache', async () => {
  vi.useFakeTimers({toFake:['Date']});
  vi.setSystemTime(new Date('2026-11-09T10:00:00Z'));
  const client = new QueryClient({defaultOptions:{queries:{retry:false}}});
  const fetch = vi.fn().mockResolvedValueOnce(new Response('',{status:404}))
    .mockResolvedValueOnce(new Response(JSON.stringify({version:2,day:'2026-11-10',generation:'a'.repeat(24)})));
  vi.stubGlobal('fetch',fetch);
  const view = render(<QueryClientProvider client={client}><DateTimeControls {...props}/></QueryClientProvider>);
  const next = () => screen.getByRole('button',{name:'Next day'}) as HTMLButtonElement;
  expect(next().disabled).toBe(true);
  await waitFor(() => expect(client.getQueryData(['publication','2026-11-10'])).toBeNull());
  expect(next().disabled).toBe(true);
  await act(async () => {await client.refetchQueries({queryKey:['publication','2026-11-10']});});
  await waitFor(() => expect(next().disabled).toBe(false));
  expect(fetch.mock.calls.map(call=>call[0])).toEqual([
    '/data/cnec/v2/2026-11-10/manifest.json','/data/cnec/v2/2026-11-10/manifest.json']);
  view.rerender(<QueryClientProvider client={client}><DateTimeControls {...props} day="2026-11-10"/></QueryClientProvider>);
  expect(next().disabled).toBe(true);
  client.clear();
});

test('market date and an open page roll over at Brussels midnight', async () => {
  expect(marketDay(new Date('2026-11-09T23:01:00Z'))).toBe('2026-11-10');
  expect(marketDay(new Date('2026-07-09T22:01:00Z'))).toBe('2026-07-10');
  vi.useFakeTimers({toFake:['Date']});
  vi.setSystemTime(new Date('2026-11-09T22:59:00Z'));
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response('',{status:404})));
  const client = new QueryClient({defaultOptions:{queries:{retry:false}}});
  render(<QueryClientProvider client={client}><DateTimeControls {...props} day="2026-11-10"/></QueryClientProvider>);
  await waitFor(() => expect(client.getQueryData(['publication','2026-11-10'])).toBeNull());
  vi.setSystemTime(new Date('2026-11-09T23:01:00Z'));
  act(() => window.dispatchEvent(new Event('focus')));
  await waitFor(() => expect(fetch).toHaveBeenCalledWith('/data/cnec/v2/2026-11-11/manifest.json',expect.anything()));
  client.clear();
});
