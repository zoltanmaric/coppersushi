import React from 'react';
import {createRoot} from 'react-dom/client';
import {CnecView} from './index';
import {marketDay} from '../../controls/market-day';
import {loadBasemap} from '../../map/basemap';

const root = createRoot(document.getElementById('app-root')!);
root.render(<div role="status">Loading map…</div>);
loadBasemap().then(config => root.render(<CnecView id="cnec-view" {...config} default_day={marketDay(new Date())}/>))
  .catch(error => root.render(<div role="alert">{String(error)}</div>));
