import { useState, useRef, useEffect, useCallback } from 'react';
import Sidebar, { MODE_STYLE } from './components/Sidebar';
import TopToolbar from './components/TopToolbar';
import ThreadView from './components/thread/ThreadView';
import Composer from './components/composer/Composer';
import RightPanel from './components/RightPanel';
import SettingsView from './components/settings/SettingsView';
import SchedulesView from './components/schedules/SchedulesView';
import CommandPalette from './components/palette/CommandPalette';
import { CodexLogo, GitIcon } from './components/icons';
import { projects as seedProjects, models } from './data/mock';

// 真实 Codex 结构：侧栏 = 模式切换 + 导航 + Projects（项目→线程，线程标模式）
// 主区 = 会话（新建线程时选 Local/Worktree/Cloud）
export default function App() {
  const [view, setView] = useState('main');
  const [theme, setTheme] = useState('dark');
  const [mode, setMode] = useState('codex');
  const [nav, setNav] = useState('threads');
  const [projects, setProjects] = useState(seedProjects);
  const [activeProjectId, setActiveProjectId] = useState('p1');
  const [activeThreadId, setActiveThreadId] = useState('t1');
  const [model, setModel] = useState('gpt-5.2');
  const [sandbox, setSandbox] = useState('Auto Edit');
  const [streaming, setStreaming] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const scrollRef = useRef(null);

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
  }, [theme]);

  const activeProject = projects.find((p) => p.id === activeProjectId);
  const activeThread = activeProject?.threads.find((t) => t.id === activeThreadId);

  useEffect(() => {
    const h = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); setPaletteOpen((v) => !v); }
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'n') { e.preventDefault(); newThread('local'); }
    };
    window.addEventListener('keydown', h);
    return () => window.removeEventListener('keydown', h);
  }, [activeProjectId]);

  const newThread = (modeId) => {
    const id = 't' + Date.now();
    const thread = {
      id, title: 'New thread', mode: modeId, branch: 'main',
      status: 'running', model, messages: [],
    };
    setProjects((ps) => ps.map((p) => (p.id === activeProjectId
      ? { ...p, threads: [thread, ...p.threads] } : p)));
    setActiveThreadId(id);
    setNav('threads');
    setView('main');
  };

  const handleNav = (id) => {
    if (id === 'scheduled') { setView('schedules'); return; }
    setNav(id);
    setView('main');
  };

  const send = (text) => {
    const upd = (ps) => ps.map((p) => (p.id === activeProjectId ? {
      ...p, threads: p.threads.map((t) => (t.id === activeThreadId
        ? { ...t, title: t.messages.length === 0 ? text.slice(0, 32) : t.title,
            messages: [...t.messages, { role: 'user', text }] }
        : t)),
    } : p));
    setProjects(upd);
    setStreaming(true);
    setTimeout(() => {
      setProjects((ps) => ps.map((p) => (p.id === activeProjectId ? {
        ...p, threads: p.threads.map((t) => (t.id === activeThreadId
          ? { ...t, messages: [...t.messages, {
              role: 'agent', thinking: '收到，开始处理。', text: '已按你的要求处理，需要确认：',
              needsApproval: true, approval: { title: 'Apply changes', desc: 'Codex 将修改 2 个文件' },
            }] }
          : t)),
      } : p)));
      setStreaming(false);
    }, 2200);
  };

  const paletteAction = useCallback((id) => {
    if (id === 'new') newThread('local');
    if (id === 'settings') setView('settings');
    if (id === 'schedules') setView('schedules');
  }, [activeProjectId]);

  useEffect(() => {
    const el = scrollRef.current?.querySelector('.thread-scroll');
    if (el) el.scrollTop = el.scrollHeight;
  }, [activeThreadId, projects, streaming, view]);

  const placeholder = activeProject ? `Ask Codex anything locally in ${activeProject.name}` : 'Ask Codex anything locally';
  const ms = activeThread ? (MODE_STYLE[activeThread.mode] || MODE_STYLE.local) : null;

  const renderMain = () => {
    if (nav === 'prs') {
      return (
        <div className="page-scroll"><div className="page-inner">
          <div className="page-head"><div><h1>Pull requests</h1><p className="page-desc">PRs created from Codex threads.</p></div></div>
          <div className="auto-card">
            <span className="tool-icon"><GitIcon /></span>
            <div className="auto-info">
              <div className="auto-name">#428 <span className="pill green">open</span></div>
              <div className="auto-desc">Add refresh token support · codex-copy</div>
            </div>
          </div>
        </div></div>
      );
    }
    if (nav === 'plugins') {
      return (
        <div className="page-scroll"><div className="page-inner">
          <div className="page-head"><div><h1>Plugins</h1><p className="page-desc">Extend Codex with plugins.</p></div></div>
          {['openai-bundled', 'chrome-remote'].map((p) => (
            <div className="model-card" key={p}>
              <div><div className="model-name">{p}</div><div className="model-desc">Enabled</div></div>
              <span className="pill green">on</span>
            </div>
          ))}
        </div></div>
      );
    }
    if (nav === 'chat') {
      return (
        <div className="page-scroll"><div className="page-inner">
          <div className="page-head"><div><h1>Chat</h1><p className="page-desc">Recent chats.</p></div></div>
          <div className="empty-note">Chat threads appear here.</div>
        </div></div>
      );
    }
    return (
      <div className="main" style={{ flex: 1 }}>
        <div className="topbar">
          <div className="topbar-title">{activeThread ? activeThread.title : 'Codex'}</div>
          {ms && <span className="mode-badge" style={{ borderColor: ms.color, color: ms.color }}>
            <span className="mode-dot" style={{ background: ms.color }} />{ms.label}
          </span>}
          {activeThread && <span className="task-branch">{activeThread.branch}</span>}
        </div>
        {activeThread && activeThread.messages.length > 0 ? (
          <ThreadView thread={activeThread} streaming={streaming} />
        ) : (
          <div className="empty-state">
            <div className="empty-logo"><CodexLogo size={52} /></div>
            <div className="empty-title">Welcome to Codex</div>
            <div className="empty-sub">The best way to build with agents</div>
          </div>
        )}
        <Composer onSend={send} disabled={streaming} placeholder={placeholder}
          model={model} onModelChange={setModel} />
      </div>
    );
  };

  return (
    <div className="app" ref={scrollRef}>
      <div className="app-body">
        <Sidebar
          mode={mode} onModeChange={setMode}
          nav={view === 'main' ? nav : ''}
          onNav={handleNav}
          projects={projects} activeProjectId={activeProjectId} activeThreadId={activeThreadId}
          onSelectThread={(pid, tid) => { setActiveProjectId(pid); setActiveThreadId(tid); setNav('threads'); setView('main'); }}
          onNewTask={newThread}
          onOpenSettings={() => setView('settings')}
        />
        {view === 'settings' ? (
          <SettingsView onClose={() => setView('main')} theme={theme} onThemeChange={setTheme} />
        ) : view === 'schedules' ? (
          <div className="main" style={{ flex: 1 }}>
            <div className="topbar">
              <div className="topbar-title">Scheduled</div>
              <button className="btn-ghost" onClick={() => setView('main')}>← Back</button>
            </div>
            <SchedulesView />
          </div>
        ) : (
          <div className="codex-toolbar-wrap">
            {mode === 'codex' && (
              <TopToolbar
                projects={projects.map((p) => ({ id: p.id, name: p.name }))}
                activeProjectId={activeProjectId} onProjectChange={setActiveProjectId}
                model={model} onModelChange={setModel}
                sandbox={sandbox} onSandboxChange={setSandbox}
                onOpenSettings={() => setView('settings')}
              />
            )}
            <div className="main-row">{renderMain()}</div>
          </div>
        )}
      </div>
      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} onAction={paletteAction} />
    </div>
  );
}
