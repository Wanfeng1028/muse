import { useState, useRef, useEffect, useCallback } from 'react';
import Sidebar from './components/Sidebar';
import ThreadView from './components/thread/ThreadView';
import Composer from './components/composer/Composer';
import RightPanel from './components/RightPanel';
import SettingsView from './components/settings/SettingsView';
import SchedulesView from './components/schedules/SchedulesView';
import CommandPalette from './components/palette/CommandPalette';
import { CodexLogo, GitIcon, MoreIcon, PanelIcon, CloudIcon } from './components/icons';
import { projects as seedProjects, models } from './data/mock';

// 真实 Codex 布局（六份实证报告）：
// - 两栏：左=侧栏（导航+Projects+线程树），右=会话区
// - 无顶栏（Project/Sandbox下拉是错的，已删）
// - 右侧面板按需从右上角菜单打开：Review / Terminal / Browser / Files
// - 线程头部：标题 + "..." 菜单；分支/模式信息在输入框下方
export default function App() {
  const [view, setView] = useState('main');
  const [theme, setTheme] = useState('dark');
  const [mode, setMode] = useState('codex');
  const [nav, setNav] = useState('threads');
  const [projects, setProjects] = useState(seedProjects);
  const [activeProjectId, setActiveProjectId] = useState('p1');
  const [activeThreadId, setActiveThreadId] = useState('t1');
  const [model, setModel] = useState('gpt-5.2');
  const [streaming, setStreaming] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [rightPanel, setRightPanel] = useState(null); // null | review | terminal | browser | files
  const [panelMenuOpen, setPanelMenuOpen] = useState(false);
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
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'j') { e.preventDefault(); setRightPanel((p) => (p === 'terminal' ? null : 'terminal')); }
    };
    window.addEventListener('keydown', h);
    return () => window.removeEventListener('keydown', h);
  }, [activeProjectId]);

  const newThread = (modeId) => {
    const id = 't' + Date.now();
    const thread = { id, title: 'Untitled chat', mode: modeId, branch: 'main', status: 'idle', model, messages: [] };
    setProjects((ps) => ps.map((p) => (p.id === activeProjectId ? { ...p, threads: [thread, ...p.threads] } : p)));
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
    setProjects((ps) => ps.map((p) => (p.id === activeProjectId ? {
      ...p, threads: p.threads.map((t) => (t.id === activeThreadId
        ? { ...t, title: t.messages.length === 0 ? text.slice(0, 32) : t.title, status: 'active',
            messages: [...t.messages, { role: 'user', text }] }
        : t)),
    } : p)));
    setStreaming(true);
    setTimeout(() => {
      setProjects((ps) => ps.map((p) => (p.id === activeProjectId ? {
        ...p, threads: p.threads.map((t) => (t.id === activeThreadId
          ? { ...t, status: 'awaiting',
              messages: [...t.messages, {
                role: 'agent', thinking: 'Thinking…', text: '已按你的要求处理，需要确认：',
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

  const PANELS = [
    { id: 'review', label: 'Review', key: '⌃⇧G' },
    { id: 'terminal', label: 'Terminal', key: '⌃`' },
    { id: 'browser', label: 'Browser', key: '⌘T' },
    { id: 'files', label: 'Files', key: '⌘P' },
  ];

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
          <span style={{ flex: 1 }} />
          {/* diff 计数按钮（真实：绿/红数字） */}
          <button className="diff-count-btn" title="Toggle diff panel" onClick={() => setRightPanel(rightPanel === 'review' ? null : 'review')}>
            <span className="diff-add">+12</span><span className="diff-del">−3</span>
          </button>
          {/* 面板菜单 */}
          <div style={{ position: 'relative' }}>
            <button className="icon-btn sm" title="Panels" onClick={() => setPanelMenuOpen(!panelMenuOpen)}>
              <PanelIcon size={15} />
            </button>
            {panelMenuOpen && (
              <>
                <div className="drop-mask" onClick={() => setPanelMenuOpen(false)} />
                <div className="drop-menu" style={{ right: 0, left: 'auto', minWidth: 190 }}>
                  {PANELS.map((p) => (
                    <div key={p.id} className="drop-item" onClick={() => { setRightPanel(rightPanel === p.id ? null : p.id); setPanelMenuOpen(false); }}>
                      <span style={{ flex: 1 }}>{p.label}</span>
                      <kbd className="kbd-sm">{p.key}</kbd>
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>
          <button className="icon-btn sm" title="Thread options"><MoreIcon size={15} /></button>
        </div>
        {activeThread && activeThread.messages.length > 0 ? (
          <ThreadView thread={activeThread} streaming={streaming} />
        ) : (
          <div className="empty-state">
            <div className="empty-cloud"><CloudIcon size={44} /></div>
            <div className="empty-title-lg">What should we build in <u>{activeProject?.name}</u>?</div>
          </div>
        )}
        <Composer onSend={send} streaming={streaming} onStop={() => setStreaming(false)}
          placeholder={placeholder} model={model} onModelChange={setModel}
          threadMode={activeThread?.mode} branch={activeThread?.branch}
          projectName={activeProject?.name} />
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
          <>
            <div className="main-row" style={{ flex: 1 }}>{renderMain()}</div>
            {rightPanel && <RightPanel panel={rightPanel} task={activeThread} onClose={() => setRightPanel(null)} />}
          </>
        )}
      </div>
      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} onAction={paletteAction} />
    </div>
  );
}
