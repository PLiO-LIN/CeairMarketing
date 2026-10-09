import { readFile, access } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('../apps/web-v32/', import.meta.url));
const html = await readFile(path.join(root, 'index.html'), 'utf8');
const docker = await readFile(path.join(root, 'Dockerfile'), 'utf8');
const copies = docker.split(/\r?\n/).filter(line => line.startsWith('COPY ')).flatMap(line => line.trim().split(/\s+/).slice(1, -1));
const references = [...html.matchAll(/<(?:script|link)\b[^>]*(?:src|href)="([^"]+)"/g)].map(match => match[1]).filter(value => value.startsWith('./'));
for (const reference of references) {
  const relative = reference.slice(2).split('?')[0];
  await access(path.join(root, relative));
  if (!copies.some(copy => relative === copy || relative.startsWith(copy + '/'))) {
    throw new Error('Docker image omits browser asset: ' + relative);
  }
}
if (/<script\b[^>]*src="https?:/i.test(html)) throw new Error('Workbench scripts must load locally.');
console.log('Browser assets exist and are included in the Docker image.');
