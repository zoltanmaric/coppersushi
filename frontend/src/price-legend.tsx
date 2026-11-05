import React from 'react';
import type {PlotlyFigure} from './contracts';

export function PriceLegend({figure}: {figure: PlotlyFigure}) {
  const fill = figure.data.find(trace => trace.type === 'choroplethmapbox');
  if (!fill || typeof fill.zmin !== 'number' || typeof fill.zmax !== 'number' || !Array.isArray(fill.colorscale)) return null;
  const stops = fill.colorscale.filter((stop): stop is [number, string] =>
    Array.isArray(stop) && typeof stop[0] === 'number' && typeof stop[1] === 'string');
  const background = `linear-gradient(to right, ${stops.map(([at, color]) => `${color} ${at * 100}%`).join(',')})`;
  const format = (value: number) => value.toLocaleString(undefined, {maximumFractionDigits: 2});
  return <div className="cnec-price-legend" aria-label="Daily day-ahead price scale">
    <div>Day-ahead · €/MWh</div>
    <div className="cnec-price-gradient" style={{background}}/>
    <div className="cnec-price-range"><span>{format(fill.zmin)}</span><span>{format(fill.zmax)}</span></div>
  </div>;
}
