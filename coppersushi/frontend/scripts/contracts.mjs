import {compile} from 'json-schema-to-typescript';
import {readFile, writeFile} from 'node:fs/promises';
for (const directory of ['pages/cnec/data', 'pages/powerflow', 'pages/polish-export-caps']) {
const schema = JSON.parse(await readFile(`${directory}/contracts.json`, 'utf8'));
const content = await compile(schema, directory === 'pages/cnec/data' ? 'CnecContracts' : directory === 'pages/powerflow' ? 'Dataset' : 'Investigation', {additionalProperties: false});
if (process.argv.includes('--check')) {
  if (await readFile(`${directory}/contracts.ts`, 'utf8') !== content) throw new Error('Run pixi run frontend-contracts');
} else await writeFile(`${directory}/contracts.ts`, content);

}
