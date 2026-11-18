import assert from 'node:assert/strict';
import {launchBrowser} from './browser.js';

// Offline image check: isolated contexts must each render through software WebGL.
const browser=await launchBrowser();
try {
  await Promise.all(Array.from({length:3},async()=>{
    const context=await browser.newContext();
    try {
      const page=await context.newPage();
      const pixel=await page.evaluate(()=>{
        const canvas=document.createElement('canvas');
        const gl=canvas.getContext('webgl');
        if(!gl) throw new Error('WebGL unavailable');
        gl.clearColor(1,0,0,1);
        gl.clear(gl.COLOR_BUFFER_BIT);
        const pixel=new Uint8Array(4);
        gl.readPixels(0,0,1,1,gl.RGBA,gl.UNSIGNED_BYTE,pixel);
        return [...pixel];
      });
      assert.deepEqual(pixel,[255,0,0,255]);
    } finally {await context.close();}
  }));
  console.log('Three parallel Chromium contexts rendered WebGL successfully.');
} finally {await browser.close();}
