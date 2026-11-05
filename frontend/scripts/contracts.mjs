import {compile} from 'json-schema-to-typescript';
import {readFile, writeFile} from 'node:fs/promises';
const schema = JSON.parse(await readFile('src/contracts.json', 'utf8'));
const content = await compile(schema, 'CnecContracts', {additionalProperties: false});
if (process.argv.includes('--check')) {
  if (await readFile('src/contracts.ts', 'utf8') !== content) throw new Error('Run pixi run frontend-contracts');
} else await writeFile('src/contracts.ts', content);
