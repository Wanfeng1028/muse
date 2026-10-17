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
