import React from 'react';
import {createRoot} from 'react-dom/client';
import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import Ajv from 'ajv';
import {OpfView} from './view';
import './style.css';
const valid = new Ajv().compile<{token:string}>({type:'object',required:['token'],additionalProperties:false,properties:{token:{type:'string',minLength:1}}});
const root = createRoot(document.getElementById('app-root')!);
try {
  const config:unknown = JSON.parse(document.getElementById('app-config')!.textContent!);
  if (!valid(config)) throw new Error('Invalid Power Flow configuration');
  const client = new QueryClient({defaultOptions:{queries:{staleTime:Infinity,retry:1,refetchOnWindowFocus:false}}});
  root.render(<QueryClientProvider client={client}><OpfView token={config.token}/></QueryClientProvider>);
} catch(error) {root.render(<div role="alert">{String(error)}</div>);}
