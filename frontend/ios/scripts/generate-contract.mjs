import fs from 'node:fs/promises';
import openapiTS, { astToString } from 'openapi-typescript';
const source = new URL('../../../docs/技术开发/02接口与权限/openapi.json', import.meta.url);
const document = JSON.parse(await fs.readFile(source, 'utf8'));
const types = astToString(await openapiTS(document, { alphabetize: true }));
const schema =
  JSON.stringify({ $id: 'yirenyoulu-contract', components: document.components }, null, 2) + '\n';
for (const [name, value] of [
  ['generated.ts', types],
  ['contract.json', schema],
]) {
  const path = new URL('../src/api/' + name, import.meta.url);
  if (process.argv.includes('--check')) {
    if ((await fs.readFile(path, 'utf8')) !== value)
      throw new Error('Client contract differs: ' + name);
  } else await fs.writeFile(path, value);
}
