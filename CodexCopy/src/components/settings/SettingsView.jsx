import { useState } from 'react';
import { SettingsIcon, PaletteIcon, CpuIcon, GitIcon, PlugIcon, FolderIcon, XIcon } from '../icons';

// 复刻 Codex 设置中心的页面结构（逆向自 general/appearance/agent/git/mcp/plugins settings chunks）
const PAGES = [
  { id: 'general', label: 'General', icon: <SettingsIcon /> },
  { id: 'appearance', label: 'Appearance', icon: <PaletteIcon /> },
  { id: 'models', label: 'Models', icon: <CpuIcon /> },
  { id: 'git', label: 'Git', icon: <GitIcon /> },
  { id: 'mcp', label: 'MCP Servers', icon: <PlugIcon /> },
  { id: 'plugins', label: 'Extensions', icon: <FolderIcon /> },
];

function Row({ label, desc, children }) {
  return (
    <div className="set-row">
      <div className="set-row-info">
        <div className="set-row-label">{label}</div>
        {desc && <div className="set-row-desc">{desc}</div>}
      </div>
      <div className="set-row-ctrl">{children}</div>
    </div>
  );
}

function Toggle({ on, onChange }) {
  return (
    <button className={'toggle' + (on ? ' on' : '')} onClick={() => onChange(!on)} role="switch" aria-checked={on}>
      <span className="knob" />
    </button>
  );
}

function Select({ value, options, onChange }) {
  return (
    <select className="select" value={value} onChange={(e) => onChange(e.target.value)}>
      {options.map((o) => <option key={o} value={o}>{o}</option>)}
    </select>
  );
}

function GeneralPage() {
  const [s, setS] = useState({ telemetry: true, autoUpdate: true, compact: false });
  const set = (k) => (v) => setS({ ...s, [k]: v });
  return (
    <div>
      <h2>General</h2>
      <Row label="Telemetry" desc="Send anonymous usage data to improve Codex">
        <Toggle on={s.telemetry} onChange={set('telemetry')} />
      </Row>
      <Row label="Auto update" desc="Download and install updates automatically">
        <Toggle on={s.autoUpdate} onChange={set('autoUpdate')} />
      </Row>
      <Row label="Compact context" desc="Automatically summarize when context fills up">
        <Toggle on={s.compact} onChange={set('compact')} />
      </Row>
    </div>
  );
}

function AppearancePage({ theme, onThemeChange }) {
  const [font, setFont] = useState('System');
  return (
    <div>
      <h2>Appearance</h2>
      <Row label="Theme" desc="Color scheme for the interface">
        <Select value={theme === 'dark' ? 'Dark' : 'Light'} options={['Dark', 'Light']} onChange={(v) => onThemeChange(v === 'Dark' ? 'dark' : 'light')} />
      </Row>
      <Row label="Font" desc="Interface font">
        <Select value={font} options={['System', 'Inter', 'SF Pro']} onChange={setFont} />
      </Row>
      <div className="theme-preview">
        <div className="tp-card dark" onClick={() => onThemeChange('dark')}><span>Dark</span>{theme === 'dark' && <span className="tp-check">●</span>}</div>
        <div className="tp-card light" onClick={() => onThemeChange('light')}><span>Light</span>{theme === 'light' && <span className="tp-check">●</span>}</div>
      </div>
    </div>
  );
}

function ModelsPage() {
  const [def, setDef] = useState('gpt-5.2');
  return (
    <div>
      <h2>Models</h2>
      <Row label="Default model" desc="Used for new threads">
        <Select value={def} options={['gpt-5.2', 'gpt-5.1', 'gpt-5-mini']} onChange={setDef} />
      </Row>
      {['gpt-5.2', 'gpt-5.1', 'gpt-5-mini'].map((m) => (
        <div className="model-card" key={m}>
          <div>
            <div className="model-name">{m} {m === def && <span className="pill">default</span>}</div>
            <div className="model-desc">{m === 'gpt-5.2' ? 'Most capable, best for complex tasks' : m === 'gpt-5.1' ? 'Balanced speed and quality' : 'Fastest, good for simple tasks'}</div>
          </div>
          {m !== def && <button className="btn-ghost" onClick={() => setDef(m)}>Set default</button>}
        </div>
      ))}
    </div>
  );
}

function GitPage() {
  const [s, setS] = useState({ worktree: true, autoCommit: false });
  const set = (k) => (v) => setS({ ...s, [k]: v });
  return (
    <div>
      <h2>Git</h2>
      <Row label="Use git worktree" desc="Isolate each task in its own worktree">
        <Toggle on={s.worktree} onChange={set('worktree')} />
      </Row>
      <Row label="Auto commit" desc="Commit changes automatically after each task">
        <Toggle on={s.autoCommit} onChange={set('autoCommit')} />
      </Row>
    </div>
  );
}

function McpPage() {
  const [servers] = useState([
    { name: 'filesystem', cmd: 'npx @modelcontextprotocol/server-filesystem', on: true },
    { name: 'github', cmd: 'npx @modelcontextprotocol/server-github', on: false },
  ]);
  const [on, setOn] = useState({ filesystem: true, github: false });
  return (
    <div>
      <h2>MCP Servers</h2>
      <p className="page-desc">Model Context Protocol servers extend Codex with tools.</p>
      {servers.map((sv) => (
        <div className="model-card" key={sv.name}>
          <div>
            <div className="model-name">{sv.name}</div>
            <div className="model-desc mono">{sv.cmd}</div>
          </div>
          <Toggle on={on[sv.name]} onChange={(v) => setOn({ ...on, [sv.name]: v })} />
        </div>
      ))}
      <button className="btn-ghost" style={{ marginTop: 12 }}>+ Add server</button>
    </div>
  );
}

function PluginsPage() {
  return (
    <div>
      <h2>Extensions</h2>
      <p className="page-desc">Bundled and installed extensions.</p>
      {['openai-bundled', 'chrome-remote'].map((p) => (
        <div className="model-card" key={p}>
          <div>
            <div className="model-name">{p}</div>
            <div className="model-desc">Enabled</div>
          </div>
          <span className="pill green">on</span>
        </div>
      ))}
    </div>
  );
}

const PAGE_BODY = (theme, onThemeChange) => ({ general: <GeneralPage />, appearance: <AppearancePage theme={theme} onThemeChange={onThemeChange} />, models: <ModelsPage />, git: <GitPage />, mcp: <McpPage />, plugins: <PluginsPage /> });

export default function SettingsView({ onClose, theme, onThemeChange }) {
  const [page, setPage] = useState('general');
  return (
    <div className="settings-view">
      <div className="settings-head">
        <h1>Codex settings</h1>
        <button className="icon-btn" onClick={onClose}><XIcon /></button>
      </div>
      <div className="settings-body">
        <nav className="settings-nav">
          {PAGES.map((p) => (
            <button key={p.id} className={'set-nav-item' + (page === p.id ? ' active' : '')} onClick={() => setPage(p.id)}>
              <span className="set-nav-icon">{p.icon}</span>
              {p.label}
            </button>
          ))}
        </nav>
        <div className="settings-content">{PAGE_BODY(theme, onThemeChange)[page]}</div>
      </div>
    </div>
  );
}
