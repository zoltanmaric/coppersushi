import type {CoreZone} from './reference';
export interface Selection {reference: CoreZone; day: string; interval: number; selected: number | null; source: "constraints" | "attribution"}
export type Action = {type: 'reference'; reference: CoreZone} | {type: 'day'; day: string} | {type: 'interval'; interval: number} |
  {type: 'select'; selected: number | null; source: "constraints" | "attribution"};

export function reduceSelection(state: Selection, action: Action): Selection {
  switch (action.type) {
    case 'reference': return {...state, reference: action.reference};
    case 'day': return action.day === state.day ? state : {...state, day: action.day, interval: 0, selected: null, source: "constraints"};
    case 'interval': return {...state, interval: action.interval};
    case 'select': return {...state, selected: action.selected, source: action.source};
  }
}
