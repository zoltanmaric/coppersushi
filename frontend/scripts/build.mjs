import './sprites.mjs';
import {build} from 'esbuild';
await build({entryPoints: ['src/index.tsx'], bundle: true, minify: true,
  format: 'iife', globalName: 'coppersushi_cnec', outfile: '../assets/cnec-view.js',
  define: {'process.env.NODE_ENV': '"production"'},
  // Share Dash's React instance, including the JSX runtime's internal dependency.
  plugins: [{name: 'dash-react', setup(build) {
    build.onResolve({filter: /^react$/}, () => ({path: 'react', namespace: 'dash'}));
    build.onLoad({filter: /.*/, namespace: 'dash'}, () => ({contents: 'module.exports = window.React;'}));
  }}],
});

// Standalone CNEC entry owns React; OPF remains on Dash's separate handler.
await build({entryPoints: ['src/bootstrap.tsx'], bundle: true, minify: true,
  format: 'iife', outfile: '../assets/cnec-app.js',
  define: {'process.env.NODE_ENV': '"production"'}});
const {copyFile} = await import('node:fs/promises');
await copyFile('node_modules/plotly.js/plotly-mapbox.min.js', '../assets/plotly-mapbox-3.7.0.min.js');
