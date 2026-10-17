import { CodexLogo } from '../icons';
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

export function AgentMessage({ msg }) {
  return (
    <div className="msg msg-agent">
      <div className="agent-avatar"><CodexLogo size={16} /></div>
      <div className="msg-agent-body">
        {msg.thinking && <ThinkingBlock text={msg.thinking} />}
        {msg.text && <div className="msg-text">{renderRich(msg.text)}</div>}
        {msg.tools?.map((t, i) => <ToolCard key={i} tool={t} />)}
        {msg.diff && <DiffBlock file={msg.diff.file} hunks={msg.diff.hunks} />}
      </div>
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
