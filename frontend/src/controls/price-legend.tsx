import React from 'react';
import type {PriceRange} from '../data/contracts';
import {PRICE_COLORSCALE} from '../map/price-scale';

const background = `linear-gradient(to right, ${PRICE_COLORSCALE.map(([at, color]) => `${color} ${at * 100}%`).join(',')})`;
const format = (value: number) => value.toLocaleString(undefined, {maximumFractionDigits: 2});

export function PriceLegend({range}: {range: PriceRange | null}) {
  return <div className="cnec-price-legend" aria-label="Daily day-ahead price scale" aria-busy={range === null}>
    <div>Day-ahead · €/MWh</div>
    <div className="cnec-price-gradient" style={{background}}/>
    <div className="cnec-price-range"><span>{range ? format(range[0]) : '\u00a0'}</span><span>{range ? format(range[1]) : '\u00a0'}</span></div>
  </div>;
}
