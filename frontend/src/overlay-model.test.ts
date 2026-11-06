import {expect, test} from 'vitest';
import {overlayModel} from './overlay-model';
import type {PlotlyFigure} from './contracts';

const figure = (data: PlotlyFigure['data']) => ({data} as PlotlyFigure);

test('explicit metadata identifies effects independently of display names and trace order', () => {
  const model = overlayModel(figure([
    {name: 'translated name', lon: [1, 2, null, 3, 4], lat: [50, 51, null, 52, 53], meta: {ambient: true}},
    {name: 'anything', lon: [10], lat: [50], meta: {effect: 'transformer'}},
  ]));
  expect(model).toEqual({ambient: [[[1, 50], [2, 51]], [[3, 52], [4, 53]]],
    selection: {kind: 'transformer', center: [10, 50]}});
  expect(overlayModel(figure([{lon: [1, 2], lat: [50, 51], meta: {effect: 'line'}}])).selection)
    .toEqual({kind: 'line', endpoints: [[1, 50], [2, 51]]});
});

test('malformed optional metadata cannot create an effect or connect missing coordinates', () => {
  expect(overlayModel(figure([
    {lon: [1, NaN], lat: [50, 51], meta: {effect: 'line'}},
    {lon: [1], lat: [], meta: {effect: 'transformer'}},
    {lon: [1], lat: [50], meta: 'legacy'},
    {lon: [1, null, 3], lat: [50, null, 52], meta: {ambient: true}},
  ]))).toEqual({ambient: [], selection: null});
});
