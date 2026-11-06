import type {ConstraintOption} from './figure';
import type {Action} from './state';

/** Translate a renderer click into selection intent for the displayed view. */
export function mapSelection(click: unknown, options: ConstraintOption[], selected: number | null, current: boolean): Action | null {
  if (!current || !click || typeof click !== 'object' || !('points' in click) || !Array.isArray(click.points)) return null;
  const candidates = click.points.flatMap(point => {
    const data = point && typeof point === 'object' && 'customdata' in point ? point.customdata : null;
    return Array.isArray(data) && typeof data[0] === 'string' ? data[0].split(',') : [];
  });
  if (selected !== null && options.some(o => o.value === String(selected) && candidates.includes(o.value))) return null;
  const option = options.find(o => o.value && candidates.includes(o.value));
  if (option) return {type: 'select', selected: Number(option.value), source: option.source};
  return selected === null ? null : {type: 'select', selected: null, source: 'constraints'};
}
