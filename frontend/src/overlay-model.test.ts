import {expect, test} from 'vitest';
import {overlayModel, supportsDecoration, updateCamera} from './overlay-model';
import type {PlotlyFigure} from './contracts';

const camera = {lat: 50, lon: 10, zoom: 3.5, bearing: 0, pitch: 0};
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

test('partial camera events retain previous fields and reject non-finite values', () => {
  expect(updateCamera(camera, {'mapbox.center': {lon: 20}, 'mapbox.zoom': NaN, 'mapbox.pitch': 30}))
    .toEqual({...camera, lon: 20, pitch: 30});
});

test('decorations are limited to flat finite canonical-world viewports; native glyphs are independent', () => {
  expect(supportsDecoration(camera, 1000, 600)).toBe(true);
  for (const change of [{pitch: 1}, {lon: 370}, {lat: 90}, {zoom: -3}, {bearing: NaN}]) {
    expect(supportsDecoration({...camera, ...change}, 1000, 600)).toBe(false);
  }
  expect(supportsDecoration(camera, 0, 600)).toBe(false);
  expect(supportsDecoration({...camera, bearing: 90}, 1000, 600)).toBe(true);
});
