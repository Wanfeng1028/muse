import { useState, useRef, useEffect, useCallback } from 'react';
import TopToolbar from './components/TopToolbar';
import TaskList from './components/TaskList';
import ThreadView from './components/thread/ThreadView';
import Composer from './components/composer/Composer';
import RightPanel from './components/RightPanel';
import SettingsView from './components/settings/SettingsView';
import SchedulesView from './components/schedules/SchedulesView';
import CommandPalette from './components/palette/CommandPalette';
import { CodexLogo } from './components/icons';
import { projects as seedProjects, tasks as seedTasks, models } from './data/mock';

// 三栏布局（依据 Codex App Interface Guide）：
// 左=任务列表 | 中=会话窗口 | 右=多功能区（文件/终端/代码/上下文）
export default function App() {
  const [view, setView] = useState('main'); // main | settings | schedules
  const [theme, setTheme] = useState('dark');
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
    setView('main');
  };

  const deleteTask = (id) => {
    setTasks((ts) => {
      const rest = ts.filter((t) => t.id !== id);
      if (id === activeTaskId && rest.length > 0) setActiveTaskId(rest[0].id);
      return rest;
    });
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
              role: 'agent',
              thinking: '收到，开始处理。',
              text: '已按你的要求处理，需要确认：',
              needsApproval: true,
              approval: { title: 'Apply changes', desc: 'Codex 将修改 2 个文件' },
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

  return (
    <div className="app" ref={scrollRef}>
      <div className="window-chrome">
        <div className="traffic-lights">
          <span className="tl close" /><span className="tl min" /><span className="tl max" />
        </div>
        <div className="chrome-title">CodexCopy — Codex 桌面端复刻</div>
      </div>

      {view === 'main' && (
        <TopToolbar
          projects={projects} activeProjectId={activeProjectId} onProjectChange={setActiveProjectId}
          model={model} onModelChange={setModel}
          sandbox={sandbox} onSandboxChange={setSandbox}
          onOpenSettings={() => setView('settings')}
        />
      )}

      <div className="app-body">
        {view === 'settings' ? (
          <SettingsView onClose={() => setView('main')} theme={theme} onThemeChange={setTheme} />
        ) : view === 'schedules' ? (
          <div className="main" style={{ flex: 1 }}>
            <div className="topbar"><div className="topbar-title">Automations</div></div>
            <SchedulesView />
          </div>
        ) : (
          <>
            <TaskList tasks={projectTasks} activeId={activeTaskId}
              onSelect={setActiveTaskId} onNew={newTask} onDelete={deleteTask} />
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
        )}
      </div>
      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} onAction={paletteAction} />
    </div>
  );
}
