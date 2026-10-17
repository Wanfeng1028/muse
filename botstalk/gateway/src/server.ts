import { createServer, type Server } from "node:http";
import { WebSocketServer } from "ws";
import { ZOMBIE_SWEEP_MS } from "@botstalk/protocol";
import type { Db } from "./db.js";
import { getRoomHistory, listPresence } from "./db.js";
import { Hub } from "./hub.js";
import { routeMessage, routeStream } from "./router.js";
import type { GatewayConfig } from "./config.js";
import type { Envelope, MessagePayload, StreamPayload } from "@botstalk/protocol";
import { createArtifactService } from "./artifacts.js";

// 排序规则：online 在前，其余按 adapter_id 字典序
function sortPresence<T extends { adapter_id: string; status: string }>(rows: T[]): T[] {
  return [...rows].sort((a, b) => {
    const aOnline = a.status === "online" ? 0 : 1;
    const bOnline = b.status === "online" ? 0 : 1;
    if (aOnline !== bOnline) return aOnline - bOnline;
    return a.adapter_id < b.adapter_id ? -1 : a.adapter_id > b.adapter_id ? 1 : 0;
  });
}

export interface RunningServer {
  httpServer: Server;
  wss: WebSocketServer;
  hub: Hub;
  close(): Promise<void>;
}

export function startServer(config: GatewayConfig, db: Db): RunningServer {
  const artifacts = createArtifactService(db, config);
  const httpServer = createServer((req, res) => {
    if (artifacts.handle(req, res)) return;

    const url = req.url ?? "";
    const method = req.method ?? "GET";

    // GET /api/rooms/:room/history
    const historyMatch = url.match(/^\/api\/rooms\/([^/?]+)\/history(?:\?|$)/);
    if (historyMatch && method === "GET") {
      res.setHeader("access-control-allow-origin", "*");
      const room = decodeURIComponent(historyMatch[1]);
      if (!room) {
        res.writeHead(400, { "content-type": "application/json" });
        res.end('{"error":"room required"}');
        return;
      }
      const parsed = new URL(url, "http://localhost");
      let limit = 50;
      const limitParam = parsed.searchParams.get("limit");
      if (limitParam !== null) {
        const n = Number.parseInt(limitParam, 10);
        if (Number.isFinite(n) && n > 0) limit = Math.min(n, 200);
      }
      let beforeId: number | undefined;
      const beforeParam = parsed.searchParams.get("before_id");
      if (beforeParam !== null) {
        const n = Number.parseInt(beforeParam, 10);
        if (Number.isFinite(n)) beforeId = n;
      }
      const rows = getRoomHistory(db, room, limit, beforeId);
      const sorted = [...rows].sort((a, b) => a.id - b.id);
      const messages = sorted.map((r) => {
        let payload: unknown;
        try {
          payload = JSON.parse(r.payload);
        } catch {
          payload = r.payload;
        }
        return {
          id: r.id,
          room: r.room,
          sender: r.sender,
          seq: r.seq,
          type: r.type,
          payload,
          ts: r.ts,
        };
      });
      res.writeHead(200, { "content-type": "application/json" });
      res.end(JSON.stringify({ messages }));
      return;
    }

    // GET /api/rooms/:room/presence
    const presenceMatch = url.match(/^\/api\/rooms\/([^/?]+)\/presence(?:\?|$)/);
    if (presenceMatch && method === "GET") {
      res.setHeader("access-control-allow-origin", "*");
      const room = decodeURIComponent(presenceMatch[1]);
      if (!room) {
        res.writeHead(400, { "content-type": "application/json" });
        res.end('{"error":"room required"}');
        return;
      }
      const rows = listPresence(db);
      const members = sortPresence(rows).map((r) => ({
        adapter_id: r.adapter_id,
        status: r.status,
        last_seen_ms: r.last_seen_ms,
        usage_in: r.usage_in,
        usage_out: r.usage_out,
      }));
      res.writeHead(200, { "content-type": "application/json" });
      res.end(JSON.stringify({ members }));
      return;
    }

    // GET /api/rooms/:room/usage
    const usageMatch = url.match(/^\/api\/rooms\/([^/?]+)\/usage(?:\?|$)/);
    if (usageMatch && method === "GET") {
      res.setHeader("access-control-allow-origin", "*");
      const room = decodeURIComponent(usageMatch[1]);
      if (!room) {
        res.writeHead(400, { "content-type": "application/json" });
        res.end('{"error":"room required"}');
        return;
      }
      const rows = sortPresence(listPresence(db));
      let totalIn = 0;
      let totalOut = 0;
      const adapters = rows.map((r) => {
        totalIn += r.usage_in;
        totalOut += r.usage_out;
        return {
          adapter_id: r.adapter_id,
          status: r.status,
          input_tokens: r.usage_in,
          output_tokens: r.usage_out,
          last_seen_ms: r.last_seen_ms,
        };
      });
      res.writeHead(200, { "content-type": "application/json" });
      res.end(
        JSON.stringify({
          adapters,
          total: { input_tokens: totalIn, output_tokens: totalOut },
        }),
      );
      return;
    }

    if (req.url === "/healthz") {
      res.writeHead(200, { "content-type": "application/json" });
      res.end('{"ok":true}');
    } else {
      res.writeHead(404);
      res.end();
    }
  });

  // artifacts 路由已在 createServer 回调内挂载（见上）

  const wss = new WebSocketServer({ server: httpServer });
  const hub = new Hub(db);

  hub.onMessage = (env: Envelope<MessagePayload>) => {
    routeMessage(hub, env);
  };

  wss.on("connection", (ws) => {
    hub.handleConnection(ws);
  });

  const timer = setInterval(() => hub.sweep(), ZOMBIE_SWEEP_MS);
  timer.unref?.();

  httpServer.listen(config.port);

  const close = async (): Promise<void> => {
    clearInterval(timer);
    await new Promise<void>((res) => wss.close(() => res()));
    await new Promise<void>((res) => httpServer.close(() => res()));
  };

  return { httpServer, wss, hub, close };
}

// 自查：红线 1-5 逐条通过
