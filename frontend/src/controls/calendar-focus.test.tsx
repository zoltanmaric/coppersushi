// @vitest-environment jsdom
import React from 'react';
import {act, cleanup, fireEvent, render, screen} from '@testing-library/react';
import {afterEach, expect, test, vi} from 'vitest';
import {QueryClient, QueryClientProvider} from '@tanstack/react-query';
import {DateTimeControls} from './date-time-controls';

afterEach(() => {cleanup(); vi.unstubAllGlobals();});

test.each([1, 0])(
  'opening the calendar (activation detail=%s) leaves focus on the trigger', detail => {
    vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response('',{status:404})));
    const client = new QueryClient({defaultOptions:{queries:{retry:false}}});
    render(<QueryClientProvider client={client}><DateTimeControls day="2026-11-03" minDay="2026-11-01"
      time="14:45 CET" previousDisabled={false} nextDisabled={false} onDay={vi.fn()}
      onPrevious={vi.fn()} onNext={vi.fn()}/></QueryClientProvider>);
    const trigger = screen.getByRole('button',{name:'Delivery day: 3 Nov 2026'});
    trigger.focus();
    fireEvent.click(trigger,{detail});
    // jsdom does not implement the browser's native popover toggle action.
    act(() => document.getElementById(trigger.getAttribute('popovertarget')!)!
      .dispatchEvent(Object.assign(new Event('toggle'),{newState:'open'})));
    expect(document.activeElement).toBe(trigger);
    client.clear();
  });
