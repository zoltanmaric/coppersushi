import {mkdir, readFile, writeFile} from 'node:fs/promises';
import {Resvg} from '@resvg/resvg-js';

// Plotly resolves marker.symbol to <symbol>-15. Both densities use the same CSS pixels.
const icons = {
  'transformer-15': {x: 0, y: 0, width: 32, height: 24},
  'transformer-selected-15': {x: 32, y: 0, width: 32, height: 24},
  'triangle-15': {x: 66, y: 6, width: 12, height: 12},
};
export async function buildSprites(output) {
  await mkdir(output, {recursive: true});
  const svg = await readFile(new URL('../icons/markers.svg', import.meta.url));
  for (const ratio of [1, 2]) {
    const suffix = ratio === 2 ? '@2x' : '';
    const prefix = new URL(`cnec-markers${suffix}`, output);
    const bitmap = new Resvg(svg, {fitTo: {mode: 'zoom', value: ratio}}).render().asPng();
    const index = Object.fromEntries(Object.entries(icons).map(([key, box]) =>
      [key, {...Object.fromEntries(Object.entries(box).map(([key, value]) => [key, value * ratio])), pixelRatio: ratio}]));
    await writeFile(new URL(`${prefix.href}.png`), bitmap);
    await writeFile(new URL(`${prefix.href}.json`), JSON.stringify(index));
  }
}
