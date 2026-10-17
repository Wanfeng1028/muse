import { useState } from 'react';
import { TerminalIcon, FileIcon, EditIcon, CheckIcon, ChevronRight, DiffIcon } from '../icons';

const ICONS = { bash: <TerminalIcon />, read: <FileIcon />, edit: <EditIcon />, write: <EditIcon />, diff: <DiffIcon /> };
const LABELS = { bash: 'Run command', read: 'Read file', edit: 'Edit file', write: 'Write file', diff: 'View diff' };

export default function ToolCard({ tool }) {
  const [open, setOpen] = useState(false);
  const lines = (tool.output || '').split('\n');
  return (
    <div className="tool-card">
      <div className="tool-head" onClick={() => setOpen(!open)}>
        <span className="tool-icon">{ICONS[tool.name] || <TerminalIcon />}</span>
        <span className="tool-kind">{LABELS[tool.name] || tool.name}</span>
        <span className="tool-name">{tool.target}</span>
        <span className="tool-status ok"><CheckIcon size={12} /> done</span>
        <span className={'twisty' + (open ? ' open' : '')}><ChevronRight size={13} /></span>
      </div>
      {open && (
        <div className="tool-body">
          {lines.map((l, i) => (
            <div key={i} className={l.startsWith('+') && !l.startsWith('+++') ? 'added' : l.startsWith('-') && !l.startsWith('---') ? 'removed' : l.startsWith('@@') ? 'hunk' : ''}>{l}</div>
          ))}
        </div>
      )}
    </div>
  );
}
