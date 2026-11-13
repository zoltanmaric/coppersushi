import React, {forwardRef, useLayoutEffect, useRef, useState} from 'react';

export const MapFrame = forwardRef<HTMLElement, React.PropsWithChildren<{id?:string;label?:string}>>(
  ({id,label,children},ref)=><section ref={ref} id={id} aria-label={label} className="map-frame">{children}</section>);

/** Capture the mounted container once; subsequent camera changes belong to the user. */
export function useMapViewport() {
  const ref=useRef<HTMLElement>(null);
  const [size,setSize]=useState<{width:number;height:number}|null>(null);
  useLayoutEffect(()=>{const rect=ref.current!.getBoundingClientRect();setSize({width:rect.width,height:rect.height});},[]);
  return {ref,size};
}
