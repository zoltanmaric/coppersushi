// @vitest-environment jsdom
import React, {useRef} from 'react';
import {cleanup, fireEvent, render} from '@testing-library/react';
import {afterEach, expect, test, vi} from 'vitest';
import {CountryLabels} from './country-labels';
import type {CountryLabel} from './country-labels';
import type {MapboxMap} from './mapbox-adapter';
import {useMapGestures} from './map-gestures';

vi.mock('./plot', () => ({clearTooltip: vi.fn(), hoverAtPointer: vi.fn()}));
afterEach(cleanup);

const label: CountryLabel = {zone: 'PL', name: 'Poland', centre: [20,52], price: 100};
function nativeMap() {
  const source = {setData: vi.fn()};
  const map = {
    addSource: vi.fn(), getSource: () => source, removeSource: vi.fn(),
    addLayer: vi.fn(), getLayer: () => ({}), removeLayer: vi.fn(),
    queryRenderedFeatures: vi.fn(() => [{properties: {zone: 'PL'}}]),
    getCanvasContainer: () => document.createElement('div'), on: vi.fn(), off: vi.fn(),
  };
  return {map: map as unknown as MapboxMap, source, calls: map};
}

test('price updates retain the native source and layer, then dispose them on unmount', () => {
  const {map, source, calls} = nativeMap();
  const {rerender, unmount} = render(<CountryLabels labels={[label]} map={map}/>);
  rerender(<CountryLabels labels={[{...label, price: 151.28}]} map={map}/>);
  expect(calls.addLayer).toHaveBeenCalledTimes(1);
  expect(calls.addSource).toHaveBeenCalledTimes(1);
  expect(source.setData.mock.lastCall?.[0].features[0].properties.text).toBe('Poland\n€151.28');
  unmount();
  expect(calls.removeLayer).toHaveBeenCalledOnce();
  expect(calls.removeSource).toHaveBeenCalledOnce();
});

function GestureMap({map, onReference, onMapClick}: {
  map: MapboxMap; onReference: (zone: string) => void; onMapClick: () => void;
}) {
  const host = useRef<HTMLDivElement>(null);
  const gestures = useMapGestures(host, map, true, onReference);
  return <div ref={host} {...gestures.handlers}><canvas onClick={onMapClick}/></div>;
}

test('a country tap uses the pointer-down label and never clears the selected constraint', () => {
  const {map, calls} = nativeMap();
  const onReference = vi.fn(), onMapClick = vi.fn();
  const {container} = render(<GestureMap map={map} onReference={onReference} onMapClick={onMapClick}/>);
  const canvas = container.querySelector('canvas')!;
  fireEvent(canvas, new MouseEvent('pointerdown', {bubbles: true, clientX: 100, clientY: 100}));
  calls.queryRenderedFeatures.mockReturnValue([{properties: {zone: 'AT'}}]);
  fireEvent.click(canvas, {clientX: 100, clientY: 100});
  expect(onReference).toHaveBeenCalledWith('PL');
  expect(onMapClick).not.toHaveBeenCalled();
});

test('a label appearing after pointer-down cannot steal the map click', () => {
  const {map, calls} = nativeMap();
  calls.queryRenderedFeatures.mockReturnValue([]);
  const onReference = vi.fn(), onMapClick = vi.fn();
  const {container} = render(<GestureMap map={map} onReference={onReference} onMapClick={onMapClick}/>);
  const canvas = container.querySelector('canvas')!;
  fireEvent(canvas, new MouseEvent('pointerdown', {bubbles: true, clientX: 100, clientY: 100}));
  calls.queryRenderedFeatures.mockReturnValue([{properties: {zone: 'PL'}}]);
  fireEvent.click(canvas, {clientX: 100, clientY: 100});
  expect(onReference).not.toHaveBeenCalled();
  expect(onMapClick).toHaveBeenCalledOnce();
});
