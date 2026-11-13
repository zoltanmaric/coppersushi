import {expect, test} from 'vitest';
import {initialCoreCamera, initialBoundsCamera} from './initial-camera';

test.each([[1280,720],[1199,1314],[390,844]])('Core fits the starting viewport %i×%i with room for controls', (width, height) => {
  const camera = initialCoreCamera(width, height);
  const scale = 512 * 2 ** camera.zoom;
  const y = (latitude: number) => (1 - Math.asinh(Math.tan(latitude * Math.PI / 180)) / Math.PI) / 2;
  expect((29.702119 + 4.794777) / 360 * scale).toBeLessThan(width - 48);
  expect((y(41.366103) - y(55.056332)) * scale).toBeLessThan(height - (width <= 650 ? 290 : 230));
  expect(camera.center.lon).toBeCloseTo(12.5);
  expect(camera.center.lat).toBeGreaterThan(48);
  expect(camera.center.lat).toBeLessThan(49);
});

 test.each([[2388,1267],[1280,720],[390,844]])('network bounds fit %i×%i with clearance', (width,height)=>{
  const bounds = [-10,35,33,71] as const;
  const camera = initialBoundsCamera(bounds,width,height);
  const scale = 512 * 2 ** camera.zoom;
  const y = (lat:number)=>(1-Math.asinh(Math.tan(lat*Math.PI/180))/Math.PI)/2;
  expect(43/360*scale).toBeLessThanOrEqual(width-55);
  expect((y(35)-y(71))*scale).toBeLessThanOrEqual(height-(width<=650?299:239));
  expect(camera.pitch).toBe(0);
});

test.each([[1743,1267],[1280,674],[390,798]])('tilted network fits projected corners at %i×%i', (width,height)=>{
  const camera=initialBoundsCamera([-10,35,33,71],width,height,60);
  const y=(lat:number)=>(1-Math.asinh(Math.tan(lat*Math.PI/180))/Math.PI)/2;
  const scale=512*2**camera.zoom, distance=1.5*height;
  for(const lon of [-10,33]) for(const lat of [35,71]) {
    const dy=(y(lat)-y(camera.center.lat))*scale;
    const perspective=distance/(distance-dy*Math.sin(Math.PI/3));
    expect(Math.abs((lon-camera.center.lon)/360*scale*perspective)).toBeLessThanOrEqual((width-56)/2+1e-6);
    expect(Math.abs(dy*.5*perspective)).toBeLessThanOrEqual((height-(width<=650?300:240))/2+1e-6);
  }
  expect(camera.pitch).toBe(60);
});
