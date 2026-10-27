export interface HistoryMessage {
  id: number | string;
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
    reply_to?: string;
    thread_id?: string;
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

export type TaskStatus = 'dispatched' | 'running' | 'done' | 'failed' | 'unsupported' | 'cancelled' | 'timed_out';

export interface TaskProgressReport {
  task_id: string;
  seq: number;
  reporter: string;
  message: string;
  data_json: string | null;
  created_at_ms: number;
}

export interface TaskItem {
  task_id: string;
  room: string;
  owner: string;
  assignee: string | null;
  title: string;
  status: TaskStatus;
  created_at_ms: number;
  updated_at_ms: number;
  deadline_ms: number | null;
  error: string | null;
  progress_count: number;
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

export async function fetchTaskDetail(taskId: string): Promise<{ task: TaskItem; progress: TaskProgressReport[] }> {
  const res = await fetch(`${BASE}/api/tasks/${encodeURIComponent(taskId)}`);
  if (!res.ok) throw new Error(`task ${res.status}`);
  const data = (await res.json()) as { task: TaskItem; progress: TaskProgressReport[] };
  return { task: data.task, progress: data.progress ?? [] };
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

export type RoomType = 'workroom' | 'playroom';

export interface RoomInfo {
  id: string;
  type: RoomType;
  name: string | null;
  topic: string | null;
  owner: string | null;
  created_at_ms: number;
}

export const ROOM_TYPE_LABEL: Record<RoomType, string> = {
  workroom: '工作坊',
  playroom: '娱乐厅',
};

export async function fetchRooms(): Promise<RoomInfo[]> {
  const res = await fetch(`${BASE}/api/rooms`);
  if (!res.ok) throw new Error(`rooms ${res.status}`);
  const data = (await res.json()) as { rooms: RoomInfo[] };
  return data.rooms ?? [];
}

export async function createRoom(input: {
  id?: string; name?: string; type?: RoomType; topic?: string; owner?: string;
}): Promise<RoomInfo> {
  const res = await fetch(`${BASE}/api/rooms`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(input),
  });
  if (!res.ok) {
    const err = (await res.json().catch(() => ({}))) as { error?: string };
    throw new Error(err.error ?? `create room ${res.status}`);
  }
  const data = (await res.json()) as { room: RoomInfo };
  return data.room;
}

export async function fetchRoom(id: string): Promise<RoomInfo> {
  const res = await fetch(`${BASE}/api/rooms/${encodeURIComponent(id)}`);
  if (!res.ok) throw new Error(`room ${res.status}`);
  const data = (await res.json()) as { room: RoomInfo };
  return data.room;
}

export async function updateRoom(
  id: string,
  patch: { name?: string; topic?: string; type?: RoomType; requester?: string },
): Promise<RoomInfo> {
  const res = await fetch(`${BASE}/api/rooms/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(patch),
  });
  if (!res.ok) {
    const err = (await res.json().catch(() => ({}))) as { error?: string };
    throw new Error(err.error ?? `update room ${res.status}`);
  }
  const data = (await res.json()) as { room: RoomInfo };
  return data.room;
}

export interface GameSession {
  id: string;
  room_id: string;
  game: string;
  state: string;
  created_at_ms: number;
  updated_at_ms: number;
}

export async function fetchGameSessions(room: string): Promise<GameSession[]> {
  const res = await fetch(`${BASE}/api/rooms/${encodeURIComponent(room)}/games`);
  if (!res.ok) throw new Error('获取游戏会话失败');
  return (await res.json()) as GameSession[];
}

export async function createGameSession(room: string, game: string, seats?: string[]): Promise<GameSession> {
  const res = await fetch(`${BASE}/api/rooms/${encodeURIComponent(room)}/games`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(seats && seats.length > 0 ? { game, seats } : { game }),
  });
  if (!res.ok) {
    const err = (await res.json().catch(() => ({}))) as { error?: string };
    throw new Error(err.error ?? `create game ${res.status}`);
  }
  return (await res.json()) as GameSession;
}

export interface GameStatePayload {
  game: string;
  seat?: string;
  state?: unknown;
  state_hash?: string;
}

import type { ApprovalRequest } from './components/ApprovalQueue';
export type { ApprovalRequest };

export async function fetchPendingApprovals(room: string): Promise<ApprovalRequest[]> {
  const res = await fetch(`${BASE}/api/rooms/${encodeURIComponent(room)}/approvals`);
  if (!res.ok) throw new Error(`approvals ${res.status}`);
  const data = (await res.json()) as { approvals: ApprovalRequest[] };
  return data.approvals ?? [];
}
export interface ScheduledTask {
  id: string; room: string; name: string; enabled: 0 | 1; interval_sec: number;
  agent_id: string | null; task_title: string; prompt: string; owner: string;
  next_run_ms: number; last_run_ms: number | null; created_at_ms: number; updated_at_ms: number;
}
export interface NewScheduledTask { name: string; interval_sec: number; agent_id?: string; task_title?: string; prompt: string; }
export interface ScheduledTaskPatch { name?: string; enabled?: boolean; interval_sec?: number; agent_id?: string | null; task_title?: string; prompt?: string; }

export interface TriggerRule {
  id: string; room: string; name: string; enabled: 0 | 1; match_type: 'keyword' | 'sender' | 'event';
  pattern: string; agent_id: string | null; task_title: string; prompt: string; owner: string;
  cooldown_sec: number; last_fired_ms: number | null; created_at_ms: number; updated_at_ms: number;
}
export interface NewTriggerRule { name: string; match_type: 'keyword' | 'sender' | 'event'; pattern: string; agent_id?: string; task_title?: string; prompt: string; cooldown_sec?: number; }
export interface TriggerRulePatch { name?: string; enabled?: boolean; match_type?: 'keyword' | 'sender' | 'event'; pattern?: string; agent_id?: string | null; task_title?: string; prompt?: string; cooldown_sec?: number; }

async function apiJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) {
    let msg = `${res.status}`;
    try { const d = (await res.json()) as { error?: string }; if (d.error) msg = d.error; } catch { /* 忽略 */ }
    throw new Error(msg);
  }
  return (await res.json()) as T;
}

export async function fetchSchedules(room: string): Promise<ScheduledTask[]> {
  const data = await apiJson<{ schedules: ScheduledTask[] }>(`${BASE}/api/rooms/${encodeURIComponent(room)}/schedules`);
  return data.schedules ?? [];
}
export async function createSchedule(room: string, input: NewScheduledTask): Promise<ScheduledTask> {
  const data = await apiJson<{ schedule: ScheduledTask }>(`${BASE}/api/rooms/${encodeURIComponent(room)}/schedules`, {
    method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ ...input, owner: 'web' }),
  });
  return data.schedule;
}
export async function updateSchedule(room: string, id: string, patch: ScheduledTaskPatch): Promise<ScheduledTask> {
  const data = await apiJson<{ schedule: ScheduledTask }>(`${BASE}/api/rooms/${encodeURIComponent(room)}/schedules/${encodeURIComponent(id)}`, {
    method: 'PATCH', headers: { 'content-type': 'application/json' }, body: JSON.stringify(patch),
  });
  return data.schedule;
}
export async function deleteSchedule(room: string, id: string): Promise<void> {
  await apiJson<{ ok: boolean }>(`${BASE}/api/rooms/${encodeURIComponent(room)}/schedules/${encodeURIComponent(id)}`, { method: 'DELETE' });
}
export async function fetchTriggers(room: string): Promise<TriggerRule[]> {
  const data = await apiJson<{ triggers: TriggerRule[] }>(`${BASE}/api/rooms/${encodeURIComponent(room)}/triggers`);
  return data.triggers ?? [];
}
export async function createTrigger(room: string, input: NewTriggerRule): Promise<TriggerRule> {
  const data = await apiJson<{ trigger: TriggerRule }>(`${BASE}/api/rooms/${encodeURIComponent(room)}/triggers`, {
    method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ ...input, owner: 'web' }),
  });
  return data.trigger;
}
export async function updateTrigger(room: string, id: string, patch: TriggerRulePatch): Promise<TriggerRule> {
  const data = await apiJson<{ trigger: TriggerRule }>(`${BASE}/api/rooms/${encodeURIComponent(room)}/triggers/${encodeURIComponent(id)}`, {
    method: 'PATCH', headers: { 'content-type': 'application/json' }, body: JSON.stringify(patch),
  });
  return data.trigger;
}
export async function deleteTrigger(room: string, id: string): Promise<void> {
  await apiJson<{ ok: boolean }>(`${BASE}/api/rooms/${encodeURIComponent(room)}/triggers/${encodeURIComponent(id)}`, { method: 'DELETE' });
}

// ===== append to web/src/api.ts =====
export interface ShareViewData {
  room: RoomInfo;
  share: { id: string; expires_at_ms: number };
  messages: HistoryMessage[];
}

export async function fetchShareView(token: string): Promise<ShareViewData> {
  const res = await fetch(`${BASE}/api/share/${encodeURIComponent(token)}`);
  if (!res.ok) {
    let error = String(res.status);
    try {
      const body = await res.json();
      if (body && typeof body.error === "string" && body.error) {
        error = body.error;
      }
    } catch {
      // keep status code
    }
    throw new Error(`share ${res.status} ${error}`);
  }
  return (await res.json()) as ShareViewData;
}

export interface ShareLinkMeta {
    id: string;
    room: string;
    created_at_ms: number;
    expires_at_ms: number;
    revoked_at_ms: number | null;
}

export interface IssuedShareLink {
    id: string;
    room: string;
    share_token: string;
    share_url: string;
    expires_at_ms: number;
}

export async function listShareLinks(room: string, requester: string): Promise<ShareLinkMeta[]> {
    const url = `${BASE}/api/rooms/${encodeURIComponent(room)}/share-links?requester=${encodeURIComponent(requester)}`;
    const data = await apiJson<{ links: ShareLinkMeta[] }>(url);
    return Array.isArray(data?.links) ? data.links : [];
}

export async function issueShareLink(room: string, requester: string, ttlHours?: number): Promise<IssuedShareLink> {
    const url = `${BASE}/api/rooms/${encodeURIComponent(room)}/share-links`;
    const body: { requester: string; ttl_hours?: number } = { requester };
    if (ttlHours !== undefined) {
        body.ttl_hours = ttlHours;
    }
    return apiJson<IssuedShareLink>(url, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) });
}

export async function revokeShareLink(room: string, id: string, requester: string): Promise<void> {
    const url = `${BASE}/api/rooms/${encodeURIComponent(room)}/share-links/${encodeURIComponent(id)}`;
    const res = await fetch(url, {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ requester }),
    });
    if (res.ok) {
        return;
    }
    let message = '';
    try {
        const parsed = (await res.json()) as { error?: string } | null;
        message = parsed?.error ?? '';
    } catch {
        // ignore parse failure
    }
    throw new Error(message || `Failed to revoke share link (HTTP ${res.status})`);
}

export interface ReactionSummary {
  reaction: string;
  count: number;
  reactors: string[];
}

// 顺序与网关 gateway/src/reactions.ts 的 SUPPORTED_REACTIONS 保持一致
export const REACTION_OPTIONS: readonly string[] = [
  '+1',
  'like',
  'smile',
  'ok',
  'done',
  'heart',
  'thumbs_up',
  'thumbs_down',
];

export async function fetchMessageReactions(room: string, messageId: number): Promise<ReactionSummary[]> {
  const data = await apiJson<{ reactions?: ReactionSummary[] }>(
    `${BASE}/api/rooms/${encodeURIComponent(room)}/messages/${messageId}/reactions`,
  );
  return Array.isArray(data.reactions) ? data.reactions : [];
}

export async function addMessageReaction(room: string, messageId: number, reaction: string, requester: string): Promise<{ added: boolean; reactions: ReactionSummary[] }> {
  const data = await apiJson<{ added?: boolean; reactions?: ReactionSummary[] }>(
    `${BASE}/api/rooms/${encodeURIComponent(room)}/messages/${messageId}/reactions`,
    {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ reaction, requester }),
    },
  );
  return {
    added: typeof data.added === 'boolean' ? data.added : false,
    reactions: Array.isArray(data.reactions) ? data.reactions : [],
  };
}

export async function removeMessageReaction(room: string, messageId: number, reaction: string, requester: string): Promise<{ removed: boolean; reactions: ReactionSummary[] }> {
  const data = await apiJson<{ removed?: boolean; reactions?: ReactionSummary[] }>(
    `${BASE}/api/rooms/${encodeURIComponent(room)}/messages/${messageId}/reactions?reaction=${encodeURIComponent(reaction)}&requester=${encodeURIComponent(requester)}`,
    { method: 'DELETE' },
  );
  return {
    removed: typeof data.removed === 'boolean' ? data.removed : false,
    reactions: Array.isArray(data.reactions) ? data.reactions : [],
  };
}

export interface IssuedPairingCode {
  code: string;
  room: string;
  expires_at_ms: number;
}

export async function issuePairingCode(room: string, requester: string, ttlMinutes?: number): Promise<IssuedPairingCode> {
  const body: { requester: string; ttl_minutes?: number } = { requester };
  if (ttlMinutes !== undefined) {
    body.ttl_minutes = ttlMinutes;
  }
  return apiJson<IssuedPairingCode>(`${BASE}/api/rooms/${encodeURIComponent(room)}/pairing-codes`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  });
}

export interface RedeemedPairingCode {
  room: string;
  adapter_id: string;
  redeemed_at_ms: number;
}

export async function redeemPairingCode(code: string, adapterId: string): Promise<RedeemedPairingCode> {
  return apiJson<RedeemedPairingCode>(`${BASE}/api/pairing-codes/redeem`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ code, adapter_id: adapterId }),
  });
}

export interface DeviceMeta {
  device_id: string;
  room: string;
  adapter_id: string;
  created_at_ms: number;
  last_seen_ms: number;
  revoked_at_ms: number | null;
}

export async function listDevices(room: string, requester: string): Promise<DeviceMeta[]> {
  const url = `${BASE}/api/rooms/${encodeURIComponent(room)}/devices?requester=${encodeURIComponent(requester)}`;
  const data = await apiJson<{ devices: DeviceMeta[] }>(url);
  return Array.isArray(data?.devices) ? data.devices : [];
}

export async function revokeDevice(room: string, deviceId: string, requester: string): Promise<void> {
  const url = `${BASE}/api/rooms/${encodeURIComponent(room)}/devices/${encodeURIComponent(deviceId)}`;
  const res = await fetch(url, {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ requester }),
  });
  if (res.ok) return;
  let message: string | undefined;
  try {
    message = (await res.json())?.error;
  } catch {
    /* ignore non-JSON error body */
  }
  throw new Error(message || `Failed to revoke device (HTTP ${res.status})`);
}
