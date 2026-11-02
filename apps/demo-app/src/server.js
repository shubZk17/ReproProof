// Node.js zero-dependency HTTP server for ReproProof inventory demo app

const http = require('http');
const fs = require('fs');
const path = require('path');
const inventory = require('./inventory');

const PORT = process.env.PORT || 3000;
const PUBLIC_DIR = path.join(__dirname, 'public');

function parseBody(req) {
  return new Promise((resolve, reject) => {
    let body = '';
    req.on('data', chunk => {
      body += chunk.toString();
    });
    req.on('end', () => {
      if (!body) return resolve({});
      try {
        resolve(JSON.parse(body));
      } catch (err) {
        resolve({});
      }
    });
    req.on('error', reject);
  });
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, `http://${req.headers.host || 'localhost'}`);
  const pathname = url.pathname;

  // CORS headers for development/testing
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') {
    res.writeHead(204);
    res.end();
    return;
  }

  // API Routes
  if (pathname === '/health' && req.method === 'GET') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ status: 'ok', app: 'inventory-demo' }));
    return;
  }

  if (pathname === '/api/items' && req.method === 'GET') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify(inventory.getItems()));
    return;
  }

  if (pathname === '/api/items' && req.method === 'POST') {
    const body = await parseBody(req);
    const item = inventory.addItem(body.name || 'Unnamed', body.count || 1);
    res.writeHead(201, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify(item));
    return;
  }

  if (pathname.startsWith('/api/items/') && req.method === 'DELETE') {
    const id = pathname.replace('/api/items/', '');
    const success = inventory.deleteItem(id);
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ success, id }));
    return;
  }

  if (pathname === '/api/reset' && req.method === 'POST') {
    const items = inventory.resetItems();
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ success: true, items }));
    return;
  }

  // Static files
  if (pathname === '/' || pathname === '/index.html') {
    const indexPath = path.join(PUBLIC_DIR, 'index.html');
    fs.readFile(indexPath, (err, data) => {
      if (err) {
        res.writeHead(500);
        res.end('Error loading index.html');
        return;
      }
      res.writeHead(200, { 'Content-Type': 'text/html' });
      res.end(data);
    });
    return;
  }

  res.writeHead(404, { 'Content-Type': 'text/plain' });
  res.end('Not Found');
});

server.listen(PORT, () => {
  console.log(`Inventory Demo running at http://localhost:${PORT}`);
});

process.on('SIGTERM', () => {
  server.close(() => process.exit(0));
});
process.on('SIGINT', () => {
  server.close(() => process.exit(0));
});
