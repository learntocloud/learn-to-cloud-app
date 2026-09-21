import { createServer } from 'node:http';
import { readFile, realpath, stat } from 'node:fs/promises';
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

export function createStaticServer({ basePath = '/' } = {}) {
  if (!/^\/(?:[a-zA-Z0-9_-]+\/)*$/.test(basePath)) {
    throw new Error('BASE_PATH must start and end with / and contain only simple path segments');
  }
  return createServer(async (request, response) => {
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
    try {
      const root = await realpath(dist);
      let filename = await realpath(path.join(root, pathname.slice(basePath.length)));
      const isInsideRoot = (target) => {
        const relative = path.relative(root, target);
        return relative !== '..' && !relative.startsWith(`..${path.sep}`) && !path.isAbsolute(relative);
      };
      if (!isInsideRoot(filename)) {
        send(403, 'Forbidden');
        return;
      }
      if ((await stat(filename)).isDirectory()) {
        if (!pathname.endsWith('/')) {
          response.writeHead(301, { Location: `${encodeURI(pathname)}/` });
          response.end();
          return;
        }
        filename = await realpath(path.join(filename, 'index.html'));
      }
      if (!isInsideRoot(filename)) {
        send(403, 'Forbidden');
        return;
      }
      const body = await readFile(filename);
      response.writeHead(200, {
        'Content-Type': types[path.extname(filename)] ?? 'application/octet-stream',
        'Content-Length': body.length,
        'Cache-Control': 'no-store',
      });
      response.end(request.method === 'HEAD' ? undefined : body);
    } catch (error) {
      if (['ENOENT', 'ENOTDIR', 'EISDIR'].includes(error.code)) {
        send(404, 'Not found');
      } else if (error.code === 'EACCES') {
        send(403, 'Forbidden');
      } else {
        console.error(error);
        send(500, 'Unable to read file');
      }
    }
  });
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  const port = Number(process.env.PORT ?? 4173);
  if (!Number.isInteger(port) || port < 1 || port > 65535) {
    throw new Error('PORT must be an integer from 1 to 65535');
  }
  const basePath = process.env.BASE_PATH ?? '/';
  const server = createStaticServer({ basePath });
  server.on('error', (error) => {
    console.error(error.message);
    process.exitCode = 1;
  });
  server.listen(port, '127.0.0.1', () => {
    console.log(`Talk: http://localhost:${port}${basePath}building-a-ladder/`);
  });
}
