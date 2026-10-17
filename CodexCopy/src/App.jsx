import { useState, useRef, useEffect, useCallback } from 'react';
import Sidebar from './components/Sidebar';
import ThreadView from './components/thread/ThreadView';
import Composer from './components/composer/Composer';
import SettingsView from './components/settings/SettingsView';
import SchedulesView from './components/schedules/SchedulesView';
import CommandPalette from './components/palette/CommandPalette';
import { CodexLogo } from './components/icons';
import { threads as seedThreads, suggestions, models } from './data/mock';

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
  {
    thinking: '这个改动涉及样式系统，先确认设计 token。',
    tools: [{ name: 'read', target: 'src/styles/tokens.css', status: 'ok', output: '→ 读取 120 行\n  - 找到 --bg-* / --text-* 变量' }],
    text: '设计 token 找到了。给你看下改动预览：',
    diff: {
      file: 'src/styles/tokens.css',
      hunks: [
        { head: '@@ -12,7 +12,9 @@ :root {', lines: [
          { t: ' ', c: '  --bg-main: #212121;' },
          { t: '-', c: '  --bg-sidebar: #171717;' },
          { t: '+', c: '  --bg-sidebar: #1a1a1a;' },
          { t: '+', c: '  --theme: dark;' },
          { t: ' ', c: '  --text-primary: #ececec;' },
        ]},
      ],
    },
  },
];

let replyIdx = 0;

export default function App() {
  const [view, setView] = useState('thread'); // thread | settings | schedules
  const [threads, setThreads] = useState(seedThreads);
  const [activeId, setActiveId] = useState('t1');
  const [streaming, setStreaming] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const scrollRef = useRef(null);

  const active = threads.find((t) => t.id === activeId);

  // Cmd+K / Ctrl+K 打开命令面板
  useEffect(() => {
    const h = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); setPaletteOpen((v) => !v); }
    };
    window.addEventListener('keydown', h);
    return () => window.removeEventListener('keydown', h);
  }, []);

  const goThread = (id) => { setActiveId(id); setView('thread'); };

  const newThread = () => {
    const id = 't' + Date.now();
    setThreads((ts) => [{ id, title: 'New thread', group: '今天', model: models[0], status: 'idle', messages: [] }, ...ts]);
    setActiveId(id);
    setView('thread');
  };

  const send = (text) => {
    const reply = FAKE_REPLIES[replyIdx++ % FAKE_REPLIES.length];
    setThreads((ts) =>
      ts.map((t) => (t.id === activeId
        ? { ...t, title: t.messages.length === 0 ? text.slice(0, 28) : t.title, status: 'working', messages: [...t.messages, { role: 'user', text }] }
        : t)));
    setStreaming(true);
    setTimeout(() => {
      setThreads((ts) =>
        ts.map((t) => (t.id === activeId
          ? { ...t, status: 'done', messages: [...t.messages, { role: 'agent', ...reply }] }
          : t)));
      setStreaming(false);
    }, 2600);
  };

  const paletteAction = useCallback((id) => {
    if (id === 'new') newThread();
    if (id === 'settings') setView('settings');
    if (id === 'schedules') setView('schedules');
    if (id === 'search') document.getElementById('thread-filter')?.focus();
    if (id === 'compact' && active) alert('Compact: 总结当前 thread 上下文（演示版未实现）');
    if (id === 'rename' && active) {
      const name = prompt('Rename thread', active.title);
      if (name) setThreads((ts) => ts.map((t) => (t.id === activeId ? { ...t, title: name } : t)));
    }
  }, [active, activeId]);

  useEffect(() => {
    const el = scrollRef.current?.querySelector('.thread-scroll');
    if (el) el.scrollTop = el.scrollHeight;
  }, [activeId, threads, streaming, view]);

  return (
    <div className="app" ref={scrollRef}>
      {/* 桌面窗口 chrome（macOS 风格） */}
      <div className="window-chrome">
        <div className="traffic-lights">
          <span className="tl close" /><span className="tl min" /><span className="tl max" />
        </div>
        <div className="chrome-title">CodexCopy — Codex 桌面端复刻</div>
      </div>
      <div className="app-body">
        <Sidebar
          threads={threads} activeId={view === 'thread' ? activeId : null}
          onSelect={goThread} onNew={newThread}
          onOpenSettings={() => setView('settings')}
          onOpenSchedules={() => setView('schedules')}
          currentView={view}
        />
        <div className="main">
          {view === 'settings' ? (
            <SettingsView onClose={() => setView('thread')} />
          ) : view === 'schedules' ? (
            <>
              <div className="topbar">
                <div className="topbar-title">Automations</div>
              </div>
              <SchedulesView />
            </>
          ) : (
            <>
              <div className="topbar">
                <div className="topbar-title">{active ? active.title : 'Codex'}</div>
                {active && <div className="model-badge"><span className="dot" />{active.model}</div>}
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
            </>
          )}
        </div>
      </div>
      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} onAction={paletteAction} />
    </div>
  );
}
