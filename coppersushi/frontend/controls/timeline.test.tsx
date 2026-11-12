// @vitest-environment jsdom
import React from 'react';
import {cleanup, fireEvent, render, screen} from '@testing-library/react';
import {afterEach, expect, test} from 'vitest';
import {Timeline, timelineLabels} from './timeline';
// Responses from the real calendar endpoint: hourly and quarter-hourly clock changes.
import calendars from '../fixtures/calendars.json';

afterEach(cleanup);

test.each([
  ['2024-08-29', '23:00'], ['2024-10-27', '23:00'], ['2026-03-29', '23:45'], ['2026-10-25', '23:45'],
] as const)('sparse clock labels follow the actual intervals on %s', (day, end) => {
  const marks = timelineLabels(calendars[day].labels);
  expect(marks.map(tick => tick.time)).toEqual(['00:00', '06:00', '12:00', '18:00', end]);
  expect(marks[0].position).toBe(0);
  expect(marks.at(-1)?.position).toBe(100);
  expect(marks.at(-1)?.index).toBe(calendars[day].labels.length - 1);
  for (const tick of marks) expect(calendars[day].labels[tick.index]).toContain(tick.time);
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

test('the sparse timeline preserves exact accessible times and quarter-hour steps', () => {
  const labels = calendars['2026-10-25'].labels;
  let selected = 0;
  render(<Timeline labels={labels} interval={0} disabled={false} onChange={index => {selected = index;}}/>);
  expect(screen.getByText('23:45')).toBeDefined();
  expect(screen.queryByText('03:00')).toBeNull();
  const slider = screen.getByLabelText('Market interval');
  expect(slider.getAttribute('aria-valuetext')).toBe(labels[0]);
  expect(slider.getAttribute('max')).toBe('99');
  expect(slider.getAttribute('step')).toBe('1');
  fireEvent.change(slider, {target: {value: '12'}});
  expect(selected).toBe(12);
});
