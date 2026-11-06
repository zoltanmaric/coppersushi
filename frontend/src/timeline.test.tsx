// @vitest-environment jsdom
import React from 'react';
import {cleanup, fireEvent, render, screen} from '@testing-library/react';
import {afterEach, expect, test} from 'vitest';
import {Timeline, timelineTicks} from './timeline';
// Responses from the real calendar endpoint: hourly and quarter-hourly clock changes.
import calendars from './fixtures/calendars.json';

afterEach(cleanup);

test.each([
  ['2024-08-29', 24], ['2024-10-27', 25], ['2026-03-29', 92], ['2026-10-25', 100],
] as const)('one tick per market interval on %s', (day, count) => {
  const ticks = timelineTicks(calendars[day].labels);
  expect(ticks).toHaveLength(count);
  expect(ticks[0].position).toBe(0);
  expect(ticks.at(-1)?.position).toBe(100);
  const labels = ticks.filter(t => t.time).map(t => `${t.time} ${t.zone}`);
  expect(new Set(labels).size).toBe(labels.length);
  expect(labels).toContain('00:00 ' + (day === '2026-03-29' ? 'CET' : 'CEST'));
  expect(labels.some(label => label.startsWith('22:00'))).toBe(true);
});

test('both repeated two-o’clock labels remain distinguishable', () => {
  for (const day of ['2024-10-27', '2026-10-25'] as const) {
    const repeated = timelineTicks(calendars[day].labels).filter(t => t.time === '02:00');
    expect(repeated.map(t => t.zone)).toEqual(['CEST', 'CET']);
    expect(repeated[1].position).toBeGreaterThan(repeated[0].position);
  }
  expect(timelineTicks(calendars['2026-03-29'].labels).some(t => t.time === '02:00')).toBe(false);
});

test('the rendered timeline exposes ticks, timezone labels and keyboard-sized interval steps', () => {
  const labels = calendars['2026-10-25'].labels;
  let selected = 0;
  const {container} = render(<Timeline labels={labels} interval={0} disabled={false} onChange={index => {selected = index;}}/>);
  expect(container.querySelectorAll('.cnec-tick')).toHaveLength(100);
  expect(container.querySelectorAll('.cnec-tick-major')).toHaveLength(13);
  expect(screen.getAllByText('02:00').map(el => el.textContent)).toEqual(['02:00CEST', '02:00CET']);
  const slider = screen.getByLabelText('Market interval');
  expect(slider.getAttribute('aria-valuetext')).toBe(labels[0]);
  expect(slider.getAttribute('max')).toBe('99');
  expect(slider.getAttribute('step')).toBe('1');
  fireEvent.change(slider, {target: {value: '12'}});
  expect(selected).toBe(12);
});
