import {compile} from 'json-schema-to-typescript';
import {readFile, writeFile} from 'node:fs/promises';
for (const directory of ['data', 'opf']) {
const schema = JSON.parse(await readFile(`src/${directory}/contracts.json`, 'utf8'));
const content = await compile(schema, directory === 'data' ? 'CnecContracts' : 'Dataset', {additionalProperties: false});
if (process.argv.includes('--check')) {
  if (await readFile(`src/${directory}/contracts.ts`, 'utf8') !== content) throw new Error('Run pixi run frontend-contracts');
} else await writeFile(`src/${directory}/contracts.ts`, content);

}
