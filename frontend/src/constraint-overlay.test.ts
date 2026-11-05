import {expect, test} from 'vitest';
import {project} from './constraint-overlay';

const camera = {lat: 50, lon: 10, zoom: 3.5, bearing: 0};
test('projects the camera centre to the viewport centre', () => {
  expect(project(10, 50, camera, 1000, 600)).toEqual([500, 300]);
});
test('projects east right, north up, and scales with zoom', () => {
  const centre = project(10, 50, camera, 1000, 600);
  const east = project(11, 50, camera, 1000, 600);
  const north = project(10, 51, camera, 1000, 600);
  expect(east[0]).toBeGreaterThan(centre[0]);
  expect(north[1]).toBeLessThan(centre[1]);
  expect(project(11, 50, {...camera, zoom: 4.5}, 1000, 600)[0] - centre[0]).toBeCloseTo(2 * (east[0] - centre[0]));
});
