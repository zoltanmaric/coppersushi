import React from 'react';
import {createRoot} from 'react-dom/client';
import {loadBasemap} from '../../map/basemap';
import {fetchStudy} from './data';
import {ExportCapView} from './view';
import {Breakdown} from './breakdown';
import {Sources} from './sources';
import './style.css';

const root=createRoot(document.getElementById('app-root')!);
root.render(<div role="status">Loading investigation…</div>);
async function start(){
  if(window.location.pathname.replace(/\/$/,'').endsWith('/breakdown')){
    const study=await fetchStudy();
    root.render(<article className="export-cap-page breakdown-embed"><Breakdown study={study} showTitle={false}/><Sources study={study}/></article>);
  }else{
    const [config,study]=await Promise.all([loadBasemap(),fetchStudy()]);
    root.render(<ExportCapView {...config} study={study}/>);
  }
}
start().catch(error=>root.render(<section role="alert">{String(error)}. <button onClick={()=>window.location.reload()}>Retry</button></section>));
