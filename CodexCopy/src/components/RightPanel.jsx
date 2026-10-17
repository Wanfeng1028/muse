import { useState } from 'react';
import { FolderIcon, TerminalIcon, DiffIcon, FileIcon, CheckIcon, XIcon } from './icons';

// 右栏：多功能区（文件浏览 / 终端 / 代码查看 / 上下文），⌘1/2/3 切换
const TABS = [
  { id: 'files', label: 'Files', icon: <FolderIcon /> },
  { id: 'terminal', label: 'Terminal', icon: <TerminalIcon /> },
  { id: 'code', label: 'Code', icon: <DiffIcon /> },
  { id: 'context', label: 'Context', icon: <FileIcon /> },
];

function FileBrowser({ files }) {
  return (
    <div className="rp-body">
      {(files || []).map((f, i) => (
        <div key={i} className="file-row">
          <FileIcon size={13} />
          <span className="file-name">{f.name}</span>
          {f.modified && <span className="pill orange">M</span>}
        </div>
      ))}
      {(!files || files.length === 0) && <div className="empty-note">No files</div>}
    </div>
  );
}

function TerminalView({ runs }) {
  return (
    <div className="rp-body mono-body">
      {(runs || []).map((r, i) => (
        <div key={i} className="term-block">
          <div className="term-cmd"><span className="prompt">$</span> {r.cmd}</div>
          <div className="term-out">{r.out}</div>
        </div>
      ))}
      {(!runs || runs.length === 0) && <div className="empty-note">No commands yet</div>}
    </div>
  );
}

function CodeViewer({ files }) {
  const mod = (files || []).find((f) => f.modified);
  return (
    <div className="rp-body">
      {mod ? (
        <>
          <div className="codeblock-head"><span>{mod.name}</span></div>
          <pre className="rp-code">{`+ export function issueRefreshToken(userId) {
+   return jwt.sign({ sub: userId }, SECRET, { expiresIn: '7d' });
+ }`}</pre>
        </>
      ) : <div className="empty-note">Select a modified file</div>}
    </div>
  );
}

function ContextView() {
  return (
    <div className="rp-body">
      <div className="ctx-row"><span>Context window</span><span className="mono">42% used</span></div>
      <div className="ctx-bar"><div className="ctx-fill" style={{ width: '42%' }} /></div>
      <div className="ctx-row"><span>Added files</span><button className="mini-btn">+ Add</button></div>
      <div className="file-row"><FileIcon size={13} /><span className="file-name">src/auth/tokens.ts</span></div>
    </div>
  );
}

export default function RightPanel({ task }) {
  const [tab, setTab] = useState('files');
  return (
    <div className="right-panel">
      <div className="rp-tabs">
        {TABS.map((t) => (
          <button key={t.id} className={'rp-tab' + (tab === t.id ? ' active' : '')}
            onClick={() => setTab(t.id)} title={t.label}>
            <span className="rp-tab-icon">{t.icon}</span>
            <span>{t.label}</span>
          </button>
        ))}
      </div>
      {tab === 'files' && <FileBrowser files={task?.files} />}
      {tab === 'terminal' && <TerminalView runs={task?.terminal} />}
      {tab === 'code' && <CodeViewer files={task?.files} />}
      {tab === 'context' && <ContextView />}
    </div>
  );
}
