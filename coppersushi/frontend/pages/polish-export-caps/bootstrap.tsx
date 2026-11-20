import React from 'react';
import {createRoot} from 'react-dom/client';
import {loadBasemap} from '../../map/basemap';
import {fetchStudy} from './data';
import {ExportCapView} from './view';
import {Breakdown} from './breakdown';
import {Sources} from './sources';
import './style.css';

const container = document.getElementById('app-root')!;
if (document.body.dataset.embed === 'true' && window.parent !== window) {
  const reportHeight = () => window.parent.postMessage(
    {type: 'polish-study-height', height: Math.ceil(container.getBoundingClientRect().height)}, '*'
  );
  new ResizeObserver(reportHeight).observe(container);
  window.addEventListener('message', event => {
    if (event.source === window.parent && event.data === 'request-polish-study-height') reportHeight();
  });
}
const root=createRoot(container);
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
