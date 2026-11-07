import {expect, test} from 'vitest';
import {mapSelection} from './map-selection';

const options = ['11T0-0000-0984-D', 'cap:PL'];
const click = (value: unknown) => ({points: [{customdata: value}]});
const clear = {type: 'select', selected: null};

test.each([undefined, null, {}, {points: null}])('absent or malformed events are ignored: %j', value => {
  expect(mapSelection(value, options, '11T0-0000-0984-D', true)).toBeNull();
});

test.each([{points: []}, {points: [{curveNumber: 0}]}, click(null), click([17]), click(['unknown'])])(
  'a background or non-constraint hit clears selection: %j', value => {
    expect(mapSelection(value, options, '11T0-0000-0984-D', true)).toEqual(clear);
    expect(mapSelection(value, options, null, true)).toBeNull();
  });

test('selects a valid identity', () => {
  expect(mapSelection(click(['cap:PL']), options, '11T0-0000-0984-D', true)).toEqual({type: 'select', selected: 'cap:PL'});
});

test('preserves the selected row on overlapping hits, otherwise follows option order', () => {
  expect(mapSelection(click(['11T0-0000-0984-D,cap:PL']), options, 'cap:PL', true)).toBeNull();
  expect(mapSelection(click(['11T0-0000-0984-D,cap:PL']), options, null, true)).toEqual({type: 'select', selected: '11T0-0000-0984-D'});
});

test.each([{points: []}, click(['11T0-0000-0984-D'])])('loading or stale figures cannot change selection: %j', value => {
  expect(mapSelection(value, options, 'cap:PL', false)).toBeNull();
});

test('a non-constraint first point does not hide later constraint hits', () => {
  const event = {points: [{curveNumber: 0}, {customdata: ['11T0-0000-0984-D']}, {customdata: ['cap:PL']}]};
  expect(mapSelection(event, options, null, true)).toEqual({type: 'select', selected: '11T0-0000-0984-D'});
  expect(mapSelection(event, options, 'cap:PL', true)).toBeNull();
});
