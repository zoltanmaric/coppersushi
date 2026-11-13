import {cp,copyFile,mkdir,rm} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {build} from 'esbuild';
import {buildSprites} from './sprites.mjs';

const root = new URL('../',import.meta.url);
const dist = new URL('dist/',root);
const assets = new URL('assets/',dist);
await rm(dist,{recursive:true,force:true});
await mkdir(assets,{recursive:true});
await cp(new URL('assets/',root),assets,{recursive:true});
await buildSprites(assets);
await build({absWorkingDir:fileURLToPath(root),
  entryPoints:{'cnec-app':'pages/cnec/bootstrap.tsx','opf-app':'pages/powerflow/bootstrap.tsx'},
  bundle:true,minify:true,format:'iife',outdir:fileURLToPath(assets),
  define:{'process.env.NODE_ENV':'"production"'}});
await copyFile(new URL('node_modules/plotly.js/plotly-mapbox.min.js',root),
  new URL('plotly-mapbox-3.7.0.min.js',assets));
