import {CORE_ZONES} from '../market/reference';

// Plotly rebuilds layers sharing a `below` target. Unique, permanent style anchors
// preserve ordering without removing existing trace layers during an interval update.
const order = [
  'published day-ahead price',
  'market-binding CNECs glow', 'market-binding CNECs', 'binding line ends', 'select line',
  'selected CNEC', 'binding country cap glow', 'binding country cap', 'select country cap',
  ...CORE_ZONES.map(zone => `${zone} ray`),
  'ray contributions', 'binding rows', 'binding transformers and PSTs',
  'selected CNEC marker',
];

export const layerAnchor = (name: string, mode?: unknown) =>
  `cnec-before-${name === 'selected CNEC' && mode === 'markers' ? `${name} marker` : name}`;

interface StyleLayer {id: string; type: string; [key: string]: unknown}

/** Fill stays below the top base-map boundary; symbols and rays stay above it. */
export function orderedMapLayers(layers: StyleLayer[]): StyleLayer[] {
  const anchors = order.map(name => ({id: layerAnchor(name), type:'background',
    paint:{'background-opacity':0}}));
  const boundary = Math.max(0,layers.length - 1);
  return [...layers.slice(0,boundary), anchors[0], ...layers.slice(boundary), ...anchors.slice(1)];
}
