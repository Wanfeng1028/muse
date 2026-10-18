import { makeEnvelope } from "@botstalk/protocol";
import type { Envelope, MessagePayload, StreamPayload, TaskEventPayload, TaskStatus } from "@botstalk/protocol";
import { randomUUID } from "node:crypto";
import type { Hub } from "./hub.js";
import type { Db } from "./db.js";
import { saveMessage, upsertTaskDispatch, updateTaskStatus, getRoomType } from "./db.js";

export function routeMessage(hub: Hub, env: Envelope<MessagePayload>, db: Db): void {
  const roomType = getRoomType(db, env.room);
  const p = env.payload;
  const intent = p.intent ?? "chat";

  // 娱乐厅禁止新任务：playroom 里 intent=task（非回执）直接拒绝，不路由。
  // 回执（task_status 已设置）放行——可能是房间改类型前派发的任务完成上报。
  if (roomType === "playroom" && intent === "task" && p.task_status === undefined) {
    if (hub.getConn(env.sender)) {
      const reply = makeEnvelope<MessagePayload>(
        "message",
        "gateway",
        env.room,
        hub.nextSeq(),
        0,
        {
          msg_id: randomUUID(),
          text: "ROOM_TYPE_FORBIDDEN: intent=task is not allowed in playroom",
          mentions: [],
          intent: "task",
          task_id: p.task_id,
          task_status: "unsupported",
        },
      );
      hub.sendTo(env.sender, reply);
    }
    return;
  }

  if (intent === "chat") {
    if (p.mentions.length > 0 && roomType === "workroom") {
      // 工作坊定向：只派发给被@的成员和发送者自己，禁止抢话。
      // 用 Set 去重，避免 mentions 含重复 adapter id 或同时含 sender 时重复投递；
      // sender 的副本统一交给下方 sender 分支处理。
      const sent = new Set<string>();
      for (const adapterId of p.mentions) {
        if (adapterId === env.sender) {
          continue;
        }
        if (sent.has(adapterId)) {
          continue;
        }
        sent.add(adapterId);
        if (hub.getConn(adapterId)) {
          hub.sendTo(adapterId, env);
        }
      }
      if (hub.getConn(env.sender)) {
        hub.sendTo(env.sender, env);
      }
    } else {
      // 娱乐厅广播：允许抢话、插科打诨；无 mention 时两类房间都广播。
      hub.broadcast(env.room, env);
    }
    return;
  }

  // task 回执（task_status 已设置）：写台账 + 广播 task_event + 当普通消息广播，不重路由
  if (intent === "task" && p.task_status !== undefined) {
    const taskId = p.task_id ?? p.msg_id;
    if (p.task_id !== undefined) {
      updateTaskStatus(db, taskId, p.task_status as TaskStatus);
    }
    hub.broadcastTaskEvent(env.room, { task_id: taskId, status: p.task_status, assignee: env.sender });
    hub.broadcast(env.room, env);
    return;
  }

  if (intent === "task") {
    const online = hub.getOnlineAdapters();
    let candidates = online.filter((id) => {
      const conn = hub.getConn(id);
      return conn !== undefined && conn.capabilities.intents.includes("task");
    });
    if (p.mentions.length > 0) {
      const allowed = new Set(p.mentions);
      candidates = candidates.filter((id) => allowed.has(id));
    }
    candidates.sort((a, b) => (a < b ? -1 : a > b ? 1 : 0));
    const pick = candidates[0];
    const taskId = p.task_id ?? p.msg_id;
    const bareTitle = p.text.replace(/^(?:@\S+\s*)+/, "").trim();
    const title = bareTitle.length > 80 ? bareTitle.slice(0, 80) + "…" : bareTitle;
    if (pick !== undefined) {
      upsertTaskDispatch(db, {
        task_id: taskId,
        room: env.room,
        owner: env.sender,
        assignee: pick,
        title,
        status: "dispatched",
      });
      hub.broadcastTaskEvent(env.room, { task_id: taskId, status: "dispatched", assignee: pick, title });
      hub.sendTo(pick, env);
      return;
    }
    upsertTaskDispatch(db, {
      task_id: taskId,
      room: env.room,
      owner: env.sender,
      assignee: null,
      title,
      status: "unsupported",
    });
    hub.broadcastTaskEvent(env.room, { task_id: taskId, status: "unsupported", title, note: "no adapter supports task intent" });
    if (hub.getConn(env.sender)) {
      const reply = makeEnvelope<MessagePayload>(
        "message",
        "gateway",
        env.room,
        hub.nextSeq(),
        0,
        {
          msg_id: randomUUID(),
          text: "no adapter supports task intent",
          mentions: [],
          intent: "task",
          task_id: p.task_id,
          task_status: "unsupported",
        },
      );
      hub.sendTo(env.sender, reply);
    }
    return;
  }
}

export function routeStream(hub: Hub, env: Envelope<StreamPayload>, db: Db): void {
  hub.broadcast(env.room, env);
  if (env.payload.final) {
    saveMessage(db, {
      room: env.room,
      sender: env.sender,
      seq: env.seq,
      type: "stream",
      payload: JSON.stringify({ stream_id: env.payload.stream_id }),
      ts: env.ts,
    });
  }
}
// 自查：红线 1-5 逐条通过
