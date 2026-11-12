import React from 'react';
import type {PriceRange} from '../data/contracts';
import {PRICE_COLORSCALE} from '../map/price-scale';

const background = `linear-gradient(to right, ${PRICE_COLORSCALE.map(([at, color]) => `${color} ${at * 100}%`).join(',')})`;
const format = (value: number) => value.toLocaleString(undefined, {maximumFractionDigits: 2});

export function ScaleLegend({range,title,description,reversed=false}: {range: PriceRange | null;title:string;description:string;reversed?:boolean}) {
  return <div className="cnec-price-legend" aria-label={description} aria-busy={range === null}>
    <div>{title}</div>
    <div className="cnec-price-gradient" style={{background:reversed ? background.replace('to right','to left') : background}}/>
    <div className="cnec-price-range"><span>{range ? format(range[0]) : '\u00a0'}</span><span>{range ? format(range[1]) : '\u00a0'}</span></div>
  </div>;
}

export function PriceLegend({range}:{range:PriceRange|null}) {return <ScaleLegend range={range} title="Day-ahead · €/MWh" description="Daily day-ahead price scale"/>;}
