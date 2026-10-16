import { KeyboardEvent, useEffect, useMemo, useRef, useState } from 'react';
import { Send, Bot, User } from 'lucide-react';
import { MemberEntry } from './Members';

interface Props {
  members: MemberEntry[];
  onSend: (text: string, mentions: string[]) => void;
}

interface MentionState {
  active: boolean;
  start: number; // @ 在 text 中的下标
  query: string;
  cursor: number;
}

const EMPTY: MentionState = { active: false, start: -1, query: '', cursor: 0 };

export default function Composer({ members, onSend }: Props) {
  const [text, setText] = useState('');
  const [mention, setMention] = useState<MentionState>(EMPTY);
  const [highlight, setHighlight] = useState(0);
  const taRef = useRef<HTMLTextAreaElement>(null);

  const candidates = useMemo(() => {
    if (!mention.active) return [];
    const q = mention.query.toLowerCase();
    return members
      .filter((m) => m.status === 'online')
      .filter((m) => (q ? m.adapter_id.toLowerCase().includes(q) : true))
      .slice(0, 8);
  }, [members, mention]);

  useEffect(() => {
    setHighlight(0);
  }, [mention.query, mention.active]);

  const updateMentionState = (value: string, caret: number) => {
    const upto = value.slice(0, caret);
    const at = upto.lastIndexOf('@');
    if (at === -1) {
      setMention(EMPTY);
      return;
    }
    const between = upto.slice(at + 1);
    if (/[\s@]/.test(between)) {
      setMention(EMPTY);
      return;
    }
    setMention({ active: true, start: at, query: between, cursor: caret });
  };

  const onChange = (v: string, caret: number) => {
    setText(v);
    updateMentionState(v, caret);
  };

  const insertMention = (name: string) => {
    const ta = taRef.current;
    if (!ta) return;
    const caret = ta.selectionStart ?? text.length;
    const before = text.slice(0, mention.start);
    const after = text.slice(caret);
    const inserted = `@${name} `;
    const next = before + inserted + after;
    setText(next);
    setMention(EMPTY);
    requestAnimationFrame(() => {
      const pos = before.length + inserted.length;
      ta.focus();
      ta.setSelectionRange(pos, pos);
    });
  };

  const submit = () => {
    const trimmed = text.trim();
    if (!trimmed) return;
    const mentions = parseMentions(trimmed, members);
    onSend(trimmed, mentions);
    setText('');
    setMention(EMPTY);
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (mention.active && candidates.length > 0) {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setHighlight((h) => (h + 1) % candidates.length);
        return;
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault();
        setHighlight((h) => (h - 1 + candidates.length) % candidates.length);
        return;
      }
      if (e.key === 'Enter' || e.key === 'Tab') {
        e.preventDefault();
        insertMention(candidates[highlight].adapter_id);
        return;
      }
      if (e.key === 'Escape') {
        e.preventDefault();
        setMention(EMPTY);
        return;
      }
    }
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  return (
    <div className="composer">
      {mention.active && candidates.length > 0 && (
        <div className="mention-pop" role="listbox">
          {candidates.map((c, i) => (
            <button
              key={c.adapter_id}
              type="button"
              role="option"
              aria-selected={i === highlight}
              className={`mention-item ${i === highlight ? 'is-active' : ''}`}
              onMouseDown={(e) => {
                e.preventDefault();
                insertMention(c.adapter_id);
              }}
            >
              <span className="mention-item-icon">
                {c.isSelf ? <User size={14} strokeWidth={2} /> : <Bot size={14} strokeWidth={2} />}
              </span>
              <span className="mention-item-name">{c.adapter_id}</span>
            </button>
          ))}
        </div>
      )}
      <div className="composer-row">
        <textarea
          ref={taRef}
          className="composer-input"
          rows={1}
          placeholder="说点什么，@ 可以叫某个成员"
          value={text}
          onChange={(e) => onChange(e.target.value, e.target.selectionStart ?? e.target.value.length)}
          onKeyDown={onKeyDown}
          onKeyUp={(e) => updateMentionState(e.currentTarget.value, e.currentTarget.selectionStart ?? 0)}
          onClick={(e) => updateMentionState(e.currentTarget.value, e.currentTarget.selectionStart ?? 0)}
        />
        <button className="btn-primary" type="button" onClick={submit} disabled={!text.trim()}>
          <Send size={16} strokeWidth={2} />
          <span>发送</span>
        </button>
      </div>
    </div>
  );
}

function parseMentions(text: string, members: MemberEntry[]): string[] {
  const names = new Set(members.map((m) => m.adapter_id));
  const out: string[] = [];
  const re = /@([^\s@]+)/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    const name = m[1];
    if (names.has(name) && !out.includes(name)) out.push(name);
  }
  return out;
}
