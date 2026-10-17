import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { LogOut } from 'lucide-react';
import { ChatSocket, InboundMessage, WSStatus } from '../ws';
import { fetchHistory, fetchPresence, HistoryMessage } from '../api';
import MessageList, { ChatItem } from './MessageList';
import Composer from './Composer';
import Members, { MemberEntry } from './Members';

interface Props {
  nick: string;
  onLeave: () => void;
}

const ROOM = 'lobby';
const PAGE_SIZE = 50;

interface TaskReceipt {
  task_id: string;
  task_status: string;
}

export default function Chat({ nick, onLeave }: Props) {
  const [items, setItems] = useState<ChatItem[]>([]);
  const [members, setMembers] = useState<MemberEntry[]>([]);
  const [status, setStatus] = useState<WSStatus>('idle');
  const [loadingOlder, setLoadingOlder] = useState(false);
  const [hasMore, setHasMore] = useState(true);

  const socketRef = useRef<ChatSocket | null>(null);
  const seenRef = useRef<Set<string>>(new Set());
  const oldestIdRef = useRef<string | null>(null);
  const loadingOlderRef = useRef(false);

  const ingestHistory = useCallback((rows: HistoryMessage[]) => {
    if (rows.length === 0) return;
    setItems((prev) => {
      const merged: ChatItem[] = [...prev];
      for (const row of rows) {
        const key = `${row.sender}#${row.seq}`;
        if (seenRef.current.has(key)) continue;
        seenRef.current.add(key);
        merged.push(toChatItem(row));
      }
      merged.sort(compareItems);
      return merged;
    });
  }, []);

  const ingestFrame = useCallback((frame: InboundMessage) => {
    if (frame.type === 'presence') {
      const adapter_id = String(frame.payload.adapter_id ?? '');
      const rawStatus = String(frame.payload.status ?? '');
      if (!adapter_id || (rawStatus !== 'online' && rawStatus !== 'offline')) return;
      const rawIn = frame.payload.usage_in;
      const rawOut = frame.payload.usage_out;
      const usage: { usage_in?: number; usage_out?: number } = {};
      if (typeof rawIn === 'number') usage.usage_in = rawIn;
      if (typeof rawOut === 'number') usage.usage_out = rawOut;
      setMembers((prev) => mergePresence(prev, adapter_id, rawStatus, Date.now(), usage));
      return;
    }
    if (frame.type !== 'message') return;
    const key = `${frame.sender}#${frame.seq}`;
    if (seenRef.current.has(key)) return;
    seenRef.current.add(key);
    const item = toChatItem({
      id: String(frame.payload.msg_id ?? key),
      room: frame.room,
      sender: frame.sender,
      seq: frame.seq,
      type: frame.type,
      payload: frame.payload as HistoryMessage['payload'],
      ts: frame.ts,
    });
    setItems((prev) => {
      const next = [...prev, item];
      next.sort(compareItems);
      return next;
    });
  }, []);

  useEffect(() => {
    let cancelled = false;

    (async () => {
      try {
        const rows = await fetchHistory(ROOM, PAGE_SIZE);
        if (cancelled) return;
        ingestHistory(rows);
        if (rows.length > 0) oldestIdRef.current = rows[0].id;
        if (rows.length < PAGE_SIZE) setHasMore(false);
      } catch {
        /* 拉不到历史先不阻塞 */
      }
    })();

    (async () => {
      try {
        const list = await fetchPresence(ROOM);
        if (cancelled) return;
        setMembers(
          list.map((m) => ({
            adapter_id: m.adapter_id,
            status: m.status,
            last_seen_ms: m.last_seen_ms,
            isSelf: m.adapter_id === nick,
            usage_in: m.usage_in,
            usage_out: m.usage_out,
          })),
        );
      } catch {
        /* ignore */
      }
    })();

    const sock = new ChatSocket(nick, ROOM, {
      onStatus: setStatus,
      onFrame: ingestFrame,
    });
    socketRef.current = sock;
    sock.connect();

    return () => {
      cancelled = true;
      sock.close();
      socketRef.current = null;
    };
  }, [nick, ingestFrame, ingestHistory]);

  const loadOlder = useCallback(async () => {
    if (loadingOlderRef.current || !hasMore || !oldestIdRef.current) return;
    loadingOlderRef.current = true;
    setLoadingOlder(true);
    try {
      const rows = await fetchHistory(ROOM, PAGE_SIZE, oldestIdRef.current);
      if (rows.length === 0) {
        setHasMore(false);
      } else {
        ingestHistory(rows);
        oldestIdRef.current = rows[0].id;
        if (rows.length < PAGE_SIZE) setHasMore(false);
      }
    } catch {
      /* ignore */
    } finally {
      loadingOlderRef.current = false;
      setLoadingOlder(false);
    }
  }, [hasMore, ingestHistory]);

  const handleSend = useCallback((text: string, mentions: string[]) => {
    socketRef.current?.sendMessage(text, mentions);
  }, []);

  const onlineCount = useMemo(
    () => members.filter((m) => m.status === 'online').length,
    [members],
  );

  return (
    <div className="chat">
      <header className="chat-top">
        <div className="chat-top-left">
          <span className="room-name">lobby</span>
          <span className="room-meta">{onlineCount} 人在线</span>
          <span className={`conn conn-${status}`} title={statusLabel(status)}>
            {statusLabel(status)}
          </span>
        </div>
        <button className="btn-ghost" type="button" onClick={onLeave} title="退出">
          <LogOut size={16} strokeWidth={2} />
          <span>退出</span>
        </button>
      </header>
      <div className="chat-body">
        <main className="chat-main">
          <MessageList
            items={items}
            selfNick={nick}
            onTopReached={loadOlder}
            loadingOlder={loadingOlder}
            hasMore={hasMore}
          />
          <Composer members={members} onSend={handleSend} />
        </main>
        <Members members={members} selfNick={nick} />
      </div>
    </div>
  );
}

function statusLabel(s: WSStatus): string {
  switch (s) {
    case 'open':
      return '已连接';
    case 'connecting':
      return '连接中';
    case 'closed':
      return '已断开';
    default:
      return '未连接';
  }
}

function toChatItem(row: HistoryMessage): ChatItem {
  const taskStatus = row.payload.task_status;
  const isTask =
    typeof taskStatus === 'string' &&
    (taskStatus === 'running' || taskStatus === 'done' || taskStatus === 'failed');
  return {
    key: `${row.sender}#${row.seq}`,
    msgId: String(row.payload.msg_id ?? row.id),
    sender: row.sender,
    seq: row.seq,
    ts: row.ts,
    text: String(row.payload.text ?? ''),
    mentions: Array.isArray(row.payload.mentions) ? row.payload.mentions : [],
    kind: isTask ? 'task' : 'message',
    taskId: row.payload.task_id,
    taskStatus: isTask ? (taskStatus as string) : undefined,
  };
}

function compareItems(a: ChatItem, b: ChatItem): number {
  if (a.ts !== b.ts) return a.ts - b.ts;
  return a.seq - b.seq;
}

function mergePresence(
  prev: MemberEntry[],
  adapter_id: string,
  status: 'online' | 'offline',
  last_seen_ms: number,
  usage?: { usage_in?: number; usage_out?: number },
): MemberEntry[] {
  const next = prev.slice();
  const idx = next.findIndex((m) => m.adapter_id === adapter_id);
  if (idx === -1) {
    next.push({
      adapter_id,
      status,
      last_seen_ms,
      isSelf: false,
      usage_in: usage?.usage_in,
      usage_out: usage?.usage_out,
    });
  } else {
    const merged: MemberEntry = { ...next[idx], status, last_seen_ms };
    // 帧里带用量就更新，没带就沿用之前记下的值
    if (usage?.usage_in !== undefined) merged.usage_in = usage.usage_in;
    if (usage?.usage_out !== undefined) merged.usage_out = usage.usage_out;
    next[idx] = merged;
  }
  next.sort((a, b) => {
    if (a.status !== b.status) return a.status === 'online' ? -1 : 1;
    return a.adapter_id.localeCompare(b.adapter_id);
  });
  return next;
}

// TaskReceipt 仅用于类型校验参考，运行时不需要
export type { TaskReceipt };
