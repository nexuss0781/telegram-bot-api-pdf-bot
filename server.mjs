import http from 'node:http';
import webhookHandler from './dist/webhook.js';
import workerCallbackHandler from './dist/worker-callback.js';
import { default as dashboardHandler } from './dist/dashboard.js';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const port = Number(process.env.PDFBOT_APP_PORT || 3000);
const publicDir = path.join(path.dirname(fileURLToPath(import.meta.url)), 'public');

function readBody(req) {
  return new Promise((resolve, reject) => {
    let body = '';
    req.setEncoding('utf8');
    req.on('data', (chunk) => {
      body += chunk;
      if (body.length > 2 * 1024 * 1024) reject(new Error('request body too large'));
    });
    req.on('end', () => {
      if (!body) return resolve(undefined);
      try { resolve(JSON.parse(body)); } catch { reject(new Error('invalid JSON body')); }
    });
    req.on('error', reject);
  });
}

function makeResponse(res) {
  return {
    setHeader(name, value) { res.setHeader(name, value); return this; },
    status(code) { res.statusCode = code; return this; },
    json(value) {
      const payload = JSON.stringify(value);
      res.setHeader('content-type', 'application/json');
      res.end(payload);
      return this;
    },
    send(value) { res.end(value); return this; },
  };
}

const server = http.createServer(async (req, res) => {
  try {
    if (req.url === '/dashboard' || req.url === '/dashboard/') {
      const html = fs.readFileSync(path.join(publicDir, 'index.html'));
      res.statusCode = 200;
      res.setHeader('content-type', 'text/html; charset=utf-8');
      res.end(html);
      return;
    }
    if (req.url === '/health' || req.url === '/api/health') {
      res.setHeader('content-type', 'application/json');
      res.end(JSON.stringify({ ok: true, service: 'telegram-pdf-bot-render' }));
      return;
    }
    if (!req.url?.startsWith('/api/')) {
      res.statusCode = 404;
      res.end('Not found');
      return;
    }
    const body = await readBody(req);
    const request = { method: req.method, headers: req.headers, body, url: req.url };
    const response = makeResponse(res);
    if (req.url.startsWith('/api/worker-callback')) await workerCallbackHandler(request, response);
    else if (req.url.startsWith('/api/dashboard')) await dashboardHandler(request, response);
    else await webhookHandler(request, response);
  } catch (error) {
    console.error('application request failed', error);
    if (!res.headersSent) {
      res.statusCode = 500;
      res.setHeader('content-type', 'application/json');
      res.end(JSON.stringify({ ok: false, error: 'Internal server error' }));
    }
  }
});

server.listen(port, '127.0.0.1', () => console.log(`PDF-BOT application listening on ${port}`));
