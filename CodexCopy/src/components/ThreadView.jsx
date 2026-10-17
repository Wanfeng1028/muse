import { useState } from 'react';
import { CodexLogo, TerminalIcon, FileIcon, EditIcon, CheckIcon, ChevronRight } from './icons';

const TOOL_ICONS = { bash: <TerminalIcon />, read: <FileIcon />, edit: <EditIcon /> };

function Thinking({ text }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="thinking">
      <div className="thinking-head" onClick={() => setOpen(!open)}>
        <span style={{ display: 'inline-flex', transform: open ? 'rotate(90deg)' : 'none', transition: 'transform .15s' }}>
          <ChevronRight />
        </span>
        <span>Thought</span>
      </div>
      {open && <div className="thinking-body">{text}</div>}
    </div>
  );
}

function ToolCard({ tool }) {
  const [open, setOpen] = useState(false);
  const lines = tool.output.split('\n');
  return (
    <div className="tool-card">
      <div className="tool-head" onClick={() => setOpen(!open)}>
        <span className="tool-icon">{TOOL_ICONS[tool.name] || <TerminalIcon />}</span>
        <span className="tool-name">{tool.name} · {tool.target}</span>
        <span className="tool-status ok"><CheckIcon /> done</span>
        <span style={{ display: 'inline-flex', transform: open ? 'rotate(90deg)' : 'none', transition: 'transform .15s', color: 'var(--text-tertiary)' }}>
          <ChevronRight />
        </span>
      </div>
      {open && (
        <div className="tool-body">
          {lines.map((l, i) => (
            <div key={i} className={l.startsWith('+') ? 'added' : l.startsWith('-') ? 'removed' : ''}>{l}</div>
          ))}
        </div>
      )}
    </div>
  );
}

function renderText(text) {
  // 简单渲染 ``` 代码块
  const parts = text.split(/(```[\s\S]*?```)/g);
  return parts.map((p, i) => {
    if (p.startsWith('```')) {
      const code = p.replace(/```\w*\n?/, '').replace(/```$/, '');
      return (
        <div className="codeblock" key={i}>
          <div className="codeblock-head">code</div>
          <pre>{code}</pre>
        </div>
      );
    }
    return <div key={i} style={{ whiteSpace: 'pre-wrap', marginBottom: 8 }}>{p}</div>;
  });
}

function AgentMessage({ msg }) {
  return (
    <div className="msg msg-agent">
      <div className="agent-avatar"><CodexLogo size={16} /></div>
      <div className="msg-agent-body">
        {msg.thinking && <Thinking text={msg.thinking} />}
        {msg.text && <div className="msg-text">{renderText(msg.text)}</div>}
        {msg.tools && msg.tools.map((t, i) => <ToolCard key={i} tool={t} />)}
      </div>
    </div>
  );
}

export default function ThreadView({ thread, streaming }) {
  return (
    <div className="thread-scroll">
      <div className="thread-inner">
        {thread.messages.map((m, i) =>
          m.role === 'user' ? (
            <div className="msg msg-user" key={i}>
              <div className="bubble">{m.text}</div>
            </div>
          ) : (
            <AgentMessage key={i} msg={m} />
          )
        )}
        {streaming && (
          <div className="msg msg-agent">
            <div className="agent-avatar"><CodexLogo size={16} /></div>
            <div className="msg-agent-body">
              <div className="status-line"><span className="spinner" /> Working…</div>
              <div className="typing"><span /><span /><span /></div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
