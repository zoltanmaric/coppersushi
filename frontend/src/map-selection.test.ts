import {expect, test} from 'vitest';
import {mapSelection} from './map-selection';
import type {ConstraintOption} from './contracts';

const options: ConstraintOption[] = [
  {label: 'No constraint', value: '', source: 'constraints'},
  {label: 'Line', value: '1', source: 'constraints'},
  {label: 'Cap', value: '-2', source: 'attribution'},
];
const click = (value: unknown) => ({points: [{customdata: value}]});
const clear = {type: 'select', selected: null, source: 'constraints'};

test.each([undefined, null, {}, {points: null}])('absent or malformed events are ignored: %j', value => {
  expect(mapSelection(value, options, 1, true)).toBeNull();
});

test.each([{points: []}, {points: [{curveNumber: 0}]}, click(null), click([17]), click(['unknown'])])(
  'a background or non-constraint hit clears selection: %j', value => {
    expect(mapSelection(value, options, 1, true)).toEqual(clear);
    expect(mapSelection(value, options, null, true)).toBeNull();
  });

test('selects a valid constraint and retains its source', () => {
  expect(mapSelection(click(['-2']), options, 1, true)).toEqual({type: 'select', selected: -2, source: 'attribution'});
});

test('preserves the selected row on overlapping hits, otherwise follows option order', () => {
  expect(mapSelection(click(['1,-2']), options, -2, true)).toBeNull();
  expect(mapSelection(click(['1,-2']), options, null, true)).toEqual({type: 'select', selected: 1, source: 'constraints'});
});

test.each([{points: []}, click(['1'])])('loading or stale figures cannot change selection: %j', value => {
  expect(mapSelection(value, options, -2, false)).toBeNull();
});

test('a non-constraint first point does not hide later constraint hits', () => {
  const event = {points: [{curveNumber: 0}, {customdata: ['1']}, {customdata: ['-2']}]};
  expect(mapSelection(event, options, null, true)).toEqual({type: 'select', selected: 1, source: 'constraints'});
  expect(mapSelection(event, options, -2, true)).toBeNull();
});
