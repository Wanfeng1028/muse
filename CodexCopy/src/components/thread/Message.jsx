import { useState } from 'react';
import { CodexLogo, CheckIcon, XIcon } from '../icons';
import ThinkingBlock from './ThinkingBlock';
import ToolCard from './ToolCard';
import CodeBlock from './CodeBlock';
import DiffBlock from './DiffBlock';

function renderRich(text) {
  const parts = text.split(/(```[\s\S]*?```)/g);
  return parts.map((p, i) => {
    if (p.startsWith('```')) {
      const m = p.match(/```(\w*)\n?([\s\S]*?)```$/);
      return <CodeBlock key={i} lang={m?.[1] || 'code'} code={(m?.[2] || '').trim()} />;
    }
    const t = p.trim();
    return t ? <div key={i} className="msg-para">{t}</div> : null;
  });
}

export function UserMessage({ text }) {
  return (
    <div className="msg msg-user">
      <div className="bubble">{text}</div>
    </div>
  );
}

export function AgentMessage({ msg, onApprove, onReject }) {
  return (
    <div className="msg msg-agent">
      <div className="agent-avatar"><CodexLogo size={16} /></div>
      <div className="msg-agent-body">
        {msg.thinking && <ThinkingBlock text={msg.thinking} />}
        {msg.text && <div className="msg-text">{renderRich(msg.text)}</div>}
        {msg.tools?.map((t, i) => <ToolCard key={i} tool={t} />)}
        {msg.diff && <DiffBlock file={msg.diff.file} hunks={msg.diff.hunks} />}
        {msg.needsApproval && msg.approval && (
          <ApprovalCard approval={msg.approval} onApprove={onApprove} onReject={onReject} />
        )}
      </div>
    </div>
  );
}

function ApprovalCard({ approval, onApprove, onReject }) {
  const [done, setDone] = useState(null);
  return (
    <div className="approval-card">
      <div className="approval-title">⚠️ Needs your confirmation</div>
      <div className="approval-name">{approval.title}</div>
      <div className="approval-desc">{approval.desc}</div>
      {!done ? (
        <div className="approval-actions">
          <button className="btn-ghost danger" onClick={() => { setDone('rejected'); onReject?.(); }}>
            <XIcon size={13} /> Reject
          </button>
          <button className="btn-primary sm" onClick={() => { setDone('approved'); onApprove?.(); }}>
            <CheckIcon size={13} /> Approve
          </button>
        </div>
      ) : (
        <div className={'diff-decision ' + (done === 'approved' ? 'accepted' : 'rejected')}>
          {done === 'approved' ? 'Approved' : 'Rejected'}
        </div>
      )}
    </div>
  );
}

export function StreamingMessage() {
  return (
    <div className="msg msg-agent">
      <div className="agent-avatar"><CodexLogo size={16} /></div>
      <div className="msg-agent-body">
        <div className="status-line"><span className="spinner" /> Working…</div>
        <div className="typing"><span /><span /><span /></div>
      </div>
    </div>
  );
}
