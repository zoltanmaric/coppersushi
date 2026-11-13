import React from 'react';
import './map-controls.css';

/** Own all overlay placement; pages supply their domain-specific controls. */
export function MapControls({legend,reference,help,controls,footer,status,loading=false,showing}:{legend:React.ReactNode;reference?:React.ReactNode;help:React.ReactNode;controls:React.ReactNode;footer?:React.ReactNode;status?:React.ReactNode;loading?:boolean;showing?:string}) {
 return <><div className={`cnec-map-tools${reference ? '' : ' map-tools-without-reference'}`}>{legend}{reference}{help}<aside className="map-status" aria-live="polite">{loading && <div role="status" aria-label="Map loading">Loading interval…{showing && <div>Showing {showing}.</div>}</div>}{status}</aside></div>
 <div className="cnec-bottom-controls">{controls}{footer}</div></>;
}
