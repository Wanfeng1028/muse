import { createServer, type Server } from "node:http";
import { existsSync, readFileSync, statSync } from "node:fs";
import { resolve as resolvePath, join as joinPath, sep as pathSep, extname } from "node:path";
import type { ServerResponse } from "node:http";
import { WebSocketServer } from "ws";
import { ZOMBIE_SWEEP_MS } from "@botstalk/protocol";
import type { Db } from "./db.js";
import { getRoomHistory, listPresence, listTasks, getTask, updateTaskStatus, countTasksByStatus } from "./db.js";
import type { TaskStatus } from "./db.js";
import type { IncomingMessage } from "node:http";
import { Hub } from "./hub.js";
import { routeMessage, routeStream } from "./router.js";
import type { GatewayConfig } from "./config.js";
import type { Envelope, MessagePayload, StreamPayload } from "@botstalk/protocol";
import { createArtifactService } from "./artifacts.js";

// 排序规则：online 在前，其余按 adapter_id 字典序
const STATIC_MIME: Record<string, string> = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json",
  ".png": "image/png",
  ".svg": "image/svg+xml",
  ".ico": "image/x-icon",
};

/**
 * 静态文件服务（Docker 一体化部署）。返回 true 表示已处理请求。
 * - 只处理 publicDir 已配置且目录存在的情形，否则返回 false 交给后续路由。
 * - /api/* 与 /healthz 由调用方排除在外。
 * - 路径穿越（resolve 后不在 publicDir 内）返回 false。
 * - 文件不存在 → SPA 回退到 index.html；连 index.html 都没有 → 返回 false。
 */
function serveStatic(publicDir: string | undefined, url: string, res: ServerResponse): boolean {
  if (!publicDir) return false;
  const base = resolvePath(publicDir);
  if (!existsSync(base)) return false;
  let pathname: string;
  try {
    pathname = decodeURIComponent(new URL(url, "http://localhost").pathname);
  } catch {
    return false;
  }
  const rel = pathname === "/" ? "index.html" : pathname.replace(/^\/+/, "");
  let file = resolvePath(base, rel);
  if (file !== base && !file.startsWith(base + pathSep)) return false;
  if (!existsSync(file) || !statSync(file).isFile()) {
    file = joinPath(base, "index.html");
    if (!existsSync(file)) return false;
  }
  const ext = extname(file).toLowerCase();
  res.writeHead(200, { "content-type": STATIC_MIME[ext] ?? "application/octet-stream" });
  res.end(readFileSync(file));
  return true;
}

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
  const httpServer = createServer(async (req, res) => {
    if (artifacts.handle(req, res)) return;

    const url = req.url ?? "";
    const method = req.method ?? "GET";

    // 静态文件（publicDir 未配置时直接跳过，不影响 /api/* 与探针）
    if (method === "GET" && !url.startsWith("/api/") && url !== "/healthz") {
      if (serveStatic(config.publicDir, url, res)) return;
    }

    // GET /api/rooms/:room/history
    const TASK_STATUSES: readonly string[] = ["dispatched", "running", "done", "failed", "unsupported", "cancelled"];
    function readJsonBody(req: IncomingMessage): Promise<unknown> {
      return new Promise((resolve) => {
        const chunks: Buffer[] = [];
        req.on("data", (c) => chunks.push(Buffer.isBuffer(c) ? c : Buffer.from(c)));
        req.on("end", () => {
          try { resolve(JSON.parse(Buffer.concat(chunks).toString("utf8"))); }
          catch { resolve(undefined); }
        });
        req.on("error", () => resolve(undefined));
      });
    }

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

    // GET /api/tasks?room=&status=&limit=
    const tasksMatch = url.match(/^\/api\/tasks(?:\?|$)/);
    if (tasksMatch && method === "GET" && !/^\/api\/tasks\//.test(url)) {
      res.setHeader("access-control-allow-origin", "*");
      const parsed = new URL(url, "http://localhost");
      const room = parsed.searchParams.get("room") ?? undefined;
      const statusParam = parsed.searchParams.get("status");
      let status: TaskStatus | undefined;
      if (statusParam !== null) {
        if (!TASK_STATUSES.includes(statusParam)) {
          res.writeHead(400, { "content-type": "application/json" });
          res.end(JSON.stringify({ error: "invalid status" }));
          return;
        }
        status = statusParam as TaskStatus;
      }
      let limit = 50;
      const limitParam = parsed.searchParams.get("limit");
      if (limitParam !== null) {
        const n = Number.parseInt(limitParam, 10);
        if (Number.isFinite(n) && n > 0) limit = Math.min(n, 200);
      }
      let before_updated_ms: number | undefined;
      let before_task_id: string | undefined;
      const bumParam = parsed.searchParams.get("before_updated_ms");
      const btiParam = parsed.searchParams.get("before_task_id");
      if (bumParam !== null && btiParam !== null) {
        const n = Number.parseInt(bumParam, 10);
        if (Number.isFinite(n) && btiParam.length > 0) {
          before_updated_ms = n;
          before_task_id = btiParam;
        }
      }
      const tasks = listTasks(db, { room, status, limit, before_updated_ms, before_task_id });
      res.writeHead(200, { "content-type": "application/json" });
      res.end(JSON.stringify({ tasks }));
      return;
    }

    // GET /api/tasks/stats?room=
    const tasksStatsMatch = url.match(/^\/api\/tasks\/stats(?:\?|$)/);
    if (tasksStatsMatch && method === "GET") {
      res.setHeader("access-control-allow-origin", "*");
      const parsed = new URL(url, "http://localhost");
      const room = parsed.searchParams.get("room") ?? undefined;
      const counts = countTasksByStatus(db, room);
      let total = 0;
      for (const k of Object.keys(counts)) total += counts[k];
      res.writeHead(200, { "content-type": "application/json" });
      res.end(JSON.stringify({ counts, total }));
      return;
    }

    // GET /api/tasks/:task_id
    const taskOneMatch = url.match(/^\/api\/tasks\/([^/?]+)(?:\?|$)/);
    if (taskOneMatch && method === "GET") {
      res.setHeader("access-control-allow-origin", "*");
      const taskId = decodeURIComponent(taskOneMatch[1]);
      const task = getTask(db, taskId);
      if (!task) {
        res.writeHead(404, { "content-type": "application/json" });
        res.end(JSON.stringify({ error: "task not found" }));
        return;
      }
      res.writeHead(200, { "content-type": "application/json" });
      res.end(JSON.stringify({ task }));
      return;
    }

    // POST /api/tasks/:task_id/cancel  body: { requester: string }
    const taskCancelMatch = url.match(/^\/api\/tasks\/([^/?]+)\/cancel(?:\?|$)/);
    if (taskCancelMatch && method === "POST") {
      res.setHeader("access-control-allow-origin", "*");
      const taskId = decodeURIComponent(taskCancelMatch[1]);
      const body = (await readJsonBody(req)) as { requester?: unknown } | undefined;
      const requester = typeof body?.requester === "string" ? body.requester : "";
      if (!requester) {
        res.writeHead(400, { "content-type": "application/json" });
        res.end(JSON.stringify({ error: "requester required" }));
        return;
      }
      const task = getTask(db, taskId);
      if (!task) {
        res.writeHead(404, { "content-type": "application/json" });
        res.end(JSON.stringify({ error: "task not found" }));
        return;
      }
      if (task.owner !== requester) {
        res.writeHead(403, { "content-type": "application/json" });
        res.end(JSON.stringify({ error: "only task owner can cancel" }));
        return;
      }
      if (task.status === "done" || task.status === "failed" || task.status === "cancelled" || task.status === "unsupported") {
        res.writeHead(409, { "content-type": "application/json" });
        res.end(JSON.stringify({ error: "task already in terminal state" }));
        return;
      }
      updateTaskStatus(db, taskId, "cancelled");
      hub.broadcastTaskEvent(task.room, { task_id: taskId, status: "cancelled", assignee: task.assignee ?? undefined, title: task.title, note: "cancelled by " + requester });
      const updated = getTask(db, taskId);
      res.writeHead(200, { "content-type": "application/json" });
      res.end(JSON.stringify({ task: updated }));
      return;
    }

    // GET /api/rooms/:room/unread?since_id=
    const unreadMatch = url.match(/^\/api\/rooms\/([^/?]+)\/unread(?:\?|$)/);
    if (unreadMatch && method === "GET") {
      res.setHeader("access-control-allow-origin", "*");
      const room = decodeURIComponent(unreadMatch[1]);
      if (!room) {
        res.writeHead(400, { "content-type": "application/json" });
        res.end(JSON.stringify({ error: "room required" }));
        return;
      }
      const parsed = new URL(url, "http://localhost");
      const sinceParam = parsed.searchParams.get("since_id");
      const sinceId = sinceParam === null ? 0 : Number.parseInt(sinceParam, 10);
      const since = Number.isFinite(sinceId) && sinceId > 0 ? sinceId : 0;
      const row = db.prepare("SELECT COUNT(*) AS n, MAX(id) AS maxId FROM messages WHERE room = ? AND id > ?").get(room, since) as unknown as { n: number; maxId: number | null };
      res.writeHead(200, { "content-type": "application/json" });
      res.end(JSON.stringify({ unread: row.n, latest_id: row.maxId }));
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
    routeMessage(hub, env, db);
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
