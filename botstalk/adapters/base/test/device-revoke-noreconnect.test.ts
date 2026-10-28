import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { WebSocketServer, WebSocket } from 'ws';
import { AdapterClient } from '../src/client.js';

type Mode = 'close4403OnHello' | 'close4403AfterHello' | 'closeNormal';

class FakeGateway {
  readonly server: WebSocketServer;
  readonly url: string;
  readonly hellos: unknown[] = [];
  private readonly clients = new Set<WebSocket>();
  constructor(private readonly mode: Mode) {
    this.server = new WebSocketServer({ port: 0 });
    this.server.on('connection', (socket: WebSocket) => {
      this.clients.add(socket);
      socket.on('message', (data: Buffer) => {
        const frame = JSON.parse(data.toString()) as { type: string };
        if (frame.type === 'hello') {
          this.hellos.push(frame);
          if (mode === 'close4403OnHello') { socket.close(4403, 'device revoked'); return; }
          socket.send(JSON.stringify({ type: 'presence', payload: {} }));
          if (mode === 'close4403AfterHello') { setTimeout(() => socket.close(4403, 'device revoked'), 50); }
          if (mode === 'closeNormal') { setTimeout(() => socket.close(), 50); }
        }
      });
      socket.on('close', () => { this.clients.delete(socket); });
    });
    const addr = this.server.address() as { port: number };
    this.url = `ws://localhost:${addr.port}`;
  }
  async shutdown(): Promise<void> {
    for (const c of this.clients) { try { c.close(); } catch { /* ignore */ } }
    await new Promise<void>((resolve) => this.server.close(() => resolve()));
  }
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

describe('device-revoke-noreconnect', () => {
  let gateway: FakeGateway | undefined;
  let client: AdapterClient | undefined;

  beforeEach(() => {
    gateway = undefined;
    client = undefined;
  });

  afterEach(async () => {
    await client?.disconnect();
    await gateway?.shutdown();
  });

  it('4403 on hello does not reconnect', async () => {
    gateway = new FakeGateway('close4403OnHello');
    const calls: Array<[number, string]> = [];
    client = new AdapterClient({
      gatewayUrl: gateway.url,
      adapterId: 'adapter-test',
      onDeviceAuthFailed: (code: number, reason: string) => {
        calls.push([code, reason]);
      },
    });
    await client.connect();
    await sleep(2600);
    expect(gateway.hellos.length).toBe(1);
    expect(client.hasDeviceAuthFailure()).toBe(true);
    expect(calls).toEqual([[4403, 'device revoked']]);
  });

  it('4403 kick does not reconnect', async () => {
    gateway = new FakeGateway('close4403AfterHello');
    const calls: Array<[number, string]> = [];
    client = new AdapterClient({
      gatewayUrl: gateway.url,
      adapterId: 'adapter-test',
      onDeviceAuthFailed: (code: number, reason: string) => {
        calls.push([code, reason]);
      },
    });
    await client.connect();
    await sleep(2600);
    expect(gateway.hellos.length).toBe(1);
    expect(client.hasDeviceAuthFailure()).toBe(true);
    expect(calls.length).toBe(1);
  });

  it('normal close still reconnects', async () => {
    gateway = new FakeGateway('closeNormal');
    const calls: Array<[number, string]> = [];
    client = new AdapterClient({
      gatewayUrl: gateway.url,
      adapterId: 'adapter-test',
      onDeviceAuthFailed: (code: number, reason: string) => {
        calls.push([code, reason]);
      },
    });
    await client.connect();
    await sleep(2600);
    expect(gateway.hellos.length).toBeGreaterThanOrEqual(2);
    expect(client.hasDeviceAuthFailure()).toBe(false);
    expect(calls).toEqual([]);
  });

  it('manual restart', async () => {
    gateway = new FakeGateway('close4403OnHello');
    const calls: Array<[number, string]> = [];
    client = new AdapterClient({
      gatewayUrl: gateway.url,
      adapterId: 'adapter-test',
      onDeviceAuthFailed: (code: number, reason: string) => {
        calls.push([code, reason]);
      },
    });
    await client.connect();
    await sleep(2600);
    expect(gateway.hellos.length).toBe(1);
    expect(calls.length).toBe(1);
    await client.connect();
    await sleep(2600);
    expect(gateway.hellos.length).toBe(2);
    expect(calls.length).toBe(2);
  }, 15000);

  it('callback throw does not break', async () => {
    gateway = new FakeGateway('close4403OnHello');
    client = new AdapterClient({
      gatewayUrl: gateway.url,
      adapterId: 'adapter-test',
      onDeviceAuthFailed: () => {
        throw new Error('boom');
      },
    });
    await client.connect();
    await sleep(2600);
    expect(gateway.hellos.length).toBe(1);
    expect(client.hasDeviceAuthFailure()).toBe(true);
  });
});