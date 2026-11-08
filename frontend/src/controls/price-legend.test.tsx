// @vitest-environment jsdom
import React from 'react';
import {cleanup, render, screen} from '@testing-library/react';
import {afterEach, expect, test} from 'vitest';
import {PriceLegend} from './price-legend';

afterEach(cleanup);

test('legend stays mounted with blank price slots until the daily range arrives',()=>{
  const {rerender}=render(<PriceLegend range={null}/>);
  const legend=screen.getByLabelText('Daily day-ahead price scale');
  const gradient=legend.querySelector('.cnec-price-gradient')!;
  const range=legend.querySelector('.cnec-price-range')!;
  const background=gradient.getAttribute('style');
  expect(screen.getByText('Day-ahead · €/MWh')).toBeTruthy();
  expect(legend.getAttribute('aria-busy')).toBe('true');
  expect(Array.from(range.children).map(span=>span.textContent)).toEqual(['\u00a0','\u00a0']);
  rerender(<PriceLegend range={[0,100]}/>);
  expect(screen.getByLabelText('Daily day-ahead price scale')).toBe(legend);
  expect(legend.querySelector('.cnec-price-range')).toBe(range);
  expect(gradient.getAttribute('style')).toBe(background);
  expect(Array.from(range.children).map(span=>span.textContent)).toEqual(['0','100']);
  expect(legend.getAttribute('aria-busy')).toBe('false');
  rerender(<PriceLegend range={null}/>);
  expect(legend.querySelector('.cnec-price-gradient')).toBe(gradient);
  expect(Array.from(range.children).map(span=>span.textContent)).toEqual(['\u00a0','\u00a0']);
});
