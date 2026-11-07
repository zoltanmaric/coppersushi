import {expect, test} from 'vitest';
import {mapSelection} from './map-selection';
import type {ConstraintOption} from './figure';

const options: ConstraintOption[] = [
  {label: 'No constraint', value: '', source: 'constraints'},
  {label: 'Line', value: '11T0-0000-0984-D', source: 'constraints'},
  {label: 'Cap', value: 'cap:PL', source: 'attribution'},
];
const click = (value: unknown) => ({points: [{customdata: value}]});
const clear = {type: 'select', selected: null, source: 'constraints'};

test.each([undefined, null, {}, {points: null}])('absent or malformed events are ignored: %j', value => {
  expect(mapSelection(value, options, '11T0-0000-0984-D', true)).toBeNull();
});

test.each([{points: []}, {points: [{curveNumber: 0}]}, click(null), click([17]), click(['unknown'])])(
  'a background or non-constraint hit clears selection: %j', value => {
    expect(mapSelection(value, options, '11T0-0000-0984-D', true)).toEqual(clear);
    expect(mapSelection(value, options, null, true)).toBeNull();
  });

test('selects a valid constraint and retains its source', () => {
  expect(mapSelection(click(['cap:PL']), options, '11T0-0000-0984-D', true)).toEqual({type: 'select', selected: 'cap:PL', source: 'attribution'});
});

test('preserves the selected row on overlapping hits, otherwise follows option order', () => {
  expect(mapSelection(click(['11T0-0000-0984-D,cap:PL']), options, 'cap:PL', true)).toBeNull();
  expect(mapSelection(click(['11T0-0000-0984-D,cap:PL']), options, null, true)).toEqual({type: 'select', selected: '11T0-0000-0984-D', source: 'constraints'});
});

test.each([{points: []}, click(['11T0-0000-0984-D'])])('loading or stale figures cannot change selection: %j', value => {
  expect(mapSelection(value, options, 'cap:PL', false)).toBeNull();
});

test('a non-constraint first point does not hide later constraint hits', () => {
  const event = {points: [{curveNumber: 0}, {customdata: ['11T0-0000-0984-D']}, {customdata: ['cap:PL']}]};
  expect(mapSelection(event, options, null, true)).toEqual({type: 'select', selected: '11T0-0000-0984-D', source: 'constraints'});
  expect(mapSelection(event, options, 'cap:PL', true)).toBeNull();
});
