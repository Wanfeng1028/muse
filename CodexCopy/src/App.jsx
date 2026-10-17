import { useState, useRef, useEffect, useCallback } from 'react';
import Sidebar from './components/Sidebar';
import ThreadView from './components/thread/ThreadView';
import Composer from './components/composer/Composer';
import SettingsView from './components/settings/SettingsView';
import SchedulesView from './components/schedules/SchedulesView';
import CommandPalette from './components/palette/CommandPalette';
import { CodexLogo } from './components/icons';
import { projects as seedProjects, suggestions, models } from './data/mock';

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
  const [view, setView] = useState('thread');
  const [theme, setTheme] = useState('dark');
  const [projects, setProjects] = useState(seedProjects);
  const [activeProjectId, setActiveProjectId] = useState('p1');
  const [activeChatId, setActiveChatId] = useState('t1');
  const [streaming, setStreaming] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const scrollRef = useRef(null);

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
  }, [theme]);

  const activeProject = projects.find((p) => p.id === activeProjectId);
  const activeChat = activeProject?.chats.find((c) => c.id === activeChatId);

  useEffect(() => {
    const h = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); setPaletteOpen((v) => !v); }
    };
    window.addEventListener('keydown', h);
    return () => window.removeEventListener('keydown', h);
  }, []);

  const selectChat = (pid, cid) => {
    setActiveProjectId(pid);
    setActiveChatId(cid);
    setView('thread');
  };

  const newChat = () => {
    const id = 't' + Date.now();
    const chat = { id, title: 'New chat', updated: '今天', model: models[0], status: 'idle', messages: [] };
    setProjects((ps) => ps.map((p) => (p.id === activeProjectId ? { ...p, chats: [chat, ...p.chats] } : p)));
    setActiveChatId(id);
    setView('thread');
  };

  const send = (text) => {
    const reply = FAKE_REPLIES[replyIdx++ % FAKE_REPLIES.length];
    const update = (ps) => ps.map((p) => (p.id === activeProjectId ? {
      ...p,
      chats: p.chats.map((c) => (c.id === activeChatId
        ? { ...c, title: c.messages.length === 0 ? text.slice(0, 32) : c.title, status: 'working', messages: [...c.messages, { role: 'user', text }] }
        : c)),
    } : p));
    setProjects(update);
    setStreaming(true);
    setTimeout(() => {
      setProjects((ps) => ps.map((p) => (p.id === activeProjectId ? {
        ...p,
        chats: p.chats.map((c) => (c.id === activeChatId
          ? { ...c, status: 'done', messages: [...c.messages, { role: 'agent', ...reply }] }
          : c)),
      } : p)));
      setStreaming(false);
    }, 2600);
  };

  const paletteAction = useCallback((id) => {
    if (id === 'new') newChat();
    if (id === 'settings') setView('settings');
    if (id === 'schedules') setView('schedules');
    if (id === 'search') document.getElementById('thread-filter')?.focus();
  }, [activeProjectId]);

  useEffect(() => {
    const el = scrollRef.current?.querySelector('.thread-scroll');
    if (el) el.scrollTop = el.scrollHeight;
  }, [activeChatId, projects, streaming, view]);

  // 真实占位文案（逆向）："Ask Codex anything locally in {project}"
  const placeholder = activeProject ? `Ask Codex anything locally in ${activeProject.name}` : 'Ask Codex anything locally';

  return (
    <div className="app" ref={scrollRef}>
      <div className="window-chrome">
        <div className="traffic-lights">
          <span className="tl close" /><span className="tl min" /><span className="tl max" />
        </div>
        <div className="chrome-title">CodexCopy — Codex 桌面端复刻</div>
      </div>
      <div className="app-body">
        <Sidebar
          projects={projects}
          activeChatId={view === 'thread' ? activeChatId : null}
          activeProjectId={activeProjectId}
          onSelectChat={selectChat}
          onNewChat={newChat}
          onOpenSettings={() => setView('settings')}
          onOpenSchedules={() => setView('schedules')}
          currentView={view}
        />
        <div className="main">
          {view === 'settings' ? (
            <SettingsView onClose={() => setView('thread')} theme={theme} onThemeChange={setTheme} />
          ) : view === 'schedules' ? (
            <>
              <div className="topbar"><div className="topbar-title">Automations</div></div>
              <SchedulesView />
            </>
          ) : (
            <>
              <div className="topbar">
                <div className="topbar-title">{activeChat ? activeChat.title : 'Codex'}</div>
                {activeProject && <div className="project-badge">{activeProject.name} · {activeProject.branch}</div>}
                {activeChat && <div className="model-badge"><span className="dot" />{activeChat.model}</div>}
              </div>
              {activeChat && activeChat.messages.length > 0 ? (
                <ThreadView thread={activeChat} streaming={streaming} />
              ) : (
                <div className="empty-state">
                  <div className="empty-logo"><CodexLogo size={52} /></div>
                  <div className="empty-title">Welcome to Codex</div>
                  <div className="empty-sub">The best way to build with agents</div>
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
              <Composer onSend={send} disabled={streaming} placeholder={placeholder} />
            </>
          )}
        </div>
      </div>
      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} onAction={paletteAction} />
    </div>
  );
}
