import { useState } from 'react';
import { DiffIcon, CheckIcon, XIcon } from '../icons';

// Diff 视图：复刻 Codex 的 review diff 卡片
export default function DiffBlock({ file, hunks, onAccept, onReject }) {
  const [mode, setMode] = useState('unified');
  const [decision, setDecision] = useState(null);
  return (
    <div className="diff-block">
      <div className="diff-head">
        <span className="tool-icon"><DiffIcon /></span>
        <span className="tool-name">{file}</span>
        <div className="seg">
          <button className={mode === 'unified' ? 'on' : ''} onClick={() => setMode('unified')}>Unified</button>
          <button className={mode === 'split' ? 'on' : ''} onClick={() => setMode('split')}>Split</button>
        </div>
      </div>
      <div className="diff-body">
        {hunks.map((h, i) => (
          <div key={i} className="hunk">
            <div className="hunk-head">{h.head}</div>
            {h.lines.map((l, j) => (
              <div key={j} className={'dline ' + (l.t === '+' ? 'add' : l.t === '-' ? 'del' : 'ctx')}>
                <span className="sign">{l.t}</span>
                <span>{l.c}</span>
              </div>
            ))}
          </div>
        ))}
      </div>
      {!decision ? (
        <div className="diff-foot">
          <button className="btn-ghost danger" onClick={() => { setDecision('rejected'); onReject?.(); }}>
            <XIcon size={13} /> Reject
          </button>
          <button className="btn-ghost ok" onClick={() => { setDecision('accepted'); onAccept?.(); }}>
            <CheckIcon size={13} /> Accept
          </button>
        </div>
      ) : (
        <div className={'diff-decision ' + decision}>
          {decision === 'accepted' ? <><CheckIcon size={13} /> Changes accepted</> : <><XIcon size={13} /> Changes rejected</>}
        </div>
      )}
    </div>
  );
}
