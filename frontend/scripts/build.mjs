import './sprites.mjs';
import {build} from 'esbuild';
// Each static view owns its React entry and CSS bundle.
await build({entryPoints: { 'cnec-app':'src/bootstrap.tsx', 'opf-app':'src/opf/bootstrap.tsx' }, bundle: true, minify: true,
  format: 'iife', outdir: '../assets',
  define: {'process.env.NODE_ENV': '"production"'}});
const {copyFile} = await import('node:fs/promises');
await copyFile('node_modules/plotly.js/plotly-mapbox.min.js', '../assets/plotly-mapbox-3.7.0.min.js');
