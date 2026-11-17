// @vitest-environment jsdom
import {act, cleanup, render} from '@testing-library/react';
import React from 'react';
import {afterEach, expect, test, vi} from 'vitest';
import {useMapCamera, type MapCamera} from './camera';
import type {MapboxMap} from './mapbox-adapter';

afterEach(cleanup);
test('restore, observe user movement, and accept URL feedback without another camera jump',()=>{
  let position={lat:50,lng:15}, zoom=4;
  const handlers=new Set<()=>void>();
  const jumpTo=vi.fn((next:{center:[number,number];zoom:number})=>{
    position={lat:next.center[1],lng:next.center[0]};zoom=next.zoom;handlers.forEach(fn=>fn());
  });
  const map={getCenter:()=>position,getZoom:()=>zoom,jumpTo,
    on:(_name:string,fn:()=>void)=>handlers.add(fn),off:(_name:string,fn:()=>void)=>handlers.delete(fn)} as unknown as MapboxMap;
  const onChange=vi.fn();
  function Host({camera}:{camera:MapCamera}){useMapCamera(map,camera,onChange);return null;}
  const {rerender,unmount}=render(<Host camera={{lat:52,lon:20,zoom:5}}/>);
  expect(jumpTo).toHaveBeenCalledTimes(1);
  expect(onChange).not.toHaveBeenCalled();
  act(()=>{position={lat:53,lng:21};handlers.forEach(fn=>fn());});
  expect(onChange).toHaveBeenCalledWith({lat:53,lon:21,zoom:5});
  rerender(<Host camera={{lat:53,lon:21,zoom:5}}/>);
  expect(jumpTo).toHaveBeenCalledTimes(1);
  // External navigation restores a different saved camera.
  rerender(<Host camera={{lat:51,lon:19,zoom:3}}/>);
  expect(jumpTo).toHaveBeenCalledTimes(2);
  expect(onChange).toHaveBeenCalledTimes(1);
  unmount();expect(handlers.size).toBe(0);
});
