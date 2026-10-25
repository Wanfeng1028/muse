import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { CalendarClock, ClipboardList, Gamepad2, LogOut, Moon, Settings, ShieldCheck, Spade } from 'lucide-react';
import { ChatSocket, InboundMessage, WSStatus } from '../ws';
import { fetchHistory, fetchPresence, fetchRoom, updateRoom, createGameSession, RoomInfo, RoomType, ROOM_TYPE_LABEL, HistoryMessage, GameStatePayload, fetchPendingApprovals } from '../api';
import MessageList, { ChatItem } from './MessageList';
import Composer from './Composer';
import Members, { MemberEntry } from './Members';
import TaskPanel from './TaskPanel';
import ApprovalQueue, { ApprovalRequest } from './ApprovalQueue';
import Workflows from './Workflows';
import GamePanel from './GamePanel';
import DoudizhuPanel, { isDoudizhuState } from '../doudizhu/DoudizhuPanel';
import DoudizhuResult from '../doudizhu/DoudizhuResult';
import DoudizhuLobby from '../doudizhu/DoudizhuLobby';
import WerewolfPanel, { isWerewolfState } from '../werewolf/WerewolfPanel';
import WerewolfResult from '../werewolf/WerewolfResult';
import WerewolfLobby from '../werewolf/WerewolfLobby';

interface Props {
  nick: string;
  room: string;
  onLeave: () => void;
}

const PAGE_SIZE = 50;

interface TaskReceipt {
  task_id: string;
  task_status: string;
}

export default function Chat({ nick, room, onLeave }: Props) {
  const [items, setItems] = useState<ChatItem[]>([]);
  const [members, setMembers] = useState<MemberEntry[]>([]);
  const [status, setStatus] = useState<WSStatus>('idle');
  const [loadingOlder, setLoadingOlder] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  const [showTasks, setShowTasks] = useState(false);
  const [showApprovals, setShowApprovals] = useState(false);
  const [showWorkflows, setShowWorkflows] = useState(false);
  const [approvals, setApprovals] = useState<ApprovalRequest[]>([]);
  const [pendingReply, setPendingReply] = useState<{ msgId: string; sender: string; text: string } | null>(null);
  const [showGame, setShowGame] = useState(false);
  const [showDoudizhuLobby, setShowDoudizhuLobby] = useState(false);
  const [doudizhuErr, setDoudizhuErr] = useState<string | null>(null);
  const [showWerewolfLobby, setShowWerewolfLobby] = useState(false);
  const [werewolfErr, setWerewolfErr] = useState<string | null>(null);
  const [gameState, setGameState] = useState<GameStatePayload | null>(null);
  const [taskRefreshKey, setTaskRefreshKey] = useState(0);
  const [unreadCount, setUnreadCount] = useState(0);
  const [roomInfo, setRoomInfo] = useState<RoomInfo | null>(null);
  const [showRoomSettings, setShowRoomSettings] = useState(false);
  const [pendingType, setPendingType] = useState<RoomType>('workroom');
  const [roomErr, setRoomErr] = useState<string | null>(null);
  const showTasksRef = useRef(false);
  showTasksRef.current = showTasks;

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
    if (frame.type === 'task_event') {
      setTaskRefreshKey((k) => k + 1);
      const tid = String(frame.payload.task_id ?? '');
      const st = String(frame.payload.status ?? '');
      if (tid && (st === 'dispatched' || st === 'failed' || st === 'cancelled')) {
        setApprovals((prev) => prev.filter((a) => a.task_id !== tid));
      }
      return;
    }
    if (frame.type === 'approval_request') {
      if (frame.room !== room) return;
      const p = frame.payload as Record<string, unknown>;
      const approvalId = String(p.approval_id ?? '');
      if (!approvalId) return;
      const item: ApprovalRequest = {
        approval_id: approvalId,
        task_id: String(p.task_id ?? ''),
        requester: String(p.requester ?? ''),
        assignee: String(p.assignee ?? ''),
        title: String(p.title ?? ''),
        expires_at_ms: Number(p.expires_at_ms ?? 0),
      };
      setApprovals((prev) =>
        prev.some((a) => a.approval_id === approvalId) ? prev : [...prev, item],
      );
      return;
    }
    if (frame.type === 'game_state') {
      const p = frame.payload as unknown as GameStatePayload;
      // 网关广播的 state 是引擎返回的 {v, state[, error]} 会话包，面板要内层 state
      const s = p.state as { v?: unknown; state?: unknown } | null | undefined;
      const inner = s && typeof s === 'object' && 'v' in s && 'state' in s ? s.state : p.state;
      setGameState({ ...p, state: inner });
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
    if (showTasksRef.current && frame.sender !== nick) {
      setUnreadCount((c) => c + 1);
    }
  }, [nick, room]);

  useEffect(() => {
    let cancelled = false;

    (async () => {
      try {
        const rows = await fetchHistory(room, PAGE_SIZE);
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
        const list = await fetchPresence(room);
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

    (async () => {
      try {
        const info = await fetchRoom(room);
        if (cancelled) return;
        setRoomInfo(info);
        setPendingType(info.type);
      } catch {
        /* 房间元数据拉不到不阻塞聊天 */
      }
    })();

    const sock = new ChatSocket(nick, room, {
      onStatus: setStatus,
      onFrame: ingestFrame,
    });
    socketRef.current = sock;
    (async () => {
      try {
        const pending = await fetchPendingApprovals(room);
        if (!cancelled) setApprovals(pending);
      } catch {
        /* 拉不到不阻塞聊天 */
      }
    })();
    sock.connect();

    return () => {
      cancelled = true;
      sock.close();
      socketRef.current = null;
    };
  }, [nick, room, ingestFrame, ingestHistory]);

  const loadOlder = useCallback(async () => {
    if (loadingOlderRef.current || !hasMore || !oldestIdRef.current) return;
    loadingOlderRef.current = true;
    setLoadingOlder(true);
    try {
      const rows = await fetchHistory(room, PAGE_SIZE, oldestIdRef.current);
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
    socketRef.current?.sendMessage(text, mentions, pendingReply?.msgId);
    setPendingReply(null);
  }, [pendingReply]);

  const handleSendTask = useCallback((text: string, mentions: string[]) => {
    socketRef.current?.sendTask(text, mentions);
  }, []);

  const markReadAndCloseTasks = useCallback(() => {
    setShowTasks(false);
    setUnreadCount(0);
  }, []);

  const jumpToTask = useCallback((taskId: string) => {
    setShowTasks(false);
    setUnreadCount(0);
    requestAnimationFrame(() => {
      const el = document.querySelector(`[data-taskid="${CSS.escape(taskId)}"]`);
      if (el) {
        el.scrollIntoView({ block: 'center', behavior: 'smooth' });
        el.classList.add('task-flash');
        window.setTimeout(() => el.classList.remove('task-flash'), 1600);
      }
    });
  }, []);

  const onlineCount = useMemo(
    () => members.filter((m) => m.status === 'online').length,
    [members],
  );

  return (
    <div className="chat">
      <header className="chat-top">
        <div className="chat-top-left">
          <span className="room-name">{roomInfo?.name || room}</span>
          {roomInfo && (
            <span className={`room-badge room-badge-${roomInfo.type}`}>
              {ROOM_TYPE_LABEL[roomInfo.type]}
            </span>
          )}
          <span className="room-meta">{onlineCount} 人在线</span>
          <span className={`conn conn-${status}`} title={statusLabel(status)}>
            {statusLabel(status)}
          </span>
        </div>
        <button className="btn-ghost" type="button" onClick={() => setShowRoomSettings((v) => !v)} title="房间设置">
          <Settings size={16} strokeWidth={2} />
          <span>设置</span>
        </button>
        <button className="btn-ghost" type="button" onClick={() => setShowGame((v) => !v)} title="小游戏">
          <Gamepad2 size={16} strokeWidth={2} />
          <span>游戏</span>
        </button>
        <button className="btn-ghost" type="button" onClick={() => { setDoudizhuErr(null); setShowDoudizhuLobby(true); }} title="开一局斗地主">
          <Spade size={16} strokeWidth={2} />
          <span>斗地主</span>
        </button>
        <button className="btn-ghost" type="button" onClick={() => { setWerewolfErr(null); setShowWerewolfLobby(true); }} title="开一局狼人杀">
          <Moon size={16} strokeWidth={2} />
          <span>狼人杀</span>
        </button>
        <button className="btn-ghost" type="button" onClick={() => setShowTasks((v) => !v)} title="任务追踪">
          <ClipboardList size={16} strokeWidth={2} />
          <span>任务</span>
        </button>
        <button className="btn-ghost" type="button" onClick={() => setShowApprovals((v) => !v)} title="审批中心">
          <ShieldCheck size={16} strokeWidth={2} />
          <span>审批{approvals.length > 0 ? ` (${approvals.length})` : ''}</span>
        </button>
        <button className="btn-ghost" type="button" onClick={() => setShowWorkflows((v) => !v)} title="定时与触发">
          <CalendarClock size={16} strokeWidth={2} />
          <span>工作流</span>
        </button>
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
            onReply={(item) => setPendingReply({ msgId: item.msgId, sender: item.sender, text: item.text })}
          />
          {pendingReply && (
            <div className="reply-bar">
              回复 {pendingReply.sender}：{pendingReply.text.slice(0, 80)}
              <button type="button" onClick={() => setPendingReply(null)}>取消</button>
            </div>
          )}
          {showTasks && unreadCount > 0 && (
            <button className="unread-pill" type="button" onClick={markReadAndCloseTasks}>
              有 {unreadCount} 条新消息，点击查看
            </button>
          )}
          <Composer members={members} onSend={handleSend} onSendTask={handleSendTask} />
        </main>
        <Members members={members} selfNick={nick} />
      </div>
      {showRoomSettings && (
        <div className="room-settings">
          <div className="room-settings-title">房间设置</div>
          <label className="room-settings-label">
            房间类型
            <select
              className="room-settings-select"
              value={pendingType}
              onChange={(e) => setPendingType(e.target.value as RoomType)}
            >
              <option value="workroom">工作坊（定向派发，任务协作）</option>
              <option value="playroom">娱乐厅（广播抢话，玩游戏）</option>
            </select>
          </label>
          <div className="room-settings-hint">
            工作坊改类型只有房主能操作，娱乐厅所有成员都能改。
          </div>
          {roomErr && <div className="room-err">{roomErr}</div>}
          <button
            className="btn-primary"
            type="button"
            onClick={async () => {
              setRoomErr(null);
              try {
                const updated = await updateRoom(room, { type: pendingType, requester: nick });
                setRoomInfo(updated);
                setShowRoomSettings(false);
              } catch (err) {
                setRoomErr(err instanceof Error ? err.message : '保存失败');
              }
            }}
          >
            保存
          </button>
        </div>
      )}
      {showGame && gameState?.game === 'doudizhu' && (
        isDoudizhuState(gameState.state) && gameState.state.phase === 'finished' ? (
          <DoudizhuResult
            state={gameState.state}
            seat={nick}
            onRematch={() => { setDoudizhuErr(null); setShowDoudizhuLobby(true); }}
            onClose={() => setShowGame(false)}
          />
        ) : (
          <DoudizhuPanel
            state={gameState.state}
            seat={nick}
            onAction={(action) => socketRef.current?.sendGameAction('doudizhu', action, nick)}
          />
        )
      )}

      {showGame && gameState?.game === 'werewolf' && (
        isWerewolfState(gameState.state) && gameState.state.phase === 'finished' ? (
          <WerewolfResult
            state={gameState.state}
            seat={nick}
            onRematch={() => { setWerewolfErr(null); setShowWerewolfLobby(true); }}
            onClose={() => setShowGame(false)}
          />
        ) : (
          <WerewolfPanel
            state={gameState.state}
            seat={nick}
            onAction={(action) => socketRef.current?.sendGameAction('werewolf', action, nick)}
          />
        )
      )}

      {showGame && gameState?.game !== 'doudizhu' && gameState?.game !== 'werewolf' && (
        <GamePanel
          gameState={gameState}
          onSendAction={(game, action) => socketRef.current?.sendGameAction(game, action)}
        />
      )}
      {showDoudizhuLobby && (
        <DoudizhuLobby
          defaultSeat={nick}
          err={doudizhuErr}
          onStart={async (seats) => {
            try {
              await createGameSession(room, 'doudizhu', seats);
              socketRef.current?.sendGameAction('doudizhu', { kind: 'start', seats }, nick);
              setShowDoudizhuLobby(false);
              setDoudizhuErr(null);
              setShowGame(true);
            } catch (e) {
              setDoudizhuErr(e instanceof Error ? e.message : '开局失败');
            }
          }}
          onClose={() => setShowDoudizhuLobby(false)}
        />
      )}
      {showWerewolfLobby && (
        <WerewolfLobby
          defaultSeat={nick}
          err={werewolfErr}
          onStart={async (seats) => {
            try {
              await createGameSession(room, 'werewolf', seats);
              socketRef.current?.sendGameAction('werewolf', { kind: 'start', seats }, nick);
              setShowWerewolfLobby(false);
              setWerewolfErr(null);
              setShowGame(true);
            } catch (e) {
              setWerewolfErr(e instanceof Error ? e.message : '开局失败');
            }
          }}
          onClose={() => setShowWerewolfLobby(false)}
        />
      )}
      {showTasks && (
        <TaskPanel
          room={room}
          nick={nick}
          refreshKey={taskRefreshKey}
          onClose={markReadAndCloseTasks}
          onJumpToTask={jumpToTask}
        />
      )}
      {showApprovals && (
        <ApprovalQueue
          approvals={approvals}
          nick={nick}
          onClose={() => setShowApprovals(false)}
          onDecide={(approvalId, decision, note) =>
            socketRef.current?.sendApprovalDecision(approvalId, decision, note)
          }
        />
      )}
      {showWorkflows && (
        <Workflows room={room} onClose={() => setShowWorkflows(false)} />
      )}
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
    replyTo: typeof row.payload.reply_to === 'string' ? row.payload.reply_to : undefined,
    threadId: typeof row.payload.thread_id === 'string' ? row.payload.thread_id : undefined,
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
