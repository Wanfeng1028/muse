import { useEffect, useLayoutEffect, useRef } from 'react';
import { Bot, Loader2, User } from 'lucide-react';

export interface ChatItem {
  key: string;
  msgId: string;
  sender: string;
  seq: number;
  ts: number;
  text: string;
  mentions: string[];
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
}

const TOP_THRESHOLD = 48;

export default function MessageList({
  items,
  selfNick,
  onTopReached,
  loadingOlder,
  hasMore,
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
        items.map((item) =>
          item.kind === 'task' ? (
            <TaskRow key={item.key} item={item} />
          ) : (
            <MessageRow key={item.key} item={item} selfNick={selfNick} />
          ),
        )
      )}
      <div ref={bottomRef} />
    </div>
  );
}

function MessageRow({ item, selfNick }: { item: ChatItem; selfNick: string }) {
  const isSelf = item.sender === selfNick;
  const mentionsMe = item.mentions.includes(selfNick);
  const highlightClass = [
    'msg',
    isSelf ? 'msg-self' : '',
    mentionsMe ? 'msg-mentioned' : '',
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <div className={highlightClass} data-key={item.key}>
      <div className="msg-avatar" aria-hidden="true">
        {isSelf ? <User size={16} strokeWidth={2} /> : <Bot size={16} strokeWidth={2} />}
      </div>
      <div className="msg-body">
        <div className="msg-head">
          <span className="msg-sender">{item.sender}</span>
          <span className="msg-time">{formatTime(item.ts)}</span>
        </div>
        <div className="msg-text">{renderText(item.text, item.mentions)}</div>
      </div>
    </div>
  );
}

function TaskRow({ item }: { item: ChatItem }) {
  const status = item.taskStatus ?? 'running';
  const label =
    status === 'running' ? '开始处理' : status === 'done' ? '处理完成' : '处理失败';
  return (
    <div className="task" data-key={item.key}>
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
