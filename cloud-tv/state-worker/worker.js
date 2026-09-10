const TV_ROOM = 'don-miguel';

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const id = env.TV_STATE.idFromName(TV_ROOM);
    const stub = env.TV_STATE.get(id);

    if (url.pathname === '/api/health') {
      return json({ ok: true, service: 'Billares Don Miguel TV state worker' });
    }

    if (url.pathname === '/api/state') {
      return stub.fetch(new Request('https://state/get'));
    }

    if (url.pathname === '/api/publish' && request.method === 'POST') {
      return stub.fetch(new Request('https://state/publish', request));
    }

    if (url.pathname === '/api/stream') {
      return stub.fetch(new Request('https://state/stream', request));
    }

    return new Response('Billares Don Miguel TV state worker', { status: 404 });
  },
};

export class BillaresTvState extends DurableObject {
  constructor(ctx, env) {
    super(ctx, env);
    this.clients = new Set();
  }

  async fetch(request) {
    const url = new URL(request.url);

    if (url.pathname === '/get') {
      this.ctx.storage.sql.exec('CREATE TABLE IF NOT EXISTS state (id TEXT PRIMARY KEY, value TEXT NOT NULL)');
      const row = this.ctx.storage.sql.exec('SELECT value FROM state WHERE id = ?', TV_ROOM).toArray()[0];
      return json(row ? JSON.parse(row.value) : emptyState());
    }

    if (url.pathname === '/publish' && request.method === 'POST') {
      const body = await request.text();
      if (body.length > 200000) return new Response('Payload too large', { status: 413 });
      try { JSON.parse(body); } catch (_) { return new Response('Invalid JSON', { status: 400 }); }
      this.ctx.storage.sql.exec('CREATE TABLE IF NOT EXISTS state (id TEXT PRIMARY KEY, value TEXT NOT NULL)');
      this.ctx.storage.sql.exec(
        'INSERT INTO state (id,value) VALUES (?,?) ON CONFLICT(id) DO UPDATE SET value=excluded.value',
        TV_ROOM,
        body,
      );
      this.broadcast(body);
      return new Response('ok');
    }

    if (url.pathname === '/stream') {
      if (request.headers.get('Upgrade')?.toLowerCase() !== 'websocket') {
        return new Response('Expected WebSocket', { status: 426 });
      }
      const pair = new WebSocketPair();
      const [client, server] = Object.values(pair);
      server.accept();
      this.clients.add(server);
      server.addEventListener('close', () => this.clients.delete(server));
      server.addEventListener('error', () => this.clients.delete(server));
      this.ctx.storage.sql.exec('CREATE TABLE IF NOT EXISTS state (id TEXT PRIMARY KEY, value TEXT NOT NULL)');
      const row = this.ctx.storage.sql.exec('SELECT value FROM state WHERE id = ?', TV_ROOM).toArray()[0];
      server.send(row ? row.value : JSON.stringify(emptyState()));
      return new Response(null, { status: 101, webSocket: client });
    }

    return new Response('Not found', { status: 404 });
  }

  broadcast(body) {
    for (const client of this.clients) {
      try { client.send(body); } catch (_) { this.clients.delete(client); }
    }
  }
}

function emptyState() {
  return {
    brand: 'Billares Don Miguel',
    updatedAt: new Date().toISOString(),
    tables: [1,2,3,4,5].map(number => ({
      number,
      status: 'available',
      start: null,
      end: null,
      amount: 0,
      rate: number <= 2 ? 120 : number <= 4 ? 100 : 70,
    })),
  };
}

function json(value, status = 200) {
  return new Response(JSON.stringify(value), {
    status,
    headers: { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store' },
  });
}
