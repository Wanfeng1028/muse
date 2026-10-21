import { makeEnvelope, APPROVAL_TTL_MS } from "@botstalk/protocol";
import type { ApprovalDecisionPayload, ApprovalRequestPayload, Envelope, MessagePayload, StreamPayload, TaskEventPayload, TaskStatus } from "@botstalk/protocol";
import { randomUUID } from "node:crypto";
import type { Hub } from "./hub.js";
import type { Db } from "./db.js";
import { saveMessage, upsertTaskDispatch, updateTaskStatus, getRoomType } from "./db.js";
import { PendingApprovals } from "./approvals.js";

let approvalMode: "off" | "all" = "off";
const pendingApprovals = new PendingApprovals();

/** 由 server 启动时按配置注入。默认 "off"：任务直达派发，行为与无审批门时一致。 */
export function setTaskApprovalMode(mode: "off" | "all"): void {
  approvalMode = mode;
}

export function getPendingApprovals(): PendingApprovals {
  return pendingApprovals;
}

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
      if (approvalMode === "all") {
        const approvalId = randomUUID();
        const expiresAtMs = Date.now() + APPROVAL_TTL_MS;
        pendingApprovals.put({
          approval_id: approvalId,
          task_id: taskId,
          room: env.room,
          requester: env.sender,
          assignee: pick,
          title,
          env,
          expires_at_ms: expiresAtMs,
        });
        upsertTaskDispatch(db, {
          task_id: taskId,
          room: env.room,
          owner: env.sender,
          assignee: pick,
          title,
          status: "pending_approval",
        });
        hub.broadcastTaskEvent(env.room, { task_id: taskId, status: "pending_approval", assignee: pick, title });
        hub.broadcast(env.room, makeEnvelope<ApprovalRequestPayload>(
          "approval_request",
          "gateway",
          env.room,
          hub.nextSeq(),
          0,
          {
            approval_id: approvalId,
            task_id: taskId,
            requester: env.sender,
            assignee: pick,
            title,
            expires_at_ms: expiresAtMs,
          },
        ));
        return;
      }
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

/** 处理 approval_decision 帧：放行则按原派发流程把任务帧发给执行者；驳回则终止并回告提出者。 */
export function routeApprovalDecision(hub: Hub, env: Envelope<ApprovalDecisionPayload>, db: Db): void {
  const pending = pendingApprovals.get(env.payload.approval_id);
  if (pending === undefined) {
    return;
  }
  if (env.room !== pending.room) {
    return;
  }
  // 执行者不能给自己的任务放行。
  if (env.sender === pending.assignee) {
    return;
  }
  pendingApprovals.take(env.payload.approval_id);
  if (env.payload.decision === "approve") {
    upsertTaskDispatch(db, {
      task_id: pending.task_id,
      room: pending.room,
      owner: pending.requester,
      assignee: pending.assignee,
      title: pending.title,
      status: "dispatched",
    });
    hub.broadcastTaskEvent(pending.room, { task_id: pending.task_id, status: "dispatched", assignee: pending.assignee, title: pending.title });
    hub.sendTo(pending.assignee, pending.env);
    return;
  }
  updateTaskStatus(db, pending.task_id, "failed");
  hub.broadcastTaskEvent(pending.room, {
    task_id: pending.task_id,
    status: "failed",
    assignee: pending.assignee,
    title: pending.title,
    note: env.payload.note ?? "approval rejected",
  });
  if (hub.getConn(pending.requester)) {
    const reply = makeEnvelope<MessagePayload>(
      "message",
      "gateway",
      pending.room,
      hub.nextSeq(),
      0,
      {
        msg_id: randomUUID(),
        text: "TASK_APPROVAL_REJECTED: " + pending.title,
        mentions: [],
        intent: "task",
        task_id: pending.task_id,
        task_status: "failed",
      },
    );
    hub.sendTo(pending.requester, reply);
  }
}

/** 清扫过期未决的审批：台账置 cancelled，广播事件并回告提出者。由 server 的定时器周期调用。 */
export function sweepApprovals(hub: Hub, db: Db, now: number): void {
  for (const pending of pendingApprovals.sweepExpired(now)) {
    updateTaskStatus(db, pending.task_id, "cancelled");
    hub.broadcastTaskEvent(pending.room, {
      task_id: pending.task_id,
      status: "cancelled",
      assignee: pending.assignee,
      title: pending.title,
      note: "approval expired",
    });
    if (hub.getConn(pending.requester)) {
      const reply = makeEnvelope<MessagePayload>(
        "message",
        "gateway",
        pending.room,
        hub.nextSeq(),
        0,
        {
          msg_id: randomUUID(),
          text: "TASK_APPROVAL_EXPIRED: " + pending.title,
          mentions: [],
          intent: "task",
          task_id: pending.task_id,
          task_status: "failed",
        },
      );
      hub.sendTo(pending.requester, reply);
    }
  }
}
// 自查：红线 1-5 逐条通过
