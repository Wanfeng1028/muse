import { useState } from 'react';
import {
  PlusIcon, SearchIcon, SettingsIcon, ClockIcon, ChevronDown, CheckIcon,
  CodexLogo, PlugIcon, GitIcon, ChatIcon, SidebarIcon, BackIcon, ForwardIcon, TrashIcon,
} from './icons';

// 真实 Codex 侧栏（依据 2026-07 真机截图）：
// 顶部：红绿灯 + 侧栏开关 + 前进后退
// 模式下拉：ChatGPT（Create, learn, and explore）/ Codex（Build, debug, and ship）
// 导航：New task / Scheduled / Plugins / Pull requests / Chat
// 下方：Projects 分组
export default function Sidebar({
  mode, onModeChange, nav, onNav,
  projects, activeProjectId, onSelectProject,
  onNewTask, onOpenSettings,
}) {
  const [modeOpen, setModeOpen] = useState(false);

  const NAV = [
    { id: 'new', label: 'New task', icon: <PlusIcon size={16} /> },
    { id: 'scheduled', label: 'Scheduled', icon: <ClockIcon size={16} /> },
    { id: 'plugins', label: 'Plugins', icon: <PlugIcon size={16} /> },
    { id: 'prs', label: 'Pull requests', icon: <GitIcon size={16} /> },
    { id: 'chat', label: 'Chat', icon: <ChatIcon size={16} /> },
  ];

  return (
    <aside className="sidebar-real">
      <div className="sr-top">
        <div className="traffic-lights sm">
          <span className="tl close" /><span className="tl min" /><span className="tl max" />
        </div>
        <button className="sr-icon-btn" title="Toggle sidebar"><SidebarIcon /></button>
        <button className="sr-icon-btn" title="Back"><BackIcon /></button>
        <button className="sr-icon-btn" title="Forward"><ForwardIcon /></button>
      </div>

      <div className="sr-mode-row">
        <div style={{ position: 'relative', flex: 1 }}>
          <button className="sr-mode-btn" onClick={() => setModeOpen(!modeOpen)}>
            <span className="sr-mode-name">{mode === 'codex' ? 'Codex' : 'ChatGPT'}</span>
            <ChevronDown size={14} />
          </button>
          {modeOpen && (
            <>
              <div className="drop-mask" onClick={() => setModeOpen(false)} />
              <div className="drop-menu sr-mode-menu">
                {[
                  { id: 'chatgpt', name: 'ChatGPT', desc: 'Create, learn, and explore' },
                  { id: 'codex', name: 'Codex', desc: 'Build, debug, and ship' },
                ].map((m) => (
                  <div key={m.id} className="drop-item sr-mode-item"
                    onClick={() => { onModeChange(m.id); setModeOpen(false); }}>
                    <span style={{ flex: 1 }}>
                      <div className="sr-mode-item-name">{m.name}</div>
                      <div className="sr-mode-item-desc">{m.desc}</div>
                    </span>
                    {mode === m.id && <CheckIcon size={14} />}
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
        <button className="sr-icon-btn" title="Search"><SearchIcon size={16} /></button>
      </div>

      <nav className="sr-nav">
        {NAV.map((n) => (
          <button key={n.id}
            className={'sr-nav-item' + (nav === n.id ? ' active' : '')}
            onClick={() => onNav(n.id)}>
            <span className="sr-nav-icon">{n.icon}</span>
            <span>{n.label}</span>
          </button>
        ))}
      </nav>

      <div className="sr-section">Projects</div>
      <div className="sr-projects">
        {(projects || []).map((p) => (
          <button key={p.id}
            className={'sr-nav-item' + (p.id === activeProjectId ? ' active' : '')}
            onClick={() => onSelectProject(p.id)}>
            <span className="sr-proj-dot" />
            <span className="sr-proj-name">{p.name}</span>
          </button>
        ))}
      </div>

      <div className="sr-bottom">
        <button className="sr-icon-btn" title="Settings" onClick={onOpenSettings}>
          <SettingsIcon size={16} />
        </button>
      </div>
    </aside>
  );
}
