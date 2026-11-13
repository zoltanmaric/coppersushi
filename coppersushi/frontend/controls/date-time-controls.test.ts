import {expect, test} from 'vitest';
import {formatDay} from './date-time-controls';

test.each([
  ['2026-11-05', '5 Nov 2026'],
  ['2026-01-01', '1 Jan 2026'],
  ['2024-02-29', '29 Feb 2024'],
  ['2026-03-29', '29 Mar 2026'],
  ['2026-10-25', '25 Oct 2026'],
  ['2026-09-30', '30 Sept 2026'],
  ['2026-12-31', '31 Dec 2026'],
])('formats delivery day %s as a calendar date', (day, label) => {
  expect(formatDay(day)).toBe(label);
});
