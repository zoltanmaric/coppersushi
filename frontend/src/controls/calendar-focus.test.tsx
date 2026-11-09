// @vitest-environment jsdom
import React from 'react';
import {cleanup, fireEvent, render} from '@testing-library/react';
import {afterEach, expect, test, vi} from 'vitest';
import {DayPicker} from '@daypicker/react';
import {CalendarDayButton} from './date-time-controls';

afterEach(() => {cleanup(); vi.restoreAllMocks();});

test('calendar opening and arrow navigation focus days without scrolling the containing article', () => {
  const focus = vi.spyOn(HTMLButtonElement.prototype, 'focus');
  const selected = new Date('2026-11-03T00:00:00Z');
  render(<DayPicker mode="single" selected={selected} defaultMonth={selected} autoFocus timeZone="UTC"
    components={{DayButton: CalendarDayButton}}/>);
  expect(document.activeElement?.getAttribute('aria-label')).toContain('Tuesday, November 3rd, 2026');
  expect(focus).toHaveBeenLastCalledWith({preventScroll:true});
  fireEvent.keyDown(document.activeElement!, {key:'ArrowRight'});
  expect(document.activeElement?.getAttribute('aria-label')).toContain('Wednesday, November 4th, 2026');
  expect(focus.mock.calls.every(([options]) => options?.preventScroll === true)).toBe(true);
});
