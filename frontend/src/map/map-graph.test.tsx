// @vitest-environment jsdom
import React from 'react';
import {act, cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, expect, test, vi} from 'vitest';
import {MapGraph} from './map-graph';
import type {PlotElement} from './plot';
import type {PlotlyFigure} from './figure';

const config={responsive:true};
const figure=(index:number):PlotlyFigure=>({data:[{name:String(index)}],layout:{mapbox:{style:{version:8,layers:[]}},uirevision:'camera'}});
let draws:{plot:PlotElement;figure:PlotlyFigure;resolve:()=>void;reject:(error:Error)=>void}[];
let events:Map<string,(event:unknown)=>unknown>;
let movement:Map<string,()=>void>;
const selections:string[]=[];
const props=(value:PlotlyFigure)=>({id:'map',figure:value,config,overlay:{ambient:[],selections:[]},hidden:false,
  countries:[],onReference:()=>{},
  onClick:(event:unknown)=>selections.push((event as {points:{customdata:string[]}[]}).points[0].customdata[0])});

beforeEach(()=>{
  draws=[]; events=new Map(); movement=new Map(); selections.length=0;
  vi.stubGlobal('PointerEvent',MouseEvent);
  // Only the GPU renderer is substituted: real React effects, event routing and promises run.
  window.Plotly={
    react:(element,view)=>{
      const plot=element as PlotElement;
      if (!plot.querySelector('canvas')) {
        plot.className='js-plotly-plot';
        plot.innerHTML='<div class="mapboxgl-canvas-container"><canvas class="mapboxgl-canvas" aria-label="Map canvas"></canvas></div><svg class="hoverlayer"></svg>';
        plot.on=(name,handler)=>{events.set(name,handler);};
        plot.removeListener=(name)=>{events.delete(name);};
        Object.assign(plot,{_fullLayout:{mapbox:{_subplot:{map:{
          dragRotate:{disable:()=>{}},touchZoomRotate:{disableRotation:()=>{}},touchPitch:{disable:()=>{}},keyboard:{disableRotation:()=>{}},
          getCanvasContainer:()=>plot.querySelector('.mapboxgl-canvas-container')!,
          project:()=>({x:0,y:0}),unproject:([x,y]:number[])=>({lng:x,lat:y}),
          isMoving:()=>false,getPitch:()=>0,getBearing:()=>0,getBounds:()=>({getWest:()=>-180,getEast:()=>180}),
          on:(name:string,handler:()=>void)=>movement.set(name,handler),off:(name:string)=>movement.delete(name),
        }}}}});
      }
      Object.assign(plot,{data:view.data,layout:view.layout});
      return new Promise((resolve,reject)=>draws.push({plot,figure:view,resolve:()=>resolve(undefined),reject}));
    },
    purge:()=>{},
  };
});
afterEach(()=>{cleanup();vi.unstubAllGlobals();});
async function settle(index:number) {
  await act(async()=>{draws[index].resolve();});
  await act(async()=>{await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));});
}

test('native camera updates cannot complete a pending render or release its selection gate',async()=>{
  const first=figure(0), second=figure(1), last=figure(95);
  const {rerender}=render(<MapGraph {...props(first)}/>);
  await waitFor(()=>expect(draws).toHaveLength(1));
  rerender(<MapGraph {...props(second)}/>);
  await settle(0);
  await waitFor(()=>expect(draws).toHaveLength(2));
  rerender(<MapGraph {...props(last)}/>);
  // Same data identity is already installed; the real drawing promise is unresolved.
  await act(async()=>{events.get('plotly_relayouting')?.({});events.get('plotly_relayout')?.({});});
  await act(async()=>{await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));});
  expect(draws).toHaveLength(2);
  events.get('plotly_click')?.({points:[{customdata:['premature']}]});
  expect(selections).toEqual([]);
  await settle(1);
  await waitFor(()=>expect(draws).toHaveLength(3));
  expect(draws[2].figure.data[0].name).toBe('95');
  await settle(2);
  await act(async()=>{events.get('plotly_click')?.({points:[{customdata:['ready']}]});});
  expect(selections).toEqual(['ready']);
});

test('native style mutations survive subsequent data updates without mutating the source layout',async()=>{
  const first=figure(0);
  const {rerender}=render(<MapGraph {...props(first)}/>);
  await waitFor(()=>expect(draws).toHaveLength(1));
  await settle(0);
  const layout=draws[0].figure.layout;
  const style=layout.mapbox.style as {layers:object[]};
  style.layers.push({id:'native-layer'});
  rerender(<MapGraph {...props({...figure(1),layout:first.layout})}/>);
  await waitFor(()=>expect(draws).toHaveLength(2));
  expect(draws[1].figure.layout).toBe(layout);
  expect((first.layout.mapbox.style as typeof style).layers).toEqual([]);
  await settle(1);
});

test('a failed replacement reports its error without enabling clicks on unconfirmed pixels',async()=>{
  const {rerender}=render(<MapGraph {...props(figure(0))}/>);
  await waitFor(()=>expect(draws).toHaveLength(1));
  await settle(0);
  rerender(<MapGraph {...props(figure(1))}/>);
  await waitFor(()=>expect(draws).toHaveLength(2));
  await act(async()=>{draws[1].reject(new Error('GPU failure'));});
  expect(screen.getByRole('alert').textContent).toContain('GPU failure');
  await act(async()=>{await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));});
  events.get('plotly_click')?.({points:[{customdata:['invalid']}]});
  expect(selections).toEqual([]);
});

test('same-figure navigation keeps the newest intent callbacks outside the render queue',async()=>{
  const view=props(figure(0));
  const countries=[{zone:'DE' as const,name:'Germany',centre:[10,50] as const,price:100}];
  const destinations:number[]=[];
  const request=(interval:number)=>({...view,countries,onReference:()=>destinations.push(interval),onClick:()=>destinations.push(interval)});
  const {rerender}=render(<MapGraph {...request(1)}/>);
  await waitFor(()=>expect(draws).toHaveLength(1));
  await settle(0);
  // Two pending interval requests can share the same visible placeholder figure.
  rerender(<MapGraph {...request(2)}/>);
  fireEvent.click(screen.getByRole('button',{name:'Use Germany as reference'}));
  await act(async()=>{events.get('plotly_click')?.({points:[]});});
  expect(destinations).toEqual([2,2]);
  expect(draws).toHaveLength(1);
});
