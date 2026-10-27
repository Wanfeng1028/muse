import React, { useEffect, useLayoutEffect, useRef } from 'react';
import { Bot, Loader2, User } from 'lucide-react';
import { REACTION_OPTIONS, ReactionSummary } from '../api';

export interface ChatItem {
  key: string;
  msgId: string;
  // dbId 为网关 messages 表整数主键；实时 WS 帧没有该值时为 null。
  dbId: number | null;
  sender: string;
  seq: number;
  ts: number;
  text: string;
  mentions: string[];
  replyTo?: string;
  threadId?: string;
  kind: 'message' | 'task';
  taskId?: string;
  taskStatus?: string;
}

interface Props {
  items: ChatItem[];
  selfNick: string;
  onTopReached: () => void;
  loadingOlder: boolean;
  hasMore: boolean;
  onReply?: (item: ChatItem) => void;
  reactions: Record<string, ReactionSummary[]>;
  onLoadReactions: (item: ChatItem) => void;
  onToggleReaction: (item: ChatItem, reaction: string) => void;
}

const TOP_THRESHOLD = 48;

export default function MessageList({
  items,
  selfNick,
  onTopReached,
  loadingOlder,
  hasMore,
  onReply,
  reactions,
  onLoadReactions,
  onToggleReaction,
}: Props) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const prevFirstKeyRef = useRef<string | null>(null);
  const prevCountRef = useRef(0);
  const stickToBottomRef = useRef(true);

  useLayoutEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const firstKey = items[0]?.key ?? null;
    const prepended = items.length > prevCountRef.current && prevFirstKeyRef.current !== null && firstKey !== prevFirstKeyRef.current;
    if (prepended) {
      // 向上翻页：保持视口相对位置
      const prevFirst = prevFirstKeyRef.current;
      const anchor = el.querySelector<HTMLElement>(`[data-key="${cssEscape(prevFirst!)}"]`);
      if (anchor) {
        el.scrollTop = anchor.offsetTop - 8;
      }
    } else if (stickToBottomRef.current) {
      bottomRef.current?.scrollIntoView({ block: 'end' });
    }
    prevFirstKeyRef.current = firstKey;
    prevCountRef.current = items.length;
  }, [items]);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const onScroll = () => {
      const distance = el.scrollHeight - el.scrollTop - el.clientHeight;
      stickToBottomRef.current = distance < 64;
      if (el.scrollTop <= TOP_THRESHOLD && hasMore && !loadingOlder) {
        onTopReached();
      }
    };
    el.addEventListener('scroll', onScroll, { passive: true });
    return () => el.removeEventListener('scroll', onScroll);
  }, [hasMore, loadingOlder, onTopReached]);

  return (
    <div className="msgs" ref={scrollRef}>
      {loadingOlder && (
        <div className="msgs-loading">
          <Loader2 size={14} strokeWidth={2} className="spin" />
          <span>加载更早的消息</span>
        </div>
      )}
      {!hasMore && items.length > 0 && (
        <div className="msgs-loading msgs-loading-quiet">已经到头了</div>
      )}
      {items.length === 0 ? (
        <div className="msgs-empty">还没有消息，说点什么吧</div>
      ) : (
        groupChatItems(items).map((group) => (
          <ThreadGroup key={group.root.key} root={group.root} replies={group.replies} items={items} selfNick={selfNick} onReply={onReply} reactions={reactions} onLoadReactions={onLoadReactions} onToggleReaction={onToggleReaction} />
        ))
      )}
      <div ref={bottomRef} />
    </div>
  );
}

function groupChatItems(items: ChatItem[]): { root: ChatItem; replies: ChatItem[] }[] {
  const byId = new Map<string, ChatItem>();
  for (const item of items) byId.set(item.msgId, item);
  const groups: { root: ChatItem; replies: ChatItem[] }[] = [];
  const grouped = new Set<string>();
  for (const item of items) {
    if (item.kind === 'task') { groups.push({ root: item, replies: [] }); grouped.add(item.key); continue; }
    const threadId = item.threadId ?? item.msgId;
    if (threadId !== item.msgId) continue;
    const replies = items.filter((x) => x.kind !== 'task' && x.threadId === item.msgId && x.msgId !== item.msgId).sort((a, b) => a.ts - b.ts || a.seq - b.seq);
    for (const r of replies) grouped.add(r.key);
    groups.push({ root: item, replies });
    grouped.add(item.key);
  }
  for (const item of items) {
    if (!grouped.has(item.key)) groups.push({ root: item, replies: [] });
  }
  return groups;
}

function ThreadGroup({ root, replies, items, selfNick, onReply, reactions, onLoadReactions, onToggleReaction }: { root: ChatItem; replies: ChatItem[]; items: ChatItem[]; selfNick: string; onReply?: (item: ChatItem) => void; reactions: Record<string, ReactionSummary[]>; onLoadReactions: (item: ChatItem) => void; onToggleReaction: (item: ChatItem, reaction: string) => void }) {
  const [open, setOpen] = React.useState(false);
  const byId = new Map(items.map((x) => [x.msgId, x]));
  if (root.kind === 'task') return <TaskRow item={root} />;
  return (
    <div className="thread-group">
      <MessageRow item={root} selfNick={selfNick} onReply={onReply} reactions={reactions} onLoadReactions={onLoadReactions} onToggleReaction={onToggleReaction} />
      {replies.length > 0 && (
        <>
          <button className="thread-toggle" onClick={() => setOpen(!open)} aria-expanded={open}>
            {open ? '收起回复' : `展开 ${replies.length} 条回复`}
          </button>
          {open && replies.map((r) => (
            <div key={r.key} className="thread-reply">
              <div className="thread-quote">
                {r.replyTo && byId.get(r.replyTo) ? `引用 ${byId.get(r.replyTo)!.sender}：${byId.get(r.replyTo)!.text.slice(0, 80)}` : '引用消息已删除'}
              </div>
              <MessageRow item={r} selfNick={selfNick} onReply={onReply} reactions={reactions} onLoadReactions={onLoadReactions} onToggleReaction={onToggleReaction} />
            </div>
          ))}
        </>
      )}
    </div>
  );
}

function MessageRow({ item, selfNick, onReply, reactions, onLoadReactions, onToggleReaction }: { item: ChatItem; selfNick: string; onReply?: (item: ChatItem) => void; reactions: Record<string, ReactionSummary[]>; onLoadReactions: (item: ChatItem) => void; onToggleReaction: (item: ChatItem, reaction: string) => void }) {
  const isSelf = item.sender === selfNick;
  const mentionsMe = item.mentions.includes(selfNick);
  const highlightClass = [
    'msg',
    isSelf ? 'msg-self' : '',
    mentionsMe ? 'msg-mentioned' : '',
  ]
    .filter(Boolean)
    .join(' ');
  const [pickerOpen, setPickerOpen] = React.useState(false);
  const loadedDbIdRef = React.useRef<number | null>(null);
  const summary = item.dbId === null ? [] : (reactions[String(item.dbId)] ?? []);
  React.useEffect(() => {
    if (item.dbId === null || loadedDbIdRef.current === item.dbId) return;
    loadedDbIdRef.current = item.dbId;
    onLoadReactions(item);
  }, [item, onLoadReactions]);

  return (
    <div className={highlightClass} data-key={item.key}>
      <div className="msg-avatar" aria-hidden="true">
        {isSelf ? <User size={16} strokeWidth={2} /> : <Bot size={16} strokeWidth={2} />}
      </div>
      <div className="msg-body">
        <div className="msg-head">
          <span className="msg-sender">{item.sender}</span>
          <span className="msg-time">{formatTime(item.ts)}</span>
          {onReply && <button className="msg-reply-btn" type="button" onClick={() => onReply(item)}>回复</button>}
          <button className="msg-react-btn" type="button" aria-expanded={pickerOpen} onClick={() => setPickerOpen((v) => !v)}>反应</button>
        </div>
        <div className="msg-text">{renderText(item.text, item.mentions)}</div>
        {summary.length > 0 && (
          <div className="msg-reactions">
            {summary.map((g) => (
              <button key={g.reaction} type="button" className={g.reactors.includes(selfNick) ? 'reaction-chip reaction-chip-mine' : 'reaction-chip'} title={g.reactors.join('、')} onClick={() => onToggleReaction(item, g.reaction)}>
                {g.reaction} {g.count}
              </button>
            ))}
          </div>
        )}
        {pickerOpen && (
          <div className="reaction-picker">
            {REACTION_OPTIONS.map((r) => (
              <button key={r} type="button" className={summary.some((g) => g.reaction === r && g.reactors.includes(selfNick)) ? 'reaction-chip reaction-chip-mine' : 'reaction-chip'} onClick={() => onToggleReaction(item, r)}>
                {r}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function TaskRow({ item }: { item: ChatItem }) {
  const status = item.taskStatus ?? 'running';
  const label =
    status === 'running' ? '开始处理' : status === 'done' ? '处理完成' : '处理失败';
  return (
    <div className="task" data-key={item.key} data-taskid={item.taskId ?? ''}>
      <span className="task-sender">{item.sender}</span>
      <span className="task-text">
        {label}
        {item.taskId ? ` · ${item.taskId}` : ''}
      </span>
      <span className="task-time">{formatTime(item.ts)}</span>
    </div>
  );
}

function renderText(text: string, mentions: string[]): React.ReactNode {
  if (!text) return null;
  if (mentions.length === 0) return text;
  const tokens = text.split(/(@[^\s@]+)/g);
  return tokens.map((tok, i) => {
    const m = tok.match(/^@(.+)$/);
    if (m && mentions.includes(m[1])) {
      return (
        <span key={i} className="mention">
          {tok}
        </span>
      );
    }
    return <span key={i}>{tok}</span>;
  });
}

function formatTime(ts: number): string {
  const d = new Date(ts);
  const hh = String(d.getHours()).padStart(2, '0');
  const mm = String(d.getMinutes()).padStart(2, '0');
  return `${hh}:${mm}`;
}

function cssEscape(s: string): string {
  return s.replace(/["\\]/g, '\\$&');
}
