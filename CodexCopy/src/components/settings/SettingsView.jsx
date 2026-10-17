import { useState } from 'react';
import { XIcon } from '../icons';

// 真实设置分类（bundle settings.nav.* 实证，16 项，分 App / Host 两组）
const NAV = [
  { group: 'App' },
  { id: 'account', label: 'Account' },
  { id: 'appearance', label: 'Appearance' },
  { id: 'general', label: 'General' },
  { id: 'agent', label: 'Configuration' },
  { id: 'git', label: 'Git' },
  { id: 'archived', label: 'Archived chats' },
  { id: 'personalization', label: 'Personalization' },
  { id: 'usage', label: 'Usage' },
  { id: 'computer-use', label: 'Computer use' },
  { id: 'worktrees', label: 'Worktrees' },
  { group: 'Host' },
  { id: 'cloud-env', label: 'Cloud Environments' },
  { id: 'mcp', label: 'MCP servers' },
  { id: 'connections', label: 'Connections' },
  { id: 'plugins', label: 'Plugins' },
  { id: 'skills', label: 'Skills' },
];

export default function SettingsView({ onClose, theme, onThemeChange }) {
  const [page, setPage] = useState('appearance');

  return (
    <div className="settings-wrap">
      <div className="settings-nav">
        <div className="settings-nav-head">
          <span>Settings</span>
          <button className="icon-btn sm" onClick={onClose}><XIcon size={13} /></button>
        </div>
        {NAV.map((n, i) => n.group ? (
          <div key={i} className="sr-section">{n.group}</div>
        ) : (
          <button key={n.id} className={'sr-nav-item' + (page === n.id ? ' active' : '')}
            onClick={() => setPage(n.id)}>
            <span>{n.label}</span>
          </button>
        ))}
      </div>
      <div className="settings-main">
        {page === 'appearance' && <AppearancePage theme={theme} onThemeChange={onThemeChange} />}
        {page === 'agent' && <AgentPage />}
        {page === 'worktrees' && <WorktreesPage />}
        {page === 'mcp' && <McpPage />}
        {page !== 'appearance' && page !== 'agent' && page !== 'worktrees' && page !== 'mcp' && (
          <div className="page-scroll"><div className="page-inner">
            <div className="page-head"><div>
              <h1>{NAV.find((n) => n.id === page)?.label}</h1>
            </div></div>
            <div className="empty-note">Settings for {NAV.find((n) => n.id === page)?.label}.</div>
          </div></div>
        )}
      </div>
    </div>
  );
}

function AppearancePage({ theme, onThemeChange }) {
  return (
    <div className="page-scroll"><div className="page-inner">
      <div className="page-head"><div><h1>Appearance</h1></div></div>
      <div className="model-card">
        <div><div className="model-name">Theme</div><div className="model-desc">Base color theme</div></div>
        <div className="seg">
          {['dark', 'light'].map((t) => (
            <button key={t} className={'seg-btn' + (theme === t ? ' active' : '')}
              onClick={() => onThemeChange(t)}>{t === 'dark' ? 'Dark' : 'Light'}</button>
          ))}
        </div>
      </div>
      <div className="model-card">
        <div><div className="model-name">UI font</div><div className="model-desc">Interface typeface</div></div>
        <span className="model-desc">System</span>
      </div>
      <div className="model-card">
        <div><div className="model-name">Code font</div><div className="model-desc">Monospace typeface</div></div>
        <span className="model-desc">JetBrains Mono</span>
      </div>
    </div></div>
  );
}

function AgentPage() {
  const [approval, setApproval] = useState('on-request');
  return (
    <div className="page-scroll"><div className="page-inner">
      <div className="page-head"><div><h1>Configuration</h1><p className="page-desc">Agent approval and sandbox policy.</p></div></div>
      <div className="model-card">
        <div><div className="model-name">Approval policy</div><div className="model-desc">When Codex asks before acting</div></div>
      </div>
      {[['untrusted', 'Ask for approval'], ['on-request', 'Approve for me'], ['never', 'Full access']].map(([v, l]) => (
        <div key={v} className="drop-item" onClick={() => setApproval(v)}>
          <span style={{ flex: 1 }}>{l}</span>
          {approval === v && <span style={{ color: 'var(--accent)' }}>✓</span>}
        </div>
      ))}
    </div></div>
  );
}

function WorktreesPage() {
  return (
    <div className="page-scroll"><div className="page-inner">
      <div className="page-head"><div><h1>Worktrees</h1></div></div>
      <div className="model-card">
        <div><div className="model-name">Worktree root</div><div className="model-desc">Where Codex creates worktrees</div></div>
        <span className="model-desc mono">$CODEX_HOME/worktrees</span>
      </div>
    </div></div>
  );
}

function McpPage() {
  return (
    <div className="page-scroll"><div className="page-inner">
      <div className="page-head"><div><h1>MCP servers</h1><p className="page-desc">Connect tools via Model Context Protocol.</p></div></div>
      <div className="empty-note">No MCP servers connected</div>
      <button className="btn-primary sm" style={{ marginTop: 12 }}>Add server</button>
    </div></div>
  );
}
