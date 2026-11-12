import React from 'react';
import './map-controls.css';

/** Own all overlay placement; pages supply their domain-specific controls. */
export function MapControls({legend,reference,help,controls,footer}:{legend:React.ReactNode;reference?:React.ReactNode;help:React.ReactNode;controls:React.ReactNode;footer?:React.ReactNode}) {
 return <><div className="cnec-map-tools">{legend}{reference}{help}</div>
 <div className="cnec-bottom-controls">{controls}{footer}</div></>;
}
