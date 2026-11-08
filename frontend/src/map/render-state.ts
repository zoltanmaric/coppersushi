import type {PlotlyFigure} from './figure';

export interface RenderState<T> {active:T; pending:T|null; busy:boolean}
export type RenderAction<T> = {type:'request';value:T} | {type:'complete';figure:PlotlyFigure};

/** One in-flight figure and one replaceable pending snapshot; never a FIFO. */
export function reduceRender<T extends {figure:PlotlyFigure}>(state:RenderState<T>,action:RenderAction<T>):RenderState<T> {
  if (action.type === 'complete') {
    if (!state.busy || action.figure !== state.active.figure) return state;
    return state.pending ? {active:state.pending,pending:null,busy:true} : {...state,busy:false};
  }
  if (action.value.figure === state.active.figure) return state.pending ? {...state,pending:null} : state;
  if (state.pending?.figure === action.value.figure) return state;
  return state.busy ? {...state,pending:action.value} : {active:action.value,pending:null,busy:true};
}
