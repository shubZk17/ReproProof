// Pinned TodoMVC Node server for ReproProof R12 third-party testing

const http = require('http');
const fs = require('fs');
const path = require('path');
const todos = require('./todos');

const PORT = process.env.PORT || 3005;
const PUBLIC_DIR = path.join(__dirname, 'public');

function parseBody(req) {
  return new Promise((resolve) => {
    let body = '';
    req.on('data', chunk => { body += chunk.toString(); });
    req.on('end', () => {
      try { resolve(JSON.parse(body || '{}')); } catch (e) { resolve({}); }
    });
  });
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, `http://${req.headers.host || 'localhost'}`);
  const pathname = url.pathname;

  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') {
    res.writeHead(204);
    res.end();
    return;
  }

  if (pathname === '/health' && req.method === 'GET') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ status: 'ok', app: 'todo-app' }));
    return;
  }

  if (pathname === '/api/todos' && req.method === 'GET') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify(todos.getTodos()));
    return;
  }

  if (pathname === '/api/todos' && req.method === 'POST') {
    const body = await parseBody(req);
    const item = todos.addTodo(body.title || 'Untitled');
    res.writeHead(201, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify(item));
    return;
  }

  if (pathname.endsWith('/toggle') && req.method === 'POST') {
    const parts = pathname.split('/');
    const id = parts[3];
    const item = todos.toggleTodo(id);
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify(item || {}));
    return;
  }

  if (pathname === '/api/todos/clear-completed' && req.method === 'POST') {
    const items = todos.clearCompleted();
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify(items));
    return;
  }

  if (pathname === '/api/reset' && req.method === 'POST') {
    const items = todos.resetTodos();
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify(items));
    return;
  }

  if (pathname === '/' || pathname === '/index.html') {
    fs.readFile(path.join(PUBLIC_DIR, 'index.html'), (err, data) => {
      if (err) {
        res.writeHead(500);
        res.end('Error loading index');
        return;
      }
      res.writeHead(200, { 'Content-Type': 'text/html' });
      res.end(data);
    });
    return;
  }

  res.writeHead(404);
  res.end('Not Found');
});

server.listen(PORT, () => {
  console.log(`TodoMVC server running on http://localhost:${PORT}`);
});
