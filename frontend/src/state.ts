export interface Selection {day: string; interval: number; selected: number | null; source: "constraints" | "attribution"}
export type Action = {type: 'day'; day: string} | {type: 'interval'; interval: number} |
  {type: 'select'; selected: number | null; source: "constraints" | "attribution"};

export function reduceSelection(state: Selection, action: Action): Selection {
  switch (action.type) {
    case 'day': return action.day === state.day ? state : {day: action.day, interval: 0, selected: null, source: "constraints"};
    case 'interval': return {...state, interval: action.interval};
    case 'select': return {...state, selected: action.selected, source: action.source};
  }
}
