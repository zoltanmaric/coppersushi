import React, {useEffect, useId, useRef, useState} from 'react';
import {supportsDecoration} from './overlay-model';
import type {Camera, OverlayModel} from './overlay-model';

const RING_RADIUS = 6;
const RING_OFFSET = 4;


/** Project a longitude/latitude into the unpitched Mapbox viewport. */
export function project(lon: number, lat: number, camera: Camera, width: number, height: number): [number, number] {
  const mercator = (x: number, y: number) => {
    const rad = Math.max(-85.051129, Math.min(85.051129, y)) * Math.PI / 180;
    return [(x + 180) / 360, (1 - Math.asinh(Math.tan(rad)) / Math.PI) / 2];
  };
  const [x, y] = mercator(lon, lat);
  const [cx, cy] = mercator(camera.lon, camera.lat);
  const scale = 512 * 2 ** camera.zoom;
  const angle = -camera.bearing * Math.PI / 180;
  const dx = (x - cx) * scale, dy = (y - cy) * scale;
  return [width / 2 + dx * Math.cos(angle) - dy * Math.sin(angle),
          height / 2 + dx * Math.sin(angle) + dy * Math.cos(angle)];
}

/** Decorative energy only; essential symbols belong to the native map. */
export function ConstraintOverlay({model, camera, hidden}: {model: OverlayModel; camera: Camera; hidden: boolean}) {
  const filterId = `energy-${useId().replace(/:/g, "")}`;
  const container = useRef<SVGSVGElement>(null);
  const [size, setSize] = useState({width: 0, height: 0});
  useEffect(() => {
    const parent = container.current?.parentElement;
    if (!parent) return;
    const measure = () => setSize({width: parent.clientWidth, height: parent.clientHeight});
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(parent);
    return () => observer.disconnect();
  }, []);
  const visible = !hidden && supportsDecoration(camera, size.width, size.height);
  const selection = visible ? model.selection : null;
  const transformer = selection?.kind === 'transformer';
  const ambient = visible ? model.ambient.map(points => points.map(([x, y]) =>
    project(x, y, camera, size.width, size.height).join(',')).join(' ')) : [];
  let bolts: {main: string; fork: string}[] = [];
  let blades: string[] = [];
  let maskCenter: [number, number] | null = null;
  if (selection) {
    const ends = selection.kind === 'line' ? selection.endpoints : [selection.center, selection.center];
    const a = project(...ends[0], camera, size.width, size.height);
    const b = project(...ends[1], camera, size.width, size.height);
    if (selection.kind === 'line') maskCenter = project(
      (ends[0][0] + ends[1][0]) / 2, (ends[0][1] + ends[1][1]) / 2, camera, size.width, size.height);
    const dx = b[0] - a[0], dy = b[1] - a[1];
    const length = Math.hypot(dx, dy);
    const ux = length > 3 ? dx / length : 1, uy = length > 3 ? dy / length : 0;
    const span = Math.max(16, length), cx = (a[0] + b[0]) / 2, cy = (a[1] + b[1]) / 2;
    const point = (along: number, offset: number) =>
      `${(cx + ux * along - uy * offset).toFixed(1)},${(cy + uy * along + ux * offset).toFixed(1)}`;
    if (transformer) {
      // Both the steady core and the restless filaments follow the same two windings.
      const ring = (offset: number, variant?: number) => Array.from({length: 65}, (_, j) => {
        const angle = j / 64 * Math.PI * 2;
        const jag = variant === undefined ? 0 :
          .65 * Math.sin(angle * 11 + variant * 4) + .35 * Math.sin(angle * 23 + variant);
        const radius = RING_RADIUS + jag;
        const x = offset + Math.cos(angle) * radius, y = Math.sin(angle) * radius;
        const bearing = -camera.bearing * Math.PI / 180;
        return `${(cx + x * Math.cos(bearing) - y * Math.sin(bearing)).toFixed(2)},${(cy + x * Math.sin(bearing) + y * Math.cos(bearing)).toFixed(2)}`;
      }).join(' ');
      blades = [-RING_OFFSET, RING_OFFSET].map(offset => ring(offset));
      bolts = [0, 1, 2].flatMap(variant => [-RING_OFFSET, RING_OFFSET].map(offset => ({main: ring(offset, variant), fork: ''})));
    } else {
      blades = [`${point(-span / 2, 0)} ${point(span / 2, 0)}`];
      bolts = [0, 1, 2].map(variant => {
        const main = Array.from({length: 37}, (_, j) => {
          const t = j / 36;
          const jag = (Math.sin(j * 2.31 + variant * 4) + .5 * Math.sin(j * 5.7 + variant)) * 2.2;
          return point((t - .5) * (span + 4), jag * Math.sin(Math.PI * t));
        }).join(' ');
        const along = (variant - 1) * span * .24;
        const side = variant % 2 ? -1 : 1;
        const fork = [point(along, 0), point(along + 2, side * 3), point(along - 1, side * 5),
          point(along + 3, side * 7), point(along + 5, side * 8)].join(' ');
        return {main, fork};
      });
    }
  }
  return <svg ref={container} className="cnec-spark" aria-hidden="true">
    <defs><filter id={filterId} x="-100%" y="-100%" width="300%" height="300%" colorInterpolationFilters="sRGB">
      <feGaussianBlur stdDeviation="3.5"/>
    </filter></defs>
    {ambient.map((path, i) => <polyline key={i} points={path} className="cnec-ambient-glow"/>)}
    <defs><mask id={`${filterId}-glyph`}>
      <rect width="100%" height="100%" fill="white"/>
      {maskCenter && <circle cx={maskCenter[0]} cy={maskCenter[1]} r="6" fill="black"/>}
    </mask></defs>
    <g mask={`url(#${filterId}-glyph)`}>
    {blades.map((blade, i) => <g key={i} className={`cnec-energy-blade${transformer ? ' cnec-transformer-energy' : ''}`}>
      <polyline points={blade} className="cnec-energy-aura" filter={`url(#${filterId})`}/>
      <polyline points={blade} className="cnec-energy-rim"/>
      <polyline points={blade} className="cnec-energy-core"/>
    </g>)}
    {bolts.map((bolt, i) => <g key={i} className={`cnec-spark-bolt cnec-spark-bolt-${i}`}>
      <polyline className="cnec-spark-glow" points={bolt.main}/><polyline className="cnec-spark-core" points={bolt.main}/>
      {bolt.fork && <polyline className="cnec-spark-core cnec-spark-fork" points={bolt.fork}/>}
    </g>)}
    </g>
  </svg>;
}
