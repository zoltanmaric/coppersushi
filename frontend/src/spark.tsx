import React, {useEffect, useRef, useState} from 'react';
import type {PlotlyFigure} from './contracts';

export interface Camera {lat: number; lon: number; zoom: number; bearing: number}

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

/** Animated, pointer-transparent selection spark; the Plotly camera remains the source of truth. */
export function SelectionSpark({figure, camera, hidden}: {figure: PlotlyFigure; camera: Camera; hidden: boolean}) {
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
  const line = figure.data.find(trace => trace.name === 'selected CNEC');
  const lon = line?.lon, lat = line?.lat;
  let bolts: {main: string; fork: string}[] = [];
  if (!hidden && Array.isArray(lon) && Array.isArray(lat) && lon.length >= 2 && lat.length >= 2 &&
      [lon[0], lon[1], lat[0], lat[1]].every(v => typeof v === 'number' && Number.isFinite(v))) {
    const a = project(lon[0] as number, lat[0] as number, camera, size.width, size.height);
    const b = project(lon[1] as number, lat[1] as number, camera, size.width, size.height);
    const dx = b[0] - a[0], dy = b[1] - a[1];
    const length = Math.hypot(dx, dy);
    const ux = length > 3 ? dx / length : 1, uy = length > 3 ? dy / length : 0;
    const span = Math.max(24, length + 14), cx = (a[0] + b[0]) / 2, cy = (a[1] + b[1]) / 2;
    const patterns = [[0, -4, 3, -5, 4, -2, 0], [0, 5, -4, 3, -5, 4, 0], [0, -2, 5, -3, 2, -4, 0]];
    const point = (along: number, offset: number) =>
      `${(cx + ux * along - uy * offset).toFixed(1)},${(cy + uy * along + ux * offset).toFixed(1)}`;
    bolts = patterns.map((pattern, i) => {
      const main = pattern.map((offset, j) => point((j / (pattern.length - 1) - .5) * span, offset)).join(' ');
      const fork = [point(0, pattern[3]), point(span * .08, pattern[3] + (i % 2 ? -7 : 7)),
                    point(span * .16, pattern[3] + (i % 2 ? -10 : 10))].join(' ');
      return {main, fork};
    });
  }
  return <svg ref={container} className="cnec-spark" aria-hidden="true">
    {bolts.map((bolt, i) => <g key={i} className={`cnec-spark-bolt cnec-spark-bolt-${i}`}>
      <polyline className="cnec-spark-glow" points={bolt.main}/><polyline className="cnec-spark-core" points={bolt.main}/>
      <polyline className="cnec-spark-glow" points={bolt.fork}/><polyline className="cnec-spark-core" points={bolt.fork}/>
    </g>)}
  </svg>;
}
