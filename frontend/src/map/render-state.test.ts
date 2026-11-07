import {expect,test} from 'vitest';
import {reduceRender} from './render-state';
import type {RenderState} from './render-state';
import type {PlotlyFigure} from './figure';
const snapshot = (interval:number)=>({figure:{data:[],layout:{mapbox:{},uirevision:'camera'}} as PlotlyFigure,interval});

test('rapid scrubbing renders the in-flight interval then only the last requested one',()=>{
  const first=snapshot(0),last=snapshot(95);
  let state:RenderState<typeof first>={active:first,pending:null,busy:true};
  for (let i=1;i<95;i++) state=reduceRender(state,{type:'request',value:snapshot(i)});
  state=reduceRender(state,{type:'request',value:last});
  expect(state.active).toBe(first);
  state=reduceRender(state,{type:'complete',figure:first.figure});
  expect(state).toEqual({active:last,pending:null,busy:true});
  expect(reduceRender(state,{type:'complete',figure:first.figure})).toBe(state);
  expect(reduceRender(state,{type:'complete',figure:last.figure}).busy).toBe(false);
});
test('returning to the in-flight figure cancels a pending update',()=>{
  const first=snapshot(0);
  let state:RenderState<typeof first>={active:first,pending:null,busy:true};
  state=reduceRender(state,{type:'request',value:snapshot(1)});
  state=reduceRender(state,{type:'request',value:first});
  expect(reduceRender(state,{type:'complete',figure:first.figure})).toEqual({active:first,pending:null,busy:false});
});
