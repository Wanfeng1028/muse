export interface HistoryMessage {
  id: string;
  room: string;
  sender: string;
  seq: number;
  type: string;
  payload: {
    msg_id?: string;
    text?: string;
    mentions?: string[];
    intent?: string;
    task_id?: string;
    task_status?: string;
  };
  ts: number;
}

export interface PresenceMember {
  adapter_id: string;
  status: 'online' | 'offline';
  last_seen_ms: number;
  usage_in?: number;
  usage_out?: number;
}

export type TaskStatus = 'dispatched' | 'running' | 'done' | 'failed' | 'unsupported' | 'cancelled';

export interface TaskItem {
  task_id: string;
  room: string;
  owner: string;
  assignee: string | null;
  title: string;
  status: TaskStatus;
  created_at_ms: number;
  updated_at_ms: number;
}

export interface TaskEventPayload {
  task_id: string;
  status: string;
  assignee?: string;
  title?: string;
  note?: string;
}

export async function fetchTasks(room: string, status?: string, limit = 50): Promise<TaskItem[]> {
  const params = new URLSearchParams({ room, limit: String(limit) });
  if (status) params.set('status', status);
  const res = await fetch(`${BASE}/api/tasks?${params.toString()}`);
  if (!res.ok) throw new Error(`tasks ${res.status}`);
  const data = (await res.json()) as { tasks: TaskItem[] };
  return data.tasks ?? [];
}

export async function fetchTaskStats(room: string): Promise<{ counts: Record<string, number>; total: number }> {
  const res = await fetch(`${BASE}/api/tasks/stats?room=${encodeURIComponent(room)}`);
  if (!res.ok) throw new Error(`task stats ${res.status}`);
  return (await res.json()) as { counts: Record<string, number>; total: number };
}

export async function cancelTask(taskId: string, requester: string): Promise<TaskItem> {
  const res = await fetch(`${BASE}/api/tasks/${encodeURIComponent(taskId)}/cancel`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ requester }),
  });
  if (!res.ok) {
    const err = (await res.json().catch(() => ({}))) as { error?: string };
    throw new Error(err.error ?? `cancel ${res.status}`);
  }
  const data = (await res.json()) as { task: TaskItem };
  return data.task;
}

export async function fetchUnread(room: string, sinceId: number): Promise<{ unread: number; latest_id: number | null }> {
  const res = await fetch(`${BASE}/api/rooms/${encodeURIComponent(room)}/unread?since_id=${sinceId}`);
  if (!res.ok) throw new Error(`unread ${res.status}`);
  return (await res.json()) as { unread: number; latest_id: number | null };
}

const BASE = (() => {
  // 网关与前端同机部署约定：HTTP API 与 WS 都走网关端口 8765。
  // 用绝对地址，避免 setContent / file:// 等场景下相对 URL 解析失败。
  if (typeof window === 'undefined') return '';
  const proto = window.location.protocol === 'https:' ? 'https' : 'http';
  const host = window.location.hostname || 'localhost';
  return `${proto}://${host}:8765`;
})();

export async function fetchHistory(
  room: string,
  limit: number,
  beforeId?: string,
): Promise<HistoryMessage[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (beforeId) params.set('before_id', beforeId);
  const res = await fetch(`${BASE}/api/rooms/${room}/history?${params.toString()}`);
  if (!res.ok) throw new Error(`history ${res.status}`);
  const data = (await res.json()) as { messages: HistoryMessage[] };
  return data.messages ?? [];
}

export async function fetchPresence(room: string): Promise<PresenceMember[]> {
  const res = await fetch(`${BASE}/api/rooms/${room}/presence`);
  if (!res.ok) throw new Error(`presence ${res.status}`);
  const data = (await res.json()) as { members: PresenceMember[] };
  return data.members ?? [];
}
