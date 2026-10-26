import { createServer, type Server } from "node:http";
import { existsSync, readFileSync, statSync } from "node:fs";
import { resolve as resolvePath, join as joinPath, sep as pathSep, extname } from "node:path";
import type { ServerResponse } from "node:http";
import { WebSocketServer } from "ws";
import { ZOMBIE_SWEEP_MS, isRoomType, isGameAllowed, canUpdateRoom, canClearOrKick, canManageRoom } from "@botstalk/protocol";
import type { Db } from "./db.js";
import { getRoomHistory, listPresenceForRoom, listTasks, getTask, getTaskProgress, updateTaskStatus, countTasksByStatus, createRoom, getRoom, listRooms, setRoomType, updateRoom, getRoomType, addRoomMember, removeRoomMember, listRoomMembers, setPersonaRole, getPermRole, setPermRole, isPermRole, countRoomMembers, createGameSession, getGameSession, listGameSessions, updateGameSessionState, endGameSession, issuePairingCode, getPairingCode, redeemPairingCode } from "./db.js";
import { issueShareLink, getShareLinkByHash, getShareLinkById, listShareLinks, revokeShareLink } from "./db.js";
import { generatePairingCode, normalizePairingCode, hashPairingCode, clampPairingTtlMinutes } from "./pairing.js";
import { generateShareToken, normalizeShareToken, hashShareToken, clampShareTtlHours, isShareExpired, isShareRevoked } from "./share.js";

// 房主恒为 admin，其余情况查成员权限列
function managePerm(db: Db, roomOwner: string | null, roomId: string, requester: string): string | undefined {
  if (requester && requester === roomOwner) {
    return "admin";
  }
  return getPermRole(db, roomId, requester);
}
import { createScheduledTask, listScheduledTasks, getScheduledTask, updateScheduledTask, deleteScheduledTask, validateScheduledTaskInput, createTriggerRule, listTriggerRules, getTriggerRule, updateTriggerRule, deleteTriggerRule, validateTriggerRuleInput } from "./workflows.js";
import type { ScheduledTaskPatch, TriggerRulePatch } from "./workflows.js";
import type { TaskStatus } from "./db.js";
import type { IncomingMessage } from "node:http";
import { Hub } from "./hub.js";
import { DoudizhuGameEngine } from "./doudizhu-game.js";
import { WerewolfGameEngine } from "./werewolf-game.js";
import { routeMessage, routeStream, routeApprovalDecision, setTaskApprovalMode, sweepApprovals, getPendingApprovals, setTaskTimeoutMs, sweepTaskTimeouts } from "./router.js";
import { sweepScheduledTasks } from "./scheduler.js";
import { checkTriggers } from "./triggers.js";
import type { GatewayConfig } from "./config.js";
import type { Envelope, MessagePayload, StreamPayload } from "@botstalk/protocol";
import { createArtifactService } from "./artifacts.js";
import { handleRegistryRoutes } from "./registry-routes.js";
import { randomUUID } from "node:crypto";

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

    // GET /api/registry/agents* —— agent registry 目录（白名单字段，不含敏感信息）
    if (handleRegistryRoutes(req, res, url, method)) return;

    // GET /api/rooms/:room/history
    const TASK_STATUSES: readonly string[] = ["dispatched", "running", "done", "failed", "unsupported", "cancelled", "pending_approval", "timed_out"];
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
      const rows = listPresenceForRoom(db, room);
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
      const rows = sortPresence(listPresenceForRoom(db, room));
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

    // GET /api/rooms/:room/approvals —— 当前房间待人工审批的任务列表（内存态，网关重启即丢）
    const approvalsMatch = url.match(/^\/api\/rooms\/([^/?]+)\/approvals(?:\?|$)/);
    if (approvalsMatch && method === "GET") {
      res.setHeader("access-control-allow-origin", "*");
      const room = decodeURIComponent(approvalsMatch[1]);
      if (!room) {
        res.writeHead(400, { "content-type": "application/json" });
        res.end('{"error":"room required"}');
        return;
      }
      const approvals = getPendingApprovals()
        .list()
        .filter((p) => p.room === room)
        .map((p) => ({
          approval_id: p.approval_id,
          task_id: p.task_id,
          requester: p.requester,
          assignee: p.assignee,
          title: p.title,
          expires_at_ms: p.expires_at_ms,
        }));
      res.writeHead(200, { "content-type": "application/json" });
      res.end(JSON.stringify({ approvals }));
      return;
    }

    // ---- 定时任务 CRUD（workflows）----
    const schedulesMatch = url.match(/^\/api\/rooms\/([^/?]+)\/schedules(?:\?|$)/);
    if (schedulesMatch && method === "GET") {
      res.setHeader("access-control-allow-origin", "*");
      const room = decodeURIComponent(schedulesMatch[1]);
      if (!room) {
        res.writeHead(400, { "content-type": "application/json" });
        res.end('{"error":"room required"}');
        return;
      }
      const schedules = listScheduledTasks(db, room);
      res.writeHead(200, { "content-type": "application/json" });
      res.end(JSON.stringify({ schedules }));
      return;
    }

    const scheduleIdMatch = url.match(/^\/api\/rooms\/([^/?]+)\/schedules\/([^/?]+)(?:\?|$)/);
    if (scheduleIdMatch && method === "GET") {
      res.setHeader("access-control-allow-origin", "*");
      const room = decodeURIComponent(scheduleIdMatch[1]);
      if (!room) {
        res.writeHead(400, { "content-type": "application/json" });
        res.end('{"error":"room required"}');
        return;
      }
      const id = decodeURIComponent(scheduleIdMatch[2]);
      if (!id) {
        res.writeHead(400, { "content-type": "application/json" });
        res.end('{"error":"id required"}');
        return;
      }
      const s = getScheduledTask(db, id);
      if (!s || s.room !== room) {
        res.writeHead(404, { "content-type": "application/json" });
        res.end('{"error":"not found"}');
        return;
      }
      res.writeHead(200, { "content-type": "application/json" });
      res.end(JSON.stringify({ schedule: s }));
      return;
    }

    const schedulesPostMatch = url.match(/^\/api\/rooms\/([^/?]+)\/schedules(?:\?|$)/);
    if (schedulesPostMatch && method === "POST") {
      res.setHeader("access-control-allow-origin", "*");
      const room = decodeURIComponent(schedulesPostMatch[1]);
      if (!room) {
        res.writeHead(400, { "content-type": "application/json" });
        res.end('{"error":"room required"}');
        return;
      }
      const raw = await readJsonBody(req);
      if (typeof raw !== "object" || raw === null) {
        res.writeHead(400, { "content-type": "application/json" });
        res.end('{"error":"invalid body"}');
        return;
      }
      const body = raw as Record<string, unknown>;
      const name = body.name;
      const intervalSec = body.interval_sec;
      const prompt = body.prompt;
      const err = validateScheduledTaskInput({ name, interval_sec: intervalSec, prompt });
      if (err) {
        res.writeHead(400, { "content-type": "application/json" });
        res.end(JSON.stringify({ error: err }));
        return;
      }
      const ownerRaw = body.owner;
      const owner = typeof ownerRaw === "string" && ownerRaw.trim() ? ownerRaw.trim() : "web";
      const agentRaw = body.agent_id;
      const titleRaw = body.task_title;
      const schedule = createScheduledTask(db, {
        room,
        name: String(name).trim(),
        interval_sec: intervalSec as number,
        agent_id: typeof agentRaw === "string" && agentRaw ? agentRaw : null,
        task_title: typeof titleRaw === "string" && titleRaw.trim() ? titleRaw.trim() : undefined,
        prompt: String(prompt).trim(),
        owner,
      });
      res.writeHead(201, { "content-type": "application/json" });
      res.end(JSON.stringify({ schedule }));
      return;
    }

    const schedulePatchMatch = url.match(/^\/api\/rooms\/([^/?]+)\/schedules\/([^/?]+)(?:\?|$)/);
    if (schedulePatchMatch && method === "PATCH") {
      res.setHeader("access-control-allow-origin", "*");
      const room = decodeURIComponent(schedulePatchMatch[1]);
      const id = decodeURIComponent(schedulePatchMatch[2]);
      if (!room) {
        res.writeHead(400, { "content-type": "application/json" });
        res.end('{"error":"room required"}');
        return;
      }
      if (!id) {
        res.writeHead(400, { "content-type": "application/json" });
        res.end('{"error":"id required"}');
        return;
      }
      const existing = getScheduledTask(db, id);
      if (!existing || existing.room !== room) {
        res.writeHead(404, { "content-type": "application/json" });
        res.end('{"error":"not found"}');
        return;
      }
      const raw = await readJsonBody(req);
      if (!raw || typeof raw !== "object" || raw === null) {
        res.writeHead(400, { "content-type": "application/json" });
        res.end('{"error":"invalid body"}');
        return;
      }
      const body = raw as Record<string, unknown>;
      const merged = {
        name: body.name ?? existing.name,
        interval_sec: body.interval_sec ?? existing.interval_sec,
        prompt: body.prompt ?? existing.prompt,
      };
      const validationError = validateScheduledTaskInput(merged);
      if (validationError) {
        res.writeHead(400, { "content-type": "application/json" });
        res.end(`{"error":"${validationError}"}`);
        return;
      }
      const patch: ScheduledTaskPatch = {};
      if (body.name !== undefined) patch.name = String(body.name).trim();
      if (body.interval_sec !== undefined) patch.interval_sec = body.interval_sec as number;
      if (body.prompt !== undefined) patch.prompt = String(body.prompt).trim();
      if (body.enabled !== undefined) patch.enabled = body.enabled === true || body.enabled === 1 || body.enabled === "1" || body.enabled === "true";
      if (body.agent_id !== undefined) patch.agent_id = typeof body.agent_id === "string" && body.agent_id ? body.agent_id : null;
      if (body.task_title !== undefined) patch.task_title = typeof body.task_title === "string" && body.task_title.trim() ? body.task_title.trim() : undefined;
      const updated = updateScheduledTask(db, id, patch);
      if (!updated) {
        res.writeHead(404, { "content-type": "application/json" });
        res.end('{"error":"not found"}');
        return;
      }
      res.setHeader("content-type", "application/json");
      res.end(JSON.stringify({ schedule: updated }));
      return;
    }
    const scheduleDeleteMatch = url.match(/^\/api\/rooms\/([^/?]+)\/schedules\/([^/?]+)(?:\?|$)/);
    if (scheduleDeleteMatch && method === "DELETE") {
      res.setHeader("access-control-allow-origin", "*");
      const room = decodeURIComponent(scheduleDeleteMatch[1]);
      const id = decodeURIComponent(scheduleDeleteMatch[2]);
      if (!room) {
        res.writeHead(400, { "content-type": "application/json" });
        res.end('{"error":"room required"}');
        return;
      }
      if (!id) {
        res.writeHead(400, { "content-type": "application/json" });
        res.end('{"error":"id required"}');
        return;
      }
      const existing = getScheduledTask(db, id);
      if (!existing || existing.room !== room) {
        res.writeHead(404, { "content-type": "application/json" });
        res.end('{"error":"not found"}');
        return;
      }
      deleteScheduledTask(db, id);
      res.setHeader("content-type", "application/json");
      res.end('{"ok":true}');
      return;
    }

    // ---- 触发规则 CRUD（workflows）----
    const triggerTrigMatch = url.match(/^\/api\/rooms\/([^/?]+)\/triggers(?:\?|$)/);
    if (triggerTrigMatch && method === "GET") {
      res.setHeader("access-control-allow-origin", "*");
      const room = decodeURIComponent(triggerTrigMatch[1]);
      if (!room) {
        res.writeHead(400, { "content-type": "application/json" });
        res.end('{"error":"room required"}');
        return;
      }
      const triggers = listTriggerRules(db, room);
      res.writeHead(200, { "content-type": "application/json" });
      res.end(JSON.stringify({ triggers }));
      return;
    }

    const triggerTrigIdMatch = url.match(/^\/api\/rooms\/([^/?]+)\/triggers\/([^/?]+)(?:\?|$)/);
    if (triggerTrigIdMatch && method === "GET") {
      res.setHeader("access-control-allow-origin", "*");
      const room = decodeURIComponent(triggerTrigIdMatch[1]);
      const id = decodeURIComponent(triggerTrigIdMatch[2]);
      if (!room) {
        res.writeHead(400, { "content-type": "application/json" });
        res.end('{"error":"room required"}');
        return;
      }
      if (!id) {
        res.writeHead(400, { "content-type": "application/json" });
        res.end('{"error":"id required"}');
        return;
      }
      const t = getTriggerRule(db, id);
      if (!t || t.room !== room) {
        res.writeHead(404, { "content-type": "application/json" });
        res.end('{"error":"not found"}');
        return;
      }
      res.writeHead(200, { "content-type": "application/json" });
      res.end(JSON.stringify({ trigger: t }));
      return;
    }

    const triggerPostMatch = url.match(/^\/api\/rooms\/([^/?]+)\/triggers(?:\?|$)/);
    if (triggerPostMatch && method === "POST") {
      res.setHeader("access-control-allow-origin", "*");
      const room = decodeURIComponent(triggerPostMatch[1]);
      if (!room) {
        res.writeHead(400, { "content-type": "application/json" });
        res.end('{"error":"room required"}');
        return;
      }

      const raw = await readJsonBody(req);
      if (typeof raw !== "object" || raw === null) {
        res.writeHead(400, { "content-type": "application/json" });
        res.end('{"error":"invalid body"}');
        return;
      }

      const body = raw as Record<string, unknown>;
      const err = validateTriggerRuleInput({
        name: body.name,
        match_type: body.match_type,
        pattern: body.pattern,
        prompt: body.prompt,
        cooldown_sec: body.cooldown_sec,
      });
      if (err) {
        res.writeHead(400, { "content-type": "application/json" });
        res.end(JSON.stringify({ error: err }));
        return;
      }

      const ownerRaw = body.owner;
      const owner = typeof ownerRaw === "string" && ownerRaw.trim() ? ownerRaw.trim() : "web";
      const agentRaw = body.agent_id;
      const titleRaw = body.task_title;
      const coolRaw = body.cooldown_sec;

      const trigger = createTriggerRule(db, {
        room,
        name: String(body.name).trim(),
        match_type: body.match_type as "keyword" | "sender" | "event",
        pattern: String(body.pattern).trim(),
        agent_id: typeof agentRaw === "string" && agentRaw ? agentRaw : null,
        task_title: typeof titleRaw === "string" && titleRaw.trim() ? titleRaw.trim() : undefined,
        prompt: String(body.prompt).trim(),
        owner,
        cooldown_sec: typeof coolRaw === "number" && Number.isInteger(coolRaw) ? coolRaw : undefined,
      });
      res.writeHead(201, { "content-type": "application/json" });
      res.end(JSON.stringify({ trigger }));
      return;
    }

    const triggerPatchMatch = url.match(/^\/api\/rooms\/([^/?]+)\/triggers\/([^/?]+)(?:\?|$)/);
    if (triggerPatchMatch && method === "PATCH") {
      res.setHeader("access-control-allow-origin", "*");
      const room = decodeURIComponent(triggerPatchMatch[1]);
      if (!room) {
        res.writeHead(400, { "content-type": "application/json" });
        res.end(JSON.stringify({ error: "room required" }));
        return;
      }
      const id = decodeURIComponent(triggerPatchMatch[2]);
      if (!id) {
        res.writeHead(400, { "content-type": "application/json" });
        res.end(JSON.stringify({ error: "id required" }));
        return;
      }
      const t = getTriggerRule(db, id);
      if (!t || t.room !== room) {
        res.writeHead(404, { "content-type": "application/json" });
        res.end(JSON.stringify({ error: "not found" }));
        return;
      }
      const raw = await readJsonBody(req);
      if (typeof raw !== "object" || raw === null) {
        res.writeHead(400, { "content-type": "application/json" });
        res.end(JSON.stringify({ error: "invalid body" }));
        return;
      }
      const body = raw as Record<string, unknown>;
      const merged = {
        name: body.name ?? t.name,
        match_type: body.match_type ?? t.match_type,
        pattern: body.pattern ?? t.pattern,
        prompt: body.prompt ?? t.prompt,
        cooldown_sec: body.cooldown_sec ?? t.cooldown_sec,
      } as Parameters<typeof validateTriggerRuleInput>[0];
      const err = validateTriggerRuleInput(merged);
      if (err) {
        res.writeHead(400, { "content-type": "application/json" });
        res.end(JSON.stringify({ error: err }));
        return;
      }
      const patch: TriggerRulePatch = {};
      if (body.name !== undefined) patch.name = String(body.name).trim();
      if (body.match_type !== undefined) patch.match_type = body.match_type as "keyword" | "sender" | "event";
      if (body.pattern !== undefined) patch.pattern = String(body.pattern).trim();
      if (body.prompt !== undefined) patch.prompt = String(body.prompt).trim();
      if (body.cooldown_sec !== undefined) patch.cooldown_sec = body.cooldown_sec as number;
      if (body.enabled !== undefined) patch.enabled = body.enabled === true || body.enabled === 1 || body.enabled === "1" || body.enabled === "true";
      if (body.agent_id !== undefined) patch.agent_id = typeof body.agent_id === "string" && body.agent_id ? body.agent_id : null;
      if (body.task_title !== undefined) patch.task_title = typeof body.task_title === "string" && body.task_title.trim() ? body.task_title.trim() : undefined;
      const updated = updateTriggerRule(db, id, patch);
      if (!updated) {
        res.writeHead(404, { "content-type": "application/json" });
        res.end(JSON.stringify({ error: "not found" }));
        return;
      }
      res.writeHead(200, { "content-type": "application/json" });
      res.end(JSON.stringify({ trigger: updated }));
      return;
    }

    const triggerDeleteMatch = url.match(/^\/api\/rooms\/([^/?]+)\/triggers\/([^/?]+)(?:\?|$)/);
    if (triggerDeleteMatch && method === "DELETE") {
      res.setHeader("access-control-allow-origin", "*");
      const room = decodeURIComponent(triggerDeleteMatch[1]);
      if (!room) {
        res.writeHead(400, { "content-type": "application/json" });
        res.end(JSON.stringify({ error: "room required" }));
        return;
      }
      const id = decodeURIComponent(triggerDeleteMatch[2]);
      if (!id) {
        res.writeHead(400, { "content-type": "application/json" });
        res.end(JSON.stringify({ error: "id required" }));
        return;
      }
      const t = getTriggerRule(db, id);
      if (!t || t.room !== room) {
        res.writeHead(404, { "content-type": "application/json" });
        res.end(JSON.stringify({ error: "not found" }));
        return;
      }
      deleteTriggerRule(db, id);
      res.writeHead(200, { "content-type": "application/json" });
      res.end(JSON.stringify({ ok: true }));
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
      res.end(JSON.stringify({ task, progress: getTaskProgress(db, taskId) }));
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

    // POST /api/rooms  body: { id?, name?, type?, topic?, owner? }
    const roomCreateMatch = url.match(/^\/api\/rooms(?:\?|$)/);
    if (roomCreateMatch && method === "POST") {
      res.setHeader("access-control-allow-origin", "*");
      const body = (await readJsonBody(req)) as { id?: unknown; name?: unknown; type?: unknown; topic?: unknown; owner?: unknown } | undefined;
      const type = body?.type === undefined ? "workroom" : body.type;
      if (!isRoomType(type)) {
        res.writeHead(400, { "content-type": "application/json" });
        res.end(JSON.stringify({ error: "INVALID_ROOM_TYPE" }));
        return;
      }
      const id = typeof body?.id === "string" && body.id.length > 0 ? body.id : randomUUID();
      if (getRoom(db, id)) {
        res.writeHead(409, { "content-type": "application/json" });
        res.end(JSON.stringify({ error: "room already exists" }));
        return;
      }
      const room = createRoom(db, {
        id,
        type,
        name: typeof body?.name === "string" ? body.name : undefined,
        topic: typeof body?.topic === "string" ? body.topic : undefined,
        owner: typeof body?.owner === "string" ? body.owner : undefined,
      });
      res.writeHead(201, { "content-type": "application/json" });
      res.end(JSON.stringify({ room }));
      return;
    }

    // GET /api/rooms
    const roomListMatch = url.match(/^\/api\/rooms(?:\?|$)/);
    if (roomListMatch && method === "GET") {
      res.setHeader("access-control-allow-origin", "*");
      res.writeHead(200, { "content-type": "application/json" });
      res.end(JSON.stringify({ rooms: listRooms(db) }));
      return;
    }

    // GET /api/rooms/:room
    const roomOneMatch = url.match(/^\/api\/rooms\/([^/?]+)(?:\?|$)/);
    if (roomOneMatch && method === "GET" && !/\/api\/rooms\/[^/?]+\//.test(url)) {
      res.setHeader("access-control-allow-origin", "*");
      const roomId = decodeURIComponent(roomOneMatch[1]);
      const room = getRoom(db, roomId);
      if (!room) {
        res.writeHead(404, { "content-type": "application/json" });
        res.end(JSON.stringify({ error: "room not found" }));
        return;
      }
      res.writeHead(200, { "content-type": "application/json" });
      res.end(JSON.stringify({ room }));
      return;
    }

    // PATCH /api/rooms/:room  body: { name?, topic?, type?, requester? }
    // 改 type 走权限：workroom 只有 owner 能改（requester 必须等于 room.owner），playroom 所有成员可改。
    const roomPatchMatch = url.match(/^\/api\/rooms\/([^/?]+)(?:\?|$)/);
    if (roomPatchMatch && method === "PATCH" && !/\/api\/rooms\/[^/?]+\//.test(url)) {
      res.setHeader("access-control-allow-origin", "*");
      const roomId = decodeURIComponent(roomPatchMatch[1]);
      const room = getRoom(db, roomId);
      if (!room) {
        res.writeHead(404, { "content-type": "application/json" });
        res.end(JSON.stringify({ error: "room not found" }));
        return;
      }
      const body = (await readJsonBody(req)) as { name?: unknown; topic?: unknown; type?: unknown; requester?: unknown } | undefined;
      const requester = typeof body?.requester === "string" ? body.requester : "";
      const isOwner = requester !== "" && requester === room.owner;
      if ((body?.name !== undefined || body?.topic !== undefined) && !canManageRoom(room.type, isOwner, managePerm(db, room.owner, roomId, requester))) {
        res.writeHead(403, { "content-type": "application/json" });
        res.end(JSON.stringify({ error: "ROOM_MANAGE_FORBIDDEN" }));
        return;
      }
      if (body?.type !== undefined) {
        if (!isRoomType(body.type)) {
          res.writeHead(400, { "content-type": "application/json" });
          res.end(JSON.stringify({ error: "INVALID_ROOM_TYPE" }));
          return;
        }
        if (managePerm(db, room.owner, roomId, requester) === "guest" || !canUpdateRoom(room.type, isOwner)) {
          res.writeHead(403, { "content-type": "application/json" });
          res.end(JSON.stringify({ error: "ROOM_TYPE_FORBIDDEN" }));
          return;
        }
        setRoomType(db, roomId, body.type);
      }
      const patch: { name?: string; topic?: string } = {};
      if (typeof body?.name === "string") patch.name = body.name;
      if (typeof body?.topic === "string") patch.topic = body.topic;
      updateRoom(db, roomId, patch);
      res.writeHead(200, { "content-type": "application/json" });
      res.end(JSON.stringify({ room: getRoom(db, roomId) }));
      return;
    }

    // GET /api/rooms/:room/members
    const membersListMatch = url.match(/^\/api\/rooms\/([^/?]+)\/members(?:\?|$)/);
    if (membersListMatch && method === "GET") {
      res.setHeader("access-control-allow-origin", "*");
      const roomId = decodeURIComponent(membersListMatch[1]);
      if (!getRoom(db, roomId)) {
        res.writeHead(404, { "content-type": "application/json" });
        res.end(JSON.stringify({ error: "room not found" }));
        return;
      }
      res.writeHead(200, { "content-type": "application/json" });
      res.end(JSON.stringify({ members: listRoomMembers(db, roomId) }));
      return;
    }

    // POST /api/rooms/:room/members  body: { adapter_id, persona_role?, requester? }
    const membersAddMatch = url.match(/^\/api\/rooms\/([^/?]+)\/members(?:\?|$)/);
    if (membersAddMatch && method === "POST") {
      res.setHeader("access-control-allow-origin", "*");
      const roomId = decodeURIComponent(membersAddMatch[1]);
      const room = getRoom(db, roomId);
      if (!room) {
        res.writeHead(404, { "content-type": "application/json" });
        res.end(JSON.stringify({ error: "room not found" }));
        return;
      }
      const body = (await readJsonBody(req)) as { adapter_id?: unknown; persona_role?: unknown; requester?: unknown } | undefined;
      const requester = typeof body?.requester === "string" ? body.requester : "";
      const isOwner = requester !== "" && requester === room.owner;
      if (!canManageRoom(room.type, isOwner, managePerm(db, room.owner, roomId, requester))) {
        res.writeHead(403, { "content-type": "application/json" });
        res.end(JSON.stringify({ error: "ROOM_MANAGE_FORBIDDEN" }));
        return;
      }
      const adapterId = typeof body?.adapter_id === "string" ? body.adapter_id : "";
      if (!adapterId) {
        res.writeHead(400, { "content-type": "application/json" });
        res.end(JSON.stringify({ error: "adapter_id required" }));
        return;
      }
      const limit = room.type === "playroom" ? config.roomMaxMembersPlayroom : config.roomMaxMembersWorkroom;
      if (countRoomMembers(db, roomId) >= limit) {
        res.writeHead(403, { "content-type": "application/json" });
        res.end(JSON.stringify({ error: "ROOM_FULL" }));
        return;
      }
      const personaRole = typeof body?.persona_role === "string" ? body.persona_role : null;
      addRoomMember(db, roomId, adapterId, personaRole);
      const member = listRoomMembers(db, roomId).find((m) => m.adapter_id === adapterId);
      res.writeHead(201, { "content-type": "application/json" });
      res.end(JSON.stringify({ member }));
      return;
    }

    // DELETE /api/rooms/:room/members/:adapter_id
    const membersDelMatch = url.match(/^\/api\/rooms\/([^/?]+)\/members\/([^/?]+)(?:\?|$)/);
    if (membersDelMatch && method === "DELETE") {
      res.setHeader("access-control-allow-origin", "*");
      const roomId = decodeURIComponent(membersDelMatch[1]);
      const adapterId = decodeURIComponent(membersDelMatch[2]);
      const room = getRoom(db, roomId);
      if (!room) {
        res.writeHead(404, { "content-type": "application/json" });
        res.end(JSON.stringify({ error: "room not found" }));
        return;
      }
      const requester = new URL(url, "http://localhost").searchParams.get("requester") ?? "";
      const isOwner = requester !== "" && requester === room.owner;
      if (!canClearOrKick(room.type, isOwner)) {
        res.writeHead(403, { "content-type": "application/json" });
        res.end(JSON.stringify({ error: "ROOM_MANAGE_FORBIDDEN" }));
        return;
      }
      if (!removeRoomMember(db, roomId, adapterId)) {
        res.writeHead(404, { "content-type": "application/json" });
        res.end(JSON.stringify({ error: "member not found" }));
        return;
      }
      res.writeHead(200, { "content-type": "application/json" });
      res.end(JSON.stringify({ ok: true }));
      return;
    }

    // PATCH /api/rooms/:room/members/:adapter_id/perm  body: { perm_role, requester? }
    // 仅房主可设；房主本人的权限固定不可改；目标须已是成员（不借此端点拉人）。
    const membersPermMatch = url.match(/^\/api\/rooms\/([^/?]+)\/members\/([^/?]+)\/perm(?:\?|$)/);
    if (membersPermMatch && method === "PATCH") {
      res.setHeader("access-control-allow-origin", "*");
      const roomId = decodeURIComponent(membersPermMatch[1]);
      const adapterId = decodeURIComponent(membersPermMatch[2]);
      const room = getRoom(db, roomId);
      if (!room) {
        res.writeHead(404, { "content-type": "application/json" });
        res.end(JSON.stringify({ error: "room not found" }));
        return;
      }
      const body = (await readJsonBody(req)) as { perm_role?: unknown; requester?: unknown } | undefined;
      const requester = typeof body?.requester === "string" ? body.requester : "";
      if (!requester || requester !== room.owner) {
        res.writeHead(403, { "content-type": "application/json" });
        res.end(JSON.stringify({ error: "ROOM_MANAGE_FORBIDDEN" }));
        return;
      }
      if (adapterId === room.owner) {
        res.writeHead(403, { "content-type": "application/json" });
        res.end(JSON.stringify({ error: "ROOM_MANAGE_FORBIDDEN" }));
        return;
      }
      const permRole = body?.perm_role;
      if (!isPermRole(permRole)) {
        res.writeHead(400, { "content-type": "application/json" });
        res.end(JSON.stringify({ error: "INVALID_PERM_ROLE" }));
        return;
      }
      if (!listRoomMembers(db, roomId).some((m) => m.adapter_id === adapterId)) {
        res.writeHead(404, { "content-type": "application/json" });
        res.end(JSON.stringify({ error: "member not found" }));
        return;
      }
      setPermRole(db, roomId, adapterId, permRole);
      const member = listRoomMembers(db, roomId).find((m) => m.adapter_id === adapterId);
      res.writeHead(200, { "content-type": "application/json" });
      res.end(JSON.stringify({ member }));
      return;
    }

    // PATCH /api/rooms/:room/members/:adapter_id  body: { persona_role }
    const membersRoleMatch = url.match(/^\/api\/rooms\/([^/?]+)\/members\/([^/?]+)(?:\?|$)/);
    if (membersRoleMatch && method === "PATCH") {
      res.setHeader("access-control-allow-origin", "*");
      const roomId = decodeURIComponent(membersRoleMatch[1]);
      const adapterId = decodeURIComponent(membersRoleMatch[2]);
      const room = getRoom(db, roomId);
      if (!room) {
        res.writeHead(404, { "content-type": "application/json" });
        res.end(JSON.stringify({ error: "room not found" }));
        return;
      }
      const body = (await readJsonBody(req)) as { persona_role?: unknown; requester?: unknown } | undefined;
      const requester = typeof body?.requester === "string" ? body.requester : "";
      const isOwner = requester !== "" && requester === room.owner;
      if (!canManageRoom(room.type, isOwner, managePerm(db, room.owner, roomId, requester))) {
        res.writeHead(403, { "content-type": "application/json" });
        res.end(JSON.stringify({ error: "ROOM_MANAGE_FORBIDDEN" }));
        return;
      }
      const role = typeof body?.persona_role === "string" ? body.persona_role : null;
      setPersonaRole(db, roomId, adapterId, role);
      const member = listRoomMembers(db, roomId).find((m) => m.adapter_id === adapterId);
      res.writeHead(200, { "content-type": "application/json" });
      res.end(JSON.stringify({ member }));
      return;
    }

    // POST /api/rooms/:room/pairing-codes  body: { requester?, ttl_minutes? } —— 房主/管理员签发一次性配对码，码只在本次响应返回，库里只存哈希
    const pairingIssueMatch = url.match(/^\/api\/rooms\/([^/?]+)\/pairing-codes(?:\?|$)/);
    if (pairingIssueMatch && method === "POST") {
      res.setHeader("access-control-allow-origin", "*");
      const roomId = decodeURIComponent(pairingIssueMatch[1]);
      const room = getRoom(db, roomId);
      if (!room) {
        res.writeHead(404, { "content-type": "application/json" });
        res.end(JSON.stringify({ error: "room not found" }));
        return;
      }
      const body = (await readJsonBody(req)) as { requester?: unknown; ttl_minutes?: unknown } | undefined;
      const requester = typeof body?.requester === "string" ? body.requester : "";
      const isOwner = requester !== "" && requester === room.owner;
      if (!canManageRoom(room.type, isOwner, managePerm(db, room.owner, roomId, requester))) {
        res.writeHead(403, { "content-type": "application/json" });
        res.end(JSON.stringify({ error: "ROOM_MANAGE_FORBIDDEN" }));
        return;
      }
      const code = generatePairingCode();
      const normalized = normalizePairingCode(code);
      if (!normalized) {
        res.writeHead(500, { "content-type": "application/json" });
        res.end(JSON.stringify({ error: "pairing code generation failed" }));
        return;
      }
      const nowMs = Date.now();
      const ttlMinutes = clampPairingTtlMinutes(body?.ttl_minutes);
      const expiresAtMs = nowMs + ttlMinutes * 60000;
      issuePairingCode(db, { codeHash: hashPairingCode(normalized), room: roomId, createdAtMs: nowMs, expiresAtMs });
      res.writeHead(201, { "content-type": "application/json" });
      res.end(JSON.stringify({ code, room: roomId, expires_at_ms: expiresAtMs }));
      return;
    }

    // POST /api/pairing-codes/redeem  body: { code, adapter_id } —— 设备凭配对码入驻：兑码成功即成为该房成员
    const pairingRedeemMatch = url.match(/^\/api\/pairing-codes\/redeem(?:\?|$)/);
    if (pairingRedeemMatch && method === "POST") {
      res.setHeader("access-control-allow-origin", "*");
      const body = (await readJsonBody(req)) as { code?: unknown; adapter_id?: unknown } | undefined;
      const adapterId = typeof body?.adapter_id === "string" ? body.adapter_id : "";
      if (!adapterId) {
        res.writeHead(400, { "content-type": "application/json" });
        res.end(JSON.stringify({ error: "adapter_id required" }));
        return;
      }
      const normalized = normalizePairingCode(body?.code);
      if (!normalized) {
        res.writeHead(400, { "content-type": "application/json" });
        res.end(JSON.stringify({ error: "INVALID_PAIRING_CODE" }));
        return;
      }
      const row = getPairingCode(db, hashPairingCode(normalized));
      if (!row) {
        res.writeHead(404, { "content-type": "application/json" });
        res.end(JSON.stringify({ error: "PAIRING_CODE_NOT_FOUND" }));
        return;
      }
      const nowMs = Date.now();
      if (row.redeemed_at_ms !== null) {
        res.writeHead(409, { "content-type": "application/json" });
        res.end(JSON.stringify({ error: "PAIRING_CODE_USED" }));
        return;
      }
      if (nowMs > row.expires_at_ms) {
        res.writeHead(410, { "content-type": "application/json" });
        res.end(JSON.stringify({ error: "PAIRING_CODE_EXPIRED" }));
        return;
      }
      const result = redeemPairingCode(db, hashPairingCode(normalized), adapterId, nowMs);
      if (result !== "ok") {
        res.writeHead(409, { "content-type": "application/json" });
        res.end(JSON.stringify({ error: "PAIRING_CODE_USED" }));
        return;
      }
      if (!listRoomMembers(db, row.room).some((m) => m.adapter_id === adapterId)) {
        addRoomMember(db, row.room, adapterId, null);
      }
      res.writeHead(200, { "content-type": "application/json" });
      res.end(JSON.stringify({ room: row.room, adapter_id: adapterId, redeemed_at_ms: nowMs }));
      return;
    }

// POST /api/rooms/:room/share-links — 房主/管理员签发只读分享链接，令牌仅此处返回一次
{
  const m = url.match(/^\/api\/rooms\/([^/?]+)\/share-links(?:\?|$)/);
  if (m && method === "POST") {
    res.setHeader("access-control-allow-origin", "*");
    const roomId = decodeURIComponent(m[1]);
    const room = getRoom(db, roomId);
    if (!room) {
      res.writeHead(404, { "content-type": "application/json" });
      res.end(JSON.stringify({ error: "room not found" }));
      return;
    }
    const body = (await readJsonBody(req)) as { requester?: unknown; ttl_hours?: unknown } | undefined;
    const requester = typeof body?.requester === "string" ? body.requester : "";
    const isOwner = requester !== "" && requester === room.owner;
    if (!canManageRoom(room.type, isOwner, managePerm(db, room.owner, roomId, requester))) {
      res.writeHead(403, { "content-type": "application/json" });
      res.end(JSON.stringify({ error: "ROOM_MANAGE_FORBIDDEN" }));
      return;
    }
    const token = generateShareToken();
    const id = randomUUID();
    const nowMs = Date.now();
    const ttl = clampShareTtlHours(body?.ttl_hours);
    const expiresAtMs = nowMs + ttl * 3600000;
    issueShareLink(db, { id, tokenHash: hashShareToken(token), room: roomId, createdAtMs: nowMs, expiresAtMs });
    res.writeHead(201, { "content-type": "application/json" });
    res.end(JSON.stringify({ id, room: roomId, share_token: token, share_url: "/share/" + token, expires_at_ms: expiresAtMs }));
    return;
  }
}

// GET /api/rooms/:room/share-links — 房主/管理员列出链接元数据，绝不返回 token_hash
{
  const m = url.match(/^\/api\/rooms\/([^/?]+)\/share-links(?:\?|$)/);
  if (m && method === "GET") {
    res.setHeader("access-control-allow-origin", "*");
    const roomId = decodeURIComponent(m[1]);
    const room = getRoom(db, roomId);
    if (!room) {
      res.writeHead(404, { "content-type": "application/json" });
      res.end(JSON.stringify({ error: "room not found" }));
      return;
    }
    const requester = new URL(url, "http://localhost").searchParams.get("requester") ?? "";
    const isOwner = requester !== "" && requester === room.owner;
    if (!canManageRoom(room.type, isOwner, managePerm(db, room.owner, roomId, requester))) {
      res.writeHead(403, { "content-type": "application/json" });
      res.end(JSON.stringify({ error: "ROOM_MANAGE_FORBIDDEN" }));
      return;
    }
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify({
      links: listShareLinks(db, roomId).map((r) => ({
        id: r.id,
        room: r.room,
        created_at_ms: r.created_at_ms,
        expires_at_ms: r.expires_at_ms,
        revoked_at_ms: r.revoked_at_ms,
      })),
    }));
    return;
  }
}

// DELETE /api/rooms/:room/share-links/:id — 房主/管理员撤销链接，成功 204 空 body
{
  const m = url.match(/^\/api\/rooms\/([^/?]+)\/share-links\/([^/?]+)(?:\?|$)/);
  if (m && method === "DELETE") {
    res.setHeader("access-control-allow-origin", "*");
    const roomId = decodeURIComponent(m[1]);
    const id = decodeURIComponent(m[2]);
    const room = getRoom(db, roomId);
    if (!room) {
      res.writeHead(404, { "content-type": "application/json" });
      res.end(JSON.stringify({ error: "room not found" }));
      return;
    }
    const body = (await readJsonBody(req)) as { requester?: unknown; ttl_hours?: unknown } | undefined;
    const requester = typeof body?.requester === "string" ? body.requester : "";
    const isOwner = requester !== "" && requester === room.owner;
    if (!canManageRoom(room.type, isOwner, managePerm(db, room.owner, roomId, requester))) {
      res.writeHead(403, { "content-type": "application/json" });
      res.end(JSON.stringify({ error: "ROOM_MANAGE_FORBIDDEN" }));
      return;
    }
    const row = getShareLinkById(db, id);
    if (!row || row.room !== roomId) {
      res.writeHead(404, { "content-type": "application/json" });
      res.end(JSON.stringify({ error: "SHARE_LINK_NOT_FOUND" }));
      return;
    }
    revokeShareLink(db, id, Date.now());
    res.writeHead(204, { "access-control-allow-origin": "*" });
    res.end();
    return;
  }
}

// GET /api/share/:token — 只读访问分享链接：不写库、不加成员、不发广播
{
  const m = url.match(/^\/api\/share\/([^/?]+)(?:\?|$)/);
  if (m && method === "GET") {
    res.setHeader("access-control-allow-origin", "*");
    const normalized = normalizeShareToken(decodeURIComponent(m[1]));
    if (normalized === null) {
      res.writeHead(400, { "content-type": "application/json" });
      res.end(JSON.stringify({ error: "INVALID_SHARE_TOKEN" }));
      return;
    }
    const row = getShareLinkByHash(db, hashShareToken(normalized));
    if (!row) {
      res.writeHead(404, { "content-type": "application/json" });
      res.end(JSON.stringify({ error: "SHARE_LINK_NOT_FOUND" }));
      return;
    }
    const record = { id: row.id, tokenHash: row.token_hash, room: row.room, createdAtMs: row.created_at_ms, expiresAtMs: row.expires_at_ms, revokedAtMs: row.revoked_at_ms };
    if (isShareRevoked(record)) {
      res.writeHead(410, { "content-type": "application/json" });
      res.end(JSON.stringify({ error: "SHARE_LINK_REVOKED" }));
      return;
    }
    if (isShareExpired(record, Date.now())) {
      res.writeHead(410, { "content-type": "application/json" });
      res.end(JSON.stringify({ error: "SHARE_LINK_EXPIRED" }));
      return;
    }
    const room = getRoom(db, row.room);
    if (!room) {
      res.writeHead(404, { "content-type": "application/json" });
      res.end(JSON.stringify({ error: "SHARE_LINK_NOT_FOUND" }));
      return;
    }
    const rows = getRoomHistory(db, row.room, 50);
    const sorted = rows.slice().sort((a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
    const messages = sorted.map((r) => {
      let payload: unknown;
      try {
        payload = JSON.parse(r.payload);
      } catch {
        payload = r.payload;
      }
      return { id: r.id, room: r.room, sender: r.sender, seq: r.seq, type: r.type, payload, ts: r.ts };
    });
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify({
      room,
      share: { id: row.id, expires_at_ms: row.expires_at_ms },
      messages,
    }));
    return;
  }
}

    // POST /api/rooms/:room/games  body: { game, id? }
    // 游戏清单由网关按房间类型强制过滤，不依赖模型。
    const gamesCreateMatch = url.match(/^\/api\/rooms\/([^/?]+)\/games(?:\?|$)/);
    if (gamesCreateMatch && method === "POST") {
      res.setHeader("access-control-allow-origin", "*");
      const roomId = decodeURIComponent(gamesCreateMatch[1]);
      const room = getRoom(db, roomId);
      if (!room) {
        res.writeHead(404, { "content-type": "application/json" });
        res.end(JSON.stringify({ error: "room not found" }));
        return;
      }
      const body = (await readJsonBody(req)) as { game?: unknown; id?: unknown } | undefined;
      const game = typeof body?.game === "string" ? body.game : "";
      if (!game) {
        res.writeHead(400, { "content-type": "application/json" });
        res.end(JSON.stringify({ error: "game required" }));
        return;
      }
      if (!isGameAllowed(room.type, game)) {
        res.writeHead(403, { "content-type": "application/json" });
        res.end(JSON.stringify({ error: "ROOM_TYPE_FORBIDDEN", game }));
        return;
      }
      const id = typeof body?.id === "string" && body.id.length > 0 ? body.id : randomUUID();
      if (getGameSession(db, id)) {
        res.writeHead(409, { "content-type": "application/json" });
        res.end(JSON.stringify({ error: "game session already exists" }));
        return;
      }
      const session = createGameSession(db, { id, room_id: roomId, game });
      res.writeHead(201, { "content-type": "application/json" });
      res.end(JSON.stringify({ session }));
      return;
    }

    // GET /api/rooms/:room/games
    const gamesListMatch = url.match(/^\/api\/rooms\/([^/?]+)\/games(?:\?|$)/);
    if (gamesListMatch && method === "GET") {
      res.setHeader("access-control-allow-origin", "*");
      const roomId = decodeURIComponent(gamesListMatch[1]);
      if (!getRoom(db, roomId)) {
        res.writeHead(404, { "content-type": "application/json" });
        res.end(JSON.stringify({ error: "room not found" }));
        return;
      }
      res.writeHead(200, { "content-type": "application/json" });
      res.end(JSON.stringify({ sessions: listGameSessions(db, roomId) }));
      return;
    }

    // PATCH /api/rooms/:room/games/:id  body: { state }
    const gamesPatchMatch = url.match(/^\/api\/rooms\/([^/?]+)\/games\/([^/?]+)(?:\?|$)/);
    if (gamesPatchMatch && method === "PATCH") {
      res.setHeader("access-control-allow-origin", "*");
      const sessionId = decodeURIComponent(gamesPatchMatch[2]);
      const body = (await readJsonBody(req)) as { state?: unknown } | undefined;
      const rawState = body?.state;
      const stateStr =
        typeof rawState === "string"
          ? rawState
          : rawState !== null && typeof rawState === "object"
            ? JSON.stringify(rawState)
            : null;
      if (stateStr === null) {
        res.writeHead(400, { "content-type": "application/json" });
        res.end(JSON.stringify({ error: "state required" }));
        return;
      }
      if (!updateGameSessionState(db, sessionId, stateStr)) {
        res.writeHead(404, { "content-type": "application/json" });
        res.end(JSON.stringify({ error: "game session not found" }));
        return;
      }
      res.writeHead(200, { "content-type": "application/json" });
      res.end(JSON.stringify({ session: getGameSession(db, sessionId) }));
      return;
    }

    // DELETE /api/rooms/:room/games/:id
    const gamesDelMatch = url.match(/^\/api\/rooms\/([^/?]+)\/games\/([^/?]+)(?:\?|$)/);
    if (gamesDelMatch && method === "DELETE") {
      res.setHeader("access-control-allow-origin", "*");
      const sessionId = decodeURIComponent(gamesDelMatch[2]);
      if (!endGameSession(db, sessionId)) {
        res.writeHead(404, { "content-type": "application/json" });
        res.end(JSON.stringify({ error: "game session not found" }));
        return;
      }
      res.writeHead(200, { "content-type": "application/json" });
      res.end(JSON.stringify({ ok: true }));
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
  // 把已经写好的斗地主引擎挂到网关，游戏 id 用 doudizhu
  hub.registerGameEngine("doudizhu", new DoudizhuGameEngine());
  // 狼人杀引擎
  hub.registerGameEngine("werewolf", new WerewolfGameEngine());

  hub.onMessage = (env: Envelope<MessagePayload>) => {
    routeMessage(hub, env, db);
    checkTriggers(hub, db, env);
  };
  setTaskApprovalMode(config.taskApprovalMode ?? "off");
  setTaskTimeoutMs(config.taskTimeoutMs ?? 300000);
  hub.onApprovalDecision = (env) => {
    routeApprovalDecision(hub, env, db);
  };

  wss.on("connection", (ws) => {
    hub.handleConnection(ws);
  });

  const timer = setInterval(() => { hub.sweep(); sweepApprovals(hub, db, Date.now()); sweepTaskTimeouts(hub, db, Date.now()); sweepScheduledTasks(hub, db, Date.now()); }, ZOMBIE_SWEEP_MS);
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
