import {expect, test} from 'vitest';
import {reserveTooltip} from './day-figure';
import type {MarketInterval} from './data/contracts';
import evidence from './reserve-evidence.json';
test('publication times are Brussels winter time and keep independent values', () => {
  const text = reserveTooltip(evidence as MarketInterval);
  expect(text).toContain('2,347 MW');
  expect(text).toContain('07:06');
  expect(text).toContain('09:10');
  expect(text).toContain('2026');
  expect(text).toContain('Matching totals');
});
