// @vitest-environment jsdom
import React from 'react';
import {cleanup, fireEvent, render, screen} from '@testing-library/react';
import {afterEach, expect, test} from 'vitest';
import {Timeline, timelineTicks} from './timeline';
// Responses from the real calendar endpoint: hourly and quarter-hourly clock changes.
import calendars from '../fixtures/calendars.json';

afterEach(cleanup);

test.each([
  ['2024-08-29', 24], ['2024-10-27', 25], ['2026-03-29', 92], ['2026-10-25', 100],
] as const)('one tick per market interval on %s', (day, count) => {
  const ticks = timelineTicks(calendars[day].labels);
  expect(ticks).toHaveLength(count);
  expect(ticks[0].position).toBe(0);
  expect(ticks.at(-1)?.position).toBe(100);
  const labels = ticks.flatMap(t => t.time ? [t.time] : []);
  expect(new Set(labels).size).toBe(labels.length);
  expect(labels).toContain('00:00');
  expect(labels.some(label => label.startsWith('21:00'))).toBe(true);
});

test.each(['2024-10-27', '2026-10-25'] as const)('repeated DST intervals expose distinct accessible times on %s', day => {
  const labels=calendars[day].labels;
  const repeated=labels.flatMap((label,index)=>label.includes('· 02:00 ') ? [index] : []);
  const props={labels,disabled:false,onChange:()=>{}};
  const {rerender}=render(<Timeline {...props} interval={repeated[0]}/>);
  expect(screen.getByRole('slider').getAttribute('aria-valuetext')).toContain('02:00 CEST');
  rerender(<Timeline {...props} interval={repeated[1]}/>);
  expect(screen.getByRole('slider').getAttribute('aria-valuetext')).toContain('02:00 CET');
});

test('the rendered timeline exposes ticks without timezone labels and keyboard-sized interval steps', () => {
  const labels = calendars['2026-10-25'].labels;
  let selected = 0;
  const {container} = render(<Timeline labels={labels} interval={0} disabled={false} onChange={index => {selected = index;}}/>);
  expect(container.querySelectorAll('.cnec-tick')).toHaveLength(100);
  expect(container.querySelectorAll('.cnec-tick-major')).toHaveLength(8);
  expect(screen.getByText('03:00').textContent).toBe('03:00');
  const slider = screen.getByLabelText('Market interval');
  expect(slider.getAttribute('aria-valuetext')).toBe(labels[0]);
  expect(slider.getAttribute('max')).toBe('99');
  expect(slider.getAttribute('step')).toBe('1');
  fireEvent.change(slider, {target: {value: '12'}});
  expect(selected).toBe(12);
});
