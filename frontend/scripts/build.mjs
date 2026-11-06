import './sprites.mjs';
import {build} from 'esbuild';
// Standalone CNEC entry owns React; OPF remains on Dash's separate handler.
await build({entryPoints: ['src/bootstrap.tsx'], bundle: true, minify: true,
  format: 'iife', outfile: '../assets/cnec-app.js',
  define: {'process.env.NODE_ENV': '"production"'}});
const {copyFile} = await import('node:fs/promises');
await copyFile('node_modules/plotly.js/plotly-mapbox.min.js', '../assets/plotly-mapbox-3.7.0.min.js');
