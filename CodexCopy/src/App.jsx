import { useState, useRef, useEffect } from 'react';
import Sidebar from './components/Sidebar';
import ThreadView from './components/ThreadView';
import Composer from './components/Composer';
import { CodexLogo } from './components/icons';
import { threads as seedThreads, suggestions, models } from './data/mock';

// 模拟 agent 回复：打字机式流式输出
const FAKE_REPLIES = [
  {
    thinking: '收到。我先看一下相关代码，确认改动范围。',
    tools: [{ name: 'read', target: 'src/', status: 'ok', output: '→ 扫描 24 个文件\n  - 找到 3 处相关逻辑' }],
    text: '看明白了。这个需求分两步做：\n\n1. 先补数据结构和接口\n2. 再接 UI 交互\n\n我先从第一步开始改。',
  },
  {
    thinking: '改动点已经明确，动手实现。',
    tools: [
      { name: 'edit', target: 'src/main.ts', status: 'ok', output: '+ export function handleRequest(req) {\n+   validate(req);\n+   return process(req);\n+ }' },
      { name: 'bash', target: 'npm test', status: 'ok', output: '✓ 12 passed\n✓ 0 failed' },
    ],
    text: '改好了，测试全过。你看下 diff，没问题我就收尾。',
  },
];

let replyIdx = 0;

export default function App() {
  const [threads, setThreads] = useState(seedThreads);
  const [activeId, setActiveId] = useState('t1');
  const [streaming, setStreaming] = useState(false);
  const scrollRef = useRef(null);

  const active = threads.find((t) => t.id === activeId);

  const newThread = () => {
    const id = 't' + Date.now();
    const t = { id, title: 'New thread', group: '今天', model: models[0], status: 'idle', messages: [] };
    setThreads([t, ...threads]);
    setActiveId(id);
  };

  const send = (text) => {
    const reply = FAKE_REPLIES[replyIdx++ % FAKE_REPLIES.length];
    setThreads((ts) =>
      ts.map((t) =>
        t.id === activeId
          ? {
              ...t,
              title: t.messages.length === 0 ? text.slice(0, 28) : t.title,
              status: 'working',
              messages: [...t.messages, { role: 'user', text }],
            }
          : t
      )
    );
    setStreaming(true);
    // 模拟思考 + 回复延迟
    setTimeout(() => {
      setThreads((ts) =>
        ts.map((t) =>
          t.id === activeId
            ? { ...t, status: 'done', messages: [...t.messages, { role: 'agent', ...reply }] }
            : t
        )
      );
      setStreaming(false);
    }, 2600);
  };

  useEffect(() => {
    const el = scrollRef.current?.querySelector('.thread-scroll');
    if (el) el.scrollTop = el.scrollHeight;
  }, [activeId, threads, streaming]);

  return (
    <div className="app" ref={scrollRef}>
      <Sidebar threads={threads} activeId={activeId} onSelect={setActiveId} onNew={newThread} />
      <div className="main">
        <div className="topbar">
          <div className="topbar-title">{active ? active.title : 'Codex'}</div>
          {active && (
            <div className="model-badge">
              <span className="dot" />
              {active.model}
            </div>
          )}
        </div>

        {active && active.messages.length > 0 ? (
          <ThreadView thread={active} streaming={streaming} />
        ) : (
          <div className="empty-state">
            <div className="empty-logo"><CodexLogo size={52} /></div>
            <div className="empty-title">What should we build?</div>
            <div className="empty-sub">CodexCopy — Codex 桌面端 UI 复刻（演示版）</div>
            <div className="suggestion-grid">
              {suggestions.map((s, i) => (
                <button key={i} className="suggestion" onClick={() => send(s.title + '：' + s.desc)}>
                  <div className="s-title">{s.title}</div>
                  <div className="s-desc">{s.desc}</div>
                </button>
              ))}
            </div>
          </div>
        )}

        <Composer onSend={send} disabled={streaming} />
      </div>
    </div>
  );
}
