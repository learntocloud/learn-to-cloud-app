import { cp, mkdir, rm } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const root = fileURLToPath(new URL('../', import.meta.url));
const output = path.join(root, 'dist');
const destination = path.join(output, 'building-a-ladder');
const reveal = path.join(root, 'node_modules/reveal.js');

await rm(output, { recursive: true, force: true });
await mkdir(path.join(destination, 'vendor/reveal'), { recursive: true });

for (const input of ['index.html', 'styles.css', 'deck.js', 'assets']) {
  await cp(path.join(root, 'building-a-ladder', input), path.join(destination, input), {
    recursive: true,
  });
}

for (const [input, outputName] of [
  ['dist/reset.css', 'reset.css'],
  ['dist/reveal.css', 'reveal.css'],
  ['dist/reveal.js', 'reveal.js'],
  ['dist/plugin/notes.js', 'notes.js'],
  ['LICENSE', 'LICENSE'],
]) {
  await cp(path.join(reveal, input), path.join(destination, 'vendor/reveal', outputName));
}

console.log(`Built ${destination}`);
