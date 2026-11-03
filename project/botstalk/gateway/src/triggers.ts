import { routeMessage } from "./router.js";
import {
  listTriggerRules,
  ruleMatches,
  claimTriggerFire,
  renderTemplate,
  type TriggerRule,
} from "./workflows.js";
import { makeEnvelope, type Envelope, type MessagePayload } from "@botstalk/protocol";
import type { Hub } from "./hub.js";
import type { Db } from "./db.js";
import { randomUUID } from "node:crypto";

/**
 * 自���守逻辑，用于检查是否应跳过触发规则检测。
 * 满足任一条件直接返回 true：系统帧、网关消息、非聊天/任务回执。
 */
export function shouldSkipTriggerCheck(env: Envelope<MessagePayload>): boolean {
  if (env.sender === "scheduler" || env.sender.startsWith("trigger:")) return true;
  if (env.sender === "gateway") return true;
  if (
    env.payload.intent !== undefined &&
    env.payload.intent !== "chat" &&
    env.payload.intent !== "task"
  )
    return true;
  return false;
}

/**
 * 检查指定消息/任务回执是否满足任何启用的触发规则，
 * 若满足则派发合成任务帧。
 */
export function checkTriggers(hub: Hub, db: Db, env: Envelope<MessagePayload>): void {
  if (shouldSkipTriggerCheck(env)) return;

  const rules = listTriggerRules(db, env.room);
  for (const rule of rules) {
    if (rule.enabled !== 1) continue;
    if (!ruleMatches(rule, env)) continue;

    const nowMs = Date.now();
    const fired = claimTriggerFire(db, rule.id, nowMs);
    if (!fired) continue;

    try {
      const taskId = randomUUID();
      const vars = {
        text: env.payload.text ?? "",
        sender: env.sender,
        room: env.room,
      };
      const text = renderTemplate(fired.prompt, vars);
      const mentions = fired.agent_id ? [fired.agent_id] : [];

      const taskEnv = makeEnvelope<MessagePayload>(
        "message",
        "trigger:" + fired.id,
        env.room,
        hub.nextSeq(),
        0,
        {
          msg_id: randomUUID(),
          text,
          mentions,
          intent: "task",
          task_id: taskId,
        },
      );

      routeMessage(hub, taskEnv, db);
    } catch (e) {
      console.error(`Trigger rule error: ruleId=${rule.id}, room=${rule.room}, error=${e}`);
    }
  }
}