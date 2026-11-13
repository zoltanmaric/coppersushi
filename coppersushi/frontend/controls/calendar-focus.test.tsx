// @vitest-environment jsdom
import React from 'react';
import {cleanup, render, screen} from '@testing-library/react';
import {afterEach, expect, test, vi} from 'vitest';
import {QueryClient, QueryClientProvider} from '@tanstack/react-query';
import {DateControls} from '../pages/cnec/date-time-controls';

afterEach(() => {cleanup(); vi.unstubAllGlobals();});

test('the mounted calendar does not take focus from the page', () => {
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response('',{status:404})));
  const client = new QueryClient({defaultOptions:{queries:{retry:false}}});
  render(<QueryClientProvider client={client}><button autoFocus>Outside calendar</button><DateControls day="2026-11-03" minDay="2026-11-01"
    onDay={vi.fn()}/></QueryClientProvider>);
  expect(document.activeElement).toBe(screen.getByRole('button',{name:'Outside calendar'}));
  client.clear();
});
