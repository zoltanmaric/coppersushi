import {coreZone} from '../market/reference';
import type {Selection} from './state';

function integer(value: string | null): number | null {
  if (value === null || !/^-?\d+$/.test(value)) return null;
  const number = Number(value);
  return Number.isSafeInteger(number) ? number : null;
}

/** Interval indices distinguish both occurrences of a daylight-saving hour. */
export function viewFromUrl(day: string, search: string): Selection {
  const parsedDay = new Date(`${day}T00:00:00Z`);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(day) || !Number.isFinite(parsedDay.getTime()) || parsedDay.getUTCFullYear() < 1 || parsedDay.toISOString().slice(0, 10) !== day) {
    throw new Error('Invalid delivery day');
  }
  const params = new URLSearchParams(search);
  const interval = integer(params.get('interval'));
  const selected = integer(params.get('constraint'));
  return {day, interval: interval !== null && interval >= 0 ? interval : 0,
    reference: coreZone(params.get('reference')) ?? 'DE', selected,
    source: selected !== null && selected < 0 ? 'attribution' : 'constraints'};
}

export function viewSearch(view: Selection, search: string): string {
  const params = new URLSearchParams(search);
  params.set('interval', String(view.interval));
  params.set('reference', view.reference);
  if (view.selected === null) params.delete('constraint');
  else params.set('constraint', String(view.selected));
  return `?${params}`;
}
