const fs = require('fs');
const http = require('http');
const path = require('path');

const publicDir = path.resolve(__dirname, '..', 'public');
const port = Number(process.argv[2] || process.env.PORT || 3000);
const mimeTypes = {
  '.css': 'text/css; charset=utf-8',
  '.html': 'text/html; charset=utf-8',
  '.jpg': 'image/jpeg',
  '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.md': 'text/markdown; charset=utf-8',
  '.png': 'image/png',
  '.svg': 'image/svg+xml',
  '.txt': 'text/plain; charset=utf-8',
  '.webp': 'image/webp',
  '.xml': 'application/xml; charset=utf-8',
};

if (!Number.isInteger(port) || port < 1 || port > 65535) {
  console.error(`Invalid port: ${process.argv[2] || process.env.PORT}`);
  process.exit(1);
}

function send(response, status, body) {
  response.writeHead(status, { 'content-type': 'text/plain; charset=utf-8' });
  response.end(body);
}

const server = http.createServer((request, response) => {
  if (request.method !== 'GET' && request.method !== 'HEAD') {
    send(response, 405, 'Method not allowed\n');
    return;
  }

  let pathname;
  try {
    pathname = decodeURIComponent(new URL(request.url, 'http://localhost').pathname);
  } catch {
    send(response, 400, 'Bad request\n');
    return;
  }

  let filePath = path.resolve(publicDir, `.${pathname}`);
  if (filePath !== publicDir && !filePath.startsWith(`${publicDir}${path.sep}`)) {
    send(response, 403, 'Forbidden\n');
    return;
  }

  fs.stat(filePath, (statError, stats) => {
    if (!statError && stats.isDirectory()) filePath = path.join(filePath, 'index.html');

    fs.stat(filePath, (fileError, fileStats) => {
      if (fileError || !fileStats.isFile()) {
        send(response, 404, 'Not found\n');
        return;
      }

      response.writeHead(200, {
        'content-length': fileStats.size,
        'content-type': mimeTypes[path.extname(filePath).toLowerCase()] || 'application/octet-stream',
      });
      if (request.method === 'HEAD') response.end();
      else fs.createReadStream(filePath).pipe(response);
    });
  });
});

server.listen(port, '0.0.0.0', () => {
  console.log(`Serving ${publicDir} on port ${port}`);
});

for (const signal of ['SIGINT', 'SIGTERM']) {
  process.on(signal, () => server.close(() => process.exit(0)));
}
