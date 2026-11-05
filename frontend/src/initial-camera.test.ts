import {expect, test} from 'vitest';
import {initialCoreCamera} from './initial-camera';

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
