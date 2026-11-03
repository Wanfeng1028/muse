import { FileIcon, FolderIcon, TerminalIcon, XIcon } from './icons';

// 右侧按需面板（新版 bundle 实测：多 Tab 制，面板叫 Changes 不是 Review）
// Changes / Terminal / Browser / Files
const TITLES = { changes: 'Changes', terminal: 'Terminal', browser: 'Browser', files: 'Files' };

export default function RightPanel({ panel, task, onClose }) {
  return (
    <div className="right-panel">
      <div className="rp-head">
        <span>{TITLES[panel] || panel}</span>
        <button className="icon-btn sm" onClick={onClose} title="Close panel"><XIcon size={13} /></button>
      </div>
      <div className="rp-body">
        {panel === 'changes' && (
          <>
            <div className="filter-menu-title">Changed files</div>
            {['src/auth/tokens.ts', 'src/auth/middleware.ts'].map((f) => (
              <div key={f} className="file-row">
                <FileIcon size={13} />
                <span className="file-name">{f}</span>
                <span className="diff-add">+12</span><span className="diff-del">−3</span>
              </div>
            ))}
            <pre className="rp-code">{`+ export function issueRefreshToken(userId) {
+   return jwt.sign({ sub: userId }, SECRET, { expiresIn: '7d' });
+ }`}</pre>
          </>
        )}
        {panel === 'terminal' && (
          <div className="mono-body">
            <div className="term-block">
              <div className="term-cmd"><span className="prompt">$</span> npm test -- auth</div>
              <div className="term-out">✓ 12 passed{'\n'}✓ 0 failed</div>
            </div>
          </div>
        )}
        {panel === 'browser' && (
          <div className="empty-note">Built-in browser — opens pages for Codex to read.</div>
        )}
        {panel === 'files' && (
          <>
            {['src/auth/tokens.ts', 'src/auth/middleware.ts', 'src/auth/index.ts', 'package.json'].map((f) => (
              <div key={f} className="file-row">
                <FileIcon size={13} />
                <span className="file-name">{f}</span>
              </div>
            ))}
          </>
        )}
      </div>
    </div>
  );
}
