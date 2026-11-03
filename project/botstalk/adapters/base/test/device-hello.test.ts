import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { WebSocketServer, WebSocket } from 'ws';
import { AdapterClient } from '../src/client.js';

type TestFrame = { type: string; payload: Record<string, unknown> };

class FakeGateway {
  readonly frames: TestFrame[] = [];
  readonly server: WebSocketServer;
  readonly url: string;
  private readonly clients = new Set<WebSocket>();

  constructor() {
    this.server = new WebSocketServer({ port: 0 });
    this.server.on('connection', (socket: WebSocket) => {
      this.clients.add(socket);
      socket.on('message', (data: Buffer) => {
        const frame = JSON.parse(data.toString()) as TestFrame;
        this.frames.push(frame);
        if (frame.type === 'hello') {
          socket.send(JSON.stringify({ type: 'presence', payload: {} }));
        }
      });
      socket.on('close', () => {
        this.clients.delete(socket);
      });
    });
    const addr = this.server.address() as { port: number };
    this.url = `ws://localhost:${addr.port}`;
  }

  async close(): Promise<void> {
    for (const c of this.clients) c.close();
    await new Promise<void>((resolve) => this.server.close(() => resolve()));
  }
}

async function waitFor(predicate: () => boolean, timeout = 2000): Promise<void> {
  const start = Date.now();
  while (!predicate()) {
    if (Date.now() - start > timeout) throw new Error('waitFor timeout');
    await new Promise((r) => setTimeout(r, 10));
  }
}

describe('device hello', () => {
  let gateway: FakeGateway;
  let client: AdapterClient | undefined;
  let savedDeviceId: string | undefined;
  let savedDeviceKey: string | undefined;

  beforeEach(() => {
    gateway = new FakeGateway();
    savedDeviceId = process.env.BOTSTALK_DEVICE_ID;
    savedDeviceKey = process.env.BOTSTALK_DEVICE_KEY;
    delete process.env.BOTSTALK_DEVICE_ID;
    delete process.env.BOTSTALK_DEVICE_KEY;
  });

  afterEach(async () => {
    await client?.disconnect();
    await gateway.close();
    if (savedDeviceId !== undefined) {
      process.env.BOTSTALK_DEVICE_ID = savedDeviceId;
    } else {
      delete process.env.BOTSTALK_DEVICE_ID;
    }
    if (savedDeviceKey !== undefined) {
      process.env.BOTSTALK_DEVICE_KEY = savedDeviceKey;
    } else {
      delete process.env.BOTSTALK_DEVICE_KEY;
    }
    vi.useRealTimers();
  });

  it('opts device pair sent', async () => {
    client = new AdapterClient({
      adapterId: 'adapter-test',
      gatewayUrl: gateway.url,
      device: { id: 'dev-1', key: 'k-abc' },
    });
    await client.connect();
    await waitFor(() => gateway.frames.some((f) => f.type === 'hello'));
    const hello = gateway.frames.find((f) => f.type === 'hello')!;
    expect(hello.payload).toMatchObject({
      adapter_id: 'adapter-test',
      device_id: 'dev-1',
      device_key: 'k-abc',
    });
    expect(hello.payload).toHaveProperty('last_seen_seq');
  });

  it('no device no fields', async () => {
    client = new AdapterClient({
      adapterId: 'adapter-test',
      gatewayUrl: gateway.url,
    });
    await client.connect();
    await waitFor(() => gateway.frames.some((f) => f.type === 'hello'));
    const hello = gateway.frames.find((f) => f.type === 'hello')!;
    expect(hello.payload).not.toHaveProperty('device_id');
    expect(hello.payload).not.toHaveProperty('device_key');
  });

  it('env pair sent', async () => {
    process.env.BOTSTALK_DEVICE_ID = 'env-dev';
    process.env.BOTSTALK_DEVICE_KEY = 'env-key';
    client = new AdapterClient({
      adapterId: 'adapter-test',
      gatewayUrl: gateway.url,
    });
    await client.connect();
    await waitFor(() => gateway.frames.some((f) => f.type === 'hello'));
    const hello = gateway.frames.find((f) => f.type === 'hello')!;
    expect(hello.payload).toMatchObject({
      device_id: 'env-dev',
      device_key: 'env-key',
    });
  });

  it('opts overrides env', async () => {
    process.env.BOTSTALK_DEVICE_ID = 'env-dev';
    process.env.BOTSTALK_DEVICE_KEY = 'env-key';
    client = new AdapterClient({
      adapterId: 'adapter-test',
      gatewayUrl: gateway.url,
      device: { id: 'opt-dev', key: 'opt-key' },
    });
    await client.connect();
    await waitFor(() => gateway.frames.some((f) => f.type === 'hello'));
    const hello = gateway.frames.find((f) => f.type === 'hello')!;
    expect(hello.payload).toMatchObject({
      device_id: 'opt-dev',
      device_key: 'opt-key',
    });
  });

  it('single opts field omitted', async () => {
    // 类型断言：故意只给 id 不给 key，验证 resolveDeviceCredentials 拒绝单字段
    const device = { id: 'only-id' } as { id: string; key: string };
    client = new AdapterClient({
      adapterId: 'adapter-test',
      gatewayUrl: gateway.url,
      device,
    });
    await client.connect();
    await waitFor(() => gateway.frames.some((f) => f.type === 'hello'));
    const hello = gateway.frames.find((f) => f.type === 'hello')!;
    expect(hello.payload).not.toHaveProperty('device_id');
    expect(hello.payload).not.toHaveProperty('device_key');
  });

  it('single env field omitted', async () => {
    process.env.BOTSTALK_DEVICE_ID = 'env-dev';
    client = new AdapterClient({
      adapterId: 'adapter-test',
      gatewayUrl: gateway.url,
    });
    await client.connect();
    await waitFor(() => gateway.frames.some((f) => f.type === 'hello'));
    const hello = gateway.frames.find((f) => f.type === 'hello')!;
    expect(hello.payload).not.toHaveProperty('device_id');
    expect(hello.payload).not.toHaveProperty('device_key');
  });

  it('empty strings omitted', async () => {
    client = new AdapterClient({
      adapterId: 'adapter-test',
      gatewayUrl: gateway.url,
      device: { id: '', key: '' },
    });
    await client.connect();
    await waitFor(() => gateway.frames.some((f) => f.type === 'hello'));
    const hello = gateway.frames.find((f) => f.type === 'hello')!;
    expect(hello.payload).not.toHaveProperty('device_id');
    expect(hello.payload).not.toHaveProperty('device_key');
  });

  it('empty env omitted', async () => {
    process.env.BOTSTALK_DEVICE_ID = '';
    process.env.BOTSTALK_DEVICE_KEY = 'some-key';
    client = new AdapterClient({
      adapterId: 'adapter-test',
      gatewayUrl: gateway.url,
    });
    await client.connect();
    await waitFor(() => gateway.frames.some((f) => f.type === 'hello'));
    const hello = gateway.frames.find((f) => f.type === 'hello')!;
    expect(hello.payload).not.toHaveProperty('device_id');
    expect(hello.payload).not.toHaveProperty('device_key');
  });
});
