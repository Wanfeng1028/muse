import { useState, useRef, useEffect, useCallback } from 'react';
import Sidebar from './components/Sidebar';
import TopToolbar from './components/TopToolbar';
import TaskList from './components/TaskList';
import ThreadView from './components/thread/ThreadView';
import Composer from './components/composer/Composer';
import RightPanel from './components/RightPanel';
import SettingsView from './components/settings/SettingsView';
import SchedulesView from './components/schedules/SchedulesView';
import CommandPalette from './components/palette/CommandPalette';
import { CodexLogo, GitIcon } from './components/icons';
import { projects as seedProjects, tasks as seedTasks, models } from './data/mock';

// 侧栏按真实截图：模式切换（ChatGPT/Codex）+ 导航（New task/Scheduled/Plugins/Pull requests/Chat）+ Projects
// 主区：三栏（任务列表 | 会话 | 多功能区）
export default function App() {
  const [view, setView] = useState('main');
  const [theme, setTheme] = useState('dark');
  const [mode, setMode] = useState('codex');
  const [nav, setNav] = useState('new');
  const [projects] = useState(seedProjects);
  const [tasks, setTasks] = useState(seedTasks);
  const [activeProjectId, setActiveProjectId] = useState('p1');
  const [activeTaskId, setActiveTaskId] = useState('t1');
  const [model, setModel] = useState('gpt-5.2');
  const [sandbox, setSandbox] = useState('Auto Edit');
  const [streaming, setStreaming] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const scrollRef = useRef(null);

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
  }, [theme]);

  const projectTasks = tasks.filter((t) => t.projectId === activeProjectId);
  const activeTask = tasks.find((t) => t.id === activeTaskId);
  const activeProject = projects.find((p) => p.id === activeProjectId);

  useEffect(() => {
    const h = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); setPaletteOpen((v) => !v); }
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'n') { e.preventDefault(); newTask(); }
    };
    window.addEventListener('keydown', h);
    return () => window.removeEventListener('keydown', h);
  }, [activeProjectId]);

  const newTask = () => {
    const id = 't' + Date.now();
    const task = {
      id, projectId: activeProjectId, title: 'New chat', status: 'running',
      model, sandbox, branch: 'main', worktree: 'local',
      files: [], terminal: [], messages: [],
    };
    setTasks((ts) => [task, ...ts]);
    setActiveTaskId(id);
    setNav('new');
    setView('main');
  };

  const handleNav = (id) => {
    if (id === 'new') { newTask(); return; }
    if (id === 'scheduled') { setView('schedules'); return; }
    setNav(id);
    setView('main');
  };

  const send = (text) => {
    setTasks((ts) => ts.map((t) => (t.id === activeTaskId
      ? { ...t, title: t.messages.length === 0 ? text.slice(0, 32) : t.title, status: 'running',
          messages: [...t.messages, { role: 'user', text }] }
      : t)));
    setStreaming(true);
    setTimeout(() => {
      setTasks((ts) => ts.map((t) => (t.id === activeTaskId
        ? { ...t, status: 'awaiting',
            messages: [...t.messages, {
              role: 'agent', thinking: '收到，开始处理。', text: '已按你的要求处理，需要确认：',
              needsApproval: true, approval: { title: 'Apply changes', desc: 'Codex 将修改 2 个文件' },
            }] }
        : t)));
      setStreaming(false);
    }, 2200);
  };

  const paletteAction = useCallback((id) => {
    if (id === 'new') newTask();
    if (id === 'settings') setView('settings');
    if (id === 'schedules') setView('schedules');
  }, [activeProjectId]);

  useEffect(() => {
    const el = scrollRef.current?.querySelector('.thread-scroll');
    if (el) el.scrollTop = el.scrollHeight;
  }, [activeTaskId, tasks, streaming, view]);

  const placeholder = activeProject ? `Ask Codex anything locally in ${activeProject.name}` : 'Ask Codex anything locally';

  const renderMain = () => {
    if (nav === 'prs') {
      return (
        <div className="page-scroll"><div className="page-inner">
          <div className="page-head"><div><h1>Pull requests</h1><p className="page-desc">PRs created from Codex tasks.</p></div></div>
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
          <div className="empty-note">Chat history lives in the Codex view.</div>
        </div></div>
      );
    }
    // default: task conversation (3-panel)
    return (
      <>
        <TaskList tasks={projectTasks} activeId={activeTaskId}
          onSelect={setActiveTaskId} onNew={newTask}
          onDelete={(id) => setTasks((ts) => ts.filter((t) => t.id !== id))} />
        <div className="main">
          <div className="topbar">
            <div className="topbar-title">{activeTask ? activeTask.title : 'Codex'}</div>
            {activeTask && <span className="task-branch">{activeTask.branch} · {activeTask.worktree}</span>}
          </div>
          {activeTask && activeTask.messages.length > 0 ? (
            <ThreadView thread={activeTask} streaming={streaming} />
          ) : (
            <div className="empty-state">
              <div className="empty-logo"><CodexLogo size={52} /></div>
              <div className="empty-title">Welcome to Codex</div>
              <div className="empty-sub">The best way to build with agents</div>
            </div>
          )}
          <Composer onSend={send} disabled={streaming} placeholder={placeholder} />
        </div>
        <RightPanel task={activeTask} />
      </>
    );
  };

  return (
    <div className="app" ref={scrollRef}>
      <div className="app-body">
        <Sidebar
          mode={mode} onModeChange={setMode}
          nav={view === 'main' ? nav : ''}
          onNav={handleNav}
          projects={projects} activeProjectId={activeProjectId}
          onSelectProject={(pid) => { setActiveProjectId(pid); setView('main'); setNav('new'); }}
          onNewTask={newTask}
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
                projects={projects} activeProjectId={activeProjectId} onProjectChange={setActiveProjectId}
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
