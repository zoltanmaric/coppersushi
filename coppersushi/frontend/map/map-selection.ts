import type {Action} from '../controls/state';

/** Translate a renderer click into selection intent for the displayed view. */
export function mapSelection(click: unknown, options: readonly string[], selected: string | null, current: boolean): Action | null {
  if (!current || !click || typeof click !== 'object' || !('points' in click) || !Array.isArray(click.points)) return null;
  const candidates = click.points.flatMap(point => {
    const data = point && typeof point === 'object' && 'customdata' in point ? point.customdata : null;
    return Array.isArray(data) && typeof data[0] === 'string' ? data[0].split(',') : [];
  });
  if (selected !== null && options.includes(selected) && candidates.includes(selected)) return null;
  const option = options.find(id => candidates.includes(id));
  if (option) return {type: 'select', selected: option};
  return selected === null ? null : {type: 'select', selected: null};
}
