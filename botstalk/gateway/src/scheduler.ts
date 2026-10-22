import { randomUUID } from "node:crypto";
import {
  makeEnvelope,
  type Envelope,
  type MessagePayload,
} from "@botstalk/protocol";
import type { Db } from "./db.js";
import type { Hub } from "./hub.js";
import { routeMessage } from "./router.js";
import {
  claimDueScheduledTasks,
  type ScheduledTask,
} from "./workflows.js";

/** 构造定时任务派发帧。 */
export function buildScheduledTaskEnvelope(
  hub: Hub,
  task: ScheduledTask,
): Envelope<MessagePayload> {
  const taskId = randomUUID();
  const mentions = task.agent_id ? [task.agent_id] : [];

  return makeEnvelope<MessagePayload>(
    "message",
    "scheduler",
    task.room,
    hub.nextSeq(),
    0,
    {
      msg_id: randomUUID(),
      text: task.prompt,
      mentions,
      intent: "task",
      task_id: taskId,
    },
  );
}

/** 领取并派发本轮到期的定时任务。 */
export function sweepScheduledTasks(
  hub: Hub,
  db: Db,
  nowMs: number,
): number {
  const due = claimDueScheduledTasks(db, nowMs);
  let dispatched = 0;

  for (const task of due) {
    try {
      const env = buildScheduledTaskEnvelope(hub, task);
      routeMessage(hub, env, db);
      dispatched += 1;
    } catch (error) {
      console.error(
        `定时任务派发失败：task id=${task.id}，room=${task.room}`,
        error,
      );
    }
  }

  return dispatched;
}