import {expect, test} from 'vitest';
import {viewFromUrl, viewSearch} from './view-url';
import {reduceSelection} from './state';
import {stepDay} from './date-time-controls';

test('a view round trips through a link without losing unrelated query or hash ownership', () => {
  const view = viewFromUrl('2026-11-03', '?interval=59&reference=BE&constraint=310503&embed=1');
  expect(view).toEqual({day: '2026-11-03', interval: 59, reference: 'BE', selected: 310503, source: 'constraints'});
  expect(viewSearch(view, '?embed=1')).toBe('?embed=1&interval=59&reference=BE&constraint=310503');
  expect(viewFromUrl(view.day, viewSearch(view, ''))).toEqual(view);
});

test('missing or malformed URL values use the initial view; cap identities retain their source', () => {
  expect(viewFromUrl('2026-10-25', '?interval=-2&reference=NO&constraint=NaN')).toEqual(
    {day: '2026-10-25', interval: 0, reference: 'DE', selected: null, source: 'constraints'});
  expect(viewFromUrl('2026-10-25', '?interval=12&constraint=-2').source).toBe('attribution');
  expect(viewFromUrl('2026-10-25', '?interval=8').interval).not.toBe(viewFromUrl('2026-10-25', '?interval=12').interval);
});

test('day navigation preserves reference, clears stale selection and steps across DST and year boundaries', () => {
  const view = viewFromUrl('2026-10-25', '?interval=12&reference=BE&constraint=-2');
  const next = reduceSelection(view, {type: 'day', day: stepDay(view.day, 1)});
  expect(next).toEqual({...view, day: '2026-10-26', interval: 0, selected: null, source: 'constraints'});
  expect(viewSearch(next, '?constraint=-2')).not.toContain('constraint');
  expect(stepDay('2026-12-31', 1)).toBe('2027-01-01');
});


test.each(['not-a-date', '2026-02-30', '2026-13-01', '2026-1-03', '0000-01-01'])(
  'rejects an invalid date route before calendar arithmetic: %s', day => {
    expect(() => viewFromUrl(day, '')).toThrow('Invalid delivery day');
  });
