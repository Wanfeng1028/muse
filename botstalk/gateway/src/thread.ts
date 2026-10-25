/** 一层 thread：reply_to 引用 + 网关派生 thread_id。
 *
 * 设计（OpenAgents 清单 6，照设计重实现，非代码搬运）：
 * - 无 reply_to：thread_id = 自身 msg_id（即为根）。
 * - 有 reply_to：thread_id = 被引用消息的 thread_id（若被引用消息本身有 thread_id），否则 = reply_to。
 *   回复的回复因此扁平化到根，不做多级嵌套。
 * - groupThreads 的分组逻辑由 BotsRouter GLM-5.3 生成、经本轮人工改编：
 *   根按自身 msg_id 归组，找不到根的回复单独成组，组内按 ts 升序，组按根 ts 升序，不改输入。
 */
import type { MessageRow } from "./db.js";

export interface ThreadItem {
  msgId: string;
  threadId: string;
  replyTo?: string;
  ts: number;
}

export function deriveThreadId(ownMsgId: string, replyTo?: string, targetThreadId?: string): string {
  if (!replyTo) return ownMsgId;
  return targetThreadId ? targetThreadId : replyTo;
}

/** 在房间历史里找被引用消息：payload 是 JSON 字符串，msg_id 在其中。 */
export function findReplyTarget(rows: MessageRow[], replyTo: string): MessageRow | undefined {
  for (const row of rows) {
    try {
      const payload = JSON.parse(row.payload) as { msg_id?: unknown; thread_id?: unknown };
      if (payload.msg_id === replyTo) return row;
    } catch {
      continue;
    }
  }
  return undefined;
}

export function targetThreadId(row: MessageRow): string | undefined {
  try {
    const payload = JSON.parse(row.payload) as { thread_id?: unknown };
    return typeof payload.thread_id === "string" && payload.thread_id.length > 0 ? payload.thread_id : undefined;
  } catch {
    return undefined;
  }
}

export function groupThreads(items: ThreadItem[]): { root: ThreadItem; replies: ThreadItem[] }[] {
  const rootMap = new Map<string, ThreadItem>();
  for (const item of items) {
    if (item.threadId === item.msgId && !rootMap.has(item.threadId)) {
      rootMap.set(item.threadId, item);
    }
  }
  const groups = new Map<string, { root: ThreadItem; replies: ThreadItem[] }>();
  const orphanReplies: ThreadItem[] = [];
  for (const item of items) {
    if (item.threadId === item.msgId) continue;
    const root = rootMap.get(item.threadId);
    if (root) {
      let group = groups.get(item.threadId);
      if (!group) {
        group = { root, replies: [] };
        groups.set(item.threadId, group);
      }
      group.replies.push(item);
    } else {
      orphanReplies.push(item);
    }
  }
  for (const root of rootMap.values()) {
    if (!groups.has(root.threadId)) {
      groups.set(root.threadId, { root, replies: [] });
    }
  }
  const result: { root: ThreadItem; replies: ThreadItem[] }[] = [];
  for (const group of groups.values()) {
    result.push({ root: group.root, replies: [...group.replies].sort((a, b) => a.ts - b.ts) });
  }
  for (const orphan of orphanReplies) {
    result.push({ root: orphan, replies: [] });
  }
  result.sort((a, b) => a.root.ts - b.root.ts);
  return result;
}
