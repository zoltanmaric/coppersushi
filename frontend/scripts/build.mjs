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
