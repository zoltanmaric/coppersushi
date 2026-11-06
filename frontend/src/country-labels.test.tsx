// @vitest-environment jsdom
import React from 'react';
import {cleanup, fireEvent, render, screen} from '@testing-library/react';
import {afterEach, expect, test} from 'vitest';
import {CountryLabels} from './country-labels';
import type {CountryLabel} from './country-labels';
import type {CoreZone} from './reference';

afterEach(cleanup);

test('price updates retain country and price nodes; clicking chooses the reference',()=>{
  const label: CountryLabel={zone:'PL',name:'Poland',centre:[20,52],price:100};
  const movement = new EventTarget();
  let x = 100;
  const map = {
    project: () => ({x,y:200}),
    on: (event:string, listener:()=>void) => movement.addEventListener(event,listener),
    off: (event:string, listener:()=>void) => movement.removeEventListener(event,listener),
  };
  let chosen: CoreZone | null=null;
  const onReference=(zone: CoreZone)=>{chosen=zone;};
  const {rerender}=render(<CountryLabels labels={[label]} map={map} onReference={onReference}/>);
  const country=screen.getByRole('button',{name:'Use Poland as reference'});
  const price=screen.getByText('€100.00');
  rerender(<CountryLabels labels={[{...label,price:151.28}]} map={map} onReference={onReference}/>);
  expect(screen.getByRole('button',{name:'Use Poland as reference'})).toBe(country);
  expect(screen.getByText('€151.28')).toBe(price);
  expect((country as HTMLButtonElement).style.transform).toContain('translate(100px,200px)');
  x = 150;
  movement.dispatchEvent(new Event('move'));
  // The native event updates position in this turn, without flushing a React render.
  expect((country as HTMLButtonElement).style.transform).toContain('translate(150px,200px)');
  fireEvent.click(country);
  expect(chosen).toBe('PL');
});
