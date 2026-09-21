import { createServer } from 'node:http';
import { constants } from 'node:fs';
import { open, readdir } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const dist = fileURLToPath(new URL('../dist/', import.meta.url));
const types = {
  '.html': 'text/html; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.webp': 'image/webp',
  '.gif': 'image/gif',
  '.ico': 'image/x-icon',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
};

async function loadAssets(directory, prefix = '') {
  const assets = new Map();
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const filename = path.join(directory, entry.name);
    const key = `${prefix}${entry.name}`;
    if (entry.isDirectory()) {
      for (const [name, asset] of await loadAssets(filename, `${key}/`)) assets.set(name, asset);
    } else if (entry.isFile()) {
      const file = await open(filename, constants.O_RDONLY | constants.O_NOFOLLOW);
      try {
        assets.set(key, {
          body: await file.readFile(),
          type: types[path.extname(entry.name)] ?? 'application/octet-stream',
        });
      } finally {
        await file.close();
      }
    } else {
      throw new Error(`Unsupported asset type: ${filename}`);
    }
  }
  return assets;
}

export async function createStaticServer({ basePath = '/' } = {}) {
  if (!/^\/(?:[a-zA-Z0-9_-]+\/)*$/.test(basePath)) {
    throw new Error('BASE_PATH must start and end with / and contain only simple path segments');
  }
  // Requests only access this snapshot, never paths on the filesystem.
  const assets = await loadAssets(dist);
  return createServer((request, response) => {
    const send = (status, message) => {
      response.writeHead(status, { 'Content-Type': 'text/plain; charset=utf-8' });
      response.end(request.method === 'HEAD' ? undefined : message);
    };
    if (!['GET', 'HEAD'].includes(request.method)) {
      response.setHeader('Allow', 'GET, HEAD');
      send(405, 'Method not allowed');
      return;
    }
    let pathname;
    try {
      pathname = decodeURIComponent(new URL(request.url, 'http://localhost').pathname);
    } catch {
      send(400, 'Malformed URL');
      return;
    }
    if (pathname.includes('\0') || pathname.includes('\\') || pathname.split('/').includes('..')) {
      send(400, 'Invalid path');
      return;
    }
    if (!pathname.startsWith(basePath)) {
      send(404, 'Not found');
      return;
    }
    const key = pathname.slice(basePath.length);
    if (!pathname.endsWith('/') && assets.has(`${key}/index.html`)) {
      response.writeHead(301, { Location: `${encodeURI(pathname)}/` });
      response.end();
      return;
    }
    const asset = assets.get(pathname.endsWith('/') ? `${key}index.html` : key);
    if (!asset) {
      send(404, 'Not found');
      return;
    }
    response.writeHead(200, {
      'Content-Type': asset.type,
      'Content-Length': asset.body.length,
      'Cache-Control': 'no-store',
    });
    response.end(request.method === 'HEAD' ? undefined : asset.body);
  });
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  const port = Number(process.env.PORT ?? 4173);
  if (!Number.isInteger(port) || port < 1 || port > 65535) {
    throw new Error('PORT must be an integer from 1 to 65535');
  }
  const basePath = process.env.BASE_PATH ?? '/';
  const server = await createStaticServer({ basePath });
  server.on('error', (error) => {
    console.error(error.message);
    process.exitCode = 1;
  });
  server.listen(port, '127.0.0.1', () => {
    console.log(`Talk: http://localhost:${port}${basePath}building-a-ladder/`);
  });
}
